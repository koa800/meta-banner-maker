"""
Notification dispatcher for the agent orchestrator.

Sends notifications via:
- LINE: Render server's /notify endpoint → LINE secretary group
- Slack: Incoming Webhook → #ai-team channel (AI チーム共有)
"""

import json
import os
import re
import urllib.request
from datetime import datetime
from pathlib import Path

import requests

from .shared_logger import get_logger

logger = get_logger("notifier")

MAX_MESSAGE_LEN = 990

DEFAULT_LINE_BOT_SERVER_URL = "https://line-mention-bot-mmzu.onrender.com"
_PROJECT_ROOT = Path(
    os.environ.get("ADDNESS_DEPLOY_ROOT", str(Path(__file__).resolve().parents[3]))
).expanduser().resolve()
_NOTIFICATION_POLICY_PATH = _PROJECT_ROOT / "System" / "config" / "secretary_notification_policy.json"
_DIGEST_QUEUE_PATH = _PROJECT_ROOT / "System" / "data" / "secretary_notification_digest.json"
_notification_policy_cache: dict | None = None

# Slack #ai-team チャネルへの通知
_SLACK_AI_TEAM_WEBHOOK = os.environ.get("SLACK_AI_TEAM_WEBHOOK_URL", "")


def _candidate_line_config_paths() -> list[Path]:
    project_root = Path(
        os.environ.get("ADDNESS_DEPLOY_ROOT", str(Path(__file__).resolve().parents[3]))
    ).expanduser().resolve()
    candidates = [
        project_root / "line_bot_local" / "config.json",
        project_root / "System" / "line_bot_local" / "config.json",
        Path.home() / ".config" / "addness" / "line_config.json",
        Path.home() / "Library" / "LineBot" / "config.json",
        Path.home() / "Desktop" / "cursor" / "System" / "line_bot_local" / "config.json",
    ]
    unique_candidates: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized = str(candidate.expanduser())
        if normalized in seen:
            continue
        seen.add(normalized)
        unique_candidates.append(Path(normalized))
    return unique_candidates


def _read_line_config(path: Path) -> tuple[str, str]:
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return "", ""

    server_url = str(config.get("server_url", "")).strip().rstrip("/")
    agent_token = str(config.get("agent_token", "")).strip()
    return server_url, agent_token


def get_line_notify_config() -> tuple[str, str, str]:
    env_server_url = os.environ.get("LINE_BOT_SERVER_URL", "").strip().rstrip("/")
    env_agent_token = os.environ.get("AGENT_TOKEN", "").strip()

    resolved_server_url = env_server_url
    resolved_agent_token = env_agent_token
    config_source = "env" if (env_server_url or env_agent_token) else "default"

    for candidate in _candidate_line_config_paths():
        if resolved_server_url and resolved_agent_token:
            break
        candidate_server_url, candidate_agent_token = _read_line_config(candidate)
        if not candidate_server_url and not candidate_agent_token:
            continue
        if not resolved_server_url and candidate_server_url:
            resolved_server_url = candidate_server_url
        if not resolved_agent_token and candidate_agent_token:
            resolved_agent_token = candidate_agent_token
        config_source = str(candidate)

    if not resolved_server_url:
        resolved_server_url = DEFAULT_LINE_BOT_SERVER_URL

    return resolved_server_url, resolved_agent_token, config_source


def _load_notification_policy() -> dict:
    global _notification_policy_cache
    if _notification_policy_cache is not None:
        return _notification_policy_cache

    try:
        _notification_policy_cache = json.loads(
            _NOTIFICATION_POLICY_PATH.read_text(encoding="utf-8")
        )
    except Exception as e:
        logger.warning(f"notification policy load failed: {e}")
        _notification_policy_cache = {}
    return _notification_policy_cache


def get_notification_delivery_class(kind: str) -> str:
    policy = _load_notification_policy()
    event_defaults = policy.get("event_defaults", {})
    delivery_class = str(event_defaults.get(kind, "immediate")).strip()
    return delivery_class if delivery_class in {"immediate", "digest", "silent"} else "immediate"


def _load_digest_queue() -> list[dict]:
    try:
        if not _DIGEST_QUEUE_PATH.exists():
            return []
        payload = json.loads(_DIGEST_QUEUE_PATH.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except Exception as e:
        logger.warning(f"digest queue load failed: {e}")
        return []


def _save_digest_queue(events: list[dict]) -> None:
    try:
        _DIGEST_QUEUE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _DIGEST_QUEUE_PATH.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(events, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(_DIGEST_QUEUE_PATH)
    except Exception as e:
        logger.warning(f"digest queue save failed: {e}")


def queue_digest_event(kind: str, message: str, summary: str = "", group_id: str = "") -> bool:
    events = _load_digest_queue()
    resolved_summary = (summary or message).strip().replace("\n", " ")
    resolved_summary = re.sub(r"\s+", " ", resolved_summary)[:200]

    for existing in events:
        if (
            existing.get("kind") == kind
            and existing.get("summary") == resolved_summary
            and existing.get("group_id", "") == group_id
        ):
            logger.info("digest event deduplicated", extra={"kind": kind})
            return True

    events.append(
        {
            "kind": kind,
            "summary": resolved_summary,
            "message": message,
            "group_id": group_id,
            "created_at": datetime.now().isoformat(),
        }
    )
    _save_digest_queue(events)
    logger.info("digest event queued", extra={"kind": kind, "summary": resolved_summary[:80]})
    return True


def flush_digest_events(title: str, kinds: list[str] | None = None, group_id: str = "") -> bool:
    events = _load_digest_queue()
    if not events:
        return True

    selected: list[dict] = []
    remaining: list[dict] = []
    kind_filter = set(kinds or [])
    for event in events:
        event_group_id = str(event.get("group_id", "") or "")
        if event_group_id != group_id:
            remaining.append(event)
            continue
        if kind_filter and event.get("kind") not in kind_filter:
            remaining.append(event)
            continue
        selected.append(event)

    if not selected:
        return True

    lines = [title, ""]
    for event in selected[:12]:
        created_at = str(event.get("created_at", ""))
        hhmm = created_at[11:16] if len(created_at) >= 16 else "--:--"
        lines.append(f"・{hhmm} {event.get('summary', '')}")

    remaining_count = len(selected) - 12
    if remaining_count > 0:
        lines.append(f"・ほか {remaining_count} 件")

    ok = send_line_notify("\n".join(lines), group_id=group_id)
    if ok:
        _save_digest_queue(remaining)
    return ok


def notify_event(
    kind: str,
    message: str,
    summary: str = "",
    truncate: bool = True,
    group_id: str = "",
) -> bool:
    delivery_class = get_notification_delivery_class(kind)
    if delivery_class == "silent":
        logger.info("notification suppressed by policy", extra={"kind": kind})
        return True
    if delivery_class == "digest":
        return queue_digest_event(kind, message=message, summary=summary, group_id=group_id)
    return send_line_notify(message, truncate=truncate, group_id=group_id)


def send_line_notify(message: str, truncate: bool = True, group_id: str = "") -> bool:
    """Send a message to a LINE group via Render server.
    group_id未指定時は秘書グループに送信。"""
    server_url, agent_token, config_source = get_line_notify_config()
    if not agent_token:
        logger.warning(
            "AGENT_TOKEN not set — cannot send LINE notification",
            extra={"config_source": config_source},
        )
        return False

    if truncate and len(message) > MAX_MESSAGE_LEN:
        message = message[:MAX_MESSAGE_LEN] + "\n...(truncated)"

    payload = {"message": message}
    if group_id:
        payload["group_id"] = group_id

    try:
        resp = requests.post(
            f"{server_url}/notify",
            headers={"Authorization": f"Bearer {agent_token}"},
            json=payload,
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


def send_line_notify_with_mention(
    message: str,
    group_id: str,
    user_id: str,
    mention_name: str,
    truncate: bool = True,
) -> bool:
    """LINEグループへ本物メンション付きで通知する。"""
    server_url, agent_token, config_source = get_line_notify_config()
    if not agent_token:
        logger.warning(
            "AGENT_TOKEN not set — cannot send LINE mention notification",
            extra={"config_source": config_source},
        )
        return False

    if truncate and len(message) > MAX_MESSAGE_LEN:
        message = message[:MAX_MESSAGE_LEN] + "\n...(truncated)"

    payload = {
        "message": message,
        "group_id": group_id,
        "user_id": user_id,
        "mention_name": mention_name,
    }

    try:
        resp = requests.post(
            f"{server_url}/notify/mention",
            headers={"Authorization": f"Bearer {agent_token}"},
            json=payload,
            timeout=40,
        )
        if resp.status_code == 200:
            logger.info(
                "LINE mention notification sent",
                extra={"group_id": group_id, "mention_name": mention_name},
            )
            return True
        logger.error(
            "LINE mention notification failed",
            extra={"status": resp.status_code, "body": resp.text[:200]},
        )
        return False
    except Exception as e:
        logger.exception("LINE mention notification error", extra={"error": str(e)})
        return False


def get_line_group_members(group_id: str, name: str = "") -> list[dict]:
    """Render 経由でグループメンバー一覧を取得する。"""
    server_url, agent_token, config_source = get_line_notify_config()
    if not agent_token:
        logger.warning(
            "AGENT_TOKEN not set — cannot fetch LINE group members",
            extra={"config_source": config_source},
        )
        return []

    try:
        resp = requests.get(
            f"{server_url}/api/group-members",
            headers={"Authorization": f"Bearer {agent_token}"},
            params={"group_id": group_id, "name": name},
            timeout=40,
        )
        if resp.status_code != 200:
            logger.error(
                "LINE group members fetch failed",
                extra={"status": resp.status_code, "body": resp.text[:200]},
            )
            return []
        data = resp.json()
        return data.get("members", []) if isinstance(data, dict) else []
    except Exception as e:
        logger.exception("LINE group members fetch error", extra={"error": str(e)})
        return []


def send_slack_ai_team(message: str, truncate: bool = True) -> bool:
    """Send a message to the Slack #ai-team channel via Incoming Webhook."""
    if not _SLACK_AI_TEAM_WEBHOOK:
        logger.debug("SLACK_AI_TEAM_WEBHOOK_URL not set — skipping Slack notification")
        return False

    if truncate and len(message) > 3000:
        message = message[:3000] + "\n...(truncated)"

    payload = json.dumps({
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False,
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            _SLACK_AI_TEAM_WEBHOOK,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            if resp.status == 200:
                logger.info("Slack #ai-team notification sent", extra={"length": len(message)})
                return True
            else:
                logger.error("Slack notification failed", extra={"status": resp.status})
                return False
    except Exception as e:
        logger.exception("Slack notification error", extra={"error": str(e)})
        return False


def notify_ai_team(message: str) -> bool:
    """Send a notification to both LINE secretary group and Slack #ai-team."""
    line_ok = send_line_notify(message)
    slack_ok = send_slack_ai_team(message)
    return line_ok or slack_ok


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
