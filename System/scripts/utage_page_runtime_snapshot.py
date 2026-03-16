#!/usr/bin/env python3
"""UTAGE の page runtime から page data を JSON で抜く。"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from typing import Any

from playwright.sync_api import sync_playwright


CDP_URL = "http://127.0.0.1:9224"
SNAPSHOT_JS = r"""
() => {
  const out = {
    title: document.title,
    url: location.href,
    page: null,
    initial_state_keys: [],
  };

  const initialState = window.__INITIAL_STATE__ || null;
  if (initialState && typeof initialState === 'object') {
    out.initial_state_keys = Object.keys(initialState);
  }

  const app = document.getElementById('app');
  const vnodePage =
    app &&
    app.__vue_app__ &&
    app.__vue_app__._container &&
    app.__vue_app__._container._vnode &&
    app.__vue_app__._container._vnode.component &&
    app.__vue_app__._container._vnode.component.data &&
    app.__vue_app__._container._vnode.component.data.page
      ? app.__vue_app__._container._vnode.component.data.page
      : null;

  const candidate = vnodePage || (initialState && initialState.page) || null;
  if (!candidate) return out;

  out.page = {
    id: candidate.id ?? null,
    name: candidate.name ?? null,
    title: candidate.title ?? null,
    is_high_speed_mode: candidate.is_high_speed_mode ?? null,
    first_view_css: candidate.first_view_css ?? null,
    css: candidate.css ?? null,
    js_head: candidate.js_head ?? null,
    js_body_top: candidate.js_body_top ?? null,
    js_body: candidate.js_body ?? null,
    thanks_page_url: candidate.thanks_page_url ?? null,
    redirect_url: candidate.redirect_url ?? null,
  };
  return out;
}
"""


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _normalize_url(url: str) -> str:
    return url.rstrip("/")


def _find_existing_tab(target_url: str) -> dict[str, Any] | None:
    normalized_target = _normalize_url(target_url)
    try:
        tabs = _get_json(f"{CDP_URL}/json/list")
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None

    exact_match = None
    prefix_match = None
    for tab in tabs:
        tab_url = tab.get("url")
        if not tab_url:
            continue
        normalized_tab = _normalize_url(tab_url)
        if normalized_tab == normalized_target:
            exact_match = tab
            break
        if normalized_target.startswith(normalized_tab) or normalized_tab.startswith(normalized_target):
            prefix_match = tab

    return exact_match or prefix_match


def _fetch_via_existing_tab(target_url: str) -> dict[str, Any] | None:
    tab = _find_existing_tab(target_url)
    if not tab or not tab.get("webSocketDebuggerUrl"):
        return None

    node_script = r"""
const wsUrl = process.argv[1];
const expression = process.argv[2];
const ws = new WebSocket(wsUrl);

ws.addEventListener('open', () => {
  ws.send(JSON.stringify({
    id: 1,
    method: 'Runtime.evaluate',
    params: {
      expression,
      returnByValue: true
    }
  }));
});

ws.addEventListener('message', (event) => {
  const message = JSON.parse(event.data.toString());
  if (message.id !== 1) return;
  if (message.result && message.result.result) {
    process.stdout.write(JSON.stringify(message.result.result.value ?? null));
    ws.close();
    return;
  }
  if (message.error) {
    process.stderr.write(JSON.stringify(message.error));
    ws.close();
  }
});

ws.addEventListener('close', () => process.exit(0));
ws.addEventListener('error', (error) => {
  process.stderr.write(String(error));
  process.exit(1);
});
"""

    completed = subprocess.run(
        ["node", "-e", node_script, tab["webSocketDebuggerUrl"], f"({SNAPSHOT_JS})()"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None


def fetch_snapshot(url: str) -> dict[str, Any]:
    existing_tab_snapshot = _fetch_via_existing_tab(url)
    if existing_tab_snapshot is not None:
        return existing_tab_snapshot

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(2500)
            data = page.evaluate(SNAPSHOT_JS)
            return data
        finally:
            page.close()
            # 既存の Chrome CDP セッションを共有しているので browser.close() は呼ばない。


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE page runtime snapshot")
    parser.add_argument("url", help="公開ページまたは edit 対象の URL")
    args = parser.parse_args()
    snapshot = fetch_snapshot(args.url)
    print(json.dumps(snapshot, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
