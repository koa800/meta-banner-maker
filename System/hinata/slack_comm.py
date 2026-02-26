"""
Slack通信モジュール（日向エージェント用）

- #ai-team への投稿
- 甲原への質問・確認依頼
- 甲原からの返答ポーリング
- 甲原からの指示受信
"""

import json
import logging
import os
import time
import urllib.request
from datetime import datetime
from typing import Optional

logger = logging.getLogger("hinata.slack")

AI_TEAM_CHANNEL = "C0AGLRJ8N3G"

# 環境変数から読み込み
_SLACK_WEBHOOK_URL = os.environ.get("SLACK_AI_TEAM_WEBHOOK_URL", "")
_SLACK_USER_TOKEN = os.environ.get("SLACK_USER_TOKEN", "")
_SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")


def _get_read_token() -> str:
    return _SLACK_USER_TOKEN or _SLACK_BOT_TOKEN


def send_message(text: str) -> bool:
    """#ai-team に日向としてメッセージを送信する。"""
    if not _SLACK_WEBHOOK_URL:
        logger.warning("SLACK_AI_TEAM_WEBHOOK_URL が未設定")
        return False

    if len(text) > 3000:
        text = text[:2990] + "\n... (省略)"

    payload = json.dumps({"text": text}).encode("utf-8")
    try:
        req = urllib.request.Request(
            _SLACK_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            ok = resp.status == 200
            if ok:
                logger.info(f"Slack送信OK: {text[:50]}...")
            return ok
    except Exception as e:
        logger.error(f"Slack送信失敗: {e}")
        return False


def ask_kohara(question: str) -> bool:
    """甲原に確認を求めるメッセージを送信する。"""
    text = f"🙋 *甲原さんに確認*\n\n{question}\n\n_返信をお待ちしています_"
    return send_message(text)


def send_report(title: str, body: str) -> bool:
    """レポートを #ai-team に投稿する。"""
    text = f"📊 *{title}*\n\n{body}"
    return send_message(text)


def fetch_new_messages(after_ts: str) -> list[dict]:
    """
    指定タイムスタンプ以降の新着メッセージを取得する。

    Returns:
        [{"user": "名前", "user_id": "U...", "text": "...", "ts": "..."}]
    """
    token = _get_read_token()
    if not token:
        logger.warning("Slackトークンが未設定")
        return []

    url = (
        f"https://slack.com/api/conversations.history"
        f"?channel={AI_TEAM_CHANNEL}&oldest={after_ts}&limit=20"
    )
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                logger.error(f"Slack API error: {data.get('error')}")
                return []
    except Exception as e:
        logger.error(f"Slack API呼び出し失敗: {e}")
        return []

    messages = []
    for msg in reversed(data.get("messages", [])):
        if msg.get("subtype") in ("channel_join", "channel_leave", "bot_add"):
            continue
        messages.append({
            "user_id": msg.get("user", ""),
            "text": msg.get("text", ""),
            "ts": msg.get("ts", ""),
        })
    return messages


def wait_for_kohara_response(after_ts: str, timeout_minutes: int = 60) -> Optional[str]:
    """
    甲原からの返答を待つ（ポーリング）。

    Args:
        after_ts: この時刻以降のメッセージを待つ
        timeout_minutes: 最大待ち時間（分）

    Returns:
        甲原のメッセージテキスト。タイムアウトならNone。
    """
    deadline = time.time() + (timeout_minutes * 60)

    while time.time() < deadline:
        messages = fetch_new_messages(after_ts)
        for msg in messages:
            # bot以外のメッセージ（= 甲原からのメッセージ）
            if msg["user_id"] and not msg["user_id"].startswith("B"):
                logger.info(f"甲原からの返答を受信: {msg['text'][:50]}...")
                return msg["text"]

        time.sleep(15)  # 15秒ごとにポーリング

    logger.warning(f"甲原からの返答がタイムアウト（{timeout_minutes}分）")
    return None


def check_for_commands(after_ts: str) -> Optional[dict]:
    """
    甲原からの新しい指示を確認する。

    Args:
        after_ts: この時刻以降のメッセージを確認

    Returns:
        {"text": "...", "ts": "...", "command_type": "..."} or None
    """
    messages = fetch_new_messages(after_ts)
    for msg in messages:
        # bot自身のメッセージはスキップ
        if not msg["user_id"] or msg["user_id"].startswith("B"):
            continue

        text = msg["text"].strip()
        if not text:
            continue

        # コマンド種別を判定
        command_type = _classify_command(text)
        logger.info(f"甲原からの指示を受信: [{command_type}] {text[:50]}...")
        return {
            "text": text,
            "ts": msg["ts"],
            "command_type": command_type,
        }

    return None


def _classify_command(text: str) -> str:
    """メッセージからコマンド種別を判定する。"""
    stop_keywords = ["止まって", "ストップ", "止めて", "待って", "やめて"]
    # statusは「状況だけ聞いている」明示的なケースのみ
    status_keywords = ["状況は", "どうなってる", "今何してる", "ステータス"]

    lower = text.lower()
    if any(kw in lower for kw in stop_keywords):
        return "stop"
    if any(kw in lower for kw in status_keywords):
        return "status"
    # それ以外は全て「指示」として Claude Code サイクルを実行
    return "instruction"
