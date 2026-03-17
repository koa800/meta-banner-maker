#!/usr/bin/env python3
"""
【アドネス株式会社】会員データ（収集）を整える。

方針:
- 収集データはソースシステムの事実だけを保持する
- 1行 = 1契約単位（面談ID優先で統合）
- 契約 / 入金前契約解除 / クーリングオフ / 中途解約を 1 タブに集約する
- 加工ロジックは入れず、収集元と追加ルールだけを明示する
"""

from __future__ import annotations

import argparse
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from gspread.exceptions import APIError

from sheets_manager import get_client


TARGET_SHEET_ID = "1VwAO5rxib8pcR7KgGn-T3HKP7FaHqZmUhIBddo3okyw"
INTERVIEW_ALL_SHEET_ID = "1vHWRdYV7nK7qF06Jk7bQ2v4_H_Grcv49Szg-vF-Kanw"
SUPPORT_PROGRESS_SHEET_ID = "1XOkJsXzEx4iV9h8F-cywg0FOS4Knf7IfekN78RZAr6I"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
STATUS_OPTIONS = ["正常", "未同期", "停止"]
STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "未同期": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
}
TAB_COLOR_MAIN = "#1A73E8"
TAB_COLOR_META = "#34A853"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
CONTRACT_RESULT_ALLOWLIST = {
    "成約",
    "クーリングオフ",
    "入金前契約解除",
    "入金前契約解除(信販否決)",
    "契約済み(入金待ち)",
}

TAB_SPECS = [
    ("会員イベント", 6000, 8),
    ("データソース管理", 80, 12),
    ("データ追加ルール", 50, 3),
]


@dataclass
class MemberEventRow:
    email: str = ""
    phone: str = ""
    name: str = ""
    line_name: str = ""
    contract_date: str = ""
    pre_payment_cancel: str = ""
    cooling_off: str = ""
    mid_term_cancel: str = ""

    def to_row(self) -> List[str]:
        return [
            self.email,
            self.phone,
            self.name,
            self.line_name,
            self.contract_date,
            self.pre_payment_cancel,
            self.cooling_off,
            self.mid_term_cancel,
        ]


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


def get_tab_url(spreadsheet_id: str, ws) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit#gid={ws.id}"


def is_quota_error(exc: APIError) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code == 429 or "Quota exceeded" in str(exc)


def run_sheets_call_with_retry(description: str, func):
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
    run_sheets_call_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_sheets_call_with_retry(description, func)


def ensure_tabs(spreadsheet):
    existing = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered = []
    for title, rows, cols in TAB_SPECS:
        ws = existing.get(title)
        if ws is None:
            ws = run_sheets_call_with_retry(f"{title} タブ作成", lambda: spreadsheet.add_worksheet(title=title, rows=rows, cols=cols))
        else:
            if ws.row_count != rows or ws.col_count != cols:
                worksheet_write_with_retry(
                    f"{title} タブサイズ調整",
                    lambda ws=ws, rows=rows, cols=cols: ws.resize(rows=rows, cols=cols),
                )
        ordered.append(ws)

    target_titles = {spec[0] for spec in TAB_SPECS}
    for title in list(existing):
        if title not in target_titles:
            worksheet_write_with_retry(
                f"{title} タブ削除",
                lambda ws=existing[title]: spreadsheet.del_worksheet(ws),
            )

    requests = []
    for idx, ws in enumerate(ordered):
        color = TAB_COLOR_MAIN if ws.title == "会員イベント" else TAB_COLOR_META
        requests.append(set_sheet_properties_request(ws.id, {"index": idx, "hidden": False}, "index,hidden"))
        requests.append(set_sheet_properties_request(ws.id, {"tabColorStyle": {"rgbColor": hex_to_rgb(color)}}, "tabColorStyle"))
    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, "会員データ（収集）のタブ整列")
    return {ws.title: ws for ws in spreadsheet.worksheets()}


def write_rows(ws, rows: List[List[str]]) -> None:
    worksheet_write_with_retry(f"{ws.title} クリア", lambda: ws.clear())
    worksheet_write_with_retry(
        f"{ws.title} 更新",
        lambda: ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED"),
    )


def style_main_tab(spreadsheet, ws, widths: List[int]) -> None:
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
            "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
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
                "textFormat": {
                    "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                    "bold": False,
                    "fontSize": 10,
                },
            },
            "userEnteredFormat(backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy,textFormat)",
        ),
        repeat_cell_request(
            ws.id,
            1,
            ws.row_count,
            4,
            len(widths),
            {
                "horizontalAlignment": "CENTER",
            },
            "userEnteredFormat.horizontalAlignment",
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


def style_meta_tab(
    spreadsheet,
    ws,
    widths: List[int],
    center_cols=None,
    date_cols=None,
    status_col=None,
    number_cols=None,
) -> None:
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
            "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
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
                "textFormat": {
                    "foregroundColor": {"red": 0, "green": 0, "blue": 0},
                    "bold": False,
                    "fontSize": 10,
                },
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
                {
                    "horizontalAlignment": "RIGHT",
                    "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
                },
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
    batch_update_with_retry(
        spreadsheet,
        {"requests": [clear_validation_request]},
        f"{ws.title} の既存入力規則クリア",
    )

    if status_col is not None:
        validation = {
            "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS]},
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


def apply_status_cell_colors(spreadsheet, ws, rows: List[List[str]], status_col_index: int) -> None:
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


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_optional_text(value: object) -> str:
    text = normalize_text(value)
    if text in {"-", "ー", "―", "なし", "無し", "N/A"}:
        return ""
    return text


def normalize_email(value: object) -> str:
    text = normalize_optional_text(value).lower()
    if not text:
        return ""
    compact = text.replace(" ", "").replace("　", "")
    if compact in {"なし", "無し", "メアドなし", "メールなし", "メールアドレスなし", "noemail", "未登録"}:
        return ""
    if not EMAIL_RE.match(compact):
        return ""
    return compact


def normalize_phone(value: object) -> str:
    return (
        normalize_optional_text(value)
        .replace("-", "")
        .replace(" ", "")
        .replace("　", "")
        .replace("+81", "0")
    )


def compact_key(value: object) -> str:
    return normalize_text(value).replace("\n", "").replace(" ", "").replace("　", "")


def get_records(ws, header_row: int = 1) -> List[dict]:
    values = run_sheets_call_with_retry(f"{ws.title} 読み取り", lambda: ws.get_all_values())
    if len(values) < header_row:
        return []
    headers = [normalize_text(v) for v in values[header_row - 1]]
    records: List[dict] = []
    for raw in values[header_row:]:
        if not any(normalize_text(cell) for cell in raw):
            continue
        row = {}
        for idx, header in enumerate(headers):
            if not header:
                continue
            cell = raw[idx] if idx < len(raw) else ""
            row[header] = cell
            compact = compact_key(header)
            if compact and compact != header:
                row[compact] = cell
        records.append(row)
    return records


def get_row_value(row: dict, *keys: str) -> str:
    for key in keys:
        if key in row and normalize_text(row.get(key)):
            return normalize_text(row.get(key))
        compact = compact_key(key)
        if compact in row and normalize_text(row.get(compact)):
            return normalize_text(row.get(compact))
    return ""


def parse_datetime_text(value: str) -> Optional[datetime]:
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y/%m/%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def choose_earliest(current: str, candidate: str) -> str:
    current_text = normalize_text(current)
    candidate_text = normalize_text(candidate)
    if not candidate_text:
        return current_text
    if not current_text:
        return candidate_text
    current_dt = parse_datetime_text(current_text)
    candidate_dt = parse_datetime_text(candidate_text)
    if current_dt and candidate_dt:
        return candidate_text if candidate_dt < current_dt else current_text
    return current_text


def is_contract_result(row: dict) -> bool:
    result = get_row_value(row, "結果")
    return result in CONTRACT_RESULT_ALLOWLIST


def build_member_key(row: dict) -> str:
    interview_id = normalize_text(row.get("面談ID"))
    if interview_id:
        return f"interview:{interview_id}"

    email = normalize_email(row.get("メールアドレス") or row.get("アドレス"))
    if email:
        return f"email:{email}"

    phone = normalize_phone(row.get("電話番号"))
    if phone:
        return f"phone:{phone}"

    line_name = normalize_text(row.get("LINE名"))
    name = normalize_text(row.get("名前") or row.get("本名"))
    return f"name:{line_name}|{name}"


def increment_fill_count(fill_counts: Dict[Tuple[str, str], int], target_column: str, priority: str) -> None:
    key = (target_column, priority)
    fill_counts[key] = fill_counts.get(key, 0) + 1


def merge_base_fields(member: MemberEventRow, row: dict, fill_counts: Dict[Tuple[str, str], int], priority_by_field: Dict[str, str]) -> None:
    email = normalize_email(row.get("メールアドレス") or row.get("アドレス"))
    phone = normalize_phone(row.get("電話番号"))
    name = normalize_optional_text(row.get("名前") or row.get("本名"))
    line_name = normalize_optional_text(row.get("LINE名"))

    if email and not member.email:
        member.email = email
        increment_fill_count(fill_counts, "メールアドレス", priority_by_field["email"])
    if phone and not member.phone:
        member.phone = phone
        increment_fill_count(fill_counts, "電話番号", priority_by_field["phone"])
    if name and not member.name:
        member.name = name
        increment_fill_count(fill_counts, "名前", priority_by_field["name"])
    if line_name and not member.line_name:
        member.line_name = line_name
        increment_fill_count(fill_counts, "LINE名", priority_by_field["line_name"])


def build_member_rows(interview_records: List[dict], cooling_records: List[dict], cancel_records: List[dict]) -> Tuple[List[List[str]], Dict[Tuple[str, str], int]]:
    merged: Dict[str, MemberEventRow] = {}
    fill_counts: Dict[Tuple[str, str], int] = {}

    for row in interview_records:
        contract_date = normalize_optional_text(get_row_value(row, "契約締結日"))
        result = get_row_value(row, "結果")
        if not is_contract_result(row):
            continue
        if not contract_date and result != "入金前契約解除":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(
            member,
            row,
            fill_counts,
            {"email": "1", "phone": "1", "name": "1", "line_name": "1"},
        )
        previous_contract_date = member.contract_date
        member.contract_date = choose_earliest(member.contract_date, contract_date)
        if member.contract_date and not previous_contract_date:
            increment_fill_count(fill_counts, "契約締結日", "1")
        if result == "入金前契約解除":
            if not member.pre_payment_cancel:
                member.pre_payment_cancel = "○"
                increment_fill_count(fill_counts, "入金前契約解除", "1")

    for row in cooling_records:
        if get_row_value(row, "クーリングオフorその他", "中途解約orその他") != "クーリングオフ":
            continue
        if get_row_value(row, "ステータス") != "完了":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(
            member,
            row,
            fill_counts,
            {"email": "2", "phone": "1", "name": "2", "line_name": "2"},
        )
        contract_date = normalize_optional_text(get_row_value(row, "契約締結日"))
        previous_contract_date = member.contract_date
        member.contract_date = choose_earliest(member.contract_date, contract_date)
        if member.contract_date and not previous_contract_date:
            increment_fill_count(fill_counts, "契約締結日", "1")
        previous_cooling_off = member.cooling_off
        member.cooling_off = choose_earliest(member.cooling_off, get_row_value(row, "対応完了日"))
        if member.cooling_off and not previous_cooling_off:
            increment_fill_count(fill_counts, "クーリングオフ", "1")

    for row in cancel_records:
        if get_row_value(row, "中途解約orその他", "クーリングオフorその他") != "中途解約":
            continue
        if get_row_value(row, "ステータス") != "完了":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(
            member,
            row,
            fill_counts,
            {"email": "3", "phone": "1", "name": "3", "line_name": "3"},
        )
        contract_date = normalize_optional_text(get_row_value(row, "契約締結日"))
        previous_contract_date = member.contract_date
        member.contract_date = choose_earliest(member.contract_date, contract_date)
        if member.contract_date and not previous_contract_date:
            increment_fill_count(fill_counts, "契約締結日", "1")
        previous_mid_term_cancel = member.mid_term_cancel
        member.mid_term_cancel = choose_earliest(member.mid_term_cancel, get_row_value(row, "対応完了日"))
        if member.mid_term_cancel and not previous_mid_term_cancel:
            increment_fill_count(fill_counts, "中途解約", "1")

    rows = [["メールアドレス", "電話番号", "名前", "LINE名", "契約締結日", "入金前契約解除", "クーリングオフ", "中途解約"]]
    data_rows = [member.to_row() for member in merged.values() if member.contract_date]
    data_rows.sort(key=lambda r: (r[4] or "9999/99/99", r[0], r[1], r[3], r[2]))
    rows.extend(data_rows)
    return rows, fill_counts


def build_data_source_rows(
    interview_tab,
    cooling_tab,
    cancel_tab,
    *,
    checked_at: str,
    interview_count: int,
    cooling_count: int,
    cancel_count: int,
    event_count: int,
    fill_counts: Dict[Tuple[str, str], int],
) -> List[List[str]]:
    def status_from_count(count: int) -> str:
        return "正常" if count > 0 else "停止"

    return [
        ["収集タブ", "対象カラム", "優先度", "ソース元", "参照タブ", "参照列", "取得条件", "ステータス", "最終同期日", "更新数", "エラー数", "備考"],
        [
            "会員イベント",
            "メールアドレス",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "メールアドレス",
            "結果が契約系（成約 / クーリングオフ / 入金前契約解除 / 入金前契約解除(信販否決) / 契約済み(入金待ち)）の行",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("メールアドレス", "1"), 0),
            0,
            f"メールアドレスの第1優先 / 元ソース対象件数 {interview_count} / 会員イベント {event_count} 行",
        ],
        [
            "会員イベント",
            "メールアドレス",
            "2",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "アドレス",
            "クーリングオフ かつ 完了",
            status_from_count(cooling_count),
            checked_at,
            fill_counts.get(("メールアドレス", "2"), 0),
            0,
            f"メールアドレスの補完元 / 元ソース対象件数 {cooling_count}",
        ],
        [
            "会員イベント",
            "メールアドレス",
            "3",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "アドレス",
            "中途解約 かつ 完了",
            status_from_count(cancel_count),
            checked_at,
            fill_counts.get(("メールアドレス", "3"), 0),
            0,
            f"メールアドレスの補完元 / 元ソース対象件数 {cancel_count}",
        ],
        [
            "会員イベント",
            "電話番号",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "電話番号",
            "結果が契約系（成約 / クーリングオフ / 入金前契約解除 / 入金前契約解除(信販否決) / 契約済み(入金待ち)）の行",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("電話番号", "1"), 0),
            0,
            f"電話番号は現状ここを正本とする / 元ソース対象件数 {interview_count}",
        ],
        [
            "会員イベント",
            "名前",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "名前",
            "結果が契約系（成約 / クーリングオフ / 入金前契約解除 / 入金前契約解除(信販否決) / 契約済み(入金待ち)）の行",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("名前", "1"), 0),
            0,
            f"名前の第1優先 / 元ソース対象件数 {interview_count}",
        ],
        [
            "会員イベント",
            "名前",
            "2",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "本名",
            "クーリングオフ かつ 完了",
            status_from_count(cooling_count),
            checked_at,
            fill_counts.get(("名前", "2"), 0),
            0,
            f"名前の補完元 / 元ソース対象件数 {cooling_count}",
        ],
        [
            "会員イベント",
            "名前",
            "3",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "本名",
            "中途解約 かつ 完了",
            status_from_count(cancel_count),
            checked_at,
            fill_counts.get(("名前", "3"), 0),
            0,
            f"名前の補完元 / 元ソース対象件数 {cancel_count}",
        ],
        [
            "会員イベント",
            "LINE名",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "LINE名",
            "結果が契約系（成約 / クーリングオフ / 入金前契約解除 / 入金前契約解除(信販否決) / 契約済み(入金待ち)）の行",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("LINE名", "1"), 0),
            0,
            f"LINE名の第1優先 / 元ソース対象件数 {interview_count}",
        ],
        [
            "会員イベント",
            "LINE名",
            "2",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "LINE名",
            "クーリングオフ かつ 完了",
            status_from_count(cooling_count),
            checked_at,
            fill_counts.get(("LINE名", "2"), 0),
            0,
            f"LINE名の補完元 / 元ソース対象件数 {cooling_count}",
        ],
        [
            "会員イベント",
            "LINE名",
            "3",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "LINE名",
            "中途解約 かつ 完了",
            status_from_count(cancel_count),
            checked_at,
            fill_counts.get(("LINE名", "3"), 0),
            0,
            f"LINE名の補完元。名前列とは別ソースだが上流で同値のことがある / 元ソース対象件数 {cancel_count}",
        ],
        [
            "会員イベント",
            "契約締結日",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "契約締結日",
            "結果が契約系で、契約締結日が入っている行",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("契約締結日", "1"), 0),
            0,
            f"最も早い契約締結日を保持する / 元ソース対象件数 {interview_count}",
        ],
        [
            "会員イベント",
            "入金前契約解除",
            "1",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "結果",
            "結果 = 入金前契約解除",
            status_from_count(interview_count),
            checked_at,
            fill_counts.get(("入金前契約解除", "1"), 0),
            0,
            f"該当時は ○ を入れる / 元ソース対象件数 {interview_count}",
        ],
        [
            "会員イベント",
            "クーリングオフ",
            "1",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "対応完了日",
            "クーリングオフ かつ 完了",
            status_from_count(cooling_count),
            checked_at,
            fill_counts.get(("クーリングオフ", "1"), 0),
            0,
            f"対応完了日を保持する / 元ソース対象件数 {cooling_count}",
        ],
        [
            "会員イベント",
            "中途解約",
            "1",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "対応完了日",
            "中途解約 かつ 完了",
            status_from_count(cancel_count),
            checked_at,
            fill_counts.get(("中途解約", "1"), 0),
            0,
            f"対応完了日を保持する / 元ソース対象件数 {cancel_count}",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["会員イベント", "1行 = 1契約単位で保持する。面談IDがあるものは面談IDで統合し、無いものだけメールアドレス、電話番号、名前系で補助統合する", "同一人物でも複数契約がありえるため、人単位ではなく契約単位を優先する"],
        ["保持対象", "全面談合算で結果が契約系の行だけを保持する", "契約締結日が無いまま解除イベントだけある行は、収集シートには載せない"],
        ["契約締結日", "全面談合算の契約締結日をそのまま入れる", "複数候補がある場合は最も早い契約締結日を採用する"],
        ["入金前契約解除", "全面談合算で結果が入金前契約解除の行がある場合は ○ を入れる", "現状のソースに解除日が無いため、フラグとして保持する"],
        ["クーリングオフ", "お客様相談窓口_進捗管理シートのクーリングオフ完了日を入れる", "定義はマスタデータ / 定義一覧に従う"],
        ["中途解約", "お客様相談窓口_進捗管理シートの中途解約完了日を入れる", "定義はマスタデータ / 定義一覧に従う"],
        ["列の取得優先度", "データソース管理に書かれた優先度順に空欄補完する", "メールアドレス、名前、LINE名は複数ソースから補完する"],
        ["名前とLINE名", "名前とLINE名は別列から取得する", "同じ値になる行があっても自動コピーではなく、上流値が同じだけとみなす"],
        ["共通除外", "【アドネス株式会社】共通除外マスタを参照し、追加日以降に発生した新規データだけ除外する", "過去データは遡って消さない"],
        ["無条件除外", "対象者名やメールアドレスに test / テスト / sample / サンプル / dummy が入るものは除外対象とする", "人を特定せず明らかにテストと分かるものだけに限定する"],
        ["異常時の扱い", "主要ソースの取得件数が 0 の場合は停止として扱い、壊れた値で上書きしない", "データソース管理のステータスで確認する"],
    ]


def main(dry_run: bool = False) -> None:
    gc = get_client()
    target_ss = run_sheets_call_with_retry("会員データ（収集）シート取得", lambda: gc.open_by_key(TARGET_SHEET_ID))
    interview_ss = run_sheets_call_with_retry("全面談合算シート取得", lambda: gc.open_by_key(INTERVIEW_ALL_SHEET_ID))
    support_ss = run_sheets_call_with_retry("お客様相談窓口_進捗管理シート取得", lambda: gc.open_by_key(SUPPORT_PROGRESS_SHEET_ID))
    tabs = ensure_tabs(target_ss)

    interview_tab = run_sheets_call_with_retry("全面談合算タブ取得", lambda: interview_ss.worksheet("全面談合算"))
    cooling_tab = run_sheets_call_with_retry("クーリングオフタブ取得", lambda: support_ss.worksheet("管理用_2025.1.25-クーオフ"))
    cancel_tab = run_sheets_call_with_retry("中途解約タブ取得", lambda: support_ss.worksheet("管理用_20250125-中途解約"))

    interview_records = get_records(interview_tab, header_row=1)
    cooling_records = get_records(cooling_tab, header_row=2)
    cancel_records = get_records(cancel_tab, header_row=2)

    interview_source_count = sum(
        1
        for row in interview_records
        if is_contract_result(row) and (
            get_row_value(row, "契約締結日") or get_row_value(row, "結果") == "入金前契約解除"
        )
    )
    cooling_source_count = sum(
        1
        for row in cooling_records
        if get_row_value(row, "クーリングオフorその他", "中途解約orその他") == "クーリングオフ"
        and get_row_value(row, "ステータス") == "完了"
    )
    cancel_source_count = sum(
        1
        for row in cancel_records
        if get_row_value(row, "中途解約orその他", "クーリングオフorその他") == "中途解約"
        and get_row_value(row, "ステータス") == "完了"
    )

    member_rows, fill_counts = build_member_rows(interview_records, cooling_records, cancel_records)
    checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    data_source_rows = build_data_source_rows(
        interview_tab,
        cooling_tab,
        cancel_tab,
        checked_at=checked_at,
        interview_count=interview_source_count,
        cooling_count=cooling_source_count,
        cancel_count=cancel_source_count,
        event_count=max(0, len(member_rows) - 1),
        fill_counts=fill_counts,
    )
    rule_rows = build_rule_rows()

    if dry_run:
        print("【dry-run】会員イベント 行数:", max(0, len(member_rows) - 1))
        print("【dry-run】全面談合算 対象行数:", interview_source_count)
        print("【dry-run】クーリングオフ 対象行数:", cooling_source_count)
        print("【dry-run】中途解約 対象行数:", cancel_source_count)
        return

    write_rows(tabs["会員イベント"], member_rows)
    style_main_tab(target_ss, tabs["会員イベント"], widths=[220, 140, 140, 140, 140, 170, 150, 140])

    write_rows(tabs["データソース管理"], data_source_rows)
    style_meta_tab(
        target_ss,
        tabs["データソース管理"],
        widths=[110, 140, 70, 230, 190, 130, 240, 90, 140, 90, 90, 280],
        center_cols=[2, 7, 9, 10],
        date_cols=[8],
        status_col=7,
        number_cols=[9, 10],
    )
    apply_status_cell_colors(target_ss, tabs["データソース管理"], data_source_rows, 7)

    write_rows(tabs["データ追加ルール"], rule_rows)
    style_meta_tab(target_ss, tabs["データ追加ルール"], widths=[150, 470, 330])

    print("【アドネス株式会社】会員データ（収集） を会員イベント中心の構成に更新しました。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="会員データ（収集）を更新する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みを行わず件数だけ確認する")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
