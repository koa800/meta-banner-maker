#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import sync_playwright


CDP_URL = "http://127.0.0.1:9224"
LOGIN_URL_PREFIX = "https://manager.linestep.net/account/login"
VISUAL_URL_PREFIX = "https://manager.linestep.net/line/visual"
CHATPLUS_HOST = "app.chatplus.jp"
EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?81[-\s]?)?0?\d{1,4}[-\s]?\d{1,4}[-\s]?\d{3,4}(?!\d)")


@dataclass
class LiveContactResult:
    status: str
    target_url: str
    final_url: str
    expected_member_id: str
    final_member_id: str
    email: str
    phone: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "status": self.status,
            "target_url": self.target_url,
            "final_url": self.final_url,
            "expected_member_id": self.expected_member_id,
            "final_member_id": self.final_member_id,
            "email": self.email,
            "phone": self.phone,
            "message": self.message,
        }


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if digits.startswith("81") and len(digits) >= 11:
        digits = "0" + digits[2:]
    if 10 <= len(digits) <= 11:
        return digits
    return ""


def extract_member_id_from_url(url: str) -> str:
    try:
        return (parse_qs(urlparse(url).query).get("id") or parse_qs(urlparse(url).query).get("member") or [""])[0]
    except Exception:
        return ""


def to_visual_url(url: str) -> str:
    member_id = extract_member_id_from_url(url)
    if member_id:
        return f"{VISUAL_URL_PREFIX}?show=detail&member={member_id}"
    return url


def collect_strings(node: Any) -> list[str]:
    values: list[str] = []
    if isinstance(node, dict):
        for value in node.values():
            values.extend(collect_strings(value))
    elif isinstance(node, list):
        for value in node:
            values.extend(collect_strings(value))
    elif isinstance(node, str):
        stripped = node.strip()
        if stripped:
            values.append(stripped)
    return values


def extract_contacts_from_texts(texts: list[str]) -> tuple[str, str]:
    email = ""
    phone = ""
    for text in texts:
        if not email:
            email_match = EMAIL_RE.search(text)
            if email_match:
                email = email_match.group(0).strip().lower()
        if not phone:
            for match in PHONE_RE.findall(text):
                normalized = normalize_phone(match)
                if normalized:
                    phone = normalized
                    break
        if email and phone:
            break
    return email, phone


def parse_pf_payloads(frame_src_list: list[str]) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for src in frame_src_list:
        try:
            parsed = urlparse(src)
            if CHATPLUS_HOST not in parsed.netloc:
                continue
            pf_raw = (parse_qs(parsed.query).get("pf") or [""])[0]
            if not pf_raw:
                continue
            pf_text = html.unescape(unquote(pf_raw))
            payload = json.loads(pf_text)
            if isinstance(payload, dict):
                payloads.append(payload)
        except Exception:
            continue
    return payloads


def extract_contacts_from_page(page) -> tuple[str, str]:
    iframe_data = page.evaluate(
        """() => Array.from(document.querySelectorAll('iframe')).map((el) => ({
          src: el.src || '',
          title: el.title || ''
        }))"""
    )
    frame_src_list = [str(item.get("src") or "").strip() for item in iframe_data or []]
    payloads = parse_pf_payloads(frame_src_list)
    texts = []
    for payload in payloads:
        texts.extend(collect_strings(payload))
    body_text = page.locator("body").inner_text(timeout=5000)
    if body_text:
        texts.append(body_text)
    return extract_contacts_from_texts(texts)


def lookup_contact(target_url: str, expected_member_id: str = "", wait_ms: int = 5000) -> LiveContactResult:
    visual_url = to_visual_url(target_url)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            return LiveContactResult(
                status="cdp_unavailable",
                target_url=target_url,
                final_url="",
                expected_member_id=expected_member_id,
                final_member_id="",
                email="",
                phone="",
                message="Chrome CDP の context が見つかりません",
            )
        context = browser.contexts[0]
        page = next((item for item in context.pages if item.url == visual_url), None)
        created = page is None
        if page is None:
            page = context.new_page()
        try:
            if created or page.url != visual_url:
                page.goto(visual_url, wait_until="domcontentloaded", timeout=120000)
                page.wait_for_timeout(wait_ms)
            final_url = page.url
            if final_url.startswith(LOGIN_URL_PREFIX):
                return LiveContactResult(
                    status="login_required",
                    target_url=target_url,
                    final_url=final_url,
                    expected_member_id=expected_member_id,
                    final_member_id="",
                    email="",
                    phone="",
                    message="Lステップの live 認証が必要です",
                )
            final_member_id = extract_member_id_from_url(final_url)
            if expected_member_id and final_member_id and final_member_id != expected_member_id:
                return LiveContactResult(
                    status="member_mismatch",
                    target_url=target_url,
                    final_url=final_url,
                    expected_member_id=expected_member_id,
                    final_member_id=final_member_id,
                    email="",
                    phone="",
                    message="表示された会員IDが通知ログの会員IDと一致しません",
                )
            email, phone = extract_contacts_from_page(page)
            if email or phone:
                return LiveContactResult(
                    status="ok",
                    target_url=target_url,
                    final_url=final_url,
                    expected_member_id=expected_member_id,
                    final_member_id=final_member_id,
                    email=email,
                    phone=phone,
                    message="Lステップ詳細ページから連絡先を取得しました",
                )
            return LiveContactResult(
                status="no_contact",
                target_url=target_url,
                final_url=final_url,
                expected_member_id=expected_member_id,
                final_member_id=final_member_id,
                email="",
                phone="",
                message="詳細ページ内にメールアドレスまたは電話番号が見つかりません",
            )
        finally:
            if created:
                page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Lステップ詳細ページから連絡先を live 取得する")
    parser.add_argument("--url", required=True, help="Lステップリンク")
    parser.add_argument("--member-id", default="", help="通知ログ上の LSTEPメンバーID")
    parser.add_argument("--wait-ms", type=int, default=5000, help="ページ描画待機ミリ秒")
    args = parser.parse_args()
    result = lookup_contact(args.url, expected_member_id=args.member_id, wait_ms=args.wait_ms)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
