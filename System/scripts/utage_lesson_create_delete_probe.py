#!/usr/bin/env python3
"""UTAGE の exploratory lesson を create -> delete で検証する。"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from typing import Any

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import body_snapshot
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target
from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
SITE_ID = "BQys60HDeOWP"
COURSE_ID = "9cc2NZYZVTap"
LIST_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course/{COURSE_ID}/lesson"
CREATE_URL = f"https://school.addness.co.jp/site/{SITE_ID}/course/{COURSE_ID}/lesson/create"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_lesson_probe"


def _find_raw_target_id() -> str:
    target = (
        find_target(url_contains=f"/site/{SITE_ID}/course/{COURSE_ID}/lesson")
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


def _raw_fill_lesson_form(target_id: str, name: str) -> bool:
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

  const group = document.querySelector('#lesson_group_id');
  if (!group) return false;
  const validGroup = Array.from(group.options || []).find((opt) => opt.value && opt.value !== '0');
  if (validGroup) setValue(group, validGroup.value);

  const nameInput = document.querySelector('#name, input[name="name"]');
  if (!nameInput) return false;
  setValue(nameInput, %s);

  const textarea = document.querySelector('textarea[name="contents"]');
  if (textarea) {{
    textarea.value = '<p>ZZ lesson probe</p>';
    textarea.dispatchEvent(new Event('input', {{ bubbles: true }}));
    textarea.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }}

  return true;
}})()
""" % json.dumps(name, ensure_ascii=False)
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


def _raw_error_texts(target_id: str) -> list[str]:
    expression = """
(() => Array.from(document.querySelectorAll('.invalid-feedback, .help-block-error, .error, .text-danger'))
  .map((el) => (el.innerText || '').trim())
  .filter(Boolean))()
"""
    return eval_target(target_id, expression) or []


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
    before = _raw_count_rows(target_id, name=name)
    navigate_target(target_id, CREATE_URL)
    time.sleep(2.5)
    if not _raw_fill_lesson_form(target_id, name):
        raise RuntimeError('raw fallback で レッスン作成フォーム を入力できませんでした')
    if not _raw_click_save(target_id):
        raise RuntimeError('raw fallback で 保存 を押せませんでした')
    time.sleep(3)
    error_texts = _raw_error_texts(target_id)
    after_create = _raw_count_rows(target_id, name=name)
    deleted_rows = _raw_delete_rows(target_id, name=name)
    after_delete = _raw_count_rows(target_id, name=name)
    snapshot = body_snapshot(target_id)
    return {
        'mode': 'raw',
        'name': name,
        'before_count': before,
        'after_create_count': after_create,
        'after_delete_count': after_delete,
        'deleted_rows': deleted_rows,
        'save_url': snapshot.get('url') or '',
        'error_texts': error_texts,
    }


async def count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until='domcontentloaded', timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator('tr', has_text=name).count()


async def delete_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until='domcontentloaded', timeout=120000)
    await page.wait_for_timeout(2500)
    deleted = 0
    while await page.locator('tr', has_text=name).count():
        row = page.locator('tr', has_text=name).first
        form = row.locator('form.form-delete').first
        await form.evaluate('(el) => el.submit()')
        await page.wait_for_load_state('networkidle')
        await page.wait_for_timeout(2500)
        deleted += 1
        await page.goto(LIST_URL, wait_until='domcontentloaded', timeout=120000)
        await page.wait_for_timeout(1500)
    return deleted


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError:
            return run_probe_raw()
        if not browser.contexts:
            raise RuntimeError('Chrome CDP に context が見つかりません')
        context = browser.contexts[0]
        page = await context.new_page()
        name = build_name()
        try:
            before = await count_rows(page, name)
            await page.goto(CREATE_URL, wait_until='domcontentloaded', timeout=120000)
            await page.wait_for_timeout(2500)
            group = page.locator('#lesson_group_id').first
            values = await group.locator('option').evaluate_all("(els) => els.map((el) => ({ value: el.value, text: (el.innerText || '').trim() }))")
            first_valid = next((item['value'] for item in values if item['value'] and item['value'] != '0'), None)
            if first_valid:
                await group.select_option(first_valid)
            await page.get_by_label('レッスン名').fill(name)
            contents = page.locator('textarea[name="contents"]').first
            if await contents.count():
                await contents.evaluate(
                    """(el, value) => {
                        el.value = value;
                        el.dispatchEvent(new Event('input', { bubbles: true }));
                        el.dispatchEvent(new Event('change', { bubbles: true }));
                    }""",
                    "<p>ZZ lesson probe</p>",
                )
            await page.get_by_role('button', name='保存').click()
            await page.wait_for_timeout(2500)
            error_texts = []
            error_locator = page.locator('.invalid-feedback, .help-block-error, .error, .text-danger')
            for i in range(await error_locator.count()):
                text = (await error_locator.nth(i).inner_text()).strip()
                if text:
                    error_texts.append(text)
            after_create = await count_rows(page, name)
            deleted = await delete_rows(page, name)
            after_delete = await count_rows(page, name)
            return {
                'mode': 'playwright',
                'name': name,
                'before_count': before,
                'after_create_count': after_create,
                'after_delete_count': after_delete,
                'deleted_rows': deleted,
                'save_url': page.url,
                'error_texts': error_texts,
            }
        finally:
            await page.close()


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit('UTAGE browser session is not ready. Complete login first.')
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
