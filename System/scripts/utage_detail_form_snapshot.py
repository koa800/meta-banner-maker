#!/usr/bin/env python3
"""UTAGE の temp product 配下で 商品詳細管理 > 追加 form を読んでから cleanup する。"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import async_playwright


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/product"
CREATE_URL = "https://school.addness.co.jp/product/create"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_detail_probe"


async def _count_rows(page, name: str) -> int:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return await page.locator("tr", has_text=name).count()


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
    return href


async def _snapshot_detail_form(page, detail_url: str) -> dict[str, Any]:
    create_url = urljoin(detail_url.rstrip("/") + "/", "create")
    await page.goto(create_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    payload = await page.evaluate(
        """
() => {
  const fields = [];
  const labels = Array.from(document.querySelectorAll('label'));
  for (const label of labels) {
    const text = (label.innerText || '').trim();
    if (!text) continue;
    const forId = label.getAttribute('for');
    let target = null;
    if (forId) target = document.getElementById(forId);
    if (!target) target = label.querySelector('input,select,textarea');
    if (!target) continue;
    const row = {
      label: text,
      tag: target.tagName.toLowerCase(),
      type: target.getAttribute('type') || null,
      name: target.getAttribute('name') || null,
      required: target.hasAttribute('required'),
    };
    if (target.tagName.toLowerCase() === 'select') {
      row.options = Array.from(target.querySelectorAll('option')).map((opt) => ({
        value: opt.getAttribute('value') || '',
        text: (opt.innerText || '').trim(),
      })).slice(0, 20);
    }
    fields.push(row);
  }
  return {
    title: document.title,
    url: location.href,
    field_count: fields.length,
    fields,
  };
}
"""
    )
    return payload


async def _delete_temp_product(page, name: str) -> None:
    await page.goto(LIST_URL, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=name).first
    form = row.locator("form.form-delete").first
    await form.evaluate("(el) => el.submit()")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2500)


async def run_snapshot() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        name = build_name()
        try:
            before = await _count_rows(page, name)
            detail_url = await _create_temp_product(page, name)
            normalized_detail_url = detail_url
            if not normalized_detail_url.startswith("http"):
                normalized_detail_url = urljoin("https://school.addness.co.jp", normalized_detail_url)
            form_snapshot = await _snapshot_detail_form(page, normalized_detail_url)
            after = await _count_rows(page, name)
            return {
                "name": name,
                "before_count": before,
                "after_count": after,
                "deleted": False,
                "detail_url": normalized_detail_url,
                "form_snapshot": form_snapshot,
            }
        finally:
            try:
                await _delete_temp_product(page, name)
            except Exception:
                pass
            await page.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="UTAGE detail create form snapshot with cleanup")
    parser.parse_args()
    result = asyncio.run(run_snapshot())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
