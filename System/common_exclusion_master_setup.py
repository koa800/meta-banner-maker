#!/usr/bin/env python3
"""
【アドネス株式会社】共通除外マスタ を初期化する。

- 既存の `【アドネス株式会社】顧客データ_複数イベント（統合） / 除外リスト` を初期データとして移行
- `支払管理表 / 全メンバーリスト` を候補元として明示
- `除外リスト / 無条件除外ルール / データソース管理 / データ追加ルール` を整備
- ヘッダー体裁、フィルタ、入力規則も同時に設定
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import gspread

from sheets_manager import get_client

SOURCE_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
SOURCE_TAB_NAME = "除外リスト"
REFERENCE_SHEET_ID = "19zhRGrA1nWa4oJp4f21Z8cT9bhu2iYe2dEEY2daHBYs"
REFERENCE_SHEET_NAME = "支払管理表"
REFERENCE_TAB_NAME = "全メンバーリスト"

TARGET_SHEET_ID = "1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw"
TARGET_SHEET_TITLE = "【アドネス株式会社】共通除外マスタ"

HEADER_BG = {"red": 0.247, "green": 0.42, "blue": 0.878}
HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}
EXCLUSION_COLUMN_WIDTHS = [220, 120, 150, 110, 90, 95, 180]
UNCONDITIONAL_COLUMN_WIDTHS = [120, 170, 90, 80, 220]
SOURCE_COLUMN_WIDTHS = [110, 150, 220, 120, 90, 90, 120, 80, 220]
RULE_COLUMN_WIDTHS = [110, 340, 260]


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(title)
        worksheet.resize(rows=rows, cols=cols)
        return worksheet
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def rename_or_create_tabs(
    spreadsheet: gspread.Spreadsheet,
) -> tuple[gspread.Worksheet, gspread.Worksheet, gspread.Worksheet, gspread.Worksheet]:
    worksheets = spreadsheet.worksheets()
    if len(worksheets) == 1 and worksheets[0].title == "シート1":
        worksheets[0].update_title("除外リスト")

    exclusion_ws = ensure_worksheet(spreadsheet, "除外リスト", 1000, 7)
    unconditional_ws = ensure_worksheet(spreadsheet, "無条件除外ルール", 50, 5)
    source_ws = ensure_worksheet(spreadsheet, "データソース管理", 50, 9)
    rule_ws = ensure_worksheet(spreadsheet, "データ追加ルール", 50, 3)
    return exclusion_ws, unconditional_ws, source_ws, rule_ws


def build_initial_rows(source_rows: List[List[str]]) -> List[List[str]]:
    migrated_rows: List[List[str]] = [[
        "メールアドレス",
        "電話番号",
        "対象者名",
        "除外理由",
        "適用範囲",
        "追加日",
        "備考",
    ]]

    for row in source_rows[1:]:
        email = row[0].strip() if len(row) > 0 else ""
        phone = row[1].strip() if len(row) > 1 else ""
        name = row[2].strip() if len(row) > 2 else ""
        reason = row[3].strip() if len(row) > 3 else ""
        added_at = row[4].strip() if len(row) > 4 else ""
        migrated_rows.append([email, phone, name, reason, "全体", added_at, ""])
    return migrated_rows


def set_header_style(worksheet: gspread.Worksheet, col_count: int) -> None:
    worksheet.freeze(rows=1)
    end_cell = gspread.utils.rowcol_to_a1(1, col_count)
    worksheet.format(
        f"A1:{end_cell}",
        {
            "backgroundColor": HEADER_BG,
            "textFormat": {"foregroundColor": HEADER_FG, "bold": True, "fontSize": 12},
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )


def set_basic_style(
    exclusion_ws: gspread.Worksheet,
    unconditional_ws: gspread.Worksheet,
    source_ws: gspread.Worksheet,
    rule_ws: gspread.Worksheet,
) -> None:
    set_header_style(exclusion_ws, 7)
    set_header_style(unconditional_ws, 5)
    set_header_style(source_ws, 9)
    set_header_style(rule_ws, 3)

    exclusion_ws.set_basic_filter()
    unconditional_ws.set_basic_filter()
    source_ws.set_basic_filter()
    rule_ws.set_basic_filter()

    exclusion_ws.format(
        "A2:C1000",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    exclusion_ws.format(
        "D2:E1000",
        {"horizontalAlignment": "CENTER", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    exclusion_ws.format(
        "F2:F1000",
        {"horizontalAlignment": "RIGHT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    exclusion_ws.format(
        "G2:G1000",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 9}, "wrapStrategy": "CLIP"},
    )
    unconditional_ws.format(
        "A2:E100",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    unconditional_ws.format(
        "D2:D100",
        {"horizontalAlignment": "CENTER", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )

    source_ws.format(
        "A2:E100",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    source_ws.format(
        "F2:F100",
        {"horizontalAlignment": "CENTER", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    source_ws.format(
        "G2:H100",
        {"horizontalAlignment": "RIGHT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )
    source_ws.format(
        "I2:I100",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )

    rule_ws.format(
        "A2:C100",
        {"horizontalAlignment": "LEFT", "textFormat": {"fontSize": 10}, "wrapStrategy": "CLIP"},
    )


def apply_layout(
    exclusion_ws: gspread.Worksheet,
    unconditional_ws: gspread.Worksheet,
    source_ws: gspread.Worksheet,
    rule_ws: gspread.Worksheet,
) -> None:
    requests = []

    def add_column_widths(worksheet: gspread.Worksheet, widths: List[int]) -> None:
        for idx, width in enumerate(widths):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": worksheet.id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

    def add_row_heights(worksheet: gspread.Worksheet, end_row: int) -> None:
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 34},
                    "fields": "pixelSize",
                }
            }
        )
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": end_row,
                    },
                    "properties": {"pixelSize": 24},
                    "fields": "pixelSize",
                }
            }
        )

    add_column_widths(exclusion_ws, EXCLUSION_COLUMN_WIDTHS)
    add_column_widths(unconditional_ws, UNCONDITIONAL_COLUMN_WIDTHS)
    add_column_widths(source_ws, SOURCE_COLUMN_WIDTHS)
    add_column_widths(rule_ws, RULE_COLUMN_WIDTHS)

    add_row_heights(exclusion_ws, 1000)
    add_row_heights(unconditional_ws, 50)
    add_row_heights(source_ws, 50)
    add_row_heights(rule_ws, 50)

    requests.extend(
        [
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": exclusion_ws.id, "index": 0},
                    "fields": "index",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": unconditional_ws.id, "index": 1},
                    "fields": "index",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": source_ws.id, "index": 2},
                    "fields": "index",
                }
            },
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": rule_ws.id, "index": 3},
                    "fields": "index",
                }
            },
        ]
    )

    exclusion_ws.spreadsheet.batch_update({"requests": requests})


def set_tab_colors(
    exclusion_ws: gspread.Worksheet,
    unconditional_ws: gspread.Worksheet,
    source_ws: gspread.Worksheet,
    rule_ws: gspread.Worksheet,
) -> None:
    exclusion_ws.update_tab_color("#4F86F7")
    unconditional_ws.update_tab_color("#9FD6B5")
    source_ws.update_tab_color("#8FB8FF")
    rule_ws.update_tab_color("#9FD6B5")


def set_validations(exclusion_ws: gspread.Worksheet, unconditional_ws: gspread.Worksheet) -> None:
    sheet_id = exclusion_ws.id
    unconditional_sheet_id = unconditional_ws.id
    requests = [
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": exclusion_ws.row_count,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in ["スタッフ", "テスト", "内部確認", "重複", "その他"]],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": exclusion_ws.row_count,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in ["全体", "集客", "個別予約", "決済", "会員"]],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
        {
            "setDataValidation": {
                "range": {
                    "sheetId": unconditional_sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": unconditional_ws.row_count,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in ["有効", "停止"]],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        },
    ]
    exclusion_ws.spreadsheet.batch_update({"requests": requests})


def main() -> None:
    client = get_client("kohara")
    source_sheet = client.open_by_key(SOURCE_SHEET_ID)
    source_rows = source_sheet.worksheet(SOURCE_TAB_NAME).get_all_values()
    reference_sheet = client.open_by_key(REFERENCE_SHEET_ID)
    reference_rows = reference_sheet.worksheet(REFERENCE_TAB_NAME).get_all_values()

    target_sheet = client.open_by_key(TARGET_SHEET_ID)
    if target_sheet.title != TARGET_SHEET_TITLE:
        target_sheet.update_title(TARGET_SHEET_TITLE)

    exclusion_ws, unconditional_ws, source_ws, rule_ws = rename_or_create_tabs(target_sheet)

    migrated_rows = build_initial_rows(source_rows)
    row_count = len(migrated_rows) - 1
    now_text = datetime.now().strftime("%Y/%m/%d %H:%M")

    exclusion_ws.clear()
    exclusion_ws.update(range_name="A1:G{}".format(len(migrated_rows)), values=migrated_rows)

    unconditional_values = [
        ["判定対象", "一致条件", "適用範囲", "状態", "備考"],
        ["対象者名", "test を含む", "全体", "有効", "大文字小文字を区別せず除外"],
        ["対象者名", "テスト を含む", "全体", "有効", "日本語表記のテストを除外"],
        ["対象者名", "sample を含む", "全体", "有効", "サンプル表記を除外"],
        ["対象者名", "サンプル を含む", "全体", "有効", "日本語表記のサンプルを除外"],
        ["対象者名", "dummy を含む", "全体", "有効", "ダミーデータを除外"],
        ["メールアドレス", "test を含む", "全体", "有効", "メール内のテスト表記を除外"],
        ["メールアドレス", "sample を含む", "全体", "有効", "メール内のサンプル表記を除外"],
        ["メールアドレス", "dummy を含む", "全体", "有効", "メール内のダミー表記を除外"],
    ]
    unconditional_ws.clear()
    unconditional_ws.update(range_name="A1:E{}".format(len(unconditional_values)), values=unconditional_values)

    source_values = [
        ["項目", "ソース元", "スプレッドシートURL", "タブ名", "参照先列", "ステータス", "最終更新", "更新数", "メモ"],
        ["候補元", REFERENCE_SHEET_NAME, f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{REFERENCE_SHEET_ID}/edit","支払管理表")', REFERENCE_TAB_NAME, "A〜最終列", "参照候補", now_text, str(max(len(reference_rows) - 1, 0)), "全員を自動除外しない。除外候補の確認元として使う"],
        ["正本", "【アドネス株式会社】共通除外マスタ", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit","【アドネス株式会社】共通除外マスタ")', "除外リスト", "A〜G列", "手動管理", now_text, str(row_count), "今後の除外追加はこのシートだけで行う"],
        ["共通ルール", "【アドネス株式会社】共通除外マスタ", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit","【アドネス株式会社】共通除外マスタ")', "無条件除外ルール", "A〜E列", "手動管理", now_text, str(len(unconditional_values) - 1), "明らかなテストデータを機械的に除外する"],
    ]
    source_ws.clear()
    source_ws.update(range_name="A1:I{}".format(len(source_values)), values=source_values)

    rule_values = [
        ["項目", "ルール", "補足"],
        ["役割", "このシートを全体の共通除外マスタとして使う", "集客 / 個別予約 / 決済 などで共通参照する前提"],
        ["候補元", "支払管理表 / 全メンバーリスト を除外候補の確認元にする", "全員を自動除外しない。必要な人だけ除外リストへ追加する"],
        ["除外判定", "メールアドレス または 電話番号 が一致した新規データを除外する", "名前だけでは除外判定しない"],
        ["無条件除外", "明らかなテストデータは 無条件除外ルール タブを参照して除外する", "説明ではなく構造化ルールを正本にする"],
        ["適用範囲", "全体 / 集客 / 個別予約 / 決済 / 会員 で管理する", "全体 はすべての集計で除外"],
        ["過去データ", "過去に確定済みの集計値は遡って除外しない", "新しく発生したデータだけ除外判定する"],
        ["初期データ", "【アドネス株式会社】顧客データ_複数イベント（統合） / 除外リスト を移植", "初回整備の履歴として残す"],
        ["手編集", "除外リストタブに追加して管理する", "他シートに個別の除外タブを増やさない"],
        ["今後の切替", "各集計スクリプトは順次このシートを参照する", "まずは CDP と 集客 と 個別予約 から切替候補"],
    ]
    rule_ws.clear()
    rule_ws.update(range_name="A1:C{}".format(len(rule_values)), values=rule_values)

    set_basic_style(exclusion_ws, unconditional_ws, source_ws, rule_ws)
    apply_layout(exclusion_ws, unconditional_ws, source_ws, rule_ws)
    set_tab_colors(exclusion_ws, unconditional_ws, source_ws, rule_ws)
    set_validations(exclusion_ws, unconditional_ws)

    print(f"created {TARGET_SHEET_TITLE} rows={row_count}")


if __name__ == "__main__":
    main()
