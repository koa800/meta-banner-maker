#!/usr/bin/env python3
"""Zapier の Chrome 既存セッションに対して自動ログインを補助する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "System" / "credentials" / "zapier.json"
CDP_URL = "http://127.0.0.1:9224"
DEFAULT_TARGET = "https://zapier.com/app/assets/zaps"
LOGIN_URL = "https://zapier.com/app/login"


def load_creds() -> dict:
    return json.loads(CREDS_PATH.read_text())


def is_logged_in(page) -> bool:
    url = page.url
    body = page.locator("body").inner_text()
    login_markers = [
        "Log in to Zapier",
        "Continue with Google",
        "Password",
        "Email",
    ]
    return "zapier.com/app/login" not in url and not any(m in body for m in login_markers)


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
        page.wait_for_timeout(2000)

        email_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[autocomplete="username"]',
        ]
        password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[autocomplete="current-password"]',
        ]

        filled_email = False
        for selector in email_selectors:
            if page.locator(selector).count():
                page.locator(selector).first.fill(creds["email"])
                filled_email = True
                break

        if not filled_email:
            print("LOGIN_NEEDS_MANUAL_CONFIRM")
            print(page.url)
            return 1

        if page.get_by_role("button", name="Continue").count():
            page.get_by_role("button", name="Continue").first.click()
            page.wait_for_timeout(1500)

        filled_password = False
        for selector in password_selectors:
            if page.locator(selector).count():
                page.locator(selector).first.fill(creds["password"])
                filled_password = True
                break

        if filled_password:
            if page.get_by_role("button", name="Log in").count():
                page.get_by_role("button", name="Log in").first.click()
            elif page.get_by_role("button", name="Continue").count():
                page.get_by_role("button", name="Continue").first.click()
            page.wait_for_timeout(3000)

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
    parser = argparse.ArgumentParser(description="Zapier 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
