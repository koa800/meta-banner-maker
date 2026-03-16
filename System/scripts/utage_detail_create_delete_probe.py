#!/usr/bin/env python3
"""UTAGE の exploratory product 配下で 商品詳細管理 > 追加 を create -> cleanup する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

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
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_detail_create_probe"


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


def _raw_count_rows(target_id: str, url: str, text: str) -> int:
    navigate_target(target_id, url)
    time.sleep(2.5)
    return int(
        eval_target(
            target_id,
            f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  return rows.filter((row) => (row.innerText || '').includes({json.dumps(text, ensure_ascii=False)})).length;
}})()
""",
        )
        or 0
    )


def _raw_fill_input_by_label(target_id: str, label_text: str, value: str) -> bool:
    expression = f"""
(() => {{
  const wanted = {json.dumps(label_text, ensure_ascii=False)};
  const next = {json.dumps(value, ensure_ascii=False)};
  const setValue = (el, val) => {{
    const proto = el.tagName === 'TEXTAREA'
      ? window.HTMLTextAreaElement.prototype
      : window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, val);
    }} else {{
      el.value = val;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {{
    const text = (label.innerText || '').trim();
    if (!text.includes(wanted)) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) {{
      target.focus();
      setValue(target, next);
      return true;
    }}
  }}
  return false;
}})()
"""
    return bool(eval_target(target_id, expression))


def _raw_select_value(target_id: str, name: str, value: str) -> bool:
    expression = f"""
(() => {{
  const el = document.querySelector('select[name={json.dumps(name)}]');
  if (!el) return false;
  el.value = {json.dumps(value)};
  el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  return el.value === {json.dumps(value)};
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


def _raw_create_temp_product(target_id: str, name: str) -> str:
    navigate_target(target_id, CREATE_URL)
    time.sleep(2.5)
    if not _raw_fill_input_by_label(target_id, "商品名", name):
        raise RuntimeError("raw fallback で temp product の商品名を入力できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で temp product の保存を押せませんでした")
    time.sleep(3)
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    href = eval_target(
        target_id,
        f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    const text = (row.innerText || '').trim();
    if (!text.includes({json.dumps(name, ensure_ascii=False)})) continue;
    const link = Array.from(row.querySelectorAll('a')).find((a) => (a.innerText || '').trim().includes('開く'));
    return link ? link.href : '';
  }}
  return '';
}})()
""",
    )
    if not href:
        raise RuntimeError("raw fallback で temp product の `開く` href を取得できませんでした")
    return str(href)


def _raw_fill_minimum_detail(target_id: str, detail_create_url: str, detail_name: str) -> dict[str, Any]:
    navigate_target(target_id, detail_create_url)
    time.sleep(2.5)
    if not _raw_fill_input_by_label(target_id, "名称", detail_name):
        raise RuntimeError("raw fallback で detail 名称を入力できませんでした")
    if not _raw_select_value(target_id, "payment_type", "credit_card"):
        raise RuntimeError("raw fallback で payment_type を選べませんでした")
    if not _raw_select_value(target_id, "payment_method", "stripe"):
        raise RuntimeError("raw fallback で payment_method を選べませんでした")
    if not _raw_select_value(target_id, "payment_setting_id", "default"):
        _raw_select_value(target_id, "payment_setting_id", "1")
    if not _raw_select_value(target_id, "type", "one_time"):
        raise RuntimeError("raw fallback で type を選べませんでした")
    expression_amount = """
(() => {
  const el = document.querySelector('input[name="amount"]');
  if (!el) return false;
  const proto = window.HTMLInputElement.prototype;
  const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
  if (descriptor && descriptor.set) {
    descriptor.set.call(el, '100');
  } else {
    el.value = '100';
  }
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return true;
})()
"""
    if not eval_target(target_id, expression_amount):
        raise RuntimeError("raw fallback で amount を入力できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で detail 保存を押せませんでした")
    time.sleep(3)
    error_texts = eval_target(
        target_id,
        """
(() => Array.from(document.querySelectorAll('.invalid-feedback, .help-block-error, .error, .text-danger'))
  .map((node) => (node.innerText || '').trim())
  .filter(Boolean))()
""",
    ) or []
    return {
        "url": body_snapshot(target_id).get("url") or "",
        "error_texts": error_texts,
    }


def _raw_delete_temp_product(target_id: str, name: str) -> None:
    while True:
        navigate_target(target_id, LIST_URL)
        time.sleep(2.5)
        deleted = bool(
            eval_target(
                target_id,
                f"""
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
""",
            )
        )
        if not deleted:
            break
        time.sleep(3)


def run_probe_raw() -> dict[str, Any]:
    target_id = _find_raw_target_id()
    product_name = build_name()
    detail_name = f"{product_name}_detail"
    before_product_count = _raw_count_rows(target_id, LIST_URL, product_name)
    detail_list_url = None
    try:
        detail_list_url = _raw_create_temp_product(target_id, product_name)
        detail_create_url = urljoin(detail_list_url.rstrip("/") + "/", "create")
        result = _raw_fill_minimum_detail(target_id, detail_create_url, detail_name)
        after_product_count = _raw_count_rows(target_id, LIST_URL, product_name)
        detail_row_count = _raw_count_rows(target_id, detail_list_url, detail_name) if detail_list_url else 0
        return {
            "mode": "raw",
            "product_name": product_name,
            "detail_name": detail_name,
            "before_product_count": before_product_count,
            "after_product_count": after_product_count,
            "detail_row_count": detail_row_count,
            "save_result": result,
        }
    finally:
        try:
            _raw_delete_temp_product(target_id, product_name)
        except Exception:
            pass


async def _count_rows(page, url: str, text: str) -> int:
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2000)
    return await page.locator("tr", has_text=text).count()


async def _create_temp_product(page, name: str) -> str:
    await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2000)
    await page.get_by_label("商品名").fill(name)
    await page.get_by_role("button", name="保存").click()
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=name).first
    href = await row.locator("a", has_text="開く").get_attribute("href")
    if not href:
        raise RuntimeError("temp product の `開く` href を取得できませんでした")
    return urljoin("https://school.addness.co.jp", href)


async def _fill_minimum_detail(page, detail_create_url: str, detail_name: str) -> dict[str, Any]:
    await page.goto(detail_create_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)

    await page.get_by_label("名称").fill(detail_name)
    await page.locator('select[name="payment_type"]').select_option("credit_card")
    await page.locator('select[name="payment_method"]').select_option("stripe")
    await page.locator('select[name="payment_setting_id"]').select_option(label="デフォルト")
    await page.locator('select[name="type"]').select_option("one_time")
    await page.locator('input[name="amount"]').first.fill("100")

    await page.get_by_role("button", name="保存").click()
    await page.wait_for_timeout(2500)

    error_texts = []
    error_locator = page.locator(".invalid-feedback, .help-block-error, .error, .text-danger")
    for i in range(await error_locator.count()):
        text = (await error_locator.nth(i).inner_text()).strip()
        if text:
            error_texts.append(text)

    return {
        "url": page.url,
        "error_texts": error_texts,
    }


async def _delete_temp_product(page, name: str) -> None:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    while await page.locator("tr", has_text=name).count():
        row = page.locator("tr", has_text=name).first
        form = row.locator("form.form-delete").first
        await form.evaluate("(el) => el.submit()")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2500)
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1500)


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
        product_name = build_name()
        detail_name = f"{product_name}_detail"
        detail_list_url = None
        try:
            before_product_count = await _count_rows(page, LIST_URL, product_name)
            detail_url = await _create_temp_product(page, product_name)
            detail_list_url = detail_url
            detail_create_url = urljoin(detail_url.rstrip("/") + "/", "create")
            result = await _fill_minimum_detail(page, detail_create_url, detail_name)
            after_product_count = await _count_rows(page, LIST_URL, product_name)
            detail_row_count = 0
            if detail_list_url:
                detail_row_count = await _count_rows(page, detail_list_url, detail_name)
            return {
                "product_name": product_name,
                "detail_name": detail_name,
                "before_product_count": before_product_count,
                "after_product_count": after_product_count,
                "detail_row_count": detail_row_count,
                "save_result": result,
            }
        finally:
            try:
                await _delete_temp_product(page, product_name)
            except Exception:
                pass
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE detail create/delete probe")
    parser.parse_args()
    if ensure_login(LIST_URL) != 0:
        raise SystemExit("UTAGE browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
