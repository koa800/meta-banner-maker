#!/usr/bin/env python3
"""Zapier assets 一覧の draft を exact 指定または Untitled Zap で削除する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"


async def _count(page, *, name: str | None = None, edit_path: str | None = None) -> int:
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    locator = page.locator('a[href*="/webintent/edit-zap/"]')
    if edit_path:
        locator = page.locator(f'a[href="{edit_path}"]')
    elif name:
        locator = page.locator('a[href*="/webintent/edit-zap/"]', has_text=name)
    return await locator.count()


async def _delete_one(page, *, name: str | None = None, edit_path: str | None = None) -> bool:
    if edit_path:
        row_link = page.locator(f'a[href="{edit_path}"]').first
    elif name:
        row_link = page.locator('a[href*="/webintent/edit-zap/"]', has_text=name).first
    else:
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


async def run_cleanup(*, name: str | None = None, edit_path: str | None = None) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            before = await _count(page, name=name, edit_path=edit_path)
            deleted = 0
            while True:
                current = await _count(page, name=name, edit_path=edit_path)
                if current == 0:
                    break
                ok = await _delete_one(page, name=name, edit_path=edit_path)
                if not ok:
                    break
                deleted += 1
            after = await _count(page, name=name, edit_path=edit_path)
            return {
                "before_count": before,
                "deleted_count": deleted,
                "after_count": after,
                "clean": after == 0,
                "name": name,
                "edit_path": edit_path,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier Untitled Zap cleanup")
    parser.add_argument("--name", help="指定名の Zap だけ削除する")
    parser.add_argument("--edit-path", help="指定 edit_path の Zap だけ削除する")
    args = parser.parse_args()
    result = asyncio.run(run_cleanup(name=args.name, edit_path=args.edit_path))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
