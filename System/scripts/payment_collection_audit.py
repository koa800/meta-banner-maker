#!/usr/bin/env python3
"""
決済データ（収集）の運用監査タブを更新する。

方針:
- 収集運用の可視化をスプレッドシート内で完結させる
- 日次同期のたびに、週次監査と月次照合に必要な集計を再生成する
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
    OPS_TAB_NAME: (120, 10),
    FILE_LOG_TAB_NAME: (5000, 13),
    ANOMALY_LOG_TAB_NAME: (3000, 10),
    MONTHLY_TAB_NAME: (500, 11),
}

WRITE_RETRY_SECONDS = (5, 10, 20, 40)
FOLDER_DATE_RE = re.compile(r"(\d{4})/(\d{1,2})/(\d{1,2})")


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
    ordered_existing = [ws.title for ws in spreadsheet.worksheets()]
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


def build_file_log_rows(state: dict[str, Any]) -> list[list[Any]]:
    rows = [[
        "処理時刻",
        "状態",
        "ソース",
        "フォルダ",
        "ファイル名",
        "raw行数",
        "converted行数",
        "追加行数",
        "duplicate除外行数",
        "warning",
        "file_id",
        "file_fingerprint",
        "月次照合キー",
    ]]

    processed_items = sorted(
        state.get("processed_files", {}).items(),
        key=lambda kv: kv[1].get("processed_at", ""),
        reverse=True,
    )
    for file_id, meta in processed_items:
        warnings = meta.get("warnings") or []
        warning_text = " / ".join(warnings)
        written_rows = numeric(meta.get("written_payment_rows")) + numeric(meta.get("written_utage_rows"))
        duplicate_rows = numeric(meta.get("skipped_payment_duplicates")) + numeric(meta.get("skipped_utage_duplicates"))
        if "ヘッダーのみでデータ行がありません" in warning_text:
            status = "0件正常"
        elif written_rows == 0 and duplicate_rows > 0:
            status = "重複のみ"
        else:
            status = "正常"
        month_key = extract_folder_month(str(meta.get("folder_name") or ""))
        rows.append([
            format_dt(parse_iso(str(meta.get("processed_at") or ""))),
            status,
            detect_source_display(meta),
            str(meta.get("folder_name") or ""),
            str(meta.get("file_name") or ""),
            numeric(meta.get("raw_row_count")),
            numeric(meta.get("converted_row_count")),
            written_rows,
            duplicate_rows,
            warning_text,
            file_id,
            str(meta.get("file_fingerprint") or ""),
            month_key,
        ])
    return rows


def build_anomaly_rows(state: dict[str, Any]) -> list[list[Any]]:
    rows = [[
        "記録時刻",
        "イベント",
        "判定",
        "ソース",
        "フォルダ",
        "ファイル名",
        "理由",
        "通知時刻",
        "file_id",
        "file_fingerprint",
    ]]

    history = list(state.get("anomaly_history") or [])
    if not history:
        for file_id, meta in state.get("anomaly_files", {}).items():
            history.append({
                "recorded_at": meta.get("first_detected_at") or meta.get("last_seen_at") or "",
                "event_type": "detected",
                "category": meta.get("category") or "",
                "source": meta.get("source") or "",
                "folder_name": meta.get("folder_name") or "",
                "file_name": meta.get("file_name") or "",
                "reason": meta.get("reason") or "",
                "notified_at": meta.get("notified_at") or "",
                "file_id": file_id,
                "file_fingerprint": meta.get("file_fingerprint") or "",
            })

    history.sort(key=lambda item: str(item.get("recorded_at") or ""), reverse=True)
    for item in history:
        rows.append([
            format_dt(parse_iso(str(item.get("recorded_at") or ""))),
            "検出" if str(item.get("event_type") or "") == "detected" else "解消",
            str(item.get("category") or ""),
            payment_import.SOURCE_DISPLAY_NAMES.get(str(item.get("source") or ""), str(item.get("source") or "")),
            str(item.get("folder_name") or ""),
            str(item.get("file_name") or ""),
            str(item.get("reason") or ""),
            format_dt(parse_iso(str(item.get("notified_at") or ""))),
            str(item.get("file_id") or ""),
            str(item.get("file_fingerprint") or ""),
        ])
    return rows


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

    summary_rows = [
        ["項目", "値", "補足", "", "ソース", "直近7日ファイル数", "直近7日追加行数", "0件CSV数", "未解決異常", "最終成功"],
        ["最終実行", format_dt(parse_iso(str(state.get("last_run") or ""))), "payment_daily_sync の完了時刻", "", "", "", "", "", "", ""],
        ["処理済みファイル総数", len(processed_files), "state に残っている正常処理ファイル数", "", "", "", "", "", "", ""],
        ["直近7日処理ファイル数", len(recent_processed), "0件CSVを含む", "", "", "", "", "", "", ""],
        ["直近7日0件CSV数", zero_data_count, "ヘッダーのみCSVを正常処理した件数", "", "", "", "", "", "", ""],
        ["直近7日追加行数", recent_written_rows, "決済データ + UTAGE補助", "", "", "", "", "", "", ""],
        ["未解決異常件数", len(unresolved_anomalies), "ignored を除く", "", "", "", "", "", "", ""],
        ["既知の対象外件数", len(unresolved_known_ignored), "known ignored の current 件数", "", "", "", "", "", "", ""],
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
    write_rows(tabs[FILE_LOG_TAB_NAME], build_file_log_rows(state))
    write_rows(tabs[ANOMALY_LOG_TAB_NAME], build_anomaly_rows(state))
    write_rows(tabs[MONTHLY_TAB_NAME], build_monthly_rows(state))


def main():
    parser = argparse.ArgumentParser(description="決済収集の運用監査タブを再生成する")
    parser.parse_args()
    sync_payment_collection_audit()
    print("決済収集の監査タブを更新しました。")


if __name__ == "__main__":
    main()
