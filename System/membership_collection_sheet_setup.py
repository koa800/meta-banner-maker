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

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

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
TAB_COLOR_MAIN = "#1A73E8"
TAB_COLOR_META = "#34A853"

TAB_SPECS = [
    ("会員イベント", 6000, 8),
    ("データソース管理", 50, 10),
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


def ensure_tabs(spreadsheet):
    existing = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered = []
    for title, rows, cols in TAB_SPECS:
        ws = existing.get(title)
        if ws is None:
            ws = spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)
        else:
            if ws.row_count != rows or ws.col_count != cols:
                ws.resize(rows=rows, cols=cols)
        ordered.append(ws)

    target_titles = {spec[0] for spec in TAB_SPECS}
    for title in list(existing):
        if title not in target_titles:
            spreadsheet.del_worksheet(existing[title])

    requests = []
    for idx, ws in enumerate(ordered):
        color = TAB_COLOR_MAIN if ws.title == "会員イベント" else TAB_COLOR_META
        requests.append(set_sheet_properties_request(ws.id, {"index": idx, "hidden": False}, "index,hidden"))
        requests.append(set_sheet_properties_request(ws.id, {"tabColorStyle": {"rgbColor": hex_to_rgb(color)}}, "tabColorStyle"))
    if requests:
        spreadsheet.batch_update({"requests": requests})
    return {ws.title: ws for ws in spreadsheet.worksheets()}


def write_rows(ws, rows: List[List[str]]) -> None:
    ws.clear()
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")


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
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat(horizontalAlignment,verticalAlignment,wrapStrategy)",
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
    spreadsheet.batch_update({"requests": requests})


def style_meta_tab(spreadsheet, ws, widths: List[int], center_cols=None, date_cols=None, status_col=None) -> None:
    center_cols = center_cols or []
    date_cols = date_cols or []
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
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat(horizontalAlignment,verticalAlignment,wrapStrategy)",
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
    for idx, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, idx, idx + 1, width))
    spreadsheet.batch_update({"requests": requests})

    if status_col is not None:
        validation = {
            "condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in STATUS_OPTIONS]},
            "showCustomUi": True,
            "strict": True,
        }
        spreadsheet.batch_update(
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
            }
        )


def normalize_text(value: object) -> str:
    return str(value or "").strip()


def normalize_optional_text(value: object) -> str:
    text = normalize_text(value)
    if text in {"-", "ー", "―", "なし", "無し", "N/A"}:
        return ""
    return text


def normalize_email(value: object) -> str:
    return normalize_optional_text(value).lower()


def normalize_phone(value: object) -> str:
    return (
        normalize_optional_text(value)
        .replace("-", "")
        .replace(" ", "")
        .replace("　", "")
        .replace("+81", "0")
    )


def get_records(ws, header_row: int = 1) -> List[dict]:
    values = ws.get_all_values()
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
            row[header] = raw[idx] if idx < len(raw) else ""
        records.append(row)
    return records


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


def merge_base_fields(member: MemberEventRow, row: dict) -> None:
    email = normalize_email(row.get("メールアドレス") or row.get("アドレス"))
    phone = normalize_phone(row.get("電話番号"))
    name = normalize_optional_text(row.get("名前") or row.get("本名"))
    line_name = normalize_optional_text(row.get("LINE名"))

    if email and not member.email:
        member.email = email
    if phone and not member.phone:
        member.phone = phone
    if name and not member.name:
        member.name = name
    if line_name and not member.line_name:
        member.line_name = line_name


def build_member_rows(interview_records: List[dict], cooling_records: List[dict], cancel_records: List[dict]) -> List[List[str]]:
    merged: Dict[str, MemberEventRow] = {}

    for row in interview_records:
        contract_date = normalize_optional_text(row.get("契約締結日"))
        result = normalize_text(row.get("結果"))
        if not contract_date and result != "入金前契約解除":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(member, row)
        member.contract_date = choose_earliest(member.contract_date, contract_date)
        if result == "入金前契約解除":
            member.pre_payment_cancel = "○"

    for row in cooling_records:
        if normalize_text(row.get("クーリングオフorその他")) != "クーリングオフ":
            continue
        if normalize_text(row.get("ステータス")) != "完了":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(member, row)
        member.cooling_off = choose_earliest(member.cooling_off, normalize_text(row.get("対応完了日")))

    for row in cancel_records:
        if normalize_text(row.get("中途解約orその他")) != "中途解約":
            continue
        if normalize_text(row.get("ステータス")) != "完了":
            continue

        key = build_member_key(row)
        member = merged.setdefault(key, MemberEventRow())
        merge_base_fields(member, row)
        member.mid_term_cancel = choose_earliest(member.mid_term_cancel, normalize_text(row.get("対応完了日")))

    rows = [["メールアドレス", "電話番号", "名前", "LINE名", "契約締結日", "入金前契約解除", "クーリングオフ", "中途解約"]]
    data_rows = [member.to_row() for member in merged.values()]
    data_rows.sort(key=lambda r: (r[4] or "9999/99/99", r[0], r[1], r[3], r[2]))
    rows.extend(data_rows)
    return rows


def build_data_source_rows(interview_tab, cooling_tab, cancel_tab) -> List[List[str]]:
    return [
        ["収集タブ", "ソース元", "参照タブ", "取得条件", "主な取得列", "ステータス", "最終同期日", "更新数", "エラー数", "備考"],
        [
            "会員イベント",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "契約締結日が入っている行、または結果が入金前契約解除の行",
            "面談ID / LINE名 / 名前 / 電話番号 / メールアドレス / 契約締結日 / 結果",
            "未同期",
            "",
            "",
            "",
            "契約締結日は日付、入金前契約解除は現在フラグで保持する",
        ],
        [
            "会員イベント",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "クーリングオフ かつ 完了",
            "面談ID / LINE名 / 本名 / アドレス / 対応完了日 / ステータス",
            "未同期",
            "",
            "",
            "",
            "クーリングオフ列には対応完了日を入れる",
        ],
        [
            "会員イベント",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "中途解約 かつ 完了",
            "面談ID / LINE名 / 本名 / アドレス / 対応完了日 / ステータス",
            "未同期",
            "",
            "",
            "",
            "中途解約列には対応完了日を入れる",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["会員イベント", "1行 = 1契約単位で保持する。面談IDがあるものは面談IDで統合し、無いものだけメールアドレス、電話番号、名前系で補助統合する", "同一人物でも複数契約がありえるため、人単位ではなく契約単位を優先する"],
        ["契約締結日", "全面談合算の契約締結日をそのまま入れる", "複数候補がある場合は最も早い契約締結日を採用する"],
        ["入金前契約解除", "全面談合算で結果が入金前契約解除の行がある場合は ○ を入れる", "現状のソースに解除日が無いため、フラグとして保持する"],
        ["クーリングオフ", "お客様相談窓口_進捗管理シートのクーリングオフ完了日を入れる", "定義はマスタデータ / 定義一覧に従う"],
        ["中途解約", "お客様相談窓口_進捗管理シートの中途解約完了日を入れる", "定義はマスタデータ / 定義一覧に従う"],
        ["共通除外", "【アドネス株式会社】共通除外マスタを参照し、追加日以降に発生した新規データだけ除外する", "過去データは遡って消さない"],
        ["無条件除外", "対象者名やメールアドレスに test / テスト / sample / サンプル / dummy が入るものは除外対象とする", "人を特定せず明らかにテストと分かるものだけに限定する"],
    ]


def main() -> None:
    gc = get_client()
    target_ss = gc.open_by_key(TARGET_SHEET_ID)
    interview_ss = gc.open_by_key(INTERVIEW_ALL_SHEET_ID)
    support_ss = gc.open_by_key(SUPPORT_PROGRESS_SHEET_ID)
    tabs = ensure_tabs(target_ss)

    interview_tab = interview_ss.worksheet("全面談合算")
    cooling_tab = support_ss.worksheet("管理用_2025.1.25-クーオフ")
    cancel_tab = support_ss.worksheet("管理用_20250125-中途解約")

    interview_records = get_records(interview_tab, header_row=1)
    cooling_records = get_records(cooling_tab, header_row=2)
    cancel_records = get_records(cancel_tab, header_row=2)

    member_rows = build_member_rows(interview_records, cooling_records, cancel_records)
    write_rows(tabs["会員イベント"], member_rows)
    style_main_tab(target_ss, tabs["会員イベント"], widths=[200, 130, 130, 130, 120, 120, 130, 130])

    data_source_rows = build_data_source_rows(interview_tab, cooling_tab, cancel_tab)
    write_rows(tabs["データソース管理"], data_source_rows)
    style_meta_tab(
        target_ss,
        tabs["データソース管理"],
        widths=[120, 220, 180, 210, 320, 90, 130, 90, 90, 230],
        center_cols=[5, 7, 8],
        date_cols=[6],
        status_col=5,
    )

    rule_rows = build_rule_rows()
    write_rows(tabs["データ追加ルール"], rule_rows)
    style_meta_tab(
        target_ss,
        tabs["データ追加ルール"],
        widths=[150, 470, 330],
    )

    print("【アドネス株式会社】会員データ（収集） を会員イベント中心の構成に更新しました。")


if __name__ == "__main__":
    main()
