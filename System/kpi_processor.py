#!/usr/bin/env python3
"""
KPI Processor - Looker Studio CSVをスプレッドシートに投入・整理

使い方:
  python3 kpi_processor.py import <CSVパス> [対象日付]
  python3 kpi_processor.py refresh

import: CSVを読み取り、日別・月別タブを更新し、元データにログ記録
refresh: 日別タブの既存データから月別タブを再計算

対象日付を省略すると2日前の日付を使用。

シート構成:
  元データ            → 実行ログ（日付 + CSVタイプ + 投入日時 + ステータス）
  スキルプラス（日別）  → CSVの内容を日付付きで一覧表示（媒体×ファネル別全行）
  スキルプラス（月別）  → 月別合計KPI（1行/月）
"""

import csv
import sys
import os
from datetime import date, datetime, timedelta
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sheets_manager

SHEET_ID = "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
RAW_TAB = "元データ"
DAILY_TAB = "スキルプラス（日別）"
MONTHLY_TAB = "スキルプラス（月別）"

# 元データ（実行ログ）ヘッダー
LOG_HEADER = ["対象日付", "CSVダウンロードタイプ", "投入日時", "ステータス"]

# 日別タブのヘッダー（日付 + CSV列）
DAILY_HEADER = ["日付", "大カテゴリ", "集客媒体", "ファネル名",
                "集客数", "個別予約数", "実施数", "売上", "広告費",
                "CPA", "個別CPO", "単月ROAS", "単月LTV"]

# 月別タブの集計カラム（CSVから合計する列）
SUM_COLS = ["集客数", "個別予約数", "実施数", "売上", "広告費"]

# 月別タブの表示カラム
MONTHLY_KPI_COLS = ["集客数", "個別予約数", "実施数", "売上", "広告費", "CPA", "CPO", "ROAS", "LTV", "粗利"]


def _parse_num(val):
    """文字列を数値に変換（¥・カンマ・%を除去、空やエラーは0）"""
    if not val:
        return 0
    try:
        cleaned = str(val).replace(",", "").replace("¥", "").replace("%", "").strip()
        return float(cleaned) if cleaned else 0
    except ValueError:
        return 0


def _calc_derived(d):
    """派生指標を計算"""
    集客 = d["集客数"]
    予約 = d["個別予約数"]
    売上 = d["売上"]
    広告費 = d["広告費"]

    d["CPA"] = round(広告費 / 集客) if 集客 > 0 else 0
    d["CPO"] = round(広告費 / 予約) if 予約 > 0 else 0
    d["ROAS"] = round(売上 / 広告費 * 100, 1) if 広告費 > 0 else 0
    d["LTV"] = round(売上 / 集客) if 集客 > 0 else 0
    d["粗利"] = round(売上 - 広告費)
    return d


def _fmt_num(val):
    """数値をカンマ区切りにフォーマット（4桁以上）"""
    try:
        n = float(str(val).replace(",", ""))
        if n == int(n):
            return f"{int(n):,}"
        return f"{round(n, 1):,}"
    except (ValueError, TypeError):
        return str(val)


def _fmt_yen(val):
    """円表記: ¥1,234,567"""
    try:
        n = float(str(val).replace(",", ""))
        return f"¥{int(round(n)):,}" if n else "¥0"
    except (ValueError, TypeError):
        return str(val)


def _fmt_pct(val):
    """パーセント表記: 123.4%"""
    try:
        n = float(str(val).replace(",", ""))
        if n == 0:
            return "0%"
        return f"{round(n, 1)}%" if n != int(n) else f"{int(n)}%"
    except (ValueError, TypeError):
        return str(val)


# 日別タブ: フォーマット対象カラムインデックス（row[0]=日付, row[1]=大カテゴリ, ...）
_DAILY_YEN_COLS = {7, 8, 9, 10, 12}   # 売上, 広告費, CPA, 個別CPO, 単月LTV
_DAILY_PCT_COLS = {11}                  # 単月ROAS
_DAILY_NUM_COLS = {4, 5, 6}             # 集客数, 個別予約数, 実施数

# 月別タブ: フォーマット対象カラム名
_MONTHLY_YEN_COLS = {"売上", "広告費", "CPA", "CPO", "LTV"}
_MONTHLY_PCT_COLS = {"ROAS"}


def _fmt_daily_row(row):
    """日別タブの1行をフォーマット（円表記・%・カンマ区切り）"""
    result = list(row)
    for i in _DAILY_YEN_COLS:
        if i < len(result):
            result[i] = _fmt_yen(result[i])
    for i in _DAILY_PCT_COLS:
        if i < len(result):
            result[i] = _fmt_pct(result[i])
    for i in _DAILY_NUM_COLS:
        if i < len(result):
            result[i] = _fmt_num(result[i])
    return result


def _fmt_monthly_val(col_name, val):
    """月別タブの値をカラム名に応じてフォーマット"""
    if col_name in _MONTHLY_YEN_COLS:
        return _fmt_yen(val)
    if col_name in _MONTHLY_PCT_COLS:
        return _fmt_pct(val)
    return _fmt_num(val)


def _center_align(ws, row_count, col_count):
    """シート全体を中央揃えにする"""
    col_letter = chr(ord("A") + col_count - 1)
    ws.format(f"A1:{col_letter}{row_count}", {
        "horizontalAlignment": "CENTER",
    })


# ─── CSV取り込み ──────────────────────────────────────────

def import_csv(csv_path, target_date=None):
    """CSVを読み取り → 日別タブにCSV全行追加 → 月別タブ再計算 → 元データにログ記録"""
    if not os.path.exists(csv_path):
        print(f"エラー: ファイルが見つかりません: {csv_path}")
        sys.exit(1)

    if not target_date:
        target_date = (date.today() - timedelta(days=2)).isoformat()

    csv_filename = os.path.basename(csv_path)

    # CSV読み込み
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        csv_header = next(reader)
        csv_rows = list(reader)

    if not csv_rows:
        print("エラー: CSVにデータがありません")
        sys.exit(1)

    print(f"CSV読み込み: {len(csv_rows)} 行（対象日付: {target_date}）")

    # スプレッドシート接続
    client = sheets_manager.get_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    # ─── 日別タブ更新（CSV全行を展開）───
    _update_daily_tab(spreadsheet, csv_rows, target_date)

    # ─── 月別タブ再計算 ───
    _recalc_monthly(spreadsheet)

    # ─── 元データにログ記録 ───
    _log_import(spreadsheet, target_date, csv_filename)

    print("完了")


def _update_daily_tab(spreadsheet, csv_rows, target_date):
    """日別タブにCSVの全行を日付付きで追加（同日データは上書き）"""
    ws_daily = spreadsheet.worksheet(DAILY_TAB)
    existing = ws_daily.get_all_values()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ヘッダー行を探す（DAILY_HEADERと一致する行）
    header_row_idx = None
    for i, row in enumerate(existing):
        if row and row[:len(DAILY_HEADER)] == DAILY_HEADER:
            header_row_idx = i
            break

    if header_row_idx is None:
        # 初回 or ヘッダー不一致: テンプレート再作成（データは保持しない）
        existing = [
            ["【スキルプラス】日別データ"] + [""] * (len(DAILY_HEADER) - 1),
            [f"最終更新: {now_str}"] + [""] * (len(DAILY_HEADER) - 1),
            [""] * len(DAILY_HEADER),
            DAILY_HEADER,
        ]
        header_row_idx = 3

    # 既存データから同日を除外
    kept = existing[:header_row_idx + 1]
    for row in existing[header_row_idx + 1:]:
        if row and row[0] != target_date:
            kept.append(row)

    # 新しいCSV行を日付付きで追加（フォーマット適用）
    new_rows = []
    for csv_row in csv_rows:
        new_rows.append(_fmt_daily_row([target_date] + csv_row))

    # 日付降順で挿入位置を探す
    result = kept[:header_row_idx + 1]
    inserted = False
    for row in kept[header_row_idx + 1:]:
        if not inserted and row and row[0] < target_date:
            result.extend(new_rows)
            inserted = True
        result.append(row)
    if not inserted:
        result.extend(new_rows)

    # 最終更新日時を更新
    result[1] = [f"最終更新: {now_str}"] + [""] * (len(DAILY_HEADER) - 1)

    # 書き込み
    col_count = len(DAILY_HEADER)
    col_letter = chr(ord("A") + col_count - 1)  # M
    ws_daily.clear()
    ws_daily.update(values=result, range_name=f"A1:{col_letter}{len(result)}")
    _center_align(ws_daily, len(result), col_count)
    print(f"日別タブ更新完了: {target_date} の {len(new_rows)} 行を投入（合計 {len(result) - header_row_idx - 1} 行）")


def _recalc_monthly(spreadsheet):
    """日別タブの全データから月別タブを再計算"""
    ws_daily = spreadsheet.worksheet(DAILY_TAB)
    ws_monthly = spreadsheet.worksheet(MONTHLY_TAB)

    daily_data = ws_daily.get_all_values()

    # ヘッダー行を探す
    header_row_idx = None
    daily_col_map = {}
    for i, row in enumerate(daily_data):
        if row and row[0] == "日付":
            header_row_idx = i
            daily_col_map = {h: j for j, h in enumerate(row)}
            break

    if header_row_idx is None:
        print("日別タブにデータがありません")
        return

    # 日付×月でまず日別合計を出し、月別に集約
    # （同じ日付に複数行があるので、まず日別にSUMしてから月別にSUM）
    daily_totals = defaultdict(lambda: {c: 0 for c in SUM_COLS})
    for row in daily_data[header_row_idx + 1:]:
        if not row or not row[0]:
            continue
        dt = row[0]
        d = daily_totals[dt]
        for col_name in SUM_COLS:
            idx = daily_col_map.get(col_name)
            if idx is not None and idx < len(row):
                d[col_name] += _parse_num(row[idx])

    # 月別集計
    monthly = defaultdict(lambda: {c: 0 for c in SUM_COLS})
    for dt, d in daily_totals.items():
        month_key = dt[:7]
        m = monthly[month_key]
        for col_name in SUM_COLS:
            m[col_name] += d[col_name]

    for mk, m in monthly.items():
        _calc_derived(m)

    sorted_months = sorted(monthly.keys(), reverse=True)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    monthly_output = [
        ["【スキルプラス】月別KPI", "", "", "", "", "", "", "", "", "", ""],
        [f"最終更新: {now_str}", "", "", "", "", "", "", "", "", "", ""],
        ["", "", "", "", "", "", "", "", "", "", ""],
        ["月"] + MONTHLY_KPI_COLS,
    ]
    for mk in sorted_months:
        m = monthly[mk]
        row = [mk] + [_fmt_monthly_val(col, m[col]) for col in MONTHLY_KPI_COLS]
        monthly_output.append(row)

    ws_monthly.clear()
    ws_monthly.update(values=monthly_output, range_name=f"A1:K{len(monthly_output)}")
    _center_align(ws_monthly, len(monthly_output), len(MONTHLY_KPI_COLS) + 1)
    print(f"月別タブ更新完了: {len(sorted_months)} ヶ月分")


def _log_import(spreadsheet, target_date, csv_filename):
    """元データタブに実行ログを記録"""
    ws_raw = spreadsheet.worksheet(RAW_TAB)
    existing = ws_raw.get_all_values()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not existing or (existing[0] and existing[0][0] != LOG_HEADER[0]):
        ws_raw.clear()
        existing = [LOG_HEADER]

    # 同日の既存ログを除去
    kept = [existing[0]]
    for row in existing[1:]:
        if row and row[0] != target_date:
            kept.append(row)

    # 新しいログを日付降順で挿入
    new_log = [target_date, csv_filename, now_str, "完了"]
    inserted = False
    result = [kept[0]]
    for row in kept[1:]:
        if not inserted and row and row[0] < target_date:
            result.append(new_log)
            inserted = True
        result.append(row)
    if not inserted:
        result.append(new_log)

    ws_raw.clear()
    ws_raw.update(values=result, range_name=f"A1:D{len(result)}")
    print(f"元データ ログ記録完了: {target_date} / {csv_filename}")


# ─── refresh ──────────────────────────────────────────────

def refresh():
    """日別タブの既存データから月別タブを再計算"""
    client = sheets_manager.get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    _recalc_monthly(spreadsheet)


# ─── process（元データ監視 → 日別自動投入）──────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_DIR = os.path.join(SCRIPT_DIR, "looker_csv_downloads")


def process():
    """元データの「完了」エントリを検知 → CSVファイルを日別に投入 → 月別再計算"""
    client = sheets_manager.get_client()
    spreadsheet = client.open_by_key(SHEET_ID)

    # ─── 元データから完了リスト取得 ───
    ws_raw = spreadsheet.worksheet(RAW_TAB)
    raw_data = ws_raw.get_all_values()

    # ─── 日別タブから既存日付を取得 ───
    ws_daily = spreadsheet.worksheet(DAILY_TAB)
    daily_data = ws_daily.get_all_values()
    existing_dates = set()
    for row in daily_data:
        if row and row[0] and len(row[0]) == 10 and row[0][4] == "-":
            existing_dates.add(row[0])

    # ─── 完了 かつ 日別未投入 の日付を検出 ───
    pending = []
    for i, row in enumerate(raw_data):
        if len(row) < 4:
            continue
        target_date = row[0]
        status = row[3]
        if status == "完了" and target_date not in existing_dates:
            pending.append((i, target_date))

    if not pending:
        print("投入対象なし（全て投入済み or 完了エントリなし）")
        return

    print(f"投入対象: {len(pending)} 日分")

    # ─── CSVファイルを探して日別に一括投入 ───
    all_new_rows = []  # (date, csv_rows) のリスト
    missing_csv = []

    for row_idx, target_date in pending:
        csv_type_name = raw_data[row_idx][1] if len(raw_data[row_idx]) > 1 else ""
        csv_path = _find_csv(target_date, csv_type_name)
        if not csv_path:
            missing_csv.append(target_date)
            continue

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # ヘッダースキップ
            csv_rows = list(reader)

        if csv_rows:
            all_new_rows.append((target_date, csv_rows))

    if missing_csv:
        print(f"CSVファイル未発見: {len(missing_csv)} 日分（{missing_csv[0]}〜{missing_csv[-1]}）")

    if not all_new_rows:
        print("投入可能なCSVがありません")
        return

    # ─── 日別タブに一括追加 ───
    _batch_update_daily(spreadsheet, all_new_rows)

    # ─── 月別タブ再計算 ───
    _recalc_monthly(spreadsheet)

    # ─── 元データの投入日時を更新 ───
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    processed_dates = {d for d, _ in all_new_rows}
    updates = []
    for i, row in enumerate(raw_data):
        if len(row) >= 4 and row[0] in processed_dates:
            updates.append((i + 1, now_str))  # 1-indexed row number

    # バッチ更新（投入日時列 = C列）
    for row_num, ts in updates:
        ws_raw.update_acell(f"C{row_num}", ts)

    print(f"投入完了: {len(all_new_rows)} 日分")


def _find_csv(target_date, csv_type_name=""):
    """日付とCSVタイプ名に対応するCSVファイルを探す"""
    # 日付ベースのファイル名候補
    candidates = [
        os.path.join(CSV_DIR, f"looker_media_funnel_{target_date}.csv"),
        os.path.join(CSV_DIR, f"looker_{target_date}.csv"),
        os.path.join(os.path.expanduser("~/Downloads"), f"looker_media_funnel_{target_date}.csv"),
        os.path.join(os.path.expanduser("~/Downloads"), f"looker_{target_date}.csv"),
    ]
    # 元データのCSVダウンロードタイプ名も候補に追加
    if csv_type_name:
        base_name = csv_type_name.replace(".csv", "")
        candidates.extend([
            os.path.join(CSV_DIR, csv_type_name),
            os.path.join(CSV_DIR, f"{base_name}_{target_date}.csv"),
            os.path.join(os.path.expanduser("~/Downloads"), csv_type_name),
            os.path.join(os.path.expanduser("~/Downloads"), f"{base_name}_{target_date}.csv"),
        ])
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def _batch_update_daily(spreadsheet, date_csv_pairs):
    """複数日のCSVデータを日別タブに一括投入"""
    ws_daily = spreadsheet.worksheet(DAILY_TAB)
    existing = ws_daily.get_all_values()

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ヘッダー行を探す
    header_row_idx = None
    for i, row in enumerate(existing):
        if row and row[:len(DAILY_HEADER)] == DAILY_HEADER:
            header_row_idx = i
            break

    if header_row_idx is None:
        existing = [
            ["【スキルプラス】日別データ"] + [""] * (len(DAILY_HEADER) - 1),
            [f"最終更新: {now_str}"] + [""] * (len(DAILY_HEADER) - 1),
            [""] * len(DAILY_HEADER),
            DAILY_HEADER,
        ]
        header_row_idx = 3

    # 新しいデータの日付セット
    new_dates = {d for d, _ in date_csv_pairs}

    # 既存データから新規日付を除外（上書き対応）
    kept = existing[:header_row_idx + 1]
    for row in existing[header_row_idx + 1:]:
        if row and row[0] not in new_dates:
            kept.append(row)

    # 新しいCSV行をフォーマットして追加
    new_formatted = []
    for target_date, csv_rows in date_csv_pairs:
        for csv_row in csv_rows:
            new_formatted.append((target_date, _fmt_daily_row([target_date] + csv_row)))

    # 全データ行を日付降順でソート
    all_data = []
    for row in kept[header_row_idx + 1:]:
        if row and row[0]:
            all_data.append(row)
    for _, fmt_row in new_formatted:
        all_data.append(fmt_row)

    all_data.sort(key=lambda r: r[0] if r else "", reverse=True)

    # 結果を構築
    result = kept[:header_row_idx + 1]
    result[1] = [f"最終更新: {now_str}"] + [""] * (len(DAILY_HEADER) - 1)
    result.extend(all_data)

    # 書き込み
    col_count = len(DAILY_HEADER)
    col_letter = chr(ord("A") + col_count - 1)
    ws_daily.clear()
    ws_daily.update(values=result, range_name=f"A1:{col_letter}{len(result)}")
    _center_align(ws_daily, len(result), col_count)

    total_new = len(new_formatted)
    total_rows = len(all_data)
    print(f"日別タブ更新完了: {len(date_csv_pairs)} 日分 / {total_new} 行追加（合計 {total_rows} 行）")


# ─── check_today（当日の2日前データのステータス確認）───────

def check_today():
    """2日前の日付が元データで「完了」になっているか確認。
    戻り値をprint: 'ok' or 'pending'
    """
    target = (date.today() - timedelta(days=2)).isoformat()
    client = sheets_manager.get_client()
    spreadsheet = client.open_by_key(SHEET_ID)
    ws_raw = spreadsheet.worksheet(RAW_TAB)
    raw_data = ws_raw.get_all_values()

    for row in raw_data:
        if len(row) >= 4 and row[0] == target:
            if row[3] == "完了":
                print(f"ok:{target}")
                return
            else:
                print(f"pending:{target}:{row[3]}")
                return

    print(f"not_found:{target}")


# ─── CLI ──────────────────────────────────────────────────

def print_usage():
    print("""
使い方:
  python3 kpi_processor.py import <CSVパス> [対象日付]
  python3 kpi_processor.py process
  python3 kpi_processor.py refresh

コマンド:
  import    CSVの全行を日別タブに投入し、月別タブを再計算、元データにログ記録
            対象日付を省略すると2日前を使用
  process   元データの「完了」エントリを検知 → CSVから日別に自動投入 → 月別再計算
            （Cursorがダウンロードしたあとに実行）
  refresh   日別タブの既存データから月別タブを再計算

例:
  python3 kpi_processor.py import ~/Downloads/looker_export.csv 2026-02-19
  python3 kpi_processor.py process
  python3 kpi_processor.py refresh
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "import":
        if len(sys.argv) < 3:
            print("エラー: CSVパスを指定してください")
            sys.exit(1)
        csv_path = sys.argv[2]
        target_date = sys.argv[3] if len(sys.argv) > 3 else None
        import_csv(csv_path, target_date)

    elif cmd == "process":
        process()

    elif cmd == "check_today":
        check_today()

    elif cmd == "refresh":
        refresh()

    else:
        print(f"不明なコマンド: {cmd}")
        print_usage()
        sys.exit(1)
