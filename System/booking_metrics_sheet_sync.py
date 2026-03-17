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
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Sequence

from gspread.exceptions import APIError
from sheets_manager import get_client


SOURCE_SHEET_ID = "1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo"
SOURCE_TAB_NAME = "個別予約集計botログ"
TARGET_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】個別面談データ"
NOTIFICATION_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "booking_notification_log_state.json")
SLACK_FALLBACK_START_DATE = "2026/03/17"

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
DATE_PREFIX_RE = re.compile(r"^(\d{4}[/-]\d{2}[/-]\d{2})")
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


@dataclass
class NotificationEvent:
    tagged_at: datetime
    line_name: str
    member_id: str
    account_name: str
    email: str
    phone: str


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
    if DATE_RE.match(value):
        return value
    for fmt in ("%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y/%m/%d")
        except ValueError:
            pass
    match = DATE_PREFIX_RE.match(value)
    if match:
        return match.group(1).replace("-", "/")
    return ""


def normalize_datetime(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


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


def notification_identity_key(event: NotificationEvent) -> str:
    if event.member_id and event.account_name:
        return f"member:{event.account_name}|{event.member_id}"
    if event.email:
        return f"email:{event.email.lower()}"
    if event.phone:
        digits = re.sub(r"\D", "", event.phone)
        return f"phone:{digits}" if digits else f"phone:{event.phone}"
    return f"line:{event.account_name}|{event.line_name}"


def load_notification_events() -> List[NotificationEvent]:
    gc = get_client()
    target = gc.open_by_key(TARGET_SHEET_ID)
    try:
        ws = target.worksheet(NOTIFICATION_LOG_TAB_NAME)
    except Exception:
        return []

    events: List[NotificationEvent] = []
    values = ws.get_all_values()
    for raw in values[1:]:
        row = raw + [""] * max(0, 7 - len(raw))
        event_at = normalize_datetime(row[0])
        if not event_at:
            continue
        if not any(str(cell).strip() for cell in row[:7]):
            continue
        events.append(
            NotificationEvent(
                tagged_at=event_at,
                line_name=str(row[1]).strip(),
                member_id=str(row[2]).strip(),
                account_name=str(row[3]).strip(),
                email=str(row[5]).strip(),
                phone=str(row[6]).strip(),
            )
        )
    return events


def build_notification_daily_counts(events: Sequence[NotificationEvent]) -> Counter:
    grouped: Dict[tuple[str, str], List[NotificationEvent]] = defaultdict(list)
    for event in events:
        if event.tagged_at.strftime("%Y/%m/%d") < SLACK_FALLBACK_START_DATE:
            continue
        grouped[(event.tagged_at.strftime("%Y/%m/%d"), notification_identity_key(event))].append(event)

    daily = Counter()
    for (date, _identity), items in grouped.items():
        items = sorted(items, key=lambda x: x.tagged_at)
        cluster_start = items[0].tagged_at
        cluster_last = items[0].tagged_at
        count = 1
        for item in items[1:]:
            gap_seconds = (item.tagged_at - cluster_last).total_seconds()
            if gap_seconds <= 600:
                cluster_last = item.tagged_at
                continue
            count += 1
            cluster_start = item.tagged_at
            cluster_last = item.tagged_at
        daily[date] += count
    return daily


def build_daily_records(records: Sequence[BookingRecord], notification_daily: Counter) -> tuple[List[DailyCountRecord], Dict[str, str]]:
    botlog_daily = Counter()
    for record in records:
        if record.cancelled:
            continue
        botlog_daily[record.booking_date] += 1

    latest_botlog_date = max(botlog_daily, default="")
    latest_notification_date = max(notification_daily, default="")
    merged_daily = Counter(botlog_daily)
    notification_fallback_start = ""
    for date in sorted(notification_daily):
        if date < SLACK_FALLBACK_START_DATE:
            continue
        if not notification_fallback_start:
            notification_fallback_start = date
        merged_daily[date] = notification_daily[date]

    result: List[DailyCountRecord] = []
    cumulative = 0
    if merged_daily:
        start_date = datetime.strptime(min(merged_daily), "%Y/%m/%d").date()
        end_date = datetime.strptime(max(merged_daily), "%Y/%m/%d").date()
        current = start_date
        while current <= end_date:
            date = current.strftime("%Y/%m/%d")
            count = merged_daily.get(date, 0)
            cumulative += count
            result.append(DailyCountRecord(date=date, count=count, cumulative_count=cumulative))
            current += timedelta(days=1)
    meta = {
        "latest_botlog_date": latest_botlog_date,
        "latest_notification_date": latest_notification_date,
        "notification_fallback_start": notification_fallback_start,
    }
    return result, meta


def build_stats(
    records: Sequence[BookingRecord],
    daily_records: Sequence[DailyCountRecord],
    daily_meta: Dict[str, str],
) -> Dict[str, object]:
    non_cancelled = [record for record in records if not record.cancelled]
    account_counter = Counter(record.booking_account_name for record in non_cancelled if record.booking_account_name)
    latest_date = daily_records[-1].date if daily_records else ""
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
        "total_booking_count": sum(record.count for record in daily_records),
        "botlog_booking_count": len(non_cancelled),
        "total_cancel_count": sum(1 for record in records if record.cancelled),
        "start_date": daily_records[0].date if daily_records else "",
        "latest_date": latest_date,
        "daily_row_count": len(daily_records),
        "booking_account_count": len(account_counter),
        "blank_account_count": sum(1 for record in non_cancelled if not record.booking_account_name),
        "status": status,
        "latest_botlog_date": daily_meta.get("latest_botlog_date", ""),
        "latest_notification_date": daily_meta.get("latest_notification_date", ""),
        "notification_fallback_start": daily_meta.get("notification_fallback_start", ""),
    }


def build_summary_rows(stats: Dict[str, object]) -> List[List[str]]:
    booking_definition = "現行は個別予約集計botログのうち、キャンセルを除いた個別予約イベント数"
    fallback_start = str(stats.get("notification_fallback_start") or "").strip()
    latest_botlog_date = str(stats.get("latest_botlog_date") or "").strip()
    if fallback_start:
        booking_definition = (
            f"{latest_botlog_date or 'botログの最新日'} までは個別予約集計botログ、"
            f"{fallback_start} 以降は個別予約通知ログで補完した個別予約イベント数"
        )
    return [
        ["項目", "数値", "定義"],
        ["更新日時", f"'{stats['updated_at']}", "このシートを作り直した時刻"],
        ["個別予約数", f"{int(stats['total_booking_count']):,}", booking_definition],
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
        ["今の役割", "確認済み", "個別予約を一度でもしたユーザーの累積確認と、予約導線が正しく発火したかの検証"],
        ["今の限界", "確認済み", "タグ単体では日別の予約イベント数を正確に取れない"],
        ["本命の通知条件", "確認待ち", "salon_reservation_reserved / reservation.reserved の予約イベント通知を優先候補として監査する"],
        ["将来の役割", "確認待ち", "予約イベント通知を1イベント1行で蓄積し、個別予約イベントの本命正本候補にする"],
        ["タグ通知の役割", "確認済み", "★【個別予約完了】★ の通知は冗長系と検証用として残す"],
        ["通知で取りたい項目", "確認待ち", "予約イベント日時 / LINE名 / LSTEPメンバーID / Lステップアカウント名 / 通知リンク"],
        ["通知の送信先", "確認済み", "Slack #個別予約通知 を第1候補にし、必要なら予約イベント専用チャンネルを追加する"],
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
        row = row + [""] * max(0, 7 - len(row))
        if any(str(cell).strip() for cell in row[:7]):
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
            "メモ": "Slack #個別予約通知 と 過去の個別予約データ を統合。LSTEPメンバーIDで友だち一覧CSVに一致した時はメールアドレス / 電話番号も補完する",
        }


def build_source_rows(stats: Dict[str, object], notification_stats: Dict[str, str]) -> List[List[str]]:
    latest_botlog_date = str(stats.get("latest_botlog_date") or "").strip()
    fallback_start = str(stats.get("notification_fallback_start") or "").strip()
    booking_calc = "日付あり and キャンセル=FALSE"
    booking_condition = "2025/01/01以降"
    booking_memo = "現行の計上元。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する"
    if fallback_start:
        booking_calc = (
            f"{SLACK_FALLBACK_START_DATE} より前は日付あり and キャンセル=FALSE、"
            f"{fallback_start} 以降は個別予約通知ログの日別件数"
        )
        booking_condition = f"2025/01/01以降（{SLACK_FALLBACK_START_DATE} から通知ログ補完）"
        booking_memo = (
            f"{SLACK_FALLBACK_START_DATE} より前は個別予約集計botログ、"
            f"{fallback_start} 以降の直近期間は 個別予約通知ログ で補完する"
        )
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
            booking_calc,
            booking_condition,
            str(stats["status"]),
            str(stats["updated_at"]),
            f"{int(stats['total_booking_count']):,}",
            "0",
            booking_memo,
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
            "Slack通知 + 過去データ",
            "2",
            f"https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit",
            NOTIFICATION_LOG_TAB_NAME,
            "A〜G列",
            "Slack通知と過去の個別予約データを 1イベント1行で統合",
            "過去分 + ★【個別予約完了】★ 通知。直近の日別個別予約数補完にも利用",
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
        ["変えるもの", "botログ固定ではなく、通知ログを本命の計上元へ段階移行する", f"現行は {SLACK_FALLBACK_START_DATE} より前を botログ、以降を通知ログで補完する"],
        ["追加するもの", "個別予約通知ログを 1イベント1行で持つ", "過去の個別予約データと Slack 通知を同じ正本へ統合する"],
        ["個別予約数", f"{SLACK_FALLBACK_START_DATE} より前は個別予約集計botログ、以降は個別予約通知ログを使う", "botログ側は日付あり and キャンセル=FALSE を基本ルールにする"],
        ["重複予約の扱い", "同一人物の通知が同じ日に10分以内で連続した時は1件にまとめる", "通知ログを使う期間だけ適用する。バグ由来の連続通知を吸収するため"],
        ["個別予約通知ログ", "過去の個別予約データを引き継ぎつつ、Lステップ の予約イベント通知とタグ通知を1イベント1行で溜める", f"まずは Slack の専用チャンネルに集約し、個別予約完了タグ通知は検証用として残し、{SLACK_FALLBACK_START_DATE} 以降の件数補完にも使う"],
        ["個別予約数（UU）", "第1版ではまだ接続しない", "LINE統合や名寄せ方針が固まってから入れる"],
        ["タグ", "★【個別予約完了】★ は今は検証用、将来も冗長系の確認軸として残す", "タグ単体は累積状態なので日別件数の正本には使わない"],
        ["予約イベント通知", "salon_reservation_reserved / reservation.reserved を本命候補として監査する", "Lステップ live 確認後に Slack 側の受け皿を増やす"],
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
    count_rows.extend([[f"'{record.date}", f"{record.count:,}", f"{record.cumulative_count:,}"] for record in daily_records])
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
    notification_events = load_notification_events()
    notification_daily = build_notification_daily_counts(notification_events)
    daily_records, daily_meta = build_daily_records(records, notification_daily)
    stats = build_stats(records, daily_records, daily_meta)
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
