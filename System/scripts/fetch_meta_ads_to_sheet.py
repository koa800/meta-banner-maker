#!/usr/bin/env python3
"""
Meta広告データを収集シートに書き込む。

方針:
- 月単位で取得。エラー時は週単位→日単位に分割して必ず取りきる
- 対象: スキルプラス関連28アカウント（VisionToDo・デザジュク除外）
- 取得項目: 確定済みの25列（Insights + メタデータ）
- 書き込み先: 【アドネス株式会社】広告データ（収集） / Meta
"""

import json
import sys
import os
import time
import requests
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sheets_manager import get_client
from gspread.exceptions import APIError

TOKEN_PATH = BASE_DIR / "credentials" / "meta_api_token.txt"
PROGRESS_PATH = BASE_DIR / "data" / "meta_ads_fetch_progress.json"
PROGRESS_PATH.parent.mkdir(parents=True, exist_ok=True)

API_VERSION = "v22.0"
BASE_URL = f"https://graph.facebook.com/{API_VERSION}"

SHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
TAB_NAME = "Meta"

# スキルプラス関連28アカウント（VisionToDo・デザジュク除外）
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
    "1183529603311248": "みかみオーガニック用",
    "9225401490867096": "アドプロ",
    "755776599362055": "ギブセル",
    "1182966010314095": "スキルプラス（サブスク導線）",
    "728822275839420": "スキルプラス（セミナー導線用）",
    "2036934017111151": "スキルプラス（無料体験会用）",
    "129782103426960": "スキルプラス（認知広告用）",
    "725165939124173": "ハイクラス",
    "2054495398217268": "直個別相談",
}

INSIGHTS_FIELDS = [
    "account_id",
    "campaign_id",
    "campaign_name",
    "adset_id",
    "adset_name",
    "ad_id",
    "ad_name",
    "impressions",
    "reach",
    "frequency",
    "clicks",
    "inline_link_clicks",
    "unique_inline_link_clicks",
    "outbound_clicks",
    "unique_outbound_clicks",
    "spend",
    "actions",
]

SHEET_HEADER = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告セットID",
    "広告セット名",
    "広告ID",
    "広告名",
    "インプレッション数",
    "リーチ",
    "フリークエンシー",
    "総クリック数",
    "リンククリック数",
    "リンククリック数（ユニーク）",
    "外部クリック数",
    "外部クリック数（ユニーク）",
    "消化金額",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "遷移先URL",
    "動画ID",
    "画像ハッシュ",
    "コンバージョン（JSON）",
]


# ============================================================
# API取得
# ============================================================


def load_token():
    token = TOKEN_PATH.read_text().strip()
    if not token:
        raise ValueError("Meta APIトークンが空です")
    return token


def api_get(url, params=None, max_retries=5):
    """レート制限・一時エラー対応付きGET"""
    for attempt in range(max_retries):
        try:
            resp = requests.get(url, params=params, timeout=120)
        except requests.exceptions.RequestException as e:
            if attempt == max_retries - 1:
                raise
            wait = 30 * (attempt + 1)
            print(f"      接続エラー。{wait}秒待機... ({e})")
            time.sleep(wait)
            continue

        if resp.status_code == 200:
            return resp

        error = {}
        try:
            error = resp.json().get("error", {})
        except Exception:
            pass

        code = error.get("code", 0)
        subcode = error.get("error_subcode", 0)

        # レート制限
        if resp.status_code in (429, 403) or code == 4 or subcode == 1504022:
            wait = min(60 * (attempt + 1), 300)
            print(f"      レート制限。{wait}秒待機... (試行 {attempt + 1}/{max_retries})")
            time.sleep(wait)
            continue

        # 一時障害（500系）
        if resp.status_code >= 500 or code in (1, 2) or subcode == 1504044:
            wait = min(30 * (attempt + 1), 180)
            print(f"      サーバーエラー (HTTP {resp.status_code})。{wait}秒待機...")
            time.sleep(wait)
            continue

        # 400系で回復不能
        if resp.status_code == 400:
            return resp

        # その他
        if attempt == max_retries - 1:
            return resp
        time.sleep(10)

    return resp


def fetch_insights_for_period(account_id, account_name, token, since, until):
    """指定期間のInsightsを全ページ取得"""
    url = f"{BASE_URL}/act_{account_id}/insights"
    params = {
        "access_token": token,
        "level": "ad",
        "fields": ",".join(INSIGHTS_FIELDS),
        "time_range": json.dumps({"since": since, "until": until}),
        "time_increment": 1,
        "limit": 500,
    }

    all_data = []
    page = 1

    while url:
        resp = api_get(url, params=params if page == 1 else None)

        if resp.status_code != 200:
            return None, resp  # エラーを呼び出し元に返す

        data = resp.json()
        rows = data.get("data", [])
        all_data.extend(rows)

        paging = data.get("paging", {})
        url = paging.get("next")
        params = None
        page += 1
        time.sleep(1)

    return all_data, None


def fetch_insights_with_subdivision(account_id, account_name, token, since, until, depth=0):
    """
    期間を取得。エラー時は半分に分割して再試行。
    月→2週間→1週間→日単位まで分割して必ず取りきる。
    """
    indent = "    " + "  " * depth
    rows, error_resp = fetch_insights_for_period(account_id, account_name, token, since, until)

    if rows is not None:
        return rows

    # エラー時: 期間を分割
    since_dt = datetime.strptime(since, "%Y-%m-%d").date()
    until_dt = datetime.strptime(until, "%Y-%m-%d").date()
    delta = (until_dt - since_dt).days

    if delta <= 0:
        # 1日でもダメなら空で返す（ログは出す）
        print(f"{indent}!! {since} は取得不可。スキップ。")
        return []

    if delta == 1:
        # 2日間を1日ずつ
        r1 = fetch_insights_with_subdivision(account_id, account_name, token, since, since, depth + 1)
        time.sleep(3)
        r2 = fetch_insights_with_subdivision(account_id, account_name, token, until, until, depth + 1)
        return r1 + r2

    # 半分に分割
    mid_dt = since_dt + timedelta(days=delta // 2)
    mid_str = mid_dt.strftime("%Y-%m-%d")
    prev_day = (mid_dt - timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"{indent}分割: {since}~{prev_day} / {mid_str}~{until}")
    time.sleep(5)

    r1 = fetch_insights_with_subdivision(account_id, account_name, token, since, prev_day, depth + 1)
    time.sleep(3)
    r2 = fetch_insights_with_subdivision(account_id, account_name, token, mid_str, until, depth + 1)
    return r1 + r2


def fetch_ad_metadata(account_id, account_name, token):
    """広告メタデータを全件取得"""
    url = f"{BASE_URL}/act_{account_id}/ads"
    params = {
        "access_token": token,
        "fields": "id,created_time,updated_time,effective_status,creative{id,object_story_spec,video_id,image_hash}",
        "limit": 500,
    }

    ad_meta = {}
    page = 1

    while url:
        resp = api_get(url, params=params if page == 1 else None)
        if resp.status_code != 200:
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
                    "effective_status": ad.get("effective_status", ""),
                    "created_time": ad.get("created_time", ""),
                    "updated_time": ad.get("updated_time", ""),
                    "creative_id": creative.get("id", ""),
                    "creative_url": link_url,
                    "video_id": creative.get("video_id", ""),
                    "image_hash": creative.get("image_hash", ""),
                }

        paging = data.get("paging", {})
        url = paging.get("next")
        params = None
        page += 1
        time.sleep(1)

    return ad_meta


# ============================================================
# データ変換
# ============================================================


def extract_list_value(field_value):
    """outbound_clicks等のリスト形式から値を取り出す"""
    if isinstance(field_value, list):
        for item in field_value:
            if isinstance(item, dict):
                return item.get("value", "")
    return field_value if field_value is not None else ""


def row_to_sheet_row(row, account_name, ad_meta):
    """APIレスポンスの1行をシートの1行に変換"""
    ad_id = row.get("ad_id", "")
    meta = ad_meta.get(ad_id, {})

    return [
        row.get("date_start", ""),
        account_name,
        row.get("account_id", ""),
        row.get("campaign_id", ""),
        row.get("campaign_name", ""),
        row.get("adset_id", ""),
        row.get("adset_name", ""),
        ad_id,
        row.get("ad_name", ""),
        row.get("impressions", ""),
        row.get("reach", ""),
        row.get("frequency", ""),
        row.get("clicks", ""),
        row.get("inline_link_clicks", ""),
        extract_list_value(row.get("unique_inline_link_clicks")),
        extract_list_value(row.get("outbound_clicks")),
        extract_list_value(row.get("unique_outbound_clicks")),
        row.get("spend", ""),
        meta.get("effective_status", ""),
        meta.get("created_time", ""),
        meta.get("updated_time", ""),
        meta.get("creative_id", ""),
        meta.get("creative_url", ""),
        meta.get("video_id", ""),
        meta.get("image_hash", ""),
        json.dumps(row.get("actions", []), ensure_ascii=False) if row.get("actions") else "",
    ]


# ============================================================
# 月リスト生成
# ============================================================


def generate_months(since_str, until_date):
    """月単位の期間リストを生成"""
    cursor = datetime.strptime(since_str, "%Y-%m-%d").date()
    months = []
    while cursor <= until_date:
        month_end = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        if month_end > until_date:
            month_end = until_date
        months.append((cursor.strftime("%Y-%m-%d"), month_end.strftime("%Y-%m-%d")))
        cursor = month_end + timedelta(days=1)
    return months


# ============================================================
# 進捗管理
# ============================================================


def load_progress():
    if PROGRESS_PATH.exists():
        try:
            return json.loads(PROGRESS_PATH.read_text())
        except Exception:
            pass
    return {"completed_accounts": {}, "total_rows_written": 0}


def save_progress(progress):
    PROGRESS_PATH.write_text(json.dumps(progress, ensure_ascii=False, indent=2))


# ============================================================
# シート書き込み
# ============================================================


def append_rows_to_sheet(ws, rows, max_chunk=5000):
    """シートの末尾に行を追加（チャンク分割）"""
    for i in range(0, len(rows), max_chunk):
        chunk = rows[i:i + max_chunk]
        for attempt in range(5):
            try:
                ws.append_rows(chunk, value_input_option="USER_ENTERED")
                break
            except APIError as e:
                if "429" in str(e) or "Quota" in str(e):
                    wait = 60 * (attempt + 1)
                    print(f"    シート書き込み制限。{wait}秒待機...")
                    time.sleep(wait)
                else:
                    raise
        time.sleep(2)


# ============================================================
# メイン
# ============================================================


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", help="特定アカウントIDだけ実行")
    parser.add_argument("--reset", action="store_true", help="進捗をリセットして最初から")
    args = parser.parse_args()

    token = load_token()
    gc = get_client("kohara")
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB_NAME)

    progress = load_progress()
    if args.reset:
        progress = {"completed_accounts": {}, "total_rows_written": 0}
        save_progress(progress)
        # シートもヘッダーだけに戻す
        ws.clear()
        ws.update("A1", [SHEET_HEADER], value_input_option="USER_ENTERED")
        print("進捗リセット完了")

    completed = progress.get("completed_accounts", {})

    today = datetime.now().date()
    since_date = "2023-03-01"
    months = generate_months(since_date, today)

    # 対象アカウント決定
    if args.account:
        if args.account not in ACCOUNTS:
            print(f"アカウント {args.account} は対象外です")
            return
        target_accounts = {args.account: ACCOUNTS[args.account]}
    else:
        target_accounts = ACCOUNTS

    remaining = {k: v for k, v in target_accounts.items() if k not in completed}
    print(f"対象: {len(target_accounts)}アカウント（残り: {len(remaining)}）")
    print(f"期間: {since_date} ~ {today} ({len(months)}ヶ月)")
    print(f"書き込み先: {TAB_NAME}")
    print("=" * 60)

    for account_id, account_name in target_accounts.items():
        if account_id in completed:
            print(f"\n[{account_name}] スキップ（完了済み: {completed[account_id]}行）")
            continue

        print(f"\n[{account_name}] (act_{account_id}) 取得開始...")

        # メタデータ取得
        print("  メタデータ取得中...")
        ad_meta = fetch_ad_metadata(account_id, account_name, token)
        print(f"  メタデータ: {len(ad_meta)}件")

        # Insights取得（月単位、エラー時は分割）
        account_rows = []
        for i, (since, until) in enumerate(months):
            print(f"  [{i + 1}/{len(months)}] {since[:7]}...", end=" ", flush=True)
            rows = fetch_insights_with_subdivision(account_id, account_name, token, since, until)
            month_spend = sum(float(r.get("spend", 0)) for r in rows)
            print(f"{len(rows)}行 ¥{month_spend:,.0f}")
            account_rows.extend(rows)
            time.sleep(2)

        # シートの行に変換
        sheet_rows = [row_to_sheet_row(r, account_name, ad_meta) for r in account_rows]

        # 書き込み
        if sheet_rows:
            print(f"  シート書き込み中... ({len(sheet_rows)}行)")
            append_rows_to_sheet(ws, sheet_rows)

        total_spend = sum(float(r.get("spend", 0)) for r in account_rows)
        print(f"  完了: {len(sheet_rows)}行, ¥{total_spend:,.0f}")

        # 進捗保存
        completed[account_id] = len(sheet_rows)
        progress["completed_accounts"] = completed
        progress["total_rows_written"] = sum(completed.values())
        save_progress(progress)

        time.sleep(5)

    print("\n" + "=" * 60)
    total = sum(completed.values())
    print(f"全アカウント完了: {total:,}行")


if __name__ == "__main__":
    main()
