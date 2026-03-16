#!/usr/bin/env python3
"""
【アドネス株式会社】個別面談データ / 個別予約通知ログ を更新する。

役割:
- Slack `#個別予約通知` に流れる Lステップ通知を 1イベント1行で保存する
- `LSTEPメンバーID + Lステップアカウント名` をイベントキー候補として保持する
- メールアドレスや顧客IDの照合は後から追記できる形にする
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from gspread.exceptions import APIError

from sheets_manager import get_client
from mac_mini.agent_orchestrator.slack_reader import (
    fetch_channel_messages,
    find_channel_by_name,
)


TARGET_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
TARGET_TAB_NAME = "個別予約通知ログ"
DEFAULT_CHANNEL_NAME = os.environ.get("BOOKING_NOTIFICATION_SLACK_CHANNEL_NAME", "個別予約通知")
MESSAGE_TAG = "★【個別予約完了】★"
STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "booking_notification_log_state.json")

TAB_COLOR = "#1A73E8"
HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_DESCRIPTION = "個別面談データ自動生成: 個別予約通知ログ"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)

COLUMNS = [
    "タグ付与日時",
    "LINE名",
    "LSTEPメンバーID",
    "Lステップアカウント名",
    "予約導線種別",
    "通知リンク",
    "メールアドレス",
    "電話番号",
]

ACCOUNT_RE = re.compile(r"^[\(（](.+?)\s*タグ通知[\)）]$")
EVENT_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
LINE_NAME_RE = re.compile(r"^(.+?)にタグ[「\"]?★【個別予約完了】★[」\"]?が追加されました。?$")
URL_RE = re.compile(r"https?://\S+")


@dataclass
class NotificationRecord:
    tagged_at: str
    line_name: str
    member_id: str
    account_name: str
    route_type: str
    notification_url: str
    slack_ts: str
    email: str
    phone: str

    def to_row(self) -> List[str]:
        return [
            self.tagged_at,
            self.line_name,
            self.member_id,
            self.account_name,
            self.route_type,
            self.notification_url,
            self.email,
            self.phone,
        ]

    @property
    def dedupe_key(self) -> str:
        return " | ".join(
            [
                self.tagged_at,
                self.account_name,
                self.member_id,
                self.line_name,
            ]
        ).strip()


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


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


def ensure_tab(spreadsheet):
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    ws = worksheets.get(TARGET_TAB_NAME)
    if ws is None:
        ws = run_write_with_retry(
            f"{TARGET_TAB_NAME} タブの作成",
            lambda: spreadsheet.add_worksheet(title=TARGET_TAB_NAME, rows=1000, cols=len(COLUMNS)),
        )
    if ws.row_count < 1000 or ws.col_count != len(COLUMNS):
        worksheet_write_with_retry(
            f"{TARGET_TAB_NAME} タブのサイズ調整",
            lambda: ws.resize(rows=max(ws.row_count, 1000), cols=len(COLUMNS)),
        )
    return ws


def ensure_header(ws) -> None:
    existing = ws.row_values(1)
    if existing[: len(COLUMNS)] == COLUMNS:
        return
    worksheet_write_with_retry(
        f"{TARGET_TAB_NAME} のヘッダー設定",
        lambda: ws.update(range_name=f"A1:{col_letter(len(COLUMNS))}1", values=[COLUMNS], value_input_option="USER_ENTERED"),
    )


def load_existing_rows(ws) -> Dict[str, NotificationRecord]:
    values = ws.get_all_values()
    existing: Dict[str, NotificationRecord] = {}
    for row in values[1:]:
        row = row + [""] * max(0, len(COLUMNS) - len(row))
        record = NotificationRecord(
            tagged_at=str(row[0]).strip(),
            line_name=str(row[1]).strip(),
            member_id=str(row[2]).strip(),
            account_name=str(row[3]).strip(),
            route_type=str(row[4]).strip(),
            notification_url=str(row[5]).strip(),
            slack_ts="",
            email=str(row[6]).strip(),
            phone=str(row[7]).strip(),
        )
        if not record.dedupe_key:
            continue
        existing[record.dedupe_key] = record
    return existing


def parse_member_id(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        return (parse_qs(parsed.query).get("id") or [""])[0]
    except Exception:
        return ""


def infer_route_type(text: str) -> str:
    if "イベント予約" in text:
        return "イベント予約"
    if "カレンダー予約" in text:
        return "カレンダー予約"
    return ""


def parse_notification_message(message: dict, channel_name: str) -> Optional[NotificationRecord]:
    text = str(message.get("text") or "").strip()
    if MESSAGE_TAG not in text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    account_name = ""
    tagged_at = ""
    line_name = ""
    notification_url = ""

    for line in lines:
        account_match = ACCOUNT_RE.match(line)
        if account_match:
            account_name = account_match.group(1).strip()
            continue
        if EVENT_AT_RE.match(line):
            tagged_at = line
            continue
        name_match = LINE_NAME_RE.match(line)
        if name_match:
            line_name = name_match.group(1).strip()
            continue
        if line.startswith("http://") or line.startswith("https://"):
            notification_url = line

    member_id = parse_member_id(notification_url)
    slack_ts = str(message.get("ts") or "").strip()
    if not slack_ts:
        return None

    route_type = infer_route_type(text)

    return NotificationRecord(
        tagged_at=tagged_at,
        line_name=line_name,
        member_id=member_id,
        account_name=account_name,
        route_type=route_type,
        notification_url=notification_url,
        slack_ts=slack_ts,
        email="",
        phone="",
    )


def merge_records(existing: Dict[str, NotificationRecord], parsed: Iterable[NotificationRecord]) -> List[NotificationRecord]:
    merged = dict(existing)
    for record in parsed:
        key = record.dedupe_key
        if key in merged:
            current = merged[key]
            merged[key] = NotificationRecord(
                tagged_at=record.tagged_at or current.tagged_at,
                line_name=record.line_name or current.line_name,
                member_id=record.member_id or current.member_id,
                account_name=record.account_name or current.account_name,
                route_type=record.route_type or current.route_type,
                notification_url=record.notification_url or current.notification_url,
                slack_ts=record.slack_ts or current.slack_ts,
                email=current.email,
                phone=current.phone,
            )
        else:
            merged[key] = record

    return sorted(
        merged.values(),
        key=lambda item: (
            item.tagged_at or "",
            item.account_name or "",
            item.line_name or "",
        ),
    )


def write_rows(ws, rows: List[List[str]]) -> None:
    end_cell = f"{col_letter(len(COLUMNS))}{len(rows)}"
    worksheet_write_with_retry(f"{TARGET_TAB_NAME} の既存データ削除", ws.clear)
    worksheet_write_with_retry(
        f"{TARGET_TAB_NAME} の書き込み",
        lambda: ws.update(range_name=f"A1:{end_cell}", values=rows, value_input_option="USER_ENTERED"),
    )


def apply_style(spreadsheet, ws, row_count: int) -> None:
    requests = [
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            len(COLUMNS),
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
            len(COLUMNS),
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
                        "endColumnIndex": len(COLUMNS),
                    }
                }
            }
        },
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "tabColor": {
                        "red": int(TAB_COLOR[1:3], 16) / 255.0,
                        "green": int(TAB_COLOR[3:5], 16) / 255.0,
                        "blue": int(TAB_COLOR[5:7], 16) / 255.0,
                    },
                },
                "fields": "tabColor",
            }
        },
    ]

    widths = [150, 180, 150, 180, 140, 280, 220, 180]
    for index, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, index, index + 1, width))

    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{TARGET_TAB_NAME} の表スタイル適用")
    worksheet_write_with_retry(f"{TARGET_TAB_NAME} のヘッダー固定", lambda: ws.freeze(rows=1))


def apply_protection(spreadsheet, ws) -> None:
    metadata = spreadsheet.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties.sheetId,protectedRanges(protectedRangeId,description,range(sheetId,startRowIndex,endRowIndex,startColumnIndex,endColumnIndex)))",
        }
    )
    requests = []
    existing_sheet_protection = False
    for sheet in metadata.get("sheets", []):
        sheet_id = sheet.get("properties", {}).get("sheetId")
        for protected_range in sheet.get("protectedRanges", []):
            range_info = protected_range.get("range", {})
            description = protected_range.get("description", "")
            range_sheet_id = range_info.get("sheetId", sheet_id)
            if range_sheet_id != ws.id:
                continue
            has_row = any(key in range_info for key in ("startRowIndex", "endRowIndex"))
            has_col = any(key in range_info for key in ("startColumnIndex", "endColumnIndex"))
            if not has_row and not has_col:
                existing_sheet_protection = True
            if description == PROTECTION_DESCRIPTION:
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_range["protectedRangeId"]}})

    if not existing_sheet_protection:
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": ws.id},
                        "description": PROTECTION_DESCRIPTION,
                        "warningOnly": False,
                        "editors": {"users": PROTECTED_EDITOR_EMAILS},
                    }
                }
            }
        )

    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, f"{TARGET_TAB_NAME} の保護設定")


def fetch_parsed_records(channel_name: str, limit: int, oldest: str = "") -> List[NotificationRecord]:
    channel = find_channel_by_name(channel_name)
    if channel is None:
        return []

    messages = fetch_channel_messages(
        channel["id"],
        oldest=oldest or None,
        limit=limit,
        include_bot_messages=True,
    )
    parsed: List[NotificationRecord] = []
    for message in messages:
        record = parse_notification_message(message, channel["name"])
        if record is not None:
            parsed.append(record)
    return parsed


def build_rows(records: List[NotificationRecord]) -> List[List[str]]:
    rows = [COLUMNS]
    rows.extend(record.to_row() for record in records)
    while len(rows) < 20:
        rows.append([""] * len(COLUMNS))
    return rows


def load_state() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(last_ts: str, imported_count: int, channel_name: str) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    payload = {
        "last_ts": last_ts,
        "imported_count": imported_count,
        "channel_name": channel_name,
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="個別予約通知ログを更新する")
    parser.add_argument("--channel-name", default=DEFAULT_CHANNEL_NAME, help="Slack チャンネル名")
    parser.add_argument("--limit", type=int, default=200, help="Slack から取得する最大件数")
    parser.add_argument("--dry-run", action="store_true", help="書き込みせず件数だけ確認する")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    gc = get_client()
    spreadsheet = gc.open_by_key(TARGET_SHEET_ID)
    ws = ensure_tab(spreadsheet)
    ensure_header(ws)
    existing = load_existing_rows(ws)
    state = load_state()
    oldest = str(state.get("last_ts") or "").strip()

    parsed = fetch_parsed_records(args.channel_name, args.limit, oldest=oldest)
    merged = merge_records(existing, parsed)

    if args.dry_run:
        print(
            "dry-run: "
            f"既存={len(existing):,}, "
            f"新規候補={len(parsed):,}, "
            f"保存後={len(merged):,}, "
            f"チャンネル={args.channel_name}"
        )
        return

    rows = build_rows(merged)
    write_rows(ws, rows)
    apply_style(spreadsheet, ws, len(rows))
    apply_protection(spreadsheet, ws)
    latest_ts = oldest
    if parsed:
        latest_ts = max((record.slack_ts for record in parsed if record.slack_ts), default=oldest)
    save_state(latest_ts or "", len(merged), args.channel_name)

    print(
        f"【アドネス株式会社】個別面談データ / {TARGET_TAB_NAME} を更新しました。"
        f"保存件数={len(merged):,}"
    )


if __name__ == "__main__":
    main()
