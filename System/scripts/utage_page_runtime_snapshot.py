#!/usr/bin/env python3
"""UTAGE の page runtime から page data を JSON で抜く。"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"


async def fetch_snapshot(url: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2500)
            data = await page.evaluate(
                """
() => {
  const out = {
    title: document.title,
    url: location.href,
    page: null,
    initial_state_keys: [],
  };

  const initialState = window.__INITIAL_STATE__ || null;
  if (initialState && typeof initialState === 'object') {
    out.initial_state_keys = Object.keys(initialState);
  }

  const app = document.getElementById('app');
  const vnodePage =
    app &&
    app.__vue_app__ &&
    app.__vue_app__._container &&
    app.__vue_app__._container._vnode &&
    app.__vue_app__._container._vnode.component &&
    app.__vue_app__._container._vnode.component.data &&
    app.__vue_app__._container._vnode.component.data.page
      ? app.__vue_app__._container._vnode.component.data.page
      : null;

  const candidate = vnodePage || (initialState && initialState.page) || null;
  if (!candidate) return out;

  out.page = {
    id: candidate.id ?? null,
    name: candidate.name ?? null,
    title: candidate.title ?? null,
    is_high_speed_mode: candidate.is_high_speed_mode ?? null,
    first_view_css: candidate.first_view_css ?? null,
    css: candidate.css ?? null,
    js_head: candidate.js_head ?? null,
    js_body_top: candidate.js_body_top ?? null,
    js_body: candidate.js_body ?? null,
    thanks_page_url: candidate.thanks_page_url ?? null,
    redirect_url: candidate.redirect_url ?? null,
  };
  return out;
}
"""
            )
            return data
        finally:
            await page.close()
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE page runtime snapshot")
    parser.add_argument("url", help="公開ページまたは edit 対象の URL")
    args = parser.parse_args()
    snapshot = asyncio.run(fetch_snapshot(args.url))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
