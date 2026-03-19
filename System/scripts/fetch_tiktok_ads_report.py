#!/usr/bin/env python3
"""TikTok広告の実績データを取得して保存する。"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import posixpath
import sys
import time
import zipfile
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import requests
from gspread.exceptions import APIError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System"))

from sheets_manager import get_client  # noqa: E402
from setup_ads_sheet import TIKTOK_HEADERS, apply_formatting  # noqa: E402


DEFAULT_AUTH_PATH = ROOT / "System" / "credentials" / "tiktok_marketing_api.json"
DEFAULT_ACCOUNTS_PATH = ROOT / "System" / "credentials" / "tiktok_ads.json"
OUTPUT_DIR = ROOT / "System" / "data" / "tiktok_ads_export"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
TAB_NAME = "TikTok"
TARGET_BUSINESS_NAMES = {"スキルプラス"}

BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
REPORT_ENDPOINT = f"{BASE_URL}/report/integrated/get/"
ADVERTISER_ENDPOINT = f"{BASE_URL}/oauth2/advertiser/get/"
AD_ENDPOINT = f"{BASE_URL}/ad/get/"
ADGROUP_ENDPOINT = f"{BASE_URL}/adgroup/get/"
ADS_MANAGER_CDP_URL = "http://127.0.0.1:9224"
ADS_MANAGER_CREATIVE_URL = "https://ads.tiktok.com/i18n/manage/creative?aadvid={advertiser_id}&st={start_date}&et={end_date}"
ADS_MANAGER_REQUEST_HEADERS = (
    "accept",
    "content-type",
    "origin",
    "referer",
    "trace-log-adv-id",
    "x-csrftoken",
)
ADS_MANAGER_PAGE_SIZE = 100
BULK_EXPORT_WAIT_SECONDS = 120
OOXML_NS = {
    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkg": "http://schemas.openxmlformats.org/package/2006/relationships",
}
BULK_EXPORT_FIELD_ALIASES = {
    "ad_id": ("Ad ID",),
    "destination": ("Destination",),
    "instant_page_id": ("Instant page ID ", "Instant page ID"),
    "website_type": ("Website type",),
    "web_url": ("Web URL",),
    "deeplink_url": ("Deeplink URL",),
    "fallback_website_url": ("Fallback Website URL",),
    "click_tracking_url": ("Click Tracking URL",),
    "optimization_location": ("Optimization location",),
    "sales_destination": ("Sales destination",),
    "campaign_type": ("Campaign type",),
}

DEFAULT_METRICS = ["spend", "impressions", "clicks"]
DEFAULT_DIMENSIONS_BY_LEVEL = {
    "AUCTION_CAMPAIGN": ["stat_time_day", "campaign_id"],
    "AUCTION_ADGROUP": ["stat_time_day", "adgroup_id"],
    "AUCTION_AD": ["stat_time_day", "ad_id"],
}
SHEET_DIMENSIONS = ["stat_time_day", "ad_id"]
SHEET_METRICS = [
    "spend",
    "impressions",
    "clicks",
    "reach",
    "frequency",
    "cpc",
    "cpm",
    "ctr",
    "conversion",
    "video_play_actions",
    "video_watched_2s",
    "video_watched_6s",
    "video_views_p100",
]
AD_FIELDS = [
    "ad_id",
    "ad_name",
    "campaign_id",
    "campaign_name",
    "adgroup_id",
    "adgroup_name",
    "secondary_status",
    "operation_status",
    "create_time",
    "modify_time",
    "video_id",
    "image_ids",
    "landing_page_url",
    "landing_page_urls",
    "smart_plus_ad_id",
    "campaign_automation_type",
    "card_id",
    "ad_format",
    "creative_type",
    "image_mode",
    "optimization_event",
]
ADGROUP_FIELDS = [
    "adgroup_id",
    "promotion_type",
    "optimization_goal",
]
TEXT_HEADERS = {
    "広告アカウントID",
    "キャンペーンID",
    "広告グループID",
    "広告ID",
    "CR識別キー",
    "メディアID",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_auth(path: Path) -> dict[str, Any]:
    auth = load_json(path)
    required = ["app_id", "app_secret", "access_token"]
    missing = [key for key in required if not str(auth.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"TikTok認証情報が不足しています: {', '.join(missing)}")
    return auth


def load_account_details(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    data = load_json(path)
    details: dict[str, dict[str, str]] = {}
    for account in data.get("ad_accounts", []):
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        if not advertiser_id:
            continue
        details[advertiser_id] = {
            key: str(value).strip() if value is not None else ""
            for key, value in account.items()
        }
    return details


def load_account_names(path: Path) -> dict[str, str]:
    details = load_account_details(path)
    return {
        advertiser_id: detail.get("advertiser_name", "")
        for advertiser_id, detail in details.items()
        if detail.get("advertiser_name", "")
    }


def filter_advertisers_by_business(
    advertiser_ids: list[str],
    account_details: dict[str, dict[str, str]],
    business_names: set[str],
) -> list[str]:
    if not business_names:
        return advertiser_ids
    filtered: list[str] = []
    for advertiser_id in advertiser_ids:
        business_name = account_details.get(advertiser_id, {}).get("business_name", "")
        if business_name in business_names:
            filtered.append(advertiser_id)
    return filtered


def parse_csv_list(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default[:]
    return [item.strip() for item in value.split(",") if item.strip()]


def default_date_range() -> tuple[str, str]:
    yesterday = date.today() - timedelta(days=1)
    value = yesterday.isoformat()
    return value, value


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "addness-tiktok-report-fetcher/1.0"})
    return session


def api_get(
    session: requests.Session,
    url: str,
    auth: dict[str, Any],
    params: dict[str, Any],
) -> dict[str, Any]:
    merged = {
        "app_id": auth["app_id"],
        "secret": auth["app_secret"],
        **params,
    }
    response = session.get(
        url,
        params=merged,
        headers={"Access-Token": auth["access_token"]},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        message = payload.get("message", "TikTok API error")
        request_id = payload.get("request_id", "")
        raise RuntimeError(f"{message} request_id={request_id}")
    return payload


def resolve_advertisers(
    session: requests.Session,
    auth: dict[str, Any],
    explicit_ids: list[str],
) -> list[str]:
    authorized = [str(item).strip() for item in auth.get("authorized_advertiser_ids", []) if str(item).strip()]
    if explicit_ids:
        missing = [advertiser_id for advertiser_id in explicit_ids if advertiser_id not in authorized]
        if missing:
            raise RuntimeError(
                "指定した advertiser_id が認可一覧にありません: " + ", ".join(missing)
            )
        return explicit_ids

    if authorized:
        return authorized

    payload = api_get(session, ADVERTISER_ENDPOINT, auth, {})
    return [
        str(item.get("advertiser_id") or "").strip()
        for item in payload.get("data", {}).get("list", [])
        if str(item.get("advertiser_id") or "").strip()
    ]


def list_advertisers(session: requests.Session, auth: dict[str, Any], account_names: dict[str, str]) -> None:
    payload = api_get(session, ADVERTISER_ENDPOINT, auth, {})
    rows = payload.get("data", {}).get("list", [])
    for row in rows:
        advertiser_id = str(row.get("advertiser_id") or "").strip()
        advertiser_name = account_names.get(advertiser_id) or str(row.get("advertiser_name") or "").strip()
        print(f"{advertiser_id}\t{advertiser_name}")


def fetch_report_rows(
    session: requests.Session,
    auth: dict[str, Any],
    advertiser_id: str,
    start_date: str,
    end_date: str,
    dimensions: list[str],
    metrics: list[str],
    data_level: str,
    page_size: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1

    while True:
        payload = api_get(
            session,
            REPORT_ENDPOINT,
            auth,
            {
                "advertiser_id": advertiser_id,
                "service_type": "AUCTION",
                "report_type": "BASIC",
                "data_level": data_level,
                "dimensions": json.dumps(dimensions, ensure_ascii=False),
                "metrics": json.dumps(metrics, ensure_ascii=False),
                "start_date": start_date,
                "end_date": end_date,
                "page": page,
                "page_size": page_size,
            },
        )

        data = payload.get("data", {})
        current_rows = data.get("list", [])
        rows.extend(current_rows)

        page_info = data.get("page_info", {})
        total_page = int(page_info.get("total_page") or 1)
        if page >= total_page:
            break

        page += 1
        time.sleep(0.5)

    return rows


def fetch_ad_metadata(
    session: requests.Session,
    auth: dict[str, Any],
    advertiser_id: str,
    ad_ids: list[str],
) -> dict[str, dict[str, Any]]:
    metadata_by_ad: dict[str, dict[str, Any]] = {}
    unique_ids = sorted({str(ad_id).strip() for ad_id in ad_ids if str(ad_id).strip()})

    for start in range(0, len(unique_ids), 100):
        batch = unique_ids[start:start + 100]
        page = 1
        while True:
            payload = api_get(
                session,
                AD_ENDPOINT,
                auth,
                {
                    "advertiser_id": advertiser_id,
                    "filtering": json.dumps({"ad_ids": batch}, ensure_ascii=False),
                    "fields": json.dumps(AD_FIELDS, ensure_ascii=False),
                    "page_size": min(100, len(batch)),
                    "page": page,
                },
            )
            data = payload.get("data", {})
            for item in data.get("list", []):
                ad_id = str(item.get("ad_id") or "").strip()
                if ad_id:
                    metadata_by_ad[ad_id] = item

            page_info = data.get("page_info", {})
            total_page = int(page_info.get("total_page") or 1)
            if page >= total_page:
                break
            page += 1
            time.sleep(0.2)

    return metadata_by_ad


def fetch_adgroup_metadata(
    session: requests.Session,
    auth: dict[str, Any],
    advertiser_id: str,
    adgroup_ids: list[str],
) -> dict[str, dict[str, Any]]:
    metadata_by_adgroup: dict[str, dict[str, Any]] = {}
    unique_ids = sorted({str(adgroup_id).strip() for adgroup_id in adgroup_ids if str(adgroup_id).strip()})

    for start in range(0, len(unique_ids), 100):
        batch = unique_ids[start:start + 100]
        page = 1
        while True:
            payload = api_get(
                session,
                ADGROUP_ENDPOINT,
                auth,
                {
                    "advertiser_id": advertiser_id,
                    "filtering": json.dumps({"adgroup_ids": batch}, ensure_ascii=False),
                    "fields": json.dumps(ADGROUP_FIELDS, ensure_ascii=False),
                    "page_size": min(100, len(batch)),
                    "page": page,
                },
            )
            data = payload.get("data", {}) or {}
            for item in data.get("list", []) or []:
                adgroup_id = normalize_lookup_id(item.get("adgroup_id", ""))
                if adgroup_id:
                    metadata_by_adgroup[adgroup_id] = item

            page_info = data.get("page_info", {}) or {}
            total_page = int(page_info.get("total_page") or 1)
            if page >= total_page:
                break
            page += 1
            time.sleep(0.2)

    return metadata_by_adgroup


def has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in {"", "[]", "None", "null"}
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def find_click_center_by_text(page, label: str) -> dict[str, float] | None:
    return page.evaluate(
        """
        (targetLabel) => {
          const elements = Array.from(document.querySelectorAll('ks-button-915, [data-testid], button, div, span'));
          const preferred = [];
          const fallback = [];
          for (const el of elements) {
            const text = (el.innerText || '').trim();
            if (text !== targetLabel) {
              continue;
            }
            const rect = el.getBoundingClientRect();
            if (!rect.width || !rect.height) {
              continue;
            }
            const tag = (el.tagName || '').toLowerCase();
            const dataTestid = el.getAttribute('data-testid') || '';
            const payload = {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
            if (tag.startsWith('ks-button') || dataTestid.startsWith('menu-bulk-import-export-entry-menu')) {
              preferred.push(payload);
            } else {
              fallback.push(payload);
            }
          }
          return preferred[0] || fallback[0] || null;
        }
        """,
        label,
    )


def click_text_button(page, label: str, timeout_seconds: int = 15) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        center = find_click_center_by_text(page, label)
        if center:
            page.mouse.click(center["x"], center["y"])
            return
        page.wait_for_timeout(500)
    raise RuntimeError(f"TikTok Ads Manager でボタンを見つけられませんでした: {label}")


def extract_ads_manager_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() in ADS_MANAGER_REQUEST_HEADERS and value
    }


def wait_for_ads_manager_request(page, holder: dict[str, Any], timeout_seconds: int = 20) -> None:
    deadline = time.time() + timeout_seconds
    while "url" not in holder and time.time() < deadline:
        page.wait_for_timeout(1000)
    if "url" not in holder:
        raise RuntimeError("TikTok Ads Manager の ad/list リクエストを取得できませんでした")


def fetch_ads_manager_ad_metadata(
    advertiser_id: str,
    start_date: str,
    end_date: str,
    target_ad_ids: list[str],
) -> dict[str, dict[str, Any]]:
    needed_ids = {normalize_lookup_id(ad_id) for ad_id in target_ad_ids if normalize_lookup_id(ad_id)}
    if not needed_ids:
        return {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(ADS_MANAGER_CDP_URL)
        if not browser.contexts:
            raise RuntimeError("TikTok Ads Manager のログイン済み Chrome コンテキストが見つかりません")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            request_holder: dict[str, Any] = {}

            def handle_request(request) -> None:
                if "statistics/op/ad/list" not in request.url:
                    return
                if "url" in request_holder:
                    return
                request_holder["url"] = request.url
                request_holder["body"] = request.post_data or "{}"
                request_holder["headers"] = request.headers

            page.on("request", handle_request)
            page.goto(
                ADS_MANAGER_CREATIVE_URL.format(
                    advertiser_id=advertiser_id,
                    start_date=start_date,
                    end_date=end_date,
                ),
                wait_until="domcontentloaded",
                timeout=120000,
            )
            wait_for_ads_manager_request(page, request_holder)

            request_url = request_holder["url"]
            request_headers = extract_ads_manager_headers(request_holder["headers"])
            request_body = json.loads(request_holder["body"])
            request_body.setdefault("common_req", {})
            request_body["common_req"]["page_size"] = ADS_MANAGER_PAGE_SIZE

            metadata_by_ad: dict[str, dict[str, Any]] = {}
            current_page = 1
            total_pages = 1

            while current_page <= total_pages:
                request_body["common_req"]["page"] = current_page
                payload = page.evaluate(
                    """
                    async ({url, body, headers}) => {
                      const response = await fetch(url, {
                        method: 'POST',
                        credentials: 'include',
                        headers,
                        body: JSON.stringify(body),
                      });
                      const text = await response.text();
                      try {
                        return {status: response.status, json: JSON.parse(text)};
                      } catch (error) {
                        return {status: response.status, text: text.slice(0, 500)};
                      }
                    }
                    """,
                    {
                        "url": request_url,
                        "body": request_body,
                        "headers": request_headers,
                    },
                )
                status = int(payload.get("status") or 0)
                if status != 200:
                    raise RuntimeError(
                        f"TikTok Ads Manager fallback の取得に失敗しました: advertiser_id={advertiser_id} status={status}"
                    )
                parsed = payload.get("json")
                if not isinstance(parsed, dict):
                    preview = str(payload.get("text") or "")[:200]
                    raise RuntimeError(
                        f"TikTok Ads Manager fallback のレスポンスを解釈できません: advertiser_id={advertiser_id} body={preview}"
                    )
                data = parsed.get("data", {}) or {}
                pagination = data.get("pagination", {}) or {}
                total_pages = int(pagination.get("page_count") or 1)
                for item in data.get("table", []) or []:
                    ad_id = normalize_lookup_id(item.get("ad_id"))
                    if not ad_id:
                        continue
                    metadata_by_ad[ad_id] = item
                if needed_ids.issubset(metadata_by_ad.keys()):
                    break
                current_page += 1
                time.sleep(0.2)

            return metadata_by_ad
        finally:
            try:
                page.close()
            except Exception:
                pass


def fetch_ads_manager_bulk_export_blob(
    advertiser_id: str,
    start_date: str,
    end_date: str,
) -> bytes:
    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(ADS_MANAGER_CDP_URL)
        if not browser.contexts:
            raise RuntimeError("TikTok Ads Manager のログイン済み Chrome コンテキストが見つかりません")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            holder: dict[str, Any] = {
                "job_id": "",
                "xlsx_body": None,
            }

            def handle_response(response) -> None:
                url = response.url
                try:
                    if "/helper/download/launch/" in url and response.request.method == "POST":
                        payload = json.loads(response.text())
                        if payload.get("code") != 0:
                            holder["launch_error"] = payload.get("msg") or "bulk export launch failed"
                            return
                        holder["job_id"] = str(payload.get("data", {}).get("job_id") or "").strip()
                        return

                    if "/helper/download/check/" not in url:
                        return
                    job_id = str(holder.get("job_id") or "").strip()
                    if job_id and job_id not in url:
                        return
                    body = response.body()
                    if body[:2] == b"PK":
                        holder["xlsx_body"] = body
                except Exception as exc:
                    holder.setdefault("response_errors", []).append(str(exc))

            page.on("response", handle_response)
            page.goto(
                ADS_MANAGER_CREATIVE_URL.format(
                    advertiser_id=advertiser_id,
                    start_date=start_date,
                    end_date=end_date,
                ),
                wait_until="domcontentloaded",
                timeout=120000,
            )
            page.wait_for_timeout(5000)
            click_text_button(page, "Bulk export/import", timeout_seconds=25)
            page.wait_for_timeout(1000)
            click_text_button(page, "Filtered ads")
            page.wait_for_timeout(1500)
            click_text_button(page, "All")

            deadline = time.time() + BULK_EXPORT_WAIT_SECONDS
            while time.time() < deadline:
                if holder.get("launch_error"):
                    raise RuntimeError(str(holder["launch_error"]))
                if holder.get("xlsx_body") is not None:
                    return holder["xlsx_body"]
                page.wait_for_timeout(1000)

            raise RuntimeError(
                f"TikTok Bulk Export の完了を待てませんでした: advertiser_id={advertiser_id} job_id={holder.get('job_id') or 'unknown'}"
            )
        finally:
            try:
                page.close()
            except Exception:
                pass


def build_smart_plus_procedural_targets(
    rows: list[dict[str, str]],
    metadata_by_ad: dict[str, dict[str, Any]],
) -> dict[str, str]:
    targets: dict[str, str] = {}
    for row in rows:
        ad_id = normalize_lookup_id(row.get("ad_id", ""))
        if not ad_id:
            continue
        metadata = metadata_by_ad.get(ad_id, {})
        if not is_smart_plus_metadata(metadata):
            continue
        if select_landing_page_url(metadata):
            continue
        creative_id = normalize_lookup_id(metadata.get("smart_plus_ad_id", "")) or ad_id
        if creative_id:
            targets[ad_id] = creative_id
    return targets


def fetch_ads_manager_smart_plus_procedural_metadata(
    advertiser_id: str,
    start_date: str,
    end_date: str,
    creative_targets: dict[str, str],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, str]]]:
    if not creative_targets:
        return {}, []

    with sync_playwright() as playwright:
        browser = playwright.chromium.connect_over_cdp(ADS_MANAGER_CDP_URL)
        if not browser.contexts:
            raise RuntimeError("TikTok Ads Manager のログイン済み Chrome コンテキストが見つかりません")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(
                ADS_MANAGER_CREATIVE_URL.format(
                    advertiser_id=advertiser_id,
                    start_date=start_date,
                    end_date=end_date,
                ),
                wait_until="domcontentloaded",
                timeout=120000,
            )
            page.wait_for_timeout(3000)
            payload = page.evaluate(
                """
                async ({ advertiserId, targets }) => {
                  const results = [];
                  for (const item of targets) {
                    const url =
                      `https://ads.tiktok.com/mi/api/v3/i18n/perf/creative/procedural_detail/?aadvid=${advertiserId}` +
                      `&creative_id=${item.creative_id}&creative_material_mode=6`;
                    try {
                      const response = await fetch(url, { credentials: 'include' });
                      const json = await response.json();
                      results.push({
                        ad_id: item.ad_id,
                        creative_id: item.creative_id,
                        status: response.status,
                        code: json?.code ?? null,
                        msg: json?.msg ?? '',
                        data: json?.data ?? {},
                      });
                    } catch (error) {
                      results.push({
                        ad_id: item.ad_id,
                        creative_id: item.creative_id,
                        status: 0,
                        code: null,
                        msg: String(error),
                        data: {},
                      });
                    }
                  }
                  return results;
                }
                """,
                {
                    "advertiserId": advertiser_id,
                    "targets": [
                        {"ad_id": ad_id, "creative_id": creative_id}
                        for ad_id, creative_id in creative_targets.items()
                    ],
                },
            )
            metadata_by_ad: dict[str, dict[str, Any]] = {}
            errors: list[dict[str, str]] = []
            for item in payload:
                ad_id = normalize_lookup_id(item.get("ad_id", ""))
                creative_id = normalize_lookup_id(item.get("creative_id", ""))
                status = int(item.get("status") or 0)
                code = item.get("code")
                data = item.get("data") if isinstance(item.get("data"), dict) else {}
                if status == 200 and code == 0:
                    metadata_by_ad[ad_id] = {
                        "creative_external_url": str(data.get("external_url") or "").strip(),
                        "creative_open_url": str(data.get("open_url") or "").strip(),
                        "creative_name": str(data.get("creative_name") or "").strip(),
                        "creative_material_mode": "6",
                        "resolved_creative_id": creative_id,
                    }
                    track_url = data.get("track_url") or []
                    if isinstance(track_url, list) and track_url:
                        metadata_by_ad[ad_id]["creative_click_tracking_url"] = str(track_url[0] or "").strip()
                    action_track_url = data.get("action_track_url") or []
                    if isinstance(action_track_url, list) and action_track_url:
                        metadata_by_ad[ad_id]["creative_action_track_url"] = str(action_track_url[0] or "").strip()
                    multi_dest_list = data.get("multi_dest_list") or []
                    if isinstance(multi_dest_list, list) and multi_dest_list:
                        metadata_by_ad[ad_id]["creative_multi_dest_list"] = multi_dest_list
                    continue
                errors.append(
                    {
                        "advertiser_id": advertiser_id,
                        "ad_id": ad_id,
                        "creative_id": creative_id,
                        "status": str(status),
                        "code": "" if code is None else str(code),
                        "error": str(item.get("msg") or "procedural_detail failed"),
                    }
                )
            return metadata_by_ad, errors
        finally:
            try:
                page.close()
            except Exception:
                pass


def merge_fallback_metadata(
    base_metadata: dict[str, dict[str, Any]],
    fallback_metadata: dict[str, dict[str, Any]],
) -> None:
    for ad_id, values in fallback_metadata.items():
        target = base_metadata.setdefault(ad_id, {})
        for key, value in values.items():
            if has_meaningful_value(value):
                target[key] = value


def merge_bulk_export_metadata_into_ads(
    base_metadata: dict[str, dict[str, Any]],
    bulk_export_metadata: dict[str, dict[str, Any]],
) -> None:
    for ad_id, target in base_metadata.items():
        candidate_ids = [
            normalize_lookup_id(target.get("smart_plus_ad_id", "")),
            normalize_lookup_id(target.get("creative_id", "")),
            normalize_lookup_id(ad_id),
        ]
        for candidate_id in candidate_ids:
            if not candidate_id:
                continue
            values = bulk_export_metadata.get(candidate_id)
            if not values:
                continue
            for key, value in values.items():
                if has_meaningful_value(value):
                    target[key] = value
            break


def merge_adgroup_metadata_into_ads(
    ad_metadata: dict[str, dict[str, Any]],
    adgroup_metadata: dict[str, dict[str, Any]],
) -> None:
    for metadata in ad_metadata.values():
        adgroup_id = normalize_lookup_id(metadata.get("adgroup_id", ""))
        if not adgroup_id:
            continue
        group_values = adgroup_metadata.get(adgroup_id, {})
        for key, value in group_values.items():
            if has_meaningful_value(value):
                metadata[key] = value


def find_missing_website_landing_page_ad_ids(
    rows: list[dict[str, str]],
    metadata_by_ad: dict[str, dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    for row in rows:
        ad_id = normalize_lookup_id(row.get("ad_id", ""))
        if not ad_id:
            continue
        metadata = metadata_by_ad.get(ad_id, {})
        if str(metadata.get("promotion_type") or "").strip() != "WEBSITE":
            continue
        if select_landing_page_url(metadata):
            continue
        missing.append(ad_id)
    return sorted(set(missing))


def find_missing_landing_page_ad_ids(
    rows: list[dict[str, str]],
    metadata_by_ad: dict[str, dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    for row in rows:
        ad_id = normalize_lookup_id(row.get("ad_id", ""))
        if not ad_id:
            continue
        metadata = metadata_by_ad.get(ad_id, {})
        if select_landing_page_url(metadata):
            continue
        missing.append(ad_id)
    return sorted(set(missing))


def find_missing_non_smart_landing_page_ad_ids(
    rows: list[dict[str, str]],
    metadata_by_ad: dict[str, dict[str, Any]],
) -> list[str]:
    missing: list[str] = []
    for row in rows:
        ad_id = normalize_lookup_id(row.get("ad_id", ""))
        if not ad_id:
            continue
        metadata = metadata_by_ad.get(ad_id, {})
        if is_smart_plus_metadata(metadata):
            continue
        if select_landing_page_url(metadata):
            continue
        missing.append(ad_id)
    return sorted(set(missing))


def flatten_rows(
    advertiser_id: str,
    advertiser_name: str,
    report_rows: list[dict[str, Any]],
) -> list[dict[str, str]]:
    flattened: list[dict[str, str]] = []
    for row in report_rows:
        item: dict[str, str] = {
            "advertiser_id": advertiser_id,
            "advertiser_name": advertiser_name,
        }
        for key, value in (row.get("dimensions") or {}).items():
            item[str(key)] = str(value)
        for key, value in (row.get("metrics") or {}).items():
            item[str(key)] = str(value)
        flattened.append(item)
    return flattened


def build_output_fields(rows: list[dict[str, str]], dimensions: list[str], metrics: list[str]) -> list[str]:
    base = ["advertiser_id", "advertiser_name"]
    ordered = base + dimensions + metrics
    extras = sorted(
        {
            key
            for row in rows
            for key in row.keys()
            if key not in ordered
        }
    )
    return ordered + extras


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")


def build_output_path(
    explicit_output: str | None,
    start_date: str,
    end_date: str,
    fmt: str,
) -> Path:
    if explicit_output:
        return Path(explicit_output)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = "csv" if fmt == "csv" else "json"
    filename = f"tiktok_ads_report_{start_date}_{end_date}_{timestamp}.{suffix}"
    return OUTPUT_DIR / filename


def normalize_stat_day(value: str) -> str:
    return str(value or "").strip().split(" ")[0]


def normalize_lookup_id(value: str | Any) -> str:
    text = str(value or "").strip()
    if text.startswith("'"):
        text = text[1:]
    if text.startswith("id:"):
        text = text.split(":", 1)[1]
    if text.endswith(".0"):
        integer, decimal = text.rsplit(".", 1)
        if decimal == "0":
            text = integer
    return text


def column_letters_to_index(reference: str) -> int:
    letters = []
    for char in reference:
        if char.isalpha():
            letters.append(char.upper())
        else:
            break
    number = 0
    for char in letters:
        number = number * 26 + (ord(char) - ord("A") + 1)
    return max(number - 1, 0)


def read_excel_cell(cell, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.findall(".//a:t", OOXML_NS))
    value_node = cell.find("a:v", OOXML_NS)
    if value_node is None:
        return ""
    raw = value_node.text or ""
    if cell_type == "s":
        return shared_strings[int(raw)]
    return raw


def parse_first_sheet_xlsx(blob: bytes) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        shared_strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("a:si", OOXML_NS):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//a:t", OOXML_NS)))

        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationship_map = {
            rel.attrib["Id"]: rel.attrib["Target"]
            for rel in rels.findall("pkg:Relationship", OOXML_NS)
        }
        first_sheet = workbook.find("a:sheets/a:sheet", OOXML_NS)
        if first_sheet is None:
            return []
        relation_id = first_sheet.attrib["{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"]
        target = relationship_map[relation_id]
        sheet_path = posixpath.normpath("xl/" + target.lstrip("/"))
        worksheet = ET.fromstring(archive.read(sheet_path))

        row_dicts: list[dict[int, str]] = []
        max_index = 0
        for row in worksheet.findall(".//a:sheetData/a:row", OOXML_NS):
            values_by_index: dict[int, str] = {}
            for cell in row.findall("a:c", OOXML_NS):
                reference = cell.attrib.get("r", "")
                column_index = column_letters_to_index(reference) if reference else len(values_by_index)
                values_by_index[column_index] = read_excel_cell(cell, shared_strings)
                max_index = max(max_index, column_index)
            row_dicts.append(values_by_index)

        if not row_dicts:
            return []

        headers = [row_dicts[0].get(index, "").strip() for index in range(max_index + 1)]
        parsed_rows: list[dict[str, str]] = []
        for row_values in row_dicts[1:]:
            parsed_row = {
                header: row_values.get(index, "").strip()
                for index, header in enumerate(headers)
                if header
            }
            if any(parsed_row.values()):
                parsed_rows.append(parsed_row)
        return parsed_rows


def get_bulk_export_value(row: dict[str, str], key: str) -> str:
    aliases = BULK_EXPORT_FIELD_ALIASES[key]
    for alias in aliases:
        value = str(row.get(alias) or "").strip()
        if value:
            return value
    return ""


def is_probable_url(value: str) -> bool:
    text = str(value or "").strip()
    return text.startswith("http://") or text.startswith("https://")


def extract_bulk_export_metadata(blob: bytes) -> dict[str, dict[str, Any]]:
    metadata_by_ad: dict[str, dict[str, Any]] = {}
    for row in parse_first_sheet_xlsx(blob):
        ad_id = normalize_lookup_id(get_bulk_export_value(row, "ad_id"))
        if not ad_id:
            continue
        metadata_by_ad[ad_id] = {
            "bulk_export_destination": get_bulk_export_value(row, "destination"),
            "bulk_export_instant_page_id": normalize_lookup_id(get_bulk_export_value(row, "instant_page_id")),
            "bulk_export_website_type": get_bulk_export_value(row, "website_type"),
            "bulk_export_web_url": get_bulk_export_value(row, "web_url"),
            "bulk_export_deeplink_url": get_bulk_export_value(row, "deeplink_url"),
            "bulk_export_fallback_website_url": get_bulk_export_value(row, "fallback_website_url"),
            "bulk_export_click_tracking_url": get_bulk_export_value(row, "click_tracking_url"),
            "bulk_export_optimization_location": get_bulk_export_value(row, "optimization_location"),
            "bulk_export_sales_destination": get_bulk_export_value(row, "sales_destination"),
            "bulk_export_campaign_type": get_bulk_export_value(row, "campaign_type"),
        }
    return metadata_by_ad


def as_sheet_text(value: str | Any) -> str:
    text = str(value or "").strip()
    return f"'{text}" if text else ""


def select_status(metadata: dict[str, Any]) -> str:
    return str(metadata.get("secondary_status") or "").strip() or str(metadata.get("operation_status") or "").strip()


def select_media_type(metadata: dict[str, Any]) -> str:
    return (
        str(metadata.get("ad_format") or "").strip()
        or str(metadata.get("creative_type") or "").strip()
        or str(metadata.get("image_mode") or "").strip()
    )


def select_media_id(metadata: dict[str, Any]) -> str:
    video_id = str(metadata.get("video_id") or "").strip()
    if video_id:
        return video_id

    image_ids = metadata.get("image_ids") or []
    if isinstance(image_ids, list):
        return "|".join(str(item).strip() for item in image_ids if str(item).strip())
    return str(image_ids).strip()


def select_creative_key(metadata: dict[str, Any]) -> str:
    creative_id = normalize_lookup_id(metadata.get("creative_id", ""))
    if creative_id:
        return creative_id

    smart_plus_ad_id = str(metadata.get("smart_plus_ad_id") or "").strip()
    if smart_plus_ad_id:
        return smart_plus_ad_id

    card_id = str(metadata.get("card_id") or "").strip()
    if card_id:
        return card_id

    media_id = select_media_id(metadata)
    if media_id:
        return media_id

    return ""


def select_landing_page_url(metadata: dict[str, Any]) -> str:
    for key in (
        "landing_page_url",
        "creative_external_url",
        "creative_open_url",
        "creative_click_tracking_url",
        "creative_deeplink_url",
        "creative_action_track_url",
    ):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value

    landing_page_urls = metadata.get("landing_page_urls") or []
    if isinstance(landing_page_urls, list):
        for item in landing_page_urls:
            value = str(item).strip()
            if value:
                return value
        return ""

    text = str(landing_page_urls).strip()
    if text in {"[]", "None", "null"}:
        text = ""
    if text:
        return text

    for key in ("bulk_export_web_url", "bulk_export_fallback_website_url", "bulk_export_click_tracking_url", "bulk_export_deeplink_url"):
        value = str(metadata.get(key) or "").strip()
        if is_probable_url(value):
            return value

    destination = str(metadata.get("bulk_export_destination") or "").strip()
    if is_probable_url(destination):
        return destination

    return ""


def is_smart_plus_metadata(metadata: dict[str, Any]) -> bool:
    automation_type = str(metadata.get("campaign_automation_type") or "").strip()
    smart_plus_ad_id = str(metadata.get("smart_plus_ad_id") or "").strip()
    return "SMART_PLUS" in automation_type or bool(smart_plus_ad_id)


def select_delivery_lane(metadata: dict[str, Any]) -> str:
    promotion_type = str(metadata.get("promotion_type") or "").strip()
    smart_plus = is_smart_plus_metadata(metadata)
    if promotion_type == "LEAD_GENERATION":
        if smart_plus:
            return "Lead Gen / Smart+"
        return "Lead Gen / 通常"
    if promotion_type == "WEBSITE":
        if smart_plus:
            return "Web / Smart+"
        return "Web / 通常"
    if smart_plus:
        return "Smart+"
    return "通常"


def select_landing_page_status(metadata: dict[str, Any]) -> str:
    if select_landing_page_url(metadata):
        return "取得済み"
    lane = select_delivery_lane(metadata)
    if lane == "Lead Gen / Smart+":
        return "未取得（Lead Gen / Smart+）"
    if lane == "Lead Gen / 通常":
        return "未取得（Lead Gen）"
    if lane == "Web / Smart+":
        return "未取得（Web / Smart+）"
    if lane == "Web / 通常":
        return "未取得（WEBSITE）"
    if lane == "Smart+":
        return "未取得（Smart+）"
    return "未取得"


def build_sheet_rows(
    rows: list[dict[str, str]],
    metadata_by_ad: dict[str, dict[str, Any]],
) -> tuple[list[list[str]], list[tuple[str, str, str]]]:
    sheet_rows: list[list[str]] = []
    keys: list[tuple[str, str, str]] = []

    for row in rows:
        advertiser_id = normalize_lookup_id(row.get("advertiser_id", ""))
        advertiser_name = str(row.get("advertiser_name") or "").strip()
        ad_id = normalize_lookup_id(row.get("ad_id", ""))
        day = normalize_stat_day(row.get("stat_time_day", ""))
        metadata = metadata_by_ad.get(ad_id, {})

        values = {
            "日付": day,
            "広告アカウント名": advertiser_name,
            "広告アカウントID": advertiser_id,
            "キャンペーンID": normalize_lookup_id(metadata.get("campaign_id", "")),
            "キャンペーン名": str(metadata.get("campaign_name") or "").strip(),
            "広告グループID": normalize_lookup_id(metadata.get("adgroup_id", "")),
            "広告グループ名": str(metadata.get("adgroup_name") or "").strip(),
            "広告ID": ad_id,
            "広告名": str(metadata.get("ad_name") or "").strip(),
            "配信ステータス": select_status(metadata),
            "広告作成日": str(metadata.get("create_time") or "").strip(),
            "最終更新日": str(metadata.get("modify_time") or "").strip(),
            "CR識別キー": select_creative_key(metadata),
            "メディアタイプ": select_media_type(metadata),
            "メディアID": select_media_id(metadata),
            "プロモーション種別": str(metadata.get("promotion_type") or "").strip(),
            "遷移先URL": select_landing_page_url(metadata),
            "URL取得状態": select_landing_page_status(metadata),
            "インプレッション": row.get("impressions", ""),
            "リーチ": row.get("reach", ""),
            "フリークエンシー": row.get("frequency", ""),
            "クリック数（all）": row.get("clicks", ""),
            "消化金額": row.get("spend", ""),
            "CPC": row.get("cpc", ""),
            "CPM": row.get("cpm", ""),
            "CTR": row.get("ctr", ""),
            "コンバージョン数（optimization event）": row.get("conversion", ""),
            "動画再生数": row.get("video_play_actions", ""),
            "動画2秒再生数": row.get("video_watched_2s", ""),
            "動画6秒再生数": row.get("video_watched_6s", ""),
            "動画完全再生数": row.get("video_views_p100", ""),
            "キャンペーン自動化種別": str(metadata.get("campaign_automation_type") or "").strip(),
            "出稿形式レーン": select_delivery_lane(metadata),
            "最適化イベント": str(metadata.get("optimization_event") or "").strip(),
        }

        prepared: list[str] = []
        for header in TIKTOK_HEADERS:
            value = values.get(header, "")
            if header in TEXT_HEADERS:
                prepared.append(as_sheet_text(value))
            else:
                prepared.append(str(value or "").strip())
        sheet_rows.append(prepared)
        keys.append((day, advertiser_id, ad_id))

    return sheet_rows, keys


def open_sheet_worksheet(sheet_id: str, tab_name: str):
    client = get_client("kohara")
    spreadsheet = client.open_by_key(sheet_id)
    worksheet = spreadsheet.worksheet(tab_name)
    current_headers = worksheet.row_values(1)
    if current_headers[:len(TIKTOK_HEADERS)] != TIKTOK_HEADERS:
        worksheet.update("A1", [TIKTOK_HEADERS], value_input_option="RAW")
    try:
        apply_formatting(spreadsheet, worksheet, TIKTOK_HEADERS)
    except APIError as exc:
        if "交互の背景色" not in str(exc):
            raise
        apply_formatting(
            spreadsheet,
            worksheet,
            TIKTOK_HEADERS,
            include_table_styles=False,
            include_protection=True,
        )
    return worksheet


def reset_sheet_values(worksheet) -> None:
    worksheet.clear()
    worksheet.update("A1", [TIKTOK_HEADERS], value_input_option="RAW")


def build_existing_keys(
    worksheet,
    advertiser_ids: list[str] | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
) -> set[tuple[str, str, str]]:
    rows = worksheet.get_all_values()
    if not rows:
        return set()

    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    advertiser_filter = set(advertiser_ids or [])
    keys: set[tuple[str, str, str]] = set()

    for row in rows[1:]:
        day = row[idx["日付"]].strip() if len(row) > idx["日付"] else ""
        advertiser_id = normalize_lookup_id(row[idx["広告アカウントID"]]) if len(row) > idx["広告アカウントID"] else ""
        ad_id = normalize_lookup_id(row[idx["広告ID"]]) if len(row) > idx["広告ID"] else ""
        if not day or not advertiser_id or not ad_id:
            continue
        if advertiser_filter and advertiser_id not in advertiser_filter:
            continue
        if since_date and day < since_date:
            continue
        if until_date and day > until_date:
            continue
        keys.add((day, advertiser_id, ad_id))

    return keys


def append_rows_to_sheet(worksheet, rows: list[list[str]], max_chunk: int = 1000) -> None:
    for start in range(0, len(rows), max_chunk):
        chunk = rows[start:start + max_chunk]
        for attempt in range(5):
            try:
                worksheet.append_rows(chunk, value_input_option="USER_ENTERED")
                break
            except APIError as exc:
                if "429" in str(exc) or "Quota" in str(exc):
                    wait = 30 * (attempt + 1)
                    print(f"シート書き込み制限。{wait}秒待機します")
                    time.sleep(wait)
                    continue
                raise
        time.sleep(1)


def summarize_sheet_quality(rows: list[list[str]]) -> dict[str, Any]:
    idx = {header: position for position, header in enumerate(TIKTOK_HEADERS)}
    summary = {
        "row_count": len(rows),
        "missing_creative_key_rows": 0,
        "missing_media_id_rows": 0,
        "missing_promotion_type_rows": 0,
        "missing_landing_page_url_rows_web": 0,
        "missing_landing_page_url_rows_lead_generation": 0,
        "missing_landing_page_url_rows_smart_plus": 0,
        "delivery_lane_counts": {},
        "url_status_counts": {},
    }
    lane_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()

    for row in rows:
        if not row[idx["CR識別キー"]].strip():
            summary["missing_creative_key_rows"] += 1
        if not row[idx["メディアID"]].strip():
            summary["missing_media_id_rows"] += 1
        promotion_type = row[idx["プロモーション種別"]].strip()
        lane = row[idx["出稿形式レーン"]].strip()
        status = row[idx["URL取得状態"]].strip()
        if lane:
            lane_counter[lane] += 1
        if status:
            status_counter[status] += 1
        if not promotion_type:
            summary["missing_promotion_type_rows"] += 1
        if promotion_type == "WEBSITE" and not row[idx["遷移先URL"]].strip():
            summary["missing_landing_page_url_rows_web"] += 1
        if promotion_type == "LEAD_GENERATION" and not row[idx["遷移先URL"]].strip():
            summary["missing_landing_page_url_rows_lead_generation"] += 1
        if "Smart+" in lane and not row[idx["遷移先URL"]].strip():
            summary["missing_landing_page_url_rows_smart_plus"] += 1

    summary["delivery_lane_counts"] = dict(lane_counter)
    summary["url_status_counts"] = dict(status_counter)
    return summary


def collect_missing_landing_page_details(rows: list[list[str]], limit: int = 20) -> list[dict[str, str]]:
    idx = {header: position for position, header in enumerate(TIKTOK_HEADERS)}
    details: list[dict[str, str]] = []

    for row in rows:
        if row[idx["遷移先URL"]].strip():
            continue
        details.append(
            {
                "日付": row[idx["日付"]].strip(),
                "広告アカウント名": row[idx["広告アカウント名"]].strip(),
                "広告アカウントID": normalize_lookup_id(row[idx["広告アカウントID"]]),
                "キャンペーン名": row[idx["キャンペーン名"]].strip(),
                "広告グループ名": row[idx["広告グループ名"]].strip(),
                "広告ID": normalize_lookup_id(row[idx["広告ID"]]),
                "広告名": row[idx["広告名"]].strip(),
                "プロモーション種別": row[idx["プロモーション種別"]].strip(),
                "出稿形式レーン": row[idx["出稿形式レーン"]].strip(),
                "キャンペーン自動化種別": row[idx["キャンペーン自動化種別"]].strip(),
                "URL取得状態": row[idx["URL取得状態"]].strip(),
            }
        )
        if len(details) >= limit:
            break

    return details


def main() -> None:
    default_start, default_end = default_date_range()
    parser = argparse.ArgumentParser(description="TikTok広告の実績データを取得する")
    parser.add_argument("--start-date", default=default_start, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end-date", default=default_end, help="終了日 YYYY-MM-DD")
    parser.add_argument(
        "--advertiser-id",
        action="append",
        default=[],
        help="対象 advertiser_id。複数指定可。未指定なら認可済み全件",
    )
    parser.add_argument(
        "--data-level",
        default="AUCTION_AD",
        choices=["AUCTION_CAMPAIGN", "AUCTION_ADGROUP", "AUCTION_AD"],
        help="取得粒度",
    )
    parser.add_argument(
        "--dimensions",
        help="カンマ区切りの dimensions。未指定なら data_level に応じた既定値",
    )
    parser.add_argument(
        "--metrics",
        help="カンマ区切りの metrics。未指定なら spend,impressions,clicks",
    )
    parser.add_argument(
        "--page-size",
        type=int,
        default=1000,
        help="1回あたりの取得件数",
    )
    parser.add_argument(
        "--format",
        choices=["csv", "json"],
        default="csv",
        help="保存形式",
    )
    parser.add_argument("--output", help="出力先パス")
    parser.add_argument(
        "--auth-path",
        default=os.environ.get("TIKTOK_MARKETING_AUTH_PATH", str(DEFAULT_AUTH_PATH)),
        help="Marketing API 認証JSONのパス",
    )
    parser.add_argument(
        "--accounts-path",
        default=os.environ.get("TIKTOK_ADS_ACCOUNTS_PATH", str(DEFAULT_ACCOUNTS_PATH)),
        help="広告アカウント一覧JSONのパス",
    )
    parser.add_argument("--list-advertisers", action="store_true", help="認可済み advertiser 一覧を表示して終了")
    parser.add_argument("--write-sheet", action="store_true", help="TikTok収集シートにも追記する")
    parser.add_argument("--sheet-id", default=SHEET_ID, help="収集シートID")
    parser.add_argument("--tab-name", default=TAB_NAME, help="追記先タブ名")
    parser.add_argument("--replace-sheet", action="store_true", help="TikTok収集タブを再生成して書き直す")
    parser.add_argument(
        "--business-name",
        action="append",
        default=[],
        help="対象に含める事業名。複数指定可。--write-sheet では未指定時にスキルプラスのみ",
    )
    args = parser.parse_args()

    auth = load_auth(Path(args.auth_path))
    account_details = load_account_details(Path(args.accounts_path))
    account_names = {
        advertiser_id: detail.get("advertiser_name", "")
        for advertiser_id, detail in account_details.items()
        if detail.get("advertiser_name", "")
    }
    session = build_session()

    if args.list_advertisers:
        list_advertisers(session, auth, account_names)
        return

    advertiser_ids = resolve_advertisers(session, auth, args.advertiser_id)
    target_business_names = set(args.business_name)
    if args.write_sheet and not target_business_names:
        target_business_names = TARGET_BUSINESS_NAMES
    advertiser_ids = filter_advertisers_by_business(advertiser_ids, account_details, target_business_names)
    if args.write_sheet:
        if args.data_level != "AUCTION_AD":
            raise RuntimeError("収集シートへ書くときは AUCTION_AD で実行してください")
        dimensions = SHEET_DIMENSIONS[:]
        metrics = SHEET_METRICS[:]
    else:
        default_dimensions = DEFAULT_DIMENSIONS_BY_LEVEL[args.data_level]
        dimensions = parse_csv_list(args.dimensions, default_dimensions)
        metrics = parse_csv_list(args.metrics, DEFAULT_METRICS)

    all_rows: list[dict[str, str]] = []
    summaries: list[tuple[str, str, int]] = []
    metadata_by_advertiser: dict[str, dict[str, dict[str, Any]]] = {}
    ads_manager_fallback_errors: list[dict[str, str]] = []

    for advertiser_id in advertiser_ids:
        advertiser_name = account_names.get(advertiser_id, "")
        report_rows = fetch_report_rows(
            session=session,
            auth=auth,
            advertiser_id=advertiser_id,
            start_date=args.start_date,
            end_date=args.end_date,
            dimensions=dimensions,
            metrics=metrics,
            data_level=args.data_level,
            page_size=args.page_size,
        )
        flattened = flatten_rows(advertiser_id, advertiser_name, report_rows)
        all_rows.extend(flattened)
        summaries.append((advertiser_id, advertiser_name, len(flattened)))

        if args.write_sheet and flattened:
            ad_ids = [row.get("ad_id", "") for row in flattened if row.get("ad_id", "")]
            metadata_by_advertiser[advertiser_id] = fetch_ad_metadata(
                session=session,
                auth=auth,
                advertiser_id=advertiser_id,
                ad_ids=ad_ids,
            )
            adgroup_ids = [
                metadata.get("adgroup_id", "")
                for metadata in metadata_by_advertiser[advertiser_id].values()
                if metadata.get("adgroup_id", "")
            ]
            adgroup_metadata = fetch_adgroup_metadata(
                session=session,
                auth=auth,
                advertiser_id=advertiser_id,
                adgroup_ids=adgroup_ids,
            )
            merge_adgroup_metadata_into_ads(metadata_by_advertiser[advertiser_id], adgroup_metadata)

            missing_landing_page_ad_ids = find_missing_website_landing_page_ad_ids(
                flattened,
                metadata_by_advertiser[advertiser_id],
            )
            if missing_landing_page_ad_ids:
                try:
                    fallback_metadata = fetch_ads_manager_ad_metadata(
                        advertiser_id=advertiser_id,
                        start_date=args.start_date,
                        end_date=args.end_date,
                        target_ad_ids=missing_landing_page_ad_ids,
                    )
                    merge_fallback_metadata(metadata_by_advertiser[advertiser_id], fallback_metadata)
                    resolved_count = sum(
                        1
                        for ad_id in missing_landing_page_ad_ids
                        if select_landing_page_url(metadata_by_advertiser[advertiser_id].get(ad_id, {}))
                    )
                    print(
                        f"{advertiser_id} AdsManager補完 -> 対象 {len(missing_landing_page_ad_ids)}件 / 解決 {resolved_count}件"
                    )
                except Exception as exc:
                    ads_manager_fallback_errors.append(
                        {
                            "advertiser_id": advertiser_id,
                            "advertiser_name": advertiser_name,
                            "missing_website_url_rows": str(len(missing_landing_page_ad_ids)),
                            "error": str(exc),
                        }
                    )
                    print(
                        f"{advertiser_id} AdsManager補完失敗 -> 対象 {len(missing_landing_page_ad_ids)}件 / {str(exc)[:160]}"
                    )

            smart_plus_targets = build_smart_plus_procedural_targets(
                flattened,
                metadata_by_advertiser[advertiser_id],
            )
            if smart_plus_targets:
                try:
                    smart_plus_metadata, smart_plus_errors = fetch_ads_manager_smart_plus_procedural_metadata(
                        advertiser_id=advertiser_id,
                        start_date=args.start_date,
                        end_date=args.end_date,
                        creative_targets=smart_plus_targets,
                    )
                    merge_fallback_metadata(metadata_by_advertiser[advertiser_id], smart_plus_metadata)
                    resolved_count = sum(
                        1
                        for ad_id in smart_plus_targets
                        if select_landing_page_url(metadata_by_advertiser[advertiser_id].get(ad_id, {}))
                    )
                    print(
                        f"{advertiser_id} Smart+補完 -> 対象 {len(smart_plus_targets)}件 / 解決 {resolved_count}件"
                    )
                    for error in smart_plus_errors:
                        ads_manager_fallback_errors.append(
                            {
                                "advertiser_id": advertiser_id,
                                "advertiser_name": advertiser_name,
                                "missing_url_rows": "1",
                                "fallback": "smart_plus_procedural_detail",
                                "ad_id": error["ad_id"],
                                "creative_id": error["creative_id"],
                                "status": error["status"],
                                "code": error["code"],
                                "error": error["error"],
                            }
                        )
                except Exception as exc:
                    ads_manager_fallback_errors.append(
                        {
                            "advertiser_id": advertiser_id,
                            "advertiser_name": advertiser_name,
                            "missing_url_rows": str(len(smart_plus_targets)),
                            "fallback": "smart_plus_procedural_detail",
                            "error": str(exc),
                        }
                    )
                    print(
                        f"{advertiser_id} Smart+補完失敗 -> 対象 {len(smart_plus_targets)}件 / {str(exc)[:160]}"
                    )

            remaining_missing_landing_page_ad_ids = find_missing_non_smart_landing_page_ad_ids(
                flattened,
                metadata_by_advertiser[advertiser_id],
            )
            if remaining_missing_landing_page_ad_ids:
                try:
                    bulk_export_blob = fetch_ads_manager_bulk_export_blob(
                        advertiser_id=advertiser_id,
                        start_date=args.start_date,
                        end_date=args.end_date,
                    )
                    bulk_export_metadata = extract_bulk_export_metadata(bulk_export_blob)
                    merge_bulk_export_metadata_into_ads(metadata_by_advertiser[advertiser_id], bulk_export_metadata)
                    resolved_count = sum(
                        1
                        for ad_id in remaining_missing_landing_page_ad_ids
                        if select_landing_page_url(metadata_by_advertiser[advertiser_id].get(ad_id, {}))
                    )
                    print(
                        f"{advertiser_id} BulkExport補完 -> 対象 {len(remaining_missing_landing_page_ad_ids)}件 / 解決 {resolved_count}件"
                    )
                except Exception as exc:
                    ads_manager_fallback_errors.append(
                        {
                            "advertiser_id": advertiser_id,
                            "advertiser_name": advertiser_name,
                            "missing_url_rows": str(len(remaining_missing_landing_page_ad_ids)),
                            "fallback": "bulk_export",
                            "error": str(exc),
                        }
                    )
                    print(
                        f"{advertiser_id} BulkExport補完失敗 -> 対象 {len(remaining_missing_landing_page_ad_ids)}件 / {str(exc)[:160]}"
                    )

        print(f"{advertiser_id} {advertiser_name or '(名称未登録)'} -> {len(flattened)}行")
        time.sleep(0.2)

    output_path = build_output_path(args.output, args.start_date, args.end_date, args.format)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        fields = build_output_fields(all_rows, dimensions, metrics)
        write_csv(output_path, all_rows, fields)
    else:
        write_json(output_path, all_rows)

    appended_rows = 0
    sheet_quality_summary = None
    missing_landing_page_details: list[dict[str, str]] = []
    if args.write_sheet:
        worksheet = open_sheet_worksheet(args.sheet_id, args.tab_name)
        if args.replace_sheet:
            reset_sheet_values(worksheet)
            worksheet = open_sheet_worksheet(args.sheet_id, args.tab_name)
            existing_keys = set()
        else:
            existing_keys = build_existing_keys(
                worksheet,
                advertiser_ids=advertiser_ids,
                since_date=args.start_date,
                until_date=args.end_date,
            )
        pending_rows: list[list[str]] = []
        pending_keys: list[tuple[str, str, str]] = []
        for advertiser_id in advertiser_ids:
            advertiser_rows = [row for row in all_rows if normalize_lookup_id(row.get("advertiser_id", "")) == advertiser_id]
            sheet_rows, keys = build_sheet_rows(advertiser_rows, metadata_by_advertiser.get(advertiser_id, {}))
            pending_rows.extend(sheet_rows)
            pending_keys.extend(keys)

        rows_to_append = [
            row
            for row, key in zip(pending_rows, pending_keys)
            if key not in existing_keys
        ]
        if rows_to_append:
            append_rows_to_sheet(worksheet, rows_to_append)
            appended_rows = len(rows_to_append)
        sheet_quality_summary = summarize_sheet_quality(pending_rows)
        missing_landing_page_details = collect_missing_landing_page_details(pending_rows)
        print(f"収集シート追記: {appended_rows}行")
        print(
            "TikTok収集品質: "
            f"CR識別キー欠損 {sheet_quality_summary['missing_creative_key_rows']} / "
            f"メディアID欠損 {sheet_quality_summary['missing_media_id_rows']} / "
            f"プロモーション種別欠損 {sheet_quality_summary['missing_promotion_type_rows']} / "
            f"遷移先URL欠損(Webのみ) {sheet_quality_summary['missing_landing_page_url_rows_web']} / "
            f"遷移先URL未取得(Lead Gen) {sheet_quality_summary['missing_landing_page_url_rows_lead_generation']} / "
            f"遷移先URL未取得(Smart+) {sheet_quality_summary['missing_landing_page_url_rows_smart_plus']}"
        )

    summary_path = output_path.with_name(output_path.stem + "_summary.json")
    summary_data = {
        "start_date": args.start_date,
        "end_date": args.end_date,
        "data_level": args.data_level,
        "dimensions": dimensions,
        "metrics": metrics,
        "advertisers": [
            {"advertiser_id": advertiser_id, "advertiser_name": advertiser_name, "rows": rows}
            for advertiser_id, advertiser_name, rows in summaries
        ],
        "total_rows": len(all_rows),
        "appended_rows": appended_rows,
        "sheet_quality": sheet_quality_summary,
        "missing_landing_page_details": missing_landing_page_details,
        "ads_manager_fallback_errors": ads_manager_fallback_errors,
        "saved_to": str(output_path),
    }
    write_json(summary_path, summary_data)

    print(f"保存先: {output_path}")
    print(f"サマリー: {summary_path}")
    print(f"合計行数: {len(all_rows)}")


if __name__ == "__main__":
    main()
