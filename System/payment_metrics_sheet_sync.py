#!/usr/bin/env python3
"""
【アドネス株式会社】スキルプラス着金データ（加工）を再生成する。

方針:
- visible なタブは `日別売上数値 / 売上サマリー / データソース管理 / データ追加ルール` の4つだけに絞る
- 内部ロジックでは 1資金イベント単位で正規化するが、明細タブは常設しない
- 日別タブにはスキルプラス事業だけを出し、`完全不明` は入れない
- `返金額` は相談窓口シートを案件正本にし、raw 決済は突合と補完にだけ使う
- `解約請求回収額` は中途解約タブの負値のうち、回収済みと確認できたものだけを正本にする
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound

from sheets_manager import get_client
from scripts.setup_payment_product_master import (
    BUSINESS_SKILLPLUS,
    MASTER_SHEET_ID,
    MASTER_PRODUCT_TAB,
    PAYMENT_MAPPING_EXCLUDED_RAW_NAMES,
    PAYMENT_COLLECTION_SHEET_ID,
    PAYMENT_COLLECTION_TAB,
    PAYMENT_MAPPING_TAB,
    source_sale_is_success,
)


TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】スキルプラス着金データ（加工）"
TARGET_SPREADSHEET_ID = "1eh8X_dsRitFDKAJVE-dbr75ycGfMffMsvJYI-Gtlv_Q"
CS_SHEET_ID = "1XOkJsXzEx4iV9h8F-cywg0FOS4Knf7IfekN78RZAr6I"
SKILLPLUS_STUDENT_SHEET_ID = "1zL8LV9CF8RLKiNDNqsYO6UXxuhBW32NcDaPJ5FqB17M"

DAILY_TAB_NAME = "日別売上数値"
SUMMARY_TAB_NAME = "売上サマリー"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    DAILY_TAB_NAME: (1200, 14),
    SUMMARY_TAB_NAME: (50, 3),
    SOURCE_MANAGEMENT_TAB_NAME: (80, 12),
    RULE_TAB_NAME: (60, 3),
}

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "data" / "payment_metrics_sheet_state.json"
LOCK_PATH = BASE_DIR / "data" / "payment_metrics_sheet_sync.lock"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 11,
}
TAB_COLORS = {
    DAILY_TAB_NAME: "#1A73E8",
    SUMMARY_TAB_NAME: "#FBBC04",
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}
STATUS_OPTIONS = ["正常", "要確認", "停止"]
STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "要確認": {"backgroundColor": {"red": 1.0, "green": 0.945, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
}
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "スキルプラス着金データ（加工）自動生成"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
START_DATE = datetime(2025, 1, 1)
START_DATE_TEXT = START_DATE.strftime("%Y/%m/%d")
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")

SKILLPLUS_CASE_CODES = {"STD", "PRM", "ELT", "SPS"}
NON_SKILLPLUS_CASE_CODES = {"デザジュク", "アドネス", "ギブセル", "その他"}
REFUND_MATCH_LOOKBACK_DAYS = 30
REFUND_MATCH_LOOKAHEAD_DAYS = 120
SKILLPLUS_BLANK_SOURCE_CONFIRMED_SOURCES = {
    "日本プラム",
    "きらぼし銀行",
    "CBS",
    "京都信販",
    "CREDIX",
}
SKILLPLUS_BLANK_SOURCE_DEFAULT_SOURCES = {
    "UnivaPay",
    "日本プラム",
    "きらぼし銀行",
    "CBS",
    "京都信販",
    "CREDIX",
    "INVOY",
}
KIRABOSHI_NON_CUSTOMER_PATTERNS = (
    "ﾕﾆｳﾞｧﾍﾟｲ",
    "ﾕﾆｳﾞｱﾍﾟｲ",
    "ﾕﾆｳﾞｧ",
    "ﾕﾆｳﾞｱ",
    "ﾆﾎﾝﾌﾟﾗﾑ",
    "ｽﾄﾗｲﾌﾟ",
    "ﾓｯｼｭ",
)
CLAIM_COLLECTED_POSITIVE_MARKERS = (
    "入金済",
    "入金確認済",
    "振込済",
    "振込み済",
    "振り込み済",
    "支払い済",
    "支払済",
    "お支払い済",
    "お支払い済み",
    "振り込まれております",
    "振り込まれており",
    "振込完了",
)
CLAIM_COLLECTED_NEGATIVE_MARKERS = (
    "未入金",
    "未払い",
    "未支払",
    "未振込",
    "振り込まれておりません",
    "振り込まれていません",
)
SKILLPLUS_STUDENT_EXCLUDED_TABS = {"最新元データ一覧"}
OTHER_BUSINESS_MATCH_LOOKBACK_DAYS = 30
OTHER_BUSINESS_MATCH_LOOKAHEAD_DAYS = 120
OTHER_BUSINESS_EVIDENCE_CONFIGS = [
    {
        "sheet_id": "1KGhnTUSDi0MqgTujvQmVSihzINpXTdo8vcmRVJUwL9k",
        "tab": "成約済み",
        "date_headers": ["初回着金日", "成約日", "初着座日"],
        "email_headers": ["メールアドレス"],
        "phone_headers": ["電話番号"],
        "name_headers": ["お名前", "名前", "回答者名"],
        "product_headers": ["商品"],
    },
    {
        "sheet_id": "1KGhnTUSDi0MqgTujvQmVSihzINpXTdo8vcmRVJUwL9k",
        "tab": "ｲﾚｷﾞｭﾗｰ",
        "date_headers": ["初回着金日", "初成約日", "登録日"],
        "email_headers": ["メール", "メールアドレス"],
        "phone_headers": ["電話番号"],
        "name_headers": ["名前", "お名前"],
        "product_headers": ["商品"],
    },
    {
        "sheet_id": "1LoJoCMKqd_L2yJpztdpnBE80PXL_rQvmtnpETQ8I7Dg",
        "tab": "全社_クライアント台帳",
        "date_headers": ["入金日(着金)", "契約締結日"],
        "email_headers": ["メールアドレス"],
        "phone_headers": ["電話番号"],
        "name_headers": ["代表者名", "担当者名"],
        "product_headers": ["商品"],
    },
    {
        "sheet_id": "1bmeTRnznd-2PuIfMLs27Vx2SuijIcfbxbq90vfKNx9M",
        "tab": "受注クライアント管理",
        "date_headers": ["入金日(着金)", "契約締結日", "成約日"],
        "email_headers": ["メールアドレス"],
        "phone_headers": ["電話番号"],
        "name_headers": ["企業担当名", "代表者名"],
        "product_headers": ["商品名"],
    },
]


@dataclass(frozen=True)
class MappingEntry:
    source: str
    raw_name: str
    product_name: str
    product_id: str
    management_code: str
    business: str
    target: str
    customer_attr: str
    status: str
    reason: str


@dataclass(frozen=True)
class PaymentSaleEvent:
    date: str
    amount: int
    email: str
    full_name: str
    line_name: str
    phone: str
    product_name: str
    business: str


@dataclass(frozen=True)
class RefundCase:
    date: str
    amount: int
    email: str
    full_name: str
    line_name: str
    phone: str
    source_tab: str
    sheet_row: int


@dataclass(frozen=True)
class OtherBusinessEvidence:
    date: str
    email: str
    phone: str
    full_name: str
    product_name: str
    source_tab: str


@dataclass(frozen=True)
class SaleContext:
    source: str
    raw_name: str
    event_date: str
    event_dt: datetime
    mapping_entry: Optional[MappingEntry]
    classification: str
    is_blank_confirmed: bool
    is_univapay_head_payment: bool
    recurring_id: str
    charge_type: str


class FileLock:
    def __init__(self, lock_path: Path = LOCK_PATH, timeout_seconds: int = 1800):
        self.lock_path = Path(lock_path)
        self.timeout_seconds = timeout_seconds

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                lock_data = json.loads(self.lock_path.read_text())
                locked_at = datetime.fromisoformat(lock_data.get("locked_at", ""))
                elapsed = (datetime.now() - locked_at).total_seconds()
                if elapsed < self.timeout_seconds:
                    raise RuntimeError(
                        f"スキルプラス着金データ（加工）の更新はロック中です: "
                        f"{lock_data.get('locked_by', '不明')} ({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"payment_metrics_sheet_sync (PID: {os.getpid()})",
        }
        self.lock_path.write_text(json.dumps(payload, ensure_ascii=False))

    def release(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


def repeat_cell_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int, fmt: dict, fields: str) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": fields,
        }
    }


def set_column_width_request(sheet_id: int, start_col: int, end_col: int, width: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_col,
                "endIndex": end_col,
            },
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }
    }


def set_row_height_request(sheet_id: int, start_row: int, end_row: int, height: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": start_row,
                "endIndex": end_row,
            },
            "properties": {"pixelSize": height},
            "fields": "pixelSize",
        }
    }


def set_sheet_properties_request(sheet_id: int, properties: dict, fields: str) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, **properties},
            "fields": fields,
        }
    }


def hex_to_rgb(hex_color: str) -> dict:
    hex_color = hex_color.lstrip("#")
    return {
        "red": int(hex_color[0:2], 16) / 255.0,
        "green": int(hex_color[2:4], 16) / 255.0,
        "blue": int(hex_color[4:6], 16) / 255.0,
    }


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_email(value: object) -> str:
    email = normalize_text(value).lower()
    if email.startswith("mailto:"):
        email = email.split("mailto:", 1)[1]
    return email


def normalize_phone(value: object) -> str:
    return re.sub(r"\D", "", normalize_text(value))


def normalize_name_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", normalize_text(value)).lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    return "".join(ch for ch in text if ch.isalnum() or ch == "ー")


def normalize_compact_text(value: object) -> str:
    return re.sub(r"[\s\u3000]+", "", unicodedata.normalize("NFKC", normalize_text(value)).lower())


def normalize_header_key(value: object) -> str:
    return re.sub(r"[\s\u3000]+", "", normalize_text(value))


def normalize_date(raw: str) -> str:
    value = normalize_text(raw)
    if not value:
        return ""
    match = DATE_RE.search(value)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def parse_date(raw: str) -> datetime | None:
    normalized = normalize_date(raw)
    if not normalized:
        return None
    return datetime.strptime(normalized, "%Y/%m/%d")


def parse_amount(raw: object) -> int:
    text = normalize_text(raw)
    if not text:
        return 0
    sign = -1 if text.startswith("-") else 1
    digits = re.sub(r"[^\d]", "", text)
    if not digits:
        return 0
    return sign * int(digits)


def normalize_display_amount(value: int) -> str:
    return f"¥{value:,}"


def normalize_display_count(value: int) -> str:
    return f"{value:,}"


def parse_meta_json(meta_json: str) -> list[dict]:
    text = normalize_text(meta_json)
    if not text:
        return []
    try:
        payload = json.loads(text)
    except Exception:
        return []

    parts: list[dict] = []
    for key in ("charge_metadata", "token_metadata"):
        part = payload.get(key)
        if isinstance(part, str):
            try:
                part = json.loads(part)
            except Exception:
                part = {}
        if isinstance(part, dict):
            parts.append(part)
    return parts


def extract_univapay_product_hints(meta_json: str) -> list[str]:
    hints: list[str] = []
    for part in parse_meta_json(meta_json):
        for key in ("product_detail_name", "univapay-product-names"):
            value = normalize_text(part.get(key))
            if value:
                hints.append(value)
    return hints


def is_univapay_head_payment(meta_json: str) -> bool:
    return any("頭金お支払い" in hint for hint in extract_univapay_product_hints(meta_json))


def payment_row_dedupe_key(row: list[str]) -> tuple[str, ...]:
    return tuple(normalize_text(cell) for cell in row)


def blank_sale_is_obvious_non_customer_transfer(row: list[str], idx: dict[str, int], source: str) -> bool:
    if source != "きらぼし銀行":
        return False
    name_text = normalize_compact_text(row[idx["名前（原本）"]])
    if not name_text:
        return False
    return any(normalize_compact_text(pattern) in name_text for pattern in KIRABOSHI_NON_CUSTOMER_PATTERNS)


def charge_is_recurring(charge_type: str, recurring_id: str) -> bool:
    normalized = normalize_text(charge_type)
    if recurring_id:
        return True
    return normalized in {"リカーリング", "定期課金"}


def claim_is_collected(*texts: object) -> bool:
    normalized = normalize_compact_text(" / ".join(normalize_text(text) for text in texts))
    if not normalized:
        return False
    negative_markers = [normalize_compact_text(marker) for marker in CLAIM_COLLECTED_NEGATIVE_MARKERS]
    positive_markers = [normalize_compact_text(marker) for marker in CLAIM_COLLECTED_POSITIVE_MARKERS]
    if any(marker in normalized for marker in negative_markers):
        return False
    return any(marker in normalized for marker in positive_markers)


def claim_case_dedupe_key(
    *,
    email: str,
    full_name: str,
    line_name: str,
    explicit_code: str,
    contract_date: str,
    amount: int,
) -> tuple[str, ...]:
    return (
        email,
        full_name,
        line_name,
        explicit_code,
        contract_date,
        str(abs(amount)),
    )


def header_index_by_exact(headers: list[str], candidates: Iterable[str]) -> Optional[int]:
    candidate_keys = {normalize_header_key(candidate) for candidate in candidates if normalize_text(candidate)}
    for index, header in enumerate(headers):
        if normalize_header_key(header) in candidate_keys:
            return index
    return None


def header_indexes_by_contains(headers: list[str], keywords: Iterable[str]) -> list[int]:
    normalized_keywords = [normalize_text(keyword) for keyword in keywords if normalize_text(keyword)]
    matches: list[int] = []
    for index, header in enumerate(headers):
        header_text = normalize_text(header)
        if any(keyword in header_text for keyword in normalized_keywords):
            matches.append(index)
    return matches


def pick_first_value(row: list[str], indexes: Iterable[int]) -> str:
    for index in indexes:
        if index < len(row):
            value = normalize_text(row[index])
            if value:
                return value
    return ""


def is_quota_error(exc: APIError) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code == 429 or "Quota exceeded" in str(exc)


def run_write_with_retry(description: str, func):
    last_error = None
    waits = (0, *WRITE_RETRY_SECONDS)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except APIError as exc:
            if not is_quota_error(exc) or attempt == len(waits):
                raise
            last_error = exc
            print(f"{description}: Sheets の書き込み回数制限に当たったため再試行します。")
    if last_error:
        raise last_error


def batch_update_with_retry(spreadsheet, body: dict, description: str) -> None:
    run_write_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_write_with_retry(description, func)


def get_all_values_with_retry(ws) -> List[List[str]]:
    for attempt in range(4):
        try:
            return ws.get_all_values()
        except Exception as exc:
            message = str(exc)
            is_quota = "429" in message or "Quota exceeded" in message
            if not is_quota or attempt == 3:
                raise
            wait_seconds = 65 * (attempt + 1)
            print(f"読み取り上限に到達: {ws.title} を {wait_seconds} 秒待って再試行")
            time.sleep(wait_seconds)
    return []


def get_or_create_target_spreadsheet(gc) -> gspread.Spreadsheet:
    try:
        spreadsheet = gc.open_by_key(TARGET_SPREADSHEET_ID)
    except SpreadsheetNotFound:
        spreadsheet = run_write_with_retry(
            "スキルプラス着金データ（加工）シートの作成",
            lambda: gc.create(TARGET_SPREADSHEET_TITLE),
        )
    ensure_spreadsheet_title(spreadsheet)
    return spreadsheet


def ensure_spreadsheet_title(spreadsheet) -> None:
    metadata = spreadsheet.fetch_sheet_metadata({"fields": "properties.title"})
    title = metadata.get("properties", {}).get("title", "")
    if title == TARGET_SPREADSHEET_TITLE:
        return
    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                {
                    "updateSpreadsheetProperties": {
                        "properties": {"title": TARGET_SPREADSHEET_TITLE},
                        "fields": "title",
                    }
                }
            ]
        },
        "スキルプラス着金データ（加工）のシート名更新",
    )


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}
    for name, (rows, cols) in TAB_SPECS.items():
        if name in tabs:
            ws = tabs[name]
            if ws.row_count != rows or ws.col_count != cols:
                worksheet_write_with_retry(
                    f"{name} タブのサイズ調整",
                    lambda ws=ws, rows=rows, cols=cols: ws.resize(rows=rows, cols=cols),
                )
            continue
        tabs[name] = run_write_with_retry(
            f"{name} タブの作成",
            lambda name=name, rows=rows, cols=cols: spreadsheet.add_worksheet(title=name, rows=rows, cols=cols),
        )

    target_names = set(TAB_SPECS.keys())
    for title, ws in list(tabs.items()):
        if title not in target_names:
            batch_update_with_retry(
                spreadsheet,
                {"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
                f"{title} タブの削除",
            )
            tabs.pop(title, None)

    requests = []
    ordered_names = [DAILY_TAB_NAME, SUMMARY_TAB_NAME, SOURCE_MANAGEMENT_TAB_NAME, RULE_TAB_NAME]
    for idx, name in enumerate(ordered_names):
        ws = tabs[name]
        requests.append(set_sheet_properties_request(ws.id, {"index": idx, "hidden": False}, "index,hidden"))
        requests.append(
            set_sheet_properties_request(
                ws.id,
                {"tabColorStyle": {"rgbColor": hex_to_rgb(TAB_COLORS[name])}},
                "tabColorStyle",
            )
        )
    batch_update_with_retry(spreadsheet, {"requests": requests}, "スキルプラス着金データ（加工）のタブ整列")
    return {ws.title: ws for ws in spreadsheet.worksheets()}


def write_rows(spreadsheet, ws, rows: List[List[object]]) -> None:
    max_cols = max((len(row) for row in rows), default=1)
    padded = [list(row) + [""] * max(0, max_cols - len(row)) for row in rows]
    target_rows = max(len(padded), 2)
    if ws.row_count != target_rows or ws.col_count != max_cols:
        worksheet_write_with_retry(
            f"{ws.title} タブのサイズ最適化",
            lambda: ws.resize(rows=target_rows, cols=max_cols),
        )
    worksheet_write_with_retry(f"{ws.title} クリア", lambda: ws.clear())
    worksheet_write_with_retry(
        f"{ws.title} 更新",
        lambda: ws.update(range_name="A1", values=padded, value_input_option="USER_ENTERED"),
    )


def style_daily_tab(spreadsheet, ws) -> None:
    widths = [120, 140, 140, 150, 135, 130, 135, 150, 110, 110, 120, 110, 110, 130]
    requests = [
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            len(widths),
            {
                "backgroundColor": HEADER_BG,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": HEADER_TEXT,
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            0,
            len(widths),
            {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "horizontalAlignment": "RIGHT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
                "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "fontSize": 10},
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            0,
            1,
            {
                "horizontalAlignment": "LEFT",
                "numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"},
            },
            "userEnteredFormat(horizontalAlignment,numberFormat)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            1,
            7,
            {
                "numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"},
            },
            "userEnteredFormat.numberFormat",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            7,
            len(widths),
            {
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            },
            "userEnteredFormat.numberFormat",
        ),
        set_row_height_request(ws.id, 0, 1, 34),
        set_row_height_request(ws.id, 1, ws.row_count, 24),
        {
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": ws.row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(widths),
                    }
                }
            }
        },
    ]
    for idx, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, idx, idx + 1, width))
    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の体裁適用")


def style_meta_tab(spreadsheet, ws, widths: List[int], *, center_cols=None, date_cols=None, status_col=None, number_cols=None) -> None:
    center_cols = center_cols or []
    date_cols = date_cols or []
    number_cols = number_cols or []
    requests = [
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            len(widths),
            {
                "backgroundColor": HEADER_BG,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": HEADER_TEXT,
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            0,
            len(widths),
            {
                "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
                "textFormat": {"foregroundColor": {"red": 0, "green": 0, "blue": 0}, "fontSize": 10},
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)",
        ),
        set_row_height_request(ws.id, 0, 1, 34),
        set_row_height_request(ws.id, 1, ws.row_count, 24),
        {
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": ws.row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(widths),
                    }
                }
            }
        },
    ]
    for idx in center_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                idx,
                idx + 1,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    for idx in date_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                idx,
                idx + 1,
                {"numberFormat": {"type": "DATE_TIME", "pattern": "yyyy/mm/dd hh:mm"}},
                "userEnteredFormat.numberFormat",
            )
        )
    for idx in number_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                idx,
                idx + 1,
                {"horizontalAlignment": "RIGHT", "numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat(horizontalAlignment,numberFormat)",
            )
        )
    if status_col is not None:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                status_col,
                status_col + 1,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    for idx, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, idx, idx + 1, width))
    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の体裁適用")

    if status_col is not None:
        validation = {
            "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": value} for value in STATUS_OPTIONS]},
            "showCustomUi": True,
            "strict": True,
        }
        batch_update_with_retry(
            spreadsheet,
            {
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": ws.id,
                                "startRowIndex": 1,
                                "endRowIndex": ws.row_count,
                                "startColumnIndex": status_col,
                                "endColumnIndex": status_col + 1,
                            },
                            "rule": validation,
                        }
                    }
                ]
            },
            f"{ws.title} のステータス入力規則",
        )


def apply_status_cell_colors(spreadsheet, ws, rows: List[List[object]], status_col_index: int) -> None:
    requests = []
    for row_index, row in enumerate(rows[1:], start=1):
        status = str(row[status_col_index]).strip() if len(row) > status_col_index else ""
        fmt = STATUS_FORMATS.get(status)
        if not fmt:
            continue
        requests.append(
            repeat_cell_request(
                ws.id,
                row_index,
                row_index + 1,
                status_col_index,
                status_col_index + 1,
                {
                    **fmt,
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"bold": True},
                },
                "userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.textFormat.bold",
            )
        )
    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} のステータス色適用")


def apply_protections(spreadsheet, tabs) -> None:
    protected_names = list(TAB_SPECS.keys())
    target_sheet_ids = {tabs[name].id for name in protected_names}
    metadata = spreadsheet.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties.sheetId,protectedRanges(protectedRangeId,description,range(sheetId,startRowIndex,endRowIndex,startColumnIndex,endColumnIndex)))",
        }
    )

    requests = []
    existing_sheet_protection = set()
    for sheet in metadata.get("sheets", []):
        sheet_id = sheet.get("properties", {}).get("sheetId")
        for protected_range in sheet.get("protectedRanges", []):
            range_info = protected_range.get("range", {})
            description = protected_range.get("description", "")
            range_sheet_id = range_info.get("sheetId", sheet_id)
            if range_sheet_id in target_sheet_ids:
                has_row = any(key in range_info for key in ("startRowIndex", "endRowIndex"))
                has_col = any(key in range_info for key in ("startColumnIndex", "endColumnIndex"))
                if not has_row and not has_col:
                    existing_sheet_protection.add(range_sheet_id)
            if range_sheet_id in target_sheet_ids and str(description).startswith(PROTECTION_PREFIX):
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_range["protectedRangeId"]}})

    for name in protected_names:
        if tabs[name].id in existing_sheet_protection:
            continue
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": tabs[name].id},
                        "description": f"{PROTECTION_PREFIX}: {name}",
                        "warningOnly": False,
                        "editors": {"users": PROTECTED_EDITOR_EMAILS},
                    }
                }
            }
        )

    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, "スキルプラス着金データ（加工）の保護設定")


def get_tab_url(spreadsheet_id: str, ws) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={ws.id}"


def load_product_business_map(ws) -> tuple[set[str], set[str]]:
    rows = get_all_values_with_retry(ws)
    if not rows:
        return set(), set()
    headers = rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    skillplus_names = set()
    non_skillplus_names = set()
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        name = normalize_text(padded[idx["商品名"]])
        business = normalize_text(padded[idx["事業区分"]])
        if not name:
            continue
        if business == BUSINESS_SKILLPLUS:
            skillplus_names.add(name)
        else:
            non_skillplus_names.add(name)
    return skillplus_names, non_skillplus_names


def load_payment_mapping(ws) -> Dict[tuple[str, str], MappingEntry]:
    rows = get_all_values_with_retry(ws)
    if not rows:
        return {}
    headers = rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    mapping: Dict[tuple[str, str], MappingEntry] = {}
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        source = normalize_text(padded[idx["決済ソース"]])
        raw_name = normalize_text(padded[idx["生商品名"]])
        if not source or not raw_name:
            continue
        mapping[(source, raw_name)] = MappingEntry(
            source=source,
            raw_name=raw_name,
            product_name=normalize_text(padded[idx["正式商品名"]]),
            product_id=normalize_text(padded[idx["商品ID"]]),
            management_code=normalize_text(padded[idx["商品管理コード"]]),
            business=normalize_text(padded[idx["事業区分"]]),
            target=normalize_text(padded[idx["対象顧客"]]),
            customer_attr=normalize_text(padded[idx["顧客属性区分"]]),
            status=normalize_text(padded[idx["判定区分"]]),
            reason=normalize_text(padded[idx["判定根拠"]]),
        )
    return mapping


def build_text_markers(product_names: Iterable[str]) -> list[str]:
    markers = {normalize_text(name) for name in product_names if normalize_text(name)}
    markers.update({"スキルプラス", "AIX", "SNSマーケ", "みかみ", "AICAN", "AIカレッジ", "センサーズ", "アクションマップ"})
    return sorted(markers, key=len, reverse=True)


def text_contains_any_marker(text: str, markers: Iterable[str]) -> bool:
    normalized = normalize_text(text)
    if not normalized:
        return False
    return any(marker and marker in normalized for marker in markers)


def is_skillplus_student_raw_tab(title: str) -> bool:
    normalized = normalize_text(title)
    return "（加工）" not in normalized and normalized not in SKILLPLUS_STUDENT_EXCLUDED_TABS


def detect_student_header_row(rows: list[list[str]]) -> Optional[int]:
    for index, row in enumerate(rows[:5]):
        joined = " / ".join(normalize_text(cell) for cell in row if normalize_text(cell))
        if not joined:
            continue
        if any(keyword in joined for keyword in ("メールアドレス", "電話番号", "お電話番号", "ご入会日", "入会日", "回答者名", "表示名")):
            return index
    return None


def build_student_header_spec(headers: list[str]) -> dict[str, object]:
    return {
        "email_indexes": header_indexes_by_contains(headers, ["メールアドレス"]),
        "phone_indexes": header_indexes_by_contains(headers, ["電話番号", "お電話番号"]),
        "full_name_indexes": header_indexes_by_contains(headers, ["お名前", "本名"]),
        "display_name_indexes": header_indexes_by_contains(headers, ["回答者名", "表示名"]),
        "nickname_indexes": header_indexes_by_contains(headers, ["ニックネーム"]),
        "furigana_indexes": header_indexes_by_contains(headers, ["ふりがな"]),
        "surname_index": header_index_by_exact(headers, ["姓", "姓（せい）"]),
        "given_name_index": header_index_by_exact(headers, ["名"]),
    }


def load_skillplus_student_identifiers(student_ss) -> dict[str, set[str]]:
    emails: set[str] = set()
    phones: set[str] = set()
    names: set[str] = set()

    for ws in student_ss.worksheets():
        if not is_skillplus_student_raw_tab(ws.title):
            continue

        rows = get_all_values_with_retry(ws)
        header_row_index = detect_student_header_row(rows)
        if header_row_index is None:
            continue

        headers = rows[header_row_index]
        spec = build_student_header_spec(headers)
        surname_index = spec["surname_index"]
        given_name_index = spec["given_name_index"]

        for row in rows[header_row_index + 1 :]:
            if not any(normalize_text(cell) for cell in row):
                continue

            email = normalize_email(pick_first_value(row, spec["email_indexes"]))
            phone = normalize_phone(pick_first_value(row, spec["phone_indexes"]))

            full_name_source = pick_first_value(row, spec["full_name_indexes"])
            if not full_name_source and surname_index is not None and given_name_index is not None:
                surname = normalize_text(row[surname_index]) if surname_index < len(row) else ""
                given_name = normalize_text(row[given_name_index]) if given_name_index < len(row) else ""
                full_name_source = f"{surname}{given_name}"

            name_candidates = [
                normalize_name_key(full_name_source),
                normalize_name_key(pick_first_value(row, spec["display_name_indexes"])),
                normalize_name_key(pick_first_value(row, spec["nickname_indexes"])),
                normalize_name_key(pick_first_value(row, spec["furigana_indexes"])),
            ]
            name_candidates = [candidate for candidate in name_candidates if candidate]

            if not email and not phone and not name_candidates:
                continue

            if email:
                emails.add(email)
            if phone:
                phones.add(phone)
            names.update(name_candidates)
    return {"emails": emails, "phones": phones, "names": names}


def detect_other_business_header_row(rows: list[list[str]], config: dict) -> Optional[int]:
    candidate_keys = {
        normalize_header_key(header)
        for header in (
            config["date_headers"]
            + config["email_headers"]
            + config["phone_headers"]
            + config["name_headers"]
            + config["product_headers"]
        )
        if normalize_text(header)
    }
    best_index: Optional[int] = None
    best_score = 0
    for index, row in enumerate(rows[:8]):
        score = sum(1 for cell in row if normalize_header_key(cell) in candidate_keys)
        if score > best_score:
            best_score = score
            best_index = index
    if best_score >= 2:
        return best_index
    return None


def build_other_business_header_spec(headers: list[str], config: dict) -> dict[str, list[int]]:
    return {
        "date_indexes": [
            index
            for index in (
                header_index_by_exact(headers, [candidate]) for candidate in config["date_headers"]
            )
            if index is not None
        ],
        "email_indexes": [
            index
            for index in (
                header_index_by_exact(headers, [candidate]) for candidate in config["email_headers"]
            )
            if index is not None
        ],
        "phone_indexes": [
            index
            for index in (
                header_index_by_exact(headers, [candidate]) for candidate in config["phone_headers"]
            )
            if index is not None
        ],
        "name_indexes": [
            index
            for index in (
                header_index_by_exact(headers, [candidate]) for candidate in config["name_headers"]
            )
            if index is not None
        ],
        "product_indexes": [
            index
            for index in (
                header_index_by_exact(headers, [candidate]) for candidate in config["product_headers"]
            )
            if index is not None
        ],
    }


def load_other_business_evidence(gc: gspread.Client) -> dict[str, dict[str, list[OtherBusinessEvidence]]]:
    indexes = {
        "emails": defaultdict(list),
        "phones": defaultdict(list),
        "names": defaultdict(list),
    }
    spreadsheet_cache: dict[str, gspread.Spreadsheet] = {}

    for config in OTHER_BUSINESS_EVIDENCE_CONFIGS:
        sheet_id = config["sheet_id"]
        if sheet_id not in spreadsheet_cache:
            spreadsheet_cache[sheet_id] = gc.open_by_key(sheet_id)
        ws = spreadsheet_cache[sheet_id].worksheet(config["tab"])
        rows = get_all_values_with_retry(ws)
        if not rows:
            continue

        header_row_index = detect_other_business_header_row(rows, config)
        if header_row_index is None:
            continue

        headers = rows[header_row_index]
        spec = build_other_business_header_spec(headers, config)
        if not (spec["date_indexes"] or spec["email_indexes"] or spec["phone_indexes"] or spec["name_indexes"]):
            continue

        for row in rows[header_row_index + 1 :]:
            if not any(normalize_text(cell) for cell in row):
                continue

            event_date = ""
            for date_index in spec["date_indexes"]:
                if date_index < len(row):
                    event_date = normalize_date(row[date_index])
                    if event_date:
                        break
            if not event_date:
                continue

            email = normalize_email(pick_first_value(row, spec["email_indexes"]))
            phone = normalize_phone(pick_first_value(row, spec["phone_indexes"]))
            full_name = normalize_name_key(pick_first_value(row, spec["name_indexes"]))
            product_name = normalize_text(pick_first_value(row, spec["product_indexes"]))
            if not email and not phone and not full_name:
                continue

            evidence = OtherBusinessEvidence(
                date=event_date,
                email=email,
                phone=phone,
                full_name=full_name,
                product_name=product_name,
                source_tab=f"{spreadsheet_cache[sheet_id].title} / {config['tab']}",
            )
            if evidence.email:
                indexes["emails"][evidence.email].append(evidence)
            if evidence.phone:
                indexes["phones"][evidence.phone].append(evidence)
            if evidence.full_name:
                indexes["names"][evidence.full_name].append(evidence)

    return indexes


def other_business_evidence_matches_event(evidence: OtherBusinessEvidence, event_dt: datetime | None) -> bool:
    if event_dt is None:
        return False
    evidence_dt = parse_date(evidence.date)
    if evidence_dt is None:
        return False
    if event_dt < evidence_dt - timedelta(days=OTHER_BUSINESS_MATCH_LOOKBACK_DAYS):
        return False
    if event_dt > evidence_dt + timedelta(days=OTHER_BUSINESS_MATCH_LOOKAHEAD_DAYS):
        return False
    return True


def identifiers_hit_other_business(
    *,
    email: str,
    phone: str,
    full_name: str,
    line_name: str,
    event_dt: datetime | None,
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> bool:
    candidate_groups: list[list[OtherBusinessEvidence]] = []
    if email and email in other_business_index["emails"]:
        candidate_groups.append(other_business_index["emails"][email])
    if phone and phone in other_business_index["phones"]:
        candidate_groups.append(other_business_index["phones"][phone])
    if full_name and full_name in other_business_index["names"]:
        candidate_groups.append(other_business_index["names"][full_name])
    if line_name and line_name in other_business_index["names"]:
        candidate_groups.append(other_business_index["names"][line_name])

    seen_keys: set[tuple[str, str, str, str, str, str]] = set()
    for candidates in candidate_groups:
        for evidence in candidates:
            dedupe_key = (
                evidence.date,
                evidence.email,
                evidence.phone,
                evidence.full_name,
                evidence.product_name,
                evidence.source_tab,
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            if other_business_evidence_matches_event(evidence, event_dt):
                return True
    return False


def build_skillplus_sale_indexes(payment_rows: list[list[str]], mapping: Dict[tuple[str, str], MappingEntry]) -> tuple[list[PaymentSaleEvent], dict[str, set[str]], Counter]:
    if not payment_rows:
        return [], {"emails": set(), "phones": set(), "names": set()}, Counter()
    headers = payment_rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    sale_events: list[PaymentSaleEvent] = []
    identifier_index = {"emails": set(), "phones": set(), "names": set()}
    source_counter = Counter()
    unknown_counter = Counter()
    seen_rows: set[tuple[str, ...]] = set()

    for row in payment_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        dedupe_key = payment_row_dedupe_key(padded)
        if dedupe_key in seen_rows:
            continue
        seen_rows.add(dedupe_key)
        source = normalize_text(padded[idx["参照システム"]])
        event = normalize_text(padded[idx["イベント"]])
        status = normalize_text(padded[idx["課金ステータス"]])
        if not source_sale_is_success(source, event, status):
            continue

        event_date = normalize_date(padded[idx["イベント日時"]])
        if not event_date:
            continue
        event_dt = parse_date(event_date)
        if not event_dt or event_dt < START_DATE:
            continue

        raw_name = normalize_text(padded[idx["商品名"]]) or "(空欄)"
        mapping_entry = mapping.get((source, raw_name))
        if not mapping_entry or mapping_entry.status != "変換済み":
            unknown_counter["amount"] += abs(parse_amount(padded[idx["イベント金額"]]))
            unknown_counter["count"] += 1
            continue
        if mapping_entry.business != BUSINESS_SKILLPLUS:
            continue

        amount = abs(parse_amount(padded[idx["イベント金額"]]))
        full_name = normalize_text(padded[idx["名前（原本）"]]) or normalize_text(
            f"{padded[idx['姓']]}{padded[idx['名']]}"
        )
        line_name = full_name
        sale_event = PaymentSaleEvent(
            date=event_date,
            amount=amount,
            email=normalize_email(padded[idx["メールアドレス"]]),
            full_name=normalize_name_key(full_name),
            line_name=normalize_name_key(line_name),
            phone=normalize_phone(padded[idx["電話番号"]]),
            product_name=mapping_entry.product_name,
            business=mapping_entry.business,
        )
        sale_events.append(sale_event)
        if sale_event.email:
            identifier_index["emails"].add(sale_event.email)
        if sale_event.phone:
            identifier_index["phones"].add(sale_event.phone)
        if sale_event.full_name:
            identifier_index["names"].add(sale_event.full_name)
        if sale_event.line_name:
            identifier_index["names"].add(sale_event.line_name)
        source_counter[source] += 1

    return sale_events, identifier_index, unknown_counter


def explicit_case_code_is_skillplus(code: str) -> Optional[bool]:
    normalized = normalize_text(code)
    if not normalized:
        return None
    if normalized in SKILLPLUS_CASE_CODES:
        return True
    if normalized in NON_SKILLPLUS_CASE_CODES:
        return False
    return None


def identifiers_hit_skillplus(email: str, phone: str, full_name: str, line_name: str, sale_index: dict[str, set[str]], student_index: dict[str, set[str]]) -> bool:
    if email and (email in sale_index["emails"] or email in student_index["emails"]):
        return True
    if phone and (phone in sale_index["phones"] or phone in student_index["phones"]):
        return True
    if full_name and (full_name in sale_index["names"] or full_name in student_index["names"]):
        return True
    if line_name and (line_name in sale_index["names"] or line_name in student_index["names"]):
        return True
    return False


def case_is_skillplus(
    *,
    explicit_code: str,
    text_blob: str,
    email: str,
    phone: str,
    full_name: str,
    line_name: str,
    event_dt: datetime | None,
    skillplus_markers: list[str],
    non_skillplus_markers: list[str],
    sale_index: dict[str, set[str]],
    student_index: dict[str, set[str]],
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> bool:
    explicit = explicit_case_code_is_skillplus(explicit_code)
    if explicit is not None:
        return explicit
    if text_contains_any_marker(text_blob, non_skillplus_markers):
        return False
    if text_contains_any_marker(text_blob, skillplus_markers):
        return True
    if identifiers_hit_other_business(
        email=email,
        phone=phone,
        full_name=full_name,
        line_name=line_name,
        event_dt=event_dt,
        other_business_index=other_business_index,
    ):
        return False
    return identifiers_hit_skillplus(email, phone, full_name, line_name, sale_index, student_index)


def collect_cs_refund_and_claims(
    cs_ss,
    sale_index: dict[str, set[str]],
    student_index: dict[str, set[str]],
    skillplus_markers: list[str],
    non_skillplus_markers: list[str],
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> tuple[dict[str, Counter], list[RefundCase], Counter]:
    tab_configs = [
        {
            "tab": "管理用_クーオフ・中途解約以外",
            "data_start_row": 3,
            "email_col": 8,
            "line_name_col": 7,
            "full_name_col": 6,
            "product_col": 9,
            "status_col": 5,
            "status_value": "完了",
            "amount_col": 15,
            "date_col": 1,
            "text_cols": [4, 14],
        },
        {
            "tab": "管理用_2025.1.25-クーオフ",
            "data_start_row": 3,
            "email_col": 10,
            "line_name_col": 9,
            "full_name_col": 8,
            "product_col": 7,
            "status_col": 6,
            "status_value": "完了",
            "amount_col": 19,
            "date_col": 23,
            "text_cols": [7, 26],
        },
        {
            "tab": "管理用_20250125-中途解約",
            "data_start_row": 3,
            "email_col": 10,
            "line_name_col": 9,
            "full_name_col": 8,
            "product_col": 7,
            "status_col": 6,
            "status_value": "完了",
            "amount_col": 23,
            "date_col": 27,
            "text_cols": [7, 32, 33, 34],
        },
    ]

    daily = defaultdict(Counter)
    refund_cases: list[RefundCase] = []
    stats = Counter()
    seen_claim_keys: set[tuple[str, ...]] = set()

    for cfg in tab_configs:
        ws = cs_ss.worksheet(cfg["tab"])
        rows = get_all_values_with_retry(ws)
        for sheet_row_number, row in enumerate(rows[cfg["data_start_row"] - 1 :], start=cfg["data_start_row"]):
            padded = row + [""] * max(0, 40 - len(row))
            status = normalize_text(padded[cfg["status_col"]])
            if status != cfg["status_value"]:
                continue

            amount = parse_amount(padded[cfg["amount_col"]])
            if amount == 0:
                continue

            event_date = normalize_date(padded[cfg["date_col"]]) or normalize_date(padded[1])
            event_dt = parse_date(event_date)
            if not event_dt or event_dt < START_DATE:
                continue

            email = normalize_email(padded[cfg["email_col"]])
            phone = normalize_phone("")
            full_name = normalize_name_key(padded[cfg["full_name_col"]])
            line_name = normalize_name_key(padded[cfg["line_name_col"]])
            explicit_code = normalize_text(padded[cfg["product_col"]])
            contract_date = normalize_date(padded[30])
            text_blob = " / ".join(normalize_text(padded[col]) for col in cfg["text_cols"])
            if not case_is_skillplus(
                explicit_code=explicit_code,
                text_blob=text_blob,
                email=email,
                phone=phone,
                full_name=full_name,
                line_name=line_name,
                event_dt=event_dt,
                skillplus_markers=skillplus_markers,
                non_skillplus_markers=non_skillplus_markers,
                sale_index=sale_index,
                student_index=student_index,
                other_business_index=other_business_index,
            ):
                continue

            if amount > 0:
                daily[event_date]["refund_amount"] += amount
                daily[event_date]["refund_count"] += 1
                refund_cases.append(
                    RefundCase(
                        date=event_date,
                        amount=amount,
                        email=email,
                        full_name=full_name,
                        line_name=line_name,
                        phone=phone,
                        source_tab=cfg["tab"],
                        sheet_row=sheet_row_number,
                    )
                )
                stats["refund_amount"] += amount
                stats["refund_count"] += 1
            else:
                if not claim_is_collected(padded[32], padded[33], padded[34]):
                    continue
                dedupe_key = claim_case_dedupe_key(
                    email=email,
                    full_name=full_name,
                    line_name=line_name,
                    explicit_code=explicit_code,
                    contract_date=contract_date,
                    amount=amount,
                )
                if dedupe_key in seen_claim_keys:
                    continue
                seen_claim_keys.add(dedupe_key)
                daily[event_date]["claim_amount"] += abs(amount)
                daily[event_date]["claim_count"] += 1
                stats["claim_amount"] += abs(amount)
                stats["claim_count"] += 1

    return daily, refund_cases, stats


def payment_refund_is_candidate(source: str, event: str, refund_date: str) -> bool:
    if source == "UnivaPay":
        return "返金" in event or bool(refund_date)
    if source == "MOSH":
        return bool(refund_date)
    return "返金" in event or bool(refund_date)


def raw_refund_matches_case(refund_case: RefundCase, *, email: str, phone: str, full_name: str, line_name: str, event_date: datetime) -> bool:
    start_date = parse_date(refund_case.date)
    if not start_date:
        return False
    if event_date < start_date - timedelta(days=REFUND_MATCH_LOOKBACK_DAYS):
        return False
    if event_date > start_date + timedelta(days=REFUND_MATCH_LOOKAHEAD_DAYS):
        return False

    if email and refund_case.email and email == refund_case.email:
        return True
    if full_name and refund_case.full_name and full_name == refund_case.full_name:
        return True
    if line_name and refund_case.line_name and line_name == refund_case.line_name:
        return True
    if phone and refund_case.phone and phone == refund_case.phone:
        return True
    return False


def build_refund_case_indexes(refund_cases: list[RefundCase]) -> dict[str, dict[str, list[RefundCase]]]:
    indexes = {"emails": defaultdict(list), "names": defaultdict(list), "phones": defaultdict(list)}
    for refund_case in refund_cases:
        if refund_case.email:
            indexes["emails"][refund_case.email].append(refund_case)
        if refund_case.full_name:
            indexes["names"][refund_case.full_name].append(refund_case)
        if refund_case.line_name and refund_case.line_name != refund_case.full_name:
            indexes["names"][refund_case.line_name].append(refund_case)
        if refund_case.phone:
            indexes["phones"][refund_case.phone].append(refund_case)
    return indexes


def collect_raw_refund_supplements(payment_rows: list[list[str]], mapping: Dict[tuple[str, str], MappingEntry], refund_cases: list[RefundCase], sale_index: dict[str, set[str]], student_index: dict[str, set[str]], skillplus_markers: list[str], non_skillplus_markers: list[str]) -> tuple[dict[str, Counter], Counter]:
    if not payment_rows:
        return defaultdict(Counter), Counter()

    headers = payment_rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    daily = defaultdict(Counter)
    stats = Counter()
    case_indexes = build_refund_case_indexes(refund_cases)
    seen_rows: set[tuple[str, ...]] = set()

    for row in payment_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        dedupe_key = payment_row_dedupe_key(padded)
        if dedupe_key in seen_rows:
            continue
        seen_rows.add(dedupe_key)
        source = normalize_text(padded[idx["参照システム"]])
        event = normalize_text(padded[idx["イベント"]])
        source_refund_date = normalize_date(padded[idx["返金日時"]])
        event_date_text = normalize_date(padded[idx["イベント日時"]])
        refund_date_text = source_refund_date or event_date_text
        refund_dt = parse_date(refund_date_text)
        if not refund_dt or refund_dt < START_DATE:
            continue
        if not payment_refund_is_candidate(source, event, source_refund_date):
            continue

        amount = abs(parse_amount(padded[idx["イベント金額"]]))
        if amount <= 0:
            continue

        raw_name = normalize_text(padded[idx["商品名"]]) or "(空欄)"
        mapping_entry = mapping.get((source, raw_name))
        email = normalize_email(padded[idx["メールアドレス"]])
        phone = normalize_phone(padded[idx["電話番号"]])
        full_name = normalize_name_key(
            normalize_text(padded[idx["名前（原本）"]]) or normalize_text(f"{padded[idx['姓']]}{padded[idx['名']]}")
        )
        line_name = full_name

        if not mapping_entry or mapping_entry.status != "変換済み":
            continue
        if mapping_entry.business != BUSINESS_SKILLPLUS:
            continue
        if not identifiers_hit_skillplus(email, phone, full_name, line_name, sale_index, student_index):
            continue

        candidate_cases: list[RefundCase] = []
        if email and email in case_indexes["emails"]:
            candidate_cases = case_indexes["emails"][email]
        elif full_name and full_name in case_indexes["names"]:
            candidate_cases = case_indexes["names"][full_name]
        elif line_name and line_name in case_indexes["names"]:
            candidate_cases = case_indexes["names"][line_name]
        elif phone and phone in case_indexes["phones"]:
            candidate_cases = case_indexes["phones"][phone]

        if any(
            raw_refund_matches_case(
                refund_case,
                email=email,
                phone=phone,
                full_name=full_name,
                line_name=line_name,
                event_date=refund_dt,
            )
            for refund_case in candidate_cases
        ):
            continue

        daily[refund_date_text]["refund_amount"] += amount
        daily[refund_date_text]["refund_count"] += 1
        stats["refund_amount"] += amount
        stats["refund_count"] += 1

    return daily, stats


def sale_matches_skillplus_student(row: list[str], idx: dict[str, int], student_index: dict[str, set[str]]) -> bool:
    email = normalize_email(row[idx["メールアドレス"]])
    phone = normalize_phone(row[idx["電話番号"]])
    full_name = normalize_name_key(
        normalize_text(row[idx["名前（原本）"]]) or normalize_text(f"{row[idx['姓']]}{row[idx['名']]}")
    )
    furigana = normalize_name_key(row[idx["フリガナ"]])
    if email and email in student_index["emails"]:
        return True
    if phone and phone in student_index["phones"]:
        return True
    if full_name and full_name in student_index["names"]:
        return True
    if furigana and furigana in student_index["names"]:
        return True
    return False


def sale_matches_other_business(
    row: list[str],
    idx: dict[str, int],
    event_dt: datetime | None,
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> bool:
    email = normalize_email(row[idx["メールアドレス"]])
    phone = normalize_phone(row[idx["電話番号"]])
    full_name = normalize_name_key(
        normalize_text(row[idx["名前（原本）"]]) or normalize_text(f"{row[idx['姓']]}{row[idx['名']]}")
    )
    return identifiers_hit_other_business(
        email=email,
        phone=phone,
        full_name=full_name,
        line_name=full_name,
        event_dt=event_dt,
        other_business_index=other_business_index,
    )


def build_sale_context(
    row: list[str],
    idx: dict[str, int],
    mapping: Dict[tuple[str, str], MappingEntry],
    student_index: dict[str, set[str]],
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> Optional[SaleContext]:
    source = normalize_text(row[idx["参照システム"]])
    event = normalize_text(row[idx["イベント"]])
    status = normalize_text(row[idx["課金ステータス"]])
    if not source_sale_is_success(source, event, status):
        return None

    event_date = normalize_date(row[idx["イベント日時"]])
    event_dt = parse_date(event_date)
    if not event_dt or event_dt < START_DATE:
        return None

    raw_name = normalize_text(row[idx["商品名"]]) or "(空欄)"
    if raw_name in PAYMENT_MAPPING_EXCLUDED_RAW_NAMES:
        classification = "excluded"
        return SaleContext(
            source=source,
            raw_name=raw_name,
            event_date=event_date,
            event_dt=event_dt,
            mapping_entry=None,
            classification=classification,
            is_blank_confirmed=False,
            is_univapay_head_payment=False,
            recurring_id=normalize_text(row[idx["定期課金ID"]]),
            charge_type=normalize_text(row[idx["課金タイプ"]]),
        )
    mapping_entry = mapping.get((source, raw_name))
    recurring_id = normalize_text(row[idx["定期課金ID"]])
    charge_type = normalize_text(row[idx["課金タイプ"]])
    classification = "unknown"
    is_blank_confirmed = False
    is_head_payment = False

    if mapping_entry and mapping_entry.status == "変換済み":
        classification = "included" if mapping_entry.business == BUSINESS_SKILLPLUS else "excluded"
    else:
        other_hit = raw_name == "(空欄)" and sale_matches_other_business(row, idx, event_dt, other_business_index)
        is_head_payment = source == "UnivaPay" and raw_name == "(空欄)" and is_univapay_head_payment(row[idx["メタデータ（JSON）"]])
        is_obvious_non_customer = raw_name == "(空欄)" and blank_sale_is_obvious_non_customer_transfer(row, idx, source)
        is_blank_confirmed = (
            raw_name == "(空欄)"
            and source in SKILLPLUS_BLANK_SOURCE_DEFAULT_SOURCES
            and not other_hit
            and not is_obvious_non_customer
        )
        if other_hit or is_obvious_non_customer:
            classification = "excluded"
        elif is_blank_confirmed or is_head_payment:
            classification = "included"

    return SaleContext(
        source=source,
        raw_name=raw_name,
        event_date=event_date,
        event_dt=event_dt,
        mapping_entry=mapping_entry,
        classification=classification,
        is_blank_confirmed=is_blank_confirmed,
        is_univapay_head_payment=is_head_payment,
        recurring_id=recurring_id,
        charge_type=charge_type,
    )


def sale_bucket(context: SaleContext, earliest_recurring_dates: dict[str, datetime]) -> str:
    if context.is_univapay_head_payment:
        return "new"

    mapping_entry = context.mapping_entry
    if charge_is_recurring(context.charge_type, context.recurring_id):
        return "recurring"

    if mapping_entry and "継続" in normalize_text(mapping_entry.product_name):
        return "recurring"

    if mapping_entry and mapping_entry.target == "会員向け":
        return "member_one_time"

    if context.raw_name == "(空欄)" and context.source in {"日本プラム", "CBS", "京都信販", "きらぼし銀行", "CREDIX", "INVOY"}:
        return "new"

    return "new"


def build_daily_rows(
    payment_rows: list[list[str]],
    mapping: Dict[tuple[str, str], MappingEntry],
    refund_daily: dict[str, Counter],
    refund_stats: Counter,
    claim_stats: Counter,
    student_index: dict[str, set[str]],
    other_business_index: dict[str, dict[str, list[OtherBusinessEvidence]]],
) -> tuple[List[List[object]], dict]:
    headers = payment_rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    daily = defaultdict(Counter)
    complete_unknown_amount = 0
    complete_unknown_count = 0
    sale_source_counts = Counter()
    earliest_recurring_dates: dict[str, datetime] = {}
    seen_rows: set[tuple[str, ...]] = set()

    contexts: list[tuple[list[str], SaleContext]] = []
    for row in payment_rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        dedupe_key = payment_row_dedupe_key(padded)
        if dedupe_key in seen_rows:
            continue
        seen_rows.add(dedupe_key)
        context = build_sale_context(padded, idx, mapping, student_index, other_business_index)
        if context is None:
            continue
        contexts.append((padded, context))
        if context.classification == "included" and context.recurring_id:
            current = earliest_recurring_dates.get(context.recurring_id)
            if current is None or context.event_dt < current:
                earliest_recurring_dates[context.recurring_id] = context.event_dt

    for padded, context in contexts:
        if context.classification == "excluded":
            continue
        if context.classification != "included":
            complete_unknown_amount += abs(parse_amount(padded[idx["イベント金額"]]))
            complete_unknown_count += 1
            continue

        amount = abs(parse_amount(padded[idx["イベント金額"]]))
        bucket = sale_bucket(context, earliest_recurring_dates)
        daily[context.event_date]["sales_amount"] += amount
        daily[context.event_date]["sales_count"] += 1
        if bucket == "new":
            daily[context.event_date]["new_sales_amount"] += amount
            daily[context.event_date]["new_sales_count"] += 1
        elif bucket == "recurring":
            daily[context.event_date]["recurring_sales_amount"] += amount
            daily[context.event_date]["recurring_sales_count"] += 1
        else:
            daily[context.event_date]["member_one_time_sales_amount"] += amount
            daily[context.event_date]["member_one_time_sales_count"] += 1
        sale_source_counts[context.source] += 1

    all_dates = set(daily.keys()) | set(refund_daily.keys())
    if not all_dates:
        rows = [[
            "日付",
            "新規着金売上",
            "継続課金売上",
            "会員向け単発売上",
            "着金売上",
            "返金額",
            "純着金売上",
            "解約請求回収額",
            "新規着金件数",
            "継続課金件数",
            "会員向け単発件数",
            "着金件数",
            "返金件数",
            "解約請求回収件数",
        ]]
        stats = {
            "new_sales_amount_total": 0,
            "recurring_sales_amount_total": 0,
            "member_one_time_sales_amount_total": 0,
            "sales_amount_total": 0,
            "refund_amount_total": 0,
            "net_sales_total": 0,
            "claim_amount_total": 0,
            "new_sales_count_total": 0,
            "recurring_sales_count_total": 0,
            "member_one_time_sales_count_total": 0,
            "sales_count_total": 0,
            "refund_count_total": 0,
            "claim_count_total": 0,
            "complete_unknown_amount": complete_unknown_amount,
            "complete_unknown_count": complete_unknown_count,
            "latest_date": "",
            "daily_row_count": 0,
            "source_row_count": 0,
            "sale_source_counts": dict(sale_source_counts),
            "supplement_refund_count": refund_stats.get("supplement_count", 0),
        }
        return rows, stats

    start_dt = START_DATE
    end_dt = max(parse_date(date_text) for date_text in all_dates if parse_date(date_text))
    rows = [[
        "日付",
        "新規着金売上",
        "継続課金売上",
        "会員向け単発売上",
        "着金売上",
        "返金額",
        "純着金売上",
        "解約請求回収額",
        "新規着金件数",
        "継続課金件数",
        "会員向け単発件数",
        "着金件数",
        "返金件数",
        "解約請求回収件数",
    ]]

    new_sales_amount_total = 0
    recurring_sales_amount_total = 0
    member_one_time_sales_amount_total = 0
    sales_amount_total = 0
    refund_amount_total = 0
    claim_amount_total = 0
    new_sales_count_total = 0
    recurring_sales_count_total = 0
    member_one_time_sales_count_total = 0
    sales_count_total = 0
    refund_count_total = 0
    claim_count_total = 0

    cursor = start_dt
    while cursor <= end_dt:
        date_text = cursor.strftime("%Y/%m/%d")
        new_sales_amount = daily[date_text]["new_sales_amount"]
        recurring_sales_amount = daily[date_text]["recurring_sales_amount"]
        member_one_time_sales_amount = daily[date_text]["member_one_time_sales_amount"]
        sales_amount = daily[date_text]["sales_amount"]
        refund_amount = refund_daily[date_text]["refund_amount"]
        claim_amount = refund_daily[date_text]["claim_amount"]
        new_sales_count = daily[date_text]["new_sales_count"]
        recurring_sales_count = daily[date_text]["recurring_sales_count"]
        member_one_time_sales_count = daily[date_text]["member_one_time_sales_count"]
        sales_count = daily[date_text]["sales_count"]
        refund_count = refund_daily[date_text]["refund_count"]
        claim_count = refund_daily[date_text]["claim_count"]
        rows.append([
            date_text,
            new_sales_amount,
            recurring_sales_amount,
            member_one_time_sales_amount,
            sales_amount,
            refund_amount,
            sales_amount - refund_amount,
            claim_amount,
            new_sales_count,
            recurring_sales_count,
            member_one_time_sales_count,
            sales_count,
            refund_count,
            claim_count,
        ])
        new_sales_amount_total += new_sales_amount
        recurring_sales_amount_total += recurring_sales_amount
        member_one_time_sales_amount_total += member_one_time_sales_amount
        sales_amount_total += sales_amount
        refund_amount_total += refund_amount
        claim_amount_total += claim_amount
        new_sales_count_total += new_sales_count
        recurring_sales_count_total += recurring_sales_count
        member_one_time_sales_count_total += member_one_time_sales_count
        sales_count_total += sales_count
        refund_count_total += refund_count
        claim_count_total += claim_count
        cursor += timedelta(days=1)

    stats = {
        "new_sales_amount_total": new_sales_amount_total,
        "recurring_sales_amount_total": recurring_sales_amount_total,
        "member_one_time_sales_amount_total": member_one_time_sales_amount_total,
        "sales_amount_total": sales_amount_total,
        "refund_amount_total": refund_amount_total,
        "net_sales_total": sales_amount_total - refund_amount_total,
        "claim_amount_total": claim_amount_total,
        "new_sales_count_total": new_sales_count_total,
        "recurring_sales_count_total": recurring_sales_count_total,
        "member_one_time_sales_count_total": member_one_time_sales_count_total,
        "sales_count_total": sales_count_total,
        "refund_count_total": refund_count_total,
        "claim_count_total": claim_count_total,
        "complete_unknown_amount": complete_unknown_amount,
        "complete_unknown_count": complete_unknown_count,
        "latest_date": end_dt.strftime("%Y/%m/%d"),
        "daily_row_count": len(rows) - 1,
        "source_row_count": len(payment_rows) - 1,
        "sale_source_counts": dict(sale_source_counts),
        "supplement_refund_count": refund_stats.get("supplement_count", 0),
    }
    return rows, stats


def build_summary_rows(stats: dict, checked_at: str) -> List[List[object]]:
    return [
        ["項目", "数値", "補足"],
        ["最終更新日時", checked_at, "このシートを最後に再生成した日時"],
        ["集計開始日", START_DATE_TEXT, "2025/01/01 以降だけを集計対象にする"],
        ["最新計上日", stats["latest_date"], "日別売上数値で最後に値を持つ日付"],
        ["累計新規着金売上", normalize_display_amount(stats["new_sales_amount_total"]), "広告判断やP/Lの基準にする新規契約の着金売上"],
        ["累計継続課金売上", normalize_display_amount(stats["recurring_sales_amount_total"]), "サブスク、月額継続、継続利用料などの継続課金"],
        ["累計会員向け単発売上", normalize_display_amount(stats["member_one_time_sales_amount_total"]), "会員向けイベント、追加販売、ツール協業などの単発売上"],
        ["累計着金売上", normalize_display_amount(stats["sales_amount_total"]), "新規着金売上 + 継続課金売上 + 会員向け単発売上"],
        ["累計返金額", normalize_display_amount(stats["refund_amount_total"]), "相談窓口シート案件正本 + raw 補完の返金合計"],
        ["累計純着金売上", normalize_display_amount(stats["net_sales_total"]), "着金売上 - 返金額"],
        ["累計解約請求回収額", normalize_display_amount(stats["claim_amount_total"]), "中途解約タブのうち回収済みと確認できた請求額"],
        ["累計新規着金件数", normalize_display_count(stats["new_sales_count_total"]), "新規契約として扱う着金件数"],
        ["累計継続課金件数", normalize_display_count(stats["recurring_sales_count_total"]), "継続課金として扱う着金件数"],
        ["累計会員向け単発件数", normalize_display_count(stats["member_one_time_sales_count_total"]), "会員向け単発売上として扱う着金件数"],
        ["累計着金件数", normalize_display_count(stats["sales_count_total"]), "新規着金件数 + 継続課金件数 + 会員向け単発件数"],
        ["累計返金件数", normalize_display_count(stats["refund_count_total"]), "返金案件数 + raw 補完件数"],
        ["累計解約請求回収件数", normalize_display_count(stats["claim_count_total"]), "回収済みと確認できた解約請求案件数"],
        ["完全不明金額", normalize_display_amount(stats["complete_unknown_amount"]), "スキルプラス事業と確定できず日別へ入れていない売上"],
        ["完全不明件数", normalize_display_count(stats["complete_unknown_count"]), "完全不明として除外した売上件数"],
    ]


def build_source_management_rows(payment_ws, mapping_ws, cs_ss, stats: dict, checked_at: str) -> List[List[object]]:
    payment_url = get_tab_url(PAYMENT_COLLECTION_SHEET_ID, payment_ws)
    mapping_url = get_tab_url(MASTER_SHEET_ID, mapping_ws)
    refund_ws = cs_ss.worksheet("管理用_2025.1.25-クーオフ")
    midterm_ws = cs_ss.worksheet("管理用_20250125-中途解約")
    status = "正常"
    if stats["complete_unknown_amount"] > 0:
        status = "要確認"

    rows = [
        ["加工タブ", "対象カラム", "優先度", "ソース元", "参照タブ", "参照列", "取得条件", "ステータス", "最終同期日", "更新数", "エラー数", "備考"],
        [
            DAILY_TAB_NAME,
            "新規着金売上 / 継続課金売上 / 会員向け単発売上 / 着金売上",
            "1",
            f'=HYPERLINK("{payment_url}","【アドネス株式会社】決済データ（収集）")',
            PAYMENT_COLLECTION_TAB,
            "イベント日時 / イベント金額 / 商品名 / 課金タイプ / 支払回数 / 定期課金ID",
            "成功売上のみ。非会員向け商品と頭金・信販・銀行振込の初回着金は新規、2回目以降の定期課金は継続課金、会員向け単発商品は会員向け単発売上へ分ける",
            status,
            f"'{checked_at}",
            stats["sales_count_total"],
            1 if status != "正常" else 0,
            "完全不明は日別に入れず売上サマリーで監視する。他事業成約リストは除外根拠として使う",
        ],
        [
            DAILY_TAB_NAME,
            "返金額 / 返金件数",
            "1",
            f'=HYPERLINK("{get_tab_url(CS_SHEET_ID, refund_ws)}","お客様相談窓口_進捗管理シート")',
            "管理用_クーオフ・中途解約以外 / 管理用_2025.1.25-クーオフ / 管理用_20250125-中途解約",
            "返金額 / 返金予定日 / 返金日",
            "相談窓口シートを案件正本にし、相談窓口にない raw 返金だけ補完採用する",
            "正常",
            f"'{checked_at}",
            stats["refund_count_total"],
            0,
            "一般返金 / クーオフ / 中途解約 の3タブを案件正本として見る",
        ],
        [
            DAILY_TAB_NAME,
            "解約請求回収額 / 解約請求回収件数",
            "1",
            f'=HYPERLINK("{get_tab_url(CS_SHEET_ID, midterm_ws)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "返金額/請求額 / 返金or支払い予定日",
            "中途解約タブの負値のうち、回収済みと確認できた請求だけを扱う",
            "正常",
            f"'{checked_at}",
            stats["claim_count_total"],
            0,
            "回収済みの請求だけを別列で持ち、通常売上へは混ぜない",
        ],
        [
            DAILY_TAB_NAME,
            "純着金売上",
            "1",
            "この加工シート",
            DAILY_TAB_NAME,
            "着金売上 / 返金額",
            "着金売上 - 返金額",
            "正常",
            f"'{checked_at}",
            stats["daily_row_count"],
            0,
            "解約請求回収額は別列で持つ",
        ],
        [
            DAILY_TAB_NAME,
            "商品分類",
            "1",
            f'=HYPERLINK("{mapping_url}","【アドネス株式会社】マスタデータ")',
            PAYMENT_MAPPING_TAB,
            "正式商品名 / 事業区分 / 対象顧客 / 顧客属性区分",
            "決済商品変換マスタで商品を正式商品へ寄せる",
            status,
            f"'{checked_at}",
            stats["source_row_count"],
            1 if status != "正常" else 0,
            f"スキルプラス受講生データ（元）を正の証拠にし、他事業成約リストを負の証拠にする。商品名空欄でも両条件を満たした銀行振込・信販売上だけを着金売上へ含める",
        ],
    ]
    return rows


def build_rule_rows() -> List[List[object]]:
    return [
        ["項目", "ルール", "補足"],
        ["日別売上数値", "手入力で直さず、元データから再生成する", "数字の理由を後から追えるようにする"],
        ["新規着金売上", "新規契約として扱う着金だけを集計する", "非会員向け商品、頭金お支払い、銀行振込・信販の初回承認/振込を含める"],
        ["継続課金売上", "月額課金や継続利用料など、積み上がる継続課金を集計する", "センサーズ 継続、AIカレッジ 継続、2回目以降の定期課金などをここへ寄せる"],
        ["会員向け単発売上", "会員向けの単発売上を継続課金とは分けて集計する", "イベント、追加販売、ツール協業などをここへ寄せる"],
        ["着金売上", "新規着金売上と継続課金売上と会員向け単発売上の合計を持つ", "総額は保持するが、広告判断では新規着金売上を優先して使う"],
        ["返金額", "相談窓口シートの返金案件を正本にする", "相談窓口に載っていない raw 返金だけを補完採用する"],
        ["返金件数", "返金イベント件数ではなく返金案件数で持つ", "分割返金でも1案件として扱う"],
        ["解約請求回収額", "中途解約タブの負値のうち、入金済み・振込済みなど回収済みと確認できた請求だけを持つ", "通常の着金売上には混ぜない"],
        ["日付", "実入出金日ではなく、確定日を使う", "着金売上はイベント日時、返金額は相談窓口上の確定日、解約請求回収額は回収済みと確認できた案件の日付を使う"],
        ["商品未特定", "銀行振込・信販の空欄成功売上は、受講生データ元タブでスキルプラス受講生と確認でき、かつ他事業成約リストと競合しないものだけ着金売上へ含める", "どのプランか不明でも、一次データ起点の根拠があるものだけ採用する"],
        ["頭金お支払い", "UnivaPay の空欄でもメタデータに `頭金お支払い` があるものはスキルプラス販売として新規着金売上へ入れる", "過去運用上 100% スキルプラス販売とみなす"],
        ["完全不明", "スキルプラス事業と確定できない売上は日別に入れない", "他事業成約リストと競合する売上、または一次データ根拠が弱い売上は売上サマリーでだけ監視する"],
        ["プラン不明", "スキルプラス事業とだけ言える売上は着金売上に含める", "商品別やプラン別に配賦できないものは内部的にプラン未特定として扱う"],
    ]


def load_run_state() -> Dict[str, int]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_run_state(stats: Dict[str, int]) -> None:
    payload = {
        "updated_at": stats["updated_at"],
        "metrics_start_date": START_DATE_TEXT,
        "new_sales_amount_total": stats["new_sales_amount_total"],
        "recurring_sales_amount_total": stats["recurring_sales_amount_total"],
        "member_one_time_sales_amount_total": stats["member_one_time_sales_amount_total"],
        "sales_amount_total": stats["sales_amount_total"],
        "refund_amount_total": stats["refund_amount_total"],
        "net_sales_total": stats["net_sales_total"],
        "claim_amount_total": stats["claim_amount_total"],
        "new_sales_count_total": stats["new_sales_count_total"],
        "recurring_sales_count_total": stats["recurring_sales_count_total"],
        "member_one_time_sales_count_total": stats["member_one_time_sales_count_total"],
        "sales_count_total": stats["sales_count_total"],
        "refund_count_total": stats["refund_count_total"],
        "claim_count_total": stats["claim_count_total"],
        "complete_unknown_amount": stats["complete_unknown_amount"],
        "complete_unknown_count": stats["complete_unknown_count"],
        "latest_date": stats["latest_date"],
        "daily_row_count": stats["daily_row_count"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def sync_payment_metrics_sheet(dry_run: bool = False) -> dict:
    with FileLock():
        gc = get_client()
        target = get_or_create_target_spreadsheet(gc)
        source = gc.open_by_key(PAYMENT_COLLECTION_SHEET_ID)
        master = gc.open_by_key(MASTER_SHEET_ID)
        cs_ss = gc.open_by_key(CS_SHEET_ID)
        student_ss = gc.open_by_key(SKILLPLUS_STUDENT_SHEET_ID)
        tabs = ensure_tabs(target)

        payment_ws = source.worksheet(PAYMENT_COLLECTION_TAB)
        mapping_ws = master.worksheet(PAYMENT_MAPPING_TAB)
        product_ws = master.worksheet(MASTER_PRODUCT_TAB)
        payment_rows = get_all_values_with_retry(payment_ws)
        mapping = load_payment_mapping(mapping_ws)
        skillplus_product_names, non_skillplus_product_names = load_product_business_map(product_ws)
        sale_events, sale_index, _ = build_skillplus_sale_indexes(payment_rows, mapping)
        student_index = load_skillplus_student_identifiers(student_ss)
        other_business_index = load_other_business_evidence(gc)
        skillplus_markers = build_text_markers(skillplus_product_names)
        non_skillplus_markers = build_text_markers(non_skillplus_product_names)

        refund_daily, refund_cases, refund_case_stats = collect_cs_refund_and_claims(
            cs_ss,
            sale_index=sale_index,
            student_index=student_index,
            skillplus_markers=skillplus_markers,
            non_skillplus_markers=non_skillplus_markers,
            other_business_index=other_business_index,
        )
        refund_supplement_daily, refund_supplement_stats = collect_raw_refund_supplements(
            payment_rows,
            mapping,
            refund_cases=refund_cases,
            sale_index=sale_index,
            student_index=student_index,
            skillplus_markers=skillplus_markers,
            non_skillplus_markers=non_skillplus_markers,
        )
        for date_text, counter in refund_supplement_daily.items():
            refund_daily[date_text]["refund_amount"] += counter["refund_amount"]
            refund_daily[date_text]["refund_count"] += counter["refund_count"]
        refund_case_stats["refund_amount"] += refund_supplement_stats["refund_amount"]
        refund_case_stats["refund_count"] += refund_supplement_stats["refund_count"]
        refund_case_stats["supplement_count"] = refund_supplement_stats["refund_count"]

        daily_rows, stats = build_daily_rows(
            payment_rows,
            mapping,
            refund_daily,
            refund_case_stats,
            refund_case_stats,
            student_index,
            other_business_index,
        )
        checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")
        stats["updated_at"] = checked_at

        summary_rows = build_summary_rows(stats, checked_at)
        source_rows = build_source_management_rows(payment_ws, mapping_ws, cs_ss, stats, checked_at)
        rule_rows = build_rule_rows()

        if dry_run:
            print("【dry-run】累計新規着金売上:", stats["new_sales_amount_total"])
            print("【dry-run】累計継続課金売上:", stats["recurring_sales_amount_total"])
            print("【dry-run】累計会員向け単発売上:", stats["member_one_time_sales_amount_total"])
            print("【dry-run】累計着金売上:", stats["sales_amount_total"])
            print("【dry-run】累計返金額:", stats["refund_amount_total"])
            print("【dry-run】累計純着金売上:", stats["net_sales_total"])
            print("【dry-run】累計解約請求回収額:", stats["claim_amount_total"])
            print("【dry-run】累計新規着金件数:", stats["new_sales_count_total"])
            print("【dry-run】累計継続課金件数:", stats["recurring_sales_count_total"])
            print("【dry-run】累計会員向け単発件数:", stats["member_one_time_sales_count_total"])
            print("【dry-run】完全不明金額:", stats["complete_unknown_amount"])
            print("【dry-run】完全不明件数:", stats["complete_unknown_count"])
            print("【dry-run】補完返金件数:", refund_case_stats.get("supplement_count", 0))
            print("【dry-run】対象日数:", stats["daily_row_count"])
            return stats

        write_rows(target, tabs[DAILY_TAB_NAME], daily_rows)
        style_daily_tab(target, tabs[DAILY_TAB_NAME])

        write_rows(target, tabs[SUMMARY_TAB_NAME], summary_rows)
        style_meta_tab(target, tabs[SUMMARY_TAB_NAME], widths=[180, 180, 420])

        write_rows(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows)
        style_meta_tab(
            target,
            tabs[SOURCE_MANAGEMENT_TAB_NAME],
            widths=[120, 140, 70, 220, 210, 180, 280, 90, 140, 90, 90, 280],
            center_cols=[2, 7],
            date_cols=[8],
            status_col=7,
            number_cols=[9, 10],
        )
        apply_status_cell_colors(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows, 7)

        write_rows(target, tabs[RULE_TAB_NAME], rule_rows)
        style_meta_tab(target, tabs[RULE_TAB_NAME], widths=[160, 500, 320])

        apply_protections(target, tabs)
        save_run_state(stats)
        print(f"{TARGET_SPREADSHEET_TITLE} を更新しました。")
        return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="スキルプラス着金データ（加工）を更新する")
    parser.add_argument("--dry-run", action="store_true", help="Sheets へ書き込まず集計だけ行う")
    args = parser.parse_args()
    sync_payment_metrics_sheet(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
