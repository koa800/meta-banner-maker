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


def normalize_title_from_ad_name(ad_name: str) -> str:
    parts = [collapse_ws(part) for part in ad_name.split("/") if collapse_ws(part)]
    if parts and re.fullmatch(r"\d{6,8}", parts[0]):
        parts = parts[1:]
    title = parts[1] if len(parts) >= 2 else ""
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
            title_core = normalize_title_from_ad_name(ad_name)
            rows.append(
                {
                    "ad_name": ad_name,
                    "title_core": title_core,
                    "title_family": extract_title_family(title_core),
                    "lp_key": extract_lp_key(ad_name),
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
        title_core = normalize_title_from_ad_name(ad_name)
        rows.append(
            {
                "rank": parse_int(data["rank"]),
                "funnel": data["funnel"],
                "ad_name": ad_name,
                "title_core": title_core,
                "title_family": extract_title_family(title_core),
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


def summarize_patterns(winner_rows: list[dict[str, Any]], failure_rows: list[dict[str, Any]], scope_note: str) -> dict[str, Any]:
    benchmarks = build_benchmarks(winner_rows)
    enriched_failures = enrich_failures(failure_rows, benchmarks)

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


def render_markdown(summary: dict[str, Any]) -> str:
    benchmarks = summary["benchmarks"]
    comparison = summary["comparison"]
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
            "",
            "## 失敗形の内訳",
            "",
            render_stage_table(summary["stage_counts"], summary["failure_count"]),
            "",
            "## タイトル家系の偏り",
            "",
            render_family_table(summary["family_signals"]) if summary["family_signals"] else "- 目立つ偏りはまだ出ていない",
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
            "- 同じ家系が失敗側に偏っていても、1回では rules に上げない。複数スナップショットか下流数値が重なってから rules 化する。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_analysis(winner_csv: Path, failure_markdown: Path) -> dict[str, Any]:
    winner_rows = load_winner_rows(winner_csv)
    failure_rows, scope_note = load_failure_rows_from_markdown(failure_markdown)
    if not winner_rows:
        raise SystemExit(f"勝ちCRのCSVを読めませんでした: {winner_csv}")
    if not failure_rows:
        raise SystemExit(f"失敗サンプルの markdown を読めませんでした: {failure_markdown}")
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

    subparsers.add_parser("status", help="現在のソースと最新集計状況を表示する")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "analyze"
    if command == "status":
        print_status()
        return

    summary = run_analysis(args.winner_csv, args.failure_markdown)
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
