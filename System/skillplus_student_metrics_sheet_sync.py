#!/usr/bin/env python3
"""
【アドネス株式会社】スキルプラス受講生データ（加工）を再生成する。

方針:
- raw の `（元）` タブ群を正本にし、`（加工）` タブ群は読まない
- processed では `受講生単位` に正規化し、決済加工の正の証拠として再利用できる形にする
- `受講生一覧 / 受講生サマリー / データソース管理 / データ追加ルール` の4タブだけを持つ
- 決済側は processed の `受講生一覧` を読む。raw シートを直接読まない
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import gspread
from gspread.exceptions import APIError, SpreadsheetNotFound

from sheets_manager import get_client


SOURCE_SHEET_ID = "1zL8LV9CF8RLKiNDNqsYO6UXxuhBW32NcDaPJ5FqB17M"
SOURCE_SPREADSHEET_TITLE = "スキルプラス受講生データ"
TARGET_SHEET_ID = "1YcSED-AbNDMa0ay1yS7jmF_j4zOEnpccNHYWGrHQJiU"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】スキルプラス受講生データ（加工）"

STUDENT_TAB_NAME = "受講生一覧"
SUMMARY_TAB_NAME = "受講生サマリー"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    STUDENT_TAB_NAME: (8000, 18),
    SUMMARY_TAB_NAME: (80, 3),
    SOURCE_MANAGEMENT_TAB_NAME: (80, 14),
    RULE_TAB_NAME: (60, 3),
}

BASE_DIR = Path(__file__).resolve().parent
STATE_PATH = BASE_DIR / "data" / "skillplus_student_metrics_sheet_state.json"
LOCK_PATH = BASE_DIR / "data" / "skillplus_student_metrics_sheet_sync.lock"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 11,
}
TAB_COLORS = {
    STUDENT_TAB_NAME: "#1A73E8",
    SUMMARY_TAB_NAME: "#FBBC04",
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}
STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "要確認": {"backgroundColor": {"red": 1.0, "green": 0.945, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
}
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "スキルプラス受講生データ（加工）自動生成"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
METRICS_START_DATE = datetime(2025, 1, 1)
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
DATETIME_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
)
SKILLPLUS_STUDENT_EXCLUDED_TABS = {"最新元データ一覧"}
PLAN_GROUPS = ["SPS", "STD/オールインワン", "プライム", "エリート", "ライト/秘密", "その他"]
PROCESSED_SOURCE_EXCLUDED_TABS = {
    STUDENT_TAB_NAME,
    SUMMARY_TAB_NAME,
    SOURCE_MANAGEMENT_TAB_NAME,
    RULE_TAB_NAME,
}
TEST_MARKERS = ("test", "テスト", "てすと", "dummy", "sample", "サンプル", "確認用")
DUMMY_EMAIL_LOCALS = {"a", "abc", "i", "test", "testo", "dummy", "sample"}


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
                        f"スキルプラス受講生データ（加工）の更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"skillplus_student_metrics_sheet_sync (PID: {os.getpid()})",
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
    email = email.replace("＠", "@").replace("．", ".")
    if email.startswith("mailto:"):
        email = email.split("mailto:", 1)[1]
    return email


def normalize_phone(value: object) -> str:
    return re.sub(r"\D", "", normalize_text(value))


def normalize_name_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", normalize_text(value)).lower()
    text = re.sub(r"[\s\u3000]+", "", text)
    return "".join(ch for ch in text if ch.isalnum() or ch == "ー")


def normalize_marker_text(value: object) -> str:
    return unicodedata.normalize("NFKC", normalize_text(value)).lower()


def normalize_header_key(value: object) -> str:
    return re.sub(r"[\s\u3000]+", "", normalize_text(value))


def normalize_date(raw: object) -> str:
    value = normalize_text(raw)
    if not value:
        return ""
    match = DATE_RE.search(value)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def normalize_datetime(raw: object) -> str:
    value = normalize_text(raw)
    if not value:
        return ""
    for fmt in DATETIME_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y/%m/%d %H:%M:%S")
        except ValueError:
            continue
    date_only = normalize_date(value)
    if date_only:
        return f"{date_only} 00:00:00"
    return ""


def email_local_part(email: str) -> str:
    if "@" not in email:
        return ""
    return email.split("@", 1)[0].strip().lower()


def contains_test_marker(*values: str) -> bool:
    for value in values:
        normalized = normalize_marker_text(value)
        if not normalized:
            continue
        compact = re.sub(r"[\s\u3000]+", "", normalized)
        if any(marker in compact for marker in TEST_MARKERS):
            return True
    return False


def is_sparse_identity(
    email: str,
    phone: str,
    full_name_source: str,
    furigana_source: str,
    display_name_source: str,
) -> bool:
    identity_fields = [email, phone, full_name_source, furigana_source, display_name_source]
    populated = sum(1 for value in identity_fields if normalize_text(value))
    return populated <= 1


def should_exclude_student_row(
    email: str,
    phone: str,
    full_name_source: str,
    furigana_source: str,
    display_name_source: str,
) -> bool:
    if contains_test_marker(full_name_source, furigana_source, display_name_source):
        return True
    email_local = email_local_part(email)
    if email_local in DUMMY_EMAIL_LOCALS and contains_test_marker(email_local):
        return True
    if is_sparse_identity(email, phone, full_name_source, furigana_source, display_name_source):
        return True
    return False


def parse_datetime(raw: object) -> Optional[datetime]:
    value = normalize_datetime(raw)
    if not value:
        return None
    return datetime.strptime(value, "%Y/%m/%d %H:%M:%S")


def build_response_date(response_at: str) -> str:
    if response_at:
        return response_at.split(" ", 1)[0]
    return ""


def header_index_by_exact(headers: list[str], candidates: Iterable[str]) -> Optional[int]:
    normalized_candidates = {normalize_header_key(candidate) for candidate in candidates}
    for index, header in enumerate(headers):
        if normalize_header_key(header) in normalized_candidates:
            return index
    return None


def header_indexes_by_contains(headers: list[str], keywords: Iterable[str]) -> list[int]:
    normalized_keywords = [normalize_header_key(keyword) for keyword in keywords]
    indexes: list[int] = []
    for index, header in enumerate(headers):
        normalized_header = normalize_header_key(header)
        if any(keyword and keyword in normalized_header for keyword in normalized_keywords):
            indexes.append(index)
    return indexes


def pick_first_value(row: list[str], indexes: Iterable[int]) -> str:
    for index in indexes:
        if index >= len(row):
            continue
        value = normalize_text(row[index])
        if value:
            return value
    return ""


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


def run_read_with_retry(description: str, func):
    last_error = None
    for attempt in range(4):
        try:
            return func()
        except Exception as exc:
            message = str(exc)
            if not is_retryable_sheets_message(message) or attempt == 3:
                raise
            last_error = exc
            wait_seconds = 65 * (attempt + 1)
            print(f"{description}: Sheets の一時読み取りエラーのため {wait_seconds} 秒後に再試行します。")
            time.sleep(wait_seconds)
    if last_error:
        raise last_error


def batch_update_with_retry(spreadsheet, body: dict, description: str) -> None:
    run_write_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_write_with_retry(description, func)


def get_all_values_with_retry(ws) -> List[List[str]]:
    return run_read_with_retry(f"{ws.title} の読み取り", ws.get_all_values)


def get_or_create_target_spreadsheet(gc) -> gspread.Spreadsheet:
    try:
        spreadsheet = run_read_with_retry(
            "スキルプラス受講生データ（加工）シートの取得",
            lambda: gc.open_by_key(TARGET_SHEET_ID),
        )
    except SpreadsheetNotFound:
        spreadsheet = run_write_with_retry(
            "スキルプラス受講生データ（加工）シートの作成",
            lambda: gc.create(TARGET_SPREADSHEET_TITLE),
        )
    ensure_spreadsheet_title(spreadsheet)
    return spreadsheet


def ensure_spreadsheet_title(spreadsheet) -> None:
    metadata = run_read_with_retry(
        "スキルプラス受講生データ（加工）シートのメタデータ取得",
        lambda: spreadsheet.fetch_sheet_metadata({"fields": "properties.title"}),
    )
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
        "スキルプラス受講生データ（加工）のシート名更新",
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
    ordered_names = [STUDENT_TAB_NAME, SUMMARY_TAB_NAME, SOURCE_MANAGEMENT_TAB_NAME, RULE_TAB_NAME]
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
    batch_update_with_retry(spreadsheet, {"requests": requests}, "スキルプラス受講生データ（加工）のタブ整列")
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


def style_table(spreadsheet, ws, widths: Sequence[int], *, center_cols: Sequence[int] = (), date_cols: Sequence[int] = (), left_cols: Sequence[int] = (), header_font_size: int = 11) -> None:
    col_count = len(widths)
    requests = [
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            col_count,
            {
                "backgroundColor": HEADER_BG,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "textFormat": {**HEADER_TEXT, "fontSize": header_font_size},
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,textFormat,wrapStrategy)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            0,
            col_count,
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
            {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}, "horizontalAlignment": "CENTER"},
            "userEnteredFormat(numberFormat,horizontalAlignment)",
        ),
        set_row_height_request(ws.id, 0, 1, 28),
        set_row_height_request(ws.id, 1, ws.row_count, 24),
        set_sheet_properties_request(ws.id, {"gridProperties": {"frozenRowCount": 1}}, "gridProperties.frozenRowCount"),
    ]
    for index, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, index, index + 1, width))
    for col in center_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                col,
                col + 1,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    for col in date_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                col,
                col + 1,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}, "horizontalAlignment": "CENTER"},
                "userEnteredFormat(numberFormat,horizontalAlignment)",
            )
        )
    for col in left_cols:
        requests.append(
            repeat_cell_request(
                ws.id,
                1,
                ws.row_count,
                col,
                col + 1,
                {"horizontalAlignment": "LEFT"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の書式設定")


def apply_status_cell_colors(spreadsheet, ws, rows: List[List[object]], status_col: int) -> None:
    requests = []
    for row_index, row in enumerate(rows[1:], start=1):
        status = normalize_text(row[status_col]) if status_col < len(row) else ""
        fmt = STATUS_FORMATS.get(status)
        if not fmt:
            continue
        requests.append(
            repeat_cell_request(
                ws.id,
                row_index,
                row_index + 1,
                status_col,
                status_col + 1,
                fmt,
                "userEnteredFormat.backgroundColor",
            )
        )
    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} のステータス色設定")


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
        batch_update_with_retry(spreadsheet, {"requests": requests}, "スキルプラス受講生データ（加工）の保護設定")


def get_tab_url(spreadsheet_id: str, ws) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={ws.id}"


def is_skillplus_student_raw_tab(title: str) -> bool:
    normalized = normalize_text(title)
    return normalized not in SKILLPLUS_STUDENT_EXCLUDED_TABS and normalized not in PROCESSED_SOURCE_EXCLUDED_TABS


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
        "admission_indexes": header_indexes_by_contains(headers, ["入会日", "ご入会日"]),
        "response_at_indexes": header_indexes_by_contains(headers, ["回答日時"]),
        "response_id_index": header_index_by_exact(headers, ["回答ID"]),
        "responder_id_index": header_index_by_exact(headers, ["回答者ID"]),
        "surname_index": header_index_by_exact(headers, ["姓", "姓（せい）"]),
        "given_name_index": header_index_by_exact(headers, ["名"]),
    }


def plan_group_from_title(title: str) -> str:
    normalized = normalize_text(title)
    if "SPS" in normalized:
        return "SPS"
    if "STD" in normalized or "オールインワン" in normalized:
        return "STD/オールインワン"
    if "プライム" in normalized:
        return "プライム"
    if "エリート" in normalized:
        return "エリート"
    if "ライト" in normalized or "秘密" in normalized:
        return "ライト/秘密"
    return "その他"


def build_identity(email: str, phone: str, full_name: str, furigana: str, display_name: str, answerer_id: str, answer_id: str, raw_tab: str, raw_row: int) -> tuple[str, str, str]:
    if email:
        return f"email:{email}", "メール", email
    if phone:
        return f"phone:{phone}", "電話番号", phone
    if full_name and furigana:
        return f"namefurigana:{full_name}|{furigana}", "氏名+ふりがな", f"{full_name} / {furigana}"
    if full_name:
        return f"name:{full_name}", "氏名", full_name
    if display_name:
        return f"display:{display_name}", "表示名", display_name
    if answerer_id:
        return f"responder:{answerer_id}", "回答者ID", answerer_id
    if answer_id:
        return f"answer:{answer_id}", "回答ID", answer_id
    return f"row:{raw_tab}:{raw_row}", "行", f"{raw_tab}:{raw_row}"


def merge_text(current: str, new_value: str) -> str:
    return current or new_value


def merge_earliest_datetime(current: str, new_value: str) -> str:
    if not current:
        return new_value
    if not new_value:
        return current
    current_dt = parse_datetime(current)
    new_dt = parse_datetime(new_value)
    if not current_dt:
        return new_value
    if not new_dt:
        return current
    return new_value if new_dt < current_dt else current


def merge_latest_datetime(current: str, new_value: str) -> str:
    if not current:
        return new_value
    if not new_value:
        return current
    current_dt = parse_datetime(current)
    new_dt = parse_datetime(new_value)
    if not current_dt:
        return new_value
    if not new_dt:
        return current
    return new_value if new_dt > current_dt else current


def build_student_aggregates(source_ss) -> tuple[list[dict[str, object]], dict[str, object]]:
    aggregates: dict[str, dict[str, object]] = {}
    source_rows_by_group: Counter[str] = Counter()
    source_tabs_by_group: defaultdict[str, set[str]] = defaultdict(set)
    skipped_tabs: list[str] = []
    source_row_count = 0
    excluded_row_count = 0

    for ws in source_ss.worksheets():
        if not is_skillplus_student_raw_tab(ws.title):
            continue

        rows = get_all_values_with_retry(ws)
        header_row_index = detect_student_header_row(rows)
        if header_row_index is None:
            if any(any(normalize_text(cell) for cell in row) for row in rows):
                skipped_tabs.append(ws.title)
            continue

        headers = rows[header_row_index]
        spec = build_student_header_spec(headers)
        plan_group = plan_group_from_title(ws.title)
        source_tabs_by_group[plan_group].add(ws.title)

        for source_offset, row in enumerate(rows[header_row_index + 1 :], start=header_row_index + 2):
            if not any(normalize_text(cell) for cell in row):
                continue

            email_raw = pick_first_value(row, spec["email_indexes"])
            phone_raw = pick_first_value(row, spec["phone_indexes"])
            full_name_source = pick_first_value(row, spec["full_name_indexes"])
            if not full_name_source and spec["surname_index"] is not None and spec["given_name_index"] is not None:
                surname = normalize_text(row[spec["surname_index"]]) if spec["surname_index"] < len(row) else ""
                given_name = normalize_text(row[spec["given_name_index"]]) if spec["given_name_index"] < len(row) else ""
                full_name_source = f"{surname}{given_name}"
            furigana_source = pick_first_value(row, spec["furigana_indexes"])
            display_name_source = pick_first_value(row, spec["display_name_indexes"]) or pick_first_value(row, spec["nickname_indexes"])

            email = normalize_email(email_raw)
            phone = normalize_phone(phone_raw)
            if should_exclude_student_row(email, phone, full_name_source, furigana_source, display_name_source):
                excluded_row_count += 1
                continue

            source_row_count += 1
            source_rows_by_group[plan_group] += 1

            full_name = normalize_name_key(full_name_source)
            furigana = normalize_name_key(furigana_source)
            display_name = normalize_name_key(display_name_source)
            response_at = normalize_datetime(pick_first_value(row, spec["response_at_indexes"]))
            first_response_date = build_response_date(response_at)
            answer_id = normalize_text(row[spec["response_id_index"]]) if spec["response_id_index"] is not None and spec["response_id_index"] < len(row) else ""
            answerer_id = normalize_text(row[spec["responder_id_index"]]) if spec["responder_id_index"] is not None and spec["responder_id_index"] < len(row) else ""

            identity_key, identity_method, identity_value = build_identity(
                email,
                phone,
                full_name,
                furigana,
                display_name,
                answerer_id,
                answer_id,
                ws.title,
                source_offset,
            )
            dedupe_key = f"{plan_group}|{identity_key}|{first_response_date}"
            current = aggregates.get(dedupe_key)
            if current is None:
                aggregates[dedupe_key] = {
                    "student_key": dedupe_key,
                    "identity_method": identity_method,
                    "identity_value": identity_value,
                    "plan_group": plan_group,
                    "first_response_date": first_response_date,
                    "first_response_at": response_at,
                    "last_response_at": response_at,
                    "email": email,
                    "phone": phone,
                    "full_name": full_name,
                    "furigana": furigana,
                    "display_name": display_name,
                    "response_count": 1,
                    "raw_tabs": {ws.title},
                    "answer_id": answer_id,
                    "answerer_id": answerer_id,
                }
                continue

            current["identity_method"] = merge_text(str(current["identity_method"]), identity_method)
            current["identity_value"] = merge_text(str(current["identity_value"]), identity_value)
            current["first_response_at"] = merge_earliest_datetime(str(current["first_response_at"]), response_at)
            current["last_response_at"] = merge_latest_datetime(str(current["last_response_at"]), response_at)
            current["email"] = merge_text(str(current["email"]), email)
            current["phone"] = merge_text(str(current["phone"]), phone)
            current["full_name"] = merge_text(str(current["full_name"]), full_name)
            current["furigana"] = merge_text(str(current["furigana"]), furigana)
            current["display_name"] = merge_text(str(current["display_name"]), display_name)
            current["answer_id"] = merge_text(str(current["answer_id"]), answer_id)
            current["answerer_id"] = merge_text(str(current["answerer_id"]), answerer_id)
            current["response_count"] = int(current["response_count"]) + 1
            cast_tabs = current["raw_tabs"]
            if isinstance(cast_tabs, set):
                cast_tabs.add(ws.title)

            first_response_at = str(current["first_response_at"])
            current["first_response_date"] = build_response_date(first_response_at)

    students: list[dict[str, object]] = []
    for item in aggregates.values():
        raw_tabs = sorted(item["raw_tabs"]) if isinstance(item["raw_tabs"], set) else []
        students.append(
            {
                "student_key": item["student_key"],
                "identity_method": item["identity_method"],
                "identity_value": item["identity_value"],
                "plan_group": item["plan_group"],
                "first_response_date": item["first_response_date"],
                "first_response_at": item["first_response_at"],
                "last_response_at": item["last_response_at"],
                "email": item["email"],
                "phone": item["phone"],
                "full_name": item["full_name"],
                "furigana": item["furigana"],
                "display_name": item["display_name"],
                "response_count": item["response_count"],
                "raw_tabs": raw_tabs,
                "answer_id": item["answer_id"],
                "answerer_id": item["answerer_id"],
            }
        )

    students.sort(
        key=lambda item: (
            item["first_response_date"] or "0000/00/00",
            item["plan_group"],
            item["full_name"] or item["display_name"] or item["email"] or item["phone"],
        ),
        reverse=True,
    )

    stats = {
        "source_row_count": source_row_count,
        "excluded_row_count": excluded_row_count,
        "student_count": len(students),
        "source_rows_by_group": dict(source_rows_by_group),
        "source_tabs_by_group": {key: sorted(value) for key, value in source_tabs_by_group.items()},
        "skipped_tabs": sorted(skipped_tabs),
    }
    return students, stats


def build_student_rows(students: list[dict[str, object]]) -> List[List[object]]:
    rows: List[List[object]] = [[
        "プラン",
        "初回回答日時",
        "最終回答日時",
        "メールアドレス",
        "電話番号",
        "お名前",
        "ふりがな",
        "表示名",
        "最初の回答ID",
        "最初の回答者ID",
    ]]
    for student in students:
        rows.append(
            [
                student["plan_group"],
                student["first_response_at"],
                student["last_response_at"],
                student["email"],
                student["phone"],
                student["full_name"],
                student["furigana"],
                student["display_name"],
                student["answer_id"],
                student["answerer_id"],
            ]
        )
    return rows


def build_admission_stats(students: list[dict[str, object]]) -> dict[str, object]:
    latest_first_response_at = ""
    missing_first_response_count = 0

    for student in students:
        first_response_at = normalize_text(student["first_response_at"])
        if not first_response_at:
            missing_first_response_count += 1
            continue
        first_response_dt = datetime.strptime(first_response_at, "%Y/%m/%d %H:%M:%S")
        if first_response_dt < METRICS_START_DATE:
            continue
        latest_first_response_at = max(latest_first_response_at, first_response_at)
    return {
        "latest_first_response_at": latest_first_response_at,
        "missing_first_response_count": missing_first_response_count,
    }


def build_summary_rows(students: list[dict[str, object]], stats: dict[str, object], checked_at: str, admission_stats: dict[str, int]) -> List[List[object]]:
    plan_counts = Counter(normalize_text(student["plan_group"]) or "その他" for student in students)
    rows = [
        ["項目", "値", "補足"],
        ["最終更新日時", checked_at, "このシートを再生成した時刻"],
        ["集計開始日", METRICS_START_DATE.strftime("%Y/%m/%d"), "受講生加工で主要に扱う起点日"],
        ["最新初回回答日時", admission_stats.get("latest_first_response_at", ""), "受講生一覧の初回回答日時ベース"],
        ["受講生数", len(students), "受講生キー単位で正規化した件数"],
        ["採用元回答件数", stats.get("source_row_count", 0), "テスト入力と極端に情報不足な行を除外した件数"],
        ["除外件数", stats.get("excluded_row_count", 0), "明確なテスト入力、または照合に使えない極端な疎データ"],
        ["初回回答日時空欄件数", admission_stats.get("missing_first_response_count", 0), "受講生一覧に初回回答日時がない件数"],
        ["SPS受講生数", plan_counts.get("SPS", 0), ""],
        ["STD/オールインワン受講生数", plan_counts.get("STD/オールインワン", 0), ""],
        ["プライム受講生数", plan_counts.get("プライム", 0), ""],
        ["エリート受講生数", plan_counts.get("エリート", 0), ""],
        ["ライト/秘密受講生数", plan_counts.get("ライト/秘密", 0), ""],
        ["その他受講生数", plan_counts.get("その他", 0), "未知の raw タブ名はここに残る"],
        ["要確認タブ数", len(stats.get("skipped_tabs", [])), "ヘッダー検出できなかった raw タブ数"],
    ]
    return rows


def build_source_management_rows(source_ss, stats: dict[str, object], checked_at: str) -> List[List[object]]:
    rows: List[List[object]] = [[
        "加工タブ",
        "対象カラム",
        "優先度",
        "ソース元",
        "参照タブ",
        "参照列",
        "取得条件",
        "ステータス",
        "最終同期日",
        "更新数",
        "エラー数",
        "備考",
        "対象期間",
        "メモ",
    ]]

    skipped_tabs = stats.get("skipped_tabs", [])
    base_status = "要確認" if skipped_tabs else "正常"
    source_url = f"https://docs.google.com/spreadsheets/d/{SOURCE_SHEET_ID}/edit"
    grouped_tabs = stats.get("source_tabs_by_group", {})
    grouped_rows = stats.get("source_rows_by_group", {})

    rows.append(
        [
            STUDENT_TAB_NAME,
            "プラン / 初回回答日時 / 最終回答日時 / メールアドレス / 電話番号 / お名前 / ふりがな / 表示名 / 回答ID",
            "1",
            f'=HYPERLINK("{source_url}","スキルプラス受講生データ")',
            "（元）タブ群",
            "メールアドレス / 電話番号 / お名前 / ふりがな / 回答者名 / 回答日時",
            "同一プランかつ同一受講生とみなせる回答を内部キーで統合し、表示上は最小列だけ残す",
            base_status,
            f"'{checked_at}",
            stats.get("student_count", 0),
            len(skipped_tabs),
            "受講生単位の正規化一覧",
            "2025/01/01以降を主に利用",
            "決済加工ではこのタブを正の証拠として使う",
        ]
    )
    for plan_group in PLAN_GROUPS:
        plan_tabs = grouped_tabs.get(plan_group) or []
        if not plan_tabs:
            continue
        rows.append(
            [
                "raw 正本",
                f"{plan_group} の元回答",
                "1",
                f'=HYPERLINK("{source_url}","スキルプラス受講生データ")',
                " / ".join(plan_tabs),
                "回答日時 / 入会日 / メールアドレス / 電話番号 / 氏名",
                "raw 形式のヘッダーを持つタブだけを対象にする。名称だけで除外しない",
                "正常",
                f"'{checked_at}",
                grouped_rows.get(plan_group, 0),
                0,
                f"{plan_group} の raw 行数",
                "全期間",
                "",
            ]
        )
    if skipped_tabs:
        rows.append(
            [
                "raw 正本",
                "ヘッダー未検出タブ",
                "1",
                f'=HYPERLINK("{source_url}","スキルプラス受講生データ")',
                " / ".join(skipped_tabs),
                "",
                "raw タブに値はあるがヘッダーが検出できなかったため未採用",
                "要確認",
                f"'{checked_at}",
                0,
                len(skipped_tabs),
                "タブ名またはヘッダー行を確認する",
                "全期間",
                "新しい raw タブ追加時の確認ポイント",
            ]
        )
    return rows


def build_rule_rows() -> List[List[object]]:
    return [
        ["項目", "ルール", "補足"],
        ["受講生一覧", "手入力で直さず、raw 形式のヘッダーを持つタブ群から再生成する", "表示列は決済照合に必要な項目だけに絞る"],
        ["raw タブ判定", "タイトルではなくヘッダー構造で判定する", "`最新元データ一覧` と processed の管理タブを除外する"],
        ["内部識別", "メール -> 電話番号 -> 氏名+ふりがな -> 氏名 -> 表示名 -> 回答者ID -> 回答ID の順で内部キーを作る", "内部キーはシートに出さず、重複統合だけに使う"],
        ["初回回答日時", "自己申告の入会日は使わず、raw に記録された初回回答日時だけを使う", "信頼できる一次データに寄せる"],
        ["プラン", "タブ名から `SPS / STD/オールインワン / プライム / エリート / ライト/秘密` を判定する", "どれにも当たらない raw タブは `その他` に残す"],
        ["除外ルール", "明確なテスト入力、または照合に使えない極端な疎データは取り込まない", "一文字名だけでは除外しない"],
        ["決済との接続", "決済加工はこの processed の `受講生一覧` を正の証拠に使う", "raw の受講生シートを直接読まない"],
        ["要確認", "値があるのにヘッダー検出できない raw タブは `要確認` に残す", "新しい raw タブ追加時の確認を簡単にする"],
    ]


def load_skillplus_student_identifiers_from_processed(ws) -> tuple[dict[str, set[str]], int]:
    rows = get_all_values_with_retry(ws)
    if not rows:
        return {"emails": set(), "phones": set(), "names": set()}, 0
    headers = rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    emails: set[str] = set()
    phones: set[str] = set()
    names: set[str] = set()
    count = 0

    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        if not any(normalize_text(cell) for cell in padded):
            continue
        count += 1
        email = normalize_email(padded[idx["メールアドレス"]]) if "メールアドレス" in idx else ""
        phone = normalize_phone(padded[idx["電話番号"]]) if "電話番号" in idx else ""
        full_name = normalize_name_key(padded[idx["お名前"]]) if "お名前" in idx else ""
        furigana = normalize_name_key(padded[idx["ふりがな"]]) if "ふりがな" in idx else ""
        display_name = normalize_name_key(padded[idx["表示名"]]) if "表示名" in idx else ""

        if email:
            emails.add(email)
        if phone:
            phones.add(phone)
        if full_name:
            names.add(full_name)
        if furigana:
            names.add(furigana)
        if display_name:
            names.add(display_name)
    return {"emails": emails, "phones": phones, "names": names}, count


def load_run_state() -> Dict[str, object]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_run_state(stats: Dict[str, object]) -> None:
    payload = {
        "updated_at": stats["updated_at"],
        "student_count": stats["student_count"],
        "source_row_count": stats["source_row_count"],
        "excluded_row_count": stats.get("excluded_row_count", 0),
        "latest_first_response_at": stats["latest_first_response_at"],
        "missing_first_response_count": stats["missing_first_response_count"],
        "skipped_tabs": stats["skipped_tabs"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def sync_skillplus_student_metrics_sheet(dry_run: bool = False, gc=None) -> dict:
    with FileLock():
        gc = gc or get_client()
        source_ss = gc.open_by_key(SOURCE_SHEET_ID)
        target = get_or_create_target_spreadsheet(gc)
        tabs = ensure_tabs(target)

        students, source_stats = build_student_aggregates(source_ss)
        student_rows = build_student_rows(students)
        admission_stats = build_admission_stats(students)
        checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")

        stats = {
            "updated_at": checked_at,
            "student_count": len(students),
            "source_row_count": source_stats["source_row_count"],
            "excluded_row_count": source_stats.get("excluded_row_count", 0),
            "latest_first_response_at": admission_stats.get("latest_first_response_at", ""),
            "missing_first_response_count": admission_stats.get("missing_first_response_count", 0),
            "skipped_tabs": source_stats.get("skipped_tabs", []),
        }

        summary_rows = build_summary_rows(students, source_stats, checked_at, admission_stats)
        source_rows = build_source_management_rows(source_ss, {**source_stats, **stats}, checked_at)
        rule_rows = build_rule_rows()

        if dry_run:
            print("【dry-run】受講生数:", stats["student_count"])
            print("【dry-run】採用元回答件数:", stats["source_row_count"])
            print("【dry-run】除外件数:", stats["excluded_row_count"])
            print("【dry-run】最新初回回答日時:", stats["latest_first_response_at"])
            print("【dry-run】初回回答日時空欄件数:", stats["missing_first_response_count"])
            if stats["skipped_tabs"]:
                print("【dry-run】要確認タブ:", ", ".join(stats["skipped_tabs"]))
            return stats

        write_rows(target, tabs[STUDENT_TAB_NAME], student_rows)
        style_table(
            target,
            tabs[STUDENT_TAB_NAME],
            widths=[150, 150, 150, 220, 120, 120, 120, 120, 120, 120],
            center_cols=[0],
            left_cols=[3, 5, 6, 7],
        )
        write_rows(target, tabs[SUMMARY_TAB_NAME], summary_rows)
        style_table(
            target,
            tabs[SUMMARY_TAB_NAME],
            widths=[180, 160, 420],
            left_cols=[0, 2],
            center_cols=[1],
        )
        write_rows(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows)
        style_table(
            target,
            tabs[SOURCE_MANAGEMENT_TAB_NAME],
            widths=[120, 220, 70, 220, 220, 240, 260, 90, 140, 90, 90, 220, 120, 260],
            center_cols=[2, 7, 9, 10, 12],
            left_cols=[0, 1, 3, 4, 5, 6, 11, 13],
        )
        apply_status_cell_colors(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows, 7)
        write_rows(target, tabs[RULE_TAB_NAME], rule_rows)
        style_table(
            target,
            tabs[RULE_TAB_NAME],
            widths=[160, 520, 340],
            left_cols=[0, 1, 2],
        )

        apply_protections(target, tabs)
        save_run_state(stats)
        print(f"{TARGET_SPREADSHEET_TITLE} を更新しました。")
        return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="スキルプラス受講生データ（加工）を更新する")
    parser.add_argument("--dry-run", action="store_true", help="Sheets へ書き込まず集計だけ行う")
    args = parser.parse_args()
    sync_skillplus_student_metrics_sheet(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
