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
AD_SPEND_METRICS_SHEET_ID = "1QLtsOOQLzmeDewHIzEqtSY5Ibr5ryCRSydyRumgtdTM"
AD_SPEND_DAILY_TAB = "広告費管理"
AD_SPEND_SOURCE_TAB = "データソース管理"
AD_SPEND_MONITOR_TAB = "加工監視"
PAYMENT_METRICS_SHEET_ID = "1eh8X_dsRitFDKAJVE-dbr75ycGfMffMsvJYI-Gtlv_Q"
PAYMENT_DAILY_TAB = "日別売上数値"
PAYMENT_SOURCE_TAB = "データソース管理"

TAB_SPECS = [
    ("スキルプラス事業サマリー", 120, 60),
    ("日別数値", 600, 24),
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


def set_date_validation_request(sheet_id: int, start_row: int, end_row: int, start_col: int, end_col: int) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": start_row,
                "endRowIndex": end_row,
                "startColumnIndex": start_col,
                "endColumnIndex": end_col,
            },
            "cell": {
                "dataValidation": {
                    "condition": {"type": "DATE_IS_VALID"},
                    "strict": True,
                    "showCustomUi": True,
                }
            },
            "fields": "dataValidation",
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
                    "hiddenDimensionStrategy": "SHOW_ALL",
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


def build_latest_actual_date_formula() -> str:
    return (
        '=IFERROR(MAX(FILTER(\'日別数値\'!$A$2:$A,'
        '\'日別数値\'!$A$2:$A<>"",'
        '\'日別数値\'!$A$2:$A<=TODAY(),'
        'BYROW(\'日別数値\'!$B$2:$Z,LAMBDA(r,SUM(N(r))>0)))),'
        'IFERROR(MAX(FILTER(\'日別数値\'!$A$2:$A,\'日別数値\'!$A$2:$A<>"")),""))'
    )


def build_recent_date_formula(offset: int) -> str:
    return (
        '=IFERROR(INDEX(SORT(FILTER(\'日別数値\'!$A$2:$A,'
        '\'日別数値\'!$A$2:$A<>"",'
        '\'日別数値\'!$A$2:$A<=TODAY(),'
        'BYROW(\'日別数値\'!$G$2:$Q,LAMBDA(r,SUM(N(r))>0))),1,FALSE),'
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


def get_range_values_with_retry(ws, range_name: str, value_render_option: str | None = None) -> List[List[str]]:
    last_error = None
    for _ in range(4):
        try:
            kwargs = {}
            if value_render_option:
                kwargs["value_render_option"] = value_render_option
            return ws.get(range_name, **kwargs)
        except Exception as exc:
            last_error = exc
            if not is_retryable_sheets_message(str(exc)):
                raise
            time.sleep(5)
    raise last_error


def open_spreadsheet_with_retry(gc, spreadsheet_id: str):
    last_error = None
    for _ in range(4):
        try:
            return gc.open_by_key(spreadsheet_id)
        except Exception as exc:
            last_error = exc
            if not is_retryable_sheets_message(str(exc)):
                raise
            time.sleep(5)
    raise last_error


def get_worksheets_with_retry(spreadsheet):
    last_error = None
    for _ in range(4):
        try:
            return spreadsheet.worksheets()
        except Exception as exc:
            last_error = exc
            if not is_retryable_sheets_message(str(exc)):
                raise
            time.sleep(5)
    raise last_error


def load_email_daily_metrics(gc) -> List[dict]:
    spreadsheet = open_spreadsheet_with_retry(gc, EMAIL_METRICS_SHEET_ID)
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
    spreadsheet = open_spreadsheet_with_retry(gc, EMAIL_METRICS_SHEET_ID)
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
    spreadsheet = open_spreadsheet_with_retry(gc, BOOKING_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(BOOKING_COUNT_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append({"date": date, "count": parse_int(row[1] if len(row) > 1 else "")})
    return metrics


def load_booking_status(gc) -> Dict[str, str]:
    spreadsheet = open_spreadsheet_with_retry(gc, BOOKING_METRICS_SHEET_ID)
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
    spreadsheet = open_spreadsheet_with_retry(gc, MEMBERSHIP_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(MEMBERSHIP_DAILY_TAB))

    metrics: List[dict] = []
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        metrics.append(
            {
                "date": date,
                "contract_count": parse_int(row[1] if len(row) > 1 else ""),
                "cooling_off_count": parse_int(row[2] if len(row) > 2 else ""),
                "member_count": parse_int(row[3] if len(row) > 3 else ""),
                "mid_term_cancel_count": parse_int(row[4] if len(row) > 4 else ""),
                "active_member_count": parse_int(row[5] if len(row) > 5 else ""),
            }
        )
    return metrics


def load_ad_spend_daily_metrics(gc) -> List[dict]:
    spreadsheet = open_spreadsheet_with_retry(gc, AD_SPEND_METRICS_SHEET_ID)
    rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_DAILY_TAB))

    totals: Dict[str, int] = {}
    for row in rows[1:]:
        date = normalize_date(row[0] if len(row) > 0 else "")
        if not date:
            continue
        totals[date] = totals.get(date, 0) + parse_int(row[6] if len(row) > 6 else "")
    return [{"date": date, "spend": spend} for date, spend in sorted(totals.items())]


def load_payment_daily_metrics(gc) -> List[dict]:
    spreadsheet = open_spreadsheet_with_retry(gc, PAYMENT_METRICS_SHEET_ID)
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
    spreadsheet = open_spreadsheet_with_retry(gc, AD_SPEND_METRICS_SHEET_ID)
    source_rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_SOURCE_TAB))

    result: Dict[str, str] = {}
    for row in source_rows[1:]:
        if not row:
            continue
        source_id = str(row[0]).strip()
        if source_id not in {
            "online_meta",
            "online_tiktok",
            "online_x",
            "offline_pdf",
            "cost_outsource_x",
            "cost_outsource_youtube",
            "cost_affiliate",
        }:
            continue
        status = str(row[7]).strip() if len(row) > 7 else ""
        latest = str(row[8]).strip().lstrip("'") if len(row) > 8 else ""
        updates = str(row[9]).strip() if len(row) > 9 else ""
        result.setdefault("ステータス一覧", []).append(status)
        result.setdefault("最終同期日一覧", []).append(latest)
        result.setdefault("更新数一覧", []).append(updates)

    monitor_rows = get_all_values_with_retry(spreadsheet.worksheet(AD_SPEND_MONITOR_TAB))
    for row in monitor_rows[1:]:
        if len(row) < 10:
            continue
        if str(row[0]).strip() != AD_SPEND_DAILY_TAB:
            continue
        result["監視ステータス"] = str(row[2]).strip()
        result["最終同期日"] = str(row[3]).strip().lstrip("'")
        result["最古日付"] = str(row[4]).strip()
        result["最新日付"] = str(row[5]).strip()
        result["更新数"] = str(row[6]).strip()
        result["エラー数"] = str(row[7]).strip()
        result["メモ"] = str(row[9]).strip()
        break

    statuses = [value for value in result.pop("ステータス一覧", []) if value]
    latest_dates = [value for value in result.pop("最終同期日一覧", []) if value]
    update_counts = [parse_int(value) for value in result.pop("更新数一覧", []) if value]
    if "ステータス" not in result:
        if result.get("監視ステータス"):
            result["ステータス"] = result["監視ステータス"]
        elif statuses and all(value == "正常" for value in statuses):
            result["ステータス"] = "正常"
        elif statuses:
            result["ステータス"] = "未同期"
    if "最終同期日" not in result and latest_dates:
        result["最終同期日"] = max(latest_dates)
    if "更新数" not in result and update_counts:
        result["更新数"] = str(sum(update_counts))
    if "エラー数" not in result:
        result["エラー数"] = "0"
    return result


def load_payment_status(gc) -> Dict[str, str]:
    spreadsheet = open_spreadsheet_with_retry(gc, PAYMENT_METRICS_SHEET_ID)
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
    spreadsheet = open_spreadsheet_with_retry(gc, MEMBERSHIP_METRICS_SHEET_ID)
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
    worksheets = {ws.title: ws for ws in get_worksheets_with_retry(spreadsheet)}

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
        ["粗利（新規）", "新規着金売上から広告費を引いた金額"],
        ["粗利", "着金売上から返金額と広告費を引き、解約請求回収額を加えた金額"],
        ["広告費", "対象媒体の消化金額"],
        ["CPA", "広告費を集客数で割った数値"],
        ["個別予約CPO", "広告費を個別予約数で割った数値"],
        ["ROAS（新規）", "新規着金売上を広告費で割った数値"],
        ["ROAS（合計）", "着金売上を広告費で割った数値"],
        ["契約数", "スキルプラスの契約書を締結した日次件数"],
        ["クーリングオフ数", "入金あり契約から7日以内に契約解除を申し出た日次件数"],
        ["会員数", "契約締結日から7日経過して会員化した日次件数"],
        ["中途解約数", "サポート期間が終了する前に契約解除が確定した日次件数"],
        ["アクティブ会員数", "会員数の累計から中途解約数の累計を引いた日次残高"],
        ["入会", "会員になること"],
        ["会員", "スキルプラスの契約締結日から7日間が経過したユーザー"],
    ]


def sync_master_definition_tab(gc) -> None:
    spreadsheet = open_spreadsheet_with_retry(gc, MASTER_DATA_SHEET_ID)
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
    member_note = membership_status.get("会員数", {}).get("メモ", "契約締結日から7日経過して会員化した日次件数を期間集計する")
    active_state = membership_status.get("アクティブ会員数", {}).get("ステータス", "確認待ち") or "確認待ち"
    active_note = membership_status.get("アクティブ会員数", {}).get("メモ", "会員数の累計から中途解約数の累計を引いた日次残高を使う")
    mid_term_state = membership_status.get("中途解約数", {}).get("ステータス", "確認待ち") or "確認待ち"
    mid_term_note = membership_status.get("中途解約数", {}).get("メモ", "お客様相談窓口_進捗管理シートの中途解約完了を日別件数へ集計する")
    cooling_off_state = membership_status.get("クーリングオフ数", {}).get("ステータス", "確認待ち") or "確認待ち"
    cooling_off_note = membership_status.get("クーリングオフ数", {}).get("メモ", "お客様相談窓口_進捗管理シートのクーリングオフ完了を日別件数へ集計する")
    payment_state = payment_status.get("ステータス", "接続中") or "接続中"
    payment_note = payment_status.get("メモ", "スキルプラス着金データ（加工）の日別売上数値を参照する")

    rows = [[""] * 60 for _ in range(120)]
    items = [
        {"kind": "header", "row": ["項目", "値", "正本シート", "状態", "メモ"]},
        {"kind": "section", "label": "基準"},
        {"kind": "metric", "key": "start_date", "label": "集計開始日", "source": "", "state": "", "note": "手入力で上書き可"},
        {"kind": "metric", "key": "end_date", "label": "集計終了日", "source": "", "state": "", "note": "today時点の最新実績日"},
        {"kind": "metric", "key": "updated_at", "label": "最終更新日", "source": "【アドネス株式会社】KPIダッシュボード / 日別数値", "state": "接続中", "note": ""},
        {"kind": "section", "label": "主要KPI"},
        {"kind": "metric", "key": "gross_profit_new", "label": "粗利（新規）", "source": "", "state": "接続中", "note": "新規着金売上 - 広告費"},
        {"kind": "metric", "key": "new_cash", "label": "新規着金売上", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": payment_note},
        {"kind": "metric", "key": "lead_count", "label": "集客数", "source": "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数", "state": "一部接続", "note": "現状はメールのみ。LINE未接続"},
        {"kind": "metric", "key": "booking_count", "label": "個別予約数", "source": "【アドネス株式会社】個別面談データ（加工） / 日別個別予約数", "state": booking_state, "note": "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する"},
        {"kind": "metric", "key": "member_count", "label": "会員数", "source": "【アドネス株式会社】会員データ（加工） / 日別会員数値", "state": member_state, "note": member_note},
        {"kind": "metric", "key": "mid_term_cancel_count", "label": "中途解約数", "source": "【アドネス株式会社】会員データ（加工） / 日別会員数値", "state": mid_term_state, "note": mid_term_note},
        {"kind": "metric", "key": "ad_spend", "label": "広告費", "source": "【アドネス株式会社】広告データ（加工） / 広告費管理", "state": "接続中", "note": "広告費管理タブの広告費を日付単位で合算した値"},
        {"kind": "section", "label": "補助指標"},
        {"kind": "metric", "key": "lead_uu", "label": "集客数（UU）", "source": "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数（UU）", "state": "一部接続", "note": "現状はメールのみ。LINE未接続"},
        {"kind": "metric", "key": "refunds", "label": "返金額", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "返金が確定した日に計上する返金額"},
        {"kind": "metric", "key": "cash_sales", "label": "着金売上（合計）", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": payment_note},
        {"kind": "metric", "key": "gross_profit", "label": "粗利（合計）", "source": "", "state": "接続中", "note": "着金売上 - 返金額 - 広告費 + 解約請求回収額"},
        {"kind": "metric", "key": "cpa", "label": "CPA", "source": "", "state": "接続中", "note": "広告費 / 集客数"},
        {"kind": "metric", "key": "booking_cpo", "label": "個別予約CPO", "source": "", "state": "接続中", "note": "広告費 / 個別予約数"},
        {"kind": "metric", "key": "roas_new", "label": "ROAS（新規）", "source": "", "state": "接続中", "note": "新規着金売上 / 広告費"},
        {"kind": "metric", "key": "roas_total", "label": "ROAS（合計）", "source": "", "state": "接続中", "note": "着金売上 / 広告費"},
        {"kind": "section", "label": "売上内訳"},
        {"kind": "metric", "key": "installment", "label": "分割回収売上", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "スキルプラス本体や対象商品の分割回収を集計する"},
        {"kind": "metric", "key": "recurring", "label": "継続課金売上", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "月額継続利用やサブスクの継続課金"},
        {"kind": "metric", "key": "member_single", "label": "会員向け単発売上", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "会員向けイベントや買切りの単発売上"},
        {"kind": "metric", "key": "net_cash", "label": "純着金売上", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "着金売上から返金額を引いた金額"},
        {"kind": "metric", "key": "recovery", "label": "解約請求回収額", "source": "【アドネス株式会社】スキルプラス着金データ（加工） / 日別売上数値", "state": payment_state, "note": "回収済みの解約請求金額"},
        {"kind": "section", "label": "会員補助"},
        {"kind": "metric", "key": "cooling_off_count", "label": "クーリングオフ数", "source": "【アドネス株式会社】会員データ（加工） / 日別会員数値", "state": cooling_off_state, "note": cooling_off_note},
        {"kind": "metric", "key": "active_member_count", "label": "アクティブ会員数", "source": "【アドネス株式会社】会員データ（加工） / 日別会員数値", "state": active_state, "note": active_note},
    ]

    row_map: Dict[str, int] = {}
    current_row = 1
    for item in items:
        if item["kind"] == "metric":
            row_map[item["key"]] = current_row
        current_row += 1

    def ref(key: str) -> str:
        return f"$B${row_map[key]}"

    def date_window_sum_formula(column_letter: str) -> str:
        return (
            f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",'''
            f'''IF(COUNTIFS('日別数値'!{column_letter}:{column_letter},"<>",'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")})=0,"",'''
            f'''SUMIFS('日別数値'!{column_letter}:{column_letter},'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")})))'''
        )

    formula_map = {
        "start_date": f'''=IF({ref("end_date")}="","",EOMONTH({ref("end_date")},-1)+1)''',
        "end_date": build_latest_actual_date_formula(),
        "updated_at": f'''=IF({ref("end_date")}="","",{ref("end_date")})''',
        "lead_count": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",SUMIFS('日別数値'!B:B,'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")}))''',
        "lead_uu": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",SUMIFS('日別数値'!C:C,'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")}))''',
        "booking_count": date_window_sum_formula("D"),
        "booking_uu": date_window_sum_formula("E"),
        "held_count": date_window_sum_formula("F"),
        "new_cash": date_window_sum_formula("G"),
        "installment": date_window_sum_formula("H"),
        "recurring": date_window_sum_formula("I"),
        "member_single": date_window_sum_formula("J"),
        "cash_sales": date_window_sum_formula("K"),
        "refunds": date_window_sum_formula("L"),
        "net_cash": date_window_sum_formula("M"),
        "recovery": date_window_sum_formula("N"),
        "gross_profit_new": date_window_sum_formula("O"),
        "gross_profit": date_window_sum_formula("P"),
        "ad_spend": date_window_sum_formula("Q"),
        "cpa": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("lead_count")})=0),"",{ref("ad_spend")}/{ref("lead_count")})''',
        "booking_cpo": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("booking_count")})=0),"",{ref("ad_spend")}/{ref("booking_count")})''',
        "roas_new": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("new_cash")})=0),"",{ref("new_cash")}/{ref("ad_spend")})''',
        "roas_total": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("cash_sales")})=0),"",{ref("cash_sales")}/{ref("ad_spend")})''',
        "member_count": date_window_sum_formula("X"),
        "mid_term_cancel_count": date_window_sum_formula("Y"),
        "cooling_off_count": date_window_sum_formula("W"),
        "active_member_count": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",IFERROR(INDEX(FILTER('日別数値'!Z:Z,'日別数値'!A:A>={ref("start_date")},'日別数値'!A:A<={ref("end_date")},'日別数値'!Z:Z<>""),ROWS(FILTER('日別数値'!Z:Z,'日別数値'!A:A>={ref("start_date")},'日別数値'!A:A<={ref("end_date")},'日別数値'!Z:Z<>""))),""))''',
    }

    write_index = 0
    for item in items:
        if item["kind"] == "header":
            rows[write_index][:5] = item["row"]
        elif item["kind"] == "section":
            rows[write_index][:5] = [item["label"], "", "", "", ""]
        else:
            rows[write_index][:5] = [
                item["label"],
                formula_map[item["key"]],
                item["source"],
                item["state"],
                item["note"],
            ]
        write_index += 1

    rows[0][6] = "直近7日"
    rows[1][6:18] = [
        "日付",
        "粗利（新規）",
        "新規着金売上",
        "着金売上",
        "返金額",
        "広告費",
        "集客数",
        "個別予約数",
        "会員数",
        "中途解約数",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    for offset in range(7):
        row_index = offset + 2
        rows[row_index][6] = build_recent_date_formula(offset)
        rows[row_index][7] = build_recent_day_formula("O", offset)
        rows[row_index][8] = build_recent_day_formula("G", offset)
        rows[row_index][9] = build_recent_day_formula("K", offset)
        rows[row_index][10] = build_recent_day_formula("L", offset)
        rows[row_index][11] = build_recent_day_formula("Q", offset)
        rows[row_index][12] = build_recent_day_formula("B", offset)
        rows[row_index][13] = build_recent_day_formula("D", offset)
        rows[row_index][14] = build_recent_day_formula("X", offset)
        rows[row_index][15] = build_recent_day_formula("Y", offset)
        rows[row_index][16] = build_recent_day_formula("T", offset)
        rows[row_index][17] = build_recent_day_formula("U", offset)

    rows[0][19:32] = [
        "週開始日",
        "粗利（新規）",
        "新規着金売上",
        "着金売上",
        "広告費",
        "集客数",
        "個別予約数",
        "会員数",
        "中途解約数",
        "CPA",
        "個別予約CPO",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    rows[1][19] = f'''=IF({ref("end_date")}="","",{ref("end_date")}-WEEKDAY({ref("end_date")},2)+1-77)'''
    for offset in range(12):
        row_index = offset + 1
        row_number = row_index + 1
        if offset > 0:
            rows[row_index][19] = f'=IF($T{row_number - 1}="","",$T{row_number - 1}+7)'
        rows[row_index][20] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$O:$O,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][21] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$G:$G,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][22] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$K:$K,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][23] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$Q:$Q,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][24] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$B:$B,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][25] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$D:$D,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][26] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$X:$X,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][27] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$Y:$Y,\'日別数値\'!$A:$A,">="&$T{row_number},\'日別数値\'!$A:$A,"<"&$T{row_number}+7))'
        rows[row_index][28] = f'=IF(OR($T{row_number}="",N($Y{row_number})=0,N($X{row_number})=0),"",$X{row_number}/$Y{row_number})'
        rows[row_index][29] = f'=IF(OR($T{row_number}="",N($Z{row_number})=0,N($X{row_number})=0),"",$X{row_number}/$Z{row_number})'
        rows[row_index][30] = f'=IF(OR($T{row_number}="",N($X{row_number})=0,N($V{row_number})=0),"",$V{row_number}/$X{row_number})'
        rows[row_index][31] = f'=IF(OR($T{row_number}="",N($X{row_number})=0,N($W{row_number})=0),"",$W{row_number}/$X{row_number})'
    return rows


def read_summary_manual_inputs(summary_ws) -> Dict[str, str]:
    rows = get_range_values_with_retry(summary_ws, "A1:B20", value_render_option="FORMULA")
    values: Dict[str, str] = {}
    for row in rows:
        label = str(row[0]).strip() if row else ""
        raw_value = str(row[1]).strip() if len(row) > 1 else ""
        if label in {"集計開始日", "集計終了日"} and raw_value and not raw_value.startswith("="):
            normalized = normalize_date(raw_value)
            if normalized:
                values["start_date" if label == "集計開始日" else "end_date"] = normalized
    return values


def build_summary_rows(manual_inputs: Dict[str, str] | None = None) -> List[List[str]]:
    manual_inputs = manual_inputs or {}
    rows = [[""] * 60 for _ in range(120)]
    items = [
        {"kind": "header", "row": ["項目", "値"]},
        {"kind": "metric", "key": "start_date", "label": "集計開始日"},
        {"kind": "metric", "key": "end_date", "label": "集計終了日"},
        {"kind": "metric", "key": "gross_profit_new", "label": "粗利（新規）"},
        {"kind": "metric", "key": "new_cash", "label": "新規着金売上"},
        {"kind": "metric", "key": "cash_sales", "label": "着金売上"},
        {"kind": "metric", "key": "lead_count", "label": "集客数"},
        {"kind": "metric", "key": "booking_count", "label": "個別予約数"},
        {"kind": "metric", "key": "member_count", "label": "会員数"},
        {"kind": "metric", "key": "mid_term_cancel_count", "label": "中途解約数"},
        {"kind": "metric", "key": "ad_spend", "label": "広告費"},
        {"kind": "metric", "key": "refunds", "label": "返金額"},
        {"kind": "metric", "key": "lead_uu", "label": "集客数（UU）"},
        {"kind": "metric", "key": "gross_profit", "label": "粗利（合計）"},
        {"kind": "metric", "key": "cpa", "label": "CPA"},
        {"kind": "metric", "key": "booking_cpo", "label": "個別予約CPO"},
        {"kind": "metric", "key": "roas_new", "label": "ROAS（新規）"},
        {"kind": "metric", "key": "roas_total", "label": "ROAS（合計）"},
        {"kind": "metric", "key": "active_member_count", "label": "アクティブ会員数"},
        {"kind": "metric", "key": "installment", "label": "分割回収売上"},
        {"kind": "metric", "key": "recurring", "label": "継続課金売上"},
        {"kind": "metric", "key": "member_single", "label": "会員向け単発売上"},
        {"kind": "metric", "key": "net_cash", "label": "純着金売上"},
        {"kind": "metric", "key": "recovery", "label": "解約請求回収額"},
    ]

    row_map: Dict[str, int] = {}
    current_row = 1
    for item in items:
        if item["kind"] == "metric":
            row_map[item["key"]] = current_row
        current_row += 1

    def ref(key: str) -> str:
        return f"$B${row_map[key]}"

    def date_window_sum_formula(column_letter: str) -> str:
        return (
            f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",'''
            f'''IF(COUNTIFS('日別数値'!{column_letter}:{column_letter},"<>",'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")})=0,"",'''
            f'''SUMIFS('日別数値'!{column_letter}:{column_letter},'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")})))'''
        )

    formula_map = {
        "start_date": manual_inputs.get("start_date") or f'''=IF({ref("end_date")}="","",EOMONTH({ref("end_date")},-1)+1)''',
        "end_date": manual_inputs.get("end_date") or build_latest_actual_date_formula(),
        "lead_count": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",SUMIFS('日別数値'!B:B,'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")}))''',
        "lead_uu": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",SUMIFS('日別数値'!C:C,'日別数値'!A:A,">="&{ref("start_date")},'日別数値'!A:A,"<="&{ref("end_date")}))''',
        "booking_count": date_window_sum_formula("D"),
        "new_cash": date_window_sum_formula("G"),
        "installment": date_window_sum_formula("H"),
        "recurring": date_window_sum_formula("I"),
        "member_single": date_window_sum_formula("J"),
        "cash_sales": date_window_sum_formula("K"),
        "refunds": date_window_sum_formula("L"),
        "net_cash": date_window_sum_formula("M"),
        "recovery": date_window_sum_formula("N"),
        "gross_profit_new": date_window_sum_formula("O"),
        "gross_profit": date_window_sum_formula("P"),
        "ad_spend": date_window_sum_formula("Q"),
        "cpa": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("lead_count")})=0),"",{ref("ad_spend")}/{ref("lead_count")})''',
        "booking_cpo": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("booking_count")})=0),"",{ref("ad_spend")}/{ref("booking_count")})''',
        "roas_new": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("new_cash")})=0),"",{ref("new_cash")}/{ref("ad_spend")})''',
        "roas_total": f'''=IF(OR(N({ref("ad_spend")})=0,N({ref("cash_sales")})=0),"",{ref("cash_sales")}/{ref("ad_spend")})''',
        "member_count": date_window_sum_formula("X"),
        "mid_term_cancel_count": date_window_sum_formula("Y"),
        "active_member_count": f'''=IF(OR({ref("start_date")}="",{ref("end_date")}=""),"",IFERROR(INDEX(FILTER('日別数値'!Z:Z,'日別数値'!A:A>={ref("start_date")},'日別数値'!A:A<={ref("end_date")},'日別数値'!Z:Z<>""),ROWS(FILTER('日別数値'!Z:Z,'日別数値'!A:A>={ref("start_date")},'日別数値'!A:A<={ref("end_date")},'日別数値'!Z:Z<>""))),""))''',
    }

    write_index = 0
    for item in items:
        if item["kind"] == "header":
            rows[write_index][:2] = item["row"]
        else:
            rows[write_index][:2] = [item["label"], formula_map[item["key"]]]
        write_index += 1

    rows[0][19:33] = [
        "日付",
        "粗利（新規）",
        "新規着金売上",
        "着金売上",
        "返金額",
        "広告費",
        "集客数",
        "個別予約数",
        "会員数",
        "中途解約数",
        "CPA",
        "個別予約CPO",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    for offset in range(7):
        row_number = offset + 2
        rows[offset + 1][19] = f'=IF({ref("end_date")}="","",{ref("end_date")}-6+{offset})'
        rows[offset + 1][20] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$O:$O,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][21] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$G:$G,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][22] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$K:$K,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][23] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$L:$L,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][24] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$Q:$Q,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][25] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$B:$B,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][26] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$D:$D,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][27] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$X:$X,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][28] = f'=IF($T{row_number}="","",SUMIFS(\'日別数値\'!$Y:$Y,\'日別数値\'!$A:$A,$T{row_number}))'
        rows[offset + 1][29] = f'=IF(OR($T{row_number}="",N($Y{row_number})=0,N($Z{row_number})=0),"",$Y{row_number}/$Z{row_number})'
        rows[offset + 1][30] = f'=IF(OR($T{row_number}="",N($Z{row_number})=0,N($AA{row_number})=0),"",$Z{row_number}/$AA{row_number})'
        rows[offset + 1][31] = f'=IF(OR($T{row_number}="",N($Y{row_number})=0,N($U{row_number})=0),"",$U{row_number}/$Y{row_number})'
        rows[offset + 1][32] = f'=IF(OR($T{row_number}="",N($Y{row_number})=0,N($V{row_number})=0),"",$V{row_number}/$Y{row_number})'

    rows[0][35:49] = [
        "週開始日",
        "粗利（新規）",
        "新規着金売上",
        "着金売上",
        "返金額",
        "広告費",
        "集客数",
        "個別予約数",
        "会員数",
        "中途解約数",
        "CPA",
        "個別予約CPO",
        "ROAS（新規）",
        "ROAS（合計）",
    ]
    rows[1][35] = f'''=IF({ref("end_date")}="","",{ref("end_date")}-WEEKDAY({ref("end_date")},2)+1-77)'''
    for offset in range(12):
        row_index = offset + 1
        row_number = row_index + 1
        if offset > 0:
            rows[row_index][35] = f'=IF($AJ{row_number - 1}="","",$AJ{row_number - 1}+7)'
        rows[row_index][36] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$O:$O,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][37] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$G:$G,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][38] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$K:$K,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][39] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$L:$L,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][40] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$Q:$Q,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][41] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$B:$B,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][42] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$D:$D,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][43] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$X:$X,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][44] = f'=IF($AJ{row_number}="","",SUMIFS(\'日別数値\'!$Y:$Y,\'日別数値\'!$A:$A,">="&$AJ{row_number},\'日別数値\'!$A:$A,"<"&$AJ{row_number}+7))'
        rows[row_index][45] = f'=IF(OR($AJ{row_number}="",N($AO{row_number})=0,N($AP{row_number})=0),"",$AO{row_number}/$AP{row_number})'
        rows[row_index][46] = f'=IF(OR($AJ{row_number}="",N($AP{row_number})=0,N($AQ{row_number})=0),"",$AP{row_number}/$AQ{row_number})'
        rows[row_index][47] = f'=IF(OR($AJ{row_number}="",N($AO{row_number})=0,N($AL{row_number})=0),"",$AL{row_number}/$AO{row_number})'
        rows[row_index][48] = f'=IF(OR($AJ{row_number}="",N($AO{row_number})=0,N($AM{row_number})=0),"",$AM{row_number}/$AO{row_number})'
    return rows


def build_summary_row_map(summary_rows: Sequence[Sequence[str]]) -> Dict[str, int]:
    row_map: Dict[str, int] = {}
    for index, row in enumerate(summary_rows, start=1):
        label = str(row[0]).strip() if row else ""
        if label and label not in row_map:
            row_map[label] = index
    return row_map



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
        "粗利（新規）",
        "粗利",
        "広告費",
        "CPA",
        "個別予約CPO",
        "ROAS（新規）",
        "ROAS（合計）",
        "契約数",
        "クーリングオフ数",
        "会員数",
        "中途解約数",
        "アクティブ会員数",
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
        "gross_profit_new": "",
        "gross_profit": "",
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
        "gross_profit_new": 0,
        "gross_profit": 0,
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
            contract_count = membership_item["contract_count"]
            cooling_off_count = membership_item["cooling_off_count"]
            member_count = membership_item["member_count"]
            mid_term_cancel_count = membership_item["mid_term_cancel_count"]
            active_member_count = membership_item["active_member_count"]
        elif membership_latest_date and date <= membership_latest_date:
            contract_count = 0
            cooling_off_count = 0
            member_count = 0
            mid_term_cancel_count = 0
            active_member_count = 0
        else:
            contract_count = ""
            cooling_off_count = ""
            member_count = ""
            mid_term_cancel_count = ""
            active_member_count = ""
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
        gross_profit_new = ""
        gross_profit = ""
        if payment_item["new_cash_sales"] != "" and ad_spend != "":
            try:
                gross_profit_new = int(payment_item["new_cash_sales"]) - int(ad_spend)
            except (ValueError, TypeError):
                gross_profit_new = ""
        if (
            payment_item["cash_sales"] != ""
            and payment_item["refunds"] != ""
            and payment_item["recovery_sales"] != ""
            and ad_spend != ""
        ):
            try:
                gross_profit = (
                    int(payment_item["cash_sales"])
                    - int(payment_item["refunds"])
                    - int(ad_spend)
                    + int(payment_item["recovery_sales"])
                )
            except (ValueError, TypeError):
                gross_profit = ""
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
            gross_profit_new,
            gross_profit,
            ad_spend,
            cpa,
            cpo,
            new_cash_roas,
            cash_roas,
            contract_count,
            cooling_off_count,
            member_count,
            mid_term_cancel_count,
            active_member_count,
        ])
    while len(rows) < 120:
        rows.append([""] * 26)
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
    membership_contract = membership_status.get("契約数", {})
    membership_member = membership_status.get("会員数", {})
    membership_mid_term = membership_status.get("中途解約数", {})
    membership_cooling_off = membership_status.get("クーリングオフ数", {})
    membership_active = membership_status.get("アクティブ会員数", {})
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
    ad_spend_memo = ad_spend_status.get("メモ", "広告費管理タブの広告費を日付単位で合算")
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
        ["粗利（新規）", "売上", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "O列", "新規着金売上 - 広告費", "2025/01/01以降", "接続中", "", "", "", "広告費を引いた新規着金ベースの粗利"],
        ["粗利", "売上", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "P列", "着金売上 - 返金額 - 広告費 + 解約請求回収額", "2025/01/01以降", "接続中", "", "", "", "スキルプラス事業の期間粗利"],
        ["広告費", "広告費", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{AD_SPEND_METRICS_SHEET_ID}/edit","【アドネス株式会社】広告データ（加工）")', AD_SPEND_DAILY_TAB, "G列（広告費）", "広告費管理タブの広告費を日付単位で合算", "2025/01/01以降", ad_spend_state, ad_spend_updated_at, ad_spend_updates, ad_spend_errors, ad_spend_memo],
        ["CPA", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "R列", "広告費 / 集客数", "広告費と集客数が入力済み", "接続中", "", "", "", "広告費と集客数が入力された日だけ自動計算"],
        ["個別予約CPO", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "S列", "広告費 / 個別予約数", "広告費と個別予約数が入力済み", "接続中", "", "", "", "広告費と個別予約数が入力された日だけ自動計算"],
        ["ROAS（新規）", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "T列", "新規着金売上 / 広告費", "新規着金売上と広告費が入力済み", "接続中", "", "", "", "広告判断用の新規着金ROAS"],
        ["ROAS（合計）", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "U列", "着金売上 / 広告費", "着金売上と広告費が入力済み", "接続中", "", "", "", "全体像を見るための着金ROAS"],
        ["契約数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "B列", "契約締結日の件数", "2025/01/01以降", membership_contract.get("ステータス", "確認待ち"), membership_contract.get("最終同期日", ""), membership_contract.get("更新数", str(membership_daily_row_count)), membership_contract.get("エラー数", "0"), membership_contract.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["クーリングオフ数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "C列", "日別件数", "2025/01/01以降", membership_cooling_off.get("ステータス", "確認待ち"), membership_cooling_off.get("最終同期日", ""), membership_cooling_off.get("更新数", str(membership_daily_row_count)), membership_cooling_off.get("エラー数", "0"), membership_cooling_off.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["会員数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "D列", "契約締結日から7日経過して会員化した日次件数", "2025/01/01以降", membership_member.get("ステータス", "確認待ち"), membership_member.get("最終同期日", ""), membership_member.get("更新数", str(membership_daily_row_count)), membership_member.get("エラー数", "0"), membership_member.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["中途解約数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "E列", "日別件数", "2025/01/01以降", membership_mid_term.get("ステータス", "確認待ち"), membership_mid_term.get("最終同期日", ""), membership_mid_term.get("更新数", str(membership_daily_row_count)), membership_mid_term.get("エラー数", "0"), membership_mid_term.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
        ["アクティブ会員数", "会員", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{MEMBERSHIP_METRICS_SHEET_ID}/edit","【アドネス株式会社】会員データ（加工）")', MEMBERSHIP_DAILY_TAB, "F列", "会員数の累計から中途解約数の累計を引いた日次残高", "2025/01/01以降", membership_active.get("ステータス", "確認待ち"), membership_active.get("最終同期日", ""), membership_active.get("更新数", str(membership_daily_row_count)), membership_active.get("エラー数", "0"), membership_active.get("メモ", "会員データ（加工）の日別会員数値を参照する")],
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
    spreadsheet = open_spreadsheet_with_retry(gc, DASHBOARD_SHEET_ID)
    tabs = ensure_target_tabs(spreadsheet)
    booking_status = load_booking_status(gc)
    membership_status = load_membership_status(gc)
    payment_status = load_payment_status(gc)

    summary_ws = tabs["スキルプラス事業サマリー"]
    summary_inputs = read_summary_manual_inputs(summary_ws)
    summary_rows = build_summary_rows(summary_inputs)
    write_rows(spreadsheet, summary_ws, summary_rows)
    apply_table_style(
        spreadsheet,
        summary_ws,
        len(summary_rows),
        2,
        widths=[220, 170],
    )
    summary_row_map = build_summary_row_map(summary_rows)

    def value_format_request(label: str, number_format: dict) -> dict:
        row_number = summary_row_map[label]
        return repeat_cell_request(
            summary_ws.id,
            row_number - 1,
            row_number,
            1,
            2,
            {"numberFormat": number_format},
            "userEnteredFormat.numberFormat",
        )

    summary_number_requests = []
    for label in ("集計開始日", "集計終了日"):
        summary_number_requests.append(
            value_format_request(label, {"type": "DATE", "pattern": "yyyy/mm/dd"})
        )
    for label in (
        "会員数",
        "集客数",
        "集客数（UU）",
        "個別予約数",
        "アクティブ会員数",
        "中途解約数",
    ):
        summary_number_requests.append(
            value_format_request(label, {"type": "NUMBER", "pattern": "#,##0"})
        )
    for label in (
        "粗利（新規）",
        "粗利（合計）",
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
    ):
        summary_number_requests.append(
            value_format_request(label, {"type": "CURRENCY", "pattern": "¥#,##0"})
        )
    for label in ("ROAS（新規）", "ROAS（合計）"):
        summary_number_requests.append(
            value_format_request(label, {"type": "PERCENT", "pattern": "0.0%"})
        )
    summary_number_requests.extend(
        [
            repeat_cell_request(
                summary_ws.id,
                1,
                8,
                19,
                20,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                8,
                20,
                25,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                8,
                25,
                29,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                8,
                29,
                31,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                8,
                31,
                33,
                {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                13,
                35,
                36,
                {"numberFormat": {"type": "DATE", "pattern": "yyyy/mm/dd"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                13,
                36,
                41,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                13,
                41,
                45,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                13,
                45,
                47,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                summary_ws.id,
                1,
                13,
                47,
                49,
                {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}},
                "userEnteredFormat.numberFormat",
            ),
        ]
    )
    apply_number_formats(
        spreadsheet,
        summary_ws,
        summary_number_requests,
    )
    summary_structure_requests = [
        repeat_cell_request(
            summary_ws.id,
            0,
            1,
            19,
            33,
            {
                "backgroundColor": {"red": 0.89, "green": 0.95, "blue": 0.99},
                "textFormat": {"bold": True, "fontSize": 11},
                "horizontalAlignment": "LEFT",
                "verticalAlignment": "MIDDLE",
            },
            "userEnteredFormat.backgroundColor,userEnteredFormat.textFormat,userEnteredFormat.horizontalAlignment,userEnteredFormat.verticalAlignment",
        ),
        repeat_cell_request(
            summary_ws.id,
            1,
            2,
            19,
            33,
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
            summary_ws.id,
            1,
            8,
            19,
            33,
            {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        repeat_cell_request(
            summary_ws.id,
            0,
            len(summary_rows),
            0,
            2,
            {
                "verticalAlignment": "MIDDLE",
                "wrapStrategy": "CLIP",
            },
            "userEnteredFormat.verticalAlignment,userEnteredFormat.wrapStrategy",
        ),
        set_date_validation_request(summary_ws.id, 1, 3, 1, 2),
        set_column_hidden_request(summary_ws.id, 19, 49, True),
    ]
    batch_update_with_retry(
        spreadsheet,
        {"requests": summary_structure_requests},
        "スキルプラス事業サマリーの構造更新",
    )
    chart_requests = list_chart_delete_requests(spreadsheet, tabs["スキルプラス事業サマリー"].id)
    chart_requests.extend(
        [
            add_line_chart_request(
                summary_ws.id,
                1,
                2,
                "直近7日 売上・広告",
                19,
                [20, 21, 22, 23, 24],
                end_row_index=8,
                width=980,
                height=240,
            ),
            add_line_chart_request(
                summary_ws.id,
                16,
                2,
                "直近7日 集客・予約・会員",
                19,
                [25, 26, 27, 28],
                end_row_index=8,
                width=980,
                height=240,
            ),
            add_line_chart_request(
                summary_ws.id,
                31,
                2,
                "直近12週間 売上・広告",
                35,
                [36, 37, 38, 39, 40],
                end_row_index=13,
                width=980,
                height=240,
            ),
            add_line_chart_request(
                summary_ws.id,
                46,
                2,
                "直近12週間 集客・予約・会員",
                35,
                [41, 42, 43, 44],
                end_row_index=13,
                width=980,
                height=240,
            ),
            add_line_chart_request(
                summary_ws.id,
                61,
                2,
                "直近12週間 広告効率",
                35,
                [45, 46, 47, 48],
                end_row_index=13,
                width=980,
                height=240,
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
        26,
        widths=[120, 120, 145, 135, 150, 125, 135, 135, 135, 145, 135, 120, 135, 145, 135, 135, 120, 110, 145, 120, 120, 110, 130, 120, 120, 135],
    )
    apply_single_line_header(spreadsheet, tabs["日別数値"], 26)
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
                19,
                {"numberFormat": {"type": "CURRENCY", "pattern": "¥#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                19,
                21,
                {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}},
                "userEnteredFormat.numberFormat",
            ),
            repeat_cell_request(
                tabs["日別数値"].id,
                1,
                len(daily_rows),
                21,
                26,
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
