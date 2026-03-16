#!/usr/bin/env python3
"""
メール集計の統合シートを再生成する。

対象シート:
- 日別メール登録件数
- 日別メール登録件数（UU）
- 複数アドレスユーザー
- メール集計サマリー
- データソース管理
- データ追加ルール

定義:
- 2026/03/06 以前:
  既存の「全メール登録数」「UUメールアドレス」シートの確定値を継承する
- 2026/03/07 以降:
  「集客データ（メールアドレス）」を正本にして再集計する
- 日別メール登録件数（UU）:
  そのメールが「集客データ（メールアドレス）」で最初に確認された日にだけ 1件と数える
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
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from sheets_manager import get_client


RAW_SOURCE_SHEET_ID = "1l5yD6xUL-1ZC73KrMtCCkDsfhx8D8C4vhylaX3VOoL4"
MASTER_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
LEGACY_UNIQUE_SHEET_ID = "1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8"
LEGACY_COUNT_SHEET_ID = "1RsRkGaHCFsFc1nT1lMQFyNG-f13llH4UX9Bl_EYxNjU"
TARGET_SHEET_ID = "13HS9KmlTdxQwMMaK45H3Ga1mMTUiJdhYKWnrExge_yY"

COUNT_TAB_NAME = "日別メール登録件数"
UU_COUNT_TAB_NAME = "日別メール登録件数（UU）"
MULTI_TAB_NAME = "複数アドレスユーザー"
SUMMARY_TAB_NAME = "メール集計サマリー"
SOURCE_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

LEGACY_DAILY_COUNT_TAB = "日別メール登録件数"
LEGACY_DAILY_UU_TAB = "日別UUメールアドレス数"
LEGACY_UU_LIST_TAB = "UUメールアドレス"
MASTER_TAB_NAME = "顧客マスタ"

CUTOFF_DATE = "2026/03/07"
PRE_CUTOFF_DATE = "2026/03/06"
START_DATE = "2025/01/01"
STATE_PATH = Path(__file__).resolve().parent / "data" / "email_collection_metrics_sheet_state.json"
LOCK_PATH = Path(__file__).resolve().parent / "data" / "email_collection_metrics_sheet_sync.lock"
ROOT_DIR = Path(__file__).resolve().parent.parent
HISTORY_SNAPSHOT_PATH = ROOT_DIR / "Master" / "output" / "email_collection_metrics_history_snapshot.json"

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "メール集計自動生成"


class FileLock:
    """ファイルベースの簡易ロック。二重実行を防ぐ。"""

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
                        f"メール集計シート更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"email_collection_metrics_sheet_sync (PID: {os.getpid()})",
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
class DailyRecord:
    date: str
    count: int
    cumulative_count: int


@dataclass
class MultiAddressUserRecord:
    customer_id: str
    email_count: int
    emails: str


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


def parse_int(raw: str) -> int:
    value = str(raw or "").strip()
    if not value:
        return 0
    digits = re.sub(r"[^\d-]", "", value)
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


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


def load_run_state() -> Dict[str, int]:
    if not STATE_PATH.exists():
        return {}
    try:
        data = json.loads(STATE_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_history_snapshot() -> Dict[str, object]:
    if not HISTORY_SNAPSHOT_PATH.exists():
        raise FileNotFoundError(
            f"履歴スナップショットが見つかりません: {HISTORY_SNAPSHOT_PATH}"
        )
    try:
        data = json.loads(HISTORY_SNAPSHOT_PATH.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(f"履歴スナップショットを読めません: {HISTORY_SNAPSHOT_PATH}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"履歴スナップショットの形式が不正です: {HISTORY_SNAPSHOT_PATH}")
    return data


def save_history_snapshot(snapshot: Dict[str, object]) -> None:
    HISTORY_SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_SNAPSHOT_PATH.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2))


def save_run_state(stats: Dict[str, int]) -> None:
    payload = {
        "updated_at": stats["updated_at"],
        "total_registration_count": stats["total_registration_count"],
        "total_uu_count": stats["total_uu_count"],
        "latest_date": stats["latest_date"],
        "future_registration_total": stats["future_registration_total"],
        "future_uu_total": stats["future_uu_total"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def detect_anomalies(stats: Dict[str, int], previous_state: Dict[str, int]) -> List[str]:
    anomalies: List[str] = []
    if stats["raw_tab_count"] <= 0:
        anomalies.append("【アドネス株式会社】集客データ（メールアドレス）の流入経路タブ数が 0 です。")
    if stats["raw_valid_rows"] <= 0:
        anomalies.append("【アドネス株式会社】集客データ（メールアドレス）から有効な行を読み取れていません。")
    if stats["future_registration_days"] <= 0:
        anomalies.append("2026/03/07 以降の日別メール登録件数を作れていません。")
    if stats["future_uu_days"] <= 0:
        anomalies.append("2026/03/07 以降の日別メール登録件数（UU）を作れていません。")
    if stats["total_registration_count"] <= 0:
        anomalies.append("日別メール登録件数の合計が 0 です。")
    if stats["total_uu_count"] <= 0:
        anomalies.append("日別メール登録件数（UU）の合計が 0 です。")
    if stats["registration_start_date"] != START_DATE:
        anomalies.append(
            f"日別メール登録件数の開始日が {START_DATE} ではなく {stats['registration_start_date'] or '空欄'} です。"
        )
    if stats["uu_start_date"] != START_DATE:
        anomalies.append(
            f"日別メール登録件数（UU）の開始日が {START_DATE} ではなく {stats['uu_start_date'] or '空欄'} です。"
        )
    if stats["future_registration_total"] < stats["future_uu_total"]:
        anomalies.append("2026/03/07 以降のメール登録件数より UU件数の方が大きくなっています。")

    prev_total = int(previous_state.get("total_registration_count", 0) or 0)
    if prev_total:
        threshold = max(3000, int(prev_total * 0.05))
        if prev_total - stats["total_registration_count"] > threshold:
            anomalies.append(
                f"日別メール登録件数の合計が前回より {prev_total - stats['total_registration_count']:,} 件減っています。"
            )

    prev_uu = int(previous_state.get("total_uu_count", 0) or 0)
    if prev_uu:
        threshold = max(3000, int(prev_uu * 0.05))
        if prev_uu - stats["total_uu_count"] > threshold:
            anomalies.append(
                f"日別メール登録件数（UU）の合計が前回より {prev_uu - stats['total_uu_count']:,} 件減っています。"
            )

    return anomalies


def build_daily_records(counter: Counter[str]) -> List[DailyRecord]:
    cumulative = 0
    records: List[DailyRecord] = []
    for date_str in sorted(counter):
        cumulative += counter[date_str]
        records.append(DailyRecord(date=date_str, count=counter[date_str], cumulative_count=cumulative))
    return records


def load_legacy_daily_counter(sheet_id: str, tab_name: str, start_date: str, cutoff_date: str) -> Counter[str]:
    gc = get_client()
    ws = gc.open_by_key(sheet_id).worksheet(tab_name)
    values = get_all_values_with_retry(ws)
    counter: Counter[str] = Counter()
    for row in values[1:]:
        if len(row) < 2:
            continue
        date_str = normalize_date(row[0])
        if not date_str or date_str < start_date or date_str >= cutoff_date:
            continue
        counter[date_str] = parse_int(row[1])
    return counter


def load_legacy_seed_emails() -> set[str]:
    gc = get_client()
    ws = gc.open_by_key(LEGACY_UNIQUE_SHEET_ID).worksheet(LEGACY_UU_LIST_TAB)
    values = get_all_values_with_retry(ws)
    seed: set[str] = set()
    for row in values[1:]:
        if len(row) < 2:
            continue
        date_str = normalize_date(row[0])
        email = normalize_email(row[1])
        if not email:
            continue
        if not date_str or date_str < CUTOFF_DATE:
            seed.add(email)
    return seed


def build_history_snapshot_from_legacy() -> Dict[str, object]:
    historical_registration_counter = load_legacy_daily_counter(
        LEGACY_COUNT_SHEET_ID,
        LEGACY_DAILY_COUNT_TAB,
        START_DATE,
        CUTOFF_DATE,
    )
    historical_uu_counter = load_legacy_daily_counter(
        LEGACY_UNIQUE_SHEET_ID,
        LEGACY_DAILY_UU_TAB,
        START_DATE,
        CUTOFF_DATE,
    )
    historical_seed = load_legacy_seed_emails()
    return {
        "generated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "range_start": START_DATE,
        "range_end": PRE_CUTOFF_DATE,
        "registration_daily": dict(sorted(historical_registration_counter.items())),
        "uu_daily": dict(sorted(historical_uu_counter.items())),
        "historical_seed_emails": sorted(historical_seed),
        "registration_total": sum(historical_registration_counter.values()),
        "uu_total": sum(historical_uu_counter.values()),
        "historical_seed_email_count": len(historical_seed),
        "source_note": "runtimeでは旧シートを参照せず、このスナップショットを使う",
    }


def collect_future_current_data(historical_seed: set[str]) -> Tuple[Counter[str], Counter[str], Dict[str, int]]:
    gc = get_client()
    spreadsheet = gc.open_by_key(RAW_SOURCE_SHEET_ID)

    registration_counter: Counter[str] = Counter()
    earliest_raw_by_email: Dict[str, str] = {}
    tab_count = 0
    rows_scanned = 0
    valid_rows = 0
    invalid_rows = 0

    for ws in spreadsheet.worksheets():
        tab_count += 1
        values = get_all_values_with_retry(ws)
        for row in values[1:]:
            if len(row) <= 1:
                continue
            rows_scanned += 1
            date_str = normalize_date(row[0])
            email = normalize_email(row[1])
            if not date_str or not email:
                invalid_rows += 1
                continue
            valid_rows += 1
            current_earliest = earliest_raw_by_email.get(email, "")
            if not current_earliest or date_str < current_earliest:
                earliest_raw_by_email[email] = date_str
            if date_str >= CUTOFF_DATE:
                registration_counter[date_str] += 1

    uu_counter: Counter[str] = Counter()
    for email, earliest_date in earliest_raw_by_email.items():
        if email in historical_seed:
            continue
        if earliest_date >= CUTOFF_DATE:
            uu_counter[earliest_date] += 1

    stats = {
        "raw_tab_count": tab_count,
        "raw_rows_scanned": rows_scanned,
        "raw_valid_rows": valid_rows,
        "raw_invalid_rows": invalid_rows,
        "raw_unique_emails": len(earliest_raw_by_email),
        "future_registration_days": len(registration_counter),
        "future_registration_total": sum(registration_counter.values()),
        "future_uu_days": len(uu_counter),
        "future_uu_total": sum(uu_counter.values()),
    }
    return registration_counter, uu_counter, stats


def collect_multi_address_users() -> Tuple[List[MultiAddressUserRecord], Dict[str, int]]:
    gc = get_client()
    ws = gc.open_by_key(MASTER_SHEET_ID).worksheet(MASTER_TAB_NAME)
    values = get_all_values_with_retry(ws)
    header = values[1]
    idx_customer_id = header.index("顧客ID")
    idx_email1 = header.index("メールアドレス")
    idx_email2 = header.index("メールアドレス2")

    records: List[MultiAddressUserRecord] = []
    extra_email_count = 0

    for row_num, row in enumerate(values[2:], start=3):
        customer_id = row[idx_customer_id].strip() if len(row) > idx_customer_id else ""
        row_emails: List[str] = []
        for idx in (idx_email1, idx_email2):
            if len(row) <= idx or not row[idx].strip():
                continue
            for raw_email in row[idx].split(","):
                email = normalize_email(raw_email)
                if email and email not in row_emails:
                    row_emails.append(email)

        if len(row_emails) >= 2:
            records.append(
                MultiAddressUserRecord(
                    customer_id=customer_id or str(row_num - 2),
                    email_count=len(row_emails),
                    emails=", ".join(row_emails),
                )
            )
            extra_email_count += len(row_emails) - 1

    stats = {
        "multi_address_user_count": len(records),
        "extra_email_count": extra_email_count,
    }
    return records, stats


def merge_counters(historical_counter: Counter[str], future_counter: Counter[str]) -> Counter[str]:
    merged: Dict[str, int] = {date_str: count for date_str, count in historical_counter.items()}
    for date_str, count in future_counter.items():
        merged[date_str] = count
    return Counter(merged)


def build_source_management_rows() -> List[List[str]]:
    return [
        ["区分", "シート名", "タブ / 場所", "参照先", "役割"],
        [
            "現行の正本",
            "【アドネス株式会社】集客データ（メールアドレス）",
            "各流入経路タブ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1l5yD6xUL-1ZC73KrMtCCkDsfhx8D8C4vhylaX3VOoL4/edit","シートを開く")',
            "2026/03/07 以降の登録件数と集客UUの正本",
        ],
        [
            "補助参照",
            "【アドネス株式会社】顧客データ（複数イベント）",
            "顧客マスタ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk/edit","シートを開く")',
            "複数アドレスユーザーの確認に使う",
        ],
        [
            "出力",
            "【アドネス株式会社】集客データ（メール集計）",
            "6タブ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/13HS9KmlTdxQwMMaK45H3Ga1mMTUiJdhYKWnrExge_yY/edit","シートを開く")',
            "集客データの重複あり件数と集客UUを一箇所で見る",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "目的"],
        ["シートの役割", "このシートはメール集客の加工データをまとめて見る統合版シート", "重複あり件数と集客UUを一箇所で判断するため"],
        ["現行の正本", "2026/03/07 以降は 【アドネス株式会社】集客データ（メールアドレス） を正とする", "今後の運用を一本化するため"],
        ["日別メール登録件数", "このタブは、重複ありのメール登録件数を見る場所", "登録という事実を日別で確認するため"],
        ["日別メール登録件数（UU）", "このタブは、集客で最初に確認されたメールだけを日別で見る場所", "新規メールの増え方を見るため"],
        ["複数アドレスユーザー", "このタブは、顧客マスタでメールアドレスを2件持つ顧客を見る場所", "名寄せの確認をするため"],
        ["メール集計サマリー", "このタブは、重複あり件数・集客UU・メール登録ユーザー数を要約して見る場所", "全体像を一目で判断するため"],
        ["データソース管理", "このタブは、どのシートを正本とし、どこを補助参照にしているかを見る場所", "参照元の認識ズレを防ぐため"],
        ["データ追加ルール", "このタブは、このシートの数え方と運用ルールを見る場所", "仕組みが形骸化しないようにするため"],
        ["媒体別分析", "今はソースを正本にし、媒体 × ファネルの集計は後段で作る", "後から LP や CR に切り戻せるようにするため"],
        ["手編集防止", "このシートの6タブは保護し、手編集しない", "再生成で上書きされるため"],
        ["異常検知", "開始日ずれ / 参照元タブ0件 / 当日側の件数欠損 / 件数急減を検知したら更新を止める", "壊れた値で上書きしないため"],
        ["更新頻度", "Orchestrator が 2時間ごとに再生成する", "定常運用で形骸化しないため"],
    ]


def collect_data() -> Tuple[List[DailyRecord], List[DailyRecord], List[MultiAddressUserRecord], Dict[str, int]]:
    history_snapshot = load_history_snapshot()
    historical_registration_counter = Counter(history_snapshot.get("registration_daily", {}))
    historical_uu_counter = Counter(history_snapshot.get("uu_daily", {}))
    historical_seed = set(history_snapshot.get("historical_seed_emails", []))
    future_registration_counter, future_uu_counter, raw_stats = collect_future_current_data(historical_seed)
    multi_records, multi_stats = collect_multi_address_users()

    merged_registration_counter = merge_counters(historical_registration_counter, future_registration_counter)
    merged_uu_counter = merge_counters(historical_uu_counter, future_uu_counter)

    registration_records = build_daily_records(merged_registration_counter)
    uu_records = build_daily_records(merged_uu_counter)

    stats = {
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "historical_daily_count_days": len(historical_registration_counter),
        "historical_daily_uu_days": len(historical_uu_counter),
        "historical_seed_emails": len(historical_seed),
        "history_snapshot_generated_at": str(history_snapshot.get("generated_at", "")),
        "raw_tab_count": raw_stats["raw_tab_count"],
        "raw_rows_scanned": raw_stats["raw_rows_scanned"],
        "raw_valid_rows": raw_stats["raw_valid_rows"],
        "raw_invalid_rows": raw_stats["raw_invalid_rows"],
        "raw_unique_emails": raw_stats["raw_unique_emails"],
        "future_registration_days": raw_stats["future_registration_days"],
        "future_registration_total": raw_stats["future_registration_total"],
        "future_uu_days": raw_stats["future_uu_days"],
        "future_uu_total": raw_stats["future_uu_total"],
        "multi_address_user_count": multi_stats["multi_address_user_count"],
        "email_registration_user_count": 0,
        "total_registration_count": sum(record.count for record in registration_records),
        "total_uu_count": sum(record.count for record in uu_records),
        "registration_start_date": registration_records[0].date if registration_records else "",
        "uu_start_date": uu_records[0].date if uu_records else "",
        "latest_date": registration_records[-1].date if registration_records else "",
    }
    stats["email_registration_user_count"] = max(
        stats["total_uu_count"] - stats["multi_address_user_count"],
        0,
    )
    return registration_records, uu_records, multi_records, stats


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered_names = [
        COUNT_TAB_NAME,
        UU_COUNT_TAB_NAME,
        MULTI_TAB_NAME,
        SUMMARY_TAB_NAME,
        SOURCE_TAB_NAME,
        RULE_TAB_NAME,
    ]
    ensured = {}
    for name in ordered_names:
        ensured[name] = tabs[name] if name in tabs else spreadsheet.add_worksheet(title=name, rows=1000, cols=5)

    for ws in spreadsheet.worksheets():
        if ws.title in ordered_names:
            continue
        values = ws.get_all_values()
        if ws.title == "シート1" and (not values or values == [[]]):
            spreadsheet.del_worksheet(ws)

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
                print(f"書き込み上限に到達: {ws.title} {range_name} を {wait_seconds} 秒待って再試行")
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
        COUNT_TAB_NAME: {
            "col_widths": [140, 170, 200],
            "numeric_cols": [1, 2],
            "tab_color": {"red": 0.357, "green": 0.584, "blue": 0.976},
        },
        UU_COUNT_TAB_NAME: {
            "col_widths": [140, 190, 220],
            "numeric_cols": [1, 2],
            "tab_color": {"red": 0.467, "green": 0.745, "blue": 0.886},
        },
        MULTI_TAB_NAME: {
            "col_widths": [140, 180, 520],
            "numeric_cols": [1],
            "tab_color": {"red": 0.973, "green": 0.776, "blue": 0.396},
        },
        SUMMARY_TAB_NAME: {
            "col_widths": [240, 180, 520],
            "numeric_cols": [1],
            "tab_color": {"red": 0.776, "green": 0.686, "blue": 0.933},
        },
        SOURCE_TAB_NAME: {
            "col_widths": [120, 260, 260, 130, 360],
            "numeric_cols": [],
            "tab_color": {"red": 0.984, "green": 0.757, "blue": 0.18},
        },
        RULE_TAB_NAME: {
            "col_widths": [150, 440, 320],
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
    protected_names = [
        COUNT_TAB_NAME,
        UU_COUNT_TAB_NAME,
        MULTI_TAB_NAME,
        SUMMARY_TAB_NAME,
        SOURCE_TAB_NAME,
        RULE_TAB_NAME,
    ]
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
        target.batch_update({"requests": requests})


def write_target(
    registration_records: Iterable[DailyRecord],
    uu_records: Iterable[DailyRecord],
    multi_records: Iterable[MultiAddressUserRecord],
    stats: Dict[str, int],
) -> None:
    gc = get_client()
    target = gc.open_by_key(TARGET_SHEET_ID)
    tabs = ensure_tabs(target)

    count_rows = [["日付", "メール登録件数", "累計メール登録件数"]]
    count_rows.extend(
        [[record.date, f"{record.count:,}", f"{record.cumulative_count:,}"] for record in registration_records]
    )

    uu_rows = [["日付", "メール登録件数（UU）", "累計メール登録件数（UU）"]]
    uu_rows.extend(
        [[record.date, f"{record.count:,}", f"{record.cumulative_count:,}"] for record in uu_records]
    )

    multi_rows = [["顧客ID", "メールアドレス数", "メールアドレス"]]
    multi_rows.extend(
        [[record.customer_id, f"{record.email_count:,}", record.emails] for record in multi_records]
    )

    summary_rows = [
        ["項目", "数値", "定義"],
        ["更新日時", stats["updated_at"], "このシートを作り直した時刻"],
        ["メール登録件数", f"{stats['total_registration_count']:,}", "日別メール登録件数の合計"],
        ["メール登録件数（UU）", f"{stats['total_uu_count']:,}", "日別メール登録件数（UU）の合計"],
        ["メール登録ユーザー数", f"{stats['email_registration_user_count']:,}", "メール登録件数（UU） - 複数アドレスユーザー数"],
        ["集計開始日", stats["registration_start_date"], "最も古い日付"],
        ["最新集計日", stats["latest_date"], "最も新しい日付"],
        ["複数アドレスユーザー数", f"{stats['multi_address_user_count']:,}", "顧客マスタでメールを2件以上持つ顧客数"],
    ]

    source_rows = build_source_management_rows()
    rule_rows = build_rule_rows()

    write_table(tabs[COUNT_TAB_NAME], count_rows)
    write_table(tabs[UU_COUNT_TAB_NAME], uu_rows)
    write_table(tabs[MULTI_TAB_NAME], multi_rows)
    write_table(tabs[SUMMARY_TAB_NAME], summary_rows)
    write_table(tabs[SOURCE_TAB_NAME], source_rows)
    write_table(tabs[RULE_TAB_NAME], rule_rows)
    apply_formatting(target, tabs)
    apply_protections(target, tabs)


def main() -> None:
    parser = argparse.ArgumentParser(description="メール集計の統合シートを再生成する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みせず件数だけ確認する")
    parser.add_argument(
        "--refresh-history-snapshot",
        action="store_true",
        help="旧シートから履歴スナップショットを再作成する",
    )
    parser.add_argument(
        "--force-write-on-anomaly",
        action="store_true",
        help="異常検知があっても強制的に書き込む",
    )
    args = parser.parse_args()

    with FileLock():
        if args.refresh_history_snapshot:
            snapshot = build_history_snapshot_from_legacy()
            save_history_snapshot(snapshot)
            print(
                "履歴スナップショット更新: "
                f"{snapshot['range_start']} - {snapshot['range_end']} / "
                f"登録件数 {snapshot['registration_total']:,} / "
                f"UU {snapshot['uu_total']:,} / "
                f"履歴メール {snapshot['historical_seed_email_count']:,}"
            )
            if args.dry_run:
                return

        registration_records, uu_records, multi_records, stats = collect_data()
        previous_state = load_run_state()
        anomalies = detect_anomalies(stats, previous_state)

        print(
            f"メール登録件数: {stats['total_registration_count']} / "
            f"メール登録件数（UU）: {stats['total_uu_count']} / "
            f"最新日: {stats['latest_date']} / "
            f"3/7以降の登録件数: {stats['future_registration_total']} / "
            f"3/7以降のUU件数: {stats['future_uu_total']} / "
            f"複数アドレスユーザー: {stats['multi_address_user_count']}"
        )

        if anomalies:
            print("異常検知:")
            for message in anomalies:
                print(f"- {message}")
            if not args.force_write_on_anomaly:
                raise SystemExit(2)

        if args.dry_run:
            return

        write_target(registration_records, uu_records, multi_records, stats)
        save_run_state(stats)
        print(
            "書き込み完了: "
            "日別メール登録件数 / 日別メール登録件数（UU） / "
            "複数アドレスユーザー / メール集計サマリー / データソース管理 / データ追加ルール"
        )


if __name__ == "__main__":
    main()
