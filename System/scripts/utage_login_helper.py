#!/usr/bin/env python3
"""UTAGE の Chrome 既存セッションに対して自動ログインを補助する。"""

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
from chrome_raw_cdp import create_target
from chrome_raw_cdp import fill_first_input as raw_fill_first_input
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target


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


def raw_is_logged_in(snapshot: dict) -> bool:
    url = str(snapshot.get("url") or "")
    body = str(snapshot.get("body") or "")
    logged_in_markers = (
        "ファネル",
        "ページ設定",
        "要素一覧",
        "保存",
        "会員サイト",
        "商品管理",
    )
    return "school.addness.co.jp" in url and "/login" not in url and "オペレーターログイン" not in body and any(
        marker in body for marker in logged_in_markers
    )


def ensure_login_raw(target_url: str) -> int:
    creds = load_creds()
    target = (
        find_target(url_contains="school.addness.co.jp")
        or find_target(title_contains="UTAGE")
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
    if "/login" not in current_url:
        navigate_target(target_id, creds["url"])
        time.sleep(2)

    raw_fill_first_input(target_id, ['input[type="email"]', 'input[name="email"]', "input"], creds["email"])
    raw_fill_first_input(target_id, ['input[type="password"]'], creds["password"])
    from chrome_raw_cdp import click_first as raw_click_first

    raw_click_first(target_id, [], ["ログイン"])
    time.sleep(4)

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
        finally:
            try:
                page.close()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description="UTAGE 自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
