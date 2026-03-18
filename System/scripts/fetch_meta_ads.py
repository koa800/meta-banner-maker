#!/usr/bin/env python3
"""
Meta広告データ一括取得スクリプト
アドネス株式会社の全広告アカウント（33件）から
日別 × 広告ID単位のデータをCSV出力する

取得期間: 2023-03-01 〜 2026-03-17（API上限37ヶ月）
"""

import csv
import json
import time
import requests
from pathlib import Path
from datetime import datetime

BASE_DIR = Path(__file__).resolve().parent.parent
TOKEN_PATH = BASE_DIR / "credentials" / "meta_api_token.txt"
OUTPUT_DIR = BASE_DIR / "data" / "meta_ads_export"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

# アドネス株式会社の広告アカウント（33件）
ACCOUNTS = {
    "1415237883429381": "スキルプラス（セミナー導線_林さん用）",
    "1367440930779480": "AI1",
    "121022750983030": "AI2（主婦層用）",
    "2691450184355750": "AI3",
    "409840901478412": "AI4（男性演者用）",
    "1162358904830949": "AI5",
    "998675178674271": "AI6（男性演者用）",
    "1371197794118685": "AI7（女性演者用）",
    "9862510673800674": "AI8（林さん用）",
    "1426593128864558": "AI9（ヒカルさん用）",
    "876451738045366": "AIエージェント",
    "6187601884607545": "SNS1",
    "1427431624693156": "SNS2",
    "569699451715260": "SNS3",
    "375117041579519": "SNS4",
    "1262316288100570": "SNS5（箕輪さん用）",
    "1768138330551086": "SNS6",
    "1434658414786552": "SNS7（林さん用）",
    "321557094103117": "VisionToDo",
    "1183529603311248": "みかみオーガニック用",
    "9225401490867096": "アドプロ",
    "755776599362055": "ギブセル",
    "1182966010314095": "スキルプラス（サブスク導線）",
    "728822275839420": "スキルプラス（セミナー導線用）",
    "2036934017111151": "スキルプラス（無料体験会用）",
    "129782103426960": "スキルプラス（認知広告用）",
    "758925672341302": "デザジュク1",
    "1711463439686617": "デザジュク2",
    "9278356638866612": "デザジュク3",
    "1036900424932610": "デザジュク4",
    "2252839445229899": "デザジュク5",
    "725165939124173": "ハイクラス",
    "2054495398217268": "直個別相談",
}

# Insights取得フィールド
INSIGHTS_FIELDS = [
    # 識別情報
    "account_id",
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "ad_id",
    "ad_name",
    # 配信
    "impressions",
    "reach",
    "frequency",
    # クリック（リンククリックのみ）
    "inline_link_clicks",
    "unique_inline_link_clicks",
    # コスト
    "spend",
    "cost_per_inline_link_click",
    "cpm",
    # 率
    "inline_link_click_ctr",
    # コンバージョン
    "actions",
    "cost_per_action_type",
]

# 進捗保存用（中断時に再開できるように）
PROGRESS_PATH = OUTPUT_DIR / "progress.json"


def load_token():
    token = TOKEN_PATH.read_text().strip()
    if not token:
        raise ValueError("トークンが空です")
    return token


def load_progress():
    if PROGRESS_PATH.exists():
        return json.loads(PROGRESS_PATH.read_text())
    return {"completed_accounts": [], "rows_so_far": 0}


def save_progress(progress):
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2))


def fetch_with_retry(url, params=None, max_retries=3):
    """レート制限対応付きリクエスト"""
    for attempt in range(max_retries):
        resp = requests.get(url, params=params)

        if resp.status_code == 200:
            return resp

        if resp.status_code in (429, 403):
            error = resp.json().get("error", {})
            if error.get("code") == 4 or error.get("error_subcode") == 1504022:
                wait = min(60 * (attempt + 1), 300)
                print(f"    レート制限。{wait}秒待機... (試行 {attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

        if resp.status_code == 400:
            return resp

        print(f"    HTTP {resp.status_code}: {resp.text[:200]}")
        time.sleep(10)

    return resp


def fetch_ad_insights_daily(account_id, account_name, token):
    """アカウントの全広告のインサイトを日別で取得"""
    url = f"{BASE_URL}/act_{account_id}/insights"
    params = {
        "access_token": token,
        "level": "ad",
        "fields": ",".join(INSIGHTS_FIELDS),
        "time_range": json.dumps({"since": "2023-03-01", "until": "2026-03-17"}),
        "time_increment": 1,  # 日別
        "limit": 500,
    }

    all_data = []
    page = 1

    while url:
        print(f"  [{account_name}] ページ {page} 取得中... ({len(all_data)}件)")
        resp = fetch_with_retry(url, params=params if page == 1 else None)

        if resp.status_code == 400:
            error = resp.json().get("error", {})
            print(f"  [{account_name}] エラー: {error.get('message', '不明')}")
            break
        elif resp.status_code != 200:
            print(f"  [{account_name}] 取得失敗 HTTP {resp.status_code}")
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


def fetch_ad_metadata(account_id, account_name, token):
    """アカウントの全広告のメタデータを取得（クリエイティブURL・動画ID・作成日・停止日相当）"""
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
            break

        data = resp.json()
        for ad in data.get("data", []):
            ad_id = ad.get("id")
            creative = ad.get("creative", {})
            story_spec = creative.get("object_story_spec", {})

            # URLを探す（link_data > video_data > photo_data の順）
            link_url = ""
            link_data = story_spec.get("link_data", {})
            if link_data:
                link_url = link_data.get("link", "")
            if not link_url:
                video_data = story_spec.get("video_data", {})
                if video_data:
                    call_to_action = video_data.get("call_to_action", {})
                    link_url = call_to_action.get("value", {}).get("link", "")
            if not link_url:
                photo_data = story_spec.get("photo_data", {})
                if photo_data:
                    link_url = photo_data.get("link", "")

            # 動画ID・クリエイティブID・画像ID
            video_id = creative.get("video_id", "")
            creative_id = creative.get("id", "")
            image_hash = creative.get("image_hash", "")

            if ad_id:
                ad_meta[ad_id] = {
                    "creative_url": link_url,
                    "video_id": video_id,
                    "creative_id": creative_id,
                    "image_hash": image_hash,
                    "ad_created_time": ad.get("created_time", ""),
                    "ad_updated_time": ad.get("updated_time", ""),
                    "effective_status": ad.get("effective_status", ""),
                }

        paging = data.get("paging", {})
        url = paging.get("next")
        params = None
        page += 1

        time.sleep(1)

    print(f"  [{account_name}] 広告メタデータ: {len(ad_meta)}件")
    return ad_meta


def flatten_row(row):
    """actions / outbound_clicks / cost_per_action_type を展開"""
    flat = {}
    for key, val in row.items():
        if key == "actions" and isinstance(val, list):
            for action in val:
                atype = action.get("action_type", "unknown")
                flat[f"action_{atype}"] = action.get("value", "")
        elif key == "cost_per_action_type" and isinstance(val, list):
            for action in val:
                atype = action.get("action_type", "unknown")
                flat[f"cost_per_action_{atype}"] = action.get("value", "")
        elif key == "outbound_clicks" and isinstance(val, list):
            for click in val:
                flat["outbound_clicks"] = click.get("value", "")
        elif key == "unique_inline_link_clicks" and isinstance(val, list):
            # リスト形式の場合
            for item in val:
                flat["unique_inline_link_clicks"] = item.get("value", "")
        else:
            flat[key] = val
    return flat


def main():
    token = load_token()
    progress = load_progress()
    completed = set(progress.get("completed_accounts", []))

    print(f"トークン読み込み完了")
    print(f"対象アカウント: {len(ACCOUNTS)}件（完了済み: {len(completed)}件）")
    print(f"出力先: {OUTPUT_DIR}")
    print("=" * 60)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"meta_ads_daily_{timestamp}.csv"

    all_rows = []
    account_summary = []
    all_ad_urls = {}

    for account_id, account_name in ACCOUNTS.items():
        if account_id in completed:
            print(f"\n[{account_name}] スキップ（完了済み）")
            continue

        print(f"\n[{account_name}] (act_{account_id}) 取得開始...")

        # インサイト取得（日別）
        rows = fetch_ad_insights_daily(account_id, account_name, token)

        # 広告メタデータ取得（クリエイティブURL・動画ID・作成日等）
        if rows:
            ad_meta = fetch_ad_metadata(account_id, account_name, token)
            all_ad_urls.update(ad_meta)

        # アカウント名を追加
        for row in rows:
            row["account_name"] = account_name

        count = len(rows)
        all_rows.extend(rows)
        account_summary.append({"name": account_name, "id": account_id, "rows": count})
        print(f"  [{account_name}] → {count}行（日別×広告ID）")

        # 進捗保存
        completed.add(account_id)
        save_progress({
            "completed_accounts": list(completed),
            "rows_so_far": len(all_rows),
        })

        time.sleep(3)

    print("\n" + "=" * 60)
    print(f"合計: {len(all_rows)}行")

    if not all_rows:
        print("データがありませんでした")
        return

    # フラット化 + メタデータ付与
    flat_rows = []
    for row in all_rows:
        flat = flatten_row(row)
        ad_id = flat.get("ad_id", "")
        meta = all_ad_urls.get(ad_id, {})
        if isinstance(meta, dict):
            flat["creative_url"] = meta.get("creative_url", "")
            flat["creative_id"] = meta.get("creative_id", "")
            flat["video_id"] = meta.get("video_id", "")
            flat["image_hash"] = meta.get("image_hash", "")
            flat["ad_created_time"] = meta.get("ad_created_time", "")
            flat["ad_updated_time"] = meta.get("ad_updated_time", "")
            flat["effective_status"] = meta.get("effective_status", "")
        flat_rows.append(flat)

    # 全カラム収集
    all_columns = set()
    for row in flat_rows:
        all_columns.update(row.keys())

    # カラム順序
    base_cols = [
        "date_start", "date_stop",
        "account_name", "account_id",
        "campaign_id", "campaign_name",
        "adset_id", "adset_name",
        "ad_id", "ad_name",
        "effective_status",
        "ad_created_time", "ad_updated_time",
        "creative_id", "creative_url", "video_id", "image_hash",
        "impressions", "reach", "frequency",
        "inline_link_clicks", "unique_inline_link_clicks",
        "spend", "cost_per_inline_link_click", "cpm",
        "inline_link_click_ctr",
    ]
    action_cols = sorted([c for c in all_columns if c.startswith(("action_", "cost_per_action_"))])
    other_cols = sorted([c for c in all_columns if c not in base_cols and c not in action_cols])
    columns = [c for c in base_cols if c in all_columns] + other_cols + action_cols

    # CSV出力
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(flat_rows)

    print(f"\nCSV出力完了: {csv_path}")
    print(f"行数: {len(flat_rows)}, カラム数: {len(columns)}")

    # サマリー出力
    summary_path = OUTPUT_DIR / f"account_summary_{timestamp}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "id", "rows"])
        writer.writeheader()
        writer.writerows(account_summary)

    print(f"サマリー出力: {summary_path}")

    # アカウント別の件数表示
    print("\n--- アカウント別件数 ---")
    for s in sorted(account_summary, key=lambda x: x["rows"], reverse=True):
        if s["rows"] > 0:
            print(f"  {s['name']}: {s['rows']}行")
    zero_count = sum(1 for s in account_summary if s["rows"] == 0)
    if zero_count:
        print(f"  （データなし: {zero_count}アカウント）")

    # 進捗ファイル削除
    if PROGRESS_PATH.exists():
        PROGRESS_PATH.unlink()
        print("\n進捗ファイルを削除しました（完了）")


if __name__ == "__main__":
    main()
