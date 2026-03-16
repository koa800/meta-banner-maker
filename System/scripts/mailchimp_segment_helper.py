#!/usr/bin/env python3
"""Mailchimp saved segment の一覧 / 作成 / 削除を扱う helper。"""

from __future__ import annotations

import argparse
import json
from typing import Any

from mailchimp_journey_snapshot import build_session, load_config


def fetch_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    session, _ = build_session()
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def list_segments(limit: int) -> dict[str, Any]:
    session, base_url = build_session()
    audience_id = load_config()["audience_id"]
    response = session.get(
        f"{base_url}/lists/{audience_id}/segments",
        params={"count": limit},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "audience_id": audience_id,
        "count": len(payload.get("segments", [])),
        "rows": [
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "type": row.get("type"),
                "member_count": row.get("member_count"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in payload.get("segments", [])
        ],
    }


def create_static_empty_segment(name: str) -> dict[str, Any]:
    session, base_url = build_session()
    audience_id = load_config()["audience_id"]
    response = session.post(
        f"{base_url}/lists/{audience_id}/segments",
        json={"name": name, "static_segment": []},
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    return {
        "audience_id": audience_id,
        "id": payload.get("id"),
        "name": payload.get("name"),
        "type": payload.get("type"),
        "member_count": payload.get("member_count"),
        "created_at": payload.get("created_at"),
    }


def delete_segment(segment_id: int) -> dict[str, Any]:
    session, base_url = build_session()
    audience_id = load_config()["audience_id"]
    response = session.delete(
        f"{base_url}/lists/{audience_id}/segments/{segment_id}",
        timeout=60,
    )
    response.raise_for_status()
    return {
        "audience_id": audience_id,
        "segment_id": segment_id,
        "deleted": True,
        "status_code": response.status_code,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp saved segment helper")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list", help="List segments")
    list_parser.add_argument("--limit", type=int, default=20)

    create_parser = sub.add_parser("create-static-empty", help="Create empty static segment")
    create_parser.add_argument("--name", required=True)

    delete_parser = sub.add_parser("delete", help="Delete segment")
    delete_parser.add_argument("--id", type=int, required=True)

    args = parser.parse_args()

    if args.cmd == "list":
        payload = list_segments(args.limit)
    elif args.cmd == "create-static-empty":
        payload = create_static_empty_segment(args.name)
    else:
        payload = delete_segment(args.id)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
