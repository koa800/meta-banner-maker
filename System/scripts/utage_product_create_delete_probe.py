#!/usr/bin/env python3
"""UTAGE の exploratory product を create -> delete で検証する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import body_snapshot
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target
from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/product"
CREATE_URL = "https://school.addness.co.jp/product/create"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_product_probe"


def _find_raw_target_id() -> str:
    target = (
        find_target(url_contains="school.addness.co.jp/product")
        or find_target(url_contains="school.addness.co.jp")
        or find_target(title_contains="UTAGE")
    )
    if target is None:
        target = create_target(LIST_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    return target_id


def _raw_count_rows(target_id: str, name: str) -> int:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    return int(
        eval_target(
            target_id,
            f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  return rows.filter((row) => (row.innerText || '').includes({json.dumps(name, ensure_ascii=False)})).length;
}})()
""",
        )
        or 0
    )


def _raw_fill_product_name(target_id: str, name: str) -> bool:
    expression = f"""
(() => {{
  const value = {json.dumps(name, ensure_ascii=False)};
  const setValue = (el, next) => {{
    const proto = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, "value");
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event("input", {{ bubbles: true }}));
    el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  }};
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {{
    const text = (label.innerText || '').trim();
    if (!text.includes('商品名')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') {{
      target.focus();
      setValue(target, value);
      return true;
    }}
  }}
  const fallback = document.querySelector('input[name="name"], input[name="title"], input');
  if (!fallback) return false;
  fallback.focus();
  setValue(fallback, value);
  return true;
}})()
"""
    return bool(eval_target(target_id, expression))


def _raw_click_save(target_id: str) -> bool:
    expression = """
(() => {
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'));
  for (const button of buttons) {
    const text = (button.innerText || button.value || '').trim();
    if (!text.includes('保存')) continue;
    button.click();
    return true;
  }
  return false;
})()
"""
    return bool(eval_target(target_id, expression))


def _raw_delete_row(target_id: str, name: str) -> bool:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    expression = f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    const text = (row.innerText || '').trim();
    if (!text.includes({json.dumps(name, ensure_ascii=False)})) continue;
    const form = row.querySelector('form.form-delete');
    if (form) {{
      form.submit();
      return true;
    }}
  }}
  return false;
}})()
"""
    return bool(eval_target(target_id, expression))


def run_probe_raw() -> dict[str, Any]:
    target_id = _find_raw_target_id()
    name = build_name()
    before = _raw_count_rows(target_id, name=name)
    navigate_target(target_id, CREATE_URL)
    time.sleep(2.5)
    if not _raw_fill_product_name(target_id, name):
        raise RuntimeError("raw fallback で 商品名 を入力できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で 保存 を押せませんでした")
    time.sleep(3)
    after_create = _raw_count_rows(target_id, name=name)
    deleted_triggered = _raw_delete_row(target_id, name=name)
    if deleted_triggered:
        time.sleep(3)
    after_delete = _raw_count_rows(target_id, name=name)
    snapshot = body_snapshot(target_id)
    return {
        "mode": "raw",
        "name": name,
        "before_count": before,
        "after_create_count": after_create,
        "after_delete_count": after_delete,
        "deleted": after_delete == before,
        "delete_triggered": deleted_triggered,
        "final_url": snapshot.get("url") or "",
    }


async def count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError:
            return run_probe_raw()
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        try:
            name = build_name()
            before = await count_rows(page, name)

            await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
            await page.wait_for_timeout(2000)
            await page.get_by_label("商品名").fill(name)
            await page.get_by_role("button", name="保存").click()
            await page.wait_for_timeout(2500)

            after_create = await count_rows(page, name)
            if after_create != before + 1:
                raise RuntimeError("商品追加後に一覧で intended row を確認できませんでした")

            row = page.locator("tr", has_text=name).first
            form = row.locator("form.form-delete").first
            await form.evaluate("(el) => el.submit()")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(2500)

            after_delete = await count_rows(page, name)
            return {
                "mode": "playwright",
                "name": name,
                "before_count": before,
                "after_create_count": after_create,
                "after_delete_count": after_delete,
                "deleted": after_delete == before,
            }
        finally:
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE exploratory product create/delete probe")
    parser.parse_args()
    if ensure_login(LIST_URL) != 0:
        raise SystemExit("UTAGE browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
