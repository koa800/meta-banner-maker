#!/usr/bin/env python3
"""
Meta広告データを収集シートに書き込む。

方針:
- 月単位で取得。エラー時は週単位→日単位に分割して必ず取りきる
- 対象: マスタデータの広告アカウントタブにある Meta広告アカウント
- 取得項目: 確定済みの25列（Insights + メタデータ）
- 書き込み先: 【アドネス株式会社】広告データ（収集） / Meta
"""

import json
import math
import sys
import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
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
STATUS_TAB_NAME = "Meta収集状況"
MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_TAB_NAME = "広告アカウント"
TARGET_BUSINESS_NAMES = {"スキルプラス"}
PAUSED_LIKE_STATUSES = {"PAUSED", "CAMPAIGN_PAUSED", "ADSET_PAUSED", "ARCHIVED", "DELETED"}
ACTIVE_LIKE_STATUSES = {"ACTIVE"}

# 旧定義。マスタ読込に失敗したときだけフォールバックで使う。
LEGACY_ACCOUNTS = {
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

STATUS_HEADER = [
    "集客媒体",
    "事業名",
    "広告アカウントID",
    "広告アカウント名",
    "アカウント状態コード",
    "停止理由コード",
    "active_campaign数",
    "active_adset数",
    "active_ad数",
    "取得状態",
    "鮮度状態",
    "最終日配信ステータス",
    "progress記録行数",
    "raw行数",
    "初回取得日",
    "最終取得日",
    "最終日経過日数",
    "必須メタ欠損行数",
    "遷移先URL未入力行数",
    "動画ID未入力行数",
    "画像ハッシュ未入力行数",
    "更新日時",
]


# ============================================================
# API取得
# ============================================================


def load_token():
    token = TOKEN_PATH.read_text().strip()
    if not token:
        raise ValueError("Meta APIトークンが空です")
    return token


def clean_cell(value):
    return str(value).strip() if value is not None else ""


def as_sheet_text(value):
    text = clean_cell(value)
    return f"'{text}" if text else ""


def normalize_sheet_id_value(value):
    if value is None or value == "":
        return ""
    if isinstance(value, float):
        if math.isnan(value):
            return ""
        if value.is_integer():
            return str(int(value))
        return format(value, ".15g")
    if isinstance(value, int):
        return str(value)
    return clean_cell(value)


def normalize_lookup_id(value):
    text = clean_cell(value)
    return text[1:] if text.startswith("'") else text


def load_target_accounts_from_master(gc):
    """マスタデータの広告アカウントタブから Meta 対象を読む。"""
    spreadsheet = gc.open_by_key(MASTER_SHEET_ID)
    worksheet = spreadsheet.worksheet(MASTER_TAB_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        raise RuntimeError("マスタデータの広告アカウントタブが空です")

    header = rows[0]
    header_index = {name: idx for idx, name in enumerate(header)}
    required_headers = ["集客媒体", "広告アカウントID", "広告アカウント名", "事業名"]
    missing_headers = [name for name in required_headers if name not in header_index]
    if missing_headers:
        raise RuntimeError(
            f"広告アカウントタブの列が不足しています: {', '.join(missing_headers)}"
        )

    accounts = {}
    for row in rows[1:]:
        media = clean_cell(row[header_index["集客媒体"]]) if len(row) > header_index["集客媒体"] else ""
        if media != "Meta広告":
            continue

        business_name = clean_cell(row[header_index["事業名"]]) if len(row) > header_index["事業名"] else ""
        if business_name not in TARGET_BUSINESS_NAMES:
            continue

        account_id = clean_cell(row[header_index["広告アカウントID"]]) if len(row) > header_index["広告アカウントID"] else ""
        account_name = clean_cell(row[header_index["広告アカウント名"]]) if len(row) > header_index["広告アカウント名"] else ""
        if not account_id or not account_name:
            continue
        accounts[account_id] = account_name

    if not accounts:
        raise RuntimeError("マスタデータから Meta広告アカウントを読み込めませんでした")
    return accounts


def load_meta_account_notes_from_master(gc):
    """マスタデータの広告アカウントタブから Meta アカウントの備考を読む。"""
    spreadsheet = gc.open_by_key(MASTER_SHEET_ID)
    worksheet = spreadsheet.worksheet(MASTER_TAB_NAME)
    rows = worksheet.get_all_values()
    if not rows:
        return {}

    header = rows[0]
    header_index = {name: idx for idx, name in enumerate(header)}
    required_headers = ["集客媒体", "広告アカウントID"]
    missing_headers = [name for name in required_headers if name not in header_index]
    if missing_headers:
        return {}

    note_idx = header_index.get("備考")
    notes = {}
    for row in rows[1:]:
        media = clean_cell(row[header_index["集客媒体"]]) if len(row) > header_index["集客媒体"] else ""
        if media != "Meta広告":
            continue
        account_id = clean_cell(row[header_index["広告アカウントID"]]) if len(row) > header_index["広告アカウントID"] else ""
        if not account_id:
            continue
        note = clean_cell(row[note_idx]) if note_idx is not None and len(row) > note_idx else ""
        notes[account_id] = note
    return notes


def resolve_target_accounts(gc):
    """通常はマスタを使い、失敗時だけ旧定義へフォールバックする。"""
    try:
        accounts = load_target_accounts_from_master(gc)
        print(f"対象アカウントをマスタから読込: {len(accounts)}件")
        return accounts
    except Exception as exc:
        print(f"マスタ読込に失敗したため旧定義を使用: {exc}")
        return LEGACY_ACCOUNTS.copy()


def ensure_text_columns(spreadsheet, worksheet):
    """長いIDが指数表記にならないよう、ID系列を TEXT 扱いにする。"""
    text_column_indexes = [2, 3, 5, 7, 21, 23, 24]
    requests = []
    for idx in text_column_indexes:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": worksheet.id,
                        "startRowIndex": 1,
                        "startColumnIndex": idx,
                        "endColumnIndex": idx + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {"type": "TEXT"}
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat",
                }
            }
        )
    spreadsheet.batch_update({"requests": requests})


def repair_existing_id_columns(worksheet, chunk_size=5000):
    """既存シート上で指数表記になっているID列を文字列へ書き直す。"""
    target_columns = {
        "C": "広告アカウントID",
        "V": "クリエイティブID",
        "X": "動画ID",
    }

    used_rows = len(worksheet.get_all_values())
    if used_rows <= 1:
        return {}

    repaired_counts = {}
    for column_letter, label in target_columns.items():
        values = worksheet.get(
            f"{column_letter}2:{column_letter}{used_rows}",
            value_render_option="UNFORMATTED_VALUE",
        )
        normalized_rows = [[normalize_sheet_id_value(row[0] if row else "")] for row in values]
        update_requests = []
        for start in range(0, len(normalized_rows), chunk_size):
            end = min(start + chunk_size, len(normalized_rows))
            update_requests.append(
                {
                    "range": f"{column_letter}{start + 2}:{column_letter}{end + 1}",
                    "values": normalized_rows[start:end],
                }
            )
        for start in range(0, len(update_requests), 50):
            worksheet.batch_update(update_requests[start:start + 50], value_input_option="RAW")
            time.sleep(1)
        repaired_counts[label] = sum(1 for row in normalized_rows if row[0] != "")

    return repaired_counts


def build_metadata_cells(meta, existing_row=None):
    existing_row = existing_row or [""] * 7
    return [
        meta.get("effective_status", existing_row[0]),
        meta.get("created_time", existing_row[1]),
        meta.get("updated_time", existing_row[2]),
        as_sheet_text(meta.get("creative_id", "")) if meta.get("creative_id", "") else existing_row[3],
        meta.get("creative_url", existing_row[4]),
        as_sheet_text(meta.get("video_id", "")) if meta.get("video_id", "") else existing_row[5],
        as_sheet_text(meta.get("image_hash", "")) if meta.get("image_hash", "") else existing_row[6],
    ]


def extract_meta_from_ad_object(ad):
    creative = ad.get("creative", {}) if isinstance(ad, dict) else {}
    story_spec = creative.get("object_story_spec", {}) if isinstance(creative, dict) else {}

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

    return {
        "effective_status": ad.get("effective_status", ""),
        "created_time": ad.get("created_time", ""),
        "updated_time": ad.get("updated_time", ""),
        "creative_id": creative.get("id", "") if isinstance(creative, dict) else "",
        "creative_url": link_url,
        "video_id": creative.get("video_id", "") if isinstance(creative, dict) else "",
        "image_hash": creative.get("image_hash", "") if isinstance(creative, dict) else "",
    }


def fetch_ad_metadata_by_ids(ad_ids, token, depth=0):
    if not ad_ids:
        return {}

    url = f"{BASE_URL}/"
    params = {
        "access_token": token,
        "ids": ",".join(ad_ids),
        "fields": "created_time,updated_time,effective_status,creative{id,object_story_spec,video_id,image_hash}",
    }
    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.exceptions.RequestException:
        resp = None

    if resp is not None and resp.status_code == 200:
        payload = resp.json()
        return {
            ad_id: extract_meta_from_ad_object(payload.get(ad_id, {}))
            for ad_id in ad_ids
            if payload.get(ad_id)
        }

    if len(ad_ids) == 1:
        status = resp.status_code if resp is not None else "request_error"
        print(f"    広告メタ情報取得失敗: ad_id={ad_ids[0]} status={status}")
        return {}

    mid = len(ad_ids) // 2
    left = fetch_ad_metadata_by_ids(ad_ids[:mid], token, depth + 1)
    time.sleep(0.1)
    right = fetch_ad_metadata_by_ids(ad_ids[mid:], token, depth + 1)
    merged = {}
    merged.update(left)
    merged.update(right)
    return merged


def backfill_existing_ad_metadata(worksheet, token, chunk_size=5000, target_account_id=None):
    rows = worksheet.get_all_values()
    if not rows:
        return {"updated_rows": 0, "target_accounts": 0, "fetched_metadata": 0}

    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    required_headers = [
        "広告アカウントID",
        "広告アカウント名",
        "広告ID",
        "配信ステータス",
        "広告作成日",
        "最終更新日",
        "クリエイティブID",
        "遷移先URL",
        "動画ID",
        "画像ハッシュ",
    ]
    missing_headers = [name for name in required_headers if name not in idx]
    if missing_headers:
        raise RuntimeError(f"Metaシートの列が不足しています: {', '.join(missing_headers)}")

    target_accounts = {}
    target_ad_ids = set()
    update_needed_rows = 0
    metadata_columns = [
        "配信ステータス",
        "広告作成日",
        "最終更新日",
        "クリエイティブID",
        "遷移先URL",
        "動画ID",
        "画像ハッシュ",
    ]

    for row in rows[1:]:
        account_id = normalize_lookup_id(row[idx["広告アカウントID"]]) if len(row) > idx["広告アカウントID"] else ""
        account_name = clean_cell(row[idx["広告アカウント名"]]) if len(row) > idx["広告アカウント名"] else ""
        ad_id = normalize_lookup_id(row[idx["広告ID"]]) if len(row) > idx["広告ID"] else ""
        if not account_id or not account_name or not ad_id:
            continue

        has_missing = any(
            len(row) <= idx[column_name] or not clean_cell(row[idx[column_name]])
            for column_name in metadata_columns
        )
        if not has_missing:
            continue

        target_accounts[account_id] = account_name
        target_ad_ids.add(ad_id)
        update_needed_rows += 1

    if target_account_id:
        target_accounts = {
            account_id: account_name
            for account_id, account_name in target_accounts.items()
            if account_id == target_account_id
        }
        allowed_account_ids = set(target_accounts.keys())
        if allowed_account_ids:
            target_ad_ids = set()
            for row in rows[1:]:
                account_id = normalize_lookup_id(row[idx["広告アカウントID"]]) if len(row) > idx["広告アカウントID"] else ""
                ad_id = normalize_lookup_id(row[idx["広告ID"]]) if len(row) > idx["広告ID"] else ""
                if account_id in allowed_account_ids and ad_id:
                    has_missing = any(
                        len(row) <= idx[column_name] or not clean_cell(row[idx[column_name]])
                        for column_name in metadata_columns
                    )
                    if has_missing:
                        target_ad_ids.add(ad_id)

    if not target_accounts or not target_ad_ids:
        return {"updated_rows": 0, "target_accounts": 0, "fetched_metadata": 0, "failed_accounts": []}

    print(f"  メタ情報補完対象: {len(target_accounts)}アカウント / {len(target_ad_ids)}広告ID")
    metadata_by_ad_id = {}
    ordered_ad_ids = sorted(target_ad_ids)
    request_chunk_size = 100
    chunks = [
        ordered_ad_ids[start:start + request_chunk_size]
        for start in range(0, len(ordered_ad_ids), request_chunk_size)
    ]
    completed_ad_ids = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_map = {
            executor.submit(fetch_ad_metadata_by_ids, chunk, token): chunk
            for chunk in chunks
        }
        for future in as_completed(future_map):
            chunk = future_map[future]
            metadata_by_ad_id.update(future.result())
            completed_ad_ids += len(chunk)
            print(f"  広告ID補完: {min(completed_ad_ids, len(ordered_ad_ids))}/{len(ordered_ad_ids)}")

    replacement_rows = []
    for row in rows[1:]:
        ad_id = normalize_lookup_id(row[idx["広告ID"]]) if len(row) > idx["広告ID"] else ""
        existing_values = [
            clean_cell(row[idx["配信ステータス"]]) if len(row) > idx["配信ステータス"] else "",
            clean_cell(row[idx["広告作成日"]]) if len(row) > idx["広告作成日"] else "",
            clean_cell(row[idx["最終更新日"]]) if len(row) > idx["最終更新日"] else "",
            clean_cell(row[idx["クリエイティブID"]]) if len(row) > idx["クリエイティブID"] else "",
            clean_cell(row[idx["遷移先URL"]]) if len(row) > idx["遷移先URL"] else "",
            clean_cell(row[idx["動画ID"]]) if len(row) > idx["動画ID"] else "",
            clean_cell(row[idx["画像ハッシュ"]]) if len(row) > idx["画像ハッシュ"] else "",
        ]
        meta = metadata_by_ad_id.get(ad_id, {})
        replacement_rows.append(build_metadata_cells(meta, existing_values))

    requests = []
    for start in range(0, len(replacement_rows), chunk_size):
        end = min(start + chunk_size, len(replacement_rows))
        requests.append(
            {
                "range": f"S{start + 2}:Y{end + 1}",
                "values": replacement_rows[start:end],
            }
        )

    for start in range(0, len(requests), 20):
        worksheet.batch_update(requests[start:start + 20], value_input_option="USER_ENTERED")
        time.sleep(2)

    return {
        "updated_rows": update_needed_rows,
        "target_accounts": len(target_accounts),
        "fetched_metadata": len(metadata_by_ad_id),
        "failed_accounts": [],
    }


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
        "limit": 100,
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


def fetch_account_status_map(account_ids, token):
    result = {}
    if not account_ids:
        return result

    def fetch_one(account_id):
        resp = requests.get(
            f"{BASE_URL}/act_{account_id}",
            params={
                "fields": "id,name,account_status,disable_reason",
                "access_token": token,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return account_id, {
            "account_status": clean_cell(data.get("account_status")),
            "disable_reason": clean_cell(data.get("disable_reason")),
        }

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(fetch_one, account_id): account_id for account_id in account_ids}
        for future in as_completed(futures):
            account_id = futures[future]
            try:
                key, value = future.result()
                result[key] = value
            except Exception as exc:
                print(f"  アカウント状態取得失敗: {account_id} {exc}")
                result[account_id] = {"account_status": "", "disable_reason": ""}

    return result


def count_active_objects(account_id, edge, token):
    url = f"{BASE_URL}/act_{account_id}/{edge}"
    params = {
        "fields": "id,effective_status,status",
        "limit": 200,
        "access_token": token,
    }
    active_count = 0
    while url:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("data", [])
        active_count += sum(
            1
            for row in rows
            if clean_cell(row.get("effective_status")) == "ACTIVE" or clean_cell(row.get("status")) == "ACTIVE"
        )
        url = data.get("paging", {}).get("next")
        params = None
    return active_count


def fetch_account_activity_map(account_ids, token):
    result = {}
    if not account_ids:
        return result

    def fetch_one(account_id):
        return account_id, {
            "active_campaigns": count_active_objects(account_id, "campaigns", token),
            "active_adsets": count_active_objects(account_id, "adsets", token),
            "active_ads": count_active_objects(account_id, "ads", token),
        }

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_one, account_id): account_id for account_id in account_ids}
        for future in as_completed(futures):
            account_id = futures[future]
            try:
                key, value = future.result()
                result[key] = value
            except Exception as exc:
                print(f"  アクティブ件数取得失敗: {account_id} {exc}")
                result[account_id] = {
                    "active_campaigns": "",
                    "active_adsets": "",
                    "active_ads": "",
                }

    return result


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
        as_sheet_text(row.get("account_id", "")),
        as_sheet_text(row.get("campaign_id", "")),
        row.get("campaign_name", ""),
        as_sheet_text(row.get("adset_id", "")),
        row.get("adset_name", ""),
        as_sheet_text(ad_id),
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
        as_sheet_text(meta.get("creative_id", "")),
        meta.get("creative_url", ""),
        as_sheet_text(meta.get("video_id", "")),
        as_sheet_text(meta.get("image_hash", "")),
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


def build_meta_raw_summary(worksheet):
    rows = worksheet.get_all_values()
    if not rows:
        return {}

    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    summary = {}
    for row in rows[1:]:
        account_id = normalize_lookup_id(row[idx["広告アカウントID"]]) if len(row) > idx["広告アカウントID"] else ""
        account_name = clean_cell(row[idx["広告アカウント名"]]) if len(row) > idx["広告アカウント名"] else ""
        date = clean_cell(row[idx["日付"]]) if len(row) > idx["日付"] else ""
        if not account_id:
            continue

        item = summary.setdefault(
            account_id,
            {
                "広告アカウント名": account_name,
                "raw行数": 0,
                "初回取得日": "",
                "最終取得日": "",
                "最終日配信ステータス": set(),
                "必須メタ欠損行数": 0,
                "遷移先URL未入力行数": 0,
                "動画ID未入力行数": 0,
                "画像ハッシュ未入力行数": 0,
            },
        )
        item["raw行数"] += 1
        item["初回取得日"] = date if not item["初回取得日"] or (date and date < item["初回取得日"]) else item["初回取得日"]

        status = clean_cell(row[idx["配信ステータス"]]) if len(row) > idx["配信ステータス"] else ""
        if not item["最終取得日"] or (date and date > item["最終取得日"]):
            item["最終取得日"] = date
            item["最終日配信ステータス"] = {status} if status else set()
        elif date == item["最終取得日"] and status:
            item["最終日配信ステータス"].add(status)

        created = clean_cell(row[idx["広告作成日"]]) if len(row) > idx["広告作成日"] else ""
        updated = clean_cell(row[idx["最終更新日"]]) if len(row) > idx["最終更新日"] else ""
        creative = clean_cell(row[idx["クリエイティブID"]]) if len(row) > idx["クリエイティブID"] else ""
        url = clean_cell(row[idx["遷移先URL"]]) if len(row) > idx["遷移先URL"] else ""
        video = clean_cell(row[idx["動画ID"]]) if len(row) > idx["動画ID"] else ""
        image = clean_cell(row[idx["画像ハッシュ"]]) if len(row) > idx["画像ハッシュ"] else ""

        if not all([status, created, updated, creative]):
            item["必須メタ欠損行数"] += 1
        if not url:
            item["遷移先URL未入力行数"] += 1
        if not video:
            item["動画ID未入力行数"] += 1
        if not image:
            item["画像ハッシュ未入力行数"] += 1

    return summary


def determine_collection_status(progress_rows, raw_rows):
    if progress_rows is None and raw_rows == 0:
        return "未取得"
    if progress_rows == 0 and raw_rows == 0:
        return "0件"
    if progress_rows is None and raw_rows > 0:
        return "要確認"
    if progress_rows == raw_rows:
        return "完了"
    return "要確認"


def format_latest_statuses(statuses):
    values = sorted(s for s in statuses if s)
    return ",".join(values)


def calc_days_since(date_text):
    if not date_text:
        return ""
    try:
        target = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return ""
    return (datetime.now().date() - target).days


def determine_freshness_status(
    raw_rows,
    latest_date,
    latest_statuses,
    master_note="",
    account_status="",
    active_campaigns=0,
    active_adsets=0,
    active_ads=0,
):
    if raw_rows == 0:
        return "0件"
    if not latest_date:
        return "未取得"

    if "停止中" in clean_cell(master_note):
        return "停止中"

    has_active_objects = any(
        str(value).strip() not in {"", "0"} and int(value) > 0
        for value in [active_campaigns, active_adsets, active_ads]
    )

    expected_latest = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")
    if latest_date >= expected_latest:
        return "最新"

    if has_active_objects:
        return "要確認"

    if account_status and account_status != "1":
        return "停止中"

    status_set = {status for status in latest_statuses if status}
    if status_set and status_set.issubset(PAUSED_LIKE_STATUSES):
        return "停止中"
    if status_set & ACTIVE_LIKE_STATUSES:
        return "要確認"
    return "要確認"


def ensure_status_tab(spreadsheet):
    try:
        return spreadsheet.worksheet(STATUS_TAB_NAME)
    except Exception:
        return spreadsheet.add_worksheet(title=STATUS_TAB_NAME, rows=200, cols=len(STATUS_HEADER))


def apply_status_tab_formatting(spreadsheet, worksheet, row_count):
    header_bg = {"red": 0.357, "green": 0.584, "blue": 0.976}
    header_text = {"red": 1, "green": 1, "blue": 1}
    worksheet.format(
        f"A1:{chr(ord('A') + len(STATUS_HEADER) - 1)}1",
        {
            "backgroundColor": header_bg,
            "textFormat": {
                "bold": True,
                "fontSize": 11,
                "foregroundColor": header_text,
                "fontFamily": "Arial",
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )
    requests = [
        {
            "updateSheetProperties": {
                "properties": {"sheetId": worksheet.id, "gridProperties": {"frozenRowCount": 1}},
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": worksheet.id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 34},
                "fields": "pixelSize",
            }
        },
        {
            "updateBorders": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 0,
                    "endRowIndex": row_count,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(STATUS_HEADER),
                },
                "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "startColumnIndex": 2,
                    "endColumnIndex": 3,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "TEXT"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "startColumnIndex": 4,
                    "endColumnIndex": 9,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "0"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "startColumnIndex": 12,
                    "endColumnIndex": 14,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "0"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": worksheet.id,
                    "startRowIndex": 1,
                    "startColumnIndex": 16,
                    "endColumnIndex": 21,
                },
                "cell": {
                    "userEnteredFormat": {
                        "numberFormat": {
                            "type": "NUMBER",
                            "pattern": "0"
                        }
                    }
                },
                "fields": "userEnteredFormat.numberFormat",
            }
        },
    ]
    for i, header in enumerate(STATUS_HEADER):
        width = max(sum(14 if ord(ch) > 127 else 7 for ch in header) + 80, 120)
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "COLUMNS",
                        "startIndex": i,
                        "endIndex": i + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    spreadsheet.batch_update({"requests": requests})


def update_meta_status_sheet(
    spreadsheet,
    raw_worksheet,
    target_accounts,
    progress,
    account_notes=None,
    account_status_map=None,
    account_activity_map=None,
):
    status_ws = ensure_status_tab(spreadsheet)
    raw_summary = build_meta_raw_summary(raw_worksheet)
    completed = progress.get("completed_accounts", {})
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    account_notes = account_notes or {}
    account_status_map = account_status_map or {}
    account_activity_map = account_activity_map or {}

    rows = [STATUS_HEADER]
    for account_id, account_name in sorted(target_accounts.items(), key=lambda item: item[1]):
        raw = raw_summary.get(account_id, {})
        progress_rows = completed.get(account_id)
        latest_statuses = raw.get("最終日配信ステータス", set())
        account_status_info = account_status_map.get(account_id, {})
        account_status = clean_cell(account_status_info.get("account_status"))
        disable_reason = clean_cell(account_status_info.get("disable_reason"))
        activity_info = account_activity_map.get(account_id, {})
        active_campaigns = activity_info.get("active_campaigns", "")
        active_adsets = activity_info.get("active_adsets", "")
        active_ads = activity_info.get("active_ads", "")
        rows.append(
                [
                    "Meta広告",
                    "スキルプラス",
                    as_sheet_text(account_id),
                    account_name,
                    account_status,
                    disable_reason,
                    active_campaigns,
                    active_adsets,
                    active_ads,
                    determine_collection_status(progress_rows, raw.get("raw行数", 0)),
                    determine_freshness_status(
                        raw.get("raw行数", 0),
                        raw.get("最終取得日", ""),
                        latest_statuses,
                        account_notes.get(account_id, ""),
                        account_status,
                        active_campaigns,
                        active_adsets,
                        active_ads,
                    ),
                    format_latest_statuses(latest_statuses),
                    progress_rows if progress_rows is not None else "",
                    raw.get("raw行数", 0),
                    raw.get("初回取得日", ""),
                    raw.get("最終取得日", ""),
                    calc_days_since(raw.get("最終取得日", "")),
                    raw.get("必須メタ欠損行数", 0),
                    raw.get("遷移先URL未入力行数", 0),
                    raw.get("動画ID未入力行数", 0),
                    raw.get("画像ハッシュ未入力行数", 0),
                    now_text,
                ]
        )

    status_ws.clear()
    status_ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")
    apply_status_tab_formatting(spreadsheet, status_ws, len(rows))
    return status_ws


# ============================================================
# メイン
# ============================================================


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--account", help="特定アカウントIDだけ実行")
    parser.add_argument("--reset", action="store_true", help="進捗をリセットして最初から")
    parser.add_argument(
        "--repair-existing-ids",
        action="store_true",
        help="既存のMeta収集シートで指数表記になっているID列を文字列へ修復して終了",
    )
    parser.add_argument(
        "--backfill-ad-metadata",
        action="store_true",
        help="既存のMeta収集シートで S:Y の広告メタ情報を後追い補完して終了",
    )
    parser.add_argument(
        "--update-status-sheet",
        action="store_true",
        help="Meta収集状況タブを現在の raw と progress から再生成して終了",
    )
    args = parser.parse_args()

    token = load_token()
    gc = get_client("kohara")
    sh = gc.open_by_key(SHEET_ID)
    ws = sh.worksheet(TAB_NAME)
    ensure_text_columns(sh, ws)
    accounts = resolve_target_accounts(gc)
    account_notes = load_meta_account_notes_from_master(gc)
    account_status_map = fetch_account_status_map(accounts.keys(), token)
    account_activity_map = fetch_account_activity_map(accounts.keys(), token)

    if args.repair_existing_ids:
        repaired = repair_existing_id_columns(ws)
        print(f"既存ID列を修復: {repaired}")
        return

    if args.backfill_ad_metadata:
        result = backfill_existing_ad_metadata(ws, token, target_account_id=args.account)
        update_meta_status_sheet(
            sh,
            ws,
            accounts,
            load_progress(),
            account_notes=account_notes,
            account_status_map=account_status_map,
            account_activity_map=account_activity_map,
        )
        print(f"既存広告メタ情報を補完: {result}")
        return

    if args.update_status_sheet:
        update_meta_status_sheet(
            sh,
            ws,
            accounts,
            load_progress(),
            account_notes=account_notes,
            account_status_map=account_status_map,
            account_activity_map=account_activity_map,
        )
        print("Meta収集状況タブを更新しました")
        return

    progress = load_progress()
    if args.reset:
        progress = {"completed_accounts": {}, "total_rows_written": 0}
        save_progress(progress)
        # シートもヘッダーだけに戻す
        ws.clear()
        ws.update("A1", [SHEET_HEADER], value_input_option="USER_ENTERED")
        ensure_text_columns(sh, ws)
        print("進捗リセット完了")

    completed = progress.get("completed_accounts", {})

    today = datetime.now().date()
    since_date = "2023-03-01"
    months = generate_months(since_date, today)

    # 対象アカウント決定
    if args.account:
        if args.account not in accounts:
            print(f"アカウント {args.account} は対象外です")
            return
        target_accounts = {args.account: accounts[args.account]}
    else:
        target_accounts = accounts

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
    update_meta_status_sheet(
        sh,
        ws,
        accounts,
        progress,
        account_notes=account_notes,
        account_status_map=account_status_map,
        account_activity_map=account_activity_map,
    )


if __name__ == "__main__":
    main()
