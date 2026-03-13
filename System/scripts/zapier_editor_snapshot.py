#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import re
from typing import Any

from playwright.async_api import async_playwright


REDACT_KEYS = {
    "password",
    "username",
    "authorization",
    "token",
    "api_key",
    "apikey",
    "secret",
    "key",
    "authentication_id",
}


def redact(value: Any, key: str | None = None) -> Any:
    lowered = (key or "").lower()
    if lowered in REDACT_KEYS:
        return "[REDACTED]"
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, key) for v in value]
    if isinstance(value, str):
        if lowered == "url":
            return re.sub(r"([?&](?:token|key|secret|password)=)[^&]+", r"\1[REDACTED]", value, flags=re.I)
        return value
    return value


async def fetch_snapshot(zap_id: str) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9224")
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            await page.goto(f"https://zapier.com/editor/{zap_id}/published", wait_until="networkidle")
            exists = await page.evaluate("() => !!document.getElementById('__NEXT_DATA__')")
            if not exists:
                raise RuntimeError("Zap editor の __NEXT_DATA__ が取得できません")
            raw = await page.evaluate(
                """
() => {
  const next = JSON.parse(document.getElementById('__NEXT_DATA__').textContent);
  const props = next?.props?.pageProps || {};
  const zap = props.zap || null;
  return {
    url: location.href,
    title: document.title,
    page: next?.page || null,
    page_props_keys: Object.keys(props),
    account_id: props.currentAccountId || null,
    user_email: props.userEmail || null,
    access_issue: !zap,
    zap: zap ? {
      id: zap.id,
      title: zap.title,
      is_enabled: zap.is_enabled,
      updated_at: zap.updated_at,
      last_user_change_at: zap.last_user_change_at,
      zdl: zap.current_version?.zdl || null
    } : null
  };
}
"""
            )
            snapshot = {
                "url": raw["url"],
                "title": raw["title"],
                "page": raw["page"],
                "page_props_keys": raw["page_props_keys"],
                "account_id": raw["account_id"],
                "user_email": "[REDACTED]" if raw["user_email"] else None,
                "access_issue": raw["access_issue"],
                "zap": redact(raw["zap"]) if raw["zap"] else None,
            }
            return snapshot
        finally:
            await page.close()
            await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Zapier editor の __NEXT_DATA__ から Zap 定義を安全に抜く")
    parser.add_argument("zap_id", help="Zapier の zap_id")
    args = parser.parse_args()
    snapshot = asyncio.run(fetch_snapshot(args.zap_id))
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
