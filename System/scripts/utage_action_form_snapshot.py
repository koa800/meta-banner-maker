#!/usr/bin/env python3
"""UTAGE のアクション設定追加フォームを snapshot する。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
CREATE_URL = "https://school.addness.co.jp/action/create"


async def run_snapshot() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)

            labels = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('label'))
  .map(el => (el.textContent || '').trim())
  .filter(Boolean)
"""
            )
            inputs = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('input, textarea, select')).map(el => ({
  tag: el.tagName.toLowerCase(),
  name: el.getAttribute('name') || '',
  type: el.getAttribute('type') || '',
  placeholder: el.getAttribute('placeholder') || '',
}))
"""
            )
            selects = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('select')).map(el => ({
  name: el.getAttribute('name') || '',
  options: Array.from(el.querySelectorAll('option')).map(opt => ({
    value: opt.getAttribute('value') || '',
    label: (opt.textContent || '').trim(),
  })),
}))
"""
            )
            button_texts = await page.evaluate(
                """
() => Array.from(document.querySelectorAll('button,a'))
  .map(el => (el.textContent || '').trim())
  .filter(Boolean)
"""
            )

            return {
                "title": await page.title(),
                "url": page.url,
                "labels": labels,
                "inputs": inputs,
                "selects": selects,
                "buttons": button_texts[:50],
            }
        finally:
            await page.close()


def main() -> None:
    result = asyncio.run(run_snapshot())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
