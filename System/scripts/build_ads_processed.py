#!/usr/bin/env python3
"""広告データ（収集）から広告データ（加工）を生成する。"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System"))

from gspread.exceptions import APIError, SpreadsheetNotFound, WorksheetNotFound  # noqa: E402
from sheets_manager import get_client  # noqa: E402
from setup_ads_sheet import apply_formatting, apply_status_controls  # noqa: E402


RAW_SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
RAW_TABS = {
    "Meta": "Meta広告",
    "TikTok": "TikTok広告",
    "X": "X広告",
}
OFFLINE_RAW_TAB = "オフライン"

MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_ACCOUNT_TAB = "広告アカウント"
MASTER_MAPPING_TAB = "広告-ファネル-LINE対応表"
MASTER_ROUTE_TAB = "流入経路マスタ"
TARGET_BUSINESS_NAMES = {"スキルプラス"}
CURRENT_MASTER_START = date(2026, 3, 19)
HISTORICAL_BASE_END = date(2026, 3, 18)
TODAY = date.today()

HISTORICAL_COST_SHEET_ID = "11r9WuMO0TINrlS2R9bua_R0hyJzZf1a-5yzz3EdBZ_Y"
HISTORICAL_COST_TAB = "シート1"
EXCLUDED_COST_ROUTES = {
    "Meta広告_デザジュク",
    "リスティング広告_デザジュク",
    "TikTok広告_デザジュク",
    "Meta広告_VTD",
}

X_OUTSOURCE_SHEET_ID = "1PryZoy0-fr2uY8j27bL8GwsnLHIgN3rzSc1ILOk333M"
X_OUTSOURCE_MONTH_TABS = [
    "2月",
    "3月",
    "4月",
    "5月",
    "6月",
    "7月",
    "8月",
    "9月",
    "10月",
    "11月",
    "12月",
    "2026/1月",
    "2026/2月",
    "2026/3月",
]

YOUTUBE_OUTSOURCE_SHEET_ID = "1CzuXAQ6bgLEO-VzFGjVqVszCsdTpbbPB08t11SNsXWs"
YOUTUBE_OUTSOURCE_TABS = {
    "AIカレッジ_24年": ("YouTube広告_AI", "YouTube広告", "AI"),
    "AIカレッジ_25年": ("YouTube広告_AI", "YouTube広告", "AI"),
    "AIカレッジ_26年": ("YouTube広告_AI", "YouTube広告", "AI"),
    "スキルプラス_25年": ("YouTube広告_スキルプラス", "YouTube広告", "スキルプラス"),
    "スキルプラス_26年": ("YouTube広告_スキルプラス", "YouTube広告", "スキルプラス"),
    "センサーズ_24年": ("YouTube広告_センサーズ", "YouTube広告", "センサーズ"),
    "センサーズ_25年": ("YouTube広告_センサーズ", "YouTube広告", "センサーズ"),
}

AFFILIATE_SHEET_ID = "1CIt-o-fWKM8R0Fd3JkqQR3fZHLCGMxvNc47qAPpy9qk"
AFFILIATE_INFLUENCER_TAB = "インフルエンサー別数値"
AFFILIATE_SKILL_TAB = "スキルプラスセミナー導線"
AFFILIATE_ROUTE = "アフィリエイト広告_スキルプラス"
AFFILIATE_MEDIA = "アフィリエイト広告"
AFFILIATE_FUNNEL = "スキルプラス"

LISTING_HISTORY_SHEET_ID = "1aghGPciHHVSCLdcJGy7EDDA8M5oYdNV7vVKSrjdEPEk"
DISPLAY_HISTORY_SHEET_ID = "1WKfKitCDwuzIyyrXoy52Rz7ArsjIVSE2D9KAVqJMUIQ"
LINE_HISTORY_SHEET_ID = "1lePi10MXsks_A4X9Op3bXszvS41MyJ-4itSdUXURidY"
TIKTOK_HISTORY_SHEET_ID = "1MsJRbZGrLOkgd7lRApr1ciFQ1GOZaIjmrXQSIe3_nCA"
META_HISTORY_SHEET_ID = "1ZqvgJxnD3BqSeb2pyh_VeiCm4KtMENi1nLoFyvThy8U"
META_BRAND_HISTORY_SHEET_ID = "1HCrVQWStz-yJ6rzc7rpUJhIkyeJ25S2iAjL_A0NAqIM"
X_BRAND_HISTORY_SHEET_ID = "1JVRMk1JFTCQ-zChRCVjUTyGpNe9Y-ehyPi4yos_I7s8"
YAHOO_HISTORY_SHEET_ID = "15BsfZjvk2etfwNCEmRd5411hCD4P7R53PsDnRCU-vmk"

HISTORICAL_REFERENCE_SOURCES = [
    {
        "source": "参考:リスティング広告",
        "sheet_id": LISTING_HISTORY_SHEET_ID,
        "cost_headers": ["⑥コスト（税込）", "コスト（税込）", "コスト"],
        "tabs": {
            "SNS": ("リスティング広告", "センサーズ"),
            "AI": ("リスティング広告", "AI"),
            "スキルプラス": ("リスティング広告", "スキルプラス"),
        },
    },
    {
        "source": "参考:ディスプレイ広告",
        "sheet_id": DISPLAY_HISTORY_SHEET_ID,
        "cost_headers": ["⑥コスト（税込）", "コスト（税込）", "コスト"],
        "tabs": {
            "SNS": ("ディスプレイ広告", "センサーズ"),
            "AI": ("ディスプレイ広告", "AI"),
            "スキルプラス": ("ディスプレイ広告", "スキルプラス"),
        },
    },
    {
        "source": "参考:LINE広告",
        "sheet_id": LINE_HISTORY_SHEET_ID,
        "cost_headers": ["コスト（税込）", "⑥コスト（税込）", "コスト"],
        "tabs": {
            "SNS": ("LINE広告", "センサーズ"),
            "AI": ("LINE広告", "AI"),
            "スキルプラス": ("LINE広告", "スキルプラス"),
            "スキルプラス（友達追加型）": ("LINE広告", "スキルプラス"),
            "スキル習得セミナー": ("LINE広告", "スキルプラス"),
            "スキルプラス（オートウェビナー用）": ("LINE広告", "スキルプラス"),
        },
    },
    {
        "source": "参考:TikTok広告",
        "sheet_id": TIKTOK_HISTORY_SHEET_ID,
        "cost_headers": ["コスト（税込）", "⑥コスト（税込）", "コスト"],
        "tabs": {
            "SNS": ("TikTok広告", "センサーズ"),
            "AI": ("TikTok広告", "AI"),
            "スキルプラス（オートウェビナー用）": ("TikTok広告", "スキルプラス"),
        },
    },
    {
        "source": "参考:Meta広告",
        "sheet_id": META_HISTORY_SHEET_ID,
        "cost_headers": ["コスト(税別)", "コスト（税別）", "コスト", "媒体管理画面消化金額"],
        "tabs": {
            "SNS": ("Meta広告", "センサーズ"),
            "AI": ("Meta広告", "AI"),
            "スキルプラス": ("Meta広告", "スキルプラス"),
            "スキルプラス（セミナー）": ("Meta広告", "スキルプラス"),
            "直個別": ("Meta広告", "直個別"),
            "スキルプラス（無料体験会）": ("Meta広告", "スキルプラス"),
        },
    },
    {
        "source": "参考:Meta認知広告",
        "sheet_id": META_BRAND_HISTORY_SHEET_ID,
        "cost_headers": ["コスト(税別)", "コスト（税別）", "コスト"],
        "tabs": {
            "スキルプラス": ("Meta広告", "ブランド認知"),
        },
    },
    {
        "source": "参考:X認知広告",
        "sheet_id": X_BRAND_HISTORY_SHEET_ID,
        "cost_headers": ["コスト(税別)", "コスト（税別）", "コスト"],
        "tabs": {
            "2月": ("X広告", "ブランド認知"),
            "3月": ("X広告", "ブランド認知"),
            "4月": ("X広告", "ブランド認知"),
            "5月": ("X広告", "ブランド認知"),
            "6月": ("X広告", "ブランド認知"),
            "7月": ("X広告", "ブランド認知"),
            "8月": ("X広告", "ブランド認知"),
            "9月": ("X広告", "ブランド認知"),
            "10月": ("X広告", "ブランド認知"),
            "11月": ("X広告", "ブランド認知"),
            "12月": ("X広告", "ブランド認知"),
            "2026/1月": ("X広告", "ブランド認知"),
            "2026/2月": ("X広告", "ブランド認知"),
            "2026/3月": ("X広告", "ブランド認知"),
        },
    },
    {
        "source": "参考:Yahoo!広告",
        "sheet_id": YAHOO_HISTORY_SHEET_ID,
        "cost_headers": ["コスト（税込）", "⑥コスト（税込）", "コスト（税抜）", "コスト(税別)", "コスト"],
        "tabs": {
            "スキルプラス（検索）": ("リスティング広告", "スキルプラス"),
            "スキルプラス（ディスプレイ） ": ("ディスプレイ広告", "スキルプラス"),
            "スキルプラス（ディスプレイ セミナー） ": ("ディスプレイ広告", "スキルプラス"),
        },
    },
]

PROCESSED_SHEET_TITLE = "【アドネス株式会社】広告データ（加工）"
PROCESSED_SHEET_ID = "1QLtsOOQLzmeDewHIzEqtSY5Ibr5ryCRSydyRumgtdTM"
ONLINE_TAB_NAME = "オンライン"
OFFLINE_TAB_NAME = "オフライン"
COST_TAB_NAME = "広告費管理"
SOURCE_MANAGEMENT_TAB = "データソース管理"
RULES_TAB = "データ追加ルール"
MONITOR_TAB = "加工監視"
WRITE_CHUNK_SIZE = 6000

STATUS_OPTIONS = ["正常", "未同期", "停止"]

PROCESSED_CURRENCY_HEADERS = {
    ONLINE_TAB_NAME: {"媒体管理画面消化金額", "広告費", "CPC", "CPM"},
    OFFLINE_TAB_NAME: {"広告費"},
    COST_TAB_NAME: {"広告費"},
}

PROCESSED_NUMBER_HEADERS = {
    ONLINE_TAB_NAME: {
        "インプレッション",
        "リーチ",
        "フリークエンシー",
        "クリック数（媒体定義）",
        "遷移クリック数",
        "CTR",
        "管理画面CV数",
        "動画再生数",
        "動画2秒再生数",
        "動画6秒再生数",
        "動画完全再生数",
        "エンゲージメント数",
    },
}

OUTPUT_DIR = ROOT / "System" / "data" / "ads_processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ONLINE_HEADERS = [
    "日付",
    "集客媒体",
    "広告アカウントID",
    "広告アカウント名",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "クリエイティブ識別キー",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "LP識別キー",
    "現在配信ステータス",
    "広告作成日",
    "最終更新日",
    "配信開始日",
    "配信終了日",
    "媒体管理画面消化金額",
    "広告費",
    "広告費算定区分",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "クリック数（媒体定義）",
    "遷移クリック数",
    "CPC",
    "CPM",
    "CTR",
    "管理画面CV数",
    "動画再生数",
    "動画2秒再生数",
    "動画6秒再生数",
    "動画完全再生数",
    "エンゲージメント数",
    "管理画面CV詳細",
    "備考",
]

OFFLINE_HEADERS = [
    "日付",
    "集客媒体",
    "事業名",
    "ファネル",
    "企画名",
    "出稿場所",
    "掲載期間",
    "広告費",
    "広告費算定区分",
    "取込日時",
    "備考",
]

COST_HEADERS = [
    "日付",
    "事業名",
    "流入経路",
    "集客媒体",
    "ファネル",
    "費用区分",
    "広告費",
    "ソース",
]

SOURCE_MANAGEMENT_HEADERS = [
    "ソースID",
    "データレーン",
    "集客媒体",
    "入力元",
    "出力先",
    "粒度",
    "主キー",
    "ステータス",
    "最終更新日",
    "更新行数",
    "備考",
]

RULE_HEADERS = [
    "ルールID",
    "対象タブ",
    "カテゴリ",
    "ルール名",
    "内容",
    "防止の仕組み",
    "検知の仕組み",
    "ステータス",
    "備考",
]

MONITOR_HEADERS = [
    "対象タブ",
    "対象レーン",
    "ステータス",
    "最終更新日",
    "最古日付",
    "最新日付",
    "行数",
    "未照合件数",
    "除外件数",
    "判定理由",
]

ONLINE_TEXT_HEADERS = {
    "ビジネスマネージャID",
    "広告アカウントID",
    "キャンペーンID",
    "広告グループID",
    "広告ID",
    "クリエイティブ識別キー",
    "メディアID",
}

@lru_cache(maxsize=1)
def get_kohara_client():
    return get_client("kohara")


@lru_cache(maxsize=None)
def get_cached_spreadsheet(sheet_id: str):
    return call_with_retry(lambda: get_kohara_client().open_by_key(sheet_id))


@lru_cache(maxsize=None)
def get_cached_worksheet(sheet_id: str, tab_name: str):
    return get_cached_spreadsheet(sheet_id).worksheet(tab_name)


def load_sheet_values(sheet_id: str, tab_name: str) -> list[list[str]]:
    worksheet = get_cached_worksheet(sheet_id, tab_name)
    return call_with_retry(lambda: worksheet.get_all_values())


@lru_cache(maxsize=None)
def load_sheet_values_batch(sheet_id: str, tab_names: tuple[str, ...]) -> dict[str, list[list[str]]]:
    spreadsheet = get_cached_spreadsheet(sheet_id)
    ranges = [f"'{tab_name}'" for tab_name in tab_names]
    if not ranges:
        return {}
    try:
        response = call_with_retry(lambda: spreadsheet.values_batch_get(ranges))
        value_ranges = response.get("valueRanges", [])
        result: dict[str, list[list[str]]] = {}
        for tab_name, value_range in zip(tab_names, value_ranges):
            result[tab_name] = value_range.get("values", [])
        return result
    except APIError as exc:
        if is_retryable_sheet_error(exc):
            raise
        result: dict[str, list[list[str]]] = {}
        for tab_name in tab_names:
            try:
                worksheet = get_cached_worksheet(sheet_id, tab_name)
                result[tab_name] = call_with_retry(lambda worksheet=worksheet: worksheet.get_all_values())
            except WorksheetNotFound:
                continue
        return result


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


def parse_number(value: str | float | int) -> float:
    text = str(value or "").replace(",", "").replace("¥", "").replace("%", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def format_number(value: float) -> str:
    if abs(value) < 1e-12:
        return "0"
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.4f}".rstrip("0").rstrip(".")


def parse_date_value(value: str, fallback_year: int | None = None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    normalized = text.replace(".", "/").replace("-", "/")
    parts = [part for part in normalized.split("/") if part]
    try:
        if len(parts) == 3:
            year, month, day = [int(part) for part in parts]
            return date(year, month, day)
        if len(parts) == 2 and fallback_year:
            month, day = [int(part) for part in parts]
            return date(fallback_year, month, day)
    except ValueError:
        return None
    return None


def format_date_value(value: date | None) -> str:
    return value.isoformat() if value else ""


def normalize_header_text(value: str) -> str:
    return str(value or "").replace("\n", "").replace(" ", "").replace("　", "").strip()


def find_header_index_by_candidates(header: list[str], candidates: list[str]) -> int | None:
    normalized_header = [normalize_header_text(value) for value in header]
    normalized_candidates = [normalize_header_text(candidate) for candidate in candidates]
    for candidate in normalized_candidates:
        for idx, value in enumerate(normalized_header):
            if value == candidate:
                return idx
    for candidate in normalized_candidates:
        for idx, value in enumerate(normalized_header):
            if candidate and candidate in value:
                return idx
    return None


def infer_funnel_from_route(route: str) -> str:
    text = str(route or "").strip()
    if not text:
        return ""
    suffix = text.split("_", 1)[-1]
    table = {
        "AI": "AI",
        "センサーズ": "センサーズ",
        "スキルプラス": "スキルプラス",
        "秘密の部屋": "ライトプラン",
        "ライトプラン": "ライトプラン",
        "ブランド認知": "ブランド認知",
    }
    return table.get(suffix, suffix)


def resolve_route(media: str, funnel: str, route_map: dict[tuple[str, str], str]) -> str:
    if not media or not funnel:
        return ""
    route = route_map.get((media, funnel))
    if route:
        return route
    return f"{media}_{funnel}"


def build_cost_row(
    date_text: str,
    route: str,
    media: str,
    funnel: str,
    cost: float | str,
    fee_type: str,
    source: str,
) -> dict[str, str]:
    return {
        "日付": date_text,
        "事業名": "スキルプラス",
        "流入経路": route,
        "集客媒体": media,
        "ファネル": funnel,
        "費用区分": fee_type,
        "広告費": format_number(parse_number(cost)),
        "ソース": source,
    }


def aggregate_cost_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    aggregated: dict[tuple[str, str, str, str, str, str, str], dict[str, str]] = {}
    order: list[tuple[str, str, str, str, str, str, str]] = []
    for row in rows:
        key = (
            row.get("日付", ""),
            row.get("事業名", ""),
            row.get("流入経路", ""),
            row.get("集客媒体", ""),
            row.get("ファネル", ""),
            row.get("費用区分", ""),
            row.get("ソース", ""),
        )
        if key not in aggregated:
            aggregated[key] = dict(row)
            order.append(key)
            continue
        existing_cost = parse_number(aggregated[key].get("広告費", ""))
        aggregated[key]["広告費"] = format_number(existing_cost + parse_number(row.get("広告費", "")))
    return [aggregated[key] for key in order]


def has_activity(record: dict[str, str]) -> bool:
    activity_headers = [
        "インプレッション",
        "クリック数（媒体定義）",
        "遷移クリック数",
        "媒体管理画面消化金額",
        "管理画面CV数",
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


def resolve_special_mapping(media: str, account_info: dict[str, str], record: dict[str, str]) -> dict[str, str] | None:
    account_name = account_info.get("広告アカウント名", "")
    campaign_name = record.get("キャンペーン名", "")
    if media == "X広告" and account_name == "みかみ｜アドネス株式会社｜スキルプラス運営":
        if "Quick promote" in campaign_name:
            return {"ファネル": "みかみメイン"}
    return None


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
        "クリエイティブ識別キー": cr_key,
        "メディアタイプ": media_type,
        "メディアID": media_id,
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": "",
        "出稿形式レーン": "",
        "媒体管理画面消化金額": cell(row, idx, "消化金額"),
        "インプレッション": cell(row, idx, "インプレッション数"),
        "リーチ": cell(row, idx, "リーチ"),
        "フリークエンシー": cell(row, idx, "フリークエンシー"),
        "クリック数（媒体定義）": cell(row, idx, "総クリック数"),
        "遷移クリック数": cell(row, idx, "外部クリック数") or cell(row, idx, "リンククリック数"),
        "遷移クリック数（ユニーク）": cell(row, idx, "外部クリック数（ユニーク）") or cell(row, idx, "リンククリック数（ユニーク）"),
        "管理画面CV数": "",
        "動画再生数": "",
        "動画2秒再生数": "",
        "動画6秒再生数": "",
        "動画完全再生数": "",
        "エンゲージメント数": "",
        "エンゲージメント率": "",
        "管理画面CV詳細": cell(row, idx, "コンバージョン（JSON）"),
        "備考": "",
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
        "クリエイティブ識別キー": normalize_lookup_id(cell(row, idx, "CR識別キー")),
        "メディアタイプ": cell(row, idx, "メディアタイプ"),
        "メディアID": normalize_lookup_id(cell(row, idx, "メディアID")),
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": cell(row, idx, "プロモーション種別"),
        "出稿形式レーン": cell(row, idx, "出稿形式レーン"),
        "媒体管理画面消化金額": cell(row, idx, "消化金額"),
        "インプレッション": cell(row, idx, "インプレッション"),
        "リーチ": cell(row, idx, "リーチ"),
        "フリークエンシー": cell(row, idx, "フリークエンシー"),
        "クリック数（媒体定義）": cell(row, idx, "クリック数（all）"),
        "遷移クリック数": "",
        "遷移クリック数（ユニーク）": "",
        "管理画面CV数": cell(row, idx, "コンバージョン数（optimization event）"),
        "動画再生数": cell(row, idx, "動画再生数"),
        "動画2秒再生数": cell(row, idx, "動画2秒再生数"),
        "動画6秒再生数": cell(row, idx, "動画6秒再生数"),
        "動画完全再生数": cell(row, idx, "動画完全再生数"),
        "エンゲージメント数": "",
        "エンゲージメント率": "",
        "管理画面CV詳細": "",
        "備考": "",
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
        "クリエイティブ識別キー": normalize_lookup_id(cell(row, idx, "クリエイティブID")),
        "メディアタイプ": cell(row, idx, "メディアタイプ"),
        "メディアID": normalize_lookup_id(cell(row, idx, "メディアID")),
        "遷移先URL": url,
        "LP識別キー": normalize_lp_key(url),
        "プロモーション種別": "",
        "出稿形式レーン": "",
        "媒体管理画面消化金額": cell(row, idx, "消化金額"),
        "インプレッション": cell(row, idx, "インプレッション"),
        "リーチ": "",
        "フリークエンシー": "",
        "クリック数（媒体定義）": link_clicks,
        "遷移クリック数": link_clicks,
        "遷移クリック数（ユニーク）": "",
        "管理画面CV数": "",
        "動画再生数": "",
        "動画2秒再生数": "",
        "動画6秒再生数": "",
        "動画完全再生数": "",
        "エンゲージメント数": cell(row, idx, "エンゲージメント数"),
        "エンゲージメント率": cell(row, idx, "エンゲージメント率"),
        "管理画面CV詳細": "",
        "備考": "",
    }


def build_media_record(media: str, row: list[str], idx: dict[str, int]) -> dict[str, str]:
    if media == "Meta広告":
        return build_meta_record(row, idx)
    if media == "TikTok広告":
        return build_tiktok_record(row, idx)
    if media == "X広告":
        return build_x_record(row, idx)
    raise ValueError(f"unsupported media: {media}")


def derive_ad_cost(media: str, spend_text: str) -> tuple[str, str]:
    spend = parse_number(spend_text)
    if media == "TikTok広告":
        return format_number(spend * 1.1), "媒体管理画面消化金額×1.1"
    return format_number(spend), "媒体管理画面消化金額"


def compute_rate_metrics(record: dict[str, str]) -> None:
    ad_cost = parse_number(record.get("広告費", ""))
    impressions = parse_number(record.get("インプレッション", ""))
    destination_clicks = parse_number(record.get("遷移クリック数", ""))
    all_clicks = parse_number(record.get("クリック数（媒体定義）", ""))
    clicks_base = destination_clicks if destination_clicks > 0 else all_clicks
    if clicks_base > 0:
        record["CPC"] = format_number(ad_cost / clicks_base)
    else:
        record["CPC"] = ""
    if impressions > 0:
        record["CPM"] = format_number(ad_cost / impressions * 1000)
        record["CTR"] = format_number(clicks_base / impressions * 100)
    else:
        record["CPM"] = ""
        record["CTR"] = ""


def collect_online_rows(
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
                unmatched.append(
                    {
                        "集客媒体": media,
                        "広告アカウントID": account_id,
                        "広告アカウント名": record["広告アカウント名"],
                        "理由": "広告アカウントマスタ未登録",
                    }
                )
                seen_unmatched.add(key)
            continue
        if account_info.get("事業名") not in TARGET_BUSINESS_NAMES:
            key = (media, account_id)
            if key not in seen_excluded:
                excluded.append(
                    {
                        "集客媒体": media,
                        "広告アカウントID": account_id,
                        "広告アカウント名": record["広告アカウント名"],
                        "事業名": account_info.get("事業名", ""),
                    }
                )
                seen_excluded.add(key)
            continue

        mapping, reason = resolve_mapping(media, record, mapping_master)
        if not mapping:
            special_mapping = resolve_special_mapping(media, account_info, record)
            if special_mapping:
                mapping = special_mapping
            elif media == "TikTok広告" and "停止中" in account_info.get("備考", ""):
                key = (media, account_id)
                if key not in seen_excluded:
                    excluded.append(
                        {
                            "集客媒体": media,
                            "広告アカウントID": account_id,
                            "広告アカウント名": record["広告アカウント名"],
                            "事業名": account_info.get("事業名", ""),
                        }
                    )
                    seen_excluded.add(key)
                continue
        if not mapping:
            key = (media, account_id, record["広告アカウント名"], reason)
            if key not in seen_unmatched:
                unmatched.append(
                    {
                        "集客媒体": media,
                        "広告アカウントID": account_id,
                        "広告アカウント名": record["広告アカウント名"],
                        "理由": reason or "広告-ファネル-LINE対応表未登録",
                    }
                )
                seen_unmatched.add(key)
            continue

        ad_cost, cost_rule = derive_ad_cost(media, record.get("媒体管理画面消化金額", ""))
        item = {
            "日付": record.get("日付", ""),
            "集客媒体": media,
            "事業名": account_info.get("事業名", ""),
            "ファネル": mapping.get("ファネル", ""),
            "流入経路": resolve_route(media, mapping.get("ファネル", ""), route_map),
            "ビジネスマネージャID": account_info.get("ビジネスマネージャID", ""),
            "ビジネスマネージャ名": account_info.get("ビジネスマネージャ名", ""),
            "広告アカウントID": record.get("広告アカウントID", ""),
            "広告アカウント名": record.get("広告アカウント名", ""),
            "キャンペーンID": record.get("キャンペーンID", ""),
            "キャンペーン名": record.get("キャンペーン名", ""),
            "広告グループID": record.get("広告グループID", ""),
            "広告グループ名": record.get("広告グループ名", ""),
            "広告ID": record.get("広告ID", ""),
            "広告名": record.get("広告名", ""),
            "クリエイティブ識別キー": record.get("クリエイティブ識別キー", ""),
            "メディアタイプ": record.get("メディアタイプ", ""),
            "メディアID": record.get("メディアID", ""),
            "遷移先URL": record.get("遷移先URL", ""),
            "LP識別キー": record.get("LP識別キー", ""),
            "現在配信ステータス": record.get("現在配信ステータス", ""),
            "プロモーション種別": record.get("プロモーション種別", ""),
            "出稿形式レーン": record.get("出稿形式レーン", ""),
            "広告作成日": record.get("広告作成日", ""),
            "最終更新日": record.get("最終更新日", ""),
            "配信開始日": "",
            "配信終了日": "",
            "媒体管理画面消化金額": record.get("媒体管理画面消化金額", ""),
            "広告費": ad_cost,
            "広告費算定区分": cost_rule,
            "インプレッション": record.get("インプレッション", ""),
            "リーチ": record.get("リーチ", ""),
            "フリークエンシー": record.get("フリークエンシー", ""),
            "クリック数（媒体定義）": record.get("クリック数（媒体定義）", ""),
            "遷移クリック数": record.get("遷移クリック数", ""),
            "遷移クリック数（ユニーク）": record.get("遷移クリック数（ユニーク）", ""),
            "CPC": "",
            "CPM": "",
            "CTR": "",
            "管理画面CV数": record.get("管理画面CV数", ""),
            "動画再生数": record.get("動画再生数", ""),
            "動画2秒再生数": record.get("動画2秒再生数", ""),
            "動画6秒再生数": record.get("動画6秒再生数", ""),
            "動画完全再生数": record.get("動画完全再生数", ""),
            "エンゲージメント数": record.get("エンゲージメント数", ""),
            "エンゲージメント率": record.get("エンゲージメント率", ""),
            "管理画面CV詳細": record.get("管理画面CV詳細", ""),
            "備考": record.get("備考", ""),
        }
        compute_rate_metrics(item)
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


def collect_offline_rows(raw_rows: list[list[str]]) -> list[dict[str, str]]:
    header = raw_rows[0]
    idx = build_index(header)
    processed: list[dict[str, str]] = []
    for row in raw_rows[1:]:
        if not any(str(value).strip() for value in row):
            continue
        processed.append(
            {
                "日付": cell(row, idx, "発生日"),
                "集客媒体": cell(row, idx, "集客媒体") or "オフライン広告",
                "事業名": "スキルプラス",
                "ファネル": "ブランド認知",
                "企画名": cell(row, idx, "企画名"),
                "出稿場所": cell(row, idx, "出稿場所"),
                "掲載期間": cell(row, idx, "掲載期間"),
                "広告費": cell(row, idx, "広告費"),
                "広告費算定区分": "請求書・共有資料ベース",
                "取込日時": cell(row, idx, "取込日時"),
                "備考": cell(row, idx, "備考"),
            }
        )
    return processed


def load_historical_cost_rows() -> list[dict[str, str]]:
    rows = load_sheet_values_batch(HISTORICAL_COST_SHEET_ID, (HISTORICAL_COST_TAB,)).get(HISTORICAL_COST_TAB, [])
    if not rows:
        return []
    header = rows[0]
    idx = build_index(header)
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        route = cell(row, idx, "流入経路")
        if not route or route in EXCLUDED_COST_ROUTES:
            continue
        date_obj = parse_date_value(cell(row, idx, "日付"))
        if not date_obj or date_obj > HISTORICAL_BASE_END:
            continue
        result.append(
            build_cost_row(
                date_text=format_date_value(date_obj),
                route=route,
                media=cell(row, idx, "媒体名"),
                funnel=infer_funnel_from_route(route),
                cost=cell(row, idx, "広告費"),
                fee_type="合算",
                source="11r9 シート1",
            )
        )
    return result


def load_historical_reference_cost_rows(route_map: dict[tuple[str, str], str]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for source_def in HISTORICAL_REFERENCE_SOURCES:
        sheet_id = source_def["sheet_id"]
        source_label = source_def["source"]
        cost_headers = source_def["cost_headers"]
        tab_names = tuple(source_def["tabs"].keys())
        try:
            grouped_rows = load_sheet_values_batch(sheet_id, tab_names)
        except WorksheetNotFound:
            grouped_rows = {}
        for tab_name, (media, funnel) in source_def["tabs"].items():
            rows = grouped_rows.get(tab_name, [])
            if len(rows) < 2:
                continue
            header = rows[1]
            cost_idx = find_header_index_by_candidates(header, cost_headers)
            if cost_idx is None:
                continue
            route = resolve_route(media, funnel, route_map)
            if route in EXCLUDED_COST_ROUTES:
                continue
            for row in rows[2:]:
                if not any(str(value).strip() for value in row):
                    continue
                date_obj = parse_date_value(row[0] if row else "")
                if not date_obj or date_obj > HISTORICAL_BASE_END:
                    continue
                cost = row[cost_idx].strip() if cost_idx < len(row) else ""
                if parse_number(cost) <= 0:
                    continue
                result.append(
                    build_cost_row(
                        date_text=format_date_value(date_obj),
                        route=route,
                        media=media,
                        funnel=funnel,
                        cost=cost,
                        fee_type="合算",
                        source=f"{source_label}:{tab_name}",
                    )
                )
    return result


def load_x_outsource_cost_rows() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    rows_map = load_sheet_values_batch(X_OUTSOURCE_SHEET_ID, tuple(X_OUTSOURCE_MONTH_TABS))
    for tab_name in X_OUTSOURCE_MONTH_TABS:
        rows = rows_map.get(tab_name, [])
        for row in rows[3:]:
            if len(row) < 14:
                continue
            date_obj = parse_date_value(row[0])
            cost = row[13].strip() if len(row) > 13 else ""
            if not date_obj or not cost:
                continue
            if "X広告_AI" in EXCLUDED_COST_ROUTES:
                continue
            result.append(
                build_cost_row(
                    date_text=format_date_value(date_obj),
                    route="X広告_AI",
                    media="X広告",
                    funnel="AI",
                    cost=cost,
                    fee_type="委託",
                    source=f"X委託:{tab_name}",
                )
            )
    return result


def load_youtube_outsource_cost_rows() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    rows_map = load_sheet_values_batch(YOUTUBE_OUTSOURCE_SHEET_ID, tuple(YOUTUBE_OUTSOURCE_TABS.keys()))
    for tab_name, (route, media, funnel) in YOUTUBE_OUTSOURCE_TABS.items():
        rows = rows_map.get(tab_name, [])
        for row in rows[16:]:
            if len(row) < 4:
                continue
            date_obj = parse_date_value(row[0])
            cost = row[3].strip() if len(row) > 3 else ""
            if not date_obj or not cost:
                continue
            if route in EXCLUDED_COST_ROUTES:
                continue
            result.append(
                build_cost_row(
                    date_text=format_date_value(date_obj),
                    route=route,
                    media=media,
                    funnel=funnel,
                    cost=cost,
                    fee_type="委託",
                    source=f"YouTube委託:{tab_name}",
                )
            )
    return result


def load_affiliate_cost_rows() -> list[dict[str, str]]:
    result: list[dict[str, str]] = []

    rows_map = load_sheet_values_batch(AFFILIATE_SHEET_ID, (AFFILIATE_INFLUENCER_TAB, AFFILIATE_SKILL_TAB))

    influencer_rows = rows_map.get(AFFILIATE_INFLUENCER_TAB, [])
    inferred_year = 2025
    previous_month = 0
    for row in influencer_rows[1:]:
        if len(row) < 24:
            continue
        date_text = row[1].strip()
        cost = row[23].strip()
        if not date_text or not cost:
            continue
        parts = date_text.split("/")
        if len(parts) != 2:
            continue
        month = int(parts[0])
        if previous_month and month < previous_month:
            inferred_year += 1
        previous_month = month
        date_obj = parse_date_value(date_text, fallback_year=inferred_year)
        if not date_obj:
            continue
        if AFFILIATE_ROUTE in EXCLUDED_COST_ROUTES:
            continue
        result.append(
            build_cost_row(
                date_text=format_date_value(date_obj),
                route=AFFILIATE_ROUTE,
                media=AFFILIATE_MEDIA,
                funnel=AFFILIATE_FUNNEL,
                cost=cost,
                fee_type="委託",
                source=f"アフィリエイト:{AFFILIATE_INFLUENCER_TAB}",
            )
        )

    seminar_rows = rows_map.get(AFFILIATE_SKILL_TAB, [])
    for row in seminar_rows[3:]:
        if len(row) < 20:
            continue
        date_obj = parse_date_value(row[0])
        cost = row[19].strip()
        if not date_obj or not cost:
            continue
        if AFFILIATE_ROUTE in EXCLUDED_COST_ROUTES:
            continue
        result.append(
            build_cost_row(
                date_text=format_date_value(date_obj),
                route=AFFILIATE_ROUTE,
                media=AFFILIATE_MEDIA,
                funnel=AFFILIATE_FUNNEL,
                cost=cost,
                fee_type="委託",
                source=f"アフィリエイト:{AFFILIATE_SKILL_TAB}",
            )
        )
    return result


def build_sheet_matrix(headers: list[str], rows: list[dict[str, str]], text_headers: set[str] | None = None) -> list[list[str]]:
    text_headers = text_headers or set()
    matrix = [headers]
    for row in rows:
        values = []
        for header in headers:
            value = row.get(header, "")
            if header in text_headers and value:
                values.append(as_sheet_text(value))
            else:
                values.append(value)
        matrix.append(values)
    return matrix


def write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_retryable_sheet_error(exc: Exception) -> bool:
    text = str(exc)
    return (
        "[429]" in text
        or "[502]" in text
        or "Quota exceeded" in text
        or "Server Error" in text
    )


def call_with_retry(func, *, attempts: int = 8, delay_seconds: int = 20):
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except APIError as exc:
            if not is_retryable_sheet_error(exc) or attempt == attempts:
                raise
            time.sleep(delay_seconds * attempt)


def open_or_create_spreadsheet(client, title: str):
    try:
        return client.open(title)
    except SpreadsheetNotFound:
        return client.create(title)


def ensure_worksheet(spreadsheet, tab_name: str, col_count: int):
    try:
        worksheet = call_with_retry(lambda: spreadsheet.worksheet(tab_name))
    except WorksheetNotFound:
        worksheets = call_with_retry(lambda: spreadsheet.worksheets())
        if len(worksheets) == 1 and worksheets[0].title in {"シート1", "Sheet1"}:
            worksheet = worksheets[0]
            call_with_retry(lambda: worksheet.update_title(tab_name))
        else:
            worksheet = call_with_retry(lambda: spreadsheet.add_worksheet(title=tab_name, rows=1000, cols=col_count))
    return worksheet


def apply_processed_number_formats(spreadsheet, worksheet, tab_name: str, headers: list[str]) -> None:
    currency_headers = PROCESSED_CURRENCY_HEADERS.get(tab_name, set())
    number_headers = PROCESSED_NUMBER_HEADERS.get(tab_name, set())
    requests = []

    for idx, header in enumerate(headers):
        pattern = None
        if header in currency_headers:
            pattern = "¥#,##0.0"
        elif header in number_headers:
            pattern = "#,##0.0"
        if not pattern:
            continue
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "endRowIndex": worksheet.row_count,
                    "startColumnIndex": idx,
                    "endColumnIndex": idx + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": pattern,
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        })

    if requests:
        call_with_retry(lambda: spreadsheet.batch_update({"requests": requests}))


def write_matrix_to_sheet(
    spreadsheet,
    tab_name: str,
    headers: list[str],
    matrix: list[list[str]],
    text_headers: set[str] | None = None,
    status_options: list[str] | None = None,
) -> None:
    worksheet = ensure_worksheet(spreadsheet, tab_name, len(headers))
    target_rows = max(len(matrix), 1000)
    call_with_retry(lambda: worksheet.resize(rows=target_rows, cols=len(headers)))
    call_with_retry(lambda: worksheet.clear())
    call_with_retry(lambda: worksheet.update(range_name="A1", values=[headers], value_input_option="RAW"))
    for start in range(1, len(matrix), WRITE_CHUNK_SIZE):
        chunk = matrix[start:start + WRITE_CHUNK_SIZE]
        call_with_retry(
            lambda start=start, chunk=chunk: worksheet.update(
                range_name=f"A{start + 1}",
                values=chunk,
                value_input_option="RAW",
            )
        )
    call_with_retry(
        lambda: apply_formatting(
            spreadsheet,
            worksheet,
            headers,
            include_table_styles=False,
            include_protection=False,
        )
    )
    apply_processed_number_formats(spreadsheet, worksheet, tab_name, headers)
    if status_options and "ステータス" in headers:
        call_with_retry(lambda: apply_status_controls(spreadsheet, worksheet, headers, status_options))


def build_source_management_rows(
    summary_media: dict[str, Any],
    offline_rows: list[dict[str, str]],
    cost_rows: list[dict[str, str]],
    generated_at: str,
) -> list[dict[str, str]]:
    rows = []
    source_defs = [
        ("online_meta", "オンライン", "Meta広告", "収集:Meta", f"{ONLINE_TAB_NAME} / {COST_TAB_NAME}", "1日×1広告ID", "日付+広告ID"),
        ("online_tiktok", "オンライン", "TikTok広告", "収集:TikTok", f"{ONLINE_TAB_NAME} / {COST_TAB_NAME}", "1日×1広告ID", "日付+広告ID"),
        ("online_x", "オンライン", "X広告", "収集:X", f"{ONLINE_TAB_NAME} / {COST_TAB_NAME}", "1日×1広告ID", "日付+広告ID"),
        ("offline_pdf", "オフライン", "オフライン広告", "収集:オフライン", f"{OFFLINE_TAB_NAME} / {COST_TAB_NAME}", "1行=1案件", "発生日+企画名+出稿場所+広告費"),
        ("cost_outsource_x", "広告費管理", "X広告", "X委託シート", COST_TAB_NAME, "1日×1流入経路", "日付+流入経路+費用区分"),
        ("cost_outsource_youtube", "広告費管理", "YouTube広告", "YouTube委託シート", COST_TAB_NAME, "1日×1流入経路", "日付+流入経路+費用区分"),
        ("cost_affiliate", "広告費管理", "アフィリエイト広告", "アフィリエイトシート", COST_TAB_NAME, "1日×1流入経路", "日付+流入経路+費用区分"),
    ]
    for source_id, lane, media, src, dest, grain, pk in source_defs:
        if media == "オフライン広告":
            row_count = len(offline_rows)
            latest = max((row.get("取込日時", "") for row in offline_rows if row.get("取込日時")), default=generated_at)
        elif lane == "広告費管理":
            row_count = sum(1 for row in cost_rows if row.get("ソース", "").startswith(src.replace("シート", "").replace(" ", "")))
            if src == "11r9 シート1":
                row_count = sum(1 for row in cost_rows if row.get("ソース") == "11r9 シート1")
            elif src == "過去参考シート補完":
                row_count = sum(1 for row in cost_rows if row.get("ソース", "").startswith("参考:"))
            elif src == "X委託シート":
                row_count = sum(1 for row in cost_rows if row.get("ソース", "").startswith("X委託:"))
            elif src == "YouTube委託シート":
                row_count = sum(1 for row in cost_rows if row.get("ソース", "").startswith("YouTube委託:"))
            elif src == "アフィリエイトシート":
                row_count = sum(1 for row in cost_rows if row.get("ソース", "").startswith("アフィリエイト:"))
            latest = generated_at
        else:
            payload = summary_media.get(media, {})
            row_count = payload.get("processed_rows", 0)
            latest = generated_at
        status = "正常" if row_count > 0 else "未同期"
        rows.append(
            {
                "ソースID": source_id,
                "データレーン": lane,
                "集客媒体": media,
                "入力元": src,
                "出力先": dest,
                "粒度": grain,
                "主キー": pk,
                "ステータス": status,
                "最終更新日": latest,
                "更新行数": str(row_count),
                "備考": "",
            }
        )
    return rows


def build_rule_rows() -> list[dict[str, str]]:
    return [
        {
            "ルールID": "online_001",
            "対象タブ": ONLINE_TAB_NAME,
            "カテゴリ": "主キー",
            "ルール名": "オンライン主キー",
            "内容": "日付+広告IDを基本の行識別に使う",
            "防止の仕組み": "日付+広告IDで正規化し、同一行は上書きではなく再集約する",
            "検知の仕組み": "加工監視で媒体別行数を監視し、主キー衝突は再生成時に監査する",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "online_002",
            "対象タブ": ONLINE_TAB_NAME,
            "カテゴリ": "広告費",
            "ルール名": "Meta/X広告費",
            "内容": "広告費 = 媒体管理画面消化金額",
            "防止の仕組み": "Meta広告/X広告は媒体別に固定式で広告費を計算する",
            "検知の仕組み": "媒体管理画面消化金額が空の行は広告費も空になり監査で止める",
            "ステータス": "正常",
            "備考": "Meta広告 / X広告",
        },
        {
            "ルールID": "online_003",
            "対象タブ": ONLINE_TAB_NAME,
            "カテゴリ": "広告費",
            "ルール名": "TikTok広告費",
            "内容": "広告費 = 媒体管理画面消化金額 × 1.1",
            "防止の仕組み": "TikTok広告だけ倍率1.1を固定適用する",
            "検知の仕組み": "TikTok広告で広告費と媒体管理画面消化金額が同額なら再監査対象にする",
            "ステータス": "正常",
            "備考": "TikTok広告のみ",
        },
        {
            "ルールID": "online_003b",
            "対象タブ": COST_TAB_NAME,
            "カテゴリ": "広告費",
            "ルール名": "広告費の正本",
            "内容": "広告費の最終値は広告費管理タブを正本として扱う",
            "防止の仕組み": "オンラインの広告費と意思決定用の広告費を分けて持つ",
            "検知の仕組み": "ダッシュボード参照元は広告費管理に固定し、別タブ参照を監査する",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "cost_001",
            "対象タブ": COST_TAB_NAME,
            "カテゴリ": "粒度",
            "ルール名": "広告費管理の粒度",
            "内容": "広告費管理は日付×流入経路を基本にしつつ、費用区分とソースで内訳を保持する",
            "防止の仕組み": "日付×流入経路×費用区分×ソースで先に集約してから書き出す",
            "検知の仕組み": "同一キーの重複件数を監査し、重複が残れば書き戻しを止める",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "cost_002",
            "対象タブ": COST_TAB_NAME,
            "カテゴリ": "期間",
            "ルール名": "2026-03-19以降の正本",
            "内容": "2026-03-19以降は収集シート・委託シート・アフィリエイトシート・オフラインを正本として使う",
            "防止の仕組み": "期間境界で11r9を切り、current正本だけを採用する",
            "検知の仕組み": "2026-03-19以降に費用区分=合算が残ったら監査で止める",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "cost_003",
            "対象タブ": COST_TAB_NAME,
            "カテゴリ": "期間",
            "ルール名": "2026-03-18以前の過去分",
            "内容": "2026-03-18以前は11r9 シート1を第1候補として使い、費用区分は合算で保持する",
            "防止の仕組み": "過去分は11r9をベースにし、自社/委託へ無理に分解しない",
            "検知の仕組み": "2026-03-18以前に自社/委託が混ざったら監査で止める",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "cost_004",
            "対象タブ": COST_TAB_NAME,
            "カテゴリ": "期間",
            "ルール名": "過去参考シート補完",
            "内容": "2026-03-18以前で11r9に無い日付×流入経路は、各媒体の参考シートから合算で補完する",
            "防止の仕組み": "11r9に同一日付×流入経路がある場合は参考シートを足さない",
            "検知の仕組み": "補完行はソースを参考シート名で保持し、過剰補完を後追い確認できる",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "online_004",
            "対象タブ": ONLINE_TAB_NAME,
            "カテゴリ": "計算列",
            "ルール名": "CPC/CPM/CTR計算",
            "内容": "CPC/CPM/CTRは加工で再計算し、rawの値は使わない",
            "防止の仕組み": "raw列をそのまま持ち込まず、分子分母から毎回再計算する",
            "検知の仕組み": "分母ゼロ時は空欄にし、異常な無限値は出さない",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "online_005",
            "対象タブ": ONLINE_TAB_NAME,
            "カテゴリ": "配信期間",
            "ルール名": "配信開始日/終了日",
            "内容": "実績が発生した最初日と最後日で配信期間を決める",
            "防止の仕組み": "広告作成日/最終更新日ではなく実績日付から期間を算出する",
            "検知の仕組み": "開始日より終了日が前になる行は監査で止める",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "offline_001",
            "対象タブ": OFFLINE_TAB_NAME,
            "カテゴリ": "粒度",
            "ルール名": "オフライン粒度",
            "内容": "1行=1案件で保持する",
            "防止の仕組み": "発生日+企画名+出稿場所+広告費で重複追加を防ぐ",
            "検知の仕組み": "同一案件の重複件数を取込時に監査する",
            "ステータス": "正常",
            "備考": "",
        },
        {
            "ルールID": "offline_002",
            "対象タブ": OFFLINE_TAB_NAME,
            "カテゴリ": "分類",
            "ルール名": "オフライン共通分類",
            "内容": "事業名=スキルプラス、ファネル=ブランド認知で保持する",
            "防止の仕組み": "オフライン案件は共通分類へ固定し、媒体別の揺れを持ち込まない",
            "検知の仕組み": "ファネル空欄や事業名ズレは加工監視で未同期に落とす",
            "ステータス": "正常",
            "備考": "",
        },
    ]


def build_monitor_rows(
    summary_media: dict[str, Any],
    online_rows: list[dict[str, str]],
    offline_rows: list[dict[str, str]],
    cost_rows: list[dict[str, str]],
    generated_at: str,
) -> list[dict[str, str]]:
    rows = []
    for media in ["Meta広告", "TikTok広告", "X広告"]:
        media_rows = [row for row in online_rows if row.get("集客媒体") == media]
        summary = summary_media.get(media, {})
        dates = [row.get("日付", "") for row in media_rows if row.get("日付", "")]
        unmatched_count = summary.get("unmatched_account_count", 0)
        status = "正常" if media_rows and unmatched_count == 0 else "未同期"
        if not media_rows:
            reason = "加工行なし"
        elif unmatched_count:
            reason = f"未照合 {unmatched_count}件"
        else:
            reason = "加工行あり"
        rows.append(
            {
                "対象タブ": ONLINE_TAB_NAME,
                "対象レーン": media,
                "ステータス": status,
                "最終更新日": generated_at,
                "最古日付": min(dates) if dates else "",
                "最新日付": max(dates) if dates else "",
                "行数": str(len(media_rows)),
                "未照合件数": str(summary.get("unmatched_account_count", 0)),
                "除外件数": str(summary.get("excluded_account_count", 0)),
                "判定理由": reason,
            }
        )
    offline_dates = [row.get("日付", "") for row in offline_rows if row.get("日付")]
    rows.append(
        {
            "対象タブ": OFFLINE_TAB_NAME,
            "対象レーン": "オフライン広告",
            "ステータス": "正常" if offline_rows else "未同期",
            "最終更新日": generated_at,
            "最古日付": min(offline_dates) if offline_dates else "",
            "最新日付": max(offline_dates) if offline_dates else "",
            "行数": str(len(offline_rows)),
            "未照合件数": "0",
            "除外件数": "0",
            "判定理由": "加工行あり" if offline_rows else "加工行なし",
        }
    )
    cost_dates = [row.get("日付", "") for row in cost_rows if row.get("日付")]
    rows.append(
        {
            "対象タブ": COST_TAB_NAME,
            "対象レーン": "広告費管理",
            "ステータス": "正常" if cost_rows else "未同期",
            "最終更新日": generated_at,
            "最古日付": min(cost_dates) if cost_dates else "",
            "最新日付": max(cost_dates) if cost_dates else "",
            "行数": str(len(cost_rows)),
            "未照合件数": "0",
            "除外件数": "0",
            "判定理由": "広告費行あり" if cost_rows else "広告費行なし",
        }
    )
    return rows


def build_cost_rows(
    online_rows: list[dict[str, str]],
    offline_rows: list[dict[str, str]],
    route_map: dict[tuple[str, str], str],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    historical_rows = load_historical_cost_rows()
    rows.extend(historical_rows)
    historical_keys = {
        (row.get("日付", ""), row.get("流入経路", ""))
        for row in historical_rows
        if row.get("日付") and row.get("流入経路")
    }

    for supplement_row in load_historical_reference_cost_rows(route_map):
        key = (supplement_row.get("日付", ""), supplement_row.get("流入経路", ""))
        if key in historical_keys:
            continue
        rows.append(supplement_row)

    current_self_aggregated: dict[tuple[str, str, str, str, str], float] = {}
    for row in online_rows:
        date_obj = parse_date_value(row.get("日付", ""))
        if not date_obj or date_obj < CURRENT_MASTER_START or date_obj > TODAY:
            continue
        key = (
            format_date_value(date_obj),
            row.get("事業名", ""),
            row.get("流入経路", ""),
            row.get("集客媒体", ""),
            row.get("ファネル", ""),
        )
        current_self_aggregated[key] = current_self_aggregated.get(key, 0.0) + parse_number(row.get("広告費", ""))

    for key, ad_cost in current_self_aggregated.items():
        date_value, business, route, media, funnel = key
        rows.append(
            {
                "日付": date_value,
                "事業名": business,
                "流入経路": route,
                "集客媒体": media,
                "ファネル": funnel,
                "費用区分": "自社",
                "広告費": format_number(ad_cost),
                "ソース": f"{media} raw",
            }
        )

    for external_row in (
        load_x_outsource_cost_rows()
        + load_youtube_outsource_cost_rows()
        + load_affiliate_cost_rows()
    ):
        date_obj = parse_date_value(external_row.get("日付", ""))
        if not date_obj or date_obj < CURRENT_MASTER_START or date_obj > TODAY:
            continue
        rows.append(external_row)

    for row in offline_rows:
        date_obj = parse_date_value(row.get("日付", ""))
        if date_obj and date_obj > TODAY:
            continue
        route = f"{row.get('集客媒体', 'オフライン広告')}_{row.get('ファネル', '')}".rstrip("_")
        rows.append(
            {
                "日付": row.get("日付", ""),
                "事業名": row.get("事業名", ""),
                "流入経路": route,
                "集客媒体": row.get("集客媒体", ""),
                "ファネル": row.get("ファネル", ""),
                "費用区分": "オフライン",
                "広告費": row.get("広告費", ""),
                "ソース": "オフライン raw",
            }
        )

    rows = [row for row in rows if row.get("費用区分") == "オフライン" or (row.get("日付") and row.get("流入経路") and parse_number(row.get("広告費", "")) > 0)]
    rows = aggregate_cost_rows(rows)
    rows.sort(key=lambda item: (item.get("日付", ""), item.get("流入経路", ""), item.get("費用区分", ""), item.get("ソース", "")))
    return rows


def validate_cost_rows(cost_rows: list[dict[str, str]]) -> dict[str, Any]:
    future_rows: list[dict[str, str]] = []
    invalid_historical_rows: list[dict[str, str]] = []
    invalid_current_rows: list[dict[str, str]] = []
    missing_required_rows: list[dict[str, str]] = []
    duplicate_counter: Counter[tuple[str, str, str, str]] = Counter()

    for row in cost_rows:
        date_text = row.get("日付", "")
        route = row.get("流入経路", "")
        fee_type = row.get("費用区分", "")
        source = row.get("ソース", "")
        duplicate_counter[(date_text, route, fee_type, source)] += 1

        date_obj = parse_date_value(date_text)
        if date_obj and date_obj > TODAY:
            future_rows.append(row)
        if date_obj and date_obj <= HISTORICAL_BASE_END and fee_type in {"自社", "委託"}:
            invalid_historical_rows.append(row)
        if date_obj and date_obj >= CURRENT_MASTER_START and fee_type == "合算":
            invalid_current_rows.append(row)

        if fee_type != "オフライン":
            if not date_text or not route or parse_number(row.get("広告費", "")) <= 0:
                missing_required_rows.append(row)

    duplicate_rows = [
        {
            "日付": key[0],
            "流入経路": key[1],
            "費用区分": key[2],
            "ソース": key[3],
            "件数": count,
        }
        for key, count in duplicate_counter.items()
        if count > 1
    ]

    return {
        "future_rows": future_rows,
        "invalid_historical_rows": invalid_historical_rows,
        "invalid_current_rows": invalid_current_rows,
        "missing_required_rows": missing_required_rows,
        "duplicate_rows": duplicate_rows,
    }


def ensure_cost_rows_valid(cost_rows: list[dict[str, str]]) -> dict[str, Any]:
    audit = validate_cost_rows(cost_rows)
    violations = {
        "future_rows": len(audit["future_rows"]),
        "invalid_historical_rows": len(audit["invalid_historical_rows"]),
        "invalid_current_rows": len(audit["invalid_current_rows"]),
        "missing_required_rows": len(audit["missing_required_rows"]),
        "duplicate_rows": len(audit["duplicate_rows"]),
    }
    if any(violations.values()):
        raise RuntimeError(f"広告費管理の監査で違反を検知: {violations}")
    return audit


def main() -> None:
    parser = argparse.ArgumentParser(description="広告データ（収集）から広告データ（加工）を生成する")
    parser.add_argument("--write-sheet", action="store_true", help="加工用スプレッドシートに書き出す")
    parser.add_argument("--cost-only", action="store_true", help="広告費管理と管理タブだけを書き出す")
    parser.add_argument("--sheet-id", default=PROCESSED_SHEET_ID, help="加工用スプレッドシートID")
    parser.add_argument("--sheet-title", default=PROCESSED_SHEET_TITLE, help="加工用スプレッドシート名")
    parser.add_argument("--output-prefix", default="ads_processed", help="出力ファイル名プレフィックス")
    args = parser.parse_args()

    master_rows = load_sheet_values_batch(
        MASTER_SHEET_ID,
        (MASTER_ACCOUNT_TAB, MASTER_MAPPING_TAB, MASTER_ROUTE_TAB),
    )
    account_rows = master_rows.get(MASTER_ACCOUNT_TAB, [])
    mapping_rows = master_rows.get(MASTER_MAPPING_TAB, [])
    route_rows = master_rows.get(MASTER_ROUTE_TAB, [])

    account_master = build_account_master(account_rows)
    mapping_master = build_mapping_master(mapping_rows)
    route_map = build_route_map(route_rows)

    summary_media: dict[str, Any] = {}
    online_rows: list[dict[str, str]] = []
    unmatched_all: list[dict[str, str]] = []
    excluded_all: list[dict[str, str]] = []

    raw_rows_map = load_sheet_values_batch(
        RAW_SHEET_ID,
        tuple(list(RAW_TABS.keys()) + [OFFLINE_RAW_TAB]),
    )
    for raw_tab, media in RAW_TABS.items():
        raw_rows = raw_rows_map.get(raw_tab, [])
        processed_rows, unmatched, excluded = collect_online_rows(
            media=media,
            raw_rows=raw_rows,
            account_master=account_master,
            mapping_master=mapping_master,
            route_map=route_map,
        )
        online_rows.extend(processed_rows)
        unmatched_all.extend(unmatched)
        excluded_all.extend(excluded)
        summary_media[media] = {
            "raw_rows": max(len(raw_rows) - 1, 0),
            "processed_rows": len(processed_rows),
            "unmatched_account_count": len(unmatched),
            "excluded_account_count": len(excluded),
            "funnel_counts": dict(Counter(row["ファネル"] for row in processed_rows if row.get("ファネル"))),
        }

    fill_delivery_span(online_rows)

    offline_raw_rows = raw_rows_map.get(OFFLINE_RAW_TAB, [])
    offline_rows = collect_offline_rows(offline_raw_rows)
    cost_rows = build_cost_rows(online_rows, offline_rows, route_map)
    cost_audit = ensure_cost_rows_valid(cost_rows)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    source_rows = build_source_management_rows(summary_media, offline_rows, cost_rows, generated_at)
    rule_rows = build_rule_rows()
    monitor_rows = build_monitor_rows(summary_media, online_rows, offline_rows, cost_rows, generated_at)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    online_csv = OUTPUT_DIR / f"{args.output_prefix}_online_{timestamp}.csv"
    offline_csv = OUTPUT_DIR / f"{args.output_prefix}_offline_{timestamp}.csv"
    summary_json = OUTPUT_DIR / f"{args.output_prefix}_{timestamp}_summary.json"
    write_csv(online_csv, ONLINE_HEADERS, online_rows)
    write_csv(offline_csv, OFFLINE_HEADERS, offline_rows)
    write_json(
        summary_json,
        {
            "generated_at": generated_at,
            "online_rows": len(online_rows),
            "offline_rows": len(offline_rows),
            "cost_rows": len(cost_rows),
            "media": summary_media,
            "unmatched_accounts": unmatched_all,
            "excluded_accounts": excluded_all,
            "cost_audit": {
                "future_rows": len(cost_audit["future_rows"]),
                "invalid_historical_rows": len(cost_audit["invalid_historical_rows"]),
                "invalid_current_rows": len(cost_audit["invalid_current_rows"]),
                "missing_required_rows": len(cost_audit["missing_required_rows"]),
                "duplicate_rows": len(cost_audit["duplicate_rows"]),
            },
            "saved_to": {
                "online_csv": str(online_csv),
                "offline_csv": str(offline_csv),
            },
        },
    )

    if args.write_sheet:
        client = get_client("kohara")
        spreadsheet = client.open_by_key(args.sheet_id) if args.sheet_id else open_or_create_spreadsheet(client, args.sheet_title)
        if not args.cost_only:
            write_matrix_to_sheet(
                spreadsheet=spreadsheet,
                tab_name=ONLINE_TAB_NAME,
                headers=ONLINE_HEADERS,
                matrix=build_sheet_matrix(ONLINE_HEADERS, online_rows, ONLINE_TEXT_HEADERS),
                text_headers=ONLINE_TEXT_HEADERS,
            )
            write_matrix_to_sheet(
                spreadsheet=spreadsheet,
                tab_name=OFFLINE_TAB_NAME,
                headers=OFFLINE_HEADERS,
                matrix=build_sheet_matrix(OFFLINE_HEADERS, offline_rows),
            )
        write_matrix_to_sheet(
            spreadsheet=spreadsheet,
            tab_name=COST_TAB_NAME,
            headers=COST_HEADERS,
            matrix=build_sheet_matrix(COST_HEADERS, cost_rows),
        )
        write_matrix_to_sheet(
            spreadsheet=spreadsheet,
            tab_name=SOURCE_MANAGEMENT_TAB,
            headers=SOURCE_MANAGEMENT_HEADERS,
            matrix=build_sheet_matrix(SOURCE_MANAGEMENT_HEADERS, source_rows),
            status_options=STATUS_OPTIONS,
        )
        write_matrix_to_sheet(
            spreadsheet=spreadsheet,
            tab_name=RULES_TAB,
            headers=RULE_HEADERS,
            matrix=build_sheet_matrix(RULE_HEADERS, rule_rows),
            status_options=STATUS_OPTIONS,
        )
        write_matrix_to_sheet(
            spreadsheet=spreadsheet,
            tab_name=MONITOR_TAB,
            headers=MONITOR_HEADERS,
            matrix=build_sheet_matrix(MONITOR_HEADERS, monitor_rows),
            status_options=STATUS_OPTIONS,
        )

    print(f"オンライン保存先: {online_csv}")
    print(f"オフライン保存先: {offline_csv}")
    print(f"サマリー: {summary_json}")
    print(f"オンライン行数: {len(online_rows)}")
    print(f"オフライン行数: {len(offline_rows)}")


if __name__ == "__main__":
    main()
