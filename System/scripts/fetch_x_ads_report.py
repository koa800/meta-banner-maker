#!/usr/bin/env python3
"""
X広告の raw 実績を取得し、広告データ（収集） / X タブへ追記する。

方針:
- 粒度は 1日 x 1promoted_tweet
- 広告 = promoted_tweet
- クリエイティブID = tweet_id
- 遷移先URL = tweet/card の destination から取得
- 対象アカウントはマスタデータの 広告アカウント タブを正本にする
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
from requests_oauthlib import OAuth1

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sheets_manager  # noqa: E402


CREDENTIAL_PATH = BASE_DIR / "credentials" / "x_ads.json"
MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w/edit?usp=sharing"
MASTER_SHEET_NAME = "広告アカウント"
COLLECTION_SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
COLLECTION_TAB_NAME = "X"
OUTPUT_DIR = BASE_DIR / "data" / "x_ads_export"
CACHE_DIR = BASE_DIR / "data" / "x_ads_cache"
ENTITY_CACHE_DIR = CACHE_DIR / "entities"
API_BASE_URL = "https://ads-api.x.com/12"
TARGET_BUSINESS_NAMES = {"スキルプラス"}
X_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "インプレッション",
    "リンククリック数",
    "消化金額",
    "エンゲージメント数",
    "エンゲージメント率",
]
DEFAULT_METRIC_GROUPS = ("ENGAGEMENT", "BILLING", "MEDIA")
STATS_BATCH_SIZE = 20
TWEET_FETCH_BATCH_SIZE = 50
CARD_FETCH_BATCH_SIZE = 25
PAGE_SIZE = 1000
APPEND_CHUNK_SIZE = 500
ENTITY_CACHE_TTL_SECONDS = 6 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 30
SYNC_STATS_DATE_CHUNK_DAYS = 7
ASYNC_STATS_DATE_CHUNK_DAYS = 90
ASYNC_JOB_POLL_SECONDS = 5
ASYNC_JOB_TIMEOUT_SECONDS = 600


@dataclass
class TargetAccount:
    account_id: str
    account_name: str
    business_name: str
    note: str
    timezone_name: str = "Asia/Tokyo"


def default_date_range() -> tuple[str, str]:
    yesterday = (datetime.now(ZoneInfo("Asia/Tokyo")).date() - timedelta(days=1)).isoformat()
    return yesterday, yesterday


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def ensure_cache_dir() -> None:
    ENTITY_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_credentials() -> dict[str, str]:
    payload = json.loads(CREDENTIAL_PATH.read_text())
    required = ["consumer_key", "secret_key", "x_access_token", "x_access_token_secret"]
    missing = [key for key in required if not str(payload.get(key, "")).strip()]
    if missing:
        raise ValueError(f"X広告の認証情報が不足しています: {', '.join(missing)}")
    return payload


def build_auth(creds: dict[str, str]) -> OAuth1:
    return OAuth1(
        creds["consumer_key"],
        creds["secret_key"],
        creds["x_access_token"],
        creds["x_access_token_secret"],
    )


def iso_to_display(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.replace("T", " ").replace("Z", "")


def normalize_lookup_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("'"):
        text = text[1:]
    if text.endswith(".0"):
        integer, decimal = text.rsplit(".", 1)
        if decimal == "0":
            text = integer
    return text


def format_id(value: Any) -> str:
    text = normalize_lookup_id(value)
    return f"'{text}" if text else ""


def format_number(value: float | int | None, digits: int = 6) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return f"{value:.{digits}f}".rstrip("0").rstrip(".")
    return str(value)


def metric_first_value(value: Any) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, list):
        if not value:
            return None
        return metric_first_value(value[0])
    if isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    if text == "":
        return None
    try:
        if "." in text:
            return float(text)
        return int(text)
    except ValueError:
        return None


def micro_to_currency(value: float | int | None) -> float | None:
    if value is None:
        return None
    return float(value) / 1_000_000


def safe_divide(numerator: float | int | None, denominator: float | int | None, multiplier: float = 1.0) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return (float(numerator) / float(denominator)) * multiplier


def chunked(values: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(values), size):
        yield values[start:start + size]


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def request_json(
    session: requests.Session,
    auth: OAuth1,
    path: str,
    params: dict[str, Any] | None = None,
    method: str = "GET",
    retries: int = 4,
) -> dict[str, Any]:
    url = f"{API_BASE_URL}{path}"
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = session.request(method, url, params=params, auth=auth, timeout=REQUEST_TIMEOUT_SECONDS)
        except Exception as exc:  # pragma: no cover - network/runtime dependent
            last_error = exc
            time.sleep(2 * (attempt + 1))
            continue
        if response.status_code == 429:
            time.sleep(15 * (attempt + 1))
            continue
        if 500 <= response.status_code < 600:
            last_error = RuntimeError(f"X Ads API server error: {response.status_code}")
            time.sleep(5 * (attempt + 1))
            continue
        response.raise_for_status()
        return response.json()
    if last_error:
        raise last_error
    raise RuntimeError(f"X Ads API request failed: {path}")


def entity_cache_path(account_id: str) -> Path:
    ensure_cache_dir()
    safe_account_id = normalize_lookup_id(account_id) or "unknown"
    return ENTITY_CACHE_DIR / f"{safe_account_id}.json"


def load_cached_entities(account_id: str, allow_stale: bool = False) -> dict[str, Any] | None:
    path = entity_cache_path(account_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
    except Exception:
        return None
    fetched_at = str(payload.get("fetched_at") or "").strip()
    entities = payload.get("entities")
    if not isinstance(entities, dict):
        return None
    if allow_stale:
        return entities
    if not fetched_at:
        return None
    try:
        fetched_time = datetime.fromisoformat(fetched_at)
    except ValueError:
        return None
    age_seconds = (datetime.now(timezone.utc) - fetched_time).total_seconds()
    if age_seconds > ENTITY_CACHE_TTL_SECONDS:
        return None
    return entities


def save_cached_entities(account_id: str, entities: dict[str, Any]) -> None:
    path = entity_cache_path(account_id)
    payload = {
        "account_id": normalize_lookup_id(account_id),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "entities": entities,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False))


def fetch_paginated(
    session: requests.Session,
    auth: OAuth1,
    path: str,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    cursor = None
    while True:
        query = dict(params or {})
        query.setdefault("count", PAGE_SIZE)
        if cursor:
            query["cursor"] = cursor
        payload = request_json(session, auth, path, query)
        all_rows.extend(payload.get("data", []))
        cursor = payload.get("next_cursor")
        if not cursor:
            break
    return all_rows


def fetch_account_catalog(session: requests.Session, auth: OAuth1) -> dict[str, dict[str, Any]]:
    payload = request_json(session, auth, "/accounts")
    return {normalize_lookup_id(row.get("id")): row for row in payload.get("data", [])}


def load_master_target_accounts(
    account_catalog: dict[str, dict[str, Any]],
    business_names: set[str],
) -> list[TargetAccount]:
    spreadsheet_id, _ = sheets_manager.extract_spreadsheet_id(MASTER_SHEET_URL)
    client = sheets_manager.get_client(None)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(MASTER_SHEET_NAME)
    records = worksheet.get_all_records()

    targets: list[TargetAccount] = []
    for row in records:
        medium = str(row.get("集客媒体") or "").strip()
        business_name = str(row.get("事業名") or "").strip()
        account_id = normalize_lookup_id(row.get("広告アカウントID"))
        if medium != "X広告":
            continue
        if business_names and business_name not in business_names:
            continue
        if not account_id:
            continue
        account_info = account_catalog.get(account_id, {})
        targets.append(
            TargetAccount(
                account_id=account_id,
                account_name=str(row.get("広告アカウント名") or account_info.get("name") or "").strip(),
                business_name=business_name,
                note=str(row.get("備考") or "").strip(),
                timezone_name=str(account_info.get("timezone") or "Asia/Tokyo").strip() or "Asia/Tokyo",
            )
        )
    return targets


def build_local_day_window(target_day: str, timezone_name: str) -> tuple[str, str]:
    tz = ZoneInfo(timezone_name)
    local_day = date.fromisoformat(target_day)
    local_start = datetime(local_day.year, local_day.month, local_day.day, 0, 0, 0, tzinfo=tz)
    local_end = local_start + timedelta(days=1)
    start_utc = local_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = local_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return start_utc, end_utc


def build_local_range_window(start_date: str, end_date: str, timezone_name: str) -> tuple[str, str, list[str]]:
    tz = ZoneInfo(timezone_name)
    start_day = date.fromisoformat(start_date)
    end_day = date.fromisoformat(end_date)
    local_start = datetime(start_day.year, start_day.month, start_day.day, 0, 0, 0, tzinfo=tz)
    local_end = datetime(end_day.year, end_day.month, end_day.day, 0, 0, 0, tzinfo=tz) + timedelta(days=1)
    start_utc = local_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end_utc = local_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    local_days: list[str] = []
    current_day = start_day
    while current_day <= end_day:
        local_days.append(current_day.isoformat())
        current_day += timedelta(days=1)
    return start_utc, end_utc, local_days


def iter_date_chunks(start_date: str, end_date: str, chunk_days: int) -> Iterable[tuple[str, str]]:
    current_start = date.fromisoformat(start_date)
    final_end = date.fromisoformat(end_date)
    while current_start <= final_end:
        current_end = min(current_start + timedelta(days=chunk_days - 1), final_end)
        yield current_start.isoformat(), current_end.isoformat()
        current_start = current_end + timedelta(days=1)


def expand_metrics_by_local_day(metrics: dict[str, Any], local_days: list[str]) -> dict[str, dict[str, Any]]:
    per_day_metrics: dict[str, dict[str, Any]] = {}
    for index, local_day in enumerate(local_days):
        day_metrics: dict[str, Any] = {}
        has_value = False
        for metric_name, metric_value in metrics.items():
            value_for_day = None
            if isinstance(metric_value, list):
                if index < len(metric_value):
                    value_for_day = metric_value[index]
            else:
                value_for_day = metric_value
            day_metrics[metric_name] = value_for_day
            if value_for_day is not None:
                has_value = True
        if has_value:
            per_day_metrics[local_day] = day_metrics
    return per_day_metrics


def download_async_payload(session: requests.Session, url: str) -> dict[str, Any]:
    response = session.get(url, timeout=120, headers={"Accept-Encoding": "identity"})
    response.raise_for_status()
    content = response.content
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    return json.loads(content.decode("utf-8"))


def fetch_stats_for_promoted_tweets_sync(
    session: requests.Session,
    auth: OAuth1,
    account_id: str,
    promoted_tweet_ids: list[str],
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    if not promoted_tweet_ids:
        return {}
    stats_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    for chunk_start_date, chunk_end_date in iter_date_chunks(start_date, end_date, SYNC_STATS_DATE_CHUNK_DAYS):
        start_time, end_time, local_days = build_local_range_window(chunk_start_date, chunk_end_date, timezone_name)
        for chunk in chunked(promoted_tweet_ids, STATS_BATCH_SIZE):
            params = {
                "entity": "PROMOTED_TWEET",
                "entity_ids": ",".join(chunk),
                "start_time": start_time,
                "end_time": end_time,
                "granularity": "DAY",
                "placement": "ALL_ON_TWITTER",
                "metric_groups": ",".join(DEFAULT_METRIC_GROUPS),
            }
            payload = request_json(session, auth, f"/stats/accounts/{account_id}", params)
            for row in payload.get("data", []):
                item_id = normalize_lookup_id(row.get("id"))
                id_data = row.get("id_data") or []
                metrics = ((id_data[0] if id_data else {}).get("metrics")) or {}
                per_day_metrics = stats_by_id.setdefault(item_id, {})
                per_day_metrics.update(expand_metrics_by_local_day(metrics, local_days))
    return stats_by_id


def fetch_async_stats_job_payload(
    session: requests.Session,
    auth: OAuth1,
    account_id: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    job_payload = request_json(session, auth, f"/stats/jobs/accounts/{account_id}", params, method="POST")
    job = job_payload.get("data") or {}
    job_id = str(job.get("id") or "").strip()
    if not job_id:
        raise RuntimeError(f"X Ads async job_id が取得できませんでした: {account_id}")

    deadline = time.time() + ASYNC_JOB_TIMEOUT_SECONDS
    while time.time() < deadline:
        poll_payload = request_json(session, auth, f"/stats/jobs/accounts/{account_id}", {"job_ids": job_id})
        data = (poll_payload.get("data") or [{}])[0]
        status = str(data.get("status") or "").strip().upper()
        if status == "SUCCESS" and data.get("url"):
            return download_async_payload(session, str(data["url"]))
        if status in {"FAILED", "CANCELED"}:
            raise RuntimeError(f"X Ads async job failed: {account_id} / {job_id} / {status}")
        time.sleep(ASYNC_JOB_POLL_SECONDS)
    raise RuntimeError(f"X Ads async job timeout: {account_id} / {job_id}")


def fetch_stats_for_promoted_tweets_async(
    session: requests.Session,
    auth: OAuth1,
    account_id: str,
    promoted_tweet_ids: list[str],
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    if not promoted_tweet_ids:
        return {}
    stats_by_id: dict[str, dict[str, dict[str, Any]]] = {}
    for chunk_start_date, chunk_end_date in iter_date_chunks(start_date, end_date, ASYNC_STATS_DATE_CHUNK_DAYS):
        start_time, end_time, local_days = build_local_range_window(chunk_start_date, chunk_end_date, timezone_name)
        for chunk in chunked(promoted_tweet_ids, STATS_BATCH_SIZE):
            params = {
                "entity": "PROMOTED_TWEET",
                "entity_ids": ",".join(chunk),
                "start_time": start_time,
                "end_time": end_time,
                "granularity": "DAY",
                "placement": "ALL_ON_TWITTER",
                "metric_groups": ",".join(DEFAULT_METRIC_GROUPS),
            }
            payload = fetch_async_stats_job_payload(session, auth, account_id, params)
            for row in payload.get("data", []):
                item_id = normalize_lookup_id(row.get("id"))
                id_data = row.get("id_data") or []
                metrics = ((id_data[0] if id_data else {}).get("metrics")) or {}
                per_day_metrics = stats_by_id.setdefault(item_id, {})
                per_day_metrics.update(expand_metrics_by_local_day(metrics, local_days))
    return stats_by_id


def fetch_stats_for_promoted_tweets(
    session: requests.Session,
    auth: OAuth1,
    account_id: str,
    promoted_tweet_ids: list[str],
    start_date: str,
    end_date: str,
    timezone_name: str,
) -> dict[str, dict[str, dict[str, Any]]]:
    total_days = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
    if total_days <= SYNC_STATS_DATE_CHUNK_DAYS:
        return fetch_stats_for_promoted_tweets_sync(
            session=session,
            auth=auth,
            account_id=account_id,
            promoted_tweet_ids=promoted_tweet_ids,
            start_date=start_date,
            end_date=end_date,
            timezone_name=timezone_name,
        )
    return fetch_stats_for_promoted_tweets_async(
        session=session,
        auth=auth,
        account_id=account_id,
        promoted_tweet_ids=promoted_tweet_ids,
        start_date=start_date,
        end_date=end_date,
        timezone_name=timezone_name,
    )


def fetch_account_entities(
    session: requests.Session,
    auth: OAuth1,
    target: TargetAccount,
) -> dict[str, Any]:
    account_id = target.account_id
    campaigns = fetch_paginated(session, auth, f"/accounts/{account_id}/campaigns")
    line_items = fetch_paginated(session, auth, f"/accounts/{account_id}/line_items")
    promoted_tweets = fetch_paginated(session, auth, f"/accounts/{account_id}/promoted_tweets")

    tweets_by_id: dict[str, dict[str, Any]] = {}
    card_by_uri: dict[str, dict[str, Any]] = {}

    tweet_ids = [normalize_lookup_id(row.get("tweet_id")) for row in promoted_tweets if row.get("tweet_id")]
    for chunk in chunked(tweet_ids, TWEET_FETCH_BATCH_SIZE):
        payload = request_json(
            session,
            auth,
            f"/accounts/{account_id}/tweets",
            {"tweet_type": "PUBLISHED", "tweet_ids": ",".join(chunk)},
        )
        for row in payload.get("data", []):
            tweets_by_id[normalize_lookup_id(row.get("id"))] = row

    card_uris = [str(tweet.get("card_uri") or "").strip() for tweet in tweets_by_id.values() if tweet.get("card_uri")]
    for chunk in chunked(card_uris, CARD_FETCH_BATCH_SIZE):
        payload = request_json(
            session,
            auth,
            f"/accounts/{account_id}/cards",
            {"card_uris": ",".join(chunk)},
        )
        for row in payload.get("data", []):
            card_uri = str(row.get("card_uri") or "").strip()
            if card_uri:
                card_by_uri[card_uri] = row

    return {
        "campaigns": {normalize_lookup_id(row.get("id")): row for row in campaigns},
        "line_items": {normalize_lookup_id(row.get("id")): row for row in line_items},
        "promoted_tweets": {normalize_lookup_id(row.get("id")): row for row in promoted_tweets},
        "tweets": tweets_by_id,
        "cards": card_by_uri,
    }


def get_account_entities(
    session: requests.Session,
    auth: OAuth1,
    target: TargetAccount,
) -> dict[str, Any]:
    cached = load_cached_entities(target.account_id)
    if cached is not None:
        print(f"[X] キャッシュ使用: {target.account_name} ({target.account_id})")
        return cached

    print(f"[X] エンティティ取得: {target.account_name} ({target.account_id})")
    try:
        entities = fetch_account_entities(session, auth, target)
    except Exception as exc:
        stale = load_cached_entities(target.account_id, allow_stale=True)
        if stale is not None:
            print(f"[X] stale キャッシュへ退避: {target.account_name} ({target.account_id}) / {exc}")
            return stale
        raise

    save_cached_entities(target.account_id, entities)
    return entities


def has_any_metric(metrics: dict[str, Any]) -> bool:
    keys = [
        "impressions",
        "clicks",
        "url_clicks",
        "engagements",
        "billed_charge_local_micro",
        "media_views",
    ]
    for key in keys:
        if metric_first_value(metrics.get(key)) is not None:
            return True
    return False


def extract_card_destination_url(card: dict[str, Any]) -> str:
    for component in card.get("components") or []:
        destination = component.get("destination") or {}
        url = str(destination.get("url") or "").strip()
        if url:
            return url
    return ""


def extract_tweet_destination_url(tweet: dict[str, Any]) -> str:
    for item in (tweet.get("entities") or {}).get("urls") or []:
        for key in ("expanded_url", "url", "display_url"):
            value = str(item.get(key) or "").strip()
            if value:
                return value
    return ""


def extract_destination_url(tweet: dict[str, Any], card: dict[str, Any]) -> str:
    return extract_card_destination_url(card) or extract_tweet_destination_url(tweet)


def extract_media_info(tweet: dict[str, Any], card: dict[str, Any]) -> tuple[str, str]:
    media_types: list[str] = []
    media_ids: list[str] = []

    for component in card.get("components") or []:
        media_key = str(component.get("media_key") or "").strip()
        if media_key:
            media_ids.append(media_key)
        metadata_map = component.get("media_metadata") or {}
        if media_key and media_key in metadata_map:
            media_type = str(metadata_map[media_key].get("type") or "").strip()
            if media_type:
                media_types.append(media_type)
        component_type = str(component.get("type") or "").strip()
        if component_type == "MEDIA" and not media_types:
            media_types.append(component_type)

    if not media_types:
        card_type = str(card.get("card_type") or "").strip()
        if card_type:
            media_types.append(card_type)

    if not media_ids:
        media_key = str(tweet.get("media_key") or "").strip()
        if media_key:
            media_ids.append(media_key)

    if not media_ids:
        card_uri = str(card.get("card_uri") or "").strip()
        if card_uri.startswith("card://"):
            media_ids.append(card_uri.replace("card://", "", 1))

    return ",".join(sorted(set(filter(None, media_types)))), ",".join(sorted(set(filter(None, media_ids))))


def extract_ad_name(tweet: dict[str, Any], promoted_tweet: dict[str, Any], line_item: dict[str, Any]) -> str:
    for key in ("name", "full_text", "text"):
        value = str(tweet.get(key) or "").strip()
        if value:
            return value
    for key in ("name",):
        value = str(line_item.get(key) or "").strip()
        if value:
            return value
    return normalize_lookup_id(promoted_tweet.get("id"))


def build_row_for_promoted_tweet(
    target_day: str,
    target: TargetAccount,
    promoted_tweet: dict[str, Any],
    metrics: dict[str, Any],
    line_items: dict[str, dict[str, Any]],
    campaigns: dict[str, dict[str, Any]],
    tweets: dict[str, dict[str, Any]],
    cards: dict[str, dict[str, Any]],
) -> list[str] | None:
    if not has_any_metric(metrics):
        return None

    promoted_tweet_id = normalize_lookup_id(promoted_tweet.get("id"))
    line_item_id = normalize_lookup_id(promoted_tweet.get("line_item_id"))
    tweet_id = normalize_lookup_id(promoted_tweet.get("tweet_id"))
    line_item = line_items.get(line_item_id, {})
    campaign_id = normalize_lookup_id(line_item.get("campaign_id"))
    campaign = campaigns.get(campaign_id, {})
    tweet = tweets.get(tweet_id, {})
    card_uri = str(tweet.get("card_uri") or "").strip()
    card = cards.get(card_uri, {})

    impressions = metric_first_value(metrics.get("impressions"))
    clicks = metric_first_value(metrics.get("clicks"))
    url_clicks = metric_first_value(metrics.get("url_clicks"))
    spend = micro_to_currency(metric_first_value(metrics.get("billed_charge_local_micro")))
    engagements = metric_first_value(metrics.get("engagements"))
    media_type, media_id = extract_media_info(tweet, card)
    destination_url = extract_destination_url(tweet, card)
    engagement_rate = safe_divide(engagements, impressions, multiplier=100.0)

    delivery_status = (
        str(line_item.get("effective_status") or "").strip()
        or str(promoted_tweet.get("entity_status") or "").strip()
        or str(line_item.get("entity_status") or "").strip()
    )

    return [
        target_day,
        target.account_name,
        format_id(target.account_id),
        format_id(campaign_id),
        str(campaign.get("name") or "").strip(),
        format_id(line_item_id),
        str(line_item.get("name") or "").strip(),
        format_id(promoted_tweet_id),
        extract_ad_name(tweet, promoted_tweet, line_item),
        delivery_status,
        iso_to_display(promoted_tweet.get("created_at")),
        iso_to_display(promoted_tweet.get("updated_at")),
        format_id(tweet_id),
        media_type,
        media_id,
        destination_url,
        format_number(impressions),
        format_number(url_clicks),
        format_number(spend, digits=2),
        format_number(engagements),
        format_number(engagement_rate, digits=6),
    ]


def get_existing_keys(
    worksheet,
    account_ids: list[str] | None = None,
    since_date: str | None = None,
    until_date: str | None = None,
) -> set[tuple[str, str, str]]:
    rows = worksheet.get_all_values()
    if not rows:
        return set()
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    filter_accounts = set(account_ids or [])
    keys: set[tuple[str, str, str]] = set()
    for row in rows[1:]:
        day = row[idx["日付"]].strip() if len(row) > idx["日付"] else ""
        account_id = normalize_lookup_id(row[idx["広告アカウントID"]]) if len(row) > idx["広告アカウントID"] else ""
        ad_id = normalize_lookup_id(row[idx["広告ID"]]) if len(row) > idx["広告ID"] else ""
        if not day or not account_id or not ad_id:
            continue
        if filter_accounts and account_id not in filter_accounts:
            continue
        if since_date and day < since_date:
            continue
        if until_date and day > until_date:
            continue
        keys.add((day, account_id, ad_id))
    return keys


def append_rows_to_sheet(worksheet, rows: list[list[str]]) -> None:
    for chunk in chunked(rows, APPEND_CHUNK_SIZE):
        worksheet.append_rows(chunk, value_input_option="USER_ENTERED")
        time.sleep(1)


def replace_sheet_rows(worksheet, rows: list[list[str]]) -> None:
    worksheet.clear()
    values = [X_HEADERS] + rows if rows else [X_HEADERS]
    worksheet.update("A1", values, value_input_option="USER_ENTERED")


def build_output_path(start_date: str, end_date: str, suffix: str) -> Path:
    ensure_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return OUTPUT_DIR / f"x_ads_report_{start_date}_{end_date}_{timestamp}.{suffix}"


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(X_HEADERS)
        writer.writerows(rows)


def build_summary(
    start_date: str,
    end_date: str,
    targets: list[TargetAccount],
    collected_rows: list[list[str]],
    appended_rows: int,
    skipped_existing_rows: int,
    per_account_row_counts: dict[str, int],
    account_catalog: dict[str, dict[str, Any]],
    failed_accounts: list[dict[str, str]],
) -> dict[str, Any]:
    missing_url_details = []
    missing_url_count = 0
    for row in collected_rows:
        if row[15].strip():
            continue
        missing_url_count += 1
        if len(missing_url_details) < 20:
            missing_url_details.append(
                {
                    "日付": row[0],
                    "広告アカウント名": row[1],
                    "広告アカウントID": normalize_lookup_id(row[2]),
                    "キャンペーン名": row[4],
                    "広告グループ名": row[6],
                    "広告ID": normalize_lookup_id(row[7]),
                    "広告名": row[8],
                }
            )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "account_count": len(targets),
        "accounts": [
            {
                "account_id": target.account_id,
                "account_name": target.account_name,
                "business_name": target.business_name,
                "timezone": target.timezone_name,
                "approval_status": str(account_catalog.get(target.account_id, {}).get("approval_status") or "").strip(),
                "rows": per_account_row_counts.get(target.account_id, 0),
            }
            for target in targets
        ],
        "total_rows": len(collected_rows),
        "appended_rows": appended_rows,
        "skipped_existing_rows": skipped_existing_rows,
        "failed_accounts": failed_accounts,
        "missing_landing_page_url_rows": missing_url_count,
        "missing_landing_page_details": missing_url_details,
    }


def main() -> None:
    default_start, default_end = default_date_range()
    parser = argparse.ArgumentParser(description="X広告 raw を取得して収集シートへ反映する")
    parser.add_argument("--start-date", default=default_start, help="開始日 YYYY-MM-DD")
    parser.add_argument("--end-date", default=default_end, help="終了日 YYYY-MM-DD")
    parser.add_argument("--account-id", action="append", default=[], help="対象広告アカウントID。複数指定可")
    parser.add_argument("--write-sheet", action="store_true", help="収集シート X タブへ追記する")
    parser.add_argument("--replace-sheet", action="store_true", help="X タブを再生成して書き直す")
    parser.add_argument("--sheet-id", default=COLLECTION_SHEET_ID, help="収集シートID")
    parser.add_argument("--tab-name", default=COLLECTION_TAB_NAME, help="追記先タブ名")
    parser.add_argument("--business-name", action="append", default=[], help="対象事業名。未指定ならスキルプラス")
    args = parser.parse_args()

    creds = load_credentials()
    auth = build_auth(creds)
    session = requests.Session()
    account_catalog = fetch_account_catalog(session, auth)

    target_business_names = set(args.business_name) or TARGET_BUSINESS_NAMES
    targets = load_master_target_accounts(account_catalog, target_business_names)
    explicit_account_ids = {normalize_lookup_id(value) for value in args.account_id if normalize_lookup_id(value)}
    if explicit_account_ids:
        targets = [target for target in targets if target.account_id in explicit_account_ids]

    if not targets:
        raise RuntimeError("対象の X広告アカウントが見つかりませんでした")

    print(f"[X] 対象アカウント数: {len(targets)}")
    all_rows: list[list[str]] = []
    per_account_row_counts: dict[str, int] = {}
    failed_accounts: list[dict[str, str]] = []

    entities_by_account = {
        target.account_id: get_account_entities(session, auth, target)
        for target in targets
    }

    print(f"[X] 集計期間: {args.start_date} -> {args.end_date}")
    for target in targets:
        entities = entities_by_account[target.account_id]
        promoted_tweet_ids = list(entities["promoted_tweets"].keys())
        try:
            stats_by_id = fetch_stats_for_promoted_tweets(
                session=session,
                auth=auth,
                account_id=target.account_id,
                promoted_tweet_ids=promoted_tweet_ids,
                start_date=args.start_date,
                end_date=args.end_date,
                timezone_name=target.timezone_name,
            )
        except Exception as exc:
            failed_accounts.append(
                {
                    "account_id": target.account_id,
                    "account_name": target.account_name,
                    "reason": str(exc),
                }
            )
            print(f"[X] 取得失敗: {target.account_name} ({target.account_id}) / {exc}")
            continue
        for promoted_tweet_id, promoted_tweet in entities["promoted_tweets"].items():
            for target_day, metrics in sorted(stats_by_id.get(promoted_tweet_id, {}).items()):
                row = build_row_for_promoted_tweet(
                    target_day=target_day,
                    target=target,
                    promoted_tweet=promoted_tweet,
                    metrics=metrics,
                    line_items=entities["line_items"],
                    campaigns=entities["campaigns"],
                    tweets=entities["tweets"],
                    cards=entities["cards"],
                )
                if not row:
                    continue
                all_rows.append(row)
                per_account_row_counts[target.account_id] = per_account_row_counts.get(target.account_id, 0) + 1

    csv_path = build_output_path(args.start_date, args.end_date, "csv")
    summary_path = build_output_path(args.start_date, args.end_date, "summary.json")
    write_csv(csv_path, all_rows)

    appended_rows = 0
    skipped_existing_rows = 0
    if args.write_sheet:
        client = sheets_manager.get_client(None)
        spreadsheet = client.open_by_key(args.sheet_id)
        worksheet = spreadsheet.worksheet(args.tab_name)
        if args.replace_sheet:
            replace_sheet_rows(worksheet, all_rows)
            appended_rows = len(all_rows)
        else:
            existing_keys = get_existing_keys(
                worksheet,
                account_ids=[target.account_id for target in targets],
                since_date=args.start_date,
                until_date=args.end_date,
            )
            rows_to_append: list[list[str]] = []
            for row in all_rows:
                key = (row[0], normalize_lookup_id(row[2]), normalize_lookup_id(row[7]))
                if key in existing_keys:
                    skipped_existing_rows += 1
                    continue
                rows_to_append.append(row)
            if rows_to_append:
                append_rows_to_sheet(worksheet, rows_to_append)
            appended_rows = len(rows_to_append)

    summary = build_summary(
        start_date=args.start_date,
        end_date=args.end_date,
        targets=targets,
        collected_rows=all_rows,
        appended_rows=appended_rows,
        skipped_existing_rows=skipped_existing_rows,
        per_account_row_counts=per_account_row_counts,
        account_catalog=account_catalog,
        failed_accounts=failed_accounts,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")

    print(f"対象アカウント数: {len(targets)}")
    print(f"取得行数: {len(all_rows)}")
    if args.write_sheet:
        print(f"追記行数: {appended_rows}")
        print(f"重複スキップ: {skipped_existing_rows}")
    if failed_accounts:
        print(f"失敗アカウント数: {len(failed_accounts)}")
    print(f"CSV: {csv_path}")
    print(f"サマリー: {summary_path}")


if __name__ == "__main__":
    main()
