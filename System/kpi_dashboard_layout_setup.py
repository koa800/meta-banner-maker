#!/usr/bin/env python3
"""
【アドネス株式会社】KPIダッシュボードの最小構成を整える。

方針:
- ダッシュボードは表示層に徹する
- 第1版は `スキルプラス事業サマリー / 日別数値 / データソース管理` の3タブだけを表に出す
- 定義は `マスタデータ / 定義一覧` に集約する
- 保留中の詳細タブや派生タブは削除せず非表示にする
- まだ接続できない数値は空欄のままにする
"""

from __future__ import annotations

from datetime import datetime
import time
from typing import Dict, Iterable, List, Sequence

from gspread.exceptions import APIError
from sheets_manager import get_client


DASHBOARD_SHEET_ID = "1utCt9ex0puEi3-oxcjq9v37Jt-9X_dpSjPowZBsHeqA"
MASTER_DATA_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
EMAIL_METRICS_SHEET_ID = "13HS9KmlTdxQwMMaK45H3Ga1mMTUiJdhYKWnrExge_yY"
EMAIL_COUNT_TAB = "日別メール登録件数"
EMAIL_UU_TAB = "日別メール登録件数（UU）"
EMAIL_SUMMARY_TAB = "メール集計サマリー"
BOOKING_METRICS_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
BOOKING_COUNT_TAB = "日別個別予約数"
BOOKING_SUMMARY_TAB = "個別予約サマリー"
BOOKING_SOURCE_TAB = "データソース管理"
MEMBERSHIP_METRICS_SHEET_ID = "1OFKvyQsydPmTqd9MwSMX53MXxG9ASfkFquyf4PV-M8E"
MEMBERSHIP_DAILY_TAB = "日別会員数値"
MEMBERSHIP_SUMMARY_TAB = "会員サマリー"
MEMBERSHIP_SOURCE_TAB = "データソース管理"
AD_SPEND_METRICS_SHEET_ID = "1-dEYsY6KB0GF2XRf7PvoxVxhICCamdCBPKxHJRJdUOE"
AD_SPEND_DAILY_TAB = "日別広告費"
AD_SPEND_SUMMARY_TAB = "広告費サマリー"
AD_SPEND_SOURCE_TAB = "データソース管理"
PAYMENT_METRICS_SHEET_ID = "1eh8X_dsRitFDKAJVE-dbr75ycGfMffMsvJYI-Gtlv_Q"
PAYMENT_DAILY_TAB = "日別売上数値"
PAYMENT_SOURCE_TAB = "データソース管理"

TAB_SPECS = [
    ("スキルプラス事業サマリー", 120, 60),
    ("日別数値", 600, 22),
    ("データソース管理", 80, 14),
]

RENAME_TABS = {
    "事業サマリー": "スキルプラス事業サマリー",
}

HIDDEN_TABS = [
    "週別数値",
    "月別数値",
    "データソース管理_old",
    "集客内訳",
    "個別予約内訳",
    "売上・広告費内訳",
    "会員内訳",
    "更新状況",
]
REBUILD_TABS = {"スキルプラス事業サマリー"}
DEPRECATED_DASHBOARD_TABS = ["定義"]

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
TAB_COLORS = {
    "スキルプラス事業サマリー": "#1A73E8",
    "日別数値": "#1A73E8",
    "データソース管理": "#34A853",
}
STATUS_FORMATS = {
    "正常": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "接続中": {"backgroundColor": {"red": 0.851, "green": 0.918, "blue": 0.827}},
    "一部接続": {"backgroundColor": {"red": 1, "green": 0.949, "blue": 0.8}},
    "確認待ち": {"backgroundColor": {"red": 0.925, "green": 0.89, "blue": 0.992}},
    "未同期": {"backgroundColor": {"red": 1, "green": 0.949, "blue": 0.8}},
    "未接続": {"backgroundColor": {"red": 1, "green": 0.949, "blue": 0.8}},
    "停止": {"backgroundColor": {"red": 0.957, "green": 0.8, "blue": 0.8}},
}
WRITE_RETRY_SECONDS = (5, 10, 20, 40)
PROTECTED_EDITOR_EMAILS = [
    "kohara.kaito@team.addness.co.jp",
    "gwsadmin@team.addness.co.jp",
]
PROTECTION_PREFIX = "KPIダッシュボード自動生成"


def col_letter(col_num: int) -> str:
    result = ""
    while col_num > 0:
        col_num, rem = divmod(col_num - 1, 26)
        result = chr(65 + rem) + result
    return result


def repeat_cell_request(
    sheet_id: int,
    start_row: int,
    end_row: int,
    start_col: int,
    end_col: int,
    fmt: dict,
    fields: str,
) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {"userEnteredFormat": fmt},
            "fields": fields,
        }
    }


def set_column_width_request(sheet_id: int, start_col: int, end_col: int, width: int) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_col,
                "endIndex": end_col,
            },
            "properties": {"pixelSize": width},
            "fields": "pixelSize",
        }
    }


def set_column_hidden_request(sheet_id: int, start_col: int, end_col: int, hidden: bool) -> dict:
    return {
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "COLUMNS",
                "startIndex": start_col,
                "endIndex": end_col,
            },
            "properties": {"hiddenByUser": hidden},
            "fields": "hiddenByUser",
        }
    }


def add_line_chart_request(
    sheet_id: int,
    anchor_row: int,
    anchor_col: int,
    title: str,
    domain_col: int,
    series_cols: Sequence[int],
    source_sheet_id: int | None = None,
    end_row_index: int = 120,
    width: int = 620,
    height: int = 260,
) -> dict:
    source_id = source_sheet_id if source_sheet_id is not None else sheet_id
    return {
        "addChart": {
            "chart": {
                "spec": {
                    "title": title,
                    "basicChart": {
                        "chartType": "LINE",
                        "legendPosition": "BOTTOM_LEGEND",
                        "headerCount": 1,
                        "axis": [
                            {"position": "BOTTOM_AXIS", "title": "日付"},
                            {"position": "LEFT_AXIS", "title": "値"},
                        ],
                        "domains": [
                            {
                                "domain": {
                                    "sourceRange": {
                                        "sources": [
                                            {
                                                "sheetId": source_id,
                                                "startRowIndex": 0,
                                                "endRowIndex": end_row_index,
                                                "startColumnIndex": domain_col,
                                                "endColumnIndex": domain_col + 1,
                                            }
                                        ]
                                    }
                                }
                            }
                        ],
                        "series": [
                            {
                                "series": {
                                    "sourceRange": {
                                        "sources": [
                                            {
                                                "sheetId": source_id,
                                                "startRowIndex": 0,
                                                "endRowIndex": end_row_index,
                                                "startColumnIndex": col,
                                                "endColumnIndex": col + 1,
                                            }
                                        ]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            }
                            for col in series_cols
                        ],
                    },
                },
                "position": {
                    "overlayPosition": {
                        "anchorCell": {
                            "sheetId": sheet_id,
                            "rowIndex": anchor_row,
                            "columnIndex": anchor_col,
                        },
                        "offsetXPixels": 0,
                        "offsetYPixels": 0,
                        "widthPixels": width,
                        "heightPixels": height,
                    }
                },
            }
        }
    }


def set_sheet_properties_request(sheet_id: int, props: dict, fields: str) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {"sheetId": sheet_id, **props},
            "fields": fields,
        }
    }


def build_recent_day_formula(column_letter: str, offset: int, date_col_letter: str = "G") -> str:
    return (
        f'=IF(${date_col_letter}{offset + 3}="","",'
        f'INDEX(\'日別数値\'!${column_letter}$2:${column_letter},'
        f'MATCH(${date_col_letter}{offset + 3},\'日別数値\'!$A$2:$A,0)))'
    )


def build_recent_date_formula(offset: int) -> str:
    return (
        '=IFERROR(INDEX(SORT(FILTER(\'日別数値\'!$A$2:$A,'
        '\'日別数値\'!$A$2:$A<>""),1,FALSE),'
        f'{offset + 1}),"")'
    )


def list_chart_delete_requests(spreadsheet, sheet_id: int) -> List[dict]:
    metadata = spreadsheet.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties.sheetId,charts(chartId,spec.title))",
        }
    )
    requests: List[dict] = []
    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if properties.get("sheetId") != sheet_id:
            continue
        for chart in sheet.get("charts", []):
            chart_id = chart.get("chartId")
            if chart_id is None:
                continue
            requests.append({"deleteEmbeddedObject": {"objectId": chart_id}})
    return requests


def normalize_date(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    for fmt in ("%Y/%m/%d", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value[:19], fmt).strftime("%Y/%m/%d")
        except ValueError:
            continue
    return ""


TRANSIENT_SHEETS_STATUS_CODES = {429, 500, 502, 503, 504}
TRANSIENT_SHEETS_ERROR_MARKERS = (
    "quota exceeded",
    "resource_exhausted",
    "service is currently unavailable",
    "backend error",
    "internal error",
    "try again later",
)


def is_retryable_sheets_error(exc: APIError) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in TRANSIENT_SHEETS_STATUS_CODES:
        return True
    return any(marker in str(exc).lower() for marker in TRANSIENT_SHEETS_ERROR_MARKERS)


def is_retryable_sheets_message(message: str) -> bool:
    normalized = str(message).lower()
    if any(code in normalized for code in ("429", "500", "502", "503", "504")):
        return True
    return any(marker in normalized for marker in TRANSIENT_SHEETS_ERROR_MARKERS)


def run_write_with_retry(description: str, func):
    last_error = None
    waits = (0, *WRITE_RETRY_SECONDS)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except APIError as exc:
            if not is_retryable_sheets_error(exc) or attempt == len(waits):
                raise
            last_error = exc
            print(
                f"{description}: Sheets の一時エラーのため "
                f"{wait_seconds or 0}秒後に再試行します。"
            )
    if last_error:
        raise last_error


def batch_update_with_retry(spreadsheet, body: dict, description: str) -> None:
    run_write_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_write_with_retry(description, func)


def parse_int(raw: str) -> int:
    value = str(raw or "").replace(",", "").replace("¥", "").replace("円", "").strip()
    if not value:
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def get_all_values_with_retry(ws) -> List[List[str]]:
    last_error = None
    for _ in range(4):
        try:
            return ws.get_all_values()
        except Exception as exc:
            last_error = exc
            if not is_retryable_sheets_message(str(exc)):
                raise
            time.sleep(5)
    raise last_error


def load_email_daily_metrics(gc) -> List[dict]:
    spreadsheet = gc.open_by_key(EMAIL_METRICS_SHEET_ID)
    count_rows = get_all_values_with_retry(spreadsheet.worksheet(EMAIL_COUNT_TAB))
    uu_rows = get_all_values_with_retry(spreadsheet.worksheet(EMAIL_UU_TAB))

    metrics: Dict[str, dict] = {}
    for row in count_rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.setdefault(date, {"date": date, "count": 0, "uu_count": 0})
        metrics[date]["count"] = parse_int(row[1] if len(row) > 1 else "")

    for row in uu_rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.setdefault(date, {"date": date, "count": 0, "uu_count": 0})
        metrics[date]["uu_count"] = parse_int(row[1] if len(row) > 1 else "")

    return [metrics[key] for key in sorted(metrics.keys())]


def load_email_metrics_status(gc) -> Dict[str, str]:
    spreadsheet = gc.open_by_key(EMAIL_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(EMAIL_SUMMARY_TAB))
    result: Dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        value = str(row[1]).strip()
        if key:
            result[key] = value
    return result


def load_booking_daily_metrics(gc) -> List[dict]:
    spreadsheet = gc.open_by_key(BOOKING_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(BOOKING_COUNT_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append({"date": date, "count": parse_int(row[1] if len(row) > 1 else "")})
    return metrics


def load_booking_status(gc) -> Dict[str, str]:
    spreadsheet = gc.open_by_key(BOOKING_METRICS_SHEET_ID)
    summary_rows = get_all_values_with_retry(spreadsheet.worksheet(BOOKING_SUMMARY_TAB))
    source_rows = get_all_values_with_retry(spreadsheet.worksheet(BOOKING_SOURCE_TAB))

    result: Dict[str, str] = {}
    for row in summary_rows[1:]:
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        value = str(row[1]).strip()
        if key:
            result[key] = value.lstrip("'")

    for row in source_rows[1:]:
        if not row:
            continue
        key = str(row[0]).strip()
        if key == "個別予約数":
            result["ステータス"] = str(row[9]).strip() if len(row) > 9 else ""
            result["最終同期日"] = str(row[10]).strip().lstrip("'") if len(row) > 10 else ""
            result["更新数"] = str(row[11]).strip() if len(row) > 11 else ""
            result["エラー数"] = str(row[12]).strip() if len(row) > 12 else ""
            result["メモ"] = str(row[13]).strip() if len(row) > 13 else ""
            break
    return result


def load_membership_daily_metrics(gc) -> List[dict]:
    spreadsheet = gc.open_by_key(MEMBERSHIP_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(MEMBERSHIP_DAILY_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append(
            {
                "date": date,
                "member_count": parse_int(row[3] if len(row) > 3 else ""),
                "mid_term_cancel_count": parse_int(row[4] if len(row) > 4 else ""),
                "cooling_off_count": parse_int(row[2] if len(row) > 2 else ""),
            }
        )
    return metrics


def load_ad_spend_daily_metrics(gc) -> List[dict]:
    spreadsheet = gc.open_by_key(AD_SPEND_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_DAILY_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append({"date": date, "spend": parse_int(row[1] if len(row) > 1 else "")})
    return metrics


def load_payment_daily_metrics(gc) -> List[dict]:
    spreadsheet = gc.open_by_key(PAYMENT_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(PAYMENT_DAILY_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append(
            {
                "date": date,
                "new_cash_sales": parse_int(row[1] if len(row) > 1 else ""),
                "installment_sales": parse_int(row[2] if len(row) > 2 else ""),
                "recurring_sales": parse_int(row[3] if len(row) > 3 else ""),
                "member_single_sales": parse_int(row[4] if len(row) > 4 else ""),
                "cash_sales": parse_int(row[5] if len(row) > 5 else ""),
                "refunds": parse_int(row[6] if len(row) > 6 else ""),
                "net_cash_sales": parse_int(row[7] if len(row) > 7 else ""),
                "recovery_sales": parse_int(row[8] if len(row) > 8 else ""),
            }
        )
    return metrics


def load_ad_spend_status(gc) -> Dict[str, str]:
    spreadsheet = gc.open_by_key(AD_SPEND_METRICS_SHEET_ID)
    source_rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_SOURCE_TAB))

    result: Dict[str, str] = {}
    for row in source_rows[1:]:
        if not row:
            continue
        key = str(row[0]).strip()
        if key == "広告費":
            result["ステータス"] = str(row[8]).strip() if len(row) > 8 else ""
            result["最終同期日"] = str(row[9]).strip().lstrip("'") if len(row) > 9 else ""
            result["更新数"] = str(row[10]).strip() if len(row) > 10 else ""
            result["エラー数"] = str(row[11]).strip() if len(row) > 11 else ""
            result["メモ"] = str(row[11]).strip() if len(row) > 11 else ""
            break

    summary_rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_SUMMARY_TAB))
    for row in summary_rows[1:]:
        if len(row) < 2:
            continue
        key = str(row[0]).strip()
        value = str(row[1]).strip()
        if key:
            result[key] = value
    return result


def load_payment_status(gc) -> Dict[str, str]:
    spreadsheet = gc.open_by_key(PAYMENT_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(PAYMENT_SOURCE_TAB))

    result: Dict[str, str] = {}
    for row in rows[1:]:
        tab_name = str(row[0]).strip() if len(row) > 0 else ""
        target = str(row[1]).strip() if len(row) > 1 else ""
        if tab_name == PAYMENT_DAILY_TAB and "着金売上" in target:
            result["ステータス"] = str(row[7]).strip() if len(row) > 7 else ""
            result["最終同期日"] = str(row[8]).strip().lstrip("'") if len(row) > 8 else ""
            result["更新数"] = str(row[9]).strip() if len(row) > 9 else ""
            result["エラー数"] = str(row[10]).strip() if len(row) > 10 else ""
            result["メモ"] = str(row[11]).strip() if len(row) > 11 else ""
            break
    return result


def load_membership_status(gc) -> Dict[str, Dict[str, str]]:
    spreadsheet = gc.open_by_key(MEMBERSHIP_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(MEMBERSHIP_SOURCE_TAB))

    result: Dict[str, Dict[str, str]] = {}
    for row in rows[1:]:
        key = str(row[1]).strip() if len(row) > 1 else ""
        if not key:
            continue
        result[key] = {
            "ステータス": str(row[7]).strip() if len(row) > 7 else "",
            "最終同期日": str(row[8]).strip().lstrip("'") if len(row) > 8 else "",
            "更新数": str(row[9]).strip() if len(row) > 9 else "",
            "エラー数": str(row[10]).strip() if len(row) > 10 else "",
            "メモ": str(row[11]).strip() if len(row) > 11 else "",
        }
    return result


def ensure_target_tabs(spreadsheet) -> Dict[str, object]:
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}

    for old_name, new_name in RENAME_TABS.items():
        if old_name in worksheets and new_name not in worksheets:
            worksheet_write_with_retry(
                f"{old_name} タブ名の変更",
                lambda old_name=old_name, new_name=new_name: worksheets[old_name].update_title(new_name),
            )
            worksheets[new_name] = worksheets.pop(old_name)

    for deprecated_title in DEPRECATED_DASHBOARD_TABS:
        ws = worksheets.get(deprecated_title)
        if ws is not None:
            worksheet_write_with_retry(
                f"{deprecated_title} タブの削除",
                lambda ws=ws: spreadsheet.del_worksheet(ws),
            )
            worksheets.pop(deprecated_title, None)

    target_tabs: Dict[str, object] = {}
    for index, (title, rows, cols) in enumerate(TAB_SPECS):
        ws = worksheets.get(title)
        if ws is not None and title in REBUILD_TABS:
            worksheet_write_with_retry(
                f"{title} タブの再作成前削除",
                lambda ws=ws: spreadsheet.del_worksheet(ws),
            )
            worksheets.pop(title, None)
            ws = None
        if ws is None:
            ws = run_write_with_retry(
                f"{title} タブの作成",
                lambda title=title, rows=rows, cols=cols: spreadsheet.add_worksheet(
                    title=title, rows=rows, cols=cols
                ),
            )
        if ws.row_count != rows or ws.col_count != cols:
            worksheet_write_with_retry(
                f"{title} タブのサイズ調整",
                lambda ws=ws, rows=rows, cols=cols: ws.resize(rows=rows, cols=cols),
            )
        target_tabs[title] = ws
        worksheets[title] = ws

        batch_update_with_retry(
            spreadsheet,
            {
                "requests": [
                    set_sheet_properties_request(
                        ws.id,
                        {"index": index, "hidden": False},
                        "index,hidden",
                    )
                ]
            },
            f"{title} タブの表示順更新",
        )

    for hidden_title in HIDDEN_TABS:
        ws = worksheets.get(hidden_title)
        if ws is not None:
            batch_update_with_retry(
                spreadsheet,
                {
                    "requests": [
                        set_sheet_properties_request(ws.id, {"hidden": True}, "hidden")
                    ]
                },
                f"{hidden_title} タブの非表示設定",
            )

    return target_tabs


def write_rows(spreadsheet, ws, rows: Sequence[Sequence[str]]) -> None:
    max_cols = max(len(row) for row in rows)
    padded = [list(row) + [""] * (max_cols - len(row)) for row in rows]
    end_cell = f"{col_letter(max_cols)}{len(padded)}"
    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                {
                    "unmergeCells": {
                        "range": {
                            "sheetId": ws.id,
                            "startRowIndex": 0,
                            "endRowIndex": ws.row_count,
                            "startColumnIndex": 0,
                            "endColumnIndex": ws.col_count,
                        }
                    }
                }
            ]
        },
        f"{ws.title} の結合解除",
    )
    worksheet_write_with_retry(f"{ws.title} の既存データ削除", ws.clear)
    worksheet_write_with_retry(
        f"{ws.title} の書き込み",
        lambda: ws.update(range_name=f"A1:{end_cell}", values=padded, value_input_option="USER_ENTERED"),
    )


def apply_table_style(spreadsheet, ws, row_count: int, col_count: int, widths: Iterable[int]) -> None:
    requests = [
        {
            "unmergeCells": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 0,
                    "endRowIndex": ws.row_count,
                    "startColumnIndex": 0,
                    "endColumnIndex": ws.col_count,
                }
            }
        },
        repeat_cell_request(
            ws.id,
            0,
            1,
            0,
            col_count,
            {
                "backgroundColor": HEADER_BG,
                "textFormat": HEADER_TEXT,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        repeat_cell_request(
            ws.id,
            1,
            row_count,
            0,
            col_count,
            {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "WRAP",
            },
            "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": col_count,
                    }
                }
            }
        },
    ]

    for index, width in enumerate(widths):
        requests.append(set_column_width_request(ws.id, index, index + 1, width))

    batch_update_with_retry(spreadsheet, {"requests": requests}, f"{ws.title} の表スタイル適用")
    worksheet_write_with_retry(f"{ws.title} のヘッダー固定", lambda: ws.freeze(rows=1))


def apply_number_formats(spreadsheet, ws, requests: Sequence[dict]) -> None:
    if not requests:
        return
    batch_update_with_retry(
        spreadsheet,
        {"requests": list(requests)},
        f"{ws.title} の数値書式適用",
    )


def apply_status_cell_colors(spreadsheet, ws, rows: Sequence[Sequence[str]], status_col_index: int) -> None:
    requests = []
    for row_index, row in enumerate(rows[1:], start=1):
        status = str(row[status_col_index]).strip() if len(row) > status_col_index else ""
        fmt = STATUS_FORMATS.get(status)
        if not fmt:
            continue
        requests.append(
            repeat_cell_request(
                ws.id,
                row_index,
                row_index + 1,
                status_col_index,
                status_col_index + 1,
                {
                    **fmt,
                    "horizontalAlignment": "CENTER",
                    "verticalAlignment": "MIDDLE",
                    "textFormat": {"bold": True},
                },
                "userEnteredFormat.backgroundColor,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.textFormat.bold",
            )
        )
    if requests:
        batch_update_with_retry(
            spreadsheet,
            {"requests": requests},
            f"{ws.title} のステータス色適用",
        )


def apply_single_line_header(spreadsheet, ws, col_count: int, font_size: int = 11) -> None:
    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                repeat_cell_request(
                    ws.id,
                    0,
                    1,
                    0,
                    col_count,
                    {
                        "textFormat": {
                            "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            "bold": True,
                            "fontSize": font_size,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "CLIP",
                    },
                    "userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
                )
            ]
        },
        f"{ws.title} のヘッダー1行化",
    )


def apply_protections(spreadsheet, tabs) -> None:
    protected_names = [title for title, _, _ in TAB_SPECS]
    target_sheet_ids = {tabs[name].id for name in protected_names}
    metadata = spreadsheet.fetch_sheet_metadata(
        {
            "includeGridData": False,
            "fields": "sheets(properties.sheetId,protectedRanges(protectedRangeId,description,range(sheetId,startRowIndex,endRowIndex,startColumnIndex,endColumnIndex)))",
        }
    )

    requests = []
    existing_sheet_protection = set()
    for sheet in metadata.get("sheets", []):
        sheet_id = sheet.get("properties", {}).get("sheetId")
        for protected_range in sheet.get("protectedRanges", []):
            range_info = protected_range.get("range", {})
            description = protected_range.get("description", "")
            range_sheet_id = range_info.get("sheetId", sheet_id)
            if range_sheet_id in target_sheet_ids:
                has_row = any(key in range_info for key in ("startRowIndex", "endRowIndex"))
                has_col = any(key in range_info for key in ("startColumnIndex", "endColumnIndex"))
                if not has_row and not has_col:
                    existing_sheet_protection.add(range_sheet_id)
            if range_sheet_id in target_sheet_ids and str(description).startswith(PROTECTION_PREFIX):
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_range["protectedRangeId"]}})

    for name in protected_names:
        if tabs[name].id in existing_sheet_protection:
            continue
        requests.append(
            {
                "addProtectedRange": {
                    "protectedRange": {
                        "range": {"sheetId": tabs[name].id},
                        "description": f"{PROTECTION_PREFIX}: {name}",
                        "warningOnly": False,
                        "editors": {"users": PROTECTED_EDITOR_EMAILS},
                    }
                }
            }
        )

    if requests:
        batch_update_with_retry(
            spreadsheet,
            {"requests": requests},
            "KPIダッシュボードの保護設定",
        )


def build_definition_master_rows() -> List[List[str]]:
    return [
        ["項目", "定義"],
        ["集客数", "ユーザーがメールアドレス登録もしくはLINE登録をした人数"],
        ["集客数（UU）", "ユーザーがメールアドレス登録もしくはLINE登録をしたユニークユーザー数"],
        ["オプトイン数", "メールアドレス登録人数"],
        ["リストイン数", "LINE登録数"],
        ["個別予約数", "ユーザーが個別予約を完了した予約イベント数"],
        ["個別予約数（UU）", "ユーザーが個別予約を完了したユニークユーザー数"],
        ["個別実施数", "オンライン面談でZoomに接続したユーザー数"],
        ["新規着金売上", "非会員向け商品の初回着金、頭金、信販初回承認・初回振込などの新規着金金額"],
        ["分割回収売上", "スキルプラス本体や対象商品の分割回収として着金した金額"],
        ["継続課金売上", "月額継続利用やサブスクリプションの継続課金として着金した金額"],
        ["会員向け単発売上", "会員向けイベントや単発販売として着金した金額"],
        ["着金売上", "新規着金売上・分割回収売上・継続課金売上・会員向け単発売上の合計"],
        ["返金額", "返金が確定した日に計上する返金案件の金額"],
        ["純着金売上", "着金売上から返金額を引いた金額"],
        ["解約請求回収額", "中途解約の請求で、実際に回収済みと確認できた金額"],
        ["広告費", "対象媒体の消化金額"],
        ["CPA", "広告費を集客数で割った数値"],
        ["個別予約CPO", "広告費を個別予約数で割った数値"],
        ["ROAS（新規）", "新規着金売上を広告費で割った数値"],
        ["ROAS（合計）", "着金売上を広告費で割った数値"],
        ["契約数", "スキルプラスの契約書を締結したユーザー数"],
        ["クーリングオフ数", "入金あり契約から7日以内に契約解除を申し出たユーザー数"],
        ["中途解約数", "サポート期間が終了する前に契約解除が確定した会員数"],
        ["入会", "会員になること"],
        ["会員", "スキルプラスの契約締結日から7日間が経過したユーザー"],
    ]


def sync_master_definition_tab(gc) -> None:
    spreadsheet = gc.open_by_key(MASTER_DATA_SHEET_ID)
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}
    ws = worksheets.get("定義一覧")
    if ws is None:
        ws = run_write_with_retry(
            "マスタデータ / 定義一覧 タブの作成",
            lambda: spreadsheet.add_worksheet(title="定義一覧", rows=120, cols=2),
        )
    if ws.row_count != 120 or ws.col_count != 2:
        worksheet_write_with_retry(
            "マスタデータ / 定義一覧 のサイズ調整",
            lambda: ws.resize(rows=120, cols=2),
        )

    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                set_sheet_properties_request(
                    ws.id,
                    {"index": 0, "hidden": False},
                    "index,hidden",
                )
            ]
        },
        "マスタデータ / 定義一覧 の表示順更新",
    )

    definition_rows = build_definition_master_rows()
    write_rows(spreadsheet, ws, definition_rows)
    apply_table_style(
        spreadsheet,
        ws,
        len(definition_rows),
        2,
        widths=[170, 560],
    )
    set_tab_color(ws, "#9E9E9E")




def build_summary_rows(
    booking_status: Dict[str, str],
    membership_status: Dict[str, Dict[str, str]],
    payment_status: Dict[str, str],
) -> List[List[str]]:
    booking_state = booking_status.get("ステータス", "接続中") or "接続中"
    member_state = membership_status.get("会員数", {}).get("ステータス", "確認待ち") or "確認待ち"
    member_note = membership_status.get("会員数", {}).get("メモ", "契約締結日から7日経過した会員の日次残高を使う")
    mid_term_state = membership_status.get("中途解約数", {}).get("ステータス", "確認待ち") or "確認待ち"
    mid_term_note = membership_status.get("中途解約数", {}).get("メモ", "お客様相談窓口_進捗管理シートの中途解約完了を日別件数へ集計する")
    cooling_off_state = membership_status.get("クーリングオフ数", {}).get("ステータス", "確認待ち") or "確認待ち"
    cooling_off_note = membership_status.get("クーリングオフ数", {}).get("メモ", "お客様相談窓口_進捗管理シートのクーリングオフ完了を日別件数へ集計する")
    payment_state = payment_status.get("ステータス", "接続中") or "接続中"
    payment_note = payment_status.get("メモ", "スキルプラス着金データ（加工）の日別売上数値を参照する")

    rows = [[""] * 60 for _ in range(120)]
    visible_rows = [
        ["項目", "値", "正本シート", "状態", "メモ"],
        ["集計開始日", '''=IFERROR(EOMONTH(MAX(FILTER('日別数値'!A:A,'日別数値'!A:A<>"")),-1)+1,"")''', "", "", "手入力で上書き可"],
        ["集計終了日", '''=IFERROR(MAX(FILTER('日別数値'!A:A,'日別数値'!A:A<>"")),"")''', "", "", "手入力で上書き可"],
        ["最終更新日", '''=IFERROR(MAX(FILTER('日別数値'!A:A,'日別数値'!A:A<>"")),"")''', "【アドネス株式会社】KPIダッシュボード / 日別数値", "接続中", ""],
        ["集客数", '''=IF(OR($B$2="",$B$3=""),"",SUMIFS('日別数値'!B:B,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3))''', "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数", "一部接続", "現状はメールのみ。LINE未接続"],
        ["集客数（UU）", '''=IF(OR($B$2="",$B$3=""),"",SUMIFS('日別数値'!C:C,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3))''', "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数（UU）", "一部接続", "現状はメールのみ。LINE未接続"],
        ["個別予約数", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3,'日別数値'!D:D,"<>")=0,"",SUMIFS('日別数値'!D:D,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】個別面談データ（加工） / 日別個別予約数", booking_state, "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する"],
        ["個別予約数（UU）", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3,'日別数値'!E:E,"<>")=0,"",SUMIFS('日別数値'!E:E,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】個別面談データ（加工） / 日別個別予約数（UU）", "確認待ち", "個別予約完了タグの通知ログとLINE統合後に接続"],
        ["個別実施数", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!F:F,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!F:F,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "Zoom接続ログ または 面談ダッシュボード", "確認待ち", "正本未確定。今は未接続"],
        ["新規着金売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!G:G,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!G:G,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, payment_note],
        ["分割回収売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!H:H,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!H:H,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "スキルプラス本体や対象商品の分割回収を集計する"],
        ["継続課金売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!I:I,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!I:I,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "月額継続利用やサブスクの継続課金"],
        ["会員向け単発売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!J:J,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!J:J,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "会員向けイベントや買切りの単発売上"],
        ["着金売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!K:K,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!K:K,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, payment_note],
        ["返金額", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!L:L,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!L:L,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "返金が確定した日に計上する返金額"],
        ["純着金売上", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!M:M,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!M:M,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "着金売上から返金額を引いた金額"],
        ["解約請求回収額", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!N:N,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!N:N,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", payment_state, "回収済みの解約請求金額"],
        ["広告費", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!O:O,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!O:O,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】広告費データ（加工） / 日別広告費", "接続中", "数値管理シートのカテゴリ=広告の日別合計。2025/07/01以降"],
        ["CPA", '''=IF(OR(N(B18)=0,N(B5)=0),"",B18/B5)''', "", "接続中", "広告費 / 集客数"],
        ["個別予約CPO", '''=IF(OR(N(B18)=0,N(B7)=0),"",B18/B7)''', "", "接続中", "広告費 / 個別予約数"],
        ["ROAS（新規）", '''=IF(OR(N(B18)=0,N(B10)=0),"",B10/B18)''', "", "接続中", "新規着金売上 / 広告費"],
        ["ROAS（合計）", '''=IF(OR(N(B18)=0,N(B14)=0),"",B14/B18)''', "", "接続中", "着金売上 / 広告費"],
        ["会員数", '''=IF(OR($B$2="",$B$3=""),"",IFERROR(INDEX(FILTER('日別数値'!T:T,'日別数値'!A:A>=$B$2,'日別数値'!A:A<=$B$3,'日別数値'!T:T<>""),ROWS(FILTER('日別数値'!T:T,'日別数値'!A:A>=$B$2,'日別数値'!A:A<=$B$3,'日別数値'!T:T<>""))),""))''', "【アドネス株式会社】会員データ（加工） / 日別会員数値", member_state, member_note],
        ["中途解約数", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!U:U,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!U:U,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】会員データ（加工） / 日別会員数値", mid_term_state, mid_term_note],
        ["クーリングオフ数", '''=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS('日別数値'!V:V,"<>",'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)=0,"",SUMIFS('日別数値'!V:V,'日別数値'!A:A,">="&$B$2,'日別数値'!A:A,"<="&$B$3)))''', "【アドネス株式会社】会員データ（加工） / 日別会員数値", cooling_off_state, cooling_off_note],
    ]
    for row_index, row in enumerate(visible_rows):
        rows[row_index][:5] = row

    rows[0][6] = "直近7日"
    rows[1][6:17] = [
        "日付",
        "新規着金売上",
        "分割回収売上",
        "継続課金売上",
        "会員向け単発売上",
        "着金売上",
        "返金額",
        "純着金売上",
        "広告費",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    for offset in range(7):
        row_index = offset + 2
        rows[row_index][6] = build_recent_date_formula(offset)
        rows[row_index][7] = build_recent_day_formula("G", offset)
        rows[row_index][8] = build_recent_day_formula("H", offset)
        rows[row_index][9] = build_recent_day_formula("I", offset)
        rows[row_index][10] = build_recent_day_formula("J", offset)
        rows[row_index][11] = build_recent_day_formula("K", offset)
        rows[row_index][12] = build_recent_day_formula("L", offset)
        rows[row_index][13] = build_recent_day_formula("M", offset)
        rows[row_index][14] = build_recent_day_formula("O", offset)
        rows[row_index][15] = build_recent_day_formula("R", offset)
        rows[row_index][16] = build_recent_day_formula("S", offset)

    rows[0][19:25] = [
        "週開始日",
        "新規着金売上",
        "着金売上",
        "広告費",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    rows[1][19] = '''=IFERROR(MAX(FILTER('日別数値'!$A$2:$A,'日別数値'!$A$2:$A<>""))-WEEKDAY(MAX(FILTER('日別数値'!$A$2:$A,'日別数値'!$A$2:$A<>"")),2)+1-77,"")'''
    for offset in range(12):
        row_index = offset + 1
        row_number = row_index + 1
        if offset > 0:
            rows[row_index][19] = f'=IF($T{row_number - 1}="","",$T{row_number - 1}+7)'
        rows[row_index][20] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$G:$G,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][21] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$K:$K,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][22] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$O:$O,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][23] = f'=IF(OR($T{row_number}="",N($W{row_number})=0,N($U{row_number})=0),"",$U{row_number}/$W{row_number})'
        rows[row_index][24] = f'=IF(OR($T{row_number}="",N($W{row_number})=0,N($V{row_number})=0),"",$V{row_number}/$W{row_number})'
    return rows



def header_only_rows(headers: Sequence[str], min_rows: int) -> List[List[str]]:
    rows = [list(headers)]
    while len(rows) < min_rows:
        rows.append([""] * len(headers))
    return rows



def build_daily_rows(
    metrics: Sequence[dict],
    booking_metrics: Sequence[dict],
    membership_metrics: Sequence[dict],
    payment_metrics: Sequence[dict],
    ad_spend_metrics: Sequence[dict] = (),
) -> List[List[str]]:
    email_map = {item["date"]: item for item in metrics}
    booking_map = {item["date"]: item for item in booking_metrics}
    membership_map = {item["date"]: item for item in membership_metrics}
    payment_map = {item["date"]: item for item in payment_metrics}
    ad_spend_map = {item["date"]: item for item in ad_spend_metrics}
    booking_latest_date = max(booking_map.keys()) if booking_map else ""
    membership_latest_date = max(membership_map.keys()) if membership_map else ""
    payment_latest_date = max(payment_map.keys()) if payment_map else ""
    ad_spend_latest_date = max(ad_spend_map.keys()) if ad_spend_map else ""
    all_dates = sorted(set(email_map.keys()) | set(booking_map.keys()) | set(membership_map.keys()) | set(payment_map.keys()) | set(ad_spend_map.keys()))

    rows = [[
        "日付",
        "集客数",
        "集客数（UU）",
        "個別予約数",
        "個別予約数（UU）",
        "個別実施数",
        "新規着金売上",
        "分割回収売上",
        "継続課金売上",
        "会員向け単発売上",
        "着金売上",
        "返金額",
        "純着金売上",
        "解約請求回収額",
        "広告費",
        "CPA",
        "個別予約CPO",
        "ROAS（新規）",
        "ROAS（合計）",
        "会員数",
        "中途解約数",
        "クーリングオフ数",
    ]]
    blank_payment = {
        "new_cash_sales": "",
        "installment_sales": "",
        "recurring_sales": "",
        "member_single_sales": "",
        "cash_sales": "",
        "refunds": "",
        "net_cash_sales": "",
        "recovery_sales": "",
    }
    zero_payment = {
        "new_cash_sales": 0,
        "installment_sales": 0,
        "recurring_sales": 0,
        "member_single_sales": 0,
        "cash_sales": 0,
        "refunds": 0,
        "net_cash_sales": 0,
        "recovery_sales": 0,
    }
    for date in all_dates:
        email_item = email_map.get(date, {"count": "", "uu_count": ""})
        if date in booking_map:
            booking_count = booking_map[date]["count"]
        elif booking_latest_date and date <= booking_latest_date:
            booking_count = 0
        else:
            booking_count = ""
        if date in membership_map:
            membership_item = membership_map[date]
            member_count = membership_item["member_count"]
            mid_term_cancel_count = membership_item["mid_term_cancel_count"]
            cooling_off_count = membership_item["cooling_off_count"]
        elif membership_latest_date and date <= membership_latest_date:
            member_count = 0
            mid_term_cancel_count = 0
            cooling_off_count = 0
        else:
            member_count = ""
            mid_term_cancel_count = ""
            cooling_off_count = ""
        if date in payment_map:
            payment_item = payment_map[date]
        elif payment_latest_date and date <= payment_latest_date:
            payment_item = zero_payment
        else:
            payment_item = blank_payment
        if date in ad_spend_map:
            ad_spend = ad_spend_map[date]["spend"]
        elif ad_spend_latest_date and date <= ad_spend_latest_date:
            ad_spend = 0
        else:
            ad_spend = ""
        cpa = ""
        if ad_spend != "" and email_item["count"] not in ("", 0, None):
            try:
                cpa = round(int(ad_spend) / int(email_item["count"]))
            except (ZeroDivisionError, ValueError, TypeError):
                cpa = ""
        cpo = ""
        if ad_spend != "" and booking_count not in ("", 0, None):
            try:
                cpo = round(int(ad_spend) / int(booking_count))
            except (ZeroDivisionError, ValueError, TypeError):
                cpo = ""
        new_cash_roas = ""
        if ad_spend not in ("", 0, None) and payment_item["new_cash_sales"] not in ("", 0, None):
            try:
                new_cash_roas = round(int(payment_item["new_cash_sales"]) / int(ad_spend), 2)
            except (ZeroDivisionError, ValueError, TypeError):
                new_cash_roas = ""
        cash_roas = ""
        if ad_spend not in ("", 0, None) and payment_item["cash_sales"] not in ("", 0, None):
            try:
                cash_roas = round(int(payment_item["cash_sales"]) / int(ad_spend), 2)
            except (ZeroDivisionError, ValueError, TypeError):
                cash_roas = ""
        rows.append([
            date,
            email_item["count"],
            email_item["uu_count"],
            booking_count,
            "",
            "",
            payment_item["new_cash_sales"],
            payment_item["installment_sales"],
            payment_item["recurring_sales"],
            payment_item["member_single_sales"],
            payment_item["cash_sales"],
            payment_item["refunds"],
            payment_item["net_cash_sales"],
            payment_item["recovery_sales"],
            ad_spend,
            cpa,
            cpo,
            new_cash_roas,
            cash_roas,
            member_count,
            mid_term_cancel_count,
            cooling_off_count,
        ])
    while len(rows) < 120:
        rows.append([""] * 22)
    return rows



def build_data_source_rows(
    status: Dict[str, str],
    daily_row_count: int,
    booking_status: Dict[str, str],
    booking_daily_row_count: int,
    membership_status: Dict[str, Dict[str, str]],
    membership_daily_row_count: int,
    payment_status: Dict[str, str],
    payment_daily_row_count: int,
    ad_spend_status: Dict[str, str] = None,
    ad_spend_daily_row_count: int = 0,
) -> List[List[str]]:
    updated_at = status.get("更新日時", "")
    booking_updated_at = booking_status.get("最終同期日") or booking_status.get("更新日時", "")
    booking_state = booking_status.get("ステータス", "未接続")
    booking_memo = booking_status.get("メモ", "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する")
    booking_updates = booking_status.get("更新数", str(booking_daily_row_count))
    booking_errors = booking_status.get("エラー数", "0")
    membership_member = membership_status.get("会員数", {})
    membership_mid_term = membership_status.get("中途解約数", {})
    membership_cooling_off = membership_status.get("クーリングオフ数", {})
    payment_state = payment_status.get("ステータス", "確認待ち")
    payment_updated_at = payment_status.get("最終同期日", "")
    payment_updates = payment_status.get("更新数", str(payment_daily_row_count))
    payment_errors = payment_status.get("エラー数", "0")
    payment_memo = payment_status.get("メモ", "スキルプラス着金データ（加工）の日別売上数値を参照する")
    ad_spend_status = ad_spend_status or {}
    ad_spend_state = ad_spend_status.get("ステータス", "確認待ち")
    ad_spend_updated_at = ad_spend_status.get("最終同期日") or ad_spend_status.get("更新日時", "")
    ad_spend_updates = ad_spend_status.get("更新数", str(ad_spend_daily_row_count))
    ad_spend_errors = ad_spend_status.get("エラー数", "0")
    ad_spend_memo = ad_spend_status.get("メモ", "数値管理シートのカテゴリ=広告の日別合計")
    rows = [
        ["KPIカラム", "グループ", "ソース元", "優先度", "スプレッドシートURL", "タブ名", "参照先列", "正規化 / 計算", "入力条件", "ステータス", "最終同期日", "更新数", "エラー数", "メモ"],
        ["集客数", "集客", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{EMAIL_METRICS_SHEET_ID}/edit","【アドネス株式会社】集客データ_メール集計（加工）")', "日別メール登録件数", "B列", "重複あり件数", "2025/01/01以降", "一部接続", updated_at, str(daily_row_count), "0", "現状はメールのみ。LINE未接続"],
        ["集客数（UU）", "集客", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{EMAIL_METRICS_SHEET_ID}/edit","【アドネス株式会社】集客データ_メール集計（加工）")', "日別メール登録件数（UU）", "B列", "最初に確認された日にだけ1件", "2025/01/01以降", "一部接続", updated_at, str(daily_row_count), "0", "現状はメールのみ。LINE未接続"],
        ["個別予約数", "個別予約", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{BOOKING_METRICS_SHEET_ID}/edit","【アドネス株式会社】個別面談データ（加工）")', "日別個別予約数", "B列", "キャンセルではない個別予約イベント数", "2025/01/01以降", booking_state, booking_updated_at, booking_updates, booking_errors, booking_memo],
        ["個別予約数（UU）", "個別予約", "加工データ", "2", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{BOOKING_METRICS_SHEET_ID}/edit","【アドネス株式会社】個別面談データ（加工）")', "日別個別予約数（UU）", "B列", "将来接続。ユニークユーザー数", "個別予約完了タグの通知ログとLINE統合後", "確認待ち", "", "", "", "現時点ではユニーク判定が弱いため未接続"],
        ["個別実施数", "個別予約", "収集データ候補", "2", "", "Zoom接続ログ または 面談ダッシュボード", "", "接続ユーザー数", "正本未確定", "確認待ち", "", "", "", "今は未接続"],
        ["新規着金売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "B列", "新規契約に紐づく初回着金", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, payment_memo],
        ["分割回収売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "C列", "スキルプラス本体の分割回収", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "スキルプラス本体や対象商品の分割回収を集計する"],
        ["継続課金売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "D列", "月額継続利用・サブスクの継続課金", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "スキルプラス継続利用や継続商品を集計する"],
        ["会員向け単発売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "E列", "会員向けイベントや買切りの単発売上", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "会員向けイベント・合宿・単発販売を集計する"],
        ["着金売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "F列", "新規・分割・継続・会員向け単発の合計", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, payment_memo],
        ["返金額", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "G列", "返金確定日の返金案件金額", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "相談窓口シートを案件正本にした返金額"],
        ["純着金売上", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "H列", "着金売上 - 返金額", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "スキルプラス事業の純着金売上"],
        ["解約請求回収額", "売上", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{PAYMENT_METRICS_SHEET_ID}/edit","【アドネス株式会社】スキルプラス着金データ（加工）")', PAYMENT_DAILY_TAB, "I列", "回収済みの解約請求金額", "2025/01/01以降", payment_state, payment_updated_at, payment_updates, payment_errors, "中途解約タブの回収済み案件のみ集計する"],
        ["広告費", "広告費", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{AD_SPEND_METRICS_SHEET_ID}/edit","【アドネス株式会社】広告費データ（加工）")', AD_SPEND_DAILY_TAB, "B列", "数値管理シートのカテゴリ=広告の日別合計", "2025/07/01以降", ad_spend_state, ad_spend_updated_at, ad_spend_updates, ad_spend_errors, ad_spend_memo],
        ["CPA", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "P列", "広告費 / 集客数", "広告費と集客数が入力済み", "接続中", "", "", "", "広告費と集客数が入力された日だけ自動計算"],
        ["個別予約CPO", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "Q列", "広告費 / 個別予約数", "広告費と個別予約数が入力済み", "接続中", "", "", "", "広告費と個別予約数が入力された日だけ自動計算"],
        ["ROAS（新規）", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "R列", "新規着金売上 / 広告費", "新規着金売上と広告費が入力済み", "接続中", "", "", "", "広告判断用の新規着金ROAS"],
        ["ROAS（合計）", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "S列", "着金売上 / 広告費", "着金売上と広告費が入力済み", "接続中", "", "", "", "全体像を見るための着金ROAS"],
        ["会員数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "D列", "契約締結日から7日経過した会員の日次残高", "2025/01/01以降", membership_member.get("ステータス", "確認待ち"), membership_member.get("最終同期日", ""), membership_member.get("更新数", str(membership_daily_row_count)), membership_member.get("エラー数", "0"), membership_member.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["中途解約数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "E列", "日別件数", "2025/01/01以降", membership_mid_term.get("ステータス", "確認待ち"), membership_mid_term.get("最終同期日", ""), membership_mid_term.get("更新数", str(membership_daily_row_count)), membership_mid_term.get("エラー数", "0"), membership_mid_term.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["クーリングオフ数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "C列", "日別件数", "2025/01/01以降", membership_cooling_off.get("ステータス", "確認待ち"), membership_cooling_off.get("最終同期日", ""), membership_cooling_off.get("更新数", str(membership_daily_row_count)), membership_cooling_off.get("エラー数", "0"), membership_cooling_off.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
    ]
    while len(rows) < 40:
        rows.append([""] * 14)
    return rows


def set_tab_color(ws, color: str) -> None:
    try:
        ws.update_tab_color(color)
    except Exception:
        pass


def main() -> None:
    gc = get_client()
    sync_master_definition_tab(gc)
    spreadsheet = gc.open_by_key(DASHBOARD_SHEET_ID)
    tabs = ensure_target_tabs(spreadsheet)
    booking_status = load_booking_status(gc)
    membership_status = load_membership_status(gc)
    payment_status = load_payment_status(gc)

    summary_rows = build_summary_rows(booking_status, membership_status, payment_status)
    write_rows(spreadsheet, tabs["スキルプラス事業サマリー"], summary_rows)
    apply_table_style(
        spreadsheet,
        tabs["スキルプラス事業サマリー"],
        len(summary_rows),
        5,
        widths=[180, 130, 320, 100, 220],
    )
    apply_number_formats(
        spreadsheet,
        tabs["スキルプラス事業サマリー"],
        [
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                1,
                4,
                1,
                2,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                4,
                9,
                1,
                2,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                9,
                20,
                1,
                2,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                20,
                22,
                1,
                2,
                {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                22,
                25,
                1,
                2,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                2,
                9,
                6,
                7,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                2,
                9,
                7,
                15,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                2,
                9,
                15,
                17,
                {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                1,
                13,
                19,
                20,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                1,
                13,
                20,
                23,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["スキルプラス事業サマリー"].id,
                1,
                13,
                23,
                25,
                {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
                "userEnteredFormat.numberFormat",
            ),
        ],
    )
    apply_status_cell_colors(
        spreadsheet,
        tabs["スキルプラス事業サマリー"],
        summary_rows,
        3,
    )
    summary_section_requests = [
        repeat_cell_request(
            tabs["スキルプラス事業サマリー"].id,
            0,
            1,
            6,
            17,
            {
                "backgroundColor": {"red": 0.89, "green": 0.95, "blue": 0.99},
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
            },
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment",
        ),
        repeat_cell_request(
            tabs["スキルプラス事業サマリー"].id,
            1,
            2,
            6,
            17,
            {
                "backgroundColor": HEADER_BG,
                "textFormat": HEADER_TEXT,
                "horizontalAlignment": "CENTER",
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        repeat_cell_request(
            tabs["スキルプラス事業サマリー"].id,
            2,
            9,
            6,
            17,
            {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        set_column_width_request(tabs["スキルプラス事業サマリー"].id, 6, 7, 105),
        set_column_width_request(tabs["スキルプラス事業サマリー"].id, 7, 15, 118),
        set_column_width_request(tabs["スキルプラス事業サマリー"].id, 15, 17, 98),
        set_column_hidden_request(tabs["スキルプラス事業サマリー"].id, 19, 25, True),
    ]
    batch_update_with_retry(
        spreadsheet,
        {"requests": summary_section_requests},
        "スキルプラス事業サマリーの直近表示更新",
    )
    chart_requests = list_chart_delete_requests(spreadsheet, tabs["スキルプラス事業サマリー"].id)
    chart_requests.extend(
        [
            add_line_chart_request(
                tabs["スキルプラス事業サマリー"].id,
                11,
                6,
                "直近12週間 着金・広告費推移",
                19,
                [20, 21, 22],
                end_row_index=13,
                width=940,
                height=260,
            ),
            add_line_chart_request(
                tabs["スキルプラス事業サマリー"].id,
                29,
                6,
                "直近12週間 ROAS推移",
                19,
                [23, 24],
                end_row_index=13,
                width=940,
                height=260,
            ),
        ]
    )
    batch_update_with_retry(
        spreadsheet,
        {"requests": chart_requests},
        "スキルプラス事業サマリーのグラフ更新",
    )

    daily_metrics = load_email_daily_metrics(gc)
    booking_metrics = load_booking_daily_metrics(gc)
    membership_metrics = load_membership_daily_metrics(gc)
    payment_metrics = load_payment_daily_metrics(gc)
    ad_spend_metrics = load_ad_spend_daily_metrics(gc)
    daily_rows = build_daily_rows(daily_metrics, booking_metrics, membership_metrics, payment_metrics, ad_spend_metrics)
    write_rows(spreadsheet, tabs["日別数値"], daily_rows)
    apply_table_style(
        spreadsheet,
        tabs["日別数値"],
        len(daily_rows),
        22,
        widths=[120, 120, 145, 135, 150, 125, 135, 135, 135, 145, 135, 120, 135, 145, 120, 110, 145, 120, 120, 120, 120, 135],
    )
    apply_single_line_header(spreadsheet, tabs["日別数値"], 22)
    apply_number_formats(
        spreadsheet,
        tabs["日別数値"],
        [
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                0,
                1,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                0,
                1,
                {"horizontalAlignment": "LEFT"},
                "userEnteredFormat.horizontalAlignment",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                1,
                6,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                6,
                17,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                17,
                19,
                {"numberFormat": {"type": "NUMBER", "pattern": "0.00"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                19,
                22,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
        ],
    )

    email_metrics_status = load_email_metrics_status(gc)
    ad_spend_status = load_ad_spend_status(gc)
    data_source_rows = build_data_source_rows(
        email_metrics_status,
        max(len(daily_metrics), 0),
        booking_status,
        max(len(booking_metrics), 0),
        membership_status,
        max(len(membership_metrics), 0),
        payment_status,
        max(len(payment_metrics), 0),
        ad_spend_status,
        max(len(ad_spend_metrics), 0),
    )
    write_rows(spreadsheet, tabs["データソース管理"], data_source_rows)
    apply_table_style(
        spreadsheet,
        tabs["データソース管理"],
        len(data_source_rows),
        14,
        widths=[170, 125, 125, 90, 280, 190, 125, 190, 160, 100, 155, 100, 90, 260],
    )
    apply_single_line_header(spreadsheet, tabs["データソース管理"], 14)
    apply_status_cell_colors(
        spreadsheet,
        tabs["データソース管理"],
        data_source_rows,
        9,
    )

    for title, _rows, _cols in TAB_SPECS:
        set_tab_color(tabs[title], TAB_COLORS[title])

    apply_protections(spreadsheet, tabs)

    print("マスタデータ / 定義一覧 と 【アドネス株式会社】KPIダッシュボード を更新しました。")


if __name__ == "__main__":
    main()
