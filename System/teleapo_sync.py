#!/usr/bin/env python3
"""
AIテレアポ管理シート同期

顧客マスタを正本として読み取り、AIテレアポ管理シートの `架電一覧` を
最新条件に合わせて更新する。運用状態は管理シート側で完結させ、
CDP には書き込まない。

Usage:
    python3 System/teleapo_sync.py sync
    python3 System/teleapo_sync.py sync --dry-run
"""

from __future__ import annotations

import re
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", message="urllib3 v2 only supports OpenSSL 1.1.1+")

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from gspread.exceptions import WorksheetNotFound
from urllib3.exceptions import NotOpenSSLWarning

from sheets_manager import ACCOUNTS, SCOPES, get_client


warnings.filterwarnings("ignore", category=NotOpenSSLWarning)


CDP_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
CDP_TAB_NAME = "顧客マスタ"
TELEAPO_SHEET_ID = "12RGMUfU8Wj0CCdcRfY7kI56kdATV7wDXjvYmGdQb_Nk"
TARGET_TAB_NAME = "架電一覧"
LEGACY_TARGET_TAB_NAMES = ["架電対象"]
HISTORY_TAB_NAME = "架電履歴"
SCORE_TAB_NAME = "架電成績"
MONITOR_TAB_NAME = "運用チェック"
RULE_TAB_NAME = "抽出条件・優先順位"
PROTECTION_DESCRIPTION_PREFIX = "teleapo_sync_protection"

TARGET_HEADERS = [
    "顧客ID",
    "電話番号",
    "メールアドレス",
    "氏名",
    "優先順位帯",
    "運用ステータス",
    "初回流入経路",
    "購入商品",
    "最新架電結果",
    "個別予約日",
]

TARGET_STATE_HEADERS = ["運用ステータス", "最新架電結果"]
HISTORY_HEADERS = ["顧客ID", "架電日", "架電結果", "未予約理由"]
DEFAULT_STATUS = "未着手"
STATUS_OPTIONS = ["未着手", "予約完了", "対応完了", "対象外"]
RESULT_OPTIONS = ["応答あり", "留守電", "応答なし", "拒否", "番号不備", "対象外"]
WRITE_CHUNK_SIZE = 1000
MIN_EMPTY_ROWS = 200
RETRY_DELAYS = [2, 5, 10]
MIN_EXPECTED_TARGET_ROWS = 1000
DROP_GUARD_RATIO = 0.5

STUDENT_FLAG_FIELDS = [
    "入会日",
    "プラン",
    "講義保管庫ID",
    "クーリングオフ日",
    "中途解約日",
]

STUDENT_PRODUCT_MARKERS = [
    "スキルプラス",
    "skillplus",
    "spスタンダード",
    "spプライム",
    "spスタンダード商品",
    "スキルプラススタンダードプラン",
    "スキルプラスプライムプラン",
    "スキルプラス ライトプラン",
    "【スキルプラス】",
]

DEZAJUKU_MARKERS = [
    "デザジュク",
    "デザ塾",
]

EXCLUDED_PRODUCT_MARKERS = [
    "デザイン限界突破3日間合宿",
    "コンドウハルキ秘密の部屋",
]

PAID_ROUTE_PREFIXES = [
    "meta広告",
    "tiktok広告",
    "youtube広告",
    "x広告",
    "リスティング広告",
    "アフィリエイト広告",
    "google広告",
]

PRIORITY_ORDER = {
    "P1": 1,
    "P2": 2,
    "P3": 3,
    "P4": 4,
    "P5": 5,
    "P6": 6,
    "P7": 7,
    "P8": 8,
    "P9": 9,
}

RECENCY_BUCKET_ORDER = {
    "0-60日": 0,
    "61-180日": 1,
    "181-365日": 2,
    "366日以上": 3,
    "日付不明": 4,
}

RULE_SHEET_ROWS = [
    ["AIテレアポ管理 要件整理", "", "", ""],
    ["区分", "項目", "内容", "補足"],
    ["最終挙動", "データ正本", "顧客マスタを読み取り専用で使う", "顧客マスタへは書き込まない"],
    ["最終挙動", "同期先", "AIテレアポ管理シートの `架電一覧` を更新する", "`顧客ID` で状態を引き継ぐ"],
    ["最終挙動", "同期タイミング", "毎朝 06:15 に最新対象へ更新する", "Google API の一時エラーはリトライする"],
    ["最終挙動", "一覧の考え方", "`架電一覧` は 1顧客 1行で残し、予約完了や対象外も `運用ステータス` で管理する", "件数急減時は更新を止めて前回一覧を保護する"],
    ["テレアポ対象", "母集団", "`個別予約合計 = 0` かつ `電話番号あり`", "この2条件を満たす人だけを抽出する"],
    ["テレアポ対象", "必須キー", "`顧客ID` がある人", "`顧客ID` が空欄の行は一覧に載せない"],
    ["テレアポ対象", "氏名", "`姓 + 名` を基本にし、欠けるときだけ `LINE名` を使う", "架電時の本人確認に使う"],
    ["テレアポ対象", "対象外_デザジュク", "`初回流入経路` または `初回購入商品` / `最新購入商品` / `購入商品` に `デザジュク` または `デザ塾` を含む人", "スキルプラス販売対象外として一覧に載せない"],
    ["テレアポ対象", "対象外_既存商品", "`初回購入商品` / `最新購入商品` / `購入商品` に `デザイン限界突破3日間合宿` / `コンドウハルキ秘密の部屋` を含む人", "既存オファー購入者として一覧に載せない"],
    ["テレアポ対象", "受講生判定", "`入会日` / `プラン` / `講義保管庫ID` / `クーリングオフ日` / `中途解約日` / 明示的なスキルプラス商品", "受講生判定に入る人は販売対象外として除外する"],
    ["優先順位", "P1", "購入2回以上 × 流入あり_その他", "最優先"],
    ["優先順位", "P2", "購入2回以上 × 広告流入", "主戦場"],
    ["優先順位", "P3", "購入1回 × 流入あり_その他", "次点"],
    ["優先順位", "P4", "購入1回 × 広告流入", "主戦場"],
    ["優先順位", "P5", "未購入 × 広告流入", "購入者の後"],
    ["優先順位", "P6", "未購入 × 流入あり_その他", "P5 の後"],
    ["優先順位", "P7", "購入2回以上 × 流入空欄", "後回し"],
    ["優先順位", "P8", "購入1回 × 流入空欄", "後回し"],
    ["優先順位", "P9", "未購入 × 流入空欄", "最後"],
    ["優先順位", "時間軸", "同一優先帯の中では `初回流入日` を使い `0-60日 -> 61-180日 -> 181-365日 -> 366日以上 -> 日付不明` の順で並べる", "`優先順位帯` は `P1_0-60日` のように base priority と時間帯を合わせて表示する"],
    ["運用ステータス", "未着手", "まだ架電運用として何も処理していない", "`架電成績` の `架電対象数` に含める"],
    ["運用ステータス", "予約完了", "`個別予約日` が入った人", "架電していないまま予約完了になることもある"],
    ["運用ステータス", "対応完了", "架電運用として追わない状態", "電話の結果に関係なく運用を閉じた状態"],
    ["運用ステータス", "対象外", "電話対象から外す状態", "受講生判定、番号不備、除外判断など"],
    ["架電成績", "架電対象数", "`運用ステータス = 未着手` の人数", "今から架電する対象数"],
    ["架電成績", "対応完了", "`運用ステータス = 対応完了` の人数", "架電件数ではなく顧客数で見る"],
    ["架電成績", "予約完了", "`運用ステータス = 予約完了` の人数", "架電なしで予約完了した人も含む"],
    ["架電成績", "予約完了（架電あり）", "`予約完了` かつ `架電履歴` が1件以上ある人数", "架電起点の予約完了を追う補助指標"],
    ["架電結果", "応答あり", "相手が電話に出た", "会話内容の成否は含めない"],
    ["架電結果", "留守電", "留守番電話につながった", "メッセージ残しの有無は別管理"],
    ["架電結果", "応答なし", "呼び出したが出なかった", "不在、呼出のみなど"],
    ["架電結果", "拒否", "相手に拒否された、または相手側で切られた", "以後の架電停止判断に使う"],
    ["架電結果", "番号不備", "欠番、桁不備、利用停止など", "通常は `対象外` へ移す"],
    ["架電結果", "対象外", "電話前に対象外と判断した", "履歴上の例外記録用"],
    ["AI更新ルール", "架電前", "AIは `運用ステータス = 未着手` を優先して読む", "今は `再架電待ち` を持たない"],
    ["AI更新ルール", "架電後_一覧更新", "`運用ステータス` / `最新架電結果` を更新する", "`最新架電結果` は電話の事実だけを記録する"],
    ["AI更新ルール", "架電後_履歴追加", "`架電履歴` に `顧客ID` / `架電日` / `架電結果` / `未予約理由` を1行追加する", "1通話 = 1行で残す"],
    ["AI更新ルール", "予約時", "`個別予約日` に日付が入った人は `予約完了` に更新する", "`顧客マスタ` は読取専用"],
    ["運用ガード", "手入力可列", "`架電一覧` では `運用ステータス` / `最新架電結果` だけを運用で触る", "それ以外の列は同期で上書きされる前提"],
    ["運用ガード", "保護", "`架電成績` / `運用チェック` / `抽出条件・優先順位` と `架電一覧` の同期列は warning-only 保護", "誤編集時に警告を出す"],
    ["運用ガード", "エラー検知", "`運用チェック` で同期鮮度と不整合件数を確認する", "`同期鮮度 = 要確認` または件数 > 0 のとき確認する"],
    ["森本さん確認事項", "送信チャネル", "`メール` / `LINE` / `両方` のどれにするか", "AIがどのチャネルを使うか決める"],
    ["森本さん確認事項", "送信タイミング", "`架電前` / `架電直後` / 条件次第 のどれにするか", "通話中の案内とセットで決める"],
    ["森本さん確認事項", "送信システム", "どのシステムから誰名義で送るか", "AI完結のための実装前提"],
    ["森本さん確認事項", "導線成功の定義", "`予約リンク送信` / `リンククリック` / `予約フォーム到達` のどこで見るか", "個別予約完了とは別に管理するか決める"],
]


def build_score_sheet_rows() -> list[list[str]]:
    return [
        ["架電成績", ""],
        ["項目", "総数"],
        ["更新日時", '=TEXT(NOW(),"yyyy/mm/dd hh:mm")'],
        ["架電対象数", f"=COUNTIFS('{TARGET_TAB_NAME}'!A2:A,"<>",'{TARGET_TAB_NAME}'!F2:F,"未着手")"],
        ["対応完了", f"=COUNTIFS('{TARGET_TAB_NAME}'!A2:A,"<>",'{TARGET_TAB_NAME}'!F2:F,"対応完了")"],
        ["応答あり", f"=COUNTIF('{HISTORY_TAB_NAME}'!C2:C,"応答あり")"],
        ["留守電", f"=COUNTIF('{HISTORY_TAB_NAME}'!C2:C,"留守電")"],
        ["応答なし", f"=COUNTIF('{HISTORY_TAB_NAME}'!C2:C,"応答なし")"],
        ["拒否", f"=COUNTIF('{HISTORY_TAB_NAME}'!C2:C,"拒否")"],
        ["番号不備", f"=COUNTIF('{HISTORY_TAB_NAME}'!C2:C,"番号不備")"],
        ["予約完了", f"=COUNTIFS('{TARGET_TAB_NAME}'!A2:A,"<>",'{TARGET_TAB_NAME}'!F2:F,"予約完了")"],
        [
            "予約完了（架電あり）",
            f"=SUMPRODUCT(N(COUNTIF(IFERROR(UNIQUE(FILTER('{HISTORY_TAB_NAME}'!A2:A,'{HISTORY_TAB_NAME}'!A2:A<>"")),"__NO_HISTORY__"),IFERROR(FILTER('{TARGET_TAB_NAME}'!A2:A,'{TARGET_TAB_NAME}'!A2:A<>"",'{TARGET_TAB_NAME}'!F2:F="予約完了"),"__NO_BOOKING__"))>0))",
        ],
    ]


def build_monitor_sheet_rows(last_synced_at: str, previous_count: int, current_count: int) -> list[list[str]]:
    return [
        ["運用チェック", ""],
        ["項目", "状態"],
        ["最終同期成功日時", last_synced_at],
        ["同期鮮度", '=IF(B3="", "未同期", IF(NOW()-B3>1, "要確認", "正常"))'],
        ["前回同期件数", str(previous_count)],
        ["今回同期件数", str(current_count)],
        ["同期件数差分", "=B6-B5"],
        ["予約完了だが個別予約日なし", f"=COUNTIFS('{TARGET_TAB_NAME}'!A2:A,"<>",'{TARGET_TAB_NAME}'!F2:F,"予約完了",'{TARGET_TAB_NAME}'!J2:J,"")"],
        ["番号不備だが対象外でない", f"=COUNTIFS('{TARGET_TAB_NAME}'!A2:A,"<>",'{TARGET_TAB_NAME}'!I2:I,"番号不備",'{TARGET_TAB_NAME}'!F2:F,"<>対象外")"],
        ["架電履歴の顧客ID空欄", f"=IFERROR(ROWS(FILTER('{HISTORY_TAB_NAME}'!B2:B,'{HISTORY_TAB_NAME}'!B2:B<>"",'{HISTORY_TAB_NAME}'!A2:A="")),0)"],
        ["架電履歴の架電結果空欄", f"=IFERROR(ROWS(FILTER('{HISTORY_TAB_NAME}'!A2:A,'{HISTORY_TAB_NAME}'!A2:A<>"",'{HISTORY_TAB_NAME}'!C2:C="")),0)"],
    ]


def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    phone = re.sub(r"[\s\-\(\)]", "", str(phone))
    if phone.startswith("+81"):
        phone = "0" + phone[3:]
    digits_only = re.sub(r"\D", "", phone)
    if len(digits_only) == 10 and not digits_only.startswith("0"):
        phone = "0" + digits_only
    return phone


def normalize_route_name(route_name: str) -> str:
    if not route_name:
        return ""
    parts = [part.strip() for part in str(route_name).strip().split("_") if part.strip()]
    if len(parts) <= 2:
        return "_".join(parts)
    return "_".join(parts[:2])


def parse_int(value: str) -> int:
    raw = re.sub(r"[^\d\-]", "", str(value or ""))
    if not raw:
        return 0
    try:
        return int(raw)
    except ValueError:
        return 0


def parse_date(value: str) -> date | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.split(" ")[0]
    for separator in ("/", "-"):
        parts = raw.split(separator)
        if len(parts) != 3:
            continue
        try:
            year, month, day = map(int, parts)
            return date(year, month, day)
        except ValueError:
            continue
    return None


def format_priority_label(base_priority: str, recency_bucket: str) -> str:
    return f"{base_priority}_{recency_bucket}"


def now_jst_text() -> str:
    return datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y/%m/%d %H:%M")


def build_contact_name(last_name: str, first_name: str, line_name: str) -> str:
    last_name = (last_name or "").strip()
    first_name = (first_name or "").strip()
    if last_name and first_name:
        return f"{last_name} {first_name}"
    if last_name or first_name:
        return last_name or first_name
    return (line_name or "").strip()


def ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return start_a < end_b and start_b < end_a


def col_to_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num -= 1
        result = chr(65 + col_num % 26) + result
        col_num //= 26
    return result


@dataclass
class SyncStats:
    scanned: int = 0
    eligible: int = 0
    skipped_no_customer_id: int = 0
    skipped_no_phone: int = 0
    skipped_has_booking: int = 0
    skipped_dezajuku: int = 0
    skipped_excluded_product: int = 0
    skipped_student: int = 0
    reused_state: int = 0


class TeleapoSync:
    def __init__(self, account: str = "kohara"):
        token_path = Path(ACCOUNTS[account])
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
        if not creds.valid and creds.expired and creds.refresh_token:
            creds.refresh(Request())

        self.client = get_client(account)
        self.auth = creds
        self.sheets_service = build("sheets", "v4", credentials=self.auth)
        self.cdp_ss = self.client.open_by_key(CDP_SHEET_ID)
        self.teleapo_ss = self.client.open_by_key(TELEAPO_SHEET_ID)
        self._headers: list[str] | None = None
        self._rows: list[list[str]] | None = None

    def get_target_worksheet(self):
        try:
            return self.teleapo_ss.worksheet(TARGET_TAB_NAME)
        except WorksheetNotFound:
            for legacy_name in LEGACY_TARGET_TAB_NAMES:
                try:
                    ws = self.teleapo_ss.worksheet(legacy_name)
                except WorksheetNotFound:
                    continue
                self.call_with_retries(
                    "架電一覧タブ名更新",
                    lambda ws=ws: ws.update_title(TARGET_TAB_NAME),
                )
                return self.teleapo_ss.worksheet(TARGET_TAB_NAME)
        raise WorksheetNotFound(TARGET_TAB_NAME)

    def get_or_create_score_worksheet(self):
        try:
            return self.teleapo_ss.worksheet(SCORE_TAB_NAME)
        except WorksheetNotFound:
            ws = self.call_with_retries(
                "架電成績タブ作成",
                lambda: self.teleapo_ss.add_worksheet(title=SCORE_TAB_NAME, rows=20, cols=2),
            )
            self.call_with_retries(
                "架電成績タブ順序更新",
                lambda: self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=TELEAPO_SHEET_ID,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {"sheetId": ws.id, "index": 2},
                                    "fields": "index",
                                }
                            }
                        ]
                    },
                ).execute(),
            )
            return ws

    def get_or_create_monitor_worksheet(self):
        try:
            return self.teleapo_ss.worksheet(MONITOR_TAB_NAME)
        except WorksheetNotFound:
            ws = self.call_with_retries(
                "運用チェックタブ作成",
                lambda: self.teleapo_ss.add_worksheet(title=MONITOR_TAB_NAME, rows=20, cols=2),
            )
            self.call_with_retries(
                "運用チェックタブ順序更新",
                lambda: self.sheets_service.spreadsheets().batchUpdate(
                    spreadsheetId=TELEAPO_SHEET_ID,
                    body={
                        "requests": [
                            {
                                "updateSheetProperties": {
                                    "properties": {"sheetId": ws.id, "index": 3},
                                    "fields": "index",
                                }
                            }
                        ]
                    },
                ).execute(),
            )
            return ws

    def call_with_retries(self, label: str, func):
        last_error = None
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                return func()
            except Exception as exc:
                last_error = exc
                if attempt >= len(RETRY_DELAYS):
                    break
                time.sleep(RETRY_DELAYS[attempt])
        raise RuntimeError(f"{label} に失敗しました: {last_error}") from last_error

    def load_cdp_rows(self) -> tuple[list[str], list[list[str]]]:
        ws = self.cdp_ss.worksheet(CDP_TAB_NAME)
        data = self.call_with_retries("顧客マスタの読み込み", ws.get_all_values)
        self._headers = data[1] if len(data) > 1 else []
        self._rows = data[2:] if len(data) > 2 else []
        return self._headers, self._rows

    def get_col_index(self, column_name: str) -> int:
        if self._headers is None:
            self.load_cdp_rows()
        assert self._headers is not None
        return self._headers.index(column_name)

    def cell(self, row: list[str], column_name: str) -> str:
        idx = self.get_col_index(column_name)
        return row[idx].strip() if idx < len(row) else ""

    def has_booking(self, row: list[str]) -> bool:
        return parse_int(self.cell(row, "個別予約合計")) > 0 or bool(self.cell(row, "個別予約日"))

    def has_phone(self, row: list[str]) -> bool:
        return bool(normalize_phone(self.cell(row, "電話番号")))

    def normalize_status(self, status: str) -> str:
        normalized = (status or "").strip()
        if normalized in STATUS_OPTIONS:
            return normalized
        return DEFAULT_STATUS

    def is_skillplus_student(self, row: list[str]) -> bool:
        if any(self.cell(row, field) for field in STUDENT_FLAG_FIELDS):
            return True

        product_text = " | ".join(
            filter(
                None,
                [
                    self.cell(row, "初回購入商品"),
                    self.cell(row, "最新購入商品"),
                    self.cell(row, "購入商品"),
                ],
            )
        ).lower()
        return any(marker.lower() in product_text for marker in STUDENT_PRODUCT_MARKERS)

    def is_dezajuku_related(self, row: list[str]) -> bool:
        target_text = " | ".join(
            filter(
                None,
                [
                    self.cell(row, "初回流入経路"),
                    self.cell(row, "初回購入商品"),
                    self.cell(row, "最新購入商品"),
                    self.cell(row, "購入商品"),
                ],
            )
        ).lower()
        return any(marker.lower() in target_text for marker in DEZAJUKU_MARKERS)

    def has_excluded_product(self, row: list[str]) -> bool:
        product_text = " | ".join(
            filter(
                None,
                [
                    self.cell(row, "初回購入商品"),
                    self.cell(row, "最新購入商品"),
                    self.cell(row, "購入商品"),
                ],
            )
        ).lower()
        return any(marker.lower() in product_text for marker in EXCLUDED_PRODUCT_MARKERS)

    def classify_route_bucket(self, route_name: str) -> str:
        route = normalize_route_name(route_name).lower()
        if not route:
            return "blank"
        if any(route.startswith(prefix) for prefix in PAID_ROUTE_PREFIXES):
            return "paid"
        return "other"

    def build_priority_tier(self, row: list[str]) -> str:
        purchase_count = parse_int(self.cell(row, "累計購入回数"))
        route_bucket = self.classify_route_bucket(self.cell(row, "初回流入経路"))

        if purchase_count >= 2 and route_bucket == "other":
            return "P1"
        if purchase_count >= 2 and route_bucket == "paid":
            return "P2"
        if purchase_count == 1 and route_bucket == "other":
            return "P3"
        if purchase_count == 1 and route_bucket == "paid":
            return "P4"
        if purchase_count == 0 and route_bucket == "paid":
            return "P5"
        if purchase_count == 0 and route_bucket == "other":
            return "P6"
        if purchase_count >= 2 and route_bucket == "blank":
            return "P7"
        if purchase_count == 1 and route_bucket == "blank":
            return "P8"
        return "P9"

    def build_status_sort_key(self, status: str) -> tuple[int, str]:
        normalized = (status or DEFAULT_STATUS).strip() or DEFAULT_STATUS
        if normalized == "未着手":
            return (0, "")
        if normalized == "予約完了":
            return (1, "")
        if normalized == "対応完了":
            return (2, "")
        if normalized == "対象外":
            return (3, "")
        return (4, normalized)

    def build_recency_sort_key(self, row: list[str]) -> tuple[int, int]:
        bucket, days_since_first_flow = self.build_recency_bucket(row)
        return (RECENCY_BUCKET_ORDER[bucket], days_since_first_flow)

    def build_recency_bucket(self, row: list[str]) -> tuple[str, int]:
        first_flow_date = parse_date(self.cell(row, "初回流入日"))
        if first_flow_date is None:
            return ("日付不明", 999999)

        days_since_first_flow = max((date.today() - first_flow_date).days, 0)
        if days_since_first_flow <= 60:
            return ("0-60日", days_since_first_flow)
        if days_since_first_flow <= 180:
            return ("61-180日", days_since_first_flow)
        if days_since_first_flow <= 365:
            return ("181-365日", days_since_first_flow)
        return ("366日以上", days_since_first_flow)

    def load_existing_target_state(self) -> tuple[dict[str, dict[str, str]], int]:
        ws = self.get_target_worksheet()
        values = self.call_with_retries("架電一覧の既存状態読み込み", ws.get_all_values)
        if not values:
            return {}, 0

        headers = values[0]
        header_map = {header: idx for idx, header in enumerate(headers)}
        states: dict[str, dict[str, str]] = {}
        for row in values[1:]:
            customer_id = row[header_map["顧客ID"]].strip() if header_map.get("顧客ID") is not None and header_map["顧客ID"] < len(row) else ""
            if not customer_id:
                continue
            states[customer_id] = {}
            for field in TARGET_STATE_HEADERS:
                idx = header_map.get(field)
                states[customer_id][field] = row[idx].strip() if idx is not None and idx < len(row) else ""
        return states, max(len(values) - 1, 0)

    def ensure_target_headers(self) -> None:
        ws = self.get_target_worksheet()
        current = self.call_with_retries("架電一覧ヘッダー読み込み", lambda: ws.row_values(1))
        if current[: len(TARGET_HEADERS)] != TARGET_HEADERS:
            end_col = col_to_letter(len(TARGET_HEADERS))
            self.call_with_retries(
                "架電一覧ヘッダー更新",
                lambda: ws.update(
                    range_name=f"A1:{end_col}1",
                    values=[TARGET_HEADERS],
                    value_input_option="USER_ENTERED",
                ),
            )

    def ensure_history_headers(self) -> None:
        ws = self.teleapo_ss.worksheet(HISTORY_TAB_NAME)
        if ws.col_count != len(HISTORY_HEADERS):
            ws.resize(rows=max(ws.row_count, 2000), cols=len(HISTORY_HEADERS))
        current = self.call_with_retries("架電履歴ヘッダー読み込み", lambda: ws.row_values(1))
        if current[: len(HISTORY_HEADERS)] != HISTORY_HEADERS:
            end_col = col_to_letter(len(HISTORY_HEADERS))
            self.call_with_retries(
                "架電履歴ヘッダー更新",
                lambda: ws.update(
                    range_name=f"A1:{end_col}1",
                    values=[HISTORY_HEADERS],
                    value_input_option="USER_ENTERED",
                ),
            )

    def ensure_target_capacity(self, required_data_rows: int) -> int:
        ws = self.get_target_worksheet()
        required_total_rows = max(required_data_rows + 1 + MIN_EMPTY_ROWS, 2000)
        if ws.row_count != required_total_rows or ws.col_count != len(TARGET_HEADERS):
            ws.resize(rows=required_total_rows, cols=len(TARGET_HEADERS))
        return required_total_rows

    def set_dropdown_validation(self, sheet_id: int, start_row: int, end_row: int, start_col: int, options: list[str]) -> dict:
        return {
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": start_row,
                    "endRowIndex": end_row,
                    "startColumnIndex": start_col,
                    "endColumnIndex": start_col + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": option} for option in options],
                    },
                    "showCustomUi": True,
                    "strict": True,
                },
            }
        }

    def ensure_target_validations(self, row_count: int) -> None:
        ws = self.get_target_worksheet()
        requests = [
            self.set_dropdown_validation(ws.id, 1, row_count, 5, STATUS_OPTIONS),
            self.set_dropdown_validation(ws.id, 1, row_count, 8, RESULT_OPTIONS),
        ]
        self.call_with_retries(
            "架電一覧プルダウン設定",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def ensure_history_validations(self) -> None:
        ws = self.teleapo_ss.worksheet(HISTORY_TAB_NAME)
        requests = [
            self.set_dropdown_validation(ws.id, 1, ws.row_count, 2, RESULT_OPTIONS),
        ]
        self.call_with_retries(
            "架電履歴プルダウン設定",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def ensure_target_filter(self, row_count: int) -> None:
        ws = self.get_target_worksheet()
        self.call_with_retries(
            "架電一覧フィルター設定",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={
                    "requests": [
                        {
                            "setBasicFilter": {
                                "filter": {
                                    "range": {
                                        "sheetId": ws.id,
                                        "startRowIndex": 0,
                                        "endRowIndex": row_count,
                                        "startColumnIndex": 0,
                                        "endColumnIndex": len(TARGET_HEADERS),
                                    }
                                }
                            }
                        }
                    ]
                },
            ).execute(),
        )

    def ensure_target_text_columns(self, row_count: int) -> None:
        ws = self.get_target_worksheet()
        requests = []
        for col in [0, 1, 2]:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 1,
                            "endRowIndex": row_count,
                            "startColumnIndex": col,
                            "endColumnIndex": col + 1,
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

        self.call_with_retries(
            "架電一覧のテキスト列設定",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def add_warning_only_protection(
        self,
        requests: list[dict],
        *,
        sheet_id: int,
        start_row: int,
        end_row: int,
        start_col: int,
        end_col: int,
        description: str,
    ) -> None:
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": start_row,
                            "endRowIndex": end_row,
                            "startColumnIndex": start_col,
                            "endColumnIndex": end_col,
                        },
                        "description": f"{PROTECTION_DESCRIPTION_PREFIX}:{description}",
                        "warningOnly": True,
                    }
                }
            }
        )

    def sync_warning_only_protections(self, target_row_count: int) -> None:
        metadata = self.call_with_retries(
            "保護範囲メタ情報取得",
            self.teleapo_ss.fetch_sheet_metadata,
        )
        target_ws = self.get_target_worksheet()
        history_ws = self.teleapo_ss.worksheet(HISTORY_TAB_NAME)
        score_ws = self.get_or_create_score_worksheet()
        monitor_ws = self.get_or_create_monitor_worksheet()
        rule_ws = self.teleapo_ss.worksheet(RULE_TAB_NAME)
        requests: list[dict] = []

        for sheet in metadata.get("sheets", []):
            for protected_range in sheet.get("protectedRanges", []):
                description = protected_range.get("description", "")
                if not description.startswith(PROTECTION_DESCRIPTION_PREFIX):
                    continue
                requests.append(
                    {
                        "deleteProtectedRange": {
                            "protectedRangeId": protected_range["protectedRangeId"],
                        }
                    }
                )

        self.add_warning_only_protection(
            requests,
            sheet_id=target_ws.id,
            start_row=0,
            end_row=1,
            start_col=0,
            end_col=len(TARGET_HEADERS),
            description="架電一覧_ヘッダー",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=target_ws.id,
            start_row=1,
            end_row=target_row_count,
            start_col=0,
            end_col=5,
            description="架電一覧_同期列_前半",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=target_ws.id,
            start_row=1,
            end_row=target_row_count,
            start_col=6,
            end_col=8,
            description="架電一覧_同期列_後半",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=target_ws.id,
            start_row=1,
            end_row=target_row_count,
            start_col=9,
            end_col=10,
            description="架電一覧_予約日",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=history_ws.id,
            start_row=0,
            end_row=1,
            start_col=0,
            end_col=len(HISTORY_HEADERS),
            description="架電履歴_ヘッダー",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=score_ws.id,
            start_row=0,
            end_row=len(build_score_sheet_rows()),
            start_col=0,
            end_col=2,
            description="架電成績",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=monitor_ws.id,
            start_row=0,
            end_row=len(build_monitor_sheet_rows(now_jst_text(), 0, 0)),
            start_col=0,
            end_col=2,
            description="運用チェック",
        )
        self.add_warning_only_protection(
            requests,
            sheet_id=rule_ws.id,
            start_row=0,
            end_row=len(RULE_SHEET_ROWS),
            start_col=0,
            end_col=4,
            description="抽出条件_優先順位",
        )

        self.call_with_retries(
            "warning-only 保護設定",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def sync_rule_sheet(self) -> None:
        ws = self.teleapo_ss.worksheet(RULE_TAB_NAME)
        end_row = len(RULE_SHEET_ROWS)
        self.call_with_retries(
            "抽出条件タブのサイズ調整",
            lambda: ws.resize(rows=end_row, cols=4),
        )
        self.call_with_retries(
            "抽出条件タブクリア",
            lambda: ws.batch_clear(["A1:D100"]),
        )
        self.call_with_retries(
            "抽出条件タブ更新",
            lambda: ws.update(
                range_name=f"A1:D{end_row}",
                values=RULE_SHEET_ROWS,
                value_input_option="USER_ENTERED",
            ),
        )
        self.format_rule_sheet(end_row)

    def format_rule_sheet(self, row_count: int) -> None:
        ws = self.teleapo_ss.worksheet(RULE_TAB_NAME)
        metadata = self.call_with_retries(
            "抽出条件タブのメタ情報取得",
            self.teleapo_ss.fetch_sheet_metadata,
        )
        target_merges = [
            {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 4},
            {"sheetId": ws.id, "startRowIndex": 2, "endRowIndex": 6, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 6, "endRowIndex": 12, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 12, "endRowIndex": 22, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 22, "endRowIndex": 26, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 26, "endRowIndex": 30, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 30, "endRowIndex": 36, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 36, "endRowIndex": 40, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 40, "endRowIndex": 43, "startColumnIndex": 0, "endColumnIndex": 1},
            {"sheetId": ws.id, "startRowIndex": 43, "endRowIndex": 47, "startColumnIndex": 0, "endColumnIndex": 1},
        ]
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 2},
                        "index": 4,
                    },
                    "fields": "gridProperties.frozenRowCount,index",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                            "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.32, "blue": 0.6},
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 14,
                            },
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.94, "blue": 0.99},
                            "textFormat": {
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 12,
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 2,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.96, "green": 0.98, "blue": 1.0},
                            "textFormat": {"bold": True},
                            "horizontalAlignment": "CENTER",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            },
            {
                "updateBorders": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 4,
                    },
                    "top": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "bottom": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "left": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "right": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "innerHorizontal": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                    "innerVertical": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                }
            },
        ]

        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != ws.id:
                continue
            for merge in sheet.get("merges", []):
                if not ranges_overlap(merge.get("startRowIndex", 0), merge.get("endRowIndex", 0), 0, row_count):
                    continue
                if not ranges_overlap(merge.get("startColumnIndex", 0), merge.get("endColumnIndex", 0), 0, 4):
                    continue
                requests.append({"unmergeCells": {"range": merge}})
            break

        for merge in target_merges:
            requests.append({"mergeCells": {"range": merge, "mergeType": "MERGE_ALL"}})

        column_widths = [140, 160, 520, 240]
        for idx, width in enumerate(column_widths):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        self.call_with_retries(
            "抽出条件タブの体裁調整",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def sync_score_sheet(self) -> None:
        ws = self.get_or_create_score_worksheet()
        rows = build_score_sheet_rows()
        row_count = len(rows)

        self.call_with_retries(
            "架電成績タブ更新",
            lambda: ws.resize(rows=row_count, cols=2),
        )
        self.call_with_retries(
            "架電成績タブ書き込み",
            lambda: ws.update(
                range_name=f"A1:B{row_count}",
                values=rows,
                value_input_option="USER_ENTERED",
            ),
        )

        metadata = self.call_with_retries(
            "架電成績タブのメタ情報取得",
            self.teleapo_ss.fetch_sheet_metadata,
        )
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 2},
                        "index": 2,
                    },
                    "fields": "gridProperties.frozenRowCount,index",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                            "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.32, "blue": 0.6},
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 14,
                            },
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.94, "blue": 0.99},
                            "textFormat": {
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 12,
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 2,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.96, "green": 0.98, "blue": 1.0},
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 2,
                        "endRowIndex": row_count,
                        "startColumnIndex": 1,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "horizontalAlignment": "RIGHT",
                        }
                    },
                    "fields": "userEnteredFormat.horizontalAlignment",
                }
            },
            {
                "updateBorders": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "top": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "bottom": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "left": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "right": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "innerHorizontal": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                    "innerVertical": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                }
            },
        ]

        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != ws.id:
                continue
            for merge in sheet.get("merges", []):
                if not ranges_overlap(merge.get("startRowIndex", 0), merge.get("endRowIndex", 0), 0, row_count):
                    continue
                if not ranges_overlap(merge.get("startColumnIndex", 0), merge.get("endColumnIndex", 0), 0, 2):
                    continue
                requests.append({"unmergeCells": {"range": merge}})
            break

        requests.append(
            {
                "mergeCells": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "mergeType": "MERGE_ALL",
                }
            }
        )

        for idx, width in enumerate([180, 180]):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        self.call_with_retries(
            "架電成績タブの体裁調整",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def sync_monitor_sheet(self, previous_count: int, current_count: int) -> None:
        ws = self.get_or_create_monitor_worksheet()
        rows = build_monitor_sheet_rows(now_jst_text(), previous_count, current_count)
        row_count = len(rows)

        self.call_with_retries(
            "運用チェックタブ更新",
            lambda: ws.resize(rows=row_count, cols=2),
        )
        self.call_with_retries(
            "運用チェックタブ書き込み",
            lambda: ws.update(
                range_name=f"A1:B{row_count}",
                values=rows,
                value_input_option="USER_ENTERED",
            ),
        )

        metadata = self.call_with_retries(
            "運用チェックタブのメタ情報取得",
            self.teleapo_ss.fetch_sheet_metadata,
        )
        requests = [
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": ws.id,
                        "gridProperties": {"frozenRowCount": 2},
                        "index": 3,
                    },
                    "fields": "gridProperties.frozenRowCount,index",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 1, "green": 1, "blue": 1},
                            "textFormat": {"fontFamily": "Arial", "fontSize": 10},
                            "verticalAlignment": "MIDDLE",
                            "wrapStrategy": "WRAP",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,verticalAlignment,wrapStrategy)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.32, "blue": 0.6},
                            "textFormat": {
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 14,
                            },
                            "horizontalAlignment": "LEFT",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": 2,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.9, "green": 0.94, "blue": 0.99},
                            "textFormat": {
                                "bold": True,
                                "fontFamily": "Arial",
                                "fontSize": 12,
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment)",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 2,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.96, "green": 0.98, "blue": 1.0},
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            },
            {
                "updateBorders": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "top": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "bottom": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "left": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "right": {"style": "SOLID", "color": {"red": 0.82, "green": 0.86, "blue": 0.92}},
                    "innerHorizontal": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                    "innerVertical": {"style": "SOLID", "color": {"red": 0.88, "green": 0.9, "blue": 0.94}},
                }
            },
        ]

        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != ws.id:
                continue
            for merge in sheet.get("merges", []):
                if not ranges_overlap(merge.get("startRowIndex", 0), merge.get("endRowIndex", 0), 0, row_count):
                    continue
                if not ranges_overlap(merge.get("startColumnIndex", 0), merge.get("endColumnIndex", 0), 0, 2):
                    continue
                requests.append({"unmergeCells": {"range": merge}})
            break

        requests.append(
            {
                "mergeCells": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 2,
                    },
                    "mergeType": "MERGE_ALL",
                }
            }
        )

        for idx, width in enumerate([220, 220]):
            requests.append(
                {
                    "updateDimensionProperties": {
                        "range": {
                            "sheetId": ws.id,
                            "dimension": "COLUMNS",
                            "startIndex": idx,
                            "endIndex": idx + 1,
                        },
                        "properties": {"pixelSize": width},
                        "fields": "pixelSize",
                    }
                }
            )

        self.call_with_retries(
            "運用チェックタブの体裁調整",
            lambda: self.sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=TELEAPO_SHEET_ID,
                body={"requests": requests},
            ).execute(),
        )

    def build_target_rows(self, existing_state: dict[str, dict[str, str]]) -> tuple[list[list[str]], SyncStats]:
        if self._rows is None:
            self.load_cdp_rows()
        assert self._rows is not None

        stats = SyncStats()
        targets: list[tuple[tuple[object, ...], list[str]]] = []

        for row in self._rows:
            stats.scanned += 1

            customer_id = self.cell(row, "顧客ID")
            if not customer_id:
                stats.skipped_no_customer_id += 1
                continue
            state = existing_state.get(customer_id, {})
            if state:
                stats.reused_state += 1

            has_booking = self.has_booking(row)
            phone = normalize_phone(self.cell(row, "電話番号"))
            is_dezajuku = self.is_dezajuku_related(row)
            has_excluded_product = self.has_excluded_product(row)
            is_student = self.is_skillplus_student(row)
            current_status = self.normalize_status(state.get("運用ステータス", ""))

            if is_dezajuku:
                stats.skipped_dezajuku += 1
                continue

            if has_excluded_product:
                stats.skipped_excluded_product += 1
                continue

            if not state and has_booking:
                stats.skipped_has_booking += 1
                continue

            if not state and not phone:
                stats.skipped_no_phone += 1
                continue

            if not state and is_student:
                stats.skipped_student += 1
                continue

            base_priority = self.build_priority_tier(row)
            recency_bucket, _ = self.build_recency_bucket(row)
            priority = format_priority_label(base_priority, recency_bucket)
            route = normalize_route_name(self.cell(row, "初回流入経路"))
            latest_result = state.get("最新架電結果", "")

            if has_booking:
                status = "予約完了"
            elif state and (is_student or not phone):
                status = "対象外"
            elif current_status == "予約完了":
                status = "対応完了" if latest_result else DEFAULT_STATUS
            else:
                status = current_status

            target_row = [
                customer_id,
                phone,
                self.cell(row, "メールアドレス"),
                build_contact_name(self.cell(row, "姓"), self.cell(row, "名"), self.cell(row, "LINE名")),
                priority,
                status,
                route,
                self.cell(row, "購入商品"),
                latest_result,
                self.cell(row, "個別予約日"),
            ]

            sort_key = (
                *self.build_status_sort_key(status),
                PRIORITY_ORDER[base_priority],
                *self.build_recency_sort_key(row),
                -parse_int(self.cell(row, "累計購入回数")),
                customer_id,
            )
            targets.append((sort_key, target_row))
            stats.eligible += 1

        targets.sort(key=lambda item: item[0])
        return [row for _, row in targets], stats

    def guard_target_count(self, new_count: int, previous_count: int, force: bool = False) -> None:
        if force or previous_count < MIN_EXPECTED_TARGET_ROWS:
            return
        if new_count == 0:
            raise RuntimeError("架電一覧が 0 件になったため同期を停止しました。前回一覧を保護します。")
        if new_count < int(previous_count * DROP_GUARD_RATIO):
            raise RuntimeError(
                f"架電一覧が急減しました: 前回 {previous_count} 件 -> 今回 {new_count} 件。前回一覧を保護するため同期を停止しました。"
            )

    def write_target_rows(self, rows: list[list[str]], previous_row_count: int) -> None:
        ws = self.get_target_worksheet()
        end_col = col_to_letter(len(TARGET_HEADERS))

        if rows:
            for start in range(0, len(rows), WRITE_CHUNK_SIZE):
                chunk = rows[start : start + WRITE_CHUNK_SIZE]
                row_start = start + 2
                row_end = row_start + len(chunk) - 1
                self.call_with_retries(
                    f"架電一覧書き込み {row_start}-{row_end}",
                    lambda row_start=row_start, row_end=row_end, chunk=chunk: ws.update(
                        range_name=f"A{row_start}:{end_col}{row_end}",
                        values=chunk,
                        value_input_option="USER_ENTERED",
                    ),
                )

        if previous_row_count > len(rows):
            self.call_with_retries(
                "架電一覧の余剰行クリア",
                lambda: ws.batch_clear([f"A{len(rows) + 2}:{end_col}{previous_row_count + 1}"]),
            )

    def sync(self, dry_run: bool = False, force: bool = False) -> SyncStats:
        self.load_cdp_rows()
        self.ensure_target_headers()
        self.ensure_history_headers()
        existing_state, previous_row_count = self.load_existing_target_state()
        target_rows, stats = self.build_target_rows(existing_state)

        if dry_run:
            self.print_summary(stats, target_rows, prefix="[ドライラン] ")
            return stats

        self.guard_target_count(len(target_rows), previous_row_count, force=force)
        row_count = self.ensure_target_capacity(len(target_rows))
        self.ensure_target_text_columns(row_count)
        self.write_target_rows(target_rows, previous_row_count)
        self.ensure_target_filter(row_count)
        self.ensure_target_validations(row_count)
        self.ensure_history_validations()
        self.sync_score_sheet()
        self.sync_monitor_sheet(previous_row_count, len(target_rows))
        self.sync_rule_sheet()
        self.sync_warning_only_protections(row_count)
        self.print_summary(stats, target_rows)
        return stats

    def print_summary(self, stats: SyncStats, target_rows: Iterable[list[str]], prefix: str = "") -> None:
        priority_counts: dict[str, int] = {key: 0 for key in PRIORITY_ORDER}
        for row in target_rows:
            priority = row[4].split("_", 1)[0]
            priority_counts[priority] = priority_counts.get(priority, 0) + 1

        print(f"{prefix}スキャン件数: {stats.scanned}")
        print(f"{prefix}架電一覧: {stats.eligible}")
        print(f"{prefix}除外_顧客IDなし: {stats.skipped_no_customer_id}")
        print(f"{prefix}除外_電話番号なし: {stats.skipped_no_phone}")
        print(f"{prefix}除外_個別予約あり: {stats.skipped_has_booking}")
        print(f"{prefix}除外_デザジュク: {stats.skipped_dezajuku}")
        print(f"{prefix}除外_既存商品: {stats.skipped_excluded_product}")
        print(f"{prefix}除外_受講生判定: {stats.skipped_student}")
        print(f"{prefix}既存状態引き継ぎ: {stats.reused_state}")
        for priority in sorted(PRIORITY_ORDER, key=PRIORITY_ORDER.get):
            print(f"{prefix}{priority}: {priority_counts.get(priority, 0)}")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"sync"}:
        print(
            """
AIテレアポ同期スクリプト

使い方:
  python3 System/teleapo_sync.py sync
  python3 System/teleapo_sync.py sync --dry-run
""".strip()
        )
        return

    dry_run = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    sync = TeleapoSync()
    sync.sync(dry_run=dry_run, force=force)


if __name__ == "__main__":
    main()
