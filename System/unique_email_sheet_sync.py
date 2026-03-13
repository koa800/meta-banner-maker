#!/usr/bin/env python3
"""
メールアドレス関連の確認用シートを再生成する。

対象シート:
- タブ1: UUメールアドレス
- タブ2: 日別UUメールアドレス数
- タブ3: 複数アドレスユーザー
- タブ4: メール集計サマリー

母集団:
- 【アドネス株式会社】顧客データ（メールアドレスのみ）: 未転換リード
- 【アドネス株式会社】顧客データ（複数イベント）: 顧客マスタ

登録日補完:
- 【アドネス株式会社】集客データ（メールアドレス）: UTAGE元データ
- 過去のUTAGE登録者CSV: 過去分の補完
- 【アドネス株式会社】顧客データ（メールアドレスのみ）: 旧メール集客データ

定義:
- UUメールアドレス数:
  顧客マスタ + メールのみ のユニークメールアドレス数
- 実際のユニーク人数（暫定）:
  UUメールアドレス数 - 追加メールアドレス数
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from sheets_manager import get_client


RAW_SOURCE_SHEET_ID = "1l5yD6xUL-1ZC73KrMtCCkDsfhx8D8C4vhylaX3VOoL4"
LEGACY_LEAD_SHEET_ID = "1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00"
MASTER_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
TARGET_SHEET_ID = "1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8"

UU_TAB_NAME = "UUメールアドレス"
DAILY_TAB_NAME = "日別UUメールアドレス数"
MULTI_TAB_NAME = "複数アドレスユーザー"
SUMMARY_TAB_NAME = "メール集計サマリー"
SOURCE_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

PAST_UTAGE_CSV_DIR = Path("/Users/koa800/Desktop/過去のCVSデータ/UATGE")
DATE_CACHE_PATH = Path(__file__).resolve().parent / "data" / "email_first_registration_cache.json"
STATE_PATH = Path(__file__).resolve().parent / "data" / "unique_email_sheet_state.json"
LOCK_PATH = Path(__file__).resolve().parent / "data" / "unique_email_sheet_sync.lock"

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "UU自動生成"


class FileLock:
    """ファイルベースの簡易ロック。UUメール再生成の同時実行を防ぐ。"""

    def __init__(self, lock_path: Path = LOCK_PATH, timeout_seconds: int = 1800):
        self.lock_path = Path(lock_path)
        self.timeout_seconds = timeout_seconds

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_path.exists():
            try:
                lock_data = json.loads(self.lock_path.read_text())
                locked_at = datetime.fromisoformat(lock_data.get("locked_at", ""))
                elapsed = (datetime.now() - locked_at).total_seconds()
                if elapsed < self.timeout_seconds:
                    raise RuntimeError(
                        f"UUメール更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"unique_email_sheet_sync (PID: {os.getpid()})",
        }
        self.lock_path.write_text(json.dumps(payload, ensure_ascii=False))

    def release(self) -> None:
        if self.lock_path.exists():
            self.lock_path.unlink()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


@dataclass
class MultiAddressUserRecord:
    customer_id: str
    email_count: int
    emails: str


@dataclass
class DailyUURecord:
    date: str
    count: int
    cumulative_count: int


def normalize_email(raw: str) -> str:
    email = str(raw or "").strip().lower()
    email = email.replace("＠", "@").replace("．", ".").replace("，", ",")
    email = email.replace("mailto:", "")
    email = email.strip("'").strip('"')
    return email if EMAIL_RE.match(email) else ""


def normalize_date(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    match = DATE_RE.search(value)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def update_earliest(store: Dict[str, str], email: str, date_str: str) -> None:
    if not email or not date_str:
        return
    current = store.get(email, "")
    if not current or date_str < current:
        store[email] = date_str


def get_all_values_with_retry(ws) -> List[List[str]]:
    for attempt in range(4):
        try:
            return ws.get_all_values()
        except Exception as exc:
            message = str(exc)
            is_quota_error = "429" in message or "Quota exceeded" in message
            if not is_quota_error or attempt == 3:
                raise
            wait_seconds = 65 * (attempt + 1)
            print(f"読み取り上限に到達: {ws.title} を {wait_seconds} 秒待って再試行")
            time.sleep(wait_seconds)
    return []


def load_date_cache() -> Dict[str, str]:
    if not DATE_CACHE_PATH.exists():
        return {}
    try:
        data = json.loads(DATE_CACHE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    cache = {}
    for email, raw_date in data.items():
        normalized_email = normalize_email(email)
        normalized_date = normalize_date(raw_date)
        if normalized_email and normalized_date:
            cache[normalized_email] = normalized_date
    return cache


def save_date_cache(cache: Dict[str, str]) -> None:
    DATE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    ordered = {email: cache[email] for email in sorted(cache)}
    DATE_CACHE_PATH.write_text(json.dumps(ordered, ensure_ascii=False, indent=2))


def load_run_state() -> Dict[str, int]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_run_state(stats: Dict[str, int]) -> None:
    payload = {
        "updated_at": stats["updated_at"],
        "uu_email_count": stats["uu_email_count"],
        "dated_uu_email_count": stats["dated_uu_email_count"],
        "undated_uu_email_count": stats["undated_uu_email_count"],
        "lead_unique": stats["lead_unique"],
        "master_people_count": stats["master_people_count"],
        "multi_address_user_count": stats["multi_address_user_count"],
        "primary_email_duplicate_count": stats["primary_email_duplicate_count"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def detect_anomalies(stats: Dict[str, int], previous_state: Dict[str, int]) -> List[str]:
    anomalies: List[str] = []

    if stats["lead_unique"] <= 0:
        anomalies.append("メールのみのユニーク件数が 0 です。元データの読み取りに失敗している可能性があります。")
    if stats["master_people_count"] <= 0:
        anomalies.append("顧客マスター人数が 0 です。顧客マスタの読み取りに失敗している可能性があります。")
    if stats["primary_email_duplicate_count"] > 0:
        anomalies.append(
            f"顧客マスターの主メール重複が {stats['primary_email_duplicate_count']:,} 件あります。"
        )

    prev_uu = int(previous_state.get("uu_email_count", 0) or 0)
    if prev_uu:
        threshold = max(5000, int(prev_uu * 0.05))
        if prev_uu - stats["uu_email_count"] > threshold:
            anomalies.append(
                f"UUメールアドレス数が前回より {prev_uu - stats['uu_email_count']:,} 件減っています。"
            )

    prev_dated = int(previous_state.get("dated_uu_email_count", 0) or 0)
    if prev_dated:
        threshold = max(5000, int(prev_dated * 0.05))
        if prev_dated - stats["dated_uu_email_count"] > threshold:
            anomalies.append(
                f"登録日ありUUメールアドレス数が前回より {prev_dated - stats['dated_uu_email_count']:,} 件減っています。"
            )

    prev_undated = int(previous_state.get("undated_uu_email_count", 0) or 0)
    if prev_undated:
        threshold = max(5000, int(max(prev_undated, 1) * 0.35))
        if stats["undated_uu_email_count"] - prev_undated > threshold:
            anomalies.append(
                f"登録日空欄UUメールアドレス数が前回より {stats['undated_uu_email_count'] - prev_undated:,} 件増えています。"
            )

    return anomalies


def build_source_management_rows() -> List[List[str]]:
    return [
        ["区分", "シート名", "タブ / 場所", "参照先", "役割"],
        [
            "母集団",
            "顧客データ（複数イベント）",
            "顧客マスタ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk/edit","シートを開く")',
            "UUメールアドレスの対象に含める",
        ],
        [
            "母集団",
            "顧客データ（メールアドレスのみ）",
            "メール集客データ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00/edit","シートを開く")',
            "UUメールアドレスの対象に含める",
        ],
        [
            "登録日補完",
            "集客データ（メールアドレス）",
            "各流入経路タブの A列",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1l5yD6xUL-1ZC73KrMtCCkDsfhx8D8C4vhylaX3VOoL4/edit","シートを開く")',
            "日常運用で使う登録日の正本",
        ],
        [
            "初回整備のみ",
            "過去UTAGE CSV",
            str(PAST_UTAGE_CSV_DIR),
            "",
            "初回整備で過去分を補完した履歴",
        ],
        [
            "初回整備のみ",
            "顧客データ（メールアドレスのみ）",
            "メール集客データ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00/edit","シートを開く")',
            "初回整備で旧登録日を補完した履歴",
        ],
        [
            "出力",
            "集客データ（UUメールアドレス）",
            "UUメールアドレス / 日別UUメールアドレス数 / 複数アドレスユーザー / メール集計サマリー",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8/edit","シートを開く")',
            "自動生成結果を書き戻す",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "目的"],
        ["母集団", "顧客マスター + メールのみ だけを使う", "メール集客の全体像を安定して管理するため"],
        ["登録日", "集客データ（メールアドレス）の各流入経路タブ A列 を正とし、同じメールは最も古い日付を使う", "登録日の正本を1つに固定するため"],
        ["件数の増やし方", "UTAGE元データや過去CSVだけで新しいメール件数を足さない", "母集団が勝手に膨らまないようにするため"],
        ["複数アドレス", "1顧客IDでメールアドレスを2個以上持つ人だけを複数アドレスユーザーに出す", "人数とメール数を分けて見るため"],
        ["自動生成タブ", "UUメールアドレス / 日別UUメールアドレス数 / 複数アドレスユーザー / メール集計サマリー は手編集しない", "再生成で上書きされるため"],
        ["異常検知", "主メール重複や件数急減を検知したら更新を止める", "壊れた値で上書きしないため"],
        ["更新頻度", "Orchestrator が 2時間ごとに再生成する", "手運用に戻らないようにするため"],
        ["変更時", "参照元の構造を変える前に このタブ / コード / ドキュメント を先に更新する", "ルールが形骸化しないようにするため"],
    ]

def collect_sheet_earliest_dates(worksheets) -> Tuple[Dict[str, str], Dict[str, int]]:
    earliest_dates: Dict[str, str] = {}
    rows_scanned = 0
    valid_rows = 0
    tab_count = 0

    for ws in worksheets:
        tab_count += 1
        values = get_all_values_with_retry(ws)
        if not values:
            continue
        for row in values[1:]:
            rows_scanned += 1
            if len(row) <= 1:
                continue
            email = normalize_email(row[1])
            registered_at = normalize_date(row[0])
            if not email or not registered_at:
                continue
            valid_rows += 1
            update_earliest(earliest_dates, email, registered_at)

    stats = {
        "tab_count": tab_count,
        "rows_scanned": rows_scanned,
        "valid_rows": valid_rows,
        "unique_emails": len(earliest_dates),
    }
    return earliest_dates, stats


def collect_csv_earliest_dates(folder: Path) -> Tuple[Dict[str, str], Dict[str, int]]:
    earliest_dates: Dict[str, str] = {}
    files = sorted(folder.glob("登録者_*.csv"))
    rows_scanned = 0
    valid_rows = 0

    for path in files:
        with path.open("r", encoding="cp932", errors="ignore", newline="") as fh:
            reader = csv.reader(fh)
            try:
                header = next(reader)
            except StopIteration:
                continue

            try:
                email_idx = header.index("メールアドレス")
                registered_idx = header.index("登録日時")
            except ValueError:
                continue

            for row in reader:
                rows_scanned += 1
                if len(row) <= max(email_idx, registered_idx):
                    continue
                email = normalize_email(row[email_idx])
                registered_at = normalize_date(row[registered_idx])
                if not email or not registered_at:
                    continue
                valid_rows += 1
                update_earliest(earliest_dates, email, registered_at)

    stats = {
        "file_count": len(files),
        "rows_scanned": rows_scanned,
        "valid_rows": valid_rows,
        "unique_emails": len(earliest_dates),
    }
    return earliest_dates, stats


def merge_earliest_dates(target: Dict[str, str], source: Dict[str, str]) -> None:
    for email, date_str in source.items():
        update_earliest(target, email, date_str)


def collect_registration_dates(gc) -> Tuple[Dict[str, str], Dict[str, int]]:
    raw_spreadsheet = gc.open_by_key(RAW_SOURCE_SHEET_ID)
    raw_dates, raw_stats = collect_sheet_earliest_dates(raw_spreadsheet.worksheets())

    legacy_ws = gc.open_by_key(LEGACY_LEAD_SHEET_ID).worksheet("メール集客データ")
    legacy_dates, legacy_stats = collect_sheet_earliest_dates([legacy_ws])

    csv_dates, csv_stats = collect_csv_earliest_dates(PAST_UTAGE_CSV_DIR)

    combined_dates = load_date_cache()
    merge_earliest_dates(combined_dates, raw_dates)
    merge_earliest_dates(combined_dates, csv_dates)
    merge_earliest_dates(combined_dates, legacy_dates)
    save_date_cache(combined_dates)

    stats = {
        "raw_tab_count": raw_stats["tab_count"],
        "raw_rows_scanned": raw_stats["rows_scanned"],
        "raw_valid_rows": raw_stats["valid_rows"],
        "raw_unique_emails": raw_stats["unique_emails"],
        "legacy_rows_scanned": legacy_stats["rows_scanned"],
        "legacy_valid_rows": legacy_stats["valid_rows"],
        "legacy_unique_emails": legacy_stats["unique_emails"],
        "csv_file_count": csv_stats["file_count"],
        "csv_rows_scanned": csv_stats["rows_scanned"],
        "csv_valid_rows": csv_stats["valid_rows"],
        "csv_unique_emails": csv_stats["unique_emails"],
        "registration_cache_count": len(combined_dates),
    }
    return combined_dates, stats


def build_daily_uu_records(uu_records: Iterable[Tuple[str, str]]) -> List[DailyUURecord]:
    counter: Counter[str] = Counter()
    for registered_at, _email in uu_records:
        if registered_at:
            counter[registered_at] += 1

    cumulative = 0
    daily_records = []
    for date_str in sorted(counter):
        cumulative += counter[date_str]
        daily_records.append(
            DailyUURecord(
                date=date_str,
                count=counter[date_str],
                cumulative_count=cumulative,
            )
        )
    return daily_records


def collect_data() -> Tuple[List[Tuple[str, str]], List[DailyUURecord], List[MultiAddressUserRecord], Dict[str, int]]:
    gc = get_client()

    registration_dates, registration_stats = collect_registration_dates(gc)
    lead_ws = gc.open_by_key(LEGACY_LEAD_SHEET_ID).worksheet("メール集客データ")
    lead_vals = get_all_values_with_retry(lead_ws)
    master_ws = gc.open_by_key(MASTER_SHEET_ID).worksheet("顧客マスタ")
    master_vals = get_all_values_with_retry(master_ws)

    unique_emails = set()
    lead_unique = set()
    master_all_emails = set()
    multi_address_users: List[MultiAddressUserRecord] = []
    extra_email_count = 0
    primary_email_counter: Counter[str] = Counter()

    for row in lead_vals[1:]:
        if len(row) <= 1:
            continue
        email = normalize_email(row[1])
        if not email:
            continue
        unique_emails.add(email)
        lead_unique.add(email)

    master_header = master_vals[1]
    idx_customer_id = master_header.index("顧客ID")
    idx_email1 = master_header.index("メールアドレス")
    idx_email2 = master_header.index("メールアドレス2")

    master_people_count = max(len(master_vals) - 2, 0)

    for row_num, row in enumerate(master_vals[2:], start=3):
        customer_id = row[idx_customer_id].strip() if len(row) > idx_customer_id else ""
        row_emails: List[str] = []

        primary_email = normalize_email(row[idx_email1]) if len(row) > idx_email1 else ""
        if primary_email:
            primary_email_counter[primary_email] += 1

        for idx in (idx_email1, idx_email2):
            if len(row) <= idx or not row[idx].strip():
                continue
            for raw_email in row[idx].split(","):
                email = normalize_email(raw_email)
                if not email:
                    continue
                unique_emails.add(email)
                master_all_emails.add(email)
                if email not in row_emails:
                    row_emails.append(email)

        if len(row_emails) >= 2:
            multi_address_users.append(
                MultiAddressUserRecord(
                    customer_id=customer_id or str(row_num - 2),
                    email_count=len(row_emails),
                    emails=", ".join(row_emails),
                )
            )
            extra_email_count += len(row_emails) - 1

    uu_records = sorted(
        ((registration_dates.get(email, ""), email) for email in unique_emails),
        key=lambda item: ((item[0] == ""), item[0], item[1]),
    )
    daily_records = build_daily_uu_records(uu_records)

    multi_address_users.sort(
        key=lambda item: int(item.customer_id) if item.customer_id.isdigit() else item.customer_id
    )

    dated_uu_email_count = sum(1 for registered_at, _email in uu_records if registered_at)
    undated_uu_email_count = len(uu_records) - dated_uu_email_count
    primary_email_duplicate_count = sum(
        1 for count in primary_email_counter.values() if count >= 2
    )

    stats = {
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "lead_unique": len(lead_unique),
        "master_people_count": master_people_count,
        "master_email_unique": len(master_all_emails),
        "primary_email_duplicate_count": primary_email_duplicate_count,
        "uu_email_count": len(uu_records),
        "dated_uu_email_count": dated_uu_email_count,
        "undated_uu_email_count": undated_uu_email_count,
        "daily_uu_days": len(daily_records),
        "multi_address_user_count": len(multi_address_users),
        "extra_email_count": extra_email_count,
        "actual_unique_people_count": len(uu_records) - extra_email_count,
        **registration_stats,
    }
    return uu_records, daily_records, multi_address_users, stats


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}

    if "ユニークメール一覧" in tabs and UU_TAB_NAME not in tabs:
        tabs["ユニークメール一覧"].update_title(UU_TAB_NAME)
        tabs[UU_TAB_NAME] = tabs.pop("ユニークメール一覧")
    if "重複メール確認" in tabs and MULTI_TAB_NAME not in tabs:
        tabs["重複メール確認"].update_title(MULTI_TAB_NAME)
        tabs[MULTI_TAB_NAME] = tabs.pop("重複メール確認")
    if "重複メールアドレス" in tabs and MULTI_TAB_NAME not in tabs:
        tabs["重複メールアドレス"].update_title(MULTI_TAB_NAME)
        tabs[MULTI_TAB_NAME] = tabs.pop("重複メールアドレス")
    if "確認" in tabs and SUMMARY_TAB_NAME not in tabs:
        tabs["確認"].update_title(SUMMARY_TAB_NAME)
        tabs[SUMMARY_TAB_NAME] = tabs.pop("確認")

    ordered_names = [
        UU_TAB_NAME,
        DAILY_TAB_NAME,
        MULTI_TAB_NAME,
        SUMMARY_TAB_NAME,
        SOURCE_TAB_NAME,
        RULE_TAB_NAME,
    ]
    ensured = {}
    for idx, name in enumerate(ordered_names):
        if name in tabs:
            ensured[name] = tabs[name]
            continue
        ensured[name] = spreadsheet.add_worksheet(title=name, rows=1000, cols=4)

    spreadsheet.batch_update(
        {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {"sheetId": ensured[name].id, "index": idx},
                        "fields": "index",
                    }
                }
                for idx, name in enumerate(ordered_names)
            ]
        }
    )
    return ensured


def write_table(ws, rows: List[List[str]]) -> None:
    row_count = max(len(rows), 1)
    col_count = max((len(row) for row in rows), default=1)

    if row_count > ws.row_count:
        ws.add_rows(row_count - ws.row_count + 200)
    if col_count > ws.col_count:
        ws.add_cols(col_count - ws.col_count)

    ws.clear()

    chunk_size = 50000
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start : start + chunk_size]
        start_row = start + 1
        end_row = start + len(chunk)
        range_name = f"A{start_row}:{col_letter(col_count)}{end_row}"
        for attempt in range(4):
            try:
                ws.update(range_name=range_name, values=chunk, value_input_option="USER_ENTERED")
                break
            except Exception as exc:
                message = str(exc)
                is_quota_error = "429" in message or "Quota exceeded" in message
                if not is_quota_error or attempt == 3:
                    raise
                wait_seconds = 65 * (attempt + 1)
                print(
                    f"書き込み上限に到達: {ws.title} {range_name} "
                    f"を {wait_seconds} 秒待って再試行"
                )
                time.sleep(wait_seconds)

    ws.resize(rows=row_count, cols=col_count)
    ws.spreadsheet.batch_update(
        {
            "requests": [
                {
                    "updateSheetProperties": {
                        "properties": {
                            "sheetId": ws.id,
                            "gridProperties": {"frozenRowCount": 1},
                        },
                        "fields": "gridProperties.frozenRowCount",
                    }
                },
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
            ]
        }
    )


def apply_formatting(target, tabs) -> None:
    header_background = {"red": 0.25882354, "green": 0.52156866, "blue": 0.95686275}
    header_foreground = {"red": 1, "green": 1, "blue": 1}
    sheet_configs = {
        UU_TAB_NAME: {
            "col_widths": [150, 360],
            "numeric_cols": [],
            "tab_color": {"red": 0.357, "green": 0.584, "blue": 0.976},
        },
        DAILY_TAB_NAME: {
            "col_widths": [140, 140, 170],
            "numeric_cols": [1, 2],
            "tab_color": {"red": 0.973, "green": 0.776, "blue": 0.396},
        },
        MULTI_TAB_NAME: {
            "col_widths": [120, 120, 620],
            "numeric_cols": [1],
            "tab_color": {"red": 0.851, "green": 0.918, "blue": 0.827},
        },
        SUMMARY_TAB_NAME: {
            "col_widths": [240, 180, 540],
            "numeric_cols": [1],
            "tab_color": {"red": 0.8, "green": 0.8, "blue": 0.8},
        },
        SOURCE_TAB_NAME: {
            "col_widths": [110, 220, 280, 130, 320],
            "numeric_cols": [],
            "tab_color": {"red": 0.984, "green": 0.757, "blue": 0.18},
        },
        RULE_TAB_NAME: {
            "col_widths": [120, 360, 320],
            "numeric_cols": [],
            "tab_color": {"red": 0.651, "green": 0.816, "blue": 0.89},
        },
    }

    metadata = target.fetch_sheet_metadata()
    target_sheet_ids = {tabs[name].id for name in sheet_configs}
    requests = []

    for sheet in metadata.get("sheets", []):
        sheet_id = sheet.get("properties", {}).get("sheetId")
        if sheet_id not in target_sheet_ids:
            continue
        for banded_range in sheet.get("bandedRanges", []):
            banded_range_id = banded_range.get("bandedRangeId")
            if banded_range_id is not None:
                requests.append({"deleteBanding": {"bandedRangeId": banded_range_id}})

    for name, config in sheet_configs.items():
        ws = tabs[name]
        end_column = len(config["col_widths"])

        requests.append(
            {
                "unmergeCells": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": end_column,
                    }
                }
            }
        )

        for idx, width in enumerate(config["col_widths"]):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id},
                    "cell": {
                        "userEnteredFormat": {
                            "wrapStrategy": "WRAP",
                            "horizontalAlignment": "LEFT",
                            "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                        }
                    },
                    "fields": "userEnteredFormat(wrapStrategy,horizontalAlignment,textFormat)",
                }
            }
        )

        requests.append(
            {
                "repeatCell": {
                    "range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": header_background,
                            "horizontalAlignment": "CENTER",
                            "wrapStrategy": "WRAP",
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": header_foreground,
                                "fontFamily": "Arial",
                                "fontSize": 12,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,horizontalAlignment,wrapStrategy,textFormat)",
                }
            }
        )

        for numeric_col in config["numeric_cols"]:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 1,
                            "startColumnIndex": numeric_col,
                            "endColumnIndex": numeric_col + 1,
                        },
                        "cell": {"userEnteredFormat": {"horizontalAlignment": "RIGHT"}},
                        "fields": "userEnteredFormat.horizontalAlignment",
                    }
                }
            )

        requests.append(
            {
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": end_column,
                        },
                        "rowProperties": {
                            "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                            "secondBandColor": {"red": 0.91, "green": 0.941, "blue": 0.996},
                            "headerColor": {"red": 1, "green": 1, "blue": 1},
                        },
                    }
                }
            }
        )

        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {"sheetId": ws.id, "tabColor": config["tab_color"]},
                    "fields": "tabColor",
                }
            }
        )

    target.batch_update({"requests": requests})


def apply_protections(target, tabs) -> None:
    protected_names = [UU_TAB_NAME, DAILY_TAB_NAME, MULTI_TAB_NAME, SUMMARY_TAB_NAME]
    target_sheet_ids = {tabs[name].id for name in protected_names}
    metadata = target.fetch_sheet_metadata(
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
            if (
                range_sheet_id in target_sheet_ids
                and str(description).startswith(PROTECTION_PREFIX)
            ):
                requests.append(
                    {"deleteProtectedRange": {"protectedRangeId": protected_range["protectedRangeId"]}}
                )

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
        target.batch_update({"requests": requests})


def write_target(
    uu_records: Iterable[Tuple[str, str]],
    daily_records: Iterable[DailyUURecord],
    multi_address_users: Iterable[MultiAddressUserRecord],
    stats: Dict[str, int],
) -> None:
    gc = get_client()
    target = gc.open_by_key(TARGET_SHEET_ID)
    tabs = ensure_tabs(target)

    uu_rows = [["登録日", "メールアドレス"]]
    uu_rows.extend([[registered_at, email] for registered_at, email in uu_records])

    daily_rows = [["日付", "UUメールアドレス数", "累計UUメールアドレス数"]]
    daily_rows.extend(
        [[record.date, f"{record.count:,}", f"{record.cumulative_count:,}"] for record in daily_records]
    )

    multi_rows = [["顧客ID", "メールアドレス数", "メールアドレス"]]
    multi_rows.extend(
        [[record.customer_id, f"{record.email_count:,}", record.emails] for record in multi_address_users]
    )

    summary_rows = [
        ["項目", "数値", "定義"],
        ["更新日時", stats["updated_at"], "この集計を作り直した時刻"],
        ["UUメールアドレス数", f"{stats['uu_email_count']:,}", "顧客マスター + メールのみ のユニークメールアドレス数"],
        ["登録日ありUUメールアドレス数", f"{stats['dated_uu_email_count']:,}", "母集団のうち初回登録日を補完できているメールアドレス数"],
        ["登録日空欄UUメールアドレス数", f"{stats['undated_uu_email_count']:,}", "母集団のうち初回登録日がまだ特定できていないメールアドレス数"],
        ["複数アドレスユーザー数", f"{stats['multi_address_user_count']:,}", "メールアドレスを2つ以上持っている顧客IDの数"],
        ["主メール重複数", f"{stats['primary_email_duplicate_count']:,}", "顧客マスターのメールアドレス 同士で重複している件数"],
        ["実際のユニーク人数（暫定）", f"{stats['actual_unique_people_count']:,}", "UUメールアドレス数 - 追加メールアドレス数"],
    ]
    source_rows = build_source_management_rows()
    rule_rows = build_rule_rows()

    write_table(tabs[UU_TAB_NAME], uu_rows)
    write_table(tabs[DAILY_TAB_NAME], daily_rows)
    write_table(tabs[MULTI_TAB_NAME], multi_rows)
    write_table(tabs[SUMMARY_TAB_NAME], summary_rows)
    write_table(tabs[SOURCE_TAB_NAME], source_rows)
    write_table(tabs[RULE_TAB_NAME], rule_rows)
    apply_formatting(target, tabs)
    apply_protections(target, tabs)


def main() -> None:
    parser = argparse.ArgumentParser(description="メール確認用シートを再生成する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みせず件数だけ確認する")
    parser.add_argument(
        "--force-write-on-anomaly",
        action="store_true",
        help="異常検知があっても強制的に書き込む",
    )
    args = parser.parse_args()

    with FileLock():
        uu_records, daily_records, multi_address_users, stats = collect_data()
        previous_state = load_run_state()
        anomalies = detect_anomalies(stats, previous_state)

        print(
            f"UTAGE元データユニーク: {stats['raw_unique_emails']} / "
            f"過去CSVユニーク: {stats['csv_unique_emails']} / "
            f"登録日キャッシュ: {stats['registration_cache_count']} / "
            f"UUメールアドレス: {stats['uu_email_count']} / "
            f"登録日あり: {stats['dated_uu_email_count']} / "
            f"登録日空欄: {stats['undated_uu_email_count']} / "
            f"日別UU日数: {stats['daily_uu_days']} / "
            f"複数アドレスユーザー: {stats['multi_address_user_count']} / "
            f"主メール重複: {stats['primary_email_duplicate_count']} / "
            f"実際のユニーク人数（暫定）: {stats['actual_unique_people_count']}"
        )

        if anomalies:
            print("異常検知:")
            for message in anomalies:
                print(f"- {message}")
            if not args.force_write_on_anomaly:
                raise SystemExit(2)

        if args.dry_run:
            return

        write_target(uu_records, daily_records, multi_address_users, stats)
        save_run_state(stats)
        print(
            "書き込み完了: "
            "UUメールアドレス / 日別UUメールアドレス数 / 複数アドレスユーザー / "
            "メール集計サマリー / データソース管理 / データ追加ルール"
        )


if __name__ == "__main__":
    main()
