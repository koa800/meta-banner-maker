#!/usr/bin/env python3
"""TikTok広告の実績データを取得して保存する。"""

from __future__ import annotations

import argparse
import csv
import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
AUTH_PATH = ROOT / "System" / "credentials" / "tiktok_marketing_api.json"
ACCOUNTS_PATH = ROOT / "System" / "credentials" / "tiktok_ads.json"
OUTPUT_DIR = ROOT / "System" / "data" / "tiktok_ads_export"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
REPORT_ENDPOINT = f"{BASE_URL}/report/integrated/get/"
ADVERTISER_ENDPOINT = f"{BASE_URL}/oauth2/advertiser/get/"

DEFAULT_METRICS = ["spend", "impressions", "clicks"]
DEFAULT_DIMENSIONS_BY_LEVEL = {
    "AUCTION_CAMPAIGN": ["stat_time_day", "campaign_id"],
    "AUCTION_ADGROUP": ["stat_time_day", "adgroup_id"],
    "AUCTION_AD": ["stat_time_day", "ad_id"],
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_auth() -> dict[str, Any]:
    auth = load_json(AUTH_PATH)
    required = ["app_id", "app_secret", "access_token"]
    missing = [key for key in required if not str(auth.get(key) or "").strip()]
    if missing:
        raise RuntimeError(f"TikTok認証情報が不足しています: {', '.join(missing)}")
    return auth


def load_account_names() -> dict[str, str]:
    if not ACCOUNTS_PATH.exists():
        return {}
    data = load_json(ACCOUNTS_PATH)
    names: dict[str, str] = {}
    for account in data.get("ad_accounts", []):
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        advertiser_name = str(account.get("advertiser_name") or "").strip()
        if advertiser_id and advertiser_name:
            names[advertiser_id] = advertiser_name
    return names


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
    parser.add_argument("--list-advertisers", action="store_true", help="認可済み advertiser 一覧を表示して終了")
    args = parser.parse_args()

    auth = load_auth()
    account_names = load_account_names()
    session = build_session()

    if args.list_advertisers:
        list_advertisers(session, auth, account_names)
        return

    advertiser_ids = resolve_advertisers(session, auth, args.advertiser_id)
    default_dimensions = DEFAULT_DIMENSIONS_BY_LEVEL[args.data_level]
    dimensions = parse_csv_list(args.dimensions, default_dimensions)
    metrics = parse_csv_list(args.metrics, DEFAULT_METRICS)

    all_rows: list[dict[str, str]] = []
    summaries: list[tuple[str, str, int]] = []

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
        print(f"{advertiser_id} {advertiser_name or '(名称未登録)'} -> {len(flattened)}行")
        time.sleep(0.2)

    output_path = build_output_path(args.output, args.start_date, args.end_date, args.format)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.format == "csv":
        fields = build_output_fields(all_rows, dimensions, metrics)
        write_csv(output_path, all_rows, fields)
    else:
        write_json(output_path, all_rows)

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
        "saved_to": str(output_path),
    }
    write_json(summary_path, summary_data)

    print(f"保存先: {output_path}")
    print(f"サマリー: {summary_path}")
    print(f"合計行数: {len(all_rows)}")


if __name__ == "__main__":
    main()
