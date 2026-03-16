#!/usr/bin/env python3
"""
CSV → Google Sheets 自動同期スクリプト

「Looker Studio CSV」フォルダ内のCSVファイルを検出し、
「元データ」シートのステータスを自動更新する。

動作:
  1. フォルダ内の日付付きCSVファイルをスキャン
  2. シートの「要エクスポート」行とマッチング
  3. マッチした行の投入日時・ステータスを「完了」に更新
  4. 日付不明のCSV（デフォルト名）を検出したらLINEで通知

使い方:
  python3 csv_sheet_sync.py              # 元データシート同期
  python3 csv_sheet_sync.py --dry-run    # 確認のみ（書き込みしない）
  python3 csv_sheet_sync.py build        # スキルプラス（日別）シートを全CSV から構築
  python3 csv_sheet_sync.py build --dry-run
  python3 csv_sheet_sync.py monthly      # スキルプラス（月別）シートを日別データから集計
  python3 csv_sheet_sync.py monthly --dry-run
  python3 csv_sheet_sync.py cache        # KPIキャッシュのみ再生成
"""

import os
import sys
import re
import csv
import json
import logging
import tempfile
import requests
from datetime import datetime, timedelta

# sheets_manager と同じディレクトリ
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
from sheets_manager import get_client, extract_spreadsheet_id

# ─── 設定 ──────────────────────────────────────────────────────
CSV_DIR = os.path.expanduser("~/Desktop/Looker Studio CSV")
SPREADSHEET_ID = "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit?gid=1948910703"
SHEET_NAME = "元データ"
DAILY_SHEET_NAME = "スキルプラス（日別）"
MONTHLY_SHEET_NAME = "スキルプラス（月別）"

# KPIサマリーキャッシュ
KPI_CACHE_PATH = os.path.join(BASE_DIR, "data", "kpi_summary.json")
ACCOUNT = "kohara"
BASE_CSV_NAME = "アドネス全体数値_媒体・ファネル別データ_表"

# LINE通知設定
CONFIG_PATH = os.path.join(BASE_DIR, "line_bot_local", "config.json")
SERVER_URL = "https://line-mention-bot-mmzu.onrender.com"
AGENT_TOKEN = ""
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH) as f:
        _cfg = json.load(f)
        AGENT_TOKEN = _cfg.get("agent_token", "")

# 通知済みファイルの記録（同じファイルを何度も通知しない）
NOTIFIED_FILE = os.path.join(BASE_DIR, "csv_sheet_sync_notified.json")

# ログ設定
LOG_FILE = os.path.join(BASE_DIR, "csv_sheet_sync.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# 日付付きファイル名パターン: 2025-07-01_アドネス全体数値_...csv
DATE_PATTERN = re.compile(r'^(\d{4}-\d{2}-\d{2})_(.+)\.csv$')


# ─── LINE通知 ─────────────────────────────────────────────────

def send_line_notify(message: str) -> bool:
    """LINE秘書グループに通知を送る"""
    if not AGENT_TOKEN:
        logger.warning("AGENT_TOKEN未設定: LINE通知をスキップ")
        return False
    try:
        resp = requests.post(
            f"{SERVER_URL}/notify",
            headers={"Authorization": f"Bearer {AGENT_TOKEN}"},
            json={"message": message},
            timeout=40,
        )
        if resp.status_code == 200:
            logger.info("LINE通知送信完了")
            return True
        else:
            logger.error(f"LINE通知失敗: {resp.status_code} {resp.text[:200]}")
            return False
    except Exception as e:
        logger.error(f"LINE通知エラー: {e}")
        return False


def load_notified():
    """通知済みファイルリストを読み込む"""
    if os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE) as f:
            return set(json.load(f))
    return set()


def save_notified(notified: set):
    """通知済みファイルリストを保存する"""
    with open(NOTIFIED_FILE, "w") as f:
        json.dump(sorted(notified), f, ensure_ascii=False)


# ─── スキャン ──────────────────────────────────────────────────

def scan_csv_folder():
    """フォルダ内の日付付きCSVファイルをスキャンして {日付: ファイル名} を返す"""
    if not os.path.isdir(CSV_DIR):
        logger.error(f"フォルダが存在しません: {CSV_DIR}")
        return {}, []

    import unicodedata
    dated_files = {}
    unnamed_files = []

    for f in os.listdir(CSV_DIR):
        f_nfc = unicodedata.normalize('NFC', f)
        if not f_nfc.endswith(".csv") or BASE_CSV_NAME not in f_nfc:
            continue

        m = DATE_PATTERN.match(f_nfc)
        if m:
            dated_files[m.group(1)] = f
        else:
            # デフォルト名（日付なし）のCSV
            unnamed_files.append(f)

    return dated_files, unnamed_files


def auto_rename_unnamed_files(unnamed_files: list, dated_files: dict, dry_run: bool = False) -> list:
    """日付不明のCSVファイルを自動リネームする。

    既存の日付付きCSVから最新日付を取得し、翌日以降を割り当てる。
    Returns: リネームしたファイル名のリスト
    """
    if not unnamed_files:
        return []

    # 既存の日付付きCSVから最新日付を特定
    if dated_files:
        latest_date = max(datetime.strptime(d, "%Y-%m-%d") for d in dated_files)
    else:
        # 日付付きCSVがない場合は昨日を基準にする
        latest_date = datetime.now() - timedelta(days=1)

    # ファイル更新日時順にソート（古い順）
    unnamed_with_mtime = []
    for f in unnamed_files:
        path = os.path.join(CSV_DIR, f)
        mtime = os.path.getmtime(path)
        unnamed_with_mtime.append((f, mtime))
    unnamed_with_mtime.sort(key=lambda x: x[1])

    renamed = []
    next_date = latest_date + timedelta(days=1)

    for fname, _ in unnamed_with_mtime:
        date_str = next_date.strftime("%Y-%m-%d")
        new_name = f"{date_str}_{fname}"
        old_path = os.path.join(CSV_DIR, fname)
        new_path = os.path.join(CSV_DIR, new_name)

        if dry_run:
            logger.info(f"(dry-run) リネーム予定: {fname} → {new_name}")
        else:
            os.rename(old_path, new_path)
            logger.info(f"自動リネーム: {fname} → {new_name}")
            renamed.append(new_name)

        next_date += timedelta(days=1)

    return renamed


# ─── シート同期 ────────────────────────────────────────────────

def sync_to_sheet(dry_run=False):
    """CSVファイルとシートを同期"""
    # 1. フォルダスキャン
    csv_files, unnamed_files = scan_csv_folder()

    # 日付不明ファイルを自動リネーム
    renamed = auto_rename_unnamed_files(unnamed_files, csv_files, dry_run=dry_run)

    # リネームがあった場合は再スキャン
    if renamed:
        csv_files, unnamed_files = scan_csv_folder()

    if not csv_files:
        logger.info("日付付きCSVファイルがありません")
        return 0

    logger.info(f"日付付きCSV: {len(csv_files)} ファイル")

    # 2. シート読み込み
    spreadsheet_id, gid = extract_spreadsheet_id(SPREADSHEET_URL)
    client = get_client(ACCOUNT)
    spreadsheet = client.open_by_key(spreadsheet_id)
    ws = next((w for w in spreadsheet.worksheets() if w.id == gid), None)
    if ws is None:
        ws = spreadsheet.worksheet(SHEET_NAME)

    data = ws.get_all_values()
    if not data:
        logger.error("シートが空です")
        return 0

    # 2.5. シートにない日付のCSVがあれば行を自動追加
    existing_dates = {row[0] for row in data[1:]}  # ヘッダー除く
    new_dates = sorted(d for d in csv_files if d not in existing_dates)

    if new_dates and not dry_run:
        new_rows = [
            [d, f"{BASE_CSV_NAME}.csv", "", "要エクスポート"]
            for d in new_dates
        ]
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        logger.info(f"元データに新規行追加: {len(new_dates)} 件 ({new_dates[0]} 〜 {new_dates[-1]})")
        # 追加後のデータを再読み込み
        data = ws.get_all_values()
    elif new_dates:
        logger.info(f"(dry-run) 元データに新規行追加予定: {len(new_dates)} 件 ({new_dates[0]} 〜 {new_dates[-1]})")

    # 3. 更新対象を特定
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    updates = []
    update_rows = []

    for i, row in enumerate(data[1:], start=2):  # skip header
        target_date = row[0]
        status = row[3] if len(row) > 3 else ""

        if status == "完了":
            continue  # 既に完了済みはスキップ

        if target_date in csv_files:
            filename = csv_files[target_date]
            updates.append({
                "row": i,
                "date": target_date,
                "filename": filename,
            })
            update_rows.append([filename, now, "完了"])

    if not updates:
        logger.info("更新対象なし（すべて完了済み or CSVなし）")
        return 0

    logger.info(f"更新対象: {len(updates)} 行")
    for u in updates[:5]:
        logger.info(f"  {u['date']} → {u['filename']}")
    if len(updates) > 5:
        logger.info(f"  ... 他 {len(updates) - 5} 行")

    if dry_run:
        logger.info("(dry-run: 書き込みスキップ)")
        return len(updates)

    # 4. 一括書き込み
    first_row = updates[0]["row"]
    last_row = updates[-1]["row"]

    if last_row - first_row + 1 == len(updates):
        # 連続行 → 一括更新
        range_notation = f"B{first_row}:D{last_row}"
        ws.update(values=update_rows, range_name=range_notation)
        logger.info(f"一括書き込み完了: {range_notation}")
    else:
        # 飛び飛び → 全行分のデータを作って一括更新
        all_rows = []
        update_map = {u["row"]: idx for idx, u in enumerate(updates)}
        for i, row in enumerate(data[1:], start=2):
            if i in update_map:
                all_rows.append(update_rows[update_map[i]])
            else:
                all_rows.append([row[1] if len(row) > 1 else "",
                                 row[2] if len(row) > 2 else "",
                                 row[3] if len(row) > 3 else ""])
        range_notation = f"B2:D{len(data)}"
        ws.update(values=all_rows, range_name=range_notation)
        logger.info(f"一括書き込み完了: {range_notation}")

    return len(updates)


# ─── スキルプラス（日別）構築 ──────────────────────────────────

def parse_number(val):
    """CSV の値を数値に変換。空文字・変換不可は 0"""
    if not val or val.strip() == "":
        return 0
    try:
        n = float(val)
        return int(n) if n == int(n) else round(n, 2)
    except (ValueError, OverflowError):
        return 0


def read_all_csvs():
    """全CSVを読み込み、日付付きの行リストを返す"""
    if not os.path.isdir(CSV_DIR):
        logger.error(f"フォルダが存在しません: {CSV_DIR}")
        return []

    import unicodedata
    all_rows = []
    files = sorted(f for f in os.listdir(CSV_DIR)
                   if DATE_PATTERN.match(unicodedata.normalize('NFC', f))
                   and BASE_CSV_NAME in unicodedata.normalize('NFC', f))

    for fname in files:
        date_str = DATE_PATTERN.match(fname).group(1)
        path = os.path.join(CSV_DIR, fname)
        with open(path, encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                continue
            for row in reader:
                if len(row) < 12:
                    continue
                # [日付, 大カテゴリ, 集客媒体, ファネル名,
                #  集客数, 個別予約数, 実施数, 売上, 広告費,
                #  CPA, 個別CPO, 単月ROAS, 単月LTV]
                all_rows.append([
                    date_str,
                    row[0],                # 大カテゴリ
                    row[1],                # 集客媒体
                    row[2],                # ファネル名
                    parse_number(row[3]),   # 集客数
                    parse_number(row[4]),   # 個別予約数
                    parse_number(row[5]),   # 実施数
                    parse_number(row[6]),   # 売上
                    parse_number(row[7]),   # 広告費
                    parse_number(row[8]),   # CPA
                    parse_number(row[9]),   # 個別CPO
                    parse_number(row[10]),  # 単月ROAS
                    parse_number(row[11]),  # 単月LTV
                ])

    logger.info(f"CSV読み込み: {len(files)} ファイル, {len(all_rows)} 行")
    return all_rows


def build_daily_sheet(dry_run=False):
    """全CSVデータを読み込み、スキルプラス（日別）シートに書き込む"""
    # 1. 全CSV読み込み
    all_rows = read_all_csvs()
    if not all_rows:
        logger.error("CSVデータがありません")
        return 0

    # 日付の範囲
    dates = sorted(set(r[0] for r in all_rows))
    logger.info(f"期間: {dates[0]} 〜 {dates[-1]} ({len(dates)} 日)")
    logger.info(f"合計: {len(all_rows)} 行")

    if dry_run:
        logger.info("(dry-run: 書き込みスキップ)")
        return len(all_rows)

    # 2. シートに接続
    client = get_client(ACCOUNT)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = spreadsheet.worksheet(DAILY_SHEET_NAME)

    # 3. シートをリサイズ（ヘッダー3行 + データ行 + 余裕100行）
    # レイアウト: 行1=最終更新, 行2=空, 行3=ヘッダー, 行4〜=データ
    needed_rows = 3 + len(all_rows) + 100
    current_rows = ws.row_count
    if needed_rows > current_rows:
        ws.resize(rows=needed_rows)
        logger.info(f"シートリサイズ: {current_rows} → {needed_rows} 行")

    # 4. 既存データをクリア（行1以降すべて）
    ws.batch_clear([f"A1:M{current_rows}"])
    logger.info("既存データクリア完了")

    # 5. データ書き込み（行4〜）
    BATCH_SIZE = 1000
    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i:i + BATCH_SIZE]
        start_row = 4 + i
        end_row = start_row + len(batch) - 1
        range_notation = f"A{start_row}:M{end_row}"
        ws.update(values=batch, range_name=range_notation, value_input_option="USER_ENTERED")
        logger.info(f"書き込み: {range_notation} ({len(batch)} 行)")

    # 6. 最終更新日を更新（行1）
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.update_acell("A1", f"最終更新: {now}")

    logger.info(f"スキルプラス（日別）構築完了: {len(all_rows)} 行")

    return len(all_rows)


# ─── スキルプラス（月別）構築 ──────────────────────────────────

def _format_month(month_key):
    """'2025-07' → '2025年7月'"""
    y, m = month_key.split("-")
    return f"{y}年{int(m)}月"


def _calc_kpi_row(month, media, funnel, 集客数, 予約数, 実施数, 売上, 広告費):
    """月別シートの1行データを計算して返す"""
    cpa = round(広告費 / 集客数) if 集客数 > 0 else 0
    cpo = round(広告費 / 予約数) if 予約数 > 0 else 0
    roas = round(売上 / 広告費 * 100, 1) if 広告費 > 0 else 0
    ltv = round(売上 / 集客数) if 集客数 > 0 else 0
    粗利 = 売上 - 広告費
    return [_format_month(month), media, funnel, 集客数, 予約数, 実施数, 売上, 広告費,
            cpa, cpo, roas, ltv, 粗利]


def build_monthly_sheet(dry_run=False):
    """日別データを月×集客媒体×ファネル別で集計し、スキルプラス（月別）シートに書き込む"""
    from collections import defaultdict

    # ソート順定義
    CATEGORY_ORDER = ["広告", "SNS", "SEO", "広報", "その他"]
    MEDIA_ORDER = [
        # 広告
        "リスティング広告", "ディスプレイ広告", "YouTube広告",
        "Yahoo!広告", "Yahoo!リスティング広告", "Yahoo!ディスプレイ広告",
        "Meta広告", "TikTok広告", "X広告", "LINE広告",
        "アフィリエイト広告", "オフライン広告",
        # SNS
        "YouTube", "X", "Instagram", "Threads", "Facebook", "TikTok",
        # SEO
        "ブランド検索", "一般検索",
        # 広報
        "HP", "広報",
        # その他
        "note", "その他",
    ]
    FUNNEL_ORDER = [
        "ブランド認知", "センサーズ", "AI", "アドプロ",
        "直個別", "みかみメイン", "スキルプラス",
        "ライトプラン", "秘密の部屋", "不明",
    ]

    def _cat_idx(cat):
        return CATEGORY_ORDER.index(cat) if cat in CATEGORY_ORDER else len(CATEGORY_ORDER)

    def _media_idx(media):
        return MEDIA_ORDER.index(media) if media in MEDIA_ORDER else len(MEDIA_ORDER)

    def _fun_idx(fun):
        return FUNNEL_ORDER.index(fun) if fun in FUNNEL_ORDER else len(FUNNEL_ORDER)

    # 1. 全CSV読み込み
    all_rows = read_all_csvs()
    if not all_rows:
        logger.error("CSVデータがありません")
        return 0

    # 2. (月, 集客媒体, ファネル名) ごとに集計 + 媒体→大カテゴリ対応表
    detail = defaultdict(lambda: {
        "集客数": 0, "予約数": 0, "実施数": 0, "売上": 0, "広告費": 0
    })
    media_to_category = {}

    for row in all_rows:
        # row: [日付, 大カテゴリ, 集客媒体, ファネル名, 集客数, 予約数, 実施数, 売上, 広告費, CPA, CPO, ROAS, LTV]
        month_key = row[0][:7]  # "2025-07-01" → "2025-07"
        category = row[1] or "その他"
        media = row[2] or "(未分類)"
        funnel = row[3] or "(未分類)"
        key = (month_key, media, funnel)
        detail[key]["集客数"] += row[4]
        detail[key]["予約数"] += row[5]
        detail[key]["実施数"] += row[6]
        detail[key]["売上"] += row[7]
        detail[key]["広告費"] += row[8]
        media_to_category[media] = category

    # 3. 月ごとにグループ化 → 詳細行 + 合計行
    #    ソート: 大カテゴリ順 → 媒体名 → ファネル順
    months = sorted(set(k[0] for k in detail.keys()))
    sheet_rows = []
    month_ranges = []  # [(month_key, detail_start_idx, detail_end_idx)]
    month_count = 0

    for month in months:
        month_keys = sorted(
            (k for k in detail.keys() if k[0] == month),
            key=lambda k: (_cat_idx(media_to_category.get(k[1], "その他")),
                           _media_idx(k[1]), k[1], _fun_idx(k[2]), k[2])
        )

        # 月合計の集計用
        total = {"集客数": 0, "予約数": 0, "実施数": 0, "売上": 0, "広告費": 0}
        detail_rows = []

        # 詳細行
        for key in month_keys:
            m = detail[key]
            detail_rows.append(_calc_kpi_row(
                month, key[1], key[2],
                m["集客数"], m["予約数"], m["実施数"], m["売上"], m["広告費"]
            ))
            for k in total:
                total[k] += m[k]

        # 合計行を先頭に、詳細行をその後に
        sheet_rows.append(_calc_kpi_row(
            month, "合計", "",
            total["集客数"], total["予約数"], total["実施数"], total["売上"], total["広告費"]
        ))
        detail_start = len(sheet_rows)
        sheet_rows.extend(detail_rows)
        detail_end = len(sheet_rows)
        month_ranges.append((month, detail_start, detail_end))
        month_count += 1

    logger.info(f"月別集計: {month_count} ヶ月, {len(sheet_rows)} 行（詳細+合計）")
    for r in sheet_rows:
        if r[1] == "合計":
            logger.info(f"  {r[0]}: [合計] 集客{r[3]:,} 売上¥{r[6]:,} 広告費¥{r[7]:,} ROAS{r[10]}%")

    if dry_run:
        logger.info("(dry-run: 書き込みスキップ)")
        return len(sheet_rows)

    # 4. シートに書き込み
    # レイアウト: 行1=最終更新, 行2=空, 行3=ヘッダー, 行4〜=データ
    client = get_client(ACCOUNT)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = spreadsheet.worksheet(MONTHLY_SHEET_NAME)

    # シートリサイズ（必要に応じて）
    needed_rows = 3 + len(sheet_rows) + 100
    current_rows = ws.row_count
    if needed_rows > current_rows:
        ws.resize(rows=needed_rows)
        logger.info(f"シートリサイズ: {current_rows} → {needed_rows} 行")

    # 既存データクリア（行1以降すべて）
    ws.batch_clear([f"A1:M{max(current_rows, needed_rows)}"])

    # ヘッダー行3を書き込み
    header = ["月", "集客媒体", "ファネル名", "集客数", "個別予約数", "実施数",
              "売上", "広告費", "CPA", "CPO", "ROAS", "LTV", "粗利"]
    ws.update(values=[header], range_name="A3:M3", value_input_option="USER_ENTERED")

    # データ書き込み（1000行ずつ分割）
    BATCH_SIZE = 1000
    for i in range(0, len(sheet_rows), BATCH_SIZE):
        batch = sheet_rows[i:i + BATCH_SIZE]
        start_row = 4 + i
        end_row = start_row + len(batch) - 1
        ws.update(values=batch, range_name=f"A{start_row}:M{end_row}",
                  value_input_option="RAW")
        logger.info(f"書き込み: A{start_row}:M{end_row} ({len(batch)} 行)")

    # ── 体裁フォーマット ──
    last_row = 3 + len(sheet_rows)

    # 数値フォーマット
    num_formats = [
        (f"D4:F{last_row}", {"type": "NUMBER", "pattern": "#,##0"}),
        (f"G4:H{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"I4:J{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"K4:K{last_row}", {"type": "NUMBER", "pattern": "0.0\"%\""}),
        (f"L4:L{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"M4:M{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
    ]
    for cell_range, num_fmt in num_formats:
        ws.format(cell_range, {"numberFormat": num_fmt})

    # 最終更新行（行1）: グレー文字・10pt
    ws.format("A1:M1", {
        "textFormat": {"foregroundColorStyle": {
            "rgbColor": {"red": 0.5, "green": 0.5, "blue": 0.5}
        }, "fontSize": 10},
    })

    # ヘッダー行（行3）: 太字・背景色・白文字・中央揃え
    ws.format("A3:M3", {
        "textFormat": {"bold": True, "foregroundColorStyle": {
            "rgbColor": {"red": 1, "green": 1, "blue": 1}
        }},
        "backgroundColor": {"red": 0.2, "green": 0.4, "blue": 0.65},
        "horizontalAlignment": "CENTER",
    })

    # 合計行: 太字・薄い背景色
    total_row_indices = [i for i, r in enumerate(sheet_rows) if r[1] == "合計"]
    for idx in total_row_indices:
        row_num = 4 + idx
        ws.format(f"A{row_num}:M{row_num}", {
            "textFormat": {"bold": True},
            "backgroundColor": {"red": 0.9, "green": 0.93, "blue": 0.98},
        })

    # ── グループ化（過去月の詳細行を折りたたみ） ──
    # 既存グループを削除
    try:
        meta = spreadsheet.fetch_sheet_metadata()
        del_reqs = []
        for s in meta.get("sheets", []):
            if s["properties"]["sheetId"] == ws.id:
                for g in s.get("rowGroups", []):
                    del_reqs.append({"deleteDimensionGroup": {"range": g["range"]}})
                break
        if del_reqs:
            spreadsheet.batch_update({"requests": del_reqs})
            logger.info(f"既存グループ削除: {len(del_reqs)} 件")
    except Exception as e:
        logger.warning(f"既存グループ削除スキップ: {e}")

    # フリーズ + グループコントロール位置（合計行の上に+/-ボタン） + グループ追加
    current_month = datetime.now().strftime("%Y-%m")
    requests = [{
        "updateSheetProperties": {
            "properties": {
                "sheetId": ws.id,
                "gridProperties": {
                    "frozenRowCount": 3,
                    "rowGroupControlAfter": False,
                },
            },
            "fields": "gridProperties.frozenRowCount,gridProperties.rowGroupControlAfter",
        }
    }]

    for month_key, detail_start, detail_end in month_ranges:
        if detail_start >= detail_end:
            continue
        requests.append({
            "addDimensionGroup": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "ROWS",
                    "startIndex": 3 + detail_start,
                    "endIndex": 3 + detail_end,
                }
            }
        })

    spreadsheet.batch_update({"requests": requests})

    # 過去月のグループを折りたたみ
    collapse_reqs = []
    for month_key, detail_start, detail_end in month_ranges:
        if detail_start >= detail_end or month_key >= current_month:
            continue
        collapse_reqs.append({
            "updateDimensionGroup": {
                "dimensionGroup": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": 3 + detail_start,
                        "endIndex": 3 + detail_end,
                    },
                    "depth": 1,
                    "collapsed": True,
                },
                "fields": "collapsed",
            }
        })

    if collapse_reqs:
        spreadsheet.batch_update({"requests": collapse_reqs})
        logger.info(f"過去月グループ折りたたみ: {len(collapse_reqs)} ヶ月")

    # ── チャート用サマリーテーブル ──
    summary_start = last_row + 3  # 1-indexed
    total_rows_data = []
    for r in sheet_rows:
        if r[1] == "合計":
            # [月, 集客数, 予約数, 実施数, 売上, 広告費, ROAS, 粗利]
            total_rows_data.append([r[0], r[3], r[4], r[5], r[6], r[7], r[10], r[12]])

    summary_header = ["月", "集客数", "個別予約数", "実施数", "売上", "広告費", "ROAS(%)", "粗利"]
    all_summary = [summary_header] + total_rows_data
    summary_end = summary_start + len(all_summary) - 1

    ws.update(
        values=all_summary,
        range_name=f"A{summary_start}:H{summary_end}",
        value_input_option="RAW",
    )
    # サマリーテーブルのフォーマット
    ws.format(f"A{summary_start}:H{summary_start}", {
        "textFormat": {"bold": True},
        "backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
    })
    ws.format(f"E{summary_start + 1}:F{summary_end}", {
        "numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"},
    })
    ws.format(f"H{summary_start + 1}:H{summary_end}", {
        "numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"},
    })
    ws.format(f"B{summary_start + 1}:D{summary_end}", {
        "numberFormat": {"type": "NUMBER", "pattern": "#,##0"},
    })
    ws.format(f"G{summary_start + 1}:G{summary_end}", {
        "numberFormat": {"type": "NUMBER", "pattern": "0.0\"%\""},
    })
    logger.info(f"サマリーテーブル: A{summary_start}:H{summary_end}")

    # ── チャート作成 ──
    # 既存チャートを削除
    try:
        meta = spreadsheet.fetch_sheet_metadata()
        chart_del = []
        for s in meta.get("sheets", []):
            if s["properties"]["sheetId"] == ws.id:
                for chart in s.get("charts", []):
                    chart_del.append({"deleteEmbeddedObject": {"objectId": chart["chartId"]}})
                break
        if chart_del:
            spreadsheet.batch_update({"requests": chart_del})
            logger.info(f"既存チャート削除: {len(chart_del)} 件")
    except Exception as e:
        logger.warning(f"既存チャート削除スキップ: {e}")

    # チャート用ソース範囲ヘルパー（0-indexed）
    sr0 = summary_start - 1  # 0-indexed header row
    sr1 = summary_end        # 0-indexed exclusive

    def _src(col_start, col_end):
        return {"sourceRange": {"sources": [{
            "sheetId": ws.id,
            "startRowIndex": sr0, "endRowIndex": sr1,
            "startColumnIndex": col_start, "endColumnIndex": col_end,
        }]}}

    chart_row = summary_end + 1  # 0-indexed anchor row for charts

    chart_reqs = [
        # Chart 1: 売上・広告費・粗利（棒グラフ）
        {"addChart": {"chart": {
            "spec": {
                "title": "売上・広告費・粗利",
                "basicChart": {
                    "chartType": "COLUMN",
                    "legendPosition": "BOTTOM_LEGEND",
                    "axis": [
                        {"position": "BOTTOM_AXIS"},
                        {"position": "LEFT_AXIS", "title": "金額"},
                    ],
                    "domains": [{"domain": _src(0, 1)}],
                    "series": [
                        {"series": _src(4, 5), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.27, "green": 0.45, "blue": 0.77}},
                        {"series": _src(5, 6), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.75, "green": 0.31, "blue": 0.30}},
                        {"series": _src(7, 8), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.44, "green": 0.68, "blue": 0.28}},
                    ],
                    "headerCount": 1,
                },
            },
            "position": {"overlayPosition": {
                "anchorCell": {"sheetId": ws.id, "rowIndex": chart_row, "columnIndex": 0},
                "widthPixels": 720, "heightPixels": 400,
            }},
        }}},
        # Chart 2: ROAS推移（折れ線グラフ）
        {"addChart": {"chart": {
            "spec": {
                "title": "ROAS推移",
                "basicChart": {
                    "chartType": "LINE",
                    "legendPosition": "BOTTOM_LEGEND",
                    "axis": [
                        {"position": "BOTTOM_AXIS"},
                        {"position": "LEFT_AXIS", "title": "ROAS (%)"},
                    ],
                    "domains": [{"domain": _src(0, 1)}],
                    "series": [
                        {"series": _src(6, 7), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.93, "green": 0.49, "blue": 0.19}},
                    ],
                    "headerCount": 1,
                },
            },
            "position": {"overlayPosition": {
                "anchorCell": {"sheetId": ws.id, "rowIndex": chart_row, "columnIndex": 7},
                "widthPixels": 520, "heightPixels": 400,
            }},
        }}},
        # Chart 3: 集客数・予約数・実施数（棒グラフ）
        {"addChart": {"chart": {
            "spec": {
                "title": "集客数・予約数・実施数",
                "basicChart": {
                    "chartType": "COLUMN",
                    "legendPosition": "BOTTOM_LEGEND",
                    "axis": [
                        {"position": "BOTTOM_AXIS"},
                        {"position": "LEFT_AXIS", "title": "件数"},
                    ],
                    "domains": [{"domain": _src(0, 1)}],
                    "series": [
                        {"series": _src(1, 2), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.27, "green": 0.45, "blue": 0.77}},
                        {"series": _src(2, 3), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.44, "green": 0.68, "blue": 0.28}},
                        {"series": _src(3, 4), "targetAxis": "LEFT_AXIS",
                         "color": {"red": 0.93, "green": 0.49, "blue": 0.19}},
                    ],
                    "headerCount": 1,
                },
            },
            "position": {"overlayPosition": {
                "anchorCell": {"sheetId": ws.id, "rowIndex": chart_row + 23, "columnIndex": 0},
                "widthPixels": 720, "heightPixels": 400,
            }},
        }}},
    ]
    spreadsheet.batch_update({"requests": chart_reqs})
    logger.info("チャート作成: 3 件")

    # 最終更新日
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.update_acell("A1", f"最終更新: {now}")

    logger.info(f"スキルプラス（月別）構築完了: {month_count} ヶ月, {len(sheet_rows)} 行")

    return len(sheet_rows)


# ─── KPIキャッシュ生成 ────────────────────────────────────────

def generate_kpi_cache(dry_run=False):
    """全CSVデータからKPIサマリーキャッシュ（JSON）を生成する。
    AI秘書がシート参照なしで即座にKPIを回答するためのデータ。"""
    from collections import defaultdict

    all_rows = read_all_csvs()
    if not all_rows:
        logger.error("CSVデータがありません → キャッシュ生成スキップ")
        return False

    # ── 1. 月別サマリ（全体） ──
    monthly = defaultdict(lambda: {"集客数": 0, "予約数": 0, "実施数": 0, "売上": 0, "広告費": 0})
    for row in all_rows:
        mk = row[0][:7]
        monthly[mk]["集客数"] += row[4]
        monthly[mk]["予約数"] += row[5]
        monthly[mk]["実施数"] += row[6]
        monthly[mk]["売上"] += row[7]
        monthly[mk]["広告費"] += row[8]

    monthly_list = []
    for month in sorted(monthly.keys()):
        m = monthly[month]
        集客 = m["集客数"]; 予約 = m["予約数"]; 実施 = m["実施数"]
        売上 = m["売上"]; 広告費 = m["広告費"]
        monthly_list.append({
            "month": month,
            "集客数": 集客, "個別予約数": 予約, "実施数": 実施,
            "売上": 売上, "広告費": 広告費,
            "CPA": round(広告費 / 集客) if 集客 > 0 else 0,
            "CPO": round(広告費 / 予約) if 予約 > 0 else 0,
            "ROAS": round(売上 / 広告費 * 100, 1) if 広告費 > 0 else 0,
            "LTV": round(売上 / 集客) if 集客 > 0 else 0,
            "粗利": 売上 - 広告費,
        })

    # ── 2. 月別×媒体 内訳 ──
    media_monthly = defaultdict(lambda: defaultdict(lambda: {"集客数": 0, "予約数": 0, "売上": 0, "広告費": 0}))
    for row in all_rows:
        mk = row[0][:7]
        media = row[2]  # 集客媒体
        if not media:
            continue
        media_monthly[mk][media]["集客数"] += row[4]
        media_monthly[mk][media]["予約数"] += row[5]
        media_monthly[mk][media]["売上"] += row[7]
        media_monthly[mk][media]["広告費"] += row[8]

    monthly_by_media = {}
    for mk in sorted(media_monthly.keys()):
        monthly_by_media[mk] = {}
        for media, vals in sorted(media_monthly[mk].items()):
            monthly_by_media[mk][media] = {
                "集客数": vals["集客数"], "個別予約数": vals["予約数"],
                "売上": vals["売上"], "広告費": vals["広告費"],
                "ROAS": round(vals["売上"] / vals["広告費"] * 100, 1) if vals["広告費"] > 0 else 0,
            }

    # ── 2b. 月別×媒体×ファネル 内訳 ──
    mf_monthly = defaultdict(lambda: defaultdict(lambda: {
        "集客数": 0, "予約数": 0, "実施数": 0, "売上": 0, "広告費": 0
    }))
    for row in all_rows:
        mk = row[0][:7]
        media = row[2] or "(未分類)"
        funnel = row[3] or "(未分類)"
        mf_key = f"{media}|{funnel}"
        mf_monthly[mk][mf_key]["集客数"] += row[4]
        mf_monthly[mk][mf_key]["予約数"] += row[5]
        mf_monthly[mk][mf_key]["実施数"] += row[6]
        mf_monthly[mk][mf_key]["売上"] += row[7]
        mf_monthly[mk][mf_key]["広告費"] += row[8]

    monthly_by_media_funnel = {}
    for mk in sorted(mf_monthly.keys()):
        monthly_by_media_funnel[mk] = {}
        for mf_key, vals in sorted(mf_monthly[mk].items()):
            集客 = vals["集客数"]; 予約 = vals["予約数"]
            売上 = vals["売上"]; 広告費 = vals["広告費"]
            monthly_by_media_funnel[mk][mf_key] = {
                "集客媒体": mf_key.split("|")[0],
                "ファネル名": mf_key.split("|")[1],
                "集客数": 集客, "個別予約数": 予約,
                "実施数": vals["実施数"], "売上": 売上, "広告費": 広告費,
                "CPA": round(広告費 / 集客) if 集客 > 0 else 0,
                "CPO": round(広告費 / 予約) if 予約 > 0 else 0,
                "ROAS": round(売上 / 広告費 * 100, 1) if 広告費 > 0 else 0,
                "LTV": round(売上 / 集客) if 集客 > 0 else 0,
                "粗利": 売上 - 広告費,
            }

    # ── 3. 直近14日 日別合計 ──
    daily_totals = defaultdict(lambda: {"集客数": 0, "予約数": 0, "売上": 0, "広告費": 0})
    for row in all_rows:
        dt = row[0]
        daily_totals[dt]["集客数"] += row[4]
        daily_totals[dt]["予約数"] += row[5]
        daily_totals[dt]["売上"] += row[7]
        daily_totals[dt]["広告費"] += row[8]

    sorted_dates = sorted(daily_totals.keys(), reverse=True)[:14]
    recent_daily = []
    for dt in sorted_dates:
        d = daily_totals[dt]
        recent_daily.append({
            "date": dt,
            "集客数": d["集客数"], "個別予約数": d["予約数"],
            "売上": d["売上"], "広告費": d["広告費"],
            "ROAS": round(d["売上"] / d["広告費"] * 100, 1) if d["広告費"] > 0 else 0,
        })

    # ── 4. 直近14日 日別×媒体 ──
    media_daily = defaultdict(lambda: defaultdict(lambda: {"集客数": 0, "売上": 0, "広告費": 0}))
    for row in all_rows:
        dt = row[0]
        if dt not in sorted_dates:
            continue
        media = row[2]
        if not media:
            continue
        media_daily[dt][media]["集客数"] += row[4]
        media_daily[dt][media]["売上"] += row[7]
        media_daily[dt][media]["広告費"] += row[8]

    recent_daily_by_media = {}
    for dt in sorted_dates:
        recent_daily_by_media[dt] = {}
        for media, vals in sorted(media_daily[dt].items()):
            recent_daily_by_media[dt][media] = {
                "集客数": vals["集客数"], "売上": vals["売上"], "広告費": vals["広告費"],
            }

    # ── 5. JSON出力 ──
    cache = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "monthly": monthly_list,
        "monthly_by_media": monthly_by_media,
        "monthly_by_media_funnel": monthly_by_media_funnel,
        "recent_daily": recent_daily,
        "recent_daily_by_media": recent_daily_by_media,
    }

    # バリデーション: 空データチェック
    if not monthly_list and not recent_daily:
        logger.warning("KPIキャッシュ生成スキップ: 月別・日別データが両方空です")
        return False

    if dry_run:
        logger.info(f"(dry-run) KPIキャッシュ生成予定: {len(monthly_list)}ヶ月, {len(recent_daily)}日分")
        return True

    # アトミック書き込み: tmpfile → rename で破損を防止
    from pathlib import Path
    cache_path = Path(KPI_CACHE_PATH)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(cache, ensure_ascii=False, indent=2)
    fd, tmp_path = tempfile.mkstemp(dir=str(cache_path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json_str)
        os.replace(tmp_path, str(KPI_CACHE_PATH))
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise

    logger.info(f"KPIキャッシュ生成完了: {KPI_CACHE_PATH} ({len(monthly_list)}ヶ月, {len(recent_daily)}日分)")
    return True


# ─── CLI ──────────────────────────────────────────────────────

if __name__ == "__main__":
    args = sys.argv[1:]
    dry_run = "--dry-run" in args

    try:
        if "cache" in args:
            # KPIキャッシュのみ再生成
            generate_kpi_cache(dry_run=dry_run)
        elif "build" in args:
            # スキルプラス（日別）シートのみ構築
            count = build_daily_sheet(dry_run=dry_run)
            if count > 0:
                logger.info(f"完了: {count} 行書き込み")
                generate_kpi_cache(dry_run=dry_run)
        elif "monthly" in args:
            # スキルプラス（月別）シートのみ構築
            count = build_monthly_sheet(dry_run=dry_run)
            if count > 0:
                logger.info(f"完了: {count} ヶ月分書き込み")
                generate_kpi_cache(dry_run=dry_run)
        else:
            # デフォルト: 元データ → 日別 → 月別 の連鎖実行
            count = sync_to_sheet(dry_run=dry_run)
            if count > 0:
                logger.info(f"元データ: {count} 行更新 → 日別・月別を再構築")
                daily = build_daily_sheet(dry_run=dry_run)
                logger.info(f"日別: {daily} 行書き込み → 月別を再集計")
                monthly = build_monthly_sheet(dry_run=dry_run)
                logger.info(f"月別: {monthly} ヶ月分書き込み → KPIキャッシュ生成")
                generate_kpi_cache(dry_run=dry_run)
            else:
                logger.info("元データに変更なし → 日別・月別の更新スキップ")
        sys.exit(0)
    except Exception as e:
        logger.error(f"エラー: {e}", exc_info=True)
        sys.exit(1)
