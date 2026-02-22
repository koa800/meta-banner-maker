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
import requests
from datetime import datetime

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

    dated_files = {}
    unnamed_files = []

    for f in os.listdir(CSV_DIR):
        if not f.endswith(".csv") or BASE_CSV_NAME not in f:
            continue

        m = DATE_PATTERN.match(f)
        if m:
            dated_files[m.group(1)] = f
        else:
            # デフォルト名（日付なし）のCSV
            unnamed_files.append(f)

    return dated_files, unnamed_files


def check_unnamed_files(unnamed_files: list, dry_run: bool = False):
    """日付不明のCSVファイルを検出してLINEで通知する"""
    if not unnamed_files:
        return

    # 通知済みリストを読み込み、未通知のファイルだけ抽出
    notified = load_notified()
    new_unnamed = [f for f in unnamed_files if f not in notified]

    if not new_unnamed:
        return

    logger.info(f"日付不明のCSVファイル: {len(new_unnamed)} 件")
    for f in new_unnamed:
        logger.info(f"  - {f}")

    if dry_run:
        logger.info("(dry-run: LINE通知スキップ)")
        return

    # LINE通知
    file_list = "\n".join(f"・{f}" for f in new_unnamed[:10])
    if len(new_unnamed) > 10:
        file_list += f"\n... 他 {len(new_unnamed) - 10} 件"

    message = (
        f"📊 Looker Studio CSV: 日付不明のファイルが {len(new_unnamed)} 件あります\n\n"
        f"{file_list}\n\n"
        f"ファイル名の先頭に日付を付けてください。\n"
        f"例: 2026-02-20_{BASE_CSV_NAME}.csv\n\n"
        f"日付を付けると自動でシートに反映されます。"
    )
    send_line_notify(message)

    # 通知済みに追加
    notified.update(new_unnamed)
    save_notified(notified)


# ─── シート同期 ────────────────────────────────────────────────

def sync_to_sheet(dry_run=False):
    """CSVファイルとシートを同期"""
    # 1. フォルダスキャン
    csv_files, unnamed_files = scan_csv_folder()

    # 日付不明ファイルのチェック
    check_unnamed_files(unnamed_files, dry_run=dry_run)

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
        ws.update(range_notation, update_rows)
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
        ws.update(range_notation, all_rows)
        logger.info(f"一括書き込み完了: {range_notation}")

    # 5. 更新完了をLINE通知
    dates = [u["date"] for u in updates]
    first = dates[0]
    last = dates[-1]
    message = f"📊 元データシート更新完了: {len(updates)} 件\n{first} 〜 {last}"
    send_line_notify(message)

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

    all_rows = []
    files = sorted(f for f in os.listdir(CSV_DIR)
                   if DATE_PATTERN.match(f) and BASE_CSV_NAME in f)

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

    # 3. シートをリサイズ（ヘッダー4行 + データ行 + 余裕100行）
    needed_rows = 4 + len(all_rows) + 100
    current_rows = ws.row_count
    if needed_rows > current_rows:
        ws.resize(rows=needed_rows)
        logger.info(f"シートリサイズ: {current_rows} → {needed_rows} 行")

    # 4. 既存データをクリア（行5以降）
    ws.batch_clear([f"A5:M{current_rows}"])
    logger.info("既存データクリア完了")

    # 5. データ書き込み（行5〜）
    # Google Sheets API は 1リクエストあたり上限あるため、1000行ずつ分割
    BATCH_SIZE = 1000
    for i in range(0, len(all_rows), BATCH_SIZE):
        batch = all_rows[i:i + BATCH_SIZE]
        start_row = 5 + i
        end_row = start_row + len(batch) - 1
        range_notation = f"A{start_row}:M{end_row}"
        ws.update(range_notation, batch, value_input_option="USER_ENTERED")
        logger.info(f"書き込み: {range_notation} ({len(batch)} 行)")

    # 6. 最終更新日を更新（行2）
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.update_acell("A2", f"最終更新: {now}")

    logger.info(f"スキルプラス（日別）構築完了: {len(all_rows)} 行")

    # 7. LINE通知
    message = (
        f"📊 スキルプラス（日別）シート更新完了\n"
        f"{dates[0]} 〜 {dates[-1]}\n"
        f"{len(dates)} 日分 / {len(all_rows)} 行"
    )
    send_line_notify(message)

    return len(all_rows)


# ─── スキルプラス（月別）構築 ──────────────────────────────────

def build_monthly_sheet(dry_run=False):
    """日別データを月単位で集計し、スキルプラス（月別）シートに書き込む"""
    from collections import defaultdict

    # 1. 全CSV読み込み
    all_rows = read_all_csvs()
    if not all_rows:
        logger.error("CSVデータがありません")
        return 0

    # 2. 月ごとに集計（集客数, 予約数, 実施数, 売上, 広告費）
    monthly = defaultdict(lambda: {
        "集客数": 0, "予約数": 0, "実施数": 0, "売上": 0, "広告費": 0
    })

    for row in all_rows:
        # row: [日付, 大カテゴリ, 集客媒体, ファネル名, 集客数, 予約数, 実施数, 売上, 広告費, CPA, CPO, ROAS, LTV]
        month_key = row[0][:7]  # "2025-07-01" → "2025-07"
        monthly[month_key]["集客数"] += row[4]
        monthly[month_key]["予約数"] += row[5]
        monthly[month_key]["実施数"] += row[6]
        monthly[month_key]["売上"] += row[7]
        monthly[month_key]["広告費"] += row[8]

    # 3. KPI計算 & 行データ作成
    sheet_rows = []
    for month in sorted(monthly.keys()):
        m = monthly[month]
        集客数 = m["集客数"]
        予約数 = m["予約数"]
        実施数 = m["実施数"]
        売上 = m["売上"]
        広告費 = m["広告費"]

        cpa = round(広告費 / 集客数) if 集客数 > 0 else 0
        cpo = round(広告費 / 予約数) if 予約数 > 0 else 0
        roas = round(売上 / 広告費 * 100, 1) if 広告費 > 0 else 0
        ltv = round(売上 / 集客数) if 集客数 > 0 else 0
        粗利 = 売上 - 広告費

        sheet_rows.append([
            month, 集客数, 予約数, 実施数, 売上, 広告費,
            cpa, cpo, roas, ltv, 粗利
        ])

    logger.info(f"月別集計: {len(sheet_rows)} ヶ月")
    for r in sheet_rows:
        logger.info(f"  {r[0]}: 集客{r[1]:,} 売上¥{r[4]:,} 広告費¥{r[5]:,} ROAS{r[8]}%")

    if dry_run:
        logger.info("(dry-run: 書き込みスキップ)")
        return len(sheet_rows)

    # 4. シートに書き込み
    client = get_client(ACCOUNT)
    spreadsheet = client.open_by_key(SPREADSHEET_ID)
    ws = spreadsheet.worksheet(MONTHLY_SHEET_NAME)

    # 既存データクリア（行5以降）
    current_rows = ws.row_count
    ws.batch_clear([f"A5:K{current_rows}"])

    # データ書き込み
    last_row = 4 + len(sheet_rows)
    ws.update(f"A5:K{last_row}", sheet_rows, value_input_option="USER_ENTERED")

    # フォーマット適用
    formats = [
        (f"B5:D{last_row}", {"type": "NUMBER", "pattern": "#,##0"}),
        (f"E5:F{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"G5:H{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"I5:I{last_row}", {"type": "NUMBER", "pattern": "0.0\"%\""}),
        (f"J5:J{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
        (f"K5:K{last_row}", {"type": "CURRENCY", "pattern": "¥#,##0"}),
    ]
    for cell_range, num_fmt in formats:
        ws.format(cell_range, {"numberFormat": num_fmt})

    # 最終更新日
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ws.update_acell("A2", f"最終更新: {now}")

    logger.info(f"スキルプラス（月別）構築完了: {len(sheet_rows)} ヶ月")

    # LINE通知
    months = [r[0] for r in sheet_rows]
    message = (
        f"📊 スキルプラス（月別）シート更新完了\n"
        f"{months[0]} 〜 {months[-1]} ({len(months)} ヶ月)"
    )
    send_line_notify(message)

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
                "集客数": vals["集客数"], "予約数": vals["予約数"],
                "売上": vals["売上"], "広告費": vals["広告費"],
                "ROAS": round(vals["売上"] / vals["広告費"] * 100, 1) if vals["広告費"] > 0 else 0,
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
        "recent_daily": recent_daily,
        "recent_daily_by_media": recent_daily_by_media,
    }

    if dry_run:
        logger.info(f"(dry-run) KPIキャッシュ生成予定: {len(monthly_list)}ヶ月, {len(recent_daily)}日分")
        return True

    with open(KPI_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)

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
