"""
Slack channel reader for the agent orchestrator.

Reads messages from Slack channels using the Bot Token (Web API).
Used to monitor #ai-team and other channels for AI Secretary awareness.
"""

import json
import os
import urllib.request
from datetime import datetime
from typing import Optional

from .shared_logger import get_logger

logger = get_logger("slack_reader")

_SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_SLACK_API_BASE = "https://slack.com/api"


def _api_call(method: str, params: dict = None) -> Optional[dict]:
    """Call Slack Web API method with Bot Token."""
    if not _SLACK_BOT_TOKEN:
        logger.warning("SLACK_BOT_TOKEN not set — cannot call Slack API")
        return None

    url = f"{_SLACK_API_BASE}/{method}"
    if params:
        query = "&".join(f"{k}={v}" for k, v in params.items() if v is not None)
        url = f"{url}?{query}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {_SLACK_BOT_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if not data.get("ok"):
                logger.error(f"Slack API {method} error: {data.get('error', 'unknown')}")
                return None
            return data
    except Exception as e:
        logger.exception(f"Slack API {method} failed: {e}")
        return None


# --- User cache (user_id -> display_name) ---
_user_cache: dict[str, str] = {}


def _resolve_user(user_id: str) -> str:
    """Resolve Slack user ID to display name (cached)."""
    if user_id in _user_cache:
        return _user_cache[user_id]

    data = _api_call("users.info", {"user": user_id})
    if data and data.get("user"):
        user = data["user"]
        name = user.get("real_name") or user.get("profile", {}).get("display_name") or user.get("name", user_id)
        _user_cache[user_id] = name
        return name

    _user_cache[user_id] = user_id
    return user_id


def fetch_channel_messages(
    channel_id: str,
    oldest: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Fetch recent messages from a Slack channel.

    Args:
        channel_id: Slack channel ID (e.g. C0AGLRJ8N3G)
        oldest: Unix timestamp string — only messages after this time
        limit: Max messages to fetch (default 50)

    Returns:
        List of dicts: [{"user": "名前", "text": "...", "ts": "...", "datetime": "..."}]
    """
    params = {"channel": channel_id, "limit": str(limit)}
    if oldest:
        params["oldest"] = oldest

    data = _api_call("conversations.history", params)
    if not data or "messages" not in data:
        return []

    messages = []
    for msg in reversed(data["messages"]):  # oldest first
        if msg.get("subtype") in ("channel_join", "channel_leave", "bot_add"):
            continue  # skip system messages

        user_id = msg.get("user", "")
        user_name = _resolve_user(user_id) if user_id else msg.get("username", "bot")
        ts = msg.get("ts", "")
        dt = datetime.fromtimestamp(float(ts)).strftime("%H:%M") if ts else ""

        messages.append({
            "user": user_name,
            "user_id": user_id,
            "text": msg.get("text", ""),
            "ts": ts,
            "datetime": dt,
        })

    return messages


def list_channels() -> list[dict]:
    """List all channels the bot is a member of.

    Returns:
        List of dicts: [{"id": "C...", "name": "...", "is_private": bool}]
    """
    channels = []

    # Public channels
    data = _api_call("conversations.list", {"types": "public_channel,private_channel", "limit": "200"})
    if data and "channels" in data:
        for ch in data["channels"]:
            if ch.get("is_member"):
                channels.append({
                    "id": ch["id"],
                    "name": ch.get("name", ""),
                    "is_private": ch.get("is_private", False),
                })

    return channels
