#!/usr/bin/env python3
"""Mailchimp の 2段階認証コードを LINE group log から取得する。"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "System" / "line_bot_local" / "config.json"
CODE_PATTERN = re.compile(r"Mailchimp verification code is:\s*(\d{6})", re.IGNORECASE)


@dataclass
class MailchimpVerificationCode:
    code: str
    timestamp: str
    group_id: str
    group_name: str
    raw_text: str


def load_line_bot_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def fetch_group_log(date_str: str) -> dict[str, Any]:
    config = load_line_bot_config()
    base_url = str(config["server_url"]).rstrip("/")
    headers = {"Authorization": f"Bearer {config['agent_token']}"}
    response = requests.get(
        f"{base_url}/api/group-log",
        headers=headers,
        params={"date": date_str},
        timeout=20,
    )
    response.raise_for_status()
    return response.json()


def iter_mailchimp_codes(max_days: int = 7) -> list[MailchimpVerificationCode]:
    hits: list[MailchimpVerificationCode] = []
    today = datetime.now()
    for offset in range(max_days):
        date_str = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        payload = fetch_group_log(date_str)
        for group_id, group_data in (payload.get("groups") or {}).items():
            group_name = str(group_data.get("group_name") or "")
            for message in group_data.get("messages") or []:
                text = str(message.get("text") or "")
                match = CODE_PATTERN.search(text)
                if not match:
                    continue
                hits.append(
                    MailchimpVerificationCode(
                        code=match.group(1),
                        timestamp=str(message.get("timestamp") or ""),
                        group_id=group_id,
                        group_name=group_name,
                        raw_text=text,
                    )
                )
    hits.sort(key=lambda item: item.timestamp, reverse=True)
    return hits


def latest_mailchimp_code(max_days: int = 7, max_age_minutes: int = 30) -> MailchimpVerificationCode | None:
    threshold = datetime.now() - timedelta(minutes=max_age_minutes)
    for item in iter_mailchimp_codes(max_days=max_days):
        try:
            stamp = datetime.fromisoformat(item.timestamp)
        except Exception:
            continue
        if stamp >= threshold:
            return item
    return None


def wait_for_mailchimp_code(
    *,
    max_days: int = 7,
    max_age_minutes: int = 30,
    not_before: datetime | None = None,
    timeout_seconds: int = 90,
    poll_interval_seconds: int = 5,
) -> MailchimpVerificationCode | None:
    started_at = datetime.now()
    while (datetime.now() - started_at).total_seconds() <= timeout_seconds:
        item = latest_mailchimp_code(
            max_days=max_days,
            max_age_minutes=max_age_minutes,
        )
        if item is not None:
            try:
                stamp = datetime.fromisoformat(item.timestamp)
            except Exception:
                stamp = None
            if not_before is None or (stamp is not None and stamp >= not_before):
                return item
        if poll_interval_seconds > 0:
            import time

            time.sleep(poll_interval_seconds)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp 認証コード取得 helper")
    parser.add_argument("--max-days", type=int, default=7)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    args = parser.parse_args()

    if args.wait_seconds > 0:
        item = wait_for_mailchimp_code(
            max_days=args.max_days,
            max_age_minutes=args.max_age_minutes,
            timeout_seconds=args.wait_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    else:
        item = latest_mailchimp_code(
            max_days=args.max_days,
            max_age_minutes=args.max_age_minutes,
        )
    if item is None:
        print(json.dumps({"found": False}, ensure_ascii=False, indent=2))
        return
    print(
        json.dumps(
            {
                "found": True,
                "code": item.code,
                "timestamp": item.timestamp,
                "group_id": item.group_id,
                "group_name": item.group_name,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
