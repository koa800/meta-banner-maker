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
  const body = document.body.innerText || "";
  const lines = body.split("\\n").map(x => x.trim()).filter(Boolean);
  const columns = ["Name", "Apps", "Location", "Last modified", "Status", "Owner"];
  const rows = [];
  const start = lines.findIndex(line => line === "Name");
  if (start >= 0) {
    let i = start + 6;
    while (i < lines.length) {
      const line = lines[i];
      if (line === "Options" || line === "Create" || line === "Search by name or webhook") {
        i += 1;
        continue;
      }
      if (line === "Loading") {
        i += 1;
        continue;
      }
      if (line === "Trash" || line === "Tables" || line === "Forms" || line === "Chatbots" || line === "Canvases" || line === "Agents") {
        break;
      }
      const name = lines[i];
      const location = lines[i + 1] || "";
      const lastModified = lines[i + 2] || "";
      rows.push({
        name,
        location,
        last_modified: lastModified,
      });
      i += 3;
    }
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
