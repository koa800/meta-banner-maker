#!/usr/bin/env python3
"""広告データ（収集）を媒体横断で加工シートへ整形する。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System"))

from gspread.exceptions import SpreadsheetNotFound, WorksheetNotFound  # noqa: E402
from sheets_manager import get_client  # noqa: E402
from setup_ads_sheet import apply_formatting  # noqa: E402


RAW_SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
RAW_TABS = {
    "Meta広告": "Meta",
    "TikTok広告": "TikTok",
    "X広告": "X",
}

MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_ACCOUNT_TAB = "広告アカウント"
MASTER_MAPPING_TAB = "広告-ファネル-LINE対応表"
MASTER_ROUTE_TAB = "流入経路マスタ"
TARGET_BUSINESS_NAMES = {"スキルプラス"}

PROCESSED_SHEET_TITLE = "【アドネス株式会社】広告データ（加工）"
PROCESSED_SHEET_ID = "1vYiKh0UL7jMFUQhjzbAkUeAxMhaySZG4sfj_wzg43go"
PROCESSED_TABS = {
    "Meta広告": "Meta",
    "TikTok広告": "TikTok",
    "X広告": "X",
}
INTEGRATED_TAB_NAME = "媒体統合"
WRITE_CHUNK_SIZE = 1500

OUTPUT_DIR = ROOT / "System" / "data" / "ads_processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

COMMON_HEADERS = [
    "集客媒体",
    "ビジネスマネージャID",
    "ビジネスマネージャ名",
    "事業名",
    "ファネル",
    "流入経路",
    "LINEアカウントID",
    "LINEアカウント名",
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "現在配信ステータス",
    "広告作成日",
    "最終更新日",
    "配信開始日",
    "配信終了日",
    "CR識別キー",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "LP識別キー",
    "プロモーション種別",
    "出稿形式レーン",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "クリック数（媒体定義）",
    "遷移クリック数",
    "遷移クリック数（ユニーク）",
    "消化金額",
    "コンバージョン数",
    "動画再生数",
    "動画2秒再生数",
    "動画6秒再生数",
    "動画完全再生数",
    "エンゲージメント数",
    "エンゲージメント率",
    "コンバージョン詳細",
]

TEXT_HEADERS = {
    "広告アカウントID",
    "キャンペーンID",
    "広告グループID",
    "広告ID",
    "ビジネスマネージャID",
    "LINEアカウントID",
    "CR識別キー",
    "メディアID",
}


def load_sheet_values(sheet_id: str, tab_name: str) -> list[list[str]]:
    client = get_client("kohara")
    worksheet = client.open_by_key(sheet_id).worksheet(tab_name)
    return worksheet.get_all_values()


def build_index(header: list[str]) -> dict[str, int]:
    return {name: idx for idx, name in enumerate(header)}


def cell(row: list[str], idx: dict[str, int], header: str) -> str:
    col = idx.get(header)
    if col is None or col >= len(row):
        return ""
    return str(row[col]).strip()


def normalize_lookup_id(value: Any) -> str:
    text = str(value or "").strip()
    if text.startswith("'"):
        text = text[1:]
    if text.endswith(".0"):
        integer, decimal = text.rsplit(".", 1)
        if decimal == "0":
            text = integer
    return text


def as_sheet_text(value: str) -> str:
    text = str(value or "").strip()
    return f"'{text}" if text else ""


def parse_number(value: str) -> float:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def has_activity(record: dict[str, str]) -> bool:
    activity_headers = [
        "インプレッション",
        "クリック数（媒体定義）",
        "遷移クリック数",
        "消化金額",
        "コンバージョン数",
        "動画再生数",
        "エンゲージメント数",
    ]
    return any(parse_number(record.get(header, "")) > 0 for header in activity_headers)


def normalize_lp_key(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    path = parsed.path.rstrip("/") or "/"
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"


def build_account_master(rows: list[list[str]]) -> dict[tuple[str, str], dict[str, str]]:
    header = rows[0]
    idx = build_index(header)
    result: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows[1:]:
        media = cell(row, idx, "集客媒体")
        account_id = normalize_lookup_id(cell(row, idx, "広告アカウントID"))
        if not media or not account_id:
            continue
        result[(media, account_id)] = {
            "集客媒体": media,
            "ビジネスマネージャID": normalize_lookup_id(cell(row, idx, "ビジネスマネージャID")),
            "ビジネスマネージャ名": cell(row, idx, "ビジネスマネージャ名"),
            "広告アカウント名": cell(row, idx, "広告アカウント名"),
            "事業名": cell(row, idx, "事業名"),
            "備考": cell(row, idx, "備考"),
        }
    return result


def build_mapping_master(rows: list[list[str]]) -> dict[tuple[str, str], list[dict[str, str]]]:
    header = rows[0]
    idx = build_index(header)
    result: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows[1:]:
        media = cell(row, idx, "集客媒体")
        account_id = normalize_lookup_id(cell(row, idx, "広告アカウントID"))
        if not media or not account_id:
            continue
        item = {
            "ファネル": cell(row, idx, "ファネル"),
            "LINEアカウントID": normalize_lookup_id(cell(row, idx, "LINEアカウントID")),
            "LINEアカウント名": cell(row, idx, "LINEアカウント名"),
        }
        if item not in result[(media, account_id)]:
            result[(media, account_id)].append(item)
    return result


def build_route_map(rows: list[list[str]]) -> dict[tuple[str, str], str]:
    header = rows[0]
    idx = build_index(header)
    route_map: dict[tuple[str, str], str] = {}
    for row in rows[1:]:
        media = cell(row, idx, "集客媒体")
        funnel = cell(row, idx, "ファネル")
        route = cell(row, idx, "流入経路")
        if media and funnel and route:
            route_map[(media, funnel)] = route
    return route_map


def mapping_keywords(funnel: str) -> list[str]:
    table = {
        "AI": ["ai"],
        "センサーズ": ["センサーズ", "sns"],
        "スキルプラス": ["スキルプラス"],
        "ライトプラン": ["ライトプラン", "サブスク", "秘密の部屋"],
        "ブランド認知": ["ブランド認知", "認知"],
        "直個別": ["直個別"],
        "アドプロ": ["アドプロ"],
        "みかみメイン": ["みかみメイン"],
        "AI研修": ["ai研修"],
    }
    return [keyword.lower() for keyword in table.get(funnel, [funnel]) if keyword]


def resolve_mapping(
    media: str,
    record: dict[str, str],
    mapping_candidates: dict[tuple[str, str], list[dict[str, str]]],
) -> tuple[dict[str, str] | None, str]:
    account_id = normalize_lookup_id(record.get("広告アカウントID", ""))
    candidates = mapping_candidates.get((media, account_id), [])
    if not candidates:
        return None, "未照合"
    if len(candidates) == 1:
        return candidates[0], ""

    haystack = " ".join(
        [
            record.get("キャンペーン名", ""),
            record.get("広告グループ名", ""),
            record.get("広告名", ""),
            record.get("遷移先URL", ""),
        ]
    ).lower()
    matched = []
    for candidate in candidates:
        if any(keyword in haystack for keyword in mapping_keywords(candidate.get("ファネル", ""))):
            matched.append(candidate)
    if len(matched) == 1:
        return matched[0], ""
    return None, "要確認（複数候補）"


def meta_media_type_and_id(record: dict[str, str]) -> tuple[str, str]:
    if record.get("動画ID"):
        return "VIDEO", record["動画ID"]
    if record.get("画像ハッシュ"):
        return "IMAGE", record["画像ハッシュ"]
    return "", ""


def build_meta_record(row: list[str], idx: dict[str, int]) -> dict[str, str]:
    media_type, media_id = meta_media_type_and_id(
        {
            "動画ID": cell(row, idx, "動画ID"),
            "画像ハッシュ": cell(row, idx, "画像ハッシュ"),
        }
    )
    creative_id = normalize_lookup_id(cell(row, idx, "クリエイティブID"))
    video_id = normalize_lookup_id(cell(row, idx, "動画ID"))
    image_hash = cell(row, idx, "画像ハッシュ")
    cr_key = creative_id or video_id or image_hash
    url = cell(row, idx, "遷移先URL")
    return {
        "日付": cell(row, idx, "日付"),
        "広告アカウント名": cell(row, idx, "広告アカウント名"),
        "広告アカウントID": normalize_lookup_id(cell(row, idx, "広告アカウントID")),
        "キャンペーンID": normalize_lookup_id(cell(row, idx, "キャンペーンID")),
        "キャンペーン名": cell(row, idx, "キャンペーン名"),
        "広告グループID": normalize_lookup_id(cell(row, idx, "広告セットID")),
        "広告グループ名": cell(row, idx, "広告セット名"),
        "広告ID": normalize_lookup_id(cell(row, idx, "広告ID")),
        "広告名": cell(row, idx, "広告名"),
        "現在配信ステータス": cell(row, idx, "配信ステータス"),
        "広告作成日": cell(row, idx, "広告作成日"),
        "最終更新日": cell(row, idx, "最終更新日"),
        "CR識別キー": cr_key,
        "メディアタイプ": media_type,
        "メディアID": media_id,
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": "",
        "出稿形式レーン": "",
        "インプレッション": cell(row, idx, "インプレッション"),
        "リーチ": cell(row, idx, "リーチ"),
        "フリークエンシー": cell(row, idx, "フリークエンシー"),
        "クリック数（媒体定義）": cell(row, idx, "総クリック数"),
        "遷移クリック数": cell(row, idx, "外部クリック数") or cell(row, idx, "リンククリック数"),
        "遷移クリック数（ユニーク）": cell(row, idx, "外部クリック数（ユニーク）") or cell(row, idx, "リンククリック数（ユニーク）"),
        "消化金額": cell(row, idx, "消化金額"),
        "コンバージョン数": "",
        "動画再生数": "",
        "動画2秒再生数": "",
        "動画6秒再生数": "",
        "動画完全再生数": "",
        "エンゲージメント数": "",
        "エンゲージメント率": "",
        "コンバージョン詳細": cell(row, idx, "コンバージョン（JSON）"),
    }


def build_tiktok_record(row: list[str], idx: dict[str, int]) -> dict[str, str]:
    url = cell(row, idx, "遷移先URL")
    return {
        "日付": cell(row, idx, "日付"),
        "広告アカウント名": cell(row, idx, "広告アカウント名"),
        "広告アカウントID": normalize_lookup_id(cell(row, idx, "広告アカウントID")),
        "キャンペーンID": normalize_lookup_id(cell(row, idx, "キャンペーンID")),
        "キャンペーン名": cell(row, idx, "キャンペーン名"),
        "広告グループID": normalize_lookup_id(cell(row, idx, "広告グループID")),
        "広告グループ名": cell(row, idx, "広告グループ名"),
        "広告ID": normalize_lookup_id(cell(row, idx, "広告ID")),
        "広告名": cell(row, idx, "広告名"),
        "現在配信ステータス": cell(row, idx, "配信ステータス"),
        "広告作成日": cell(row, idx, "広告作成日"),
        "最終更新日": cell(row, idx, "最終更新日"),
        "CR識別キー": normalize_lookup_id(cell(row, idx, "CR識別キー")),
        "メディアタイプ": cell(row, idx, "メディアタイプ"),
        "メディアID": normalize_lookup_id(cell(row, idx, "メディアID")),
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": cell(row, idx, "プロモーション種別"),
        "出稿形式レーン": cell(row, idx, "出稿形式レーン"),
        "インプレッション": cell(row, idx, "インプレッション"),
        "リーチ": cell(row, idx, "リーチ"),
        "フリークエンシー": cell(row, idx, "フリークエンシー"),
        "クリック数（媒体定義）": cell(row, idx, "クリック数（all）"),
        "遷移クリック数": "",
        "遷移クリック数（ユニーク）": "",
        "消化金額": cell(row, idx, "消化金額"),
        "コンバージョン数": cell(row, idx, "コンバージョン数（optimization event）"),
        "動画再生数": cell(row, idx, "動画再生数"),
        "動画2秒再生数": cell(row, idx, "動画2秒再生数"),
        "動画6秒再生数": cell(row, idx, "動画6秒再生数"),
        "動画完全再生数": cell(row, idx, "動画完全再生数"),
        "エンゲージメント数": "",
        "エンゲージメント率": "",
        "コンバージョン詳細": "",
    }


def build_x_record(row: list[str], idx: dict[str, int]) -> dict[str, str]:
    url = cell(row, idx, "遷移先URL")
    link_clicks = cell(row, idx, "リンククリック数")
    return {
        "日付": cell(row, idx, "日付"),
        "広告アカウント名": cell(row, idx, "広告アカウント名"),
        "広告アカウントID": normalize_lookup_id(cell(row, idx, "広告アカウントID")),
        "キャンペーンID": normalize_lookup_id(cell(row, idx, "キャンペーンID")),
        "キャンペーン名": cell(row, idx, "キャンペーン名"),
        "広告グループID": normalize_lookup_id(cell(row, idx, "広告グループID")),
        "広告グループ名": cell(row, idx, "広告グループ名"),
        "広告ID": normalize_lookup_id(cell(row, idx, "広告ID")),
        "広告名": cell(row, idx, "広告名"),
        "現在配信ステータス": cell(row, idx, "配信ステータス"),
        "広告作成日": cell(row, idx, "広告作成日"),
        "最終更新日": cell(row, idx, "最終更新日"),
        "CR識別キー": normalize_lookup_id(cell(row, idx, "クリエイティブID")),
        "メディアタイプ": cell(row, idx, "メディアタイプ"),
        "メディアID": normalize_lookup_id(cell(row, idx, "メディアID")),
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": "",
        "出稿形式レーン": "",
        "インプレッション": cell(row, idx, "インプレッション"),
        "リーチ": "",
        "フリークエンシー": "",
        "クリック数（媒体定義）": link_clicks,
        "遷移クリック数": link_clicks,
        "遷移クリック数（ユニーク）": "",
        "消化金額": cell(row, idx, "消化金額"),
        "コンバージョン数": "",
        "動画再生数": "",
        "動画2秒再生数": "",
        "動画6秒再生数": "",
        "動画完全再生数": "",
        "エンゲージメント数": cell(row, idx, "エンゲージメント数"),
        "エンゲージメント率": cell(row, idx, "エンゲージメント率"),
        "コンバージョン詳細": "",
    }


def build_media_record(media: str, row: list[str], idx: dict[str, int]) -> dict[str, str]:
    if media == "Meta広告":
        return build_meta_record(row, idx)
    if media == "TikTok広告":
        return build_tiktok_record(row, idx)
    if media == "X広告":
        return build_x_record(row, idx)
    raise ValueError(f"unsupported media: {media}")


def collect_processed_rows(
    media: str,
    raw_rows: list[list[str]],
    account_master: dict[tuple[str, str], dict[str, str]],
    mapping_master: dict[tuple[str, str], list[dict[str, str]]],
    route_map: dict[tuple[str, str], str],
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    header = raw_rows[0]
    idx = build_index(header)
    processed: list[dict[str, str]] = []
    unmatched: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    seen_unmatched = set()
    seen_excluded = set()

    for row in raw_rows[1:]:
        record = build_media_record(media, row, idx)
        account_id = record["広告アカウントID"]
        if not account_id:
            continue
        account_info = account_master.get((media, account_id))
        if not account_info:
            key = (media, account_id, record["広告アカウント名"])
            if key not in seen_unmatched:
                unmatched.append({
                    "集客媒体": media,
                    "広告アカウントID": account_id,
                    "広告アカウント名": record["広告アカウント名"],
                    "理由": "広告アカウントマスタ未登録",
                })
                seen_unmatched.add(key)
            continue
        if account_info.get("事業名") not in TARGET_BUSINESS_NAMES:
            key = (media, account_id)
            if key not in seen_excluded:
                excluded.append({
                    "集客媒体": media,
                    "広告アカウントID": account_id,
                    "広告アカウント名": record["広告アカウント名"],
                    "事業名": account_info.get("事業名", ""),
                })
                seen_excluded.add(key)
            continue

        mapping, reason = resolve_mapping(media, record, mapping_master)
        if not mapping:
            key = (media, account_id, record["広告アカウント名"], reason)
            if key not in seen_unmatched:
                unmatched.append({
                    "集客媒体": media,
                    "広告アカウントID": account_id,
                    "広告アカウント名": record["広告アカウント名"],
                    "理由": reason or "広告-ファネル-LINE対応表未登録",
                })
                seen_unmatched.add(key)
            continue

        item = {
            "集客媒体": media,
            "ビジネスマネージャID": account_info.get("ビジネスマネージャID", ""),
            "ビジネスマネージャ名": account_info.get("ビジネスマネージャ名", ""),
            "事業名": account_info.get("事業名", ""),
            "ファネル": mapping.get("ファネル", ""),
            "流入経路": route_map.get((media, mapping.get("ファネル", "")), ""),
            "LINEアカウントID": mapping.get("LINEアカウントID", ""),
            "LINEアカウント名": mapping.get("LINEアカウント名", ""),
            **record,
            "配信開始日": "",
            "配信終了日": "",
        }
        processed.append(item)

    return processed, unmatched, excluded


def fill_delivery_span(rows: list[dict[str, str]]) -> None:
    spans: dict[tuple[str, str, str], list[str]] = {}
    for row in rows:
        key = (row.get("集客媒体", ""), row.get("広告アカウントID", ""), row.get("広告ID", ""))
        if not all(key) or not has_activity(row):
            continue
        date_value = row.get("日付", "")
        if not date_value:
            continue
        bucket = spans.setdefault(key, [date_value, date_value])
        if date_value < bucket[0]:
            bucket[0] = date_value
        if date_value > bucket[1]:
            bucket[1] = date_value
    for row in rows:
        key = (row.get("集客媒体", ""), row.get("広告アカウントID", ""), row.get("広告ID", ""))
        span = spans.get(key)
        if span:
            row["配信開始日"] = span[0]
            row["配信終了日"] = span[1]


def build_sheet_matrix(rows: list[dict[str, str]]) -> list[list[str]]:
    matrix = [COMMON_HEADERS]
    for row in rows:
        values = []
        for header in COMMON_HEADERS:
            value = row.get(header, "")
            if header in TEXT_HEADERS and value:
                values.append(as_sheet_text(value))
            else:
                values.append(value)
        matrix.append(values)
    return matrix


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMMON_HEADERS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def open_or_create_spreadsheet(client, title: str):
    try:
        return client.open(title)
    except SpreadsheetNotFound:
        return client.create(title)


def ensure_worksheet(spreadsheet, tab_name: str, col_count: int):
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


def write_rows_to_sheet(sheet_id: str, sheet_title: str, tab_name: str, rows: list[dict[str, str]]) -> tuple[str, str]:
    client = get_client("kohara")
    spreadsheet = client.open_by_key(sheet_id) if sheet_id else open_or_create_spreadsheet(client, sheet_title)
    worksheet = ensure_worksheet(spreadsheet, tab_name, len(COMMON_HEADERS))
    matrix = build_sheet_matrix(rows)
    target_rows = max(len(matrix), 1000)
    worksheet.resize(rows=target_rows, cols=len(COMMON_HEADERS))
    worksheet.clear()
    worksheet.update(range_name="A1", values=[COMMON_HEADERS], value_input_option="RAW")
    for start in range(1, len(matrix), WRITE_CHUNK_SIZE):
        chunk = matrix[start:start + WRITE_CHUNK_SIZE]
        worksheet.update(range_name=f"A{start + 1}", values=chunk, value_input_option="RAW")
    apply_formatting(spreadsheet, worksheet, COMMON_HEADERS, include_table_styles=False, include_protection=False)
    return spreadsheet.id, worksheet.title


def main() -> None:
    parser = argparse.ArgumentParser(description="広告データ（収集）を媒体横断で加工する")
    parser.add_argument("--output-prefix", default="ads_processed", help="出力ファイル名プレフィックス")
    parser.add_argument("--write-sheet", action="store_true", help="加工用スプレッドシートに書き出す")
    parser.add_argument("--sheet-id", default=PROCESSED_SHEET_ID, help="加工用スプレッドシートID")
    parser.add_argument("--sheet-title", default=PROCESSED_SHEET_TITLE, help="加工用スプレッドシート名")
    args = parser.parse_args()

    account_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_ACCOUNT_TAB)
    mapping_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_MAPPING_TAB)
    route_rows = load_sheet_values(MASTER_SHEET_ID, MASTER_ROUTE_TAB)

    account_master = build_account_master(account_rows)
    mapping_master = build_mapping_master(mapping_rows)
    route_map = build_route_map(route_rows)

    per_media_rows: dict[str, list[dict[str, str]]] = {}
    summary: dict[str, Any] = {"media": {}}
    all_rows: list[dict[str, str]] = []

    for media, raw_tab in RAW_TABS.items():
        raw_rows = load_sheet_values(RAW_SHEET_ID, raw_tab)
        processed_rows, unmatched, excluded = collect_processed_rows(
            media=media,
            raw_rows=raw_rows,
            account_master=account_master,
            mapping_master=mapping_master,
            route_map=route_map,
        )
        fill_delivery_span(processed_rows)
        per_media_rows[media] = processed_rows
        all_rows.extend(processed_rows)
        summary["media"][media] = {
            "raw_rows": max(len(raw_rows) - 1, 0),
            "processed_rows": len(processed_rows),
            "unmatched_accounts": unmatched,
            "unmatched_account_count": len(unmatched),
            "excluded_accounts": excluded,
            "excluded_account_count": len(excluded),
            "funnel_counts": dict(Counter(row["ファネル"] for row in processed_rows if row.get("ファネル"))),
        }

    fill_delivery_span(all_rows)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"{args.output_prefix}_{timestamp}.csv"
    summary_path = OUTPUT_DIR / f"{args.output_prefix}_{timestamp}_summary.json"
    write_csv(csv_path, all_rows)
    summary["saved_to"] = str(csv_path)
    summary["total_processed_rows"] = len(all_rows)
    summary["total_funnel_counts"] = dict(Counter(row["ファネル"] for row in all_rows if row.get("ファネル")))

    if args.write_sheet:
        written_tabs = {}
        for media, tab_name in PROCESSED_TABS.items():
            sheet_id, worksheet_title = write_rows_to_sheet(
                sheet_id=args.sheet_id,
                sheet_title=args.sheet_title,
                tab_name=tab_name,
                rows=per_media_rows[media],
            )
            written_tabs[media] = {"sheet_id": sheet_id, "tab_name": worksheet_title}
        sheet_id, worksheet_title = write_rows_to_sheet(
            sheet_id=args.sheet_id,
            sheet_title=args.sheet_title,
            tab_name=INTEGRATED_TAB_NAME,
            rows=all_rows,
        )
        summary["written_tabs"] = written_tabs
        summary["integrated_tab"] = {"sheet_id": sheet_id, "tab_name": worksheet_title}

    write_json(summary_path, summary)
    print(f"保存先: {csv_path}")
    print(f"サマリー: {summary_path}")
    for media, payload in summary["media"].items():
        print(
            f"{media}: 加工 {payload['processed_rows']} / 未照合 {payload['unmatched_account_count']} / "
            f"除外 {payload['excluded_account_count']}"
        )
    print(f"統合行数: {len(all_rows)}")


if __name__ == "__main__":
    main()
