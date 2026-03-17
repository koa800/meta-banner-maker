#!/usr/bin/env python3
"""Zapier の exploratory draft を create -> persisted -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import time
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import body_snapshot
from chrome_raw_cdp import click_first
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import fill_first_input
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target
from zapier_login_helper import ensure_login as ensure_zapier_login


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"
CREATE_URL = "https://zapier.com/webintent/create-zap?useCase=from-scratch"


def _extract_edit_path(url: str | None) -> str | None:
    if not url:
        return None
    marker = "/webintent/edit-zap/"
    if marker not in url:
        return None
    path = url.split("zapier.com", 1)[-1]
    return path if path.startswith("/") else None

ROWS_EXPRESSION = """
() => {
  const links = Array.from(document.querySelectorAll('a[href*="/webintent/edit-zap/"]'));
  const out = [];
  for (const link of links) {
    const name = (link.textContent || '').trim();
    if (name !== 'Untitled Zap') continue;
    const row = link.closest('tr');
    const cells = row ? Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim()) : [];
    out.push({
      name,
      href: link.getAttribute('href') || '',
      last_modified: cells[3] || '',
      status: cells[4] || '',
    });
  }
  return out;
}
"""


async def _collect_untitled_rows(page) -> list[dict[str, str]]:
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    rows = await page.evaluate(
        """
() => {
  const links = Array.from(document.querySelectorAll('a[href*="/webintent/edit-zap/"]'));
  const out = [];
  for (const link of links) {
    const name = (link.textContent || '').trim();
    if (name !== 'Untitled Zap') continue;
    const row = link.closest('tr');
    const cells = row ? Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim()) : [];
    out.push({
      name,
      href: link.getAttribute('href') || '',
      last_modified: cells[3] || '',
      status: cells[4] || '',
    });
  }
  return out;
}
"""
    )
    return rows


async def _wait_for_new_row(page, before: list[dict[str, Any]], *, timeout_ms: int = 20000, poll_ms: int = 1500) -> list[dict[str, Any]]:
    before_paths = {str(item.get("href") or "") for item in before}
    started = time.time()
    while (time.time() - started) * 1000 <= timeout_ms:
        rows = await _collect_untitled_rows(page)
        created_rows = [
            item for item in rows
            if str(item.get("href") or "") not in before_paths
        ]
        if created_rows:
            return created_rows
        await page.wait_for_timeout(poll_ms)
    return []


def _find_assets_target_id() -> str:
    target = find_target(url_contains="/app/assets/zaps") or find_target(url_contains="zapier.com")
    if target is None:
        target = create_target(ASSETS_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    return target_id


def _collect_untitled_rows_raw() -> list[dict[str, Any]]:
    target_id = _find_assets_target_id()
    navigate_target(target_id, ASSETS_URL)
    time.sleep(2.5)
    return eval_target(target_id, f"({ROWS_EXPRESSION})()") or []


def _wait_for_new_row_raw(before: list[dict[str, Any]], *, timeout_seconds: int = 20, poll_seconds: float = 1.5) -> list[dict[str, Any]]:
    before_paths = {str(item.get("href") or "") for item in before}
    started = time.time()
    while time.time() - started <= timeout_seconds:
        rows = _collect_untitled_rows_raw()
        created_rows = [
            item for item in rows
            if str(item.get("href") or "") not in before_paths
        ]
        if created_rows:
            return created_rows
        time.sleep(poll_seconds)
    return []


def _open_create_target_raw() -> str:
    target = find_target(url_contains="/webintent/create-zap") or create_target(CREATE_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    navigate_target(target_id, CREATE_URL)
    time.sleep(3.0)
    return target_id


def _choose_webhook_trigger_raw(target_id: str) -> None:
    opened = bool(
        eval_target(
            target_id,
            """(() => {
              const node =
                document.querySelector('[data-testid="step-node-1"][role="button"]') ||
                document.querySelector('[data-testid^="step-node-"][role="button"]');
              if (!node) return false;
              node.click();
              node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
              return true;
            })()""",
        )
    )
    if not opened and not click_first(
        target_id,
        selectors=["[data-testid='step-node-1'][role='button']", "[data-testid^='step-node-'][role='button']", "button", "div[role='button']", "[data-testid*='trigger']"],
        text_candidates=["Select the event that starts your Zap", "Trigger"],
    ):
        raise RuntimeError("raw fallback で Trigger 入口を押せませんでした")
    time.sleep(1.5)
    if not fill_first_input(
        target_id,
        [
            "input[placeholder*='Search apps']",
            "input[aria-label*='Search apps']",
            "input[type='search']",
            "input[type='text']",
        ],
        "Webhooks",
    ):
        raise RuntimeError("raw fallback で app search を埋められませんでした")
    time.sleep(1.0)
    if not click_first(
        target_id,
        selectors=["button", "div[role='option']", "li[role='option']", "div"],
        text_candidates=["Webhooks"],
    ):
        raise RuntimeError("raw fallback で Webhooks を選べませんでした")
    time.sleep(1.5)
    if not click_first(
        target_id,
        selectors=["button", "div[role='button']", "div"],
        text_candidates=["Choose an event", "Event"],
    ):
        raise RuntimeError("raw fallback で Choose an event を開けませんでした")
    time.sleep(1.0)
    if not click_first(
        target_id,
        selectors=["button", "div[role='option']", "li[role='option']", "div"],
        text_candidates=["Catch Hook"],
    ):
        raise RuntimeError("raw fallback で Catch Hook を選べませんでした")
    time.sleep(2.0)


def _try_choose_mailchimp_action_raw(target_id: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action_app": None,
        "action_event": None,
        "action_selected": False,
        "post_action_stage": None,
    }
    opened = bool(
        eval_target(
            target_id,
            """(() => {
              const nodes = Array.from(document.querySelectorAll('[data-testid^="step-node-"][role="button"]'));
              const node =
                nodes.find((el) => (el.innerText || '').includes('Select the event for your Zap to run')) ||
                nodes[1] ||
                null;
              if (!node) return false;
              node.click();
              node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }));
              return true;
            })()""",
        )
    )
    if not opened and not click_first(
        target_id,
        selectors=["[data-testid^='step-node-'][role='button']", "button", "div[role='button']", "div"],
        text_candidates=["Add a step", "Action", "Select the event for your Zap to run"],
    ):
        return result
    time.sleep(1.5)
    if not fill_first_input(
        target_id,
        [
            "input[placeholder*='Search apps']",
            "input[aria-label*='Search apps']",
            "input[type='search']",
            "input[type='text']",
        ],
        "Mailchimp",
    ):
        return result
    time.sleep(1.0)
    if not click_first(
        target_id,
        selectors=["button", "div[role='option']", "li[role='option']", "div"],
        text_candidates=["Mailchimp"],
    ):
        return result
    time.sleep(1.5)
    if not click_first(
        target_id,
        selectors=["button", "div[role='button']", "div"],
        text_candidates=["Choose an event", "Event"],
    ):
        return result
    time.sleep(1.0)
    if not click_first(
        target_id,
        selectors=["button", "div[role='option']", "li[role='option']", "div"],
        text_candidates=["Add/Update Subscriber"],
    ):
        return result
    time.sleep(2.0)
    stage = eval_target(
        target_id,
        """(() => {
          const text = document.body ? document.body.innerText : '';
          if (text.includes('Choose account') || text.includes('Add account to continue')) return 'Choose account';
          if (text.includes('Set up action')) return 'Set up action';
          if (text.includes('Test')) return 'Test';
          return null;
        })()""",
    )
    result["action_app"] = "Mailchimp"
    result["action_event"] = "Add/Update Subscriber"
    result["action_selected"] = True
    result["post_action_stage"] = stage
    return result


def _cleanup_exact_via_script(*, edit_path: str | None = None, name: str | None = None) -> dict[str, Any]:
    command = [
        "python3",
        "/Users/koa800/Desktop/cursor/System/scripts/zapier_cleanup_untitled.py",
    ]
    if edit_path:
        command.extend(["--edit-path", edit_path])
    elif name:
        command.extend(["--name", name])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "zapier cleanup failed").strip())
    return json.loads(completed.stdout)


async def _choose_webhook_trigger(page) -> None:
    trigger_opened = False
    trigger_candidates = [
        page.get_by_text("Select the event that starts your Zap", exact=False).first,
        page.get_by_text("Trigger", exact=False).first,
        page.locator("[data-testid^='step-node-'][role='button']").first,
    ]
    for locator in trigger_candidates:
        try:
            if await locator.is_visible(timeout=1200):
                await locator.click(timeout=5000)
                trigger_opened = True
                break
        except Exception:
            continue
    if not trigger_opened:
        raise RuntimeError("Trigger 入口を開けませんでした")

    await page.wait_for_timeout(2500)

    search_filled = False
    search_candidates = [
        page.get_by_role("textbox", name="Search apps"),
        page.locator("input[placeholder*='Search apps']").first,
        page.locator("input[type='search']").first,
        page.locator("input[type='text']").first,
    ]
    for locator in search_candidates:
        try:
            if await locator.is_visible(timeout=1200):
                await locator.fill("Webhooks")
                search_filled = True
                break
        except Exception:
            continue
    if not search_filled:
        raise RuntimeError("Search apps に Webhooks を入れられませんでした")

    await page.wait_for_timeout(1500)

    webhook_selected = False
    webhook_candidates = [
        page.get_by_text("Webhooks by Zapier", exact=False).first,
        page.get_by_text("Webhooks", exact=False).first,
    ]
    for locator in webhook_candidates:
        try:
            if await locator.is_visible(timeout=1200):
                await locator.click(timeout=5000)
                webhook_selected = True
                break
        except Exception:
            continue
    if not webhook_selected:
        raise RuntimeError("Webhooks by Zapier を選べませんでした")

    await page.wait_for_timeout(2500)

    event_opened = False
    event_candidates = [
        page.get_by_text("Choose an event", exact=False).first,
        page.get_by_text("Event", exact=False).first,
        page.get_by_role("button", name="Choose an event").first,
    ]
    for locator in event_candidates:
        try:
            if await locator.is_visible(timeout=1200):
                await locator.click(timeout=5000)
                event_opened = True
                break
        except Exception:
            continue
    if not event_opened:
        raise RuntimeError("Choose an event を開けませんでした")

    await page.wait_for_timeout(1500)

    catch_hook_selected = False
    for locator in [
        page.get_by_text("Catch Hook", exact=False).first,
        page.get_by_role("option", name="Catch Hook").first,
    ]:
        try:
            if await locator.is_visible(timeout=1200):
                await locator.click(timeout=5000)
                catch_hook_selected = True
                break
        except Exception:
            continue
    if not catch_hook_selected:
        raise RuntimeError("Catch Hook を選べませんでした")

    await page.wait_for_timeout(3000)


async def _open_action_picker(page) -> bool:
    # current builder では、2つ目以降の action は `Add a step` を優先して開く。
    # 既存 step node を先に押すと、既存 action の fields を再度開く回がある。
    add_step_candidates = [
        page.locator('[aria-label="Add step"]').first,
        page.get_by_text("Add a step", exact=False).first,
        page.get_by_role("button", name="Add a step").first,
    ]
    for locator in add_step_candidates:
        try:
            if await locator.is_visible(timeout=1000):
                await locator.click(timeout=5000)
                await page.wait_for_timeout(2500)
                return True
        except Exception:
            continue

    # `Add a step` が見えない時だけ、placeholder step node を入口として使う
    try:
        step_nodes = page.locator("[data-testid^='step-node-'][role='button']")
        count = await step_nodes.count()
        for index in range(count):
            node = step_nodes.nth(index)
            try:
                text = (await node.inner_text(timeout=800)).strip()
            except Exception:
                text = ""
            if "Select the event for your Zap to run" in text or "Action" in text:
                await node.click(timeout=5000)
                await page.wait_for_timeout(2500)
                return True
        if count >= 2:
            await step_nodes.nth(1).click(timeout=5000)
            await page.wait_for_timeout(2500)
            return True
    except Exception:
        pass

    action_cta_candidates = [
        page.get_by_text("Action", exact=False).first,
        page.get_by_role("button", name="Action").first,
    ]
    for locator in action_cta_candidates:
        try:
            if await locator.is_visible(timeout=1000):
                await locator.click(timeout=5000)
                await page.wait_for_timeout(2500)
                return True
        except Exception:
            continue
    return False


async def _choose_action_app(page, app_name: str) -> bool:
    query = app_name
    if app_name == "Webhooks by Zapier":
        query = "Webhooks"
    try:
        await page.get_by_role("textbox", name="Search apps").fill(query)
    except Exception:
        try:
            await page.get_by_role("textbox").nth(0).fill(query)
        except Exception:
            return False
    await page.wait_for_timeout(1500)
    try:
        if app_name == "Webhooks by Zapier":
            await page.get_by_text("Webhooks", exact=False).last.click(timeout=10000)
        else:
            await page.get_by_text(app_name, exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)
        return True
    except Exception:
        return False


async def _choose_event(page, event_name: str) -> bool:
    choose_event_candidates = [
        page.get_by_text("Choose an event", exact=False).first,
        page.get_by_text("Event", exact=False).first,
    ]
    opened = False
    for locator in choose_event_candidates:
        try:
            if await locator.is_visible(timeout=1000):
                await locator.click(timeout=5000)
                opened = True
                break
        except Exception:
            continue
    if not opened:
        return False
    await page.wait_for_timeout(1500)
    try:
        await page.get_by_text(event_name, exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)
        return True
    except Exception:
        return False


async def _detect_post_action_stage(page) -> str | None:
    if await page.locator("text=Choose account").first.is_visible(timeout=1200):
        return "Choose account"
    if await page.locator("text=Set up action").first.is_visible(timeout=1200):
        return "Set up action"
    if await page.locator("text=Test").first.is_visible(timeout=1200):
        return "Test"
    return None


async def _try_choose_mailchimp_action(page) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action_app": None,
        "action_event": None,
        "action_selected": False,
        "post_action_stage": None,
    }
    try:
        if not await _open_action_picker(page):
            return result

        if not await _choose_action_app(page, "Mailchimp"):
            return result
        if not await _choose_event(page, "Add/Update Subscriber"):
            return result

        result["action_app"] = "Mailchimp"
        result["action_event"] = "Add/Update Subscriber"
        result["action_selected"] = True
        result["post_action_stage"] = await _detect_post_action_stage(page)
        return result
    except Exception:
        return result


async def _try_choose_webhook_post_first_action(page) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action_app": None,
        "action_event": None,
        "action_selected": False,
        "post_action_stage": None,
    }
    try:
        if not await _open_action_picker(page):
            return result
        if not await _choose_action_app(page, "Webhooks by Zapier"):
            return result
        if not await _choose_event(page, "POST"):
            return result
        result["action_app"] = "Webhooks by Zapier"
        result["action_event"] = "POST"
        result["action_selected"] = True
        result["post_action_stage"] = await _detect_post_action_stage(page)
        return result
    except Exception:
        return result


async def _try_choose_webhook_post_action(page) -> dict[str, Any]:
    result: dict[str, Any] = {
        "second_action_app": None,
        "second_action_event": None,
        "second_action_selected": False,
        "post_second_action_stage": None,
    }
    try:
        if not await _open_action_picker(page):
            return result

        if not await _choose_action_app(page, "Webhooks by Zapier"):
            return result
        if not await _choose_event(page, "POST"):
            return result

        result["second_action_app"] = "Webhooks by Zapier"
        result["second_action_event"] = "POST"
        result["second_action_selected"] = True
        result["post_second_action_stage"] = await _detect_post_action_stage(page)
        return result
    except Exception:
        return result


async def _try_choose_second_action(page, action_app: str) -> dict[str, Any]:
    if action_app == "mailchimp":
        result = await _try_choose_mailchimp_action(page)
        return {
            "second_action_app": result.get("action_app"),
            "second_action_event": result.get("action_event"),
            "second_action_selected": result.get("action_selected"),
            "post_second_action_stage": result.get("post_action_stage"),
        }
    return await _try_choose_webhook_post_action(page)


async def run_probe(
    with_action: bool = False,
    with_second_action: bool = False,
    action_app: str = "mailchimp",
    second_action_app: str = "webhook-post",
) -> dict[str, Any]:
    try:
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError("Playwright.connect_over_cdp timeout") from exc
            if not browser.contexts:
                raise RuntimeError("Chrome CDP に context が見つかりません")
            context = browser.contexts[0]
            page = await context.new_page()
            cleanup_page = await context.new_page()
            try:
                before = await _collect_untitled_rows(cleanup_page)

                await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3000)
                created_title = await page.title()
                header = ""
                for selector in ("text=Untitled Zap", "text=Draft", "text=Trigger"):
                    try:
                        if await page.locator(selector).first.is_visible(timeout=1000):
                            header = selector.replace("text=", "")
                            break
                    except Exception:
                        continue

                await _choose_webhook_trigger(page)

                action_result = {
                    "action_app": None,
                    "action_event": None,
                    "action_selected": False,
                }
                if with_action:
                    if action_app == "webhook-post":
                        action_result = await _try_choose_webhook_post_first_action(page)
                    else:
                        action_result = await _try_choose_mailchimp_action(page)

                second_action_result = {
                    "second_action_app": None,
                    "second_action_event": None,
                    "second_action_selected": False,
                    "post_second_action_stage": None,
                }
                if with_action and with_second_action and action_result.get("action_selected"):
                    second_action_result = await _try_choose_second_action(page, second_action_app)

                created_edit_path = _extract_edit_path(page.url)
                created_row: dict[str, Any]
                if created_edit_path:
                    created_row = {"href": created_edit_path}
                else:
                    created_rows = await _wait_for_new_row(cleanup_page, before)
                    if len(created_rows) != 1:
                        raise RuntimeError("新規 draft の edit_path を一意に特定できませんでした")
                    created_row = created_rows[0]
                after_create = await _collect_untitled_rows(cleanup_page)

                await cleanup_page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
                await cleanup_page.wait_for_timeout(3000)
                row_link = cleanup_page.locator(f'a[href="{created_row["href"]}"]').first
                await row_link.scroll_into_view_if_needed()
                row = row_link.locator("xpath=ancestor::tr[1]")
                menu_button = row.get_by_role("button", name="Zap actions")
                await menu_button.click(timeout=5000)
                await cleanup_page.get_by_role("menuitem", name="Delete").click(timeout=5000)
                await cleanup_page.get_by_role("button", name="Delete").click(timeout=5000)
                await cleanup_page.wait_for_timeout(3000)

                after_delete = await _collect_untitled_rows(cleanup_page)
                return {
                    "mode": "playwright",
                    "created_title": created_title,
                    "builder_marker": header,
                    "created_edit_path": created_row.get("href"),
                    "before_count": len(before),
                    "after_open_count": len(after_create),
                    "persisted_after_open": True,
                    "trigger_app": "Webhooks by Zapier",
                    "trigger_event": "Catch Hook",
                    **action_result,
                    **second_action_result,
                    "after_delete_count": len(after_delete),
                    "deleted": len(after_delete) == len(before),
                }
            finally:
                await page.close()
                await cleanup_page.close()
    except RuntimeError as exc:
        if "connect_over_cdp timeout" not in str(exc):
            raise
        before = _collect_untitled_rows_raw()
        target_id = _open_create_target_raw()
        title = eval_target(target_id, "document.title") or ""
        marker = eval_target(
            target_id,
            """(() => {
              const text = document.body ? document.body.innerText : '';
              if (text.includes('Trigger')) return 'Trigger';
              if (text.includes('Draft')) return 'Draft';
              if (text.includes('Untitled Zap')) return 'Untitled Zap';
              return '';
            })()""",
        ) or ""
        _choose_webhook_trigger_raw(target_id)
        action_result = {
            "action_app": None,
            "action_event": None,
            "action_selected": False,
            "post_action_stage": None,
        }
        if with_action:
            if action_app == "webhook-post":
                action_result = {
                    "action_app": None,
                    "action_event": None,
                    "action_selected": False,
                    "post_action_stage": None,
                }
            else:
                action_result = _try_choose_mailchimp_action_raw(target_id)
        second_action_result = {
            "second_action_app": None,
            "second_action_event": None,
            "second_action_selected": False,
            "post_second_action_stage": None,
        }
        current_snapshot = body_snapshot(target_id)
        created_edit_path = _extract_edit_path(str(current_snapshot.get("url") or ""))
        if created_edit_path:
            created_row = {"href": created_edit_path}
        else:
            created_rows = _wait_for_new_row_raw(before)
            if len(created_rows) != 1:
                raise RuntimeError("raw fallback で新規 draft の edit_path を一意に特定できませんでした")
            created_row = created_rows[0]
        after_create = _collect_untitled_rows_raw()
        cleanup = _cleanup_exact_via_script(edit_path=created_row.get("href"))
        return {
            "mode": "raw",
            "created_title": title,
            "builder_marker": marker,
            "created_edit_path": created_row.get("href"),
            "before_count": len(before),
            "after_open_count": len(after_create),
            "persisted_after_open": True,
            "trigger_app": "Webhooks by Zapier",
            "trigger_event": "Catch Hook",
            **action_result,
            **second_action_result,
            "after_delete_count": cleanup.get("after_count"),
            "deleted": cleanup.get("clean", False),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier exploratory draft create/delete probe")
    parser.add_argument("--with-action", action="store_true", help="Mailchimp Add/Update Subscriber まで試す")
    parser.add_argument("--with-second-action", action="store_true", help="2つ目の action として Webhooks POST まで試す")
    parser.add_argument(
        "--action-app",
        choices=["mailchimp", "webhook-post"],
        default="mailchimp",
        help="最初の action として選ぶ app/event",
    )
    parser.add_argument(
        "--second-action-app",
        choices=["mailchimp", "webhook-post"],
        default="webhook-post",
        help="2つ目の action として選ぶ app/event",
    )
    args = parser.parse_args()
    login_status = ensure_zapier_login(ASSETS_URL)
    if login_status == 2:
        raise SystemExit("Zapier browser session is not ready. CDP connection timed out.")
    if login_status != 0:
        raise SystemExit("Zapier browser session is not ready. Complete login first.")
    result = asyncio.run(
        run_probe(
            with_action=args.with_action,
            with_second_action=args.with_second_action,
            action_app=args.action_app,
            second_action_app=args.second_action_app,
        )
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
