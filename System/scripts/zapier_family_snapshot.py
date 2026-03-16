#!/usr/bin/env python3
"""Zapier の visible current 一覧から step family を集計する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target


CDP_URL = "http://127.0.0.1:9224"
ASSETS_URL = "https://zapier.com/app/assets/zaps"
EDITOR_URL_TEMPLATE = "https://zapier.com/editor/{zap_id}/published"

ROWS_EXPRESSION = """
() => {
  const out = [];
  const seen = new Set();
  const links = Array.from(document.querySelectorAll('a[href*="/webintent/edit-zap/"]'));
  for (const link of links) {
    const name = (link.textContent || '').trim();
    if (!name || seen.has(name)) continue;
    seen.add(name);
    const href = link.getAttribute('href') || '';
    const match = href.match(/\/webintent\/edit-zap\/(\d+)/);
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

ZDL_EXPRESSION = """
() => {
  const el = document.getElementById('__NEXT_DATA__');
  if (!el) return null;
  const next = JSON.parse(el.textContent);
  return next.props.pageProps?.zap?.current_version?.zdl || null;
}
"""


def _find_assets_target_id() -> str:
    target = find_target(url_contains="/app/assets/zaps") or find_target(url_contains="zapier.com")
    if target is None:
        target = create_target(ASSETS_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    return target_id


def _fetch_rows_raw(limit: int) -> list[dict[str, Any]]:
    target_id = _find_assets_target_id()
    navigate_target(target_id, ASSETS_URL)
    time.sleep(2.5)
    rows = eval_target(target_id, f"({ROWS_EXPRESSION})()") or []
    return rows[:limit]


def _fetch_zdl_raw(zap_id: str) -> dict[str, Any]:
    target = find_target(url_contains=f"/editor/{zap_id}/published") or find_target(url_contains=f"/webintent/edit-zap/{zap_id}")
    if target is None:
        target = create_target(EDITOR_URL_TEMPLATE.format(zap_id=zap_id))
    target_id = str(target["id"])
    activate_target(target_id)
    navigate_target(target_id, EDITOR_URL_TEMPLATE.format(zap_id=zap_id))
    time.sleep(2.5)
    return eval_target(target_id, f"({ZDL_EXPRESSION})()") or {}


async def fetch_rows(limit: int) -> list[dict[str, Any]]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
            if not browser.contexts:
                raise RuntimeError("Chrome CDP に context が見つかりません")
            context = browser.contexts[0]
            page = await context.new_page()
            try:
                await page.goto(ASSETS_URL, wait_until="domcontentloaded", timeout=120000)
                await page.wait_for_timeout(3000)
                rows = await page.evaluate(ROWS_EXPRESSION)
                return rows[:limit]
            finally:
                await page.close()
                await browser.close()
    except PlaywrightTimeoutError:
        return _fetch_rows_raw(limit)


async def fetch_zdl(zap_id: str) -> dict[str, Any]:
    try:
        async with async_playwright() as p:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
            if not browser.contexts:
                raise RuntimeError("Chrome CDP に context が見つかりません")
            context = browser.contexts[0]
            page = await context.new_page()
            try:
                await page.goto(
                    EDITOR_URL_TEMPLATE.format(zap_id=zap_id),
                    wait_until="domcontentloaded",
                    timeout=120000,
                )
                await page.wait_for_timeout(2500)
                raw = await page.evaluate(ZDL_EXPRESSION)
                return raw or {}
            finally:
                await page.close()
                await browser.close()
    except PlaywrightTimeoutError:
        return _fetch_zdl_raw(zap_id)


async def build_summary(limit: int) -> dict[str, Any]:
    rows = await fetch_rows(limit)
    items: list[dict[str, Any]] = []
    family_counter: Counter[str] = Counter()
    for row in rows:
        zap_id = row.get("zap_id")
        if not zap_id:
            continue
        zdl = await fetch_zdl(str(zap_id))
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
        signature = " -> ".join(f'{step["app"]}:{step["action"]}' for step in steps)
        family_counter[signature] += 1
        items.append(
            {
                "zap_id": zap_id,
                "name": row.get("name"),
                "location": row.get("location"),
                "last_modified": row.get("last_modified"),
                "steps": steps,
                "signature": signature,
            }
        )
    families = [{"signature": signature, "count": count} for signature, count in family_counter.most_common()]
    return {"count": len(items), "families": families, "items": items}


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier visible current の step family を集計する")
    parser.add_argument("--limit", type=int, default=25, help="読む visible row 数")
    args = parser.parse_args()
    summary = asyncio.run(build_summary(args.limit))
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
