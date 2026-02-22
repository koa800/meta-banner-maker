#!/usr/bin/env python3
"""
Google Docs Manager
- 任意のドキュメントURLまたはIDで読み込み・書き込み
- マルチアカウント対応（--account オプションで切り替え）
- OAuth2 認証 (refresh_token で自動更新)

アカウント:
  kohara   → kohara.kaito@team.addness.co.jp  (デフォルト)
  gwsadmin → gwsadmin@team.addness.co.jp
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

logger = logging.getLogger("docs_manager")

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


def extract_doc_id(url_or_id):
    """URLまたはIDからドキュメントIDを抽出"""
    if re.match(r'^[a-zA-Z0-9_-]+$', url_or_id) and '/' not in url_or_id:
        return url_or_id

    match = re.search(r'/document/d/([a-zA-Z0-9_-]+)', url_or_id)
    if match:
        return match.group(1)

    raise ValueError(f"ドキュメントIDを抽出できません: {url_or_id}")


def get_service(account=None, service_type="docs"):
    """OAuth2 認証してサービスを返す"""
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

    if service_type == "docs":
        return build("docs", "v1", credentials=creds)
    elif service_type == "drive":
        return build("drive", "v3", credentials=creds)


# ─── ヘルパー ─────────────────────────────────────────────────

def extract_text(elements):
    """ドキュメント要素からテキストを抽出"""
    text = ""
    for element in elements:
        if "paragraph" in element:
            for run in element["paragraph"].get("elements", []):
                if "textRun" in run:
                    text += run["textRun"]["content"]
        elif "table" in element:
            table = element["table"]
            for row in table.get("tableRows", []):
                row_text = []
                for cell in row.get("tableCells", []):
                    cell_text = extract_text(cell.get("content", []))
                    row_text.append(cell_text.strip())
                text += " | ".join(row_text) + "\n"
        elif "sectionBreak" in element:
            pass
    return text


# ─── 読み込み系 ───────────────────────────────────────────────

def info(url_or_id, account=None):
    """ドキュメントの情報を表示"""
    doc_id = extract_doc_id(url_or_id)
    service = get_service(account, "docs")
    doc = service.documents().get(documentId=doc_id).execute()

    print(f"タイトル: {doc['title']}")
    print(f"ID: {doc['documentId']}")
    print(f"URL: https://docs.google.com/document/d/{doc['documentId']}/edit")

    body = doc.get("body", {})
    content = body.get("content", [])
    text = extract_text(content)
    line_count = len(text.strip().split("\n"))
    char_count = len(text)
    print(f"行数: {line_count}")
    print(f"文字数: {char_count}")


def read(url_or_id, account=None):
    """ドキュメントの全テキストを読み込み"""
    doc_id = extract_doc_id(url_or_id)
    service = get_service(account, "docs")
    doc = service.documents().get(documentId=doc_id).execute()

    print(f"=== {doc['title']} ===\n")

    body = doc.get("body", {})
    content = body.get("content", [])
    text = extract_text(content)
    print(text)
    return text


def read_json(url_or_id, account=None):
    """ドキュメントの構造をJSON形式で出力"""
    doc_id = extract_doc_id(url_or_id)
    service = get_service(account, "docs")
    doc = service.documents().get(documentId=doc_id).execute()

    print(json.dumps(doc, ensure_ascii=False, indent=2))
    return doc


# ─── 書き込み系 ───────────────────────────────────────────────

def append_text(url_or_id, text, account=None):
    """ドキュメントの末尾にテキストを追加"""
    doc_id = extract_doc_id(url_or_id)
    service = get_service(account, "docs")

    # 末尾のインデックスを取得
    doc = service.documents().get(documentId=doc_id).execute()
    end_index = doc["body"]["content"][-1]["endIndex"] - 1

    requests = [
        {
            "insertText": {
                "location": {"index": end_index},
                "text": text,
            }
        }
    ]

    service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    print(f"追記完了: {len(text)} 文字を末尾に追加")


def replace_text(url_or_id, old_text, new_text, account=None):
    """ドキュメント内のテキストを置換"""
    doc_id = extract_doc_id(url_or_id)
    service = get_service(account, "docs")

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": old_text, "matchCase": True},
                "replaceText": new_text,
            }
        }
    ]

    result = service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()

    replies = result.get("replies", [{}])
    count = replies[0].get("replaceAllText", {}).get("occurrencesChanged", 0)
    print(f"置換完了: '{old_text}' → '{new_text}' ({count} 箇所)")


# ─── ドライブ系 ───────────────────────────────────────────────

def list_my_docs(query=None, account=None):
    """アクセスできるドキュメント一覧"""
    service = get_service(account, "drive")

    q = "mimeType='application/vnd.google-apps.document' and trashed=false"
    if query:
        q += f" and name contains '{query}'"

    results = service.files().list(
        q=q,
        pageSize=200,
        fields="files(id, name, modifiedTime)",
        orderBy="modifiedTime desc",
    ).execute()

    files = results.get("files", [])
    print(f"=== アクセス可能なドキュメント ({len(files)} 件) ===")
    if not files:
        print("  (見つかりませんでした)")
        return

    for f in files:
        print(f"  - {f['name']}")
        print(f"    URL: https://docs.google.com/document/d/{f['id']}/edit")
        print(f"    更新: {f.get('modifiedTime', '不明')}")
        print()


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
使い方: python3 docs_manager.py [--account <名前>] <コマンド> [オプション]

アカウント:
  --account kohara     kohara.kaito@team.addness.co.jp（デフォルト）
  --account gwsadmin   gwsadmin@team.addness.co.jp

コマンド:
  auth <アカウント名>                   認証を実行（ブラウザが開きます）
  info <URL|ID>                       ドキュメントの情報を表示
  read <URL|ID>                       ドキュメントのテキストを読み込み
  json <URL|ID>                       JSON構造を出力
  append <URL|ID> <テキスト>           末尾にテキストを追加
  replace <URL|ID> <旧テキスト> <新>   テキストを置換
  list [検索語]                        アクセス可能なドキュメント一覧

例:
  python3 docs_manager.py read "https://docs.google.com/document/d/xxxxx/edit"
  python3 docs_manager.py --account gwsadmin list
  python3 docs_manager.py append "URL" "追加するテキスト"
  python3 docs_manager.py replace "URL" "旧テキスト" "新テキスト"
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

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
            read(argv[1], account=account)

        elif cmd == "json":
            if len(argv) < 2:
                print("エラー: URLまたはIDを指定してください")
                sys.exit(1)
            read_json(argv[1], account=account)

        elif cmd == "append":
            if len(argv) < 3:
                print("エラー: URLとテキストを指定してください")
                sys.exit(1)
            append_text(argv[1], argv[2], account=account)

        elif cmd == "replace":
            if len(argv) < 4:
                print("エラー: URL, 旧テキスト, 新テキストを指定してください")
                sys.exit(1)
            replace_text(argv[1], argv[2], argv[3], account=account)

        elif cmd == "list":
            query = argv[1] if len(argv) > 1 else None
            list_my_docs(query=query, account=account)

        else:
            print(f"不明なコマンド: {cmd}")
            print_usage()
            sys.exit(1)

    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)
