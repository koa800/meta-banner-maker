#!/usr/bin/env python3
"""
オフライン広告の過去分を収集シートへ投入する。

- 粒度: 1行 = 1案件
- 集客媒体: オフライン広告
- 発生日が空なら空欄のまま保持
- 同一案件は重複追加しない
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheets_manager import get_client


TARGET_SPREADSHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
SOURCE_SPREADSHEET_ID = "1P8clrwVZsh_wjhq9E5BmFAGUwOkkIBvYFxbxtuhlMaE"
SOURCE_TAB_NAME = "オフライン広告数値"
TARGET_TAB_NAME = "オフライン"
TARGET_HEADERS = [
    "発生日",
    "集客媒体",
    "企画名",
    "出稿場所",
    "掲載期間",
    "広告費",
    "取込日時",
    "備考",
]


def normalize_date(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return text


def normalize_money(value: str):
    text = (value or "").strip()
    if not text:
        return ""
    digits = (
        text.replace("¥", "")
        .replace(",", "")
        .replace("円", "")
        .replace(" ", "")
        .strip()
    )
    try:
        return int(digits)
    except ValueError:
        return text


def normalize_key_part(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def build_key(record: dict) -> tuple[str, str, str, str, str]:
    return (
        normalize_key_part(record.get("企画名")),
        normalize_key_part(record.get("出稿場所")),
        normalize_key_part(record.get("掲載期間")),
        normalize_key_part(record.get("発生日")),
        normalize_key_part(record.get("広告費")),
    )


def ensure_target_header(ws):
    values = ws.get_all_values()
    if not values:
        if ws.col_count != len(TARGET_HEADERS):
            ws.resize(cols=len(TARGET_HEADERS))
        ws.update("A1", [TARGET_HEADERS], value_input_option="RAW")
        return

    current_headers = values[0]
    if current_headers[: len(TARGET_HEADERS)] == TARGET_HEADERS and len(current_headers) == len(TARGET_HEADERS):
        if ws.col_count != len(TARGET_HEADERS):
            ws.resize(cols=len(TARGET_HEADERS))
        return

    migrated_rows = []
    for row in values[1:]:
        migrated_rows.append(
            [
                row[current_headers.index(header)].strip()
                if header in current_headers and current_headers.index(header) < len(row)
                else ""
                for header in TARGET_HEADERS
            ]
        )

    ws.clear()
    if ws.col_count != len(TARGET_HEADERS):
        ws.resize(cols=len(TARGET_HEADERS))
    ws.update("A1", [TARGET_HEADERS] + migrated_rows, value_input_option="RAW")


def load_existing_keys(ws) -> set[tuple[str, str, str, str, str]]:
    values = ws.get_all_values()
    if not values:
        return set()
    rows = values[1:]
    keys = set()
    for row in rows:
        padded = row + [""] * (len(TARGET_HEADERS) - len(row))
        record = {
            "発生日": padded[0],
            "企画名": padded[2],
            "出稿場所": padded[3],
            "掲載期間": padded[4],
            "広告費": padded[5],
        }
        keys.add(build_key(record))
    return keys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-sheet-id", default=TARGET_SPREADSHEET_ID)
    parser.add_argument("--source-sheet-id", default=SOURCE_SPREADSHEET_ID)
    parser.add_argument("--source-tab", default=SOURCE_TAB_NAME)
    parser.add_argument("--target-tab", default=TARGET_TAB_NAME)
    args = parser.parse_args()

    client = get_client("kohara")
    source_sh = client.open_by_key(args.source_sheet_id)
    target_sh = client.open_by_key(args.target_sheet_id)

    source_ws = source_sh.worksheet(args.source_tab)
    try:
        target_ws = target_sh.worksheet(args.target_tab)
    except Exception:
        target_ws = target_sh.add_worksheet(title=args.target_tab, rows=1000, cols=len(TARGET_HEADERS))

    ensure_target_header(target_ws)
    existing_keys = load_existing_keys(target_ws)

    source_values = source_ws.get_all_values()
    if not source_values:
        print("元シートが空です")
        return

    headers = source_values[0]
    indexes = {
        "企画名": headers.index("企画名"),
        "出稿場所": headers.index("出稿場所"),
        "掲載期間": headers.index("掲載期間"),
        "発生日": headers.index("発生日"),
        "広告費": headers.index("広告費"),
    }

    now_text = datetime.now().strftime("%Y/%m/%d %H:%M")
    append_rows = []
    skipped = 0

    for row_number, row in enumerate(source_values[1:], start=2):
        padded = row + [""] * (len(headers) - len(row))
        item = {name: padded[idx].strip() for name, idx in indexes.items()}
        if not any(item.values()):
            continue

        record = {
            "発生日": normalize_date(item["発生日"]),
            "集客媒体": "オフライン広告",
            "企画名": item["企画名"],
            "出稿場所": item["出稿場所"],
            "掲載期間": item["掲載期間"],
            "広告費": normalize_money(item["広告費"]),
            "取込日時": now_text,
            "備考": "",
        }
        key = build_key(record)
        if key in existing_keys:
            skipped += 1
            continue
        existing_keys.add(key)
        append_rows.append([
            record["発生日"],
            record["集客媒体"],
            record["企画名"],
            record["出稿場所"],
            record["掲載期間"],
            record["広告費"],
            record["取込日時"],
            record["備考"],
        ])

    if append_rows:
        target_ws.append_rows(append_rows, value_input_option="USER_ENTERED")

    print(
        f"オフライン広告取込: 追加 {len(append_rows)} 件 / 重複スキップ {skipped} 件 / 対象 {len(source_values) - 1} 行"
    )


if __name__ == "__main__":
    main()
