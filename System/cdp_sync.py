#!/usr/bin/env python3
"""
CDP同期スクリプト
- ソースシートからCDP顧客マスタにデータを取り込む
- 除外リストに該当するメールアドレス/電話番号はスキップ
- 名寄せ（メール/電話番号一致で統合）
- 電話番号バリデーション・メール類似検知
- 変更ログ記録（before/after）
- 増分同期対応
- ドライラン対応（--dry-run で実際の書き込みなし）
"""

import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheets_manager import get_client

CDP_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
DATA_DIR = Path(__file__).resolve().parent / "data"
CHANGE_LOG_PATH = DATA_DIR / "cdp_change_log.json"
SYNC_STATE_PATH = DATA_DIR / "cdp_sync_state.json"
SIMILARITY_LOG_PATH = DATA_DIR / "cdp_email_warnings.json"
LOCK_FILE_PATH = DATA_DIR / "cdp_sync.lock"
LOCK_TIMEOUT_SECONDS = 600  # 10分でロックタイムアウト


# ─── 排他制御（簡易ロック） ────────────────────────────

class SyncLock:
    """ファイルベースの簡易ロック。同期の同時実行を防止する"""

    def __init__(self, lock_path=LOCK_FILE_PATH, timeout=LOCK_TIMEOUT_SECONDS):
        self.lock_path = Path(lock_path)
        self.timeout = timeout

    def acquire(self):
        """ロックを取得する。既にロック中ならFalseを返す"""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)

        if self.lock_path.exists():
            # タイムアウトチェック（デッドロック防止）
            try:
                lock_data = json.loads(self.lock_path.read_text())
                lock_time = datetime.fromisoformat(lock_data.get("locked_at", ""))
                elapsed = (datetime.now() - lock_time).total_seconds()
                if elapsed < self.timeout:
                    print(f"同期ロック中: {lock_data.get('locked_by', '不明')} "
                          f"({int(elapsed)}秒前に開始)")
                    return False
                else:
                    print(f"ロックタイムアウト（{int(elapsed)}秒経過）→ 強制解除")
            except (json.JSONDecodeError, ValueError, IOError):
                print("破損したロックファイルを検出 → 強制解除")

        # ロック取得
        lock_data = {
            "locked_at": datetime.now().isoformat(),
            "locked_by": f"cdp_sync (PID: {os.getpid()})",
        }
        self.lock_path.write_text(json.dumps(lock_data, ensure_ascii=False))
        return True

    def release(self):
        """ロックを解除する"""
        if self.lock_path.exists():
            self.lock_path.unlink()

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("同期がロック中です。他の同期が完了するまで待ってください")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


# ─── 変更ログ ─────────────────────────────────────────

class SyncLogger:
    """同期時の変更前後の値をログに記録する"""

    def __init__(self, log_path=CHANGE_LOG_PATH, max_entries=10000):
        self.log_path = Path(log_path)
        self.max_entries = max_entries
        self._entries = []
        self._load()

    def _load(self):
        if self.log_path.exists():
            try:
                self._entries = json.loads(self.log_path.read_text())
            except (json.JSONDecodeError, IOError):
                self._entries = []

    def log(self, action, row_key, column, old_value, new_value, source=""):
        """変更を1件記録する

        Args:
            action: "update" / "insert" / "skip"
            row_key: 顧客の識別キー（メールアドレス等）
            column: 変更されたCDPカラム名
            old_value: 変更前の値
            new_value: 変更後の値
            source: データソース名
        """
        self._entries.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "row_key": row_key,
            "column": column,
            "old_value": str(old_value) if old_value else "",
            "new_value": str(new_value) if new_value else "",
            "source": source,
        })

    def save(self):
        """ログをファイルに保存（古いエントリは自動削除）"""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # 上限を超えたら古い方から削除
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]
        self.log_path.write_text(
            json.dumps(self._entries, ensure_ascii=False, indent=2)
        )
        print(f"変更ログ: {len(self._entries)}件保存 → {self.log_path}")

    def summary(self):
        """今回のセッションで記録したログの集計"""
        actions = {}
        for e in self._entries:
            actions[e["action"]] = actions.get(e["action"], 0) + 1
        return actions


# ─── 増分同期の状態管理 ────────────────────────────────

class SyncState:
    """ソースごとの最終同期状態を追跡する"""

    def __init__(self, state_path=SYNC_STATE_PATH):
        self.state_path = Path(state_path)
        self._state = {}
        self._load()

    def _load(self):
        if self.state_path.exists():
            try:
                self._state = json.loads(self.state_path.read_text())
            except (json.JSONDecodeError, IOError):
                self._state = {}

    def get_last_sync(self, source_key):
        """ソースの最終同期情報を取得

        Args:
            source_key: ソースの識別キー（URL+タブ名）
        Returns:
            {"last_sync": ISO日時, "last_row_count": int} or None
        """
        return self._state.get(source_key)

    def update(self, source_key, row_count):
        """同期完了後に状態を更新"""
        self._state[source_key] = {
            "last_sync": datetime.now().isoformat(),
            "last_row_count": row_count,
        }

    def save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2)
        )


# ─── 電話番号バリデーション ────────────────────────────

def validate_phone(phone):
    """電話番号のバリデーション

    Returns:
        (normalized, warnings) のタプル
        normalized: 正規化済み電話番号（問題がなければそのまま）
        warnings: 警告メッセージのリスト
    """
    warnings = []
    if not phone:
        return "", warnings

    raw = phone.strip()

    # 科学的記数法の検出（例: 9.01E+09）
    if re.search(r'[eE]\+?\d+', raw):
        warnings.append(f"科学的記数法を検出: '{raw}' → Googleスプレッドシートで数値変換された可能性あり")
        # 復元を試みる
        try:
            num = int(float(raw))
            raw = str(num)
            warnings.append(f"  → '{num}' に復元を試行")
        except (ValueError, OverflowError):
            warnings.append(f"  → 復元不可。手動確認が必要")
            return raw, warnings

    normalized = normalize_phone(raw)

    # 桁数チェック（日本の電話番号: 10〜11桁）
    digits_only = re.sub(r'\D', '', normalized)
    if digits_only and (len(digits_only) < 10 or len(digits_only) > 11):
        warnings.append(f"桁数異常: '{normalized}' ({len(digits_only)}桁) → 10〜11桁が正常")

    # 先頭が0でない場合（国際番号変換後）
    if digits_only and not digits_only.startswith('0'):
        warnings.append(f"先頭が0でない: '{normalized}' → 国番号変換漏れの可能性")

    return normalized, warnings


# ─── メール類似検知 ────────────────────────────────────

def levenshtein_distance(s1, s2):
    """2つの文字列のレーベンシュタイン距離を計算"""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    prev_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            # 挿入・削除・置換のコスト
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def find_similar_emails(new_email, existing_emails, threshold=2):
    """類似メールアドレスを検出する

    Args:
        new_email: 新しいメールアドレス
        existing_emails: 既存メールアドレスのセットまたはリスト
        threshold: レーベンシュタイン距離の閾値（デフォルト2）

    Returns:
        [(existing_email, distance), ...] 類似メールのリスト
    """
    new_lower = new_email.strip().lower()
    similar = []

    # ドメイン部分が同じものだけ比較（パフォーマンス最適化）
    new_local, new_domain = new_lower.split("@", 1) if "@" in new_lower else (new_lower, "")

    for existing in existing_emails:
        existing_lower = existing.strip().lower()
        if new_lower == existing_lower:
            continue  # 完全一致はスキップ

        ex_local, ex_domain = existing_lower.split("@", 1) if "@" in existing_lower else (existing_lower, "")

        # 同じドメインのメールのみ比較
        if new_domain and ex_domain and new_domain == ex_domain:
            dist = levenshtein_distance(new_local, ex_local)
            if dist <= threshold:
                similar.append((existing, dist))

    return sorted(similar, key=lambda x: x[1])


# ─── メールアドレスのバリデーション・正規化 ─────────────

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')


def is_valid_email(email):
    """メールアドレスが有効な形式かチェック"""
    return bool(_EMAIL_RE.match(email.strip())) if email else False


def clean_email(raw):
    """メールアドレスセルをクリーンアップ。有効なメールのみカンマ区切りで返す"""
    if not raw or not raw.strip():
        return ""
    s = raw.strip()
    # 全角→半角
    s = s.replace('＠', '@').replace('．', '.').replace('，', ',')
    s = s.replace('mailto:', '')
    s = s.rstrip("'").rstrip('"')
    # @前後のスペース除去
    s = re.sub(r'\s*@\s*', '@', s)
    # 区切り文字を統一
    s = s.replace('　', ',').replace('\n', ',')
    s = re.sub(r'(\.[a-zA-Z]{2,})\s+([a-zA-Z0-9])', r'\1,\2', s)
    # 括弧内のコメント除去
    s = re.sub(r'[（(][^）)]*[）)]', '', s)
    # 有効なメールのみ抽出
    parts = [p.strip() for p in s.split(',') if p.strip()]
    valid = [p for p in parts if _EMAIL_RE.match(p)]
    return ', '.join(valid)


# ─── ユーティリティ ───────────────────────────────────

def normalize_phone(phone):
    """電話番号を正規化（ハイフン除去、+81→0変換、先頭0補完）"""
    if not phone:
        return ""
    phone = re.sub(r'[\s\-\(\)]', '', phone)
    if phone.startswith('+81'):
        phone = '0' + phone[3:]
    # 10桁で先頭が0でない → 先頭0が欠落している可能性が高い
    digits_only = re.sub(r'\D', '', phone)
    if len(digits_only) == 10 and not digits_only.startswith('0'):
        phone = '0' + digits_only
    return phone


def normalize_amount(amount_str):
    """金額を正規化（¥ + 3桁カンマ区切り）"""
    if not amount_str:
        return ""
    # 既に ¥ 付きならそのまま
    if amount_str.startswith("¥"):
        return amount_str
    # 数値のみ抽出
    digits = re.sub(r'[^\d]', '', amount_str)
    if not digits:
        return amount_str
    return f"¥{int(digits):,}"


def normalize_date(date_str):
    """日付をYYYY/MM/DD形式に正規化"""
    if not date_str:
        return ""
    # 既にYYYY/MM/DD形式ならそのまま
    if re.match(r'^\d{4}/\d{2}/\d{2}$', date_str):
        return date_str
    # YYYY-MM-DD → YYYY/MM/DD
    m = re.match(r'^(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
    if m:
        return f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"
    return date_str


def normalize_zipcode(zipcode):
    """郵便番号を正規化（ハイフンあり 3桁-4桁）"""
    if not zipcode:
        return ""
    digits = re.sub(r'\D', '', zipcode)
    if len(digits) == 7:
        return f"{digits[:3]}-{digits[3:]}"
    return zipcode


def calculate_age(birth_date_str):
    """生年月日から今日時点の年齢を計算する

    Args:
        birth_date_str: "YYYY/MM/DD" or "YYYY-MM-DD" 形式

    Returns:
        年齢（int）。パース不可なら None
    """
    if not birth_date_str:
        return None
    # YYYY/MM/DD or YYYY-MM-DD
    m = re.match(r'^(\d{4})[/-](\d{1,2})[/-](\d{1,2})', birth_date_str.strip())
    if not m:
        return None
    try:
        from datetime import date
        birth = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        today = date.today()
        age = today.year - birth.year
        if (today.month, today.day) < (birth.month, birth.day):
            age -= 1
        return age if age >= 0 else None
    except ValueError:
        return None


def resolve_age(birth_date_str, survey_age_str):
    """年齢を解決する（生年月日優先、なければアンケート年代）

    優先順位:
      1. 生年月日がある → 正確な年齢を計算（例: "35"）
      2. 生年月日がない → アンケートの年代をそのまま使用（例: "30代"）

    Args:
        birth_date_str: 生年月日（"YYYY/MM/DD" 等）
        survey_age_str: アンケート回答の年代（"30代" 等）

    Returns:
        年齢の文字列（"35" or "30代"）。どちらもなければ ""
    """
    age = calculate_age(birth_date_str)
    if age is not None:
        return str(age)
    if survey_age_str and survey_age_str.strip():
        return survey_age_str.strip()
    return ""


def _col_to_letter(col_num):
    """1ベースの列番号をExcel形式の列文字に変換（1→A, 26→Z, 27→AA, ...）"""
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + col_num % 26) + result
        col_num //= 26
    return result


# ─── メインクラス ─────────────────────────────────────

class CDPSync:
    def __init__(self, account="kohara"):
        self.client = get_client(account)
        self.ss = self.client.open_by_key(CDP_SHEET_ID)
        self._exclusion_list = None
        self._exclusion_emails = set()
        self._exclusion_phones = set()
        self._master_headers = None
        self._master_data = None
        self.logger = SyncLogger()
        self.sync_state = SyncState()

    # ─── 除外リスト ─────────────────────────────────────

    def load_exclusion_list(self):
        """除外リストを読み込む（メール・電話番号）"""
        ws = self.ss.worksheet("除外リスト")
        data = ws.get_all_values()
        # ヘッダー: メールアドレス / 電話番号 / 対象者名 / 除外理由 / 追加日
        self._exclusion_emails = set()
        self._exclusion_phones = set()
        for row in data[1:]:
            if len(row) > 0 and row[0].strip():
                self._exclusion_emails.add(row[0].strip().lower())
            if len(row) > 1 and row[1].strip():
                self._exclusion_phones.add(normalize_phone(row[1].strip()))
        print(f"除外リスト: メール{len(self._exclusion_emails)}件, "
              f"電話{len(self._exclusion_phones)}件")
        self._exclusion_list = self._exclusion_emails  # 後方互換
        return self._exclusion_emails

    def is_excluded(self, email=None, phone=None):
        """メール・電話番号のいずれかが除外リストに含まれるか"""
        if self._exclusion_list is None:
            self.load_exclusion_list()
        if email and email.strip().lower() in self._exclusion_emails:
            return True
        if phone and normalize_phone(phone.strip()) in self._exclusion_phones:
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
        """メールアドレスでインデックスを構築（名寄せ用）
        カンマ区切りの複数メールにも対応（各メールを個別にインデックス）
        """
        if self._master_data is None:
            self.load_master()
        email_idx = self.get_col_index("メールアドレス")
        if email_idx is None:
            return {}
        index = {}
        for i, row in enumerate(self._master_data):
            if email_idx < len(row) and row[email_idx].strip():
                for email in row[email_idx].split(","):
                    email = email.strip().lower()
                    if email and is_valid_email(email):
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

    # ─── データソース管理の読み込み ─────────────────────

    def load_source_mappings(self):
        """データソース管理タブからカラムマッピングを読み込む

        Returns:
            [{
                "cdp_column": CDPカラム名,
                "group": グループ名,
                "source": ソース元,
                "priority": 優先度(int),
                "url": スプレッドシートURL,
                "tab": タブ名,
                "ref_column": 参照先列名,
                "normalize": 正規化ルール,
            }, ...]
        """
        ws = self.ss.worksheet("データソース管理")
        data = ws.get_all_values()
        if len(data) < 2:
            return []

        mappings = []
        for row in data[1:]:  # 行2以降がデータ（行1:カラム名）
            if len(row) < 7 or not row[0].strip():
                continue
            # URL が空のものはスキップ（同期対象外）
            if not row[4].strip():
                continue
            priority = 1
            try:
                priority = int(row[3]) if row[3].strip() else 1
            except ValueError:
                priority = 1

            mappings.append({
                "cdp_column": row[0].strip(),
                "group": row[1].strip() if len(row) > 1 else "",
                "source": row[2].strip() if len(row) > 2 else "",
                "priority": priority,
                "url": row[4].strip(),
                "tab": row[5].strip() if len(row) > 5 else "",
                "ref_column": row[6].strip() if len(row) > 6 else "",
                "normalize": row[7].strip() if len(row) > 7 else "",
            })

        print(f"データソース管理: {len(mappings)}件のマッピング")
        return mappings

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

    # ─── 同期（本実装） ────────────────────────────────

    def sync(self, source_url, tab_name, column_mapping, email_col,
             phone_col=None, dry_run=False, incremental=True):
        """ソースシートからCDP顧客マスタにデータを同期する

        Args:
            source_url: ソースシートのURL
            tab_name: ソースのタブ名
            column_mapping: {CDPカラム名: ソースカラム名} のマッピング
            email_col: ソース側のメールアドレスカラム名
            phone_col: ソース側の電話番号カラム名（あれば）
            dry_run: Trueなら書き込みしない
            incremental: Trueなら増分同期（前回同期以降の差分のみ）
        """
        self.load_exclusion_list()
        self.load_master()
        email_index = self.build_email_index()
        phone_index = self.build_phone_index()

        source_headers, source_rows = self.read_source(source_url, tab_name)

        # ソースのカラムインデックス
        src_email_idx = source_headers.index(email_col) if email_col in source_headers else None
        src_phone_idx = source_headers.index(phone_col) if phone_col and phone_col in source_headers else None

        if src_email_idx is None:
            print(f"エラー: ソースにメールカラム '{email_col}' が見つかりません")
            return None

        # ソースカラムのマッピングインデックス
        src_col_indices = {}
        for cdp_col, src_col in column_mapping.items():
            if src_col in source_headers:
                src_col_indices[cdp_col] = source_headers.index(src_col)

        # カンマ区切りで追記するカラム（複数回の値を蓄積）
        append_columns = {"セミナー予約日", "個別予約日", "個別着座日"}

        # 日付信頼性フィルター: 個別予約日は2025/7/30以降のみ取り込む
        reservation_date_cutoff = datetime(2025, 7, 30)
        reservation_src_idx = src_col_indices.get("個別予約日")

        # 増分同期: 前回同期以降の行数差分のみ処理
        source_key = f"{source_url}#{tab_name}"
        start_row = 0
        if incremental:
            last_state = self.sync_state.get_last_sync(source_key)
            if last_state and last_state.get("last_row_count", 0) > 0:
                start_row = last_state["last_row_count"]
                if start_row >= len(source_rows):
                    print(f"増分同期: 新しい行なし（前回: {start_row}行）")
                    return {"total": 0, "skipped": len(source_rows)}
                print(f"増分同期: 行{start_row + 1}〜{len(source_rows)}を処理")

        # 既存メールアドレスの一覧（類似検知用）
        all_existing_emails = set(email_index.keys())
        email_warnings = []

        stats = {
            "total": len(source_rows) - start_row,
            "excluded": 0,
            "updated": 0,
            "inserted": 0,
            "no_key": 0,
            "phone_warnings": 0,
            "email_warnings": 0,
        }

        ws = self.ss.worksheet("顧客マスタ") if not dry_run else None

        # ソースの行数に合わせてグリッドを事前拡張
        if not dry_run:
            current_rows = ws.row_count
            needed_rows = len(self._master_data) + 2 + len(source_rows)
            if needed_rows > current_rows:
                add = needed_rows - current_rows + 500
                ws.add_rows(add)
                print(f"グリッド拡張: {current_rows} → {current_rows + add}行")
        updates = []  # バッチ更新用（既存行の変更）
        new_rows = []  # バッチ追加用（新規顧客）

        for row_idx in range(start_row, len(source_rows)):
            row = source_rows[row_idx]
            raw_email = row[src_email_idx].strip() if src_email_idx < len(row) else ""
            email = clean_email(raw_email)  # バリデーション + 正規化
            email_lower = email.lower() if email else ""
            phone = row[src_phone_idx].strip() if src_phone_idx and src_phone_idx < len(row) else ""

            # 除外チェック
            if self.is_excluded(email, phone):
                stats["excluded"] += 1
                self.logger.log("skip", email or phone, "", "", "", "除外リスト")
                continue

            # 電話番号バリデーション
            if phone:
                normalized_phone, phone_warns = validate_phone(phone)
                if phone_warns:
                    stats["phone_warnings"] += 1
                    for w in phone_warns:
                        print(f"  ⚠ 電話番号: {w}")
                    self.logger.log("warning", email or phone, "電話番号",
                                    phone, normalized_phone, "バリデーション")
                phone = normalized_phone

            # メール類似検知（大量同期時はスキップ: O(n²)で遅いため）
            if email and email_lower not in email_index and len(all_existing_emails) < 1000:
                similar = find_similar_emails(email, all_existing_emails)
                if similar:
                    stats["email_warnings"] += 1
                    for sim_email, dist in similar:
                        print(f"  ⚠ メール類似: '{email}' ≈ '{sim_email}' (距離: {dist})")
                        email_warnings.append({
                            "new_email": email,
                            "similar_to": sim_email,
                            "distance": dist,
                            "timestamp": datetime.now().isoformat(),
                        })
                    self.logger.log("warning", email, "メールアドレス",
                                    "", email, f"類似検知: {similar[0][0]}")

            # 名寄せ（メール → 電話番号の順）
            master_row_idx = None
            if email_lower and email_lower in email_index:
                master_row_idx = email_index[email_lower]
            elif phone:
                norm_phone = normalize_phone(phone)
                if norm_phone in phone_index:
                    master_row_idx = phone_index[norm_phone]

            if master_row_idx is not None:
                # 既存顧客 → 更新
                # 電話番号で名寄せされた場合、新しいメールを追記
                if email and email_lower not in email_index:
                    email_cidx = self.get_col_index("メールアドレス")
                    if email_cidx is not None:
                        existing_email = ""
                        if email_cidx < len(self._master_data[master_row_idx]):
                            existing_email = self._master_data[master_row_idx][email_cidx]
                        existing_set = {e.strip().lower() for e in existing_email.split(",") if e.strip()}
                        if email_lower not in existing_set:
                            new_email = f"{existing_email}, {email}" if existing_email else email
                            self._master_data[master_row_idx][email_cidx] = new_email
                            email_index[email_lower] = master_row_idx
                            all_existing_emails.add(email_lower)
                            if not dry_run:
                                sheet_row = master_row_idx + 3
                                col_letter = _col_to_letter(email_cidx + 1)
                                updates.append({
                                    "range": f"{col_letter}{sheet_row}",
                                    "values": [[new_email]],
                                })
                            self.logger.log("update", email, "メールアドレス",
                                            existing_email, new_email,
                                            f"{source_url}#{tab_name}")

                updated_any = False
                for cdp_col, src_idx in src_col_indices.items():
                    if src_idx >= len(row):
                        continue
                    new_val = row[src_idx].strip()
                    if not new_val:
                        continue
                    # メールアドレスは上のロジックで処理済み
                    if cdp_col == "メールアドレス":
                        continue

                    # 個別予約日は2025/7/30以前のデータをスキップ
                    if cdp_col == "個別予約日" and reservation_src_idx is not None:
                        try:
                            date_str = new_val.split(" ")[0]  # "2025/01/01 0:00:00" → "2025/01/01"
                            m = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', date_str)
                            if m:
                                d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
                                if d < reservation_date_cutoff:
                                    continue  # 2025/7/30以前はスキップ
                        except (ValueError, IndexError):
                            pass

                    cdp_idx = self.get_col_index(cdp_col)
                    if cdp_idx is None:
                        continue

                    old_val = ""
                    if cdp_idx < len(self._master_data[master_row_idx]):
                        old_val = self._master_data[master_row_idx][cdp_idx]

                    # カンマ区切り追記カラム: 既存値に追記（重複チェック付き）
                    if cdp_col in append_columns:
                        if old_val:
                            # 日付部分のみ抽出して比較（時刻部分を除去）
                            normalized_new = normalize_date(new_val.split(" ")[0])
                            existing_dates = {normalize_date(d.strip().split(" ")[0])
                                              for d in old_val.split(",")}
                            if normalized_new in existing_dates:
                                continue  # 重複はスキップ
                            new_val = f"{old_val}, {normalized_new}"
                        else:
                            new_val = normalize_date(new_val.split(" ")[0])

                    # 値が同じなら更新しない
                    elif old_val == new_val:
                        continue

                    # 空→値: 無条件で記録
                    # 値→値: 最終更新日が新しい方を採用（ソースが最新と見なす）
                    self.logger.log("update", email or phone, cdp_col,
                                    old_val, new_val,
                                    f"{source_url}#{tab_name}")

                    if not dry_run:
                        # シートの行番号 = master_row_idx + 3（行1:グループ, 行2:カラム, 行3〜:データ）
                        sheet_row = master_row_idx + 3
                        col_letter = _col_to_letter(cdp_idx + 1)
                        updates.append({
                            "range": f"{col_letter}{sheet_row}",
                            "values": [[new_val]],
                        })
                    updated_any = True

                if updated_any:
                    stats["updated"] += 1
            elif email or phone:
                # 新規顧客 → 追加
                stats["inserted"] += 1
                self.logger.log("insert", email or phone, "",
                                "", "", f"{source_url}#{tab_name}")

                # 新規行を構築（ドライラン含む。インメモリのインデックスは常に更新）
                new_row = [""] * len(self._master_headers)
                cid_idx = self.get_col_index("顧客ID")
                if cid_idx is not None:
                    new_row[cid_idx] = str(len(self._master_data) + 1)

                create_idx = self.get_col_index("作成日")
                if create_idx is not None:
                    new_row[create_idx] = datetime.now().strftime("%Y/%m/%d")

                email_cidx = self.get_col_index("メールアドレス")
                if email_cidx is not None and email:
                    new_row[email_cidx] = email

                phone_cidx = self.get_col_index("電話番号")
                if phone_cidx is not None and phone:
                    new_row[phone_cidx] = phone

                for cdp_col, src_idx in src_col_indices.items():
                    if src_idx < len(row) and row[src_idx].strip():
                        val = row[src_idx].strip()
                        if cdp_col in append_columns:
                            val = normalize_date(val.split(" ")[0])
                        if cdp_col == "個別予約日":
                            try:
                                m2 = re.match(r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', val)
                                if m2:
                                    d = datetime(int(m2.group(1)), int(m2.group(2)), int(m2.group(3)))
                                    if d < reservation_date_cutoff:
                                        continue
                            except (ValueError, IndexError):
                                pass
                        cdp_idx = self.get_col_index(cdp_col)
                        if cdp_idx is not None:
                            new_row[cdp_idx] = val

                if not dry_run:
                    new_rows.append(new_row)

                # インメモリのインデックス更新（名寄せ用。ドライランでも更新）
                self._master_data.append(new_row)
                if email_lower:
                    email_index[email_lower] = len(self._master_data) - 1
                    all_existing_emails.add(email_lower)
                if phone:
                    phone_index[normalize_phone(phone)] = len(self._master_data) - 1
            else:
                stats["no_key"] += 1

        # バッチ書き込み実行
        if not dry_run:
            import time
            # 既存行の更新（チャンク分割: 500件ずつ）
            if updates:
                CHUNK = 500
                for i in range(0, len(updates), CHUNK):
                    chunk = updates[i:i + CHUNK]
                    ws.batch_update(chunk, value_input_option="USER_ENTERED")
                    if i + CHUNK < len(updates):
                        time.sleep(1)  # API制限回避
                print(f"既存行の更新: {len(updates)}セル書き込み完了")

            # 新規行の追加（update()で範囲指定書き込み。グリッド膨張を防止）
            if new_rows:
                # 書き込み開始行 = ヘッダー2行 + 既存データ行数 + 1
                # ※ self._master_data には今回追加分も含まれている
                existing_before = len(self._master_data) - len(new_rows)
                start_row = existing_before + 3  # 行1:グループ, 行2:カラム
                # グリッドが足りなければ拡張
                needed = start_row + len(new_rows)
                if needed > ws.row_count:
                    ws.add_rows(needed - ws.row_count + 100)
                    print(f"  グリッド拡張 → {ws.row_count}行")
                CHUNK = 500
                last_col = _col_to_letter(len(self._master_headers))
                for i in range(0, len(new_rows), CHUNK):
                    chunk = new_rows[i:i + CHUNK]
                    r1 = start_row + i
                    r2 = r1 + len(chunk) - 1
                    ws.update(range_name=f"A{r1}:{last_col}{r2}",
                              values=chunk,
                              value_input_option="USER_ENTERED")
                    print(f"  新規追加: {i + len(chunk)}/{len(new_rows)}行")
                    if i + CHUNK < len(new_rows):
                        time.sleep(1)
                print(f"新規行の追加: {len(new_rows)}行書き込み完了")

        # 増分同期の状態を保存（ドライランでは保存しない）
        if not dry_run:
            self.sync_state.update(source_key, len(source_rows))
            self.sync_state.save()

        # 変更ログ保存
        self.logger.save()

        # メール類似警告の保存
        if email_warnings:
            _save_email_warnings(email_warnings)

        # 結果表示
        mode = "ドライラン" if dry_run else "同期完了"
        print(f"\n=== {mode} ===")
        print(f"処理対象: {stats['total']}件")
        print(f"除外: {stats['excluded']}件")
        print(f"更新: {stats['updated']}件")
        print(f"新規追加: {stats['inserted']}件")
        print(f"キーなし: {stats['no_key']}件")
        if stats["phone_warnings"]:
            print(f"電話番号警告: {stats['phone_warnings']}件")
        if stats["email_warnings"]:
            print(f"メール類似警告: {stats['email_warnings']}件 → {SIMILARITY_LOG_PATH}")

        return stats

    # ─── データソース管理ステータス更新 ─────────────────

    def update_source_status(self, source_row_idx, status, update_count=0,
                             error_count=0):
        """データソース管理のステータス・同期日・更新数・エラー数を更新

        Args:
            source_row_idx: データソース管理の行インデックス（0始まり、データ行のみ）
            status: "正常" / "更新なし" / "停止"
            update_count: 更新件数
            error_count: エラー件数
        """
        ws = self.ss.worksheet("データソース管理")
        sheet_row = source_row_idx + 2  # 行1:カラム名

        now = datetime.now().strftime("%Y/%m/%d")
        # I列:ステータス, J列:最終同期日, K列:更新数, L列:エラー数
        ws.update(f"I{sheet_row}:L{sheet_row}",
                  [[status, now, update_count, error_count]],
                  value_input_option="USER_ENTERED")

    # ─── ドライラン（旧互換） ──────────────────────────

    def dry_run(self, source_url, tab_name, column_mapping, email_col):
        """ドライラン: 取り込み結果をシミュレーション"""
        return self.sync(source_url, tab_name, column_mapping, email_col,
                         dry_run=True, incremental=False)

    # ─── 自動同期 ──────────────────────────────────────

    def auto_sync(self, dry_run=False, incremental=True):
        """データソース管理のマッピングを読み取り、全ソースを自動同期する

        Args:
            dry_run: Trueなら書き込みしない
            incremental: Trueなら増分同期
        """
        mappings = self.load_source_mappings()
        if not mappings:
            print("同期対象のマッピングがありません")
            return

        # ソース（URL+タブ）でグルーピング
        sources = {}
        for m in mappings:
            key = f"{m['url']}#{m['tab']}"
            if key not in sources:
                sources[key] = {
                    "url": m["url"],
                    "tab": m["tab"],
                    "column_mapping": {},
                    "source_name": m["source"],
                }
            sources[key]["column_mapping"][m["cdp_column"]] = m["ref_column"]

        print(f"\n自動同期: {len(sources)}ソースを処理")

        total_stats = {
            "sources": len(sources),
            "updated": 0,
            "inserted": 0,
            "excluded": 0,
            "errors": 0,
        }

        for key, src in sources.items():
            print(f"\n--- {src['source_name']}: {src['tab']} ---")
            try:
                # メールアドレス列を特定（マッピングから探す）
                email_col = src["column_mapping"].get("メールアドレス", "")
                phone_col = src["column_mapping"].get("電話番号", "")

                if not email_col:
                    print(f"  スキップ: メールアドレスのマッピングがありません")
                    continue

                stats = self.sync(
                    src["url"], src["tab"], src["column_mapping"],
                    email_col, phone_col=phone_col,
                    dry_run=dry_run, incremental=incremental,
                )

                if stats:
                    total_stats["updated"] += stats.get("updated", 0)
                    total_stats["inserted"] += stats.get("inserted", 0)
                    total_stats["excluded"] += stats.get("excluded", 0)

            except Exception as e:
                total_stats["errors"] += 1
                print(f"  エラー: {e}")
                self.logger.log("error", key, "", "", str(e), src["source_name"])

        print(f"\n=== 自動同期{'（ドライラン）' if dry_run else ''}完了 ===")
        print(f"ソース数: {total_stats['sources']}")
        print(f"更新: {total_stats['updated']}件")
        print(f"新規: {total_stats['inserted']}件")
        print(f"除外: {total_stats['excluded']}件")
        if total_stats["errors"]:
            print(f"エラー: {total_stats['errors']}件")

        self.logger.save()
        return total_stats

    # ─── 行数自動拡張チェック ──────────────────────────

    def ensure_capacity(self, min_empty_rows=100):
        """顧客マスタの行数が足りなければ自動拡張する"""
        ws = self.ss.worksheet("顧客マスタ")
        current_rows = ws.row_count
        data_rows = len(self._master_data) if self._master_data else 0
        # ヘッダー2行 + データ行
        used_rows = data_rows + 2
        empty_rows = current_rows - used_rows

        if empty_rows < min_empty_rows:
            add_rows = min_empty_rows - empty_rows + 500  # 余裕を持って追加
            ws.add_rows(add_rows)
            print(f"行数拡張: {current_rows} → {current_rows + add_rows}行 "
                  f"（空き行: {empty_rows} → {empty_rows + add_rows}）")


# ─── メール類似警告の保存 ─────────────────────────────

def _save_email_warnings(warnings):
    """メール類似警告をファイルに保存（追記）"""
    path = Path(SIMILARITY_LOG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = []
    if path.exists():
        try:
            existing = json.loads(path.read_text())
        except (json.JSONDecodeError, IOError):
            existing = []
    existing.extend(warnings)
    # 最新1000件のみ保持
    if len(existing) > 1000:
        existing = existing[-1000:]
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2))


# ─── CLI ─────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("""
CDP同期スクリプト

使い方:
  python3 cdp_sync.py sync              全ソース自動同期
  python3 cdp_sync.py sync --dry-run    全ソース自動同期（ドライラン）
  python3 cdp_sync.py sync --full       全ソース全件同期（増分なし）
  python3 cdp_sync.py dry-run <ソースURL> <タブ名> <メールカラム名>
  python3 cdp_sync.py exclusion-list
  python3 cdp_sync.py status
  python3 cdp_sync.py check-phones      電話番号のバリデーションチェック

例:
  python3 cdp_sync.py sync --dry-run
  python3 cdp_sync.py dry-run "https://docs.google.com/.../edit" "友だちリスト" "メールアドレス"
""")
        return

    cmd = sys.argv[1]
    sync = CDPSync()

    if cmd == "sync":
        dry_run = "--dry-run" in sys.argv
        incremental = "--full" not in sys.argv
        lock = SyncLock()
        try:
            with lock:
                sync.load_master()
                sync.ensure_capacity()
                sync.auto_sync(dry_run=dry_run, incremental=incremental)
        except RuntimeError as e:
            print(f"エラー: {e}")
            sys.exit(1)

    elif cmd == "dry-run":
        if len(sys.argv) < 5:
            print("エラー: ソースURL, タブ名, メールカラム名を指定してください")
            return
        source_url = sys.argv[2]
        tab_name = sys.argv[3]
        email_col = sys.argv[4]
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

        # 増分同期の状態表示
        state = SyncState()
        if state._state:
            print(f"\n同期状態:")
            for key, val in state._state.items():
                print(f"  {key}: 最終同期 {val.get('last_sync', '未')}, "
                      f"行数 {val.get('last_row_count', 0)}")

    elif cmd == "check-phones":
        sync.load_master()
        phone_idx = sync.get_col_index("電話番号")
        if phone_idx is None:
            print("電話番号カラムが見つかりません")
            return
        warn_count = 0
        for i, row in enumerate(sync._master_data):
            if phone_idx < len(row) and row[phone_idx].strip():
                _, warns = validate_phone(row[phone_idx])
                if warns:
                    warn_count += 1
                    print(f"  行{i + 3}: {row[phone_idx]}")
                    for w in warns:
                        print(f"    ⚠ {w}")
        print(f"\n電話番号チェック完了: {warn_count}件の警告")

    else:
        print(f"不明なコマンド: {cmd}")


if __name__ == "__main__":
    main()
