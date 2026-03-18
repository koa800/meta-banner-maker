#!/usr/bin/env python3
"""
決済データの日次同期スクリプト。

Google Driveの日別フォルダからCSVを検出し、
共通25列に正規化して収集シートに追記する。

運用フロー:
1. 人がCSVをGoogle Driveの日別フォルダに格納
2. このスクリプトがOrchestratorで定期実行される
3. 未取り込みのCSVを検出 → 正規化 → 収集シートに追記
4. 取り込み済みのファイルは状態ファイルに記録（二重取り込み防止）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# 日別フォルダの親フォルダID（Google Drive）
DRIVE_FOLDER_ID = "1VH2IFBLWguLzxsIJwcLgd96ypTMOdk8Q"

# 状態ファイル（取り込み済みCSVを記録）
STATE_PATH = BASE_DIR / "data" / "payment_daily_sync_state.json"

# Google認証
TOKEN_PATH = BASE_DIR / "credentials" / "token.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def get_drive_service():
    """Google Drive APIサービスを取得"""
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
    return build("drive", "v3", credentials=creds)


def load_state() -> dict:
    """取り込み済みファイルの状態を読み込み"""
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text())
        except Exception:
            pass
    return {"processed_files": {}, "last_run": ""}


def save_state(state: dict):
    """状態を保存"""
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def list_daily_folders(service) -> List[dict]:
    """日別フォルダの一覧を取得（直近のもの）"""
    results = service.files().list(
        q=f"'{DRIVE_FOLDER_ID}' in parents and mimeType='application/vnd.google-apps.folder'",
        fields="files(id, name, createdTime)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
        orderBy="name desc",
        pageSize=10,
    ).execute()
    return results.get("files", [])


def list_csvs_in_folder(service, folder_id: str) -> List[dict]:
    """フォルダ内のCSVファイル一覧を取得"""
    results = service.files().list(
        q=f"'{folder_id}' in parents and name contains '.csv'",
        fields="files(id, name, size, createdTime)",
        includeItemsFromAllDrives=True,
        supportsAllDrives=True,
    ).execute()
    return results.get("files", [])


def download_csv(service, file_id: str) -> bytes:
    """CSVファイルをダウンロード"""
    request = service.files().get_media(fileId=file_id)
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    buffer.seek(0)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description="決済データの日次同期")
    parser.add_argument("--dry-run", action="store_true", help="取り込みせずに確認のみ")
    parser.add_argument("--days", type=int, default=2, help="確認する日数（デフォルト2日=今日と昨日）")
    args = parser.parse_args()

    state = load_state()
    processed = state.get("processed_files", {})

    print(f"最終実行: {state.get('last_run', 'なし')}")
    print(f"取り込み済みファイル: {len(processed)}件")

    # Google Drive接続
    service = get_drive_service()

    # 日別フォルダを取得
    folders = list_daily_folders(service)
    print(f"\n日別フォルダ: {len(folders)}件（直近）")

    new_files = []
    for folder in folders[:args.days]:
        folder_name = folder["name"]
        folder_id = folder["id"]
        print(f"\n[{folder_name}]")

        csvs = list_csvs_in_folder(service, folder_id)
        for csv_file in csvs:
            file_id = csv_file["id"]
            file_name = csv_file["name"]
            file_size = int(csv_file.get("size", 0))

            if file_id in processed:
                print(f"  {file_name} — 取り込み済み")
                continue

            print(f"  {file_name} ({file_size:,} bytes) — 未取り込み")
            new_files.append({
                "folder_name": folder_name,
                "file_id": file_id,
                "file_name": file_name,
                "file_size": file_size,
            })

    if not new_files:
        print("\n新しいCSVはありません。")
        save_state(state)
        return

    print(f"\n未取り込み: {len(new_files)}件")

    if args.dry_run:
        print("--dry-run: 取り込みをスキップします。")
        return

    # CSVをダウンロードしてローカルに保存
    tmp_dir = BASE_DIR / "data" / "payment_csv_tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    csv_paths = []
    for f in new_files:
        print(f"\nダウンロード: {f['file_name']}...")
        raw = download_csv(service, f["file_id"])
        local_path = tmp_dir / f["file_name"]
        local_path.write_bytes(raw)
        csv_paths.append(str(local_path))
        print(f"  保存: {local_path} ({len(raw):,} bytes)")

    # payment_csv_to_sheet.py を呼び出して取り込み
    import subprocess
    cmd = [
        sys.executable,
        str(BASE_DIR / "scripts" / "payment_csv_to_sheet.py"),
    ] + csv_paths

    print(f"\n取り込み実行中...")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BASE_DIR / "scripts"))
    print(result.stdout)
    if result.stderr:
        # FutureWarningなどは無視
        for line in result.stderr.split("\n"):
            if line and "FutureWarning" not in line and "NotOpenSSLWarning" not in line and "DeprecationWarning" not in line:
                print(f"  STDERR: {line}")

    if result.returncode == 0:
        # 取り込み成功。状態を更新
        for f in new_files:
            processed[f["file_id"]] = {
                "file_name": f["file_name"],
                "folder_name": f["folder_name"],
                "processed_at": datetime.now().isoformat(),
            }
        state["processed_files"] = processed
        save_state(state)
        print(f"\n取り込み完了。{len(new_files)}件を記録しました。")

        # 一時ファイルを削除
        for p in csv_paths:
            Path(p).unlink(missing_ok=True)
    else:
        print(f"\n取り込みでエラーが発生しました。returncode={result.returncode}")


if __name__ == "__main__":
    main()
