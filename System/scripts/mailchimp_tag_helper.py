#!/usr/bin/env python3
"""Mailchimp tag の一覧 / 付与 / 解除 / member 確認を扱う helper。"""

from __future__ import annotations

import argparse
import hashlib
import json
import warnings
from typing import Any

try:
    from urllib3.exceptions import NotOpenSSLWarning
except Exception:  # pragma: no cover
    NotOpenSSLWarning = None

if NotOpenSSLWarning is not None:
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

from mailchimp_journey_snapshot import build_session, load_config


def subscriber_hash(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode("utf-8")).hexdigest()


def audience_id() -> str:
    return load_config()["audience_id"]


def get_member(email: str) -> dict[str, Any]:
    session, base_url = build_session()
    response = session.get(
        f"{base_url}/lists/{audience_id()}/members/{subscriber_hash(email)}",
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "email_address": payload.get("email_address"),
        "id": payload.get("id"),
        "status": payload.get("status"),
        "tags_count": payload.get("tags_count"),
        "last_changed": payload.get("last_changed"),
    }


def list_tags(limit: int, name: str | None) -> dict[str, Any]:
    session, base_url = build_session()
    params: dict[str, Any] = {"count": limit}
    if name:
        params["name"] = name
    response = session.get(
        f"{base_url}/lists/{audience_id()}/tag-search",
        params=params,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "audience_id": audience_id(),
        "count": len(payload.get("tags", [])),
        "rows": [
            {
                "name": row.get("name"),
                "member_count": row.get("member_count"),
            }
            for row in payload.get("tags", [])
        ],
    }


def ensure_member(email: str, status_if_new: str) -> dict[str, Any]:
    session, base_url = build_session()
    email_address = email.strip().lower()
    member_hash = subscriber_hash(email_address)
    response = session.put(
        f"{base_url}/lists/{audience_id()}/members/{member_hash}",
        json={
            "email_address": email_address,
            "status_if_new": status_if_new,
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "email_address": payload.get("email_address"),
        "id": payload.get("id"),
        "status": payload.get("status"),
        "last_changed": payload.get("last_changed"),
    }


def update_tags(email: str, tag_name: str, active: bool, status_if_new: str | None) -> dict[str, Any]:
    if status_if_new:
        ensure_member(email, status_if_new=status_if_new)
    session, base_url = build_session()
    member_hash = subscriber_hash(email)
    response = session.post(
        f"{base_url}/lists/{audience_id()}/members/{member_hash}/tags",
        json={"tags": [{"name": tag_name, "status": "active" if active else "inactive"}]},
        timeout=60,
    )
    response.raise_for_status()
    return {
        "audience_id": audience_id(),
        "email_address": email.strip().lower(),
        "member_hash": member_hash,
        "tag_name": tag_name,
        "status": "active" if active else "inactive",
        "result": "ok",
    }


def archive_member(email: str) -> dict[str, Any]:
    session, base_url = build_session()
    member_hash = subscriber_hash(email)
    response = session.delete(
        f"{base_url}/lists/{audience_id()}/members/{member_hash}",
        timeout=60,
    )
    response.raise_for_status()
    return {
        "audience_id": audience_id(),
        "email_address": email.strip().lower(),
        "member_hash": member_hash,
        "archived": True,
        "status_code": response.status_code,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp tag helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list-tags", help="List tags")
    list_parser.add_argument("--limit", type=int, default=20)
    list_parser.add_argument("--name")

    member_parser = sub.add_parser("member", help="Get member summary")
    member_parser.add_argument("--email", required=True)

    ensure_parser = sub.add_parser("ensure-member", help="Create or upsert a member")
    ensure_parser.add_argument("--email", required=True)
    ensure_parser.add_argument("--status-if-new", default="subscribed")

    add_parser = sub.add_parser("add-tag", help="Add tag to member")
    add_parser.add_argument("--email", required=True)
    add_parser.add_argument("--tag", required=True)
    add_parser.add_argument("--status-if-new")

    remove_parser = sub.add_parser("remove-tag", help="Remove tag from member")
    remove_parser.add_argument("--email", required=True)
    remove_parser.add_argument("--tag", required=True)

    archive_parser = sub.add_parser("archive-member", help="Archive member")
    archive_parser.add_argument("--email", required=True)

    args = parser.parse_args()

    if args.cmd == "list-tags":
        payload = list_tags(limit=args.limit, name=args.name)
    elif args.cmd == "member":
        payload = get_member(args.email)
    elif args.cmd == "ensure-member":
        payload = ensure_member(args.email, status_if_new=args.status_if_new)
    elif args.cmd == "add-tag":
        payload = update_tags(args.email, args.tag, active=True, status_if_new=args.status_if_new)
    elif args.cmd == "remove-tag":
        payload = update_tags(args.email, args.tag, active=False, status_if_new=None)
    else:
        payload = archive_member(args.email)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
