#!/usr/bin/env python3
"""UTAGE の temp product 配下で detail に action と bundle を紐づけて保存確認する。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from playwright.async_api import async_playwright

from utage_login_helper import ensure_login


CDP_URL = "http://127.0.0.1:9224"
LIST_URL = "https://school.addness.co.jp/product"
CREATE_URL = "https://school.addness.co.jp/product/create"
ACTION_LABEL = "【スタンダード】事業構築コース　講義保管庫解放アクション"
BUNDLE_LABEL = "スキルプラス講義保管庫全開放"


def build_name() -> str:
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_detail_chain_probe"


async def _count_rows(page, url: str, text: str) -> int:
    await page.goto(url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
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
    return href if href.startswith("http") else urljoin("https://school.addness.co.jp", href)


async def _select_option_by_text(page, name: str, text: str) -> str:
    select = page.locator(f"select[name='{name}']").first
    await select.wait_for(state="visible", timeout=10000)
    option_value = await select.evaluate(
        """(el, wanted) => {
          const options = Array.from(el.options || []);
          const hit = options.find((opt) => (opt.textContent || '').trim().includes(wanted));
          return hit ? hit.value : '';
        }""",
        text,
    )
    if not option_value:
        raise RuntimeError(f"{name} で {text} を選べませんでした")
    await select.select_option(option_value)
    await page.wait_for_timeout(300)
    return str(option_value)


async def _fill_detail_form(page, detail_create_url: str, detail_name: str) -> dict[str, str]:
    await page.goto(detail_create_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    await page.get_by_label("名称").fill(detail_name)
    await page.locator("select[name='payment_type']").select_option("credit_card")
    await page.locator("select[name='payment_method']").select_option("stripe")
    payment_setting = page.locator("select[name='payment_setting_id']").first
    setting_value = await payment_setting.evaluate(
        """(el) => {
          const options = Array.from(el.options || []);
          const hit = options.find((opt) => !!opt.value);
          return hit ? hit.value : '';
        }"""
    )
    if not setting_value:
        raise RuntimeError("payment_setting_id の有効値を取得できませんでした")
    await payment_setting.select_option(setting_value)
    await page.locator("select[name='type']").select_option("one_time")
    await page.locator("input[name='amount']").first.fill("100")
    action_value = await _select_option_by_text(page, "action_id", ACTION_LABEL)
    bundle_value = await _select_option_by_text(page, "bundle_id", BUNDLE_LABEL)
    await page.get_by_role("button", name="保存").click()
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(2500)
    return {
        "payment_setting_id": str(setting_value),
        "action_id": action_value,
        "bundle_id": bundle_value,
    }


async def _open_detail_edit(page, detail_list_url: str, detail_name: str) -> str:
    await page.goto(detail_list_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    row = page.locator("tr", has_text=detail_name).first
    href = await row.locator("a[href*='/edit']").last.get_attribute("href")
    if not href:
        raise RuntimeError("detail row の edit href を取得できませんでした")
    edit_url = href if href.startswith("http") else urljoin("https://school.addness.co.jp", href)
    await page.goto(edit_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(2500)
    return edit_url


async def _read_selected(page, name: str) -> dict[str, str]:
    select = page.locator(f"select[name='{name}']").first
    await select.wait_for(state="visible", timeout=10000)
    return await select.evaluate(
        """(el) => ({
          value: el.value || '',
          text: ((el.options || [])[el.selectedIndex] || {}).textContent?.trim() || ''
        })"""
    )


async def _delete_temp_product(page, name: str) -> int:
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


async def run_probe() -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL, timeout=15000)
        if not browser.contexts:
            raise RuntimeError("Chrome CDP に context が見つかりません")
        context = browser.contexts[0]
        page = await context.new_page()
        product_name = build_name()
        detail_name = f"{product_name}_detail"
        try:
            before_product_count = await _count_rows(page, LIST_URL, product_name)
            detail_list_url = await _create_temp_product(page, product_name)
            detail_create_url = urljoin(detail_list_url.rstrip("/") + "/", "create")
            selected_values = await _fill_detail_form(page, detail_create_url, detail_name)
            detail_row_count = await _count_rows(page, detail_list_url, detail_name)
            edit_url = await _open_detail_edit(page, detail_list_url, detail_name)
            action_selected = await _read_selected(page, "action_id")
            bundle_selected = await _read_selected(page, "bundle_id")
            deleted_rows = await _delete_temp_product(page, product_name)
            after_product_count = await _count_rows(page, LIST_URL, product_name)
            return {
                "product_name": product_name,
                "detail_name": detail_name,
                "before_product_count": before_product_count,
                "detail_row_count": detail_row_count,
                "detail_list_url": detail_list_url,
                "detail_create_url": detail_create_url,
                "detail_edit_url": edit_url,
                "selected_values": selected_values,
                "action_selected": action_selected,
                "bundle_selected": bundle_selected,
                "deleted_rows": deleted_rows,
                "after_product_count": after_product_count,
            }
        finally:
            await page.close()


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit("UTAGE browser session is not ready. Complete login first.")
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
