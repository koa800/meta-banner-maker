#!/usr/bin/env python3
"""UTAGE の exploratory page を temporary funnel 配下で create -> rollback する。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any

sys.path.insert(0, "/Users/koa800/Desktop/cursor/System/scripts")

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import body_snapshot
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import navigate_target
from utage_funnel_create_delete_probe import _create_funnel, _delete_funnel
from utage_funnel_create_delete_probe import _find_raw_target_id
from utage_funnel_create_delete_probe import _raw_create_funnel
from utage_funnel_create_delete_probe import _raw_delete_funnel
from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/funnel"
PAGE_TITLE = "ZZ_TEST_UTAGE_page_probe"


async def _resolve_page_urls(page, funnel_id: int) -> dict[str, str]:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    result = await page.evaluate(
        """(createdId) => {
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {
    const del = row.querySelector(`form.form-delete[action$="/funnel/${createdId}"]`);
    if (!del) continue;
    const pageLink = Array.from(row.querySelectorAll('a')).find((a) => (a.innerText || '').trim() === 'ページ一覧');
    const commonLink = Array.from(row.querySelectorAll('a')).find((a) => (a.innerText || '').trim() === '共通設定');
    return {
      page_list_url: pageLink ? pageLink.href : '',
      create_url: pageLink ? pageLink.href.replace(/\\/page$/, '') + '/create' : '',
      edit_url: commonLink ? commonLink.href : '',
    };
  }
  return { page_list_url: '', create_url: '', edit_url: '' };
}""",
        funnel_id,
    )
    return result


def _resolve_page_urls_raw(target_id: str, funnel_id: int) -> dict[str, str]:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    result = eval_target(
        target_id,
        f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    const del = row.querySelector('form.form-delete[action$="/funnel/{funnel_id}"]');
    if (!del) continue;
    const links = Array.from(row.querySelectorAll('a'));
    const pageLink = links.find((a) => ((a.innerText || '').trim()) === 'ページ一覧');
    const commonLink = links.find((a) => ((a.innerText || '').trim()) === '共通設定');
    return {{
      page_list_url: pageLink ? pageLink.href : '',
      create_url: pageLink ? pageLink.href.replace(/\\/page$/, '') + '/create' : '',
      edit_url: commonLink ? commonLink.href : '',
    }};
  }}
  return {{ page_list_url: '', create_url: '', edit_url: '' }};
}})()
""",
    ) or {}
    return result


def _fill_page_title_raw(target_id: str, title: str) -> bool:
    expression = f"""
(() => {{
  const value = {json.dumps(title, ensure_ascii=False)};
  const setValue = (el, next) => {{
    const proto = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {{
    const text = (label.innerText || '').trim();
    if (!text.includes('名称') && !text.includes('ページ名') && !text.includes('タイトル')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') {{
      target.focus();
      setValue(target, value);
      return true;
    }}
  }}
  const fallback = document.querySelector('input[name="title"], input[name="name"], input');
  if (!fallback) return false;
  fallback.focus();
  setValue(fallback, value);
  return true;
}})()
"""
    return bool(eval_target(target_id, expression))


def _click_save_raw(target_id: str) -> bool:
    return bool(
        eval_target(
            target_id,
            """
(() => {
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'));
  for (const button of buttons) {
    const text = (button.innerText || button.value || '').trim();
    if (!text.includes('保存')) continue;
    button.click();
    return true;
  }
  return false;
})()
""",
        )
    )


def _inspect_created_page_raw(target_id: str, title: str) -> dict[str, Any]:
    expression = f"""
(() => {{
  const body = document.body.innerText || '';
  const links = Array.from(document.querySelectorAll('a'))
    .map((a) => ({{ text: (a.innerText || '').trim(), href: a.href }}))
    .filter((x) => x.text || x.href);
  const errorTexts = Array.from(document.querySelectorAll('.invalid-feedback, .text-danger, .alert, .c-callout, .error, .errors'))
    .map((el) => (el.innerText || '').trim())
    .filter(Boolean);
  return {{
    current_url: location.href,
    body_has_title: body.includes({json.dumps(title, ensure_ascii=False)}),
    row_link: links.find((x) => x.text === {json.dumps(title, ensure_ascii=False)}) || null,
    edit_link: links.find((x) => x.text === '編集') || null,
    preview_link: links.find((x) => x.text === 'プレビュー') || null,
    error_texts: errorTexts,
  }};
}})()
"""
    return eval_target(target_id, expression) or {}


def run_probe_raw() -> dict[str, Any]:
    target_id = _find_raw_target_id()
    funnel_result = _raw_create_funnel(target_id)
    urls = _resolve_page_urls_raw(target_id, int(funnel_result["created_id"]))
    if not urls.get("create_url") or not urls.get("page_list_url"):
        raise RuntimeError("raw fallback で temporary funnel の `ページ一覧` または `追加` URL を特定できませんでした")

    navigate_target(target_id, str(urls["create_url"]))
    time.sleep(2.5)
    if not _fill_page_title_raw(target_id, PAGE_TITLE):
        raise RuntimeError("raw fallback で ページ名 を入力できませんでした")
    if not _click_save_raw(target_id):
        raise RuntimeError("raw fallback で 保存 を押せませんでした")
    time.sleep(3)

    created_page = _inspect_created_page_raw(target_id, PAGE_TITLE)
    deleted = _raw_delete_funnel(target_id, int(funnel_result["created_id"]))
    snapshot = body_snapshot(target_id)
    return {
        "mode": "raw",
        **funnel_result,
        **urls,
        "page_title": PAGE_TITLE,
        "page_created": bool(created_page.get("body_has_title")),
        "page_current_url": created_page.get("current_url") or snapshot.get("url") or "",
        "page_row_link": created_page.get("row_link"),
        "page_edit_link": created_page.get("edit_link"),
        "page_preview_link": created_page.get("preview_link"),
        "page_error_texts": created_page.get("error_texts") or [],
        "deleted": deleted,
    }


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError:
            return run_probe_raw()
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            funnel_result = await _create_funnel(page)
            urls = await _resolve_page_urls(page, funnel_result["created_id"])
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

            deleted = await _delete_funnel(page, funnel_result["created_id"])
            return {
                "mode": "playwright",
                **funnel_result,
                **urls,
                "page_title": PAGE_TITLE,
                "page_created": created_page["body_has_title"],
                "page_current_url": created_page["current_url"],
                "page_row_link": created_page["row_link"],
                "page_edit_link": created_page["edit_link"],
                "page_preview_link": created_page["preview_link"],
                "page_error_texts": created_page["error_texts"],
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
