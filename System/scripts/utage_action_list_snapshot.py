#!/usr/bin/env python3
"""UTAGE のアクション設定一覧から exact な一覧情報を抜く。"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urljoin

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

            add_href = None
            add_locator = page.locator("a", has_text="追加").first
            if await add_locator.count():
                add_href = await add_locator.get_attribute("href")

            rows = page.locator("tr")
            visible_rows: list[dict[str, Any]] = []
            for i in range(await rows.count()):
                row = rows.nth(i)
                text = (await row.inner_text()).strip()
                if not text:
                    continue
                if "アクション名" in text and "編集" in text:
                    continue
                links = row.locator("a")
                row_links = []
                for j in range(await links.count()):
                    link = links.nth(j)
                    label = (await link.inner_text()).strip()
                    href = await link.get_attribute("href")
                    if not label and not href:
                        continue
                    row_links.append(
                        {
                            "label": label,
                            "href": urljoin(LIST_URL, href) if href else None,
                        }
                    )
                visible_rows.append(
                    {
                        "text": text,
                        "links": row_links,
                    }
                )
                if len(visible_rows) >= 10:
                    break

            return {
                "title": await page.title(),
                "url": page.url,
                "add_href": urljoin(LIST_URL, add_href) if add_href else None,
                "rows": visible_rows,
            }
        finally:
            await page.close()


def main() -> None:
    result = asyncio.run(run_snapshot())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
