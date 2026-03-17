#!/usr/bin/env python3
"""Zapier の current create から draft を作り、Location を検証する。"""

from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from playwright.async_api import async_playwright

from zapier_create_delete_probe import ASSETS_URL
from zapier_create_delete_probe import _choose_webhook_trigger
from zapier_create_delete_probe import _collect_untitled_rows
from zapier_create_delete_probe import _extract_edit_path
from zapier_create_delete_probe import _wait_for_new_row
from zapier_login_helper import ensure_login as ensure_zapier_login


CDP_URL = "http://127.0.0.1:9224"
FOLDER_NAME = "甲原"
FOLDER_URL = "https://zapier.com/app/assets/zaps/folders/019cdd75-b612-ec46-7e5b-bd8a9015a667"


def _cleanup_exact_via_script(*, edit_path: str | None = None) -> dict[str, Any]:
    command = [
        "python3",
        "/Users/koa800/Desktop/cursor/System/scripts/zapier_cleanup_untitled.py",
    ]
    if edit_path:
        command.extend(["--edit-path", edit_path])
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout or "zapier cleanup failed").strip())
    return json.loads(completed.stdout)


async def _open_folder_create(page) -> None:
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    async def _click(candidates) -> bool:
        for locator in candidates:
            try:
                if await locator.is_visible(timeout=1200):
                    await locator.click(timeout=5000)
                    return True
            except Exception:
                continue
        return False

    create_zap_candidates = [
        page.get_by_role("button", name="Create Zap").first,
        page.locator("button:has-text('Create Zap')").first,
        page.locator("a:has-text('Create Zap')").first,
        page.get_by_role("menuitem", name="Create Zap").first,
    ]
    create_entry_candidates = [
        page.get_by_role("button", name="Create").first,
        page.get_by_role("link", name="Create").first,
        page.locator("button:has-text('Create')").first,
    ]

    clicked = await _click(create_zap_candidates)
    if not clicked:
        opened_menu = await _click(create_entry_candidates)
        if opened_menu:
            await page.wait_for_timeout(1200)
            if "/editor" in page.url or "/webintent/edit-zap/" in page.url:
                clicked = True
            else:
                clicked = await _click(create_zap_candidates)
    if not clicked:
        raise RuntimeError("assets page の `Create` から editor に入れませんでした")
    await page.wait_for_timeout(3000)


async def _asset_meta_for_path(page, edit_path: str) -> dict[str, Any]:
    await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(3000)
    row = page.locator(f'a[href="{edit_path}"]').first.locator("xpath=ancestor::tr[1]")
    cells = row.locator("td")
    values: list[str] = []
    for i in range(await cells.count()):
        try:
            text = (await cells.nth(i).inner_text(timeout=1000)).strip()
        except Exception:
            text = ""
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
        created_edit_path: str | None = None
        try:
            before = await _collect_untitled_rows(cleanup_page)
            await _open_folder_create(page)
            await _choose_webhook_trigger(page)

            created_edit_path = _extract_edit_path(page.url)
            if not created_edit_path:
                created_rows = await _wait_for_new_row(cleanup_page, before)
                if len(created_rows) != 1:
                    raise RuntimeError("新規 draft の edit_path を一意に特定できませんでした")
                created_edit_path = created_rows[0]["href"]

            asset_meta = await _asset_meta_for_path(cleanup_page, created_edit_path)
            return {
                "folder_name": FOLDER_NAME,
                "folder_url": FOLDER_URL,
                "created_edit_path": created_edit_path,
                "asset_meta": asset_meta,
                "location_matches_folder": asset_meta.get("location") == FOLDER_NAME,
            }
        finally:
            if created_edit_path:
                try:
                    _cleanup_exact_via_script(edit_path=created_edit_path)
                except Exception:
                    pass
            try:
                await page.close()
            except Exception:
                pass
            try:
                await cleanup_page.close()
            except Exception:
                pass


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
