#!/usr/bin/env python3
"""UTAGE の exploratory lesson を create -> edit -> rollback -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright

from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
SITE_ID = "BQys60HDeOWP"
COURSE_ID = "9cc2NZYZVTap"
LIST_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course/{COURSE_ID}/lesson"
CREATE_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course/{COURSE_ID}/lesson/create"
UPDATED_NAME = "ZZ_TEST_UTAGE_lesson_edit_probe_UPDATED"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_lesson_edit_probe"


async def _count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


async def _delete_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    deleted = 0
    while await page.locator("tr", has_text=name).count():
        row = page.locator("tr", has_text=name).first
        form = row.locator("form.form-delete").first
        await form.evaluate("(el) => el.submit()")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2500)
        deleted += 1
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1500)
    return deleted


async def _create_lesson(page, name: str) -> None:
    await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    group = page.locator("#lesson_group_id").first
    values = await group.locator("option").evaluate_all(
        "(els) => els.map((el) => ({ value: el.value, text: (el.innerText || '').trim() }))"
    )
    first_valid = next((item["value"] for item in values if item["value"] and item["value"] != "0"), None)
    if first_valid:
        await group.select_option(first_valid)
    await page.get_by_label("レッスン名").fill(name)
    contents = page.locator('textarea[name="contents"]').first
    if await contents.count():
        await contents.evaluate(
            """(el, value) => {
                el.value = value;
                el.dispatchEvent(new Event('input', { bubbles: true }));
                el.dispatchEvent(new Event('change', { bubbles: true }));
            }""",
            "<p>ZZ lesson edit probe</p>",
        )
    await page.get_by_role("button", name="保存").click()
    await page.wait_for_timeout(2500)


async def _open_edit_link(page, name: str) -> str:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=name).first
    link = row.locator('a[href*="/edit"]').last
    href = await link.get_attribute("href")
    if not href:
        raise RuntimeError("レッスン一覧の row から edit link を取得できませんでした")
    edit_url = href if href.startswith("http") else f"https://school.addness.co.jp{href}"
    await page.goto(edit_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return edit_url


async def _save(page) -> None:
    candidates = [
        page.locator("#save-basic"),
        page.get_by_role("button", name="保存", exact=True),
        page.get_by_role("button", name="保存"),
    ]
    for locator in candidates:
        try:
            if await locator.first.is_visible(timeout=800):
                await locator.first.click(timeout=5000)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)
                return
        except Exception:
            continue
    raise RuntimeError("保存 ボタンを確定できませんでした")


async def _read_values(page) -> dict[str, Any]:
    lesson_name = await page.get_by_label("レッスン名").input_value()
    return {"レッスン名": lesson_name}


async def _set_lesson_name(page, next_value: str) -> None:
    field = page.get_by_label("レッスン名")
    await field.fill(next_value)
    await page.wait_for_timeout(300)
    await _save(page)


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        name = build_name()
        try:
            before_count = await _count_rows(page, name)
            await _create_lesson(page, name)
            after_create_count = await _count_rows(page, name)
            edit_url = await _open_edit_link(page, name)
            before_values = await _read_values(page)
            await _set_lesson_name(page, UPDATED_NAME)
            after_values = await _read_values(page)
            await _set_lesson_name(page, name)
            rollback_values = await _read_values(page)
            deleted_rows = await _delete_rows(page, name)
            after_delete_count = await _count_rows(page, name)
            return {
                "mode": "playwright",
                "before_count": before_count,
                "after_create_count": after_create_count,
                "edit_url": edit_url,
                "before_values": before_values,
                "after_values": after_values,
                "rollback_values": rollback_values,
                "deleted_rows": deleted_rows,
                "after_delete_count": after_delete_count,
            }
        finally:
            await page.close()


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit(1)
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
