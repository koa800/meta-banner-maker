#!/usr/bin/env python3
"""
【アドネス株式会社】共通除外マスタ を初期化する。

- 既存の `【アドネス株式会社】顧客データ（複数イベント） / 除外リスト` を初期データとして移行
- `除外リスト / データソース管理 / データ追加ルール` の3タブを整備
- ヘッダー体裁、フィルタ、入力規則も同時に設定
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List

import gspread

from sheets_manager import get_client

SOURCE_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
SOURCE_TAB_NAME = "除外リスト"

TARGET_SHEET_ID = "1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw"
TARGET_SHEET_TITLE = "【アドネス株式会社】共通除外マスタ"

HEADER_BG = {"red": 0.247, "green": 0.42, "blue": 0.878}
HEADER_FG = {"red": 1.0, "green": 1.0, "blue": 1.0}


@dataclass
class ExclusionRow:
    exclusion_id: str
    email: str
    phone: str
    lstep_member_id: str
    lstep_account_name: str
    target_name: str
    reason: str
    scope: str
    created_at: str
    note: str

    def to_list(self) -> List[str]:
        return [
            self.exclusion_id,
            self.email,
            self.phone,
            self.lstep_member_id,
            self.lstep_account_name,
            self.target_name,
            self.reason,
            self.scope,
            self.created_at,
            self.note,
        ]


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        worksheet = spreadsheet.worksheet(title)
        worksheet.resize(rows=max(rows, worksheet.row_count), cols=max(cols, worksheet.col_count))
        return worksheet
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def rename_or_create_tabs(spreadsheet: gspread.Spreadsheet) -> tuple[gspread.Worksheet, gspread.Worksheet, gspread.Worksheet]:
    worksheets = spreadsheet.worksheets()
    if len(worksheets) == 1 and worksheets[0].title == "シート1":
        worksheets[0].update_title("除外リスト")

    exclusion_ws = ensure_worksheet(spreadsheet, "除外リスト", 1000, 10)
    source_ws = ensure_worksheet(spreadsheet, "データソース管理", 50, 9)
    rule_ws = ensure_worksheet(spreadsheet, "データ追加ルール", 50, 3)
    return exclusion_ws, source_ws, rule_ws


def build_initial_rows(source_rows: List[List[str]]) -> List[List[str]]:
    migrated_rows: List[List[str]] = [[
        "除外ID",
        "メールアドレス",
        "電話番号",
        "LSTEPメンバーID",
        "Lステップアカウント名",
        "対象者名",
        "除外理由",
        "適用範囲",
        "追加日",
        "備考",
    ]]

    for idx, row in enumerate(source_rows[1:], start=1):
        email = row[0].strip() if len(row) > 0 else ""
        phone = row[1].strip() if len(row) > 1 else ""
        name = row[2].strip() if len(row) > 2 else ""
        reason = row[3].strip() if len(row) > 3 else ""
        added_at = row[4].strip() if len(row) > 4 else ""
        migrated_rows.append(
            ExclusionRow(
                exclusion_id=f"EX{idx:04d}",
                email=email,
                phone=phone,
                lstep_member_id="",
                lstep_account_name="",
                target_name=name,
                reason=reason,
                scope="全体",
                created_at=added_at,
                note="",
            ).to_list()
        )
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


def set_basic_style(exclusion_ws: gspread.Worksheet, source_ws: gspread.Worksheet, rule_ws: gspread.Worksheet) -> None:
    set_header_style(exclusion_ws, 10)
    set_header_style(source_ws, 9)
    set_header_style(rule_ws, 3)

    exclusion_ws.set_basic_filter()
    source_ws.set_basic_filter()
    rule_ws.set_basic_filter()

    exclusion_ws.columns_auto_resize(1, 10)
    source_ws.columns_auto_resize(1, 9)
    rule_ws.columns_auto_resize(1, 3)


def set_tab_colors(exclusion_ws: gspread.Worksheet, source_ws: gspread.Worksheet, rule_ws: gspread.Worksheet) -> None:
    exclusion_ws.update_tab_color("#4F86F7")
    source_ws.update_tab_color("#8FB8FF")
    rule_ws.update_tab_color("#9FD6B5")


def set_validations(exclusion_ws: gspread.Worksheet) -> None:
    spreadsheet_id = exclusion_ws.spreadsheet.id
    sheet_id = exclusion_ws.id
    requests = [
        {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": exclusion_ws.row_count,
                    "startColumnIndex": 6,
                    "endColumnIndex": 7,
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
                    "startColumnIndex": 7,
                    "endColumnIndex": 8,
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
    ]
    exclusion_ws.spreadsheet.batch_update({"requests": requests})


def main() -> None:
    client = get_client("kohara")
    source_sheet = client.open_by_key(SOURCE_SHEET_ID)
    source_rows = source_sheet.worksheet(SOURCE_TAB_NAME).get_all_values()

    target_sheet = client.open_by_key(TARGET_SHEET_ID)
    if target_sheet.title != TARGET_SHEET_TITLE:
        target_sheet.update_title(TARGET_SHEET_TITLE)

    exclusion_ws, source_ws, rule_ws = rename_or_create_tabs(target_sheet)

    migrated_rows = build_initial_rows(source_rows)
    row_count = len(migrated_rows) - 1
    now_text = datetime.now().strftime("%Y/%m/%d %H:%M")

    exclusion_ws.clear()
    exclusion_ws.update(range_name="A1:J{}".format(len(migrated_rows)), values=migrated_rows)

    source_values = [
        ["項目", "ソース元", "スプレッドシートURL", "タブ名", "参照先列", "ステータス", "最終更新", "更新数", "メモ"],
        ["初期データ", "【アドネス株式会社】顧客データ（複数イベント）", f"https://docs.google.com/spreadsheets/d/{SOURCE_SHEET_ID}/edit", "除外リスト", "A〜E列", "初期化済み", now_text, str(row_count), "既存の除外リストを初期データとして移行"],
        ["継続運用", "【アドネス株式会社】共通除外マスタ", f"https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit", "除外リスト", "A〜J列", "手動管理", now_text, str(row_count), "今後の除外追加はこのシートだけで行う"],
    ]
    source_ws.clear()
    source_ws.update(range_name="A1:I{}".format(len(source_values)), values=source_values)

    rule_values = [
        ["項目", "ルール", "補足"],
        ["役割", "このシートを全体の共通除外マスタとして使う", "集客 / 個別予約 / 決済 などで共通参照する前提"],
        ["除外判定", "メールアドレス / 電話番号 / LSTEPメンバーID + Lステップアカウント名 のいずれか一致で除外候補にする", "名前だけでは除外判定しない"],
        ["適用範囲", "全体 / 集客 / 個別予約 / 決済 / 会員 で管理する", "全体 はすべての集計で除外"],
        ["初期データ", "【アドネス株式会社】顧客データ（複数イベント） / 除外リスト を移植", "今後はここを正本にする"],
        ["手編集", "除外リストタブに追加して管理する", "他シートに個別の除外タブを増やさない"],
        ["今後の切替", "各集計スクリプトは順次このシートを参照する", "まずは CDP と 集客 と 個別予約 から切替候補"],
    ]
    rule_ws.clear()
    rule_ws.update(range_name="A1:C{}".format(len(rule_values)), values=rule_values)

    set_basic_style(exclusion_ws, source_ws, rule_ws)
    set_tab_colors(exclusion_ws, source_ws, rule_ws)
    set_validations(exclusion_ws)

    print(f"created {TARGET_SHEET_TITLE} rows={row_count}")


if __name__ == "__main__":
    main()
