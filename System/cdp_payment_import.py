#!/usr/bin/env python3
"""
決済履歴CSVからCDP顧客マスタへのインポート
- 全決済履歴シート_決済履歴_表.csv を読み込み
- メールアドレスで既存顧客と名寄せ
- 購入関連カラム（初回/最終購入日・商品・着金売上・購入商品一覧）を更新
- 空欄の姓名・フリガナ・LINE名を補完
"""

import csv
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_sync import (
    CDPSync, normalize_amount, normalize_date, clean_email,
    is_valid_email, is_spam_email, _col_to_letter, SyncLock,
    build_furigana_dict, split_furigana,
    build_surname_dict, split_japanese_name,
)

CSV_PATH = os.path.expanduser(
    "~/Desktop/LステップCVS/決済履歴シート/全決済履歴シート_決済履歴_表.csv"
)


def split_name(name):
    """氏名を姓名に分割"""
    if not name or name == "-":
        return "", ""
    name = name.strip()
    parts = re.split(r'[\s　]+', name)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return name, ""


def split_katakana_name(kana):
    """カタカナ名を姓名に分割（スペース区切り）"""
    if not kana or kana == "-":
        return "", ""
    kana = kana.strip()
    parts = re.split(r'[\s　]+', kana)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return kana, ""


def read_payment_csv():
    """決済履歴CSVを読み込み、顧客ごとに集約する

    Returns:
        {email_lower: {
            "メールアドレス": str,
            "purchases": [(date_str, product, amount_int), ...],
            "氏名": str,
            "カタカナ名": str,
            "LINE名": str,
        }}
    """
    customers = {}
    stats = {"total": 0, "no_email": 0, "with_email": 0}

    with open(CSV_PATH, encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        headers = next(reader)

        # カラムインデックス
        idx = {h.strip(): i for i, h in enumerate(headers)}
        date_i = idx.get("日付", 0)
        product_i = idx.get("商品名", 6)
        email_i = idx.get("メールアドレス", 8)
        line_i = idx.get("LINE名", 9)
        name_i = idx.get("氏名", 10)
        kana_i = idx.get("カタカナ名", 11)
        amount_i = idx.get("着金売上", 12)

        for row in reader:
            stats["total"] += 1
            if len(row) <= email_i:
                continue

            email_raw = row[email_i].strip()
            if not email_raw or email_raw == "-":
                stats["no_email"] += 1
                continue

            email = clean_email(email_raw)
            email_lower = email.split(",")[0].strip().lower() if email else ""
            if not email_lower or not is_valid_email(email_lower):
                stats["no_email"] += 1
                continue

            stats["with_email"] += 1

            # 購入データ
            date_str = row[date_i].strip() if len(row) > date_i else ""
            product = row[product_i].strip() if len(row) > product_i else ""
            amount_str = row[amount_i].strip() if len(row) > amount_i else "0"

            # 金額をintに変換
            amount = 0
            try:
                amount = int(amount_str.replace(",", "").replace("¥", ""))
            except ValueError:
                pass

            # 顧客データ集約
            if email_lower not in customers:
                customers[email_lower] = {
                    "メールアドレス": email,
                    "purchases": [],
                    "氏名": "",
                    "カタカナ名": "",
                    "LINE名": "",
                }

            c = customers[email_lower]

            # 購入レコード追加（商品名が"-"でなければ）
            if date_str:
                c["purchases"].append((date_str, product, amount))

            # 氏名・カナ・LINE名（最初に見つかったものを保持）
            name = row[name_i].strip() if len(row) > name_i else ""
            if name and name != "-" and not c["氏名"]:
                c["氏名"] = name

            kana = row[kana_i].strip() if len(row) > kana_i else ""
            if kana and kana != "-" and not c["カタカナ名"]:
                c["カタカナ名"] = kana

            line = row[line_i].strip() if len(row) > line_i else ""
            if line and line != "-" and not c["LINE名"]:
                c["LINE名"] = line

    print(f"\nCSV読み込み完了:")
    print(f"  総行数: {stats['total']}")
    print(f"  メールあり: {stats['with_email']}")
    print(f"  メールなし: {stats['no_email']}")
    print(f"  ユニーク顧客: {len(customers)}")

    return customers


def aggregate_purchases(customers):
    """顧客ごとの購入データを集約する"""
    for email, c in customers.items():
        purchases = c["purchases"]
        if not purchases:
            c["初回購入日"] = ""
            c["初回購入商品"] = ""
            c["最終購入日"] = ""
            c["最終購入商品"] = ""
            c["購入商品"] = ""
            c["着金売上"] = 0
            continue

        # 日付でソート
        purchases.sort(key=lambda x: x[0])

        # 初回・最終
        c["初回購入日"] = normalize_date(purchases[0][0])
        c["初回購入商品"] = purchases[0][1] if purchases[0][1] != "-" else ""
        c["最終購入日"] = normalize_date(purchases[-1][0])
        c["最終購入商品"] = purchases[-1][1] if purchases[-1][1] != "-" else ""

        # 購入商品一覧（ユニーク、"-"除外、順序保持）
        seen = set()
        products = []
        for _, prod, _ in purchases:
            if prod and prod != "-" and prod not in seen:
                seen.add(prod)
                products.append(prod)
        c["購入商品"] = ", ".join(products)

        # 着金売上合計
        c["着金売上"] = sum(amt for _, _, amt in purchases)

    return customers


def import_to_cdp(customers, dry_run=False):
    """顧客購入データをCDP顧客マスタに反映"""
    cdp = CDPSync()
    cdp.load_exclusion_list()
    cdp.load_master()
    email_index = cdp.build_email_index()

    # カラムインデックス取得
    col_indices = {}
    for col in ["姓", "名", "フリガナ（姓）", "フリガナ（名）", "LINE名",
                "初回購入日", "初回購入商品", "最終購入日", "最終購入商品",
                "購入商品", "着金売上", "返金額", "LTV", "最終更新日"]:
        col_indices[col] = cdp.get_col_index(col)

    # フリガナ辞書・姓辞書を構築
    sei_idx = cdp.get_col_index("姓")
    mei_idx = cdp.get_col_index("名")
    furi_sei_idx = cdp.get_col_index("フリガナ（姓）")
    furi_mei_idx = cdp.get_col_index("フリガナ（名）")
    sei_reading, kanji_len_median = build_furigana_dict(
        cdp._master_data, sei_idx, furi_sei_idx, furi_mei_idx
    )
    surname_dict = build_surname_dict(cdp._master_data, sei_idx, mei_idx)

    stats = {
        "matched": 0, "updated": 0, "not_found": 0, "new_added": 0,
        "excluded": 0, "cells": 0, "name_filled": 0,
        "kana_filled": 0, "line_filled": 0,
    }
    updates = []
    today = datetime.now().strftime("%Y/%m/%d")

    ws = cdp.ss.worksheet("顧客マスタ") if not dry_run else None

    for email_lower, data in customers.items():
        email = data["メールアドレス"]

        # 除外チェック
        if cdp.is_excluded(email):
            stats["excluded"] += 1
            continue

        # スパム/テストメール検知
        if is_spam_email(email):
            stats["excluded"] += 1
            continue

        # 名寄せ
        if email_lower not in email_index:
            stats["not_found"] += 1
            continue

        master_row_idx = email_index[email_lower]
        stats["matched"] += 1
        sheet_row = master_row_idx + 3
        updated = False

        def get_existing(col_name):
            idx = col_indices.get(col_name)
            if idx is None:
                return ""
            if idx < len(cdp._master_data[master_row_idx]):
                return cdp._master_data[master_row_idx][idx]
            return ""

        def set_cell(col_name, value):
            nonlocal updated
            idx = col_indices.get(col_name)
            if idx is None or not value:
                return
            col_letter = _col_to_letter(idx + 1)
            updates.append({
                "range": f"{col_letter}{sheet_row}",
                "values": [[value]],
            })
            # メモリ上のデータも更新
            while len(cdp._master_data[master_row_idx]) <= idx:
                cdp._master_data[master_row_idx].append("")
            cdp._master_data[master_row_idx][idx] = value
            updated = True

        # === 購入データ更新（決済履歴CSVが権威ソース → 上書き） ===

        if data["初回購入日"]:
            set_cell("初回購入日", data["初回購入日"])
            stats["cells"] += 1

        if data["初回購入商品"]:
            set_cell("初回購入商品", data["初回購入商品"])
            stats["cells"] += 1

        if data["最終購入日"]:
            set_cell("最終購入日", data["最終購入日"])
            stats["cells"] += 1

        if data["最終購入商品"]:
            set_cell("最終購入商品", data["最終購入商品"])
            stats["cells"] += 1

        if data["購入商品"]:
            set_cell("購入商品", data["購入商品"])
            stats["cells"] += 1

        if data["着金売上"] > 0:
            set_cell("着金売上", normalize_amount(str(data["着金売上"])))
            stats["cells"] += 1

            # LTV計算（着金売上 - 返金額）
            refund_str = get_existing("返金額")
            refund = 0
            if refund_str:
                refund_digits = re.sub(r'[^\d]', '', refund_str)
                if refund_digits:
                    refund = int(refund_digits)
            ltv = data["着金売上"] - refund
            set_cell("LTV", normalize_amount(str(ltv)))
            stats["cells"] += 1

        # === 空欄補完（上書きしない） ===

        # 姓名
        if not get_existing("姓") and data["氏名"]:
            sei, mei = split_japanese_name(data["氏名"], surname_dict)
            if sei:
                set_cell("姓", sei)
                stats["name_filled"] += 1
                stats["cells"] += 1
            if mei and not get_existing("名"):
                set_cell("名", mei)
                stats["cells"] += 1

        # フリガナ
        if not get_existing("フリガナ（姓）") and data["カタカナ名"]:
            kana_sei, kana_mei = split_katakana_name(data["カタカナ名"])
            if not kana_mei and kana_sei:
                # スペースなしの場合、辞書ベースで分割を試みる
                existing_sei = get_existing("姓")
                existing_mei = get_existing("名")
                split_sei, split_mei = split_furigana(
                    kana_sei, existing_sei, existing_mei,
                    sei_reading, kanji_len_median
                )
                if split_sei and split_mei:
                    kana_sei, kana_mei = split_sei, split_mei
            if kana_sei:
                set_cell("フリガナ（姓）", kana_sei)
                stats["kana_filled"] += 1
                stats["cells"] += 1
            if kana_mei and not get_existing("フリガナ（名）"):
                set_cell("フリガナ（名）", kana_mei)
                stats["cells"] += 1

        # LINE名
        if not get_existing("LINE名") and data["LINE名"]:
            set_cell("LINE名", data["LINE名"])
            stats["line_filled"] += 1
            stats["cells"] += 1

        # 最終更新日
        if updated:
            stats["updated"] += 1
            idx = col_indices.get("最終更新日")
            if idx is not None:
                col_letter = _col_to_letter(idx + 1)
                updates.append({
                    "range": f"{col_letter}{sheet_row}",
                    "values": [[today]],
                })

    # バッチ書き込み（既存顧客の更新）
    if not dry_run and updates:
        CHUNK = 500
        for i in range(0, len(updates), CHUNK):
            chunk = updates[i:i + CHUNK]
            ws.batch_update(chunk, value_input_option="USER_ENTERED")
            if i + CHUNK < len(updates):
                time.sleep(1)
            print(f"  更新 {min(i + CHUNK, len(updates))}/{len(updates)}")
        print(f"\n更新書き込み完了: {len(updates)}セル")

    # === 新規顧客の追加 ===

    # 現在の最大顧客ID
    id_idx = col_indices.get("最終更新日")  # just for checking
    id_idx = cdp.get_col_index("顧客ID")
    max_id = 0
    for row in cdp._master_data:
        if id_idx is not None and id_idx < len(row) and row[id_idx].strip():
            try:
                max_id = max(max_id, int(row[id_idx]))
            except ValueError:
                pass

    new_rows = []
    for email_lower, data in customers.items():
        email = data["メールアドレス"]
        if cdp.is_excluded(email):
            continue
        if email_lower in email_index:
            continue

        max_id += 1
        sei, mei = split_japanese_name(data["氏名"], surname_dict) if data["氏名"] else ("", "")
        kana_sei, kana_mei = split_katakana_name(data["カタカナ名"]) if data["カタカナ名"] else ("", "")
        if not kana_mei and kana_sei and sei:
            s_sei, s_mei = split_furigana(kana_sei, sei, mei, sei_reading, kanji_len_median)
            if s_sei and s_mei:
                kana_sei, kana_mei = s_sei, s_mei

        num_cols = len(cdp._master_headers)
        row = [""] * num_cols

        def _set(col_name, val):
            idx = cdp.get_col_index(col_name)
            if idx is not None and val:
                row[idx] = val

        _set("顧客ID", str(max_id))
        _set("作成日", today)
        _set("最終更新日", today)
        _set("メールアドレス", email)
        _set("LINE名", data["LINE名"])
        _set("姓", sei)
        _set("名", mei)
        _set("フリガナ（姓）", kana_sei)
        _set("フリガナ（名）", kana_mei)
        _set("初回購入日", data["初回購入日"])
        _set("初回購入商品", data["初回購入商品"])
        _set("最終購入日", data["最終購入日"])
        _set("最終購入商品", data["最終購入商品"])
        _set("購入商品", data["購入商品"])
        amount = normalize_amount(str(data["着金売上"])) if data["着金売上"] > 0 else ""
        _set("着金売上", amount)
        _set("LTV", amount)
        new_rows.append(row)
        stats["new_added"] += 1

    if not dry_run and new_rows:
        current_rows = len(cdp._master_data) + 2
        needed_rows = current_rows + len(new_rows)
        if needed_rows > ws.row_count:
            ws.add_rows(needed_rows - ws.row_count + 500)

        CHUNK = 500
        for i in range(0, len(new_rows), CHUNK):
            chunk = new_rows[i:i + CHUNK]
            start_row = current_rows + 1 + i
            end_row = start_row + len(chunk) - 1
            last_col_letter = _col_to_letter(len(cdp._master_headers))
            ws.update(range_name=f"A{start_row}:{last_col_letter}{end_row}",
                      values=chunk, value_input_option="USER_ENTERED")
            if i + CHUNK < len(new_rows):
                time.sleep(1)
            print(f"  新規 {min(i + CHUNK, len(new_rows))}/{len(new_rows)}")
        print(f"\n新規追加完了: {len(new_rows)}件")

        # 新規行に罫線を適用
        first_new_row = current_rows + 1  # 1-indexed
        cdp.apply_borders(
            start_row_idx=first_new_row - 1,  # 0-indexed
            end_row_idx=first_new_row - 1 + len(new_rows),
        )

    print(f"\n=== {'ドライラン' if dry_run else 'インポート完了'} ===")
    print(f"CDPマッチ: {stats['matched']}件")
    print(f"  うち更新: {stats['updated']}件（{stats['cells']}セル）")
    print(f"新規追加: {stats['new_added']}件")
    print(f"除外: {stats['excluded']}件")
    print(f"姓名補完: {stats['name_filled']}件")
    print(f"フリガナ補完: {stats['kana_filled']}件")
    print(f"LINE名補完: {stats['line_filled']}件")


def setup_formulas(dry_run=False):
    """累計購入回数のARRAYFORMULAを設定（カラム位置は動的に取得）"""
    if dry_run:
        print("\n[ドライラン] ARRAYFORMULA設定をスキップ")
        return

    cdp = CDPSync()
    cdp.load_master()
    ws = cdp.ss.worksheet("顧客マスタ")

    count_idx = cdp.get_col_index("累計購入回数")
    product_idx = cdp.get_col_index("購入商品")
    if count_idx is None or product_idx is None:
        print("累計購入回数 or 購入商品カラムが見つかりません")
        return

    count_col = _col_to_letter(count_idx + 1)
    product_col = _col_to_letter(product_idx + 1)
    formula = f'=ARRAYFORMULA(IF({product_col}3:{product_col}="","",LEN({product_col}3:{product_col})-LEN(SUBSTITUTE({product_col}3:{product_col},",",""))+1))'
    ws.update(range_name=f"{count_col}3", values=[[formula]], value_input_option="USER_ENTERED")
    print(f"\n累計購入回数({count_col}3): ARRAYFORMULA設定完了")


# ─── CLI ─────────────────────────────────────────────────

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    print("=== 決済履歴CSV → CDPインポート ===\n")

    if not os.path.exists(CSV_PATH):
        print(f"CSVファイルが見つかりません: {CSV_PATH}")
        sys.exit(1)

    customers = read_payment_csv()

    if not customers:
        print("インポート対象なし")
        sys.exit(0)

    # 集約
    aggregate_purchases(customers)

    # 統計表示
    has_purchase = sum(1 for c in customers.values() if c["着金売上"] > 0)
    has_name = sum(1 for c in customers.values() if c["氏名"])
    has_kana = sum(1 for c in customers.values() if c["カタカナ名"])
    has_line = sum(1 for c in customers.values() if c["LINE名"])
    total_amount = sum(c["着金売上"] for c in customers.values())

    print(f"\n集約データ（{len(customers)}人）:")
    print(f"  購入あり: {has_purchase}")
    print(f"  氏名あり: {has_name}")
    print(f"  カナあり: {has_kana}")
    print(f"  LINE名あり: {has_line}")
    print(f"  着金売上合計: ¥{total_amount:,}")

    import_to_cdp(customers, dry_run=dry_run)
    setup_formulas(dry_run=dry_run)
