#!/usr/bin/env python3
"""UTAGE の Chrome 既存セッションに対して自動ログインを補助する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "System" / "credentials" / "utage.json"
CDP_URL = "http://127.0.0.1:9224"
DEFAULT_TARGET = "https://school.addness.co.jp/funnel"


def load_creds() -> dict:
    return json.loads(CREDS_PATH.read_text())


def is_logged_in(page) -> bool:
    url = page.url
    body = page.locator("body").inner_text()
    logged_in_markers = (
        "ファネル",
        "ページ設定",
        "要素一覧",
        "保存",
        "会員サイト",
        "商品管理",
    )
    return "/login" not in url and "オペレーターログイン" not in body and any(
        marker in body for marker in logged_in_markers
    )


def ensure_login(target_url: str) -> int:
    creds = load_creds()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        if is_logged_in(page):
            print("ALREADY_LOGGED_IN")
            print(page.url)
            return 0

        if "/login" not in page.url:
            page.goto(creds["url"], wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(1500)

        if page.locator('input[type="email"]').count():
            page.locator('input[type="email"]').first.fill(creds["email"])
        elif page.locator('input[name="email"]').count():
            page.locator('input[name="email"]').first.fill(creds["email"])
        else:
            page.locator("input").first.fill(creds["email"])

        page.locator('input[type="password"]').first.fill(creds["password"])
        page.get_by_role("button", name="ログイン").click()
        page.wait_for_timeout(4000)

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        if is_logged_in(page):
            print("LOGIN_SUCCESS")
            print(page.url)
            return 0

        print("LOGIN_NEEDS_MANUAL_CONFIRM")
        print(page.url)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="UTAGE 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
