#!/usr/bin/env python3
"""Zapier の 2つ目 action 入口を探索して cleanup する。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
import json
from typing import Any

from playwright.async_api import async_playwright

from zapier_create_delete_probe import CREATE_URL
from zapier_create_delete_probe import _choose_webhook_trigger
from zapier_create_delete_probe import _cleanup_exact_via_script
from zapier_create_delete_probe import _collect_untitled_rows
from zapier_create_delete_probe import _extract_edit_path
from zapier_create_delete_probe import _open_action_picker
from zapier_create_delete_probe import _try_choose_webhook_post_first_action
from zapier_create_delete_probe import _wait_for_new_row


CDP_URL = "http://127.0.0.1:9224"


async def _collect_ui_markers(page) -> dict[str, Any]:
    step_nodes: list[str] = []
    nodes = page.locator("[data-testid^='step-node-'][role='button']")
    for i in range(await nodes.count()):
        try:
            text = (await nodes.nth(i).inner_text(timeout=1000)).strip()
        except Exception:
            text = ""
        if text:
            step_nodes.append(text)

    buttons: list[str] = []
    btns = page.locator("button")
    for i in range(min(await btns.count(), 60)):
        try:
            text = (await btns.nth(i).inner_text(timeout=500)).strip()
        except Exception:
            text = ""
        if text:
            buttons.append(text)

    body = await page.locator("body").inner_text(timeout=3000)
    body_markers = []
    for key in [
        "Add a step",
        "Action",
        "Choose an event",
        "Choose account",
        "Add account to continue",
        "Set up action",
        "Test",
        "Publish",
    ]:
        if key in body:
            body_markers.append(key)

    return {
        "url": page.url,
        "step_nodes": step_nodes,
        "buttons": buttons,
        "body_markers": body_markers,
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
            await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)

            await _choose_webhook_trigger(page)
            first_action = await _try_choose_webhook_post_first_action(page)

            created_edit_path = _extract_edit_path(page.url)
            if not created_edit_path:
                created_rows = await _wait_for_new_row(cleanup_page, before)
                if len(created_rows) == 1:
                    created_edit_path = created_rows[0]["href"]

            before_second = await _collect_ui_markers(page)
            second_picker_opened = await _open_action_picker(page)
            if second_picker_opened:
                await page.wait_for_timeout(2500)
            after_second = await _collect_ui_markers(page)

            return {
                "first_action": first_action,
                "created_edit_path": created_edit_path,
                "before_second": before_second,
                "second_picker_opened": second_picker_opened,
                "after_second": after_second,
            }
        finally:
            if created_edit_path:
                try:
                    _cleanup_exact_via_script(edit_path=created_edit_path)
                except Exception:
                    pass
            with suppress(Exception):
                await page.close()
            with suppress(Exception):
                await cleanup_page.close()


def main() -> None:
    result = asyncio.run(asyncio.wait_for(run_probe(), timeout=90))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
