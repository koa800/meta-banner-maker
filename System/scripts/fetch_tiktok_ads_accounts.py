#!/usr/bin/env python3
"""TikTokビジネスセンターの広告主アカウント一覧を取得して設定へ保存する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path

from playwright.async_api import Page, async_playwright


ROOT = Path(__file__).resolve().parents[2]
CREDENTIAL_PATH = ROOT / "System" / "credentials" / "tiktok_ads.json"
CDP_URL = "http://127.0.0.1:9224"
ADV_URL_RE = re.compile(r"^https://business\.tiktok\.com/manage/accounts/adv\?org_id=(\d+)")
BUSINESS_URL_RE = re.compile(r"^https://business\.tiktok\.com/manage/(?:overview|accounts/adv)\?org_id=(\d+)")
TOTAL_RE = re.compile(r"合計\s*(\d+)\s*件の記録")
ENTRY_RE = re.compile(
    r"(?P<name>[^\n]+)\n"
    r"ID:\s*(?P<id>\d{19})\n\s*\n"
    r"(?P<status>[^\n]+)\n\s*"
    r"(?P<owner>[^\n]+)",
)


def load_config() -> dict:
    return json.loads(CREDENTIAL_PATH.read_text())


def save_config(data: dict) -> None:
    CREDENTIAL_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def business_name_for(account_name: str, owner_name: str) -> str:
    if account_name == "マイグレ株式会社_ADD":
        return "スキルプラス"
    if "デザジュク" in account_name:
        return "デザジュク"
    if "ADD" in account_name or "Addness" in owner_name:
        return "Addness"
    return "スキルプラス"


def parse_total_count(body: str) -> int | None:
    match = TOTAL_RE.search(body)
    if not match:
        return None
    return int(match.group(1))


def parse_accounts(body: str) -> list[dict[str, str]]:
    accounts: list[dict[str, str]] = []
    seen: set[str] = set()

    for chunk in body.split("広告マネージャーに移動"):
        match = ENTRY_RE.search(chunk)
        if not match:
            continue

        advertiser_name = match.group("name").strip()
        advertiser_id = match.group("id").strip()
        status = match.group("status").strip()
        owner_name = match.group("owner").strip()

        if advertiser_id in seen:
            continue

        seen.add(advertiser_id)
        accounts.append(
            {
                "advertiser_id": advertiser_id,
                "advertiser_name": advertiser_name,
                "business_name": business_name_for(advertiser_name, owner_name),
                "status": status,
                "owner_name": owner_name,
            }
        )

    return accounts


async def find_tiktok_page(browser) -> tuple[Page, str]:
    for context in browser.contexts:
        for page in context.pages:
            url = page.url or ""
            match = BUSINESS_URL_RE.match(url)
            if match:
                return page, match.group(1)
    raise RuntimeError("TikTokビジネスセンターのログイン済みタブが見つかりません")


async def goto_adv_page(page: Page, org_id: str) -> None:
    await page.bring_to_front()
    adv_url = f"https://business.tiktok.com/manage/accounts/adv?org_id={org_id}"
    if not ADV_URL_RE.match(page.url or ""):
        await page.goto(adv_url, wait_until="domcontentloaded", timeout=120000)
    await page.wait_for_timeout(4000)


async def current_page_number(page: Page) -> int:
    value = await page.evaluate(
        """
        () => {
          const active = document.querySelector('li.bc-okee-pager-item-checked');
          const text = (active?.innerText || '1').trim();
          return Number(text) || 1;
        }
        """
    )
    return int(value or 1)


async def page_numbers(page: Page) -> list[int]:
    values = await page.evaluate(
        """
        () => Array.from(document.querySelectorAll('li.bc-okee-pager-item'))
          .map(el => (el.innerText || '').trim())
          .filter(text => /^\\d+$/.test(text))
          .map(text => Number(text));
        """
    )
    return sorted(set(int(v) for v in values or []))


async def click_page(page: Page, target_page: int) -> bool:
    clicked = await page.evaluate(
        """
        (targetPage) => {
          const item = Array.from(document.querySelectorAll('li.bc-okee-pager-item'))
            .find(el => (el.innerText || '').trim() === String(targetPage));
          if (!item) return false;
          item.click();
          return true;
        }
        """,
        target_page,
    )
    if clicked:
        await page.wait_for_timeout(4000)
    return bool(clicked)


async def fetch_accounts() -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP_URL)
        page, org_id = await find_tiktok_page(browser)
        await goto_adv_page(page, org_id)

        collected: dict[str, dict[str, str]] = {}
        expected_total: int | None = None

        for target_page in [1, *[n for n in await page_numbers(page) if n > 1]]:
            if await current_page_number(page) != target_page:
                ok = await click_page(page, target_page)
                if not ok:
                    raise RuntimeError(f"ページ {target_page} へ遷移できません")

            body = await page.locator("body").inner_text(timeout=10000)
            expected_total = expected_total or parse_total_count(body)
            for account in parse_accounts(body):
                collected[account["advertiser_id"]] = account

        if expected_total is not None and len(collected) != expected_total:
            raise RuntimeError(
                f"TikTok広告アカウントの取得件数が一致しません: expected={expected_total}, actual={len(collected)}"
            )

        title = await page.locator("body").inner_text(timeout=10000)
        business_center_name = "アドネス株式会社"
        first_line = title.splitlines()[1:3]
        if first_line:
            for line in first_line:
                stripped = line.strip()
                if stripped and stripped != "ビジネスセンター":
                    business_center_name = stripped
                    break

        return {
            "business_center_id": org_id,
            "business_center_name": business_center_name,
            "ad_accounts": [collected[key] for key in sorted(collected.keys())],
        }


async def async_main(dry_run: bool) -> None:
    fetched = await fetch_accounts()
    print(json.dumps(fetched, ensure_ascii=False, indent=2))

    if dry_run:
        return

    config = load_config()
    config["business_center_id"] = fetched["business_center_id"]
    config["business_center_name"] = fetched["business_center_name"]
    config["ad_accounts"] = fetched["ad_accounts"]
    save_config(config)
    print(f"saved_to={CREDENTIAL_PATH}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
