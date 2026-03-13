#!/usr/bin/env python3
"""Import payment history CSV into KPI foundation raw_payments and kpi_daily."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
import hashlib
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "System"))

from sheets_manager import get_client  # noqa: E402


DEFAULT_SHEET_ID = "1w-eFCzbGjgmoiuZe54X49BVZw46vm7hg6_CXI7f_gmw"
DEFAULT_CSV_PATH = Path("/Users/koa800/Desktop/過去のCVSデータ/決済履歴シート/全決済履歴シート_決済履歴_表.csv")
RAW_TAB = "raw_payments"
KPI_DAILY_TAB = "kpi_daily"

RAW_HEADER = [
    "payment_id", "paid_at", "paid_date", "payment_system", "business_category",
    "media", "funnel", "product_type", "product_name", "original_product_name",
    "customer_key", "email", "phone", "line_name", "full_name",
    "full_name_kana", "gross_amount", "refund_amount", "net_amount", "route_key",
    "source_file", "imported_at", "note",
]

KPI_DAILY_HEADER = [
    "date", "leads", "bookings", "cash_revenue", "ad_spend",
    "member_join", "member_cancel", "member_cooling_off", "member_net", "roas",
    "cpa", "cpo", "note",
]


def _col_letter(col_count: int) -> str:
    result = ""
    value = col_count
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _clean_email(value: str) -> str:
    value = str(value or "").strip()
    if not value or value == "-":
        return ""
    return value.split(",")[0].strip().lower()


def _clean_text(value: str) -> str:
    value = str(value or "").strip()
    return "" if value == "-" else value


def _normalize_date(value: str) -> str:
    value = _clean_text(value)
    if not value:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return value


def _normalize_amount(value: str) -> int:
    digits = re.sub(r"[^\d-]", "", str(value or ""))
    if not digits:
        return 0
    try:
        return int(digits)
    except ValueError:
        return 0


def _make_payment_id(row: list[str]) -> str:
    raw = "|".join(row)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def load_payment_records(csv_path: Path) -> tuple[list[list[str]], dict[str, int]]:
    with csv_path.open(encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        headers = next(reader)
        index = {name.strip(): i for i, name in enumerate(headers)}

        records: list[list[str]] = []
        daily_revenue: dict[str, int] = {}
        imported_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for row in reader:
            paid_at = _clean_text(row[index["日付"]]) if index.get("日付") is not None else ""
            paid_date = _normalize_date(paid_at)
            payment_system = _clean_text(row[index["決済方法"]]) if index.get("決済方法") is not None else ""
            business_category = _clean_text(row[index["大カテゴリ"]]) if index.get("大カテゴリ") is not None else ""
            media = _clean_text(row[index["集客媒体"]]) if index.get("集客媒体") is not None else ""
            funnel = _clean_text(row[index["ファネル名"]]) if index.get("ファネル名") is not None else ""
            product_type = _clean_text(row[index["商品種類"]]) if index.get("商品種類") is not None else ""
            product_name = _clean_text(row[index["商品名"]]) if index.get("商品名") is not None else ""
            original_product_name = _clean_text(row[index["修正前商品名"]]) if index.get("修正前商品名") is not None else ""
            email = _clean_email(row[index["メールアドレス"]]) if index.get("メールアドレス") is not None else ""
            line_name = _clean_text(row[index["LINE名"]]) if index.get("LINE名") is not None else ""
            full_name = _clean_text(row[index["氏名"]]) if index.get("氏名") is not None else ""
            full_name_kana = _clean_text(row[index["カタカナ名"]]) if index.get("カタカナ名") is not None else ""
            gross_amount = _normalize_amount(row[index["着金売上"]]) if index.get("着金売上") is not None else 0
            customer_key = email or line_name or full_name
            route_key = ""

            record = [
                _make_payment_id(row),
                paid_at,
                paid_date,
                payment_system,
                business_category,
                media,
                funnel,
                product_type,
                product_name,
                original_product_name,
                customer_key,
                email,
                "",
                line_name,
                full_name,
                full_name_kana,
                str(gross_amount),
                "0",
                str(gross_amount),
                route_key,
                csv_path.name,
                imported_at,
                "",
            ]
            records.append(record)

            if paid_date:
                daily_revenue[paid_date] = daily_revenue.get(paid_date, 0) + gross_amount

    records.sort(key=lambda item: (item[2], item[0]))
    return records, daily_revenue


def _write_tab(ws, header: list[str], rows: list[list[str]]) -> None:
    ws.clear()
    values = [header] + rows
    end_col = _col_letter(len(header))
    ws.resize(rows=max(len(values) + 50, ws.row_count), cols=max(len(header), ws.col_count))

    chunk_size = 5000
    updates = [{"range": f"A1:{end_col}1", "values": [header]}]
    for start in range(0, len(rows), chunk_size):
        chunk = rows[start:start + chunk_size]
        row_start = start + 2
        row_end = row_start + len(chunk) - 1
        updates.append({"range": f"A{row_start}:{end_col}{row_end}", "values": chunk})
    ws.batch_update(updates, value_input_option="USER_ENTERED")


def build_kpi_daily_rows(daily_revenue: dict[str, int]) -> list[list[str]]:
    rows = []
    for date_key in sorted(daily_revenue):
        rows.append([
            date_key,
            "",
            "",
            str(daily_revenue[date_key]),
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "payments_only",
        ])
    return rows


def import_payments(sheet_id: str, csv_path: Path, account: str | None) -> tuple[int, int]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSVが見つかりません: {csv_path}")

    records, daily_revenue = load_payment_records(csv_path)

    client = get_client(account)
    spreadsheet = client.open_by_key(sheet_id)
    raw_ws = spreadsheet.worksheet(RAW_TAB)
    kpi_daily_ws = spreadsheet.worksheet(KPI_DAILY_TAB)

    _write_tab(raw_ws, RAW_HEADER, records)
    _write_tab(kpi_daily_ws, KPI_DAILY_HEADER, build_kpi_daily_rows(daily_revenue))

    try:
        raw_ws.freeze(rows=1)
        kpi_daily_ws.freeze(rows=1)
    except Exception:
        pass

    return len(records), len(daily_revenue)


def main() -> int:
    parser = argparse.ArgumentParser(description="決済履歴CSVを KPI 基盤へ反映する")
    parser.add_argument("--sheet-id", default=DEFAULT_SHEET_ID, help="反映先のKPI基盤シートID")
    parser.add_argument("--csv", default=str(DEFAULT_CSV_PATH), help="決済履歴CSVのパス")
    parser.add_argument("--account", help="sheets_manager で使うアカウント名")
    args = parser.parse_args()

    records, days = import_payments(
        sheet_id=args.sheet_id,
        csv_path=Path(args.csv),
        account=args.account,
    )
    print(f"raw_payments rows: {records}")
    print(f"kpi_daily revenue dates: {days}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
