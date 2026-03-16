#!/usr/bin/env python3
"""
【アドネス株式会社】個別面談データ を再生成する。

第1版の方針:
- 現行の正本候補は `【アドネス】顧客管理シート / 個別予約集計botログ`
- `個別予約数` だけを先に接続する
- `個別予約数（UU）` は将来用の枠だけを作り、今は未接続にする
- `★【個別予約完了】★` は現時点では日別件数の正本に使わず、将来の通知ログ正本候補として扱う
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Sequence

from gspread.exceptions import APIError
from sheets_manager import get_client


SOURCE_SHEET_ID = "1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo"
SOURCE_TAB_NAME = "個別予約集計botログ"
TARGET_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】個別面談データ"
NOTIFICATION_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "booking_notification_log_state.json")

COUNT_TAB_NAME = "日別個別予約数"
UU_TAB_NAME = "日別個別予約数（UU）"
SUMMARY_TAB_NAME = "個別予約サマリー"
TAG_TAB_NAME = "タグ検証"
NOTIFICATION_LOG_TAB_NAME = "個別予約通知ログ"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    COUNT_TAB_NAME: (500, 3),
    UU_TAB_NAME: (500, 3),
    SUMMARY_TAB_NAME: (60, 3),
    TAG_TAB_NAME: (60, 3),
    SOURCE_MANAGEMENT_TAB_NAME: (60, 14),
    RULE_TAB_NAME: (60, 3),
}

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}

TAB_COLORS = {
    COUNT_TAB_NAME: "#1A73E8",
    UU_TAB_NAME: "#1A73E8",
    SUMMARY_TAB_NAME: "#FBBC04",
    TAG_TAB_NAME: "#A142F4",
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}

STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "一部接続": {"backgroundColor": {"red": 1, "green": 0.949, "blue": 0.8}},
    "未接続": {"backgroundColor": {"red": 1, "green": 0.949, "blue": 0.8}},
    "未同期": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
    "確認待ち": {"backgroundColor": {"red": 0.925, "green": 0.89, "blue": 0.992}},
}

PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "個別面談データ自動生成"

DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")
WRITE_RETRY_SECONDS = (5, 10, 20, 40)


@dataclass
class BookingRecord:
    booking_date: str
    line_name: str
    route_name: str
    cancelled: bool
    customer_name: str
    tag_name: str
    email: str
    cr_name: str
    booking_account_name: str
    phone_number: str


@dataclass
class DailyCountRecord:
    date: str
    count: int
    cumulative_count: int


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def repeat_cell_request(
    sheet_id: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    fmt: dict,
    fields: str,
) -> dict:
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


def normalize_date(raw: str) -> str:
    value = str(raw or "").strip()
    return value if DATE_RE.match(value) else ""


def pad_rows(rows: List[List[str]], min_rows: int, min_cols: int) -> List[List[str]]:
    padded = [row + [""] * max(0, min_cols - len(row)) for row in rows]
    while len(padded) < min_rows:
        padded.append([""] * min_cols)
    return padded


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
            print(
                f"{description}: Sheets の書き込み回数制限に当たったため "
                f"{wait_seconds or 0}秒後に再試行します。"
            )
    if last_error:
        raise last_error


def batch_update_with_retry(spreadsheet, body: dict, description: str) -> None:
    run_write_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_write_with_retry(description, func)


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
        "個別面談データのシート名更新",
    )


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}

    if "シート1" in tabs and len(tabs) == 1:
        worksheet_write_with_retry(
            "個別面談データの初期タブ名変更",
            lambda: tabs["シート1"].update_title(COUNT_TAB_NAME),
        )
        tabs[COUNT_TAB_NAME] = tabs.pop("シート1")

    for name, (rows, cols) in TAB_SPECS.items():
        if name in tabs:
            ws = tabs[name]
            if ws.row_count < rows:
                worksheet_write_with_retry(
                    f"{name} の行数拡張",
                    lambda ws=ws, rows=rows: ws.add_rows(rows - ws.row_count),
                )
            if ws.col_count < cols:
                worksheet_write_with_retry(
                    f"{name} の列数拡張",
                    lambda ws=ws, cols=cols: ws.add_cols(cols - ws.col_count),
                )
            continue
        tabs[name] = run_write_with_retry(
            f"{name} タブの作成",
            lambda name=name, rows=rows, cols=cols: spreadsheet.add_worksheet(
                title=name, rows=rows, cols=cols
            ),
        )

    return tabs


def write_rows(spreadsheet, ws, rows: List[List[str]]) -> None:
    max_cols = max((len(row) for row in rows), default=1)
    padded = pad_rows(rows, len(rows), max_cols)
    end_cell = f"{col_letter(max_cols)}{len(padded)}"
    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                {
                    "unmergeCells": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 0,
                            "endRowIndex": ws.row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": ws.col_count,
                        }
                    }
                }
            ]
        },
        f"{ws.title} の結合解除",
    )
    worksheet_write_with_retry(f"{ws.title} の既存データ削除", ws.clear)
    worksheet_write_with_retry(
        f"{ws.title} の書き込み",
        lambda: ws.update(range_name=f"A1:{end_cell}", values=padded, value_input_option="USER_ENTERED"),
    )


def apply_table_style(spreadsheet, ws, row_count: int, col_count: int, widths: Iterable[int]) -> None:
    requests = [
        {
            "unmergeCells": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 0,
                    "endRowIndex": ws.row_count,
                    "startColumnIndex": 0,
                    "endColumnIndex": ws.col_count,
                }
            }
        },
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            col_count,
            {
                "backgroundColor": HEADER_BG,
                "textFormat": HEADER_TEXT,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        repeat_cell_request(
            ws.id,
            1,
            row_count,
            0,
            col_count,
            {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
            "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    }
                }
            }
        },
        {
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "tabColor": {"red": 1, "green": 1, "blue": 1}},
                "fields": "tabColor",
            }
        },
    ]

    for index, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, index, index + 1, width))

    if ws.title in TAB_COLORS:
        hex_color = TAB_COLORS[ws.title].lstrip("#")
        rgb = {
            "red": int(hex_color[0:2], 16) / 255.0,
            "green": int(hex_color[2:4], 16) / 255.0,
            "blue": int(hex_color[4:6], 16) / 255.0,
        }
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "tabColor": rgb},
                    "fields": "tabColor",
                }
            }
        )

    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の表スタイル適用")
    worksheet_write_with_retry(f"{ws.title} のヘッダー固定", lambda: ws.freeze(rows=1))


def apply_number_formats(spreadsheet, requests: Sequence[dict]) -> None:
    if requests:
        batch_update_with_retry(
            spreadsheet,
            {"requests": list(requests)},
            "個別面談データの数値書式適用",
        )


def apply_status_cell_colors(spreadsheet, ws, rows: Sequence[Sequence[str]], status_col_index: int) -> None:
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
        batch_update_with_retry(
            spreadsheet,
            {"requests": requests},
            f"{ws.title} のステータス色適用",
        )


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
        batch_update_with_retry(
            spreadsheet,
            {"requests": requests},
            "個別面談データの保護設定",
        )


def load_booking_rows() -> List[BookingRecord]:
    gc = get_client()
    source = gc.open_by_key(SOURCE_SHEET_ID)
    ws = source.worksheet(SOURCE_TAB_NAME)
    values = ws.get_all_values()

    header_index = None
    for idx, row in enumerate(values[:20]):
        if "キャンセル" in row and "LINE名" in row:
            header_index = idx
            break
    if header_index is None:
        raise RuntimeError("個別予約集計botログのヘッダー行を特定できません。")

    records: List[BookingRecord] = []
    for raw in values[header_index + 1 :]:
        row = raw + [""] * max(0, 13 - len(raw))
        booking_date = normalize_date(row[0])
        cancelled = row[3].strip().upper()
        has_identity = any(str(row[idx]).strip() for idx in (1, 4, 6, 12) if idx < len(row))
        if not booking_date or cancelled not in {"TRUE", "FALSE"} or not has_identity:
            continue
        records.append(
            BookingRecord(
                booking_date=booking_date,
                line_name=str(row[1]).strip(),
                route_name=str(row[2]).strip(),
                cancelled=cancelled == "TRUE",
                customer_name=str(row[4]).strip(),
                tag_name=str(row[5]).strip(),
                email=str(row[6]).strip(),
                cr_name=str(row[7]).strip(),
                booking_account_name=str(row[8]).strip(),
                phone_number=str(row[12]).strip(),
            )
        )
    return records


def build_daily_records(records: Sequence[BookingRecord]) -> List[DailyCountRecord]:
    daily = Counter()
    for record in records:
        if record.cancelled:
            continue
        daily[record.booking_date] += 1

    result: List[DailyCountRecord] = []
    cumulative = 0
    for date in sorted(daily):
        cumulative += daily[date]
        result.append(DailyCountRecord(date=date, count=daily[date], cumulative_count=cumulative))
    return result


def build_stats(records: Sequence[BookingRecord], daily_records: Sequence[DailyCountRecord]) -> Dict[str, object]:
    non_cancelled = [record for record in records if not record.cancelled]
    account_counter = Counter(record.booking_account_name for record in non_cancelled if record.booking_account_name)
    latest_date = max((record.booking_date for record in records), default="")
    updated_at = datetime.now().strftime("%Y/%m/%d %H:%M")

    status = "正常"
    if latest_date:
        try:
            gap = (datetime.now().date() - datetime.strptime(latest_date, "%Y/%m/%d").date()).days
            if gap >= 7:
                status = "未同期"
        except ValueError:
            status = "未同期"
    else:
        status = "未接続"

    return {
        "updated_at": updated_at,
        "total_booking_count": len(non_cancelled),
        "total_cancel_count": sum(1 for record in records if record.cancelled),
        "start_date": daily_records[0].date if daily_records else "",
        "latest_date": daily_records[-1].date if daily_records else "",
        "daily_row_count": len(daily_records),
        "booking_account_count": len(account_counter),
        "blank_account_count": sum(1 for record in non_cancelled if not record.booking_account_name),
        "status": status,
    }


def build_summary_rows(stats: Dict[str, object]) -> List[List[str]]:
    return [
        ["項目", "数値", "定義"],
        ["更新日時", f"'{stats['updated_at']}", "このシートを作り直した時刻"],
        ["個別予約数", f"{int(stats['total_booking_count']):,}", "現行は個別予約集計botログのうち、キャンセルを除いた個別予約イベント数"],
        ["個別予約数（UU）", "", "将来接続。LSTEP通知ログとLINE統合後の同一人物判定で持つ"],
        ["キャンセル数", f"{int(stats['total_cancel_count']):,}", "個別予約集計botログでキャンセル=TRUE の件数"],
        ["集計開始日", f"'{stats['start_date']}", "日別個別予約数の最初の日付"],
        ["最新集計日", f"'{stats['latest_date']}", "日別個別予約数の最新の日付"],
        ["予約アカウント名あり件数", f"{int(stats['booking_account_count']):,}", "予約アカウント名が入っているユニークアカウント数"],
        ["予約アカウント名空欄件数", f"{int(stats['blank_account_count']):,}", "キャンセル除外後も予約アカウント名が空欄の行数"],
    ]


def build_tag_rows() -> List[List[str]]:
    return [
        ["項目", "状態", "内容"],
        ["対象タグ", "確認済み", "★【個別予約完了】★"],
        ["付与条件1", "確認済み", "ユーザーがカレンダー予約で指定コースを予約した時に付与される"],
        ["付与条件2", "確認済み", "ユーザーがLステップのイベント予約で予約した時に付与される"],
        ["タグの性質1", "確認済み", "一度付いたら外さない"],
        ["タグの性質2", "確認済み", "再予約してもタグ数は増えない"],
        ["今の役割", "確認済み", "個別予約を一度でもしたユーザーの累積確認"],
        ["今の限界", "確認済み", "タグ単体では日別の予約イベント数を正確に取れない"],
        ["将来の役割", "確認待ち", "タグ付与の通知を1イベント1行で蓄積し、個別予約イベントの正本候補にする"],
        ["通知で取りたい項目", "確認待ち", "タグ付与日時 / LINE名 / LSTEPメンバーID / Lステップアカウント名 / 予約導線種別"],
        ["通知の送信先", "確認済み", "Slack #個別予約通知 を第1候補にする"],
        ["確認対象アカウント", "確認待ち", "スキルプラス@企画専用 / 【スキルプラス】フリープラン / みかみ@個別専用 / みかみ@AI_個別専用 / 【みかみ】アドネス株式会社"],
    ]


def load_notification_log_stats(target) -> Dict[str, str]:
    try:
        ws = target.worksheet(NOTIFICATION_LOG_TAB_NAME)
    except Exception:
        return {
            "ステータス": "未接続",
            "最終同期日": "",
            "更新数": "",
            "エラー数": "",
            "メモ": "通知ログタブ未作成",
        }

    values = ws.get_all_values()
    event_count = 0
    for row in values[1:]:
        row = row + [""] * max(0, 8 - len(row))
        if any(str(cell).strip() for cell in row[:6]):
            event_count += 1
    state = {}
    if os.path.exists(NOTIFICATION_STATE_PATH):
        try:
            with open(NOTIFICATION_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}

    latest_imported_at = str(state.get("updated_at") or "").strip()

    if event_count == 0:
        return {
            "ステータス": "未接続",
            "最終同期日": latest_imported_at,
            "更新数": "0",
            "エラー数": "0",
            "メモ": "Slack通知の取込待ち",
        }

    return {
        "ステータス": "正常" if event_count else "未接続",
        "最終同期日": latest_imported_at,
        "更新数": f"{event_count:,}" if event_count else "0",
        "エラー数": "0",
        "メモ": "Slack #個別予約通知 から取り込んだ通知ログ",
    }


def build_source_rows(stats: Dict[str, object], notification_stats: Dict[str, str]) -> List[List[str]]:
    return [
        ["KPIカラム", "グループ", "ソース元", "優先度", "スプレッドシートURL", "タブ名", "参照先列", "正規化 / 計算", "入力条件", "ステータス", "最終同期日", "更新数", "エラー数", "メモ"],
        [
            "個別予約数",
            "個別予約",
            "収集データ",
            "1",
            f"https://docs.google.com/spreadsheets/d/{SOURCE_SHEET_ID}/edit",
            SOURCE_TAB_NAME,
            "A列,D列,G列,I列,M列",
            "日付あり and キャンセル=FALSE",
            "2025/01/01以降",
            str(stats["status"]),
            str(stats["updated_at"]),
            f"{int(stats['total_booking_count']):,}",
            "0",
            "現行の計上元。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する",
        ],
        [
            "個別予約数（UU）",
            "個別予約",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "未接続",
            "",
            "",
            "",
            "LINE統合前は同一人物判定が弱いため未接続",
        ],
        [
            "個別予約通知ログ",
            "個別予約",
            "Lステップ通知機能",
            "2",
            f"https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit",
            NOTIFICATION_LOG_TAB_NAME,
            "A〜H列",
            "Slack 通知を 1イベント1行で保存",
            "★【個別予約完了】★ が付いた時に通知",
            notification_stats["ステータス"],
            notification_stats["最終同期日"],
            notification_stats["更新数"],
            notification_stats["エラー数"],
            notification_stats["メモ"],
        ],
        [
            "タグ検証",
            "検証",
            "Lステップ",
            "1",
            "",
            "タグ管理",
            "タグ名",
            "★【個別予約完了】★ を確認",
            "ブラウザ確認後に確定",
            "確認待ち",
            "",
            "",
            "",
            "タグは正本ではなく検証用",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["変えないもの", "個別予約数は予約イベント数として数える", "同じ人が別日に再予約したら別件数で数える"],
        ["変えないもの2", "★【個別予約完了】★ は予約完了の成立条件として扱う", "一度付いたら外れず、再予約でも増えない"],
        ["変えるもの", "botログ固定ではなく、通知ログを本命の計上元へ段階移行する", "現行は botログ、将来は Slack 通知ログ"],
        ["追加するもの", "個別予約通知ログを 1イベント1行で持つ", "Slack #個別予約通知 の bot 通知を取り込む"],
        ["個別予約数", "現行は【アドネス】顧客管理シート / 個別予約集計botログ を使う", "日付あり and キャンセル=FALSE の行だけを数える"],
        ["個別予約通知ログ", "将来は Lステップ の通知機能で ★【個別予約完了】★ の付与を1イベント1行で溜める", "まずは Slack の専用チャンネルに集約し、難しい時だけ Chatwork を使う"],
        ["個別予約数（UU）", "第1版ではまだ接続しない", "LINE統合や名寄せ方針が固まってから入れる"],
        ["タグ", "★【個別予約完了】★ は今は検証用、将来は通知ログのトリガーに使う", "タグ単体は累積状態なので日別件数の正本には使わない"],
        ["手編集", "このシートの自動生成タブは手編集しない", "更新はスクリプトから行う"],
        ["異常検知", "最新集計日が古い時は未同期として扱う", "今は source 側の最新日を見て判定する"],
    ]


def write_target(daily_records: Sequence[DailyCountRecord], stats: Dict[str, object]) -> None:
    gc = get_client()
    target = gc.open_by_key(TARGET_SHEET_ID)
    ensure_spreadsheet_title(target)
    tabs = ensure_tabs(target)
    notification_stats = load_notification_log_stats(target)

    count_rows = [["日付", "個別予約数", "累計個別予約数"]]
    count_rows.extend([[record.date, f"{record.count:,}", f"{record.cumulative_count:,}"] for record in daily_records])
    count_rows = pad_rows(count_rows, 120, 3)

    uu_rows = [["日付", "個別予約数（UU）", "累計個別予約数（UU）"]]
    uu_rows = pad_rows(uu_rows, 120, 3)

    summary_rows = pad_rows(build_summary_rows(stats), 20, 3)
    tag_rows = pad_rows(build_tag_rows(), 20, 3)
    source_rows = pad_rows(build_source_rows(stats, notification_stats), 20, 14)
    rule_rows = pad_rows(build_rule_rows(), 20, 3)

    write_rows(target, tabs[COUNT_TAB_NAME], count_rows)
    write_rows(target, tabs[UU_TAB_NAME], uu_rows)
    write_rows(target, tabs[SUMMARY_TAB_NAME], summary_rows)
    write_rows(target, tabs[TAG_TAB_NAME], tag_rows)
    write_rows(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows)
    write_rows(target, tabs[RULE_TAB_NAME], rule_rows)

    apply_table_style(target, tabs[COUNT_TAB_NAME], len(count_rows), 3, [140, 160, 180])
    apply_table_style(target, tabs[UU_TAB_NAME], len(uu_rows), 3, [140, 180, 200])
    apply_table_style(target, tabs[SUMMARY_TAB_NAME], len(summary_rows), 3, [220, 160, 420])
    apply_table_style(target, tabs[TAG_TAB_NAME], len(tag_rows), 3, [180, 120, 520])
    apply_table_style(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], len(source_rows), 14, [150, 110, 110, 70, 260, 160, 150, 220, 140, 90, 140, 90, 80, 260])
    apply_table_style(target, tabs[RULE_TAB_NAME], len(rule_rows), 3, [180, 360, 320])

    number_format_requests = [
        repeat_cell_request(
            tabs[COUNT_TAB_NAME].id,
            1,
            len(count_rows),
            1,
            3,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
            "userEnteredFormat.numberFormat",
        ),
        repeat_cell_request(
            tabs[UU_TAB_NAME].id,
            1,
            len(uu_rows),
            1,
            3,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
            "userEnteredFormat.numberFormat",
        ),
        repeat_cell_request(
            tabs[SUMMARY_TAB_NAME].id,
            1,
            len(summary_rows),
            1,
            2,
            {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
            "userEnteredFormat.numberFormat",
        ),
    ]
    apply_number_formats(target, number_format_requests)
    apply_status_cell_colors(target, tabs[TAG_TAB_NAME], tag_rows, 1)
    apply_status_cell_colors(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows, 9)
    apply_protections(target, tabs)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="【アドネス株式会社】個別面談データを再生成する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みは行わず、集計結果だけ確認する")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    records = load_booking_rows()
    daily_records = build_daily_records(records)
    stats = build_stats(records, daily_records)
    if args.dry_run:
        print(
            "dry-run: "
            f"個別予約数={stats['total_booking_count']:,}, "
            f"キャンセル数={stats['total_cancel_count']:,}, "
            f"開始日={stats['start_date']}, "
            f"最新日={stats['latest_date']}, "
            f"ステータス={stats['status']}"
        )
        return
    write_target(daily_records, stats)
    print("【アドネス株式会社】個別面談データの第1版を更新しました。")


if __name__ == "__main__":
    main()
