#!/usr/bin/env python3
"""Meta広告CR一覧の Looker CSV を正規化し、失敗パターン候補を集約する。"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).resolve().parent / "data" / "meta_cr_dashboard"
DEFAULT_INPUT_DIR = Path.home() / "Desktop" / "Looker Studio CSV" / "meta_cr_dashboard"
NORMALIZED_CSV_PATH = DATA_DIR / "latest_normalized.csv"
SUMMARY_JSON_PATH = DATA_DIR / "failure_summary.json"
KNOWLEDGE_PATH = ROOT_DIR / "Master" / "knowledge" / "広告CR失敗パターン.md"

FAIL_CR_JUDGMENTS = {"はずれ"}
SOFT_FAIL_CR_JUDGMENTS = {"微妙"}
FAIL_KPI_JUDGMENTS = {"許容KPI未達成"}

TEXT_COLUMNS = (
    "ファネル",
    "広告名",
    "製作者",
    "運用者",
    "CR判定",
    "KPI判定",
    "広告タイプ",
    "動画URL",
    "管理画面URL",
    "配信状況",
    "作成日",
)

NUMERIC_COLUMNS = (
    "インプレッション",
    "リーチ",
    "リンククリック数",
    "集客数",
    "フロント購入数",
    "消化金額",
    "CTR",
    "CVR",
    "CPA",
    "CPO",
    "CPM",
    "フック率（3秒間視聴）",
    "25%視聴維持率",
    "50%視聴維持率",
    "75%視聴維持率",
    "100%視聴維持率",
)

HEADER_MAP = {
    "ファネル": "funnel",
    "広告名": "ad_name",
    "製作者": "creator",
    "運用者": "operator",
    "CR判定": "cr_judgment",
    "KPI判定": "kpi_judgment",
    "広告タイプ": "ad_type",
    "動画URL": "video_url",
    "管理画面URL": "manager_url",
    "配信状況": "delivery_status",
    "作成日": "created_on",
    "インプレッション": "impressions",
    "リーチ": "reach",
    "リンククリック数": "link_clicks",
    "集客数": "leads",
    "フロント購入数": "front_purchases",
    "消化金額": "spend",
    "CTR": "ctr",
    "CVR": "cvr",
    "CPA": "cpa",
    "CPO": "cpo",
    "CPM": "cpm",
    "フック率（3秒間視聴）": "hook_rate",
    "25%視聴維持率": "view_25_rate",
    "50%視聴維持率": "view_50_rate",
    "75%視聴維持率": "view_75_rate",
    "100%視聴維持率": "view_100_rate",
}


def collapse_ws(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def detect_snapshot_date(path: Path) -> str:
    match = re.match(r"(\d{4}-\d{2}-\d{2})_", path.name)
    if match:
        return match.group(1)
    return datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()


def parse_int(value: str) -> int | None:
    text = collapse_ws(value).replace(",", "")
    if not text or text == "-":
        return None
    text = text.replace("¥", "").replace("%", "")
    try:
        return int(float(text))
    except ValueError:
        return None


def parse_float(value: str) -> float | None:
    text = collapse_ws(value).replace(",", "")
    if not text or text == "-":
        return None
    text = text.replace("¥", "").replace("%", "")
    try:
        return float(text)
    except ValueError:
        return None


def completeness_score(row: dict[str, Any]) -> int:
    fields = (
        "cr_judgment",
        "kpi_judgment",
        "leads",
        "spend",
        "ctr",
        "cpa",
        "hook_rate",
        "lp_key",
        "cr_key",
    )
    return sum(1 for field in fields if row.get(field) not in ("", None))


def extract_ad_parts(ad_name: str) -> dict[str, str]:
    parts = [collapse_ws(part) for part in ad_name.split("/") if collapse_ws(part)]
    created_token = ""
    if parts and re.fullmatch(r"\d{6,8}", parts[0]):
        created_token = parts.pop(0)
    creator = parts[0] if len(parts) >= 1 else ""
    title = parts[1] if len(parts) >= 2 else ""
    lp_cr = parts[2] if len(parts) >= 3 else ""
    lp_match = re.search(r"(LP\d+)", lp_cr)
    cr_match = re.search(r"(CR\d+)", lp_cr)
    title_core = re.sub(r"[＿_]+", " ", title).strip()
    return {
        "created_token": created_token,
        "creator_from_name": creator,
        "title": title,
        "title_core": title_core,
        "lp_key": lp_match.group(1) if lp_match else "",
        "cr_key": cr_match.group(1) if cr_match else "",
    }


def load_csv_rows(path: Path) -> list[dict[str, str]]:
    last_error: Exception | None = None
    for encoding in ("utf-8-sig", "cp932", "utf-8", "shift_jis"):
        try:
            text = path.read_text(encoding=encoding)
            lines = text.splitlines()
            header_index = None
            for index, line in enumerate(lines):
                if "広告名" in line and "CR判定" in line and "KPI判定" in line:
                    header_index = index
                    break
            if header_index is None:
                continue
            reader = csv.DictReader(lines[header_index:])
            rows: list[dict[str, str]] = []
            for row in reader:
                if not row:
                    continue
                ad_name = collapse_ws(row.get("広告名"))
                if not ad_name:
                    continue
                rows.append({key: collapse_ws(value) for key, value in row.items() if key})
            if rows:
                return rows
        except Exception as exc:  # pragma: no cover - encoding fallback
            last_error = exc
    if last_error:
        raise last_error
    return []


def normalize_row(raw_row: dict[str, str], source_path: Path) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "snapshot_date": detect_snapshot_date(source_path),
        "source_file": source_path.name,
    }
    for column in TEXT_COLUMNS:
        normalized[HEADER_MAP[column]] = collapse_ws(raw_row.get(column))
    for column in NUMERIC_COLUMNS:
        field = HEADER_MAP[column]
        if column in {"CTR", "CVR", "フック率（3秒間視聴）", "25%視聴維持率", "50%視聴維持率", "75%視聴維持率", "100%視聴維持率"}:
            normalized[field] = parse_float(raw_row.get(column, ""))
        else:
            normalized[field] = parse_int(raw_row.get(column, ""))

    ad_parts = extract_ad_parts(normalized["ad_name"])
    normalized.update(ad_parts)
    if not normalized.get("creator") and normalized["creator_from_name"]:
        normalized["creator"] = normalized["creator_from_name"]
    return normalized


def choose_latest_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row.get("ad_name") or f"{row.get('source_file')}:{row.get('cr_key')}"
        previous = by_key.get(key)
        if not previous:
            by_key[key] = row
            continue
        current_tuple = (row.get("snapshot_date", ""), completeness_score(row))
        previous_tuple = (previous.get("snapshot_date", ""), completeness_score(previous))
        if current_tuple >= previous_tuple:
            by_key[key] = row
    return sorted(by_key.values(), key=lambda item: (item.get("snapshot_date", ""), item.get("ad_name", "")))


def counter_to_records(counter: Counter, limit: int = 10) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common(limit) if name]


def collect_counter(rows: list[dict[str, Any]], field: str) -> Counter:
    return Counter(collapse_ws(row.get(field)) for row in rows if collapse_ws(row.get(field)))


def summarize_patterns(rows: list[dict[str, Any]]) -> dict[str, Any]:
    unique_rows = choose_latest_rows(rows)
    strict_fail_rows = [
        row for row in unique_rows
        if row.get("cr_judgment") in FAIL_CR_JUDGMENTS or row.get("kpi_judgment") in FAIL_KPI_JUDGMENTS
    ]
    soft_fail_rows = [row for row in unique_rows if row.get("cr_judgment") in SOFT_FAIL_CR_JUDGMENTS]
    fail_rows = choose_latest_rows(strict_fail_rows + soft_fail_rows)

    lp_totals = collect_counter(unique_rows, "lp_key")
    lp_fails = collect_counter(fail_rows, "lp_key")
    lp_fail_ratio = []
    for lp_key, total in lp_totals.items():
        if not total:
            continue
        lp_fail_ratio.append({
            "lp_key": lp_key,
            "fail_count": lp_fails.get(lp_key, 0),
            "total_count": total,
            "fail_ratio": round(lp_fails.get(lp_key, 0) / total, 4),
        })
    lp_fail_ratio.sort(key=lambda item: (item["fail_ratio"], item["fail_count"]), reverse=True)

    high_hook_failures = sorted(
        [
            row for row in fail_rows
            if (row.get("hook_rate") or 0) >= 40
        ],
        key=lambda row: ((row.get("hook_rate") or 0), (row.get("spend") or 0)),
        reverse=True,
    )[:10]

    low_ctr_failures = sorted(
        [
            row for row in fail_rows
            if row.get("ctr") is not None and row.get("ctr") < 1.0
        ],
        key=lambda row: ((row.get("spend") or 0), (row.get("ctr") or 0)),
        reverse=True,
    )[:10]

    high_spend_failures = sorted(
        fail_rows,
        key=lambda row: (row.get("spend") or 0),
        reverse=True,
    )[:10]

    grouped_by_pattern: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fail_rows:
        title_core = collapse_ws(row.get("title_core") or row.get("title"))
        if title_core:
            grouped_by_pattern[title_core].append(row)

    repeated_patterns = sorted(
        [
            {
                "pattern": pattern,
                "count": len(pattern_rows),
                "lp_keys": sorted({row.get("lp_key") for row in pattern_rows if row.get("lp_key")}),
                "funnel_keys": sorted({row.get("funnel") for row in pattern_rows if row.get("funnel")}),
            }
            for pattern, pattern_rows in grouped_by_pattern.items()
        ],
        key=lambda item: item["count"],
        reverse=True,
    )[:15]

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_dir": str(DEFAULT_INPUT_DIR),
        "snapshot_files": len({row["source_file"] for row in rows}),
        "snapshot_rows": len(rows),
        "unique_rows": len(unique_rows),
        "strict_fail_rows": len(strict_fail_rows),
        "soft_fail_rows": len(soft_fail_rows),
        "fail_rows": len(fail_rows),
        "cr_judgment_counts": counter_to_records(collect_counter(unique_rows, "cr_judgment")),
        "kpi_judgment_counts": counter_to_records(collect_counter(unique_rows, "kpi_judgment")),
        "fail_funnel_counts": counter_to_records(collect_counter(fail_rows, "funnel")),
        "fail_lp_counts": counter_to_records(collect_counter(fail_rows, "lp_key")),
        "fail_creator_counts": counter_to_records(collect_counter(fail_rows, "creator")),
        "fail_operator_counts": counter_to_records(collect_counter(fail_rows, "operator")),
        "fail_title_patterns": repeated_patterns,
        "lp_fail_ratio": lp_fail_ratio[:10],
        "high_hook_failures": high_hook_failures,
        "low_ctr_failures": low_ctr_failures,
        "high_spend_failures": high_spend_failures,
    }
    return summary


def render_counter_table(records: list[dict[str, Any]], left_header: str, right_header: str = "件数") -> str:
    lines = [f"| {left_header} | {right_header} |", "|---|---:|"]
    for record in records:
        lines.append(f"| {record['name']} | {record['count']} |")
    return "\n".join(lines)


def render_example_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 広告名 | LP | CR判定 | KPI判定 | CTR | CPA | フック率 | 消化金額 |",
        "|---|---|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {ad} | {lp} | {cr} | {kpi} | {ctr} | {cpa} | {hook} | {spend} |".format(
                ad=row.get("ad_name", ""),
                lp=row.get("lp_key", "-"),
                cr=row.get("cr_judgment", "-"),
                kpi=row.get("kpi_judgment", "-"),
                ctr=f"{row['ctr']:.1f}%" if row.get("ctr") is not None else "-",
                cpa=f"¥{int(row['cpa']):,}" if row.get("cpa") is not None else "-",
                hook=f"{row['hook_rate']:.1f}%" if row.get("hook_rate") is not None else "-",
                spend=f"¥{int(row['spend']):,}" if row.get("spend") is not None else "-",
            )
        )
    return "\n".join(lines)


def render_markdown(summary: dict[str, Any]) -> str:
    title_pattern_lines = []
    for item in summary["fail_title_patterns"][:10]:
        lp_keys = ", ".join(item["lp_keys"]) if item["lp_keys"] else "-"
        title_pattern_lines.append(f"- `{item['pattern']}`: {item['count']}件（LP: {lp_keys}）")
    lp_ratio_lines = []
    for item in summary["lp_fail_ratio"][:5]:
        lp_ratio_lines.append(
            f"- `{item['lp_key']}`: 失敗 {item['fail_count']} / 全体 {item['total_count']} "
            f"（失敗比率 {item['fail_ratio'] * 100:.1f}%）"
        )
    lines = [
        "# 広告CR失敗パターン",
        "",
        f"最終更新: {datetime.now().date().isoformat()}",
        "",
        "この文書は Meta広告の CR ダッシュボード CSV を正規化して、`失敗候補` を集計したものです。",
        "`何が外れたか` の比較には使えるが、`なぜ外れたか` の断定には使わない。",
        "",
        "## 集計対象",
        "",
        f"- スナップショットCSV: {summary['snapshot_files']}ファイル",
        f"- スナップショット総行数: {summary['snapshot_rows']}行",
        f"- 広告名ベースのユニークCR: {summary['unique_rows']}件",
        f"- 厳しめの失敗件数（`はずれ` or `許容KPI未達成`）: {summary['strict_fail_rows']}件",
        f"- 失敗候補件数（上記 + `微妙`）: {summary['fail_rows']}件",
        "",
        "## 判定分布",
        "",
        render_counter_table(summary["cr_judgment_counts"], "CR判定"),
        "",
        render_counter_table(summary["kpi_judgment_counts"], "KPI判定"),
        "",
        "## 失敗候補の偏り",
        "",
        render_counter_table(summary["fail_funnel_counts"], "ファネル"),
        "",
        render_counter_table(summary["fail_lp_counts"], "LP"),
        "",
        render_counter_table(summary["fail_creator_counts"], "製作者"),
        "",
        "## 繰り返し出る失敗タイトル",
        "",
    ]
    lines.extend(title_pattern_lines or ["- まだ十分な母数がありません"])
    lines.extend([
        "",
        "## LPごとの失敗比率",
        "",
    ])
    lines.extend(lp_ratio_lines or ["- まだ十分な母数がありません"])
    lines.extend([
        "",
        "## 高フックでも外れている例",
        "",
        render_example_table(summary["high_hook_failures"][:8]) if summary["high_hook_failures"] else "- 該当なし",
        "",
        "## 低CTRの失敗例",
        "",
        render_example_table(summary["low_ctr_failures"][:8]) if summary["low_ctr_failures"] else "- 該当なし",
        "",
        "## 高消化金額の失敗例",
        "",
        render_example_table(summary["high_spend_failures"][:8]) if summary["high_spend_failures"] else "- 該当なし",
        "",
        "## 読み方",
        "",
        "- まず `高フックでも外れる型` と `低CTRで止まる型` を分ける",
        "- 次に `同じタイトルの派生が何度も外れていないか` を見る",
        "- そのあとで `LP / ファネル / 製作者` の偏りを読む",
        "- 原因断定は Looker 数値だけでやらず、LP・面談定性・下流売上と重ねる",
        "",
    ])
    return "\n".join(lines).strip() + "\n"


def write_normalized_csv(rows: list[dict[str, Any]]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with NORMALIZED_CSV_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def load_all_rows(input_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(input_dir.glob("*.csv")):
        for raw_row in load_csv_rows(path):
            rows.append(normalize_row(raw_row, path))
    return rows


def run_analysis(input_dir: Path) -> dict[str, Any]:
    rows = load_all_rows(input_dir)
    if not rows:
        raise SystemExit(f"CSVが見つかりません: {input_dir}")
    summary = summarize_patterns(rows)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_normalized_csv(rows)
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    KNOWLEDGE_PATH.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def print_status(input_dir: Path) -> None:
    csv_files = sorted(input_dir.glob("*.csv"))
    summary = json.loads(SUMMARY_JSON_PATH.read_text(encoding="utf-8")) if SUMMARY_JSON_PATH.exists() else {}
    print(json.dumps({
        "input_dir": str(input_dir),
        "csv_files": len(csv_files),
        "latest_csv": csv_files[-1].name if csv_files else "",
        "latest_summary_generated_at": summary.get("generated_at", ""),
        "snapshot_rows": summary.get("snapshot_rows", 0),
        "unique_rows": summary.get("unique_rows", 0),
        "fail_rows": summary.get("fail_rows", 0),
    }, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Meta広告CRダッシュボードCSVを正規化して失敗パターン候補を集計する")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="CSVを読み、正規化・集計・knowledge更新を行う")
    analyze.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)

    status = subparsers.add_parser("status", help="現在の入力状況と集計状況を表示する")
    status.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "analyze"
    input_dir: Path = args.input_dir
    if command == "status":
        print_status(input_dir)
        return
    summary = run_analysis(input_dir)
    print(json.dumps({
        "generated_at": summary["generated_at"],
        "snapshot_files": summary["snapshot_files"],
        "snapshot_rows": summary["snapshot_rows"],
        "unique_rows": summary["unique_rows"],
        "strict_fail_rows": summary["strict_fail_rows"],
        "fail_rows": summary["fail_rows"],
        "knowledge_path": str(KNOWLEDGE_PATH),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
