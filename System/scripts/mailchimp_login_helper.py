#!/usr/bin/env python3
"""Mailchimp の Chrome 既存セッションに対して自動ログインを補助する。"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from datetime import timedelta
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
from mailchimp_tfa_code_helper import wait_for_mailchimp_code


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


def dismiss_cookie_overlay(page) -> None:
    selectors = [
        "#onetrust-accept-btn-handler",
        "button[aria-label='Accept']",
        "button[aria-label='Allow all']",
        "button:has-text('Accept')",
        "button:has-text('Allow all')",
        "button:has-text('I agree')",
    ]
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count():
            try:
                locator.first.click(timeout=2000)
                page.wait_for_timeout(500)
                return
            except Exception:
                continue
    try:
        page.evaluate(
            """
            () => {
              const sdk = document.querySelector('#onetrust-consent-sdk');
              if (sdk) sdk.remove();
              document.querySelectorAll('.onetrust-pc-dark-filter,.ot-fade-in').forEach((el) => el.remove());
            }
            """
        )
    except Exception:
        pass


def click_first(page, selectors: list[str], timeout: int = 3000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if not locator.count():
            continue
        try:
            locator.first.click(timeout=timeout)
            page.wait_for_timeout(600)
            return True
        except Exception:
            continue
    return False


def fill_first(page, selectors: list[str], value: str, timeout: int = 3000) -> bool:
    for selector in selectors:
        locator = page.locator(selector)
        if not locator.count():
            continue
        try:
            locator.first.fill(value, timeout=timeout)
            page.wait_for_timeout(300)
            return True
        except Exception:
            continue
    return False


def try_complete_tfa(page) -> bool:
    if "/login/verify/" not in page.url:
        return False

    sent_at = datetime.now()
    click_first(
        page,
        [
            "button:has-text('Send code via SMS')",
            "button:has-text('Send code')",
        ],
        timeout=2000,
    )
    page.wait_for_timeout(2500)

    code_item = wait_for_mailchimp_code(
        max_days=7,
        max_age_minutes=10080,
        not_before=sent_at - timedelta(minutes=1),
        timeout_seconds=90,
        poll_interval_seconds=5,
    )
    if code_item is None:
        return False

    filled = fill_first(
        page,
        [
            "input[name='code']",
            "input[inputmode='numeric']",
            "input[autocomplete='one-time-code']",
            "input[type='tel']",
            "input[type='text']",
        ],
        code_item.code,
    )
    if not filled:
        return False

    clicked = click_first(
        page,
        [
            "button:has-text('Verify')",
            "button:has-text('Continue')",
            "button:has-text('Log in')",
            "button[type='submit']",
        ],
        timeout=4000,
    )
    if not clicked:
        return False

    page.wait_for_timeout(3000)
    return is_logged_in(page)


def raw_is_logged_in(snapshot: dict) -> bool:
    url = str(snapshot.get("url") or "")
    body = str(snapshot.get("body") or "")
    return (
        "mailchimp.com" in url
        and
        "login.mailchimp.com" not in url
        and "/login/verify/" not in url
        and "/login/tfa" not in url
        and "Mailchimp Login" not in body
        and "Login verification" not in body
        and "2-factor authentication" not in body
    )


def ensure_login_raw(target_url: str) -> int:
    creds = load_creds()
    target = (
        find_target(url_contains="us5.admin.mailchimp.com")
        or find_target(url_contains="login.mailchimp.com")
        or find_target(title_contains="Mailchimp")
    )
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
    if "login.mailchimp.com" not in current_url and "/login/tfa" not in current_url and "/login/verify/" not in current_url:
        navigate_target(target_id, LOGIN_URL)
        time.sleep(2)
        snapshot = body_snapshot(target_id)

    raw_fill_first_input(target_id, ['input[name="username"]'], creds["email"])
    raw_click_first(target_id, [], ["Log in"])
    time.sleep(1.5)
    snapshot = body_snapshot(target_id)

    if 'input[name="password"]' in str(snapshot.get("body") or "") or "Password" in str(snapshot.get("body") or ""):
        raw_fill_first_input(target_id, ['input[name="password"]'], creds["password"])
        raw_click_first(target_id, [], ["Log in"])
        time.sleep(3)
        snapshot = body_snapshot(target_id)

    verify_url = str(snapshot.get("url") or "")
    if "/login/tfa" in verify_url or "/login/verify/" in verify_url or "2-factor authentication" in str(snapshot.get("title") or ""):
        send_clicked = raw_click_first(
            target_id,
            [],
            ["Send code via SMS", "Send code"],
        )
        if send_clicked:
            time.sleep(2.5)
        else:
            time.sleep(1.0)
        code_item = wait_for_mailchimp_code(
            max_days=7,
            max_age_minutes=10080,
            not_before=datetime.now() - timedelta(minutes=1),
            timeout_seconds=90,
            poll_interval_seconds=5,
        )
        if code_item is None:
            print("LOGIN_NEEDS_TFA")
            print(verify_url or target_url)
            return 1
        raw_fill_first_input(
            target_id,
            [
                'input[name="code"]',
                'input[autocomplete="one-time-code"]',
                'input[inputmode="numeric"]',
                'input[type="tel"]',
                'input[type="text"]',
            ],
            code_item.code,
        )
        raw_click_first(target_id, [], ["Verify", "Continue", "Log in"])
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
            page.wait_for_timeout(1500)
            dismiss_cookie_overlay(page)
            page.locator('input[name="username"]').fill(creds["email"])
            page.get_by_role("button", name="Log in").click()
            page.wait_for_timeout(1500)

            if page.locator('input[name="password"]').count():
                dismiss_cookie_overlay(page)
                page.locator('input[name="password"]').fill(creds["password"])
                page.get_by_role("button", name="Log in").click()
                page.wait_for_timeout(2500)

            if "login/tfa" in page.url or "/login/verify/" in page.url:
                if try_complete_tfa(page):
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(2000)
                    if is_logged_in(page):
                        print("LOGIN_SUCCESS")
                        print(page.url)
                        return 0
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
        finally:
            try:
                page.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Mailchimp 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
