#!/usr/bin/env python3
"""UTAGE の exploratory product を create -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/product"
CREATE_URL = "https://school.addness.co.jp/product/create"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_product_probe"


async def count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            name = build_name()
            before = await count_rows(page, name)

            await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2000)
            await page.get_by_label("商品名").fill(name)
            await page.get_by_role("button", name="保存").click()
            await page.wait_for_timeout(2500)

            after_create = await count_rows(page, name)
            if after_create != before + 1:
                raise RuntimeError("商品追加後に一覧で intended row を確認できませんでした")

            row = page.locator("tr", has_text=name).first
            form = row.locator("form.form-delete").first
            await form.evaluate("(el) => el.submit()")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2500)

            after_delete = await count_rows(page, name)
            return {
                "name": name,
                "before_count": before,
                "after_create_count": after_create,
                "after_delete_count": after_delete,
                "deleted": after_delete == before,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE exploratory product create/delete probe")
    parser.parse_args()
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
