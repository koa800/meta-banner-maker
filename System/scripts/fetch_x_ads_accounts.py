#!/usr/bin/env python3
"""
X広告アカウント一覧を取得し、マスタデータの広告アカウントタブへ差分追加する。

前提:
- 認証情報は System/credentials/x_ads.json に保存
- 既存行は 広告アカウントID で重複判定
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests
from requests_oauthlib import OAuth1

import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sheets_manager  # noqa: E402


CREDENTIAL_PATH = BASE_DIR / "credentials" / "x_ads.json"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w/edit?gid=1496246166#gid=1496246166"
SHEET_NAME = "広告アカウント"
API_URL = "https://ads-api.x.com/12/accounts"
BUSINESS_MANAGER_ID = "be2wlcx208ap"
BUSINESS_MANAGER_NAME = "アドネス株式会社"

# 2026-03-18 時点の X 広告アカウント運用では、AI/SNS/スキルプラス名義の導線も事業名はスキルプラスで扱う。
BUSINESS_NAME_OVERRIDES = {
    "18ce55084qj": "スキルプラス",
    "18ce55mik02": "スキルプラス",
    "18ce55qkmoy": "スキルプラス",
    "18ce55sfuew": "スキルプラス",
    "18ce55tc6dv": "スキルプラス",
}


def load_credentials() -> dict:
    creds = json.loads(CREDENTIAL_PATH.read_text())
    required = [
        "consumer_key",
        "secret_key",
        "x_access_token",
        "x_access_token_secret",
    ]
    missing = [key for key in required if not str(creds.get(key, "")).strip()]
    if missing:
        raise ValueError(f"認証情報が不足しています: {', '.join(missing)}")
    return creds


def fetch_accounts(creds: dict) -> list[dict]:
    auth = OAuth1(
        creds["consumer_key"],
        creds["secret_key"],
        creds["x_access_token"],
        creds["x_access_token_secret"],
    )
    response = requests.get(API_URL, auth=auth, timeout=20)
    response.raise_for_status()
    return response.json().get("data", [])


def build_note(account: dict) -> str:
    notes: list[str] = []
    approval_status = str(account.get("approval_status") or "").strip()
    timezone = str(account.get("timezone") or "").strip()
    deleted = bool(account.get("deleted"))

    if approval_status and approval_status != "ACCEPTED":
        notes.append(f"承認状態: {approval_status}")
    if timezone and timezone != "Asia/Tokyo":
        notes.append(f"timezone: {timezone}")
    if deleted:
        notes.append("deleted")

    return " / ".join(notes)


def build_rows(accounts: list[dict]) -> list[list[str]]:
    rows: list[list[str]] = []
    for account in accounts:
        account_id = str(account.get("id") or "").strip()
        account_name = str(account.get("name") or "").strip()
        business_id = str(account.get("business_id") or "").strip()
        business_name = str(account.get("business_name") or "").strip()

        if not account_id or not account_name:
            continue

        rows.append(
            [
                "X広告",
                business_id or BUSINESS_MANAGER_ID,
                business_name or BUSINESS_MANAGER_NAME,
                account_id,
                account_name,
                BUSINESS_NAME_OVERRIDES.get(account_id, ""),
                build_note(account),
            ]
        )
    return rows


def existing_account_ids() -> set[str]:
    spreadsheet_id, _ = sheets_manager.extract_spreadsheet_id(SPREADSHEET_URL)
    client = sheets_manager.get_client(None)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    records = worksheet.get_all_records()
    ids: set[str] = set()
    for row in records:
        value = str(row.get("広告アカウントID") or "").strip()
        if value:
            ids.add(value)
    return ids


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    creds = load_credentials()
    accounts = fetch_accounts(creds)
    rows = build_rows(accounts)
    existing_ids = existing_account_ids()

    target_rows = [row for row in rows if row[3] not in existing_ids]

    print(f"取得アカウント数: {len(rows)}")
    print(f"追加対象: {len(target_rows)}")

    for row in rows:
        status = "追加" if row[3] not in existing_ids else "既存"
        print(f"[{status}] {row[3]} | {row[4]} | 事業名={row[5] or '(空)'} | 備考={row[6] or '(なし)'}")

    if args.dry_run or not target_rows:
        return

    sheets_manager.append_rows(SPREADSHEET_URL, target_rows, sheet_name=SHEET_NAME)


if __name__ == "__main__":
    main()
