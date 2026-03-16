#!/usr/bin/env python3
"""UTAGE の既存アクション edit 画面から delete 導線を snapshot する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
DEFAULT_URL = "https://school.addness.co.jp/action/sxJIs4cUbbBz/edit"


async def run_snapshot(url: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)
            delete_forms = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('form')).map(form => ({
  action: form.getAttribute('action') || '',
  method: form.getAttribute('method') || '',
  hasDeleteMethod: !!form.querySelector('input[name="_method"][value="DELETE"]'),
  text: (form.innerText || '').trim().slice(0, 200),
})).filter(item => item.hasDeleteMethod || item.text.includes('削除'))
"""
            )
            delete_buttons = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('button,a')).map(el => ({
  tag: el.tagName.toLowerCase(),
  text: (el.textContent || '').trim(),
  href: el.getAttribute('href') || '',
  formaction: el.getAttribute('formaction') || '',
}))
.filter(item => item.text.includes('削除'))
"""
            )
            return {
                "title": await page.title(),
                "url": page.url,
                "delete_forms": delete_forms,
                "delete_buttons": delete_buttons,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE action edit delete snapshot")
    parser.add_argument("--url", default=DEFAULT_URL)
    args = parser.parse_args()
    result = asyncio.run(run_snapshot(args.url))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
