#!/usr/bin/env python3
"""UTAGE の exploratory bundle を create -> edit -> rollback -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target
from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
SITE_ID = "BQys60HDeOWP"
LIST_URL = f"https://school.addness.co.jp/site/{SITE_ID}/bundle"
CREATE_URL = f"https://school.addness.co.jp/site/{SITE_ID}/bundle/create"
UPDATED_NAME = "ZZ_TEST_UTAGE_bundle_edit_probe_UPDATED"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_bundle_edit_probe"


def _find_raw_target_id() -> str:
    target = (
        find_target(url_contains=f"school.addness.co.jp/site/{SITE_ID}/bundle")
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
    expression = f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  return rows.filter((row) => (row.innerText || '').includes({json.dumps(name, ensure_ascii=False)})).length;
}})()
"""
    return int(eval_target(target_id, expression) or 0)


def _raw_fill_bundle_form(target_id: str, name: str) -> bool:
    expression = f"""
(() => {{
  const setValue = (el, next) => {{
    const proto = el.tagName === 'SELECT'
      ? window.HTMLSelectElement.prototype
      : window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const byLabel = (text) => {{
    const labels = Array.from(document.querySelectorAll('label'));
    for (const label of labels) {{
      if (!((label.innerText || '').trim()).includes(text)) continue;
      return label.control || document.getElementById(label.getAttribute('for')) || label.parentElement.querySelector('input, select');
    }}
    return null;
  }};
  const nameInput = byLabel('バンドルコース名') || document.querySelector('input[name="name"], input');
  if (!nameInput) return false;
  nameInput.focus();
  setValue(nameInput, {json.dumps(name, ensure_ascii=False)});

  const addCourse = document.querySelector('select[name="add-course"]');
  if (addCourse) {{
    const options = Array.from(addCourse.options || []);
    const firstValid = options.find((opt) => opt.value && opt.value !== '0');
    if (firstValid) {{
      setValue(addCourse, firstValid.value);
    }}
  }}
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
    if (button.form) {
      button.form.submit();
      return true;
    }
    button.click();
    return true;
  }
  return false;
})()
"""
    return bool(eval_target(target_id, expression))


def _raw_get_edit_link(target_id: str, name: str) -> str:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    expression = f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    if (!((row.innerText || '').includes({json.dumps(name, ensure_ascii=False)}))) continue;
    const anchors = Array.from(row.querySelectorAll('a'));
    for (const anchor of anchors) {{
      const text = (anchor.innerText || '').trim();
      const href = anchor.getAttribute('href') || '';
      if (text.includes('編集') && href) {{
        return href.startsWith('http') ? href : `https://school.addness.co.jp${{href}}`;
      }}
    }}
  }}
  return '';
}})()
"""
    edit_url = str(eval_target(target_id, expression) or "")
    if not edit_url:
      raise RuntimeError("raw fallback で バンドルコース一覧の row から edit link を取得できませんでした")
    return edit_url


def _raw_read_values(target_id: str) -> dict[str, Any]:
    expression = """
(() => {
  const byLabel = (text) => {
    const labels = Array.from(document.querySelectorAll('label'));
    for (const label of labels) {
      if (!((label.innerText || '').trim()).includes(text)) continue;
      const control = label.control || document.getElementById(label.getAttribute('for')) || label.parentElement.querySelector('input, select');
      if (control) return control;
    }
    return null;
  };
  const input = byLabel('バンドルコース名') || document.querySelector('input[name="name"], input');
  return {
    'バンドルコース名': input ? (input.value || '') : ''
  };
})()
"""
    return dict(eval_target(target_id, expression) or {})


def _raw_set_bundle_name(target_id: str, next_value: str) -> bool:
    expression = f"""
(() => {{
  const setValue = (el, next) => {{
    const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const byLabel = (text) => {{
    const labels = Array.from(document.querySelectorAll('label'));
    for (const label of labels) {{
      if (!((label.innerText || '').trim()).includes(text)) continue;
      return label.control || document.getElementById(label.getAttribute('for')) || label.parentElement.querySelector('input, select');
    }}
    return null;
  }};
  const input = byLabel('バンドルコース名') || document.querySelector('input[name="name"], input');
  if (!input) return false;
  input.focus();
  setValue(input, {json.dumps(next_value, ensure_ascii=False)});
  return true;
}})()
"""
    return bool(eval_target(target_id, expression))


def _raw_delete_rows(target_id: str, name: str) -> int:
    deleted = 0
    while True:
        navigate_target(target_id, LIST_URL)
        time.sleep(2.5)
        expression = f"""
(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    if (!((row.innerText || '').includes({json.dumps(name, ensure_ascii=False)}))) continue;
    const form = row.querySelector('form.form-delete');
    if (!form) return false;
    form.submit();
    return true;
  }}
  return false;
}})()
"""
        triggered = bool(eval_target(target_id, expression))
        if not triggered:
            break
        deleted += 1
        time.sleep(3)
    return deleted


def run_probe_raw() -> dict[str, Any]:
    target_id = _find_raw_target_id()
    name = build_name()
    before_count = _raw_count_rows(target_id, name)
    navigate_target(target_id, CREATE_URL)
    time.sleep(2.5)
    if not _raw_fill_bundle_form(target_id, name):
        raise RuntimeError("raw fallback で バンドルコース作成フォーム を入力できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で 保存 を押せませんでした")
    time.sleep(3)
    after_create_count = _raw_count_rows(target_id, name)
    edit_url = _raw_get_edit_link(target_id, name)
    navigate_target(target_id, edit_url)
    time.sleep(2.5)
    before_values = _raw_read_values(target_id)
    if not _raw_set_bundle_name(target_id, UPDATED_NAME):
        raise RuntimeError("raw fallback で バンドルコース名 を更新できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で 編集保存 を押せませんでした")
    time.sleep(3)
    navigate_target(target_id, edit_url)
    time.sleep(2.5)
    after_values = _raw_read_values(target_id)
    if not _raw_set_bundle_name(target_id, name):
        raise RuntimeError("raw fallback で rollback 値 を更新できませんでした")
    if not _raw_click_save(target_id):
        raise RuntimeError("raw fallback で rollback 保存 を押せませんでした")
    time.sleep(3)
    navigate_target(target_id, edit_url)
    time.sleep(2.5)
    rollback_values = _raw_read_values(target_id)
    deleted_rows = _raw_delete_rows(target_id, name)
    after_delete_count = _raw_count_rows(target_id, name)
    return {
        "mode": "raw",
        "before_count": before_count,
        "after_create_count": after_create_count,
        "edit_url": edit_url,
        "before_values": before_values,
        "after_values": after_values,
        "rollback_values": rollback_values,
        "deleted_rows": deleted_rows,
        "after_delete_count": after_delete_count,
    }


async def _count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


async def _delete_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    deleted = 0
    while await page.locator("tr", has_text=name).count():
        row = page.locator("tr", has_text=name).first
        form = row.locator("form.form-delete").first
        await form.evaluate("(el) => el.submit()")
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(2500)
        deleted += 1
        await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(1500)
    return deleted


async def _create_bundle(page, name: str) -> None:
    await page.goto(CREATE_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    await page.get_by_label("バンドルコース名").fill(name)
    add_course = page.locator('select[name="add-course"]').first
    values = await add_course.locator("option").evaluate_all(
        "(els) => els.map((el) => ({ value: el.value, text: (el.innerText || '').trim() }))"
    )
    first_valid = next((item["value"] for item in values if item["value"] and item["value"] != "0"), None)
    if first_valid:
        await add_course.select_option(first_valid)
    await page.get_by_role("button", name="保存").click()
    await page.wait_for_timeout(2500)


async def _open_edit_link(page, name: str) -> str:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=name).first
    href = None
    try:
        link = row.locator('a[href*="/edit"]').first
        href = await link.get_attribute("href")
    except Exception:
        href = None
    if not href:
        anchors = await row.locator("a").evaluate_all(
            """(els) => els.map((el) => ({
                text: (el.innerText || '').trim(),
                href: el.getAttribute('href') || ''
            }))"""
        )
        for anchor in anchors:
            text = str(anchor.get("text") or "")
            candidate = str(anchor.get("href") or "")
            if "編集" in text and candidate:
                href = candidate
                break
    if not href:
        raise RuntimeError("バンドルコース一覧の row から edit link を取得できませんでした")
    edit_url = href if href.startswith("http") else f"https://school.addness.co.jp{href}"
    await page.goto(edit_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return edit_url


async def _save(page) -> None:
    candidates = [
        page.locator("#save-basic"),
        page.get_by_role("button", name="保存", exact=True),
        page.get_by_role("button", name="保存"),
    ]
    for locator in candidates:
        try:
            if await locator.first.is_visible(timeout=800):
                await locator.first.click(timeout=5000)
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(2000)
                return
        except Exception:
            continue
    raise RuntimeError("保存 ボタンを確定できませんでした")


async def _read_values(page) -> dict[str, Any]:
    bundle_name = await page.get_by_label("バンドルコース名").input_value()
    return {"バンドルコース名": bundle_name}


async def _set_bundle_name(page, next_value: str) -> None:
    field = page.get_by_label("バンドルコース名")
    await field.fill(next_value)
    await page.wait_for_timeout(300)
    await _save(page)


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
        name = build_name()
        try:
            before_count = await _count_rows(page, name)
            await _create_bundle(page, name)
            after_create_count = await _count_rows(page, name)
            if after_create_count == before_count:
                return run_probe_raw()
            edit_url = await _open_edit_link(page, name)
            before_values = await _read_values(page)
            await _set_bundle_name(page, UPDATED_NAME)
            after_values = await _read_values(page)
            await _set_bundle_name(page, name)
            rollback_values = await _read_values(page)
            deleted_rows = await _delete_rows(page, name)
            after_delete_count = await _count_rows(page, name)
            return {
                "mode": "playwright",
                "before_count": before_count,
                "after_create_count": after_create_count,
                "edit_url": edit_url,
                "before_values": before_values,
                "after_values": after_values,
                "rollback_values": rollback_values,
                "deleted_rows": deleted_rows,
                "after_delete_count": after_delete_count,
            }
        except RuntimeError:
            return run_probe_raw()
        finally:
            await page.close()


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit(1)
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
