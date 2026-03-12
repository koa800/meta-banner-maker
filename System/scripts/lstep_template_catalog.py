#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

import browser_cookie3
import requests

BASE_URL = "https://manager.linestep.net"
LIST_URL = f"{BASE_URL}/api/templates"


def session() -> requests.Session:
    s = requests.Session()
    s.cookies = browser_cookie3.chrome(domain_name="manager.linestep.net")
    s.headers.update(
        {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": f"{BASE_URL}/line/template",
            "User-Agent": "Mozilla/5.0",
        }
    )
    return s


def infer_template_type(item: dict[str, Any]) -> str:
    form_type = item.get("form_type")
    editor_version = item.get("editor_version")
    if form_type == 60 and editor_version == 2:
        return "フレックスメッセージ"
    if form_type == 30 and editor_version == 1:
        return "カルーセルメッセージ(新方式)"
    if form_type == 40 and editor_version == 10:
        return "テンプレートパック"
    if form_type == 8 and editor_version == 0:
        return "標準メッセージ"
    return f"不明(form_type={form_type}, editor_version={editor_version})"


def generic_edit_url(item_id: int, group_id: int | None) -> str:
    group = 0 if group_id is None else group_id
    return f"{BASE_URL}/line/template/edit/{item_id}?group={group}"


def resolve_edit_url(s: requests.Session, item_id: int, group_id: int | None) -> str:
    url = generic_edit_url(item_id, group_id)
    resp = s.get(url, allow_redirects=True, timeout=30)
    return resp.url


def list_templates(
    s: requests.Session,
    search: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    page = 1
    out: list[dict[str, Any]] = []
    while len(out) < limit:
        resp = s.get(LIST_URL, params={"page": page}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        for item in payload.get("data", []):
            name = item.get("name", "")
            if search and search not in name:
                continue
            out.append(
                {
                    "id": item.get("id"),
                    "name": name,
                    "type": infer_template_type(item),
                    "group": item.get("group"),
                    "created_at": item.get("created_at"),
                    "content_preview": (item.get("content_text") or "")[:120],
                    "edit_url": resolve_edit_url(s, item.get("id"), item.get("group")),
                }
            )
            if len(out) >= limit:
                break
        if page >= payload.get("last_page", page):
            break
        page += 1
    return out


def summarize_flex(editor_json: dict[str, Any]) -> dict[str, Any]:
    panels = editor_json.get("panels", []) or []
    blocks: list[dict[str, Any]] = []
    for panel in panels:
        for block in panel.get("blocks", []) or []:
            info = {"type": block.get("type")}
            action = block.get("action") or {}
            if isinstance(action, dict) and action:
                info["action_type"] = action.get("type")
                info["action_url"] = action.get("url") or action.get("uri")
            blocks.append(info)
    counts: dict[str, int] = {}
    for block in blocks:
        key = block.get("type") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return {
        "panel_count": len(panels),
        "block_counts": counts,
        "blocks": blocks,
    }


def inspect_template(s: requests.Session, item_id: int) -> dict[str, Any]:
    page = 1
    item: dict[str, Any] | None = None
    while True:
        resp = s.get(LIST_URL, params={"page": page}, timeout=30)
        resp.raise_for_status()
        payload = resp.json()
        for row in payload.get("data", []):
            if row.get("id") == item_id:
                item = row
                break
        if item or page >= payload.get("last_page", page):
            break
        page += 1
    if not item:
        raise SystemExit(f"template not found: {item_id}")

    result: dict[str, Any] = {
        "id": item.get("id"),
        "name": item.get("name"),
        "type": infer_template_type(item),
        "group": item.get("group"),
        "created_at": item.get("created_at"),
        "content_text": item.get("content_text"),
        "generic_edit_url": generic_edit_url(item.get("id"), item.get("group")),
        "resolved_edit_url": resolve_edit_url(s, item.get("id"), item.get("group")),
    }

    if result["type"] == "フレックスメッセージ":
        resp = s.get(f"{BASE_URL}/api/template/lflexes/{item_id}", timeout=30)
        resp.raise_for_status()
        detail = resp.json()
        result["alt_text"] = detail.get("alt_text")
        result["flex_summary"] = summarize_flex(detail.get("editor_json") or {})

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Lステップのテンプレート一覧と種類を exact に読む")
    subparsers = parser.add_subparsers(dest="cmd", required=True)

    p_list = subparsers.add_parser("list")
    p_list.add_argument("--search", default="")
    p_list.add_argument("--limit", type=int, default=30)

    p_inspect = subparsers.add_parser("inspect")
    p_inspect.add_argument("--id", type=int, required=True)

    args = parser.parse_args()
    s = session()

    if args.cmd == "list":
        data = list_templates(s, search=args.search, limit=args.limit)
    else:
        data = inspect_template(s, args.id)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
