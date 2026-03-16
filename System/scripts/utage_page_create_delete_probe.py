#!/usr/bin/env python3
"""UTAGE の exploratory page を temporary funnel 配下で create -> rollback する。"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

sys.path.insert(0, "/Users/koa800/Desktop/cursor/System/scripts")

from playwright.async_api import async_playwright

from utage_funnel_create_delete_probe import _create_funnel, _delete_funnel
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


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
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
            await page.locator('input[name="title"]').fill(PAGE_TITLE)
            await page.get_by_role("button", name="保存").click(timeout=5000)
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2500)

            created_page = await page.evaluate(
                """(title) => {
  const body = document.body.innerText || '';
  const links = Array.from(document.querySelectorAll('a'))
    .map((a) => ({ text: (a.innerText || '').trim(), href: a.href }))
    .filter((x) => x.text || x.href);
  return {
    current_url: location.href,
    body_has_title: body.includes(title),
    row_link: links.find((x) => x.text === title) || null,
    edit_link: links.find((x) => x.text === '編集') || null,
    preview_link: links.find((x) => x.text === 'プレビュー') || null,
  };
}""",
                PAGE_TITLE,
            )

            deleted = await _delete_funnel(page, funnel_result["created_id"])
            return {
                **funnel_result,
                **urls,
                "page_title": PAGE_TITLE,
                "page_created": created_page["body_has_title"],
                "page_current_url": created_page["current_url"],
                "page_row_link": created_page["row_link"],
                "page_edit_link": created_page["edit_link"],
                "page_preview_link": created_page["preview_link"],
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
