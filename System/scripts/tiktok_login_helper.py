#!/usr/bin/env python3
"""TikTok Ads の Chrome 既存セッションに対して自動ログインを補助する。

- 既存 Chrome CDP(9224) に接続
- TikTok Ads が未ログインなら email/password を自動入力
- CAPTCHA / 2FA が出た場合は、そこまで自動で進めて手動承認待ちにする
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "System" / "credentials" / "tiktok_login.json"
CDP_URL = "http://127.0.0.1:9224"
DEFAULT_TARGET = "https://ads.tiktok.com/i18n/homepage/"
LOGIN_HOST = "ads.tiktok.com"


def load_creds() -> dict:
    return json.loads(CREDS_PATH.read_text())


def is_logged_in(page) -> bool:
    url = page.url
    title = page.title()
    body = page.locator("body").inner_text(timeout=10000)
    return (
        LOGIN_HOST in url
        and "/login/" not in url
        and "Log in to your TikTok for Business account" not in body
        and "TikTok Ads: Log In" not in title
    )


def fill_first(page, selectors: list[str], value: str, timeout: int = 3000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if not locator.count():
            continue
        try:
            locator.first.fill(value, timeout=timeout)
            page.wait_for_timeout(400)
            return True
        except Exception:
            continue
    return False


def click_first(page, selectors: list[str], timeout: int = 3000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if not locator.count():
            continue
        try:
            locator.first.click(timeout=timeout)
            page.wait_for_timeout(800)
            return True
        except Exception:
            continue
    return False


def ensure_login(target_url: str) -> int:
    creds = load_creds()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            print("NO_CONTEXT", flush=True)
            return 1
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(3000)
            if is_logged_in(page):
                print("ALREADY_LOGGED_IN", flush=True)
                print(page.url, flush=True)
                return 0

            page.goto(creds["login_url"], wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)

            email_filled = fill_first(
                page,
                [
                    'input[placeholder="Email"]',
                    'input[type="email"]',
                    'input[name="email"]',
                    'input[autocomplete="username"]',
                ],
                creds["email"],
            )
            password_filled = fill_first(
                page,
                [
                    'input[placeholder="Password"]',
                    'input[type="password"]',
                    'input[name="password"]',
                    'input[autocomplete="current-password"]',
                ],
                creds["password"],
            )
            print(f"EMAIL_FILLED={email_filled}", flush=True)
            print(f"PASSWORD_FILLED={password_filled}", flush=True)

            clicked = click_first(
                page,
                [
                    'button[type="submit"]',
                    'button:has-text("Log in")',
                    'button:has-text("ログイン")',
                ],
                timeout=4000,
            )
            print(f"LOGIN_CLICKED={clicked}", flush=True)
            time.sleep(5)

            page.goto(target_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(4000)
            if is_logged_in(page):
                print("LOGIN_SUCCESS", flush=True)
                print(page.url, flush=True)
                return 0

            print("LOGIN_NEEDS_MANUAL_CONFIRM", flush=True)
            print(page.url, flush=True)
            return 1
        finally:
            try:
                page.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="TikTok Ads 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
