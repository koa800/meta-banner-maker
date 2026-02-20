#!/usr/bin/env python3
"""
Google Calendar Manager
- Googleカレンダーの予定作成・取得・削除
- マルチアカウント対応（--account オプションで切り替え）
- OAuth2 認証 (refresh_token で自動更新)

アカウント:
  kohara   → kohara.kaito@team.addness.co.jp  (デフォルト)
  gwsadmin → gwsadmin@team.addness.co.jp

使い方:
  python3 calendar_manager.py list                           # 今後の予定一覧
  python3 calendar_manager.py list "2026-03-14"              # 特定日の予定
  python3 calendar_manager.py add "タイトル" "2026-03-14"    # 終日予定を追加
  python3 calendar_manager.py add "タイトル" "2026-03-14T10:00" "2026-03-14T11:00"  # 時間指定
  python3 calendar_manager.py delete "イベントID"            # 予定を削除
  python3 calendar_manager.py --account gwsadmin list        # 別アカウントで実行
"""

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import json
import logging
import sys
import os
import re
from datetime import datetime, timedelta

logger = logging.getLogger("calendar_manager")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_SECRET_PATH = os.path.join(BASE_DIR, "client_secret.json")

ACCOUNTS = {
    "kohara": os.path.join(BASE_DIR, "token_calendar.json"),
    "gwsadmin": os.path.join(BASE_DIR, "token_calendar_gwsadmin.json"),
    "personal": os.path.join(BASE_DIR, "token_calendar_personal.json"),
}
DEFAULT_ACCOUNT = "personal"

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
]


def get_credentials(account=None):
    """OAuth2 認証して資格情報を返す"""
    if account is None:
        account = DEFAULT_ACCOUNT

    if account not in ACCOUNTS:
        print(f"エラー: 不明なアカウント '{account}'")
        print(f"利用可能: {', '.join(ACCOUNTS.keys())}")
        sys.exit(1)

    token_path = ACCOUNTS[account]
    creds = None

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print(f"[{account}] ブラウザが開きます。対象アカウントでログインしてください。")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"[{account}] 認証完了。トークンを保存しました。")

    return creds


def get_service(account=None):
    """Google Calendar APIサービスを返す"""
    creds = get_credentials(account)
    return build("calendar", "v3", credentials=creds)


def list_events(service, target_date=None, max_results=10):
    """予定を一覧表示"""
    if target_date:
        time_min = f"{target_date}T00:00:00+09:00"
        time_max = f"{target_date}T23:59:59+09:00"
    else:
        now = datetime.now().astimezone()
        time_min = now.isoformat()
        time_max = (now + timedelta(days=30)).isoformat()

    events_result = service.events().list(
        calendarId="primary",
        timeMin=time_min,
        timeMax=time_max,
        maxResults=max_results,
        singleEvents=True,
        orderBy="startTime",
    ).execute()

    events = events_result.get("items", [])
    if not events:
        print("予定はありません。")
        return

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        print(f"  [{event['id'][:12]}] {start} ~ {end}  {event.get('summary', '(タイトルなし)')}")
        # 参加者リストを出力（自分以外、メールアドレスを表示）
        attendees = event.get("attendees", [])
        if attendees:
            others = [
                a.get("displayName") or a.get("email", "")
                for a in attendees
                if not a.get("self", False)
            ]
            if others:
                print(f"    参加者: {', '.join(others[:5])}")


def add_event(service, title, start, end=None):
    """予定を追加"""
    if "T" in start:
        event_body = {
            "summary": title,
            "start": {"dateTime": start, "timeZone": "Asia/Tokyo"},
            "end": {"dateTime": end or start, "timeZone": "Asia/Tokyo"},
        }
    else:
        if end is None:
            end_date = datetime.strptime(start, "%Y-%m-%d") + timedelta(days=1)
            end = end_date.strftime("%Y-%m-%d")
        event_body = {
            "summary": title,
            "start": {"date": start},
            "end": {"date": end},
        }

    event = service.events().insert(calendarId="primary", body=event_body).execute()
    print(f"予定を作成しました:")
    print(f"  タイトル: {event.get('summary')}")
    print(f"  開始: {event['start'].get('date', event['start'].get('dateTime'))}")
    print(f"  終了: {event['end'].get('date', event['end'].get('dateTime'))}")
    print(f"  リンク: {event.get('htmlLink')}")
    return event


def delete_event(service, event_id):
    """予定を削除"""
    service.events().delete(calendarId="primary", eventId=event_id).execute()
    print(f"予定を削除しました: {event_id}")


def main():
    args = sys.argv[1:]
    account = None

    if "--account" in args:
        idx = args.index("--account")
        account = args[idx + 1]
        args = args[:idx] + args[idx + 2:]

    if len(args) < 1:
        print(__doc__)
        sys.exit(1)

    command = args[0]
    service = get_service(account)

    if command == "list":
        target_date = args[1] if len(args) > 1 else None
        list_events(service, target_date)

    elif command == "add":
        if len(args) < 3:
            print("使い方: add 'タイトル' '開始日(時)' ['終了日(時)']")
            sys.exit(1)
        title = args[1]
        start = args[2]
        end = args[3] if len(args) > 3 else None
        add_event(service, title, start, end)

    elif command == "delete":
        if len(args) < 2:
            print("使い方: delete 'イベントID'")
            sys.exit(1)
        delete_event(service, args[1])

    else:
        print(f"不明なコマンド: {command}")
        print("利用可能: list, add, delete")
        sys.exit(1)


if __name__ == "__main__":
    main()
