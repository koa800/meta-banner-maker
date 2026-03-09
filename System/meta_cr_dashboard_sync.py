#!/usr/bin/env python3
"""Meta広告CRの勝ち基準と失敗サンプルを比較し、失敗形を知識化する。"""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data" / "meta_cr_dashboard"
DEFAULT_WINNER_CSV = ROOT_DIR / "System" / "data" / "cr_bigwinners_raw.csv"
DEFAULT_FAILURE_MARKDOWN = ROOT_DIR / "Master" / "addness" / "meta_ads_cr_dashboard.md"
SUMMARY_JSON_PATH = DATA_DIR / "failure_summary.json"
KNOWLEDGE_PATH = ROOT_DIR / "Master" / "knowledge" / "広告CR失敗パターン.md"

FAILURE_COLUMNS = (
    "rank",
    "funnel",
    "ad_name",
    "creator",
    "operator",
    "cr_judgment",
    "kpi_judgment",
    "delivery_status",
    "created_on",
    "impressions",
    "leads",
    "spend",
    "ctr",
    "cpa",
    "hook_rate",
)


def collapse_ws(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def looks_like_date_segment(value: str) -> bool:
    text = collapse_ws(value)
    return bool(
        re.fullmatch(r"\d{6,8}", text)
        or re.fullmatch(r"\d{4}/\d{1,2}/\d{1,2}", text)
        or re.fullmatch(r"\d{1,2}/\d{1,2}.*", text)
        or re.fullmatch(r"\d{1,2}月\d{1,2}日.*", text)
    )


def extract_title_segments(ad_name: str, creator: str = "") -> list[str]:
    parts = [collapse_ws(part) for part in str(ad_name or "").split("/") if collapse_ws(part)]
    if parts and looks_like_date_segment(parts[0]):
        parts = parts[1:]
    creator_name = collapse_ws(creator)
    if creator_name and parts and parts[0] == creator_name:
        parts = parts[1:]
    elif len(parts) >= 3 and re.search(r"LP\d+", parts[-1]):
        parts = parts[1:]
    if parts and re.search(r"LP\d+", parts[-1]):
        parts = parts[:-1]
    return parts


def parse_number(value: Any) -> float | None:
    text = collapse_ws(value).replace(",", "").replace("¥", "").replace("%", "")
    if not text or text in {"-", "データなし"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value: Any) -> int | None:
    number = parse_number(value)
    return int(number) if number is not None else None


def parse_currency(value: Any) -> float | None:
    return parse_number(value)


def parse_rate(value: Any, decimal_ratio: bool = False) -> float | None:
    number = parse_number(value)
    if number is None:
        return None
    return number * 100 if decimal_ratio else number


def normalize_title_from_ad_name(ad_name: str, creator: str = "") -> str:
    title = "/".join(extract_title_segments(ad_name, creator))
    title = re.sub(r"[＿_]+", " ", title)
    return collapse_ws(title)


def extract_lp_key(ad_name: str) -> str:
    match = re.search(r"(LP\d+)", ad_name or "")
    return match.group(1) if match else ""


def extract_title_family(title: str) -> str:
    normalized = collapse_ws(title)
    if not normalized:
        return ""
    family = re.split(r"\s+|with|（|\(", normalized, maxsplit=1)[0]
    return collapse_ws(family)


def extract_opening_key(title_segments: list[str]) -> str:
    for segment in title_segments:
        if "冒頭" in segment:
            return collapse_ws(segment)
    return ""


def extract_distribution_hint(title_segments: list[str]) -> str:
    hints = [
        collapse_ws(segment)
        for segment in title_segments
        if re.search(r"類似|ノンタゲ|広告ID\d+|テスト|予算テスト", segment)
    ]
    return collapse_ws("/".join(hints))


def extract_theme_key(title_segments: list[str]) -> str:
    kept: list[str] = []
    for segment in title_segments:
        normalized = collapse_ws(segment)
        if not normalized:
            continue
        if "冒頭" in normalized:
            continue
        if re.fullmatch(r"広告ID\d+", normalized):
            continue
        if re.search(r"類似\d|ノンタゲ", normalized):
            continue
        kept.append(normalized)
    if kept:
        return collapse_ws("/".join(kept))
    return collapse_ws("/".join(title_segments))


def is_meaningful_theme(theme_key: str) -> bool:
    normalized = collapse_ws(theme_key)
    if not normalized:
        return False
    if re.fullmatch(r"[0-9/ ]+", normalized):
        return False
    return True


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * ratio
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def load_winner_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            ad_name = collapse_ws(raw.get("広告名"))
            if not ad_name:
                continue
            creator = collapse_ws(raw.get("製作者"))
            title_segments = extract_title_segments(ad_name, creator)
            title_core = normalize_title_from_ad_name(ad_name, creator)
            video_url = collapse_ws(raw.get("動画URL"))
            thumbnail_url = collapse_ws(raw.get("サムネイル"))
            rows.append(
                {
                    "ad_name": ad_name,
                    "creator": creator,
                    "title_segments": title_segments,
                    "title_core": title_core,
                    "title_family": extract_title_family(title_core),
                    "theme_key": extract_theme_key(title_segments),
                    "opening_key": extract_opening_key(title_segments),
                    "distribution_hint": extract_distribution_hint(title_segments),
                    "lp_key": extract_lp_key(ad_name),
                    "funnel": collapse_ws(raw.get("ファネル")),
                    "created_on": collapse_ws(raw.get("作成日")),
                    "video_url": video_url,
                    "thumbnail_url": thumbnail_url,
                    "asset_key": video_url if video_url and video_url != "データなし" else thumbnail_url,
                    "ctr": parse_rate(raw.get("CTR"), decimal_ratio=True),
                    "hook_rate": parse_rate(raw.get("フック率（3秒間視聴）"), decimal_ratio=True),
                    "cpa": parse_currency(raw.get("CPA")),
                }
            )
    return rows


def extract_scope_note(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("> 全"):
            return stripped.lstrip("> ").strip()
    return ""


def load_failure_rows_from_markdown(path: Path) -> tuple[list[dict[str, Any]], str]:
    text = path.read_text(encoding="utf-8")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.startswith("| "):
            continue
        cells = [collapse_ws(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) != len(FAILURE_COLUMNS):
            continue
        if not cells[0].isdigit():
            continue
        data = dict(zip(FAILURE_COLUMNS, cells))
        ad_name = data["ad_name"]
        creator = data["creator"]
        title_segments = extract_title_segments(ad_name, creator)
        title_core = normalize_title_from_ad_name(ad_name, creator)
        rows.append(
            {
                "rank": parse_int(data["rank"]),
                "funnel": data["funnel"],
                "ad_name": ad_name,
                "creator": creator,
                "title_segments": title_segments,
                "title_core": title_core,
                "title_family": extract_title_family(title_core),
                "theme_key": extract_theme_key(title_segments),
                "opening_key": extract_opening_key(title_segments),
                "distribution_hint": extract_distribution_hint(title_segments),
                "lp_key": extract_lp_key(ad_name),
                "cr_judgment": data["cr_judgment"],
                "kpi_judgment": data["kpi_judgment"],
                "delivery_status": data["delivery_status"],
                "created_on": data["created_on"],
                "impressions": parse_int(data["impressions"]),
                "leads": parse_int(data["leads"]),
                "spend": parse_currency(data["spend"]),
                "ctr": parse_rate(data["ctr"]),
                "cpa": parse_currency(data["cpa"]),
                "hook_rate": parse_rate(data["hook_rate"]),
            }
        )
    return rows, extract_scope_note(text)


def load_failure_rows_from_csv(path: Path) -> tuple[list[dict[str, Any]], str]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            ad_name = collapse_ws(raw.get("広告名"))
            if not ad_name:
                continue
            cr_judgment = collapse_ws(raw.get("CR判定"))
            if cr_judgment == "大当たり":
                continue
            creator = collapse_ws(raw.get("製作者"))
            title_segments = extract_title_segments(ad_name, creator)
            title_core = normalize_title_from_ad_name(ad_name, creator)
            rows.append(
                {
                    "rank": None,
                    "funnel": collapse_ws(raw.get("ファネル")),
                    "ad_name": ad_name,
                    "creator": creator,
                    "title_segments": title_segments,
                    "title_core": title_core,
                    "title_family": extract_title_family(title_core),
                    "theme_key": extract_theme_key(title_segments),
                    "opening_key": extract_opening_key(title_segments),
                    "distribution_hint": extract_distribution_hint(title_segments),
                    "lp_key": extract_lp_key(ad_name),
                    "cr_judgment": cr_judgment,
                    "kpi_judgment": collapse_ws(raw.get("KPI判定")),
                    "delivery_status": collapse_ws(raw.get("配信状況")),
                    "created_on": collapse_ws(raw.get("作成日")),
                    "impressions": parse_int(raw.get("インプレッション")),
                    "leads": parse_int(raw.get("集客数")),
                    "spend": parse_currency(raw.get("消化金額")),
                    "ctr": parse_rate(raw.get("CTR"), decimal_ratio=True),
                    "cpa": parse_currency(raw.get("CPA")),
                    "hook_rate": parse_rate(raw.get("フック率（3秒間視聴）"), decimal_ratio=True),
                }
            )
    scope_note = f"{path.name} から非大当たり {len(rows)}件を読み込み"
    return rows, scope_note


def build_benchmarks(rows: list[dict[str, Any]]) -> dict[str, float]:
    ctr_values = [row["ctr"] for row in rows if row.get("ctr") is not None]
    hook_values = [row["hook_rate"] for row in rows if row.get("hook_rate") is not None]
    cpa_values = [row["cpa"] for row in rows if row.get("cpa") is not None]
    return {
        "winner_ctr_p25": percentile(ctr_values, 0.25) or 0.0,
        "winner_ctr_median": statistics.median(ctr_values) if ctr_values else 0.0,
        "winner_hook_p25": percentile(hook_values, 0.25) or 0.0,
        "winner_hook_median": statistics.median(hook_values) if hook_values else 0.0,
        "winner_cpa_median": statistics.median(cpa_values) if cpa_values else 0.0,
        "winner_cpa_p75": percentile(cpa_values, 0.75) or 0.0,
    }


def classify_failure_shape(row: dict[str, Any], benchmarks: dict[str, float]) -> tuple[str, str, str]:
    ctr = row.get("ctr")
    hook = row.get("hook_rate")
    cpa = row.get("cpa")

    if ctr is not None and hook is not None and ctr < benchmarks["winner_ctr_p25"] and hook < benchmarks["winner_hook_p25"]:
        return (
            "最初で止まる",
            "冒頭の注意獲得もクリック意欲も弱く、そもそも前に進まない。",
            "strong",
        )

    if ctr is not None and ctr < benchmarks["winner_ctr_p25"]:
        return (
            "見られるが押されない",
            "視聴はされても、自分事化や次を見たい理由が弱く、クリック意思まで届かない。",
            "strong" if hook is not None else "medium",
        )

    if cpa is not None and cpa > benchmarks["winner_cpa_p75"]:
        return (
            "押されるが集客単価が重い",
            "興味は取れているが、期待値ズレか見込客の質の弱さで集客効率が崩れている。",
            "strong",
        )

    return (
        "上流は通るが後ろで失敗",
        "フックとクリックは一定以上。CR単体より、約束の質・LP・オファー・導線の崩れを先に疑う。",
        "strong" if ctr is not None and hook is not None else "medium",
    )


def family_signal_rows(winner_rows: list[dict[str, Any]], failure_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    winner_counts = Counter(row["title_family"] for row in winner_rows if row.get("title_family"))
    failure_counts = Counter(row["title_family"] for row in failure_rows if row.get("title_family"))
    records: list[dict[str, Any]] = []
    for family, failure_count in failure_counts.most_common():
        winner_count = winner_counts.get(family, 0)
        if not family:
            continue
        if failure_count == 1 and winner_count > 0:
            continue
        records.append(
            {
                "family": family,
                "failure_count": failure_count,
                "winner_count": winner_count,
                "signal": "失敗側に偏る" if winner_count == 0 else "勝ち負け混在",
            }
        )
    return records[:10]


def enrich_failures(failure_rows: list[dict[str, Any]], benchmarks: dict[str, float]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for row in failure_rows:
        bucket, reason, confidence = classify_failure_shape(row, benchmarks)
        enriched_row = dict(row)
        enriched_row["failure_bucket"] = bucket
        enriched_row["reason"] = reason
        enriched_row["confidence"] = confidence
        enriched.append(enriched_row)
    return enriched


def build_context_hint(rows: list[dict[str, Any]]) -> str:
    distribution_hints = sorted(
        {
            row.get("distribution_hint")
            for row in rows
            if row.get("distribution_hint")
        }
    )
    lp_keys = sorted({row.get("lp_key") for row in rows if row.get("lp_key")})
    dates = sorted({row.get("created_on") for row in rows if row.get("created_on")})
    if distribution_hints and all(re.fullmatch(r"広告ID\d+", hint or "") for hint in distribution_hints):
        return "広告ID差による配信面ブレを先に疑う"
    if len(distribution_hints) >= 2:
        return "配信対象や配信条件の差が大きい可能性が高い"
    if len(lp_keys) >= 2:
        return "LP差による期待値ズレを先に疑う"
    if len(dates) >= 2:
        return "配信時期差や既視感の蓄積を疑う"
    return "同一アセットでも広告セット・学習状態・配信面でブレる"


def summarize_same_asset_variation(winner_rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in winner_rows:
        asset_key = collapse_ws(row.get("asset_key"))
        if asset_key and asset_key != "データなし":
            groups[asset_key].append(row)

    multi_groups = [rows for rows in groups.values() if len(rows) >= 2]

    exact_context_examples: list[dict[str, Any]] = []
    exact_context_groups: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in winner_rows:
        asset_key = collapse_ws(row.get("asset_key"))
        if not asset_key or asset_key == "データなし":
            continue
        exact_context_groups[(asset_key, row.get("created_on", ""), row.get("lp_key", ""))].append(row)
    for rows in exact_context_groups.values():
        if len(rows) < 2:
            continue
        ctrs = [row["ctr"] for row in rows if row.get("ctr") is not None]
        cpas = [row["cpa"] for row in rows if row.get("cpa") is not None]
        exact_context_examples.append(
            {
                "count": len(rows),
                "created_on": rows[0].get("created_on", ""),
                "lp_key": rows[0].get("lp_key", ""),
                "ctr_spread": (max(ctrs) - min(ctrs)) if len(ctrs) >= 2 else 0.0,
                "cpa_spread": (max(cpas) - min(cpas)) if len(cpas) >= 2 else 0.0,
                "context_hint": build_context_hint(rows),
                "rows": rows,
            }
        )
    exact_context_examples.sort(key=lambda item: (item["cpa_spread"], item["ctr_spread"], item["count"]), reverse=True)

    audience_variation_examples = [
        item
        for item in exact_context_examples
        if len(
            {
                collapse_ws(row.get("distribution_hint"))
                for row in item.get("rows", [])
                if collapse_ws(row.get("distribution_hint"))
            }
        )
        >= 2
    ]

    broad_vs_narrow_examples: list[dict[str, Any]] = []
    broad_ctr_lower_count = 0
    broad_ctr_compared_count = 0
    broad_cpa_heavier_count = 0
    broad_cpa_compared_count = 0
    for item in audience_variation_examples:
        broad_rows = [
            row
            for row in item.get("rows", [])
            if "ノンタゲ" in collapse_ws(row.get("distribution_hint"))
        ]
        narrow_rows = [
            row
            for row in item.get("rows", [])
            if "類似" in collapse_ws(row.get("distribution_hint"))
        ]
        if not broad_rows or not narrow_rows:
            continue
        broad_ctr_values = [row["ctr"] for row in broad_rows if row.get("ctr") is not None]
        narrow_ctr_values = [row["ctr"] for row in narrow_rows if row.get("ctr") is not None]
        broad_cpa_values = [row["cpa"] for row in broad_rows if row.get("cpa") is not None]
        narrow_cpa_values = [row["cpa"] for row in narrow_rows if row.get("cpa") is not None]
        broad_ctr = statistics.mean(broad_ctr_values) if broad_ctr_values else None
        narrow_ctr = statistics.mean(narrow_ctr_values) if narrow_ctr_values else None
        broad_cpa = statistics.mean(broad_cpa_values) if broad_cpa_values else None
        narrow_cpa = statistics.mean(narrow_cpa_values) if narrow_cpa_values else None
        if broad_ctr is not None and narrow_ctr is not None:
            broad_ctr_compared_count += 1
            if broad_ctr < narrow_ctr:
                broad_ctr_lower_count += 1
        if broad_cpa is not None and narrow_cpa is not None:
            broad_cpa_compared_count += 1
            if broad_cpa > narrow_cpa:
                broad_cpa_heavier_count += 1
        broad_vs_narrow_examples.append(
            {
                "created_on": item.get("created_on"),
                "lp_key": item.get("lp_key"),
                "count": item.get("count"),
                "broad_label": " / ".join(
                    sorted(
                        {
                            collapse_ws(row.get("distribution_hint"))
                            for row in broad_rows
                            if collapse_ws(row.get("distribution_hint"))
                        }
                    )
                ),
                "narrow_label": " / ".join(
                    sorted(
                        {
                            collapse_ws(row.get("distribution_hint"))
                            for row in narrow_rows
                            if collapse_ws(row.get("distribution_hint"))
                        }
                    )
                ),
                "broad_ctr": broad_ctr,
                "narrow_ctr": narrow_ctr,
                "broad_cpa": broad_cpa,
                "narrow_cpa": narrow_cpa,
                "context_hint": item.get("context_hint", ""),
                "rows": item.get("rows", []),
            }
        )
    broad_vs_narrow_examples.sort(
        key=lambda item: (
            ((item.get("broad_cpa") or 0.0) - (item.get("narrow_cpa") or 0.0)),
            ((item.get("narrow_ctr") or 0.0) - (item.get("broad_ctr") or 0.0)),
            item.get("count", 0),
        ),
        reverse=True,
    )

    cross_lp_examples: list[dict[str, Any]] = []
    for rows in multi_groups:
        lp_keys = sorted({row.get("lp_key") for row in rows if row.get("lp_key")})
        if len(lp_keys) < 2:
            continue
        ctrs = [row["ctr"] for row in rows if row.get("ctr") is not None]
        cpas = [row["cpa"] for row in rows if row.get("cpa") is not None]
        cross_lp_examples.append(
            {
                "count": len(rows),
                "lp_keys": lp_keys,
                "ctr_spread": (max(ctrs) - min(ctrs)) if len(ctrs) >= 2 else 0.0,
                "cpa_spread": (max(cpas) - min(cpas)) if len(cpas) >= 2 else 0.0,
                "context_hint": build_context_hint(rows),
                "rows": rows,
            }
        )
    cross_lp_examples.sort(key=lambda item: (item["cpa_spread"], item["ctr_spread"], item["count"]), reverse=True)

    theme_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in winner_rows:
        theme_key = collapse_ws(row.get("theme_key"))
        if theme_key:
            theme_groups[theme_key].append(row)

    opening_examples: list[dict[str, Any]] = []
    for theme_key, rows in theme_groups.items():
        if not is_meaningful_theme(theme_key):
            continue
        openings = sorted({row.get("opening_key") for row in rows if row.get("opening_key")})
        if len(openings) < 2:
            continue
        by_opening: list[dict[str, Any]] = []
        for opening_key in openings:
            subset = [row for row in rows if row.get("opening_key") == opening_key]
            ctrs = [row["ctr"] for row in subset if row.get("ctr") is not None]
            cpas = [row["cpa"] for row in subset if row.get("cpa") is not None]
            by_opening.append(
                {
                    "opening_key": opening_key,
                    "count": len(subset),
                    "ctr_median": statistics.median(ctrs) if ctrs else None,
                    "cpa_median": statistics.median(cpas) if cpas else None,
                }
            )
        cpa_values = [record["cpa_median"] for record in by_opening if record.get("cpa_median") is not None]
        ctr_values = [record["ctr_median"] for record in by_opening if record.get("ctr_median") is not None]
        opening_examples.append(
            {
                "theme_key": theme_key,
                "count": len(rows),
                "cpa_spread": (max(cpa_values) - min(cpa_values)) if len(cpa_values) >= 2 else 0.0,
                "ctr_spread": (max(ctr_values) - min(ctr_values)) if len(ctr_values) >= 2 else 0.0,
                "openings": by_opening,
            }
        )
    opening_examples.sort(key=lambda item: (item["count"], item["cpa_spread"], item["ctr_spread"]), reverse=True)

    return {
        "same_asset_groups_ge_2": len(multi_groups),
        "rows_in_same_asset_groups": sum(len(rows) for rows in multi_groups),
        "same_asset_same_context_examples": exact_context_examples[:5],
        "same_asset_same_context_group_count": len(exact_context_examples),
        "audience_variation_group_count": len(audience_variation_examples),
        "audience_variation_examples": audience_variation_examples[:5],
        "broad_vs_narrow_group_count": len(broad_vs_narrow_examples),
        "broad_ctr_lower_count": broad_ctr_lower_count,
        "broad_ctr_compared_count": broad_ctr_compared_count,
        "broad_cpa_heavier_count": broad_cpa_heavier_count,
        "broad_cpa_compared_count": broad_cpa_compared_count,
        "broad_vs_narrow_examples": broad_vs_narrow_examples[:5],
        "same_asset_cross_lp_examples": cross_lp_examples[:5],
        "theme_opening_examples": opening_examples[:5],
    }


def summarize_patterns(winner_rows: list[dict[str, Any]], failure_rows: list[dict[str, Any]], scope_note: str) -> dict[str, Any]:
    benchmarks = build_benchmarks(winner_rows)
    enriched_failures = enrich_failures(failure_rows, benchmarks)
    same_asset_summary = summarize_same_asset_variation(winner_rows)

    stage_counts = Counter(row["failure_bucket"] for row in enriched_failures)
    examples_by_stage: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in enriched_failures:
        examples_by_stage[row["failure_bucket"]].append(row)

    failure_ctr_values = [row["ctr"] for row in failure_rows if row.get("ctr") is not None]
    failure_hook_values = [row["hook_rate"] for row in failure_rows if row.get("hook_rate") is not None]
    failure_cpa_values = [row["cpa"] for row in failure_rows if row.get("cpa") is not None]

    top_funnel_strong = [
        row
        for row in failure_rows
        if row.get("ctr") is not None
        and row.get("hook_rate") is not None
        and row["ctr"] >= benchmarks["winner_ctr_median"]
        and row["hook_rate"] >= benchmarks["winner_hook_median"]
    ]

    efficient_but_failed = [
        row
        for row in top_funnel_strong
        if row.get("cpa") is not None and row["cpa"] <= benchmarks["winner_cpa_p75"]
    ]

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "winner_source": str(DEFAULT_WINNER_CSV),
        "failure_source": str(DEFAULT_FAILURE_MARKDOWN),
        "failure_scope_note": scope_note,
        "winner_count": len(winner_rows),
        "failure_count": len(failure_rows),
        "benchmarks": {
            **benchmarks,
            "failure_ctr_median": statistics.median(failure_ctr_values) if failure_ctr_values else 0.0,
            "failure_hook_median": statistics.median(failure_hook_values) if failure_hook_values else 0.0,
            "failure_cpa_median": statistics.median(failure_cpa_values) if failure_cpa_values else 0.0,
        },
        "comparison": {
            "failure_ctr_ge_winner_median": sum(
                1 for row in failure_rows if row.get("ctr") is not None and row["ctr"] >= benchmarks["winner_ctr_median"]
            ),
            "failure_hook_ge_winner_median": sum(
                1
                for row in failure_rows
                if row.get("hook_rate") is not None and row["hook_rate"] >= benchmarks["winner_hook_median"]
            ),
            "failure_cpa_le_winner_median": sum(
                1 for row in failure_rows if row.get("cpa") is not None and row["cpa"] <= benchmarks["winner_cpa_median"]
            ),
            "top_funnel_strong_failures": len(top_funnel_strong),
            "efficient_but_failed": len(efficient_but_failed),
        },
        "stage_counts": [
            {"name": name, "count": count}
            for name, count in stage_counts.most_common()
        ],
        "stage_examples": {
            bucket: rows[:5]
            for bucket, rows in examples_by_stage.items()
        },
        "family_signals": family_signal_rows(winner_rows, failure_rows),
        "same_asset_summary": same_asset_summary,
    }
    return summary


def format_percent(value: float | None) -> str:
    return "-" if value is None else f"{value:.1f}%"


def format_yen(value: float | None) -> str:
    return "-" if value is None else f"¥{int(round(value)):,}"


def render_stage_table(stage_counts: list[dict[str, Any]], failure_count: int) -> str:
    lines = ["| 失敗形 | 件数 | 構成比 |", "|---|---:|---:|"]
    for record in stage_counts:
        share = (record["count"] / failure_count) * 100 if failure_count else 0
        lines.append(f"| {record['name']} | {record['count']} | {share:.1f}% |")
    return "\n".join(lines)


def render_family_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| タイトル家系 | 失敗数 | 勝ち数 | 読み |", "|---|---:|---:|---|"]
    for row in rows:
        lines.append(
            f"| {row['family']} | {row['failure_count']} | {row['winner_count']} | {row['signal']} |"
        )
    return "\n".join(lines)


def render_examples(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 広告名 | LP | CTR | CPA | フック率 | 解釈 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {ad} | {lp} | {ctr} | {cpa} | {hook} | {reason} |".format(
                ad=row["ad_name"],
                lp=row.get("lp_key") or "-",
                ctr=format_percent(row.get("ctr")),
                cpa=format_yen(row.get("cpa")),
                hook=format_percent(row.get("hook_rate")),
                reason=row["reason"],
            )
        )
    return "\n".join(lines)


def render_same_asset_context_examples(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 日付 | LP | 件数 | CTR幅 | CPA幅 | 先に疑うこと | 代表行 |",
        "|---|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        examples = " / ".join(
            filter(
                None,
                [
                    collapse_ws(example.get("distribution_hint")) or collapse_ws(example.get("title_core"))
                    for example in row.get("rows", [])[:3]
                ],
            )
        )
        lines.append(
            "| {date} | {lp} | {count} | {ctr:.2f}% | {cpa} | {hint} | {examples} |".format(
                date=row.get("created_on") or "-",
                lp=row.get("lp_key") or "-",
                count=row.get("count", 0),
                ctr=row.get("ctr_spread", 0.0),
                cpa=format_yen(row.get("cpa_spread")),
                hint=row.get("context_hint", "-"),
                examples=examples or "-",
            )
        )
    return "\n".join(lines)


def render_cross_lp_examples(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| LP群 | 件数 | CTR幅 | CPA幅 | 先に疑うこと | 代表行 |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in rows:
        examples = " / ".join(
            filter(
                None,
                [
                    collapse_ws(example.get("title_core")) or collapse_ws(example.get("ad_name"))
                    for example in row.get("rows", [])[:2]
                ],
            )
        )
        lines.append(
            "| {lps} | {count} | {ctr:.2f}% | {cpa} | {hint} | {examples} |".format(
                lps=", ".join(row.get("lp_keys", [])) or "-",
                count=row.get("count", 0),
                ctr=row.get("ctr_spread", 0.0),
                cpa=format_yen(row.get("cpa_spread")),
                hint=row.get("context_hint", "-"),
                examples=examples or "-",
            )
        )
    return "\n".join(lines)


def render_broad_vs_narrow_examples(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 日付 | LP | 広いオーディエンス | 狭いオーディエンス | CTR | CPA | 読み |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        ctr_text = "- / -"
        if row.get("broad_ctr") is not None or row.get("narrow_ctr") is not None:
            ctr_text = f"{format_percent(row.get('broad_ctr'))} -> {format_percent(row.get('narrow_ctr'))}"
        cpa_text = "- / -"
        if row.get("broad_cpa") is not None or row.get("narrow_cpa") is not None:
            cpa_text = f"{format_yen(row.get('broad_cpa'))} -> {format_yen(row.get('narrow_cpa'))}"
        lines.append(
            "| {date} | {lp} | {broad} | {narrow} | {ctr} | {cpa} | {hint} |".format(
                date=row.get("created_on") or "-",
                lp=row.get("lp_key") or "-",
                broad=row.get("broad_label") or "-",
                narrow=row.get("narrow_label") or "-",
                ctr=ctr_text,
                cpa=cpa_text,
                hint=row.get("context_hint", "-"),
            )
        )
    return "\n".join(lines)


def render_opening_examples(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| テーマ | 冒頭構成 | 件数 | CTR中央値 | CPA中央値 |",
        "|---|---|---:|---:|---:|",
    ]
    for row in rows:
        theme_key = row.get("theme_key") or "-"
        for opening in row.get("openings", []):
            lines.append(
                "| {theme} | {opening_key} | {count} | {ctr} | {cpa} |".format(
                    theme=theme_key,
                    opening_key=opening.get("opening_key") or "-",
                    count=opening.get("count", 0),
                    ctr=format_percent(opening.get("ctr_median")),
                    cpa=format_yen(opening.get("cpa_median")),
                )
            )
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    benchmarks = summary["benchmarks"]
    comparison = summary["comparison"]
    same_asset_summary = summary["same_asset_summary"]
    lines = [
        "# 広告CR失敗パターン",
        "",
        f"最終更新: {datetime.now().date().isoformat()}",
        "",
        "Meta広告CRの失敗は、`誰が作ったか` より `どこで崩れたか` で読む。",
        "ここでは `勝ちCR 340件` を基準に、`失敗側 24件` を比較している。",
        "",
        "## 集計対象",
        "",
        f"- 勝ち基準: `System/data/cr_bigwinners_raw.csv`（{summary['winner_count']}件）",
        f"- 失敗サンプル: `Master/addness/meta_ads_cr_dashboard.md`（{summary['failure_count']}件）",
    ]
    if summary["failure_scope_note"]:
        lines.append(f"- 失敗側の範囲: {summary['failure_scope_note']}")
    lines.extend(
        [
            "- 注意: 失敗側は `消化金額上位24件` のスナップショット。全失敗CRの全量ではなく、高消化で負けた型を先に見ている。",
            "",
            "## 勝ち基準との比較",
            "",
            "| 指標 | 勝ちCR中央値 | 失敗側中央値 |",
            "|---|---:|---:|",
            f"| CTR | {benchmarks['winner_ctr_median']:.2f}% | {benchmarks['failure_ctr_median']:.2f}% |",
            f"| フック率 | {benchmarks['winner_hook_median']:.2f}% | {benchmarks['failure_hook_median']:.2f}% |",
            f"| CPA | {format_yen(benchmarks['winner_cpa_median'])} | {format_yen(benchmarks['failure_cpa_median'])} |",
            "",
            f"- 失敗 {summary['failure_count']}件のうち `{comparison['failure_ctr_ge_winner_median']}` 件は CTR が勝ちCR中央値以上",
            f"- 失敗 {summary['failure_count']}件のうち `{comparison['failure_hook_ge_winner_median']}` 件は フック率が勝ちCR中央値以上",
            f"- 失敗 {summary['failure_count']}件のうち `{comparison['top_funnel_strong_failures']}` 件は CTR とフック率の両方が勝ちCR中央値以上",
            f"- その中でも `{comparison['efficient_but_failed']}` 件は CPA まで勝ちCRの第3四分位以内に収まる",
            "",
            "## まず読むべき本質",
            "",
            f"- 高消化の失敗は `冒頭で死ぬ型` より `上流は通るが後ろで失敗` が中心。今回の24件では `{comparison['top_funnel_strong_failures']}` 件がこの形に入る。",
            "- つまり、失敗CRの主因を `フック不足` だけで説明しない。約束の質、クリック後の期待値、LP・オファー・導線の崩れを先に疑う。",
            "- 一方で `タイトルの家系` には偏りがある。言い回し単体で勝てるわけではないが、同じ家系が繰り返し外れているなら失敗候補として重く見る。",
            f"- 勝ちCR 340件の中だけでも、同一アセットの再利用群は `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。CR単体ではなく `配信対象（オーディエンス） / 広告ID / 広告セットID / LP / 時期` を切って読む必要がある。",
            "",
            "## Meta広告分析から見えた SNS広告共通の失敗メカニズム",
            "",
            "- ここで見ているのは Meta広告CR だが、`フックを広く取りすぎて広いオーディエンスに寄る失敗` という構造自体は SNS広告全般で起こる。",
            f"- 勝ちCR 340件の内部だけでも、`同一アセット × 同日 × 同LP` まで揃えて数値を比べられる群が `{same_asset_summary['same_asset_same_context_group_count']}` 群あり、そのうち配信対象差を読める群が `{same_asset_summary['audience_variation_group_count']}` 群ある。",
            f"- さらに `ノンタゲ vs 類似` を直接比べられる群は `{same_asset_summary['broad_vs_narrow_group_count']}` 群あり、CTR は `{same_asset_summary['broad_ctr_lower_count']}/{same_asset_summary['broad_ctr_compared_count']}` 群で広い側が低く、CPA は比較可能な `{same_asset_summary['broad_cpa_heavier_count']}/{same_asset_summary['broad_cpa_compared_count']}` 群で広い側が重かった。",
            "- つまり `広いフックで人を集める -> オーディエンスが広がる -> 浅い反応層に学習する -> CTRやフック率の見た目より後ろの質が弱くなる` を、SNS広告の代表的な失敗メカニズムとして常に疑う。",
            "",
            "### ノンタゲと類似で差が出た例",
            "",
            render_broad_vs_narrow_examples(same_asset_summary["broad_vs_narrow_examples"])
            if same_asset_summary["broad_vs_narrow_examples"]
            else "- まだ該当なし",
            "",
            "## 失敗形の内訳",
            "",
            render_stage_table(summary["stage_counts"], summary["failure_count"]),
            "",
            "## タイトル家系の偏り",
            "",
            render_family_table(summary["family_signals"]) if summary["family_signals"] else "- 目立つ偏りはまだ出ていない",
            "",
            "## 同一アセットでも数値がズレる例",
            "",
            "- まず `同じ動画URL/画像` を束ねる。そこから `同日・同LP` で比べ、最後に `LP差 / 時期差 / 冒頭差` を見る。",
            f"- 今回の340件では、同一アセット群が `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。`同じCRなのに数値が違う` を解くための最初の切り口になる。",
            "",
            "### 同日・同LPでもズレる例",
            "",
            render_same_asset_context_examples(same_asset_summary["same_asset_same_context_examples"])
            if same_asset_summary["same_asset_same_context_examples"]
            else "- まだ該当なし",
            "",
            "### 同一アセットをLP違いで回した例",
            "",
            render_cross_lp_examples(same_asset_summary["same_asset_cross_lp_examples"])
            if same_asset_summary["same_asset_cross_lp_examples"]
            else "- まだ該当なし",
            "",
            "### 同テーマの冒頭構成差",
            "",
            render_opening_examples(same_asset_summary["theme_opening_examples"])
            if same_asset_summary["theme_opening_examples"]
            else "- まだ該当なし",
        ]
    )

    for stage in summary["stage_counts"]:
        bucket = stage["name"]
        rows = summary["stage_examples"].get(bucket, [])
        lines.extend(
            [
                "",
                f"## 具体例: {bucket}",
                "",
                render_examples(rows) if rows else "- 該当なし",
            ]
        )

    lines.extend(
        [
            "",
            "## この知識の使い方",
            "",
            "- まず `どこで崩れたか` を決める。`誰が作ったか` や `単語単体` に逃げない。",
            "- `上流は通るが後ろで失敗` に入ったら、CR単体の改善より `約束の質 / LP / オファー / 導線` を優先して見る。",
            "- `押されるが集客単価が重い` は、興味は取れているので `質の低いクリック` か `期待値ズレ` を疑う。",
            "- 同一アセット比較は `asset -> 配信対象（オーディエンス） -> 広告ID / 広告セットID -> LP -> 時期 -> 冒頭` の順で切る。順番を飛ばして `このCRは強い/弱い` と断定しない。",
            "- 同じ家系が失敗側に偏っていても、1回では rules に上げない。複数スナップショットか下流数値が重なってから rules 化する。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_analysis(winner_csv: Path, failure_markdown: Path | None, failure_csv: Path | None = None) -> dict[str, Any]:
    winner_rows = load_winner_rows(winner_csv)
    if failure_csv:
        failure_rows, scope_note = load_failure_rows_from_csv(failure_csv)
    elif failure_markdown:
        failure_rows, scope_note = load_failure_rows_from_markdown(failure_markdown)
    else:
        raise SystemExit("failure_markdown か failure_csv のどちらかが必要です")
    if not winner_rows:
        raise SystemExit(f"勝ちCRのCSVを読めませんでした: {winner_csv}")
    if not failure_rows:
        source_label = str(failure_csv or failure_markdown)
        raise SystemExit(f"失敗サンプルを読めませんでした: {source_label}")
    summary = summarize_patterns(winner_rows, failure_rows, scope_note)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    KNOWLEDGE_PATH.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def print_status() -> None:
    summary = json.loads(SUMMARY_JSON_PATH.read_text(encoding="utf-8")) if SUMMARY_JSON_PATH.exists() else {}
    print(
        json.dumps(
            {
                "winner_source": str(DEFAULT_WINNER_CSV),
                "failure_source": str(DEFAULT_FAILURE_MARKDOWN),
                "latest_summary_generated_at": summary.get("generated_at", ""),
                "winner_count": summary.get("winner_count", 0),
                "failure_count": summary.get("failure_count", 0),
                "knowledge_path": str(KNOWLEDGE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meta広告CRの勝ち基準と失敗サンプルを比較して失敗形を知識化する")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="勝ち基準と失敗サンプルを比較して knowledge を更新する")
    analyze.add_argument("--winner-csv", type=Path, default=DEFAULT_WINNER_CSV)
    analyze.add_argument("--failure-markdown", type=Path, default=DEFAULT_FAILURE_MARKDOWN)
    analyze.add_argument("--failure-csv", type=Path, default=None)

    subparsers.add_parser("status", help="現在のソースと最新集計状況を表示する")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "analyze"
    if command == "status":
        print_status()
        return

    summary = run_analysis(args.winner_csv, args.failure_markdown, args.failure_csv)
    print(
        json.dumps(
            {
                "generated_at": summary["generated_at"],
                "winner_count": summary["winner_count"],
                "failure_count": summary["failure_count"],
                "knowledge_path": str(KNOWLEDGE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
