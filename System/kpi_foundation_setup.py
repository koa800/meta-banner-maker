#!/usr/bin/env python3
"""Provision the KPI foundation spreadsheet."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "System"))

from sheets_manager import get_client  # noqa: E402


DEFAULT_TITLE = "【アドネス株式会社】KPI基盤（正本）"


@dataclass(frozen=True)
class WorksheetSpec:
    title: str
    rows: int
    cols: int
    values: list[list[str]]
    freeze_rows: int = 1
    table_header: bool = True


def _col_letter(col_count: int) -> str:
    result = ""
    value = col_count
    while value > 0:
        value, remainder = divmod(value - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _pad_rows(rows: list[list[str]], col_count: int) -> list[list[str]]:
    return [row + [""] * (col_count - len(row)) for row in rows]


def _sheet_is_effectively_empty(ws) -> bool:
    values = ws.get("A1:C5", value_render_option="FORMATTED_VALUE")
    for row in values:
        for cell in row:
            if str(cell).strip():
                return False
    return True


def _is_default_sheet_name(title: str) -> bool:
    return title in {"Sheet1", "シート1", "Sheet2", "シート2"}


def _resize_if_needed(ws, rows: int, cols: int) -> None:
    target_rows = max(rows, ws.row_count)
    target_cols = max(cols, ws.col_count)
    if target_rows != ws.row_count or target_cols != ws.col_count:
        ws.resize(rows=target_rows, cols=target_cols)


def _build_readme_rows(sheet_url: str) -> list[list[str]]:
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    return [
        ["【アドネス株式会社】KPI基盤（正本）"],
        ["作成日時", created_at],
        ["URL", sheet_url],
        ["目的", "Lookerや日報ではなく、一次データから5KPIを再現する正本を持つ"],
        [],
        ["レイヤー", "役割", "代表タブ", "補足"],
        ["raw", "元データの取込入口", "raw_ads_* / raw_funnel_events / raw_payments / raw_membership", "人が見やすい形ではなく、欠損なく持つ"],
        ["fact/master", "機械可読な正本", "route_master / 導線データ / 媒体×CR×LPデータ / 顧客マスタ", "会議資料や日報はここから作る"],
        ["view", "表示用", "kpi_daily / exec_dashboard", "ROAS / CPA / CPO はここで計算する"],
        [],
        ["5KPI", "定義", "正本粒度", "一次データ"],
        ["集客数", "導線に lead が成立した有効件数", "導線データ 1イベント1行", "UTAGE / Lステップ / Mailchimp / フォーム"],
        ["個別予約数", "個別相談の予約確定件数", "導線データ 1イベント1行", "UTAGE / Lステップ / 面談DB / 予約システム"],
        ["着金売上", "実際に着金した金額", "raw_payments 1取引1行", "Univapay / MOSH / Invoy / 銀行振込 / 返金管理"],
        ["広告費", "媒体で実際に消化した費用", "媒体×CR×LPデータ 1日×1route_key", "Meta / Google / TikTok / X"],
        ["会員純増", "入会 - クーリングオフ - 中途解約", "raw_membership 1状態変化1行", "会員管理元データ / 解約管理 / 返金管理"],
        [],
        ["次の投入順", "理由"],
        ["1. raw_payments", "着金売上は一次データが比較的明確で、早く正確に固めやすい"],
        ["2. raw_ads_*", "広告費も一次データが明確で、ROASの土台になる"],
        ["3. raw_funnel_events", "lead / booking の定義を固める"],
        ["4. raw_membership", "最後に会員純増を統合する"],
        [],
        ["注意", "Looker / 日報 / 数値管理シート / 会議資料は表示層であり、このシートの正本ではない"],
    ]


def _dashboard_rows() -> list[list[str]]:
    return [
        ["KPIダッシュボード", "", "", "", ""],
        ["最新集計日", '=IFERROR(TEXT(INDEX(FILTER(kpi_daily!A2:A,kpi_daily!A2:A<>""),COUNTA(FILTER(kpi_daily!A2:A,kpi_daily!A2:A<>""))),"yyyy-mm-dd"),"")', "", "", ""],
        ["", "", "", "", ""],
        ["指標", "最新値", "計算ルール", "入力元", "状態"],
        ["集客数", '=IFERROR(INDEX(FILTER(kpi_daily!B2:B,kpi_daily!B2:B<>""),COUNTA(FILTER(kpi_daily!B2:B,kpi_daily!B2:B<>""))),"")', "lead の件数", "導線データ", "構築待ち"],
        ["個別予約数", '=IFERROR(INDEX(FILTER(kpi_daily!C2:C,kpi_daily!C2:C<>""),COUNTA(FILTER(kpi_daily!C2:C,kpi_daily!C2:C<>""))),"")', "booking の件数", "導線データ", "構築待ち"],
        ["着金売上", '=IFERROR(INDEX(FILTER(kpi_daily!D2:D,kpi_daily!D2:D<>""),COUNTA(FILTER(kpi_daily!D2:D,kpi_daily!D2:D<>""))),"")', "実着金合計", "raw_payments", "構築待ち"],
        ["広告費", '=IFERROR(INDEX(FILTER(kpi_daily!E2:E,kpi_daily!E2:E<>""),COUNTA(FILTER(kpi_daily!E2:E,kpi_daily!E2:E<>""))),"")', "実消化費用", "媒体×CR×LPデータ", "構築待ち"],
        ["会員純増", '=IFERROR(INDEX(FILTER(kpi_daily!I2:I,kpi_daily!I2:I<>""),COUNTA(FILTER(kpi_daily!I2:I,kpi_daily!I2:I<>""))),"")', "join - cancel - cooling_off", "raw_membership", "構築待ち"],
        ["ROAS", '=IFERROR(INDEX(FILTER(kpi_daily!J2:J,kpi_daily!J2:J<>""),COUNTA(FILTER(kpi_daily!J2:J,kpi_daily!J2:J<>""))),"")', "着金売上 / 広告費", "kpi_daily", "自動計算"],
        ["CPA", '=IFERROR(INDEX(FILTER(kpi_daily!K2:K,kpi_daily!K2:K<>""),COUNTA(FILTER(kpi_daily!K2:K,kpi_daily!K2:K<>""))),"")', "広告費 / 集客数", "kpi_daily", "自動計算"],
        ["CPO", '=IFERROR(INDEX(FILTER(kpi_daily!L2:L,kpi_daily!L2:L<>""),COUNTA(FILTER(kpi_daily!L2:L,kpi_daily!L2:L<>""))),"")', "広告費 / 個別予約数", "kpi_daily", "自動計算"],
    ]


def build_specs(sheet_url: str) -> list[WorksheetSpec]:
    return [
        WorksheetSpec(
            title="README",
            rows=40,
            cols=4,
            values=_build_readme_rows(sheet_url),
            freeze_rows=0,
            table_header=False,
        ),
        WorksheetSpec(
            title="raw_ads_meta",
            rows=1000,
            cols=20,
            values=[[
                "date", "account_name", "campaign_id", "campaign_name", "adset_id",
                "adset_name", "ad_id", "ad_name", "route_key", "spend",
                "impressions", "clicks", "landing_views", "leads", "bookings",
                "cash_revenue", "source_file", "source_date", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_ads_google",
            rows=1000,
            cols=20,
            values=[[
                "date", "account_name", "campaign_id", "campaign_name", "ad_group_id",
                "ad_group_name", "ad_id", "ad_name", "route_key", "spend",
                "impressions", "clicks", "landing_views", "leads", "bookings",
                "cash_revenue", "source_file", "source_date", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_ads_tiktok",
            rows=1000,
            cols=20,
            values=[[
                "date", "account_name", "campaign_id", "campaign_name", "adgroup_id",
                "adgroup_name", "ad_id", "ad_name", "route_key", "spend",
                "impressions", "clicks", "landing_views", "leads", "bookings",
                "cash_revenue", "source_file", "source_date", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_ads_x",
            rows=1000,
            cols=20,
            values=[[
                "date", "account_name", "campaign_id", "campaign_name", "line_item_id",
                "line_item_name", "ad_id", "ad_name", "route_key", "spend",
                "impressions", "clicks", "landing_views", "leads", "bookings",
                "cash_revenue", "source_file", "source_date", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_funnel_events",
            rows=2000,
            cols=20,
            values=[[
                "event_id", "occurred_at", "event_date", "event_type", "customer_key",
                "email", "phone", "line_name", "source_system", "source_event_id",
                "route_key", "media", "funnel", "cr_name", "lp_name",
                "landing_url", "status", "value_jpy", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_payments",
            rows=2000,
            cols=23,
            values=[[
                "payment_id", "paid_at", "paid_date", "payment_system", "business_category",
                "media", "funnel", "product_type", "product_name", "original_product_name",
                "customer_key", "email", "phone", "line_name", "full_name",
                "full_name_kana", "gross_amount", "refund_amount", "net_amount", "route_key",
                "source_file", "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="raw_membership",
            rows=2000,
            cols=17,
            values=[[
                "membership_event_id", "occurred_at", "event_date", "customer_key", "email",
                "phone", "line_name", "product_name", "membership_plan", "event_type",
                "event_status", "quantity", "route_key", "source_system", "source_file",
                "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="route_master",
            rows=500,
            cols=15,
            values=[[
                "route_key", "media", "funnel", "cr_name", "cr_id",
                "lp_name", "lp_id", "primary_line_account", "landing_url", "seminar_name",
                "booking_type", "owner", "status", "start_date", "note",
            ]],
        ),
        WorksheetSpec(
            title="導線データ",
            rows=3000,
            cols=17,
            values=[[
                "event_id", "event_date", "occurred_at", "event_type", "user_id",
                "customer_key", "route_key", "media", "funnel", "cr_name",
                "lp_name", "source_system", "source_record_id", "value_jpy", "status",
                "imported_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="媒体×CR×LPデータ",
            rows=2000,
            cols=18,
            values=[[
                "date", "route_key", "media", "funnel", "cr_name",
                "lp_name", "ad_spend", "impressions", "clicks", "landing_views",
                "leads", "bookings", "attends", "cash_revenue", "refund_amount",
                "member_join", "member_cancel", "note",
            ]],
        ),
        WorksheetSpec(
            title="顧客マスタ",
            rows=3000,
            cols=20,
            values=[[
                "user_id", "customer_key", "email", "phone", "line_name",
                "current_stage", "first_route_key", "latest_route_key", "first_lead_at", "first_booking_at",
                "latest_booking_at", "latest_attend_at", "first_paid_at", "latest_paid_at", "total_cash_revenue",
                "total_refund_amount", "membership_status", "membership_started_at", "membership_ended_at", "note",
            ]],
        ),
        WorksheetSpec(
            title="kpi_daily",
            rows=1000,
            cols=13,
            values=[[
                "date", "leads", "bookings", "cash_revenue", "ad_spend",
                "member_join", "member_cancel", "member_cooling_off", "member_net", "roas",
                "cpa", "cpo", "note",
            ]],
        ),
        WorksheetSpec(
            title="exec_dashboard",
            rows=60,
            cols=5,
            values=_dashboard_rows(),
            freeze_rows=4,
            table_header=False,
        ),
    ]


def _apply_table_style(spreadsheet, ws, col_count: int, freeze_rows: int) -> None:
    if freeze_rows:
        ws.freeze(rows=freeze_rows)
    spreadsheet.batch_update({
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.98},
                            "textFormat": {"bold": True},
                            "wrapStrategy": "WRAP",
                            "verticalAlignment": "MIDDLE",
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment",
                }
            },
            {
                "setBasicFilter": {
                    "filter": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 0,
                            "endRowIndex": ws.row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": col_count,
                        }
                    }
                }
            },
        ]
    })


def _apply_readme_style(spreadsheet, ws) -> None:
    spreadsheet.batch_update({
        "requests": [
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
                            "textFormat": {"bold": True, "fontSize": 16},
                        }
                    },
                    "fields": "userEnteredFormat.textFormat",
                }
            }
        ]
    })


def _apply_dashboard_style(spreadsheet, ws) -> None:
    spreadsheet.batch_update({
        "requests": [
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True, "fontSize": 16},
                        }
                    },
                    "fields": "userEnteredFormat.textFormat",
                }
            },
            {
                "repeatCell": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 3,
                        "endRowIndex": 4,
                        "startColumnIndex": 0,
                        "endColumnIndex": 5,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.92, "green": 0.95, "blue": 0.98},
                            "textFormat": {"bold": True},
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat",
                }
            },
        ]
    })
    ws.freeze(rows=4)


def _ensure_worksheet(spreadsheet, spec: WorksheetSpec, rewrite: bool) -> None:
    try:
        ws = spreadsheet.worksheet(spec.title)
    except Exception:
        ws = spreadsheet.add_worksheet(title=spec.title, rows=spec.rows, cols=spec.cols)

    _resize_if_needed(ws, spec.rows, spec.cols)

    if rewrite or _sheet_is_effectively_empty(ws):
        values = _pad_rows(spec.values, spec.cols)
        end_cell = f"{_col_letter(spec.cols)}{len(values)}"
        ws.clear()
        ws.update(range_name=f"A1:{end_cell}", values=values, value_input_option="USER_ENTERED")

    if spec.title == "README":
        _apply_readme_style(spreadsheet, ws)
    elif spec.title == "exec_dashboard":
        _apply_dashboard_style(spreadsheet, ws)
    elif spec.table_header:
        _apply_table_style(spreadsheet, ws, spec.cols, spec.freeze_rows)


def _ensure_readme_worksheet(spreadsheet, rewrite: bool) -> None:
    specs = build_specs(spreadsheet.url)
    readme_spec = next(spec for spec in specs if spec.title == "README")

    try:
        ws = spreadsheet.worksheet("README")
    except Exception:
        all_sheets = spreadsheet.worksheets()
        if len(all_sheets) == 1 and _is_default_sheet_name(all_sheets[0].title):
            ws = all_sheets[0]
            ws.update_title("README")
        else:
            ws = spreadsheet.add_worksheet(title="README", rows=readme_spec.rows, cols=readme_spec.cols)
    _resize_if_needed(ws, readme_spec.rows, readme_spec.cols)

    if rewrite or _sheet_is_effectively_empty(ws):
        values = _pad_rows(readme_spec.values, readme_spec.cols)
        end_cell = f"{_col_letter(readme_spec.cols)}{len(values)}"
        ws.clear()
        ws.update(range_name=f"A1:{end_cell}", values=values, value_input_option="USER_ENTERED")
    _apply_readme_style(spreadsheet, ws)


def _find_existing_spreadsheet(client, title: str):
    files = client.list_spreadsheet_files(title=title)
    for item in files:
        if item.get("name") == title:
            return client.open_by_key(item["id"])
    return None


def _cleanup_default_sheets(spreadsheet) -> None:
    for ws in spreadsheet.worksheets():
        if _is_default_sheet_name(ws.title) and _sheet_is_effectively_empty(ws):
            try:
                spreadsheet.del_worksheet(ws)
            except Exception:
                pass


def provision_spreadsheet(title: str, sheet_id: str | None, account: str | None, rewrite: bool) -> str:
    client = get_client(account)
    if sheet_id:
        spreadsheet = client.open_by_key(sheet_id)
    else:
        spreadsheet = _find_existing_spreadsheet(client, title)
        if spreadsheet is None:
            spreadsheet = client.create(title)
            try:
                spreadsheet.share("gwsadmin@team.addness.co.jp", perm_type="user", role="writer", notify=False)
            except Exception:
                pass

    _ensure_readme_worksheet(spreadsheet, rewrite=rewrite)

    for spec in build_specs(spreadsheet.url):
        if spec.title == "README":
            continue
        _ensure_worksheet(spreadsheet, spec, rewrite=rewrite)

    _cleanup_default_sheets(spreadsheet)

    return spreadsheet.id


def main() -> int:
    parser = argparse.ArgumentParser(description="KPI基盤スプレッドシートの初期構築")
    parser.add_argument("--title", default=DEFAULT_TITLE, help="作成するスプレッドシート名")
    parser.add_argument("--sheet-id", help="既存シートを初期化する場合のID")
    parser.add_argument("--account", help="sheets_manager で使うアカウント名")
    parser.add_argument("--rewrite", action="store_true", help="既存タブがあってもテンプレートを書き直す")
    args = parser.parse_args()

    sheet_id = provision_spreadsheet(
        title=args.title,
        sheet_id=args.sheet_id,
        account=args.account,
        rewrite=args.rewrite,
    )
    print(f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
