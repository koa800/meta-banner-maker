#!/usr/bin/env python3
"""決済データ用の商品マスタ構造をマスタデータへ反映する。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import gspread

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sheets_manager import get_client  # noqa: E402


MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_PRODUCT_TAB = "商品マスタ"
PAYMENT_MAPPING_TAB = "決済商品変換マスタ"

REFERENCE_SHEET_ID = "1Y6akVont1zmqoVgLS527tbjMButHUS6ej5zHdY8XhA0"
REFERENCE_TAB = "シート1"

PAYMENT_COLLECTION_SHEET_ID = "1FfGM0HpofM8yayhJniArXp_vQ6-4JRvlp6rxDt-eHTI"
PAYMENT_COLLECTION_TAB = "決済データ"

PRODUCT_MASTER_HEADERS = [
    "商品コード",
    "商品名",
    "対象顧客",
    "販売状況",
    "価格",
    "購入形態",
    "初期費用",
    "商品種類",
    "事業区分",
]

PAYMENT_MAPPING_HEADERS = [
    "決済ソース",
    "生商品名",
    "参照件数",
    "参照金額",
    "正式商品名",
    "事業区分",
    "判定区分",
    "補助条件",
    "判定根拠",
    "備考",
]

BUSINESS_SKILLPLUS = "スキルプラス事業"
BUSINESS_ADDNESS = "Addness事業"
BUSINESS_AI_TRAINING = "AI研修事業"

PAYMENT_MAPPING_WIDTHS = [120, 360, 90, 130, 260, 130, 110, 220, 220, 240]
PRODUCT_MASTER_WIDTHS = [120, 260, 140, 100, 110, 120, 100, 100, 130]


@dataclass
class PaymentAggregate:
    source: str
    raw_name: str
    count: int = 0
    amount: int = 0


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(title)
        if ws.row_count < rows or ws.col_count < cols:
            ws.resize(rows=max(ws.row_count, rows), cols=max(ws.col_count, cols))
        return ws
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def parse_amount(value: str) -> int:
    text = (value or "").strip()
    if not text:
        return 0
    normalized = (
        text.replace("¥", "")
        .replace(",", "")
        .replace("，", "")
        .replace("−", "-")
        .replace("—", "-")
        .replace("ー", "-")
        .replace(" ", "")
    )
    match = re.search(r"-?\d+", normalized)
    return int(match.group()) if match else 0


def normalize_display_amount(value: int) -> str:
    return f"¥{value:,}"


def source_sale_is_success(src: str, event: str, status: str) -> bool:
    if src == "UnivaPay":
        return event == "売上" and status == "成功"
    if src == "MOSH":
        return status == "支払い済み"
    if src == "INVOY":
        return status == "入金済"
    if src == "日本プラム":
        return status == "最終承認"
    if src in {"きらぼし銀行", "CBS", "京都信販", "CREDIX"}:
        return True
    return False


def normalize_candidate_name(raw_name: str) -> str:
    text = (raw_name or "").strip()
    if not text or text == "(空欄)":
        return text

    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = re.sub(r"\s*~[^~]*~\s*$", "", text).strip()
    text = text.replace("（全額返金保証付）", "")
    text = text.replace("（全額返金保証）", "")
    text = text.replace("~購入後1週間以内に限り【全額返金保証付き】~", "")
    text = text.replace("　", " ").strip()
    return text


def infer_business_from_master(code: str, name: str, current: str) -> str:
    if current:
        return current

    normalized = (name or "").replace("　", " ").strip()

    if "スキルプラスfor Biz" in normalized or "研修" in normalized:
        return BUSINESS_AI_TRAINING

    if code.startswith("IN-SYS-") or code.startswith("IN-BIZ-"):
        return BUSINESS_ADDNESS

    if "AIエージェント" in normalized or "概念実証" in normalized or "PoC" in normalized:
        return BUSINESS_ADDNESS

    if code.startswith("IN-SKL-"):
        return BUSINESS_SKILLPLUS

    skillplus_markers = (
        "AIX",
        "SNSマーケ",
        "みかみ",
        "AICAN",
        "アクションマップ",
        "アドネスサポートパック",
    )
    if code.startswith("IN-EDU-") and any(marker in normalized for marker in skillplus_markers):
        return BUSINESS_SKILLPLUS

    return ""


def load_product_master_rows(ws: gspread.Worksheet) -> tuple[list[str], list[list[str]]]:
    values = ws.get_all_values()
    if not values:
        return PRODUCT_MASTER_HEADERS[:], []
    headers = values[0]
    rows = values[1:]
    return headers, rows


def sync_product_master_structure(ws: gspread.Worksheet) -> dict[str, tuple[str, str]]:
    headers, rows = load_product_master_rows(ws)
    if not headers:
        headers = PRODUCT_MASTER_HEADERS[:]

    for header in PRODUCT_MASTER_HEADERS:
        if header not in headers:
            headers.append(header)

    normalized_rows: list[list[str]] = []
    product_index: dict[str, tuple[str, str]] = {}

    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        record = {headers[idx]: padded[idx] for idx in range(len(headers))}
        code = record.get("商品コード", "").strip()
        name = record.get("商品名", "").strip()
        if not code and not name:
            continue

        business = infer_business_from_master(code, name, record.get("事業区分", "").strip())
        record["事業区分"] = business
        normalized_rows.append([record.get(header, "") for header in headers])
        product_index[name] = (code, business)

    payload = [headers] + normalized_rows
    ws.clear()
    ws.resize(rows=max(len(payload) + 20, 200), cols=len(headers))
    ws.update(range_name="A1", values=payload, value_input_option="USER_ENTERED")
    apply_basic_formatting(ws, PRODUCT_MASTER_WIDTHS)
    return product_index


def load_reference_mapping(ws: gspread.Worksheet) -> dict[str, str]:
    rows = ws.get_all_values()
    mapping: dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 3:
            continue
        raw_name = (row[0] or "").strip()
        mapped_name = (row[2] or "").strip()
        if raw_name and mapped_name and raw_name not in mapping:
            mapping[raw_name] = mapped_name
    return mapping


def aggregate_live_payment_products(ws: gspread.Worksheet) -> list[PaymentAggregate]:
    rows = ws.get_all_values()
    if not rows:
        return []

    headers = rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    aggregates: dict[tuple[str, str], PaymentAggregate] = {}

    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        source = padded[idx["参照システム"]].strip()
        event = padded[idx["イベント"]].strip()
        status = padded[idx["課金ステータス"]].strip()
        if not source_sale_is_success(source, event, status):
            continue

        raw_name = padded[idx["商品名"]].strip() or "(空欄)"
        key = (source, raw_name)
        aggregate = aggregates.setdefault(key, PaymentAggregate(source=source, raw_name=raw_name))
        aggregate.count += 1
        aggregate.amount += parse_amount(padded[idx["イベント金額"]])

    return sorted(
        aggregates.values(),
        key=lambda item: (-item.amount, -item.count, item.source, item.raw_name),
    )


def build_mapping_rows(
    aggregates: Iterable[PaymentAggregate],
    product_index: dict[str, tuple[str, str]],
    reference_mapping: dict[str, str],
) -> list[list[str]]:
    rows: list[list[str]] = [PAYMENT_MAPPING_HEADERS]
    exact_product_names = set(product_index.keys())

    for aggregate in aggregates:
        raw_name = aggregate.raw_name
        candidate_name = ""
        business = ""
        status = "要確認"
        extra_condition = ""
        reason_parts: list[str] = []
        note = ""

        if raw_name == "(空欄)":
            status = "不明"
            extra_condition = "イベント金額・課金タイプ・メール照合で個別判定"
            note = "空欄商品のため自動確定しない"
        else:
            if raw_name in exact_product_names:
                candidate_name = raw_name
                reason_parts.append("商品マスタ完全一致")
            elif raw_name in reference_mapping:
                candidate_name = reference_mapping[raw_name]
                reason_parts.append("不明商品名照合テーブル")
            else:
                normalized = normalize_candidate_name(raw_name)
                if normalized in exact_product_names:
                    candidate_name = normalized
                    reason_parts.append("装飾除去で一致")

            if candidate_name:
                code, business = product_index.get(candidate_name, ("", ""))
                if candidate_name not in exact_product_names:
                    status = "商品マスタ未登録"
                    note = "正式商品名候補はあるが商品マスタ未登録"
                else:
                    status = "変換済み"
                    if code:
                        reason_parts.append(code)
            else:
                status = "要確認"
                note = "正式商品名候補を未確定"

        rows.append(
            [
                aggregate.source,
                raw_name,
                str(aggregate.count),
                normalize_display_amount(aggregate.amount),
                candidate_name,
                business,
                status,
                extra_condition,
                " / ".join(reason_parts),
                note,
            ]
        )

    return rows


def apply_basic_formatting(ws: gspread.Worksheet, widths: list[int]) -> None:
    ws.freeze(rows=1)
    ws.set_basic_filter()
    end_col = max(len(widths), ws.col_count)
    ws.format(
        f"A1:{gspread.utils.rowcol_to_a1(1, end_col)}",
        {
            "backgroundColor": {"red": 0.247, "green": 0.42, "blue": 0.878},
            "textFormat": {
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                "bold": True,
                "fontSize": 10,
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "CLIP",
        },
    )
    ws.format(
        f"A2:{gspread.utils.rowcol_to_a1(max(ws.row_count, 2), end_col)}",
        {
            "textFormat": {"fontSize": 10},
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "CLIP",
        },
    )

    requests = []
    for idx, width in enumerate(widths):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    requests.extend(
        [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 34},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": max(ws.row_count, 2),
                    },
                    "properties": {"pixelSize": 24},
                    "fields": "pixelSize",
                }
            },
        ]
    )
    ws.spreadsheet.batch_update({"requests": requests})


def write_mapping_rows(ws: gspread.Worksheet, rows: list[list[str]]) -> None:
    ws.clear()
    ws.resize(rows=max(len(rows) + 50, 500), cols=len(PAYMENT_MAPPING_HEADERS))
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")
    apply_basic_formatting(ws, PAYMENT_MAPPING_WIDTHS)


def main() -> None:
    gc = get_client()

    master_ss = gc.open_by_key(MASTER_SHEET_ID)
    product_ws = master_ss.worksheet(MASTER_PRODUCT_TAB)
    mapping_ws = ensure_worksheet(master_ss, PAYMENT_MAPPING_TAB, 500, len(PAYMENT_MAPPING_HEADERS))

    reference_ss = gc.open_by_key(REFERENCE_SHEET_ID)
    reference_ws = reference_ss.worksheet(REFERENCE_TAB)

    payment_ss = gc.open_by_key(PAYMENT_COLLECTION_SHEET_ID)
    payment_ws = payment_ss.worksheet(PAYMENT_COLLECTION_TAB)

    product_index = sync_product_master_structure(product_ws)
    reference_mapping = load_reference_mapping(reference_ws)
    aggregates = aggregate_live_payment_products(payment_ws)
    mapping_rows = build_mapping_rows(aggregates, product_index, reference_mapping)
    write_mapping_rows(mapping_ws, mapping_rows)

    print(f"商品マスタ更新: {len(product_index):,} 商品")
    print(f"決済商品変換マスタ更新: {len(mapping_rows) - 1:,} 行")


if __name__ == "__main__":
    main()
