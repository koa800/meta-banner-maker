#!/usr/bin/env python3
"""Zapier の exploratory draft を create -> persisted -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"
CREATE_URL = "https://zapier.com/webintent/create-zap?useCase=from-scratch"


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


async def run_probe(with_action: bool = False) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
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

            after_create = await _collect_untitled_rows(cleanup_page)
            if len(after_create) <= len(before):
                raise RuntimeError("Catch Hook まで選択しても persisted draft が assets 一覧に現れませんでした")

            # 先頭の Untitled Zap を exploratory draft とみなして削除する。
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
                "created_title": created_title,
                "builder_marker": header,
                "before_count": len(before),
                "after_open_count": len(after_create),
                "persisted_after_open": True,
                "trigger_app": "Webhooks by Zapier",
                "trigger_event": "Catch Hook",
                **action_result,
                "after_delete_count": len(after_delete),
                "deleted": len(after_delete) == len(before),
            }
        finally:
            await page.close()
            await cleanup_page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier exploratory draft create/delete probe")
    parser.add_argument("--with-action", action="store_true", help="Mailchimp Add/Update Subscriber まで試す")
    args = parser.parse_args()
    result = asyncio.run(run_probe(with_action=args.with_action))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
