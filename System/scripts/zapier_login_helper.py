#!/usr/bin/env python3
"""Zapier の Chrome 既存セッションに対して自動ログインを補助する。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import body_snapshot
from chrome_raw_cdp import click_first as raw_click_first
from chrome_raw_cdp import create_target
from chrome_raw_cdp import fill_first_input as raw_fill_first_input
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target


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


def raw_is_logged_in(snapshot: dict) -> bool:
    url = str(snapshot.get("url") or "")
    body = str(snapshot.get("body") or "")
    login_markers = [
        "Log in to Zapier",
        "Continue with Google",
        "Password",
        "Email",
    ]
    return "zapier.com" in url and "zapier.com/app/login" not in url and not any(m in body for m in login_markers)


def ensure_login_raw(target_url: str) -> int:
    creds = load_creds()
    target = find_target(url_contains="zapier.com") or find_target(title_contains="Zapier")
    if target is None:
        target = create_target(target_url)

    target_id = str(target["id"])
    activate_target(target_id)
    snapshot = body_snapshot(target_id)
    if raw_is_logged_in(snapshot):
        print("ALREADY_LOGGED_IN_RAW")
        print(snapshot.get("url") or target_url)
        return 0

    current_url = str(snapshot.get("url") or "")
    if "zapier.com/app/login" not in current_url:
        navigate_target(target_id, LOGIN_URL)
        time.sleep(2)

    raw_fill_first_input(
        target_id,
        ['input[type="email"]', 'input[name="email"]', 'input[autocomplete="username"]'],
        creds["email"],
    )
    raw_click_first(target_id, [], ["Continue"])
    time.sleep(1.5)
    raw_fill_first_input(
        target_id,
        ['input[type="password"]', 'input[name="password"]', 'input[autocomplete="current-password"]'],
        creds["password"],
    )
    raw_click_first(target_id, [], ["Log in", "Continue"])
    time.sleep(3)
    navigate_target(target_id, target_url)
    time.sleep(3)
    snapshot = body_snapshot(target_id)
    if raw_is_logged_in(snapshot):
        print("LOGIN_SUCCESS_RAW")
        print(snapshot.get("url") or target_url)
        return 0

    print("LOGIN_NEEDS_MANUAL_CONFIRM")
    print(snapshot.get("url") or target_url)
    return 1


def ensure_login(target_url: str) -> int:
    creds = load_creds()
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError:
            return ensure_login_raw(target_url)
        context = browser.contexts[0]
        page = context.new_page()
        page.set_default_timeout(15000)
        page.set_default_navigation_timeout(60000)
        try:
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
        finally:
            try:
                page.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Zapier 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
