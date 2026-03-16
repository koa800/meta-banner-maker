#!/usr/bin/env python3
"""UTAGE 商品一覧の exploratory test row を削除する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/product"


async def run_cleanup(pattern: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            before = await page.locator("tr", has_text=pattern).count()
            deleted = 0
            while await page.locator("tr", has_text=pattern).count():
                row = page.locator("tr", has_text=pattern).first
                form = row.locator("form.form-delete").first
                await form.evaluate("(el) => el.submit()")
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2500)
                deleted += 1
                await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(1500)
            after = await page.locator("tr", has_text=pattern).count()
            return {
                "pattern": pattern,
                "before_count": before,
                "deleted_count": deleted,
                "after_count": after,
                "clean": after == 0,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE exploratory product cleanup")
    parser.add_argument("--pattern", default="UTAGE_detail_probe", help="row substring to delete")
    args = parser.parse_args()
    result = asyncio.run(run_cleanup(args.pattern))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
