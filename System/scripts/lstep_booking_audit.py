#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

from lstep_auth import BASE_URL, build_authenticated_session, fetch_authenticated_context

NOTIFICATION_PAGE_URL = f"{BASE_URL}/line/notification"
NOTIFICATION_API_URL = f"{BASE_URL}/api/notifications"
TAG_API_URL = f"{BASE_URL}/api/tags"
MEMBER_QUERY_API_URL = f"{BASE_URL}/api/member-queries"
ACTION_DATA_API_URL = f"{BASE_URL}/api/action/data"
SALON_API_URL = f"{BASE_URL}/api/salon"

BOOKING_KEYWORDS = (
    "個別予約",
    "予約数",
    "予約通知",
    "予約完了",
    "イベント予約",
    "カレンダー",
    "個別専用",
    "面談予約",
)
BOOKING_TIMINGS = {
    "salon_reservation_reserved",
    "reservation.reserved",
    "tag_attached",
}
OUTPUT_JSON_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "lstep_booking_audit_latest.json"
)


def fetch_json(
    session: requests.Session, url: str, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def list_paginated(
    session: requests.Session,
    url: str,
    data_key: str = "data",
    max_pages: int = 20,
) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while page <= max_pages:
        payload = fetch_json(session, url, {"page": page})
        batch = payload.get(data_key, []) or []
        items.extend(batch)
        if page >= int(payload.get("last_page", page) or page):
            break
        page += 1
    return items


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values() if flatten_text(v))
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value if flatten_text(v))
    return str(value)


def collect_int_values(node: Any, key_name: str) -> list[int]:
    found: list[int] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key == key_name:
                if isinstance(value, list):
                    for item in value:
                        try:
                            found.append(int(item))
                        except (TypeError, ValueError):
                            pass
                else:
                    try:
                        found.append(int(value))
                    except (TypeError, ValueError):
                        pass
            else:
                found.extend(collect_int_values(value, key_name))
    elif isinstance(node, list):
        for item in node:
            found.extend(collect_int_values(item, key_name))
    return found


def extract_member_query_ids(condition: Any) -> list[int]:
    ids = set(collect_int_values(condition, "member_query_id"))
    ids.update(collect_int_values(condition, "member_query_ids"))
    return sorted(ids)


def extract_tag_ids(condition: Any) -> list[int]:
    ids = set(collect_int_values(condition, "tag_id"))
    ids.update(collect_int_values(condition, "tag_ids"))
    ids.update(collect_int_values(condition, "ids"))
    return sorted(ids)


def extract_salon_ids(condition: Any) -> list[int]:
    ids = set(collect_int_values(condition, "salon_id"))
    ids.update(collect_int_values(condition, "salon_ids"))
    return sorted(ids)


def extract_trigger_keys(timings: Any) -> list[str]:
    keys: list[str] = []
    for timing in timings or []:
        if isinstance(timing, dict):
            key = str(timing.get("key") or "").strip()
            if key:
                keys.append(key)
    return keys


def extract_channel_labels(channels: Any) -> list[str]:
    labels: list[str] = []
    for channel in channels or []:
        if not isinstance(channel, dict):
            continue
        name = str(channel.get("name") or channel.get("label") or "").strip()
        key = str(channel.get("key") or "").strip()
        address = str(channel.get("address") or channel.get("value") or "").strip()
        if name:
            labels.append(name)
        elif key and address:
            labels.append(f"{key}:{address}")
        elif key:
            labels.append(key)
    return labels


def is_booking_notification(item: dict[str, Any]) -> bool:
    title = str(item.get("title") or "")
    text = flatten_text(item.get("condition"))
    triggers = set(extract_trigger_keys(item.get("timings")))
    joined = f"{title} {text}"
    if any(keyword in joined for keyword in BOOKING_KEYWORDS):
        return True
    return bool(triggers & BOOKING_TIMINGS)


def normalize_notification(item: dict[str, Any]) -> dict[str, Any]:
    condition = item.get("condition") or {}
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "use_notify": item.get("use_notify"),
        "account": {
            "id": ((item.get("account") or {}).get("id")),
            "name": ((item.get("account") or {}).get("name")),
            "real_name": ((item.get("account") or {}).get("real_name")),
        },
        "trigger_keys": extract_trigger_keys(item.get("timings")),
        "channel_labels": extract_channel_labels(item.get("channels")),
        "member_query_ids": extract_member_query_ids(condition),
        "tag_ids": extract_tag_ids(condition),
        "salon_ids": extract_salon_ids(condition),
        "condition_text": flatten_text(condition),
    }


def inspect_tag(session: requests.Session, tag_id: int) -> dict[str, Any]:
    payload = fetch_json(session, f"{TAG_API_URL}/{tag_id}")
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "append_action_id": payload.get("append_action_id"),
        "description": payload.get("description"),
    }


def inspect_member_query(session: requests.Session, query_id: int) -> dict[str, Any]:
    payload = fetch_json(session, f"{MEMBER_QUERY_API_URL}/{query_id}")
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "condition_text": flatten_text(payload.get("condition")),
    }


def inspect_action(session: requests.Session, action_id: int) -> dict[str, Any]:
    payload = fetch_json(session, f"{ACTION_DATA_API_URL}/{action_id}")
    return {
        "id": payload.get("aid"),
        "name": payload.get("a_name"),
        "input_count": len(payload.get("inputs") or []),
        "funnel_descriptions": payload.get("funnel_descriptions"),
    }


def inspect_salon(session: requests.Session, salon_id: int) -> dict[str, Any]:
    payload = fetch_json(session, f"{SALON_API_URL}/{salon_id}")
    return {
        "id": payload.get("id"),
        "name": payload.get("name"),
        "reservation_type": payload.get("reservation_type"),
        "follow_action_id": payload.get("follow_action_id"),
        "cancel_action_id": payload.get("cancel_action_id"),
    }


def build_report(expected_account_name: str | None = None) -> dict[str, Any]:
    session = build_authenticated_session(
        referer=NOTIFICATION_PAGE_URL,
        probe_url=f"{NOTIFICATION_API_URL}?page=1",
        expected_account_name=expected_account_name,
    )
    context = fetch_authenticated_context(session, NOTIFICATION_PAGE_URL) or {}
    notifications = list_paginated(session, NOTIFICATION_API_URL, max_pages=20)
    booking_notifications = [
        normalize_notification(item)
        for item in notifications
        if is_booking_notification(item)
    ]

    tag_ids = sorted(
        {
            tag_id
            for item in booking_notifications
            for tag_id in item.get("tag_ids", [])
        }
    )
    member_query_ids = sorted(
        {
            query_id
            for item in booking_notifications
            for query_id in item.get("member_query_ids", [])
        }
    )
    salon_ids = sorted(
        {
            salon_id
            for item in booking_notifications
            for salon_id in item.get("salon_ids", [])
        }
    )

    tag_details = [inspect_tag(session, tag_id) for tag_id in tag_ids]
    action_ids = sorted(
        {
            int(item["append_action_id"])
            for item in tag_details
            if item.get("append_action_id")
        }
    )
    action_details = [inspect_action(session, action_id) for action_id in action_ids]
    member_query_details = [
        inspect_member_query(session, query_id) for query_id in member_query_ids
    ]
    salon_details = [inspect_salon(session, salon_id) for salon_id in salon_ids]

    trigger_counter = Counter(
        trigger
        for item in booking_notifications
        for trigger in item.get("trigger_keys", [])
    )
    channel_counter = Counter(
        label
        for item in booking_notifications
        for label in item.get("channel_labels", [])
    )

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "authenticated_context": context,
        "summary": {
            "notification_total": len(notifications),
            "booking_notification_total": len(booking_notifications),
            "trigger_counts": dict(trigger_counter),
            "channel_counts": dict(channel_counter),
        },
        "booking_notifications": booking_notifications,
        "tag_details": tag_details,
        "member_query_details": member_query_details,
        "salon_details": salon_details,
        "action_details": action_details,
    }


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Lステップの個別予約通知を監査する")
    parser.add_argument("--expected-account", help="想定する Lステップアカウント名")
    parser.add_argument(
        "--output-json",
        default=str(OUTPUT_JSON_PATH),
        help="JSON保存先。空文字で保存しない",
    )
    args = parser.parse_args()

    report = build_report(expected_account_name=args.expected_account)
    if args.output_json.strip():
        write_json(Path(args.output_json), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
