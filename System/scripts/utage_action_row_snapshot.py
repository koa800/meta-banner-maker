#!/usr/bin/env python3
"""UTAGE アクション一覧の first content row HTML を snapshot する。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/action"


async def run_snapshot() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)
            rows = page.locator("tr")
            target_index = None
            for i in range(await rows.count()):
                text = (await rows.nth(i).inner_text()).strip()
                if text and "編集" in text and "管理名称" not in text:
                    target_index = i
                    break
            if target_index is None:
                raise RuntimeError("対象 row を見つけられませんでした")
            row = rows.nth(target_index)
            html = await row.evaluate("(el) => el.outerHTML")
            text = (await row.inner_text()).strip()
            return {
                "row_index": target_index,
                "text": text,
                "html": html,
            }
        finally:
            await page.close()


def main() -> None:
    result = asyncio.run(run_snapshot())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
