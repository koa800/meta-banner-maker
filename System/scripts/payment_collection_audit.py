#!/usr/bin/env python3
"""
決済データ（収集）の運用監査タブを更新する。

方針:
- 人が見る場所は `運用監査` 1枚に絞る
- 日次同期のたびに、最新日付の到着確認と月次照合を再生成する
- 月次照合は「日別フォルダに入ったCSVが収集シートへ正しく反映されたか」を検証する
"""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from gspread.exceptions import APIError

BASE_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE_DIR))

from sheets_manager import get_client
from scripts import payment_csv_to_sheet as payment_import


SHEET_ID = payment_import.SHEET_ID
STATE_PATH = BASE_DIR / "data" / "payment_daily_sync_state.json"

OPS_TAB_NAME = "運用監査"
FILE_LOG_TAB_NAME = "取込ファイルログ"
ANOMALY_LOG_TAB_NAME = "異常ファイルログ"
MONTHLY_TAB_NAME = "月次照合"

AUDIT_TAB_SPECS = {
    OPS_TAB_NAME: (240, 12),
}
OBSOLETE_AUDIT_TABS = (
    FILE_LOG_TAB_NAME,
    ANOMALY_LOG_TAB_NAME,
    MONTHLY_TAB_NAME,
)

WRITE_RETRY_SECONDS = (5, 10, 20, 40)
FOLDER_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")
DAILY_ARRIVAL_RULES = [
    {"source": "UnivaPay", "expectation": "必須"},
    {"source": "日本プラム", "expectation": "必須"},
    {"source": "MOSH", "expectation": "必須"},
    {"source": "きらぼし銀行", "expectation": "必須"},
    {"source": "INVOY", "expectation": "必須"},
    {"source": "UTAGE売上一覧", "expectation": "必須"},
    {"source": "CREDIX", "expectation": "任意"},
]
ARRIVAL_STATUS_RANK = {
    "未検出": 0,
    "要確認": 1,
    "重複確認": 2,
    "0件正常": 3,
    "確認済み": 4,
}


def load_state() -> dict[str, Any]:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def run_with_retry(description: str, func):
    last_error = None
    waits = (0, *WRITE_RETRY_SECONDS)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except APIError as exc:
            error_text = str(exc)
            retryable = any(token in error_text for token in ("429", "Quota", "503", "Service is currently unavailable"))
            if not retryable or attempt == len(waits):
                raise
            last_error = exc
            print(f"{description}: Sheets API の一時エラーのため再試行します。")
    if last_error:
        raise last_error


def ensure_audit_tabs(spreadsheet):
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    for title, (rows, cols) in AUDIT_TAB_SPECS.items():
        ws = worksheets.get(title)
        if ws is None:
            ws = run_with_retry(
                f"{title} タブ作成",
                lambda title=title, rows=rows, cols=cols: spreadsheet.add_worksheet(title=title, rows=rows, cols=cols),
            )
            worksheets[title] = ws
        elif ws.row_count < rows or ws.col_count < cols:
            run_with_retry(
                f"{title} タブサイズ調整",
                lambda ws=ws, rows=max(ws.row_count, rows), cols=max(ws.col_count, cols): ws.resize(rows=rows, cols=cols),
            )

    for title in OBSOLETE_AUDIT_TABS:
        ws = worksheets.get(title)
        if ws is None:
            continue
        run_with_retry(f"{title} タブ削除", lambda ws=ws: spreadsheet.del_worksheet(ws))

    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    ordered_existing = [ws.title for ws in spreadsheet.worksheets()]
    requests = []
    base_titles = [
        payment_import.TAB_NAME,
        payment_import.UTAGE_TAB_NAME,
        payment_import.SOURCE_MGMT_TAB,
        "データ追加ルール",
    ]
    ordered_titles = [title for title in base_titles if title in worksheets]
    for title in AUDIT_TAB_SPECS:
        if title in worksheets:
            ordered_titles.append(title)
    for title in ordered_existing:
        if title not in ordered_titles and title in worksheets:
            ordered_titles.append(title)

    for idx, title in enumerate(ordered_titles):
        ws = worksheets[title]
        requests.append({
            "updateSheetProperties": {
                "properties": {"sheetId": ws.id, "index": idx, "hidden": False},
                "fields": "index,hidden",
            }
        })

    if requests:
        run_with_retry("監査タブ整列", lambda: spreadsheet.batch_update({"requests": requests}))

    return {ws.title: ws for ws in spreadsheet.worksheets()}


def write_rows(ws, rows: list[list[Any]]) -> None:
    target_rows = max(len(rows) + 20, ws.row_count)
    target_cols = max(max((len(row) for row in rows), default=1), ws.col_count)
    if target_rows != ws.row_count or target_cols != ws.col_count:
        run_with_retry(f"{ws.title} サイズ調整", lambda: ws.resize(rows=target_rows, cols=target_cols))
    run_with_retry(f"{ws.title} クリア", lambda: ws.clear())
    run_with_retry(
        f"{ws.title} 更新",
        lambda: ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED"),
    )


def parse_iso(raw: str) -> datetime | None:
    value = str(raw or "").strip()
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_dt(dt: datetime | None) -> str:
    if dt is None:
        return ""
    return dt.strftime("%Y/%m/%d %H:%M")


def extract_folder_month(folder_name: str) -> str:
    match = FOLDER_DATE_RE.search(str(folder_name or ""))
    if not match:
        return ""
    year, month, _ = match.groups()
    return f"{year}/{int(month):02d}"


def extract_folder_date_key(folder_name: str) -> str:
    match = FOLDER_DATE_RE.search(str(folder_name or ""))
    if not match:
        return ""
    year, month, day = match.groups()
    return f"{year}/{int(month):02d}/{int(day):02d}"


def detect_source_display(meta: dict[str, Any]) -> str:
    source = str(meta.get("source") or "").strip()
    if not source:
        source = payment_import.detect_source(str(meta.get("file_name") or "")) or ""
    return payment_import.SOURCE_DISPLAY_NAMES.get(source, source)


def numeric(value: Any) -> int:
    try:
        return int(str(value or "0").strip())
    except ValueError:
        return 0


def update_arrival_status(
    coverage: dict[tuple[str, str], dict[str, Any]],
    *,
    date_key: str,
    source_name: str,
    status: str,
    file_name: str = "",
    note: str = "",
    seen_at: str = "",
) -> None:
    if not date_key or not source_name:
        return
    key = (date_key, source_name)
    entry = coverage.setdefault(key, {"status": "未検出", "files": set(), "notes": set(), "seen_at": ""})
    if ARRIVAL_STATUS_RANK.get(status, 0) > ARRIVAL_STATUS_RANK.get(str(entry.get("status") or "未検出"), 0):
        entry["status"] = status
    if file_name:
        entry["files"].add(file_name)
    if note:
        entry["notes"].add(note)
    if seen_at and seen_at > str(entry.get("seen_at") or ""):
        entry["seen_at"] = seen_at


def load_recent_scanned_folders(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    snapshots: dict[str, dict[str, Any]] = {}
    for item in state.get("recent_scanned_folders", []):
        folder_name = str(item.get("folder_name") or "")
        date_key = str(item.get("folder_date_key") or "") or extract_folder_date_key(folder_name)
        if not date_key:
            continue
        current = snapshots.get(date_key)
        captured_at = str(item.get("captured_at") or "")
        if current and captured_at <= str(current.get("captured_at") or ""):
            continue
        snapshots[date_key] = {
            "folder_name": folder_name,
            "captured_at": captured_at,
            "file_count": numeric(item.get("file_count")),
            "csv_like_count": numeric(item.get("csv_like_count")),
            "supported_count": numeric(item.get("supported_count")),
            "ignored_count": numeric(item.get("ignored_count")),
            "unknown_count": numeric(item.get("unknown_count")),
            "duplicate_count": numeric(item.get("duplicate_count")),
        }
    return snapshots


def build_folder_summary(snapshot: dict[str, Any] | None) -> str:
    if not snapshot:
        return "処理履歴から再構成"

    parts = [
        f"ファイル{numeric(snapshot.get('file_count'))}",
        f"CSV{numeric(snapshot.get('csv_like_count'))}",
        f"対象{numeric(snapshot.get('supported_count'))}",
    ]
    if numeric(snapshot.get("duplicate_count")):
        parts.append(f"重複{numeric(snapshot.get('duplicate_count'))}")
    if numeric(snapshot.get("unknown_count")):
        parts.append(f"未知{numeric(snapshot.get('unknown_count'))}")
    if numeric(snapshot.get("ignored_count")):
        parts.append(f"対象外{numeric(snapshot.get('ignored_count'))}")
    return " / ".join(parts)


def build_daily_arrival_rows(state: dict[str, Any]) -> tuple[list[list[Any]], int, str]:
    coverage: dict[tuple[str, str], dict[str, Any]] = {}
    folder_snapshots = load_recent_scanned_folders(state)
    date_keys: set[str] = set(folder_snapshots.keys())

    for meta in state.get("processed_files", {}).values():
        date_key = extract_folder_date_key(str(meta.get("folder_name") or ""))
        source_name = detect_source_display(meta)
        if not date_key or not source_name:
            continue
        date_keys.add(date_key)
        warning_text = " / ".join(meta.get("warnings") or [])
        if "ヘッダーのみでデータ行がありません" in warning_text:
            status = "0件正常"
        else:
            status = "確認済み"
        update_arrival_status(
            coverage,
            date_key=date_key,
            source_name=source_name,
            status=status,
            file_name=str(meta.get("file_name") or ""),
            note=warning_text,
            seen_at=str(meta.get("processed_at") or ""),
        )

    for meta in state.get("duplicate_files", {}).values():
        date_key = extract_folder_date_key(str(meta.get("folder_name") or ""))
        source_name = detect_source_display(meta)
        if not date_key or not source_name:
            continue
        date_keys.add(date_key)
        update_arrival_status(
            coverage,
            date_key=date_key,
            source_name=source_name,
            status="重複確認",
            file_name=str(meta.get("file_name") or ""),
            note=str(meta.get("duplicate_reason") or ""),
            seen_at=str(meta.get("detected_at") or ""),
        )

    for meta in state.get("anomaly_files", {}).values():
        source_name = detect_source_display(meta)
        date_key = extract_folder_date_key(str(meta.get("folder_name") or ""))
        if not date_key or not source_name:
            continue
        date_keys.add(date_key)
        category = str(meta.get("category") or "")
        if category == "ignored":
            continue
        update_arrival_status(
            coverage,
            date_key=date_key,
            source_name=source_name,
            status="要確認",
            file_name=str(meta.get("file_name") or ""),
            note=str(meta.get("reason") or ""),
            seen_at=str(meta.get("last_seen_at") or ""),
        )

    latest_dates = sorted(date_keys, reverse=True)[:3]
    rows = [["対象日", "フォルダ確認", "期待", "ソース", "到着状況", "確認ファイル", "補足"]]
    latest_missing_required = 0
    latest_date_key = latest_dates[0] if latest_dates else ""

    for date_key in latest_dates:
        folder_summary = build_folder_summary(folder_snapshots.get(date_key))
        for rule in DAILY_ARRIVAL_RULES:
            source_name = rule["source"]
            entry = coverage.get((date_key, source_name), {"status": "未検出", "files": set(), "notes": set()})
            status = str(entry.get("status") or "未検出")
            if date_key == latest_date_key and rule["expectation"] == "必須" and status == "未検出":
                latest_missing_required += 1
            rows.append([
                date_key,
                folder_summary,
                rule["expectation"],
                source_name,
                status,
                " / ".join(sorted(entry.get("files") or []))[:300],
                " / ".join(sorted(entry.get("notes") or []))[:300],
            ])
        rows.append([])

    if rows and rows[-1] == []:
        rows.pop()
    return rows, latest_missing_required, latest_date_key


def build_monthly_rows(state: dict[str, Any]) -> list[list[Any]]:
    current_month = datetime.now().strftime("%Y/%m")
    monthly: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {
        "processed_files": 0,
        "zero_data_files": 0,
        "raw_rows": 0,
        "converted_rows": 0,
        "written_rows": 0,
        "duplicate_rows": 0,
        "issue_files": 0,
        "last_sync": "",
    })

    for meta in state.get("processed_files", {}).values():
        month_key = extract_folder_month(str(meta.get("folder_name") or ""))
        if not month_key:
            processed_at = parse_iso(str(meta.get("processed_at") or ""))
            month_key = processed_at.strftime("%Y/%m") if processed_at else ""
        source_name = detect_source_display(meta)
        if not month_key or not source_name:
            continue
        key = (month_key, source_name)
        agg = monthly[key]
        agg["processed_files"] += 1
        agg["raw_rows"] += numeric(meta.get("raw_row_count"))
        agg["converted_rows"] += numeric(meta.get("converted_row_count"))
        written_rows = numeric(meta.get("written_payment_rows")) + numeric(meta.get("written_utage_rows"))
        duplicate_rows = numeric(meta.get("skipped_payment_duplicates")) + numeric(meta.get("skipped_utage_duplicates"))
        agg["written_rows"] += written_rows
        agg["duplicate_rows"] += duplicate_rows
        warning_text = " / ".join(meta.get("warnings") or [])
        if "ヘッダーのみでデータ行がありません" in warning_text:
            agg["zero_data_files"] += 1
        processed_at = str(meta.get("processed_at") or "")
        if processed_at > agg["last_sync"]:
            agg["last_sync"] = processed_at

    for meta in state.get("anomaly_files", {}).values():
        category = str(meta.get("category") or "")
        if category == "ignored":
            continue
        month_key = extract_folder_month(str(meta.get("folder_name") or ""))
        if not month_key:
            last_seen = parse_iso(str(meta.get("last_seen_at") or ""))
            month_key = last_seen.strftime("%Y/%m") if last_seen else ""
        source_name = detect_source_display(meta)
        if not month_key or not source_name:
            continue
        monthly[(month_key, source_name)]["issue_files"] += 1

    rows = [[
        "対象月",
        "ソース",
        "正常ファイル数",
        "0件CSV数",
        "raw行数",
        "converted行数",
        "追加行数",
        "duplicate除外行数",
        "未解決異常件数",
        "balance",
        "ステータス",
    ]]

    for (month_key, source_name), agg in sorted(monthly.items(), key=lambda item: item[0], reverse=True):
        balance = agg["converted_rows"] - agg["written_rows"] - agg["duplicate_rows"]
        if agg["issue_files"] > 0 or balance != 0:
            status = "要確認"
        elif month_key == current_month:
            status = "速報"
        else:
            status = "照合済"
        rows.append([
            month_key,
            source_name,
            agg["processed_files"],
            agg["zero_data_files"],
            agg["raw_rows"],
            agg["converted_rows"],
            agg["written_rows"],
            agg["duplicate_rows"],
            agg["issue_files"],
            balance,
            status,
        ])
    return rows


def build_ops_rows(state: dict[str, Any], spreadsheet) -> list[list[Any]]:
    metadata = spreadsheet.fetch_sheet_metadata()
    total_cells = 0
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        grid = props.get("gridProperties", {})
        total_cells += int(grid.get("rowCount", 0)) * int(grid.get("columnCount", 0))
    remaining_cells = 10_000_000 - total_cells

    now = datetime.now()
    recent_cutoff = now - timedelta(days=7)
    processed_files = state.get("processed_files", {})
    recent_processed = []
    zero_data_count = 0
    recent_written_rows = 0
    per_source: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "files": 0,
        "written_rows": 0,
        "zero_data_files": 0,
        "issues": 0,
        "last_success": "",
    })

    for meta in processed_files.values():
        processed_at = parse_iso(str(meta.get("processed_at") or ""))
        if processed_at is None:
            continue
        source_name = detect_source_display(meta)
        written_rows = numeric(meta.get("written_payment_rows")) + numeric(meta.get("written_utage_rows"))
        warning_text = " / ".join(meta.get("warnings") or [])
        if processed_at >= recent_cutoff:
            recent_processed.append(meta)
            recent_written_rows += written_rows
            if "ヘッダーのみでデータ行がありません" in warning_text:
                zero_data_count += 1
        bucket = per_source[source_name]
        if processed_at >= recent_cutoff:
            bucket["files"] += 1
            bucket["written_rows"] += written_rows
            if "ヘッダーのみでデータ行がありません" in warning_text:
                bucket["zero_data_files"] += 1
        if str(meta.get("processed_at") or "") > bucket["last_success"]:
            bucket["last_success"] = str(meta.get("processed_at") or "")

    unresolved_anomalies = [meta for meta in state.get("anomaly_files", {}).values() if str(meta.get("category") or "") != "ignored"]
    unresolved_known_ignored = [meta for meta in state.get("anomaly_files", {}).values() if str(meta.get("category") or "") == "ignored"]
    for meta in unresolved_anomalies:
        source_name = detect_source_display(meta)
        if source_name:
            per_source[source_name]["issues"] += 1

    folder_snapshots = load_recent_scanned_folders(state)
    daily_arrival_rows, latest_missing_required, latest_date_key = build_daily_arrival_rows(state)
    latest_folder_summary = build_folder_summary(folder_snapshots.get(latest_date_key))
    monthly_rows = build_monthly_rows(state)

    summary_rows = [
        ["項目", "値", "補足", "", "ソース", "直近7日ファイル数", "直近7日追加行数", "0件CSV数", "未解決異常", "最終成功"],
        ["最終実行", format_dt(parse_iso(str(state.get("last_run") or ""))), "payment_daily_sync の完了時刻", "", "", "", "", "", "", ""],
        ["最新確認フォルダ", latest_date_key, latest_folder_summary, "", "", "", "", "", "", ""],
        ["直近7日処理ファイル数", len(recent_processed), "0件CSVを含む", "", "", "", "", "", "", ""],
        ["直近7日0件CSV数", zero_data_count, "ヘッダーのみCSVを正常処理した件数", "", "", "", "", "", "", ""],
        ["直近7日追加行数", recent_written_rows, "決済データ + UTAGE補助", "", "", "", "", "", "", ""],
        ["未解決異常件数", len(unresolved_anomalies), "ignored を除く", "", "", "", "", "", "", ""],
        ["既知の対象外件数", len(unresolved_known_ignored), "known ignored の current 件数", "", "", "", "", "", "", ""],
        ["最新日付の必須ソース未到着", latest_missing_required, "最新フォルダ日付で必須ソースが未検出の件数", "", "", "", "", "", "", ""],
        ["総セル数", total_cells, "Google Sheets 上限 10,000,000", "", "", "", "", "", "", ""],
        ["残セル数", remaining_cells, "容量監視の目安", "", "", "", "", "", "", ""],
    ]

    source_order = list(payment_import.SOURCE_DISPLAY_NAMES.values())
    for idx, source_name in enumerate(source_order, start=1):
        bucket = per_source.get(source_name, {})
        row_index = idx
        if row_index >= len(summary_rows):
            summary_rows.append([""] * 10)
        summary_rows[row_index][4] = source_name
        summary_rows[row_index][5] = bucket.get("files", 0)
        summary_rows[row_index][6] = bucket.get("written_rows", 0)
        summary_rows[row_index][7] = bucket.get("zero_data_files", 0)
        summary_rows[row_index][8] = bucket.get("issues", 0)
        summary_rows[row_index][9] = format_dt(parse_iso(str(bucket.get("last_success") or "")))

    summary_rows.append([])
    summary_rows.append(["未解決異常", "判定", "ソース", "フォルダ", "ファイル名", "理由"])
    for meta in sorted(unresolved_anomalies, key=lambda item: str(item.get("last_seen_at") or ""), reverse=True)[:10]:
        summary_rows.append([
            format_dt(parse_iso(str(meta.get("last_seen_at") or ""))),
            str(meta.get("category") or ""),
            detect_source_display(meta),
            str(meta.get("folder_name") or ""),
            str(meta.get("file_name") or ""),
            str(meta.get("reason") or ""),
        ])

    summary_rows.append([])
    summary_rows.append(["日次到着確認", "", "", "", "", ""])
    summary_rows.extend(daily_arrival_rows)
    summary_rows.append([])
    summary_rows.append(["月次照合", "", "", "", "", "", "", "", "", "", ""])
    summary_rows.append(["ステータス定義", "速報=当月 / 照合済=差分なし / 要確認=差分あり or 未解決異常あり", "", "", "", "", "", "", "", "", ""])
    summary_rows.extend(monthly_rows)

    return summary_rows


def sync_payment_collection_audit(spreadsheet=None, state: dict[str, Any] | None = None) -> None:
    if state is None:
        state = load_state()
    if spreadsheet is None:
        gc = get_client("kohara")
        spreadsheet = gc.open_by_key(SHEET_ID)

    structure_errors = payment_import.validate_collection_sheet_headers(spreadsheet)
    if structure_errors:
        raise RuntimeError(" / ".join(structure_errors))

    tabs = ensure_audit_tabs(spreadsheet)
    write_rows(tabs[OPS_TAB_NAME], build_ops_rows(state, spreadsheet))


def main():
    parser = argparse.ArgumentParser(description="決済収集の運用監査タブを再生成する")
    parser.parse_args()
    sync_payment_collection_audit()
    print("決済収集の監査タブを更新しました。")


if __name__ == "__main__":
    main()
