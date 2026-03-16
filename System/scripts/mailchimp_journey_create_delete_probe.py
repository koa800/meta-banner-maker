#!/usr/bin/env python3
"""Mailchimp Journey の exploratory draft を create -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from mailchimp_login_helper import CDP_URL, ensure_login as ensure_mailchimp_login
from mailchimp_tag_helper import get_member, update_tags


AUTOMATIONS_URL = "https://us5.admin.mailchimp.com/customer-journey/"
SAFE_EMAIL = "koa800sea.nifs+1006@gmail.com"


def build_names() -> tuple[str, str]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (
        f"ZZ_TEST_JOURNEY_{stamp}",
        f"zz_test_tag_journey_{stamp}".lower(),
    )


async def _click_first_visible(page, selectors: list[tuple[str, str]], timeout: int = 5000) -> bool:
    for kind, value in selectors:
        try:
            if kind == "role":
                role, name = value.split("::", 1)
                locator = page.get_by_role(role, name=name).first
            else:
                locator = page.locator(value).first
            if await locator.is_visible(timeout=1000):
                await locator.click(timeout=timeout)
                return True
        except Exception:
            continue
    return False


async def _fill_first_visible(page, selectors: list[str], value: str) -> bool:
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if await locator.is_visible(timeout=1000):
                await locator.fill(value, timeout=5000)
                return True
        except Exception:
            continue
    return False


async def _visible_texts(page, selector: str, limit: int = 20) -> list[str]:
    try:
        items = await page.locator(selector).evaluate_all(
            """(nodes, maxItems) => nodes
              .map((node) => (node.innerText || node.textContent || '').trim())
              .filter(Boolean)
              .slice(0, maxItems)""",
            limit,
        )
        return [item for item in items if isinstance(item, str) and item.strip()]
    except Exception:
        return []


async def _open_builder(page) -> None:
    await page.goto(AUTOMATIONS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    clicked = await _click_first_visible(
        page,
        [
            ("role", "button::Build from scratch"),
            ("css", "button:has-text('Build from scratch')"),
            ("css", "a:has-text('Build from scratch')"),
        ],
    )
    if not clicked:
        diagnostics = {
            "url": page.url,
            "title": await page.title(),
            "buttons": await _visible_texts(page, "button"),
            "links": await _visible_texts(page, "a"),
            "headings": await _visible_texts(page, "h1, h2, h3"),
        }
        raise RuntimeError(
            "`Build from scratch` を押せませんでした: "
            + json.dumps(diagnostics, ensure_ascii=False)
        )
    await page.wait_for_timeout(4000)


async def _set_flow_name_and_audience(page, journey_name: str) -> None:
    filled = await _fill_first_visible(
        page,
        [
            "input[placeholder*='Name']",
            "input[name='journeyName']",
            "input[type='text']",
        ],
        journey_name,
    )
    if not filled:
        raise RuntimeError("`Name flow` の入力欄を特定できませんでした")
    await page.wait_for_timeout(1000)

    continued = await _click_first_visible(
        page,
        [
            ("role", "button::Continue"),
            ("css", "button:has-text('Continue')"),
        ],
    )
    if not continued:
        raise RuntimeError("`Audience` へ進む `Continue` を押せませんでした")
    await page.wait_for_timeout(3000)

    # audience は current では 1 つだけの前提が多い。候補があれば選び、なくても Continue を試す。
    await _click_first_visible(
        page,
        [
            ("css", "[role='option']"),
            ("css", "button[role='option']"),
            ("css", "li[role='option']"),
        ],
        timeout=3000,
    )
    await page.wait_for_timeout(1000)

    continued = await _click_first_visible(
        page,
        [
            ("role", "button::Continue"),
            ("css", "button:has-text('Continue')"),
        ],
    )
    if not continued:
        raise RuntimeError("`Choose a trigger` へ進む `Continue` を押せませんでした")
    await page.wait_for_timeout(4000)


async def _set_tag_added_trigger(page, tag_name: str) -> None:
    picked = await _click_first_visible(
        page,
        [
            ("css", "button:has-text('Tag added')"),
            ("css", "div:has-text('Tag added')"),
            ("css", "span:has-text('Tag added')"),
        ],
        timeout=8000,
    )
    if not picked:
        raise RuntimeError("`Tag added` を選べませんでした")
    await page.wait_for_timeout(3000)

    clicked = await _click_first_visible(
        page,
        [
            ("css", "button:has-text('Set a tag')"),
            ("css", "div:has-text('Set a tag')"),
            ("css", "[aria-label='Set a tag']"),
        ],
        timeout=5000,
    )
    if not clicked:
        raise RuntimeError("`Set a tag` を開けませんでした")
    await page.wait_for_timeout(1500)

    filled = await _fill_first_visible(
        page,
        [
            "input[placeholder*='Search']",
            "input[aria-label*='Search']",
            "input[type='search']",
            "input[type='text']",
        ],
        tag_name,
    )
    if not filled:
        raise RuntimeError("tag 検索欄を特定できませんでした")
    await page.wait_for_timeout(1500)

    picked = await _click_first_visible(
        page,
        [
            ("css", f"button:has-text('{tag_name}')"),
            ("css", f"div:has-text('{tag_name}')"),
            ("css", f"span:has-text('{tag_name}')"),
        ],
        timeout=5000,
    )
    if not picked:
        raise RuntimeError("作成済み tag を選べませんでした")
    await page.wait_for_timeout(1000)

    saved = await _click_first_visible(
        page,
        [
            ("role", "button::Save Trigger"),
            ("css", "button:has-text('Save Trigger')"),
        ],
    )
    if not saved:
        raise RuntimeError("`Save Trigger` を押せませんでした")
    await page.wait_for_timeout(4000)


async def _delete_journey(page, journey_name: str) -> bool:
    await page.goto(AUTOMATIONS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(4000)
    row = page.locator(f"text={journey_name}").first
    if not await row.is_visible(timeout=5000):
        return False
    container = row.locator("xpath=ancestor::*[self::tr or self::li or self::div][1]")
    menu = container.get_by_role("button").last
    try:
        await menu.click(timeout=5000)
    except Exception:
        # last button が違う時は、見える候補を総当たり
        clicked = await _click_first_visible(
            container,
            [
                ("role", "button::Actions"),
                ("css", "button[aria-haspopup='menu']"),
                ("css", "button"),
            ],
            timeout=5000,
        )
        if not clicked:
            return False
    await page.wait_for_timeout(1000)
    deleted = await _click_first_visible(
        page,
        [
            ("role", "menuitem::Delete"),
            ("css", "button:has-text('Delete')"),
            ("css", "div[role='menuitem']:has-text('Delete')"),
        ],
    )
    if not deleted:
        return False
    await page.wait_for_timeout(1500)
    confirmed = await _click_first_visible(
        page,
        [
            ("role", "button::Delete flow"),
            ("role", "button::Delete"),
            ("css", "button:has-text('Delete flow')"),
            ("css", "button:has-text('Delete')"),
        ],
    )
    if not confirmed:
        return False
    await page.wait_for_timeout(4000)
    return True


async def run_probe() -> dict[str, Any]:
    journey_name, tag_name = build_names()
    before_member = get_member(SAFE_EMAIL)
    update_tags(SAFE_EMAIL, tag_name, active=True, status_if_new=None)
    tag_active = get_member(SAFE_EMAIL)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Playwright.connect_over_cdp timeout") from exc
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await _open_builder(page)
            await _set_flow_name_and_audience(page, journey_name)
            await _set_tag_added_trigger(page, tag_name)
            url_after_trigger = page.url
            deleted = await _delete_journey(page, journey_name)
            return {
                "journey_name": journey_name,
                "tag_name": tag_name,
                "member_tags_before": before_member.get("tags_count"),
                "member_tags_after_tag_add": tag_active.get("tags_count"),
                "url_after_trigger": url_after_trigger,
                "deleted": deleted,
            }
        finally:
            try:
                update_tags(SAFE_EMAIL, tag_name, active=False, status_if_new=None)
            except Exception:
                pass
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp Journey exploratory create/delete probe")
    parser.parse_args()
    login_status = ensure_mailchimp_login(AUTOMATIONS_URL)
    if login_status == 2:
        raise SystemExit("Mailchimp browser session is not ready. CDP connection timed out.")
    if login_status != 0:
        raise SystemExit("Mailchimp browser session is not ready. Complete login/TFA first.")
    result = asyncio.run(asyncio.wait_for(run_probe(), timeout=180))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
