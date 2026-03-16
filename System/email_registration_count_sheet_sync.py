#!/usr/bin/env python3
"""
メール登録件数の管理シートを再生成する。

対象シート:
- タブ1: 日別メール登録件数
- タブ2: メール登録件数サマリー
- タブ3: データソース管理
- タブ4: データ追加ルール

定義:
- メール登録件数:
  最初の接点における登録という事実を 1件として数える
- 同じメールが同じ日に複数回あれば、その回数分だけ数える
- 日付はソースごとの日付列から日単位で正規化して使う
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
HISTORICAL_COUNT_SHEET_ID = "1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo"
HISTORICAL_COUNT_TAB_NAME = "日別集客数"
UU_EMAIL_SHEET_ID = "1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8"
TARGET_SHEET_ID = "1RsRkGaHCFsFc1nT1lMQFyNG-f13llH4UX9Bl_EYxNjU"

DAILY_TAB_NAME = "日別メール登録件数"
SUMMARY_TAB_NAME = "メール登録件数サマリー"
SOURCE_TAB_NAME = "データソース管理"
RULE_TAB_NAME = "データ追加ルール"

CURRENT_SOURCE_START = "2026/03/07"
FEBRUARY_2025_START = "2025/02/01"
FEBRUARY_2025_END = "2025/02/28"
TODAY_STR = datetime.now().strftime("%Y/%m/%d")

FEBRUARY_2025_CSV_DIR = Path("/Users/koa800/Desktop/2025年2月")
STATE_PATH = Path(__file__).resolve().parent / "data" / "email_registration_count_sheet_state.json"
LOCK_PATH = Path(__file__).resolve().parent / "data" / "email_registration_count_sheet_sync.lock"

MONTH_HEADER_RE = re.compile(r"^(\d{4})年(\d{1,2})月（集客数）$")
DAY_HEADER_RE = re.compile(r"^(\d{1,2})/(\d{1,2})$")
DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "全メール登録件数自動生成"

FEBRUARY_2025_FILE_METRICS = {
    "【Meta広告】数値管理シート - AI.csv": "①オプト獲得数_合計（UTAGE）",
    "【Meta広告】数値管理シート - SNS.csv": "①オプト獲得数合計",
    "【TikTok広告】数値管理シート2025 - AI.csv": "①オプト獲得数UTAGE",
    "【TikTok広告】数値管理シート2025 - SNS.csv": "①オプト獲得数UTAGE",
    "【YouTube広告】数値管理シート2025 - AI（合算）.csv": "①オプト獲得数UTAGE",
    "【YouTube広告】数値管理シート2025 - SNS（合算）.csv": "①オプト獲得数UTAGE",
    "【𝕏広告】数値管理シート - AI（全体）.csv": "①オプト獲得数（UTAGE）",
    "【リスティング広告】数値管理シート2025年 - SNS.csv": "①②リスト獲得数（黄みかみ登録）",
}


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
                        f"全メール登録件数シート更新はロック中です: {lock_data.get('locked_by', '不明')} "
                        f"({int(elapsed)}秒前に開始)"
                    )
            except RuntimeError:
                raise
            except Exception:
                pass

        payload = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"email_registration_count_sheet_sync (PID: {os.getpid()})",
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
class DailyCountRecord:
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


def parse_int(raw: str) -> int:
    value = str(raw or "").strip()
    if not value or value in {"-", "#VALUE!", "#DIV/0!"}:
        return 0
    value = value.replace(",", "").replace("¥", "").replace("%", "")
    match = NUMBER_RE.search(value)
    if not match:
        return 0
    return int(float(match.group(0)))


def normalize_metric_label(raw: str) -> str:
    value = str(raw or "").strip()
    value = value.replace("\n", "").replace("\r", "").replace("\t", "")
    value = value.replace(" ", "").replace("　", "")
    return value


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


def save_run_state(stats: Dict[str, int]) -> None:
    payload = {
        "updated_at": stats["updated_at"],
        "total_registration_count": stats["total_registration_count"],
        "daily_count_days": stats["daily_count_days"],
        "first_registration_date": stats["first_registration_date"],
        "latest_registration_date": stats["latest_registration_date"],
        "current_source_tab_count": stats["current_source_tab_count"],
        "historical_daily_day_count": stats["historical_daily_day_count"],
        "february_csv_file_count": stats["february_csv_file_count"],
        "invalid_rows": stats["invalid_rows"],
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))


def detect_anomalies(stats: Dict[str, int], previous_state: Dict[str, int]) -> List[str]:
    anomalies: List[str] = []

    if stats["current_source_tab_count"] <= 0:
        anomalies.append("集客データ（メールアドレス）の流入経路タブ数が 0 です。")
    if stats["historical_daily_day_count"] <= 0:
        anomalies.append("日別集客数シートから過去件数を取得できていません。")
    if stats["february_csv_file_count"] <= 0:
        anomalies.append("2025年2月CSVを 1件も読み取れていません。")
    if stats["total_registration_count"] <= 0:
        anomalies.append("全メール登録件数が 0 です。元データの読み取りに失敗している可能性があります。")
    if stats["daily_count_days"] <= 0:
        anomalies.append("日別メール登録件数の日数が 0 です。登録日の読み取りに失敗している可能性があります。")
    if stats["first_registration_date"] and stats["first_registration_date"] < "2025/01/01":
        anomalies.append("最初の登録日が 2025/01/01 より前です。旧補完データが混ざっている可能性があります。")

    prev_total = int(previous_state.get("total_registration_count", 0) or 0)
    if prev_total:
        threshold = max(3000, int(prev_total * 0.05))
        if prev_total - stats["total_registration_count"] > threshold:
            anomalies.append(
                f"全メール登録件数が前回より {prev_total - stats['total_registration_count']:,} 件減っています。"
            )

    prev_days = int(previous_state.get("daily_count_days", 0) or 0)
    if prev_days and prev_days - stats["daily_count_days"] > 5:
        anomalies.append(
            f"日別メール登録件数の日数が前回より {prev_days - stats['daily_count_days']:,} 日減っています。"
        )

    return anomalies


def build_source_management_rows() -> List[List[str]]:
    return [
        ["区分", "シート名", "タブ / 場所", "参照先", "役割"],
        [
            "過去件数の正本",
            "【アドネス】顧客管理シート",
            "日別集客数 / 広告セクション",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo/edit","シートを開く")',
            "2025/01/01 - 2026/03/05 の日別件数を補完する",
        ],
        [
            "2025年2月補完",
            "2025年2月CSV",
            str(FEBRUARY_2025_CSV_DIR),
            "",
            "日別集客数シートで欠けている 2025年2月の日別件数を補完する",
        ],
        [
            "現行運用の元データ",
            "集客データ（メールアドレス）",
            "各流入経路タブ",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1l5yD6xUL-1ZC73KrMtCCkDsfhx8D8C4vhylaX3VOoL4/edit","シートを開く")',
            "2026/03/07 以降の登録件数の正本",
        ],
        [
            "参照",
            "集客データ（UUメールアドレス）",
            "UUメールアドレス / 日別UUメールアドレス数",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8/edit","シートを開く")',
            "初回流入ベースの重複なし人数を見る時に参照する",
        ],
        [
            "廃止した補完",
            "過去UTAGE登録者CSV",
            "/Users/koa800/Desktop/過去のCVSデータ/UATGE",
            "",
            "2024/06/11 起点の旧補完は信頼性不足のため使わない",
        ],
        [
            "出力",
            "集客データ（全メール登録数）",
            "日別メール登録件数 / メール登録件数サマリー / データソース管理 / データ追加ルール",
            '=HYPERLINK("https://docs.google.com/spreadsheets/d/1RsRkGaHCFsFc1nT1lMQFyNG-f13llH4UX9Bl_EYxNjU/edit","シートを開く")',
            "登録件数の集計結果を固定する",
        ],
    ]


def build_rule_rows() -> List[List[str]]:
    return [
        ["項目", "ルール", "目的"],
        ["数え方", "1登録を 1件として数える", "メールアドレス数ではなく登録という事実を持つため"],
        ["同一メールの扱い", "同じメールが同じ日に 2回登録されたら 2件として数える", "重複ありの登録件数を保持するため"],
        ["過去件数", "2025/01/01 - 2026/03/05 は 日別集客数シートの 広告 セクションを正とする", "最初の接点の件数だけを安定して持つため"],
        ["2025年2月", "2025年2月だけは月別CSVの指定列で日別件数を補完する", "日別集客数シートの欠損を埋めるため"],
        ["現行運用", "2026/03/07 以降は 集客データ（メールアドレス） の各流入経路タブを正とする", "現在の登録件数を最も信頼できる元データで持つため"],
        ["旧補完", "2024/06/11 起点の旧CSV補完は使わない", "信頼性が怪しい数値を再投入しないため"],
        ["対象", "現行元データでは 登録日時 と メールアドレス の両方が有効な行だけを集計する", "壊れた値を件数に入れないため"],
        ["初回流入との違い", "初回流入の重複なし人数は UUメールアドレス シートで管理し、このシートでは持たない", "指標の役割を混ぜないため"],
        ["自動生成タブ", "このシートの4タブは手編集しない", "再生成で上書きされるため"],
        ["異常検知", "件数急減や参照元異常を検知したら更新を止める", "壊れた値で上書きしないため"],
        ["更新頻度", "Orchestrator が 2時間ごとに再生成する", "手運用に戻らないようにするため"],
    ]


def build_daily_count_records(counter: Counter[str]) -> List[DailyCountRecord]:
    cumulative = 0
    daily_records = []
    for date_str in sorted(counter):
        cumulative += counter[date_str]
        daily_records.append(
            DailyCountRecord(
                date=date_str,
                count=counter[date_str],
                cumulative_count=cumulative,
            )
        )
    return daily_records


def collect_current_sheet_counts(gc) -> Tuple[Counter[str], Dict[str, int]]:
    raw_spreadsheet = gc.open_by_key(RAW_SOURCE_SHEET_ID)

    daily_counter: Counter[str] = Counter()
    tab_count = 0
    rows_scanned = 0
    valid_rows = 0
    invalid_rows = 0

    for ws in raw_spreadsheet.worksheets():
        tab_count += 1
        values = get_all_values_with_retry(ws)
        if not values:
            continue

        for row in values[1:]:
            if len(row) <= 1:
                continue
            rows_scanned += 1
            registered_at = normalize_date(row[0])
            email = normalize_email(row[1])
            if not registered_at or not email:
                invalid_rows += 1
                continue
            valid_rows += 1
            if registered_at >= CURRENT_SOURCE_START:
                daily_counter[registered_at] += 1

    stats = {
        "tab_count": tab_count,
        "rows_scanned": rows_scanned,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "day_count": len(daily_counter),
    }
    return daily_counter, stats


def collect_historical_sheet_counts(gc) -> Tuple[Counter[str], Dict[str, int]]:
    ws = gc.open_by_key(HISTORICAL_COUNT_SHEET_ID).worksheet(HISTORICAL_COUNT_TAB_NAME)
    values = get_all_values_with_retry(ws)

    daily_counter: Counter[str] = Counter()
    current_year = 0
    current_month = 0
    current_date_columns: Dict[int, str] = {}
    current_category = ""
    rows_scanned = 0
    value_cell_count = 0

    for row in values:
        label = row[0].strip() if row else ""
        month_match = MONTH_HEADER_RE.match(label)
        if month_match:
            current_year = int(month_match.group(1))
            current_month = int(month_match.group(2))
            current_category = ""
            current_date_columns = {}
            for idx, cell in enumerate(row):
                day_match = DAY_HEADER_RE.match(str(cell or "").strip())
                if not day_match:
                    continue
                header_month = int(day_match.group(1))
                header_day = int(day_match.group(2))
                if header_month != current_month:
                    continue
                current_date_columns[idx] = f"{current_year:04d}/{current_month:02d}/{header_day:02d}"
            continue

        if not current_date_columns:
            continue
        if label == "大カテゴリ":
            current_category = ""
            continue
        if label:
            current_category = label
        if current_category != "広告":
            continue

        rows_scanned += 1
        for col_idx, date_str in current_date_columns.items():
            if col_idx >= len(row):
                continue
            if date_str > TODAY_STR:
                continue
            cell_value = str(row[col_idx] or "").strip()
            if not cell_value:
                continue
            count = parse_int(cell_value)
            if count:
                value_cell_count += 1
            daily_counter[date_str] += count

    stats = {
        "rows_scanned": rows_scanned,
        "value_cell_count": value_cell_count,
        "day_count": len(daily_counter),
    }
    return daily_counter, stats


def find_metric_index(header_row: List[str], expected_metric: str) -> int:
    expected = normalize_metric_label(expected_metric)
    for idx, cell in enumerate(header_row):
        if expected and expected in normalize_metric_label(cell):
            return idx
    return -1


def collect_february_2025_csv_counts() -> Tuple[Counter[str], Dict[str, int]]:
    daily_counter: Counter[str] = Counter()
    file_count = 0
    rows_scanned = 0
    valid_rows = 0
    invalid_rows = 0

    for filename, expected_metric in FEBRUARY_2025_FILE_METRICS.items():
        path = FEBRUARY_2025_CSV_DIR / filename
        if not path.exists():
            raise FileNotFoundError(f"2025年2月補完CSVが見つかりません: {path}")

        file_count += 1
        with path.open("r", encoding="utf-8-sig", newline="") as fh:
            rows = list(csv.reader(fh))

        metric_idx = -1
        for row in rows[:10]:
            metric_idx = find_metric_index(row, expected_metric)
            if metric_idx >= 0:
                break
        if metric_idx < 0:
            raise RuntimeError(f"{filename} で対象列 {expected_metric} を見つけられませんでした。")

        for row in rows:
            if not row:
                continue
            date_str = normalize_date(row[0])
            if not date_str:
                continue
            if not (FEBRUARY_2025_START <= date_str <= FEBRUARY_2025_END):
                continue

            rows_scanned += 1
            if metric_idx >= len(row):
                invalid_rows += 1
                continue

            daily_counter[date_str] += parse_int(row[metric_idx])
            valid_rows += 1

    stats = {
        "file_count": file_count,
        "rows_scanned": rows_scanned,
        "valid_rows": valid_rows,
        "invalid_rows": invalid_rows,
        "day_count": len(daily_counter),
    }
    return daily_counter, stats


def merge_counters(
    historical_counter: Counter[str],
    february_counter: Counter[str],
    current_counter: Counter[str],
) -> Counter[str]:
    merged: Dict[str, int] = {date_str: count for date_str, count in historical_counter.items()}
    for date_str, count in february_counter.items():
        merged[date_str] = count
    for date_str, count in current_counter.items():
        merged[date_str] = count
    return Counter(merged)


def collect_data() -> Tuple[List[DailyCountRecord], Dict[str, int]]:
    gc = get_client()

    historical_counter, historical_stats = collect_historical_sheet_counts(gc)
    february_counter, february_stats = collect_february_2025_csv_counts()
    current_counter, current_stats = collect_current_sheet_counts(gc)

    daily_counter = merge_counters(historical_counter, february_counter, current_counter)
    daily_records = build_daily_count_records(daily_counter)
    first_date = daily_records[0].date if daily_records else ""
    latest_date = daily_records[-1].date if daily_records else ""

    stats = {
        "updated_at": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "current_source_tab_count": current_stats["tab_count"],
        "rows_scanned": current_stats["rows_scanned"] + february_stats["rows_scanned"] + historical_stats["rows_scanned"],
        "valid_rows": current_stats["valid_rows"] + february_stats["valid_rows"],
        "invalid_rows": current_stats["invalid_rows"] + february_stats["invalid_rows"],
        "historical_daily_day_count": historical_stats["day_count"],
        "historical_value_cell_count": historical_stats["value_cell_count"],
        "february_csv_file_count": february_stats["file_count"],
        "february_daily_day_count": february_stats["day_count"],
        "february_valid_rows": february_stats["valid_rows"],
        "current_daily_day_count": current_stats["day_count"],
        "current_valid_rows": current_stats["valid_rows"],
        "total_registration_count": sum(record.count for record in daily_records),
        "daily_count_days": len(daily_records),
        "first_registration_date": first_date,
        "latest_registration_date": latest_date,
    }
    return daily_records, stats


def ensure_tabs(spreadsheet):
    tabs = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered_names = [
        DAILY_TAB_NAME,
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
        DAILY_TAB_NAME: {
            "col_widths": [140, 180, 200],
            "numeric_cols": [1, 2],
            "tab_color": {"red": 0.357, "green": 0.584, "blue": 0.976},
        },
        SUMMARY_TAB_NAME: {
            "col_widths": [240, 180, 520],
            "numeric_cols": [1],
            "tab_color": {"red": 0.973, "green": 0.776, "blue": 0.396},
        },
        SOURCE_TAB_NAME: {
            "col_widths": [110, 240, 300, 130, 340],
            "numeric_cols": [],
            "tab_color": {"red": 0.984, "green": 0.757, "blue": 0.18},
        },
        RULE_TAB_NAME: {
            "col_widths": [140, 420, 320],
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
    protected_names = [DAILY_TAB_NAME, SUMMARY_TAB_NAME, SOURCE_TAB_NAME, RULE_TAB_NAME]
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
    daily_records: Iterable[DailyCountRecord],
    stats: Dict[str, int],
) -> None:
    gc = get_client()
    target = gc.open_by_key(TARGET_SHEET_ID)
    tabs = ensure_tabs(target)

    daily_rows = [["日付", "メール登録件数", "累計メール登録件数"]]
    daily_rows.extend(
        [[record.date, f"{record.count:,}", f"{record.cumulative_count:,}"] for record in daily_records]
    )

    summary_rows = [
        ["項目", "数値", "定義"],
        ["更新日時", stats["updated_at"], "この集計を作り直した時刻"],
        ["全メール登録件数", f"{stats['total_registration_count']:,}", "最初の接点における登録件数の合計"],
        ["日別集計日数", f"{stats['daily_count_days']:,}", "メール登録件数を持てている日数"],
        ["最初の登録日", stats["first_registration_date"], "集計できた中で最も古い登録日"],
        ["最新の登録日", stats["latest_registration_date"], "集計できた中で最も新しい登録日"],
        ["現行参照元タブ数", f"{stats['current_source_tab_count']:,}", "集客データ（メールアドレス）の流入経路タブ数"],
        ["過去件数ソース日数", f"{stats['historical_daily_day_count']:,}", "日別集客数シートから取得できた日数"],
        ["2025年2月補完ファイル数", f"{stats['february_csv_file_count']:,}", "2025年2月補完に使ったCSVファイル数"],
        ["集計対象外行数", f"{stats['invalid_rows']:,}", "現行元データと2025年2月CSVで壊れていて数えていない行数"],
    ]

    source_rows = build_source_management_rows()
    rule_rows = build_rule_rows()

    write_table(tabs[DAILY_TAB_NAME], daily_rows)
    write_table(tabs[SUMMARY_TAB_NAME], summary_rows)
    write_table(tabs[SOURCE_TAB_NAME], source_rows)
    write_table(tabs[RULE_TAB_NAME], rule_rows)
    apply_formatting(target, tabs)
    apply_protections(target, tabs)


def main() -> None:
    parser = argparse.ArgumentParser(description="全メール登録件数シートを再生成する")
    parser.add_argument("--dry-run", action="store_true", help="書き込みせず件数だけ確認する")
    parser.add_argument(
        "--force-write-on-anomaly",
        action="store_true",
        help="異常検知があっても強制的に書き込む",
    )
    args = parser.parse_args()

    with FileLock():
        daily_records, stats = collect_data()
        previous_state = load_run_state()
        anomalies = detect_anomalies(stats, previous_state)

        print(
            f"全メール登録件数: {stats['total_registration_count']} / "
            f"日別日数: {stats['daily_count_days']} / "
            f"最初の登録日: {stats['first_registration_date']} / "
            f"最新の登録日: {stats['latest_registration_date']} / "
            f"現行参照元タブ数: {stats['current_source_tab_count']} / "
            f"過去件数ソース日数: {stats['historical_daily_day_count']} / "
            f"2025年2月補完ファイル数: {stats['february_csv_file_count']} / "
            f"集計対象外行数: {stats['invalid_rows']}"
        )

        if anomalies:
            print("異常検知:")
            for message in anomalies:
                print(f"- {message}")
            if not args.force_write_on_anomaly:
                raise SystemExit(2)

        if args.dry_run:
            return

        write_target(daily_records, stats)
        save_run_state(stats)
        print(
            "書き込み完了: "
            "日別メール登録件数 / メール登録件数サマリー / "
            "データソース管理 / データ追加ルール"
        )


if __name__ == "__main__":
    main()
