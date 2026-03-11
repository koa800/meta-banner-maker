#!/usr/bin/env python3
"""Zapier の visible current 一覧から step family を集計する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"


async def fetch_rows(limit: int) -> list[dict[str, Any]]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(3000)
            rows = await page.evaluate(
                """
() => {
  const out = [];
  const seen = new Set();
  const links = Array.from(document.querySelectorAll('a[href*="/webintent/edit-zap/"]'));
  for (const link of links) {
    const name = (link.textContent || '').trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const href = link.getAttribute('href') || '';
    const match = href.match(/\\/webintent\\/edit-zap\\/(\\d+)/);
    const row = link.closest('tr');
    const cells = row ? Array.from(row.querySelectorAll('td')).map(td => (td.innerText || '').trim()) : [];
    out.push({
      name,
      zap_id: match ? match[1] : null,
      location: cells[2] || '',
      last_modified: cells[3] || '',
      status: cells[4] || '',
      owner: cells[5] || '',
    });
  }
  return out;
}
"""
            )
            return rows[:limit]
        finally:
            await page.close()
            await browser.close()


async def fetch_zdl(zap_id: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(
                f"https://zapier.com/editor/{zap_id}/published",
                wait_until="domcontentloaded",
                timeout=120000,
            )
            await page.wait_for_timeout(2500)
            raw = await page.evaluate(
                """
() => {
  const el = document.getElementById('__NEXT_DATA__');
  if (!el) return null;
  const next = JSON.parse(el.textContent);
  return next.props.pageProps?.zap?.current_version?.zdl || null;
}
"""
            )
            return raw or {}
        finally:
            await page.close()
            await browser.close()


async def build_summary(limit: int) -> dict[str, Any]:
    rows = await fetch_rows(limit)
    items: list[dict[str, Any]] = []
    family_counter: Counter[str] = Counter()
    for row in rows:
        zdl = await fetch_zdl(row["zap_id"])
        steps = []
        for step in zdl.get("steps", []):
            params = step.get("params") or {}
            steps.append(
                {
                    "app": step.get("app"),
                    "action": step.get("action"),
                    "type": step.get("type"),
                    "params_keys": sorted(list(params.keys())),
                }
            )
        signature = " -> ".join(f'{s["app"]}:{s["action"]}' for s in steps)
        family_counter[signature] += 1
        items.append(
            {
                "zap_id": row["zap_id"],
                "name": row["name"],
                "location": row["location"],
                "last_modified": row["last_modified"],
                "steps": steps,
                "signature": signature,
            }
        )
    families = [{"signature": sig, "count": count} for sig, count in family_counter.most_common()]
    return {"count": len(items), "families": families, "items": items}


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier visible current の step family を集計する")
    parser.add_argument("--limit", type=int, default=25, help="読む visible row 数")
    args = parser.parse_args()
    summary = asyncio.run(build_summary(args.limit))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
