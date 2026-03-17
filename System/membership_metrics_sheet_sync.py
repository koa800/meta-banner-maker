#!/usr/bin/env python3
"""
【アドネス株式会社】会員データ（加工）を再生成する。

方針:
- 正本は `【アドネス株式会社】会員データ（収集） / 会員イベント`
- 日別で持つのは、契約 -> クーリングオフ -> 会員数 -> 中途解約 -> アクティブ会員
- `契約数` は「スキルプラスの契約書を締結したユーザー数」
- `クーリングオフ数` は「入金あり契約から7日以内に契約解除を申し出たユーザー数」
- `会員数` は「契約締結日から7日間が経過し、入金前契約解除でもクーリングオフでもない契約」の件数
- `中途解約数` は「サポート期間が終了する前に契約解除が確定した会員数」
- `アクティブ会員` は `会員数` の累計から `中途解約数` の累計を引いた残高
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from common_exclusion import CommonExclusionMaster
from gspread.exceptions import APIError
from sheets_manager import get_client


TARGET_SHEET_ID = "1OFKvyQsydPmTqd9MwSMX53MXxG9ASfkFquyf4PV-M8E"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】会員データ（加工）"
SOURCE_SHEET_ID = "1VwAO5rxib8pcR7KgGn-T3HKP7FaHqZmUhIBddo3okyw"
SOURCE_SPREADSHEET_TITLE = "【アドネス株式会社】会員データ（収集）"
SOURCE_TAB_NAME = "会員イベント"

DAILY_TAB_NAME = "日別会員数値"
SUMMARY_TAB_NAME = "会員サマリー"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    DAILY_TAB_NAME: (1200, 6),
    SUMMARY_TAB_NAME: (50, 3),
    SOURCE_MANAGEMENT_TAB_NAME: (80, 12),
    RULE_TAB_NAME: (50, 3),
}

STATE_PATH = Path(__file__).resolve().parent / "data" / "membership_metrics_sheet_state.json"
LOCK_PATH = Path(__file__).resolve().parent / "data" / "membership_metrics_sheet_sync.lock"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
TAB_COLORS = {
    DAILY_TAB_NAME: "#1A73E8",
    SUMMARY_TAB_NAME: "#FBBC04",
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}
STATUS_OPTIONS = ["正常", "未同期", "停止"]
STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "未同期": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
}
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "会員データ（加工）自動生成"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")


@dataclass
class DailyMembershipRecord:
    date: str
    contract_count: int
    cooling_off_count: int
    member_count: int
    mid_term_cancel_count: int
    active_member_count: int

    def to_row(self) -> List[object]:
        return [
            self.date,
            self.contract_count,
            self.cooling_off_count,
            self.member_count,
            self.mid_term_cancel_count,
            self.active_member_count,
        ]


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
                        f"会員データ（加工）の更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"membership_metrics_sheet_sync (PID: {os.getpid()})",
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


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def get_tab_url(spreadsheet_id: str, ws) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={ws.id}"


def normalize_date(raw: str) -> str:
    value = str(raw or "").strip()
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


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_email(value: object) -> str:
    return normalize_text(value).lower()


def normalize_phone(value: object) -> str:
    text = normalize_text(value)
    return re.sub(r"\D", "", text)


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
        "会員データ（加工）のシート名更新",
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
    batch_update_with_retry(spreadsheet, {"requests": requests}, "会員データ（加工）のタブ整列")
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
    widths = [120, 90, 110, 90, 100, 110]
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
                "wrapStrategy": "WRAP",
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
                "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat,numberFormat)",
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
                "wrapStrategy": "WRAP",
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
                {"horizontalAlignment": "RIGHT"},
                "userEnteredFormat.horizontalAlignment",
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
    for idx, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, idx, idx + 1, width))
    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の体裁適用")

    clear_validation_request = {
        "setDataValidation": {
            "range": {
                "sheetId": ws.id,
                "startRowIndex": 1,
                "endRowIndex": ws.row_count,
                "startColumnIndex": 0,
                "endColumnIndex": len(widths),
            },
            "rule": None,
        }
    }
    batch_update_with_retry(spreadsheet, {"requests": [clear_validation_request]}, f"{ws.title} の既存入力規則クリア")

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
        batch_update_with_retry(spreadsheet, {"requests": requests}, "会員データ（加工）の保護設定")


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
        "source_row_count": stats["source_row_count"],
        "contract_total": stats["contract_total"],
        "cooling_off_total": stats["cooling_off_total"],
        "member_total": stats["member_total"],
        "mid_term_total": stats["mid_term_total"],
        "active_latest": stats["active_latest"],
        "latest_date": stats["latest_date"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def detect_anomalies(stats: Dict[str, int], previous_state: Dict[str, int]) -> List[str]:
    anomalies: List[str] = []
    if stats["source_row_count"] <= 0:
        anomalies.append("会員イベントの行数が 0 です。")
    if stats["contract_total"] <= 0:
        anomalies.append("契約数の合計が 0 です。")
    if stats["member_total"] <= 0:
        anomalies.append("会員数の合計が 0 です。")
    if stats["daily_row_count"] <= 0:
        anomalies.append("日別会員数値を作れていません。")
    if stats["active_latest"] < 0:
        anomalies.append("アクティブ会員数が負になっています。")
    if stats["invalid_mid_term_count"] > 0:
        anomalies.append(f"会員化日より前の中途解約が {stats['invalid_mid_term_count']:,} 件あります。")

    prev_member_total = int(previous_state.get("member_total", 0) or 0)
    if prev_member_total:
        threshold = max(100, int(prev_member_total * 0.05))
        if prev_member_total - stats["member_total"] > threshold:
            anomalies.append(f"会員数の合計が前回より {prev_member_total - stats['member_total']:,} 件減っています。")

    return anomalies


def load_collection_rows() -> List[Dict[str, str]]:
    gc = get_client()
    source = gc.open_by_key(SOURCE_SHEET_ID)
    ws = source.worksheet(SOURCE_TAB_NAME)
    values = get_all_values_with_retry(ws)
    if not values:
        return []
    headers = [normalize_text(v) for v in values[0]]
    rows: List[Dict[str, str]] = []
    for raw in values[1:]:
        if not any(normalize_text(cell) for cell in raw):
            continue
        row = {headers[idx]: raw[idx] if idx < len(raw) else "" for idx in range(len(headers)) if headers[idx]}
        rows.append(row)
    return rows


def build_daily_rows(collection_rows: List[Dict[str, str]]) -> tuple[List[List[object]], Dict[str, int]]:
    exclusion_master = CommonExclusionMaster.load(force_refresh=True)
    contract_counts: Counter[str] = Counter()
    cooling_off_counts: Counter[str] = Counter()
    member_counts: Counter[str] = Counter()
    mid_term_counts: Counter[str] = Counter()

    valid_source_rows = 0
    excluded_rows = 0
    pre_payment_cancel_total = 0
    invalid_mid_term_count = 0
    ignored_mid_term_non_member_count = 0

    all_dates: List[datetime] = []

    for row in collection_rows:
        contract_date = normalize_date(row.get("契約締結日", ""))
        if not contract_date:
            continue

        email = normalize_email(row.get("メールアドレス", ""))
        phone = normalize_phone(row.get("電話番号", ""))
        name = normalize_text(row.get("名前", "")) or normalize_text(row.get("LINE名", ""))

        if exclusion_master.is_excluded(email=email, phone=phone, name=name, scope="会員", event_date=contract_date):
            excluded_rows += 1
            continue

        valid_source_rows += 1
        contract_counts[contract_date] += 1
        contract_dt = parse_date(contract_date)
        if contract_dt:
            all_dates.append(contract_dt)

        pre_payment_cancel = normalize_text(row.get("入金前契約解除", ""))
        cooling_off_date = normalize_date(row.get("クーリングオフ", ""))
        mid_term_cancel_date = normalize_date(row.get("中途解約", ""))

        if pre_payment_cancel:
            pre_payment_cancel_total += 1

        if cooling_off_date:
            cooling_off_counts[cooling_off_date] += 1
            cooling_dt = parse_date(cooling_off_date)
            if cooling_dt:
                all_dates.append(cooling_dt)

        member_date = ""
        if contract_dt and not pre_payment_cancel and not cooling_off_date:
            member_dt = contract_dt + timedelta(days=7)
            member_date = member_dt.strftime("%Y/%m/%d")
            member_counts[member_date] += 1
            all_dates.append(member_dt)

        if mid_term_cancel_date:
            cancel_dt = parse_date(mid_term_cancel_date)
            if member_date and cancel_dt and cancel_dt >= datetime.strptime(member_date, "%Y/%m/%d"):
                mid_term_counts[mid_term_cancel_date] += 1
                all_dates.append(cancel_dt)
            elif member_date:
                invalid_mid_term_count += 1
            else:
                ignored_mid_term_non_member_count += 1

    if not all_dates:
        return [[
            "日付", "契約数", "クーリングオフ数", "会員数", "中途解約数", "アクティブ会員"
        ]], {
            "source_row_count": 0,
            "excluded_row_count": excluded_rows,
            "contract_total": 0,
            "cooling_off_total": 0,
            "member_total": 0,
            "mid_term_total": 0,
            "active_latest": 0,
            "latest_date": "",
            "pre_payment_cancel_total": pre_payment_cancel_total,
            "invalid_mid_term_count": invalid_mid_term_count,
            "ignored_mid_term_non_member_count": ignored_mid_term_non_member_count,
            "daily_row_count": 0,
        }

    start_dt = min(all_dates)
    end_dt = max(all_dates)
    rows: List[List[object]] = [["日付", "契約数", "クーリングオフ数", "会員数", "中途解約数", "アクティブ会員"]]

    current_active = 0
    cursor = start_dt
    while cursor <= end_dt:
        date_text = cursor.strftime("%Y/%m/%d")
        contract = contract_counts.get(date_text, 0)
        cooling = cooling_off_counts.get(date_text, 0)
        member = member_counts.get(date_text, 0)
        mid_term = mid_term_counts.get(date_text, 0)
        current_active += member - mid_term
        rows.append(
            DailyMembershipRecord(
                date=date_text,
                contract_count=contract,
                cooling_off_count=cooling,
                member_count=member,
                mid_term_cancel_count=mid_term,
                active_member_count=current_active,
            ).to_row()
        )
        cursor += timedelta(days=1)

    stats = {
        "source_row_count": valid_source_rows,
        "excluded_row_count": excluded_rows,
        "contract_total": sum(contract_counts.values()),
        "cooling_off_total": sum(cooling_off_counts.values()),
        "member_total": sum(member_counts.values()),
        "mid_term_total": sum(mid_term_counts.values()),
        "active_latest": current_active,
        "latest_date": end_dt.strftime("%Y/%m/%d"),
        "pre_payment_cancel_total": pre_payment_cancel_total,
        "invalid_mid_term_count": invalid_mid_term_count,
        "ignored_mid_term_non_member_count": ignored_mid_term_non_member_count,
        "daily_row_count": len(rows) - 1,
    }
    return rows, stats


def build_summary_rows(stats: Dict[str, int], checked_at: str) -> List[List[object]]:
    return [
        ["項目", "数値", "補足"],
        ["契約数累計", stats["contract_total"], "スキルプラスの契約書を締結したユーザー数の累計"],
        ["クーリングオフ数累計", stats["cooling_off_total"], "入金あり契約から7日以内に契約解除を申し出たユーザー数の累計"],
        ["会員数累計", stats["member_total"], "契約締結日 + 7日で会員化した件数の累計"],
        ["中途解約数累計", stats["mid_term_total"], "サポート期間が終了する前に契約解除が確定した会員数の累計"],
        ["アクティブ会員数", stats["active_latest"], "会員数累計 - 中途解約数累計"],
        ["入金前契約解除数累計", stats["pre_payment_cancel_total"], "日別では持たず、会員化除外条件としてだけ使う"],
        ["会員化前として無視した中途解約数", stats["ignored_mid_term_non_member_count"], "入金前契約解除またはクーリングオフ済みのため、中途解約数に入れていない件数"],
        ["除外件数", stats["excluded_row_count"], "共通除外マスタと無条件除外で除外した件数"],
        ["最終同期日", checked_at, "データソース管理も同時更新"],
    ]


def build_source_management_rows(source_ws, checked_at: str, stats: Dict[str, int], anomalies: List[str]) -> List[List[object]]:
    source_url = get_tab_url(SOURCE_SHEET_ID, source_ws)
    status = "停止" if anomalies else ("正常" if stats["source_row_count"] > 0 else "未同期")
    error_count = len(anomalies)
    return [
        ["加工タブ", "対象カラム", "優先度", "ソース元", "参照タブ", "参照列", "取得条件", "ステータス", "最終同期日", "更新数", "エラー数", "備考"],
        [
            "日別会員数値",
            "契約数",
            "1",
            f'=HYPERLINK("{source_url}","{SOURCE_SPREADSHEET_TITLE}")',
            SOURCE_TAB_NAME,
            "契約締結日",
            "契約締結日がある行を日別件数にする",
            status,
            checked_at,
            stats["contract_total"],
            error_count,
            "スキルプラスの契約書を締結したユーザー数",
        ],
        [
            "日別会員数値",
            "クーリングオフ数",
            "1",
            f'=HYPERLINK("{source_url}","{SOURCE_SPREADSHEET_TITLE}")',
            SOURCE_TAB_NAME,
            "クーリングオフ",
            "クーリングオフ日がある行を日別件数にする",
            status,
            checked_at,
            stats["cooling_off_total"],
            error_count,
            "入金あり契約から7日以内に契約解除を申し出たユーザー数",
        ],
        [
            "日別会員数値",
            "会員数",
            "1",
            f'=HYPERLINK("{source_url}","{SOURCE_SPREADSHEET_TITLE}")',
            SOURCE_TAB_NAME,
            "契約締結日 / 入金前契約解除 / クーリングオフ",
            "契約締結日 + 7日、かつ入金前契約解除とクーリングオフが無い行を会員化する",
            status,
            checked_at,
            stats["member_total"],
            error_count,
            "会員数と入会数は同義として扱う",
        ],
        [
            "日別会員数値",
            "中途解約数",
            "1",
            f'=HYPERLINK("{source_url}","{SOURCE_SPREADSHEET_TITLE}")',
            SOURCE_TAB_NAME,
            "中途解約",
            "中途解約日があり、会員化後のものだけを日別件数にする",
            status,
            checked_at,
            stats["mid_term_total"],
            error_count,
            f"サポート期間が終了する前に契約解除が確定した会員数。入金前契約解除またはクーリングオフ済みの中途解約 {stats['ignored_mid_term_non_member_count']:,} 件は無視",
        ],
        [
            "日別会員数値",
            "アクティブ会員",
            "1",
            f'=HYPERLINK("{source_url}","{SOURCE_SPREADSHEET_TITLE}")',
            SOURCE_TAB_NAME,
            "会員数 / 中途解約",
            "会員数の累計から中途解約数の累計を引いた残高",
            status,
            checked_at,
            stats["active_latest"],
            error_count,
            "負の値になった場合は停止する",
        ],
    ]


def build_rule_rows() -> List[List[object]]:
    return [
        ["項目", "ルール", "補足"],
        ["日別会員数値", "会員イベントを正本にして再生成する。手入力での修正はしない", "壊れた値で上書きしない"],
        ["契約数", "契約締結日がある件数をその日の日別契約数とする", "スキルプラスの契約書を締結したユーザー数"],
        ["クーリングオフ数", "クーリングオフ日がある件数をその日の日別クーリングオフ数とする", "入金あり契約から7日以内に契約解除を申し出たユーザー数。お客様相談窓口_進捗管理シートの収集結果をそのまま使う"],
        ["会員数", "契約締結日 + 7日 を会員日とし、入金前契約解除とクーリングオフが無い契約だけを会員化する", "入会数と会員数は同義として扱う"],
        ["中途解約数", "中途解約日があり、会員化後のものだけをその日の日別中途解約数とする", "入金前契約解除またはクーリングオフ済みの行にある中途解約は無視する"],
        ["アクティブ会員", "会員数の累計から中途解約数の累計を引いた残高で持つ", "クーリングオフは会員化前に除外されるためここでは引かない"],
        ["入金前契約解除", "日別数値には持たず、会員化除外条件としてだけ使う", "会員サマリーでは累計を表示する"],
        ["共通除外", "【アドネス株式会社】共通除外マスタ を参照し、追加日以降の新規イベントだけ除外する", "過去データは遡って消さない"],
        ["無条件除外", "test / テスト / sample / サンプル / dummy などの明らかなテストデータは除外する", "会員イベント収集側と同じルールを使う"],
        ["異常時の扱い", "元データ 0件、会員数 0件、アクティブ会員が負、会員化日より前の中途解約が発生した場合は停止する", "入金前契約解除やクーリングオフ済みの行にある中途解約は停止理由にしない"],
    ]


def main(dry_run: bool = False) -> None:
    with FileLock():
        gc = get_client()
        target = gc.open_by_key(TARGET_SHEET_ID)
        source = gc.open_by_key(SOURCE_SHEET_ID)
        ensure_spreadsheet_title(target)
        tabs = ensure_tabs(target)
        source_ws = source.worksheet(SOURCE_TAB_NAME)

        source_values = get_all_values_with_retry(source_ws)
        if not source_values:
            raise RuntimeError("会員イベントを読み取れません。")
        headers = [normalize_text(v) for v in source_values[0]]
        collection_rows = []
        for raw in source_values[1:]:
            if not any(normalize_text(cell) for cell in raw):
                continue
            row = {headers[idx]: raw[idx] if idx < len(raw) else "" for idx in range(len(headers)) if headers[idx]}
            collection_rows.append(row)

        daily_rows, stats = build_daily_rows(collection_rows)
        checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")
        stats["updated_at"] = checked_at

        previous_state = load_run_state()
        anomalies = detect_anomalies(stats, previous_state)
        if anomalies and not dry_run:
            raise RuntimeError(" / ".join(anomalies))

        summary_rows = build_summary_rows(stats, checked_at)
        source_rows = build_source_management_rows(source_ws, checked_at, stats, anomalies)
        rule_rows = build_rule_rows()

        if dry_run:
            print("【dry-run】会員数累計:", stats["member_total"])
            print("【dry-run】アクティブ会員:", stats["active_latest"])
            print("【dry-run】契約数累計:", stats["contract_total"])
            print("【dry-run】クーリングオフ数累計:", stats["cooling_off_total"])
            print("【dry-run】中途解約数累計:", stats["mid_term_total"])
            print("【dry-run】会員イベント対象行:", stats["source_row_count"])
            print("【dry-run】除外件数:", stats["excluded_row_count"])
            if anomalies:
                print("【dry-run】異常:", " / ".join(anomalies))
            return

        write_rows(target, tabs[DAILY_TAB_NAME], daily_rows)
        style_daily_tab(target, tabs[DAILY_TAB_NAME])

        write_rows(target, tabs[SUMMARY_TAB_NAME], summary_rows)
        style_meta_tab(target, tabs[SUMMARY_TAB_NAME], widths=[180, 120, 340], date_cols=[1], number_cols=[1])

        write_rows(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows)
        style_meta_tab(
            target,
            tabs[SOURCE_MANAGEMENT_TAB_NAME],
            widths=[120, 120, 70, 220, 160, 170, 260, 90, 140, 90, 90, 280],
            center_cols=[2, 7],
            date_cols=[8],
            status_col=7,
            number_cols=[9, 10],
        )
        apply_status_cell_colors(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows, 7)

        write_rows(target, tabs[RULE_TAB_NAME], rule_rows)
        style_meta_tab(target, tabs[RULE_TAB_NAME], widths=[160, 480, 330])

        apply_protections(target, tabs)
        save_run_state(stats)
        print("【アドネス株式会社】会員データ（加工）を更新しました。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="会員データ（加工）を更新する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みを行わず件数だけ確認する")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
