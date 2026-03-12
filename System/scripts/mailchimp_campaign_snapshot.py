#!/usr/bin/env python3
"""Mailchimp の recent regular campaign を要約して JSON で出す。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from bs4 import BeautifulSoup
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "System" / "config" / "mailchimp.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def build_session() -> tuple[requests.Session, str]:
    config = load_config()
    api_key = config["api_key"]
    server_prefix = config["server_prefix"]
    session = requests.Session()
    session.auth = ("anystring", api_key)
    session.headers.update({"Content-Type": "application/json"})
    base_url = f"https://{server_prefix}.api.mailchimp.com/3.0"
    return session, base_url


def classify_href(href: str) -> str:
    lowered = href.lower()
    if "skill.addness.co.jp" in lowered:
        return "short.io"
    if "school.addness.co.jp" in lowered:
        return "UTAGE"
    if "liff.line.me" in lowered or "line.me/" in lowered or "liff-gateway.lineml.jp" in lowered:
        return "direct LINE"
    return "other"


def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\\\']([^"\\\']+)["\\\']', html, flags=re.I)
    cleaned: list[str] = []
    for href in hrefs:
        href = href.strip()
        if not href:
            continue
        if href.startswith("mailto:") or href.startswith("tel:"):
            continue
        lowered = href.lower()
        if any(
            blocked in lowered
            for blocked in [
                "fonts.googleapis.com",
                "fonts.gstatic.com",
                "*|archive|*",
                "*|update_profile|*",
                "*|unsub|*",
            ]
        ):
            continue
        if href not in cleaned:
            cleaned.append(href)
    return cleaned


def extract_text_preview(html: str, limit: int = 1200) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[: max(1, limit // 40)]


def fetch_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def get_report(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/reports/{campaign_id}")


def get_content(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/campaigns/{campaign_id}/content")


def get_campaign(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/campaigns/{campaign_id}")


def build_snapshot(limit: int) -> dict[str, Any]:
    session, base_url = build_session()
    campaigns = fetch_json(
        session,
        f"{base_url}/campaigns",
        params={
            "type": "regular",
            "status": "sent",
            "sort_field": "send_time",
            "sort_dir": "DESC",
            "count": limit,
        },
    )
    rows: list[dict[str, Any]] = []
    for campaign in campaigns.get("campaigns", []):
        campaign_id = campaign["id"]
        report = get_report(session, base_url, campaign_id)
        content = get_content(session, base_url, campaign_id)
        html = content.get("html", "")
        hrefs = extract_links(html)
        main_href = hrefs[0] if hrefs else ""
        rows.append(
            {
                "id": campaign_id,
                "title": campaign.get("settings", {}).get("title", ""),
                "subject_line": campaign.get("settings", {}).get("subject_line", ""),
                "send_time": campaign.get("send_time"),
                "emails_sent": report.get("emails_sent"),
                "open_rate": report.get("opens", {}).get("open_rate"),
                "click_rate": report.get("clicks", {}).get("click_rate"),
                "main_cta_type": classify_href(main_href) if main_href else "none",
                "main_cta_href": main_href,
                "link_count": len(hrefs),
                "html_sha1": hashlib.sha1(html.encode("utf-8")).hexdigest(),
            }
        )
    return {
        "count": len(rows),
        "rows": rows,
    }


def build_campaign_detail(campaign_id: str) -> dict[str, Any]:
    session, base_url = build_session()
    campaign = get_campaign(session, base_url, campaign_id)
    report = get_report(session, base_url, campaign_id)
    content = get_content(session, base_url, campaign_id)
    html = content.get("html", "")
    hrefs = extract_links(html)
    main_href = hrefs[0] if hrefs else ""
    return {
        "id": campaign_id,
        "title": campaign.get("settings", {}).get("title", ""),
        "subject_line": campaign.get("settings", {}).get("subject_line", ""),
        "from_name": campaign.get("settings", {}).get("from_name", ""),
        "reply_to": campaign.get("settings", {}).get("reply_to", ""),
        "send_time": campaign.get("send_time"),
        "emails_sent": report.get("emails_sent"),
        "open_rate": report.get("opens", {}).get("open_rate"),
        "click_rate": report.get("clicks", {}).get("click_rate"),
        "main_cta_type": classify_href(main_href) if main_href else "none",
        "main_cta_href": main_href,
        "links": hrefs,
        "text_preview": extract_text_preview(html),
        "html_sha1": hashlib.sha1(html.encode("utf-8")).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp recent regular campaign snapshot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--limit", type=int, help="直近の regular campaign 取得件数")
    group.add_argument("--campaign-id", help="特定 campaign ID の詳細を取得")
    args = parser.parse_args()
    if args.campaign_id:
        snapshot = build_campaign_detail(args.campaign_id)
    else:
        snapshot = build_snapshot(args.limit or 10)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
