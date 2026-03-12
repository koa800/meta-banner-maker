#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from lstep_auth import build_authenticated_session

BASE_URL = "https://manager.linestep.net"
LIST_URL = f"{BASE_URL}/api/templates"


def session() -> requests.Session:
    return build_authenticated_session(
        referer=f"{BASE_URL}/line/template",
        probe_url=f"{BASE_URL}/api/templates?page=1",
    )


def fetch_json(
    s: requests.Session,
    url: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resp = s.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


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
    def rich_text_to_plain(doc: dict[str, Any] | None) -> str | None:
        if not isinstance(doc, dict):
            return None
        out: list[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                node_type = node.get("type")
                if node_type == "text" and node.get("text"):
                    out.append(str(node["text"]))
                for child in node.get("content", []) or []:
                    walk(child)
            elif isinstance(node, list):
                for child in node:
                    walk(child)

        walk(doc)
        text = "".join(out).strip()
        return text or None

    panels = editor_json.get("panels", []) or []
    blocks: list[dict[str, Any]] = []
    for panel in panels:
        for block in panel.get("blocks", []) or []:
            info = {"type": block.get("type")}
            text_preview = rich_text_to_plain(block.get("text"))
            if text_preview:
                info["text_preview"] = text_preview[:120]
            action = block.get("action") or {}
            if isinstance(action, dict) and action:
                info["action_type"] = action.get("type")
                info["action_label"] = action.get("label")
                info["action_description"] = action.get("description")
                data = action.get("data") or {}
                url_action = data.get("url_action") or {}
                info["action_url"] = (
                    action.get("url")
                    or action.get("uri")
                    or url_action.get("url")
                )
            blocks.append(info)
    counts: dict[str, int] = {}
    for block in blocks:
        key = block.get("type") or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return {
        "theme_colors": editor_json.get("themeColors"),
        "panel_count": len(panels),
        "block_counts": counts,
        "blocks": blocks,
    }


def infer_carousel_action_kind(action: dict[str, Any]) -> str | None:
    if action.get("action_form_id"):
        return "回答フォームを開く"
    if action.get("action_id"):
        return "アクション実行"
    if action.get("action_tel") or action.get("phone_number"):
        return "電話をかける"
    if action.get("action_mail") or action.get("email"):
        return "メールを送る"
    if action.get("line_official_account_id") or action.get("friend_add_account_id"):
        return "LINEアカウントを友だち追加"
    if action.get("scenario_id") or action.get("step_id"):
        return "シナリオを移動・停止"
    if action.get("url") or action.get("uri"):
        return "URLを開く"
    return None


def summarize_carousel(carousel_json: dict[str, Any]) -> dict[str, Any]:
    panels = carousel_json.get("panels", []) or []
    panel_summaries: list[dict[str, Any]] = []
    for panel in panels:
        actions: list[dict[str, Any]] = []
        for action in panel.get("actions", []) or []:
            info: dict[str, Any] = {
                "title": action.get("title"),
                "action_type": action.get("action_type"),
            }
            kind = infer_carousel_action_kind(action)
            if kind:
                info["kind"] = kind
            if action.get("action_form_id"):
                info["action_form_id"] = action.get("action_form_id")
            if action.get("action_liff_size"):
                info["action_liff_size"] = action.get("action_liff_size")
            if action.get("url"):
                info["url"] = action.get("url")
            if action.get("uri"):
                info["uri"] = action.get("uri")
            actions.append(info)
        panel_summaries.append(
            {
                "title": panel.get("title"),
                "text_preview": (panel.get("text") or "")[:120],
                "action_count": len(actions),
                "actions": actions,
            }
        )
    return {
        "alt_text": carousel_json.get("altText"),
        "answer_type": carousel_json.get("answerType"),
        "panel_count": len(panels),
        "panels": panel_summaries,
        "config": {
            "twice_reply_type": (carousel_json.get("config") or {}).get("twice_reply_type"),
            "twice_do_reply": (carousel_json.get("config") or {}).get("twice_do_reply"),
            "twice_action_id": (carousel_json.get("config") or {}).get("twice_action_id"),
        },
    }


def summarize_standard_message(content_text: str | None) -> dict[str, Any]:
    if not content_text:
        return {
            "char_count": 0,
            "line_count": 0,
            "url_candidates": [],
            "leading_lines": [],
        }
    normalized = content_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line.strip()]
    urls = re.findall(r"https?://[^\s]+", normalized)
    return {
        "char_count": len(normalized),
        "line_count": len(lines),
        "url_candidates": urls,
        "leading_lines": lines[:6],
    }


def decode_js_string(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return bytes(value, "utf-8").decode("unicode_escape")
    except Exception:
        return value


def summarize_pack(s: requests.Session, item_id: int) -> dict[str, Any]:
    url = f"{BASE_URL}/line/eggpack/show/{item_id}"
    resp = s.get(url, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    page_title = ""
    title_el = soup.select_one("h1.page-title")
    if title_el:
        page_title = " ".join(title_el.get_text(" ", strip=True).split())

    step_rows: list[dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        no_cell = tr.find("th")
        cells = tr.find_all("td")
        if not no_cell or len(cells) < 1:
            continue
        no_value = " ".join(no_cell.get_text(" ", strip=True).split())
        if not no_value.isdigit():
            continue
        values = [" ".join(td.get_text(" ", strip=True).split()) for td in cells]
        body_cell = cells[0]
        template_badge = body_cell.find("span", class_="label")
        rich_viewer = body_cell.find("rich-viewer")
        preview = None
        if rich_viewer and rich_viewer.has_attr(":content"):
            preview = decode_js_string(rich_viewer.get(":content", "").strip('"'))[:120]
        edit_links: list[str] = []
        for a in tr.find_all("a", href=True):
            href = a["href"]
            if href:
                edit_links.append(href)
        actions: list[str] = []
        for a in tr.find_all("a", href=True):
            text = " ".join(a.get_text(" ", strip=True).split())
            if text:
                actions.append(text)
        for button in tr.find_all("button"):
            text = " ".join(button.get_text(" ", strip=True).split())
            if text:
                actions.append(text)
        step_rows.append(
            {
                "no": no_value,
                "body": values[0] if values else "",
                "step_type": "テンプレート" if template_badge else "本文",
                "preview": preview,
                "actions": actions,
                "links": edit_links,
            }
        )

    tester = soup.find("v-tester-selector")
    test_url = tester.get("url") if tester else None
    test_item_id = tester.get("item_id") if tester else None

    return {
        "page_title": page_title,
        "step_count": len(step_rows),
        "steps": step_rows,
        "test_url": test_url,
        "test_item_id": test_item_id,
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

    if result["type"] == "標準メッセージ":
        result["content_summary"] = summarize_standard_message(item.get("content_text"))
    elif result["type"] == "カルーセルメッセージ(新方式)":
        detail = fetch_json(
            s,
            f"{BASE_URL}/api/line/template/{item_id}",
            params={"group": item.get("group")},
        )
        messages_data = detail.get("messagesData") or {}
        result["disable_cv"] = messages_data.get("disable_cv")
        result["carousel_summary"] = summarize_carousel(messages_data.get("carousel") or {})
    elif result["type"] == "フレックスメッセージ":
        detail = fetch_json(s, f"{BASE_URL}/api/template/lflexes/{item_id}")
        result["alt_text"] = detail.get("alt_text")
        result["flex_summary"] = summarize_flex(detail.get("editor_json") or {})
    elif result["type"] == "テンプレートパック":
        result["pack_summary"] = summarize_pack(s, item_id)

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
    try:
        s = session()
    except RuntimeError as exc:
        raise SystemExit(str(exc))

    if args.cmd == "list":
        data = list_templates(s, search=args.search, limit=args.limit)
    else:
        data = inspect_template(s, args.id)

    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
