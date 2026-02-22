#!/usr/bin/env python3
"""
Google Spreadsheet Manager
- 任意のスプレッドシートURLまたはIDで読み込み・書き込み
- マルチアカウント対応（--account オプションで切り替え）
- OAuth2 認証 (refresh_token で自動更新)

アカウント:
  kohara   → kohara.kaito@team.addness.co.jp  (デフォルト)
  gwsadmin → gwsadmin@team.addness.co.jp
"""

import gspread
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import json
import logging
import sys
import os
import re

logger = logging.getLogger("sheets_manager")

# 認証ファイルパス
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_DIR = os.path.join(BASE_DIR, "credentials")
CLIENT_SECRET_PATH = os.path.join(CREDENTIALS_DIR, "client_secret.json")

# アカウント別トークンファイル
ACCOUNTS = {
    "kohara": os.path.join(CREDENTIALS_DIR, "token.json"),
    "gwsadmin": os.path.join(CREDENTIALS_DIR, "token_gwsadmin.json"),
}
DEFAULT_ACCOUNT = "kohara"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def extract_spreadsheet_id(url_or_id):
    """URLまたはIDからスプレッドシートIDを抽出"""
    if re.match(r'^[a-zA-Z0-9_-]+$', url_or_id) and '/' not in url_or_id:
        return url_or_id, None

    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        spreadsheet_id = match.group(1)
        gid_match = re.search(r'[#&?]gid=(\d+)', url_or_id)
        gid = int(gid_match.group(1)) if gid_match else None
        return spreadsheet_id, gid

    raise ValueError(f"スプレッドシートIDを抽出できません: {url_or_id}")


def get_client(account=None):
    """OAuth2 認証してクライアントを返す"""
    if account is None:
        account = DEFAULT_ACCOUNT

    if account not in ACCOUNTS:
        print(f"エラー: 不明なアカウント '{account}'")
        print(f"利用可能: {', '.join(ACCOUNTS.keys())}")
        sys.exit(1)

    token_path = ACCOUNTS[account]
    creds = None

    # 既存トークンがあれば読み込み
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    # トークンがないか期限切れなら再認証
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print(f"[{account}] ブラウザが開きます。対象アカウントでログインしてください。")
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # トークンを保存
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"[{account}] 認証完了。トークンを保存しました。")

    client = gspread.authorize(creds)
    return client


# ─── 認証コマンド ─────────────────────────────────────────────

def auth(account):
    """指定アカウントの認証を実行（トークンを強制再取得）"""
    if account not in ACCOUNTS:
        print(f"エラー: 不明なアカウント '{account}'")
        print(f"利用可能: {', '.join(ACCOUNTS.keys())}")
        sys.exit(1)

    token_path = ACCOUNTS[account]
    print(f"[{account}] ブラウザが開きます。対象アカウントでログインしてください。")
    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET_PATH, SCOPES)
    creds = flow.run_local_server(port=0)

    with open(token_path, "w") as f:
        f.write(creds.to_json())
    print(f"[{account}] 認証完了！トークンを {token_path} に保存しました。")


# ─── 読み込み系 ───────────────────────────────────────────────

def info(url_or_id, account=None):
    """スプレッドシートの情報を表示（タイトル、全シート一覧）"""
    spreadsheet_id, _ = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    print(f"タイトル: {spreadsheet.title}")
    print(f"ID: {spreadsheet.id}")
    print(f"URL: {spreadsheet.url}")
    print(f"\nシート一覧:")
    for ws in spreadsheet.worksheets():
        print(f"  - {ws.title} (gid: {ws.id}, {ws.row_count}行 x {ws.col_count}列)")


def read(url_or_id, sheet_name=None, range_notation=None, account=None):
    """シートのデータを読み込み"""
    spreadsheet_id, gid = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    elif gid is not None:
        ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
        if ws is None:
            print(f"エラー: gid={gid} のシートが見つかりません")
            return None
    else:
        ws = spreadsheet.sheet1

    if range_notation:
        data = ws.get(range_notation)
    else:
        data = ws.get_all_values()

    print(f"=== {spreadsheet.title} / {ws.title} ===")
    print(f"({len(data)} 行)\n")
    for i, row in enumerate(data):
        print(f"  行{i+1}: {row}")
    return data


def read_json(url_or_id, sheet_name=None, account=None):
    """シートのデータをJSON形式で出力（1行目をヘッダーとして使用）"""
    spreadsheet_id, gid = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    elif gid is not None:
        ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
        if ws is None:
            print(f"エラー: gid={gid} のシートが見つかりません")
            return None
    else:
        ws = spreadsheet.sheet1

    records = ws.get_all_records()
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return records


def read_all(url_or_id, max_rows=30, account=None):
    """全シートの名前とデータを取得"""
    spreadsheet_id, _ = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    print(f"=== {spreadsheet.title} ===\n")

    for ws in spreadsheet.worksheets():
        print(f"--- {ws.title} (gid: {ws.id}) ---")
        data = ws.get_all_values()
        if data:
            for i, row in enumerate(data[:max_rows]):
                print(f"  行{i+1}: {row}")
            if len(data) > max_rows:
                print(f"  ... (残り {len(data) - max_rows} 行)")
        else:
            print("  (空のシート)")
        print()


# ─── 書き込み系 ───────────────────────────────────────────────

def write_cell(url_or_id, cell, value, sheet_name=None, account=None):
    """単一セルに書き込み"""
    spreadsheet_id, gid = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    elif gid is not None:
        ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
        if ws is None:
            print(f"エラー: gid={gid} のシートが見つかりません")
            return
    else:
        ws = spreadsheet.sheet1

    ws.update_acell(cell, value)
    print(f"書き込み完了: {ws.title}!{cell} = {value}")


def write_range(url_or_id, range_notation, values, sheet_name=None, account=None):
    """範囲に書き込み"""
    spreadsheet_id, gid = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    elif gid is not None:
        ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
        if ws is None:
            print(f"エラー: gid={gid} のシートが見つかりません")
            return
    else:
        ws = spreadsheet.sheet1

    ws.update(range_notation, values)
    print(f"書き込み完了: {ws.title}!{range_notation} ({len(values)} 行)")


def append_rows(url_or_id, values, sheet_name=None, account=None):
    """末尾に行を追加"""
    spreadsheet_id, gid = extract_spreadsheet_id(url_or_id)
    client = get_client(account)
    spreadsheet = client.open_by_key(spreadsheet_id)

    if sheet_name:
        ws = spreadsheet.worksheet(sheet_name)
    elif gid is not None:
        ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
        if ws is None:
            print(f"エラー: gid={gid} のシートが見つかりません")
            return
    else:
        ws = spreadsheet.sheet1

    ws.append_rows(values)
    print(f"追加完了: {ws.title} に {len(values)} 行追加")


# ─── ドライブ系 ───────────────────────────────────────────────

def list_my_sheets(query=None, account=None):
    """自分がアクセスできるスプレッドシート一覧"""
    client = get_client(account)
    spreadsheets = client.list_spreadsheet_files(title=query)

    print(f"=== アクセス可能なスプレッドシート ===")
    if not spreadsheets:
        print("  (見つかりませんでした)")
        return

    for ss in spreadsheets:
        print(f"  - {ss['name']}")
        print(f"    ID: {ss['id']}")
        print(f"    URL: https://docs.google.com/spreadsheets/d/{ss['id']}/edit")
        print()


# ─── CLI ──────────────────────────────────────────────────────

def parse_account(args):
    """--account オプションを解析して除去"""
    account = DEFAULT_ACCOUNT
    filtered = []
    i = 0
    while i < len(args):
        if args[i] == "--account" and i + 1 < len(args):
            account = args[i + 1]
            i += 2
        else:
            filtered.append(args[i])
            i += 1
    return account, filtered


def print_usage():
    print("""
使い方: python3 sheets_manager.py [--account <名前>] <コマンド> [オプション]

アカウント:
  --account kohara     kohara.kaito@team.addness.co.jp（デフォルト）
  --account gwsadmin   gwsadmin@team.addness.co.jp

コマンド:
  auth <アカウント名>                   認証を実行（ブラウザが開きます）
  info <URL|ID>                       スプレッドシートの情報を表示
  read <URL|ID> [シート名] [範囲]     シートのデータを読み込み
  json <URL|ID> [シート名]            JSON形式で読み込み
  all <URL|ID>                        全シートを読み込み
  write <URL|ID> <セル> <値> [シート]  単一セルに書き込み
  append <URL|ID> <JSON配列>          末尾に行を追加
  list [検索語]                        アクセス可能なシート一覧

例:
  python3 sheets_manager.py auth gwsadmin
  python3 sheets_manager.py --account gwsadmin list
  python3 sheets_manager.py --account gwsadmin read "https://docs.google.com/spreadsheets/d/xxxxx/edit"
  python3 sheets_manager.py read "https://docs.google.com/spreadsheets/d/xxxxx/edit#gid=0"
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    # --account オプションを解析
    account, argv = parse_account(sys.argv[1:])

    if not argv:
        print_usage()
        sys.exit(0)

    cmd = argv[0]

    try:
        if cmd == "auth":
            target = argv[1] if len(argv) > 1 else account
            auth(target)

        elif cmd == "info":
            if len(argv) < 2:
                print("エラー: URLまたはIDを指定してください")
                sys.exit(1)
            info(argv[1], account=account)

        elif cmd == "read":
            if len(argv) < 2:
                print("エラー: URLまたはIDを指定してください")
                sys.exit(1)
            url = argv[1]
            sheet_name = argv[2] if len(argv) > 2 else None
            range_notation = argv[3] if len(argv) > 3 else None
            read(url, sheet_name=sheet_name, range_notation=range_notation, account=account)

        elif cmd == "json":
            if len(argv) < 2:
                print("エラー: URLまたはIDを指定してください")
                sys.exit(1)
            url = argv[1]
            sheet_name = argv[2] if len(argv) > 2 else None
            read_json(url, sheet_name=sheet_name, account=account)

        elif cmd == "all":
            if len(argv) < 2:
                print("エラー: URLまたはIDを指定してください")
                sys.exit(1)
            read_all(argv[1], account=account)

        elif cmd == "write":
            if len(argv) < 4:
                print("エラー: URL, セル, 値を指定してください")
                sys.exit(1)
            url = argv[1]
            cell = argv[2]
            value = argv[3]
            sheet_name = argv[4] if len(argv) > 4 else None
            write_cell(url, cell, value, sheet_name=sheet_name, account=account)

        elif cmd == "append":
            if len(argv) < 3:
                print("エラー: URLとJSON配列を指定してください")
                sys.exit(1)
            url = argv[1]
            values = json.loads(argv[2])
            sheet_name = argv[3] if len(argv) > 3 else None
            append_rows(url, values, sheet_name=sheet_name, account=account)

        elif cmd == "list":
            query = argv[1] if len(argv) > 1 else None
            list_my_sheets(query=query, account=account)

        else:
            print(f"不明なコマンド: {cmd}")
            print_usage()
            sys.exit(1)

    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
