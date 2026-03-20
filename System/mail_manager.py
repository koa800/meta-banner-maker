#!/usr/bin/env python3
"""
メール受信箱マネージャー
- 1時間ごとにGmailを取得し、返信必要/不要で分類
- 返信必要なもの: 返信文を提案 → 承認で自動送信
- 不要なもの: 削除（ゴミ箱へ）
- 同一送信者で「不要」が10回以上: Gmailフィルターで受信トレイに届かないようにする

アカウント:
  personal → koa800sea.nifs@gmail.com  (デフォルト)
  kohara   → kohara.kaito@team.addness.co.jp
  gwsadmin → gwsadmin@team.addness.co.jp

使い方:
  python3 mail_manager.py run              # 取得・分類（cron用）
  python3 mail_manager.py review          # 削除確認待ちを承認→学習
  python3 mail_manager.py approve         # 返信待ちを表示し、承認で送信
  python3 mail_manager.py status          # 状態・保留件数・学習済み一覧
  python3 mail_manager.py setup-slack     # Slack 連携（URL入力→保存→テスト送信）
  python3 mail_manager.py slack-test      # Slack にテスト通知を送る
  python3 mail_manager.py --account gwsadmin run
"""

import base64
import json
import logging
import os
import re
import sys
import urllib.request
from email.mime.text import MIMEText
from pathlib import Path
from datetime import datetime

from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logger = logging.getLogger("mail_manager")

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_DIR = BASE_DIR / "credentials"

ACCOUNTS = {
    "personal": CREDENTIALS_DIR / "token_gmail_personal.json",
    "kohara": CREDENTIALS_DIR / "token_gmail.json",
    "adteam": CREDENTIALS_DIR / "token_gmail_adteam.json",
    "gwsadmin": CREDENTIALS_DIR / "token_gmail_gwsadmin.json",
}
CLIENT_SECRETS = {
    "personal": CREDENTIALS_DIR / "client_secret_personal.json",
    "kohara": CREDENTIALS_DIR / "client_secret.json",
    "adteam": CREDENTIALS_DIR / "client_secret_personal.json",
    "gwsadmin": CREDENTIALS_DIR / "client_secret.json",
}
DEFAULT_ACCOUNT = "personal"

DATA_DIR = BASE_DIR / "mail_inbox_data"
STATE_FILE = DATA_DIR / "state.json"
PENDING_FILE = DATA_DIR / "pending.json"
DELETE_REVIEW_FILE = DATA_DIR / "delete_review.json"
CONFIG_FILE = DATA_DIR / "config.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

NOT_NEEDED_THRESHOLD = 5  # この回数以上削除したら送信者をブロック（受信トレイに届かなくなる）


class ReauthRequiredError(RuntimeError):
    """対話端末での再認証が必要なときに送出する。"""


def _interactive_auth_allowed() -> bool:
    """ブラウザ認証を始めてよい実行文脈か判定する。"""
    override = os.environ.get("MAIL_MANAGER_ALLOW_BROWSER_AUTH", "").strip().lower()
    if override in {"1", "true", "yes", "on"}:
        return True
    if override in {"0", "false", "no", "off"}:
        return False
    return sys.stdin.isatty() and sys.stdout.isatty()


def _quarantine_token(token_path: Path, reason: str) -> None:
    """壊れた token を退避する。"""
    if not token_path.exists():
        return
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = token_path.with_name(f"{token_path.stem}.{reason}.{timestamp}{token_path.suffix}")
    try:
        token_path.replace(backup_path)
    except OSError:
        pass


def _notify_reauth_required(account: str, detail: str) -> None:
    """Slack に再認証必要を通知する。"""
    command = f"python3 /Users/koa800/Desktop/cursor/System/mail_manager.py --account {account} run"
    message = (
        f"⚠️ Gmail({account}) の再認証が必要です。\n"
        f"{detail}\n"
        f"新MacBookの対話ターミナルで次を実行してください。\n`{command}`"
    )
    send_to_slack(message)


def load_config():
    """config.json から設定を読み込む。環境変数が優先。"""
    out = {
        "slack_webhook_url": os.environ.get("SLACK_WEBHOOK_URL", "").strip(),
        "slack_channel": os.environ.get("SLACK_CHANNEL", "").strip(),
        "openai_api_key": os.environ.get("OPENAI_API_KEY", "").strip(),
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not out["slack_webhook_url"]:
                out["slack_webhook_url"] = (data.get("slack_webhook_url") or "").strip()
            if not out["slack_channel"]:
                out["slack_channel"] = (data.get("slack_channel") or "").strip()
            if not out["openai_api_key"]:
                out["openai_api_key"] = (data.get("openai_api_key") or "").strip()
        except Exception:
            pass
    return out


def load_slack_config():
    """後方互換性のため"""
    return load_config()


def send_to_slack(message: str) -> bool:
    """Slack Incoming Webhook で通知を送信。環境変数または config.json の URL を使用。"""
    cfg = load_slack_config()
    webhook_url = cfg["slack_webhook_url"]
    if not webhook_url:
        return False
    payload = {
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    channel = cfg["slack_channel"]
    if channel:
        payload["channel"] = channel if channel.startswith("#") else f"#{channel}"
    try:
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status == 200
    except Exception as e:
        logger.error("Slack送信エラー", extra={"error": {"type": type(e).__name__, "message": str(e)}})
        print(f"Slack送信エラー: {e}")
        return False


def get_credentials(account=None):
    """OAuth2 認証して資格情報を返す"""
    if account is None:
        account = DEFAULT_ACCOUNT
    if account not in ACCOUNTS:
        logger.error("不明なアカウント", extra={"account": account, "available": list(ACCOUNTS.keys())})
        print(f"エラー: 不明なアカウント '{account}'")
        print(f"利用可能: {', '.join(ACCOUNTS.keys())}")
        sys.exit(1)

    token_path = ACCOUNTS[account]
    creds = None
    if token_path.exists():
        try:
            if token_path.stat().st_size == 0:
                raise ValueError("token file is empty")
            creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        except Exception as e:
            _quarantine_token(token_path, "invalid")
            logger.warning("Gmail token load failed; falling back to browser auth", extra={
                "account": account,
                "error": {"type": type(e).__name__, "message": str(e)},
            })
            print(f"[{account}] 既存トークンを読み込めませんでした。再認証が必要です。")
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as e:
                _quarantine_token(token_path, "invalid")
                logger.warning("Gmail token refresh failed; falling back to browser auth", extra={
                    "account": account,
                    "error": {"type": type(e).__name__, "message": str(e)},
                })
                print(f"[{account}] 既存トークンを再利用できませんでした。ブラウザ再認証に切り替えます。")
                creds = None
        if not creds or not creds.valid:
            if not _interactive_auth_allowed():
                detail = "保存済みトークンが無いか、無効です。"
                _notify_reauth_required(account, detail)
                raise ReauthRequiredError(f"Gmail({account}) は対話ターミナルでの再認証が必要です。")
            client_secret_path = CLIENT_SECRETS.get(account, CLIENT_SECRETS["kohara"])
            print(f"[{account}] ブラウザが開きます。対象アカウントでログインしてください。")
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as f:
            f.write(creds.to_json())
        print(f"[{account}] 認証完了。トークンを保存しました。")
    return creds


def get_gmail_service(account=None):
    """Gmail API サービスを返す"""
    creds = get_credentials(account)
    return build("gmail", "v1", credentials=creds)


def ensure_data_dir():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_state():
    ensure_data_dir()
    if not STATE_FILE.exists():
        return {"not_needed_count": {}, "blocked_senders": [], "auto_delete_senders": [], "held_message_ids": []}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if "auto_delete_senders" not in data:
            data["auto_delete_senders"] = []
        if "held_message_ids" not in data:
            data["held_message_ids"] = []
        return data


def save_state(state):
    ensure_data_dir()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_pending():
    ensure_data_dir()
    if not PENDING_FILE.exists():
        return []
    with open(PENDING_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_pending(pending):
    ensure_data_dir()
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)


def load_delete_review():
    ensure_data_dir()
    if not DELETE_REVIEW_FILE.exists():
        return []
    with open(DELETE_REVIEW_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_delete_review(review_list):
    ensure_data_dir()
    with open(DELETE_REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(review_list, f, ensure_ascii=False, indent=2)


def parse_sender(header_list):
    """From ヘッダーからメールアドレスを抽出"""
    if not header_list:
        return ""
    for h in header_list:
        if h.get("name", "").lower() == "from":
            v = h.get("value", "")
            # "Name <email@example.com>" 形式
            match = re.search(r"<([^>]+)>", v)
            if match:
                return match.group(1).strip().lower()
            return v.strip().lower()
    return ""


def get_header(msg, name):
    """メッセージヘッダーを取得"""
    headers = msg.get("payload", {}).get("headers", [])
    for h in headers:
        if h.get("name", "").lower() == name.lower():
            return h.get("value", "")
    return ""


def get_body_text(msg, max_len=2000):
    """本文テキストを取得"""
    payload = msg.get("payload", {})
    body = ""
    if "body" in payload and payload["body"].get("data"):
        body = base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    else:
        for part in payload.get("parts", []):
            if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
                body = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                break
    return (body or "(本文なし)")[:max_len]


SYSTEM_LABELS = {
    "INBOX", "UNREAD", "IMPORTANT", "SENT", "DRAFT", "SPAM", "TRASH",
    "STARRED", "CATEGORY_PERSONAL", "CATEGORY_SOCIAL", "CATEGORY_PROMOTIONS",
    "CATEGORY_UPDATES", "CATEGORY_FORUMS",
}


def fetch_inbox(service, max_results=50, exclude_senders=None):
    """受信トレイのメールを取得（ブロック済み送信者は除外）"""
    exclude_senders = set((exclude_senders or []))
    result = service.users().messages().list(
        userId="me",
        labelIds=["INBOX"],
        maxResults=max_results,
    ).execute()
    messages = result.get("messages", [])
    out = []
    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        sender = parse_sender(msg.get("payload", {}).get("headers", []))
        if sender in exclude_senders:
            continue
        subject = get_header(msg, "Subject")
        body_text = get_body_text(msg, 2000)
        snippet = msg.get("snippet", "") or body_text[:300]
        label_ids = set(msg.get("labelIds", []))
        has_custom_label = bool(label_ids - SYSTEM_LABELS)
        out.append({
            "id": msg["id"],
            "thread_id": msg.get("threadId", ""),
            "from": sender,
            "subject": subject,
            "snippet": snippet,
            "body": body_text,
            "message_id_header": get_header(msg, "Message-ID"),
            "date": get_header(msg, "Date"),
            "has_custom_label": has_custom_label,
        })
    return out


def classify_messages(messages, openai_api_key=None):
    """OpenAI で返信必要/不要を分類"""
    if not messages:
        return []
    try:
        from openai import OpenAI
    except ImportError:
        print("OpenAI 未インストール: pip install openai")
        return [{"message": m, "need_reply": True, "reason": "OpenAI未使用", "suggested_reply": ""} for m in messages]

    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_API_KEY が未設定のため、すべて「返信必要」として扱います。")
        return [{"message": m, "need_reply": True, "reason": "API未設定", "suggested_reply": ""} for m in messages]

    client = OpenAI(api_key=api_key)
    batch = []
    for m in messages:
        batch.append(
            f"From: {m['from']}\nSubject: {m['subject']}\n\n{m['snippet']}"
        )

    prompt = """以下のメールそれぞれについて、返信が必要か不要かを判定してください。

【絶対に削除してはいけない（返信必要として扱う）】
- イベント予約・申し込み確認（イベサポ、予約確認、チケットなど）
- Lステップの通知（顧客からの質問、回答通知など）
- 個人宛のメッセージ（名前を呼びかけている、個人的な内容）
- 予約・注文の確認メール
- アカウントセキュリティ警告（不正ログイン、新しいデバイスなど）

【返信不要（削除可）の例】
- 純粋なニュースレター・メルマガ（読者向け一斉配信）
- 広告・セール・キャンペーン案内
- SNS通知（LinkedIn、Wantedly、Facebook等の自動通知）
- 一般的なサービス更新通知

【返信必要の例】
- 質問・依頼・打診がある
- 相手が返事を期待している
- ビジネス上返信すべきもの

※迷ったら「返信必要」として扱う。削除より残す方が安全。

各メールに対して、次のJSON形式で1行ずつ出力してください（他に説明文は不要）:
{"need_reply": true/false, "reason": "理由（短く）"}

メール一覧:
"""
    for i, body in enumerate(batch, 1):
        prompt += f"\n--- メール{i} ---\n{body}\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたはメールの優先度を判定する秘書です。JSONのみを出力してください。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2000,
            temperature=0.2,
        )
        text = response.choices[0].message.content.strip()
        results = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            if line.startswith("{"):
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    results.append({"need_reply": True, "reason": "parse error"})
        while len(results) < len(messages):
            results.append({"need_reply": True, "reason": "未分類"})
        out = []
        for m, r in zip(messages, results[: len(messages)]):
            out.append({
                "message": m,
                "need_reply": bool(r.get("need_reply", True)),
                "reason": str(r.get("reason", "")),
                "suggested_reply": "",
            })
        return out
    except Exception as e:
        logger.exception("メール分類エラー", extra={
            "mail_count": len(messages),
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        print(f"分類エラー: {e}")
        return [{"message": m, "need_reply": True, "reason": str(e), "suggested_reply": ""} for m in messages]


def _load_identity_context():
    """IDENTITY.md から文体情報を読み込む"""
    identity_path = BASE_DIR.parent / "Master" / "self_clone" / "kohara" / "IDENTITY.md"
    if not identity_path.exists():
        return ""
    try:
        return identity_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def generate_replies(need_reply_items, openai_api_key=None):
    """返信必要メールに対して、甲原さんの文体で適切な返信案を生成"""
    if not need_reply_items:
        return need_reply_items
    try:
        from openai import OpenAI
    except ImportError:
        return need_reply_items

    api_key = openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return need_reply_items

    client = OpenAI(api_key=api_key)
    identity = _load_identity_context()

    batch = []
    for item in need_reply_items:
        m = item["message"]
        body = m.get("body", m.get("snippet", ""))
        batch.append(f"From: {m['from']}\nSubject: {m['subject']}\nDate: {m.get('date', '')}\n\n{body}")

    prompt = f"""あなたは甲原海人（こうはらかいと）のメール秘書です。
以下のメールそれぞれに対して、甲原として適切な返信案を作成してください。

## 甲原海人のプロフィール・文体
{identity}

## メール返信のルール

1. **返信が不要なメール（自動通知・領収書・セキュリティ通知など）には「返信不要」と書く**
   - 決済完了通知、領収書、パスワード変更通知など → 返信不要
   - サービスからの自動通知（料金改定のお知らせ等） → 返信不要
   - ただしアクションが必要な場合は返信案を書く

2. **返信する場合のルール**
   - メール文体は丁寧語ベース（LINEよりフォーマル）
   - ただし甲原らしい温度感・テンポは残す
   - 「お疲れ様です！」「ありがとうございます！」など、甲原らしい挨拶で始める
   - 要件に対して的確に回答する
   - 不明点があれば素直に聞く
   - 過度に丁寧な敬語は使わない（「かしこまりました」→「承知しました！」）

3. **イベント招待・セミナー案内**
   - 参加するかどうかは甲原が判断するので、「参加/不参加を選べる形」で返信案を2パターン提示
   - 形式: 「【参加する場合】...」「【不参加の場合】...」

4. **送信者が個人（ビジネス相手）の場合**
   - 相手の要件をしっかり読み取って回答
   - 相手が返答を求めている質問には具体的に答える

## 出力形式
各メールに対して、次のJSON形式で1行ずつ出力してください（他に説明文は不要）:
- 返信する場合: {{"reply": "返信案テキスト", "no_reply_reason": ""}}
- 返信不要の場合: {{"reply": "", "no_reply_reason": "理由（例: 決済完了通知のため返信不要）"}}

重要:
- replyフィールドに「返信不要」というテキストを入れないでください。返信不要の場合はreplyを空文字にしてno_reply_reasonに理由を書いてください
- イベント招待の場合はreplyに「【参加する場合】\\n...\\n\\n【不参加の場合】\\n...」の形で2パターン書いてください

メール一覧:
"""
    for i, body_text in enumerate(batch, 1):
        prompt += f"\n--- メール{i} ---\n{body_text}\n"

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "あなたは甲原海人のメール秘書です。甲原の文体を再現した実用的な返信案を作成してください。JSONのみを出力してください。"},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            temperature=0.4,
        )
        text = response.choices[0].message.content.strip()
        results = []
        for line in text.split("\n"):
            line = line.strip()
            if not line or line.startswith("---"):
                continue
            if line.startswith("{"):
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    results.append({"reply": "", "no_reply_reason": ""})
        while len(results) < len(need_reply_items):
            results.append({"reply": "", "no_reply_reason": ""})

        for item, r in zip(need_reply_items, results[:len(need_reply_items)]):
            reply = str(r.get("reply", "") or "").strip()
            no_reply_reason = str(r.get("no_reply_reason", "") or "").strip()
            # "返信不要" がreplyに入ってしまった場合のフォールバック
            if reply in ("返信不要", "返信不要です", "返信不要。"):
                no_reply_reason = no_reply_reason or "自動通知のため返信不要"
                reply = ""
            if no_reply_reason and not reply:
                item["suggested_reply"] = ""
                item["no_reply_reason"] = no_reply_reason
            else:
                item["suggested_reply"] = reply
                item["no_reply_reason"] = ""
        return need_reply_items
    except Exception as e:
        logger.exception("返信案生成エラー", extra={"error": str(e)})
        print(f"返信案生成エラー: {e}")
        return need_reply_items


def create_block_filter(service, sender_email):
    """送信者をブロック: 受信トレイに入れないフィルターを作成"""
    body = {
        "criteria": {"from": sender_email},
        "action": {"removeLabelIds": ["INBOX"]},
    }
    try:
        service.users().settings().filters().create(userId="me", body=body).execute()
        return True
    except Exception as e:
        logger.error("フィルター作成エラー", extra={
            "sender": sender_email,
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        print(f"フィルター作成エラー ({sender_email}): {e}")
        return False


def get_labels(service):
    """ユーザー作成のラベル一覧を取得（システムラベルを除外）"""
    try:
        results = service.users().labels().list(userId="me").execute()
        labels = results.get("labels", [])
        user_labels = [
            {"id": l["id"], "name": l["name"]}
            for l in labels
            if l["type"] == "user"
        ]
        return sorted(user_labels, key=lambda x: x["name"])
    except Exception as e:
        logger.error("ラベル取得エラー", extra={"error": {"type": type(e).__name__, "message": str(e)}})
        print(f"ラベル取得エラー: {e}")
        return []


def create_label(service, label_name):
    """新しいラベルを作成"""
    try:
        body = {
            "name": label_name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }
        result = service.users().labels().create(userId="me", body=body).execute()
        return {"id": result["id"], "name": result["name"]}
    except Exception as e:
        if "already exists" in str(e).lower():
            labels = get_labels(service)
            for l in labels:
                if l["name"] == label_name:
                    return l
        logger.error("ラベル作成エラー", extra={"label": label_name, "error": {"type": type(e).__name__, "message": str(e)}})
        print(f"ラベル作成エラー: {e}")
        return None


def create_label_filter(service, sender_email, label_id, skip_inbox=True):
    """送信者からのメールを指定ラベルに振り分けるフィルターを作成"""
    try:
        filters = service.users().settings().filters().list(userId="me").execute()
        for f in filters.get("filter", []):
            criteria = f.get("criteria", {})
            if criteria.get("from") == sender_email:
                service.users().settings().filters().delete(
                    userId="me", id=f["id"]
                ).execute()
                break
    except Exception:
        pass

    action = {"addLabelIds": [label_id]}
    if skip_inbox:
        action["removeLabelIds"] = ["INBOX"]
    body = {
        "criteria": {"from": sender_email},
        "action": action,
    }
    try:
        service.users().settings().filters().create(userId="me", body=body).execute()
        return True
    except Exception as e:
        logger.error("ラベルフィルター作成エラー", extra={
            "sender": sender_email, "label_id": label_id,
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        print(f"フィルター作成エラー ({sender_email}): {e}")
        return False


def trash_message(service, msg_id):
    """メールをゴミ箱に移動"""
    try:
        service.users().messages().trash(userId="me", id=msg_id).execute()
        return True
    except Exception as e:
        logger.error("ゴミ箱移動エラー", extra={"msg_id": msg_id, "error": {"type": type(e).__name__, "message": str(e)}})
        print(f"ゴミ箱移動エラー: {e}")
        return False


def archive_message(service, msg_id):
    """メールを受信トレイから外す（アーカイブ）"""
    try:
        service.users().messages().modify(
            userId="me",
            id=msg_id,
            body={"removeLabelIds": ["INBOX"]},
        ).execute()
        return True
    except Exception as e:
        print(f"アーカイブエラー: {e}")
        return False


def send_reply(service, original_msg, reply_text, from_email):
    """返信メールを送信（スレッドに追加）。original_msg は {from, subject, thread_id, message_id_header} の辞書"""
    subject = (original_msg.get("subject") or "").strip()
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject
    msg = MIMEText(reply_text, "plain", "utf-8")
    msg["To"] = original_msg.get("from", from_email)
    msg["Subject"] = subject
    msg["In-Reply-To"] = original_msg.get("message_id_header", "")
    msg["References"] = original_msg.get("message_id_header", "")

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").strip()
    body = {"raw": raw, "threadId": original_msg.get("thread_id")}
    try:
        service.users().messages().send(userId="me", body=body).execute()
        return True
    except Exception as e:
        logger.error("メール送信エラー", extra={
            "to": original_msg.get("from", ""),
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        print(f"送信エラー: {e}")
        return False


def run_once(account=None, openai_api_key=None):
    """1回分の取得・分類・不要削除・ブロック処理"""
    global DATA_DIR, STATE_FILE, PENDING_FILE, DELETE_REVIEW_FILE
    effective = account or DEFAULT_ACCOUNT
    DATA_DIR = BASE_DIR / "mail_inbox_data" / effective
    STATE_FILE = DATA_DIR / "state.json"
    PENDING_FILE = DATA_DIR / "pending.json"
    DELETE_REVIEW_FILE = DATA_DIR / "delete_review.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    logger.info("run_once 開始", extra={"account": effective})
    if not openai_api_key:
        openai_api_key = load_config().get("openai_api_key")
    service = get_gmail_service(account)
    state = load_state()
    blocked = set(state.get("blocked_senders", []))
    auto_delete = set(state.get("auto_delete_senders", []))
    count_map = state.get("not_needed_count", {})

    messages = fetch_inbox(service, max_results=50, exclude_senders=blocked)
    if not messages:
        logger.info("未処理メールなし")
        print("受信トレイに未処理のメールはありません。")
        return

    held_ids = set(state.get("held_message_ids", []))

    classified = classify_messages(messages, openai_api_key)
    pending = load_pending()
    pending_ids = {p["message_id"] for p in pending}
    delete_review = load_delete_review()
    delete_review_ids = {r["message_id"] for r in delete_review}

    new_delete_review = 0
    auto_deleted = 0
    new_pending_items = []

    for item in classified:
        m = item["message"]
        need = item["need_reply"]
        reason = item.get("reason", "")
        sender = m["from"]
        has_custom_label = m.get("has_custom_label", False)

        if m["id"] in held_ids:
            continue

        # 学習済み送信者はAI判定に関係なく自動削除（ラベル付きは保護）
        if sender in auto_delete and not has_custom_label:
            trash_message(service, m["id"])
            count_map[sender] = count_map.get(sender, 0) + 1
            auto_deleted += 1
            print(f"  [自動削除] {sender} - {m['subject'][:40]}... (学習済み)")

            if count_map[sender] >= NOT_NEEDED_THRESHOLD:
                if sender not in state.get("blocked_senders", []):
                    if create_block_filter(service, sender):
                        state.setdefault("blocked_senders", []).append(sender)
                        print(f"  → 送信者をブロックしました: {sender}")
            continue

        if has_custom_label and not need:
            need = True
            reason = "ラベル付きのため保護"

        if need:
            if m["id"] not in pending_ids:
                new_item = {
                    "message_id": m["id"],
                    "thread_id": m["thread_id"],
                    "from": m["from"],
                    "subject": m["subject"],
                    "snippet": m["snippet"],
                    "message_id_header": m.get("message_id_header"),
                    "suggested_reply": "",
                    "no_reply_reason": "",
                    "date": m.get("date", ""),
                }
                new_pending_items.append({"message": m, "pending_item": new_item})
                pending_ids.add(m["id"])
            label_mark = " [ラベル付]" if has_custom_label else ""
            print(f"  [返信必要{label_mark}] {sender} - {m['subject'][:40]}...")
        else:
            if m["id"] not in delete_review_ids:
                delete_review.append({
                    "message_id": m["id"],
                    "thread_id": m["thread_id"],
                    "from": m["from"],
                    "subject": m["subject"],
                    "snippet": m["snippet"],
                    "reason": reason,
                    "date": m.get("date", ""),
                })
                delete_review_ids.add(m["id"])
                new_delete_review += 1
            print(f"  [削除確認待ち] {sender} - {m['subject'][:40]}... (理由: {reason})")

    # 新規返信待ちメールの返信案を一括生成
    if new_pending_items:
        print(f"\n返信案を生成中（{len(new_pending_items)} 件）...")
        reply_items = [{"message": npi["message"], "suggested_reply": "", "no_reply_reason": ""} for npi in new_pending_items]
        generate_replies(reply_items, openai_api_key)
        for npi, ri in zip(new_pending_items, reply_items):
            npi["pending_item"]["suggested_reply"] = ri.get("suggested_reply", "")
            npi["pending_item"]["no_reply_reason"] = ri.get("no_reply_reason", "")
        pending.extend([npi["pending_item"] for npi in new_pending_items])

    state["not_needed_count"] = count_map
    save_state(state)
    save_pending(pending)
    save_delete_review(delete_review)

    logger.info("run_once 完了", extra={
        "pending": len(pending), "delete_review": len(delete_review),
        "auto_deleted": auto_deleted, "new_delete_review": new_delete_review,
    })
    print(f"\n完了。返信待ち: {len(pending)} 件 / 削除確認待ち: {len(delete_review)} 件 / 自動削除: {auto_deleted} 件")

    if new_delete_review > 0:
        print(f"\n💡 削除確認が {new_delete_review} 件あります。")
        print("   確認: python3 mail_manager.py review")

    # Slack 通知
    notify_lines = []
    if pending:
        notify_lines.append(f"📬 返信待ち: {len(pending)} 件")
    if delete_review:
        notify_lines.append(f"🗑️ 削除確認待ち: {len(delete_review)} 件")
    if auto_deleted:
        notify_lines.append(f"✅ 自動削除: {auto_deleted} 件")
    if notify_lines:
        send_to_slack("\n".join(notify_lines))

def cmd_approve(account=None):
    """保留中の返信を表示し、承認で送信"""
    pending = load_pending()
    if not pending:
        print("返信待ちのメールはありません。")
        return

    service = get_gmail_service(account)
    # 表示用に元メール情報を保持（send_reply 用に message 形式を復元）
    for i, p in enumerate(pending, 1):
        orig = {
            "from": p["from"],
            "subject": p["subject"],
            "thread_id": p["thread_id"],
            "message_id_header": p.get("message_id_header"),
        }
        print(f"\n--- [{i}] {p['from']} ---")
        print(f"件名: {p['subject']}")
        print(f"内容: {p['snippet'][:200]}...")
        print(f"提案返信: {p.get('suggested_reply', '(なし)')}")
        print("  [y] 送信  [e] 編集  [s] スキップ(保留のまま)  [d] 削除して保留から外す")

    print("\n操作: 番号 + コマンド (例: 1 y, 2 e)")
    line = input("> ").strip()
    if not line:
        return
    parts = line.split(None, 1)
    try:
        idx = int(parts[0])
        cmd = (parts[1] if len(parts) > 1 else "s").lower()
    except (ValueError, IndexError):
        print("例: 1 y")
        return

    if idx < 1 or idx > len(pending):
        print("無効な番号です。")
        return

    p = pending[idx - 1]
    orig = {
        "from": p["from"],
        "subject": p["subject"],
        "thread_id": p["thread_id"],
        "message_id_header": p.get("message_id_header"),
    }

    if cmd == "y":
        if send_reply(service, orig, p.get("suggested_reply", ""), p["from"]):
            print("送信しました。")
            pending.pop(idx - 1)
            save_pending(pending)
        else:
            print("送信に失敗しました。")
    elif cmd == "e":
        reply_text = input("返信文を入力> ").strip()
        if reply_text and send_reply(service, orig, reply_text, p["from"]):
            print("送信しました。")
            pending.pop(idx - 1)
            save_pending(pending)
    elif cmd == "d":
        # ゴミ箱に移動して保留から削除
        try:
            service.users().messages().trash(userId="me", id=p["message_id"]).execute()
        except Exception:
            pass
        pending.pop(idx - 1)
        save_pending(pending)
        print("削除し、保留から外しました。")
    else:
        print("スキップしました。")


def cmd_setup_slack():
    """Slack 連携を対話で設定し、設定を保存してテスト送信する。"""
    ensure_data_dir()
    print("Slack 連携の設定")
    print("  Webhook URL は https://api.slack.com/apps → アプリ → Incoming Webhooks で取得できます。")
    print("")
    url = input("Webhook URL を貼り付けて Enter: ").strip()
    if not url:
        print("URL が空のため中止しました。")
        return
    if not url.startswith("https://hooks.slack.com/"):
        print("警告: 通常 Webhook URL は https://hooks.slack.com/services/... です。")
    ch = input("通知先チャンネル（例: 定常業務。省略可）: ").strip()
    config = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception:
            pass
    config["slack_webhook_url"] = url
    config["slack_channel"] = ch
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"設定を保存しました: {CONFIG_FILE}")
    print("テスト通知を送信します...")
    if send_to_slack("✅ メール受信箱マネージャーと Slack の連携が完了しました。このチャンネルに返信待ち通知が届きます。"):
        print("Slack にテスト通知を送りました。チャンネルを確認してください。")
    else:
        print("テスト送信に失敗しました。URL を確認してください。")


def cmd_slack_test():
    """Slack にテスト通知を1通送る。"""
    if not load_slack_config()["slack_webhook_url"]:
        print("Slack が未設定です。先に python3 mail_manager.py setup-slack を実行してください。")
        return
    if send_to_slack("📬 メール受信箱マネージャーからのテスト通知です。連携は正常です。"):
        print("Slack にテスト通知を送りました。")
    else:
        print("送信に失敗しました。setup-slack で URL を確認してください。")


def cmd_review(account=None):
    """削除確認待ちを表示し、承認で削除＆送信者を学習"""
    delete_review = load_delete_review()
    if not delete_review:
        print("削除確認待ちのメールはありません。")
        return

    state = load_state()
    auto_delete = set(state.get("auto_delete_senders", []))
    count_map = state.get("not_needed_count", {})
    blocked = set(state.get("blocked_senders", []))
    service = get_gmail_service(account)

    print(f"\n削除確認待ち: {len(delete_review)} 件\n")
    print("操作: y=削除して学習 / n=残す / s=スキップ / q=終了\n")

    remaining = []
    for i, item in enumerate(delete_review, 1):
        sender = item["from"]
        current_count = count_map.get(sender, 0)
        print(f"[{i}/{len(delete_review)}] {sender} (削除回数: {current_count})")
        print(f"  件名: {item['subject'][:60]}")
        print(f"  理由: {item.get('reason', '不明')}")
        print(f"  内容: {item['snippet'][:100]}...")
        print()

        while True:
            choice = input("  削除して学習? (y/n/s/q): ").strip().lower()
            if choice == "y":
                trash_message(service, item["message_id"])
                if sender not in auto_delete:
                    auto_delete.add(sender)
                    state["auto_delete_senders"] = list(auto_delete)
                count_map[sender] = count_map.get(sender, 0) + 1
                state["not_needed_count"] = count_map
                save_state(state)
                print(f"  → 削除しました。次回から {sender} は自動削除されます。")

                if count_map[sender] >= NOT_NEEDED_THRESHOLD and sender not in blocked:
                    if create_block_filter(service, sender):
                        blocked.add(sender)
                        state["blocked_senders"] = list(blocked)
                        save_state(state)
                        print(f"  → {NOT_NEEDED_THRESHOLD}回削除のためブロックしました（今後メールが届きません）")
                print()
                break
            elif choice == "n":
                remaining.append(item)
                print("  → 残しました。\n")
                break
            elif choice == "s":
                remaining.append(item)
                print("  → スキップしました。\n")
                break
            elif choice == "q":
                remaining.append(item)
                remaining.extend(delete_review[i:])
                save_delete_review(remaining)
                print(f"\n中断しました。残り: {len(remaining)} 件")
                return
            else:
                print("  y/n/s/q のいずれかを入力してください。")

    save_delete_review(remaining)
    print(f"\n完了。削除確認待ち残り: {len(remaining)} 件")
    print(f"学習済み送信者: {len(auto_delete)} 件")
    print(f"ブロック済み送信者: {len(blocked)} 件")


def cmd_status():
    """状態表示"""
    state = load_state()
    pending = load_pending()
    delete_review = load_delete_review()
    count = state.get("not_needed_count", {})
    blocked = state.get("blocked_senders", [])
    auto_delete = state.get("auto_delete_senders", [])

    print(f"返信待ち: {len(pending)} 件")
    print(f"削除確認待ち: {len(delete_review)} 件")
    print(f"学習済み送信者（自動削除）: {len(auto_delete)} 件")
    print(f"ブロック済み送信者: {len(blocked)} 件")

    if auto_delete:
        print("\n自動削除する送信者:")
        for a in auto_delete[:20]:
            print(f"  - {a}")
        if len(auto_delete) > 20:
            print(f"  ... 他 {len(auto_delete) - 20} 件")

    if blocked:
        print("\nブロック済み:")
        for b in blocked[:10]:
            print(f"  - {b}")
        if len(blocked) > 10:
            print(f"  ... 他 {len(blocked) - 10} 件")


def main():
    global DATA_DIR, STATE_FILE, PENDING_FILE, DELETE_REVIEW_FILE
    args = sys.argv[1:]
    account = None
    if "--account" in args:
        i = args.index("--account")
        account = args[i + 1]
        args = args[:i] + args[i + 2:]

    # アカウント別データディレクトリ（複数アカウントの混在を防ぐ）
    # CONFIG_FILE（Slack/OpenAI設定）はアカウント共通なので変更しない
    effective_account = account or DEFAULT_ACCOUNT
    DATA_DIR = BASE_DIR / "mail_inbox_data" / effective_account
    STATE_FILE = DATA_DIR / "state.json"
    PENDING_FILE = DATA_DIR / "pending.json"
    DELETE_REVIEW_FILE = DATA_DIR / "delete_review.json"

    if not args:
        print(__doc__)
        sys.exit(1)

    cmd = args[0].lower()
    try:
        if cmd == "run":
            run_once(account=account)
        elif cmd == "approve":
            cmd_approve(account=account)
        elif cmd == "review":
            cmd_review(account=account)
        elif cmd == "status":
            cmd_status()
        elif cmd == "setup-slack":
            cmd_setup_slack()
        elif cmd == "slack-test":
            cmd_slack_test()
        else:
            print(f"不明なコマンド: {cmd}")
            print("利用可能: run, approve, review, status, setup-slack, slack-test")
            sys.exit(1)
    except ReauthRequiredError as e:
        print(f"エラー: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
