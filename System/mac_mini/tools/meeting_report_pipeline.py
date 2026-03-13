#!/usr/bin/env python3
"""経営会議資料を Sheets 正本で生成するパイプライン。"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")
os.environ.setdefault("MPLCONFIGDIR", "/tmp/addness_mpl_meeting_report")

import matplotlib.pyplot as plt
import requests
from PIL import Image, ImageDraw, ImageFont

SYSTEM_DIR = Path(__file__).resolve().parents[2]
if str(SYSTEM_DIR) not in sys.path:
    sys.path.insert(0, str(SYSTEM_DIR))

from docs_manager import get_service as get_google_service
from sheets_manager import get_client
from mac_mini.tools.meeting_report_v4 import delete_current_section

REPORT_DOC_ID = "18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s"
REPORT_SHEET_ID = "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk"
REPORT_TAB_NAME = "日報"
MEETING_MASTER_TAB = "経営会議KPI"

SKILL_PLUS_SHEET_ID = "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
SKILL_PLUS_DAILY_TAB = "スキルプラス（日別）"

CONFIG_PATH = SYSTEM_DIR / "line_bot_local" / "config.json"
OUTPUT_ROOT = Path("/tmp/meeting_report")
TIMEZONE = ZoneInfo("Asia/Tokyo")

ROAS_TARGET = 300.0
CPA_TARGET = 3000.0

CARD_COLORS = [
    "#E8EBF7",
    "#E7EDF6",
    "#E5F3F3",
    "#E3F0EB",
    "#F1EEDC",
    "#F3EBE0",
    "#F3E8F1",
    "#ECEDEF",
    "#E5F0EA",
]


@dataclass(frozen=True)
class MeetingPeriods:
    meeting_date: date
    month_start: date
    month_end: date
    week_start: date
    week_end: date
    prev_week_start: date
    prev_week_end: date
    days_in_month: int
    elapsed_days: int


def _parse_number(value: Any) -> float:
    text = str(value or "").replace(",", "").replace("¥", "").replace("%", "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _safe_div(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return numerator / denominator


def _safe_pct_change(current: float, previous: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / previous


def _format_int(value: float) -> str:
    return f"{int(round(value)):,}"


def _format_signed_int(value: float) -> str:
    rounded = int(round(value))
    return f"{rounded:+,}"


def _format_pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def _format_signed_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.{digits}f}%"


def _format_signed_point(value: float) -> str:
    return f"{value:+.0f}pt"


def _format_yen(value: float) -> str:
    return f"{int(round(value)):,}円"


def _format_compact_yen(value: float) -> str:
    amount = float(value)
    abs_amount = abs(amount)
    if abs_amount >= 100_000_000:
        formatted = f"{amount / 100_000_000:.2f}".rstrip("0").rstrip(".")
        return f"{formatted}億円"
    if abs_amount >= 10_000:
        return f"{amount / 10_000:,.0f}万円"
    return _format_yen(amount)


def _format_budget_yen(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f}億円"
    return _format_compact_yen(value)


def _format_people(value: float) -> str:
    return f"{int(round(value)):,}人"


def _metric_row(label: str, unit: str, target: float, actual: float, progress: float, forecast: float | None, note: str) -> list[Any]:
    return [
        label,
        unit,
        target,
        actual,
        progress,
        "" if forecast is None else forecast,
        note,
    ]


def calculate_periods(meeting_date: date) -> MeetingPeriods:
    month_start = meeting_date.replace(day=1)
    month_end = meeting_date - timedelta(days=2)
    week_end = month_end
    week_start = week_end - timedelta(days=6)
    prev_week_end = week_start - timedelta(days=1)
    prev_week_start = prev_week_end - timedelta(days=6)
    days_in_month = calendar.monthrange(meeting_date.year, meeting_date.month)[1]
    elapsed_days = (month_end - month_start).days + 1
    return MeetingPeriods(
        meeting_date=meeting_date,
        month_start=month_start,
        month_end=month_end,
        week_start=week_start,
        week_end=week_end,
        prev_week_start=prev_week_start,
        prev_week_end=prev_week_end,
        days_in_month=days_in_month,
        elapsed_days=elapsed_days,
    )


def _date_label(target_date: date) -> str:
    return f"{target_date.month}/{target_date.day}"


def _period_text(start: date, end: date) -> str:
    return f"{start.month}/{start.day}-{end.month}/{end.day}"


def _load_report_sheet() -> list[list[str]]:
    client = get_client()
    ws = client.open_by_key(REPORT_SHEET_ID).worksheet(REPORT_TAB_NAME)
    return ws.get_all_values()


def _load_skill_plus_rows() -> list[list[str]]:
    client = get_client()
    ws = client.open_by_key(SKILL_PLUS_SHEET_ID).worksheet(SKILL_PLUS_DAILY_TAB)
    return ws.get_all_values()


def _build_report_row_map(report_rows: list[list[str]]) -> tuple[list[str], dict[str, list[str]]]:
    if len(report_rows) < 5:
        raise ValueError("日報シートの行数が不足しています")

    header = report_rows[0]
    row_by_label: dict[str, list[str]] = {}
    for row in report_rows[:20]:
        label = row[2].strip() if len(row) > 2 else ""
        if label and label not in row_by_label:
            row_by_label[label] = row

    required_labels = [
        "着金売上（確定ベース）",
        "広告費（新井さん集計待ち）",
        "集客数",
        "個別予約数",
        "スキルプラス会員数",
        "解約数",
        "サブスク新規会員数",
    ]
    missing = [label for label in required_labels if label not in row_by_label]
    if missing:
        raise ValueError(f"日報シートの要約行が不足しています: {', '.join(missing)}")
    return header, row_by_label


def _period_indices(header: list[str], start_date: date, end_date: date) -> list[int]:
    indices: list[int] = []
    current = start_date
    while current <= end_date:
        label = _date_label(current)
        try:
            indices.append(header.index(label))
        except ValueError as exc:
            raise ValueError(f"日報シートに {label} 列がありません") from exc
        current += timedelta(days=1)
    return indices


def _sum_row_period(row: list[str], indices: list[int]) -> float:
    total = 0.0
    for idx in indices:
        if idx < len(row):
            total += _parse_number(row[idx])
    return total


def _metric_total(row_by_label: dict[str, list[str]], label: str, indices: list[int]) -> float:
    return _sum_row_period(row_by_label[label], indices)


def _aggregate_skill_plus_by_date(rows: list[list[str]]) -> dict[date, dict[str, float]]:
    totals: dict[date, dict[str, float]] = defaultdict(
        lambda: {"leads": 0.0, "bookings": 0.0, "revenue": 0.0, "ad_spend": 0.0}
    )
    for row in rows[3:]:
        if not row or not row[0]:
            continue
        try:
            current_date = date.fromisoformat(row[0][:10])
        except ValueError:
            continue
        totals[current_date]["leads"] += _parse_number(row[4] if len(row) > 4 else 0)
        totals[current_date]["bookings"] += _parse_number(row[5] if len(row) > 5 else 0)
        totals[current_date]["revenue"] += _parse_number(row[7] if len(row) > 7 else 0)
        totals[current_date]["ad_spend"] += _parse_number(row[8] if len(row) > 8 else 0)
    return totals


def _build_trend_weeks(periods: MeetingPeriods, daily_totals: dict[date, dict[str, float]]) -> list[dict[str, Any]]:
    weeks: list[dict[str, Any]] = []
    for offset in range(11, -1, -1):
        week_end = periods.week_end - timedelta(days=offset * 7)
        week_start = week_end - timedelta(days=6)
        leads = bookings = revenue = ad_spend = 0.0
        current = week_start
        while current <= week_end:
            day_total = daily_totals.get(current, {})
            leads += day_total.get("leads", 0.0)
            bookings += day_total.get("bookings", 0.0)
            revenue += day_total.get("revenue", 0.0)
            ad_spend += day_total.get("ad_spend", 0.0)
            current += timedelta(days=1)
        cpa = _safe_div(ad_spend, leads)
        roas = _safe_div(revenue, ad_spend) * 100
        weeks.append(
            {
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "label": _period_text(week_start, week_end),
                "leads": round(leads),
                "bookings": round(bookings),
                "revenue": round(revenue),
                "ad_spend": round(ad_spend),
                "cpa": round(cpa),
                "roas": round(roas, 1),
            }
        )
    return weeks


def _derive_score_and_comment(monthly: dict[str, Any]) -> tuple[int, str]:
    revenue_forecast_ratio = _safe_div(monthly["forecast_revenue"], monthly["revenue_target"])
    lead_forecast_ratio = _safe_div(monthly["forecast_leads"], monthly["lead_target"])
    roas = monthly["roas"]

    if revenue_forecast_ratio >= 1.05 and lead_forecast_ratio >= 1.0 and roas >= ROAS_TARGET:
        score = 5
    elif revenue_forecast_ratio >= 0.9 and lead_forecast_ratio >= 0.9 and roas >= 250:
        score = 4
    elif revenue_forecast_ratio >= 0.75 and lead_forecast_ratio >= 0.8:
        score = 3
    elif revenue_forecast_ratio >= 0.5 or lead_forecast_ratio >= 0.6:
        score = 2
    else:
        score = 1

    if revenue_forecast_ratio >= 1.0 and roas >= ROAS_TARGET:
        comment = "着金売上は目標ペースです。集客量とROASの両方を維持できています。"
    elif revenue_forecast_ratio >= 0.8 and lead_forecast_ratio >= 0.9:
        comment = "集客は進んでいますが、着金売上はまだ目標ペース未達です。ROAS改善が引き続き必要です。"
    elif lead_forecast_ratio >= 0.8:
        comment = "集客は一定水準を維持していますが、着金売上が目標ペースを下回っています。着金効率の改善が必要です。"
    else:
        comment = "着金売上と集客数の両方が目標ペース未達です。集客量とROASを同時に立て直す必要があります。"
    return score, comment


def build_meeting_dataset(meeting_date: date | None = None) -> dict[str, Any]:
    current_date = meeting_date or datetime.now(TIMEZONE).date()
    periods = calculate_periods(current_date)

    report_rows = _load_report_sheet()
    header, row_by_label = _build_report_row_map(report_rows)
    month_indices = _period_indices(header, periods.month_start, periods.month_end)
    week_indices = _period_indices(header, periods.week_start, periods.week_end)
    prev_week_indices = _period_indices(header, periods.prev_week_start, periods.prev_week_end)

    revenue_target = _parse_number(row_by_label["着金売上（確定ベース）"][3])
    ad_spend_budget = _parse_number(row_by_label["広告費（新井さん集計待ち）"][3])
    lead_target = _parse_number(row_by_label["集客数"][3])
    booking_target = _parse_number(row_by_label["個別予約数"][3])

    revenue_actual = _metric_total(row_by_label, "着金売上（確定ベース）", month_indices)
    ad_spend_actual = _metric_total(row_by_label, "広告費（新井さん集計待ち）", month_indices)
    leads_actual = _metric_total(row_by_label, "集客数", month_indices)
    bookings_actual = _metric_total(row_by_label, "個別予約数", month_indices)
    member_net_actual = _metric_total(row_by_label, "スキルプラス会員数", month_indices)
    cancellations_actual = _metric_total(row_by_label, "解約数", month_indices)
    new_subscribers_actual = _metric_total(row_by_label, "サブスク新規会員数", month_indices)

    revenue_week = _metric_total(row_by_label, "着金売上（確定ベース）", week_indices)
    ad_spend_week = _metric_total(row_by_label, "広告費（新井さん集計待ち）", week_indices)
    leads_week = _metric_total(row_by_label, "集客数", week_indices)
    bookings_week = _metric_total(row_by_label, "個別予約数", week_indices)
    member_net_week = _metric_total(row_by_label, "スキルプラス会員数", week_indices)
    cancellations_week = _metric_total(row_by_label, "解約数", week_indices)

    revenue_prev_week = _metric_total(row_by_label, "着金売上（確定ベース）", prev_week_indices)
    ad_spend_prev_week = _metric_total(row_by_label, "広告費（新井さん集計待ち）", prev_week_indices)
    leads_prev_week = _metric_total(row_by_label, "集客数", prev_week_indices)
    bookings_prev_week = _metric_total(row_by_label, "個別予約数", prev_week_indices)
    member_net_prev_week = _metric_total(row_by_label, "スキルプラス会員数", prev_week_indices)
    cancellations_prev_week = _metric_total(row_by_label, "解約数", prev_week_indices)

    roas_actual = _safe_div(revenue_actual, ad_spend_actual) * 100
    cpa_actual = _safe_div(ad_spend_actual, leads_actual)
    cpo_actual = _safe_div(ad_spend_actual, bookings_actual)
    forecast_revenue = _safe_div(revenue_actual, periods.elapsed_days) * periods.days_in_month
    forecast_leads = _safe_div(leads_actual, periods.elapsed_days) * periods.days_in_month

    roas_week = _safe_div(revenue_week, ad_spend_week) * 100
    cpa_week = _safe_div(ad_spend_week, leads_week)
    cpo_week = _safe_div(ad_spend_week, bookings_week)
    roas_prev_week = _safe_div(revenue_prev_week, ad_spend_prev_week) * 100
    cpa_prev_week = _safe_div(ad_spend_prev_week, leads_prev_week)
    cpo_prev_week = _safe_div(ad_spend_prev_week, bookings_prev_week)

    monthly = {
        "revenue_target": revenue_target,
        "revenue_actual": revenue_actual,
        "revenue_progress": _safe_div(revenue_actual, revenue_target),
        "forecast_revenue": forecast_revenue,
        "ad_spend_budget": ad_spend_budget,
        "ad_spend_actual": ad_spend_actual,
        "ad_spend_progress": _safe_div(ad_spend_actual, ad_spend_budget),
        "lead_target": lead_target,
        "lead_actual": leads_actual,
        "lead_progress": _safe_div(leads_actual, lead_target),
        "forecast_leads": forecast_leads,
        "booking_target": booking_target,
        "booking_actual": bookings_actual,
        "booking_progress": _safe_div(bookings_actual, booking_target),
        "member_net_actual": member_net_actual,
        "cancellations_actual": cancellations_actual,
        "new_subscribers_actual": new_subscribers_actual,
        "roas": roas_actual,
        "cpa": cpa_actual,
        "cpo": cpo_actual,
    }

    weekly = {
        "lead_current": leads_week,
        "lead_previous": leads_prev_week,
        "lead_change_pct": _safe_pct_change(leads_week, leads_prev_week),
        "lead_change_abs": leads_week - leads_prev_week,
        "booking_current": bookings_week,
        "booking_previous": bookings_prev_week,
        "booking_change_pct": _safe_pct_change(bookings_week, bookings_prev_week),
        "booking_change_abs": bookings_week - bookings_prev_week,
        "revenue_current": revenue_week,
        "revenue_previous": revenue_prev_week,
        "revenue_change_pct": _safe_pct_change(revenue_week, revenue_prev_week),
        "revenue_change_abs": revenue_week - revenue_prev_week,
        "ad_spend_current": ad_spend_week,
        "ad_spend_previous": ad_spend_prev_week,
        "ad_spend_change_pct": _safe_pct_change(ad_spend_week, ad_spend_prev_week),
        "ad_spend_change_abs": ad_spend_week - ad_spend_prev_week,
        "roas_current": roas_week,
        "roas_previous": roas_prev_week,
        "roas_change_pt": roas_week - roas_prev_week,
        "cpa_current": cpa_week,
        "cpa_previous": cpa_prev_week,
        "cpa_change_pct": _safe_pct_change(cpa_week, cpa_prev_week),
        "cpa_change_abs": cpa_week - cpa_prev_week,
        "cpo_current": cpo_week,
        "cpo_previous": cpo_prev_week,
        "cpo_change_pct": _safe_pct_change(cpo_week, cpo_prev_week),
        "cpo_change_abs": cpo_week - cpo_prev_week,
        "member_net_current": member_net_week,
        "member_net_previous": member_net_prev_week,
        "member_net_change_abs": member_net_week - member_net_prev_week,
        "cancellations_current": cancellations_week,
        "cancellations_previous": cancellations_prev_week,
        "cancellations_change_abs": cancellations_week - cancellations_prev_week,
    }

    score, comment = _derive_score_and_comment(monthly)
    skill_plus_rows = _load_skill_plus_rows()
    trend_weeks = _build_trend_weeks(periods, _aggregate_skill_plus_by_date(skill_plus_rows))

    news_lines = [
        f"月次の集客数は {_format_people(monthly['lead_actual'])} / 目標進捗 {_format_pct(monthly['lead_progress'])}",
        f"直近7日間の ROAS は前週比 {_format_signed_point(weekly['roas_change_pt'])} です",
        f"直近7日間の CPA は前週比 {_format_signed_pct(weekly['cpa_change_pct'])} です",
    ]

    dataset = {
        "generated_at": datetime.now(TIMEZONE).isoformat(timespec="seconds"),
        "doc_url": f"https://docs.google.com/document/d/{REPORT_DOC_ID}/edit",
        "periods": {
            "meeting_date": periods.meeting_date.isoformat(),
            "month_start": periods.month_start.isoformat(),
            "month_end": periods.month_end.isoformat(),
            "week_start": periods.week_start.isoformat(),
            "week_end": periods.week_end.isoformat(),
            "prev_week_start": periods.prev_week_start.isoformat(),
            "prev_week_end": periods.prev_week_end.isoformat(),
            "days_in_month": periods.days_in_month,
            "elapsed_days": periods.elapsed_days,
        },
        "score": score,
        "comment": comment,
        "news_lines": news_lines,
        "monthly": monthly,
        "weekly": weekly,
        "trend_weeks": trend_weeks,
    }
    return dataset


def _meeting_sheet_rows(dataset: dict[str, Any], sheet_url: str) -> list[list[Any]]:
    periods = dataset["periods"]
    monthly = dataset["monthly"]
    weekly = dataset["weekly"]
    trend_weeks = dataset["trend_weeks"]

    rows: list[list[Any]] = [
        ["経営会議KPI"],
        ["generated_at", dataset["generated_at"]],
        ["meeting_date", periods["meeting_date"]],
        ["doc_url", dataset["doc_url"]],
        ["sheet_url", sheet_url],
        [],
        ["periods"],
        ["period_key", "start_date", "end_date", "note"],
        ["monthly", periods["month_start"], periods["month_end"], "当月1日から会議2日前の水曜まで"],
        ["weekly", periods["week_start"], periods["week_end"], "会議基準の直近7日間"],
        ["previous_week", periods["prev_week_start"], periods["prev_week_end"], "比較用の前週7日間"],
        [],
        ["summary"],
        ["summary_key", "value"],
        ["score", dataset["score"]],
        ["comment", dataset["comment"]],
        [],
        ["monthly_kpi"],
        ["metric_key", "label", "unit", "target", "actual", "progress_pct", "forecast", "note"],
    ]

    monthly_rows = {
        "cash_revenue": _metric_row("着金売上", "JPY", monthly["revenue_target"], monthly["revenue_actual"], monthly["revenue_progress"], monthly["forecast_revenue"], "日報トップ要約行を会議基準で再集計"),
        "leads": _metric_row("集客数", "count", monthly["lead_target"], monthly["lead_actual"], monthly["lead_progress"], monthly["forecast_leads"], "日報トップ要約行を会議基準で再集計"),
        "bookings": _metric_row("個別予約数", "count", monthly["booking_target"], monthly["booking_actual"], monthly["booking_progress"], None, "日報トップ要約行を会議基準で再集計"),
        "ad_spend": _metric_row("広告費", "JPY", monthly["ad_spend_budget"], monthly["ad_spend_actual"], monthly["ad_spend_progress"], None, "日報トップ要約行を会議基準で再集計"),
        "roas": _metric_row("ROAS", "pct", ROAS_TARGET, monthly["roas"], _safe_div(monthly["roas"], ROAS_TARGET), None, "着金売上 ÷ 広告費 × 100"),
        "cpa": _metric_row("CPA", "JPY", CPA_TARGET, monthly["cpa"], _safe_div(CPA_TARGET, monthly["cpa"]) if monthly["cpa"] else 0, None, "広告費 ÷ 集客数"),
        "cpo": _metric_row("個別CPO", "JPY", 0, monthly["cpo"], 0, None, "広告費 ÷ 個別予約数"),
        "member_net": _metric_row("会員純増", "count", 0, monthly["member_net_actual"], 0, None, "日報トップ要約行のスキルプラス会員数を使用"),
        "cancellations": _metric_row("解約数", "count", 0, monthly["cancellations_actual"], 0, None, "日報トップ要約行を会議基準で再集計"),
        "new_subscribers": _metric_row("サブスク新規会員数", "count", 0, monthly["new_subscribers_actual"], 0, None, "日報トップ要約行を会議基準で再集計"),
    }
    for metric_key, values in monthly_rows.items():
        rows.append([metric_key, *values])

    rows.extend(
        [
            [],
            ["weekly_kpi"],
            ["metric_key", "label", "unit", "current", "previous", "delta_abs", "delta_pct", "note"],
            ["leads", "集客数", "count", weekly["lead_current"], weekly["lead_previous"], weekly["lead_change_abs"], weekly["lead_change_pct"], "木曜-水曜で比較"],
            ["bookings", "個別予約数", "count", weekly["booking_current"], weekly["booking_previous"], weekly["booking_change_abs"], weekly["booking_change_pct"], "木曜-水曜で比較"],
            ["cash_revenue", "着金売上", "JPY", weekly["revenue_current"], weekly["revenue_previous"], weekly["revenue_change_abs"], weekly["revenue_change_pct"], "木曜-水曜で比較"],
            ["ad_spend", "広告費", "JPY", weekly["ad_spend_current"], weekly["ad_spend_previous"], weekly["ad_spend_change_abs"], weekly["ad_spend_change_pct"], "木曜-水曜で比較"],
            ["roas", "ROAS", "pct", weekly["roas_current"], weekly["roas_previous"], weekly["roas_change_pt"], "", "差分は point"],
            ["cpa", "CPA", "JPY", weekly["cpa_current"], weekly["cpa_previous"], weekly["cpa_change_abs"], weekly["cpa_change_pct"], "広告費 ÷ 集客数"],
            ["cpo", "個別CPO", "JPY", weekly["cpo_current"], weekly["cpo_previous"], weekly["cpo_change_abs"], weekly["cpo_change_pct"], "広告費 ÷ 個別予約数"],
            ["member_net", "会員純増", "count", weekly["member_net_current"], weekly["member_net_previous"], weekly["member_net_change_abs"], "", "日報トップ要約行のスキルプラス会員数を使用"],
            ["cancellations", "解約数", "count", weekly["cancellations_current"], weekly["cancellations_previous"], weekly["cancellations_change_abs"], "", "日報トップ要約行を会議基準で再集計"],
            [],
            ["trend_12weeks"],
            ["week_start", "week_end", "leads", "bookings", "revenue", "ad_spend", "cpa", "roas"],
        ]
    )

    for week in trend_weeks:
        rows.append(
            [
                week["week_start"],
                week["week_end"],
                week["leads"],
                week["bookings"],
                week["revenue"],
                week["ad_spend"],
                week["cpa"],
                week["roas"],
            ]
        )

    return rows


def update_meeting_master_sheet(dataset: dict[str, Any]) -> str:
    client = get_client()
    spreadsheet = client.open_by_key(REPORT_SHEET_ID)
    try:
        ws = spreadsheet.worksheet(MEETING_MASTER_TAB)
    except Exception:
        ws = spreadsheet.add_worksheet(title=MEETING_MASTER_TAB, rows=200, cols=12)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{REPORT_SHEET_ID}/edit?gid={ws.id}"
    values = _meeting_sheet_rows(dataset, sheet_url)

    ws.clear()
    ws.update(values=values, range_name=f"A1:H{len(values)}")
    try:
        ws.freeze(rows=1)
        ws.format("A1:H1", {"textFormat": {"bold": True, "fontSize": 14}})
        for header_row in ("A8:D10", "A18:H19", "A32:H33", "A45:H46"):
            ws.format(header_row, {"textFormat": {"bold": True}})
    except Exception:
        pass
    return sheet_url


def _resolve_font_path() -> str:
    candidates = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("日本語フォントが見つかりません")


def _font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size=size)


def _draw_cards(title: str, subtitle: str, cards: list[dict[str, str]], output_path: Path) -> None:
    font_path = _resolve_font_path()
    canvas = Image.new("RGB", (1280, 760), "#F7F6F4")
    draw = ImageDraw.Draw(canvas)
    draw.text((56, 38), title, fill="#1F2937", font=_font(font_path, 34))
    draw.text((56, 92), subtitle, fill="#6B7280", font=_font(font_path, 16))

    margin_x = 56
    margin_y = 146
    gap_x = 42
    gap_y = 28
    card_w = 362
    card_h = 166

    for idx, card in enumerate(cards):
        row = idx // 3
        col = idx % 3
        x = margin_x + col * (card_w + gap_x)
        y = margin_y + row * (card_h + gap_y)
        draw.rounded_rectangle((x, y, x + card_w, y + card_h), radius=18, fill=CARD_COLORS[idx], outline="#D7D4CF")
        draw.text((x + 18, y + 18), card["label"], fill="#374151", font=_font(font_path, 15))
        draw.text((x + 18, y + 58), card["value"], fill="#1F2937", font=_font(font_path, 24))
        draw.text((x + 18, y + 118), card["sub"], fill="#6B7280", font=_font(font_path, 14))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path)


def create_monthly_image(dataset: dict[str, Any], output_path: Path) -> Path:
    periods = dataset["periods"]
    monthly = dataset["monthly"]
    cards = [
        {
            "label": "集客数",
            "value": _format_people(monthly["lead_actual"]),
            "sub": f"目標 {_format_people(monthly['lead_target'])} / 進捗 {_format_pct(monthly['lead_progress'])}",
        },
        {
            "label": "個別予約数",
            "value": f"{_format_int(monthly['booking_actual'])}件",
            "sub": f"目標 {_format_int(monthly['booking_target'])}件 / 進捗 {_format_pct(monthly['booking_progress'])}",
        },
        {
            "label": "着金売上",
            "value": _format_compact_yen(monthly["revenue_actual"]),
            "sub": f"目標 {_format_budget_yen(monthly['revenue_target'])} / 進捗 {_format_pct(monthly['revenue_progress'])}",
        },
        {
            "label": "ROAS",
            "value": f"{monthly['roas']:.0f}%",
            "sub": f"目安 {ROAS_TARGET:.0f}%",
        },
        {
            "label": "広告費",
            "value": _format_compact_yen(monthly["ad_spend_actual"]),
            "sub": f"予算 {_format_budget_yen(monthly['ad_spend_budget'])} / 進捗 {_format_pct(monthly['ad_spend_progress'])}",
        },
        {
            "label": "CPA",
            "value": _format_yen(monthly["cpa"]),
            "sub": f"目安 {_format_yen(CPA_TARGET)}",
        },
        {
            "label": "個別CPO",
            "value": _format_yen(monthly["cpo"]),
            "sub": "広告費 / 個別予約数",
        },
        {
            "label": "会員純増",
            "value": _format_signed_int(monthly["member_net_actual"]),
            "sub": f"解約 {_format_int(monthly['cancellations_actual'])} / サブスク新規 {_format_int(monthly['new_subscribers_actual'])}",
        },
        {
            "label": "着地予想",
            "value": f"{_format_compact_yen(monthly['forecast_revenue'])} / {_format_people(monthly['forecast_leads'])}",
            "sub": "着金売上 / 集客数",
        },
    ]
    _draw_cards(
        title=f"{date.fromisoformat(periods['meeting_date']).month}月 KPI ({_period_text(date.fromisoformat(periods['month_start']), date.fromisoformat(periods['month_end']))})",
        subtitle="会議基準の水曜締めで集計",
        cards=cards,
        output_path=output_path,
    )
    return output_path


def create_weekly_image(dataset: dict[str, Any], output_path: Path) -> Path:
    periods = dataset["periods"]
    weekly = dataset["weekly"]
    cards = [
        {
            "label": "集客数",
            "value": _format_people(weekly["lead_current"]),
            "sub": f"前週比 {_format_signed_pct(weekly['lead_change_pct'])}",
        },
        {
            "label": "個別予約数",
            "value": f"{_format_int(weekly['booking_current'])}件",
            "sub": f"前週比 {_format_signed_pct(weekly['booking_change_pct'])}",
        },
        {
            "label": "着金売上",
            "value": _format_compact_yen(weekly["revenue_current"]),
            "sub": f"前週比 {_format_signed_pct(weekly['revenue_change_pct'])}",
        },
        {
            "label": "ROAS",
            "value": f"{weekly['roas_current']:.0f}%",
            "sub": f"前週 {weekly['roas_previous']:.0f}% / {_format_signed_point(weekly['roas_change_pt'])}",
        },
        {
            "label": "広告費",
            "value": _format_compact_yen(weekly["ad_spend_current"]),
            "sub": f"前週比 {_format_signed_pct(weekly['ad_spend_change_pct'])}",
        },
        {
            "label": "CPA",
            "value": _format_yen(weekly["cpa_current"]),
            "sub": f"前週 {_format_yen(weekly['cpa_previous'])} / {_format_signed_pct(weekly['cpa_change_pct'])}",
        },
        {
            "label": "個別CPO",
            "value": _format_yen(weekly["cpo_current"]),
            "sub": f"前週 {_format_yen(weekly['cpo_previous'])} / {_format_signed_pct(weekly['cpo_change_pct'])}",
        },
        {
            "label": "会員純増",
            "value": _format_signed_int(weekly["member_net_current"]),
            "sub": f"前週 {_format_signed_int(weekly['member_net_previous'])}",
        },
        {
            "label": "解約数",
            "value": _format_int(weekly["cancellations_current"]),
            "sub": f"前週 {_format_int(weekly['cancellations_previous'])}",
        },
    ]
    _draw_cards(
        title=f"過去7日間 KPI ({_period_text(date.fromisoformat(periods['week_start']), date.fromisoformat(periods['week_end']))})",
        subtitle=f"前週 {_period_text(date.fromisoformat(periods['prev_week_start']), date.fromisoformat(periods['prev_week_end']))} との比較",
        cards=cards,
        output_path=output_path,
    )
    return output_path


def create_trend_image(dataset: dict[str, Any], output_path: Path) -> Path:
    font_path = _resolve_font_path()
    plt.rcParams["font.family"] = ["Hiragino Sans", "Arial Unicode MS", "sans-serif"]
    weeks = dataset["trend_weeks"]
    labels = [week["week_end"][5:] for week in weeks]
    leads = [week["leads"] for week in weeks]
    bookings = [week["bookings"] for week in weeks]
    ad_spend = [week["ad_spend"] / 10_000 for week in weeks]
    cpa = [week["cpa"] for week in weeks]

    fig, axes = plt.subplots(2, 2, figsize=(14, 8), facecolor="#F7F6F4")
    fig.suptitle("過去12週間 KPI 推移", fontsize=24, y=0.98)
    fig.text(0.125, 0.935, "会議基準の水曜締めで集計", fontsize=12, color="#6B7280")

    series = [
        ("集客数", leads, "#93A8E6", axes[0, 0], "人"),
        ("個別予約数", bookings, "#A7C8E8", axes[0, 1], "件"),
        ("広告費", ad_spend, "#D7C886", axes[1, 0], "万円"),
        ("CPA", cpa, "#C9A27E", axes[1, 1], "円"),
    ]

    for title, values, color, ax, unit in series:
        ax.set_facecolor("#FFFFFF")
        ax.plot(labels, values, color=color, linewidth=3, marker="o")
        ax.fill_between(labels, values, color=color, alpha=0.12)
        ax.set_title(title, fontsize=16, loc="left")
        ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
        ax.tick_params(axis="x", rotation=45, labelsize=10)
        ax.tick_params(axis="y", labelsize=10)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#D1D5DB")
        ax.spines["bottom"].set_color("#D1D5DB")
        ax.set_ylabel(unit, fontsize=10, color="#6B7280")

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=160, facecolor=fig.get_facecolor(), bbox_inches="tight")
    plt.close(fig)
    return output_path


def _load_render_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def upload_image(image_path: Path) -> str:
    config = _load_render_config()
    url = f"{config['server_url']}/api/upload_image"
    with image_path.open("rb") as handle:
        response = requests.post(
            url,
            files={"file": (image_path.name, handle, "image/png")},
            headers={"Authorization": f"Bearer {config['agent_token']}"},
            timeout=30,
        )
    response.raise_for_status()
    payload = response.json()
    image_url = payload.get("image_url", "")
    if not image_url:
        raise ValueError(f"画像URLを取得できませんでした: {payload}")
    return image_url


def _find_text_range(content: list[dict[str, Any]], target: str) -> tuple[int, int] | None:
    for block in content:
        paragraph = block.get("paragraph")
        if not paragraph:
            continue
        for element in paragraph.get("elements", []):
            text_run = element.get("textRun")
            if not text_run:
                continue
            content_text = text_run.get("content", "")
            if target in content_text:
                start = element["startIndex"] + content_text.index(target)
                end = start + len(target)
                return start, end
    return None


def _doc_text(dataset: dict[str, Any], sheet_url: str) -> str:
    periods = dataset["periods"]
    monthly = dataset["monthly"]
    weekly = dataset["weekly"]

    meeting_date = date.fromisoformat(periods["meeting_date"])
    month_start = date.fromisoformat(periods["month_start"])
    month_end = date.fromisoformat(periods["month_end"])
    week_start = date.fromisoformat(periods["week_start"])
    week_end = date.fromisoformat(periods["week_end"])
    prev_week_start = date.fromisoformat(periods["prev_week_start"])
    prev_week_end = date.fromisoformat(periods["prev_week_end"])

    news_lines = "\n".join(f"・{line}" for line in dataset["news_lines"])
    return (
        f"{meeting_date.strftime('%Y/%m/%d')}　アドネス経営会議\n"
        "\n"
        "【総評】\n"
        f"{month_end.month}/{month_end.day}\n"
        f"{dataset['score']}/5\n"
        f"└{dataset['comment']}\n"
        "\n"
        "＜NEWS！＞\n"
        f"{news_lines}\n"
        "\n"
        f"【{meeting_date.month}月目標と現状】\n"
        f"{meeting_date.month}月の目標\n"
        f"・着金売上: {_format_budget_yen(monthly['revenue_target'])}\n"
        f"・集客数: {_format_people(monthly['lead_target'])}\n"
        f"・正本シート: {sheet_url}\n"
        f"{meeting_date.month}月の進捗状況 ({month_start.month}/{month_start.day}〜{month_end.month}/{month_end.day})\n"
        f"・着金売上 {_format_compact_yen(monthly['revenue_actual'])} / 目標進捗 {_format_pct(monthly['revenue_progress'])}\n"
        f"・集客数 {_format_people(monthly['lead_actual'])} / 目標進捗 {_format_pct(monthly['lead_progress'])}\n"
        f"・ROAS {monthly['roas']:.0f}% / CPA {_format_yen(monthly['cpa'])}\n"
        "[[MONTHLY_IMAGE]]\n"
        "\n"
        "【過去7日間KPI】\n"
        f"期間 ({week_start.month}/{week_start.day}〜{week_end.month}/{week_end.day}) / 比較 ({prev_week_start.month}/{prev_week_start.day}〜{prev_week_end.month}/{prev_week_end.day})\n"
        f"・集客数 {_format_signed_pct(weekly['lead_change_pct'])} / 着金売上 {_format_signed_pct(weekly['revenue_change_pct'])}\n"
        f"・ROAS {_format_signed_point(weekly['roas_change_pt'])} / CPA {_format_signed_pct(weekly['cpa_change_pct'])}\n"
        "[[WEEKLY_IMAGE]]\n"
        "\n"
        "【過去12週間推移】\n"
        "会議基準の水曜締めで集計\n"
        "[[TREND_IMAGE]]\n"
        "\n"
        "【その他・共有事項】\n"
        "・会議資料の正本は Google Sheets の「経営会議KPI」です\n"
        "・Looker Studio は確認用に残し、資料生成では使いません\n"
    )


def update_google_doc(dataset: dict[str, Any], sheet_url: str, image_urls: dict[str, str]) -> str:
    service = get_google_service(service_type="docs")
    delete_current_section()

    body_text = _doc_text(dataset, sheet_url)
    requests = [{"insertText": {"location": {"index": 1}, "text": body_text}}]
    end_index = 1 + len(body_text)
    requests.append(
        {
            "insertSectionBreak": {
                "location": {"index": end_index - 1},
                "sectionType": "NEXT_PAGE",
            }
        }
    )
    service.documents().batchUpdate(documentId=REPORT_DOC_ID, body={"requests": requests}).execute()

    doc = service.documents().get(documentId=REPORT_DOC_ID).execute()
    content = doc["body"]["content"]

    style_requests: list[dict[str, Any]] = []
    title = f"{date.fromisoformat(dataset['periods']['meeting_date']).strftime('%Y/%m/%d')}　アドネス経営会議"
    title_range = _find_text_range(content, title)
    if title_range:
        start, end = title_range
        style_requests.extend(
            [
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {
                            "bold": True,
                            "underline": True,
                            "fontSize": {"magnitude": 20, "unit": "PT"},
                        },
                        "fields": "bold,underline,fontSize",
                    }
                },
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": start, "endIndex": end + 1},
                        "paragraphStyle": {"alignment": "CENTER"},
                        "fields": "alignment",
                    }
                },
            ]
        )

    for header in ["【総評】", "＜NEWS！＞", "【過去7日間KPI】", "【過去12週間推移】", "【その他・共有事項】"]:
        found = _find_text_range(content, header)
        if found:
            start, end = found
            style_requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": start, "endIndex": end},
                        "textStyle": {
                            "bold": True,
                            "fontSize": {"magnitude": 14, "unit": "PT"},
                        },
                        "fields": "bold,fontSize",
                    }
                }
            )

    month_header = f"【{date.fromisoformat(dataset['periods']['meeting_date']).month}月目標と現状】"
    found = _find_text_range(content, month_header)
    if found:
        start, end = found
        style_requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "bold": True,
                        "fontSize": {"magnitude": 14, "unit": "PT"},
                    },
                    "fields": "bold,fontSize",
                }
            }
        )

    score_range = _find_text_range(content, f"{dataset['score']}/5")
    if score_range:
        start, end = score_range
        style_requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "bold": True,
                        "fontSize": {"magnitude": 13, "unit": "PT"},
                    },
                    "fields": "bold,fontSize",
                }
            }
        )

    if style_requests:
        service.documents().batchUpdate(documentId=REPORT_DOC_ID, body={"requests": style_requests}).execute()

    doc = service.documents().get(documentId=REPORT_DOC_ID).execute()
    content = doc["body"]["content"]
    image_map = {
        "[[MONTHLY_IMAGE]]": image_urls["monthly"],
        "[[WEEKLY_IMAGE]]": image_urls["weekly"],
        "[[TREND_IMAGE]]": image_urls["trend"],
    }
    replace_requests: list[dict[str, Any]] = []
    for placeholder, image_url in image_map.items():
        found = _find_text_range(content, placeholder)
        if not found:
            continue
        start, end = found
        replace_requests.extend(
            [
                {"deleteContentRange": {"range": {"startIndex": start, "endIndex": end}}},
                {
                    "insertInlineImage": {
                        "location": {"index": start},
                        "uri": image_url,
                        "objectSize": {
                            "width": {"magnitude": 500, "unit": "PT"},
                            "height": {"magnitude": 320, "unit": "PT"},
                        },
                    }
                },
            ]
        )

    if replace_requests:
        replace_requests.sort(
            key=lambda req: req.get("deleteContentRange", {}).get("range", {}).get("startIndex", req.get("insertInlineImage", {}).get("location", {}).get("index", 0)),
            reverse=True,
        )
        service.documents().batchUpdate(documentId=REPORT_DOC_ID, body={"requests": replace_requests}).execute()

    return dataset["doc_url"]


def build_meeting_report(meeting_date: date | None = None, update_doc: bool = True, update_sheet: bool = True) -> dict[str, Any]:
    dataset = build_meeting_dataset(meeting_date)

    sheet_url = ""
    if update_sheet:
        sheet_url = update_meeting_master_sheet(dataset)
    dataset["sheet_url"] = sheet_url

    period = dataset["periods"]["meeting_date"].replace("-", "")
    output_dir = OUTPUT_ROOT / period
    monthly_path = create_monthly_image(dataset, output_dir / "meeting_monthly_kpi.png")
    weekly_path = create_weekly_image(dataset, output_dir / "meeting_weekly_kpi.png")
    trend_path = create_trend_image(dataset, output_dir / "meeting_12week.png")

    image_urls = {
        "monthly": upload_image(monthly_path),
        "weekly": upload_image(weekly_path),
        "trend": upload_image(trend_path),
    }
    dataset["image_urls"] = image_urls

    if update_doc:
        update_google_doc(dataset, sheet_url, image_urls)

    return dataset


def main() -> None:
    parser = argparse.ArgumentParser(description="経営会議資料を Sheets 正本で生成する")
    parser.add_argument("--date", help="会議日 (YYYY-MM-DD)")
    parser.add_argument("--skip-doc", action="store_true", help="Google Docs 更新をスキップ")
    parser.add_argument("--skip-sheet", action="store_true", help="正本シート更新をスキップ")
    args = parser.parse_args()

    meeting_date = date.fromisoformat(args.date) if args.date else None
    result = build_meeting_report(
        meeting_date=meeting_date,
        update_doc=not args.skip_doc,
        update_sheet=not args.skip_sheet,
    )
    print(
        json.dumps(
            {
                "doc_url": result["doc_url"],
                "sheet_url": result.get("sheet_url", ""),
                "score": result["score"],
                "comment": result["comment"],
                "image_urls": result["image_urls"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
