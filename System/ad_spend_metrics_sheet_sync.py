#!/usr/bin/env python3
"""
【アドネス株式会社】広告費データ（加工）を再生成する。

方針:
- 正本は `【アドネス全体】数値管理シート / スキルプラス（日別）` の `カテゴリ=広告` 行
- col8（広告費）を日別で集計し、媒体別の内訳も持つ
- データ範囲: 2025-07-01 ~ 最新（数値管理シートに依存）
- KPIダッシュボードの `広告費` 列に接続するための加工シート
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

from gspread.exceptions import APIError
from sheets_manager import get_client


# --- スプレッドシート定義 ---

TARGET_SHEET_ID = "1-dEYsY6KB0GF2XRf7PvoxVxhICCamdCBPKxHJRJdUOE"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】広告費データ（加工）"

SOURCE_SHEET_ID = "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
SOURCE_SPREADSHEET_TITLE = "【アドネス全体】数値管理シート"
SOURCE_TAB_NAME = "スキルプラス（日別）"

# --- タブ定義 ---

DAILY_TAB_NAME = "日別広告費"
MEDIA_TAB_NAME = "媒体別広告費"
SUMMARY_TAB_NAME = "広告費サマリー"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    DAILY_TAB_NAME: (600, 3),
    MEDIA_TAB_NAME: (3000, 3),
    SUMMARY_TAB_NAME: (50, 3),
    SOURCE_MANAGEMENT_TAB_NAME: (60, 12),
    RULE_TAB_NAME: (50, 3),
}

# --- パス定義 ---

STATE_PATH = Path(__file__).resolve().parent / "data" / "ad_spend_metrics_sheet_state.json"
LOCK_PATH = Path(__file__).resolve().parent / "data" / "ad_spend_metrics_sheet_sync.lock"

# --- 書式定義 ---

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
TAB_COLORS = {
    DAILY_TAB_NAME: "#1A73E8",
    MEDIA_TAB_NAME: "#1A73E8",
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
PROTECTION_PREFIX = "広告費データ（加工）自動生成"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)

# --- データ集計設定 ---

SOURCE_CATEGORY = "広告"
AD_SPEND_COL_INDEX = 8  # col8 = 広告費（¥形式）
MEDIA_COL_INDEX = 2     # col2 = 媒体
FUNNEL_COL_INDEX = 3    # col3 = ファネル
DATE_COL_INDEX = 0      # col0 = 日付
CATEGORY_COL_INDEX = 1  # col1 = カテゴリ

DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
YEN_RE = re.compile(r"[¥￥,\s]")

# 広告媒体の正規化マッピング
MEDIA_NORMALIZE = {
    "Meta広告": "Meta広告",
    "TikTok広告": "TikTok広告",
    "X広告": "X広告",
    "YouTube広告": "YouTube広告",
    "LINE広告": "LINE広告",
    "リスティング広告": "リスティング広告",
    "Yahoo!リスティング広告": "Yahoo!広告",
    "Yahoo!ディスプレイ広告": "Yahoo!広告",
    "Yahoo!広告": "Yahoo!広告",
    "ディスプレイ広告": "ディスプレイ広告",
    "アフィリエイト広告": "アフィリエイト広告",
    "オフライン広告": "オフライン広告",
}


# ============================================================
# ユーティリティ
# ============================================================


class FileLock:
    def __init__(self, lock_path: Path = LOCK_PATH, timeout_seconds: int = 1800):
        self.lock_path = Path(lock_path)
        self.timeout_seconds = timeout_seconds

    @staticmethod
    def _extract_pid(lock_data: dict) -> int | None:
        locked_by = str(lock_data.get("locked_by", ""))
        match = re.search(r"PID:\s*(\d+)", locked_by)
        if not match:
            return None
        try:
            return int(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _pid_is_running(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                lock_data = json.loads(self.lock_path.read_text())
                locked_at = datetime.fromisoformat(lock_data.get("locked_at", ""))
                elapsed = (datetime.now() - locked_at).total_seconds()
                locked_pid = self._extract_pid(lock_data)
                if locked_pid and not self._pid_is_running(locked_pid):
                    self.lock_path.unlink(missing_ok=True)
                elif elapsed < self.timeout_seconds:
                    raise RuntimeError(
                        f"広告費データ（加工）の更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"ad_spend_metrics_sheet_sync (PID: {os.getpid()})",
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


def normalize_date(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    match = DATE_RE.search(value)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def parse_yen(raw: str) -> float:
    """¥形式の金額をfloatに変換。例: '¥2,724,841' -> 2724841.0"""
    text = str(raw or "").strip()
    if not text:
        return 0.0
    cleaned = YEN_RE.sub("", text)
    if not cleaned or cleaned == "-":
        return 0.0
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


TRANSIENT_SHEETS_STATUS_CODES = {429, 500, 502, 503, 504}
TRANSIENT_SHEETS_ERROR_MARKERS = (
    "quota exceeded",
    "resource_exhausted",
    "service is currently unavailable",
    "backend error",
    "internal error",
    "try again later",
)


def is_retryable_sheets_error(exc: APIError) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in TRANSIENT_SHEETS_STATUS_CODES:
        return True
    return any(marker in str(exc).lower() for marker in TRANSIENT_SHEETS_ERROR_MARKERS)


def is_retryable_sheets_message(message: str) -> bool:
    normalized = str(message).lower()
    if any(code in normalized for code in ("429", "500", "502", "503", "504")):
        return True
    return any(marker in normalized for marker in TRANSIENT_SHEETS_ERROR_MARKERS)


def run_read_with_retry(description: str, func):
    last_error = None
    waits = (0, 5, 10, 20, 40)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except Exception as exc:
            if not is_retryable_sheets_message(str(exc)) or attempt == len(waits):
                raise
            last_error = exc
            print(f"{description}: Sheets の一時エラーのため再試行します。")
    if last_error:
        raise last_error


def run_write_with_retry(description: str, func):
    last_error = None
    waits = (0, *WRITE_RETRY_SECONDS)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except APIError as exc:
            if not is_retryable_sheets_error(exc) or attempt == len(waits):
                raise
            last_error = exc
            print(f"{description}: Sheets の一時エラーのため再試行します。")
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
            if not is_retryable_sheets_message(message) or attempt == 3:
                raise
            wait_seconds = 65 * (attempt + 1)
            print(f"読み取り一時エラー: {ws.title} を {wait_seconds} 秒待って再試行")
            time.sleep(wait_seconds)
    return []


# ============================================================
# タブ管理
# ============================================================


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
        "広告費データ（加工）のシート名更新",
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
    ordered_names = [DAILY_TAB_NAME, MEDIA_TAB_NAME, SUMMARY_TAB_NAME, SOURCE_MANAGEMENT_TAB_NAME, RULE_TAB_NAME]
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
    batch_update_with_retry(spreadsheet, {"requests": requests}, "広告費データ（加工）のタブ整列")
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


# ============================================================
# 書式適用
# ============================================================


def style_daily_tab(spreadsheet, ws) -> None:
    widths = [130, 150, 180]
    requests = [
        repeat_cell_request(
            ws.id, 0, 1, 0, len(widths),
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
            ws.id, 1, ws.row_count, 0, len(widths),
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
            ws.id, 1, ws.row_count, 0, 1,
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


def style_media_tab(spreadsheet, ws) -> None:
    widths = [130, 180, 150]
    requests = [
        repeat_cell_request(
            ws.id, 0, 1, 0, len(widths),
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
            ws.id, 1, ws.row_count, 0, len(widths),
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
            ws.id, 1, ws.row_count, 0, 1,
            {
                "horizontalAlignment": "LEFT",
                "numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"},
            },
            "userEnteredFormat(horizontalAlignment,numberFormat)",
        ),
        repeat_cell_request(
            ws.id, 1, ws.row_count, 1, 2,
            {"horizontalAlignment": "LEFT"},
            "userEnteredFormat.horizontalAlignment",
        ),
        repeat_cell_request(
            ws.id, 1, ws.row_count, 2, 3,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
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
            ws.id, 0, 1, 0, len(widths),
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
            ws.id, 1, ws.row_count, 0, len(widths),
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
                ws.id, 1, ws.row_count, idx, idx + 1,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    for idx in number_cols:
        requests.append(
            repeat_cell_request(
                ws.id, 1, ws.row_count, idx, idx + 1,
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
                row_index, row_index + 1,
                status_col_index, status_col_index + 1,
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

    metadata = spreadsheet.fetch_sheet_metadata({"fields": "sheets.protectedRanges"})
    existing = []
    for sheet in metadata.get("sheets", []):
        for pr in sheet.get("protectedRanges", []):
            if pr.get("description", "").startswith(PROTECTION_PREFIX):
                existing.append(pr["protectedRangeId"])

    requests = []
    for pr_id in existing:
        requests.append({"deleteProtectedRange": {"protectedRangeId": pr_id}})
    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, "既存保護の削除")

    requests = []
    for name in protected_names:
        ws = tabs[name]
        requests.append({
            "addProtectedRange": {
                "protectedRange": {
                    "range": {"sheetId": ws.id},
                    "description": f"{PROTECTION_PREFIX}: {name}",
                    "editors": {"users": PROTECTED_EDITOR_EMAILS},
                }
            }
        })
    batch_update_with_retry(spreadsheet, {"requests": requests}, "保護の適用")


# ============================================================
# データ読み込み・集計
# ============================================================


def load_source_data(gc) -> List[List[str]]:
    """数値管理シートから日別データを読み込む"""
    print(f"ソース読み込み: {SOURCE_SPREADSHEET_TITLE} / {SOURCE_TAB_NAME}")
    source_sh = run_read_with_retry("広告費ソースシート取得", lambda: gc.open_by_key(SOURCE_SHEET_ID))
    source_ws = run_read_with_retry(f"{SOURCE_TAB_NAME} 取得", lambda: source_sh.worksheet(SOURCE_TAB_NAME))
    rows = get_all_values_with_retry(source_ws)
    print(f"  読み込み行数: {len(rows)}")
    return rows


def normalize_media(raw_media: str) -> str:
    """媒体名を正規化する"""
    media = str(raw_media or "").strip()
    return MEDIA_NORMALIZE.get(media, media)


def aggregate_ad_spend(source_rows: List[List[str]]) -> tuple:
    """
    ソースデータから広告費を集計する。

    Returns:
        (daily_totals, media_daily, media_set)
        daily_totals: {date: total_spend}
        media_daily: {date: {media: spend}}
        media_set: set of media names
    """
    daily_totals: Dict[str, float] = defaultdict(float)
    media_daily: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))
    media_set: set = set()
    skipped = 0

    for row in source_rows:
        if len(row) <= AD_SPEND_COL_INDEX:
            continue

        category = str(row[CATEGORY_COL_INDEX]).strip()
        if category != SOURCE_CATEGORY:
            continue

        date_str = normalize_date(row[DATE_COL_INDEX])
        if not date_str:
            skipped += 1
            continue

        spend = parse_yen(row[AD_SPEND_COL_INDEX])
        media = normalize_media(row[MEDIA_COL_INDEX])

        daily_totals[date_str] += spend
        media_daily[date_str][media] += spend
        if media:
            media_set.add(media)

    print(f"  広告行数: {sum(1 for _ in daily_totals)} 日分 (スキップ: {skipped})")
    return dict(daily_totals), dict(media_daily), media_set


# ============================================================
# 異常検知
# ============================================================


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {}


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def detect_anomalies(daily_totals: Dict[str, float], prev_state: dict) -> List[str]:
    anomalies = []

    if not daily_totals:
        anomalies.append("広告費データが0件です")
        return anomalies

    total_spend = sum(daily_totals.values())
    if total_spend <= 0:
        anomalies.append("広告費の合計が0円です")

    prev_day_count = prev_state.get("day_count", 0)
    if prev_day_count > 0:
        current_count = len(daily_totals)
        decrease_pct = (prev_day_count - current_count) / prev_day_count * 100
        if decrease_pct > 5:
            anomalies.append(
                f"集計日数が急減しています: {prev_day_count} -> {current_count} ({decrease_pct:.1f}%減)"
            )

    prev_total = prev_state.get("total_spend", 0)
    if prev_total > 0:
        decrease_pct = (prev_total - total_spend) / prev_total * 100
        if decrease_pct > 10:
            anomalies.append(
                f"広告費合計が急減しています: ¥{prev_total:,.0f} -> ¥{total_spend:,.0f} ({decrease_pct:.1f}%減)"
            )

    return anomalies


# ============================================================
# タブデータ生成
# ============================================================


def build_daily_rows(daily_totals: Dict[str, float]) -> List[List[object]]:
    """日別広告費タブのデータ行を生成"""
    header = ["日付", "広告費", "累計広告費"]
    sorted_dates = sorted(daily_totals.keys())

    rows = [header]
    cumulative = 0
    for date_str in sorted_dates:
        spend = daily_totals[date_str]
        cumulative += spend
        rows.append([date_str, int(round(spend)), int(round(cumulative))])

    return rows


def build_media_rows(media_daily: Dict[str, Dict[str, float]]) -> List[List[object]]:
    """媒体別広告費タブのデータ行を生成"""
    header = ["日付", "媒体", "広告費"]
    sorted_dates = sorted(media_daily.keys())

    rows = [header]
    for date_str in sorted_dates:
        media_spends = media_daily[date_str]
        for media in sorted(media_spends.keys()):
            spend = media_spends[media]
            if spend != 0:
                rows.append([date_str, media, int(round(spend))])

    return rows


def build_summary_rows(daily_totals: Dict[str, float], media_set: set) -> List[List[object]]:
    """広告費サマリータブのデータ行を生成"""
    header = ["項目", "値"]
    sorted_dates = sorted(daily_totals.keys())
    total_spend = sum(daily_totals.values())
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")

    rows = [
        header,
        ["更新日時", now_str],
        ["広告費合計", f"¥{int(round(total_spend)):,}"],
        ["集計日数", len(sorted_dates)],
        ["集計開始日", sorted_dates[0] if sorted_dates else ""],
        ["最新集計日", sorted_dates[-1] if sorted_dates else ""],
        ["媒体数", len(media_set)],
        ["媒体一覧", " / ".join(sorted(media_set))],
    ]
    return rows


def build_source_management_rows(daily_totals: Dict[str, float], anomalies: List[str]) -> List[List[object]]:
    """データソース管理タブのデータ行を生成"""
    header = [
        "KPI項目", "ソース名", "優先度", "スプレッドシート",
        "参照タブ", "参照列", "集計ルール", "入力条件",
        "ステータス", "最終同期日", "更新数", "備考",
    ]
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    sorted_dates = sorted(daily_totals.keys())

    status = "正常"
    notes = ""
    if anomalies:
        status = "停止"
        notes = " / ".join(anomalies)

    source_url = f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{SOURCE_SHEET_ID}/edit", "{SOURCE_SPREADSHEET_TITLE}")'

    rows = [
        header,
        [
            "広告費",
            SOURCE_SPREADSHEET_TITLE,
            "1",
            source_url,
            SOURCE_TAB_NAME,
            "col8（広告費）",
            "カテゴリ=広告 の行を日別集計",
            "¥形式を数値変換、0円含む",
            status,
            now_str,
            len(sorted_dates),
            notes,
        ],
    ]
    return rows


def build_rule_rows() -> List[List[object]]:
    """データ追加ルールタブのデータ行を生成"""
    header = ["項目", "ルール", "補足"]
    rules = [
        header,
        ["正本", f"【アドネス全体】数値管理シート / {SOURCE_TAB_NAME}", "カテゴリ=広告 の行の col8（広告費）を使う"],
        ["集計方法", "毎回全日分を再計算する再生成型", "差分更新ではなく全量置き換え"],
        ["日別広告費", "日付ごとに全媒体・全ファネルの広告費を合算", "¥形式を数値に変換して加算"],
        ["媒体別広告費", "日付×媒体で広告費を集計", "類似媒体名は正規化して統合（例: Yahoo!リスティング→Yahoo!広告）"],
        ["累計広告費", "日付を昇順に並べ、当日までの広告費を積み上げ", ""],
        ["データ範囲", "数値管理シートにデータがある日付のみ", "現在 2025/07/01 開始。将来 API で補完可能"],
        ["手編集禁止", "5タブすべて自動生成。手で値を書き換えない", ""],
        ["異常検知", "広告行0件 / 日数急減5%超 / 合計金額急減10%超で停止", "データソース管理のステータスに反映"],
        ["更新頻度", "Orchestrator で 2時間ごとに再生成", ""],
        ["除外", "共通除外マスタは不要（広告費はメールアドレス単位のデータではない）", ""],
    ]
    return rules


# ============================================================
# メイン処理
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="広告費データ（加工）を再生成する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなしで集計結果だけ表示")
    parser.add_argument("--force-write-on-anomaly", action="store_true", help="異常検知時も書き込みを強行")
    args = parser.parse_args()

    gc = get_client("kohara")

    # 1. ソースデータ読み込み
    source_rows = load_source_data(gc)

    # 2. 広告費集計
    daily_totals, media_daily, media_set = aggregate_ad_spend(source_rows)

    if not daily_totals:
        print("広告費データが0件のため終了します。")
        return

    sorted_dates = sorted(daily_totals.keys())
    total_spend = sum(daily_totals.values())
    print(f"\n集計結果:")
    print(f"  日付範囲: {sorted_dates[0]} ~ {sorted_dates[-1]}")
    print(f"  集計日数: {len(sorted_dates)}")
    print(f"  広告費合計: ¥{int(round(total_spend)):,}")
    print(f"  媒体数: {len(media_set)}")
    print(f"  媒体一覧: {', '.join(sorted(media_set))}")

    # 3. 異常検知
    prev_state = load_state()
    anomalies = detect_anomalies(daily_totals, prev_state)
    if anomalies:
        print(f"\n異常検知:")
        for a in anomalies:
            print(f"  - {a}")
        if not args.force_write_on_anomaly and not args.dry_run:
            print("書き込みを中止します。--force-write-on-anomaly で強行できます。")
            return

    if args.dry_run:
        print("\n--dry-run: 書き込みをスキップします。")
        # サンプル表示
        print("\n日別広告費（直近5日）:")
        for d in sorted_dates[-5:]:
            print(f"  {d}: ¥{int(round(daily_totals[d])):,}")
        return

    # 4. ロック取得
    with FileLock():
        print("\nロック取得")

        # 5. ターゲットシート準備
        target_sh = gc.open_by_key(TARGET_SHEET_ID)
        ensure_spreadsheet_title(target_sh)
        tabs = ensure_tabs(target_sh)
        print("タブ準備完了")

        # 6. データ行生成
        daily_rows = build_daily_rows(daily_totals)
        media_rows = build_media_rows(media_daily)
        summary_rows = build_summary_rows(daily_totals, media_set)
        source_mgmt_rows = build_source_management_rows(daily_totals, anomalies)
        rule_rows = build_rule_rows()

        # 7. 書き込み
        print("書き込み開始...")
        write_rows(target_sh, tabs[DAILY_TAB_NAME], daily_rows)
        print(f"  {DAILY_TAB_NAME}: {len(daily_rows) - 1} 行")

        write_rows(target_sh, tabs[MEDIA_TAB_NAME], media_rows)
        print(f"  {MEDIA_TAB_NAME}: {len(media_rows) - 1} 行")

        write_rows(target_sh, tabs[SUMMARY_TAB_NAME], summary_rows)
        print(f"  {SUMMARY_TAB_NAME}: {len(summary_rows) - 1} 行")

        write_rows(target_sh, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_mgmt_rows)
        print(f"  {SOURCE_MANAGEMENT_TAB_NAME}: {len(source_mgmt_rows) - 1} 行")

        write_rows(target_sh, tabs[RULE_TAB_NAME], rule_rows)
        print(f"  {RULE_TAB_NAME}: {len(rule_rows) - 1} 行")

        # 8. 書式適用
        print("書式適用中...")
        style_daily_tab(target_sh, tabs[DAILY_TAB_NAME])
        style_media_tab(target_sh, tabs[MEDIA_TAB_NAME])
        style_meta_tab(
            target_sh, tabs[SUMMARY_TAB_NAME],
            widths=[200, 300],
        )
        style_meta_tab(
            target_sh, tabs[SOURCE_MANAGEMENT_TAB_NAME],
            widths=[120, 200, 60, 280, 160, 160, 200, 160, 80, 160, 80, 200],
            status_col=8,
        )
        apply_status_cell_colors(target_sh, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_mgmt_rows, 8)
        style_meta_tab(
            target_sh, tabs[RULE_TAB_NAME],
            widths=[160, 380, 300],
        )

        # 9. 保護適用
        print("保護適用中...")
        apply_protections(target_sh, tabs)

        # 10. 状態保存
        state = {
            "updated_at": datetime.now().isoformat(),
            "day_count": len(sorted_dates),
            "total_spend": total_spend,
            "start_date": sorted_dates[0],
            "end_date": sorted_dates[-1],
            "media_count": len(media_set),
        }
        save_state(state)

        print(f"\n完了: {TARGET_SPREADSHEET_TITLE}")
        print(f"  URL: https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit")


if __name__ == "__main__":
    main()
