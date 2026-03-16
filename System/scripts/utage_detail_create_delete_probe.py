#!/usr/bin/env python3
"""UTAGE の exploratory product 配下で 商品詳細管理 > 追加 を create -> cleanup する。"""

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
    return f"ZZ_TEST_{datetime.now().strftime('%Y%m%d_%H%M%S')}_UTAGE_detail_create_probe"


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
        browser = await p.chromium.connect_over_cdp(CDP_URL)
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
    result = asyncio.run(run_probe())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
