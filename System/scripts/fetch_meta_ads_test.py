#!/usr/bin/env python3
"""
Meta広告データ取得 — 1アカウントテスト版
確定した取得項目で1アカウントだけ取得し、中身と件数を確認する。
"""

import json
import time
import requests
from pathlib import Path
from datetime import datetime, timedelta

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_PATH = BASE_DIR / "credentials" / "meta_api_token.txt"
OUTPUT_DIR = BASE_DIR / "data" / "meta_ads_export"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# テスト用: 1アカウントだけ
TEST_ACCOUNT_ID = "728822275839420"
TEST_ACCOUNT_NAME = "スキルプラス（セミナー導線用）"

# API上限: 約37ヶ月前
today = datetime.now().date()
since_date = (today - timedelta(days=37 * 30)).strftime("%Y-%m-%d")
until_date = today.strftime("%Y-%m-%d")

# 確定した取得フィールド（配信実績）
INSIGHTS_FIELDS = [
    # 識別情報
    "account_id",
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "ad_id",
    "ad_name",
    # 配信（総数 + ユニーク）
    "impressions",
    "reach",
    "frequency",
    # クリック（総数 + ユニーク）
    "clicks",
    "inline_link_clicks",
    "unique_inline_link_clicks",
    "outbound_clicks",
    "unique_outbound_clicks",
    # コスト
    "spend",
    # コンバージョン
    "actions",
    "cost_per_action_type",
]


def load_token():
    token = TOKEN_PATH.read_text().strip()
    if not token:
        raise ValueError("トークンが空です")
    return token


def fetch_with_retry(url, params=None, max_retries=3):
    for attempt in range(max_retries):
        resp = requests.get(url, params=params)

        if resp.status_code == 200:
            return resp

        if resp.status_code in (429, 403):
            error = resp.json().get("error", {})
            if error.get("code") == 4 or error.get("error_subcode") == 1504022:
                wait = min(60 * (attempt + 1), 300)
                print(f"  レート制限。{wait}秒待機... (試行 {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

        if resp.status_code == 400:
            return resp

        print(f"  HTTP {resp.status_code}: {resp.text[:300]}")
        time.sleep(10)

    return resp


def fetch_insights(account_id, account_name, token):
    url = f"{BASE_URL}/act_{account_id}/insights"
    params = {
        "access_token": token,
        "level": "ad",
        "fields": ",".join(INSIGHTS_FIELDS),
        "time_range": json.dumps({"since": since_date, "until": until_date}),
        "time_increment": 1,
        "limit": 500,
    }

    all_data = []
    page = 1

    while url:
        print(f"  [{account_name}] ページ {page} 取得中... ({len(all_data)}件)")
        resp = fetch_with_retry(url, params=params if page == 1 else None)

        if resp.status_code == 400:
            error = resp.json().get("error", {})
            print(f"  エラー: {error.get('message', '不明')}")
            print(f"  エラー詳細: {json.dumps(error, indent=2)[:500]}")
            break
        elif resp.status_code != 200:
            print(f"  取得失敗 HTTP {resp.status_code}")
            break

        data = resp.json()
        rows = data.get("data", [])
        all_data.extend(rows)

        paging = data.get("paging", {})
        url = paging.get("next")
        params = None
        page += 1

        time.sleep(2)

    return all_data


def fetch_metadata(account_id, account_name, token):
    url = f"{BASE_URL}/act_{account_id}/ads"
    params = {
        "access_token": token,
        "fields": "id,created_time,updated_time,effective_status,creative{id,object_story_spec,video_id,image_hash,image_url}",
        "limit": 500,
    }

    ad_meta = {}
    page = 1

    while url:
        resp = fetch_with_retry(url, params=params if page == 1 else None)
        if resp.status_code != 200:
            print(f"  メタデータ取得失敗 HTTP {resp.status_code}")
            break

        data = resp.json()
        for ad in data.get("data", []):
            ad_id = ad.get("id")
            creative = ad.get("creative", {})
            story_spec = creative.get("object_story_spec", {})

            link_url = ""
            for source_key in ("link_data", "video_data", "photo_data"):
                source = story_spec.get(source_key, {})
                if source_key == "link_data":
                    link_url = source.get("link", "")
                elif source_key == "video_data":
                    cta = source.get("call_to_action", {})
                    link_url = cta.get("value", {}).get("link", "")
                elif source_key == "photo_data":
                    link_url = source.get("link", "")
                if link_url:
                    break

            if ad_id:
                ad_meta[ad_id] = {
                    "creative_url": link_url,
                    "video_id": creative.get("video_id", ""),
                    "creative_id": creative.get("id", ""),
                    "image_hash": creative.get("image_hash", ""),
                    "ad_created_time": ad.get("created_time", ""),
                    "ad_updated_time": ad.get("updated_time", ""),
                    "effective_status": ad.get("effective_status", ""),
                }

        paging = data.get("paging", {})
        url = paging.get("next")
        params = None
        page += 1
        time.sleep(1)

    return ad_meta


def main():
    token = load_token()
    print(f"テスト対象: {TEST_ACCOUNT_NAME} (act_{TEST_ACCOUNT_ID})")
    print(f"取得期間: {since_date} ~ {until_date}")
    print(f"取得フィールド: {len(INSIGHTS_FIELDS)}項目")
    print("=" * 60)

    # 1. Insights取得
    print("\n--- Insights取得 ---")
    rows = fetch_insights(TEST_ACCOUNT_ID, TEST_ACCOUNT_NAME, token)
    print(f"\n取得行数: {len(rows)}")

    if not rows:
        print("データがありませんでした。トークンの有効期限を確認してください。")
        return

    # 2. メタデータ取得
    print("\n--- メタデータ取得 ---")
    ad_meta = fetch_metadata(TEST_ACCOUNT_ID, TEST_ACCOUNT_NAME, token)
    print(f"メタデータ件数: {len(ad_meta)}")

    # 3. サンプルデータ表示
    print("\n--- サンプル（1行目） ---")
    sample = rows[0]
    for key, val in sample.items():
        if isinstance(val, list):
            print(f"  {key}: [{len(val)}件] {json.dumps(val[:2], ensure_ascii=False)[:200]}")
        else:
            print(f"  {key}: {val}")

    # 4. 取得できたフィールド確認
    all_keys = set()
    for row in rows:
        all_keys.update(row.keys())
    print(f"\n--- 取得できたフィールド ({len(all_keys)}種類) ---")
    for key in sorted(all_keys):
        print(f"  {key}")

    # 5. 日付範囲
    dates = sorted(set(row.get("date_start", "") for row in rows))
    print(f"\n--- 日付範囲 ---")
    print(f"  最古: {dates[0] if dates else 'なし'}")
    print(f"  最新: {dates[-1] if dates else 'なし'}")
    print(f"  日数: {len(dates)}")

    # 6. 広告ID数
    ad_ids = set(row.get("ad_id", "") for row in rows)
    print(f"\n--- 広告数 ---")
    print(f"  ユニーク広告ID: {len(ad_ids)}")

    # 7. 消化金額サマリー
    total_spend = sum(float(row.get("spend", 0)) for row in rows)
    print(f"\n--- 消化金額 ---")
    print(f"  合計: ¥{total_spend:,.0f}")

    # 8. outbound_clicks の形式確認
    print("\n--- outbound_clicks の形式確認 ---")
    for row in rows[:5]:
        ob = row.get("outbound_clicks")
        uob = row.get("unique_outbound_clicks")
        if ob or uob:
            print(f"  outbound_clicks: {ob}")
            print(f"  unique_outbound_clicks: {uob}")
            break
    else:
        print("  outbound_clicks を持つ行が見つかりませんでした（最初の5行で）")

    # 9. メタデータのサンプル
    if ad_meta:
        sample_ad_id = next(iter(ad_meta))
        print(f"\n--- メタデータサンプル (ad_id: {sample_ad_id}) ---")
        for key, val in ad_meta[sample_ad_id].items():
            print(f"  {key}: {val}")

    print("\n完了")


if __name__ == "__main__":
    main()
