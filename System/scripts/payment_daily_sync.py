#!/usr/bin/env python3
"""
決済データの日次同期スクリプト。

Google Drive の日別フォルダから CSV を検出し、
正常な決済 CSV だけを収集シートへ追記する。

方針:
1. ファイル名で supported / ignored / unknown を分類する
2. supported でもヘッダー不一致なら「何か違う」と判定して隔離する
3. 正常ファイルだけ取り込む
4. 重複は file_id / file fingerprint / 行 fingerprint の3段で防ぐ
5. 異常ファイルは隔離ログに残し、初回だけ LINE 通知する
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

from sheets_manager import get_client
import payment_metrics_sheet_sync
from scripts import payment_csv_to_sheet as payment_import
from scripts import payment_collection_audit

try:
    from mac_mini.agent_orchestrator.notifier import send_line_notify
except Exception:
    send_line_notify = None

try:
    from line_notify import send as send_line_notify_simple
except Exception:
    send_line_notify_simple = None


DRIVE_FOLDER_ID = "1VH2IFBLWguLzxsIJwcLgd96ypTMOdk8Q"
STATE_PATH = BASE_DIR / "data" / "payment_daily_sync_state.json"
TMP_DIR = BASE_DIR / "data" / "payment_csv_tmp"
TOKEN_PATH = BASE_DIR / "credentials" / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_LOOKBACK_DAYS = 14
RETRYABLE_ANOMALY_CATEGORIES = {"import_error"}
MAX_HISTORY_ITEMS = 1000
MAX_SCANNED_FOLDERS = 30


def get_drive_service():
    """Google Drive API サービスを取得する。"""
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "processed_files": {},
        "processed_file_fingerprints": {},
        "anomaly_files": {},
        "anomaly_fingerprints": {},
        "anomaly_history": [],
        "duplicate_files": {},
        "recent_scanned_folders": [],
        "last_run": "",
        "last_summary": {},
    }


def checkpoint_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now().isoformat()
    checkpoint_state(state)


def append_anomaly_history(state: dict, event: dict) -> None:
    history = state.setdefault("anomaly_history", [])
    history.append(event)
    if len(history) > MAX_HISTORY_ITEMS:
        del history[:-MAX_HISTORY_ITEMS]


def list_daily_folders(service, page_size: int = 60) -> list[dict]:
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name, createdTime)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        orderBy="createdTime desc",
        pageSize=page_size,
    ).execute()
    return results.get("files", [])


def list_files_in_folder(service, folder_id: str) -> list[dict]:
    results = service.files().list(
        q=f"'{folder_id}' in parents and mimeType != 'application/vnd.google-apps.folder'",
        fields="files(id, name, mimeType, size, createdTime, md5Checksum)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return results.get("files", [])


def download_csv(service, file_id: str) -> bytes:
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.getvalue()


def extract_folder_date(folder_name: str) -> Optional[datetime]:
    match = re.search(r"(\d{4})/(\d{1,2})/(\d{1,2})", folder_name)
    if not match:
        return None
    year, month, day = map(int, match.groups())
    return datetime(year, month, day)


def extract_folder_date_key(folder_name: str) -> str:
    folder_date = extract_folder_date(folder_name)
    if folder_date is None:
        return ""
    return folder_date.strftime("%Y/%m/%d")


def build_file_fingerprint(file_meta: dict) -> str:
    md5_checksum = str(file_meta.get("md5Checksum") or "").strip()
    if md5_checksum:
        return f"md5:{md5_checksum}"
    raw = "|".join(
        [
            str(file_meta.get("name") or "").strip(),
            str(file_meta.get("size") or "").strip(),
            str(file_meta.get("createdTime") or "").strip(),
        ]
    ) 
    return "meta:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def is_csv_like_file(file_meta: dict) -> bool:
    mime_type = str(file_meta.get("mimeType") or "").lower()
    file_name = str(file_meta.get("name") or "").lower()
    return mime_type == "text/csv" or file_name.endswith(".csv")


def notify_line(message: str) -> bool:
    if send_line_notify is not None:
        try:
            return bool(send_line_notify(message))
        except Exception as exc:
            print(f"LINE通知でエラー: {exc}")

    if send_line_notify_simple is not None:
        try:
            return bool(send_line_notify_simple(message))
        except Exception as exc:
            print(f"簡易LINE通知でエラー: {exc}")

    print("LINE通知モジュールを読み込めないため通知をスキップします。")
    return False


def build_alert_message(title: str, file_name: str, folder_name: str, reason: str, category: str) -> str:
    category_label = {
        "ignored": "既知の対象外",
        "unknown": "未知ファイル",
        "unexpected_content": "何か違う",
        "import_error": "取込失敗",
    }.get(category, category)
    lines = [
        title,
        "",
        f"・判定: {category_label}",
        f"・ファイル: {file_name}",
        f"・フォルダ: {folder_name}",
        f"・理由: {reason}",
        "",
        "次に見てほしいこと",
    ]
    if category == "ignored":
        lines.append("・既知の対象外として自動除外済みです。必要なら対象外パターンだけ見直してください。")
    elif category == "unknown":
        lines.append("・対象外なら既知の対象外へ追加、対象なら取込仕様を追加してください。")
    elif category == "unexpected_content":
        lines.append("・ファイル名は対象ですが中身が想定外です。CSVヘッダー変更や出力形式変更を確認してください。")
    else:
        lines.append("・このファイルだけ再試行対象に残しています。正常ファイルの取込は継続しています。")
    return "\n".join(lines)


def register_anomaly(state: dict, file_meta: dict, category: str, reason: str, notify: bool = True) -> None:
    now_iso = datetime.now().isoformat()
    file_id = str(file_meta["id"])
    fingerprint = build_file_fingerprint(file_meta)

    previous = state.setdefault("anomaly_files", {}).get(file_id, {})
    previous_category = previous.get("category", "")
    previous_reason = previous.get("reason", "")
    should_record_history = not previous
    if not previous:
        previous = {
            "file_name": file_meta["name"],
            "folder_name": file_meta.get("folder_name", ""),
            "category": category,
            "reason": reason,
            "first_detected_at": now_iso,
            "notified_at": "",
            "file_fingerprint": fingerprint,
        }

    previous.update(
        {
            "file_name": file_meta["name"],
            "folder_name": file_meta.get("folder_name", ""),
            "category": category,
            "reason": reason,
            "last_seen_at": now_iso,
            "file_fingerprint": fingerprint,
            "source": str(file_meta.get("source") or ""),
        }
    )
    if previous_category != category or previous_reason != reason:
        should_record_history = True
    state["anomaly_files"][file_id] = previous

    anomaly_fingerprints = state.setdefault("anomaly_fingerprints", {})
    known_fingerprint = anomaly_fingerprints.get(fingerprint, {})
    already_notified = bool(previous.get("notified_at")) or bool(known_fingerprint.get("notified_at"))
    anomaly_fingerprints[fingerprint] = {
        "file_name": file_meta["name"],
        "category": category,
        "reason": reason,
        "source": str(file_meta.get("source") or ""),
        "notified_at": known_fingerprint.get("notified_at", ""),
    }

    if notify and not already_notified:
        title = "決済CSVの監視で確認が必要なファイルを検出しました"
        message = build_alert_message(
            title=title,
            file_name=file_meta["name"],
            folder_name=file_meta.get("folder_name", ""),
            reason=reason,
            category=category,
        )
        if notify_line(message):
            previous["notified_at"] = now_iso
            anomaly_fingerprints[fingerprint] = {
                "file_name": file_meta["name"],
                "category": category,
                "reason": reason,
                "source": str(file_meta.get("source") or ""),
                "notified_at": now_iso,
            }

    if should_record_history:
        append_anomaly_history(
            state,
            {
                "recorded_at": now_iso,
                "event_type": "detected",
                "category": category,
                "source": str(file_meta.get("source") or ""),
                "folder_name": file_meta.get("folder_name", ""),
                "file_name": file_meta["name"],
                "reason": reason,
                "notified_at": previous.get("notified_at", ""),
                "file_id": file_id,
                "file_fingerprint": fingerprint,
            },
        )


def mark_duplicate_file(state: dict, file_meta: dict, duplicate_reason: str) -> None:
    state.setdefault("duplicate_files", {})[str(file_meta["id"])] = {
        "file_name": file_meta["name"],
        "folder_name": file_meta.get("folder_name", ""),
        "duplicate_reason": duplicate_reason,
        "detected_at": datetime.now().isoformat(),
        "file_fingerprint": build_file_fingerprint(file_meta),
    }


def resolve_anomaly(state: dict, file_meta: dict) -> None:
    file_id = str(file_meta["id"])
    fingerprint = build_file_fingerprint(file_meta)
    resolved = state.setdefault("anomaly_files", {}).pop(file_id, None)
    state.setdefault("anomaly_fingerprints", {}).pop(fingerprint, None)
    if resolved:
        append_anomaly_history(
            state,
            {
                "recorded_at": datetime.now().isoformat(),
                "event_type": "resolved",
                "category": resolved.get("category", ""),
                "source": resolved.get("source", ""),
                "folder_name": resolved.get("folder_name", ""),
                "file_name": resolved.get("file_name", ""),
                "reason": resolved.get("reason", ""),
                "notified_at": resolved.get("notified_at", ""),
                "file_id": file_id,
                "file_fingerprint": fingerprint,
            },
        )


def anomaly_blocks_reimport(meta: dict) -> bool:
    category = str(meta.get("category") or "").strip()
    reason = str(meta.get("reason") or "").strip()
    if not category:
        return True
    if category == "unexpected_content" and "ヘッダーのみでデータ行がありません" in reason:
        return False
    return category not in RETRYABLE_ANOMALY_CATEGORIES


def infer_source_display_name(meta: dict) -> str:
    source = str(meta.get("source") or "").strip()
    if not source:
        source = payment_import.detect_source(str(meta.get("file_name") or "")) or ""
    if not source:
        return ""
    return payment_import.SOURCE_DISPLAY_NAMES.get(source, source)


def collect_unresolved_source_issues(state: dict) -> dict[str, int]:
    issue_counts: dict[str, int] = {}
    for meta in state.get("anomaly_files", {}).values():
        category = str(meta.get("category") or "").strip()
        if category not in {"unexpected_content", "import_error"}:
            continue
        source_name = infer_source_display_name(meta)
        if not source_name:
            continue
        issue_counts[source_name] = issue_counts.get(source_name, 0) + 1
    return issue_counts


def should_scan_folder(folder_name: str, days: int) -> bool:
    if "全期間" in folder_name:
        return False
    if days <= 0:
        return True
    folder_date = extract_folder_date(folder_name)
    if folder_date is None:
        return True
    cutoff = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days - 1)
    return folder_date >= cutoff


def build_folder_snapshot(folder_name: str, captured_at: str) -> dict:
    return {
        "folder_name": folder_name,
        "folder_date_key": extract_folder_date_key(folder_name),
        "captured_at": captured_at,
        "file_count": 0,
        "csv_like_count": 0,
        "supported_count": 0,
        "ignored_count": 0,
        "unknown_count": 0,
        "duplicate_count": 0,
    }


def save_recent_scanned_folders(state: dict, folder_snapshots: dict[str, dict]) -> None:
    snapshots = sorted(
        folder_snapshots.values(),
        key=lambda item: str(item.get("folder_date_key") or item.get("folder_name") or ""),
        reverse=True,
    )
    state["recent_scanned_folders"] = snapshots[:MAX_SCANNED_FOLDERS]


def main():
    parser = argparse.ArgumentParser(description="決済データの日次同期")
    parser.add_argument("--dry-run", action="store_true", help="取り込みせずに確認のみ")
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="確認対象の日数。フォルダ名の日付がこの範囲内のものを走査する",
    )
    args = parser.parse_args()

    state = load_state()
    processed_files = state.setdefault("processed_files", {})
    processed_fingerprints = state.setdefault("processed_file_fingerprints", {})
    anomaly_fingerprints = state.setdefault("anomaly_fingerprints", {})
    seen_file_fingerprints = set(processed_fingerprints.keys()) | {
        fingerprint
        for fingerprint, meta in anomaly_fingerprints.items()
        if anomaly_blocks_reimport(meta)
    }

    print(f"最終実行: {state.get('last_run', 'なし')}")
    print(f"取り込み済みファイル: {len(processed_files)}件")

    service = get_drive_service()
    folders = [folder for folder in list_daily_folders(service) if should_scan_folder(folder["name"], args.days)]
    print(f"\n対象フォルダ: {len(folders)}件")

    candidates: list[dict] = []
    scanned_at = datetime.now().isoformat()
    recent_folder_snapshots: dict[str, dict] = {}
    ignored_count = 0
    unknown_count = 0
    duplicate_count = 0

    for folder in folders:
        folder_name = folder["name"]
        folder_id = folder["id"]
        print(f"\n[{folder_name}]")

        files = list_files_in_folder(service, folder_id)
        snapshot_key = extract_folder_date_key(folder_name) or folder_name
        folder_snapshot = recent_folder_snapshots.setdefault(snapshot_key, build_folder_snapshot(folder_name, scanned_at))
        for file_meta in files:
            file_id = str(file_meta["id"])
            file_name = str(file_meta["name"])
            file_fingerprint = build_file_fingerprint(file_meta)
            file_meta["folder_name"] = folder_name
            file_meta["folder_id"] = folder_id
            file_meta["file_fingerprint"] = file_fingerprint
            folder_snapshot["file_count"] += 1

            file_status, source, reason = payment_import.classify_filename(file_name)
            csv_like = is_csv_like_file(file_meta)
            if csv_like:
                folder_snapshot["csv_like_count"] += 1
            if file_status == "unknown":
                folder_snapshot["unknown_count"] += 1
            elif file_status == "ignored":
                folder_snapshot["ignored_count"] += 1
            else:
                folder_snapshot["supported_count"] += 1

            if not csv_like:
                if file_status == "ignored":
                    ignored_count += 1
                    print(f"  {file_name} — 既知の対象外（非CSV）")
                    register_anomaly(state, file_meta, category="ignored", reason=reason, notify=False)
                else:
                    unknown_count += 1
                    mime_type = str(file_meta.get("mimeType") or "unknown")
                    print(f"  {file_name} — 未知ファイル（非CSV）")
                    register_anomaly(
                        state,
                        file_meta,
                        category="unknown",
                        reason=f"CSV以外のファイルを検出: {mime_type}",
                    )
                seen_file_fingerprints.add(file_fingerprint)
                continue

            if file_id in processed_files:
                print(f"  {file_name} — 取り込み済み")
                continue

            if file_fingerprint in seen_file_fingerprints:
                duplicate_count += 1
                folder_snapshot["duplicate_count"] += 1
                print(f"  {file_name} — 重複ファイルとしてスキップ")
                mark_duplicate_file(
                    state,
                    file_meta,
                    duplicate_reason=(
                        f"同一 fingerprint を "
                        f"{processed_fingerprints.get(file_fingerprint, {}).get('file_name') or state.get('anomaly_fingerprints', {}).get(file_fingerprint, {}).get('file_name', '既存ファイル')} "
                        "で確認済み"
                    ),
                )
                continue

            if file_status == "ignored":
                ignored_count += 1
                print(f"  {file_name} — 既知の対象外")
                register_anomaly(state, file_meta, category="ignored", reason=reason, notify=False)
                seen_file_fingerprints.add(file_fingerprint)
                continue
            if file_status == "unknown":
                unknown_count += 1
                print(f"  {file_name} — 未知ファイル")
                register_anomaly(state, file_meta, category="unknown", reason=reason)
                seen_file_fingerprints.add(file_fingerprint)
                continue

            file_meta["source"] = source
            print(f"  {file_name} — 取込候補 ({source})")
            candidates.append(file_meta)
            seen_file_fingerprints.add(file_fingerprint)

    print(
        "\n候補まとめ: "
        f"取込候補 {len(candidates)}件 / 対象外 {ignored_count}件 / 未知 {unknown_count}件 / 重複 {duplicate_count}件"
    )
    save_recent_scanned_folders(state, recent_folder_snapshots)
    checkpoint_state(state)

    if args.dry_run:
        print("--dry-run: 取り込みをスキップします。")
        save_state(state)
        return

    if not candidates:
        unresolved_source_issues = collect_unresolved_source_issues(state)
        if unresolved_source_issues:
            gc = get_client("kohara")
            spreadsheet = gc.open_by_key(payment_import.SHEET_ID)
            structure_errors = payment_import.validate_collection_sheet_headers(spreadsheet)
            if structure_errors:
                raise RuntimeError(" / ".join(structure_errors))
            payment_import.update_source_management(
                spreadsheet,
                {
                    source_name: {
                        "status": "要確認",
                        "error_count": issue_count,
                    }
                    for source_name, issue_count in unresolved_source_issues.items()
                },
            )
        state["last_summary"] = {
            "processed_files": 0,
            "ignored_files": ignored_count,
            "unknown_files": unknown_count,
            "duplicate_files": duplicate_count,
            "written_payment_rows": 0,
            "written_utage_rows": 0,
        }
        save_state(state)
        payment_collection_audit.sync_payment_collection_audit(spreadsheet=spreadsheet if unresolved_source_issues else None, state=state)
        payment_metrics_sheet_sync.sync_payment_metrics_sheet()
        print("\n新しい取込対象ファイルはありません。")
        return

    TMP_DIR.mkdir(parents=True, exist_ok=True)
    gc = get_client("kohara")
    spreadsheet = gc.open_by_key(payment_import.SHEET_ID)
    structure_errors = payment_import.validate_collection_sheet_headers(spreadsheet)
    if structure_errors:
        raise RuntimeError(" / ".join(structure_errors))
    existing_payment_signatures, existing_utage_signatures = payment_import.load_existing_row_signatures(spreadsheet)

    processed_count = 0
    unexpected_count = 0
    import_error_count = 0
    written_payment_total = 0
    written_utage_total = 0
    skipped_payment_duplicates_total = 0
    skipped_utage_duplicates_total = 0
    source_write_counts: dict[str, int] = {}

    for file_meta in candidates:
        local_path = TMP_DIR / file_meta["name"]
        try:
            print(f"\nダウンロード: {file_meta['name']}...")
            raw = download_csv(service, file_meta["id"])
            local_path.write_bytes(raw)
            print(f"  保存: {local_path} ({len(raw):,} bytes)")

            result = payment_import.process_csv_file(local_path)
            if result["status"] != "supported":
                unexpected_count += 1
                print(f"  取込除外: {result['status']} / {result['reason']}")
                register_anomaly(
                    state,
                    file_meta,
                    category=result["status"],
                    reason=result["reason"] or "CSV内容が想定と一致しません",
                )
                checkpoint_state(state)
                continue

            if result["warnings"]:
                print(f"  注意: {result['warnings'][0]}")

            write_result = payment_import.append_normalized_rows(
                spreadsheet,
                result["payment_rows"],
                result["utage_rows"],
                existing_payment_signatures=existing_payment_signatures,
                existing_utage_signatures=existing_utage_signatures,
            )

            written_count = write_result["written_payment_rows"] + write_result["written_utage_rows"]
            written_payment_total += write_result["written_payment_rows"]
            written_utage_total += write_result["written_utage_rows"]
            skipped_payment_duplicates_total += write_result["skipped_payment_duplicates"]
            skipped_utage_duplicates_total += write_result["skipped_utage_duplicates"]

            source_name = payment_import.SOURCE_DISPLAY_NAMES.get(result["source"], str(result["source"]))
            source_write_counts[source_name] = source_write_counts.get(source_name, 0) + written_count

            processed_count += 1
            resolve_anomaly(state, file_meta)
            processed_files[str(file_meta["id"])] = {
                "file_name": file_meta["name"],
                "folder_name": file_meta["folder_name"],
                "source": result["source"],
                "processed_at": datetime.now().isoformat(),
                "raw_row_count": result["raw_row_count"],
                "converted_row_count": result["converted_row_count"],
                "warnings": result["warnings"],
                "written_payment_rows": write_result["written_payment_rows"],
                "written_utage_rows": write_result["written_utage_rows"],
                "skipped_payment_duplicates": write_result["skipped_payment_duplicates"],
                "skipped_utage_duplicates": write_result["skipped_utage_duplicates"],
                "file_fingerprint": file_meta["file_fingerprint"],
            }
            processed_fingerprints[file_meta["file_fingerprint"]] = {
                "file_name": file_meta["name"],
                "processed_file_id": str(file_meta["id"]),
                "processed_at": datetime.now().isoformat(),
            }
            checkpoint_state(state)
            print(
                "  取り込み完了: "
                f"決済データ {write_result['written_payment_rows']:,}行 "
                f"(重複除外 {write_result['skipped_payment_duplicates']:,}行), "
                f"UTAGE補助 {write_result['written_utage_rows']:,}行 "
                f"(重複除外 {write_result['skipped_utage_duplicates']:,}行)"
            )
        except Exception as exc:
            import_error_count += 1
            print(f"  取り込み失敗: {exc}")
            register_anomaly(
                state,
                file_meta,
                category="import_error",
                reason=str(exc)[:200],
            )
            checkpoint_state(state)
        finally:
            local_path.unlink(missing_ok=True)

    source_issue_counts = collect_unresolved_source_issues(state)
    if source_write_counts or source_issue_counts:
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
        source_health = {
            source_name: {
                "status": "要確認" if source_issue_counts.get(source_name, 0) else "正常",
                "last_sync": now_str,
                "row_count": row_count,
                "error_count": source_issue_counts.get(source_name, 0),
            }
            for source_name, row_count in source_write_counts.items()
        }
        for source_name, issue_count in source_issue_counts.items():
            if source_name in source_health:
                continue
            source_health[source_name] = {
                "status": "要確認",
                "error_count": issue_count,
            }
        payment_import.update_source_management(spreadsheet, source_health)

    state["last_summary"] = {
        "processed_files": processed_count,
        "ignored_files": ignored_count,
        "unknown_files": unknown_count,
        "unexpected_content_files": unexpected_count,
        "duplicate_files": duplicate_count,
        "import_error_files": import_error_count,
        "written_payment_rows": written_payment_total,
        "written_utage_rows": written_utage_total,
        "skipped_payment_duplicates": skipped_payment_duplicates_total,
        "skipped_utage_duplicates": skipped_utage_duplicates_total,
    }
    save_state(state)
    payment_collection_audit.sync_payment_collection_audit(spreadsheet=spreadsheet, state=state)
    payment_metrics_sheet_sync.sync_payment_metrics_sheet()

    print("\n実行結果:")
    print(f"  処理成功ファイル: {processed_count}件")
    print(f"  既知の対象外: {ignored_count}件")
    print(f"  未知ファイル: {unknown_count}件")
    print(f"  中身不一致: {unexpected_count}件")
    print(f"  重複ファイル: {duplicate_count}件")
    print(f"  取込エラー: {import_error_count}件")
    print(f"  追加行数（決済データ）: {written_payment_total:,}行")
    print(f"  追加行数（UTAGE補助）: {written_utage_total:,}行")
    print(f"  重複除外（決済データ）: {skipped_payment_duplicates_total:,}行")
    print(f"  重複除外（UTAGE補助）: {skipped_utage_duplicates_total:,}行")


if __name__ == "__main__":
    main()
