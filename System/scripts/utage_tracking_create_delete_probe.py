#!/usr/bin/env python3
"""UTAGE の temporary funnel 配下で 登録経路 を create -> rollback する。"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime
from typing import Any

from playwright.async_api import async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

sys.path.insert(0, "/Users/koa800/Desktop/cursor/System/scripts")

from chrome_raw_cdp import eval_target
from chrome_raw_cdp import navigate_target
from utage_funnel_create_delete_probe import _create_funnel, _delete_funnel
from utage_funnel_create_delete_probe import _find_raw_target_id
from utage_funnel_create_delete_probe import _raw_create_funnel
from utage_funnel_create_delete_probe import _raw_delete_funnel
from utage_login_helper import CDP_URL, ensure_login_raw


LIST_URL = "https://school.addness.co.jp/funnel"


def _build_name() -> str:
    return f"ZZ_TEST_UTAGE_tracking_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


async def _resolve_tracking_urls(page, funnel_id: int) -> dict[str, str]:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    result = await page.evaluate(
        """(createdId) => {
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {
    const del = row.querySelector(`form.form-delete[action$="/funnel/${createdId}"]`);
    if (!del) continue;
    const pageLink = Array.from(row.querySelectorAll('a')).find((a) => (a.innerText || '').trim() === 'ページ一覧');
    if (!pageLink) return { tracking_url: '', tracking_create_url: '' };
    const base = pageLink.href.replace(/\/page$/, '');
    return {
      tracking_url: `${base}/tracking`,
      tracking_create_url: `${base}/tracking/create`,
    };
  }
  return { tracking_url: '', tracking_create_url: '' };
}""",
        funnel_id,
    )
    return result


def _resolve_tracking_urls_raw(target_id: str, funnel_id: int) -> dict[str, str]:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)
    return eval_target(
        target_id,
        f"""(() => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    const del = row.querySelector('form.form-delete[action$="/funnel/{funnel_id}"]');
    if (!del) continue;
    const pageLink = Array.from(row.querySelectorAll('a')).find((a) => (a.innerText || '').trim() === 'ページ一覧');
    if (!pageLink) return {{ tracking_url: '', tracking_create_url: '' }};
    const base = pageLink.href.replace(/\\/page$/, '');
    return {{
      tracking_url: `${{base}}/tracking`,
      tracking_create_url: `${{base}}/tracking/create`,
    }};
  }}
  return {{ tracking_url: '', tracking_create_url: '' }};
}})()""",
    ) or {}


async def _capture_form(page) -> dict[str, Any]:
    return await page.evaluate(
        """() => {
  const labels = Array.from(document.querySelectorAll('label'))
    .map((el) => (el.innerText || '').trim())
    .filter(Boolean);
  const selects = Array.from(document.querySelectorAll('select')).map((el) => ({
    name: el.name || '',
    options: Array.from(el.options || []).map((opt) => ({
      value: opt.value || '',
      text: (opt.textContent || '').trim(),
      selected: !!opt.selected,
      disabled: !!opt.disabled,
    })),
  }));
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'))
    .map((el) => (el.innerText || el.value || '').trim())
    .filter(Boolean);
  const heading = (document.querySelector('h1, h2, h3')?.innerText || '').trim();
  return { heading, labels, buttons, selects, url: location.href };
}"""
    )


def _capture_form_raw(target_id: str) -> dict[str, Any]:
    return eval_target(
        target_id,
        """(() => {
  const labels = Array.from(document.querySelectorAll('label'))
    .map((el) => (el.innerText || '').trim())
    .filter(Boolean);
  const selects = Array.from(document.querySelectorAll('select')).map((el) => ({
    name: el.name || '',
    options: Array.from(el.options || []).map((opt) => ({
      value: opt.value || '',
      text: (opt.textContent || '').trim(),
      selected: !!opt.selected,
      disabled: !!opt.disabled,
    })),
  }));
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'))
    .map((el) => (el.innerText || el.value || '').trim())
    .filter(Boolean);
  const heading = (document.querySelector('h1, h2, h3')?.innerText || '').trim();
  return { heading, labels, buttons, selects, url: location.href };
})()""",
    ) or {}


async def _fill_tracking_name(page, route_name: str) -> bool:
    return await page.evaluate(
        """(value) => {
  const setValue = (el, next) => {
    const proto = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) {
      descriptor.set.call(el, next);
    } else {
      el.value = next;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  };
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {
    const text = (label.innerText || '').trim();
    if (!text.includes('登録経路名') && !text.includes('名称')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') {
      target.focus();
      setValue(target, value);
      return true;
    }
  }
  const fallback = document.querySelector('input[name="name"], input[name="title"], input[type="text"]');
  if (!fallback) return false;
  fallback.focus();
  setValue(fallback, value);
  return true;
}""",
        route_name,
    )


def _fill_tracking_name_raw(target_id: str, route_name: str) -> bool:
    return bool(
        eval_target(
            target_id,
            f"""((value) => {{
  const setValue = (el, next) => {{
    const proto = window.HTMLInputElement.prototype;
    const descriptor = Object.getOwnPropertyDescriptor(proto, 'value');
    if (descriptor && descriptor.set) {{
      descriptor.set.call(el, next);
    }} else {{
      el.value = next;
    }}
    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }};
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {{
    const text = (label.innerText || '').trim();
    if (!text.includes('登録経路名') && !text.includes('名称')) continue;
    const target = label.control || document.getElementById(label.getAttribute('for'));
    if (target && target.tagName === 'INPUT') {{
      target.focus();
      setValue(target, value);
      return true;
    }}
  }}
  const fallback = document.querySelector('input[name="name"], input[name="title"], input[type="text"]');
  if (!fallback) return false;
  fallback.focus();
  setValue(fallback, value);
  return true;
}})({json.dumps(route_name, ensure_ascii=False)})""",
        )
    )


async def _select_first_non_empty(page) -> bool:
    return await page.evaluate(
        """() => {
  let touched = false;
  for (const select of Array.from(document.querySelectorAll('select'))) {
    const options = Array.from(select.options || []).filter((opt) => opt.value && !opt.disabled);
    if (!options.length) continue;
    select.value = options[0].value;
    select.dispatchEvent(new Event('input', { bubbles: true }));
    select.dispatchEvent(new Event('change', { bubbles: true }));
    touched = true;
  }
  return touched;
}"""
    )


def _select_first_non_empty_raw(target_id: str) -> bool:
    return bool(
        eval_target(
            target_id,
            """(() => {
  let touched = false;
  for (const select of Array.from(document.querySelectorAll('select'))) {
    const options = Array.from(select.options || []).filter((opt) => opt.value && !opt.disabled);
    if (!options.length) continue;
    select.value = options[0].value;
    select.dispatchEvent(new Event('input', { bubbles: true }));
    select.dispatchEvent(new Event('change', { bubbles: true }));
    touched = true;
  }
  return touched;
})()""",
        )
    )


async def _save(page) -> bool:
    return await page.evaluate(
        """() => {
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'));
  for (const button of buttons) {
    const text = (button.innerText || button.value || '').trim();
    if (!text.includes('保存') && !text.includes('追加')) continue;
    button.click();
    return true;
  }
  return false;
}"""
    )


def _save_raw(target_id: str) -> bool:
    return bool(
        eval_target(
            target_id,
            """(() => {
  const buttons = Array.from(document.querySelectorAll('button, input[type="submit"], a.btn'));
  for (const button of buttons) {
    const text = (button.innerText || button.value || '').trim();
    if (!text.includes('保存') && !text.includes('追加')) continue;
    button.click();
    return true;
  }
  return false;
})()""",
        )
    )


async def _find_created_row(page, route_name: str, tracking_url: str) -> dict[str, Any]:
    await page.goto(tracking_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.evaluate(
        """(routeName) => {
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {
    if (!(row.innerText || '').includes(routeName)) continue;
    const form = row.querySelector('form.form-delete');
    return {
      found: true,
      text: (row.innerText || '').trim(),
      delete_action: form ? form.getAttribute('action') || '' : '',
    };
  }
  return { found: false, text: '', delete_action: '' };
}""",
        route_name,
    )


def _find_created_row_raw(target_id: str, route_name: str, tracking_url: str) -> dict[str, Any]:
    navigate_target(target_id, tracking_url)
    time.sleep(2.5)
    return eval_target(
        target_id,
        f"""((routeName) => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    if (!(row.innerText || '').includes(routeName)) continue;
    const form = row.querySelector('form.form-delete');
    return {{
      found: true,
      text: (row.innerText || '').trim(),
      delete_action: form ? form.getAttribute('action') || '' : '',
    }};
  }}
  return {{ found: false, text: '', delete_action: '' }};
}})({json.dumps(route_name, ensure_ascii=False)})""",
    ) or {}


async def _delete_tracking(page, route_name: str) -> bool:
    return await page.evaluate(
        """(routeName) => {
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {
    if (!(row.innerText || '').includes(routeName)) continue;
    const form = row.querySelector('form.form-delete');
    if (!form) return false;
    form.submit();
    return true;
  }
  return false;
}""",
        route_name,
    )


def _delete_tracking_raw(target_id: str, route_name: str, tracking_url: str) -> bool:
    navigate_target(target_id, tracking_url)
    time.sleep(2.5)
    return bool(
        eval_target(
            target_id,
            f"""((routeName) => {{
  const rows = Array.from(document.querySelectorAll('tr'));
  for (const row of rows) {{
    if (!(row.innerText || '').includes(routeName)) continue;
    const form = row.querySelector('form.form-delete');
    if (!form) return false;
    form.submit();
    return true;
  }}
  return false;
}})({json.dumps(route_name, ensure_ascii=False)})""",
        )
    )


def run_probe_raw() -> dict[str, Any]:
    if ensure_login_raw(LIST_URL) != 0:
        raise RuntimeError("UTAGE raw login helper が current で通りませんでした")

    target_id = _find_raw_target_id()
    funnel_created = _raw_create_funnel(target_id)
    route_name = _build_name()
    urls = _resolve_tracking_urls_raw(target_id, int(funnel_created["created_id"]))
    if not urls.get("tracking_create_url"):
        raise RuntimeError("temporary funnel の 登録経路 create URL を取得できませんでした")

    navigate_target(target_id, str(urls["tracking_create_url"]))
    time.sleep(2.5)
    before = _capture_form_raw(target_id)

    if not _fill_tracking_name_raw(target_id, route_name):
        raise RuntimeError("登録経路名 を入力できませんでした")
    _select_first_non_empty_raw(target_id)
    if not _save_raw(target_id):
        raise RuntimeError("登録経路 create で 保存 を押せませんでした")
    time.sleep(3)

    created_row = _find_created_row_raw(target_id, route_name, str(urls["tracking_url"]))
    deleted = False
    if created_row.get("found"):
        deleted = _delete_tracking_raw(target_id, route_name, str(urls["tracking_url"]))
        if deleted:
            time.sleep(2.5)

    funnel_deleted = _raw_delete_funnel(target_id, int(funnel_created["created_id"]))

    return {
        "mode": "raw",
        "route_name": route_name,
        "before": before,
        "tracking_url": urls.get("tracking_url") or "",
        "tracking_create_url": urls.get("tracking_create_url") or "",
        "created_row": created_row,
        "tracking_deleted": deleted,
        "funnel_created": funnel_created,
        "funnel_deleted": funnel_deleted,
    }


async def run_probe() -> dict[str, Any]:
    if ensure_login_raw(LIST_URL) != 0:
        raise RuntimeError("UTAGE login helper が current で通りませんでした")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        except PlaywrightTimeoutError:
            return run_probe_raw()
        if not browser.contexts:
            raise RuntimeError("UTAGE browser context を取得できませんでした")
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()

        funnel_created = await _create_funnel(page)
        route_name = _build_name()
        urls = await _resolve_tracking_urls(page, int(funnel_created["created_id"]))
        if not urls.get("tracking_create_url"):
            raise RuntimeError("temporary funnel の 登録経路 create URL を取得できませんでした")

        await page.goto(str(urls["tracking_create_url"]), wait_until="domcontentloaded", timeout=120000)
        await page.wait_for_timeout(2500)
        before = await _capture_form(page)

        filled = await _fill_tracking_name(page, route_name)
        if not filled:
            raise RuntimeError("登録経路名 を入力できませんでした")
        await _select_first_non_empty(page)

        clicked = await _save(page)
        if not clicked:
            raise RuntimeError("登録経路 create で 保存 を押せませんでした")
        await page.wait_for_timeout(3000)

        created_row = await _find_created_row(page, route_name, str(urls["tracking_url"]))
        deleted = False
        if created_row.get("found"):
            deleted = await _delete_tracking(page, route_name)
            if deleted:
                await page.wait_for_timeout(2500)

        funnel_deleted = await _delete_funnel(page, int(funnel_created["created_id"]))

        return {
            "mode": "playwright",
            "route_name": route_name,
            "before": before,
            "tracking_url": urls.get("tracking_url") or "",
            "tracking_create_url": urls.get("tracking_create_url") or "",
            "created_row": created_row,
            "tracking_deleted": deleted,
            "funnel_created": funnel_created,
            "funnel_deleted": funnel_deleted,
        }


def main() -> None:
    print(json.dumps(asyncio.run(run_probe()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
