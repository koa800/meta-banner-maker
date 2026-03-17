#!/usr/bin/env python3
"""
【アドネス株式会社】個別面談データ（収集） / 個別予約通知ログ を更新する。

役割:
- Slack `#個別予約通知` に流れる Lステップ通知を 1イベント1行で保存する
- `LSTEPメンバーID + Lステップアカウント名` をイベントキー候補として保持する
- メールアドレスや電話番号は将来の Lステップ live 取得で補完できる形にする
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional
from urllib.parse import parse_qs, urlparse

from gspread.exceptions import APIError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

from sheets_manager import get_client
from lstep_member_contact_live import lookup_contact
from mac_mini.agent_orchestrator.slack_reader import (
    fetch_channel_messages,
    find_channel_by_name,
)


TARGET_SHEET_ID = "12bYadR0cgi24t4tz8GeESlsKffmNkkTHprI4ray_Sq4"
TARGET_SPREADSHEET_TITLE = "【アドネス株式会社】個別面談データ（収集）"
TARGET_TAB_NAME = "個別予約通知ログ"
SOURCE_MANAGEMENT_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"
DEFAULT_CHANNEL_NAME = os.environ.get("BOOKING_NOTIFICATION_SLACK_CHANNEL_NAME", "個別予約通知")
DEFAULT_FETCH_LIMIT = int(os.environ.get("BOOKING_NOTIFICATION_SLACK_FETCH_LIMIT", "1000"))
BACKFILL_HOURS = int(os.environ.get("BOOKING_NOTIFICATION_SLACK_BACKFILL_HOURS", "168"))
MESSAGE_TAG = "★【個別予約完了】★"
STATE_PATH = os.path.join(os.path.dirname(__file__), "data", "booking_notification_log_state.json")
LSTEP_DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
LEGACY_BOOKING_SHEET_ID = "1LAzT12KfHKDJTuI69DEdDmS7oD0T6Kz9V5D0mdJDPsQ"
LEGACY_BOOKING_TAB_NAME = "シート1"
OLD_METRICS_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
OLD_NOTIFICATION_LOG_TAB_NAME = "個別予約通知ログ"

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
TAB_COLORS = {
    TARGET_TAB_NAME: "#1A73E8",
    SOURCE_MANAGEMENT_TAB_NAME: "#34A853",
    RULE_TAB_NAME: "#9E9E9E",
}
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "個別面談データ（収集）自動生成"
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
LIVE_ENRICH_LIMIT = int(os.environ.get("BOOKING_NOTIFICATION_LIVE_ENRICH_LIMIT", "20"))
SLACK_PARSE_WARN_RATIO = float(os.environ.get("BOOKING_NOTIFICATION_SLACK_PARSE_WARN_RATIO", "0.05"))
SLACK_PARSE_STOP_RATIO = float(os.environ.get("BOOKING_NOTIFICATION_SLACK_PARSE_STOP_RATIO", "0.20"))

COLUMNS = [
    "予約イベント日時",
    "LINE名",
    "LSTEPメンバーID",
    "Lステップアカウント名",
    "Lステップリンク",
    "メールアドレス",
    "電話番号",
]

TAB_SPECS = {
    TARGET_TAB_NAME: (2000, len(COLUMNS)),
    SOURCE_MANAGEMENT_TAB_NAME: (40, 14),
    RULE_TAB_NAME: (40, 3),
}

ACCOUNT_RE = re.compile(r"^[\(（](.+?)[\)）]\s*タグ通知$")
EVENT_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$")
LINE_NAME_RE = re.compile(r"^(.+?)にタグ[「\"]?★【個別予約完了】★[」\"]?が追加されました。?$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class NotificationRecord:
    tagged_at: str
    line_name: str
    member_id: str
    account_name: str
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
            self.notification_url,
            self.email,
            self.phone,
        ]

    @property
    def dedupe_key(self) -> str:
        tagged_at = self.tagged_at.strip()
        account_name = self.account_name.strip()
        member_id = self.member_id.strip()
        line_name = self.line_name.strip()
        email = self.email.strip().lower()
        phone = re.sub(r"\D", "", self.phone)

        if tagged_at and account_name and member_id:
            return " | ".join(["event", tagged_at, account_name, member_id]).strip()
        if tagged_at and account_name and line_name:
            return " | ".join(["event", tagged_at, account_name, line_name]).strip()
        if tagged_at and line_name:
            return " | ".join(["event", tagged_at, line_name]).strip()
        if tagged_at and email:
            return " | ".join(["event", tagged_at, email]).strip()
        if tagged_at and phone:
            return " | ".join(["event", tagged_at, phone]).strip()
        return ""

    @property
    def legacy_key(self) -> str:
        return self.dedupe_key


@dataclass
class LiveEnrichSummary:
    status: str
    checked_at: str
    updated_count: int
    error_count: int
    memo: str


@dataclass
class SlackIngestSummary:
    status: str
    checked_at: str
    fetched_count: int
    tagged_count: int
    parsed_count: int
    error_count: int
    parse_failure_rate: float
    latest_tagged_at: str
    latest_parsed_at: str
    memo: str


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def normalize_tagged_at(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
    ):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if re.match(r"^\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}:\d{2}$", raw):
        date_part, time_part = raw.split(" ", 1)
        hour, minute, second = time_part.split(":")
        return f"{date_part} {int(hour):02d}:{minute}:{second}"
    if re.match(r"^\d{4}/\d{2}/\d{2} \d{1,2}:\d{2}:\d{2}$", raw):
        date_part, time_part = raw.split(" ", 1)
        year, month, day = date_part.split("/")
        hour, minute, second = time_part.split(":")
        return f"{year}-{month}-{day} {int(hour):02d}:{minute}:{second}"
    return raw


def normalize_account_name(value: str) -> str:
    return str(value or "").strip().replace("@", "＠")


def is_email(value: str) -> bool:
    return bool(EMAIL_RE.match(str(value or "").strip()))


def normalize_phone(value: str) -> str:
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if 10 <= len(digits) <= 11:
        return digits
    return ""


def build_record(
    tagged_at: str,
    line_name: str,
    member_id: str,
    account_name: str,
    notification_url: str,
    slack_ts: str,
    email: str,
    phone: str,
) -> NotificationRecord:
    return NotificationRecord(
        tagged_at=normalize_tagged_at(tagged_at),
        line_name=str(line_name).strip(),
        member_id=str(member_id).strip(),
        account_name=str(account_name).strip(),
        notification_url=str(notification_url).strip(),
        slack_ts=str(slack_ts).strip(),
        email=str(email).strip(),
        phone=str(phone).strip(),
    )


def merge_record_pair(current: NotificationRecord, incoming: NotificationRecord) -> NotificationRecord:
    return NotificationRecord(
        tagged_at=current.tagged_at or incoming.tagged_at,
        line_name=current.line_name or incoming.line_name,
        member_id=current.member_id or incoming.member_id,
        account_name=current.account_name or incoming.account_name,
        notification_url=current.notification_url or incoming.notification_url,
        slack_ts=current.slack_ts or incoming.slack_ts,
        email=current.email or incoming.email,
        phone=current.phone or incoming.phone,
    )


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
        "個別面談データ（収集）のシート名更新",
    )


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}
    if "シート1" in tabs and len(tabs) == 1:
        worksheet_write_with_retry(
            "個別面談データ（収集）の初期タブ名変更",
            lambda: tabs["シート1"].update_title(TARGET_TAB_NAME),
        )
        tabs[TARGET_TAB_NAME] = tabs.pop("シート1")

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
            lambda name=name, rows=rows, cols=cols: spreadsheet.add_worksheet(
                title=name, rows=rows, cols=cols
            ),
        )

    return tabs


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
    header = values[0] if values else []
    header_index = {str(name).strip(): idx for idx, name in enumerate(header)}
    tagged_at_idx = header_index.get("予約イベント日時", 0)
    line_name_idx = header_index.get("LINE名", 1)
    member_id_idx = header_index.get("LSTEPメンバーID", 2)
    account_name_idx = header_index.get("Lステップアカウント名", 3)
    notification_url_idx = header_index.get("Lステップリンク")
    email_idx = header_index.get("メールアドレス")
    phone_idx = header_index.get("電話番号")
    for row in values[1:]:
        row = row + [""] * max(0, len(COLUMNS) - len(row))
        raw_notification_url = str(row[notification_url_idx]).strip() if notification_url_idx is not None and notification_url_idx < len(row) else ""
        raw_email = str(row[email_idx]).strip() if email_idx is not None and email_idx < len(row) else ""
        raw_phone = str(row[phone_idx]).strip() if phone_idx is not None and phone_idx < len(row) else ""

        notification_url = raw_notification_url if raw_notification_url.startswith(("http://", "https://")) else ""
        email_candidates = [value for value in (raw_notification_url, raw_email, raw_phone) if is_email(value)]
        phone_candidates = [value for value in (raw_notification_url, raw_email, raw_phone) if normalize_phone(value)]
        email = email_candidates[0] if email_candidates else ""
        phone = normalize_phone(phone_candidates[0]) if phone_candidates else ""

        record = build_record(
            tagged_at=row[tagged_at_idx] if tagged_at_idx < len(row) else "",
            line_name=row[line_name_idx] if line_name_idx < len(row) else "",
            member_id=row[member_id_idx] if member_id_idx < len(row) else "",
            account_name=row[account_name_idx] if account_name_idx < len(row) else "",
            notification_url=notification_url,
            slack_ts="",
            email=email,
            phone=phone,
        )
        if not record.dedupe_key:
            continue
        if record.dedupe_key in existing:
            existing[record.dedupe_key] = merge_record_pair(existing[record.dedupe_key], record)
        else:
            existing[record.dedupe_key] = record
    return existing


def load_old_metrics_rows(gc) -> Dict[str, NotificationRecord]:
    try:
        spreadsheet = gc.open_by_key(OLD_METRICS_SHEET_ID)
        ws = spreadsheet.worksheet(OLD_NOTIFICATION_LOG_TAB_NAME)
    except Exception:
        return {}
    return load_existing_rows(ws)


def parse_member_id(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urlparse(html.unescape(url))
        return (parse_qs(parsed.query).get("id") or [""])[0]
    except Exception:
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
        if "<http://" in line or "<https://" in line:
            embedded = re.search(r"<(https?://[^>|]+)", line)
            if embedded:
                notification_url = html.unescape(embedded.group(1).strip())
                continue
        if line.startswith("http://") or line.startswith("https://"):
            notification_url = html.unescape(line)

    member_id = parse_member_id(notification_url)
    slack_ts = str(message.get("ts") or "").strip()
    if not slack_ts:
        return None

    return build_record(
        tagged_at=tagged_at,
        line_name=line_name,
        member_id=member_id,
        account_name=account_name,
        notification_url=notification_url,
        slack_ts=slack_ts,
        email="",
        phone="",
    )


def load_legacy_records() -> List[NotificationRecord]:
    try:
        gc = get_client()
        spreadsheet = gc.open_by_key(LEGACY_BOOKING_SHEET_ID)
        ws = spreadsheet.worksheet(LEGACY_BOOKING_TAB_NAME)
        values = ws.get_all_values()
    except Exception as exc:
        print(f"過去の個別予約データの読み込みをスキップしました: {exc}")
        return []
    if not values:
        return []

    header = values[0]
    header_index = {name: idx for idx, name in enumerate(header)}
    required = {"面談予約日", "LINE名", "面談キャンセル", "メールアドレス", "電話番号"}
    missing = required - set(header_index)
    if missing:
        raise RuntimeError(f"過去の個別予約データに必要列がありません: {sorted(missing)}")

    records: List[NotificationRecord] = []
    for raw_row in values[1:]:
        row = raw_row + [""] * max(0, len(header) - len(raw_row))
        cancelled = str(row[header_index["面談キャンセル"]]).strip().upper()
        if cancelled == "TRUE":
            continue
        tagged_at = normalize_tagged_at(row[header_index["面談予約日"]])
        line_name = str(row[header_index["LINE名"]]).strip()
        email = str(row[header_index["メールアドレス"]]).strip()
        phone = str(row[header_index["電話番号"]]).strip()
        if not tagged_at or not any((line_name, email, phone)):
            continue
        records.append(build_record(
            tagged_at=tagged_at,
            line_name=line_name,
            member_id="",
            account_name="",
            notification_url="",
            slack_ts="",
            email=email,
            phone=phone,
        ))
    return records


def merge_records(existing: Dict[str, NotificationRecord], parsed: Iterable[NotificationRecord]) -> List[NotificationRecord]:
    merged = dict(existing)
    for record in parsed:
        key = record.dedupe_key
        if key in merged:
            merged[key] = merge_record_pair(merged[key], record)
        else:
            merged[key] = record

    collapsed: Dict[str, NotificationRecord] = {}
    for record in merged.values():
        key = record.legacy_key or record.dedupe_key
        if key in collapsed:
            collapsed[key] = merge_record_pair(collapsed[key], record)
        else:
            collapsed[key] = record

    return sorted(
        collapsed.values(),
        key=lambda item: (
            item.tagged_at or "",
            item.account_name or "",
            item.line_name or "",
        ),
    )


def enrich_records_with_live_contacts(records: List[NotificationRecord]) -> tuple[List[NotificationRecord], LiveEnrichSummary]:
    checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    if LIVE_ENRICH_LIMIT <= 0:
        return records, LiveEnrichSummary(
            status="未同期",
            checked_at=checked_at,
            updated_count=0,
            error_count=0,
            memo="live補完は停止中です",
        )

    def sort_key(record: NotificationRecord) -> tuple[str, str]:
        return (record.tagged_at or "", record.slack_ts or "")

    candidates = [
        record
        for record in sorted(records, key=sort_key, reverse=True)
        if record.notification_url and (not record.email or not record.phone)
    ][:LIVE_ENRICH_LIMIT]
    if not candidates:
        return records, LiveEnrichSummary(
            status="正常",
            checked_at=checked_at,
            updated_count=0,
            error_count=0,
            memo="補完対象なし",
        )

    updates: Dict[str, NotificationRecord] = {}
    error_count = 0
    checked_count = 0
    auth_blocked_message = ""
    for record in candidates:
        try:
            result = lookup_contact(record.notification_url, expected_member_id=record.member_id)
        except Exception as exc:
            print(f"Lステップ live 補完に失敗しました: {record.notification_url} / {exc}")
            error_count += 1
            continue
        checked_count += 1
        if result.status != "ok":
            print(f"Lステップ live 補完をスキップしました: {result.message}")
            if result.status == "login_required":
                auth_blocked_message = result.message
                break
            if result.status in {"cdp_unavailable", "member_mismatch"}:
                error_count += 1
            continue
        updated = NotificationRecord(
            tagged_at=record.tagged_at,
            line_name=record.line_name,
            member_id=record.member_id,
            account_name=record.account_name,
            notification_url=record.notification_url,
            slack_ts=record.slack_ts,
            email=result.email or record.email,
            phone=result.phone or record.phone,
        )
        updates[record.dedupe_key] = updated

    if not updates:
        if auth_blocked_message:
            return records, LiveEnrichSummary(
                status="未同期",
                checked_at=checked_at,
                updated_count=0,
                error_count=max(error_count, 1),
                memo=auth_blocked_message,
            )
        if error_count > 0 and checked_count == 0:
            return records, LiveEnrichSummary(
                status="停止",
                checked_at=checked_at,
                updated_count=0,
                error_count=error_count,
                memo="live補完でエラーが発生",
            )
        return records, LiveEnrichSummary(
            status="正常",
            checked_at=checked_at,
            updated_count=0,
            error_count=error_count,
            memo=f"補完対象 {len(candidates):,}件 / 補完なし",
        )

    merged_records: List[NotificationRecord] = []
    for record in records:
        merged_records.append(updates.get(record.dedupe_key, record))
    return merged_records, LiveEnrichSummary(
        status="正常",
        checked_at=checked_at,
        updated_count=len(updates),
        error_count=error_count,
        memo=f"補完対象 {len(candidates):,}件 / 補完成功 {len(updates):,}件",
    )


def write_rows(ws, rows: List[List[str]]) -> None:
    end_cell = f"{col_letter(len(COLUMNS))}{len(rows)}"
    target_rows = max(len(rows), 1)
    if ws.row_count != target_rows or ws.col_count != len(COLUMNS):
        worksheet_write_with_retry(
            f"{TARGET_TAB_NAME} タブのサイズ最適化",
            lambda: ws.resize(rows=target_rows, cols=len(COLUMNS)),
        )
    worksheet_write_with_retry(f"{TARGET_TAB_NAME} の既存データ削除", ws.clear)
    worksheet_write_with_retry(
        f"{TARGET_TAB_NAME} の書き込み",
        lambda: ws.update(range_name=f"A1:{end_cell}", values=rows, value_input_option="USER_ENTERED"),
    )


def write_simple_rows(ws, rows: List[List[str]], col_count: int) -> None:
    end_cell = f"{col_letter(col_count)}{len(rows)}"
    target_rows = max(len(rows), 1)
    if ws.row_count != target_rows or ws.col_count != col_count:
        worksheet_write_with_retry(
            f"{ws.title} タブのサイズ最適化",
            lambda: ws.resize(rows=target_rows, cols=col_count),
        )
    worksheet_write_with_retry(f"{ws.title} の既存データ削除", ws.clear)
    worksheet_write_with_retry(
        f"{ws.title} の書き込み",
        lambda: ws.update(range_name=f"A1:{end_cell}", values=rows, value_input_option="USER_ENTERED"),
    )


def apply_table_style(spreadsheet, ws, row_count: int, col_count: int, widths: List[int], wrap: str = "CLIP") -> None:
    requests = [
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
                "properties": {
                    "sheetId": ws.id,
                    "tabColor": {
                        "red": int(TAB_COLORS[ws.title][1:3], 16) / 255.0,
                        "green": int(TAB_COLORS[ws.title][3:5], 16) / 255.0,
                        "blue": int(TAB_COLORS[ws.title][5:7], 16) / 255.0,
                    },
                },
                "fields": "tabColor",
            }
        },
    ]

    for index, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, index, index + 1, width))

    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の表スタイル適用")
    worksheet_write_with_retry(f"{ws.title} のヘッダー固定", lambda: ws.freeze(rows=1))


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
            if description == f"{PROTECTION_PREFIX}: {ws.title}":
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_range["protectedRangeId"]}})

    if not existing_sheet_protection:
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": ws.id},
                        "description": f"{PROTECTION_PREFIX}: {ws.title}",
                        "warningOnly": False,
                        "editors": {"users": PROTECTED_EDITOR_EMAILS},
                    }
                }
            }
        )

    if requests:
        batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の保護設定")


def build_source_management_rows(
    imported_count: int,
    updated_at: str,
    slack_summary: SlackIngestSummary,
    live_summary: LiveEnrichSummary,
) -> List[List[str]]:
    return [
        ["対象タブ", "グループ", "ソース元", "優先度", "スプレッドシートURL", "タブ名", "参照先列", "正規化 / 計算", "入力条件", "ステータス", "最終同期日", "更新数", "エラー数", "メモ"],
        [
            TARGET_TAB_NAME,
            "個別予約",
            "Slack #個別予約通知",
            "1",
            "",
            DEFAULT_CHANNEL_NAME,
            "メッセージ本文",
            "★【個別予約完了】★ 通知を 1イベント1行で保存。LSTEPリンクを保持し、旧CSVではなく将来の Lステップ live 取得でメールアドレス / 電話番号を補完する",
            "継続取得の正本",
            slack_summary.status,
            f"'{slack_summary.checked_at}" if slack_summary.checked_at else (f"'{updated_at}" if updated_at else ""),
            f"{imported_count:,}",
            f"{slack_summary.error_count:,}",
            (
                f"{slack_summary.memo} / 取得={slack_summary.fetched_count:,} / "
                f"対象通知={slack_summary.tagged_count:,} / 解析成功={slack_summary.parsed_count:,} / "
                f"解析失敗率={slack_summary.parse_failure_rate:.1%} / "
                f"最新対象通知={slack_summary.latest_tagged_at or 'なし'} / "
                f"最新保存通知={slack_summary.latest_parsed_at or 'なし'}。"
                "収集データの正本。過去データは初回移行時のみ一度だけ追加し、継続取得の正本にはしない"
            ),
        ],
        [
            TARGET_TAB_NAME,
            "個別予約",
            "Lステップ live 補完",
            "2",
            "",
            "会員詳細",
            "E:G列",
            "Lステップリンクから会員詳細を開き、メールアドレスと電話番号を補完する",
            "Lステップの認証が有効であること",
            live_summary.status,
            f"'{live_summary.checked_at}" if live_summary.checked_at else "",
            f"{live_summary.updated_count:,}",
            f"{live_summary.error_count:,}",
            live_summary.memo,
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "補足"],
        ["役割", "このシートは収集データだけを持つ", "加工や集計は【アドネス株式会社】個別面談データで行う"],
        ["継続取得", "Slack #個別予約通知 を継続的な正本にする", "★【個別予約完了】★ の通知を 1イベント1行で保存する"],
        ["友だち情報補完", "手元の友だち一覧CSVは今後使わない", "Lステップリンクから live 取得できる仕組みへ移行する"],
        ["初回移行", "過去の個別予約データは初回移行時に一度だけ取り込む", "継続運用では参照しない"],
        ["重複保存", "同じ通知は重複して保存しない", "日時 / アカウント / メンバーID / LINE名 / メール / 電話で吸収する"],
        ["手編集", "自動生成タブは手編集しない", "更新はスクリプトから行う"],
    ]


def fetch_parsed_records(channel_name: str, limit: int, oldest: str = "") -> tuple[List[NotificationRecord], SlackIngestSummary]:
    checked_at = datetime.now().strftime("%Y/%m/%d %H:%M")
    try:
        channel = find_channel_by_name(channel_name)
    except Exception as exc:
        return [], SlackIngestSummary(
            status="停止",
            checked_at=checked_at,
            fetched_count=0,
            tagged_count=0,
            parsed_count=0,
            error_count=1,
            parse_failure_rate=0.0,
            latest_tagged_at="",
            latest_parsed_at="",
            memo=f"Slack チャンネルの確認に失敗: {exc}",
        )
    if channel is None:
        return [], SlackIngestSummary(
            status="停止",
            checked_at=checked_at,
            fetched_count=0,
            tagged_count=0,
            parsed_count=0,
            error_count=1,
            parse_failure_rate=0.0,
            latest_tagged_at="",
            latest_parsed_at="",
            memo="Slack チャンネルが見つからない",
        )

    try:
        messages = fetch_channel_messages(
            channel["id"],
            oldest=oldest or None,
            limit=limit,
            include_bot_messages=True,
        )
    except Exception as exc:
        return [], SlackIngestSummary(
            status="停止",
            checked_at=checked_at,
            fetched_count=0,
            tagged_count=0,
            parsed_count=0,
            error_count=1,
            parse_failure_rate=0.0,
            latest_tagged_at="",
            latest_parsed_at="",
            memo=f"Slack メッセージ取得に失敗: {exc}",
        )
    parsed: List[NotificationRecord] = []
    tagged_count = 0
    parse_error_count = 0
    latest_tagged_at = ""
    latest_parsed_at = ""
    for message in messages:
        text = str(message.get("text") or "").strip()
        if MESSAGE_TAG not in text:
            continue
        tagged_count += 1
        record = parse_notification_message(message, channel["name"])
        message_ts = str(message.get("ts") or "").strip()
        if message_ts:
            try:
                latest_dt = datetime.fromtimestamp(float(message_ts))
                latest_tagged_at = max(latest_tagged_at, latest_dt.strftime("%Y-%m-%d %H:%M:%S"))
            except Exception:
                pass
        if record is not None:
            parsed.append(record)
            if record.tagged_at:
                latest_parsed_at = max(latest_parsed_at, record.tagged_at)
        else:
            parse_error_count += 1

    parse_failure_rate = (parse_error_count / tagged_count) if tagged_count else 0.0
    status = "正常"
    memo = "Slack 通知を正常に解析した"
    if tagged_count > 0 and len(parsed) == 0:
        status = "停止"
        memo = "対象通知は見つかったが解析に失敗した"
    elif parse_failure_rate >= SLACK_PARSE_STOP_RATIO:
        status = "停止"
        memo = "対象通知の解析失敗率が高い"
    elif parse_failure_rate >= SLACK_PARSE_WARN_RATIO:
        status = "未同期"
        memo = "対象通知の一部を解析できなかった"
    elif not messages:
        status = "未同期"
        memo = "Slack メッセージを取得できなかった"
    elif tagged_count == 0:
        memo = "取得範囲内に対象通知は無かった"

    return parsed, SlackIngestSummary(
        status=status,
        checked_at=checked_at,
        fetched_count=len(messages),
        tagged_count=tagged_count,
        parsed_count=len(parsed),
        error_count=parse_error_count,
        parse_failure_rate=parse_failure_rate,
        latest_tagged_at=latest_tagged_at,
        latest_parsed_at=latest_parsed_at,
        memo=memo,
    )


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


def save_state(last_ts: str, imported_count: int, channel_name: str, slack_summary: SlackIngestSummary) -> None:
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    payload = {
        "last_ts": last_ts,
        "imported_count": imported_count,
        "channel_name": channel_name,
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "slack_status": slack_summary.status,
        "slack_error_count": slack_summary.error_count,
        "slack_memo": slack_summary.memo,
        "slack_fetched_count": slack_summary.fetched_count,
        "slack_tagged_count": slack_summary.tagged_count,
        "slack_parsed_count": slack_summary.parsed_count,
        "slack_parse_failure_rate": slack_summary.parse_failure_rate,
        "slack_latest_tagged_at": slack_summary.latest_tagged_at,
        "slack_latest_parsed_at": slack_summary.latest_parsed_at,
    }
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="個別予約通知ログを更新する")
    parser.add_argument("--channel-name", default=DEFAULT_CHANNEL_NAME, help="Slack チャンネル名")
    parser.add_argument("--limit", type=int, default=DEFAULT_FETCH_LIMIT, help="Slack から取得する最大件数")
    parser.add_argument("--dry-run", action="store_true", help="書き込みせず件数だけ確認する")
    return parser.parse_args()


def resolve_fetch_oldest(state: dict) -> str:
    backfill_threshold = datetime.now() - timedelta(hours=BACKFILL_HOURS)
    backfill_ts = f"{backfill_threshold.timestamp():.6f}"
    state_ts = str(state.get("last_ts") or "").strip()
    if not state_ts:
        return backfill_ts
    try:
        return min(state_ts, backfill_ts, key=float)
    except Exception:
        return backfill_ts


def main() -> None:
    args = parse_args()
    gc = get_client()
    spreadsheet = gc.open_by_key(TARGET_SHEET_ID)
    ensure_spreadsheet_title(spreadsheet)
    tabs = ensure_tabs(spreadsheet)
    ws = tabs[TARGET_TAB_NAME]
    ensure_header(ws)
    existing = load_existing_rows(ws)
    if not existing:
        existing = load_old_metrics_rows(gc)
    state = load_state()
    oldest = resolve_fetch_oldest(state)

    legacy_records = load_legacy_records()
    slack_records, slack_summary = fetch_parsed_records(args.channel_name, args.limit, oldest=oldest)
    merged = merge_records(existing, [*legacy_records, *slack_records])
    merged, live_summary = enrich_records_with_live_contacts(merged)

    if args.dry_run:
        print(
            "dry-run: "
            f"既存={len(existing):,}, "
            f"過去取込={len(legacy_records):,}, "
            f"Slack新規候補={len(slack_records):,}, "
            f"Slack解析失敗={slack_summary.error_count:,}, "
            f"保存後={len(merged):,}, "
            f"チャンネル={args.channel_name}"
        )
        return

    rows = build_rows(merged)
    write_rows(ws, rows)
    source_rows = build_source_management_rows(
        len(merged),
        datetime.now().strftime("%Y/%m/%d %H:%M"),
        slack_summary,
        live_summary,
    )
    rule_rows = build_rule_rows()
    write_simple_rows(tabs[SOURCE_MANAGEMENT_TAB_NAME], source_rows, 14)
    write_simple_rows(tabs[RULE_TAB_NAME], rule_rows, 3)
    apply_table_style(spreadsheet, ws, len(rows), len(COLUMNS), [180, 180, 150, 200, 320, 240, 180], wrap="CLIP")
    apply_table_style(spreadsheet, tabs[SOURCE_MANAGEMENT_TAB_NAME], len(source_rows), 14, [180, 110, 140, 70, 220, 160, 120, 280, 140, 90, 140, 90, 80, 280], wrap="CLIP")
    apply_table_style(spreadsheet, tabs[RULE_TAB_NAME], len(rule_rows), 3, [150, 420, 360], wrap="WRAP")
    for tab in tabs.values():
        apply_protection(spreadsheet, tab)
    latest_ts = oldest
    if slack_records:
        latest_ts = max((record.slack_ts for record in slack_records if record.slack_ts), default=oldest)
    save_state(latest_ts or "", len(merged), args.channel_name, slack_summary)

    print(
        f"【アドネス株式会社】個別面談データ（収集） / {TARGET_TAB_NAME} を更新しました。"
        f"保存件数={len(merged):,}"
    )


if __name__ == "__main__":
    main()
