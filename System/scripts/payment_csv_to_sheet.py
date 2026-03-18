#!/usr/bin/env python3
"""
決済CSVを共通25列に正規化して収集シートに書き込む。

方針:
- CSV格納は人がやる。このスクリプトはCSV読み込み→正規化→シート書き込みを担当
- 各ソースのCSVを共通25列に変換する
- 収集段階ではフィルタしない。全イベント・全ステータスを入れる
- 書き込み先: 【アドネス株式会社】決済データ（収集） / 決済データ
"""

from __future__ import annotations

import argparse
import csv
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

HEADER = [
    "課金ID", "参照システム", "イベント", "イベント日時", "イベント金額",
    "課金金額", "課金ステータス", "商品名", "メールアドレス", "姓",
    "名", "名前（原本）", "フリガナ", "電話番号", "決済手段",
    "カードブランド", "課金タイプ", "支払回数", "定期課金ID", "返金日時",
    "返金金額", "返金ステータス", "返金理由", "登録経路", "メタデータ（JSON）",
]

WRITE_RETRY_SECONDS = (5, 10, 20, 40)


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
                if ("429" in str(e) or "Quota" in str(e)) and attempt < len(WRITE_RETRY_SECONDS):
                    print(f"  シート書き込み制限。{WRITE_RETRY_SECONDS[attempt]}秒待機...")
                else:
                    raise
        time.sleep(2)


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
    """UnivaPayのCSVを共通25列に変換。認証プロセスは除外"""
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
            g("課金金額"),                   # 6. 課金金額
            g("課金ステータス"),             # 7. 課金ステータス
            product_name,                    # 8. 商品名
            normalize_email(g("メールアドレス")),  # 9. メールアドレス
            sei,                             # 10. 姓
            mei,                             # 11. 名
            customer_name,                   # 12. 名前（原本）
            "",                              # 13. フリガナ
            normalize_phone(g("電話番号")),  # 14. 電話番号
            g("決済方法"),                   # 15. 決済手段
            g("ブランド"),                   # 16. カードブランド
            g("タイプ"),                     # 17. 課金タイプ
            g("支払い回数"),                 # 18. 支払回数
            g("定期課金ID"),                 # 19. 定期課金ID
            normalize_datetime(g("返金作成日時")),  # 20. 返金日時
            g("返金金額"),                   # 21. 返金金額
            g("返金ステータス"),             # 22. 返金ステータス
            g("理由"),                       # 23. 返金理由
            "",                              # 24. 登録経路
            meta_json,                       # 25. メタデータ（JSON）
        ])

    if skipped:
        print(f"  認証プロセス除外: {skipped:,}件")

    return result


# ============================================================
# MOSH変換
# ============================================================


def convert_mosh(rows: List[List[str]]) -> List[List[str]]:
    """MOSHのCSVを共通25列に変換"""
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
            "",                              # 6. 課金金額
            g("決済ステータス"),             # 7. 課金ステータス
            g("サービス名"),                 # 8. 商品名
            normalize_email(g("email")),     # 9. メールアドレス
            sei,                             # 10. 姓
            mei,                             # 11. 名
            guest_name,                      # 12. 名前（原本）
            "",                              # 13. フリガナ
            "",                              # 14. 電話番号
            g("支払い方法"),                 # 15. 決済手段
            "",                              # 16. カードブランド
            g("支払い種別"),                 # 17. 課金タイプ
            g("総支払い回数"),               # 18. 支払回数
            "",                              # 19. 定期課金ID
            normalize_datetime(g("キャンセル日時")),  # 20. 返金日時
            "",                              # 21. 返金金額
            g("分割ステータス"),             # 22. 返金ステータス
            "",                              # 23. 返金理由
            "",                              # 24. 登録経路
            "",                              # 25. メタデータ（JSON）
        ])

    return result


# ============================================================
# 日本プラム変換
# ============================================================


def convert_jplum(rows: List[List[str]]) -> List[List[str]]:
    """日本プラムのCSVを共通25列に変換"""
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
            "",                              # 6. 課金金額
            g("状態"),                       # 7. 課金ステータス
            "",                              # 8. 商品名（CSVにない）
            normalize_email(g("メールアドレス")),  # 9. メールアドレス
            sei,                             # 10. 姓
            mei,                             # 11. 名
            full_name,                       # 12. 名前（原本）
            kana,                            # 13. フリガナ
            "",                              # 14. 電話番号
            "日本プラム（分割払い）",         # 15. 決済手段
            "",                              # 16. カードブランド
            "分割",                          # 17. 課金タイプ
            g("支払回数"),                   # 18. 支払回数
            "",                              # 19. 定期課金ID
            "",                              # 20. 返金日時
            "",                              # 21. 返金金額
            "",                              # 22. 返金ステータス
            "",                              # 23. 返金理由
            "",                              # 24. 登録経路
            "",                              # 25. メタデータ（JSON）
        ])

    return result


# ============================================================
# きらぼし銀行変換
# ============================================================


def convert_kiraboshi(rows: List[List[str]]) -> List[List[str]]:
    """きらぼし銀行のCSVを共通25列に変換"""
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
            "",                              # 6. 課金金額
            "振込",                          # 7. 課金ステータス
            "",                              # 8. 商品名
            "",                              # 9. メールアドレス
            "",                              # 10. 姓
            "",                              # 11. 名
            summary,                         # 12. 名前（原本）（半角カタカナのまま）
            kana_name_full,                  # 13. フリガナ（全角変換）
            "",                              # 14. 電話番号
            "銀行振込",                      # 15. 決済手段
            "",                              # 16. カードブランド
            "",                              # 17. 課金タイプ
            "",                              # 18. 支払回数
            "",                              # 19. 定期課金ID
            "",                              # 20. 返金日時
            "",                              # 21. 返金金額
            "",                              # 22. 返金ステータス
            "",                              # 23. 返金理由
            "",                              # 24. 登録経路
            "",                              # 25. メタデータ（JSON）
        ])

    return result


# ============================================================
# INVOY変換
# ============================================================


def convert_invoy(rows: List[List[str]]) -> List[List[str]]:
    """INVOYのCSVを共通25列に変換"""
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
            "",                              # 6. 課金金額
            g("ステータス"),                 # 7. 課金ステータス
            g("件名"),                       # 8. 商品名
            "",                              # 9. メールアドレス（CSVにない）
            sei,                             # 10. 姓
            mei,                             # 11. 名
            customer_name,                   # 12. 名前（原本）
            "",                              # 13. フリガナ
            "",                              # 14. 電話番号
            "INVOY",                         # 15. 決済手段
            "",                              # 16. カードブランド
            "",                              # 17. 課金タイプ
            "",                              # 18. 支払回数
            "",                              # 19. 定期課金ID
            "",                              # 20. 返金日時
            "",                              # 21. 返金金額
            "",                              # 22. 返金ステータス
            "",                              # 23. 返金理由
            "",                              # 24. 登録経路
            "",                              # 25. メタデータ（JSON）
        ])

    return result


# ============================================================
# CREDIX変換
# ============================================================


def convert_credix(rows: List[List[str]]) -> List[List[str]]:
    """CREDIXのCSVを共通25列に変換"""
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
            "",                              # 6. 課金金額
            g("結果"),                       # 7. 課金ステータス
            "",                              # 8. 商品名（CSVにない）
            normalize_email(g("E-mail")),    # 9. メールアドレス
            "",                              # 10. 姓
            "",                              # 11. 名
            "",                              # 12. 名前（原本）
            "",                              # 13. フリガナ
            normalize_phone(g("電話番号")),  # 14. 電話番号
            "CREDIX",                        # 15. 決済手段
            "",                              # 16. カードブランド
            "",                              # 17. 課金タイプ
            g("支払回数"),                   # 18. 支払回数
            "",                              # 19. 定期課金ID
            normalize_datetime(g("取り消し日")),  # 20. 返金日時
            "",                              # 21. 返金金額
            "",                              # 22. 返金ステータス
            "",                              # 23. 返金理由
            "",                              # 24. 登録経路
            "",                              # 25. メタデータ（JSON）
        ])

    return result


# ============================================================
# UTAGE売上一覧変換
# ============================================================


def convert_utage(rows: List[List[str]]) -> List[List[str]]:
    """UTAGE売上一覧のCSVをUTAGE補助タブ用の9列に変換（決済データタブには入れない）"""
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
            g("支払方法"),                   # 8. 支払方法
            g("ステータス"),                 # 9. ステータス
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


# ============================================================
# メイン
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="決済CSVを収集シートに書き込む")
    parser.add_argument("csv_paths", nargs="+", help="CSVファイルのパス")
    parser.add_argument("--source", choices=list(CONVERTERS.keys()), help="ソースを明示指定（自動判定を上書き）")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなしで変換結果だけ表示")
    args = parser.parse_args()

    all_rows = []       # 決済データタブ用（25列）
    utage_rows = []     # UTAGE補助タブ用（9列）

    for csv_path in args.csv_paths:
        path = Path(csv_path)
        if not path.exists():
            print(f"ファイルが見つかりません: {csv_path}")
            continue

        source = args.source or detect_source(path.name)
        if not source:
            print(f"ソースを判定できません: {path.name}")
            print(f"  --source オプションで明示指定してください: {list(CONVERTERS.keys())}")
            continue

        converter = CONVERTERS[source]
        print(f"\n[{source}] {path.name} を読み込み中...")
        rows = read_csv(str(path))
        print(f"  CSV行数: {len(rows) - 1}")

        converted = converter(rows)
        print(f"  変換後行数: {len(converted)}")

        if converted:
            # サンプル表示
            sample = converted[0]
            print(f"  サンプル（1行目）:")
            if source == "utage":
                utage_header = ["売上日時", "商品名", "メールアドレス", "名前", "電話番号", "登録経路", "金額", "支払方法", "ステータス"]
                for i, (h, v) in enumerate(zip(utage_header, sample)):
                    if v:
                        print(f"    {h}: {v[:80]}")
            else:
                for i, (h, v) in enumerate(zip(HEADER, sample)):
                    if v:
                        print(f"    {h}: {v[:80]}")

        if source == "utage":
            utage_rows.extend(converted)
        else:
            all_rows.extend(converted)

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

    if all_rows:
        print(f"\n決済データタブに書き込み中... ({len(all_rows):,} 行)")
        ws = sh.worksheet(TAB_NAME)
        append_rows_with_retry(ws, all_rows)
        print(f"  書き込み完了")

    if utage_rows:
        print(f"\nUTAGE補助タブに書き込み中... ({len(utage_rows):,} 行)")
        ws_utage = sh.worksheet(UTAGE_TAB_NAME)
        append_rows_with_retry(ws_utage, utage_rows)
        print(f"  書き込み完了")

    # データソース管理のステータスを更新
    try:
        ws_source = sh.worksheet(SOURCE_MGMT_TAB)
        source_rows = ws_source.get_all_values()
        now_str = datetime.now().strftime("%Y/%m/%d %H:%M")

        # ソースごとの行数を集計
        source_counts = {}
        for row in all_rows:
            s = row[1]  # 参照システム列
            source_counts[s] = source_counts.get(s, 0) + 1

        for i, srow in enumerate(source_rows):
            if i == 0:
                continue
            source_name = srow[0] if srow else ""
            if source_name in source_counts:
                # ステータス(7列目)、最終同期日(8列目)、行数(9列目)を更新
                ws_source.update_cell(i + 1, 7, "正常")
                ws_source.update_cell(i + 1, 8, now_str)
                ws_source.update_cell(i + 1, 9, source_counts[source_name])
        print("データソース管理を更新しました。")
    except Exception as e:
        print(f"データソース管理の更新でエラー: {e}")


if __name__ == "__main__":
    main()
