#!/usr/bin/env python3
"""
KPI Anomaly Detector - KPIデータの異常検知と根本原因分析

kpi_summary.json を読み取り、日別・月別の異常を検知する。
異常が見つかった場合、媒体へドリルダウンして根本原因の仮説を生成。

使い方:
  python3 kpi_anomaly_detector.py              # 検知実行（異常時のみ出力）
  python3 kpi_anomaly_detector.py --verbose    # 全指標の状態を出力
  python3 kpi_anomaly_detector.py --json       # JSON形式で出力
"""

from __future__ import annotations

import calendar
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

SCRIPT_DIR = Path(__file__).parent
KPI_CACHE = SCRIPT_DIR / "data" / "kpi_summary.json"

# 監視メトリクス: (名前, 方向, 注目閾値, 警告閾値)
# higher_is_bad: 上がると悪い（CPA, 広告費）
# lower_is_bad: 下がると悪い（ROAS, 集客数, 売上, 予約数）
DAILY_METRICS = [
    {"name": "集客数", "direction": "lower_is_bad", "caution": 0.20, "warning": 0.35},
    {"name": "売上", "direction": "lower_is_bad", "caution": 0.20, "warning": 0.35},
    {"name": "広告費", "direction": "higher_is_bad", "caution": 0.25, "warning": 0.40},
    {"name": "ROAS", "direction": "lower_is_bad", "caution": 0.15, "warning": 0.30},
    {"name": "個別予約数", "direction": "lower_is_bad", "caution": 0.20, "warning": 0.35},
]

# 月別は比率メトリクスのみ（絶対値は月途中だと比較が不正確）
MONTHLY_METRICS = [
    {"name": "CPA", "direction": "higher_is_bad", "caution": 0.15, "warning": 0.30},
    {"name": "ROAS", "direction": "lower_is_bad", "caution": 0.15, "warning": 0.30},
    {"name": "CPO", "direction": "higher_is_bad", "caution": 0.15, "warning": 0.30},
    {"name": "LTV", "direction": "lower_is_bad", "caution": 0.15, "warning": 0.30},
]


def load_kpi_data() -> dict:
    if not KPI_CACHE.exists():
        return {}
    return json.loads(KPI_CACHE.read_text(encoding="utf-8"))


def _pct_change(current: float, baseline: float) -> float:
    if baseline == 0:
        return 0.0
    return (current - baseline) / baseline


def _avg(values: list) -> float:
    return sum(values) / len(values) if values else 0.0


def _check_staleness(data: dict) -> str | None:
    """データの鮮度チェック。48時間以上古ければ警告"""
    updated_at = data.get("updated_at", "")
    if not updated_at:
        return "KPIデータの更新日時が不明"
    try:
        updated = datetime.fromisoformat(updated_at)
        age_hours = (datetime.now() - updated).total_seconds() / 3600
        if age_hours > 48:
            return f"KPIデータが{age_hours:.0f}時間前の古いデータです"
    except (ValueError, TypeError):
        pass
    return None


def analyze_daily(data: dict) -> list[dict]:
    """直近3日 vs 前7日の平均を比較"""
    recent_daily = data.get("recent_daily", [])
    if len(recent_daily) < 5:
        return []

    recent_3 = recent_daily[:3]
    prior_7 = recent_daily[3:10]

    if len(prior_7) < 3:
        return []

    findings = []
    for metric in DAILY_METRICS:
        name = metric["name"]
        recent_vals = [d.get(name, 0) for d in recent_3 if d.get(name) is not None]
        prior_vals = [d.get(name, 0) for d in prior_7 if d.get(name) is not None]

        # 0値が多すぎるデータは比較しない
        recent_nonzero = [v for v in recent_vals if v != 0]
        prior_nonzero = [v for v in prior_vals if v != 0]

        if len(recent_nonzero) < 2 or len(prior_nonzero) < 2:
            continue

        recent_avg = _avg(recent_nonzero)
        prior_avg = _avg(prior_nonzero)
        change = _pct_change(recent_avg, prior_avg)

        is_bad = (metric["direction"] == "higher_is_bad" and change > 0) or \
                 (metric["direction"] == "lower_is_bad" and change < 0)

        abs_change = abs(change)
        if abs_change >= metric["warning"] and is_bad:
            severity = "警告"
        elif abs_change >= metric["caution"] and is_bad:
            severity = "注目"
        else:
            continue

        findings.append({
            "type": "daily",
            "metric": name,
            "severity": severity,
            "change_pct": round(change * 100, 1),
            "recent_avg": round(recent_avg),
            "prior_avg": round(prior_avg),
            "recent_period": f"{recent_3[-1]['date']}〜{recent_3[0]['date']}",
            "prior_period": f"{prior_7[-1]['date']}〜{prior_7[0]['date']}",
        })

    return findings


def analyze_monthly(data: dict) -> list[dict]:
    """最新月の比率メトリクス vs 前3ヶ月平均を比較"""
    monthly = data.get("monthly", [])
    if len(monthly) < 4:
        return []

    current = monthly[-1]
    prior_3 = monthly[-4:-1]

    findings = []
    for metric in MONTHLY_METRICS:
        name = metric["name"]
        current_val = current.get(name, 0)
        prior_vals = [m.get(name, 0) for m in prior_3 if m.get(name, 0) != 0]

        if current_val == 0 or not prior_vals:
            continue

        prior_avg = _avg(prior_vals)
        change = _pct_change(current_val, prior_avg)

        is_bad = (metric["direction"] == "higher_is_bad" and change > 0) or \
                 (metric["direction"] == "lower_is_bad" and change < 0)

        abs_change = abs(change)
        if abs_change >= metric["warning"] and is_bad:
            severity = "警告"
        elif abs_change >= metric["caution"] and is_bad:
            severity = "注目"
        else:
            continue

        findings.append({
            "type": "monthly",
            "metric": name,
            "severity": severity,
            "change_pct": round(change * 100, 1),
            "current_month": current["month"],
            "current_val": current_val,
            "prior_avg": round(prior_avg),
            "prior_months": [m["month"] for m in prior_3],
        })

    return findings


def analyze_monthly_absolute(data: dict) -> list[dict]:
    """月別の絶対値メトリクスを日割りプロレートで比較"""
    monthly = data.get("monthly", [])
    recent_daily = data.get("recent_daily", [])
    if len(monthly) < 4 or not recent_daily:
        return []

    current = monthly[-1]
    prior_3 = monthly[-4:-1]
    current_month_str = current["month"]

    # 最新日付から経過日数を算出
    latest_date = recent_daily[0].get("date", "")
    if not latest_date.startswith(current_month_str):
        return []  # 最新月のデータがない

    year, month_num = int(current_month_str[:4]), int(current_month_str[5:7])
    days_in_month = calendar.monthrange(year, month_num)[1]
    days_elapsed = int(latest_date[8:10])

    if days_elapsed < 7:
        return []  # 月初7日未満はプロレート不正確

    prorate = days_in_month / days_elapsed

    abs_metrics = [
        {"name": "集客数", "direction": "lower_is_bad", "caution": 0.20, "warning": 0.35},
        {"name": "売上", "direction": "lower_is_bad", "caution": 0.20, "warning": 0.35},
    ]

    findings = []
    for metric in abs_metrics:
        name = metric["name"]
        current_val = current.get(name, 0)
        projected = round(current_val * prorate)
        prior_vals = [m.get(name, 0) for m in prior_3 if m.get(name, 0) != 0]

        if projected == 0 or not prior_vals:
            continue

        prior_avg = _avg(prior_vals)
        change = _pct_change(projected, prior_avg)

        is_bad = (metric["direction"] == "higher_is_bad" and change > 0) or \
                 (metric["direction"] == "lower_is_bad" and change < 0)

        abs_change = abs(change)
        if abs_change >= metric["warning"] and is_bad:
            severity = "警告"
        elif abs_change >= metric["caution"] and is_bad:
            severity = "注目"
        else:
            continue

        findings.append({
            "type": "monthly_projected",
            "metric": name,
            "severity": severity,
            "change_pct": round(change * 100, 1),
            "current_month": current_month_str,
            "current_val": current_val,
            "projected_val": projected,
            "prior_avg": round(prior_avg),
            "days_elapsed": days_elapsed,
            "days_in_month": days_in_month,
        })

    return findings


def drill_down_media(data: dict, findings: list[dict]) -> list[dict]:
    """異常の原因を媒体別にドリルダウン"""
    enriched = []

    for finding in findings:
        finding = dict(finding)

        if finding["type"] == "daily":
            rdbm = data.get("recent_daily_by_media", {})
            recent_daily = data.get("recent_daily", [])
            metric = finding["metric"]

            # daily_by_media は 集客数, 売上, 広告費 のみ
            if metric not in ("集客数", "売上", "広告費") or not rdbm:
                enriched.append(finding)
                continue

            recent_dates = [d["date"] for d in recent_daily[:3]]
            prior_dates = [d["date"] for d in recent_daily[3:10]]

            all_media = set()
            for dt in recent_dates + prior_dates:
                if dt in rdbm:
                    all_media.update(rdbm[dt].keys())

            media_changes = []
            for media in all_media:
                r_vals = [rdbm.get(dt, {}).get(media, {}).get(metric, 0) for dt in recent_dates]
                p_vals = [rdbm.get(dt, {}).get(media, {}).get(metric, 0) for dt in prior_dates]
                r_nz = [v for v in r_vals if v != 0]
                p_nz = [v for v in p_vals if v != 0]

                r_avg = _avg(r_nz) if r_nz else 0
                p_avg = _avg(p_nz) if p_nz else 0

                if p_avg > 0:
                    change = _pct_change(r_avg, p_avg)
                    media_changes.append({
                        "media": media,
                        "change_pct": round(change * 100, 1),
                        "abs_impact": round(r_avg - p_avg),
                        "recent_avg": round(r_avg),
                        "prior_avg": round(p_avg),
                    })

            media_changes.sort(key=lambda x: abs(x["abs_impact"]), reverse=True)
            finding["media_breakdown"] = media_changes[:5]

        elif finding["type"] in ("monthly", "monthly_projected"):
            mbm = data.get("monthly_by_media", {})
            current_month = finding["current_month"]
            monthly = data.get("monthly", [])
            metric = finding["metric"]

            if current_month not in mbm:
                enriched.append(finding)
                continue

            # 前3ヶ月の媒体データ
            prior_months = [m["month"] for m in monthly[-4:-1]]
            current_media = mbm[current_month]

            all_media = set(current_media.keys())
            for pm in prior_months:
                if pm in mbm:
                    all_media.update(mbm[pm].keys())

            media_changes = []
            for media in all_media:
                c_val = current_media.get(media, {}).get(metric, 0)
                p_vals = [mbm.get(pm, {}).get(media, {}).get(metric, 0) for pm in prior_months]
                p_vals = [v for v in p_vals if v != 0]
                p_avg = _avg(p_vals) if p_vals else 0

                if p_avg > 0 and c_val > 0:
                    change = _pct_change(c_val, p_avg)
                    media_changes.append({
                        "media": media,
                        "change_pct": round(change * 100, 1),
                        "abs_impact": round(c_val - p_avg),
                        "current_val": round(c_val),
                        "prior_avg": round(p_avg),
                    })

            media_changes.sort(key=lambda x: abs(x["abs_impact"]), reverse=True)
            finding["media_breakdown"] = media_changes[:5]

        enriched.append(finding)

    return enriched


def generate_hypotheses(findings: list[dict]) -> list[dict]:
    """異常パターンから原因仮説を生成"""
    for finding in findings:
        hypotheses = []
        metric = finding["metric"]
        media_breakdown = finding.get("media_breakdown", [])

        # 媒体集中度チェック
        if media_breakdown:
            top = media_breakdown[0]
            total_impact = sum(abs(m["abs_impact"]) for m in media_breakdown)
            top_share = abs(top["abs_impact"]) / total_impact * 100 if total_impact > 0 else 0

            if top_share > 60:
                hypotheses.append(
                    f"{top['media']}に変動が集中（影響度{top_share:.0f}%）"
                    f"→ {top['media']}の運用変更を確認"
                )
            elif len(media_breakdown) >= 3:
                hypotheses.append("複数媒体で同時変動 → 市場全体の変化（季節要因・競合）の可能性")

        # メトリクス固有
        if metric == "CPA" and finding["change_pct"] > 0:
            hypotheses.append("CPA上昇 → CR疲弊・配信面ズレ・競合CPM高騰のいずれか確認")
        elif metric == "ROAS" and finding["change_pct"] < 0:
            hypotheses.append("ROAS低下 → CPA上昇 or 成約率低下 or LTV低下を切り分け")
        elif metric == "集客数" and finding["change_pct"] < 0:
            hypotheses.append("集客数減少 → 広告予算縮小・配信制限・CR停止の可能性")
        elif metric == "売上" and finding["change_pct"] < 0:
            hypotheses.append("売上減少 → 集客数減 or 成約率低下 or 単価変動を確認")
        elif metric == "広告費" and finding["change_pct"] > 0:
            hypotheses.append("広告費増加 → 意図的拡大か確認（予算設定ミスの可能性）")
        elif metric == "CPO" and finding["change_pct"] > 0:
            hypotheses.append("CPO上昇 → 予約率低下 or CPA上昇を切り分け")
        elif metric == "LTV" and finding["change_pct"] < 0:
            hypotheses.append("LTV低下 → 成約単価の変化 or 商品ミックスの変化を確認")

        finding["hypotheses"] = hypotheses

    return findings


def format_line_report(findings: list[dict], data: dict) -> str:
    """LINE通知用フォーマット（990文字制限を意識）"""
    if not findings:
        return ""

    severity_order = {"警告": 0, "注目": 1}
    findings.sort(key=lambda f: (severity_order.get(f["severity"], 9), -abs(f["change_pct"])))

    lines = ["\n📊 KPI異常検知レポート", "━━━━━━━━━━━━"]

    for f in findings:
        icon = "🔴" if f["severity"] == "警告" else "🟡"
        arrow = "↑" if f["change_pct"] > 0 else "↓"

        if f["type"] == "daily":
            lines.append(f"{icon} {f['metric']} {arrow}{abs(f['change_pct'])}%（日別）")
            lines.append(f"  直近3日: {f['recent_avg']:,} / 前7日: {f['prior_avg']:,}")
        elif f["type"] == "monthly_projected":
            lines.append(f"{icon} {f['metric']} {arrow}{abs(f['change_pct'])}%（{f['current_month']}予測）")
            lines.append(f"  着地見込: {f['projected_val']:,} / 前3ヶ月平均: {f['prior_avg']:,}")
        else:
            lines.append(f"{icon} {f['metric']} {arrow}{abs(f['change_pct'])}%（{f['current_month']}）")
            lines.append(f"  当月: {f['current_val']:,} / 前3ヶ月平均: {f['prior_avg']:,}")

        # 原因媒体
        media = f.get("media_breakdown", [])[:2]
        if media:
            causes = [f"{m['media']}({m['change_pct']:+.0f}%)" for m in media]
            lines.append(f"  主因: {', '.join(causes)}")

        # 仮説（1つ）
        hyp = f.get("hypotheses", [])
        if hyp:
            lines.append(f"  → {hyp[0]}")

        lines.append("")

    lines.append("━━━━━━━━━━━━")
    updated = data.get("updated_at", "不明")[:16]
    lines.append(f"データ: {updated}")

    return "\n".join(lines)


def run_detection(verbose: bool = False) -> tuple[list[dict], str]:
    """異常検知を実行。(findings, formatted_report) を返す"""
    data = load_kpi_data()
    if not data:
        return [], "KPIデータなし"

    # データ鮮度チェック
    stale_msg = _check_staleness(data)

    # 分析実行
    daily_findings = analyze_daily(data)
    monthly_findings = analyze_monthly(data)
    projected_findings = analyze_monthly_absolute(data)
    all_findings = daily_findings + monthly_findings + projected_findings

    if not all_findings:
        if verbose:
            msg = "✅ KPI異常なし（全指標が正常範囲内）"
            if stale_msg:
                msg += f"\n⚠️ {stale_msg}"
            return [], msg
        return [], ""

    # ドリルダウン & 仮説生成
    all_findings = drill_down_media(data, all_findings)
    all_findings = generate_hypotheses(all_findings)

    # レポート生成
    report = format_line_report(all_findings, data)
    if stale_msg:
        report += f"\n⚠️ {stale_msg}"

    return all_findings, report


if __name__ == "__main__":
    verbose = "--verbose" in sys.argv
    as_json = "--json" in sys.argv

    findings, report = run_detection(verbose=verbose)

    if as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=2))
    elif report:
        print(report)
    else:
        print("✅ KPI異常なし")
