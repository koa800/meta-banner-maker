#!/usr/bin/env python3
"""Chrome raw CDP helper.

Playwright の connect_over_cdp が詰まる時でも、
既存タブの列挙・評価・遷移・作成・close を最低限できるようにする。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.request
from typing import Any

CDP_BASE = "http://127.0.0.1:9224"
CDP_VERSION_URL = f"{CDP_BASE}/json/version"
CDP_LIST_URL = f"{CDP_BASE}/json/list"


def _http_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def browser_websocket_url() -> str:
    payload = _http_json(CDP_VERSION_URL)
    websocket_url = payload.get("webSocketDebuggerUrl")
    if not websocket_url:
        raise RuntimeError("browser websocket url が見つかりません")
    return websocket_url


def list_targets() -> list[dict[str, Any]]:
    return _http_json(CDP_LIST_URL)


def _send_cdp(websocket_url: str, method: str, params: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any]:
    node_script = r"""
const wsUrl = process.argv[1];
const method = process.argv[2];
const params = JSON.parse(process.argv[3] || "{}");
const id = 1;
const ws = new WebSocket(wsUrl);

ws.addEventListener("open", () => {
  ws.send(JSON.stringify({ id, method, params }));
});

ws.addEventListener("message", (event) => {
  const data = JSON.parse(event.data.toString());
  if (data.id !== id) return;
  if (data.error) {
    console.error(JSON.stringify(data.error));
    ws.close();
    process.exit(1);
    return;
  }
  process.stdout.write(JSON.stringify(data.result || {}));
  ws.close();
});

ws.addEventListener("close", () => process.exit(0));
ws.addEventListener("error", (error) => {
  console.error(String(error));
  process.exit(1);
});
"""
    completed = subprocess.run(
        ["node", "-e", node_script, websocket_url, method, json.dumps(params or {}, ensure_ascii=False)],
        capture_output=True,
        text=True,
        timeout=timeout + 3,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or "raw CDP send failed").strip())
    try:
        return json.loads(completed.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover
        raise RuntimeError("raw CDP response decode failed") from exc


def send_browser(method: str, params: dict[str, Any] | None = None, timeout: int = 8) -> dict[str, Any]:
    return _send_cdp(browser_websocket_url(), method, params=params, timeout=timeout)


def find_target(
    *,
    title_contains: str | None = None,
    url_contains: str | None = None,
    exact_url: str | None = None,
) -> dict[str, Any] | None:
    for target in list_targets():
        title = str(target.get("title") or "")
        url = str(target.get("url") or "")
        if exact_url is not None and url != exact_url:
            continue
        if title_contains is not None and title_contains not in title:
            continue
        if url_contains is not None and url_contains not in url:
            continue
        return target
    return None


def create_target(url: str) -> dict[str, Any]:
    result = send_browser("Target.createTarget", {"url": url})
    target_id = result.get("targetId")
    if not target_id:
        raise RuntimeError("targetId を取得できません")
    target = find_target_by_id(target_id)
    if not target:
        raise RuntimeError("作成した target が一覧に現れません")
    return target


def find_target_by_id(target_id: str) -> dict[str, Any] | None:
    for target in list_targets():
        if target.get("id") == target_id:
            return target
    return None


def activate_target(target_id: str) -> None:
    send_browser("Target.activateTarget", {"targetId": target_id})


def close_target(target_id: str) -> None:
    send_browser("Target.closeTarget", {"targetId": target_id})


def navigate_target(target_id: str, url: str) -> None:
    target = find_target_by_id(target_id)
    if not target or not target.get("webSocketDebuggerUrl"):
        raise RuntimeError("navigate 対象の target websocket が見つかりません")
    _send_cdp(target["webSocketDebuggerUrl"], "Page.navigate", {"url": url})


def eval_target(target_id: str, expression: str, *, return_by_value: bool = True, await_promise: bool = False, timeout: int = 8) -> Any:
    target = find_target_by_id(target_id)
    if not target or not target.get("webSocketDebuggerUrl"):
        raise RuntimeError("evaluate 対象の target websocket が見つかりません")
    result = _send_cdp(
        target["webSocketDebuggerUrl"],
        "Runtime.evaluate",
        {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": await_promise,
        },
        timeout=timeout,
    )
    return (result.get("result") or {}).get("value")


def body_snapshot(target_id: str, limit: int = 1200) -> dict[str, Any]:
    expression = f"""
(() => {{
  const text = document.body ? document.body.innerText.slice(0, {limit}) : "";
  return {{
    url: location.href,
    title: document.title,
    body: text
  }};
}})()
"""
    return eval_target(target_id, expression) or {}


def fill_first_input(target_id: str, selectors: list[str], value: str) -> bool:
    selector_json = json.dumps(selectors, ensure_ascii=False)
    value_json = json.dumps(value, ensure_ascii=False)
    expression = f"""
(() => {{
  const selectors = {selector_json};
  const value = {value_json};
  const setValue = (el, next) => {{
    const proto = el.tagName === "TEXTAREA"
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }};
  for (const selector of selectors) {{
    const el = document.querySelector(selector);
    if (!el) continue;
    el.focus();
    setValue(el, value);
    return true;
  }}
  return false;
}})()
"""
    return bool(eval_target(target_id, expression))


def click_first(target_id: str, selectors: list[str], text_candidates: list[str] | None = None) -> bool:
    selector_json = json.dumps(selectors, ensure_ascii=False)
    text_json = json.dumps(text_candidates or [], ensure_ascii=False)
    expression = f"""
(() => {{
  const selectors = {selector_json};
  const textCandidates = {text_json};
  const bySelectors = () => {{
    for (const selector of selectors) {{
      const el = document.querySelector(selector);
      if (!el) continue;
      el.click();
      return true;
    }}
    return false;
  }};
  const byText = () => {{
    const nodes = Array.from(document.querySelectorAll("button, a, input[type='submit'], input[type='button']"));
    for (const node of nodes) {{
      const label = (node.innerText || node.value || "").trim();
      if (!label) continue;
      if (textCandidates.some((candidate) => label.includes(candidate))) {{
        node.click();
        return true;
      }}
    }}
    return false;
  }};
  return bySelectors() || byText();
}})()
    """
    return bool(eval_target(target_id, expression))


def main() -> None:
    parser = argparse.ArgumentParser(description="Chrome raw CDP helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--title-contains")
    list_parser.add_argument("--url-contains")

    snap_parser = subparsers.add_parser("snapshot")
    snap_parser.add_argument("target_id")
    snap_parser.add_argument("--limit", type=int, default=1200)

    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("target_id")

    navigate_parser = subparsers.add_parser("navigate")
    navigate_parser.add_argument("target_id")
    navigate_parser.add_argument("url")

    eval_parser = subparsers.add_parser("eval")
    eval_parser.add_argument("target_id")
    eval_parser.add_argument("expression")

    args = parser.parse_args()

    if args.command == "list":
        targets = list_targets()
        if args.title_contains or args.url_contains:
            filtered: list[dict[str, Any]] = []
            for target in targets:
                title = str(target.get("title") or "")
                url = str(target.get("url") or "")
                if args.title_contains and args.title_contains not in title:
                    continue
                if args.url_contains and args.url_contains not in url:
                    continue
                filtered.append(target)
            targets = filtered
        print(json.dumps(targets, ensure_ascii=False, indent=2))
        return

    if args.command == "snapshot":
        print(json.dumps(body_snapshot(args.target_id, limit=args.limit), ensure_ascii=False, indent=2))
        return

    if args.command == "activate":
        activate_target(args.target_id)
        print(json.dumps({"ok": True, "target_id": args.target_id}, ensure_ascii=False, indent=2))
        return

    if args.command == "navigate":
        navigate_target(args.target_id, args.url)
        print(json.dumps({"ok": True, "target_id": args.target_id, "url": args.url}, ensure_ascii=False, indent=2))
        return

    if args.command == "eval":
        print(json.dumps({"value": eval_target(args.target_id, args.expression)}, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    main()
