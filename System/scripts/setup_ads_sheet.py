#!/usr/bin/env python3
"""
広告データ収集シートの初期設計
スプレッドシート設計ルール（Skills/6_システム/スプレッドシート設計ルール.md）準拠
"""

import json
import sys
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sheets_manager import get_client

SPREADSHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"
SYSTEM_DIR = Path(__file__).resolve().parents[1]

# 色定義（スキル準拠）
HEADER_BG = {"red": 0.357, "green": 0.584, "blue": 0.976}  # 青
HEADER_TEXT = {"red": 1, "green": 1, "blue": 1}  # 白
ZEBRA_BG = {"red": 0.91, "green": 0.941, "blue": 0.996}  # 薄い青
WHITE = {"red": 1, "green": 1, "blue": 1}
STATUS_GREEN = {"red": 0.851, "green": 0.918, "blue": 0.827}
STATUS_YELLOW = {"red": 1, "green": 0.949, "blue": 0.8}
STATUS_GRAY = {"red": 0.898, "green": 0.898, "blue": 0.898}

SOURCE_STATUS_OPTIONS = ["正常", "未同期", "停止"]
RULE_STATUS_OPTIONS = ["正常", "未同期", "停止"]
STATUS_COLOR_MAP = {
    "正常": STATUS_GREEN,
    "未同期": STATUS_YELLOW,
    "停止": STATUS_GRAY,
}

# --- Meta広告 ---
META_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告セットID",
    "広告セット名",
    "広告ID",
    "広告名",
    "インプレッション",
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

# --- TikTok広告 ---
TIKTOK_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "CR識別キー",
    "メディアタイプ",
    "メディアID",
    "プロモーション種別",
    "遷移先URL",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "クリック数（all）",
    "消化金額",
    "コンバージョン数（optimization event）",
    "動画再生数",
    "動画2秒再生数",
    "動画6秒再生数",
    "動画完全再生数",
    "出稿形式レーン",
]

# --- X (Twitter)広告 ---
X_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "インプレッション",
    "リンククリック数",
    "消化金額",
    "エンゲージメント数",
    "エンゲージメント率",
]

TABS = {
    "Meta": META_HEADERS,
    "TikTok": TIKTOK_HEADERS,
    "X": X_HEADERS,
}

SOURCE_HEADERS = [
    "ソースID",
    "集客媒体",
    "データ種別",
    "優先度",
    "取得レーン",
    "ソース元",
    "参照先",
    "スクリプト",
    "対象タブ",
    "対象項目",
    "粒度",
    "主キー",
    "対象事業",
    "更新頻度",
    "ステータス",
    "最終同期日",
    "更新数",
    "エラー数",
    "メモ",
]

RULE_HEADERS = [
    "ルールID",
    "カテゴリ",
    "集客媒体",
    "対象タブ",
    "ルール名",
    "内容",
    "防止の仕組み",
    "検知の仕組み",
    "重複判定キー",
    "更新方式",
    "欠損時の扱い",
    "異常時の扱い",
    "実行タイミング",
    "ステータス",
    "補足",
]

MANAGEMENT_TABS = {
    "データソース管理": {
        "headers": SOURCE_HEADERS,
    },
    "データ追加ルール": {
        "headers": RULE_HEADERS,
    },
}

LEGACY_MANAGEMENT_TABS = [
    "Metaデータソース管理",
    "Metaデータ追加ルール",
    "TikTokデータソース管理",
    "TikTokデータ追加ルール",
    "Xデータソース管理",
    "Xデータ追加ルール",
]

# タブ色（RGB 0-1）
TAB_COLOR_BLUE = {"red": 0.357, "green": 0.584, "blue": 0.976}


def to_a1_column_letter(column_number):
    """1始まりの列番号をA1表記の列記号へ変換する。"""
    result = []
    number = column_number
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def estimate_column_width(header):
    """カラム名から適切な列幅を推定（全角≒14px, 半角≒7px + 余白20px）"""
    width = 0
    for char in header:
        if ord(char) > 127:
            width += 14
        else:
            width += 7
    return max(width + 80, 120)  # 少し広めに取り、最低120px


def format_timestamp(dt):
    if dt is None:
        return ""
    return dt.strftime("%Y/%m/%d %H:%M")


def latest_mtime(paths: Iterable[Path]):
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    latest_path = max(existing, key=lambda path: path.stat().st_mtime)
    return datetime.fromtimestamp(latest_path.stat().st_mtime)


def safe_data_row_count(sh, tab_name):
    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        return 0
    values = ws.col_values(1)
    return max(len(values) - 1, 0)


def count_tiktok_lane_rows(sh, keyword):
    try:
        ws = sh.worksheet("TikTok")
    except Exception:
        return 0
    lane_col = TIKTOK_HEADERS.index("出稿形式レーン") + 1
    values = ws.col_values(lane_col)[1:]
    return sum(1 for value in values if keyword in value)


def latest_path(paths: Iterable[Path]):
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    return max(existing, key=lambda path: path.stat().st_mtime)


def load_json_file(path: Optional[Path]):
    if path is None or not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def safe_int(value):
    if value in ("", None):
        return 0
    try:
        return int(value)
    except Exception:
        try:
            return int(float(str(value)))
        except Exception:
            return 0


def join_note(*parts):
    return " / ".join([str(part) for part in parts if part])


def get_meta_monitor_summary(sh):
    try:
        rows = sh.worksheet("Metaアカウント監視").get_all_records()
    except Exception:
        rows = []

    retrieval_counts = Counter(str(row.get("取得状態", "")).strip() for row in rows)
    running_counts = Counter(str(row.get("稼働状態", "")).strip() for row in rows)
    restriction_counts = Counter(str(row.get("制限状態", "")).strip() for row in rows)

    unretrieved_count = sum(
        1
        for row in rows
        if str(row.get("取得状態", "")).strip() not in ("", "完了", "0件")
    )
    required_meta_missing_total = sum(safe_int(row.get("必須メタ欠損行数")) for row in rows)

    return {
        "rows": rows,
        "retrieval_counts": retrieval_counts,
        "running_counts": running_counts,
        "restriction_counts": restriction_counts,
        "unretrieved_count": unretrieved_count,
        "meta_limited_count": restriction_counts.get("Meta制限", 0),
        "required_meta_missing_total": required_meta_missing_total,
    }


def get_tiktok_runtime_summary():
    export_dir = SYSTEM_DIR / "data" / "tiktok_ads_export"
    summary_path = latest_path(export_dir.glob("tiktok_ads_report_*_summary.json"))
    health_path = latest_path(export_dir.glob("tiktok_token_health_*.json"))

    summary = load_json_file(summary_path)
    health = load_json_file(health_path)
    quality = summary.get("sheet_quality", {})

    warn_checks = [check.get("name", "") for check in health.get("checks", []) if check.get("status") == "warn"]
    fail_checks = [check.get("name", "") for check in health.get("checks", []) if check.get("status") == "fail"]

    return {
        "summary_path": summary_path,
        "health_path": health_path,
        "overall_status": health.get("overall_status", ""),
        "warn_checks": warn_checks,
        "fail_checks": fail_checks,
        "total_rows": safe_int(summary.get("total_rows")),
        "row_count": safe_int(quality.get("row_count")),
        "missing_creative_key_rows": safe_int(quality.get("missing_creative_key_rows")),
        "missing_media_id_rows": safe_int(quality.get("missing_media_id_rows")),
        "missing_promotion_type_rows": safe_int(quality.get("missing_promotion_type_rows")),
        "missing_landing_page_url_rows_web": safe_int(quality.get("missing_landing_page_url_rows_web")),
        "missing_landing_page_url_rows_lead_generation": safe_int(quality.get("missing_landing_page_url_rows_lead_generation")),
        "missing_landing_page_url_rows_smart_plus": safe_int(quality.get("missing_landing_page_url_rows_smart_plus")),
        "fallback_error_count": len(summary.get("ads_manager_fallback_errors", [])),
        "url_status_counts": quality.get("url_status_counts", {}),
    }


def get_x_runtime_summary():
    export_dir = SYSTEM_DIR / "data" / "x_ads_export"
    summary_path = latest_path(export_dir.glob("x_ads_report_*_summary.json"))
    summary = load_json_file(summary_path)
    return {
        "summary_path": summary_path,
        "total_rows": safe_int(summary.get("total_rows")),
        "appended_rows": safe_int(summary.get("appended_rows")),
        "skipped_existing_rows": safe_int(summary.get("skipped_existing_rows")),
        "missing_landing_page_url_rows": safe_int(summary.get("missing_landing_page_url_rows")),
        "account_count": safe_int(summary.get("account_count")),
        "accounts": summary.get("accounts", []),
    }


def source_row(
    source_id,
    medium,
    data_type,
    priority,
    lane,
    source_name,
    reference,
    script,
    tab,
    target_fields,
    grain,
    primary_key,
    business,
    frequency,
    status,
    synced_at,
    update_count,
    error_count,
    note,
):
    return [
        source_id,
        medium,
        data_type,
        priority,
        lane,
        source_name,
        reference,
        script,
        tab,
        target_fields,
        grain,
        primary_key,
        business,
        frequency,
        status,
        synced_at,
        update_count,
        error_count,
        note,
    ]


def build_source_management_rows(sh):
    meta_rows = safe_data_row_count(sh, "Meta")
    meta_status_rows = safe_data_row_count(sh, "Metaアカウント監視")
    tiktok_rows = safe_data_row_count(sh, "TikTok")
    x_rows = safe_data_row_count(sh, "X")
    tiktok_normal_rows = count_tiktok_lane_rows(sh, "通常")
    tiktok_smart_rows = count_tiktok_lane_rows(sh, "Smart+")

    meta_progress_path = SYSTEM_DIR / "data" / "meta_ads_fetch_progress.json"
    meta_sync = format_timestamp(latest_mtime([meta_progress_path]))
    tiktok_summary_path = latest_path((SYSTEM_DIR / "data" / "tiktok_ads_export").glob("tiktok_ads_report_*_summary.json"))
    tiktok_sync = format_timestamp(latest_mtime([tiktok_summary_path] if tiktok_summary_path else []))
    x_summary_path = latest_path((SYSTEM_DIR / "data" / "x_ads_export").glob("x_ads_report_*_summary.json"))
    x_sync = format_timestamp(latest_mtime([x_summary_path] if x_summary_path else []))

    meta_summary = get_meta_monitor_summary(sh)
    tiktok_summary = get_tiktok_runtime_summary()
    x_summary = get_x_runtime_summary()

    meta_raw_status = "正常"
    meta_raw_errors = meta_summary["unretrieved_count"] + meta_summary["meta_limited_count"]
    meta_raw_note = join_note(
        "広告アカウントマスタ基準で取得する raw 正本",
        f"Meta制限 {meta_summary['meta_limited_count']}件" if meta_summary["meta_limited_count"] else "",
    )
    if not meta_sync or meta_rows == 0 or meta_summary["unretrieved_count"] > 0:
        meta_raw_status = "未同期"
        meta_raw_note = join_note(
            meta_raw_note,
            "まだ raw が同期されていない" if meta_rows == 0 else "",
            f"未取得 {meta_summary['unretrieved_count']}件" if meta_summary["unretrieved_count"] else "",
        )

    meta_metadata_status = "正常"
    meta_metadata_errors = meta_summary["required_meta_missing_total"]
    meta_metadata_note = join_note(
        "raw の S:Z を補完する",
        f"必須メタ欠損 {meta_summary['required_meta_missing_total']}件" if meta_summary["required_meta_missing_total"] else "",
    )
    if not meta_sync or meta_rows == 0 or meta_summary["required_meta_missing_total"] > 0:
        meta_metadata_status = "未同期"
        meta_metadata_note = join_note(meta_metadata_note, "補完前" if meta_rows == 0 else "")

    meta_status_status = "正常"
    meta_status_errors = meta_summary["meta_limited_count"]
    meta_status_note = join_note(
        "異常検知の正本。マスタの備考=制限中も参照する",
        f"Meta制限 {meta_summary['meta_limited_count']}件" if meta_summary["meta_limited_count"] else "",
    )
    if not meta_sync or meta_status_rows == 0:
        meta_status_status = "未同期"
        meta_status_note = join_note(meta_status_note, "監視タブ未生成")

    tiktok_missing_url_total = (
        tiktok_summary["missing_landing_page_url_rows_web"]
        + tiktok_summary["missing_landing_page_url_rows_lead_generation"]
        + tiktok_summary["missing_landing_page_url_rows_smart_plus"]
    )
    tiktok_warn_note = f"health={','.join(tiktok_summary['warn_checks'])}" if tiktok_summary["warn_checks"] else ""

    tiktok_raw_status = "正常"
    tiktok_raw_errors = (
        len(tiktok_summary["fail_checks"])
        + tiktok_summary["missing_creative_key_rows"]
        + tiktok_missing_url_total
        + tiktok_summary["fallback_error_count"]
        + tiktok_summary["missing_media_id_rows"]
    )
    tiktok_raw_note = join_note(
        "広告アカウントマスタ基準で取得する raw 正本",
        tiktok_warn_note,
        f"メディアID欠損 {tiktok_summary['missing_media_id_rows']}件" if tiktok_summary["missing_media_id_rows"] else "",
        f"URL欠損 {tiktok_missing_url_total}件" if tiktok_missing_url_total else "",
        f"fallback error {tiktok_summary['fallback_error_count']}件" if tiktok_summary["fallback_error_count"] else "",
    )
    if (
        not tiktok_sync
        or tiktok_rows == 0
        or tiktok_summary["fail_checks"]
        or tiktok_summary["missing_creative_key_rows"] > 0
        or tiktok_missing_url_total > 0
        or tiktok_summary["fallback_error_count"] > 0
    ):
        tiktok_raw_status = "未同期"
        tiktok_raw_note = join_note(tiktok_raw_note, "まだ raw が同期されていない" if tiktok_rows == 0 else "")

    tiktok_metadata_status = "正常"
    tiktok_metadata_errors = tiktok_summary["missing_creative_key_rows"] + tiktok_summary["missing_media_id_rows"]
    tiktok_metadata_note = join_note(
        "public API 側で取れる広告メタ情報",
        f"CR識別キー欠損 {tiktok_summary['missing_creative_key_rows']}件" if tiktok_summary["missing_creative_key_rows"] else "",
        f"メディアID欠損 {tiktok_summary['missing_media_id_rows']}件" if tiktok_summary["missing_media_id_rows"] else "",
    )
    if not tiktok_sync or tiktok_rows == 0 or tiktok_summary["missing_creative_key_rows"] > 0:
        tiktok_metadata_status = "未同期"
        tiktok_metadata_note = join_note(tiktok_metadata_note, "補完前" if tiktok_rows == 0 else "")

    tiktok_adgroup_status = "正常"
    tiktok_adgroup_errors = 0
    tiktok_adgroup_note = "URL補完レーン判定にも使う"
    if not tiktok_sync or tiktok_rows == 0:
        tiktok_adgroup_status = "未同期"
        tiktok_adgroup_note = join_note(tiktok_adgroup_note, "補完前")
    elif tiktok_summary["missing_promotion_type_rows"] > 0:
        tiktok_adgroup_status = "未同期"
        tiktok_adgroup_errors = tiktok_summary["missing_promotion_type_rows"]
        tiktok_adgroup_note = join_note(tiktok_adgroup_note, f"プロモーション種別欠損 {tiktok_summary['missing_promotion_type_rows']}件")

    normal_lane_missing = (
        tiktok_summary["missing_landing_page_url_rows_web"]
        + tiktok_summary["missing_landing_page_url_rows_lead_generation"]
    )
    smart_lane_missing = tiktok_summary["missing_landing_page_url_rows_smart_plus"]

    tiktok_normal_fallback_status = "正常" if tiktok_sync else "未同期"
    tiktok_normal_fallback_errors = 0
    tiktok_normal_fallback_note = "通常出稿レーンの URL 補完"
    if tiktok_sync and normal_lane_missing > 0:
        tiktok_normal_fallback_status = "未同期"
        tiktok_normal_fallback_errors = normal_lane_missing
        tiktok_normal_fallback_note = join_note(tiktok_normal_fallback_note, f"通常レーンURL欠損 {normal_lane_missing}件")

    tiktok_smart_fallback_status = "正常" if tiktok_sync else "未同期"
    tiktok_smart_fallback_errors = 0
    tiktok_smart_fallback_note = "Smart+ レーンの URL 補完"
    if tiktok_sync and smart_lane_missing > 0:
        tiktok_smart_fallback_status = "未同期"
        tiktok_smart_fallback_errors = smart_lane_missing
        tiktok_smart_fallback_note = join_note(tiktok_smart_fallback_note, f"Smart+ URL欠損 {smart_lane_missing}件")

    tiktok_bulk_status = "停止"
    tiktok_bulk_errors = 0
    tiktok_bulk_note = "現状は Smart+ detail までで欠損 0。最後の保険として残す"
    if tiktok_missing_url_total > 0:
        tiktok_bulk_status = "未同期"
        tiktok_bulk_errors = tiktok_missing_url_total
        tiktok_bulk_note = join_note(tiktok_bulk_note, f"残欠 {tiktok_missing_url_total}件")

    x_missing_url_count = x_summary["missing_landing_page_url_rows"]
    x_raw_status = "正常"
    x_raw_errors = x_missing_url_count
    x_raw_note = join_note(
        "広告アカウントマスタ基準で取得する raw 正本",
        f"対象アカウント {x_summary['account_count']}件" if x_summary["account_count"] else "",
        f"URL欠損 {x_missing_url_count}件" if x_missing_url_count else "",
    )
    if not x_sync or x_rows == 0 or x_missing_url_count > 0:
        x_raw_status = "未同期"
        x_raw_note = join_note(x_raw_note, "まだ raw が同期されていない" if x_rows == 0 else "")

    x_metadata_status = "正常"
    x_metadata_errors = x_missing_url_count
    x_metadata_note = join_note(
        "promoted_tweets / tweets / cards から CR と URL を補完する",
        f"URL欠損 {x_missing_url_count}件" if x_missing_url_count else "",
    )
    if not x_sync or x_rows == 0 or x_missing_url_count > 0:
        x_metadata_status = "未同期"
        x_metadata_note = join_note(x_metadata_note, "補完前" if x_rows == 0 else "")

    return [
        source_row(
            "meta_insights_raw",
            "Meta",
            "実績",
            "1",
            "本取得",
            "Meta Graph API",
            "act_{ad_account_id}/insights",
            "System/scripts/fetch_meta_ads_to_sheet.py",
            "Meta",
            "日付 / 各ID / 実績列 / コンバージョン(JSON)",
            "1日 x 1広告ID",
            "日付+広告アカウントID+広告ID",
            "スキルプラス",
            "日次",
            meta_raw_status,
            meta_sync,
            str(meta_rows),
            str(meta_raw_errors),
            meta_raw_note,
        ),
        source_row(
            "meta_ad_metadata",
            "Meta",
            "広告メタ情報",
            "2",
            "補完",
            "Meta Graph API",
            "ad fields / creative fields",
            "System/scripts/fetch_meta_ads_to_sheet.py",
            "Meta",
            "配信ステータス / 作成日 / 最終更新日 / クリエイティブID / 遷移先URL / 動画ID / 画像ハッシュ",
            "1広告ID x 最新メタ",
            "広告ID",
            "スキルプラス",
            "日次 + backfill時",
            meta_metadata_status,
            meta_sync,
            str(meta_rows),
            str(meta_metadata_errors),
            meta_metadata_note,
        ),
        source_row(
            "meta_account_status",
            "Meta",
            "収集状況",
            "1",
            "監視",
            "Meta Graph API",
            "account / campaign / adset / ad status",
            "System/scripts/fetch_meta_ads_to_sheet.py",
            "Metaアカウント監視",
            "取得状態 / 稼働状態 / 制限状態 / 判定理由",
            "1広告アカウント",
            "広告アカウントID",
            "スキルプラス",
            "日次",
            meta_status_status,
            meta_sync,
            str(meta_status_rows),
            str(meta_status_errors),
            meta_status_note,
        ),
        source_row(
            "tiktok_report_raw",
            "TikTok",
            "実績",
            "1",
            "本取得",
            "TikTok Marketing API",
            "report/integrated/get",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "日付 / 各ID / 実績列 / 動画系 / 出稿形式レーン",
            "1日 x 1広告ID",
            "日付+広告アカウントID+広告ID",
            "スキルプラス",
            "日次",
            tiktok_raw_status,
            tiktok_sync,
            str(tiktok_rows),
            str(tiktok_raw_errors),
            tiktok_raw_note,
        ),
        source_row(
            "tiktok_ad_metadata",
            "TikTok",
            "広告メタ情報",
            "1",
            "補完",
            "TikTok Marketing API",
            "ad/get",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "配信ステータス / 作成日 / 最終更新日 / CR識別キー / メディアタイプ / メディアID",
            "1広告ID x 最新メタ",
            "広告ID",
            "スキルプラス",
            "日次",
            tiktok_metadata_status,
            tiktok_sync,
            str(tiktok_rows),
            str(tiktok_metadata_errors),
            tiktok_metadata_note,
        ),
        source_row(
            "tiktok_adgroup_metadata",
            "TikTok",
            "広告グループ情報",
            "1",
            "補完",
            "TikTok Marketing API",
            "adgroup/get",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "プロモーション種別",
            "1広告グループ x 最新メタ",
            "広告グループID",
            "スキルプラス",
            "日次",
            tiktok_adgroup_status,
            tiktok_sync,
            str(tiktok_rows),
            str(tiktok_adgroup_errors),
            tiktok_adgroup_note,
        ),
        source_row(
            "tiktok_ads_manager_list",
            "TikTok",
            "URL補完",
            "2",
            "fallback",
            "TikTok Ads Manager",
            "internal ad/list",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "遷移先URL",
            "1広告ID x fallback",
            "広告ID",
            "スキルプラス",
            "URL欠損時",
            tiktok_normal_fallback_status,
            tiktok_sync,
            str(tiktok_normal_rows),
            str(tiktok_normal_fallback_errors),
            tiktok_normal_fallback_note,
        ),
        source_row(
            "tiktok_smart_plus_detail",
            "TikTok",
            "URL補完",
            "2",
            "fallback",
            "TikTok Ads Manager",
            "procedural_detail",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "遷移先URL",
            "1広告ID x fallback",
            "広告ID",
            "スキルプラス",
            "URL欠損時",
            tiktok_smart_fallback_status,
            tiktok_sync,
            str(tiktok_smart_rows),
            str(tiktok_smart_fallback_errors),
            tiktok_smart_fallback_note,
        ),
        source_row(
            "tiktok_bulk_export",
            "TikTok",
            "URL補完",
            "3",
            "fallback",
            "TikTok Ads Manager",
            "Bulk export",
            "System/scripts/fetch_tiktok_ads_report.py",
            "TikTok",
            "遷移先URL",
            "1広告ID x fallback",
            "広告ID",
            "スキルプラス",
            "残欠時のみ",
            tiktok_bulk_status,
            tiktok_sync if tiktok_bulk_status != "停止" else "",
            "0",
            str(tiktok_bulk_errors),
            tiktok_bulk_note,
        ),
        source_row(
            "x_report_raw",
            "X",
            "実績",
            "1",
            "本取得",
            "X Ads API",
            "stats / campaigns / line_items / promoted_tweets",
            "System/scripts/fetch_x_ads_report.py",
            "X",
            "日付 / 各ID / 実績列 / URL",
            "1日 x 1promoted_tweet",
            "日付+広告アカウントID+広告ID",
            "スキルプラス",
            "日次",
            x_raw_status,
            x_sync,
            str(x_rows),
            str(x_raw_errors),
            x_raw_note,
        ),
        source_row(
            "x_entity_metadata",
            "X",
            "広告メタ情報",
            "2",
            "補完",
            "X Ads API",
            "tweets / cards",
            "System/scripts/fetch_x_ads_report.py",
            "X",
            "広告名 / 配信ステータス / クリエイティブ / 遷移先URL",
            "1promoted_tweet x 最新メタ",
            "広告ID",
            "スキルプラス",
            "日次",
            x_metadata_status,
            x_sync,
            str(x_rows),
            str(x_metadata_errors),
            x_metadata_note,
        ),
    ]


def rule_row(
    rule_id,
    category,
    medium,
    target_tab,
    rule_name,
    content,
    prevention,
    detection,
    duplicate_key,
    update_mode,
    missing_policy,
    abnormal_policy,
    timing,
    status,
    note,
):
    return [
        rule_id,
        category,
        medium,
        target_tab,
        rule_name,
        content,
        prevention,
        detection,
        duplicate_key,
        update_mode,
        missing_policy,
        abnormal_policy,
        timing,
        status,
        note,
    ]


def rule_status_from_source(source_status, ok_label="正常"):
    if source_status == "正常":
        return ok_label
    if source_status == "未同期":
        return "未同期"
    if source_status == "停止":
        return "停止"
    return ok_label


def build_rule_rows(sh):
    source_rows = build_source_management_rows(sh)
    source_status_map = {row[0]: row[14] for row in source_rows}
    tiktok_runtime = get_tiktok_runtime_summary()
    tiktok_token_rule_status = "正常"
    if tiktok_runtime["fail_checks"]:
        tiktok_token_rule_status = "未同期"

    return [
        rule_row(
            "common_scope",
            "共通",
            "全媒体",
            "Meta / TikTok / X",
            "対象事業を固定する",
            "収集と加工の対象は、広告アカウントマスタで事業名がスキルプラスの広告アカウントだけに絞る",
            "広告アカウントマスタの事業名を正本にし、対象外事業は最初から対象に入れない",
            "対象外事業の行が raw に出たら停止して検知する",
            "集客媒体+広告アカウントID",
            "対象外事業は収集対象から外す",
            "対象外は追加しない",
            "対象事業とズレた行が出たら停止",
            "本取得前",
            "正常",
            "Addness / デザジュク / AI研修は raw 対象外",
        ),
        rule_row(
            "common_id_text",
            "共通",
            "全媒体",
            "Meta / TikTok / X",
            "長いIDを文字列で保持する",
            "広告アカウントID、キャンペーンID、広告グループID、広告ID、CR関連IDはすべて文字列として書き込む",
            "書き込み時に文字列で投入し、指数表記を防ぐ",
            "指数表記や桁落ちを見つけたら補正対象として検知する",
            "各ID列",
            "既存セルも必要に応じて書き直す",
            "値なしは空欄保持",
            "指数表記が出たら補完または書き直し",
            "書き込み時",
            "正常",
            "Meta で実修復済み",
        ),
        rule_row(
            "common_no_manual_edit",
            "共通",
            "全媒体",
            "Meta / TikTok / X / 管理タブ",
            "自動生成タブは手編集しない",
            "raw と管理タブはスクリプトで再生成する前提とし、人の直接更新を正本にしない",
            "管理タブを setup_ads_sheet.py 正本で毎回再生成する",
            "再実行で差分が戻る前提で、手編集は破棄されることを明示する",
            "",
            "再実行で壊れない idempotent 運用",
            "手編集は次回再生成で上書きされる",
            "正本と食い違う手編集を見つけたら巻き戻す",
            "常時",
            "正常",
            "管理タブは setup_ads_sheet.py が正本",
        ),
        rule_row(
            "meta_raw_append",
            "追加",
            "Meta",
            "Meta",
            "raw を重複なしで追記する",
            "1日 x 1広告ID を単位に Meta raw を追加し、同じ主キー行は重複作成しない",
            "主キーで追記前重複を防ぐ",
            "主キー重複や件数急減を検知して止める",
            "日付+広告アカウントID+広告ID",
            "追記",
            "値なしは空欄保持",
            "主キー重複や件数急減で停止",
            "日次本取得時",
            rule_status_from_source(source_status_map.get("meta_insights_raw", "正常")),
            "広告アカウントマスタ基準で対象を決める",
        ),
        rule_row(
            "meta_status_replace",
            "監視",
            "Meta",
            "Metaアカウント監視",
            "収集状況タブを毎回作り直す",
            "取得状態、稼働状態、制限状態、判定理由を 1広告アカウント単位で再生成する",
            "監視ロジックをスクリプトに集約し、人の判定揺れを防ぐ",
            "稼働中/停止中/Meta制限の判定に矛盾があれば検知する",
            "広告アカウントID",
            "全面更新",
            "0件と停止中を分離して残す",
            "稼働中/停止中/Meta制限の判定に矛盾があれば停止",
            "本取得後",
            rule_status_from_source(source_status_map.get("meta_account_status", "正常")),
            "Meta 側の effective_status とマスタ備考を併用する",
        ),
        rule_row(
            "meta_gap_refresh",
            "補完",
            "Meta",
            "Meta",
            "稼働中アカウントの欠損日だけ再取得する",
            "raw の最終取得日が古いのに稼働中と判定されたアカウントだけ、直近ギャップを差分再取得する",
            "全件再取得ではなくギャップだけを対象にし、過剰更新を防ぐ",
            "監視タブで gap 判定が出た時だけ再取得対象として検知する",
            "日付+広告アカウントID+広告ID",
            "差分再取得",
            "欠損日は再取得対象にする",
            "再取得しても埋まらなければ停止ではなく監視継続",
            "監視タブで要補完判定が出た時",
            rule_status_from_source(source_status_map.get("meta_account_status", "正常")),
            "--refresh-running-gaps",
        ),
        rule_row(
            "tiktok_raw_append",
            "追加",
            "TikTok",
            "TikTok",
            "raw を重複なしで追記する",
            "1日 x 1広告ID を単位に TikTok raw を追加し、同じ主キー行は重複作成しない",
            "主キーで追記前重複を防ぐ",
            "主キー重複や URL 欠損件数の急増を検知する",
            "日付+広告アカウントID+広告ID",
            "追記",
            "値なしは空欄保持",
            "主キー重複や URL 欠損件数の急増を検知する",
            "日次本取得時",
            rule_status_from_source(source_status_map.get("tiktok_report_raw", "正常")),
            "クリックは all、動画指標は raw に残す",
        ),
        rule_row(
            "tiktok_url_fallback",
            "補完",
            "TikTok",
            "TikTok",
            "URL 欠損時に fallback を順に当てる",
            "public API で遷移先URLが取れない広告は、通常出稿は ad/list、Smart+ は procedural_detail で補完する",
            "通常出稿と Smart+ を別レーンで処理し、取り漏れを防ぐ",
            "missing_landing_page_details と summary の欠損件数で未解決を検知する",
            "広告ID",
            "本取得後に補完",
            "未取得は空欄のまま残し summary へ記録する",
            "missing_landing_page_details が残ったら監視対象",
            "本取得直後",
            rule_status_from_source(
                "未同期"
                if source_status_map.get("tiktok_ads_manager_list") == "未同期"
                or source_status_map.get("tiktok_smart_plus_detail") == "未同期"
                or source_status_map.get("tiktok_bulk_export") == "未同期"
                else "正常"
            ),
            "Bulk export は最後の保険として待機",
        ),
        rule_row(
            "tiktok_token_reauth",
            "認証",
            "TikTok",
            "TikTok",
            "認証 fail 時だけ browser 再認可する",
            "health check が fail した時だけ browser セッションを使って新しい access token を再取得し、再診断する",
            "定期 health check を先に通して、不要な再認可を防ぐ",
            "health check の warn / fail を見て再認可要否を検知する",
            "app_id+access_token",
            "再認可後に再診断",
            "refresh_token を前提にしない",
            "再認可も fail したら収集停止",
            "health check fail 時",
            tiktok_token_rule_status,
            "既存運用を壊さないよう read-only 側で閉じる",
        ),
        rule_row(
            "x_raw_append",
            "追加",
            "X",
            "X",
            "raw を重複なしで追記する",
            "1日 x 1promoted_tweet で raw を追加する。主キー重複を許さない",
            "主キーで追記前重複を防ぐ",
            "件数0や主キー重複で停止して検知する",
            "日付+広告アカウントID+広告ID",
            "追記",
            "値なしは空欄保持",
            "件数0や主キー重複で停止",
            "日次本取得時",
            rule_status_from_source(source_status_map.get("x_report_raw")),
            "Xタブの日次追記に使う",
        ),
        rule_row(
            "x_metadata_fill",
            "補完",
            "X",
            "X",
            "URL や CR を補完する",
            "raw 取得時に promoted_tweets / tweets / cards から広告名、配信状態、クリエイティブ、遷移先URLを補完する",
            "raw 本体が取れた後だけ補完を回し、先走りを防ぐ",
            "補完失敗件数をエラー数へ反映して検知する",
            "広告ID",
            "本取得内で補完",
            "未取得は空欄保持",
            "補完失敗件数をエラー数へ反映する",
            "本取得直後",
            rule_status_from_source(source_status_map.get("x_entity_metadata")),
            "URL欠損は summary で追う",
        ),
    ]


def apply_formatting(sh, ws, headers, include_table_styles=True, include_protection=True):
    """スキル準拠の書式を適用"""
    sheet_id = ws.id
    col_count = len(headers)
    col_letter = to_a1_column_letter(col_count)

    metadata = sh.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties.sheetId,bandedRanges,protectedRanges)",
        }
    )
    existing_sheet_meta = {}
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == sheet_id:
            existing_sheet_meta = sheet
            break

    # --- ヘッダー書式（青背景 / 白文字 / 太字 / fontSize 11 / 中央揃え / Arial）---
    header_range = f"A1:{col_letter}1"
    ws.format(header_range, {
        "backgroundColor": HEADER_BG,
        "textFormat": {
            "bold": True,
            "fontSize": 11,
            "foregroundColor": HEADER_TEXT,
            "fontFamily": "Arial",
        },
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE",
    })

    # --- フリーズ行1 ---
    requests = []
    for banded_range in existing_sheet_meta.get("bandedRanges", []):
        banded_range_id = banded_range.get("bandedRangeId")
        if banded_range_id:
            requests.append({"deleteBanding": {"bandedRangeId": banded_range_id}})
    for protected_range in existing_sheet_meta.get("protectedRanges", []):
        range_info = protected_range.get("range", {})
        if range_info.get("startRowIndex") == 0 and range_info.get("endRowIndex") == 1:
            protected_range_id = protected_range.get("protectedRangeId")
            if protected_range_id:
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_range_id}})
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # --- タブ色 ---
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "tabColorStyle": {"rgbColor": TAB_COLOR_BLUE},
            },
            "fields": "tabColorStyle",
        }
    })

    # --- 列幅 ---
    for i, header in enumerate(headers):
        width = estimate_column_width(header)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        })

    # --- ヘッダー行の高さ ---
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1,
            },
            "properties": {"pixelSize": 36},
            "fields": "pixelSize",
        }
    })

    # --- ヘッダー行の黒枠 ---
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            },
            "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
        }
    })

    if include_table_styles:
        # --- 罫線（ヘッダー行 + データ領域100行分）---
        # 外枠太線
        requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 101,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
            }
        })
        # --- 交互色（addBanding）---
        requests.append({
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 1,
                        "endRowIndex": 1000,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "rowProperties": {
                        "firstBandColor": WHITE,
                        "secondBandColor": ZEBRA_BG,
                    },
                }
            }
        })

        # --- データ行のデフォルト書式（Arial / fontSize 10）---
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "fontFamily": "Arial",
                            "fontSize": 10,
                            "bold": False,
                        },
                    }
                },
                "fields": "userEnteredFormat.textFormat",
            }
        })

    if include_protection:
        # --- ヘッダー行保護（警告モード）---
        requests.append({
            "addProtectedRange": {
                "protectedRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "description": "ヘッダー行（変更注意）",
                    "warningOnly": True,
                }
            }
        })

    sh.batch_update({"requests": requests})


def apply_status_controls(sh, ws, headers, status_options):
    if "ステータス" not in headers:
        return

    status_col = headers.index("ステータス")
    status_range = {
        "sheetId": ws.id,
        "startRowIndex": 1,
        "endRowIndex": ws.row_count,
        "startColumnIndex": status_col,
        "endColumnIndex": status_col + 1,
    }

    metadata = sh.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties(sheetId,title),conditionalFormats)",
        }
    )

    delete_requests = []
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") != ws.id:
            continue
        rules = sheet.get("conditionalFormats", [])
        for idx in range(len(rules) - 1, -1, -1):
            rule = rules[idx]
            for rule_range in rule.get("ranges", []):
                if (
                    rule_range.get("sheetId") == ws.id
                    and rule_range.get("startColumnIndex") == status_col
                    and rule_range.get("endColumnIndex") == status_col + 1
                ):
                    delete_requests.append(
                        {
                            "deleteConditionalFormatRule": {
                                "sheetId": ws.id,
                                "index": idx,
                            }
                        }
                    )
                    break

    requests = delete_requests + [
        {
            "setDataValidation": {
                "range": status_range,
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": value} for value in status_options],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        },
        {
            "repeatCell": {
                "range": status_range,
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "CLIP",
                        "textFormat": {
                            "fontFamily": "Arial",
                            "fontSize": 10,
                            "bold": True,
                        },
                    }
                },
                "fields": "userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy,userEnteredFormat.textFormat.fontFamily,userEnteredFormat.textFormat.fontSize,userEnteredFormat.textFormat.bold",
            }
        },
    ]

    rule_index = 0
    for status_value, color in STATUS_COLOR_MAP.items():
        if status_value not in status_options:
            continue
        requests.append(
            {
                "addConditionalFormatRule": {
                    "index": rule_index,
                    "rule": {
                        "ranges": [status_range],
                        "booleanRule": {
                            "condition": {
                                "type": "TEXT_EQ",
                                "values": [{"userEnteredValue": status_value}],
                            },
                            "format": {"backgroundColor": color},
                        },
                    },
                }
            }
        )
        rule_index += 1

    sh.batch_update({"requests": requests})


def ensure_reference_tab(sh, existing_sheets, tab_name, headers, rows):
    values = [headers] + rows
    ws = existing_sheets.get(tab_name)
    target_rows = max(len(values) + 20, 100)
    if ws is None:
        ws = sh.add_worksheet(title=tab_name, rows=target_rows, cols=len(headers))
    else:
        if ws.row_count < target_rows:
            ws.resize(rows=target_rows)
        if ws.col_count < len(headers):
            ws.resize(cols=len(headers))
    ws.clear()
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    apply_formatting(sh, ws, headers)
    if tab_name == "データソース管理":
        apply_status_controls(sh, ws, headers, SOURCE_STATUS_OPTIONS)
    elif tab_name == "データ追加ルール":
        apply_status_controls(sh, ws, headers, RULE_STATUS_OPTIONS)
    return ws


def resolve_management_rows(sh, tab_name):
    if tab_name == "データソース管理":
        return build_source_management_rows(sh)
    if tab_name == "データ追加ルール":
        return build_rule_rows(sh)
    return []


def ensure_management_tabs(sh):
    current_sheets = {ws.title: ws for ws in sh.worksheets()}
    for tab_name in LEGACY_MANAGEMENT_TABS:
        ws = current_sheets.get(tab_name)
        if ws is not None:
            sh.del_worksheet(ws)
            current_sheets = {sheet.title: sheet for sheet in sh.worksheets()}
    for tab_name, config in MANAGEMENT_TABS.items():
        ensure_reference_tab(
            sh,
            current_sheets,
            tab_name,
            config["headers"],
            resolve_management_rows(sh, tab_name),
        )
        current_sheets = {ws.title: ws for ws in sh.worksheets()}


def main():
    reformat_only = "--reformat-only" in sys.argv
    client = get_client("kohara")
    sh = client.open_by_key(SPREADSHEET_ID)

    existing_sheets = {ws.title: ws for ws in sh.worksheets()}

    if reformat_only:
        for tab_name, headers in TABS.items():
            if tab_name not in existing_sheets:
                continue
            ws = existing_sheets[tab_name]
            current_headers = ws.row_values(1) or headers
            apply_formatting(sh, ws, current_headers, include_table_styles=False, include_protection=False)
            print(f"[{tab_name}] 既存タブにヘッダー体裁を再適用。")
        ensure_management_tabs(sh)
        print("\n既存タブの再整形完了！")
        return

    for tab_name, headers in TABS.items():
        # 既存タブがあれば削除して再作成（書式を完全リセット）
        if tab_name in existing_sheets:
            sh.del_worksheet(existing_sheets[tab_name])
            print(f"[{tab_name}] 既存タブを削除。")

        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        print(f"[{tab_name}] タブを新規作成。")

        # ヘッダー書き込み
        ws.update([headers], "A1")

        # 書式適用
        apply_formatting(sh, ws, headers)

        print(f"[{tab_name}] 書式設定完了（{len(headers)}列）")

    ensure_management_tabs(sh)

    # デフォルトの「シート1」を削除
    existing_sheets = {ws.title: ws for ws in sh.worksheets()}
    if "シート1" in existing_sheets:
        sh.del_worksheet(existing_sheets["シート1"])
        print("「シート1」を削除。")

    print("\n設計完了！")


if __name__ == "__main__":
    main()
