#!/usr/bin/env python3
"""UTAGE の temporary funnel 配下で page の 1変更 -> rollback を検証する。"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

sys.path.insert(0, "/Users/koa800/Desktop/cursor/System/scripts")

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from utage_funnel_create_delete_probe import _create_funnel, _delete_funnel
from utage_login_helper import ensure_login
from utage_page_create_delete_probe import _resolve_page_urls


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/funnel"
PAGE_TITLE = "ZZ_TEST_UTAGE_page_edit_probe"
UPDATED_TITLE = "ZZ_TEST_UTAGE_page_edit_probe_UPDATED"


async def _create_probe_page(page, funnel_id: int) -> dict[str, Any]:
    urls = await _resolve_page_urls(page, funnel_id)
    if not urls["create_url"] or not urls["page_list_url"]:
        raise RuntimeError("temporary funnel の `ページ一覧` または `追加` URL を特定できませんでした")

    await page.goto(urls["create_url"], wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    title_locator = page.locator(
        'input[name="title"], input[name="name"], input[placeholder*="名称"], input[placeholder*="タイトル"]'
    ).first
    await title_locator.fill(PAGE_TITLE)
    await page.get_by_role("button", name="保存").click(timeout=5000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2500)

    created_page = await page.evaluate(
        """(title) => {
  const body = document.body.innerText || '';
  const links = Array.from(document.querySelectorAll('a'))
    .map((a) => ({ text: (a.innerText || '').trim(), href: a.href }))
    .filter((x) => x.text || x.href);
  const errorTexts = Array.from(document.querySelectorAll('.invalid-feedback, .text-danger, .alert, .c-callout, .error, .errors'))
    .map((el) => (el.innerText || '').trim())
    .filter(Boolean);
  return {
    current_url: location.href,
    body_has_title: body.includes(title),
    row_link: links.find((x) => x.text === title) || null,
    edit_link: links.find((x) => x.text === '編集') || null,
    preview_link: links.find((x) => x.text === 'プレビュー') || null,
    error_texts: errorTexts,
  };
}""",
        PAGE_TITLE,
    )
    return {**urls, **created_page}


async def _open_basic_info(page) -> None:
    try:
        modal = page.locator(".modal.show").first
        if await modal.is_visible(timeout=1000):
            close_candidates = [
                modal.locator('[data-dismiss="modal"]').first,
                modal.locator("button.close").first,
                modal.locator(".btn-close").first,
            ]
            closed = False
            for locator in close_candidates:
                try:
                    if await locator.is_visible(timeout=500):
                        await locator.click(timeout=3000)
                        await page.wait_for_timeout(800)
                        closed = True
                        break
                except Exception:
                    continue
            if not closed:
                try:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(800)
                except Exception:
                    pass
    except Exception:
        pass

    await page.get_by_text("ページ設定", exact=False).first.click(timeout=10000, force=True)
    await page.wait_for_timeout(1200)
    await page.get_by_text("基本情報", exact=False).first.click(timeout=10000)
    await page.wait_for_timeout(1200)


async def _set_basic_title(page, next_value: str) -> None:
    await _open_basic_info(page)
    updated = await page.evaluate(
        """(nextValue) => {
  const labels = Array.from(document.querySelectorAll('label'));
  const setValue = (el, value) => {
    const proto = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) descriptor.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const candidates = [];
  for (const label of labels) {
    const text = (label.innerText || '').trim();
    if (!text.includes('ページタイトル') && !text.includes('管理名称') && !text.includes('名称')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') candidates.push(target);
  }
  const fallback = document.querySelectorAll('input[type="text"]');
  for (const input of fallback) candidates.push(input);
  for (const input of candidates) {
    if (!(input instanceof HTMLInputElement)) continue;
    input.focus();
    setValue(input, nextValue);
    return true;
  }
  return false;
}""",
        next_value,
    )
    if not updated:
        raise RuntimeError("ページ設定 > 基本情報 で title 系 input を更新できませんでした")
    await page.locator("#save-basic").click(timeout=10000)
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2000)


async def _read_basic_values(page) -> dict[str, Any]:
    await _open_basic_info(page)
    values = await page.evaluate(
        """() => {
  const labels = Array.from(document.querySelectorAll('label'));
  const out = {};
  for (const label of labels) {
    const text = (label.innerText || '').trim();
    if (!text.includes('ページタイトル') && !text.includes('管理名称') && !text.includes('名称')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') {
      out[text] = target.value || '';
    }
  }
  return out;
}"""
    )
    return values


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError as exc:
            raise RuntimeError("Playwright.connect_over_cdp timeout") from exc
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            funnel_result = await _create_funnel(page)
            probe_page = await _create_probe_page(page, funnel_result["created_id"])
            edit_link = (probe_page.get("edit_link") or {}).get("href")
            if not edit_link:
                raise RuntimeError("作成したページの `編集` URL を特定できませんでした")

            await page.goto(edit_link, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            before_values = await _read_basic_values(page)

            await _set_basic_title(page, UPDATED_TITLE)
            after_values = await _read_basic_values(page)

            await _set_basic_title(page, PAGE_TITLE)
            rollback_values = await _read_basic_values(page)

            deleted = await _delete_funnel(page, funnel_result["created_id"])
            return {
                "mode": "playwright",
                **funnel_result,
                "page_title": PAGE_TITLE,
                "edit_link": edit_link,
                "before_values": before_values,
                "after_values": after_values,
                "rollback_values": rollback_values,
                "deleted": deleted,
            }
        finally:
            await page.close()


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit("UTAGE browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
