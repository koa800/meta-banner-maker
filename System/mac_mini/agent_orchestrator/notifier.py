"""
Notification dispatcher for the agent orchestrator.

Sends notifications via the Render LINE bot server's /notify endpoint.
The server forwards messages to the secretary LINE group using LINE Messaging API.
"""

import os
import requests
from typing import Optional

from .shared_logger import get_logger

logger = get_logger("notifier")

MAX_MESSAGE_LEN = 990

# Renderサーバー経由でLINE秘書グループに通知
_SERVER_URL = os.environ.get(
    "LINE_BOT_SERVER_URL", "https://line-mention-bot-mmzu.onrender.com"
)
_AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "")


def send_line_notify(message: str, truncate: bool = True) -> bool:
    """Send a message to the LINE secretary group via Render server."""
    if not _AGENT_TOKEN:
        logger.warning("AGENT_TOKEN not set — cannot send LINE notification")
        return False

    if truncate and len(message) > MAX_MESSAGE_LEN:
        message = message[:MAX_MESSAGE_LEN] + "\n...(truncated)"

    try:
        resp = requests.post(
            f"{_SERVER_URL}/notify",
            headers={"Authorization": f"Bearer {_AGENT_TOKEN}"},
            json={"message": message},
            timeout=40,  # Renderのコールドスタート待ち
        )
        if resp.status_code == 200:
            logger.info("LINE notification sent", extra={"length": len(message)})
            return True
        else:
            logger.error(
                "LINE notification failed",
                extra={"status": resp.status_code, "body": resp.text[:200]},
            )
            return False
    except Exception as e:
        logger.exception("LINE notification error", extra={"error": str(e)})
        return False


def notify_repair_proposal(
    branch: str,
    description: str,
    diff_summary: str,
    server_base_url: str = "http://localhost:8500",
) -> bool:
    """Send a repair proposal notification with approve/reject URLs."""
    approve_url = f"{server_base_url}/repair/approve"
    reject_url = f"{server_base_url}/repair/reject"

    diff_preview = diff_summary[:400] if diff_summary else "(no diff)"

    message = (
        f"\n🔧 自動修復提案\n"
        f"ブランチ: {branch}\n"
        f"━━━━━━━━━━━━\n"
        f"{description[:300]}\n"
        f"━━━━━━━━━━━━\n"
        f"変更:\n{diff_preview}\n"
        f"━━━━━━━━━━━━\n"
        f"✅ 承認: {approve_url}\n"
        f"❌ 却下: {reject_url}"
    )
    return send_line_notify(message)


def notify_repair_result(branch: str, action: str, detail: str = "") -> bool:
    """Notify about the result of a repair action (merged/rejected/failed)."""
    emoji = {"merged": "✅", "rejected": "❌", "failed": "⚠️"}.get(action, "ℹ️")
    message = f"\n{emoji} 修復 {action}\nブランチ: {branch}"
    if detail:
        message += f"\n{detail[:300]}"
    return send_line_notify(message)


def notify_error_detected(error_count: int, sample_error: str = "") -> bool:
    """Notify that new errors were detected and repair is starting."""
    message = (
        f"\n⚠️ エラー検出: {error_count}件\n"
        f"自動修復を開始します...\n"
    )
    if sample_error:
        message += f"\n例: {sample_error[:200]}"
    return send_line_notify(message)
