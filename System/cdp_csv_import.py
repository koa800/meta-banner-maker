#!/usr/bin/env python3
"""
LステップCSVからCDP顧客マスタへのワンショットインポート
- ~/Desktop/LステップCVS/ 配下の全CSVを読み込み
- メール/電話番号で既存顧客と名寄せ
- 信頼性の高い一次データとして既存値も上書き
"""

import csv
import glob
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_sync import (
    CDPSync, normalize_phone, clean_email, is_valid_email,
    is_valid_age, is_valid_url, _col_to_letter, SyncLock,
    build_furigana_dict, split_furigana,
)


CSV_DIR = os.path.expanduser("~/Desktop/LステップCVS")

# ─── カラム検出パターン ─────────────────────────────────

def detect_columns(headers):
    """CSVヘッダーからCDPカラムへのマッピングを自動検出"""
    mapping = {}
    for i, h in enumerate(headers):
        h = h.strip()
        if not h:
            continue

        # メールアドレス
        if h in ("メールアドレス", "【メールアドレス】") or \
           "メールアドレスを教えてください" in h or \
           h == "メールアドレス_メールアドレス":
            mapping.setdefault("メールアドレス", i)

        # 電話番号
        elif h in ("電話番号", "【電話番号（任意）】") or "電話番号を教えてください" in h:
            mapping.setdefault("電話番号", i)

        # 姓
        elif h == "姓" or ("名前を入力" in h and "姓" in h):
            mapping.setdefault("姓", i)

        # 名
        elif h == "名" or ("名前を入力" in h and "名" in h and "姓" not in h):
            mapping.setdefault("名", i)

        # フルネーム（姓名が別カラムにない場合のフォールバック）
        elif h in ("お名前", "お名前（フルネーム）", "名前（任意）"):
            mapping.setdefault("フルネーム", i)
        elif "名前を入力してください" == h.lstrip("0123456789?? "):
            mapping.setdefault("フルネーム", i)

        # 回答者名（最終フォールバック）
        elif h == "回答者名":
            mapping.setdefault("回答者名", i)

        # 性別
        elif h in ("性別", "性別（任意）"):
            mapping.setdefault("性別", i)

        # 年齢
        elif h in ("年齢", "年齢（任意）", "ご年齢") or \
             "年齢を" in h or "年齢について" in h or "ご年齢" in h:
            mapping.setdefault("年齢", i)

        # 年収
        elif "年収" in h and "仕事" not in h:
            mapping.setdefault("年収", i)

        # 職業
        elif h in ("ご職業", "現在のお仕事は？") or \
             ("仕事" in h and ("内容" in h or "ジャンル" in h or "ついて" in h)) or \
             ("お仕事" in h and "について" in h):
            mapping.setdefault("職業", i)

        # 悩み（選択肢）
        elif "悩み" in h and ("選んで" in h or "感じている" in h):
            mapping.setdefault("現在の悩み", i)

        # 悩み（詳細テキスト）
        elif "悩み" in h and ("詳細" in h or "相談" in h or "期待" in h):
            mapping.setdefault("目標", i)  # 詳細は目標カラムに

        # その他の回答（隠しデータ抽出用）
        elif h == "その他の回答":
            mapping.setdefault("_その他", i)

    return mapping


def extract_from_other(text):
    """「その他の回答」から【XX】YYY パターンを抽出"""
    if not text:
        return {}
    result = {}
    for m in re.finditer(r'【([^】]+)】\s*([^【\n]+)', text):
        key, val = m.group(1).strip(), m.group(2).strip()
        if "性別" in key:
            result.setdefault("性別", val)
        elif "姓" == key:
            result.setdefault("姓", val)
        elif "名" == key:
            result.setdefault("名", val)
        elif "電話" in key:
            result.setdefault("電話番号", val)
        elif "年齢" in key:
            result.setdefault("年齢", val)
    return result


def normalize_age_csv(raw):
    """CSV年齢値を正規化（"43歳"→"40代", "30代"→"30代"）"""
    if not raw:
        return ""
    raw = raw.strip()
    # "XX歳" → 年代に変換
    m = re.match(r'^(\d{1,3})\s*歳?$', raw)
    if m:
        age = int(m.group(1))
        if age < 10:
            return ""
        decade = (age // 10) * 10
        return f"{decade}代"
    # "XX代" はそのまま
    if re.match(r'^\d{1,2}代$', raw):
        return raw
    # "20代前半" 等
    m2 = re.match(r'^(\d{1,2})代', raw)
    if m2:
        return f"{m2.group(1)}代"
    return ""


def split_fullname(name):
    """フルネームを姓名に分割"""
    if not name:
        return "", ""
    name = name.strip()
    # スペース区切り
    parts = re.split(r'[\s　]+', name)
    if len(parts) >= 2:
        return parts[0], parts[1]
    return name, ""


# ─── CSV読み込み ─────────────────────────────────────────

def read_all_csvs():
    """全CSVを読み込み、人物単位でマージした辞書を返す
    キー: (email, phone) → {cdpカラム: 値}
    """
    persons = {}  # email_lower → {cdpカラム: 値}
    phone_to_email = {}  # phone → email（紐付け用）
    stats = {"files": 0, "rows": 0, "with_email": 0, "with_phone": 0}

    for f in sorted(glob.glob(f"{CSV_DIR}/**/*.csv", recursive=True)):
        fname = os.path.basename(f)
        folder = os.path.basename(os.path.dirname(f))

        # エンコーディング検出
        rows = []
        headers = []
        for enc in ("cp932", "utf-8-sig", "utf-8"):
            try:
                with open(f, encoding=enc) as fh:
                    reader = csv.reader(fh)
                    headers = [h.strip() for h in next(reader)]
                    rows = list(reader)
                break
            except (UnicodeDecodeError, StopIteration):
                continue

        if not headers:
            continue

        col_map = detect_columns(headers)
        if not col_map:
            continue

        stats["files"] += 1

        for row in rows:
            stats["rows"] += 1

            def get(key):
                idx = col_map.get(key)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return ""

            # メール・電話を取得
            raw_email = get("メールアドレス")
            email = clean_email(raw_email)
            email_lower = email.split(",")[0].strip().lower() if email else ""
            phone = normalize_phone(get("電話番号"))

            # その他の回答から隠しデータ抽出
            other_data = extract_from_other(get("_その他"))
            if not phone and other_data.get("電話番号"):
                phone = normalize_phone(other_data["電話番号"])

            # メールも電話もなければスキップ
            if not email_lower and not phone:
                continue

            if email_lower:
                stats["with_email"] += 1
            if phone:
                stats["with_phone"] += 1

            # 人物キーの解決（メール優先）
            person_key = None
            if email_lower:
                person_key = email_lower
                if phone:
                    phone_to_email[phone] = email_lower
            elif phone:
                # 電話番号で既知のメールがあればそちらに統合
                if phone in phone_to_email:
                    person_key = phone_to_email[phone]
                else:
                    person_key = f"phone:{phone}"

            if person_key not in persons:
                persons[person_key] = {
                    "メールアドレス": "",
                    "電話番号": "",
                }

            p = persons[person_key]

            # メール・電話
            if email and not p["メールアドレス"]:
                p["メールアドレス"] = email
            if phone and not p["電話番号"]:
                p["電話番号"] = phone

            # 姓名
            sei = get("姓") or other_data.get("姓", "")
            mei = get("名") or other_data.get("名", "")
            if not sei and not mei:
                fullname = get("フルネーム") or get("回答者名")
                sei, mei = split_fullname(fullname)
            if sei and not p.get("姓"):
                p["姓"] = sei
            if mei and not p.get("名"):
                p["名"] = mei

            # 性別
            gender = get("性別") or other_data.get("性別", "")
            if gender and gender in ("男性", "女性") and not p.get("性別"):
                p["性別"] = gender

            # 年齢
            age_raw = get("年齢") or other_data.get("年齢", "")
            age = normalize_age_csv(age_raw)
            if age and not p.get("年齢"):
                p["年齢"] = age

            # 年収
            income = get("年収")
            if income and not p.get("年収"):
                p["年収"] = income

            # 職業
            job = get("職業")
            if job and not p.get("職業"):
                p["職業"] = job

            # 悩み
            concern = get("現在の悩み")
            if concern and not p.get("現在の悩み"):
                p["現在の悩み"] = concern

            # 目標（悩み詳細）
            goal = get("目標")
            if goal and not p.get("目標"):
                p["目標"] = goal

    print(f"\nCSV読み込み完了:")
    print(f"  ファイル数: {stats['files']}")
    print(f"  行数: {stats['rows']}")
    print(f"  ユニーク人物: {len(persons)}")
    print(f"  メールあり行: {stats['with_email']}")
    print(f"  電話あり行: {stats['with_phone']}")

    return persons


# ─── CDPインポート ────────────────────────────────────────

def import_to_cdp(persons, dry_run=False):
    """人物データをCDP顧客マスタに反映"""
    cdp = CDPSync()
    cdp.load_exclusion_list()
    cdp.load_master()
    email_index = cdp.build_email_index()
    phone_index = cdp.build_phone_index()

    # CDPカラムのうち、CSVから更新するもの
    target_cols = ["姓", "名", "性別", "年齢", "年収", "職業", "現在の悩み", "目標"]

    stats = {"matched": 0, "updated": 0, "new": 0, "excluded": 0, "cells": 0}
    updates = []  # バッチ更新用
    update_date_idx = cdp.get_col_index("最終更新日")

    ws = cdp.ss.worksheet("顧客マスタ") if not dry_run else None

    for key, data in persons.items():
        email = data.get("メールアドレス", "")
        phone = data.get("電話番号", "")
        email_lower = email.split(",")[0].strip().lower() if email else ""

        # 除外チェック
        if cdp.is_excluded(email, phone):
            stats["excluded"] += 1
            continue

        # 名寄せ
        master_row_idx = None
        if email_lower and email_lower in email_index:
            master_row_idx = email_index[email_lower]
        elif phone and phone in phone_index:
            master_row_idx = phone_index[phone]

        if master_row_idx is not None:
            # 既存顧客 → 空フィールドを補完 + Lステップは信頼性が高いので上書き
            stats["matched"] += 1
            updated = False

            for col_name in target_cols:
                new_val = data.get(col_name, "")
                if not new_val:
                    continue

                cdp_idx = cdp.get_col_index(col_name)
                if cdp_idx is None:
                    continue

                old_val = ""
                if cdp_idx < len(cdp._master_data[master_row_idx]):
                    old_val = cdp._master_data[master_row_idx][cdp_idx]

                # 既存値が空 → 補完
                if not old_val:
                    if not dry_run:
                        sheet_row = master_row_idx + 3
                        col_letter = _col_to_letter(cdp_idx + 1)
                        updates.append({
                            "range": f"{col_letter}{sheet_row}",
                            "values": [[new_val]],
                        })
                    cdp._master_data[master_row_idx][cdp_idx] = new_val
                    stats["cells"] += 1
                    updated = True

            if updated:
                stats["updated"] += 1
                # 最終更新日を自動更新
                if update_date_idx is not None and not dry_run:
                    from datetime import datetime
                    today = datetime.now().strftime("%Y/%m/%d")
                    sheet_row = master_row_idx + 3
                    col_letter = _col_to_letter(update_date_idx + 1)
                    updates.append({
                        "range": f"{col_letter}{sheet_row}",
                        "values": [[today]],
                    })
        else:
            # 新規顧客は追加しない（CSVだけでは不十分）
            # ただしメールor電話があれば名寄せ用にインデックス更新
            stats["new"] += 1

    # バッチ書き込み
    if not dry_run and updates:
        import time
        CHUNK = 500
        for i in range(0, len(updates), CHUNK):
            chunk = updates[i:i + CHUNK]
            ws.batch_update(chunk, value_input_option="USER_ENTERED")
            if i + CHUNK < len(updates):
                time.sleep(1)
        print(f"\n書き込み完了: {len(updates)}セル")

    print(f"\n=== {'ドライラン' if dry_run else 'インポート完了'} ===")
    print(f"既存顧客マッチ: {stats['matched']}件")
    print(f"  うち更新: {stats['updated']}件（{stats['cells']}セル）")
    print(f"除外: {stats['excluded']}件")
    print(f"CDP未登録: {stats['new']}件（※今回は追加しない）")


# ─── CLI ─────────────────────────────────────────────────

if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv

    print("=== LステップCSV → CDPインポート ===\n")
    persons = read_all_csvs()

    if not persons:
        print("インポート対象なし")
        sys.exit(0)

    # 統計表示
    has_email = sum(1 for p in persons.values() if p.get("メールアドレス"))
    has_phone = sum(1 for p in persons.values() if p.get("電話番号"))
    has_name = sum(1 for p in persons.values() if p.get("姓"))
    has_age = sum(1 for p in persons.values() if p.get("年齢"))
    has_gender = sum(1 for p in persons.values() if p.get("性別"))
    has_income = sum(1 for p in persons.values() if p.get("年収"))
    has_job = sum(1 for p in persons.values() if p.get("職業"))
    has_concern = sum(1 for p in persons.values() if p.get("現在の悩み"))

    print(f"\n抽出データ（{len(persons)}人）:")
    print(f"  メール: {has_email}")
    print(f"  電話: {has_phone}")
    print(f"  姓名: {has_name}")
    print(f"  性別: {has_gender}")
    print(f"  年齢: {has_age}")
    print(f"  年収: {has_income}")
    print(f"  職業: {has_job}")
    print(f"  悩み: {has_concern}")

    import_to_cdp(persons, dry_run=dry_run)
