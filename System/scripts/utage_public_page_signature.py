#!/usr/bin/env python3
"""UTAGE 公開ページの code 署名を JSON で出す。"""

from __future__ import annotations

import argparse
import json
import re
from typing import Any

import requests


STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.I | re.S)
SCRIPT_RE = re.compile(r"<script[^>]*>(.*?)</script>", re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.I)


def fetch_html(url: str) -> tuple[str, str]:
    response = requests.get(url, timeout=60, allow_redirects=True)
    response.raise_for_status()
    return response.text, response.url


def clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def build_signature(html: str, final_url: str) -> dict[str, Any]:
    title_match = TITLE_RE.search(html)
    styles = STYLE_RE.findall(html)
    scripts = SCRIPT_RE.findall(html)
    hrefs = HREF_RE.findall(html)

    liff_urls = [href for href in hrefs if "liff.line.me" in href or "line.me/" in href or "lineml.jp" in href]
    shortio_urls = [href for href in hrefs if "skill.addness.co.jp" in href]

    auto_redirect_patterns = [
        "location.href",
        "location.replace",
        "window.location",
        "setTimeout",
        "liff.line.me",
        "lineml.jp/landing",
    ]
    auto_redirect_hits = []
    for pattern in auto_redirect_patterns:
        if pattern in html:
            auto_redirect_hits.append(pattern)

    head_style_len = len(clean_text(styles[0])) if styles else 0
    body_script_lens = [len(clean_text(script)) for script in scripts]

    return {
        "title": clean_text(title_match.group(1) if title_match else ""),
        "final_url": final_url,
        "has_gtm": "googletagmanager" in html,
        "style_tag_count": len(styles),
        "script_tag_count": len(scripts),
        "first_style_len": head_style_len,
        "liff_url_count": len(liff_urls),
        "shortio_url_count": len(shortio_urls),
        "follow_token_count": html.count("follow=%40"),
        "auto_redirect_hits": auto_redirect_hits,
        "max_script_len": max(body_script_lens) if body_script_lens else 0,
        "sample_liff_url": liff_urls[0] if liff_urls else "",
        "sample_shortio_url": shortio_urls[0] if shortio_urls else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE public page signature")
    parser.add_argument("url", help="UTAGE public page URL")
    args = parser.parse_args()
    html, final_url = fetch_html(args.url)
    print(json.dumps(build_signature(html, final_url), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
