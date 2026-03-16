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


def _cleanup_untitled_via_script() -> dict[str, Any]:
    completed = subprocess.run(
        [
            "python3",
            "/Users/koa800/Desktop/cursor/System/scripts/zapier_cleanup_untitled.py",
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "zapier cleanup failed").strip())
    return json.loads(completed.stdout)


async def _choose_webhook_trigger(page) -> None:
    await page.get_by_text("Select the event that starts your Zap", exact=False).first.click(timeout=10000)
    await page.wait_for_timeout(3000)
    await page.get_by_role("textbox", name="Search apps").fill("Webhooks")
    await page.wait_for_timeout(1500)
    await page.get_by_text("Webhooks", exact=False).first.click(timeout=10000)
    await page.wait_for_timeout(3000)
    await page.get_by_text("Choose an event", exact=False).first.click(timeout=10000)
    await page.wait_for_timeout(1500)
    await page.get_by_text("Catch Hook", exact=False).first.click(timeout=10000)
    await page.wait_for_timeout(3000)


async def _try_choose_mailchimp_action(page) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action_app": None,
        "action_event": None,
        "action_selected": False,
        "post_action_stage": None,
    }
    try:
        action_cta_candidates = [
            page.get_by_text("Add a step", exact=False).first,
            page.get_by_text("Action", exact=False).first,
            page.get_by_role("button", name="Action").first,
        ]
        clicked = False
        for locator in action_cta_candidates:
            try:
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            return result

        await page.wait_for_timeout(2500)
        try:
            await page.get_by_role("textbox", name="Search apps").fill("Mailchimp")
        except Exception:
            await page.get_by_role("textbox").nth(0).fill("Mailchimp")
        await page.wait_for_timeout(1500)
        await page.get_by_text("Mailchimp", exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)

        choose_event_candidates = [
            page.get_by_text("Choose an event", exact=False).first,
            page.get_by_text("Event", exact=False).first,
        ]
        for locator in choose_event_candidates:
            try:
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    break
            except Exception:
                continue
        await page.wait_for_timeout(1500)
        await page.get_by_text("Add/Update Subscriber", exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)

        result["action_app"] = "Mailchimp"
        result["action_event"] = "Add/Update Subscriber"
        result["action_selected"] = True
        if await page.locator("text=Choose account").first.is_visible(timeout=1500):
            result["post_action_stage"] = "Choose account"
        elif await page.locator("text=Set up action").first.is_visible(timeout=1500):
            result["post_action_stage"] = "Set up action"
        elif await page.locator("text=Test").first.is_visible(timeout=1500):
            result["post_action_stage"] = "Test"
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
        action_cta_candidates = [
            page.get_by_text("Add a step", exact=False).first,
            page.get_by_text("Action", exact=False).first,
            page.get_by_role("button", name="Action").first,
        ]
        clicked = False
        for locator in action_cta_candidates:
            try:
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    clicked = True
                    break
            except Exception:
                continue
        if not clicked:
            return result

        await page.wait_for_timeout(2500)
        try:
            await page.get_by_role("textbox", name="Search apps").fill("Webhooks")
        except Exception:
            await page.get_by_role("textbox").nth(0).fill("Webhooks")
        await page.wait_for_timeout(1500)
        await page.get_by_text("Webhooks", exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)

        choose_event_candidates = [
            page.get_by_text("Choose an event", exact=False).first,
            page.get_by_text("Event", exact=False).first,
        ]
        for locator in choose_event_candidates:
            try:
                if await locator.is_visible(timeout=1000):
                    await locator.click(timeout=5000)
                    break
            except Exception:
                continue
        await page.wait_for_timeout(1500)
        await page.get_by_text("POST", exact=False).first.click(timeout=10000)
        await page.wait_for_timeout(2500)

        result["second_action_app"] = "Webhooks by Zapier"
        result["second_action_event"] = "POST"
        result["second_action_selected"] = True
        if await page.locator("text=Choose account").first.is_visible(timeout=1500):
            result["post_second_action_stage"] = "Choose account"
        elif await page.locator("text=Set up action").first.is_visible(timeout=1500):
            result["post_second_action_stage"] = "Set up action"
        elif await page.locator("text=Test").first.is_visible(timeout=1500):
            result["post_second_action_stage"] = "Test"
        return result
    except Exception:
        return result


async def run_probe(with_action: bool = False, with_second_action: bool = False) -> dict[str, Any]:
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
                    action_result = await _try_choose_mailchimp_action(page)

                second_action_result = {
                    "second_action_app": None,
                    "second_action_event": None,
                    "second_action_selected": False,
                    "post_second_action_stage": None,
                }
                if with_action and with_second_action and action_result.get("action_selected"):
                    second_action_result = await _try_choose_webhook_post_action(page)

                after_create = await _collect_untitled_rows(cleanup_page)
                if len(after_create) <= len(before):
                    raise RuntimeError("Catch Hook まで選択しても persisted draft が assets 一覧に現れませんでした")

                await cleanup_page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
                await cleanup_page.wait_for_timeout(3000)
                row_link = cleanup_page.locator('a[href*="/webintent/edit-zap/"]', has_text="Untitled Zap").first
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
            action_result = _try_choose_mailchimp_action_raw(target_id)
        second_action_result = {
            "second_action_app": None,
            "second_action_event": None,
            "second_action_selected": False,
            "post_second_action_stage": None,
        }
        after_create = _collect_untitled_rows_raw()
        if len(after_create) <= len(before):
            raise RuntimeError("raw fallback でも persisted draft が assets 一覧に現れませんでした")
        cleanup = _cleanup_untitled_via_script()
        return {
            "mode": "raw",
            "created_title": title,
            "builder_marker": marker,
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
    args = parser.parse_args()
    login_status = ensure_zapier_login(ASSETS_URL)
    if login_status == 2:
        raise SystemExit("Zapier browser session is not ready. CDP connection timed out.")
    if login_status != 0:
        raise SystemExit("Zapier browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe(with_action=args.with_action, with_second_action=args.with_second_action))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
