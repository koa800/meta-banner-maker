#!/usr/bin/env python3
"""TikTok Marketing API の access_token をブラウザ認可で再取得する。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System" / "scripts"))

from tiktok_login_helper import DEFAULT_TARGET, ensure_login  # noqa: E402


DEFAULT_AUTH_PATH = ROOT / "System" / "credentials" / "tiktok_marketing_api.json"
TOKEN_ENDPOINT = "https://business-api.tiktok.com/open_api/v1.3/oauth2/access_token/"
CDP_URL = "http://127.0.0.1:9224"
AUTH_CONFIRM_SELECTORS = [
    'button:has-text("Confirm")',
    'button:has-text("Authorize")',
    'button:has-text("Allow")',
    'button:has-text("確認")',
    'button:has-text("許可")',
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_state() -> str:
    return f"codex_refresh_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def build_authorization_url(auth: dict[str, Any], state: str) -> str:
    template = str(auth.get("advertiser_authorization_url") or "").strip()
    if template:
        return template.replace("{state}", state)

    app_id = str(auth.get("app_id") or "").strip()
    redirect_url = str(auth.get("redirect_url") or "").strip()
    if not app_id or not redirect_url:
        raise RuntimeError("TikTok の認可URL生成に必要な app_id または redirect_url がありません")
    return (
        "https://business-api.tiktok.com/portal/auth"
        f"?app_id={app_id}&state={state}&redirect_uri={requests.utils.quote(redirect_url, safe='')}"
    )


def extract_auth_code(final_url: str, expected_state: str) -> tuple[str, str]:
    parsed = urlparse(final_url)
    query = parse_qs(parsed.query)
    state = (query.get("state") or [""])[0]
    if state != expected_state:
        raise RuntimeError(f"state が一致しません: expected={expected_state} actual={state}")

    auth_code = (query.get("auth_code") or query.get("code") or [""])[0]
    if not auth_code:
        raise RuntimeError("認可URLから auth_code を取得できませんでした")
    return auth_code, state


def click_authorize_if_present(page) -> None:
    for selector in AUTH_CONFIRM_SELECTORS:
        locator = page.locator(selector)
        if not locator.count():
            continue
        locator.first.click(timeout=5000)
        page.wait_for_timeout(1500)
        return


def obtain_auth_code_via_browser(auth_url: str, redirect_url: str, state: str) -> tuple[str, str]:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP の context が見つかりません")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(auth_url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)
            click_authorize_if_present(page)
            try:
                page.wait_for_url(f"{redirect_url}*", timeout=120000)
            except PlaywrightTimeoutError as exc:
                raise RuntimeError(f"認可後の redirect を待てませんでした: {page.url}") from exc
            final_url = page.url
            auth_code, _ = extract_auth_code(final_url, state)
            return auth_code, final_url
        finally:
            try:
                page.close()
            except Exception:
                pass


def exchange_auth_code(auth: dict[str, Any], auth_code: str) -> dict[str, Any]:
    response = requests.post(
        TOKEN_ENDPOINT,
        json={
            "app_id": auth["app_id"],
            "secret": auth["app_secret"],
            "auth_code": auth_code,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 0:
        raise RuntimeError(
            f"TikTok token endpoint error: code={payload.get('code')} "
            f"message={payload.get('message')} request_id={payload.get('request_id')}"
        )
    return payload


def update_auth_payload(
    current: dict[str, Any],
    *,
    payload: dict[str, Any],
    auth_code: str,
    state: str,
    final_url: str,
) -> dict[str, Any]:
    data = payload.get("data") or {}
    now_iso = datetime.now().astimezone().isoformat(timespec="seconds")
    updated = dict(current)
    updated["access_token"] = str(data.get("access_token") or "").strip()
    updated["authorized_advertiser_ids"] = [
        str(item).strip() for item in (data.get("advertiser_ids") or []) if str(item).strip()
    ]
    updated["scope"] = data.get("scope") or []
    updated["auth_code_last_used"] = auth_code
    updated["oauth_state_last_used"] = state
    updated["token_obtained_at"] = now_iso
    updated["access_token_request_id"] = str(payload.get("request_id") or "").strip()
    updated["last_authorization_redirect_url"] = final_url

    refresh_token = str(data.get("refresh_token") or "").strip()
    if refresh_token:
        updated["refresh_token"] = refresh_token
        updated["refresh_token_status"] = "browser 再認可で refresh_token を取得"
    else:
        updated["refresh_token"] = ""
        updated["refresh_token_status"] = (
            f"{now_iso} の /open_api/v1.3/oauth2/access_token/ 実レスポンスでも refresh_token は返らなかった。"
            "運用上の正本は browser 再認可スクリプト"
        )

    expires_in = data.get("expires_in")
    updated["access_token_expires_at"] = str(expires_in or "").strip()
    refresh_expires_in = data.get("refresh_expires_in")
    updated["refresh_token_expires_at"] = str(refresh_expires_in or "").strip()
    return updated


def main() -> int:
    parser = argparse.ArgumentParser(description="TikTok Marketing API の access_token を再取得する")
    parser.add_argument(
        "--auth-path",
        default=str(DEFAULT_AUTH_PATH),
        help="Marketing API 認証JSONのパス",
    )
    args = parser.parse_args()

    auth_path = Path(args.auth_path)
    auth = load_json(auth_path)

    redirect_url = str(auth.get("redirect_url") or "").strip()
    if not redirect_url:
        raise RuntimeError("redirect_url が未設定です")

    state = build_state()
    auth_url = build_authorization_url(auth, state)

    ensure_login(DEFAULT_TARGET)

    auth_code, final_url = obtain_auth_code_via_browser(auth_url, redirect_url, state)
    payload = exchange_auth_code(auth, auth_code)
    updated = update_auth_payload(
        auth,
        payload=payload,
        auth_code=auth_code,
        state=state,
        final_url=final_url,
    )
    save_json(auth_path, updated)

    print(f"saved_to={auth_path}")
    print(f"request_id={payload.get('request_id', '')}")
    print(f"advertiser_count={len(updated.get('authorized_advertiser_ids') or [])}")
    print(f"refresh_token_present={'yes' if updated.get('refresh_token') else 'no'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
