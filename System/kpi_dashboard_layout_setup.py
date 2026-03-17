#!/usr/bin/env python3
"""
【アドネス株式会社】KPIダッシュボードの最小構成を整える。

方針:
- ダッシュボードは表示層に徹する
- 第1版は `定義 / スキルプラス事業サマリー / 日別数値 / データソース管理` の4タブだけを表に出す
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
EMAIL_METRICS_SHEET_ID = "13HS9KmlTdxQwMMaK45H3Ga1mMTUiJdhYKWnrExge_yY"
EMAIL_COUNT_TAB = "日別メール登録件数"
EMAIL_UU_TAB = "日別メール登録件数（UU）"
EMAIL_SUMMARY_TAB = "メール集計サマリー"
BOOKING_METRICS_SHEET_ID = "1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8"
BOOKING_COUNT_TAB = "日別個別予約数"
BOOKING_SUMMARY_TAB = "個別予約サマリー"
BOOKING_SOURCE_TAB = "データソース管理"

TAB_SPECS = [
    ("定義", 80, 2),
    ("スキルプラス事業サマリー", 120, 23),
    ("日別数値", 600, 14),
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

HEADER_BG = {"red": 0.26, "green": 0.52, "blue": 0.96}
HEADER_TEXT = {
    "foregroundColor": {"red": 1, "green": 1, "blue": 1},
    "bold": True,
    "fontSize": 12,
}
TAB_COLORS = {
    "定義": "#9E9E9E",
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
    width: int = 620,
    height: int = 260,
) -> dict:
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
                                                "sheetId": sheet_id,
                                                "startRowIndex": 0,
                                                "endRowIndex": 120,
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
                                                "sheetId": sheet_id,
                                                "startRowIndex": 0,
                                                "endRowIndex": 120,
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


def is_quota_error(exc: APIError) -> bool:
    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    return status_code == 429 or "Quota exceeded" in str(exc)


def run_write_with_retry(description: str, func):
    last_error = None
    waits = (0, *WRITE_RETRY_SECONDS)
    for attempt, wait_seconds in enumerate(waits, start=1):
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return func()
        except APIError as exc:
            if not is_quota_error(exc) or attempt == len(waits):
                raise
            last_error = exc
            print(
                f"{description}: Sheets の書き込み回数制限に当たったため "
                f"{wait_seconds or 0}秒後に再試行します。"
            )
    if last_error:
        raise last_error


def batch_update_with_retry(spreadsheet, body: dict, description: str) -> None:
    run_write_with_retry(description, lambda: spreadsheet.batch_update(body))


def worksheet_write_with_retry(description: str, func) -> None:
    run_write_with_retry(description, func)


def parse_int(raw: str) -> int:
    value = str(raw or "").replace(",", "").strip()
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


def ensure_target_tabs(spreadsheet) -> Dict[str, object]:
    worksheets = {ws.title: ws for ws in spreadsheet.worksheets()}

    for old_name, new_name in RENAME_TABS.items():
        if old_name in worksheets and new_name not in worksheets:
            worksheet_write_with_retry(
                f"{old_name} タブ名の変更",
                lambda old_name=old_name, new_name=new_name: worksheets[old_name].update_title(new_name),
            )
            worksheets[new_name] = worksheets.pop(old_name)

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


def build_definition_rows() -> List[List[str]]:
    return [
        ["項目", "定義"],
        ["日付", "1日ごとの集計日。ダッシュボード全体の日次の基準になる日付"],
        ["集客数", "ユーザーがメールアドレス登録もしくはLINE登録をした人数"],
        ["集客数（UU）", "ユーザーがメールアドレス登録もしくはLINE登録をしたユニークユーザー数"],
        ["オプトイン数", "メールアドレス登録人数"],
        ["リストイン数", "LINE登録数"],
        ["個別予約数", "ユーザーに ★【個別予約完了】★ が付与された予約イベント数。現行は【アドネス】顧客管理シート / 個別予約集計botログ を暫定正本にし、継続体制では Slack #個別予約通知 から作る 個別予約通知ログ へ切り替える"],
        ["個別予約数（UU）", "現時点では未接続。将来、個別予約完了タグの通知ログとLINE統合後の同一人物判定で算出するユニークユーザー数"],
        ["個別実施数", "将来接続。オンライン面談でZoomに接続したユーザー数"],
        ["着金売上", "ユーザーの申込金額のうち、銀行口座に入金することが確定した金額"],
        ["広告費", "対象媒体の消化金額"],
        ["CPA", "広告費 / 集客数"],
        ["個別予約CPO", "広告費 / 個別予約数"],
        ["ROAS", "着金売上 / 広告費"],
        ["会員数", "スキルプラスの契約締結日から7日間が経過したユーザー数"],
        ["中途解約数", "会員中にサポート期間が終了する前に契約解除が確定したユーザー数"],
        ["クーリングオフ数", "入金あり契約から7日以内に契約解除を申し出たユーザー数"],
    ]


def build_summary_rows(booking_status: Dict[str, str]) -> List[List[str]]:
    booking_state = booking_status.get("ステータス", "接続中") or "接続中"
    rows = [[""] * 23 for _ in range(120)]
    visible_rows = [
        ["項目", "値", "正本シート", "状態", "メモ"],
        ["集計開始日", '=IFERROR(EOMONTH(MAX(FILTER(\'日別数値\'!A:A,\'日別数値\'!A:A<>"")),-1)+1,"")', "", "", "手入力で上書き可"],
        ["集計終了日", '=IFERROR(MAX(FILTER(\'日別数値\'!A:A,\'日別数値\'!A:A<>"")),"")', "", "", "手入力で上書き可"],
        ["最終更新日", '=IFERROR(MAX(FILTER(\'日別数値\'!A:A,\'日別数値\'!A:A<>"")),"")', "【アドネス株式会社】KPIダッシュボード / 日別数値", "接続中", ""],
        ["集客数", '=IF(OR($B$2="",$B$3=""),"",SUMIFS(\'日別数値\'!B:B,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3))', "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数", "一部接続", "現状はメールのみ。LINE未接続"],
        ["集客数（UU）", '=IF(OR($B$2="",$B$3=""),"",SUMIFS(\'日別数値\'!C:C,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3))', "【アドネス株式会社】集客データ_メール集計（加工） / 日別メール登録件数（UU）", "一部接続", "現状はメールのみ。LINE未接続"],
        ["個別予約数", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3,\'日別数値\'!D:D,"<>")=0,"",SUMIFS(\'日別数値\'!D:D,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "【アドネス株式会社】個別面談データ（加工） / 日別個別予約数", booking_state, "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する"],
        ["個別予約数（UU）", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3,\'日別数値\'!E:E,"<>")=0,"",SUMIFS(\'日別数値\'!E:E,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "【アドネス株式会社】個別面談データ（加工） / 日別個別予約数（UU）", "確認待ち", "個別予約完了タグの通知ログとLINE統合後に接続"],
        ["個別実施数", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3,\'日別数値\'!F:F,"<>")=0,"",SUMIFS(\'日別数値\'!F:F,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "Zoom接続ログ または 面談ダッシュボード", "確認待ち", "正本未確定。今は未接続"],
        ["着金売上", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!G:G,"<>",\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)=0,"",SUMIFS(\'日別数値\'!G:G,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "決済履歴シート + お客様相談窓口_進捗管理シート", "確認待ち", "着金の正本を日別で固める必要あり"],
        ["広告費", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!H:H,"<>",\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)=0,"",SUMIFS(\'日別数値\'!H:H,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "媒体原本（Meta / Google / TikTok / X）", "確認待ち", "legacy の Looker 依存から切り替える"],
        ["CPA", '=IF(OR(N(B11)=0,N(B5)=0),"",B11/B5)', "", "未接続", "広告費 / 集客数"],
        ["個別予約CPO", '=IF(OR(N(B11)=0,N(B7)=0),"",B11/B7)', "", "未接続", "広告費 / 個別予約数"],
        ["ROAS", '=IF(OR(N(B11)=0,N(B10)=0),"",B10/B11)', "", "未接続", "着金売上 / 広告費"],
        ["会員数", '=IF(OR($B$2="",$B$3=""),"",IFERROR(INDEX(FILTER(\'日別数値\'!L:L,\'日別数値\'!A:A>=$B$2,\'日別数値\'!A:A<=$B$3,\'日別数値\'!L:L<>""),ROWS(FILTER(\'日別数値\'!L:L,\'日別数値\'!A:A>=$B$2,\'日別数値\'!A:A<=$B$3,\'日別数値\'!L:L<>""))),""))', "【アドネス株式会社】会員データ（加工） / 日別会員数値", "確認待ち", "契約締結日から7日経過した会員の日次残高を使う"],
        ["中途解約数", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!M:M,"<>",\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)=0,"",SUMIFS(\'日別数値\'!M:M,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "【アドネス株式会社】会員データ（加工） / 日別会員数値", "確認待ち", "お客様相談窓口_進捗管理シートの中途解約完了を日別件数へ集計する"],
        ["クーリングオフ数", '=IF(OR($B$2="",$B$3=""),"",IF(COUNTIFS(\'日別数値\'!N:N,"<>",\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)=0,"",SUMIFS(\'日別数値\'!N:N,\'日別数値\'!A:A,">="&$B$2,\'日別数値\'!A:A,"<="&$B$3)))', "【アドネス株式会社】会員データ（加工） / 日別会員数値", "確認待ち", "お客様相談窓口_進捗管理シートのクーリングオフ完了を日別件数へ集計する"],
    ]
    for row in visible_rows:
        if len(row) > 4 and "現行は botログ。将来は個別予約完了タグの通知ログへ切替候補" in str(row[4]):
            row[4] = str(row[4]).replace(
                "現行は botログ。将来は個別予約完了タグの通知ログへ切替候補",
                "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する",
            )
    for row_index, row in enumerate(visible_rows):
        rows[row_index][:5] = row

    helper_headers = [
        "日付", "集客数", "集客数（UU）", "個別予約数", "個別予約数（UU）", "個別実施数",
        "着金売上", "広告費", "CPA", "個別予約CPO", "ROAS", "会員数", "中途解約数", "クーリングオフ数",
    ]
    rows[0][9:23] = helper_headers
    rows[1][9] = '=IFERROR(FILTER(\'日別数値\'!A2:N,\'日別数値\'!A2:A>=$B$2,\'日別数値\'!A2:A<=$B$3),"")'
    return rows


def header_only_rows(headers: Sequence[str], min_rows: int) -> List[List[str]]:
    rows = [list(headers)]
    while len(rows) < min_rows:
        rows.append([""] * len(headers))
    return rows


def build_daily_rows(metrics: Sequence[dict], booking_metrics: Sequence[dict]) -> List[List[str]]:
    email_map = {item["date"]: item for item in metrics}
    booking_map = {item["date"]: item for item in booking_metrics}
    booking_latest_date = max(booking_map.keys()) if booking_map else ""
    all_dates = sorted(set(email_map.keys()) | set(booking_map.keys()))

    rows = [[
        "日付",
        "集客数",
        "集客数（UU）",
        "個別予約数",
        "個別予約数（UU）",
        "個別実施数",
        "着金売上",
        "広告費",
        "CPA",
        "個別予約CPO",
        "ROAS",
        "会員数",
        "中途解約数",
        "クーリングオフ数",
    ]]
    for date in all_dates:
        email_item = email_map.get(date, {"count": "", "uu_count": ""})
        if date in booking_map:
            booking_count = booking_map[date]["count"]
        elif booking_latest_date and date <= booking_latest_date:
            booking_count = 0
        else:
            booking_count = ""
        rows.append([
            date,
            email_item["count"],
            email_item["uu_count"],
            booking_count,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ])
    while len(rows) < 120:
        rows.append([""] * 14)
    return rows


def build_data_source_rows(status: Dict[str, str], daily_row_count: int, booking_status: Dict[str, str], booking_daily_row_count: int) -> List[List[str]]:
    updated_at = status.get("更新日時", "")
    booking_updated_at = booking_status.get("最終同期日") or booking_status.get("更新日時", "")
    booking_state = booking_status.get("ステータス", "未接続")
    booking_memo = booking_status.get("メモ", "現行は botログ。継続体制では Slack #個別予約通知 から作る 個別予約通知ログへ移行する")
    booking_updates = booking_status.get("更新数", str(booking_daily_row_count))
    booking_errors = booking_status.get("エラー数", "0")
    rows = [
        ["KPIカラム", "グループ", "ソース元", "優先度", "スプレッドシートURL", "タブ名", "参照先列", "正規化 / 計算", "入力条件", "ステータス", "最終同期日", "更新数", "エラー数", "メモ"],
        ["集客数", "集客", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{EMAIL_METRICS_SHEET_ID}/edit","【アドネス株式会社】集客データ_メール集計（加工）")', "日別メール登録件数", "B列", "重複あり件数", "2025/01/01以降", "一部接続", updated_at, str(daily_row_count), "0", "現状はメールのみ。LINE未接続"],
        ["集客数（UU）", "集客", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{EMAIL_METRICS_SHEET_ID}/edit","【アドネス株式会社】集客データ_メール集計（加工）")', "日別メール登録件数（UU）", "B列", "最初に確認された日にだけ1件", "2025/01/01以降", "一部接続", updated_at, str(daily_row_count), "0", "現状はメールのみ。LINE未接続"],
        ["個別予約数", "個別予約", "加工データ", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{BOOKING_METRICS_SHEET_ID}/edit","【アドネス株式会社】個別面談データ（加工）")', "日別個別予約数", "B列", "キャンセルではない個別予約イベント数", "2025/01/01以降", booking_state, booking_updated_at, booking_updates, booking_errors, booking_memo],
        ["個別予約数（UU）", "個別予約", "加工データ", "2", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{BOOKING_METRICS_SHEET_ID}/edit","【アドネス株式会社】個別面談データ（加工）")', "日別個別予約数（UU）", "B列", "将来接続。ユニークユーザー数", "個別予約完了タグの通知ログとLINE統合後", "確認待ち", "", "", "", "現時点ではユニーク判定が弱いため未接続"],
        ["個別実施数", "個別予約", "収集データ候補", "2", "", "Zoom接続ログ または 面談ダッシュボード", "", "接続ユーザー数", "正本未確定", "確認待ち", "", "", "", "今は未接続"],
        ["着金売上", "売上", "収集データ候補", "1", "", "決済履歴シート + お客様相談窓口_進捗管理シート", "", "日別着金額", "着金日と返金処理の確定", "確認待ち", "", "", "", "日別正本の集計シートが未作成"],
        ["広告費", "広告費", "収集データ候補", "1", "", "媒体原本（Meta / Google / TikTok / X）", "", "対象媒体の消化額", "対象アカウントの確定", "確認待ち", "", "", "", "legacy の Looker 依存を外す必要あり"],
        ["CPA", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "I列", "広告費 / 集客数", "広告費と集客数が入力済み", "未接続", "", "", "", "自動計算予定"],
        ["個別予約CPO", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "J列", "広告費 / 個別予約数", "広告費と個別予約数が入力済み", "未接続", "", "", "", "自動計算予定"],
        ["ROAS", "計算値", "計算式", "1", f'=HYPERLINK("https://docs.google.com/spreadsheets/d/{DASHBOARD_SHEET_ID}/edit","【アドネス株式会社】KPIダッシュボード")', "日別数値", "K列", "着金売上 / 広告費", "着金売上と広告費が入力済み", "未接続", "", "", "", "自動計算予定"],
        ["会員数", "会員", "収集データ候補", "1", "", "全面談合算 + お客様相談窓口_進捗管理シート", "契約締結日 / 入金前契約解除 / クーリングオフ / 中途解約", "契約締結日から7日経過した会員の日次残高", "会員イベントの定義確定後", "確認待ち", "", "", "", "会員データ（加工）の日別残高シートが未作成"],
        ["中途解約数", "会員", "収集データ候補", "1", "", "お客様相談窓口_進捗管理シート", "管理用_20250125-中途解約 / 対応完了日", "日別件数", "中途解約日の集計ルール確定後", "確認待ち", "", "", "", "会員データ（加工）で日別件数へ集計する"],
        ["クーリングオフ数", "会員", "収集データ候補", "1", "", "お客様相談窓口_進捗管理シート", "管理用_2025.1.25-クーオフ / 対応完了日", "日別件数", "クーリングオフ日の集計ルール確定後", "確認待ち", "", "", "", "お客様相談窓口_進捗管理シートの集計をそのまま使う"],
    ]
    while len(rows) < 30:
        rows.append([""] * 14)
    return rows


def set_tab_color(ws, color: str) -> None:
    try:
        ws.update_tab_color(color)
    except Exception:
        pass


def main() -> None:
    gc = get_client()
    spreadsheet = gc.open_by_key(DASHBOARD_SHEET_ID)
    tabs = ensure_target_tabs(spreadsheet)
    booking_status = load_booking_status(gc)

    definition_rows = build_definition_rows()
    write_rows(spreadsheet, tabs["定義"], definition_rows)
    apply_table_style(
        spreadsheet,
        tabs["定義"],
        len(definition_rows),
        2,
        widths=[180, 620],
    )

    summary_rows = build_summary_rows(booking_status)
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
                17,
                1,
                2,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
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
    batch_update_with_retry(
        spreadsheet,
        {
            "requests": [
                set_column_hidden_request(tabs["スキルプラス事業サマリー"].id, 9, 23, True),
                add_line_chart_request(
                    tabs["スキルプラス事業サマリー"].id,
                    0,
                    6,
                    "日別集客推移",
                    9,
                    [10, 11],
                ),
                add_line_chart_request(
                    tabs["スキルプラス事業サマリー"].id,
                    18,
                    6,
                    "日別予約・実施推移",
                    9,
                    [12, 13, 14],
                ),
                add_line_chart_request(
                    tabs["スキルプラス事業サマリー"].id,
                    36,
                    6,
                    "日別売上・広告費推移",
                    9,
                    [15, 16],
                ),
                add_line_chart_request(
                    tabs["スキルプラス事業サマリー"].id,
                    54,
                    6,
                    "日別会員推移",
                    9,
                    [20, 21, 22],
                ),
            ]
        },
        "スキルプラス事業サマリーのグラフ更新",
    )

    daily_metrics = load_email_daily_metrics(gc)
    booking_metrics = load_booking_daily_metrics(gc)
    daily_rows = build_daily_rows(daily_metrics, booking_metrics)
    write_rows(spreadsheet, tabs["日別数値"], daily_rows)
    apply_table_style(
        spreadsheet,
        tabs["日別数値"],
        len(daily_rows),
        14,
        widths=[110, 100, 120, 110, 120, 110, 120, 110, 90, 120, 90, 110, 100, 180],
    )
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
                14,
                {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}},
                "userEnteredFormat.numberFormat",
            ),
        ],
    )

    email_metrics_status = load_email_metrics_status(gc)
    data_source_rows = build_data_source_rows(
        email_metrics_status,
        max(len(daily_metrics), 0),
        booking_status,
        max(len(booking_metrics), 0),
    )
    write_rows(spreadsheet, tabs["データソース管理"], data_source_rows)
    apply_table_style(
        spreadsheet,
        tabs["データソース管理"],
        len(data_source_rows),
        14,
        widths=[140, 110, 110, 70, 230, 160, 100, 160, 140, 90, 140, 90, 80, 220],
    )
    apply_status_cell_colors(
        spreadsheet,
        tabs["データソース管理"],
        data_source_rows,
        9,
    )

    for title, _rows, _cols in TAB_SPECS:
        set_tab_color(tabs[title], TAB_COLORS[title])

    print("【アドネス株式会社】KPIダッシュボードの最小構成を更新しました。")


if __name__ == "__main__":
    main()
