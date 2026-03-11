#!/usr/bin/env python3
from __future__ import annotations

"""
Addness CLI — Codex / 秘書が Addness を直接操作するための入口

主な用途:
    python addness_cli.py search-goals --query "..."                    # ゴール検索
    python addness_cli.py get-goal --goal-id "..."                      # ゴール詳細取得
    python addness_cli.py create-goal --parent-id "..." --title "..."   # 子ゴール作成
    python addness_cli.py update-goal-title --goal-id "..." --title "..."
    python addness_cli.py update-goal-status --goal-id "..." --status completed
    python addness_cli.py update-goal-due-date --goal-id "..." --due-date 2026-03-31
    python addness_cli.py update-goal-description --goal-id "..." --description "..."
    python addness_cli.py list-comments --goal-id "..."
    python addness_cli.py post-comment --goal-id "..." --text "..."
    python addness_cli.py resolve-comment --comment-id "..."
    python addness_cli.py archive-goal --goal-id "..."
    python addness_cli.py delete-goal --goal-id "..." --expected-title "..." --yes
    python addness_cli.py list-ai-threads --goal-id "..."
    python addness_cli.py consult --goal-id "..." --message "..." --purpose brainstorm
    python addness_cli.py smoke-test --headless
"""

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent
SYSTEM_DIR = SCRIPT_DIR.parent
if str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

from addness_feedback_manager import (  # noqa: E402
    ensure_logged_in as ensure_addness_logged_in,
    load_addness_config as load_runtime_addness_config,
    open_context as open_addness_context,
)
from addness_browser import (  # noqa: E402
    check_comments_for_instructions,
    find_my_goal,
    get_goal_info,
)

CONFIG_PATH = SCRIPT_DIR / "config.json"
DEFAULT_AI_MODEL = "gemini-3.1-flash-lite-preview"
DEFAULT_AI_MODE = "hearing_mode"
DEFAULT_AI_TITLE = "新しいチャット"
DEFAULT_AI_TIMEOUT_SECONDS = 60
DEFAULT_SMOKE_TEST_PARENT_ID = "9db003bc-1d6e-4043-bb00-f400c39c760b"
DEFAULT_SAFE_DELETE_PARENT_IDS = (DEFAULT_SMOKE_TEST_PARENT_ID,)
ADDNESS_DATA_DIR = SYSTEM_DIR / "data"
ADDNESS_AUDIT_LOG_PATH = ADDNESS_DATA_DIR / "addness_audit_log.jsonl"
ADDNESS_ACTIVITY_SUMMARY_PATH = ADDNESS_DATA_DIR / "addness_activity_summary_latest.json"
ADDNESS_SMOKE_TEST_REPORT_PATH = ADDNESS_DATA_DIR / "addness_smoke_test_latest.json"

AI_PURPOSE_MAP = {
    "brainstorm": "brainstorm",
    "壁打ち": "brainstorm",
    "completion_criteria": "completion_criteria",
    "完了条件": "completion_criteria",
    "task_breakdown": "task_breakdown",
    "タスク化": "task_breakdown",
    "execution": "execution",
    "実行": "execution",
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
            return json.load(handle)
    return {}


def _ensure_addness_data_dir() -> None:
    ADDNESS_DATA_DIR.mkdir(parents=True, exist_ok=True)


def _append_jsonl(path: Path, payload: dict) -> None:
    _ensure_addness_data_dir()
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _write_json_file(path: Path, payload: dict) -> None:
    _ensure_addness_data_dir()
    tmp_path = path.with_suffix(f"{path.suffix}.tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    tmp_path.replace(path)


def _resolve_smoke_test_parent_id(config: dict) -> str:
    raw = os.environ.get("ADDNESS_SMOKE_TEST_PARENT_ID") or config.get("smoke_test_parent_id") or DEFAULT_SMOKE_TEST_PARENT_ID
    value = str(raw or "").strip()
    if not value:
        raise RuntimeError("smoke_test_parent_id を設定してください")
    return value


def _resolve_safe_delete_parent_ids(config: dict) -> list[str]:
    raw = os.environ.get("ADDNESS_SAFE_DELETE_PARENT_IDS")
    if raw:
        values = [item.strip() for item in raw.split(",")]
    else:
        configured = config.get("safe_delete_parent_ids") or list(DEFAULT_SAFE_DELETE_PARENT_IDS)
        if isinstance(configured, str):
            values = [item.strip() for item in configured.split(",")]
        else:
            values = [str(item).strip() for item in configured]
    return [value for value in values if value]


def _build_goal_url(goal_id: Optional[str] = None, goal_url: Optional[str] = None) -> Optional[str]:
    if goal_url:
        return goal_url
    if goal_id:
        return f"https://www.addness.com/goals/{goal_id}"
    return None


def _goal_id_from_url(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    match = re.search(r"/goals/([0-9a-f-]{36})", value)
    return match.group(1) if match else None


def _add_headless_args(parser) -> None:
    parser.add_argument("--headless", dest="headless", action="store_true", help="headlessで実行")
    parser.add_argument("--headed", dest="headless", action="store_false", help="headありで実行")
    parser.set_defaults(headless=None)


def _open_addness(playwright, config: dict, headless: Optional[bool] = None, target_url: Optional[str] = None, open_my_goal: bool = True):
    if headless is None:
        headless = config.get("headless", True)
    runtime_config = load_runtime_addness_config()
    browser, context, page = open_addness_context(playwright, headless=headless)

    start_url = target_url or config.get("addness_start_url") or runtime_config.get("start_url", "https://www.addness.com")
    timeout_ms = int(config.get("timeout_ms", runtime_config.get("timeout_ms", 60_000)))
    if not ensure_addness_logged_in(page, context, start_url, timeout_ms):
        context.close()
        browser.close()
        return None, None, None

    if target_url:
        page.goto(target_url, wait_until="domcontentloaded", timeout=60_000)
        page.wait_for_timeout(2_000)
        return browser, context, page

    if open_my_goal:
        goal_url = find_my_goal(page, my_goal_url=config.get("my_goal_url"))
        if not goal_url:
            context.close()
            browser.close()
            return None, None, None

    return browser, context, page


def _get_auth_context(page) -> dict:
    auth = page.evaluate(
        """async () => {
            const cookies = Object.fromEntries(
                document.cookie
                    .split('; ')
                    .filter(Boolean)
                    .map((row) => {
                        const idx = row.indexOf('=');
                        if (idx === -1) return [row, ''];
                        return [row.slice(0, idx), row.slice(idx + 1)];
                    })
            );
            const token = await window.Clerk.session.getToken();
            return {
                token,
                userId: window.Clerk.user.id,
                userName: window.Clerk.user.fullName || window.Clerk.user.username || "",
                organizationId: cookies.selectedOrganizationId || '',
            };
        }"""
    )
    if not auth.get("token") or not auth.get("userId") or not auth.get("organizationId"):
        raise RuntimeError("Addness の認証情報を取得できませんでした")
    return auth


def _fetch_result(page, auth: dict, url: str, method: str = "GET", body: Optional[dict] = None) -> dict:
    return page.evaluate(
        """async ({url, method, body, auth}) => {
            const headers = {
                Accept: "*/*",
                Authorization: `Bearer ${auth.token}`,
                "X-Organization-Id": auth.organizationId,
                "X-User-Id": auth.userId,
            };
            if (body !== null) {
                headers["Content-Type"] = "application/json";
            }
            const response = await fetch(url, {
                method,
                headers,
                body: body === null ? undefined : JSON.stringify(body),
            });
            const text = await response.text();
            let json = null;
            try {
                json = JSON.parse(text);
            } catch (_error) {
                json = null;
            }
            return {
                status: response.status,
                ok: response.ok,
                text,
                json,
            };
        }""",
        {"url": url, "method": method, "body": body, "auth": auth},
    )


def _fetch_json(page, auth: dict, url: str, method: str = "GET", body: Optional[dict] = None) -> dict:
    result = _fetch_result(page, auth, url, method=method, body=body)
    if not result.get("ok"):
        raise RuntimeError(f"fetch failed: {method} {url} [{result.get('status')}] {result.get('text', '')[:300]}")
    return result.get("json") or {}


def _fetch_internal_form_result(page, url: str, fields: list[list[str]]) -> dict:
    return page.evaluate(
        """async ({url, fields}) => {
            const form = new FormData();
            for (const [key, value] of fields) {
                form.append(key, value);
            }
            const response = await fetch(url, {
                method: "POST",
                body: form,
            });
            const text = await response.text();
            let json = null;
            try {
                json = JSON.parse(text);
            } catch (_error) {
                json = null;
            }
            return {
                status: response.status,
                ok: response.ok,
                text,
                json,
            };
        }""",
        {"url": url, "fields": fields},
    )


def _unwrap_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload.get("data")
    return payload


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _normalize_due_date(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        raise RuntimeError("due_date が空です")
    if "T" in raw:
        return raw
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            parsed = datetime.strptime(raw, fmt)
            return parsed.strftime("%Y-%m-%dT00:00:00Z")
        except ValueError:
            continue
    raise RuntimeError("due_date は YYYY-MM-DD / YYYY/MM/DD / ISO8601 で指定してください")


def _status_payload_from_input(status: str) -> dict:
    normalized = (status or "").strip().lower()
    if normalized in {"completed", "complete", "done", "完了"}:
        return {"completedAt": _utc_now_iso()}
    if normalized in {"none", "open", "active", "incomplete", "未完了"}:
        return {"completedAt": None}
    return {"status": (status or "").strip().upper()}


def _extract_goal_id(goal_id: Optional[str], goal_url: Optional[str], page=None) -> Optional[str]:
    resolved = goal_id or _goal_id_from_url(goal_url)
    if resolved:
        return resolved
    if page is not None:
        return _goal_id_from_url(page.url)
    return None


def _extract_comment_text(comment: dict) -> str:
    content = comment.get("content")
    if isinstance(content, dict):
        for key in ("text", "body", "content"):
            value = content.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    if isinstance(content, str) and content.strip():
        return content.strip()
    for key in ("text", "body"):
        value = comment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _extract_actor_name(payload: dict) -> str:
    for key in ("author", "createdBy", "organizationMember", "member", "owner", "user"):
        nested = payload.get(key)
        if isinstance(nested, dict):
            name = nested.get("name") or nested.get("displayName") or nested.get("fullName")
            if name:
                return name
    for key in ("authorName", "memberName", "createdByName"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _normalize_comment_item(comment: dict) -> dict:
    return {
        "id": comment.get("id"),
        "text": _extract_comment_text(comment),
        "author": _extract_actor_name(comment),
        "createdAt": comment.get("createdAt"),
        "resolvedAt": comment.get("resolvedAt"),
    }


def _normalize_thread_item(thread: dict) -> dict:
    metadata = thread.get("metadata") or {}
    return {
        "id": thread.get("id"),
        "title": thread.get("title"),
        "status": thread.get("status"),
        "purpose": metadata.get("thread_purpose"),
        "objectiveId": metadata.get("objective_id"),
        "lastMessageAt": thread.get("lastMessageAt"),
        "createdAt": thread.get("createdAt"),
        "updatedAt": thread.get("updatedAt"),
    }


def _extract_thread_goal_id(thread: dict) -> Optional[str]:
    metadata = thread.get("metadata") or {}
    objective_id = metadata.get("objective_id")
    if isinstance(objective_id, str) and objective_id:
        return objective_id
    objective_ids = metadata.get("mentioned_objective_ids") or []
    if isinstance(objective_ids, list) and objective_ids:
        return objective_ids[0]
    return None


def _extract_message_text(message: dict) -> str:
    content = message.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if isinstance(text, str):
            return text
    if isinstance(content, str):
        return content
    return ""


def _normalize_message_item(message: dict) -> dict:
    return {
        "id": message.get("id"),
        "role": message.get("role"),
        "messageIndex": message.get("messageIndex"),
        "text": _extract_message_text(message),
        "createdAt": message.get("createdAt"),
    }


def _goal_snapshot(goal: dict) -> dict:
    return {
        "id": goal.get("id"),
        "title": goal.get("title"),
        "parentId": goal.get("parentId"),
        "status": goal.get("status"),
        "isCompleted": goal.get("isCompleted"),
        "dueDate": goal.get("dueDate"),
        "url": _build_goal_url(goal_id=goal.get("id")),
    }


def _goal_lineage(page, auth: dict, goal: dict) -> list[dict]:
    lineage: list[dict] = []
    current = goal
    visited: set[str] = set()
    while current:
        goal_id = str(current.get("id") or "").strip()
        if not goal_id or goal_id in visited:
            break
        visited.add(goal_id)
        lineage.append(_goal_snapshot(current))
        parent_id = str(current.get("parentId") or "").strip()
        if not parent_id:
            break
        current = _get_goal(page, auth, parent_id)
    lineage.reverse()
    return lineage


def _goal_is_under_parent(lineage: list[dict], allowed_parent_ids: list[str]) -> bool:
    allowed = set(allowed_parent_ids)
    if not allowed or len(lineage) <= 1:
        return False
    return any(item.get("id") in allowed for item in lineage[:-1])


def _lineage_titles(lineage: list[dict]) -> list[str]:
    return [item.get("title") or item.get("id") or "" for item in lineage]


def _write_audit_log(
    command_name: str,
    auth: dict,
    *,
    goal_id: Optional[str] = None,
    goal_title: Optional[str] = None,
    status: str = "success",
    details: Optional[dict] = None,
) -> None:
    try:
        _append_jsonl(
            ADDNESS_AUDIT_LOG_PATH,
            {
                "occurredAt": _utc_now_iso(),
                "command": command_name,
                "status": status,
                "organizationId": auth.get("organizationId"),
                "userId": auth.get("userId"),
                "userName": auth.get("userName"),
                "goalId": goal_id,
                "goalTitle": goal_title,
                "details": details or {},
            },
        )
    except Exception:
        pass


def _assert_delete_goal_guard(args, goal: dict, lineage: list[dict], safe_parent_ids: list[str]) -> dict:
    if not args.yes:
        raise RuntimeError("delete-goal は --yes が必要です")

    actual_title = str(goal.get("title") or "").strip()
    expected_title = str(getattr(args, "expected_title", "") or "").strip()
    if not expected_title:
        raise RuntimeError("delete-goal は --expected-title が必要です")
    if expected_title != actual_title:
        raise RuntimeError(f"delete-goal の title 確認に失敗しました: actual='{actual_title}' expected='{expected_title}'")

    actual_parent_id = str(goal.get("parentId") or "").strip()
    expected_parent_id = str(getattr(args, "expected_parent_id", "") or "").strip()
    if expected_parent_id and expected_parent_id != actual_parent_id:
        raise RuntimeError(
            f"delete-goal の parent 確認に失敗しました: actual='{actual_parent_id}' expected='{expected_parent_id}'"
        )

    under_safe_parent = _goal_is_under_parent(lineage, safe_parent_ids)
    if not under_safe_parent and not getattr(args, "allow_non_test_goal", False):
        raise RuntimeError("delete-goal はテスト配下のみ既定で許可します。必要なら --allow-non-test-goal を付けてください")

    return {
        "expected_title": expected_title,
        "actual_title": actual_title,
        "expected_parent_id": expected_parent_id or None,
        "actual_parent_id": actual_parent_id or None,
        "safe_parent_ids": safe_parent_ids,
        "under_safe_parent": under_safe_parent,
        "lineage": lineage,
    }


def _get_goal(page, auth: dict, goal_id: str) -> dict:
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{goal_id}")
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _get_current_member(page, auth: dict) -> dict:
    payload = _fetch_json(
        page,
        auth,
        f"https://vt.api.addness.com/api/v1/team/organizations/{auth['organizationId']}/current_member",
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _search_goals(page, auth: dict, query: str, limit: int = 20) -> list[dict]:
    params = urlencode(
        {
            "q": query,
            "organizationId": auth["organizationId"],
            "limit": limit,
        }
    )
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v1/team/search?{params}")
    items = ((_unwrap_data(payload) or {}).get("items")) or []
    return [item.get("data", {}) for item in items if item.get("type") == "objective" and item.get("data")]


def _get_member_activity(page, auth: dict, member_id: str, limit: int = 100, offset: int = 0) -> dict:
    params = urlencode({"member_id": member_id, "limit": limit, "offset": offset})
    payload = _fetch_json(
        page,
        auth,
        f"https://vt.api.addness.com/api/v1/team/organizations/{auth['organizationId']}/activity-logs/by-member?{params}",
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _get_goal_children(page, auth: dict, goal_id: str, limit: int = 100, offset: int = 0) -> list[dict]:
    params = urlencode({"limit": limit, "offset": offset})
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{goal_id}/children?{params}")
    data = _unwrap_data(payload)
    if not isinstance(data, dict):
        return []
    return data.get("children") or []


def _create_goal(page, auth: dict, parent_id: str, title: str) -> dict:
    children = _get_goal_children(page, auth, parent_id, limit=100)
    next_order_no = max((child.get("orderNo") or 0) for child in children) + 1 if children else 1
    payload = _fetch_json(
        page,
        auth,
        "https://vt.api.addness.com/api/v2/objectives",
        method="POST",
        body={
            "organizationId": auth["organizationId"],
            "parentObjectiveId": parent_id,
            "title": title,
            "orderNo": next_order_no,
        },
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _update_goal_v2(page, auth: dict, goal_id: str, update_payload: dict) -> dict:
    payload = _fetch_json(
        page,
        auth,
        f"https://vt.api.addness.com/api/v2/objectives/{goal_id}",
        method="PATCH",
        body=update_payload,
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _update_goal_description(page, auth: dict, goal_id: str, description: str) -> dict:
    payload = _fetch_json(
        page,
        auth,
        f"https://vt.api.addness.com/api/v1/team/objectives/{goal_id}",
        method="PATCH",
        body={"description": description},
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _list_goal_comments(page, auth: dict, goal_id: str, resolved: bool = False, limit: int = 20, offset: int = 0, sort: str = "desc") -> dict:
    params = urlencode(
        {
            "resolved": "true" if resolved else "false",
            "limit": limit,
            "offset": offset,
            "sort": sort,
        }
    )
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{goal_id}/comments?{params}")
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _create_comment(page, auth: dict, goal_id: str, text: str) -> dict:
    payload = _fetch_json(
        page,
        auth,
        "https://vt.api.addness.com/api/v1/team/comments",
        method="POST",
        body={
            "commentableType": "objective",
            "commentableId": goal_id,
            "content": text,
            "mentions": [],
            "files": [],
        },
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _resolve_comment(page, auth: dict, comment_id: str) -> dict:
    payload = _fetch_json(
        page,
        auth,
        f"https://vt.api.addness.com/api/v1/team/comments/{comment_id}/resolve",
        method="PATCH",
        body=None,
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _delete_comment(page, auth: dict, comment_id: str) -> dict:
    return _fetch_result(
        page,
        auth,
        f"https://vt.api.addness.com/api/v1/team/comments/{comment_id}",
        method="DELETE",
        body=None,
    )


def _archive_goal(page, auth: dict, goal_id: str) -> dict:
    return _fetch_result(
        page,
        auth,
        "https://vt.api.addness.com/api/v2/objectives/archive",
        method="POST",
        body={"objectiveIds": [goal_id]},
    )


def _delete_goal(page, auth: dict, goal_id: str) -> dict:
    return _fetch_result(
        page,
        auth,
        "https://vt.api.addness.com/api/v2/objectives/delete",
        method="DELETE",
        body={"objectiveIds": [goal_id]},
    )


def _normalize_ai_purpose(purpose: str) -> str:
    resolved = AI_PURPOSE_MAP.get((purpose or "").strip(), "")
    if resolved:
        return resolved
    normalized = (purpose or "").strip().lower()
    if normalized in AI_PURPOSE_MAP:
        return AI_PURPOSE_MAP[normalized]
    raise RuntimeError("purpose は brainstorm / completion_criteria / task_breakdown / execution を使ってください")


def _list_ai_threads(page, auth: dict, goal_id: str, limit: int = 20, offset: int = 0) -> dict:
    params = urlencode(
        {
            "limit": limit,
            "offset": offset,
            "objectiveId": goal_id,
            "threadScope": "objective",
        }
    )
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v1/team/ai/threads?{params}")
    return payload if isinstance(payload, dict) else {}


def _get_ai_thread(page, auth: dict, thread_id: str) -> dict:
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v1/team/ai/threads/{thread_id}")
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _get_ai_thread_messages(page, auth: dict, thread_id: str, limit: int = 1000) -> dict:
    payload = _fetch_json(page, auth, f"https://vt.api.addness.com/api/v1/team/ai/threads/{thread_id}/messages?limit={limit}")
    return payload if isinstance(payload, dict) else {}


def _create_ai_thread(page, auth: dict, goal_id: str, purpose: str, title: str = DEFAULT_AI_TITLE) -> dict:
    payload = _fetch_json(
        page,
        auth,
        "https://vt.api.addness.com/api/v1/team/ai/threads",
        method="POST",
        body={
            "title": title,
            "metadata": {
                "objective_id": goal_id,
                "thread_scope": "objective",
                "thread_origin": "goal_detail",
                "thread_purpose": _normalize_ai_purpose(purpose),
            },
        },
    )
    data = _unwrap_data(payload)
    return data if isinstance(data, dict) else {}


def _send_ai_chat_message(page, thread_id: str, message: str, goal_id: str, model: str = DEFAULT_AI_MODEL, mode: str = DEFAULT_AI_MODE) -> dict:
    fields = [
        ["message", message],
        ["mode", mode],
        ["model", model],
        ["mentionedObjectiveIds", json.dumps([goal_id], ensure_ascii=False)],
        ["mentionedMemberIds", "[]"],
        ["mentionedSkillIds", "[]"],
        ["userLocalTime", _utc_now_iso()],
        ["timezone", "Asia/Tokyo"],
    ]
    return _fetch_internal_form_result(page, f"/api/ai/threads/{thread_id}/chat", fields)


def _wait_for_ai_assistant_message(page, auth: dict, thread_id: str, after_message_index: int, user_text: str, timeout_seconds: int) -> Optional[dict]:
    latest_payload = {}
    for _ in range(timeout_seconds):
        latest_payload = _get_ai_thread_messages(page, auth, thread_id, limit=1000)
        messages = latest_payload.get("messages") or []
        latest_user_index = after_message_index
        for message in messages:
            if message.get("role") != "user":
                continue
            message_index = int(message.get("messageIndex") or 0)
            if message_index <= after_message_index:
                continue
            if user_text and _extract_message_text(message) != user_text:
                continue
            latest_user_index = max(latest_user_index, message_index)
        assistants = [
            message
            for message in messages
            if message.get("role") == "assistant" and int(message.get("messageIndex") or 0) > latest_user_index
        ]
        if assistants:
            return assistants[-1]
        page.wait_for_timeout(1_000)
    return None


def _summarize_activity(items: list[dict]) -> dict:
    event_type_counts = Counter(item.get("eventType") or "unknown" for item in items)
    event_category_counts = Counter(item.get("eventCategory") or "unknown" for item in items)
    priority_map = {
        "objective.created": {"operation": "create_goal", "guardrail": "safe_write"},
        "objective.title_updated": {"operation": "update_goal_title", "guardrail": "safe_write"},
        "objective.status_changed": {"operation": "update_goal_status", "guardrail": "safe_write"},
        "objective.due_date_changed": {"operation": "update_goal_due_date", "guardrail": "safe_write"},
        "objective.relation_changed": {"operation": "reparent_goal", "guardrail": "safe_write"},
        "objective.archived": {"operation": "archive_goal", "guardrail": "reversible_write"},
        "objective.deleted": {"operation": "delete_goal", "guardrail": "explicit_confirmation_required"},
        "comment.created": {"operation": "post_comment", "guardrail": "safe_write"},
        "comment.resolved": {"operation": "resolve_comment", "guardrail": "safe_write"},
        "comment.deleted": {"operation": "delete_comment", "guardrail": "explicit_confirmation_required"},
        "ai.session_started": {"operation": "start_ai_session", "guardrail": "cost_care"},
        "ai.message_sent": {"operation": "send_ai_message", "guardrail": "cost_care"},
    }

    priority_operations = []
    for event_type, count in event_type_counts.most_common(20):
        mapped = priority_map.get(event_type)
        if not mapped:
            continue
        priority_operations.append(
            {
                "eventType": event_type,
                "count": count,
                "operation": mapped["operation"],
                "guardrail": mapped["guardrail"],
            }
        )

    samples = [
        {
            "occurredAt": item.get("occurredAt"),
            "eventType": item.get("eventType"),
            "description": item.get("description"),
            "goalId": (item.get("goalInfo") or {}).get("goalId"),
            "goalTitle": (item.get("goalInfo") or {}).get("goalTitle"),
        }
        for item in items[:20]
    ]
    return {
        "eventTypeCounts": [
            {"eventType": event_type, "count": count}
            for event_type, count in event_type_counts.most_common(20)
        ],
        "eventCategoryCounts": [
            {"eventCategory": event_category, "count": count}
            for event_category, count in event_category_counts.most_common(20)
        ],
        "priorityOperations": priority_operations,
        "samples": samples,
    }


def _append_smoke_step(report: dict, name: str, success: bool, **details) -> None:
    report.setdefault("steps", []).append({"name": name, "success": success, **details})


def _run_smoke_test(page, auth: dict, parent_id: str, timeout_seconds: int, keep_artifacts: bool, safe_parent_ids: list[str]) -> dict:
    parent = _get_goal(page, auth, parent_id)
    parent_lineage = _goal_lineage(page, auth, parent)
    if parent_id not in safe_parent_ids and not _goal_is_under_parent(parent_lineage, safe_parent_ids):
        raise RuntimeError("smoke-test は safe delete parent 配下でのみ実行します")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    due_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    base_title = f"TEST_AddnessSmoke_{timestamp}"
    archive_title = f"{base_title}_archive"
    description = f"完了の基準 smoke test {timestamp}"
    comment_text = f"smoke comment {timestamp}"
    ai_message = "接続確認です。20文字以内で返答してください。"

    report = {
        "success": False,
        "executedAt": _utc_now_iso(),
        "parent": _goal_snapshot(parent),
        "parentLineage": parent_lineage,
        "steps": [],
        "cleanup": {},
    }

    created_goal_id: Optional[str] = None
    archive_goal_id: Optional[str] = None
    created_comment_id: Optional[str] = None

    try:
        created = _create_goal(page, auth, parent_id, base_title)
        created_goal_id = created.get("id")
        if not created_goal_id:
            raise RuntimeError("smoke-test で goal_id を取得できませんでした")
        created_goal = _get_goal(page, auth, created_goal_id)
        _append_smoke_step(report, "create_goal", True, goal=_goal_snapshot(created_goal))

        renamed_title = f"{base_title}_renamed"
        renamed_goal = _update_goal_v2(page, auth, created_goal_id, {"title": renamed_title})
        _append_smoke_step(report, "update_goal_title", True, after_title=renamed_goal.get("title"))

        _update_goal_v2(page, auth, created_goal_id, {"dueDate": _normalize_due_date(due_date)})
        due_goal = _get_goal(page, auth, created_goal_id)
        _append_smoke_step(report, "update_goal_due_date", True, dueDate=due_goal.get("dueDate"))

        _update_goal_description(page, auth, created_goal_id, description)
        described_goal = _get_goal(page, auth, created_goal_id)
        _append_smoke_step(report, "update_goal_description", True, description=described_goal.get("description"))

        _update_goal_v2(page, auth, created_goal_id, _status_payload_from_input("completed"))
        completed_goal = _get_goal(page, auth, created_goal_id)
        _append_smoke_step(report, "update_goal_status_completed", True, isCompleted=completed_goal.get("isCompleted"))

        _update_goal_v2(page, auth, created_goal_id, _status_payload_from_input("none"))
        reopened_goal = _get_goal(page, auth, created_goal_id)
        _append_smoke_step(report, "update_goal_status_open", True, isCompleted=reopened_goal.get("isCompleted"))

        comment = _create_comment(page, auth, created_goal_id, comment_text)
        created_comment_id = comment.get("id")
        _append_smoke_step(report, "post_comment", True, comment=_normalize_comment_item(comment))

        if not created_comment_id:
            raise RuntimeError("smoke-test の comment_id を取得できませんでした")
        _resolve_comment(page, auth, created_comment_id)
        _append_smoke_step(report, "resolve_comment", True, comment_id=created_comment_id)

        delete_comment_result = _delete_comment(page, auth, created_comment_id)
        _append_smoke_step(
            report,
            "delete_comment",
            delete_comment_result.get("ok", False),
            comment_id=created_comment_id,
            status=delete_comment_result.get("status"),
        )
        if not delete_comment_result.get("ok", False):
            raise RuntimeError(f"smoke-test の comment delete に失敗しました [{delete_comment_result.get('status')}]")

        archive_goal = _create_goal(page, auth, parent_id, archive_title)
        archive_goal_id = archive_goal.get("id")
        if not archive_goal_id:
            raise RuntimeError("smoke-test の archive goal_id を取得できませんでした")
        archive_result = _archive_goal(page, auth, archive_goal_id)
        archive_check = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{archive_goal_id}")
        archived = archive_result.get("ok", False) and archive_check.get("status") == 404
        _append_smoke_step(
            report,
            "archive_goal",
            archived,
            goal_id=archive_goal_id,
            archive_status=archive_result.get("status"),
            after_get_status=archive_check.get("status"),
        )
        if not archived:
            raise RuntimeError("smoke-test の archive_goal に失敗しました")

        thread = _create_ai_thread(page, auth, created_goal_id, "brainstorm", title=f"{base_title}_ai")
        thread_id = thread.get("id")
        if not thread_id:
            raise RuntimeError("smoke-test の thread_id を取得できませんでした")
        _append_smoke_step(report, "start_ai_session", True, thread_id=thread_id)

        before_payload = _get_ai_thread_messages(page, auth, thread_id, limit=1000)
        before_messages = before_payload.get("messages") or []
        max_index = max((int(message.get("messageIndex") or 0) for message in before_messages), default=0)
        send_result = _send_ai_chat_message(page, thread_id, ai_message, created_goal_id)
        if not send_result.get("ok"):
            raise RuntimeError(f"smoke-test の AI送信に失敗しました [{send_result.get('status')}]")
        assistant = _wait_for_ai_assistant_message(
            page,
            auth,
            thread_id,
            after_message_index=max_index,
            user_text=ai_message,
            timeout_seconds=timeout_seconds,
        )
        ai_success = assistant is not None and bool(_extract_message_text(assistant).strip())
        _append_smoke_step(
            report,
            "send_ai_message",
            ai_success,
            thread_id=thread_id,
            response=_extract_message_text(assistant) if assistant else "",
        )
        if not ai_success:
            raise RuntimeError("smoke-test の AI応答待ちに失敗しました")

        report["success"] = True
        return report
    except Exception as error:
        report["error"] = str(error)
        return report
    finally:
        cleanup = report.setdefault("cleanup", {})
        if archive_goal_id:
            cleanup["archive_goal_id"] = archive_goal_id
            cleanup["archive_goal_kept_archived"] = True
        if created_comment_id:
            cleanup["comment_id"] = created_comment_id
        if created_goal_id:
            cleanup["goal_id"] = created_goal_id
            if keep_artifacts:
                cleanup["goal_deleted"] = False
                cleanup["kept_for_debug"] = True
            else:
                delete_result = _delete_goal(page, auth, created_goal_id)
                after_check = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{created_goal_id}")
                cleanup["goal_deleted"] = delete_result.get("ok", False) and after_check.get("status") == 404
                cleanup["delete_status"] = delete_result.get("status")
                cleanup["after_get_status"] = after_check.get("status")


def _open_parent_change_dialog(page) -> None:
    page.evaluate(
        """() => {
            const triggers = Array.from(document.querySelectorAll('button[data-slot="dropdown-menu-trigger"]'))
                .filter((el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && rect.y < 200
                        && style.visibility !== "hidden"
                        && style.display !== "none";
                })
                .sort((a, b) => b.getBoundingClientRect().x - a.getBoundingClientRect().x);
            if (!triggers.length) {
                throw new Error("親ゴール変更メニューのトリガーが見つかりません");
            }
            triggers[0].click();
        }"""
    )
    page.wait_for_timeout(1_000)
    page.get_by_role("menuitem", name="親ゴールの変更").click()
    page.wait_for_timeout(1_000)


def _capture_reparent_action_headers(page, goal_id: str, capture_queries: list[str]) -> dict:
    for query in capture_queries:
        page.evaluate(
            """(goalId) => {
                window.__addnessReqLog = [];
                const originalFetch = window.fetch.bind(window);
                window.fetch = async (...args) => {
                    const [input, init] = args;
                    const url = typeof input === "string" ? input : input.url;
                    const method = (init && init.method) || "GET";
                    const body = init && init.body ? String(init.body) : null;
                    let headers = {};
                    try {
                        headers = init && init.headers
                            ? Object.fromEntries(new Headers(init.headers).entries())
                            : {};
                    } catch (_error) {
                        headers = {};
                    }
                    window.__addnessReqLog.push({ method, url, body, headers });
                    if (method === "POST" && typeof url === "string" && url === `/goals/${goalId}`) {
                        throw new Error("blocked for header capture");
                    }
                    return originalFetch(...args);
                };
            }""",
            goal_id,
        )
        _open_parent_change_dialog(page)
        search_input = page.locator('input[placeholder="ゴールを検索"]').first
        search_input.click()
        search_input.fill(query)
        page.wait_for_timeout(2_000)
        options = page.locator('[role="option"]')
        if options.count() == 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            continue

        options.first.click()
        page.wait_for_timeout(500)
        page.get_by_role("button", name="変更する").click()
        page.wait_for_timeout(1_500)
        logs = page.evaluate("window.__addnessReqLog || []")
        for log in reversed(logs):
            if log.get("method") == "POST" and log.get("url") == f"/goals/{goal_id}":
                headers = log.get("headers") or {}
                next_action = headers.get("next-action")
                router_state = headers.get("next-router-state-tree")
                if next_action and router_state:
                    return {
                        "next_action": next_action,
                        "router_state": router_state,
                    }
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    raise RuntimeError("親ゴール変更の server action ヘッダーを取得できませんでした")


def _reparent_goal(page, goal_id: str, new_parent_id: str) -> dict:
    action_headers = _capture_reparent_action_headers(page, goal_id, ["スキル", "アドネス", "定常", "信頼"])
    return page.evaluate(
        """async ({goalId, newParentId, nextAction, routerState}) => {
            const response = await fetch(`/goals/${goalId}`, {
                method: "POST",
                headers: {
                    Accept: "text/x-component",
                    "Next-Action": nextAction,
                    "Next-Router-State-Tree": routerState,
                    "Content-Type": "text/plain;charset=UTF-8",
                },
                body: JSON.stringify([goalId, { newParentObjectiveId: newParentId }]),
            });
            return {
                status: response.status,
                text: await response.text(),
            };
        }""",
        {
            "goalId": goal_id,
            "newParentId": new_parent_id,
            "nextAction": action_headers["next_action"],
            "routerState": action_headers["router_state"],
        },
    )


def cmd_login(_args) -> None:
    config = load_config()
    print("=" * 50)
    print("Addness の初回ログイン")
    print("ブラウザが開きます。Googleアカウントでログインしてください。")
    print("=" * 50)

    with sync_playwright() as playwright:
        runtime_config = load_runtime_addness_config()
        browser, context, page = open_addness_context(playwright, headless=False)
        start_url = config.get("addness_start_url") or runtime_config.get("start_url", "https://www.addness.com")
        timeout_ms = int(config.get("timeout_ms", runtime_config.get("timeout_ms", 300_000)))
        if ensure_addness_logged_in(page, context, start_url, timeout_ms):
            print("\nログイン成功。セッションを保存しました。")
        else:
            print("\nログインに失敗しました。再度実行してください。")
        context.close()
        browser.close()


def cmd_check_comments(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            instruction = check_comments_for_instructions(page)
            print(json.dumps({"instruction": instruction or ""}, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_get_goal_info(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            info = get_goal_info(page)
            print(json.dumps(info, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_search_goals(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            goals = _search_goals(page, auth, args.query, limit=args.limit)
            result = [
                {
                    "id": goal.get("id"),
                    "title": goal.get("title"),
                    "status": goal.get("status"),
                    "parentObjectiveId": goal.get("parentObjectiveId"),
                    "breadcrumb": goal.get("breadcrumb", []),
                }
                for goal in goals
            ]
            print(json.dumps({"query": args.query, "items": result}, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_get_goal(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(
            playwright,
            config,
            headless=args.headless,
            target_url=_build_goal_url(goal_id=args.goal_id),
            open_my_goal=False,
        )
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            goal = _get_goal(page, auth, args.goal_id)
            print(json.dumps(goal, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_create_goal(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            parent = _get_goal(page, auth, args.parent_id)
            created = _create_goal(page, auth, args.parent_id, args.title)
            goal_id = created.get("id")
            if not goal_id:
                raise RuntimeError("作成したゴールIDを取得できませんでした")
            if args.due_date:
                _update_goal_v2(page, auth, goal_id, {"dueDate": _normalize_due_date(args.due_date)})
            if args.description is not None:
                _update_goal_description(page, auth, goal_id, args.description)
            if args.status:
                _update_goal_v2(page, auth, goal_id, _status_payload_from_input(args.status))
            after = _get_goal(page, auth, goal_id)
            payload = {
                "goal_id": goal_id,
                "title": after.get("title"),
                "parent_id": after.get("parentId"),
                "parent_title": parent.get("title"),
                "dueDate": after.get("dueDate"),
                "description": after.get("description"),
                "isCompleted": after.get("isCompleted"),
                "url": _build_goal_url(goal_id=goal_id),
            }
            _write_audit_log("create_goal", auth, goal_id=goal_id, goal_title=after.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_update_goal_title(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before = _get_goal(page, auth, args.goal_id)
            after = _update_goal_v2(page, auth, args.goal_id, {"title": args.title})
            payload = {
                "goal_id": args.goal_id,
                "before_title": before.get("title"),
                "after_title": after.get("title"),
            }
            _write_audit_log("update_goal_title", auth, goal_id=args.goal_id, goal_title=after.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_update_goal_status(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before = _get_goal(page, auth, args.goal_id)
            _update_goal_v2(page, auth, args.goal_id, _status_payload_from_input(args.status))
            after = _get_goal(page, auth, args.goal_id)
            payload = {
                "goal_id": args.goal_id,
                "status_input": args.status,
                "before_isCompleted": before.get("isCompleted"),
                "after_isCompleted": after.get("isCompleted"),
                "completedAt": after.get("completedAt"),
                "status": after.get("status"),
            }
            _write_audit_log("update_goal_status", auth, goal_id=args.goal_id, goal_title=after.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_update_goal_due_date(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before = _get_goal(page, auth, args.goal_id)
            after = _update_goal_v2(page, auth, args.goal_id, {"dueDate": _normalize_due_date(args.due_date)})
            payload = {
                "goal_id": args.goal_id,
                "before_dueDate": before.get("dueDate"),
                "after_dueDate": after.get("dueDate"),
            }
            _write_audit_log("update_goal_due_date", auth, goal_id=args.goal_id, goal_title=before.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_update_goal_description(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before = _get_goal(page, auth, args.goal_id)
            _update_goal_description(page, auth, args.goal_id, args.description)
            after = _get_goal(page, auth, args.goal_id)
            payload = {
                "goal_id": args.goal_id,
                "before_description": before.get("description"),
                "after_description": after.get("description"),
            }
            _write_audit_log("update_goal_description", auth, goal_id=args.goal_id, goal_title=after.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_reparent_goal(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(
            playwright,
            config,
            headless=args.headless,
            target_url=_build_goal_url(goal_id=args.goal_id),
            open_my_goal=False,
        )
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before = _get_goal(page, auth, args.goal_id)
            action = _reparent_goal(page, args.goal_id, args.new_parent_id)
            page.wait_for_timeout(3_500)
            after = _get_goal(page, auth, args.goal_id)
            new_parent = _get_goal(page, auth, args.new_parent_id)
            payload = {
                "goal_id": args.goal_id,
                "goal_title": after.get("title"),
                "before_parent_id": before.get("parentId"),
                "after_parent_id": after.get("parentId"),
                "new_parent_id": args.new_parent_id,
                "new_parent_title": new_parent.get("title"),
                "success": after.get("parentId") == args.new_parent_id,
                "action_status": action.get("status"),
            }
            _write_audit_log("reparent_goal", auth, goal_id=args.goal_id, goal_title=after.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_list_comments(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            payload = _list_goal_comments(page, auth, args.goal_id, resolved=args.resolved, limit=args.limit, offset=args.offset, sort=args.sort)
            comments = payload.get("comments") or []
            print(
                json.dumps(
                    {
                        "goal_id": args.goal_id,
                        "resolved": args.resolved,
                        "totalCount": payload.get("totalCount", len(comments)),
                        "items": [_normalize_comment_item(comment) for comment in comments],
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            context.close()
            browser.close()


def cmd_post_comment(args) -> None:
    config = load_config()
    target_url = _build_goal_url(goal_id=args.goal_id, goal_url=args.goal_url)
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(
            playwright,
            config,
            headless=args.headless,
            target_url=target_url,
            open_my_goal=target_url is None,
        )
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            goal_id = _extract_goal_id(args.goal_id, args.goal_url, page=page)
            if not goal_id:
                raise RuntimeError("投稿先の goal_id を特定できませんでした")
            created = _create_comment(page, auth, goal_id, args.text)
            goal = _get_goal(page, auth, goal_id)
            payload = {
                "success": True,
                "goal_id": goal_id,
                "goal_title": goal.get("title"),
                "goal_url": _build_goal_url(goal_id=goal_id),
                "comment": _normalize_comment_item(created) if created else None,
            }
            _write_audit_log("post_comment", auth, goal_id=goal_id, goal_title=goal.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_resolve_comment(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            resolved = _resolve_comment(page, auth, args.comment_id)
            payload = {"comment_id": args.comment_id, "result": resolved or {"resolved": True}}
            _write_audit_log("resolve_comment", auth, details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_delete_comment(args) -> None:
    if not args.yes:
        print(json.dumps({"error": "delete-comment は --yes が必要です"}, ensure_ascii=False))
        sys.exit(1)
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            result = _delete_comment(page, auth, args.comment_id)
            payload = {
                "comment_id": args.comment_id,
                "deleted": result.get("ok", False),
                "status": result.get("status"),
            }
            _write_audit_log("delete_comment", auth, status="success" if payload["deleted"] else "error", details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_archive_goal(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before_result = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{args.goal_id}")
            before_payload = before_result.get("json") or {}
            before = _unwrap_data(before_payload) if before_result.get("ok") else {}
            result = _archive_goal(page, auth, args.goal_id)
            after_check = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{args.goal_id}")
            payload = {
                "goal_id": args.goal_id,
                "goal_title": before.get("title"),
                "archived": result.get("ok", False) and after_check.get("status") == 404,
                "archive_status": result.get("status"),
                "after_get_status": after_check.get("status"),
            }
            _write_audit_log(
                "archive_goal",
                auth,
                goal_id=args.goal_id,
                goal_title=before.get("title"),
                status="success" if payload["archived"] else "error",
                details=payload,
            )
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_delete_goal(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            before_result = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{args.goal_id}")
            before_payload = before_result.get("json") or {}
            before = _unwrap_data(before_payload) if before_result.get("ok") else {}
            lineage = _goal_lineage(page, auth, before) if before else []
            safe_parent_ids = _resolve_safe_delete_parent_ids(config)
            try:
                guard = _assert_delete_goal_guard(args, before, lineage, safe_parent_ids)
            except Exception as error:
                payload = {
                    "goal_id": args.goal_id,
                    "goal_title": before.get("title"),
                    "goal_parent_id": before.get("parentId"),
                    "lineage_titles": _lineage_titles(lineage),
                    "error": str(error),
                }
                _write_audit_log(
                    "delete_goal",
                    auth,
                    goal_id=args.goal_id,
                    goal_title=before.get("title"),
                    status="blocked",
                    details=payload,
                )
                print(json.dumps(payload, ensure_ascii=False))
                sys.exit(1)
            result = _delete_goal(page, auth, args.goal_id)
            after_check = _fetch_result(page, auth, f"https://vt.api.addness.com/api/v2/objectives/{args.goal_id}")
            payload = {
                "goal_id": args.goal_id,
                "goal_title": before.get("title"),
                "goal_parent_id": before.get("parentId"),
                "lineage_titles": _lineage_titles(lineage),
                "deleted": result.get("ok", False) and after_check.get("status") == 404,
                "delete_status": result.get("status"),
                "after_get_status": after_check.get("status"),
                "guard": {
                    "expected_title": guard.get("expected_title"),
                    "expected_parent_id": guard.get("expected_parent_id"),
                    "under_safe_parent": guard.get("under_safe_parent"),
                },
            }
            _write_audit_log(
                "delete_goal",
                auth,
                goal_id=args.goal_id,
                goal_title=before.get("title"),
                status="success" if payload["deleted"] else "error",
                details=payload,
            )
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_current_member(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            member = _get_current_member(page, auth)
            print(json.dumps(member, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_member_activity(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            current_member = _get_current_member(page, auth)
            member_id = args.member_id or current_member.get("id")
            if not member_id:
                raise RuntimeError("member_id を特定できませんでした")
            activity = _get_member_activity(page, auth, member_id, limit=args.limit, offset=args.offset)
            items = activity.get("items") or []
            print(
                json.dumps(
                    {
                        "member": current_member if current_member.get("id") == member_id else {"id": member_id},
                        "limit": activity.get("limit", args.limit),
                        "offset": activity.get("offset", args.offset),
                        "totalCount": activity.get("totalCount", len(items)),
                        "items": items,
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            context.close()
            browser.close()


def cmd_activity_summary(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            current_member = _get_current_member(page, auth)
            member_id = args.member_id or current_member.get("id")
            if not member_id:
                raise RuntimeError("member_id を特定できませんでした")

            all_items = []
            total_count = None
            for page_index in range(args.pages):
                offset = page_index * args.page_size
                activity = _get_member_activity(page, auth, member_id, limit=args.page_size, offset=offset)
                items = activity.get("items") or []
                if total_count is None:
                    total_count = activity.get("totalCount")
                all_items.extend(items)
                if len(items) < args.page_size:
                    break

            summary = _summarize_activity(all_items)
            payload = {
                "member": current_member if current_member.get("id") == member_id else {"id": member_id},
                "totalCount": total_count if total_count is not None else len(all_items),
                "fetched": len(all_items),
                "pages": args.pages,
                "pageSize": args.page_size,
                "savedReportPath": str(ADDNESS_ACTIVITY_SUMMARY_PATH) if args.save_report else None,
                **summary,
            }
            if args.save_report:
                _write_json_file(ADDNESS_ACTIVITY_SUMMARY_PATH, payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_list_ai_threads(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            payload = _list_ai_threads(page, auth, args.goal_id, limit=args.limit, offset=args.offset)
            threads = payload.get("threads") or []
            print(
                json.dumps(
                    {
                        "goal_id": args.goal_id,
                        "count": len(threads),
                        "items": [_normalize_thread_item(thread) for thread in threads],
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            context.close()
            browser.close()


def cmd_get_ai_messages(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            payload = _get_ai_thread_messages(page, auth, args.thread_id, limit=args.limit)
            messages = payload.get("messages") or []
            print(
                json.dumps(
                    {
                        "thread_id": args.thread_id,
                        "count": len(messages),
                        "items": [_normalize_message_item(message) for message in messages],
                    },
                    ensure_ascii=False,
                )
            )
        finally:
            context.close()
            browser.close()


def cmd_start_ai_session(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            thread = _create_ai_thread(page, auth, args.goal_id, args.purpose, title=args.title or DEFAULT_AI_TITLE)
            payload = _normalize_thread_item(thread)
            _write_audit_log("start_ai_session", auth, goal_id=args.goal_id, details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_send_ai_message(args) -> None:
    config = load_config()
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            thread = _get_ai_thread(page, auth, args.thread_id)
            goal_id = args.goal_id or _extract_thread_goal_id(thread)
            if not goal_id:
                raise RuntimeError("thread から objective_id を特定できませんでした。goal_id を指定してください")
            before_payload = _get_ai_thread_messages(page, auth, args.thread_id, limit=1000)
            before_messages = before_payload.get("messages") or []
            max_index = max((int(message.get("messageIndex") or 0) for message in before_messages), default=0)
            send_result = _send_ai_chat_message(
                page,
                args.thread_id,
                args.message,
                goal_id,
                model=args.model or DEFAULT_AI_MODEL,
                mode=args.mode or DEFAULT_AI_MODE,
            )
            if not send_result.get("ok"):
                raise RuntimeError(f"AI送信に失敗しました [{send_result.get('status')}] {send_result.get('text', '')[:300]}")
            assistant = _wait_for_ai_assistant_message(
                page,
                auth,
                args.thread_id,
                after_message_index=max_index,
                user_text=args.message,
                timeout_seconds=args.timeout_seconds,
            )
            payload = {
                "thread_id": args.thread_id,
                "goal_id": goal_id,
                "message": args.message,
                "response": _extract_message_text(assistant) if assistant else "",
                "assistant_message": _normalize_message_item(assistant) if assistant else None,
            }
            _write_audit_log("send_ai_message", auth, goal_id=goal_id, details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_consult(args) -> None:
    config = load_config()
    target_url = _build_goal_url(goal_id=args.goal_id, goal_url=args.goal_url)
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(
            playwright,
            config,
            headless=args.headless,
            target_url=target_url,
            open_my_goal=target_url is None,
        )
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            goal_id = _extract_goal_id(args.goal_id, args.goal_url, page=page)
            if not goal_id:
                raise RuntimeError("相談先の goal_id を特定できませんでした")
            goal = _get_goal(page, auth, goal_id)
            message = args.message
            if not message:
                if args.instruction:
                    message = (
                        f"甲原さんから以下の指示がありました。\n"
                        f"「{args.instruction}」\n\n"
                        "この指示を踏まえて、今やるべきアクションを1つだけ提案してください。"
                    )
                else:
                    message = "このゴールの完了基準に向けて、今やるべき次のアクションを1つだけ提案してください。"

            if args.thread_id:
                thread = _get_ai_thread(page, auth, args.thread_id)
                thread_id = args.thread_id
            else:
                thread = _create_ai_thread(page, auth, goal_id, args.purpose, title=args.title or DEFAULT_AI_TITLE)
                thread_id = thread.get("id")
            if not thread_id:
                raise RuntimeError("AI thread_id を取得できませんでした")

            before_payload = _get_ai_thread_messages(page, auth, thread_id, limit=1000)
            before_messages = before_payload.get("messages") or []
            max_index = max((int(item.get("messageIndex") or 0) for item in before_messages), default=0)
            send_result = _send_ai_chat_message(
                page,
                thread_id,
                message,
                goal_id,
                model=args.model or DEFAULT_AI_MODEL,
                mode=args.mode or DEFAULT_AI_MODE,
            )
            if not send_result.get("ok"):
                raise RuntimeError(f"AI送信に失敗しました [{send_result.get('status')}] {send_result.get('text', '')[:300]}")
            assistant = _wait_for_ai_assistant_message(
                page,
                auth,
                thread_id,
                after_message_index=max_index,
                user_text=message,
                timeout_seconds=args.timeout_seconds,
            )
            payload = {
                "goal_id": goal_id,
                "goal_title": goal.get("title"),
                "goal_url": _build_goal_url(goal_id=goal_id),
                "thread_id": thread_id,
                "purpose": _normalize_ai_purpose(args.purpose),
                "message": message,
                "response": _extract_message_text(assistant) if assistant else "",
                "assistant_message": _normalize_message_item(assistant) if assistant else None,
            }
            _write_audit_log("consult", auth, goal_id=goal_id, goal_title=goal.get("title"), details=payload)
            print(json.dumps(payload, ensure_ascii=False))
        finally:
            context.close()
            browser.close()


def cmd_smoke_test(args) -> None:
    config = load_config()
    parent_id = args.parent_id or _resolve_smoke_test_parent_id(config)
    with sync_playwright() as playwright:
        browser, context, page = _open_addness(playwright, config, headless=args.headless, open_my_goal=False)
        if not page:
            print(json.dumps({"error": "Addnessログインに失敗"}, ensure_ascii=False))
            sys.exit(1)
        try:
            auth = _get_auth_context(page)
            report = _run_smoke_test(
                page,
                auth,
                parent_id=parent_id,
                timeout_seconds=args.timeout_seconds,
                keep_artifacts=args.keep_artifacts,
                safe_parent_ids=_resolve_safe_delete_parent_ids(config),
            )
            report["savedReportPath"] = str(ADDNESS_SMOKE_TEST_REPORT_PATH)
            _write_json_file(ADDNESS_SMOKE_TEST_REPORT_PATH, report)
            _write_audit_log(
                "smoke_test",
                auth,
                goal_id=parent_id,
                goal_title=(report.get("parent") or {}).get("title"),
                status="success" if report.get("success") else "error",
                details={
                    "parent_id": parent_id,
                    "savedReportPath": str(ADDNESS_SMOKE_TEST_REPORT_PATH),
                    "steps": report.get("steps", []),
                    "cleanup": report.get("cleanup", {}),
                    "error": report.get("error"),
                },
            )
            print(json.dumps(report, ensure_ascii=False))
            if not report.get("success"):
                sys.exit(1)
        finally:
            context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Addness CLI for Codex / 秘書")
    subparsers = parser.add_subparsers(dest="command")

    p_login = subparsers.add_parser("login", help="初回ログイン（手動）")

    p_consult = subparsers.add_parser("consult", help="AIと相談する")
    p_consult.add_argument("--goal-id", default=None, help="相談対象の goal_id")
    p_consult.add_argument("--goal-url", default=None, help="相談対象の goal_url")
    p_consult.add_argument("--thread-id", default=None, help="既存 AI thread_id。未指定なら新規作成")
    p_consult.add_argument("--purpose", default="brainstorm", help="brainstorm / completion_criteria / task_breakdown / execution")
    p_consult.add_argument("--message", default=None, help="AIへ送るメッセージ")
    p_consult.add_argument("--instruction", default=None, help="旧互換の指示文")
    p_consult.add_argument("--title", default=None, help="新規会話タイトル")
    p_consult.add_argument("--model", default=None, help="AIモデル")
    p_consult.add_argument("--mode", default=None, help="AIモード")
    p_consult.add_argument("--timeout-seconds", type=int, default=DEFAULT_AI_TIMEOUT_SECONDS, help="返答待ち秒数")
    _add_headless_args(p_consult)

    p_check_comments = subparsers.add_parser("check-comments", help="コメントから指示を確認")
    _add_headless_args(p_check_comments)

    p_goal_info = subparsers.add_parser("get-goal-info", help="現在のゴール情報を取得")
    _add_headless_args(p_goal_info)

    p_search = subparsers.add_parser("search-goals", help="任意文字列でゴール検索")
    p_search.add_argument("--query", required=True, help="検索文字列")
    p_search.add_argument("--limit", type=int, default=20, help="取得件数")
    _add_headless_args(p_search)

    p_goal = subparsers.add_parser("get-goal", help="goal_id で任意ゴールを取得")
    p_goal.add_argument("--goal-id", required=True, help="取得したい goal_id")
    _add_headless_args(p_goal)

    p_create_goal = subparsers.add_parser("create-goal", help="子ゴールを新規作成")
    p_create_goal.add_argument("--parent-id", required=True, help="親 goal_id")
    p_create_goal.add_argument("--title", required=True, help="新しいゴール名")
    p_create_goal.add_argument("--due-date", default=None, help="期日 YYYY-MM-DD / YYYY/MM/DD / ISO8601")
    p_create_goal.add_argument("--description", default=None, help="完了の基準")
    p_create_goal.add_argument("--status", default=None, help="completed / none")
    _add_headless_args(p_create_goal)

    p_update_title = subparsers.add_parser("update-goal-title", help="ゴールタイトル変更")
    p_update_title.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_update_title.add_argument("--title", required=True, help="新しいタイトル")
    _add_headless_args(p_update_title)

    p_update_status = subparsers.add_parser("update-goal-status", help="ゴールの完了状態変更")
    p_update_status.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_update_status.add_argument("--status", required=True, help="completed / none / raw status")
    _add_headless_args(p_update_status)

    p_update_due = subparsers.add_parser("update-goal-due-date", help="ゴール期日変更")
    p_update_due.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_update_due.add_argument("--due-date", required=True, help="YYYY-MM-DD / YYYY/MM/DD / ISO8601")
    _add_headless_args(p_update_due)

    p_update_desc = subparsers.add_parser("update-goal-description", help="完了の基準を変更")
    p_update_desc.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_update_desc.add_argument("--description", required=True, help="完了の基準")
    _add_headless_args(p_update_desc)

    p_reparent = subparsers.add_parser("reparent-goal", help="親ゴールを変更")
    p_reparent.add_argument("--goal-id", required=True, help="子にしたい goal_id")
    p_reparent.add_argument("--new-parent-id", required=True, help="新しい親 goal_id")
    _add_headless_args(p_reparent)

    p_list_comments = subparsers.add_parser("list-comments", help="ゴールのコメント一覧を取得")
    p_list_comments.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_list_comments.add_argument("--resolved", action="store_true", default=False, help="resolved コメントを取得")
    p_list_comments.add_argument("--limit", type=int, default=20, help="取得件数")
    p_list_comments.add_argument("--offset", type=int, default=0, help="offset")
    p_list_comments.add_argument("--sort", default="desc", help="desc / asc")
    _add_headless_args(p_list_comments)

    p_comment = subparsers.add_parser("post-comment", help="コメントを投稿")
    p_comment.add_argument("--text", required=True, help="コメント内容")
    p_comment.add_argument("--goal-id", default=None, help="投稿先 goal_id")
    p_comment.add_argument("--goal-url", default=None, help="投稿先 goal_url")
    _add_headless_args(p_comment)

    p_resolve_comment = subparsers.add_parser("resolve-comment", help="コメントを解決済みにする")
    p_resolve_comment.add_argument("--comment-id", required=True, help="対象 comment_id")
    _add_headless_args(p_resolve_comment)

    p_delete_comment = subparsers.add_parser("delete-comment", help="コメントを削除")
    p_delete_comment.add_argument("--comment-id", required=True, help="対象 comment_id")
    p_delete_comment.add_argument("--yes", action="store_true", default=False, help="削除確認")
    _add_headless_args(p_delete_comment)

    p_archive = subparsers.add_parser("archive-goal", help="ゴールをアーカイブ")
    p_archive.add_argument("--goal-id", required=True, help="対象 goal_id")
    _add_headless_args(p_archive)

    p_delete_goal = subparsers.add_parser("delete-goal", help="ゴールを削除")
    p_delete_goal.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_delete_goal.add_argument("--expected-title", default=None, help="削除対象タイトルの一致確認")
    p_delete_goal.add_argument("--expected-parent-id", default=None, help="削除対象親 goal_id の一致確認")
    p_delete_goal.add_argument("--allow-non-test-goal", action="store_true", default=False, help="テスト配下以外の削除を許可")
    p_delete_goal.add_argument("--yes", action="store_true", default=False, help="削除確認")
    _add_headless_args(p_delete_goal)

    p_current_member = subparsers.add_parser("current-member", help="現在ログイン中メンバー情報を取得")
    _add_headless_args(p_current_member)

    p_member_activity = subparsers.add_parser("member-activity", help="メンバー行動ログを取得")
    p_member_activity.add_argument("--member-id", default=None, help="対象 member_id。未指定なら自分")
    p_member_activity.add_argument("--limit", type=int, default=100, help="取得件数")
    p_member_activity.add_argument("--offset", type=int, default=0, help="取得開始位置")
    _add_headless_args(p_member_activity)

    p_activity_summary = subparsers.add_parser("activity-summary", help="行動ログを集計して主要操作を返す")
    p_activity_summary.add_argument("--member-id", default=None, help="対象 member_id。未指定なら自分")
    p_activity_summary.add_argument("--pages", type=int, default=5, help="何ページ分集計するか")
    p_activity_summary.add_argument("--page-size", type=int, default=100, help="1ページあたり件数")
    p_activity_summary.add_argument("--save-report", action="store_true", default=False, help="集計結果をローカル保存")
    _add_headless_args(p_activity_summary)

    p_list_ai_threads = subparsers.add_parser("list-ai-threads", help="ゴールに紐づく AI スレッド一覧")
    p_list_ai_threads.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_list_ai_threads.add_argument("--limit", type=int, default=20, help="取得件数")
    p_list_ai_threads.add_argument("--offset", type=int, default=0, help="offset")
    _add_headless_args(p_list_ai_threads)

    p_get_ai_messages = subparsers.add_parser("get-ai-messages", help="AI スレッドのメッセージ一覧")
    p_get_ai_messages.add_argument("--thread-id", required=True, help="対象 thread_id")
    p_get_ai_messages.add_argument("--limit", type=int, default=1000, help="取得件数")
    _add_headless_args(p_get_ai_messages)

    p_start_ai = subparsers.add_parser("start-ai-session", help="新しい AI 会話を開始")
    p_start_ai.add_argument("--goal-id", required=True, help="対象 goal_id")
    p_start_ai.add_argument("--purpose", default="brainstorm", help="brainstorm / completion_criteria / task_breakdown / execution")
    p_start_ai.add_argument("--title", default=None, help="スレッドタイトル")
    _add_headless_args(p_start_ai)

    p_send_ai = subparsers.add_parser("send-ai-message", help="既存 AI スレッドにメッセージ送信")
    p_send_ai.add_argument("--thread-id", required=True, help="対象 thread_id")
    p_send_ai.add_argument("--message", required=True, help="送るメッセージ")
    p_send_ai.add_argument("--goal-id", default=None, help="関連 goal_id。未指定なら thread metadata から推定")
    p_send_ai.add_argument("--model", default=None, help="AIモデル")
    p_send_ai.add_argument("--mode", default=None, help="AIモード")
    p_send_ai.add_argument("--timeout-seconds", type=int, default=DEFAULT_AI_TIMEOUT_SECONDS, help="返答待ち秒数")
    _add_headless_args(p_send_ai)

    p_smoke_test = subparsers.add_parser("smoke-test", help="Addness の主要操作をテスト配下で一括検証")
    p_smoke_test.add_argument("--parent-id", default=None, help="テスト用親 goal_id。未指定なら設定値")
    p_smoke_test.add_argument("--timeout-seconds", type=int, default=DEFAULT_AI_TIMEOUT_SECONDS, help="AI返答待ち秒数")
    p_smoke_test.add_argument("--keep-artifacts", action="store_true", default=False, help="失敗時のテストゴールを残す")
    _add_headless_args(p_smoke_test)

    args = parser.parse_args()

    commands = {
        "login": cmd_login,
        "consult": cmd_consult,
        "check-comments": cmd_check_comments,
        "get-goal-info": cmd_get_goal_info,
        "search-goals": cmd_search_goals,
        "get-goal": cmd_get_goal,
        "create-goal": cmd_create_goal,
        "update-goal-title": cmd_update_goal_title,
        "update-goal-status": cmd_update_goal_status,
        "update-goal-due-date": cmd_update_goal_due_date,
        "update-goal-description": cmd_update_goal_description,
        "reparent-goal": cmd_reparent_goal,
        "list-comments": cmd_list_comments,
        "post-comment": cmd_post_comment,
        "resolve-comment": cmd_resolve_comment,
        "delete-comment": cmd_delete_comment,
        "archive-goal": cmd_archive_goal,
        "delete-goal": cmd_delete_goal,
        "current-member": cmd_current_member,
        "member-activity": cmd_member_activity,
        "activity-summary": cmd_activity_summary,
        "list-ai-threads": cmd_list_ai_threads,
        "get-ai-messages": cmd_get_ai_messages,
        "start-ai-session": cmd_start_ai_session,
        "send-ai-message": cmd_send_ai_message,
        "smoke-test": cmd_smoke_test,
    }

    if args.command in commands:
        commands[args.command](args)
        return

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()
