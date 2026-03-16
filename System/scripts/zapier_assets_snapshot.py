#!/usr/bin/env python3
"""Zapier assets 一覧の visible rows を JSON で抜く。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target


CDP_URL = "http://127.0.0.1:9224"
DEFAULT_URL = "https://zapier.com/app/assets/zaps"


ASSETS_EXPRESSION = """
() => {
  const columns = ["Name", "Apps", "Location", "Last modified", "Status", "Owner"];
  const rows = [];
  const seen = new Set();
  const links = Array.from(document.querySelectorAll('a[href*="/webintent/edit-zap/"]'));
  for (const link of links) {
    const name = (link.textContent || "").trim();
    const href = link.getAttribute('href') || '';
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const idMatch = href.match(/\\/webintent\\/edit-zap\\/(\\d+)/);
    const row = link.closest('tr');
    const cells = row ? Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim()) : [];
    rows.push({
      name,
      zap_id: idMatch ? idMatch[1] : null,
      edit_path: href,
      location: cells[2] || '',
      last_modified: cells[3] || '',
      status: cells[4] || '',
      owner: cells[5] || '',
    });
  }
  return {
    title: document.title,
    columns,
    rows,
  };
}
"""


def _find_raw_target_id() -> str:
    target = find_target(url_contains="zapier.com/app/assets/zaps") or find_target(url_contains="zapier.com")
    if target is None:
        target = create_target(DEFAULT_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    return target_id


def _fetch_assets_raw(limit: int) -> dict[str, Any]:
    target_id = _find_raw_target_id()
    navigate_target(target_id, DEFAULT_URL)
    time.sleep(2.5)
    raw = eval_target(target_id, f"({ASSETS_EXPRESSION})()") or {}
    raw["mode"] = "raw"
    raw["rows"] = (raw.get("rows") or [])[:limit]
    return raw


async def fetch_assets(limit: int) -> dict[str, Any]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
            if not browser.contexts:
                raise RuntimeError("Chrome CDP に context が見つかりません")
            context = browser.contexts[0]
            page = await context.new_page()
            try:
                await page.goto(DEFAULT_URL, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3000)
                raw = await page.evaluate(ASSETS_EXPRESSION)
                raw["mode"] = "playwright"
                raw["rows"] = raw["rows"][:limit]
                return raw
            finally:
                await page.close()
                await browser.close()
    except PlaywrightTimeoutError:
        return _fetch_assets_raw(limit)


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier assets 一覧の visible rows を JSON 出力する")
    parser.add_argument("--limit", type=int, default=50, help="取得する row 数")
    args = parser.parse_args()
    snapshot = asyncio.run(fetch_assets(args.limit))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
