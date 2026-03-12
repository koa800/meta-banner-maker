#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

import requests

from lstep_auth import build_authenticated_session

BASE_URL = "https://manager.linestep.net"
LIST_URL = f"{BASE_URL}/api/actions"


def session() -> requests.Session:
    return build_authenticated_session(
        referer=f"{BASE_URL}/line/action",
        probe_url=f"{BASE_URL}/api/actions?page=1",
    )


def fetch_json(s: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = s.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def list_actions(s: requests.Session, search: str = "", limit: int = 50) -> list[dict[str, Any]]:
    page = 1
    out: list[dict[str, Any]] = []
    search_lower = search.lower()
    while len(out) < limit:
        payload = fetch_json(s, LIST_URL, params={"page": page})
        for item in payload.get("data", []):
            name = item.get("name", "")
            if search and search_lower not in name.lower():
                continue
            out.append(
                {
                    "id": item.get("id"),
                    "name": name,
                    "created_at": item.get("created_at"),
                    "next_work_at": item.get("next_work_at"),
                    "has_task": item.get("has_task"),
                    "group": item.get("group"),
                    "action_texts": item.get("action_texts", []),
                }
            )
            if len(out) >= limit:
                break
        if page >= payload.get("last_page", page):
            break
        page += 1
    return out


def inspect_action(s: requests.Session, action_id: int) -> dict[str, Any]:
    detail = fetch_json(s, f"{BASE_URL}/api/action/data/{action_id}")
    texts = fetch_json(s, f"{BASE_URL}/api/actions/{action_id}/texts")
    inputs = detail.get("inputs", []) or []
    return {
        "aid": detail.get("aid"),
        "a_name": detail.get("a_name"),
        "a_twice_type": detail.get("a_twice_type"),
        "funnel_descriptions": detail.get("funnel_descriptions"),
        "input_count": len(inputs),
        "inputs": inputs,
        "action_texts": texts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTEP action catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list", help="List actions")
    list_parser.add_argument("--search", default="", help="Action name substring")
    list_parser.add_argument("--limit", type=int, default=50, help="Max rows")

    inspect_parser = sub.add_parser("inspect", help="Inspect one action")
    inspect_parser.add_argument("--id", type=int, required=True, help="Action ID")

    args = parser.parse_args()
    try:
        s = session()
    except RuntimeError as exc:
        raise SystemExit(str(exc))
    if args.cmd == "list":
        data = list_actions(s, search=args.search, limit=args.limit)
    else:
        data = inspect_action(s, args.id)
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
