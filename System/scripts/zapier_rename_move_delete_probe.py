#!/usr/bin/env python3
"""Zapier draft を rename -> Folder=甲原 -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright

from zapier_create_delete_probe import ASSETS_URL
from zapier_create_delete_probe import CREATE_URL
from zapier_create_delete_probe import _choose_webhook_trigger
from zapier_create_delete_probe import _collect_untitled_rows
from zapier_create_delete_probe import _extract_edit_path
from zapier_create_delete_probe import _open_create_from_folder
from zapier_create_delete_probe import _wait_for_new_row
from zapier_login_helper import ensure_login as ensure_zapier_login


CDP_URL = "http://127.0.0.1:9224"
FOLDER_NAME = "甲原"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_Zapier_rename_probe"


async def _rename_draft(page, name: str) -> None:
    candidates = [
        page.get_by_text("Untitled Zap", exact=False).first,
        page.get_by_text("Draft", exact=False).first,
        page.locator("button").filter(has_text="Untitled Zap").first,
    ]
    clicked = False
    for locator in candidates:
        try:
            if await locator.is_visible(timeout=1000):
                await locator.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue
    if not clicked:
        raise RuntimeError("Zap title menu を開けませんでした")
    await page.get_by_text("Rename", exact=False).first.click(timeout=5000)
    await page.wait_for_timeout(1000)
    textbox = page.get_by_role("textbox").first
    await textbox.fill(name)
    await textbox.press("Enter")
    await page.wait_for_timeout(2500)


async def _move_to_folder(page, folder_name: str) -> None:
    details_candidates = [
        page.get_by_role("button", name="Zap details"),
        page.get_by_text("Zap details", exact=False).first,
    ]
    opened = False
    for locator in details_candidates:
        try:
            if await locator.is_visible(timeout=800):
                await locator.click(timeout=5000)
                opened = True
                break
        except Exception:
            continue
    if not opened:
        return
    await page.wait_for_timeout(1000)
    try:
        await page.get_by_text("Folder", exact=False).click(timeout=5000)
        await page.wait_for_timeout(1000)
        await page.get_by_text(folder_name, exact=False).first.click(timeout=5000)
        await page.wait_for_timeout(2500)
    except Exception:
        return


async def _asset_row(page, name: str):
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    row_link = page.locator('a[href*="/webintent/edit-zap/"]', has_text=name).first
    row = row_link.locator("xpath=ancestor::tr[1]")
    return row_link, row


async def _delete_named_row(page, name: str) -> None:
    row_link, row = await _asset_row(page, name)
    await row_link.scroll_into_view_if_needed()
    menu_button = row.get_by_role("button", name="Zap actions")
    await menu_button.click(timeout=5000)
    await page.get_by_role("menuitem", name="Delete").click(timeout=5000)
    await page.get_by_role("button", name="Delete Zap").click(timeout=5000)
    await page.wait_for_timeout(3000)


async def _read_asset_meta(page, name: str) -> dict[str, Any]:
    _, row = await _asset_row(page, name)
    cells = row.locator("td")
    values: list[str] = []
    for i in range(await cells.count()):
        text = (await cells.nth(i).inner_text(timeout=1000)).strip()
        values.append(text)
    return {
        "name": values[0] if len(values) > 0 else "",
        "apps": values[1] if len(values) > 1 else "",
        "location": values[2] if len(values) > 2 else "",
        "last_modified": values[3] if len(values) > 3 else "",
        "status": values[4] if len(values) > 4 else "",
        "owner": values[5] if len(values) > 5 else "",
    }


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        cleanup_page = await context.new_page()
        new_name = build_name()
        try:
            before = await _collect_untitled_rows(cleanup_page)
            await _open_create_from_folder(page)
            await _choose_webhook_trigger(page)
            created_edit_path = _extract_edit_path(page.url)
            if not created_edit_path:
                created_rows = await _wait_for_new_row(cleanup_page, before)
                if len(created_rows) != 1:
                    raise RuntimeError("新規 draft の edit_path を一意に特定できませんでした")
                created_edit_path = created_rows[0]["href"]
            await _rename_draft(page, new_name)
            await _move_to_folder(page, FOLDER_NAME)
            meta = await _read_asset_meta(cleanup_page, new_name)
            await _delete_named_row(cleanup_page, new_name)
            after = await cleanup_page.locator('a[href*="/webintent/edit-zap/"]', has_text=new_name).count()
            return {
                "mode": "playwright",
                "edit_path": created_edit_path,
                "name": new_name,
                "folder": FOLDER_NAME,
                "asset_meta": meta,
                "after_delete_count": after,
                "deleted": after == 0,
            }
        finally:
            await page.close()
            await cleanup_page.close()


def main() -> None:
    login_status = ensure_zapier_login(ASSETS_URL)
    if login_status == 2:
        raise SystemExit("Zapier browser session is not ready. CDP connection timed out.")
    if login_status != 0:
        raise SystemExit("Zapier browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
