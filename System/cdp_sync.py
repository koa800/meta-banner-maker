#!/usr/bin/env python3
"""
CDP同期スクリプト
- ソースシートからCDP顧客マスタにデータを取り込む
- 除外リストに該当するメールアドレスはスキップ
- 名寄せ（メール/電話番号一致で統合）
- ドライラン対応（--dry-run で実際の書き込みなし）
"""

import sys
import os
import re
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheets_manager import get_client

CDP_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"


class CDPSync:
    def __init__(self, account="kohara"):
        self.client = get_client(account)
        self.ss = self.client.open_by_key(CDP_SHEET_ID)
        self._exclusion_list = None
        self._exclusion_emails = set()
        self._exclusion_phones = set()
        self._exclusion_lines = set()
        self._master_headers = None
        self._master_data = None

    # ─── 除外リスト ─────────────────────────────────────

    def load_exclusion_list(self):
        """除外リストを読み込む（メール・電話番号・LINE名）"""
        ws = self.ss.worksheet("除外リスト")
        data = ws.get_all_values()
        # ヘッダー: メールアドレス / 電話番号 / LINE名 / 名前 / 除外理由 / 追加日
        self._exclusion_emails = set()
        self._exclusion_phones = set()
        self._exclusion_lines = set()
        for row in data[1:]:
            if len(row) > 0 and row[0].strip():
                self._exclusion_emails.add(row[0].strip().lower())
            if len(row) > 1 and row[1].strip():
                self._exclusion_phones.add(normalize_phone(row[1].strip()))
            if len(row) > 2 and row[2].strip():
                self._exclusion_lines.add(row[2].strip())
        total = len(self._exclusion_emails | self._exclusion_phones | self._exclusion_lines)
        print(f"除外リスト: メール{len(self._exclusion_emails)}件, "
              f"電話{len(self._exclusion_phones)}件, LINE{len(self._exclusion_lines)}件")
        self._exclusion_list = self._exclusion_emails  # 後方互換
        return self._exclusion_emails

    def is_excluded(self, email=None, phone=None, line_name=None):
        """メール・電話番号・LINE名のいずれかが除外リストに含まれるか"""
        if self._exclusion_list is None:
            self.load_exclusion_list()
        if email and email.strip().lower() in self._exclusion_emails:
            return True
        if phone and normalize_phone(phone.strip()) in self._exclusion_phones:
            return True
        if line_name and line_name.strip() in self._exclusion_lines:
            return True
        return False

    # ─── 顧客マスタ ─────────────────────────────────────

    def load_master(self):
        """顧客マスタのヘッダーと全データを読み込む"""
        ws = self.ss.worksheet("顧客マスタ")
        data = ws.get_all_values()
        self._master_headers = data[1] if len(data) > 1 else []  # 行2がカラム名
        self._master_data = data[2:] if len(data) > 2 else []    # 行3以降がデータ
        print(f"顧客マスタ: {len(self._master_headers)}列, {len(self._master_data)}行")
        return self._master_headers, self._master_data

    def get_col_index(self, col_name):
        """カラム名からインデックスを取得（位置ではなく名前で検索）"""
        if self._master_headers is None:
            self.load_master()
        try:
            return self._master_headers.index(col_name)
        except ValueError:
            return None

    def build_email_index(self):
        """メールアドレスでインデックスを構築（名寄せ用）"""
        if self._master_data is None:
            self.load_master()
        email_idx = self.get_col_index("メールアドレス")
        if email_idx is None:
            return {}
        index = {}
        for i, row in enumerate(self._master_data):
            if email_idx < len(row) and row[email_idx].strip():
                email = row[email_idx].strip().lower()
                index[email] = i
        return index

    def build_phone_index(self):
        """電話番号でインデックスを構築（名寄せ用）"""
        if self._master_data is None:
            self.load_master()
        phone_idx = self.get_col_index("電話番号")
        if phone_idx is None:
            return {}
        index = {}
        for i, row in enumerate(self._master_data):
            if phone_idx < len(row) and row[phone_idx].strip():
                phone = normalize_phone(row[phone_idx].strip())
                if phone:
                    index[phone] = i
        return index

    # ─── ソース読み込み ─────────────────────────────────

    def read_source(self, spreadsheet_url, tab_name=None):
        """ソースシートを読み込み（ヘッダー行 + データ行）"""
        from sheets_manager import extract_spreadsheet_id
        sheet_id, gid = extract_spreadsheet_id(spreadsheet_url)
        source_ss = self.client.open_by_key(sheet_id)

        if tab_name:
            ws = source_ss.worksheet(tab_name)
        elif gid is not None:
            ws = next((w for w in source_ss.worksheets() if w.id == gid), None)
        else:
            ws = source_ss.sheet1

        data = ws.get_all_values()
        headers = data[0] if data else []
        rows = data[1:] if len(data) > 1 else []
        print(f"ソース [{ws.title}]: {len(headers)}列, {len(rows)}行")
        return headers, rows

    # ─── ドライラン ─────────────────────────────────────

    def dry_run(self, source_url, tab_name, column_mapping, email_col):
        """ドライラン: 取り込み結果をシミュレーション

        Args:
            source_url: ソースシートのURL
            tab_name: ソースのタブ名
            column_mapping: {CDPカラム名: ソースカラム名} のマッピング
            email_col: ソース側のメールアドレスカラム名
        """
        self.load_exclusion_list()
        self.load_master()
        email_index = self.build_email_index()
        phone_index = self.build_phone_index()

        source_headers, source_rows = self.read_source(source_url, tab_name)

        # ソースのカラムインデックス
        src_email_idx = source_headers.index(email_col) if email_col in source_headers else None
        if src_email_idx is None:
            print(f"エラー: ソースにメールカラム '{email_col}' が見つかりません")
            return

        stats = {
            "total": len(source_rows),
            "excluded": 0,
            "matched_email": 0,
            "matched_phone": 0,
            "new": 0,
            "no_key": 0,
            "excluded_emails": [],
        }

        for row in source_rows:
            email = row[src_email_idx].strip().lower() if src_email_idx < len(row) else ""

            # 除外チェック
            if email and self.is_excluded(email):
                stats["excluded"] += 1
                stats["excluded_emails"].append(email)
                continue

            # 名寄せ
            if email and email in email_index:
                stats["matched_email"] += 1
            elif not email:
                stats["no_key"] += 1
            else:
                stats["new"] += 1

        print("\n=== ドライラン結果 ===")
        print(f"ソース合計: {stats['total']}件")
        print(f"除外（スタッフ/テスト）: {stats['excluded']}件")
        if stats["excluded_emails"]:
            for e in stats["excluded_emails"][:5]:
                print(f"  - {e}")
            if len(stats["excluded_emails"]) > 5:
                print(f"  ... 他{len(stats['excluded_emails']) - 5}件")
        print(f"既存顧客（メール一致）: {stats['matched_email']}件 → 更新")
        print(f"新規顧客: {stats['new']}件 → 追加")
        print(f"キーなし（メール空）: {stats['no_key']}件 → スキップ")

        return stats


# ─── ユーティリティ ───────────────────────────────────

def normalize_phone(phone):
    """電話番号を正規化（ハイフン除去、+81→0変換）"""
    if not phone:
        return ""
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if phone.startswith('+81'):
        phone = '0' + phone[3:]
    return phone


# ─── CLI ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("""
CDP同期スクリプト

使い方:
  python3 cdp_sync.py dry-run <ソースURL> <タブ名> <メールカラム名>
  python3 cdp_sync.py exclusion-list
  python3 cdp_sync.py status

例:
  python3 cdp_sync.py dry-run "https://docs.google.com/.../edit" "友だちリスト" "メールアドレス"
  python3 cdp_sync.py exclusion-list
""")
        return

    cmd = sys.argv[1]
    sync = CDPSync()

    if cmd == "dry-run":
        if len(sys.argv) < 5:
            print("エラー: ソースURL, タブ名, メールカラム名を指定してください")
            return
        source_url = sys.argv[2]
        tab_name = sys.argv[3]
        email_col = sys.argv[4]
        # カラムマッピングは今後設定ファイルから読む
        sync.dry_run(source_url, tab_name, {}, email_col)

    elif cmd == "exclusion-list":
        emails = sync.load_exclusion_list()
        for e in sorted(emails):
            print(f"  - {e}")

    elif cmd == "status":
        sync.load_exclusion_list()
        sync.load_master()
        email_index = sync.build_email_index()
        phone_index = sync.build_phone_index()
        print(f"\nメールアドレスあり: {len(email_index)}件")
        print(f"電話番号あり: {len(phone_index)}件")

    else:
        print(f"不明なコマンド: {cmd}")


if __name__ == "__main__":
    main()
