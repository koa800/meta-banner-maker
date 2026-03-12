#!/usr/bin/env python3
"""Lステップのテンプレート編集画面を snapshot する。

使い方:
  python3 System/scripts/lstep_template_snapshot.py --url <edit_url>

前提:
- Google Chrome の CDP が 9224 で開いている
- Lステップにログイン済み
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9224"


def collect_inputs(page) -> list[dict[str, str]]:
    script = """() => {
      const nodes = Array.from(document.querySelectorAll('input, textarea, select'));
      return nodes.map((el) => {
        const tag = el.tagName.toLowerCase();
        const type = el.getAttribute('type') || '';
        const name = el.getAttribute('name') || '';
        const id = el.getAttribute('id') || '';
        const placeholder = el.getAttribute('placeholder') || '';
        let value = '';
        if (tag === 'select') {
          value = el.value || '';
        } else if (type === 'checkbox' || type === 'radio') {
          value = el.checked ? 'checked' : '';
        } else {
          value = el.value || '';
        }
        const label = (() => {
          if (id) {
            const byFor = document.querySelector(`label[for="${id}"]`);
            if (byFor) return (byFor.textContent || '').trim();
          }
          const wrapper = el.closest('label');
          if (wrapper) return (wrapper.textContent || '').trim();
          const prev = el.previousElementSibling;
          if (prev) return (prev.textContent || '').trim();
          return '';
        })();
        return {tag, type, name, id, placeholder, value, label};
      });
    }"""
    return page.evaluate(script)


def collect_buttons(page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('button, a, input[type="submit"], input[type="button"]'))
        .map((el) => (el.textContent || el.value || '').trim())
        .filter(Boolean)
        """
    )


def collect_prosemirror(page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.ProseMirror'))
        .map((el) => (el.textContent || '').trim())
        .filter(Boolean)
        """
    )


def collect_headings(page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('h1, h2, h3, h4, .title, .subtitle, th, legend'))
        .map((el) => (el.textContent || '').trim())
        .filter(Boolean)
        .slice(0, 120)
        """
    )


def snapshot(url: str) -> dict:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(2500)
        data = {
            "url": page.url,
            "title": page.title(),
            "headings": collect_headings(page),
            "buttons": collect_buttons(page),
            "prosemirror": collect_prosemirror(page),
            "inputs": collect_inputs(page),
        }
        page.close()
        return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--out")
    args = parser.parse_args()
    data = snapshot(args.url)
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
