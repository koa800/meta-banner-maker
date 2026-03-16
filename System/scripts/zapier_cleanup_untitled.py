#!/usr/bin/env python3
"""Zapier assets 一覧の Untitled Zap draft を削除する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"


async def _count(page) -> int:
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    return await page.locator('a[href*="/webintent/edit-zap/"]', has_text="Untitled Zap").count()


async def _delete_one(page) -> bool:
    row_link = page.locator('a[href*="/webintent/edit-zap/"]', has_text="Untitled Zap").first
    if not await row_link.count():
        return False
    await row_link.scroll_into_view_if_needed()
    row = row_link.locator("xpath=ancestor::tr[1]")
    menu_button = row.get_by_role("button", name="Zap actions")
    await menu_button.click(timeout=5000)
    await page.get_by_role("menuitem", name="Delete").click(timeout=5000)
    await page.get_by_role("button", name="Delete").click(timeout=5000)
    await page.wait_for_timeout(3000)
    return True


async def run_cleanup() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            before = await _count(page)
            deleted = 0
            while True:
                current = await _count(page)
                if current == 0:
                    break
                ok = await _delete_one(page)
                if not ok:
                    break
                deleted += 1
            after = await _count(page)
            return {
                "before_count": before,
                "deleted_count": deleted,
                "after_count": after,
                "clean": after == 0,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier Untitled Zap cleanup")
    parser.parse_args()
    result = asyncio.run(run_cleanup())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
