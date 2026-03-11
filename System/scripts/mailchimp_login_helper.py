#!/usr/bin/env python3
"""Mailchimp の Chrome 既存セッションに対して自動ログインを補助する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "System" / "credentials" / "mailchimp_login.json"
CDP_URL = "http://127.0.0.1:9224"
DEFAULT_TARGET = "https://us5.admin.mailchimp.com/customer-journey/"
LOGIN_URL = "https://login.mailchimp.com/"


def load_creds() -> dict:
    return json.loads(CREDS_PATH.read_text())


def is_logged_in(page) -> bool:
    url = page.url
    body = page.locator("body").inner_text()
    return (
        "login.mailchimp.com" not in url
        and "/login/verify/" not in url
        and "Mailchimp Login" not in body
        and "Login verification" not in body
    )


def ensure_login(target_url: str) -> int:
    creds = load_creds()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        if is_logged_in(page):
            print("ALREADY_LOGGED_IN")
            print(page.url)
            return 0

        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(1500)
        page.locator('input[name="username"]').fill(creds["email"])
        page.get_by_role("button", name="Log in").click()
        page.wait_for_timeout(1500)

        if page.locator('input[name="password"]').count():
            page.locator('input[name="password"]').fill(creds["password"])
            page.get_by_role("button", name="Log in").click()
            page.wait_for_timeout(2500)

        if "login/tfa" in page.url or "/login/verify/" in page.url:
            print("LOGIN_NEEDS_TFA")
            print(page.url)
            return 1

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2000)
        if is_logged_in(page):
            print("LOGIN_SUCCESS")
            print(page.url)
            return 0

        print("LOGIN_NEEDS_MANUAL_CONFIRM")
        print(page.url)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Mailchimp 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
