#!/usr/bin/env python3
"""Meta広告の収集データをマスタ照合して加工データとして保存する。"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System"))

from sheets_manager import get_client  # noqa: E402
from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound  # noqa: E402
from setup_ads_sheet import apply_formatting  # noqa: E402


RAW_SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
RAW_TAB_NAME = "Meta"

MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_ACCOUNT_TAB = "広告アカウント"
MASTER_MAPPING_TAB = "広告-ファネル-LINE対応表"
MASTER_ROUTE_TAB = "流入経路マスタ"
TARGET_BUSINESS_NAMES = {"スキルプラス"}

OUTPUT_DIR = ROOT / "System" / "data" / "meta_ads_processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PROCESSED_SHEET_TITLE = "【アドネス株式会社】広告データ（加工）"
PROCESSED_SHEET_ID = "1vYiKh0UL7jMFUQhjzbAkUeAxMhaySZG4sfj_wzg43go"
PROCESSED_TAB_NAME = "Meta"
WRITE_CHUNK_SIZE = 1500

ENRICHED_HEADERS = [
    "集客媒体",
    "ビジネスマネージャID",
    "ビジネスマネージャ名",
    "事業名",
    "ファネル",
    "流入経路",
    "LINEアカウントID",
    "LINEアカウント名",
]

TEXT_HEADERS = {
    "広告アカウントID",
    "キャンペーンID",
    "広告セットID",
    "広告ID",
    "クリエイティブID",
    "動画ID",
    "画像ハッシュ",
    "ビジネスマネージャID",
    "LINEアカウントID",
}


def load_sheet_values(sheet_id: str, tab_name: str) -> list[list[str]]:
    client = get_client("kohara")
    worksheet = client.open_by_key(sheet_id).worksheet(tab_name)
    return worksheet.get_all_values()


def build_index(header: list[str]) -> dict[str, int]:
    return {name: idx for idx, name in enumerate(header)}


def build_mapping_by_account(rows: list[list[str]]) -> dict[str, dict[str, str]]:
    header = rows[0]
    idx = build_index(header)
    mapping = {}
    for row in rows[1:]:
        media = row[idx["集客媒体"]].strip() if len(row) > idx["集客媒体"] else ""
        account_id = row[idx["広告アカウントID"]].strip() if len(row) > idx["広告アカウントID"] else ""
        if media != "Meta広告" or not account_id:
            continue
        mapping[account_id] = {
            "集客媒体": media,
            "ビジネスマネージャID": row[idx["ビジネスマネージャID"]].strip() if len(row) > idx["ビジネスマネージャID"] else "",
            "ビジネスマネージャ名": row[idx["ビジネスマネージャ名"]].strip() if len(row) > idx["ビジネスマネージャ名"] else "",
            "事業名": row[idx["事業名"]].strip() if len(row) > idx["事業名"] else "",
            "ファネル": row[idx["ファネル"]].strip() if len(row) > idx["ファネル"] else "",
            "LINEアカウントID": row[idx["LINEアカウントID"]].strip() if len(row) > idx["LINEアカウントID"] else "",
            "LINEアカウント名": row[idx["LINEアカウント名"]].strip() if len(row) > idx["LINEアカウント名"] else "",
        }
    return mapping


def build_excluded_accounts(rows: list[list[str]]) -> dict[str, dict[str, str]]:
    header = rows[0]
    idx = build_index(header)
    excluded_accounts = {}
    for row in rows[1:]:
        media = row[idx["集客媒体"]].strip() if len(row) > idx["集客媒体"] else ""
        business_name = row[idx["事業名"]].strip() if len(row) > idx["事業名"] else ""
        account_id = row[idx["広告アカウントID"]].strip() if len(row) > idx["広告アカウントID"] else ""
        account_name = row[idx["広告アカウント名"]].strip() if len(row) > idx["広告アカウント名"] else ""
        if media != "Meta広告" or business_name in TARGET_BUSINESS_NAMES or not account_id:
            continue
        excluded_accounts[account_id] = {
            "広告アカウントID": account_id,
            "広告アカウント名": account_name,
            "事業名": business_name,
        }
    return excluded_accounts


def build_route_map(rows: list[list[str]]) -> dict[tuple[str, str], str]:
    header = rows[0]
    idx = build_index(header)
    route_map: dict[tuple[str, str], str] = {}
    for row in rows[1:]:
        media = row[idx["集客媒体"]].strip() if len(row) > idx["集客媒体"] else ""
        funnel = row[idx["ファネル"]].strip() if len(row) > idx["ファネル"] else ""
        route = row[idx["流入経路"]].strip() if len(row) > idx["流入経路"] else ""
        if not media or not funnel or not route:
            continue
        route_map[(media, funnel)] = route
    return route_map


def build_processed_rows(
    raw_rows: list[list[str]],
    mapping_by_account: dict[str, dict[str, str]],
    route_map: dict[tuple[str, str], str],
    excluded_accounts: dict[str, dict[str, str]],
) -> tuple[list[dict[str, str]], list[tuple[str, str]], list[dict[str, str]]]:
    raw_header = raw_rows[0]
    idx = build_index(raw_header)
    processed_rows: list[dict[str, str]] = []
    unmatched_accounts: list[tuple[str, str]] = []
    seen_excluded = set()
    excluded_hits: list[dict[str, str]] = []
    seen_unmatched = set()

    for row in raw_rows[1:]:
        account_id = row[idx["広告アカウントID"]].strip() if len(row) > idx["広告アカウントID"] else ""
        account_name = row[idx["広告アカウント名"]].strip() if len(row) > idx["広告アカウント名"] else ""
        if not account_id:
            continue

        excluded = excluded_accounts.get(account_id)
        if excluded:
            if account_id not in seen_excluded:
                excluded_hits.append(excluded)
                seen_excluded.add(account_id)
            continue

        mapping = mapping_by_account.get(account_id)
        if not mapping:
            key = (account_id, account_name)
            if key not in seen_unmatched:
                unmatched_accounts.append(key)
                seen_unmatched.add(key)
            continue

        item = {header: (row[i] if i < len(row) else "") for i, header in enumerate(raw_header)}
        item["集客媒体"] = mapping["集客媒体"]
        item["ビジネスマネージャID"] = mapping["ビジネスマネージャID"]
        item["ビジネスマネージャ名"] = mapping["ビジネスマネージャ名"]
        item["事業名"] = mapping["事業名"]
        item["ファネル"] = mapping["ファネル"]
        item["流入経路"] = route_map.get((mapping["集客媒体"], mapping["ファネル"]), "")
        item["LINEアカウントID"] = mapping["LINEアカウントID"]
        item["LINEアカウント名"] = mapping["LINEアカウント名"]
        processed_rows.append(item)

    return processed_rows, unmatched_accounts, excluded_hits


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def as_sheet_text(value: str) -> str:
    text = str(value).strip()
    return f"'{text}" if text else ""


def build_sheet_matrix(fieldnames: list[str], rows: list[dict[str, str]]) -> list[list[str]]:
    matrix: list[list[str]] = [fieldnames]
    for row in rows:
        values = []
        for header in fieldnames:
            value = row.get(header, "")
            if header in TEXT_HEADERS and value:
                values.append(as_sheet_text(value))
            else:
                values.append(value)
        matrix.append(values)
    return matrix


def open_or_create_spreadsheet(client, title: str):
    try:
        return client.open(title)
    except SpreadsheetNotFound:
        return client.create(title)


def ensure_processed_worksheet(spreadsheet, tab_name: str, col_count: int):
    try:
        worksheet = spreadsheet.worksheet(tab_name)
    except WorksheetNotFound:
        worksheets = spreadsheet.worksheets()
        if len(worksheets) == 1 and worksheets[0].title in {"シート1", "Sheet1"}:
            worksheet = worksheets[0]
            worksheet.update_title(tab_name)
        else:
            worksheet = spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=col_count)
    return worksheet


def write_rows_to_sheet(
    sheet_id: str,
    sheet_title: str,
    tab_name: str,
    fieldnames: list[str],
    rows: list[dict[str, str]],
) -> tuple[str, str]:
    client = get_client("kohara")
    if sheet_id:
        spreadsheet = client.open_by_key(sheet_id)
    else:
        spreadsheet = open_or_create_spreadsheet(client, sheet_title)
    worksheet = ensure_processed_worksheet(spreadsheet, tab_name, len(fieldnames))
    matrix = build_sheet_matrix(fieldnames, rows)

    target_rows = max(len(matrix), 1000)
    target_cols = len(fieldnames)
    worksheet.resize(rows=target_rows, cols=target_cols)
    worksheet.clear()
    worksheet.update(range_name="A1", values=[fieldnames], value_input_option="RAW")

    for start in range(1, len(matrix), WRITE_CHUNK_SIZE):
        chunk = matrix[start:start + WRITE_CHUNK_SIZE]
        worksheet.update(range_name=f"A{start + 1}", values=chunk, value_input_option="RAW")

    apply_formatting(spreadsheet, worksheet, fieldnames, include_table_styles=False, include_protection=False)
    return spreadsheet.id, worksheet.title


def main() -> None:
    parser = argparse.ArgumentParser(description="Meta広告の加工用CSVを生成する")
    parser.add_argument("--output-prefix", default="meta_ads_processed", help="出力ファイル名プレフィックス")
    parser.add_argument("--write-sheet", action="store_true", help="加工用スプレッドシートにも書き出す")
    parser.add_argument("--sheet-id", default=PROCESSED_SHEET_ID, help="加工用スプレッドシートID")
    parser.add_argument("--sheet-title", default=PROCESSED_SHEET_TITLE, help="加工用スプレッドシート名")
    parser.add_argument("--tab-name", default=PROCESSED_TAB_NAME, help="加工用タブ名")
    args = parser.parse_args()

    raw_rows = load_sheet_values(RAW_SHEET_ID, RAW_TAB_NAME)
    account_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_ACCOUNT_TAB)
    mapping_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_MAPPING_TAB)
    route_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_ROUTE_TAB)

    excluded_accounts = build_excluded_accounts(account_rows)
    mapping_by_account = build_mapping_by_account(mapping_rows)
    route_map = build_route_map(route_rows)
    processed_rows, unmatched_accounts, excluded_hits = build_processed_rows(
        raw_rows,
        mapping_by_account,
        route_map,
        excluded_accounts,
    )

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"{args.output_prefix}_{timestamp}.csv"
    summary_path = OUTPUT_DIR / f"{args.output_prefix}_{timestamp}_summary.json"

    raw_header = raw_rows[0]
    fieldnames = ENRICHED_HEADERS + raw_header
    write_csv(csv_path, fieldnames, processed_rows)

    funnel_counter = Counter(row["ファネル"] for row in processed_rows if row.get("ファネル"))
    summary = {
        "saved_to": str(csv_path),
        "total_processed_rows": len(processed_rows),
        "matched_account_count": len({row["広告アカウントID"] for row in processed_rows}),
        "unmatched_accounts": [
            {"広告アカウントID": account_id, "広告アカウント名": account_name}
            for account_id, account_name in unmatched_accounts
        ],
        "unmatched_account_count": len(unmatched_accounts),
        "excluded_accounts": excluded_hits,
        "excluded_account_count": len(excluded_hits),
        "funnel_counts": dict(funnel_counter),
    }

    if args.write_sheet:
        processed_sheet_id, processed_tab_name = write_rows_to_sheet(
            sheet_id=args.sheet_id,
            sheet_title=args.sheet_title,
            tab_name=args.tab_name,
            fieldnames=fieldnames,
            rows=processed_rows,
        )
        summary["processed_sheet_id"] = processed_sheet_id
        summary["processed_tab_name"] = processed_tab_name

    write_json(summary_path, summary)

    print(f"保存先: {csv_path}")
    print(f"サマリー: {summary_path}")
    print(f"加工行数: {len(processed_rows)}")
    print(f"未照合アカウント数: {len(unmatched_accounts)}")
    if args.write_sheet:
        print(f"加工シート: {args.sheet_title} / {args.tab_name}")


if __name__ == "__main__":
    main()
