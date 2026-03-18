#!/usr/bin/env python3
"""TikTok Marketing API の認証状態を read-only で確認する。"""

from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from fetch_tiktok_ads_report import (
    DEFAULT_ACCOUNTS_PATH,
    DEFAULT_AUTH_PATH,
    api_get,
    build_session,
    load_account_names,
    load_auth,
    resolve_advertisers,
)


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "System" / "data" / "tiktok_ads_export"
BASE_URL = "https://business-api.tiktok.com/open_api/v1.3"
ADVERTISER_ENDPOINT = f"{BASE_URL}/oauth2/advertiser/get/"
REPORT_ENDPOINT = f"{BASE_URL}/report/integrated/get/"


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def yesterday_str() -> str:
    return (date.today() - timedelta(days=1)).isoformat()


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def summarize_token_age(auth: dict[str, Any]) -> dict[str, Any]:
    obtained_at = str(auth.get("token_obtained_at") or "").strip()
    parsed = parse_iso(obtained_at)
    if not parsed:
        return {
            "status": "warn",
            "message": "token_obtained_at が無いか、時刻として解釈できません",
        }

    now = datetime.now(parsed.tzinfo)
    age_seconds = int((now - parsed).total_seconds())
    return {
        "status": "ok",
        "obtained_at": obtained_at,
        "age_hours": round(age_seconds / 3600, 2),
    }


def summarize_refresh_token(auth: dict[str, Any]) -> dict[str, Any]:
    refresh_token = str(auth.get("refresh_token") or "").strip()
    if refresh_token:
        return {"status": "ok", "message": "refresh_token あり"}
    return {
        "status": "warn",
        "message": "refresh_token は未保存",
        "note": str(auth.get("refresh_token_status") or "").strip(),
    }


def advertiser_check(session, auth: dict[str, Any]) -> dict[str, Any]:
    payload = api_get(session, ADVERTISER_ENDPOINT, auth, {})
    rows = payload.get("data", {}).get("list", [])
    return {
        "status": "ok",
        "count": len(rows),
        "request_id": payload.get("request_id", ""),
    }


def report_probe(
    session,
    auth: dict[str, Any],
    advertiser_id: str,
) -> dict[str, Any]:
    target_date = yesterday_str()
    payload = api_get(
        session,
        REPORT_ENDPOINT,
        auth,
        {
            "advertiser_id": advertiser_id,
            "service_type": "AUCTION",
            "report_type": "BASIC",
            "data_level": "AUCTION_AD",
            "dimensions": json.dumps(["stat_time_day", "ad_id"], ensure_ascii=False),
            "metrics": json.dumps(["spend", "impressions", "clicks"], ensure_ascii=False),
            "start_date": target_date,
            "end_date": target_date,
            "page": 1,
            "page_size": 1,
        },
    )
    page_info = payload.get("data", {}).get("page_info", {})
    rows = payload.get("data", {}).get("list", [])
    return {
        "status": "ok",
        "advertiser_id": advertiser_id,
        "date": target_date,
        "sample_rows": len(rows),
        "total_rows": int(page_info.get("total_number") or 0),
        "request_id": payload.get("request_id", ""),
    }


def compute_overall_status(checks: list[dict[str, Any]]) -> str:
    statuses = [check.get("status", "fail") for check in checks]
    if "fail" in statuses:
        return "fail"
    if "warn" in statuses:
        return "warn"
    return "ok"


def save_report(report: dict[str, Any]) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / f"tiktok_token_health_{timestamp}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="TikTok token health check")
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
    parser.add_argument(
        "--advertiser-id",
        help="report probe に使う advertiser_id。未指定なら認可済み一覧の先頭",
    )
    args = parser.parse_args()

    auth = load_auth(Path(args.auth_path))
    account_names = load_account_names(Path(args.accounts_path))
    session = build_session()

    checks: list[dict[str, Any]] = []
    checks.append({"name": "token_age", **summarize_token_age(auth)})
    checks.append({"name": "refresh_token", **summarize_refresh_token(auth)})

    try:
        advertisers = resolve_advertisers(session, auth, [args.advertiser_id] if args.advertiser_id else [])
        checks.append({"name": "authorized_advertisers", "status": "ok", "count": len(advertisers)})
        checks.append({"name": "advertiser_api", **advertiser_check(session, auth)})
        probe_target = args.advertiser_id or advertisers[0]
        probe = report_probe(session, auth, probe_target)
        probe["advertiser_name"] = account_names.get(probe_target, "")
        checks.append({"name": "report_probe", **probe})
    except Exception as exc:
        checks.append({"name": "api_probe", "status": "fail", "message": str(exc)})

    overall_status = compute_overall_status(checks)
    report = {
        "checked_at": iso_now(),
        "overall_status": overall_status,
        "auth_path": str(args.auth_path),
        "accounts_path": str(args.accounts_path),
        "checks": checks,
    }
    saved_path = save_report(report)

    print(f"overall_status={overall_status}")
    for check in checks:
        label = check.get("name", "check")
        status = check.get("status", "fail")
        if status == "ok":
            print(f"[OK] {label}")
        elif status == "warn":
            print(f"[WARN] {label}: {check.get('message', '')}")
        else:
            print(f"[FAIL] {label}: {check.get('message', '')}")
    print(f"saved_to={saved_path}")

    return 0 if overall_status in {"ok", "warn"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
