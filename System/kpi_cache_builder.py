#!/usr/bin/env python3
"""
KPI Cache Builder - ローカルCSVキャッシュからkpi_summary.jsonを生成

sheets_sync.py が Master/sheets/ に保存したCSVファイルを読み取り、
エージェントが高速参照できるJSON形式のKPIサマリーを出力する。

使い方:
  python3 kpi_cache_builder.py              # kpi_summary.json を生成
  python3 kpi_cache_builder.py --output /path/to/output.json
  python3 kpi_cache_builder.py --check      # キャッシュの鮮度チェックのみ

CSV → JSON 変換により、Sheets APIが使えない環境でもKPIデータに即座にアクセス可能。
"""

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
SHEETS_DIR = PROJECT_ROOT / "Master" / "sheets"

KPI_SHEET_ID = "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
REPORT_SHEET_ID = "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk"

DAILY_CSV = SHEETS_DIR / KPI_SHEET_ID / "スキルプラス（日別）.csv"
MONTHLY_CSV = SHEETS_DIR / KPI_SHEET_ID / "スキルプラス（月別）.csv"
REPORT_CSV = SHEETS_DIR / REPORT_SHEET_ID / "日報.csv"

DEFAULT_OUTPUT = SCRIPT_DIR / "data" / "kpi_summary.json"


def _parse_num(val: str) -> float:
    if not val:
        return 0
    try:
        return float(str(val).replace(",", "").replace("¥", "").replace("%", "").strip() or "0")
    except (ValueError, TypeError):
        return 0


def _read_monthly_csv() -> list[dict]:
    if not MONTHLY_CSV.exists():
        return []

    results = []
    with open(MONTHLY_CSV, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = None
        for row in reader:
            if not row or not row[0]:
                continue
            if row[0] == "月":
                header = row
                continue
            if header and len(row[0]) >= 7 and "-" in row[0]:
                entry = {"month": row[0]}
                for i, col_name in enumerate(header[1:], 1):
                    if i < len(row):
                        raw = row[i]
                        if "%" in raw:
                            entry[col_name] = _parse_num(raw)
                        elif "¥" in raw or col_name in ("売上", "広告費", "CPA", "CPO", "LTV", "粗利"):
                            entry[col_name] = int(_parse_num(raw))
                        else:
                            entry[col_name] = int(_parse_num(raw))
                results.append(entry)
    return results


def _read_daily_csv() -> tuple[list[dict], dict]:
    """日別CSVを読み、(recent_daily_totals, monthly_by_media) を返す"""
    if not DAILY_CSV.exists():
        return [], {}

    daily_totals = defaultdict(lambda: {"集客数": 0, "個別予約数": 0, "実施数": 0, "売上": 0, "広告費": 0})
    monthly_media = defaultdict(lambda: defaultdict(lambda: {"集客数": 0, "個別予約数": 0, "実施数": 0, "売上": 0, "広告費": 0}))

    with open(DAILY_CSV, encoding="utf-8") as f:
        reader = csv.reader(f)
        header = None
        col_map = {}
        for row in reader:
            if not row or not row[0]:
                continue
            if row[0] == "日付":
                header = row
                col_map = {h: i for i, h in enumerate(row)}
                continue
            if not header:
                continue

            dt = row[0]
            if len(dt) < 10 or dt[4] != "-":
                continue

            media = row[col_map.get("集客媒体", 2)] if col_map.get("集客媒体", 2) < len(row) else "不明"
            month_key = dt[:7]

            for key in ("集客数", "個別予約数", "実施数", "売上", "広告費"):
                idx = col_map.get(key)
                if idx is not None and idx < len(row):
                    val = _parse_num(row[idx])
                    daily_totals[dt][key] += val
                    monthly_media[month_key][media][key] += val

    # 直近7日の日別合計
    sorted_dates = sorted(daily_totals.keys(), reverse=True)[:7]
    recent_daily = []
    for dt in sorted_dates:
        d = daily_totals[dt]
        ad = d["広告費"]
        roas = round(d["売上"] / ad * 100, 1) if ad > 0 else 0
        recent_daily.append({
            "date": dt,
            "集客数": int(d["集客数"]),
            "個別予約数": int(d["個別予約数"]),
            "実施数": int(d["実施数"]),
            "売上": int(d["売上"]),
            "広告費": int(d["広告費"]),
            "ROAS": roas,
        })

    # 月別×媒体（直近3ヶ月）
    mbm = {}
    for mk in sorted(monthly_media.keys(), reverse=True)[:3]:
        mbm[mk] = {}
        for media, vals in monthly_media[mk].items():
            ad = vals["広告費"]
            roas = round(vals["売上"] / ad * 100, 1) if ad > 0 else 0
            mbm[mk][media] = {
                "集客数": int(vals["集客数"]),
                "個別予約数": int(vals["個別予約数"]),
                "売上": int(vals["売上"]),
                "広告費": int(vals["広告費"]),
                "ROAS": roas,
            }

    return recent_daily, mbm


def _read_report_csv() -> dict:
    """広告チーム日報CSVから当月のサマリーを取得"""
    if not REPORT_CSV.exists():
        return {}

    with open(REPORT_CSV, encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)

    if len(rows) < 10:
        return {}

    header = rows[0] if rows else []
    result = {}

    row_map = {}
    for r in rows:
        if len(r) >= 3:
            key = r[2].strip() if r[2] else ""
            if key and key not in row_map:
                row_map[key] = r

    for label, out_key in [
        ("着金売上（確定ベース）", "着金売上"),
        ("広告費（新井さん集計待ち）", "広告費"),
        ("集客数", "集客数"),
        ("個別予約数", "個別予約数"),
    ]:
        row = row_map.get(label)
        if not row:
            continue
        month_total = row[4] if len(row) > 4 else ""
        month_target = row[3] if len(row) > 3 else ""
        result[out_key] = {
            "月間目標": month_target,
            "月間実績": month_total,
        }
        latest_val = ""
        latest_col = ""
        for i in range(len(row) - 1, 4, -1):
            if row[i] and row[i].strip():
                latest_val = row[i]
                latest_col = header[i] if i < len(header) else ""
                break
        if latest_val:
            result[out_key]["直近日"] = latest_col
            result[out_key]["直近値"] = latest_val

    return result


def build_cache(output_path: Path = None) -> dict:
    """CSVからKPIサマリーJSONを構築"""
    monthly = _read_monthly_csv()
    recent_daily, monthly_by_media = _read_daily_csv()
    report_summary = _read_report_csv()

    cache = {
        "monthly": monthly,
        "monthly_by_media": monthly_by_media,
        "recent_daily": recent_daily,
        "report_summary": report_summary,
        "updated_at": datetime.now().isoformat(),
        "source": "csv_cache",
    }

    out = output_path or DEFAULT_OUTPUT
    out.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ KPIキャッシュ生成完了: {out}")
    print(f"   月別: {len(monthly)}ヶ月 / 日別: {len(recent_daily)}日 / 媒体別: {len(monthly_by_media)}ヶ月")
    if report_summary:
        print(f"   日報サマリー: {', '.join(report_summary.keys())}")

    return cache


def check_cache(output_path: Path = None) -> bool:
    """キャッシュの鮮度チェック。24時間以内なら True"""
    out = output_path or DEFAULT_OUTPUT
    if not out.exists():
        print("❌ キャッシュファイルなし")
        return False
    try:
        cache = json.loads(out.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(cache.get("updated_at", "2000-01-01"))
        age_hours = (datetime.now() - updated).total_seconds() / 3600
        if age_hours < 24:
            print(f"✅ キャッシュ有効（{age_hours:.1f}時間前に更新）")
            return True
        else:
            print(f"⚠️ キャッシュ期限切れ（{age_hours:.1f}時間前に更新）")
            return False
    except Exception as e:
        print(f"❌ キャッシュ読み取りエラー: {e}")
        return False


if __name__ == "__main__":
    if "--check" in sys.argv:
        output = None
        for i, a in enumerate(sys.argv):
            if a == "--output" and i + 1 < len(sys.argv):
                output = Path(sys.argv[i + 1])
        check_cache(output)
    else:
        output = None
        for i, a in enumerate(sys.argv):
            if a == "--output" and i + 1 < len(sys.argv):
                output = Path(sys.argv[i + 1])
        build_cache(output)
