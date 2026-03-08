#!/usr/bin/env python3
"""
Addness上の日向コメントを秘書承認フローに流し込み、承認後は甲原アカウントで返信する。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config" / "addness.json"
SESSION_PATH = SCRIPT_DIR / "data" / "addness_session.json"
PASSWORD_PATH = SCRIPT_DIR / "credentials" / "kohara_google.txt"
SNAPSHOT_PATH = SCRIPT_DIR / "addness_data" / "latest.json"
RUNTIME_DATA_DIR = Path.home() / "agents" / "data"
RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = RUNTIME_DATA_DIR / "addness_hinata_feedback_state.json"
LOCAL_AGENT_CONFIG = RUNTIME_DATA_DIR / "config.json"

DEFAULT_START_URL = "https://www.addness.com/todo/execution"
ROOT_GOAL_ID = "45e3a49b-4818-429d-936e-913d41b5d833"
KOHARA_GOAL_ID = "69bbece5-9ff7-4f96-b7f8-0227d0560f9c"
GOOGLE_EMAIL_CANDIDATES = [
    "koa800sea.nifs@gmail.com",
    "kohara.kaito@team.addness.co.jp",
]
HINATA_NAME_CANDIDATES = ("日向", "ひなた", "hinata")


def load_json(path: Path, default: Any):
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def save_json(path: Path, data: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def load_addness_config() -> dict:
    config = load_json(CONFIG_PATH, {})
    return {
        "start_url": config.get("start_url", DEFAULT_START_URL),
        "timeout_ms": int(config.get("timeout_ms", 60_000)),
        "headless": bool(config.get("headless", True)),
    }


def load_local_agent_config() -> dict:
    config = load_json(LOCAL_AGENT_CONFIG, {})
    return {
        "server_url": os.environ.get("LINE_BOT_SERVER_URL") or config.get("server_url", ""),
        "agent_token": os.environ.get("AGENT_TOKEN") or os.environ.get("LOCAL_AGENT_TOKEN") or config.get("agent_token", ""),
    }


def normalize_text(value: str) -> str:
    return re.sub(r"[\s\u3000]+", "", (value or "")).casefold()


def is_hinata_name(name: str) -> bool:
    normalized = normalize_text(name)
    return any(candidate in normalized for candidate in HINATA_NAME_CANDIDATES)


def is_authenticated(page) -> bool:
    url = page.url or ""
    return "addness.com" in url and "sign-in" not in url and "sign-up" not in url


def read_google_password() -> str:
    if not PASSWORD_PATH.exists():
        return ""
    try:
        return PASSWORD_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def notify_owner(message: str, label: str = "Addness確認"):
    config = load_local_agent_config()
    if not config["server_url"] or not config["agent_token"]:
        return
    try:
        requests.post(
            f"{config['server_url'].rstrip('/')}/api/notify_owner",
            json={"message": message, "label": label},
            headers={"Authorization": f"Bearer {config['agent_token']}"},
            timeout=15,
        )
    except Exception:
        pass


def click_if_visible(page, selectors: list[str]) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector)
            if locator.count() > 0 and locator.first.is_visible():
                locator.first.click()
                return True
        except Exception:
            continue
    return False


def wait_for_addness_redirect(page, timeout_ms: int) -> bool:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if is_authenticated(page):
            return True
        time.sleep(2)
    return False


def maybe_handle_two_factor(page, timeout_ms: int):
    url = page.url or ""
    body_preview = ""
    try:
        body_preview = (page.locator("body").inner_text(timeout=3000) or "")[:500]
    except Exception:
        body_preview = ""

    if "challenge" not in url and "確認" not in body_preview and "スマートフォン" not in body_preview:
        return

    notify_owner(
        "🔐 Addnessログインで2段階認証の承認が必要です。iPhoneの確認をお願いします。",
        label="Addnessログイン",
    )
    wait_for_addness_redirect(page, min(timeout_ms, 120_000))


def auto_google_login(page, timeout_ms: int) -> bool:
    password = read_google_password()
    if not password:
        return False

    google_selectors = [
        'button:has-text("Googleで続ける")',
        'button:has-text("Google")',
        'a:has-text("Google")',
        '[data-provider="google"]',
        '[class*="google"]',
    ]
    try:
        page.wait_for_selector(", ".join(google_selectors + ['input[type="email"]']), timeout=15_000)
    except PlaywrightTimeoutError:
        pass

    click_if_visible(page, google_selectors)
    try:
        page.wait_for_url("**accounts.google.com/**", timeout=15_000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(3_000)

    for email in GOOGLE_EMAIL_CANDIDATES:
        try:
            for selector in (
                f'text="{email}"',
                f'[data-email="{email}"]',
                f'li:has-text("{email}")',
            ):
                account_choice = page.locator(selector)
                if account_choice.count() > 0:
                    account_choice.first.click()
                    page.wait_for_timeout(3_000)
                    break
        except Exception:
            pass

        try:
            email_input = page.locator('input[type="email"]')
            if email_input.count() > 0:
                email_input.first.fill(email)
                click_if_visible(page, ['button:has-text("次へ")', "#identifierNext"])
                page.wait_for_timeout(3_000)
        except Exception:
            pass

        try:
            password_input = page.locator('input[type="password"]')
            if password_input.count() > 0:
                password_input.first.fill(password)
                click_if_visible(page, ['button:has-text("次へ")', "#passwordNext"])
                page.wait_for_timeout(5_000)
        except Exception:
            pass

        click_if_visible(
            page,
            [
                'button:has-text("許可")',
                'button:has-text("続行")',
                'button:has-text("Allow")',
                '[id="submit_approve_access"]',
            ],
        )
        page.wait_for_timeout(3_000)

        maybe_handle_two_factor(page, timeout_ms)
        if wait_for_addness_redirect(page, 20_000):
            return True

        try:
            page.goto(DEFAULT_START_URL, wait_until="domcontentloaded", timeout=60_000)
            time.sleep(2)
            if is_authenticated(page):
                return True
            click_if_visible(
                page,
                [
                    'button:has-text("Google")',
                    'a:has-text("Google")',
                    '[data-provider="google"]',
                    '[class*="google"]',
                ],
            )
            time.sleep(3)
        except Exception:
            pass

    return is_authenticated(page)


def open_context(playwright, headless: bool):
    browser = playwright.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
        ],
    )
    context_kwargs = {"viewport": {"width": 1440, "height": 960}}
    if SESSION_PATH.exists():
        context_kwargs["storage_state"] = str(SESSION_PATH)
    context = browser.new_context(**context_kwargs)
    page = context.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return browser, context, page


def ensure_logged_in(page, context, start_url: str, timeout_ms: int) -> bool:
    try:
        page.goto(start_url, wait_until="networkidle", timeout=60_000)
    except PlaywrightTimeoutError:
        page.goto(start_url, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(3)
    if is_authenticated(page):
        return True

    if auto_google_login(page, timeout_ms):
        try:
            context.storage_state(path=str(SESSION_PATH))
        except Exception:
            pass
        return True

    return False


def fetch_json(page, url: str) -> dict:
    result = page.evaluate(
        """async (inputUrl) => {
            const response = await fetch(inputUrl, { headers: { Accept: "application/json" } });
            const text = await response.text();
            let body = null;
            try {
                body = JSON.parse(text);
            } catch (error) {
                body = { raw: text };
            }
            return {
                ok: response.ok,
                status: response.status,
                url: response.url,
                body,
            };
        }""",
        url,
    )
    return result or {}


def flatten_tree(nodes: list[dict], depth: int = 0, parent_id: str = "") -> list[dict]:
    flat = []
    for node in nodes or []:
        if not isinstance(node, dict):
            continue
        current = {
            "id": node.get("id") or node.get("objectiveId"),
            "title": node.get("title", ""),
            "owner_name": ((node.get("owner") or {}).get("name", "")),
            "depth": depth,
            "parent_id": parent_id,
            "goal_url": f"https://www.addness.com/goals/{node.get('id') or node.get('objectiveId')}",
            "children": node.get("children", []),
        }
        if current["id"]:
            flat.append(current)
        flat.extend(flatten_tree(node.get("children", []), depth + 1, current["id"]))
    return flat


def find_kohara_root(flat_nodes: list[dict]) -> dict | None:
    matches = [
        node for node in flat_nodes
        if normalize_text(node.get("owner_name", "")) == normalize_text("甲原海人")
    ]
    if not matches:
        return None
    matches.sort(key=lambda node: (node.get("depth", 99), -len(node.get("children", []))))
    return matches[0]


def load_cached_tree_and_counts() -> tuple[list[dict], dict[str, int]]:
    snapshot = load_json(SNAPSHOT_PATH, {})
    api_responses = snapshot.get("api_responses", {}) if isinstance(snapshot, dict) else {}

    tree_payload = api_responses.get("/api/v1/team/daily_focus_objectives/tree", {})
    tree_data = ((tree_payload or {}).get("data")) or []
    flat_nodes = flatten_tree(tree_data)

    counts_payload = api_responses.get(
        f"/api/v1/team/objectives/{ROOT_GOAL_ID}/unresolved_comments_counts", {}
    )
    counts = ((counts_payload or {}).get("data")) or []
    count_map = {
        item.get("id"): int(item.get("unresolvedCommentsCount", 0))
        for item in counts
        if isinstance(item, dict) and item.get("id")
    }
    return flat_nodes, count_map


def get_comment_urls(page) -> list[str]:
    urls = page.evaluate(
        """() => {
            return performance
                .getEntriesByType("resource")
                .map((entry) => entry.name)
                .filter((name) => name.includes("/api/v1/team/comments"));
        }"""
    )
    return list(dict.fromkeys(urls or []))


def open_comments_if_needed(page):
    click_if_visible(
        page,
        [
            'button:has-text("コメント")',
            '[role="tab"]:has-text("コメント")',
            'button[aria-label*="comment"]',
            '[class*="comment"][role="button"]',
        ],
    )
    time.sleep(2)


def extract_value(obj: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(obj, dict):
        return ""
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def extract_text_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts = [extract_text_value(item) for item in value]
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        direct = extract_value(value, ("text", "content", "body", "message", "comment"))
        if direct:
            return direct
        for item in value.values():
            extracted = extract_text_value(item)
            if extracted:
                return extracted
    return ""


def extract_author_name(comment: dict) -> str:
    direct = extract_value(comment, ("authorName", "createdByName", "memberName", "ownerName", "userName"))
    if direct:
        return direct
    for key in ("author", "owner", "creator", "createdBy", "organizationMember", "member", "user", "sender"):
        nested = comment.get(key)
        if isinstance(nested, dict):
            name = extract_value(nested, ("name", "displayName", "fullName"))
            if name:
                return name
    return ""


def is_unresolved_comment(comment: dict) -> bool:
    if comment.get("resolvedAt"):
        return False
    if "isResolved" in comment:
        return not bool(comment.get("isResolved"))
    if "resolved" in comment:
        return not bool(comment.get("resolved"))
    status = str(comment.get("status", "")).upper()
    if status in {"RESOLVED", "DONE"}:
        return False
    return True


def collect_comment_objects(value: Any, results: list[dict]):
    if isinstance(value, list):
        for item in value:
            collect_comment_objects(item, results)
        return
    if not isinstance(value, dict):
        return

    text = extract_text_value(value)
    comment_id = extract_value(value, ("id", "commentId"))
    author_name = extract_author_name(value)
    if comment_id and text and (author_name or any(key in value for key in ("author", "owner", "creator", "createdBy", "organizationMember"))):
        results.append(value)
    for nested in value.values():
        collect_comment_objects(nested, results)


def normalize_comment(goal_id: str, goal_title: str, comment: dict) -> dict:
    comment_id = extract_value(comment, ("id", "commentId"))
    text = extract_text_value(comment)
    created_at = extract_value(comment, ("createdAt", "updatedAt", "postedAt"))
    author_name = extract_author_name(comment)
    if not comment_id:
        raw = f"{goal_id}|{author_name}|{created_at}|{text}"
        comment_id = "synthetic-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return {
        "comment_id": comment_id,
        "goal_id": goal_id,
        "goal_title": goal_title,
        "author_name": author_name,
        "text": text,
        "created_at": created_at,
        "unresolved": is_unresolved_comment(comment),
    }


def extract_dom_comments(page, goal_id: str, goal_title: str) -> list[dict]:
    items = page.evaluate(
        """() => {
            const results = [];
            const nodes = Array.from(document.querySelectorAll('[data-comment-id]'));
            nodes.forEach((node, index) => {
                const textNode = node.querySelector('.comment-markdown');
                const text = (textNode?.innerText || "").trim();
                if (!text || text.length < 5) return;
                const author = (node.querySelector('span.text-sm.font-medium')?.innerText || "").trim();
                const createdAt = node.querySelector('time[datetime]')?.getAttribute('datetime') || "";
                results.push({
                    id: node.getAttribute("data-comment-id") || node.id || `dom-${index}`,
                    author,
                    createdAt,
                    text,
                });
            });
            return results;
        }"""
    ) or []

    normalized = []
    for item in items:
        text = (item.get("text") or "").strip()
        normalized.append({
            "comment_id": item.get("id", ""),
            "goal_id": goal_id,
            "goal_title": goal_title,
            "author_name": (item.get("author") or "").strip(),
            "text": text,
            "created_at": item.get("createdAt", ""),
            "unresolved": True,
        })
    return normalized


def fetch_goal_comments(page, goal_id: str, goal_title: str) -> list[dict]:
    goal_url = f"https://www.addness.com/goals/{goal_id}"
    try:
        page.evaluate("() => performance.clearResourceTimings()")
    except Exception:
        pass

    try:
        page.goto(goal_url, wait_until="networkidle", timeout=60_000)
    except PlaywrightTimeoutError:
        page.goto(goal_url, wait_until="domcontentloaded", timeout=60_000)
    time.sleep(3)

    open_comments_if_needed(page)
    time.sleep(2)

    comment_urls = get_comment_urls(page)
    if not comment_urls:
        open_comments_if_needed(page)
        time.sleep(2)
        comment_urls = get_comment_urls(page)

    results = []
    if comment_urls:
        payload = fetch_json(page, comment_urls[-1])
        comment_objects = []
        body = payload.get("body", {})
        comments = (((body or {}).get("data") or {}).get("comments"))
        if isinstance(comments, list):
            comment_objects = comments
        else:
            collect_comment_objects(body, comment_objects)

        for item in comment_objects:
            if not isinstance(item, dict):
                continue
            normalized = normalize_comment(goal_id, goal_title, item)
            if normalized["text"]:
                results.append(normalized)

    if results:
        deduped = {}
        for item in results:
            deduped[item["comment_id"]] = item
        return list(deduped.values())

    return extract_dom_comments(page, goal_id, goal_title)


def register_feedback(feedback: dict) -> tuple[bool, str]:
    config = load_local_agent_config()
    if not config["server_url"] or not config["agent_token"]:
        return False, "server_url または agent_token が未設定です"

    payload = {
        "feedback_id": feedback["comment_id"],
        "comment_id": feedback["comment_id"],
        "goal_id": feedback["goal_id"],
        "goal_title": feedback["goal_title"],
        "goal_url": f"https://www.addness.com/goals/{feedback['goal_id']}",
        "sender_name": "日向",
        "original_text": feedback["text"],
        "created_at": feedback.get("created_at", ""),
    }

    response = requests.post(
        f"{config['server_url'].rstrip('/')}/api/addness/hinata-feedback",
        json=payload,
        headers={"Authorization": f"Bearer {config['agent_token']}"},
        timeout=20,
    )
    if response.status_code != 200:
        return False, f"server_error:{response.status_code}:{response.text[:200]}"
    return True, response.text[:200]


def prune_state(state: dict):
    processed = state.get("processed", {})
    if len(processed) <= 1000:
        return
    items = sorted(processed.items(), key=lambda item: item[1], reverse=True)[:800]
    state["processed"] = dict(items)


def scan(limit_goals: int, headless: bool) -> dict:
    addness_config = load_addness_config()
    state = load_json(STATE_FILE, {"processed": {}})
    registered = []
    skipped = []
    errors = []

    with sync_playwright() as playwright:
        browser, context, page = open_context(playwright, headless=headless)
        try:
            if not ensure_logged_in(page, context, addness_config["start_url"], addness_config["timeout_ms"]):
                raise RuntimeError("Addnessにログインできませんでした。セッション期限切れの可能性があります。")

            tree_payload = fetch_json(page, "/api/v1/team/daily_focus_objectives/tree?depth=10")
            tree_data = ((tree_payload.get("body") or {}).get("data")) or []
            flat_nodes = flatten_tree(tree_data)
            count_map = {}

            if flat_nodes:
                counts_payload = fetch_json(
                    page,
                    f"/api/v1/team/objectives/{ROOT_GOAL_ID}/unresolved_comments_counts",
                )
                counts = (((counts_payload.get("body") or {}).get("data")) or [])
                count_map = {
                    item.get("id"): int(item.get("unresolvedCommentsCount", 0))
                    for item in counts
                    if item.get("id")
                }

            if not flat_nodes or not count_map:
                cached_nodes, cached_count_map = load_cached_tree_and_counts()
                if cached_nodes:
                    flat_nodes = cached_nodes
                if cached_count_map:
                    count_map = cached_count_map

            kohara_root = find_kohara_root(flat_nodes)
            if not kohara_root:
                kohara_root = next(
                    (node for node in flat_nodes if node.get("id") == KOHARA_GOAL_ID),
                    {"id": KOHARA_GOAL_ID, "title": "『スキルプラス』をスキルアップ市場No.1にする"},
                )

            id_to_node = {node["id"]: node for node in flat_nodes}
            subtree_goal_ids = {kohara_root.get("id")}
            changed = True
            while changed:
                changed = False
                for node in flat_nodes:
                    node_id = node.get("id")
                    parent_id = node.get("parent_id")
                    if node_id and parent_id in subtree_goal_ids and node_id not in subtree_goal_ids:
                        subtree_goal_ids.add(node_id)
                        changed = True

            candidate_goal_ids = [
                goal_id for goal_id, count in sorted(count_map.items(), key=lambda item: item[1], reverse=True)
                if count > 0 and goal_id in subtree_goal_ids
            ][:limit_goals]

            fallback_goal_ids = [
                node["id"]
                for node in flat_nodes
                if node.get("id")
                and node.get("id") in subtree_goal_ids
                and node.get("id") != kohara_root.get("id")
            ]
            for goal_id in fallback_goal_ids:
                if goal_id not in candidate_goal_ids:
                    candidate_goal_ids.append(goal_id)
                if len(candidate_goal_ids) >= limit_goals:
                    break

            for goal_id in candidate_goal_ids:
                node = id_to_node.get(goal_id, {})
                goal_title = node.get("title") or goal_id
                try:
                    comments = fetch_goal_comments(page, goal_id, goal_title)
                except Exception as error:
                    errors.append({"goal_id": goal_id, "error": str(error)})
                    continue

                hinata_comments = []
                for comment in comments:
                    if not comment.get("unresolved"):
                        continue
                    if not is_hinata_name(comment.get("author_name", "")):
                        continue
                    if comment["comment_id"] in state.get("processed", {}):
                        skipped.append(comment["comment_id"])
                        continue
                    hinata_comments.append(comment)

                hinata_comments.sort(key=lambda item: item.get("created_at", ""))
                for comment in hinata_comments:
                    ok, response_preview = register_feedback(comment)
                    if ok:
                        state.setdefault("processed", {})[comment["comment_id"]] = datetime.now().isoformat()
                        registered.append({
                            "comment_id": comment["comment_id"],
                            "goal_id": comment["goal_id"],
                            "goal_title": comment["goal_title"],
                            "preview": comment["text"][:80],
                        })
                    else:
                        errors.append({
                            "goal_id": comment["goal_id"],
                            "comment_id": comment["comment_id"],
                            "error": response_preview,
                        })

            prune_state(state)
            state["last_scan_at"] = datetime.now().isoformat()
            save_json(STATE_FILE, state)
        finally:
            context.close()
            browser.close()

    return {
        "success": True,
        "registered_count": len(registered),
        "registered": registered,
        "skipped_count": len(skipped),
        "errors": errors,
    }


def post_comment(goal_id: str, goal_url: str, text: str, headless: bool) -> dict:
    if not text.strip():
        raise RuntimeError("返信文が空です。")

    addness_config = load_addness_config()
    target_url = goal_url or f"https://www.addness.com/goals/{goal_id}"

    with sync_playwright() as playwright:
        browser, context, page = open_context(playwright, headless=headless)
        try:
            if not ensure_logged_in(page, context, target_url, addness_config["timeout_ms"]):
                raise RuntimeError("Addnessにログインできませんでした。セッション期限切れの可能性があります。")

            page.goto(target_url, wait_until="networkidle", timeout=60_000)
            time.sleep(2)
            open_comments_if_needed(page)
            time.sleep(1)

            comment_input = page.locator(
                'textarea[placeholder*="コメント"], '
                '[placeholder*="コメントを送信"], '
                'textarea[placeholder*="メンション"], '
                '[contenteditable="true"][role="textbox"], '
                '[contenteditable="true"][data-slate-editor="true"]'
            ).last
            if comment_input.count() == 0:
                raise RuntimeError("コメント入力欄が見つかりませんでした。")

            comment_input.click()
            time.sleep(0.5)
            comment_input.fill(text.strip())
            time.sleep(0.5)
            page.keyboard.press("Meta+Enter")
            time.sleep(1)
            click_if_visible(
                page,
                [
                    'button:has-text("送信")',
                    '[aria-label*="送信"]',
                    '[data-testid*="send"]',
                ],
            )
            time.sleep(2)

            try:
                page.locator(f"text={text.strip()[:20]}").first.wait_for(timeout=5_000)
            except Exception:
                pass

            title = ""
            try:
                title = page.locator("h1").first.inner_text(timeout=3_000).strip()
            except Exception:
                title = goal_id or goal_url

            return {
                "success": True,
                "goal_title": title,
                "goal_url": page.url,
            }
        finally:
            context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Addness feedback manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="未解決の日向コメントを検知して秘書承認フローへ登録")
    scan_parser.add_argument("--limit-goals", type=int, default=10)
    scan_parser.add_argument("--headless", action="store_true", default=False)

    post_parser = subparsers.add_parser("post-comment", help="甲原アカウントでAddnessにコメント投稿")
    post_parser.add_argument("--goal-id", default="")
    post_parser.add_argument("--goal-url", default="")
    post_parser.add_argument("--text", required=True)
    post_parser.add_argument("--headless", action="store_true", default=False)

    args = parser.parse_args()

    try:
        if args.command == "scan":
            result = scan(limit_goals=args.limit_goals, headless=args.headless)
        else:
            result = post_comment(
                goal_id=args.goal_id,
                goal_url=args.goal_url,
                text=args.text,
                headless=args.headless,
            )
        print(json.dumps(result, ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"success": False, "error": str(error)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
