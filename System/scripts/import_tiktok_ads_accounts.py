#!/usr/bin/env python3
"""
TikTok広告アカウント情報を設定ファイルから読み込み、
マスタデータの広告アカウントタブへ差分追加する。

用途:
- まずは TikTok 管理画面で確認できる情報だけを手入力で保持する
- 後から API 連携に切り替えても、広告アカウント台帳の入口は変えない
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import sheets_manager  # noqa: E402


CREDENTIAL_PATH = BASE_DIR / "credentials" / "tiktok_ads.json"
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w/edit?gid=1496246166#gid=1496246166"
SHEET_NAME = "広告アカウント"


def load_config() -> dict:
    return json.loads(CREDENTIAL_PATH.read_text())


def normalize_note(account: dict, business_center_name: str) -> str:
    parts: list[str] = []
    for key, label in [
        ("currency", "currency"),
        ("timezone", "timezone"),
        ("status", "status"),
        ("note", ""),
    ]:
        value = str(account.get(key) or "").strip()
        if not value:
            continue
        parts.append(f"{label}: {value}" if label else value)

    owner_name = str(account.get("owner_name") or "").strip()
    if owner_name and owner_name != business_center_name:
        parts.append(f"owner: {owner_name}")

    return " / ".join(parts)


def build_rows(config: dict) -> list[list[str]]:
    business_center_id = str(config.get("business_center_id") or "").strip()
    business_center_name = str(config.get("business_center_name") or "").strip()

    rows: list[list[str]] = []
    for account in config.get("ad_accounts", []):
        advertiser_id = str(account.get("advertiser_id") or "").strip()
        advertiser_name = str(account.get("advertiser_name") or "").strip()
        business_name = str(account.get("business_name") or "").strip()
        row_business_center_id = str(account.get("business_center_id") or business_center_id).strip()
        row_business_center_name = str(account.get("business_center_name") or business_center_name).strip()

        if not advertiser_id or not advertiser_name:
            continue

        rows.append(
            [
                "TikTok広告",
                row_business_center_id,
                row_business_center_name,
                advertiser_id,
                advertiser_name,
                business_name,
                normalize_note(account, row_business_center_name),
            ]
        )
    return rows


def worksheet_and_existing_rows():
    spreadsheet_id, _ = sheets_manager.extract_spreadsheet_id(SPREADSHEET_URL)
    client = sheets_manager.get_client(None)
    spreadsheet = client.open_by_key(spreadsheet_id)
    worksheet = spreadsheet.worksheet(SHEET_NAME)
    records = worksheet.get_all_records()
    row_map: dict[str, int] = {}
    for row_number, row in enumerate(records, start=2):
        value = str(row.get("広告アカウントID") or "").strip()
        if value:
            row_map[value] = row_number
    return worksheet, row_map


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    config = load_config()
    rows = build_rows(config)
    worksheet, existing_row_map = worksheet_and_existing_rows()
    update_rows = [(existing_row_map[row[3]], row) for row in rows if row[3] in existing_row_map]
    append_rows = [row for row in rows if row[3] not in existing_row_map]

    print(f"設定済みアカウント数: {len(rows)}")
    print(f"更新対象: {len(update_rows)}")
    print(f"追加対象: {len(append_rows)}")

    for row in rows:
        status = "更新" if row[3] in existing_row_map else "追加"
        print(f"[{status}] {row[3]} | {row[4]} | 事業名={row[5] or '(空)'} | 備考={row[6] or '(なし)'}")

    if args.dry_run:
        return

    for row_number, row in update_rows:
        worksheet.update(range_name=f"A{row_number}:G{row_number}", values=[row])

    if append_rows:
        worksheet.append_rows(append_rows)


if __name__ == "__main__":
    main()
