#!/usr/bin/env python3
"""UTAGE の exploratory course を create -> edit -> rollback -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
SITE_ID = "BQys60HDeOWP"
LIST_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course"
CREATE_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course/create"
UPDATED_NAME = "ZZ_TEST_UTAGE_course_edit_probe_UPDATED"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_course_edit_probe"


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


async def _create_course(page, name: str) -> None:
    await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    await page.get_by_label("コース名").fill(name)
    await page.get_by_label("管理名称").fill(f"{name}_mg")
    await page.locator("#url").evaluate(
        """(el, value) => {
            el.value = value;
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
        }""",
        "https://example.com/utage-course-edit-probe",
    )
    await page.get_by_role("button", name="保存").click()
    await page.wait_for_timeout(2500)


async def _open_edit_link(page, name: str) -> str:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=name).first
    link = row.locator("a[href*='/edit']").last
    href = await link.get_attribute("href")
    if not href:
        raise RuntimeError("コース一覧の row から edit link を取得できませんでした")
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
    course_name = await page.get_by_label("コース名").input_value()
    manage_name = await page.get_by_label("管理名称").input_value()
    return {"コース名": course_name, "管理名称": manage_name}


async def _set_manage_name(page, next_value: str) -> None:
    field = page.get_by_label("管理名称")
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
            await _create_course(page, name)
            after_create_count = await _count_rows(page, name)
            edit_url = await _open_edit_link(page, name)
            before_values = await _read_values(page)
            await _set_manage_name(page, UPDATED_NAME)
            after_values = await _read_values(page)
            await _set_manage_name(page, f"{name}_mg")
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
