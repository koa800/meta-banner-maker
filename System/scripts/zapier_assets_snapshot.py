#!/usr/bin/env python3
"""Zapier assets 一覧の visible rows を JSON で抜く。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
DEFAULT_URL = "https://zapier.com/app/assets/zaps"


async def fetch_assets(limit: int) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(DEFAULT_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)
            raw = await page.evaluate(
                """
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
            )
            raw["rows"] = raw["rows"][:limit]
            return raw
        finally:
            await page.close()
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier assets 一覧の visible rows を JSON 出力する")
    parser.add_argument("--limit", type=int, default=50, help="取得する row 数")
    args = parser.parse_args()
    snapshot = asyncio.run(fetch_assets(args.limit))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
