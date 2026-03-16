#!/usr/bin/env python3
"""UTAGE の exploratory action を create -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/action"
CREATE_URL = "https://school.addness.co.jp/action/create"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_action_probe"


async def count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


async def delete_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    deleted = 0
    while await page.locator("tr", has_text=name).count():
        row = page.locator("tr", has_text=name).first
        await row.locator("a[data-toggle='dropdown']").first.click(timeout=5000)
        await page.wait_for_timeout(500)
        form = row.locator("form.form-delete").first
        await form.evaluate("(el) => el.submit()")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2500)
        deleted += 1
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1500)
    return deleted


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        name = build_name()
        try:
            before = await count_rows(page, name)

            await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            await page.get_by_label("管理用名称").fill(name)
            await page.locator('select[name="detail[0][type]"]').first.select_option("webhook")
            await page.locator('input[name="detail[0][url]"]').first.fill("https://example.com/utage-action-probe")
            await page.locator('input[name="detail[0][data][0][name]"]').first.fill("source")
            await page.locator('input[name="detail[0][data][0][value]"]').first.fill("utage_action_probe")
            await page.get_by_role("button", name="保存").click()
            await page.wait_for_timeout(2500)

            error_texts: list[str] = []
            error_locator = page.locator(".invalid-feedback, .help-block-error, .error, .text-danger")
            for i in range(await error_locator.count()):
                text = (await error_locator.nth(i).inner_text()).strip()
                if text:
                    error_texts.append(text)

            after_create = await count_rows(page, name)
            deleted = await delete_rows(page, name)
            after_delete = await count_rows(page, name)

            return {
                "name": name,
                "before_count": before,
                "after_create_count": after_create,
                "after_delete_count": after_delete,
                "deleted_rows": deleted,
                "save_url": page.url,
                "error_texts": error_texts,
            }
        finally:
            await page.close()


def main() -> None:
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
