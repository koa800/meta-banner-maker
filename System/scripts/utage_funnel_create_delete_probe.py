#!/usr/bin/env python3
"""UTAGE の exploratory funnel を create -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/funnel"
CREATE_URL = "https://school.addness.co.jp/funnel/create"


def _extract_funnel_id(text: str) -> int | None:
    match = re.search(r"/funnel/(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


async def _collect_funnel_ids(page) -> list[int]:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    ids = await page.evaluate(
        """
() => {
  const out = [];
  for (const form of Array.from(document.querySelectorAll('form.form-delete'))) {
    const action = form.getAttribute('action') || '';
    const match = action.match(/\\/funnel\\/(\\d+)/);
    if (match) out.push(Number(match[1]));
  }
  return out;
}
"""
    )
    return sorted(set(int(v) for v in ids))


async def _open_blank_detail(page) -> None:
    await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    detail_href = await page.evaluate(
        """
() => {
  const links = Array.from(document.querySelectorAll('a[href*="/detail"]'));
  for (const link of links) {
    const card = link.closest('.card');
    const text = (card?.innerText || '').trim();
    if (text.includes('空白のファネル') && (link.innerText || '').includes('詳細')) {
      return link.href;
    }
  }
  return null;
}
"""
    )
    if not detail_href:
        raise RuntimeError("`空白のファネル > 詳細` の href を取得できませんでした")
    await page.goto(detail_href, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2000)


async def _create_funnel(page) -> dict[str, Any]:
    before_ids = await _collect_funnel_ids(page)

    await _open_blank_detail(page)
    detail_url = page.url
    await page.evaluate("document.querySelector('button.btn-add').form.submit()")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2500)

    after_ids = await _collect_funnel_ids(page)
    new_ids = sorted(set(after_ids) - set(before_ids))
    created_id = None
    if new_ids:
        created_id = new_ids[-1]
    else:
        created_id = _extract_funnel_id(page.url)

    if not created_id:
        raise RuntimeError("追加したファネルIDを特定できませんでした")

    return {
        "before_count": len(before_ids),
        "after_create_count": len(after_ids),
        "detail_url": detail_url,
        "created_url": page.url,
        "created_id": created_id,
    }


async def _delete_funnel(page, funnel_id: int) -> bool:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    form = page.locator(f'form.form-delete[action$="/funnel/{funnel_id}"]').first
    if not await form.count():
        return False
    await form.evaluate("(el) => el.submit()")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2500)
    remaining_ids = await _collect_funnel_ids(page)
    return funnel_id not in remaining_ids


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            created = await _create_funnel(page)
            deleted = await _delete_funnel(page, created["created_id"])
            after_delete_ids = await _collect_funnel_ids(page)
            return {
                **created,
                "after_delete_count": len(after_delete_ids),
                "deleted": deleted,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE exploratory funnel create/delete probe")
    parser.parse_args()
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
