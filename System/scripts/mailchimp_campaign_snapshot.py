#!/usr/bin/env python3
"""Mailchimp の recent regular campaign を要約して JSON で出す。"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
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


def is_relevant_href(href: str) -> bool:
    href = href.strip()
    if not href:
        return False
    if href.startswith("mailto:") or href.startswith("tel:"):
        return False
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
        return False
    return True


def extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'href=["\\\']([^"\\\']+)["\\\']', html, flags=re.I)
    cleaned: list[str] = []
    for href in hrefs:
        href = href.strip()
        if not is_relevant_href(href):
            continue
        if href not in cleaned:
            cleaned.append(href)
    return cleaned


def normalize_visible_url(text: str) -> str:
    normalized = text.strip()
    normalized = normalized.replace(" ", "")
    normalized = normalized.replace("\n", "")
    normalized = normalized.replace("https//", "https://")
    normalized = normalized.replace("http//", "http://")
    return normalized


def extract_link_objects(html: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if not is_relevant_href(href):
            continue
        text = anchor.get_text(" ", strip=True)
        key = (text, href)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "text": text,
                "href": href,
                "type": classify_href(href),
            }
        )
    return rows


def detect_display_url_mismatches(link_objects: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in link_objects:
        text = row.get("text", "")
        href = row.get("href", "")
        if not text or "http" not in text.lower():
            continue
        visible_url = normalize_visible_url(text)
        actual_url = normalize_visible_url(href)
        if visible_url != actual_url:
            rows.append(
                {
                    "visible_text": text,
                    "visible_url_guess": visible_url,
                    "actual_href": href,
                    "type": row.get("type", ""),
                }
            )
    return rows


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


def get_click_details(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/reports/{campaign_id}/click-details")


def get_content(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/campaigns/{campaign_id}/content")


def get_campaign(session: requests.Session, base_url: str, campaign_id: str) -> dict[str, Any]:
    return fetch_json(session, f"{base_url}/campaigns/{campaign_id}")


def summarize_click_details(payload: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in payload.get("urls_clicked", []) or []:
        url = row.get("url") or ""
        if not url:
            continue
        current = grouped.setdefault(
            url,
            {
                "url": url,
                "type": classify_href(url),
                "entry_count": 0,
                "total_clicks": 0,
                "unique_clicks_sum": 0,
                "last_click": row.get("last_click"),
            },
        )
        current["entry_count"] += 1
        current["total_clicks"] += row.get("total_clicks") or 0
        current["unique_clicks_sum"] += row.get("unique_clicks") or 0
        last_click = row.get("last_click")
        if last_click and (not current["last_click"] or last_click > current["last_click"]):
            current["last_click"] = last_click
    return sorted(grouped.values(), key=lambda item: (-item["total_clicks"], item["url"]))


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
        click_details = get_click_details(session, base_url, campaign_id)
        content = get_content(session, base_url, campaign_id)
        html = content.get("html", "")
        hrefs = extract_links(html)
        link_objects = extract_link_objects(html)
        hyperlink_mismatches = detect_display_url_mismatches(link_objects)
        main_href = hrefs[0] if hrefs else ""
        top_clicked_urls = summarize_click_details(click_details)
        main_click = top_clicked_urls[0] if top_clicked_urls else {}
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
                "top_clicked_type": main_click.get("type", "none"),
                "top_clicked_url": main_click.get("url", ""),
                "top_clicked_total_clicks": main_click.get("total_clicks", 0),
                "link_count": len(hrefs),
                "hyperlink_mismatch_count": len(hyperlink_mismatches),
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
    click_details = get_click_details(session, base_url, campaign_id)
    content = get_content(session, base_url, campaign_id)
    html = content.get("html", "")
    hrefs = extract_links(html)
    link_objects = extract_link_objects(html)
    hyperlink_mismatches = detect_display_url_mismatches(link_objects)
    main_href = hrefs[0] if hrefs else ""
    top_clicked_urls = summarize_click_details(click_details)
    main_click = top_clicked_urls[0] if top_clicked_urls else {}
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
        "top_clicked_type": main_click.get("type", "none"),
        "top_clicked_url": main_click.get("url", ""),
        "top_clicked_total_clicks": main_click.get("total_clicks", 0),
        "top_clicked_urls": top_clicked_urls[:10],
        "links": hrefs,
        "links_detailed": link_objects,
        "hyperlink_mismatches": hyperlink_mismatches,
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
