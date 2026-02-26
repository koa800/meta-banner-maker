"""
Slack通信モジュール（日向エージェント用）

送信専用 — #ai-team への投稿・報告のみ。
Slack監視（受信）はOrchestratorの slack_dispatch タスクが担当し、
hinata_tasks.json 経由で日向に指示を渡す。
"""

import json
import logging
import os
import urllib.request

logger = logging.getLogger("hinata.slack")

# 環境変数から読み込み
_SLACK_WEBHOOK_URL = os.environ.get("SLACK_AI_TEAM_WEBHOOK_URL", "")


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
