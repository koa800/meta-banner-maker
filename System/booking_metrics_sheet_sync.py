#!/usr/bin/env python3
"""
【アドネス株式会社】個別面談データ を再生成する。

第1版の方針:
- 現行の正本候補は `【アドネス】顧客管理シート / 個別予約集計botログ`
- `個別予約数` だけを先に接続する
- `個別予約数（UU）` は将来用の枠だけを作り、今は未同期にする
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

from common_exclusion import CommonExclusionMaster
from gspread.exceptions import APIError
from sheets_manager import get_client


TARGET_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】個別面談データ"
COLLECTION_SHEET_ID = "12bYadR0cgi24t4tz8GeESlsKffmNkkTHprI4ray_Sq4"
COLLECTION_SPREADSHEET_TITLE = "【アドネス株式会社】個別面談データ（収集）"
COLLECTION_NOTIFICATION_LOG_TAB_NAME = "個別予約通知ログ"
NOTIFICATION_STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "booking_notification_log_state.json")
SOURCE_SHEET_ID = "1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo"
SOURCE_TAB_NAME = "個別予約集計botログ"
LEGACY_BOOKING_SHEET_ID = "1LAzT12KfHKDJTuI69DEdDmS7oD0T6Kz9V5D0mdJDPsQ"
LEGACY_BOOKING_TAB_NAME = "シート1"

COUNT_TAB_NAME = "日別個別予約数"
UU_TAB_NAME = "日別個別予約数（UU）"
SUMMARY_TAB_NAME = "個別予約サマリー"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

TAB_SPECS = {
    COUNT_TAB_NAME: (500, 3),
    UU_TAB_NAME: (500, 3),
    SUMMARY_TAB_NAME: (60, 3),
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
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}

STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "未同期": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
    "確認待ち": {"backgroundColor": {"red": 0.925, "green": 0.89, "blue": 0.992}},
}

PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "個別面談データ自動生成"
UNUSED_TAB_NAMES = {"タグ検証", "個別予約通知ログ"}

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
            if ws.col_count != cols:
                worksheet_write_with_retry(
                    f"{name} の列数調整",
                    lambda ws=ws, cols=cols: ws.resize(rows=ws.row_count, cols=cols),
                )
            continue
        tabs[name] = run_write_with_retry(
            f"{name} タブの作成",
            lambda name=name, rows=rows, cols=cols: spreadsheet.add_worksheet(
                title=name, rows=rows, cols=cols
            ),
        )

    for name in UNUSED_TAB_NAMES:
        ws = tabs.get(name)
        if ws is None:
            continue
        if len(tabs) <= len(TAB_SPECS):
            continue
        batch_update_with_retry(
            spreadsheet,
            {"requests": [{"deleteSheet": {"sheetId": ws.id}}]},
            f"{name} タブの削除",
        )
        tabs.pop(name, None)

    return tabs


def write_rows(spreadsheet, ws, rows: List[List[str]]) -> None:
    max_cols = max((len(row) for row in rows), default=1)
    padded = [row + [""] * max(0, max_cols - len(row)) for row in rows]
    end_cell = f"{col_letter(max_cols)}{len(padded)}"
    target_rows = max(len(padded), 2)
    if ws.row_count != target_rows or ws.col_count != max_cols:
        worksheet_write_with_retry(
            f"{ws.title} タブのサイズ最適化",
            lambda: ws.resize(rows=target_rows, cols=max_cols),
        )
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


def apply_table_style(spreadsheet, ws, row_count: int, col_count: int, widths: Iterable[int], wrap: str = "CLIP") -> None:
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
                "wrapStrategy": wrap,
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
    try:
        source = gc.open_by_key(SOURCE_SHEET_ID)
        ws = source.worksheet(SOURCE_TAB_NAME)
        values = ws.get_all_values()
    except Exception:
        return []

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
    target = gc.open_by_key(COLLECTION_SHEET_ID)
    try:
        ws = target.worksheet(COLLECTION_NOTIFICATION_LOG_TAB_NAME)
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


def build_notification_daily_counts(events: Sequence[NotificationEvent]) -> tuple[Counter, int]:
    exclusion_master = CommonExclusionMaster.load()
    grouped: Dict[tuple[str, str], List[NotificationEvent]] = defaultdict(list)
    excluded_count = 0
    for event in events:
        event_date = event.tagged_at.strftime("%Y/%m/%d")
        if exclusion_master.is_excluded(
            email=event.email,
            phone=event.phone,
            name=event.line_name,
            scope="個別予約",
            event_date=event_date,
        ):
            excluded_count += 1
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
    return daily, excluded_count


def build_daily_records(records: Sequence[BookingRecord], notification_daily: Counter) -> tuple[List[DailyCountRecord], Dict[str, str]]:
    botlog_daily = Counter()
    for record in records:
        if record.cancelled:
            continue
        botlog_daily[record.booking_date] += 1

    latest_botlog_date = max(botlog_daily, default="")
    latest_notification_date = max(notification_daily, default="")
    if notification_daily:
        merged_daily = Counter(notification_daily)
        notification_fallback_start = min(notification_daily)
    else:
        merged_daily = Counter(botlog_daily)
        notification_fallback_start = ""

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
    excluded_count: int,
) -> Dict[str, object]:
    non_cancelled = [record for record in records if not record.cancelled]
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
        status = "未同期"

    return {
        "updated_at": updated_at,
        "total_booking_count": sum(record.count for record in daily_records),
        "botlog_booking_count": len(non_cancelled),
        "total_cancel_count": sum(1 for record in records if record.cancelled),
        "start_date": daily_records[0].date if daily_records else "",
        "latest_date": latest_date,
        "daily_row_count": len(daily_records),
        "status": status,
        "latest_botlog_date": daily_meta.get("latest_botlog_date", ""),
        "latest_notification_date": daily_meta.get("latest_notification_date", ""),
        "notification_fallback_start": daily_meta.get("notification_fallback_start", ""),
        "excluded_notification_count": excluded_count,
    }


def build_summary_rows(stats: Dict[str, object]) -> List[List[str]]:
    booking_definition = "個別予約通知ログを日別集計し、同一人物の同日10分以内連続通知を1件にまとめた個別予約イベント数"
    fallback_start = str(stats.get("notification_fallback_start") or "").strip()
    latest_botlog_date = str(stats.get("latest_botlog_date") or "").strip()
    if fallback_start:
        booking_definition = (
            f"{fallback_start} 以降の個別予約通知ログを正本にし、"
            "同一人物の同日10分以内連続通知を1件にまとめた個別予約イベント数"
        )
    return [
        ["項目", "数値", "定義"],
        ["更新日時", f"'{stats['updated_at']}", "このシートを作り直した時刻"],
        ["個別予約数", f"{int(stats['total_booking_count']):,}", booking_definition],
        ["個別予約数（UU）", "", "将来接続。LSTEP通知ログとLINE統合後の同一人物判定で持つ"],
        ["キャンセル数", f"{int(stats['total_cancel_count']):,}", "個別予約集計botログでキャンセル=TRUE の件数"],
        ["除外件数", f"{int(stats['excluded_notification_count']):,}", "共通除外マスタで除外した個別予約通知ログの件数"],
        ["集計開始日", f"'{stats['start_date']}", "日別個別予約数の最初の日付"],
        ["最新集計日", f"'{stats['latest_date']}", "日別個別予約数の最新の日付"],
    ]


def load_notification_log_stats(target) -> Dict[str, str]:
    try:
        collection = get_client().open_by_key(COLLECTION_SHEET_ID)
        ws = collection.worksheet(COLLECTION_NOTIFICATION_LOG_TAB_NAME)
    except Exception:
        return {
            "ステータス": "停止",
            "最終同期日": "",
            "更新数": "",
            "エラー数": "1",
            "メモ": "収集シートに接続できない",
        }

    values = ws.get_all_values()
    event_count = 0
    for row in values[1:]:
        row = row + [""] * max(0, 6 - len(row))
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
            "ステータス": "未同期",
            "最終同期日": latest_imported_at,
            "更新数": "0",
            "エラー数": "0",
            "メモ": "Slack通知の取込待ち",
        }

    return {
        "ステータス": "正常",
        "最終同期日": latest_imported_at,
        "更新数": f"{event_count:,}" if event_count else "0",
        "エラー数": "0",
            "メモ": "Slack #個別予約通知 と 過去の個別予約データ を統合。LSTEPメンバーIDで友だち一覧CSVに一致した時はメールアドレス / 電話番号も補完する",
        }


def build_source_rows(stats: Dict[str, object], notification_stats: Dict[str, str]) -> List[List[str]]:
    fallback_start = str(stats.get("notification_fallback_start") or "").strip()
    booking_calc = "個別予約通知ログを日別集計し、同一人物の同日10分以内連続通知を1件にまとめる"
    booking_condition = "2025/01/01以降"
    booking_memo = "個別予約通知ログを個別予約数の正本にする。過去シートは一時的な補完入力元として扱う"
    if fallback_start:
        booking_calc = (
            f"{fallback_start} 以降の個別予約通知ログを日別集計し、"
            "同一人物の同日10分以内連続通知を1件にまとめる"
        )
        booking_condition = f"2025/01/01以降（{fallback_start} から通知ログ正本）"
        booking_memo = (
            "個別予約通知ログを正本にする。"
            "Slack通知と過去シートを一つのイベントログへ統合し、日別個別予約数を作る"
        )
    return [
        ["KPIカラム", "グループ", "ソース元", "優先度", "スプレッドシートURL", "タブ名", "参照先列", "正規化 / 計算", "入力条件", "ステータス", "最終同期日", "更新数", "エラー数", "メモ"],
        [
            "個別予約数",
            "個別予約",
            "加工データ",
            "1",
            f"https://docs.google.com/spreadsheets/d/{TARGET_SHEET_ID}/edit",
            COUNT_TAB_NAME,
            "A〜C列",
            booking_calc,
            booking_condition,
            notification_stats["ステータス"] if notification_stats["ステータス"] else str(stats["status"]),
            notification_stats["最終同期日"] if notification_stats["最終同期日"] else str(stats["updated_at"]),
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
            "未同期",
            "",
            "",
            "",
            "LINE統合前は同一人物判定が弱いため未同期",
        ],
        [
            "個別予約通知ログ",
            "収集データ",
            "Slack通知",
            "1",
            f"https://docs.google.com/spreadsheets/d/{COLLECTION_SHEET_ID}/edit",
            COLLECTION_NOTIFICATION_LOG_TAB_NAME,
            "A〜G列",
            "Slack通知と過去の個別予約データを 1イベント1行で統合",
            "継続取得の正本",
            notification_stats["ステータス"],
            notification_stats["最終同期日"],
            notification_stats["更新数"],
            notification_stats["エラー数"],
            f"{notification_stats['メモ']}。日別個別予約数では共通除外マスタも参照する",
        ],
        [
            "共通除外",
            "個別予約",
            "【アドネス株式会社】共通除外マスタ",
            "2",
            "https://docs.google.com/spreadsheets/d/1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw/edit",
            "除外リスト / 無条件除外ルール",
            "メールアドレス / 電話番号 / 対象者名",
            "追加日以降に発生した個別予約だけ除外する",
            "2025/01/01以降",
            "正常",
            f"'{stats['updated_at']}",
            f"{int(stats['excluded_notification_count']):,}",
            "0",
            "通知ログは残し、日別個別予約数を作る時だけ除外を効かせる",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["個別予約数", "個別予約通知ログを日別集計して使う", "同一人物の同日10分以内連続通知は1件にまとめる"],
        ["共通除外", "【アドネス株式会社】共通除外マスタ を参照して、新しく発生した除外対象だけ日別集計から外す", "通知ログの生データ自体は消さない"],
        ["重複予約の扱い", "同一人物の通知が同じ日に10分以内で連続した時は1件にまとめる", "全期間で適用する。バグ由来の連続通知を吸収するため"],
        ["収集データ", "個別予約通知ログは別シートで継続取得する", "このシートには生データを持たない"],
        ["過去補完データ", "過去シートは通知ログへ一度だけ取り込む", "日別個別予約数の継続的な正本にはしない"],
        ["個別予約数（UU）", "第1版ではまだ接続しない", "LINE統合や名寄せ方針が固まってから入れる"],
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

    uu_rows = [["日付", "個別予約数（UU）", "累計個別予約数（UU）"]]

    summary_rows = build_summary_rows(stats)
    source_rows = build_source_rows(stats, notification_stats)
    rule_rows = build_rule_rows()

    write_rows(target, tabs[COUNT_TAB_NAME], count_rows)
    write_rows(target, tabs[UU_TAB_NAME], uu_rows)
    write_rows(target, tabs[SUMMARY_TAB_NAME], summary_rows)
    write_rows(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows)
    write_rows(target, tabs[RULE_TAB_NAME], rule_rows)

    apply_table_style(target, tabs[COUNT_TAB_NAME], len(count_rows), 3, [140, 160, 180], wrap="CLIP")
    apply_table_style(target, tabs[UU_TAB_NAME], len(uu_rows), 3, [140, 180, 200], wrap="CLIP")
    apply_table_style(target, tabs[SUMMARY_TAB_NAME], len(summary_rows), 3, [220, 160, 500], wrap="CLIP")
    apply_table_style(target, tabs[SOURCE_MANAGEMENT_TAB_NAME], len(source_rows), 14, [180, 110, 110, 70, 260, 160, 130, 220, 140, 90, 140, 90, 80, 280], wrap="CLIP")
    apply_table_style(target, tabs[RULE_TAB_NAME], len(rule_rows), 3, [180, 420, 360], wrap="WRAP")

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
    notification_daily, excluded_count = build_notification_daily_counts(notification_events)
    daily_records, daily_meta = build_daily_records(records, notification_daily)
    stats = build_stats(records, daily_records, daily_meta, excluded_count)
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
