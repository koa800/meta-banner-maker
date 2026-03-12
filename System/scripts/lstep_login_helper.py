#!/usr/bin/env python3
"""Lステップの Chrome 既存セッションに対して自動ログインを補助する。

- 既存 Chrome CDP(9224) に接続
- ログイン済みなら target URL へ移動
- 未ログインなら ID/PW を自動入力
- reCAPTCHA checkbox iframe を見つけたら OS クリックで checkbox を試す
- ログインボタンが有効化されたら押す

注意:
- 画像 challenge が出た場合は完全自動にならない
- その場合でも「どこまで自動で進めたか」を標準出力に返す
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDS_PATH = ROOT / "System" / "credentials" / "lstep.json"
CDP_URL = "http://127.0.0.1:9224"
DEFAULT_TARGET = "https://manager.linestep.net/line/landing"


def load_creds() -> dict:
    return json.loads(CREDS_PATH.read_text())


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True)


def activate_and_place_chrome() -> bool:
    script = """
tell application "Google Chrome"
  activate
  if (count of windows) > 0 then
    set bounds of front window to {0, 25, 1000, 800}
  end if
end tell
"""
    try:
        run(["osascript", "-e", script])
        return True
    except Exception:
        return False


def try_click_checkbox(page) -> bool:
    frames = page.locator("iframe")
    count = frames.count()
    for i in range(count):
        frame = frames.nth(i)
        title = (frame.get_attribute("title") or "").lower()
        src = (frame.get_attribute("src") or "").lower()
        if "captcha" not in title and "captcha" not in src and "recaptcha" not in title and "recaptcha" not in src:
            continue
        box = frame.bounding_box()
        if not box:
            continue

        window_metrics = page.evaluate(
            """() => ({
                screenX: window.screenX,
                screenY: window.screenY,
                outerHeight: window.outerHeight,
                innerHeight: window.innerHeight
            })"""
        )
        chrome_top = max(0, window_metrics["outerHeight"] - window_metrics["innerHeight"])
        click_x = int(window_metrics["screenX"] + box["x"] + min(40, box["width"] / 2))
        click_y = int(window_metrics["screenY"] + chrome_top + box["y"] + min(40, box["height"] / 2))
        try:
            run(["cliclick", f"c:{click_x},{click_y}"])
            return True
        except Exception:
            return False
    return False


def is_logged_in(page) -> bool:
    body = page.locator("body").inner_text()
    return "ユーザーID・ログインパスワードをお忘れの方はこちら" not in body and "Lステップ" in page.title()


def ensure_login(target_url: str) -> int:
    creds = load_creds()
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.new_page()

        page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)
        if is_logged_in(page):
            print("ALREADY_LOGGED_IN")
            print(page.url)
            return 0

        page.goto(creds["login_url"], wait_until="domcontentloaded", timeout=60000)
        time.sleep(2)

        if page.locator('input[name="account_name"]').count():
            page.locator('input[name="account_name"]').fill(creds["user_id"])
        if page.locator('input[type="password"]').count():
            page.locator('input[type="password"]').fill(creds["password"])

        activated = activate_and_place_chrome()
        print(f"CHROME_ACTIVATED={activated}")
        time.sleep(1)
        clicked = try_click_checkbox(page)
        print(f"CAPTCHA_CLICK_ATTEMPTED={clicked}")

        for _ in range(12):
            buttons = page.locator("button")
            for i in range(buttons.count()):
                text = (buttons.nth(i).inner_text() or "").strip()
                if text == "ログイン" and buttons.nth(i).is_enabled():
                    buttons.nth(i).click()
                    time.sleep(5)
                    page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                    time.sleep(2)
                    if is_logged_in(page):
                        print("LOGIN_SUCCESS")
                        print(page.url)
                        return 0
            time.sleep(1)

        print("LOGIN_NEEDS_MANUAL_CONFIRM")
        print(page.url)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Lステップ自動ログイン補助")
    parser.add_argument("--target", default=DEFAULT_TARGET, help="ログイン後に開く URL")
    args = parser.parse_args()
    return ensure_login(args.target)


if __name__ == "__main__":
    sys.exit(main())
