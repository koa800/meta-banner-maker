#!/usr/bin/env python3
"""
決済CSVを共通20列に正規化して収集シートに書き込む。

方針:
- CSV格納は人がやる。このスクリプトはCSV読み込み→正規化→シート書き込みを担当
- 各ソースのCSVを共通20列に変換する
- 収集段階ではフィルタしない。全イベント・全ステータスを入れる
- 書き込み先: 【アドネス株式会社】決済データ（収集） / 決済データ
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sheets_manager import get_client
from gspread.exceptions import APIError

SHEET_ID = "1FfGM0HpofM8yayhJniArXp_vQ6-4JRvlp6rxDt-eHTI"
TAB_NAME = "決済データ"
UTAGE_TAB_NAME = "UTAGE補助"
SOURCE_MGMT_TAB = "データソース管理"
UTAGE_HEADER = ["売上日時", "商品名", "メールアドレス", "名前", "電話番号", "登録経路", "金額", "ステータス"]

HEADER = [
    "課金ID", "参照システム", "イベント", "イベント日時", "イベント金額",
    "課金ステータス", "商品名", "メールアドレス", "姓", "名",
    "名前（原本）", "フリガナ", "電話番号", "カードブランド", "課金タイプ",
    "支払回数", "定期課金ID", "返金日時", "返金金額",
    "メタデータ（JSON）",
]

WRITE_RETRY_SECONDS = (5, 10, 20, 40)

SOURCE_DISPLAY_NAMES = {
    "univapay": "UnivaPay",
    "jplum": "日本プラム",
    "mosh": "MOSH",
    "kiraboshi": "きらぼし銀行",
    "invoy": "INVOY",
    "credix": "CREDIX",
    "utage": "UTAGE売上一覧",
}

KNOWN_IGNORED_FILE_PATTERNS = [
    (
        re.compile(r"^スキルプラス\s*-\s*受講生サイト登録受講生_.*\.csv$", re.IGNORECASE),
        "UTAGE受講生サイト登録一覧。決済データの取込対象外",
    ),
    (
        re.compile(r"^(?:\d{1,2}[/-]\d{1,2}|\d{1,2}月\d{1,2}日?|データ)なし(?:\.[A-Za-z0-9]+)?$", re.IGNORECASE),
        "データなしメモ。決済データの取込対象外",
    ),
]

SOURCE_REQUIRED_HEADERS = {
    "univapay": {
        "課金ID",
        "イベント",
        "イベント作成日時",
        "イベント金額",
        "課金金額",
        "課金ステータス",
        "メールアドレス",
        "決済方法",
    },
    "jplum": {
        "受付ID",
        "申込者氏名",
        "状態",
        "申込金額",
    },
    "mosh": {
        "サービスID",
        "ゲストID",
        "ゲスト名",
        "決済日",
        "申し込み総額(税込)",
        "決済ステータス",
        "サービス名",
    },
    "kiraboshi": {
        "番号",
        "勘定日",
        "取引区分",
        "入金金額（円）",
        "摘要",
    },
    "invoy": {
        "請求書番号",
        "請求先",
        "件名",
        "請求額",
        "ステータス",
    },
    "credix": {
        "オーダーNo",
        "決済日時",
        "決済金額",
        "結果",
    },
    "utage": {
        "売上日時",
        "商品",
        "メールアドレス",
        "名前",
        "電話番号",
        "登録経路",
        "金額",
        "支払方法",
        "ステータス",
    },
}


# ============================================================
# ユーティリティ
# ============================================================


def read_csv(path: str, encodings=None) -> List[List[str]]:
    """CSVを読み込む。エンコーディングを自動検出"""
    encodings = encodings or ["utf-8-sig", "utf-8", "shift_jis", "cp932"]
    raw = Path(path).read_bytes()
    for enc in encodings:
        try:
            content = raw.decode(enc)
            reader = csv.reader(io.StringIO(content))
            return list(reader)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"デコード失敗: {path}")


def split_name(full_name: str) -> tuple:
    """姓名を分割。分割できない場合は空文字を返す"""
    name = full_name.strip()
    if not name:
        return "", "", ""

    # 「高橋 雅人(タカハシ マサヒト)」形式（日本プラム）
    paren_match = re.match(r"^(.+?)\((.+?)\)$", name)
    if paren_match:
        kanji = paren_match.group(1).strip()
        kana = paren_match.group(2).strip()
        parts = re.split(r"[\s　]+", kanji)
        if len(parts) >= 2:
            return parts[0], " ".join(parts[1:]), kana
        return "", "", kana

    # スペース区切り
    parts = re.split(r"[\s　]+", name)
    if len(parts) >= 2:
        return parts[0], " ".join(parts[1:]), ""

    return "", "", ""


def extract_json_value(json_str: str, key: str) -> str:
    """JSON文字列から指定キーの値を取得"""
    if not json_str or not json_str.strip():
        return ""
    try:
        data = json.loads(json_str)
        return str(data.get(key, ""))
    except (json.JSONDecodeError, TypeError):
        return ""


def normalize_email(email: str) -> str:
    return email.strip().lower() if email else ""


def normalize_datetime(raw: str) -> str:
    """日付をYYYY/MM/DD HH:MM:SS形式に統一する"""
    if not raw:
        return ""
    text = raw.strip()

    # 「2026年03月15日」形式
    m = re.match(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"

    # 「2026-03-17 04:52:32」形式 → スラッシュに変換
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})(.*)", text)
    if m:
        time_part = m.group(4).strip()
        date_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
        if time_part:
            return f"{date_str} {time_part}"
        return date_str

    # 「2026/3/2」形式 → ゼロ埋め
    m = re.match(r"(\d{4})/(\d{1,2})/(\d{1,2})(.*)", text)
    if m:
        time_part = m.group(4).strip()
        date_str = f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
        if time_part:
            return f"{date_str} {time_part}"
        return date_str

    return text


def normalize_phone(phone: str) -> str:
    """電話番号を正規化。ハイフンなし、+81→0変換"""
    if not phone:
        return ""
    p = re.sub(r"[\s\-\(\)]+", "", phone.strip())
    if p.startswith("+81"):
        p = "0" + p[3:]
    return p


def append_rows_with_retry(ws, rows: List[List], chunk_size=5000):
    """シートの末尾に行を追加（チャンク分割＋リトライ）"""
    for i in range(0, len(rows), chunk_size):
        chunk = rows[i:i + chunk_size]
        for attempt, wait in enumerate([0, *WRITE_RETRY_SECONDS]):
            if wait:
                time.sleep(wait)
            try:
                ws.append_rows(chunk, value_input_option="USER_ENTERED")
                break
            except APIError as e:
                error_text = str(e)
                retryable = any(
                    token in error_text
                    for token in ("429", "Quota", "503", "Service is currently unavailable")
                )
                if retryable and attempt < len(WRITE_RETRY_SECONDS):
                    print(f"  シートAPI一時エラー。{WRITE_RETRY_SECONDS[attempt]}秒待機...")
                else:
                    raise
        time.sleep(2)


def classify_filename(filename: str) -> tuple[str, Optional[str], str]:
    """ファイル名から supported / ignored / unknown を判定する。"""
    source = detect_source(filename)
    if source:
        return "supported", source, ""

    for pattern, reason in KNOWN_IGNORED_FILE_PATTERNS:
        if pattern.match(filename):
            return "ignored", None, reason

    return "unknown", None, "想定していないCSVファイル名"


def validate_csv_rows(rows: List[List[str]], source: str) -> List[str]:
    """CSVのヘッダーと最低限の内容を検証する。"""
    errors: List[str] = []
    if not rows:
        return ["CSVが空です"]

    header = [str(cell).strip() for cell in rows[0]]
    required_headers = SOURCE_REQUIRED_HEADERS.get(source, set())
    missing = [name for name in required_headers if name not in header]
    if missing:
        errors.append(f"必須ヘッダー不足: {', '.join(missing)}")

    if len(rows) <= 1:
        errors.append("ヘッダーのみでデータ行がありません")

    return errors


def row_signature(row: List[str], kind: str) -> str:
    raw = "|".join([kind, *[str(cell).strip() for cell in row]])
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def load_existing_row_signatures(spreadsheet) -> tuple[set[str], set[str]]:
    payment_signatures: set[str] = set()
    utage_signatures: set[str] = set()

    try:
        payment_rows = spreadsheet.worksheet(TAB_NAME).get_all_values()
        for row in payment_rows[1:]:
            if any(str(cell).strip() for cell in row):
                payment_signatures.add(row_signature(row, "payment"))
    except Exception:
        pass

    try:
        utage_rows = spreadsheet.worksheet(UTAGE_TAB_NAME).get_all_values()
        for row in utage_rows[1:]:
            if any(str(cell).strip() for cell in row):
                utage_signatures.add(row_signature(row, "utage"))
    except Exception:
        pass

    return payment_signatures, utage_signatures


def append_normalized_rows(
    spreadsheet,
    payment_rows: List[List[str]],
    utage_rows: List[List[str]],
    existing_payment_signatures: Optional[set[str]] = None,
    existing_utage_signatures: Optional[set[str]] = None,
) -> dict:
    """重複行を除外しながら収集シートへ追記する。"""
    if existing_payment_signatures is None or existing_utage_signatures is None:
        existing_payment_signatures, existing_utage_signatures = load_existing_row_signatures(spreadsheet)

    payment_to_write: List[List[str]] = []
    utage_to_write: List[List[str]] = []
    skipped_payment = 0
    skipped_utage = 0

    for row in payment_rows:
        signature = row_signature(row, "payment")
        if signature in existing_payment_signatures:
            skipped_payment += 1
            continue
        existing_payment_signatures.add(signature)
        payment_to_write.append(row)

    for row in utage_rows:
        signature = row_signature(row, "utage")
        if signature in existing_utage_signatures:
            skipped_utage += 1
            continue
        existing_utage_signatures.add(signature)
        utage_to_write.append(row)

    if payment_to_write:
        ws = spreadsheet.worksheet(TAB_NAME)
        append_rows_with_retry(ws, payment_to_write)

    if utage_to_write:
        ws_utage = spreadsheet.worksheet(UTAGE_TAB_NAME)
        append_rows_with_retry(ws_utage, utage_to_write)

    return {
        "written_payment_rows": len(payment_to_write),
        "written_utage_rows": len(utage_to_write),
        "skipped_payment_duplicates": skipped_payment,
        "skipped_utage_duplicates": skipped_utage,
    }


def update_source_management(spreadsheet, source_counts: Dict[str, int]) -> None:
    """データソース管理の同期情報を更新する。"""
    try:
        ws_source = spreadsheet.worksheet(SOURCE_MGMT_TAB)
        source_rows = ws_source.get_all_values()
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
        for i, srow in enumerate(source_rows):
            if i == 0:
                continue
            source_name = srow[0] if srow else ""
            if source_name in source_counts:
                ws_source.update_cell(i + 1, 7, "正常")
                ws_source.update_cell(i + 1, 8, now_str)
                ws_source.update_cell(i + 1, 9, source_counts[source_name])
        print("データソース管理を更新しました。")
    except Exception as e:
        print(f"データソース管理の更新でエラー: {e}")


# ============================================================
# UnivaPay変換
# ============================================================


# UnivaPayで収集対象とするイベント（決済に関わる事実のみ）
# 認証プロセス（3-Dセキュア、CVVオーソリ、トークン発行）は除外
UNIVAPAY_INCLUDE_EVENTS = {
    "売上",
    "売上失敗",
    "返金",
    "赤伝返金",
    "赤伝返金失敗",
    "チャージバック",
    "キャンセル",
    "キャンセル失敗",
}

UNIVAPAY_EXCLUDE_EVENTS = {
    "3-Dセキュア認証",
    "3-Dセキュア認証失敗",
    "3-Dセキュア認証タイムアウト",
    "3-Dセキュア認証処理待ち",
    "CVVオーソリ",
    "CVVオーソリ失敗",
    "リカーリングトークン発行",
    "ワンタイムトークン発行",
}


def convert_univapay(rows: List[List[str]]) -> List[List[str]]:
    """UnivaPayのCSVを共通20列に変換。認証プロセスは除外"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []
    skipped = 0

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        # 認証プロセスのイベントを除外
        event = g("イベント")
        if event in UNIVAPAY_EXCLUDE_EVENTS:
            skipped += 1
            continue

        # メタデータからcustomer_nameと商品名を抽出
        charge_meta = g("課金メタデータ")
        token_meta = g("トークンメタデータ")
        product_name = extract_json_value(charge_meta, "product_detail_name")
        customer_name = extract_json_value(charge_meta, "customer_name")
        if not customer_name:
            customer_name = extract_json_value(token_meta, "univapay-name")

        sei, mei, _ = split_name(customer_name)

        # メタデータJSON（トークン+課金を統合）
        meta_json = ""
        if token_meta or charge_meta:
            meta_parts = {}
            if token_meta:
                meta_parts["token_metadata"] = token_meta
            if charge_meta:
                meta_parts["charge_metadata"] = charge_meta
            meta_json = json.dumps(meta_parts, ensure_ascii=False)

        result.append([
            g("課金ID"),                    # 1. 課金ID
            "UnivaPay",                      # 2. 参照システム
            g("イベント"),                   # 3. イベント
            normalize_datetime(g("イベント作成日時")),  # 4. イベント日時
            g("イベント金額"),               # 5. イベント金額
            g("課金ステータス"),             # 6. 課金ステータス
            product_name,                    # 7. 商品名
            normalize_email(g("メールアドレス")),  # 8. メールアドレス
            sei,                             # 9. 姓
            mei,                             # 10. 名
            customer_name,                   # 11. 名前（原本）
            "",                              # 12. フリガナ
            normalize_phone(g("電話番号")),  # 13. 電話番号
            g("ブランド"),                   # 14. カードブランド
            g("タイプ"),                     # 15. 課金タイプ
            g("支払い回数"),                 # 16. 支払回数
            g("定期課金ID"),                 # 17. 定期課金ID
            normalize_datetime(g("返金作成日時")),  # 18. 返金日時
            g("返金金額"),                   # 19. 返金金額
            meta_json,                       # 20. メタデータ（JSON）
        ])

    if skipped:
        print(f"  認証プロセス除外: {skipped:,}件")

    return result


# ============================================================
# MOSH変換
# ============================================================


def convert_mosh(rows: List[List[str]]) -> List[List[str]]:
    """MOSHのCSVを共通20列に変換"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        guest_name = g("ゲスト名")
        sei, mei, _ = split_name(guest_name)

        # 複合キー: サービスID + ゲストID + 決済日
        charge_id = f"MOSH-{g('サービスID')}-{g('ゲストID')}-{g('決済日')}"

        result.append([
            charge_id,                       # 1. 課金ID
            "MOSH",                          # 2. 参照システム
            "",                              # 3. イベント（MOSHにはない）
            normalize_datetime(g("決済日")),  # 4. イベント日時
            g("申し込み総額(税込)"),          # 5. イベント金額
            g("決済ステータス"),             # 6. 課金ステータス
            g("サービス名"),                 # 7. 商品名
            normalize_email(g("email")),     # 8. メールアドレス
            sei,                             # 9. 姓
            mei,                             # 10. 名
            guest_name,                      # 11. 名前（原本）
            "",                              # 12. フリガナ
            "",                              # 13. 電話番号
            "",                              # 14. カードブランド
            g("支払い種別"),                 # 15. 課金タイプ
            g("総支払い回数"),               # 16. 支払回数
            "",                              # 17. 定期課金ID
            normalize_datetime(g("キャンセル日時")),  # 18. 返金日時
            "",                              # 19. 返金金額
            "",                              # 20. メタデータ（JSON）
        ])

    return result


# ============================================================
# 日本プラム変換
# ============================================================


def convert_jplum(rows: List[List[str]]) -> List[List[str]]:
    """日本プラムのCSVを共通20列に変換"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        full_name = g("申込者氏名")
        sei, mei, kana = split_name(full_name)

        result.append([
            g("受付ID"),                     # 1. 課金ID
            "日本プラム",                    # 2. 参照システム
            "",                              # 3. イベント
            normalize_datetime(g("立替日") or g("申込年月日")),  # 4. イベント日時
            g("申込金額"),                   # 5. イベント金額
            g("状態"),                       # 6. 課金ステータス
            "",                              # 7. 商品名（CSVにない）
            normalize_email(g("メールアドレス")),  # 8. メールアドレス
            sei,                             # 9. 姓
            mei,                             # 10. 名
            full_name,                       # 11. 名前（原本）
            kana,                            # 12. フリガナ
            "",                              # 13. 電話番号
            "",                              # 14. カードブランド
            "分割",                          # 15. 課金タイプ
            g("支払回数"),                   # 16. 支払回数
            "",                              # 17. 定期課金ID
            "",                              # 18. 返金日時
            "",                              # 19. 返金金額
            "",                              # 20. メタデータ（JSON）
        ])

    return result


# ============================================================
# きらぼし銀行変換
# ============================================================


def convert_kiraboshi(rows: List[List[str]]) -> List[List[str]]:
    """きらぼし銀行のCSVを共通20列に変換"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    # 法人振込の対象外パターン
    exclude_patterns = [
        "ﾕﾆｳﾞｧﾍﾟｲ", "ﾕﾆｳﾞｧ", "ｽﾄﾗｲﾌﾟ", "ﾓｯｼｭ",
    ]

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        # 振込のみ対象
        if g("取引区分") != "振込":
            continue

        # 入金のみ（出金は除外）
        amount = g("入金金額（円）").replace(",", "")
        if not amount:
            continue

        # 法人振込を除外
        summary = g("摘要")
        is_excluded = any(p in summary for p in exclude_patterns)
        if is_excluded:
            continue

        # 半角カタカナ→全角カタカナ変換
        import unicodedata
        kana_name = summary
        # 半角→全角
        kana_name_full = ""
        for ch in kana_name:
            full = unicodedata.normalize("NFKC", ch)
            kana_name_full += full

        result.append([
            g("番号"),                       # 1. 課金ID
            "きらぼし銀行",                  # 2. 参照システム
            "",                              # 3. イベント
            normalize_datetime(g("勘定日")),  # 4. イベント日時
            amount,                          # 5. イベント金額
            "振込",                          # 6. 課金ステータス
            "",                              # 7. 商品名
            "",                              # 8. メールアドレス
            "",                              # 9. 姓
            "",                              # 10. 名
            summary,                         # 11. 名前（原本）（半角カタカナのまま）
            kana_name_full,                  # 12. フリガナ（全角変換）
            "",                              # 13. 電話番号
            "",                              # 14. カードブランド
            "",                              # 15. 課金タイプ
            "",                              # 16. 支払回数
            "",                              # 17. 定期課金ID
            "",                              # 18. 返金日時
            "",                              # 19. 返金金額
            "",                              # 20. メタデータ（JSON）
        ])

    return result


# ============================================================
# INVOY変換
# ============================================================


def convert_invoy(rows: List[List[str]]) -> List[List[str]]:
    """INVOYのCSVを共通20列に変換"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        # 請求書番号から日付を抽出（先頭8桁がYYYYMMDD）
        invoice_no = g("請求書番号")
        date_str = ""
        if len(invoice_no) >= 8:
            try:
                d = invoice_no[:8]
                datetime.strptime(d, "%Y%m%d")
                date_str = f"{d[:4]}/{d[4:6]}/{d[6:8]}"
            except ValueError:
                pass

        customer_name = g("請求先")
        sei, mei, _ = split_name(customer_name)

        result.append([
            invoice_no,                      # 1. 課金ID
            "INVOY",                         # 2. 参照システム
            "",                              # 3. イベント
            date_str,                        # 4. イベント日時
            g("請求額"),                     # 5. イベント金額
            g("ステータス"),                 # 6. 課金ステータス
            g("件名"),                       # 7. 商品名
            "",                              # 8. メールアドレス（CSVにない）
            sei,                             # 9. 姓
            mei,                             # 10. 名
            customer_name,                   # 11. 名前（原本）
            "",                              # 12. フリガナ
            "",                              # 13. 電話番号
            "",                              # 14. カードブランド
            "",                              # 15. 課金タイプ
            "",                              # 16. 支払回数
            "",                              # 17. 定期課金ID
            "",                              # 18. 返金日時
            "",                              # 19. 返金金額
            "",                              # 20. メタデータ（JSON）
        ])

    return result


# ============================================================
# CREDIX変換
# ============================================================


def convert_credix(rows: List[List[str]]) -> List[List[str]]:
    """CREDIXのCSVを共通20列に変換"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        result.append([
            g("オーダーNo"),                 # 1. 課金ID
            "CREDIX",                        # 2. 参照システム
            "",                              # 3. イベント
            normalize_datetime(g("決済日時")),  # 4. イベント日時
            g("決済金額"),                   # 5. イベント金額
            g("結果"),                       # 6. 課金ステータス
            "",                              # 7. 商品名（CSVにない）
            normalize_email(g("E-mail")),    # 8. メールアドレス
            "",                              # 9. 姓
            "",                              # 10. 名
            "",                              # 11. 名前（原本）
            "",                              # 12. フリガナ
            normalize_phone(g("電話番号")),  # 13. 電話番号
            "",                              # 14. カードブランド
            "",                              # 15. 課金タイプ
            g("支払回数"),                   # 16. 支払回数
            "",                              # 17. 定期課金ID
            normalize_datetime(g("取り消し日")),  # 18. 返金日時
            "",                              # 19. 返金金額
            "",                              # 20. メタデータ（JSON）
        ])

    return result


# ============================================================
# UTAGE売上一覧変換
# ============================================================


def convert_utage(rows: List[List[str]]) -> List[List[str]]:
    """UTAGE売上一覧のCSVをUTAGE補助タブ用の8列に変換（決済データタブには入れない）"""
    if not rows:
        return []

    header = rows[0]
    col = {h: i for i, h in enumerate(header)}
    result = []

    for row in rows[1:]:
        def g(name):
            idx = col.get(name)
            if idx is None or idx >= len(row):
                return ""
            return row[idx].strip()

        # ¥0取引を除外（受講生サイト登録時のカード認証。決済の事実ではない）
        amount = g("金額")
        if amount == "0" or amount == "":
            continue

        # 3列目は空列だが商品の詳細名が入っている場合がある
        product_detail = row[2].strip() if len(row) > 2 else ""
        product_name = product_detail or g("商品")

        result.append([
            normalize_datetime(g("売上日時")),  # 1. 売上日時
            product_name,                    # 2. 商品名
            normalize_email(g("メールアドレス")),  # 3. メールアドレス
            g("名前"),                       # 4. 名前
            normalize_phone(g("電話番号")),  # 5. 電話番号
            g("登録経路"),                   # 6. 登録経路
            g("金額"),                       # 7. 金額
            g("ステータス"),                 # 8. ステータス
        ])

    return result


# ============================================================
# ソース判定
# ============================================================

CONVERTERS = {
    "univapay": convert_univapay,
    "jplum": convert_jplum,
    "mosh": convert_mosh,
    "kiraboshi": convert_kiraboshi,
    "invoy": convert_invoy,
    "credix": convert_credix,
    "utage": convert_utage,
}

def detect_source(filename: str) -> Optional[str]:
    """ファイル名からソースを判定"""
    name = filename.lower()
    if name.startswith("決済-") or name.startswith("決済_"):
        return "univapay"
    if name.startswith("contracts_"):
        return "jplum"
    if name.startswith("amind_order"):
        return "mosh"
    if name.startswith("nmr"):
        return "kiraboshi"
    if name.startswith("invoy_"):
        return "invoy"
    if re.match(r"^\d{6}\.csv$", name) or name.startswith("credix"):
        return "credix"
    if name.startswith("売上一覧"):
        return "utage"
    return None


def process_csv_file(path: Path, source_override: Optional[str] = None) -> dict:
    """1つのCSVを分類・検証・変換して結果を返す。"""
    status, detected_source, reason = classify_filename(path.name)
    if source_override:
        status = "supported"
        detected_source = source_override
        reason = ""

    result = {
        "file_name": path.name,
        "status": status,
        "source": detected_source,
        "reason": reason,
        "raw_row_count": 0,
        "converted_row_count": 0,
        "payment_rows": [],
        "utage_rows": [],
        "validation_errors": [],
    }

    if status != "supported" or not detected_source:
        return result

    rows = read_csv(str(path))
    result["raw_row_count"] = max(len(rows) - 1, 0)

    validation_errors = validate_csv_rows(rows, detected_source)
    if validation_errors:
        result["status"] = "unexpected_content"
        result["reason"] = " / ".join(validation_errors)
        result["validation_errors"] = validation_errors
        return result

    converter = CONVERTERS[detected_source]
    converted = converter(rows)
    result["converted_row_count"] = len(converted)
    if detected_source == "utage":
        result["utage_rows"] = converted
    else:
        result["payment_rows"] = converted

    return result


# ============================================================
# メイン
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="決済CSVを収集シートに書き込む")
    parser.add_argument("csv_paths", nargs="+", help="CSVファイルのパス")
    parser.add_argument("--source", choices=list(CONVERTERS.keys()), help="ソースを明示指定（自動判定を上書き）")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなしで変換結果だけ表示")
    args = parser.parse_args()

    all_rows = []
    utage_rows = []
    source_counts: Dict[str, int] = {}

    for csv_path in args.csv_paths:
        path = Path(csv_path)
        if not path.exists():
            print(f"ファイルが見つかりません: {csv_path}")
            continue

        result = process_csv_file(path, source_override=args.source)
        if result["status"] == "ignored":
            print(f"\n[ignored] {path.name}")
            print(f"  理由: {result['reason']}")
            continue
        if result["status"] == "unknown":
            print(f"\n[unknown] {path.name}")
            print(f"  理由: {result['reason']}")
            continue
        if result["status"] == "unexpected_content":
            print(f"\n[unexpected_content] {path.name}")
            print(f"  理由: {result['reason']}")
            continue

        source = result["source"]
        print(f"\n[{source}] {path.name} を読み込み中...")
        print(f"  CSV行数: {result['raw_row_count']}")
        print(f"  変換後行数: {result['converted_row_count']}")

        sample_rows = result["utage_rows"] if source == "utage" else result["payment_rows"]
        if sample_rows:
            sample = sample_rows[0]
            print("  サンプル（1行目）:")
            display_header = UTAGE_HEADER if source == "utage" else HEADER
            for h, v in zip(display_header, sample):
                if v:
                    print(f"    {h}: {str(v)[:80]}")

        if source == "utage":
            utage_rows.extend(result["utage_rows"])
        else:
            all_rows.extend(result["payment_rows"])
        display_name = SOURCE_DISPLAY_NAMES.get(source, source)
        source_counts[display_name] = source_counts.get(display_name, 0) + result["converted_row_count"]

    if not all_rows and not utage_rows:
        print("\n変換データがありません。")
        return

    print(f"\n合計: 決済データ {len(all_rows):,} 行 / UTAGE補助 {len(utage_rows):,} 行")

    if args.dry_run:
        print("--dry-run: 書き込みをスキップします。")
        return

    # シートに書き込み
    gc = get_client("kohara")
    sh = gc.open_by_key(SHEET_ID)
    print("\n収集シートに書き込み中...")
    write_result = append_normalized_rows(sh, all_rows, utage_rows)
    print(
        "  決済データ 追加: "
        f"{write_result['written_payment_rows']:,} 行 "
        f"(重複除外 {write_result['skipped_payment_duplicates']:,} 行)"
    )
    print(
        "  UTAGE補助 追加: "
        f"{write_result['written_utage_rows']:,} 行 "
        f"(重複除外 {write_result['skipped_utage_duplicates']:,} 行)"
    )
    update_source_management(sh, source_counts)


if __name__ == "__main__":
    main()
