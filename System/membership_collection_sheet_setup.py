#!/usr/bin/env python3
"""
【アドネス株式会社】会員データ（収集）の骨格を整える。

方針:
- 収集データは source system のイベントをそのまま落とす
- 契約 / 入金前契約解除 / クーリングオフ / 中途解約 を別タブで持つ
- 加工ロジックは入れず、データ追加ルールとデータソース管理だけを先に整える
"""

from __future__ import annotations

from typing import Dict, List

from sheets_manager import get_client


TARGET_SHEET_ID = "1VwAO5rxib8pcR7KgGn-T3HKP7FaHqZmUhIBddo3okyw"
INTERVIEW_ALL_SHEET_ID = "1vHWRdYV7nK7qF06Jk7bQ2v4_H_Grcv49Szg-vF-Kanw"
SUPPORT_PROGRESS_SHEET_ID = "1XOkJsXzEx4iV9h8F-cywg0FOS4Knf7IfekN78RZAr6I"
EXCLUSION_MASTER_SHEET_ID = "1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
STATUS_OPTIONS = ["正常", "未同期", "停止"]
TAB_COLOR_EVENT = "#1A73E8"
TAB_COLOR_META = "#34A853"

TAB_SPECS = [
    ("契約イベント", 2000, 9),
    ("入金前契約解除イベント", 2000, 10),
    ("クーリングオフイベント", 2000, 8),
    ("中途解約イベント", 2000, 8),
    ("データソース管理", 50, 11),
    ("データ追加ルール", 50, 3),
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

    if "シート1" in existing and len(spreadsheet.worksheets()) > len(TAB_SPECS):
        spreadsheet.del_worksheet(existing["シート1"])

    requests = []
    for idx, ws in enumerate(ordered):
        color = TAB_COLOR_META if ws.title in ("データソース管理", "データ追加ルール") else TAB_COLOR_EVENT
        requests.append(set_sheet_properties_request(ws.id, {"index": idx, "hidden": False}, "index,hidden"))
        requests.append(set_sheet_properties_request(ws.id, {"tabColorStyle": {"rgbColor": hex_to_rgb(color)}}, "tabColorStyle"))
    if requests:
        spreadsheet.batch_update({"requests": requests})
    return {ws.title: ws for ws in spreadsheet.worksheets()}


def hex_to_rgb(hex_color: str) -> dict:
    hex_color = hex_color.lstrip("#")
    return {
        "red": int(hex_color[0:2], 16) / 255.0,
        "green": int(hex_color[2:4], 16) / 255.0,
        "blue": int(hex_color[4:6], 16) / 255.0,
    }


def write_rows(ws, rows: List[List[str]]) -> None:
    ws.clear()
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")


def style_event_tab(spreadsheet, ws, widths: List[int]) -> None:
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
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
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
                ws.id, 1, ws.row_count, idx, idx + 1,
                {"horizontalAlignment": "CENTER"},
                "userEnteredFormat.horizontalAlignment",
            )
        )
    for idx in date_cols:
        requests.append(
            repeat_cell_request(
                ws.id, 1, ws.row_count, idx, idx + 1,
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


def build_event_headers() -> Dict[str, List[List[str]]]:
    return {
        "契約イベント": [[
            "契約締結日", "顧客ID", "面談ID", "LINE名", "名前", "電話番号", "メールアドレス", "流入経路", "契約プラン"
        ]],
        "入金前契約解除イベント": [[
            "契約締結日", "顧客ID", "面談ID", "LINE名", "名前", "電話番号", "メールアドレス", "流入経路", "結果", "備考"
        ]],
        "クーリングオフイベント": [[
            "対応開始日", "対応完了日", "面談ID", "LINE名", "本名", "アドレス", "解約プロダクト", "ステータス"
        ]],
        "中途解約イベント": [[
            "対応開始日", "対応完了日", "面談ID", "LINE名", "本名", "アドレス", "解約プロダクト", "ステータス"
        ]],
    }


def build_data_source_rows(interview_ss, support_ss) -> List[List[str]]:
    interview_tab = interview_ss.worksheet("全面談合算")
    cooling_tab = support_ss.worksheet("管理用_2025.1.25-クーオフ")
    cancel_tab = support_ss.worksheet("管理用_20250125-中途解約")
    return [
        ["収集タブ", "イベント", "ソース元", "参照タブ", "取得条件", "主な取得列", "ステータス", "最終同期日", "更新数", "エラー数", "備考"],
        [
            "契約イベント",
            "契約",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "契約締結日が入っている行",
            "顧客ID / 面談ID / LINE名 / 名前 / 電話番号 / メールアドレス / 流入経路 / 契約締結日",
            "未同期",
            "",
            "",
            "",
            "契約プランは販売プラン①〜④を加工側で統合する前提",
        ],
        [
            "入金前契約解除イベント",
            "入金前契約解除",
            f'=HYPERLINK("{get_tab_url(INTERVIEW_ALL_SHEET_ID, interview_tab)}","面談記入_DB【全期間】")',
            "全面談合算",
            "結果が入金前契約解除の行",
            "顧客ID / 面談ID / LINE名 / 名前 / 電話番号 / メールアドレス / 流入経路 / 契約締結日 / 結果",
            "未同期",
            "",
            "",
            "",
            "解除日が無いため、日別化の基準は加工時に要確認",
        ],
        [
            "クーリングオフイベント",
            "クーリングオフ",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cooling_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_2025.1.25-クーオフ",
            "クーリングオフ かつ 完了",
            "対応開始日 / 対応完了日 / 面談ID / LINE名 / 本名 / アドレス / 解約プロダクト / ステータス",
            "未同期",
            "",
            "",
            "",
            "クーリングオフ数はお客様相談窓口_進捗管理シートの集計を正とする",
        ],
        [
            "中途解約イベント",
            "中途解約",
            f'=HYPERLINK("{get_tab_url(SUPPORT_PROGRESS_SHEET_ID, cancel_tab)}","お客様相談窓口_進捗管理シート")',
            "管理用_20250125-中途解約",
            "中途解約 かつ 完了",
            "対応開始日 / 対応完了日 / 面談ID / LINE名 / 本名 / アドレス / 解約プロダクト / ステータス",
            "未同期",
            "",
            "",
            "",
            "サポート期間終了前に契約解除が確定した会員数の入口",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["契約イベント", "全面談合算から契約締結日が入っている行だけを取得する", "収集データではソースシステムの列だけを保持し、会員判定は加工で行う"],
        ["入金前契約解除イベント", "全面談合算から結果が入金前契約解除の行だけを取得する", "解除日がソースシステムに無い場合は空欄のまま持ち、加工時に別途判断する"],
        ["クーリングオフイベント", "お客様相談窓口_進捗管理シートの管理用_2025.1.25-クーオフから、クーリングオフかつ完了の行だけを取得する", "クーリングオフ数の定義はマスタデータ / 定義一覧に従う"],
        ["中途解約イベント", "お客様相談窓口_進捗管理シートの管理用_20250125-中途解約から、中途解約かつ完了の行だけを取得する", "中途解約数の定義はマスタデータ / 定義一覧に従う"],
        ["共通除外", "【アドネス株式会社】共通除外マスタを参照し、追加日以降に発生した新規データだけ除外する", "過去データは遡って消さない"],
        ["無条件除外", "対象者名やメールアドレスに test / テスト / sample / サンプル / dummy が入るものは除外対象とする", "人を特定せず明らかにテストと分かるものだけに限定する"],
    ]


def main() -> None:
    gc = get_client()
    target_ss = gc.open_by_key(TARGET_SHEET_ID)
    interview_ss = gc.open_by_key(INTERVIEW_ALL_SHEET_ID)
    support_ss = gc.open_by_key(SUPPORT_PROGRESS_SHEET_ID)
    tabs = ensure_tabs(target_ss)

    event_headers = build_event_headers()
    event_widths = {
        "契約イベント": [120, 90, 90, 150, 130, 140, 190, 170, 160],
        "入金前契約解除イベント": [120, 90, 90, 150, 130, 140, 190, 170, 140, 170],
        "クーリングオフイベント": [130, 130, 90, 150, 130, 190, 120, 90],
        "中途解約イベント": [130, 130, 90, 150, 130, 190, 120, 90],
    }
    for title, rows in event_headers.items():
        write_rows(tabs[title], rows)
        style_event_tab(target_ss, tabs[title], event_widths[title])

    data_source_rows = build_data_source_rows(interview_ss, support_ss)
    write_rows(tabs["データソース管理"], data_source_rows)
    style_meta_tab(
        target_ss,
        tabs["データソース管理"],
        widths=[150, 120, 220, 180, 190, 320, 90, 130, 90, 90, 220],
        center_cols=[1, 6, 8, 9],
        date_cols=[7],
        status_col=6,
    )

    rule_rows = build_rule_rows()
    write_rows(tabs["データ追加ルール"], rule_rows)
    style_meta_tab(
        target_ss,
        tabs["データ追加ルール"],
        widths=[150, 430, 300],
    )

    print("【アドネス株式会社】会員データ（収集） のタブ構成を整えました。")


if __name__ == "__main__":
    main()
