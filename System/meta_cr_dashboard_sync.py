#!/usr/bin/env python3
"""Meta広告CRの勝ち基準と失敗サンプルを比較し、失敗形を知識化する。"""

from __future__ import annotations

import asyncio
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
DEFAULT_FULL_FAILURE_CSV = DATA_DIR / "full_failure_raw_latest.csv"
CDP_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
CDP_MASTER_TAB = "顧客マスタ"
CDP_DOWNSTREAM_RANGE = "AC2:AU"
DEFAULT_CDP_URL = "http://127.0.0.1:9224"
DEFAULT_LOOKER_PAGE_KEY = "p_i93dt7hmvd"
VIDEO_CACHE_DIR = DATA_DIR / "video_cache"
VIDEO_SIGNAL_SUMMARY_PATH = DATA_DIR / "video_signal_summary.json"
DEFAULT_VIDEO_MODEL = "base"
DEFAULT_VIDEO_CLIP_SECONDS = 45
SUCCESS_JUDGMENTS = {"大当たり", "当たり"}

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

CIRCLED_NUMBER_MAP = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",
}


def collapse_ws(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def get_video_reader():
    import sys

    system_path = str(ROOT_DIR / "System")
    if system_path not in sys.path:
        sys.path.insert(0, system_path)
    from video_reader.video_reader import process_video_url

    return process_video_url


def normalize_opening_number(text: str) -> str:
    normalized = collapse_ws(text)
    for source, target in CIRCLED_NUMBER_MAP.items():
        normalized = normalized.replace(source, target)
    return normalized


def extract_opening_marker(text: str) -> str:
    normalized = normalize_opening_number(text)
    match = re.search(r"冒頭\s*[-_：:]?\s*([0-9]+)", normalized)
    if match:
        return f"冒頭{match.group(1)}"
    if "冒頭" in normalized:
        return collapse_ws(normalized)
    return ""


def strip_opening_marker(text: str) -> str:
    normalized = normalize_opening_number(text)
    cleaned = re.sub(r"冒頭\s*[-_：:]?\s*[0-9]+", "", normalized)
    cleaned = cleaned.replace("【", "").replace("】", "")
    cleaned = re.sub(r"[-_／/]+", " ", cleaned)
    return collapse_ws(cleaned)


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


def extract_month_key(value: Any) -> str:
    text = collapse_ws(value)
    match = re.match(r"(\d{4})/(\d{1,2})/", text)
    if not match:
        return ""
    year = match.group(1)
    month = int(match.group(2))
    return f"{year}/{month:02d}"


def normalize_title_from_ad_name(ad_name: str, creator: str = "") -> str:
    title = "/".join(extract_title_segments(ad_name, creator))
    title = re.sub(r"[＿_]+", " ", title)
    return collapse_ws(title)


def extract_lp_key(ad_name: str) -> str:
    match = re.search(r"(LP\d+)", ad_name or "")
    return match.group(1) if match else ""


def extract_cr_code(text: str) -> str:
    match = re.search(r"(CR\d+)", collapse_ws(text).upper())
    return match.group(1) if match else ""


def extract_title_family(title: str) -> str:
    normalized = collapse_ws(title)
    if not normalized:
        return ""
    family = re.split(r"\s+|with|（|\(", normalized, maxsplit=1)[0]
    return collapse_ws(family)


def extract_opening_key(title_segments: list[str]) -> str:
    for segment in title_segments:
        opening_marker = extract_opening_marker(segment)
        if opening_marker:
            return opening_marker
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
        if re.fullmatch(r"広告ID\d+", normalized):
            continue
        if re.search(r"類似\d|ノンタゲ", normalized):
            continue
        cleaned = strip_opening_marker(normalized)
        if cleaned:
            kept.append(cleaned)
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


VIDEO_BROAD_PATTERNS: dict[str, tuple[str, ...]] = {
    "広い危機訴求": ("このままじゃ", "このままでは", "人生を変", "後悔", "無駄にした"),
    "広い属性呼びかけ": ("会社員", "副業", "初心者", "みんな", "あなた"),
    "著名人/権威": ("堀江", "林社長", "フォロワー", "月1億", "有名"),
    "無料特典": ("無料", "テンプレ", "受け取って", "プレゼント"),
    "強い感情語": ("終わった", "やばい", "ガチ", "絶対"),
}

VIDEO_NARROW_PATTERNS: dict[str, tuple[str, ...]] = {
    "具体数値": ("月収", "万円", "30秒", "38分", "1分"),
    "具体行動": ("LP", "オプトイン", "面談", "予約", "広告費", "CTR", "CPA"),
    "具体対象": ("店舗", "デザイナー", "講師", "フリーランス", "経営者"),
}


def summarize_text_excerpt(text: str, limit: int = 140) -> str:
    normalized = collapse_ws(text)
    if len(normalized) <= limit:
        return normalized
    return normalized[:limit].rstrip() + "…"


def find_marker_hits(text: str, patterns: dict[str, tuple[str, ...]]) -> list[str]:
    normalized = collapse_ws(text)
    hits: list[str] = []
    for label, words in patterns.items():
        if any(word in normalized for word in words):
            hits.append(label)
    return hits


def classify_audience_scope(broad_hits: list[str], narrow_hits: list[str]) -> str:
    if len(broad_hits) >= 2 and len(narrow_hits) == 0:
        return "広い"
    if len(narrow_hits) >= 2 and len(broad_hits) == 0:
        return "狭い"
    if len(broad_hits) > len(narrow_hits):
        return "やや広い"
    if len(narrow_hits) > len(broad_hits):
        return "やや狭い"
    return "混合"


def build_video_signal_record(row: dict[str, Any], transcript_text: str, duration: int, max_seconds: int | None) -> dict[str, Any]:
    opening_excerpt = summarize_text_excerpt(transcript_text, limit=160)
    broad_hits = find_marker_hits(opening_excerpt, VIDEO_BROAD_PATTERNS)
    narrow_hits = find_marker_hits(opening_excerpt, VIDEO_NARROW_PATTERNS)
    return {
        "asset_key": row.get("asset_key", ""),
        "ad_name": row.get("ad_name", ""),
        "title_core": row.get("title_core", ""),
        "theme_key": row.get("theme_key", ""),
        "opening_key": row.get("opening_key", ""),
        "lp_key": row.get("lp_key", ""),
        "created_on": row.get("created_on", ""),
        "failure_bucket": row.get("failure_bucket", ""),
        "distribution_hint": row.get("distribution_hint", ""),
        "spend": row.get("spend"),
        "ctr": row.get("ctr"),
        "cpa": row.get("cpa"),
        "hook_rate": row.get("hook_rate"),
        "video_url": row.get("video_url", ""),
        "duration": duration,
        "clip_seconds": max_seconds or duration,
        "opening_excerpt": opening_excerpt,
        "broad_hits": broad_hits,
        "narrow_hits": narrow_hits,
        "audience_scope": classify_audience_scope(broad_hits, narrow_hits),
    }


def row_sort_key(row: dict[str, Any]) -> tuple[float, float, float]:
    spend = float(row.get("spend") or 0.0)
    ctr = float(row.get("ctr") or 0.0)
    cpa = float(row.get("cpa") or 0.0)
    return (spend, ctr, cpa)


def select_video_rows(rows: list[dict[str, Any]], limit: int, bucket: str = "") -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_assets: set[str] = set()
    filtered = rows
    if bucket:
        filtered = [row for row in rows if row.get("failure_bucket") == bucket]
    ordered = sorted(filtered, key=row_sort_key, reverse=True)
    for row in ordered:
        asset_key = collapse_ws(row.get("asset_key"))
        video_url = collapse_ws(row.get("video_url"))
        if not asset_key or not video_url or asset_key == "データなし" or video_url == "データなし":
            continue
        if asset_key in seen_assets:
            continue
        selected.append(row)
        seen_assets.add(asset_key)
        if len(selected) >= limit:
            break
    return selected


def normalize_failure_bucket_label(label: str) -> str:
    mapping = {
        "最初で止まる": "フックで離脱",
        "見られるが押されない": "見られるがクリックされない",
        "押されるが集客単価が重い": "クリックされるがCPAが高い",
        "上流は通るが後ろで失敗": "CTRとフック率は通るがオプトイン以降で失敗",
    }
    return mapping.get(label, label)


def render_video_scope_summary(summary: dict[str, Any]) -> str:
    rows = [
        "| failure bucket | transcribed assets | broad/やや広い | 混合 | narrow/やや狭い |",
        "|---|---:|---:|---:|---:|",
    ]
    for bucket in summary.get("bucket_scope_counts", []):
        rows.append(
            "| {bucket} | {count} | {broad} | {mixed} | {narrow} |".format(
                bucket=normalize_failure_bucket_label(bucket["failure_bucket"]),
                count=bucket["count"],
                broad=bucket["broad_like"],
                mixed=bucket["mixed"],
                narrow=bucket["narrow_like"],
            )
        )
    return "\n".join(rows)


def render_video_marker_summary(summary: dict[str, Any]) -> str:
    rows = [
        "| broad marker | count |",
        "|---|---:|",
    ]
    for record in summary.get("broad_marker_counts", []):
        rows.append(f"| {record['label']} | {record['count']} |")
    return "\n".join(rows)


def render_video_examples(records: list[dict[str, Any]]) -> str:
    lines = [
        "| 広告名 | failure bucket | 冒頭抜粋 | broad markers | audience scope | CTR | CPA |",
        "|---|---|---|---|---|---:|---:|",
    ]
    for record in records:
        lines.append(
            "| {ad} | {bucket} | {excerpt} | {markers} | {scope} | {ctr} | {cpa} |".format(
                ad=record.get("ad_name", ""),
                bucket=normalize_failure_bucket_label(record.get("failure_bucket", "-")),
                excerpt=record.get("opening_excerpt", "-"),
                markers=", ".join(record.get("broad_hits", [])) or "-",
                scope=record.get("audience_scope", "-"),
                ctr=format_percent(record.get("ctr")),
                cpa=format_yen(record.get("cpa")),
            )
        )
    return "\n".join(lines)

def parse_iso_date(text: str) -> tuple[int, int, int]:
    parts = text.split("-")
    if len(parts) != 3:
        raise SystemExit(f"日付は YYYY-MM-DD 形式で指定してください: {text}")
    year, month, day = (int(part) for part in parts)
    return year, month, day


async def capture_full_failure_raw(
    cdp_url: str,
    page_key: str,
    date_start: str,
    output_path: Path,
) -> dict[str, Any]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise SystemExit(f"playwright が必要です: {exc}") from exc

    menu_labels = ["グラフのメニューを表示", "グラフをエクスポート", "データのエクスポート"]
    open_script = """(label) => {
      const nodes = [...document.querySelectorAll('[aria-label],[title],button,[role="button"],div[role="button"],li,[role="menuitem"],[role="option"]')];
      const target = nodes.find(el => {
        const fields = [(el.innerText||'').trim(), (el.getAttribute('aria-label')||'').trim(), (el.getAttribute('title')||'').trim()].filter(Boolean);
        return fields.some(field => field === label || field.startsWith(label));
      });
      if (!target) return 'not_found';
      target.click();
      return 'ok';
    }"""

    year, month, day = parse_iso_date(date_start)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(cdp_url)
        page = None
        for context in browser.contexts:
            for candidate in context.pages:
                if page_key in candidate.url and "/u/0/" in candidate.url:
                    page = candidate
                    break
            if page:
                break
        if not page:
            raise SystemExit(
                f"認証済みの Looker Studio タブが見つかりませんでした: page_key={page_key}"
            )

        await page.bring_to_front()
        await page.wait_for_timeout(1000)
        await page.evaluate(
            """() => {
              const btn = document.querySelector('button.canvas-date-input');
              if (!btn) return 'date_button_not_found';
              btn.click();
              return 'ok';
            }"""
        )
        await page.wait_for_timeout(800)
        await page.evaluate(
            """() => {
              const startRoot = document.querySelector('.start-date-picker') || document;
              const period = startRoot.querySelector('button.mat-calendar-period-button');
              if (!period) return 'period_not_found';
              period.click();
              return 'period_clicked';
            }"""
        )
        await page.wait_for_timeout(400)
        year_result = await page.evaluate(
            """(yearText) => {
              const root = document.querySelector('.start-date-picker') || document;
              const btn = [...root.querySelectorAll('button')].find(el => (el.innerText || '').trim() === yearText);
              if (!btn) return 'year_not_found';
              btn.click();
              return 'year_clicked';
            }""",
            str(year),
        )
        if year_result != "year_clicked":
            raise SystemExit(f"開始年の選択に失敗しました: {year_result}")
        await page.wait_for_timeout(400)
        month_result = await page.evaluate(
            """(monthText) => {
              const root = document.querySelector('.start-date-picker') || document;
              const btn = [...root.querySelectorAll('button')].find(el => (el.innerText || '').trim() === monthText);
              if (!btn) return 'month_not_found';
              btn.click();
              return 'month_clicked';
            }""",
            f"{month}月",
        )
        if month_result != "month_clicked":
            raise SystemExit(f"開始月の選択に失敗しました: {month_result}")
        await page.wait_for_timeout(400)
        day_result = await page.evaluate(
            """(label) => {
              const root = document.querySelector('.start-date-picker') || document;
              const btn = root.querySelector(`button[aria-label="${label}"]`);
              if (!btn) return 'day_not_found';
              btn.click();
              return 'day_clicked';
            }""",
            f"{year}年{month}月{day}日",
        )
        if day_result != "day_clicked":
            raise SystemExit(f"開始日の選択に失敗しました: {day_result}")
        await page.wait_for_timeout(400)
        apply_result = await page.evaluate(
            """() => {
              const btn = [...document.querySelectorAll('button')].find(el => (el.innerText || '').trim() === '適用');
              if (!btn) return 'apply_not_found';
              btn.click();
              return 'apply_clicked';
            }"""
        )
        if apply_result != "apply_clicked":
            raise SystemExit(f"日付適用に失敗しました: {apply_result}")
        await page.wait_for_timeout(5000)

        for label in menu_labels:
            result = await page.evaluate(open_script, label)
            if result != "ok":
                raise SystemExit(f"エクスポートメニューの操作に失敗しました: {label} -> {result}")
            await page.wait_for_timeout(800)

        export_button = page.get_by_role("button", name="エクスポート").last
        async with page.expect_download(timeout=180000) as download_info:
            await export_button.click(force=True)
        download = await download_info.value
        if output_path.exists():
            output_path.unlink()
        await download.save_as(str(output_path))
        await browser.close()

    with output_path.open("r", encoding="utf-8-sig", newline="") as fh:
        row_count = sum(1 for _ in fh) - 1
    return {
        "output_path": str(output_path),
        "row_count": row_count,
        "date_start": date_start,
        "page_key": page_key,
    }


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
            if cr_judgment in SUCCESS_JUDGMENTS:
                continue
            creator = collapse_ws(raw.get("製作者"))
            title_segments = extract_title_segments(ad_name, creator)
            title_core = normalize_title_from_ad_name(ad_name, creator)
            video_url = collapse_ws(raw.get("動画URL"))
            thumbnail_url = collapse_ws(raw.get("サムネイル"))
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
                    "video_url": video_url,
                    "thumbnail_url": thumbnail_url,
                    "asset_key": video_url if video_url and video_url != "データなし" else thumbnail_url,
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
    scope_note = f"{path.name} から非勝ち {len(rows)}件を読み込み"
    return rows, scope_note


def load_positive_rows_from_csv(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for raw in reader:
            ad_name = collapse_ws(raw.get("広告名"))
            if not ad_name:
                continue
            cr_judgment = collapse_ws(raw.get("CR判定"))
            if cr_judgment not in SUCCESS_JUDGMENTS:
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
                    "cr_judgment": cr_judgment,
                    "ctr": parse_rate(raw.get("CTR"), decimal_ratio=True),
                    "hook_rate": parse_rate(raw.get("フック率（3秒間視聴）"), decimal_ratio=True),
                    "cpa": parse_currency(raw.get("CPA")),
                }
            )
    return rows


def summarize_mixed_exact_crs(
    positive_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    positive_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    failure_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in positive_rows:
        name = collapse_ws(row.get("ad_name"))
        if name:
            positive_by_name[name].append(row)
    for row in failure_rows:
        name = collapse_ws(row.get("ad_name"))
        if name:
            failure_by_name[name].append(row)

    mixed_rows: list[dict[str, Any]] = []
    for name in sorted(set(positive_by_name) & set(failure_by_name)):
        pos = positive_by_name[name]
        neg = failure_by_name[name]
        pos_ctrs = [row.get("ctr") for row in pos if row.get("ctr") is not None]
        neg_ctrs = [row.get("ctr") for row in neg if row.get("ctr") is not None]
        pos_cpas = [row.get("cpa") for row in pos if row.get("cpa") is not None]
        neg_cpas = [row.get("cpa") for row in neg if row.get("cpa") is not None]
        mixed_rows.append(
            {
                "ad_name": name,
                "positive_count": len(pos),
                "failure_count": len(neg),
                "lp_keys": sorted({row.get("lp_key", "") for row in pos + neg if row.get("lp_key")}),
                "positive_ctr_median": statistics.median(pos_ctrs) if pos_ctrs else None,
                "failure_ctr_median": statistics.median(neg_ctrs) if neg_ctrs else None,
                "positive_cpa_median": statistics.median(pos_cpas) if pos_cpas else None,
                "failure_cpa_median": statistics.median(neg_cpas) if neg_cpas else None,
                "read": "完全同一CRで勝ち負け混在。まず運用差を疑う。",
            }
        )
    mixed_rows.sort(key=lambda row: (row["positive_count"] + row["failure_count"], row["failure_count"]), reverse=True)
    return mixed_rows[:limit]


def summarize_family_month_context(
    positive_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    limit: int = 18,
) -> list[dict[str, Any]]:
    family_totals: Counter[str] = Counter()
    family_positive: Counter[str] = Counter()
    buckets: dict[tuple[str, str], dict[str, Any]] = defaultdict(
        lambda: {"positive_count": 0, "failure_count": 0, "ctr_values": [], "cpa_values": [], "stage": Counter()}
    )

    for row in positive_rows:
        family = collapse_ws(row.get("title_family"))
        month_key = extract_month_key(row.get("created_on"))
        if not family or not month_key:
            continue
        family_totals[family] += 1
        family_positive[family] += 1
        bucket = buckets[(family, month_key)]
        bucket["positive_count"] += 1
        if row.get("ctr") is not None:
            bucket["ctr_values"].append(row["ctr"])
        if row.get("cpa") is not None:
            bucket["cpa_values"].append(row["cpa"])

    for row in failure_rows:
        family = collapse_ws(row.get("title_family"))
        month_key = extract_month_key(row.get("created_on"))
        if not family or not month_key:
            continue
        family_totals[family] += 1
        bucket = buckets[(family, month_key)]
        bucket["failure_count"] += 1
        if row.get("failure_bucket"):
            bucket["stage"][row["failure_bucket"]] += 1
        if row.get("ctr") is not None:
            bucket["ctr_values"].append(row["ctr"])
        if row.get("cpa") is not None:
            bucket["cpa_values"].append(row["cpa"])

    focus_families = [
        family
        for family, total in family_totals.most_common()
        if total >= 20 and family_positive.get(family, 0) > 0
    ][:6]

    rows: list[dict[str, Any]] = []
    for family in focus_families:
        family_rows = []
        for (bucket_family, month_key), bucket in buckets.items():
            if bucket_family != family:
                continue
            total_count = bucket["positive_count"] + bucket["failure_count"]
            if total_count < 5:
                continue
            month = int(month_key.split("/")[1])
            if month in {11, 12, 1}:
                read = "年末年始の空気や自己評価タイミング、市場の関心上昇を重ねて読む。"
            else:
                read = "その月の市場背景、トレンド、既視感の有無を重ねて読む。"
            family_rows.append(
                {
                    "family": family,
                    "month_key": month_key,
                    "positive_count": bucket["positive_count"],
                    "failure_count": bucket["failure_count"],
                    "total_count": total_count,
                    "top_stage_name": bucket["stage"].most_common(1)[0][0] if bucket["stage"] else "",
                    "top_stage_count": bucket["stage"].most_common(1)[0][1] if bucket["stage"] else 0,
                    "ctr_median": statistics.median(bucket["ctr_values"]) if bucket["ctr_values"] else None,
                    "cpa_median": statistics.median(bucket["cpa_values"]) if bucket["cpa_values"] else None,
                    "read": read,
                }
            )
        family_rows.sort(key=lambda row: (row["total_count"], row["positive_count"]), reverse=True)
        chosen: list[dict[str, Any]] = []
        seen_stages: set[str] = set()
        for row in family_rows:
            stage_name = row.get("top_stage_name") or ""
            if stage_name and stage_name not in seen_stages:
                chosen.append(row)
                seen_stages.add(stage_name)
            if len(chosen) >= 3:
                break
        if len(chosen) < 3:
            for row in family_rows:
                if row not in chosen:
                    chosen.append(row)
                if len(chosen) >= 3:
                    break
        chosen.sort(key=lambda row: row["month_key"])
        rows.extend(chosen)

    rows.sort(key=lambda row: (row["family"], row["month_key"]), reverse=False)
    return rows[:limit]


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
            "フックで離脱",
            "CTRとフック率がどちらも勝ちCRの下位25%基準を下回っていて、フックで離脱している。",
            "strong",
        )

    if ctr is not None and ctr < benchmarks["winner_ctr_p25"]:
        return (
            "見られるがクリックされない",
            "フック率は出ても CTR が勝ちCRの下位25%基準を下回っていて、クリックまで届かない。",
            "strong" if hook is not None else "medium",
        )

    if cpa is not None and cpa > benchmarks["winner_cpa_p75"]:
        return (
            "クリックされるがCPAが高い",
            "CTR は出るが CPA が勝ちCRの上位25%基準を上回っていて、オプトイン率かターゲット層の質で崩れている。",
            "strong",
        )

    return (
        "CTRとフック率は通るがオプトイン以降で失敗",
        "CTR とフック率は勝ち基準帯にある。CR単体より LP・オファー・導線・ターゲット層を先に疑う。",
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


def summarize_family_bucket_profiles(
    failure_rows: list[dict[str, Any]],
    limit: int = 6,
) -> list[dict[str, Any]]:
    by_family: dict[str, Counter] = defaultdict(Counter)
    for row in failure_rows:
        family = collapse_ws(row.get("title_family"))
        bucket = row.get("failure_bucket")
        if not family or not bucket:
            continue
        by_family[family]["total"] += 1
        by_family[family][bucket] += 1

    rows: list[dict[str, Any]] = []
    for family, counter in sorted(by_family.items(), key=lambda item: item[1]["total"], reverse=True):
        total = counter["total"]
        if total < 50:
            continue
        top_buckets = [(name, count) for name, count in counter.items() if name != "total"]
        top_buckets.sort(key=lambda item: item[1], reverse=True)
        primary_name, primary_count = top_buckets[0]
        secondary_name, secondary_count = top_buckets[1] if len(top_buckets) > 1 else ("-", 0)

        if primary_name == "見られるがクリックされない":
            read = "フック率は残るが、CTRが伸びずクリックに届いていない。"
        elif primary_name == "フックで離脱":
            read = "冒頭の新規性や対象ワードが弱く、フックで離脱している。"
        elif primary_name == "クリックされるがCPAが高い":
            read = "クリックは取れているので、オプトイン率かターゲット層の質を疑う。"
        elif secondary_count and (primary_count - secondary_count) / total <= 0.08:
            read = "崩れ方が二極化していて、単一原因で見ない方がいい。"
        else:
            read = "CTRとフック率は通るので、CR単体より LP・オファー・導線・ターゲット層を先に疑う。"

        rows.append(
            {
                "family": family,
                "total": total,
                "primary_bucket": primary_name,
                "primary_share": primary_count / total * 100,
                "secondary_bucket": secondary_name,
                "secondary_share": secondary_count / total * 100 if secondary_count else 0.0,
                "read": read,
            }
        )
    return rows[:limit]


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


def backfill_video_signals(
    rows: list[dict[str, Any]],
    *,
    limit: int,
    bucket: str,
    whisper_model: str,
    max_seconds: int,
) -> dict[str, Any]:
    process_video_url = get_video_reader()
    VIDEO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    selected_rows = select_video_rows(rows, limit=limit, bucket=bucket)
    processed: list[dict[str, Any]] = []
    reused = 0
    error_records: list[dict[str, Any]] = []
    reused_errors = 0
    for row in selected_rows:
        asset_key = collapse_ws(row.get("asset_key"))
        cache_dir = VIDEO_CACHE_DIR / re.sub(r"[^A-Za-z0-9._-]+", "_", asset_key)[:120]
        signal_path = cache_dir / "signal.json"
        error_path = cache_dir / "error.json"
        if signal_path.exists():
            processed.append(json.loads(signal_path.read_text(encoding="utf-8")))
            reused += 1
            continue
        if error_path.exists():
            error_records.append(json.loads(error_path.read_text(encoding="utf-8")))
            reused_errors += 1
            continue

        cache_dir.mkdir(parents=True, exist_ok=True)
        try:
            result = process_video_url(
                row.get("video_url", ""),
                out_dir=cache_dir,
                no_frames=True,
                whisper_model=whisper_model,
                max_seconds=max_seconds,
                title_hint=row.get("ad_name", ""),
            )
            transcript_text = collapse_ws(result.get("transcript_text", ""))
            signal = build_video_signal_record(
                row,
                transcript_text,
                int(result.get("duration") or 0),
                max_seconds,
            )
            signal_path.write_text(json.dumps(signal, ensure_ascii=False, indent=2), encoding="utf-8")
            processed.append(signal)
        except Exception as exc:
            error_record = {
                "asset_key": asset_key,
                "ad_name": row.get("ad_name", ""),
                "video_url": row.get("video_url", ""),
                "failure_bucket": row.get("failure_bucket", ""),
                "error_type": exc.__class__.__name__,
                "error_message": collapse_ws(str(exc))[:500],
                "recorded_at": datetime.now().isoformat(timespec="seconds"),
            }
            error_path.write_text(json.dumps(error_record, ensure_ascii=False, indent=2), encoding="utf-8")
            error_records.append(error_record)

    scope_buckets: defaultdict[str, Counter] = defaultdict(Counter)
    marker_counter: Counter[str] = Counter()
    for record in processed:
        scope = record.get("audience_scope", "混合")
        bucket_name = record.get("failure_bucket") or "未分類"
        marker_counter.update(record.get("broad_hits", []))
        if scope in {"広い", "やや広い"}:
            scope_buckets[bucket_name]["broad_like"] += 1
        elif scope in {"狭い", "やや狭い"}:
            scope_buckets[bucket_name]["narrow_like"] += 1
        else:
            scope_buckets[bucket_name]["mixed"] += 1
        scope_buckets[bucket_name]["count"] += 1

    bucket_scope_counts = [
        {
            "failure_bucket": bucket_name,
            "count": counter.get("count", 0),
            "broad_like": counter.get("broad_like", 0),
            "mixed": counter.get("mixed", 0),
            "narrow_like": counter.get("narrow_like", 0),
        }
        for bucket_name, counter in sorted(scope_buckets.items(), key=lambda item: item[1].get("count", 0), reverse=True)
    ]

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "bucket_filter": bucket,
        "requested_limit": limit,
        "processed_count": len(processed),
        "reused_count": reused,
        "error_count": len(error_records),
        "reused_error_count": reused_errors,
        "video_cache_dir": str(VIDEO_CACHE_DIR),
        "bucket_scope_counts": bucket_scope_counts,
        "broad_marker_counts": [
            {"label": label, "count": count}
            for label, count in marker_counter.most_common()
        ],
        "top_errors": error_records[:10],
        "top_examples": sorted(
            processed,
            key=lambda record: (
                len(record.get("broad_hits", [])),
                float(record.get("spend") or 0.0),
                float(record.get("ctr") or 0.0),
            ),
            reverse=True,
        )[:10],
    }
    VIDEO_SIGNAL_SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


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
        return "オーディエンスや配信条件の差が大きい可能性が高い"
    if len(lp_keys) >= 2:
        return "LPとオファーの期待値ズレを先に疑う"
    if len(dates) >= 2:
        return "配信時期差や既視感の蓄積を疑う"
    return "同一アセットでも広告セット・学習状態・配信面でブレる"


def summarize_same_asset_variation(source_rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        asset_key = collapse_ws(row.get("asset_key"))
        if asset_key and asset_key != "データなし":
            groups[asset_key].append(row)

    multi_groups = [group_rows for group_rows in groups.values() if len(group_rows) >= 2]

    exact_context_examples: list[dict[str, Any]] = []
    exact_context_groups: defaultdict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        asset_key = collapse_ws(row.get("asset_key"))
        if not asset_key or asset_key == "データなし":
            continue
        exact_context_groups[(asset_key, row.get("created_on", ""), row.get("lp_key", ""))].append(row)
    for group_rows in exact_context_groups.values():
        if len(group_rows) < 2:
            continue
        ctrs = [row["ctr"] for row in group_rows if row.get("ctr") is not None]
        cpas = [row["cpa"] for row in group_rows if row.get("cpa") is not None]
        exact_context_examples.append(
            {
                "count": len(group_rows),
                "created_on": group_rows[0].get("created_on", ""),
                "lp_key": group_rows[0].get("lp_key", ""),
                "ctr_spread": (max(ctrs) - min(ctrs)) if len(ctrs) >= 2 else 0.0,
                "cpa_spread": (max(cpas) - min(cpas)) if len(cpas) >= 2 else 0.0,
                "context_hint": build_context_hint(group_rows),
                "rows": group_rows,
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
    for group_rows in multi_groups:
        lp_keys = sorted({row.get("lp_key") for row in group_rows if row.get("lp_key")})
        if len(lp_keys) < 2:
            continue
        ctrs = [row["ctr"] for row in group_rows if row.get("ctr") is not None]
        cpas = [row["cpa"] for row in group_rows if row.get("cpa") is not None]
        cross_lp_examples.append(
            {
                "count": len(group_rows),
                "lp_keys": lp_keys,
                "ctr_spread": (max(ctrs) - min(ctrs)) if len(ctrs) >= 2 else 0.0,
                "cpa_spread": (max(cpas) - min(cpas)) if len(cpas) >= 2 else 0.0,
                "context_hint": build_context_hint(group_rows),
                "rows": group_rows,
            }
        )
    cross_lp_examples.sort(key=lambda item: (item["cpa_spread"], item["ctr_spread"], item["count"]), reverse=True)

    theme_groups: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        theme_key = collapse_ws(row.get("theme_key"))
        if theme_key:
            theme_groups[theme_key].append(row)

    opening_examples: list[dict[str, Any]] = []
    for theme_key, theme_rows in theme_groups.items():
        if not is_meaningful_theme(theme_key):
            continue
        openings = sorted({row.get("opening_key") for row in theme_rows if row.get("opening_key")})
        if len(openings) < 2:
            continue
        by_opening: list[dict[str, Any]] = []
        for opening_key in openings:
            subset = [row for row in theme_rows if row.get("opening_key") == opening_key]
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
        meaningful_openings = [record for record in by_opening if record.get("count", 0) >= 2]
        if len(meaningful_openings) < 2:
            continue
        cpa_values = [record["cpa_median"] for record in meaningful_openings if record.get("cpa_median") is not None]
        ctr_values = [record["ctr_median"] for record in meaningful_openings if record.get("ctr_median") is not None]
        opening_examples.append(
            {
                "theme_key": theme_key,
                "count": len(theme_rows),
                "cpa_spread": (max(cpa_values) - min(cpa_values)) if len(cpa_values) >= 2 else 0.0,
                "ctr_spread": (max(ctr_values) - min(ctr_values)) if len(ctr_values) >= 2 else 0.0,
                "openings": meaningful_openings,
            }
        )
    opening_examples.sort(key=lambda item: (item["count"], item["cpa_spread"], item["ctr_spread"]), reverse=True)

    return {
        "same_asset_groups_ge_2": len(multi_groups),
        "rows_in_same_asset_groups": sum(len(group_rows) for group_rows in multi_groups),
        "rows_in_same_asset_same_context_groups": sum(len(group_rows) for group_rows in exact_context_groups.values() if len(group_rows) >= 2),
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


def load_cdp_downstream_by_cr_code() -> dict[str, Any]:
    import sys

    system_path = str(ROOT_DIR / "System")
    if system_path not in sys.path:
        sys.path.insert(0, system_path)
    from sheets_manager import get_client

    sheet = get_client().open_by_key(CDP_SHEET_ID)
    ws = sheet.worksheet(CDP_MASTER_TAB)
    values = ws.get(CDP_DOWNSTREAM_RANGE)
    if not values:
        return {"generated_at": datetime.now().isoformat(timespec="seconds"), "rows_with_cr_code": 0, "codes": {}}

    headers = values[0]
    rows = values[1:]
    idx = {header: i for i, header in enumerate(headers)}

    by_code: dict[str, dict[str, Any]] = {}
    rows_with_cr_code = 0
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        cr_code = extract_cr_code(padded[idx["CR名"]]) if "CR名" in idx else ""
        if not cr_code:
            continue
        rows_with_cr_code += 1
        record = by_code.setdefault(
            cr_code,
            {
                "customer_rows": 0,
                "buyer_rows": 0,
                "total_sales": 0.0,
                "total_refunds": 0.0,
                "total_ltv": 0.0,
                "ltv_values": [],
            },
        )
        record["customer_rows"] += 1

        first_purchase_date = collapse_ws(padded[idx["初回購入日"]]) if "初回購入日" in idx else ""
        purchase_count = parse_int(padded[idx["累計購入回数"]]) if "累計購入回数" in idx else None
        sales = parse_currency(padded[idx["着金売上"]]) if "着金売上" in idx else None
        refunds = parse_currency(padded[idx["返金額"]]) if "返金額" in idx else None
        ltv = parse_currency(padded[idx["LTV"]]) if "LTV" in idx else None

        if first_purchase_date or (purchase_count is not None and purchase_count > 0) or (sales is not None and sales > 0):
            record["buyer_rows"] += 1
        if sales is not None:
            record["total_sales"] += sales
        if refunds is not None:
            record["total_refunds"] += refunds
        if ltv is not None:
            record["total_ltv"] += ltv
            record["ltv_values"].append(ltv)

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rows_with_cr_code": rows_with_cr_code,
        "codes": by_code,
    }


def summarize_cdp_downstream(
    positive_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    cdp_summary = load_cdp_downstream_by_cr_code()
    cdp_codes: dict[str, dict[str, Any]] = cdp_summary["codes"]

    raw_code_summary: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "lp_keys": set(),
            "positive_count": 0,
            "failure_count": 0,
            "failure_buckets": Counter(),
        }
    )

    for row in positive_rows:
        code = extract_cr_code(row.get("ad_name", ""))
        if not code:
            continue
        raw_code_summary[code]["positive_count"] += 1
        lp_key = collapse_ws(row.get("lp_key"))
        if lp_key:
            raw_code_summary[code]["lp_keys"].add(lp_key)

    for row in failure_rows:
        code = extract_cr_code(row.get("ad_name", ""))
        if not code:
            continue
        raw_code_summary[code]["failure_count"] += 1
        lp_key = collapse_ws(row.get("lp_key"))
        if lp_key:
            raw_code_summary[code]["lp_keys"].add(lp_key)
        bucket = collapse_ws(row.get("failure_bucket"))
        if bucket:
            raw_code_summary[code]["failure_buckets"][bucket] += 1

    matched_codes = sorted(set(cdp_codes) & set(raw_code_summary))

    bucket_rollup: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "cr_codes": set(),
            "customer_rows": 0,
            "buyer_rows": 0,
            "total_sales": 0.0,
            "total_refunds": 0.0,
            "total_ltv": 0.0,
            "ltv_values": [],
        }
    )
    lp_rollup: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "cr_codes": set(),
            "customer_rows": 0,
            "buyer_rows": 0,
            "total_sales": 0.0,
            "total_refunds": 0.0,
            "total_ltv": 0.0,
            "ltv_values": [],
        }
    )

    matched_customer_rows = 0
    matched_buyer_rows = 0
    matched_ltv_values: list[float] = []
    single_lp_codes = 0
    ambiguous_lp_codes = 0

    for code in matched_codes:
        cdp_record = cdp_codes[code]
        raw_record = raw_code_summary[code]
        matched_customer_rows += cdp_record["customer_rows"]
        matched_buyer_rows += cdp_record["buyer_rows"]
        matched_ltv_values.extend(cdp_record["ltv_values"])

        failure_buckets = raw_record["failure_buckets"]
        if failure_buckets:
            bucket = failure_buckets.most_common(1)[0][0]
            target = bucket_rollup[bucket]
            target["cr_codes"].add(code)
            target["customer_rows"] += cdp_record["customer_rows"]
            target["buyer_rows"] += cdp_record["buyer_rows"]
            target["total_sales"] += cdp_record["total_sales"]
            target["total_refunds"] += cdp_record["total_refunds"]
            target["total_ltv"] += cdp_record["total_ltv"]
            target["ltv_values"].extend(cdp_record["ltv_values"])

        lp_keys = {lp for lp in raw_record["lp_keys"] if lp}
        if len(lp_keys) == 1:
            single_lp_codes += 1
            lp_key = next(iter(lp_keys))
            target = lp_rollup[lp_key]
            target["cr_codes"].add(code)
            target["customer_rows"] += cdp_record["customer_rows"]
            target["buyer_rows"] += cdp_record["buyer_rows"]
            target["total_sales"] += cdp_record["total_sales"]
            target["total_refunds"] += cdp_record["total_refunds"]
            target["total_ltv"] += cdp_record["total_ltv"]
            target["ltv_values"].extend(cdp_record["ltv_values"])
        elif len(lp_keys) >= 2:
            ambiguous_lp_codes += 1

    def finalize_rollup(source: dict[str, dict[str, Any]], key_name: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for key, record in source.items():
            ltv_values = record["ltv_values"]
            rows.append(
                {
                    key_name: key,
                    "cr_code_count": len(record["cr_codes"]),
                    "customer_rows": record["customer_rows"],
                    "buyer_rows": record["buyer_rows"],
                    "total_sales": record["total_sales"],
                    "total_refunds": record["total_refunds"],
                    "total_ltv": record["total_ltv"],
                    "buyer_rate": (record["buyer_rows"] / record["customer_rows"] * 100) if record["customer_rows"] else None,
                    "ltv_per_customer": (record["total_ltv"] / record["customer_rows"]) if record["customer_rows"] else None,
                    "refund_rate": (record["total_refunds"] / record["total_sales"] * 100) if record["total_sales"] else None,
                    "ltv_median": statistics.median(ltv_values) if ltv_values else None,
                }
            )
        rows.sort(key=lambda row: (row["total_ltv"], row["customer_rows"]), reverse=True)
        return rows

    return {
        "generated_at": cdp_summary["generated_at"],
        "cdp_rows_with_cr_code": cdp_summary["rows_with_cr_code"],
        "cdp_unique_cr_codes": len(cdp_codes),
        "raw_unique_cr_codes": len(raw_code_summary),
        "matched_cr_codes": len(matched_codes),
        "matched_customer_rows": matched_customer_rows,
        "matched_buyer_rows": matched_buyer_rows,
        "matched_ltv_median": statistics.median(matched_ltv_values) if matched_ltv_values else None,
        "single_lp_codes": single_lp_codes,
        "ambiguous_lp_codes": ambiguous_lp_codes,
        "bucket_rows": finalize_rollup(bucket_rollup, "failure_bucket"),
        "lp_rows": finalize_rollup(lp_rollup, "lp_key"),
    }


def summarize_patterns(
    winner_rows: list[dict[str, Any]],
    failure_rows: list[dict[str, Any]],
    positive_rows: list[dict[str, Any]],
    scope_note: str,
    failure_source: Path,
    failure_mode: str,
) -> dict[str, Any]:
    benchmarks = build_benchmarks(winner_rows)
    enriched_failures = enrich_failures(failure_rows, benchmarks)
    winner_same_asset_summary = summarize_same_asset_variation(winner_rows)
    failure_same_asset_summary = summarize_same_asset_variation(failure_rows)
    cdp_downstream_summary = summarize_cdp_downstream(positive_rows, enriched_failures)

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
        "failure_source": str(failure_source),
        "failure_mode": failure_mode,
        "failure_scope_note": scope_note,
        "winner_count": len(winner_rows),
        "positive_count": len(positive_rows),
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
        "family_signals": family_signal_rows(positive_rows, failure_rows),
        "family_bucket_profiles": summarize_family_bucket_profiles(enriched_failures),
        "mixed_exact_crs": summarize_mixed_exact_crs(positive_rows, failure_rows),
        "family_month_contexts": summarize_family_month_context(positive_rows, enriched_failures),
        "winner_same_asset_summary": winner_same_asset_summary,
        "failure_same_asset_summary": failure_same_asset_summary,
        "cdp_downstream_summary": cdp_downstream_summary,
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


def render_stage_definition_table(benchmarks: dict[str, float]) -> str:
    return "\n".join(
        [
            "| 失敗形 | 判定基準 |",
            "|---|---|",
            f"| フックで離脱 | CTR < {benchmarks['winner_ctr_p25']:.2f}% かつ フック率 < {benchmarks['winner_hook_p25']:.2f}% |",
            f"| 見られるがクリックされない | CTR < {benchmarks['winner_ctr_p25']:.2f}% |",
            f"| クリックされるがCPAが高い | CPA > {format_yen(benchmarks['winner_cpa_p75'])} |",
            "| CTRとフック率は通るがオプトイン以降で失敗 | 上記3条件に入らない非勝ちCR |",
        ]
    )


def render_cdp_join_table(summary: dict[str, Any]) -> str:
    rows = [
        ("CDP側の顧客行（CRコードあり）", f"{summary['cdp_rows_with_cr_code']:,}"),
        ("CDP側のユニークCRコード", f"{summary['cdp_unique_cr_codes']:,}"),
        ("Meta raw側のユニークCRコード", f"{summary['raw_unique_cr_codes']:,}"),
        ("結線できたCRコード", f"{summary['matched_cr_codes']:,}"),
        ("結線できた顧客行", f"{summary['matched_customer_rows']:,}"),
        ("結線できた購入者行", f"{summary['matched_buyer_rows']:,}"),
        ("LPを一意に解けたCRコード", f"{summary['single_lp_codes']:,}"),
        ("LPが複数にまたがるCRコード", f"{summary['ambiguous_lp_codes']:,}"),
        ("結線行のLTV中央値", format_yen(summary.get("matched_ltv_median"))),
    ]
    lines = ["| 項目 | 数値 |", "|---|---:|"]
    for label, value in rows:
        lines.append(f"| {label} | {value} |")
    return "\n".join(lines)


def render_downstream_rollup(rows: list[dict[str, Any]], key_name: str, key_label: str) -> str:
    lines = [
        f"| {key_label} | CRコード数 | 顧客行 | 購入者行 | 購入者率 | 着金売上 | 返金額 | 返金率 | 顧客あたりLTV | LTV中央値 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {key} | {codes} | {customers} | {buyers} | {buyer_rate} | {sales} | {refunds} | {refund_rate} | {ltv_per_customer} | {ltv_median} |".format(
                key=row[key_name],
                codes=row["cr_code_count"],
                customers=row["customer_rows"],
                buyers=row["buyer_rows"],
                buyer_rate=format_percent(row["buyer_rate"]),
                sales=format_yen(row["total_sales"]),
                refunds=format_yen(row["total_refunds"]),
                refund_rate=format_percent(row["refund_rate"]),
                ltv_per_customer=format_yen(row["ltv_per_customer"]),
                ltv_median=format_yen(row["ltv_median"]),
            )
        )
    return "\n".join(lines)


def build_cdp_downstream_insights(summary: dict[str, Any]) -> list[str]:
    insights: list[str] = []
    bucket_rows = summary.get("bucket_rows", [])
    lp_rows = summary.get("lp_rows", [])
    if bucket_rows:
        top_ltv_bucket = max(bucket_rows, key=lambda row: row.get("ltv_per_customer") or 0.0)
        top_buyer_bucket = max(bucket_rows, key=lambda row: row.get("buyer_rate") or 0.0)
        top_refund_bucket = max(bucket_rows, key=lambda row: row.get("refund_rate") or 0.0)
        insights.append(
            f"- `失敗形` で見ると、顧客あたりLTVが最も高いのは `{top_ltv_bucket['failure_bucket']}` で `{format_yen(top_ltv_bucket.get('ltv_per_customer'))}`。"
            " `CPAが高い/低い` だけではなく、その市場に対してどの質の顧客を連れてきたかで読む。"
        )
        insights.append(
            f"- `失敗形` で見ると、購入者率が最も高いのは `{top_buyer_bucket['failure_bucket']}` で `{format_percent(top_buyer_bucket.get('buyer_rate'))}`。"
            " 安く獲得すること自体ではなく、獲得後の購入率まで含めて読む。"
        )
        insights.append(
            f"- 返金率が最も高いのは `{top_refund_bucket['failure_bucket']}` で `{format_percent(top_refund_bucket.get('refund_rate'))}`。"
            " ただし、これは `CTRが低いから返金率が高い` と断定する意味ではない。現時点の結線母集団ではこの失敗形が最も高い、という事実に留める。"
        )
    stable_lp_rows = [row for row in lp_rows if row.get("customer_rows", 0) >= 50]
    if stable_lp_rows:
        top_ltv_lp = max(stable_lp_rows, key=lambda row: row.get("ltv_per_customer") or 0.0)
        top_refund_lp = max(stable_lp_rows, key=lambda row: row.get("refund_rate") or 0.0)
        insights.append(
            f"- `LP` では、顧客あたりLTVが最も高いのは `{top_ltv_lp['lp_key']}` で `{format_yen(top_ltv_lp.get('ltv_per_customer'))}`。"
            " LPのオプトインCVRだけでなく、下流売上まで含めた強さを見る。"
        )
        insights.append(
            f"- `LP` では、返金率が最も高いのは `{top_refund_lp['lp_key']}` で `{format_percent(top_refund_lp.get('refund_rate'))}`。"
            " オファーやターゲット層のズレを含めて確認する。"
        )
    return insights


def render_family_table(rows: list[dict[str, Any]]) -> str:
    lines = ["| CR系統ラベル | 失敗数 | 勝ち数 | 読み |", "|---|---:|---:|---|"]
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
        openings = sorted(
            row.get("openings", []),
            key=lambda opening: (
                opening.get("count", 0),
                opening.get("cpa_median") or 0.0,
                opening.get("ctr_median") or 0.0,
            ),
            reverse=True,
        )
        for opening in openings[:5]:
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


def render_mixed_exact_crs(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 広告名 | 勝ち数 | 非勝ち数 | LP群 | CTR中央値 | CPA中央値 | 先に読むこと |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        ctr_text = f"{format_percent(row.get('positive_ctr_median'))} -> {format_percent(row.get('failure_ctr_median'))}"
        cpa_text = f"{format_yen(row.get('positive_cpa_median'))} -> {format_yen(row.get('failure_cpa_median'))}"
        lines.append(
            "| {ad} | {pos} | {neg} | {lps} | {ctr} | {cpa} | {read} |".format(
                ad=row.get("ad_name") or "-",
                pos=row.get("positive_count", 0),
                neg=row.get("failure_count", 0),
                lps=", ".join(row.get("lp_keys", [])) or "-",
                ctr=ctr_text,
                cpa=cpa_text,
                read=row.get("read", "-"),
            )
        )
    return "\n".join(lines)


def render_family_month_contexts(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| CR系統 | 月 | 勝ち数 | 非勝ち数 | 主な崩れ方 | CTR中央値 | CPA中央値 | 読み |",
        "|---|---|---:|---:|---|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {family} | {month} | {pos} | {neg} | {stage} | {ctr} | {cpa} | {read} |".format(
                family=row.get("family") or "-",
                month=row.get("month_key") or "-",
                pos=row.get("positive_count", 0),
                neg=row.get("failure_count", 0),
                stage=row.get("top_stage_name") or "-",
                ctr=format_percent(row.get("ctr_median")),
                cpa=format_yen(row.get("cpa_median")),
                read=row.get("read", "-"),
            )
        )
    return "\n".join(lines)


def render_family_bucket_profiles(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| CR系統 | 非勝ち件数 | 主な失敗形 | 構成比 | 次点の失敗形 | 構成比 | 読み |",
        "|---|---:|---|---:|---|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| {family} | {total} | {primary} | {primary_share:.1f}% | {secondary} | {secondary_share:.1f}% | {read} |".format(
                family=row.get("family") or "-",
                total=row.get("total", 0),
                primary=row.get("primary_bucket") or "-",
                primary_share=row.get("primary_share", 0.0),
                secondary=row.get("secondary_bucket") or "-",
                secondary_share=row.get("secondary_share", 0.0),
                read=row.get("read") or "-",
            )
        )
    return "\n".join(lines)


def build_time_context_insights(rows: list[dict[str, Any]]) -> list[str]:
    by_family: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_family[row.get("family", "")].append(row)
    for family_rows in by_family.values():
        family_rows.sort(key=lambda row: row.get("month_key", ""))

    insights: list[str] = []

    one_year = by_family.get("1年後悔", [])
    if one_year:
        winter_rows = [row for row in one_year if row.get("month_key", "")[5:7] in {"11", "12", "01"}]
        if winter_rows:
            insights.append(
                "- `1年後悔` は、年末年始に `また1年無駄にした` という自己評価のタイミングと噛み合う。"
                " いまの表でも `2025/12` `2026/01` に観測が厚く、まずは `年末の反省需要` と接続した旬を疑う。"
            )
        if any(row.get("top_stage_name") == "CTRとフック率は通るがオプトイン以降で失敗" for row in winter_rows):
            insights.append(
                "- ただし `1年後悔` の崩れ方は、冬でも `フックで離脱` より `CTRとフック率は通るがオプトイン以降で失敗` が主。"
                " つまりフック自体は残りやすく、課題は `ターゲット層` と `オファー` に寄りやすい。"
            )

    mondainai = by_family.get("問題ないです", [])
    if mondainai:
        late_summer = next((row for row in mondainai if row.get("month_key") == "2025/08"), None)
        later_first_stop = next(
            (
                row
                for row in mondainai
                if row.get("month_key") in {"2025/09", "2025/10"}
                and row.get("top_stage_name") == "フックで離脱"
            ),
            None,
        )
        if late_summer and later_first_stop and late_summer.get("top_stage_name") != later_first_stop.get("top_stage_name"):
            insights.append(
                "- `問題ないです` は、`2025/08` では `CTRとフック率は通るがオプトイン以降で失敗` が主だったのに、`2025/09〜10` では `フックで離脱` へ移っている。"
                " 自社の露出増だけでなく、他社が同じフォーマットを模倣したことで市場全体に既視感が広がり、`新しい情報ではない` と判断されてスキップが増えた可能性が高い。"
            )

    machigae = by_family.get("間違えました", [])
    if machigae:
        nov = next((row for row in machigae if row.get("month_key") == "2025/11"), None)
        dec = next((row for row in machigae if row.get("month_key") == "2025/12"), None)
        if nov and dec and nov.get("top_stage_name") != dec.get("top_stage_name"):
            insights.append(
                "- `間違えました` は、`2025/11` では `CTRとフック率は通るがオプトイン以降で失敗` が多い一方、`2025/12` では `フックで離脱` に寄る。"
                " `暴露 / 訂正` の驚きは初速を作るが、既視感が出ると一気に冒頭で離脱されやすい。"
            )

    yame = by_family.get("全部やめました", [])
    if yame:
        feb = next((row for row in yame if row.get("month_key") == "2026/02"), None)
        mar = next((row for row in yame if row.get("month_key") == "2026/03"), None)
        if feb and mar:
            insights.append(
                "- `全部やめました` は、`2026/02` では `CTRとフック率は通るがオプトイン以降で失敗` が主で CTR も高めだが、`2026/03` では `見られるがクリックされない` へずれている。"
                " 反王道メッセージが一度は新鮮でも、翌月には `またその話か` になり、クリックする理由が弱くなった可能性が高い。"
            )

    if insights:
        insights.append(
            "- 時期差は `勝ち数が増えた/減った` だけでなく、`どこで崩れるかがどう変わったか` を見る。"
            " 同じCR系統でも `CTRとフック率は通るがオプトイン以降で失敗 -> フックで離脱 / 見られるがクリックされない` にずれたら、旬切れや既視感の発生を先に疑う。"
        )

    return insights


def render_markdown(summary: dict[str, Any]) -> str:
    benchmarks = summary["benchmarks"]
    comparison = summary["comparison"]
    failure_mode = summary.get("failure_mode", "markdown")
    winner_same_asset_summary = summary["winner_same_asset_summary"]
    failure_same_asset_summary = summary["failure_same_asset_summary"]
    same_asset_summary = failure_same_asset_summary if failure_mode == "csv" else winner_same_asset_summary
    video_signal_summary = summary.get("video_signal_summary") or {}
    cdp_downstream_summary = summary.get("cdp_downstream_summary") or {}
    failure_source_name = Path(summary["failure_source"]).name
    if failure_mode == "csv":
        comparison_header = f"ここでは `大当たり基準 {summary['winner_count']}件` をベンチマークにしつつ、`勝ち側 {summary['positive_count']}件` と `非勝ち {summary['failure_count']}件` を比較している。"
        failure_source_line = f"- 失敗ソース: `System/data/meta_cr_dashboard/{failure_source_name}`（勝ち側 {summary['positive_count']}件 / 非勝ち {summary['failure_count']}件）"
        failure_note_line = "- 注意: full raw では `大当たり / 当たり` を勝ち側、その他を非勝ち側として読む。"
        top_funnel_line = f"- 非勝ち全量 `{summary['failure_count']}` 件のうち、`{comparison['top_funnel_strong_failures']}` 件は `CTRとフック率は通るがオプトイン以降で失敗` の候補に入る。"
        same_asset_source_line = f"- 非勝ち全量 `{summary['failure_count']}` 件の中だけでも、同一アセットの再利用群は `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。CR単体ではなく `オーディエンス / 広告ID / 広告セットID / LP / 時期` を切って読む必要がある。"
        meta_common_line = f"- 非勝ち全量の内部だけでも、`同一アセット × 同日 × 同LP` まで揃えて数値を比べられる群が `{same_asset_summary['same_asset_same_context_group_count']}` 群 `{same_asset_summary['rows_in_same_asset_same_context_groups']}` 件あり、そのうちオーディエンス差を読める群が `{same_asset_summary['audience_variation_group_count']}` 群ある。"
        same_asset_section_line = f"- 今回の失敗全量では、同一アセット群が `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。`同じCRなのに数値が違う` を解くときの一次切り分けに使う。"
    else:
        comparison_header = "ここでは `勝ちCR 340件` を基準に、`失敗側 24件` を比較している。"
        failure_source_line = f"- 失敗サンプル: `{summary['failure_source']}`（{summary['failure_count']}件）"
        failure_note_line = "- 注意: 失敗側は `消化金額上位24件` のスナップショット。全失敗CRの全量ではなく、高消化で負けた型を先に見ている。"
        top_funnel_line = f"- 高消化の失敗は `フックで離脱` より `CTRとフック率は通るがオプトイン以降で失敗` が中心。今回の24件では `{comparison['top_funnel_strong_failures']}` 件がこの形に入る。"
        same_asset_source_line = f"- 勝ちCR 340件の中だけでも、同一アセットの再利用群は `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。CR単体ではなく `オーディエンス / 広告ID / 広告セットID / LP / 時期` を切って読む必要がある。"
        meta_common_line = f"- 勝ちCR 340件の内部だけでも、`同一アセット × 同日 × 同LP` まで揃えて数値を比べられる群が `{same_asset_summary['same_asset_same_context_group_count']}` 群あり、そのうちオーディエンス差を読める群が `{same_asset_summary['audience_variation_group_count']}` 群ある。"
        same_asset_section_line = f"- 今回の340件では、同一アセット群が `{same_asset_summary['same_asset_groups_ge_2']}` 群 `{same_asset_summary['rows_in_same_asset_groups']}` 件ある。`同じCRなのに数値が違う` を解くための最初の切り口になる。"
    lines = [
        "# 広告CR失敗パターン",
        "",
        f"最終更新: {datetime.now().date().isoformat()}",
        "",
        "Meta広告CRの失敗は、`誰が作ったか` より `どこで崩れたか` で読む。",
        comparison_header,
        "",
        "## 失敗CRの定義",
        "",
        "- `1年後悔` や `林さん` のような CR系統ラベルそのものを `失敗CR` と呼ばない",
        "- `失敗CR` は、`大当たりCR / 当たりCR` に入らない側の CR 個体を指す",
        "- `完全に同じCR` で `勝ち / 非勝ち` が混在するときは、まず `運用差` を疑う",
        "- `フックが全然違う` なら、テーマやCR系統ラベルが近くても `別CR` として扱う",
        "- CR系統ラベルは `比較ラベル` であり、勝ち負けの断定には使わない",
        "",
        "## まず切る変数",
        "",
        "- 広告集客で大きく切る変数は `CR / 運用 / LP`",
        "- ただし、CR には `旬` がある。時代や時期によって見られ方は変わる",
        "- したがって実務上は `CR / 運用 / LP / 時期` の4軸で切る",
        "- `今見られている` を `恒久的に強い` と誤認しない",
        "",
        "## 集計対象",
        "",
        f"- 勝ち基準: `System/data/cr_bigwinners_raw.csv`（{summary['winner_count']}件）",
        failure_source_line,
    ]
    if summary["failure_scope_note"]:
        lines.append(f"- 失敗側の範囲: {summary['failure_scope_note']}")
    lines.extend(
        [
            failure_note_line,
            "",
            "## 勝ち基準との比較",
            "",
            "| 指標 | 勝ちCR中央値 | 失敗側中央値 |",
            "|---|---:|---:|",
            f"| CTR | {benchmarks['winner_ctr_median']:.2f}% | {benchmarks['failure_ctr_median']:.2f}% |",
            f"| フック率 | {benchmarks['winner_hook_median']:.2f}% | {benchmarks['failure_hook_median']:.2f}% |",
            f"| CPA | {format_yen(benchmarks['winner_cpa_median'])} | {format_yen(benchmarks['failure_cpa_median'])} |",
            "",
            "## 失敗形の判定基準（現在の自動分類）",
            "",
            render_stage_definition_table(benchmarks),
            "",
            f"- 非勝ち {summary['failure_count']}件のうち `{comparison['failure_ctr_ge_winner_median']}` 件は CTR が勝ちCR中央値以上",
            f"- 非勝ち {summary['failure_count']}件のうち `{comparison['failure_hook_ge_winner_median']}` 件は フック率が勝ちCR中央値以上",
            f"- 非勝ち {summary['failure_count']}件のうち `{comparison['top_funnel_strong_failures']}` 件は CTR とフック率の両方が勝ちCR中央値以上",
            f"- その中でも `{comparison['efficient_but_failed']}` 件は CPA まで勝ちCRの第3四分位以内に収まる",
            "",
            "## まず読むべき本質",
            "",
            top_funnel_line,
            "- つまり、失敗CRの主因を `フック不足` だけで説明しない。クリック後の期待値、LP・オファー・導線の崩れを先に疑う。",
            "- 一方で `CR系統ラベル` には偏りがある。言い回し単体で勝てるわけではないが、同じ系統が繰り返し外れているなら失敗候補として重く見る。",
            same_asset_source_line,
            "",
            "## Meta広告分析から見えた SNS広告共通の失敗メカニズム",
            "",
            "- ここで見ているのは Meta広告CR だが、`フックを広く取りすぎて広いオーディエンスに寄る失敗` という構造自体は SNS広告全般で起こる。",
            meta_common_line,
            f"- さらに `ノンタゲ vs 類似` を直接比べられる群は `{same_asset_summary['broad_vs_narrow_group_count']}` 群あり、CTR は `{same_asset_summary['broad_ctr_lower_count']}/{same_asset_summary['broad_ctr_compared_count']}` 群で広い側が低く、CPA は比較可能な `{same_asset_summary['broad_cpa_heavier_count']}/{same_asset_summary['broad_cpa_compared_count']}` 群で広い側が重かった。",
            f"- 勝ちCR 340件の再利用群でも、同じ比較ができる `{winner_same_asset_summary['broad_vs_narrow_group_count']}` 群では CTR が `{winner_same_asset_summary['broad_ctr_lower_count']}/{winner_same_asset_summary['broad_ctr_compared_count']}`、CPA が `{winner_same_asset_summary['broad_cpa_heavier_count']}/{winner_same_asset_summary['broad_cpa_compared_count']}` で広い側が不利だった。良いクリエイティブでも、広いオーディエンスに寄ると質が崩れやすい。",
            "- つまり `広いフックで人を集める -> オーディエンスが広がる -> 浅い反応層に学習する -> CTRやフック率の見た目よりオプトイン率やターゲット層の質が弱くなる` を、SNS広告の代表的な失敗メカニズムとして常に疑う。",
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
            "## CDP結線状況",
            "",
            "- CDP は `CR名` の末尾 `CRコード` で Meta raw と結線している。",
            "- LP別の下流集計は、`1つのCRコードが raw 上で単一LPにしか紐づかないもの` だけを使う。複数LPにまたがるCRコードは除外している。",
            "",
            render_cdp_join_table(cdp_downstream_summary) if cdp_downstream_summary else "- まだ結線できていない",
            "",
            "## 失敗形ごとの下流売上/LTV",
            "",
            render_downstream_rollup(cdp_downstream_summary.get("bucket_rows", [])[:8], "failure_bucket", "失敗形")
            if cdp_downstream_summary.get("bucket_rows")
            else "- まだ該当なし",
            "",
            "## LPごとの下流売上/LTV",
            "",
            render_downstream_rollup(cdp_downstream_summary.get("lp_rows", [])[:8], "lp_key", "LP")
            if cdp_downstream_summary.get("lp_rows")
            else "- まだ該当なし",
            "",
            "## 下流数値から見える仮説",
            "",
            *(
                build_cdp_downstream_insights(cdp_downstream_summary)
                if cdp_downstream_summary
                else ["- まだ十分な結線がない"]
            ),
            "",
            "## CR系統ラベルの偏り",
            "",
            render_family_table(summary["family_signals"]) if summary["family_signals"] else "- 目立つ偏りはまだ出ていない",
            "",
            "## CR系統ごとの主な失敗形",
            "",
            render_family_bucket_profiles(summary["family_bucket_profiles"])
            if summary["family_bucket_profiles"]
            else "- まだ該当なし",
            "",
            "## 同じCRで勝ち負け混在する例",
            "",
            "- ここは `CR系統` ではなく `広告名ベースの同一CR` を見ている",
            "- 同じCRで `勝ち / 非勝ち` が混ざるなら、creative の善し悪しより `運用差` を先に疑う",
            "",
            render_mixed_exact_crs(summary["mixed_exact_crs"]) if summary["mixed_exact_crs"] else "- まだ該当なし",
            "",
            "## CR系統ごとの時期差",
            "",
            "- `時期` は日付ではなく、その時期の社会背景・市場背景・旬まで含めて読む",
            "- ここは `CR系統 × 月` の観察表。数値だけで断定せず、その月の空気と重ねて解釈する",
            "",
            render_family_month_contexts(summary["family_month_contexts"])
            if summary["family_month_contexts"]
            else "- まだ該当なし",
            "",
            "## 時期文脈から見える仮説",
            "",
            *(
                build_time_context_insights(summary["family_month_contexts"])
                if summary["family_month_contexts"]
                else ["- まだ十分な観察がない"]
            ),
            "",
            "## 同一アセットでも数値がズレる例",
            "",
            "- まず `同じ動画URL/画像` を束ねる。そこから `同日・同LP` で比べ、最後に `LP差 / 時期差 / 冒頭差` を見る。",
            same_asset_section_line,
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

    if video_signal_summary.get("processed_count"):
        lines.extend(
            [
                "",
                "## 動画内容まで読んだ所見",
                "",
                "- Meta広告のCR分析は、数値だけでなく `実際の冒頭文` まで見る。特に `CTRとフック率は通るがオプトイン以降で失敗` では、広いフックで広いオーディエンスに学習していないかを先に疑う。",
                f"- 今回は `動画 {video_signal_summary['processed_count']}本` を文字起こしし、冒頭の broad marker と audience scope を集計した。",
                "",
                render_video_scope_summary(video_signal_summary),
                "",
                render_video_marker_summary(video_signal_summary),
                "",
                "### 冒頭の具体例",
                "",
                render_video_examples(video_signal_summary.get("top_examples", [])),
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
            "- `CTRとフック率は通るがオプトイン以降で失敗` に入ったら、CR単体の改善より `LP / オファー / 導線 / ターゲット層` を優先して見る。",
            "- `クリックされるがCPAが高い` は、クリックはされるので `オプトイン率の低さ` か `ターゲット層の質` を疑う。",
            "- 同一アセット比較は `asset -> オーディエンス -> 広告ID / 広告セットID -> LP -> 時期 -> 冒頭` の順で切る。順番を飛ばして `このCRは強い/弱い` と断定しない。",
            "- 同じCR系統が失敗側に偏っていても、1回では rules に上げない。複数スナップショットか下流数値が重なってから rules 化する。",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def run_analysis(winner_csv: Path, failure_markdown: Path | None, failure_csv: Path | None = None) -> dict[str, Any]:
    winner_rows = load_winner_rows(winner_csv)
    positive_rows = winner_rows
    failure_source: Path
    failure_mode: str
    if failure_csv:
        failure_rows, scope_note = load_failure_rows_from_csv(failure_csv)
        positive_rows = load_positive_rows_from_csv(failure_csv)
        failure_source = failure_csv
        failure_mode = "csv"
    elif failure_markdown:
        failure_rows, scope_note = load_failure_rows_from_markdown(failure_markdown)
        failure_source = failure_markdown
        failure_mode = "markdown"
    else:
        raise SystemExit("failure_markdown か failure_csv のどちらかが必要です")
    if not winner_rows:
        raise SystemExit(f"勝ちCRのCSVを読めませんでした: {winner_csv}")
    if not failure_rows:
        source_label = str(failure_csv or failure_markdown)
        raise SystemExit(f"失敗サンプルを読めませんでした: {source_label}")
    summary = summarize_patterns(winner_rows, failure_rows, positive_rows, scope_note, failure_source, failure_mode)
    if VIDEO_SIGNAL_SUMMARY_PATH.exists():
        summary["video_signal_summary"] = json.loads(VIDEO_SIGNAL_SUMMARY_PATH.read_text(encoding="utf-8"))
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    KNOWLEDGE_PATH.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def print_status() -> None:
    summary = json.loads(SUMMARY_JSON_PATH.read_text(encoding="utf-8")) if SUMMARY_JSON_PATH.exists() else {}
    video_summary = (
        json.loads(VIDEO_SIGNAL_SUMMARY_PATH.read_text(encoding="utf-8"))
        if VIDEO_SIGNAL_SUMMARY_PATH.exists()
        else {}
    )
    print(
        json.dumps(
            {
                "winner_source": str(DEFAULT_WINNER_CSV),
                "failure_source": summary.get("failure_source", str(DEFAULT_FAILURE_MARKDOWN)),
                "failure_mode": summary.get("failure_mode", ""),
                "latest_summary_generated_at": summary.get("generated_at", ""),
                "winner_count": summary.get("winner_count", 0),
                "positive_count": summary.get("positive_count", 0),
                "failure_count": summary.get("failure_count", 0),
                "video_signal_generated_at": video_summary.get("generated_at", ""),
                "video_signal_processed_count": video_summary.get("processed_count", 0),
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

    capture = subparsers.add_parser("capture-full-raw", help="認証済みの Looker Studio タブから Meta広告 CR一覧 full raw を保存する")
    capture.add_argument("--cdp-url", default=DEFAULT_CDP_URL)
    capture.add_argument("--page-key", default=DEFAULT_LOOKER_PAGE_KEY)
    capture.add_argument("--date-start", default="2023-01-01")
    capture.add_argument("--output", type=Path, default=DEFAULT_FULL_FAILURE_CSV)

    video_backfill = subparsers.add_parser("video-backfill", help="Meta動画URLを文字起こしして冒頭シグナルを集計する")
    video_backfill.add_argument("--winner-csv", type=Path, default=DEFAULT_WINNER_CSV)
    video_backfill.add_argument("--failure-csv", type=Path, default=DEFAULT_FULL_FAILURE_CSV)
    video_backfill.add_argument("--limit", type=int, default=20)
    video_backfill.add_argument("--bucket", default="CTRとフック率は通るがオプトイン以降で失敗")
    video_backfill.add_argument("--all-buckets", action="store_true")
    video_backfill.add_argument("--whisper-model", default=DEFAULT_VIDEO_MODEL)
    video_backfill.add_argument("--max-seconds", type=int, default=DEFAULT_VIDEO_CLIP_SECONDS)

    subparsers.add_parser("status", help="現在のソースと最新集計状況を表示する")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "analyze"
    if command == "status":
        print_status()
        return
    if command == "capture-full-raw":
        result = asyncio.run(
            capture_full_failure_raw(
                cdp_url=args.cdp_url,
                page_key=args.page_key,
                date_start=args.date_start,
                output_path=args.output,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if command == "video-backfill":
        winner_rows = load_winner_rows(args.winner_csv)
        failure_rows, _ = load_failure_rows_from_csv(args.failure_csv)
        benchmarks = build_benchmarks(winner_rows)
        enriched_failures = enrich_failures(failure_rows, benchmarks)
        bucket = "" if getattr(args, "all_buckets", False) else args.bucket
        result = backfill_video_signals(
            enriched_failures,
            limit=args.limit,
            bucket=bucket,
            whisper_model=args.whisper_model,
            max_seconds=args.max_seconds,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    summary = run_analysis(args.winner_csv, args.failure_markdown, args.failure_csv)
    print(
        json.dumps(
            {
                "generated_at": summary["generated_at"],
                "winner_count": summary["winner_count"],
                "failure_count": summary["failure_count"],
                "failure_source": summary["failure_source"],
                "failure_mode": summary["failure_mode"],
                "knowledge_path": str(KNOWLEDGE_PATH),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
