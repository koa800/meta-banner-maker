#!/usr/bin/env python3
"""
ダウンロードした請求書 PDF からオフライン広告費を抽出し、
`【アドネス株式会社】広告データ（収集） / オフライン` へ追加する。

対応している PDF:
- LAGF 株式会社の交通広告 invoice
- 株式会社Riche Lab の TOKYO MX 請求書

方針:
- 既存のオフライン raw の粒度に合わせる
- LAGF は明細単位で 1 行ずつ追加する
- Riche Lab は TOKYO MX 月次 1 行として追加する
- 既存行と重複する場合はスキップする
"""

from __future__ import annotations

import argparse
import calendar
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sheets_manager import get_client

from import_offline_ads_to_sheet import (
    TARGET_HEADERS,
    TARGET_SPREADSHEET_ID,
    TARGET_TAB_NAME,
    build_key,
    ensure_target_header,
    load_existing_keys,
)


DOWNLOADS_DIR = Path("/Users/koa800/Downloads")

LAGF_PLACEMENT_MAP = {
    "北大阪急行": ("交通広告", "⼤阪／北⼤阪急⾏"),
    "JR西日本(快速)": ("交通広告", "⼤阪／JR⻄⽇本(快速)"),
}


@dataclass
class OfflineRecord:
    発生日: str
    集客媒体: str
    企画名: str
    出稿場所: str
    掲載期間: str
    広告費: int
    取込日時: str
    備考: str = ""

    def to_row(self) -> list[str | int]:
        return [
            self.発生日,
            self.集客媒体,
            self.企画名,
            self.出稿場所,
            self.掲載期間,
            self.広告費,
            self.取込日時,
            self.備考,
        ]


def extract_pdf_text(pdf_path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", str(pdf_path), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def normalize_ws_value(value: str) -> str:
    return (value or "").strip()


def load_existing_periods(ws) -> dict[tuple[str, str], str]:
    values = ws.get_all_values()
    if not values:
        return {}
    rows = values[1:]
    period_map: dict[tuple[str, str], tuple[str, str]] = {}
    for row in rows:
        padded = row + [""] * (len(TARGET_HEADERS) - len(row))
        key = (normalize_ws_value(padded[2]), normalize_ws_value(padded[3]))
        if not key[0] or not key[1] or not normalize_ws_value(padded[4]):
            continue
        date_text = normalize_ws_value(padded[0])
        current = period_map.get(key)
        if current is None or date_text > current[0]:
            period_map[key] = (date_text, normalize_ws_value(padded[4]))
    return {key: period for key, (_, period) in period_map.items()}


def first_day_previous_month(year: int, month: int) -> str:
    if month == 1:
        return f"{year - 1}-12-01"
    return f"{year}-{month - 1:02d}-01"


def month_period_text(year: int, month: int) -> str:
    last_day = calendar.monthrange(year, month)[1]
    return f"{month}月1日〜{month}月{last_day}日"


def parse_lagf(pdf_path: Path, text: str, period_map: dict[tuple[str, str], str], now_text: str) -> list[OfflineRecord]:
    if "LAGF株式会社" not in text:
        return []

    date_match = re.search(r"(\d{4}\.\d{2}\.\d{2})", text)
    if not date_match:
        raise ValueError(f"LAGF請求書の日付を取得できません: {pdf_path.name}")
    invoice_date = datetime.strptime(date_match.group(1), "%Y.%m.%d").strftime("%Y-%m-%d")

    lines = [line.strip() for line in text.splitlines()]
    records: list[OfflineRecord] = []
    for i, line in enumerate(lines):
        if "月分）" not in line:
            continue
        placement = None
        for needle in LAGF_PLACEMENT_MAP:
            if needle in line:
                placement = needle
                break
        if placement is None:
            continue

        pre_tax = None
        for next_line in lines[i + 1 : i + 8]:
            cleaned = next_line.replace(",", "")
            if cleaned.isdigit():
                pre_tax = int(cleaned)
                break
        if pre_tax is None:
            raise ValueError(f"LAGF請求書の金額を取得できません: {pdf_path.name} / {line}")

        企画名, 出稿場所 = LAGF_PLACEMENT_MAP[placement]
        掲載期間 = period_map.get((企画名, 出稿場所), "")
        if not 掲載期間:
            raise ValueError(f"既存オフライン行から掲載期間を引けません: {企画名} / {出稿場所}")

        records.append(
            OfflineRecord(
                発生日=invoice_date,
                集客媒体="オフライン広告",
                企画名=企画名,
                出稿場所=出稿場所,
                掲載期間=掲載期間,
                広告費=int(pre_tax * 1.1),
                取込日時=now_text,
            )
        )
    return records


def parse_richelab(pdf_path: Path, text: str, now_text: str) -> list[OfflineRecord]:
    if "株式会社Riche Lab" not in text:
        return []

    month_match = re.search(r"TOKYO MXのCM放映\((\d{4})年(\d{1,2})月分\)", text)
    if not month_match:
        return []

    year = int(month_match.group(1))
    month = int(month_match.group(2))
    amount_match = re.search(r"ご請求金額\s+¥?([\d,]+)", text)
    if not amount_match:
        amount_match = re.search(r"請求額\s+([\d,]+)", text)
    if not amount_match:
        raise ValueError(f"Riche Lab請求書の請求額を取得できません: {pdf_path.name}")

    amount = int(amount_match.group(1).replace(",", ""))
    return [
        OfflineRecord(
            発生日=first_day_previous_month(year, month),
            集客媒体="オフライン広告",
            企画名="TOKYO MXのCM",
            出稿場所="TOKYO MX",
            掲載期間=month_period_text(year, month),
            広告費=amount,
            取込日時=now_text,
        )
    ]


def parse_pdf(pdf_path: Path, period_map: dict[tuple[str, str], str], now_text: str) -> list[OfflineRecord]:
    text = extract_pdf_text(pdf_path)
    lagf_records = parse_lagf(pdf_path, text, period_map, now_text)
    if lagf_records:
        return lagf_records
    riche_records = parse_richelab(pdf_path, text, now_text)
    if riche_records:
        return riche_records
    return []


def default_pdf_paths() -> list[Path]:
    patterns = [
        "【Invoice】アドネス様_2026.01.pdf",
        "【Invoice】アドネス様_2026.02.pdf",
        "2026年2月分コンサルティング費‗アドネス株式会社様（株式会社RicheLab）.pdf",
        "2026年3月分コンサルティング費‗アドネス株式会社様（株式会社RicheLab） (1).pdf",
        "2026年4月分コンサルティング費‗アドネス株式会社様（株式会社RicheLab）.pdf",
    ]
    return [DOWNLOADS_DIR / name for name in patterns]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-sheet-id", default=TARGET_SPREADSHEET_ID)
    parser.add_argument("--target-tab", default=TARGET_TAB_NAME)
    parser.add_argument("pdfs", nargs="*", help="取り込む PDF のパス。未指定時は今日の5件を使う")
    args = parser.parse_args()

    pdf_paths = [Path(p).expanduser() for p in args.pdfs] if args.pdfs else default_pdf_paths()
    missing = [str(path) for path in pdf_paths if not path.exists()]
    if missing:
        raise FileNotFoundError("PDF が見つかりません: " + ", ".join(missing))

    client = get_client("kohara")
    target_sh = client.open_by_key(args.target_sheet_id)
    try:
        target_ws = target_sh.worksheet(args.target_tab)
    except Exception:
        target_ws = target_sh.add_worksheet(title=args.target_tab, rows=1000, cols=len(TARGET_HEADERS))

    ensure_target_header(target_ws)
    existing_keys = load_existing_keys(target_ws)
    period_map = load_existing_periods(target_ws)
    now_text = datetime.now().strftime("%Y/%m/%d %H:%M")

    append_rows: list[list[str | int]] = []
    added = 0
    skipped = 0
    details: list[str] = []

    for pdf_path in pdf_paths:
        records = parse_pdf(pdf_path, period_map, now_text)
        if not records:
            details.append(f"{pdf_path.name}: 対応外")
            continue

        file_added = 0
        file_skipped = 0
        for record in records:
            key = build_key(
                {
                    "発生日": record.発生日,
                    "企画名": record.企画名,
                    "出稿場所": record.出稿場所,
                    "掲載期間": record.掲載期間,
                    "広告費": record.広告費,
                }
            )
            if key in existing_keys:
                skipped += 1
                file_skipped += 1
                continue
            existing_keys.add(key)
            append_rows.append(record.to_row())
            added += 1
            file_added += 1
        details.append(f"{pdf_path.name}: 追加 {file_added} / 重複 {file_skipped}")

    if append_rows:
        target_ws.append_rows(append_rows, value_input_option="USER_ENTERED")

    print(f"PDF取込: 追加 {added} 件 / 重複スキップ {skipped} 件 / 対象PDF {len(pdf_paths)} 件")
    for line in details:
        print(line)


if __name__ == "__main__":
    main()
