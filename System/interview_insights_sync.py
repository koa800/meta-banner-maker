#!/usr/bin/env python3
"""
AILEAD の面談収録URLから CDP の定性欄を補完する。

- 顧客マスタの `収録URL` を起点に AILEAD GraphQL から transcript / summary を取得
- Anthropic / Claude CLI で `現在の悩み` / `理想の未来` / `過去の解決策` を抽出
- 既存の CDP カラムが空のときだけ書き込む（--force で上書き可）
- 詳細な抽出結果は System/data/interview_insights_cache/ にキャッシュする
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import warnings
from collections import Counter
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any

warnings.filterwarnings(
    "ignore",
    message="urllib3 v2 only supports OpenSSL 1.1.1+",
)
warnings.filterwarnings(
    "ignore",
    message="You are using a Python version 3.9 past its end of life.",
    category=FutureWarning,
)

import browser_cookie3
import requests
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sheets_manager import get_client


CDP_SHEET_ID = "1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk"
CDP_TAB_NAME = "顧客マスタ"
DATA_DIR = Path(__file__).resolve().parent / "data"
CACHE_DIR = DATA_DIR / "interview_insights_cache"
STATE_PATH = DATA_DIR / "interview_insights_state.json"
ANALYSIS_PATH = DATA_DIR / "interview_insights_analysis.json"
AILEAD_AUTH_PATH = DATA_DIR / "ailead_auth_record.json"
LOCK_PATH = DATA_DIR / "interview_insights_sync.lock"
MASTER_DIR = Path(__file__).resolve().parent.parent / "Master"
ANALYSIS_MARKDOWN_PATH = MASTER_DIR / "knowledge" / "面談定性比較.md"
DEFAULT_LIMIT = 10
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_CHROME_DIR = Path.home() / "Library" / "Application Support" / "Google" / "Chrome"
DEFAULT_CHROME_EXECUTABLE = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CELL_TEXT_MAX_CHARS = 90
PAST_SOLUTIONS_MAX_CHARS = 70
WRITE_FLUSH_ROW_COUNT = 5
ROW_ERROR_COOLDOWN_HOURS = 24
ROW_LOW_CONFIDENCE_COOLDOWN_HOURS = 168
LOCK_STALE_HOURS = 6
CALL_URL_RE = re.compile(r"/call/([0-9a-fA-F-]{36})")
YOUTUBE_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtu\.be/[A-Za-z0-9_-]{11}[^\s]*)|https?://(?:www\.)?youtube\.com/[^\s]+")
LOOM_URL_RE = re.compile(r"https?://(?:www\.)?loom\.com/share/[A-Za-z0-9]+[^\s]*")
GRAPHQL_URL = "https://dashboard.ailead.app/api/v2/graphql"
DASHBOARD_URL = "https://dashboard.ailead.app/"
CALL_RESULT_HASH = "93db159f9a97df6d0a976d875a72827c99a90875ef213b9563aed440e4c88a80"
CALL_SUMMARY_HASH = "469311b6f8c6a9d9851b1560a8c9a8877a351647feca8f6b46bd5482bbd26826"
CURRENT_PAINS_HEADER = "現在の悩み"
IDEAL_FUTURE_HEADERS = ("理想の未来", "目標")
PAST_SOLUTIONS_HEADER = "過去の解決策"
QUALITATIVE_GROUP_NAME = "定性情報"

CALL_RESULT_QUERY = """
query callResult($callResultId: String!) {
  callResult(callResultId: $callResultId) {
    id
    callTitle
    startDatetime
    duration
    playbackUrl
    thumbnailUrl
    system
    visibility
    isInternal
    ipCallResultType
    callParticipants {
      id
      participantName
    }
    callDializations {
      id
      participantName
      startTime
      endTime
    }
    callTranscripts {
      id
      participantName
      startTime
      endTime
      text
      internalParticipantId
    }
  }
}
"""

CALL_SUMMARY_QUERY = """
query callSummary($callResultId: String!) {
  callResult(callResultId: $callResultId) {
    callSummary {
      id
      description
      keywords
      topics {
        id
        title
        description
        speakerName
        category
        dateTime
      }
    }
  }
}
"""

SUMMARY_PROMPT = """あなたは営業面談から顧客理解を抽出して CDP に記録する分析者です。
推測で盛らず、発言から言えることだけを短く整理してください。

出力は JSON のみで返してください。スキーマ:
{
  "summary": "面談の要約。120文字以内",
  "current_pains_text": "CDP の `現在の悩み` にそのまま入れられる文。90文字以内",
  "ideal_future_text": "CDP の `理想の未来` にそのまま入れられる文。90文字以内",
  "past_solutions_text": "CDP の `過去の解決策` にそのまま入れられる文。70文字以内",
  "current_pains": ["悩み1", "悩み2"],
  "ideal_futures": ["未来1", "未来2"],
  "past_solutions": ["過去の解決策1", "過去の解決策2"],
  "customer_type": "顧客タイプを一言",
  "confidence": "high または medium または low",
  "evidence_notes": ["根拠1", "根拠2"]
}

ルール:
- `current_pains_text` / `ideal_future_text` / `past_solutions_text` は 1セルで読める短い日本語にする
- 長くても `current_pains_text` / `ideal_future_text` は 90文字以内、`past_solutions_text` は 70文字以内に収める
- `past_solutions_text` は特に短く、自己流・過去商材・独学などを 1-2 個だけ簡潔に書く
- 情報が弱い場合は無理に埋めず空文字を返す
- `confidence=low` は transcript / summary から十分な根拠が読めない時だけにする
- セールス側の都合ではなく、顧客本人の悩み・理想の未来・過去の解決策を優先する
"""


@dataclass
class TargetRow:
    sheet_row: int
    customer_id: str
    email: str
    line_name: str
    cr_name: str
    first_route: str
    salesperson: str
    ltv: str
    recording_url: str
    current_pains: str
    ideal_future: str
    past_solutions: str


class AuthError(RuntimeError):
    pass


class ExecutionLockError(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(collapse_ws(value))
    except Exception:
        return None


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@contextmanager
def interview_sync_lock(command_name: str):
    LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": os.getpid(),
        "command": command_name,
        "started_at": now_iso(),
    }
    while True:
        try:
            fd = os.open(LOCK_PATH, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False, indent=2))
            break
        except FileExistsError:
            existing = load_json(LOCK_PATH, {})
            started_at = parse_iso_datetime(existing.get("started_at", ""))
            if started_at:
                elapsed_hours = max(0.0, (datetime.now() - started_at).total_seconds() / 3600)
                if elapsed_hours < LOCK_STALE_HOURS:
                    raise ExecutionLockError(
                        "面談定性補完はすでに実行中です: "
                        f"pid={existing.get('pid', 'unknown')} "
                        f"command={collapse_ws(existing.get('command', 'unknown'))}"
                    )
            try:
                LOCK_PATH.unlink()
            except FileNotFoundError:
                continue

    try:
        yield
    finally:
        try:
            existing = load_json(LOCK_PATH, {})
            if int(existing.get("pid") or 0) == os.getpid():
                LOCK_PATH.unlink()
        except FileNotFoundError:
            pass


def collapse_ws(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(text or ""))
    normalized = normalized.replace("\ufffd", " ")
    normalized = re.sub(r"[\x00-\x1f\x7f]", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def to_col_letter(col_number: int) -> str:
    result = ""
    n = col_number
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def extract_call_result_id(url: str) -> str | None:
    match = CALL_URL_RE.search(url or "")
    return match.group(1) if match else None


def dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        cleaned = collapse_ws(value)
        if not cleaned or cleaned in seen:
            continue
        ordered.append(cleaned)
        seen.add(cleaned)
    return ordered


def extract_ailead_urls(value: str) -> list[str]:
    return dedupe_preserve_order(re.findall(r"https://dashboard\.ailead\.app/call/[^\s]+", value or ""))


def extract_video_urls(value: str) -> list[str]:
    urls = []
    urls.extend(YOUTUBE_URL_RE.findall(value or ""))
    urls.extend(LOOM_URL_RE.findall(value or ""))
    return dedupe_preserve_order(urls)


def extract_supported_recording_urls(value: str) -> list[str]:
    return dedupe_preserve_order(extract_ailead_urls(value) + extract_video_urls(value))


def normalize_recording_url(value: str) -> str:
    urls = extract_supported_recording_urls(value)
    if urls:
        return urls[-1]
    return (value or "").strip()


def detect_recording_source(url: str) -> str:
    normalized = normalize_recording_url(url)
    if "dashboard.ailead.app/call/" in normalized:
        return "ailead"
    if "youtu.be/" in normalized or "youtube.com/" in normalized:
        return "youtube"
    if "loom.com/share/" in normalized:
        return "loom"
    return "unknown"


def extract_video_cache_key(url: str) -> str:
    normalized = normalize_recording_url(url)
    youtube_match = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", normalized)
    if youtube_match:
        return f"youtube_{youtube_match.group(1)}"
    loom_match = re.search(r"loom\.com/share/([A-Za-z0-9]+)", normalized)
    if loom_match:
        return f"loom_{loom_match.group(1)}"
    return re.sub(r"[^A-Za-z0-9_-]+", "_", normalized)[:80]


def recording_cache_key(url: str) -> str:
    source = detect_recording_source(url)
    if source == "ailead":
        return extract_call_result_id(url) or extract_video_cache_key(url)
    if source in {"youtube", "loom"}:
        return extract_video_cache_key(url)
    return extract_video_cache_key(url)


def combine_insights(insights_list: list[dict[str, Any]]) -> dict[str, Any]:
    non_low = [item for item in insights_list if (item.get("confidence") or "").lower() != "low"]
    source_items = non_low or insights_list

    current_pains = dedupe_preserve_order(
        [item for insights in source_items for item in insights.get("current_pains", [])]
    )
    ideal_futures = dedupe_preserve_order(
        [item for insights in source_items for item in insights.get("ideal_futures", [])]
    )
    past_solutions = dedupe_preserve_order(
        [item for insights in source_items for item in insights.get("past_solutions", [])]
    )
    evidence_notes = dedupe_preserve_order(
        [item for insights in source_items for item in insights.get("evidence_notes", [])]
    )
    summaries = dedupe_preserve_order([collapse_ws(item.get("summary", "")) for item in source_items])

    confidence = "low"
    if any((item.get("confidence") or "").lower() == "high" for item in insights_list):
        confidence = "high"
    elif any((item.get("confidence") or "").lower() == "medium" for item in insights_list):
        confidence = "medium"

    return {
        "summary": fit_cell_text(" / ".join(summaries[:2]), 120),
        "current_pains_text": fit_cell_text(join_items_for_cell(current_pains), CELL_TEXT_MAX_CHARS),
        "ideal_future_text": fit_cell_text(join_items_for_cell(ideal_futures), CELL_TEXT_MAX_CHARS),
        "past_solutions_text": fit_cell_text(join_items_for_cell(past_solutions), PAST_SOLUTIONS_MAX_CHARS),
        "current_pains": current_pains,
        "ideal_futures": ideal_futures,
        "past_solutions": past_solutions,
        "customer_type": collapse_ws(next((x.get("customer_type", "") for x in source_items if x.get("customer_type")), "")),
        "confidence": confidence,
        "evidence_notes": evidence_notes[:6],
        "source_count": len(insights_list),
        "non_low_count": len(non_low),
    }


def extract_text_block(response: Any) -> str:
    parts = []
    for block in getattr(response, "content", []):
        text = getattr(block, "text", "")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def resolve_anthropic_api_key() -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if api_key:
        return api_key

    config_paths = [
        Path(__file__).resolve().parent / "line_bot_local" / "config.json",
        Path(__file__).resolve().parent / "config" / "line_bot_local.json",
    ]
    for config_path in config_paths:
        if not config_path.exists():
            continue
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        api_key = (data.get("anthropic_api_key") or "").strip()
        if api_key:
            return api_key

    return ""


def detect_claude_cli() -> str:
    candidates = [
        shutil.which("claude"),
        "/opt/homebrew/bin/claude",
        str(Path.home() / ".local" / "bin" / "claude"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError("Claude CLI が見つかりません")


def join_items_for_cell(values: list[str], max_items: int = 2) -> str:
    cleaned = [collapse_ws(x) for x in values if collapse_ws(x)]
    return " / ".join(cleaned[:max_items])


def fit_cell_text(text: str, max_chars: int) -> str:
    normalized = collapse_ws(text)
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def ranges_overlap(start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) < min(end_a, end_b)


def parse_yen_amount(value: str) -> int | None:
    cleaned = re.sub(r"[^\d-]", "", collapse_ws(value))
    if not cleaned or cleaned == "-":
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def percentile_value(values: list[int], percentile: float) -> int | None:
    if not values:
        return None
    sorted_values = sorted(values)
    idx = round((len(sorted_values) - 1) * percentile)
    idx = max(0, min(idx, len(sorted_values) - 1))
    return sorted_values[idx]


def split_cell_items(text: str) -> list[str]:
    normalized = collapse_ws(text)
    if not normalized:
        return []
    if "/" in normalized:
        return [collapse_ws(part) for part in re.split(r"\s*/\s*", normalized) if collapse_ws(part)]
    return [normalized]


def summarize_top_items(rows: list[dict[str, Any]], field: str, top_n: int = 8) -> list[dict[str, Any]]:
    counter: Counter[str] = Counter()
    for row in rows:
        for item in split_cell_items(str(row.get(field, ""))):
            counter[item] += 1
    return [{"text": text, "count": count} for text, count in counter.most_common(top_n)]


def ltv_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [int(row["ltv_value"]) for row in rows if row.get("ltv_value") is not None]
    if not values:
        return {"count": 0, "average": None, "median": None}
    return {
        "count": len(values),
        "average": round(sum(values) / len(values)),
        "median": int(median(values)),
    }


def build_segment_summary(
    rows: list[dict[str, Any]],
    sort_key: str,
    descending: bool,
    sample_size: int = 5,
) -> dict[str, Any]:
    ordered = sorted(
        rows,
        key=lambda row: (row.get(sort_key) is None, row.get(sort_key) or 0, row.get("sheet_row", 0)),
        reverse=descending,
    )
    return {
        "row_count": len(rows),
        "ltv_stats": ltv_stats(rows),
        "top_current_pains": summarize_top_items(rows, "current_pains"),
        "top_ideal_futures": summarize_top_items(rows, "ideal_future"),
        "top_past_solutions": summarize_top_items(rows, "past_solutions"),
        "sample_rows": [
            {
                "sheet_row": row["sheet_row"],
                "customer_id": row["customer_id"],
                "ltv": row["ltv_text"],
                "cr_name": row["cr_name"],
                "first_route": row["first_route"],
                "current_pains": row["current_pains"],
                "ideal_future": row["ideal_future"],
                "past_solutions": row["past_solutions"],
            }
            for row in ordered[:sample_size]
        ],
    }


def top_texts(segment: dict[str, Any], field: str, limit: int = 3) -> list[str]:
    items = segment.get(field) or []
    return [collapse_ws(item.get("text", "")) for item in items[:limit] if collapse_ws(item.get("text", ""))]


def format_top_items(items: list[dict[str, Any]], limit: int = 3) -> str:
    parts = []
    for item in (items or [])[:limit]:
        text = collapse_ws(item.get("text", ""))
        count = item.get("count", 0)
        if not text:
            continue
        parts.append(f"{text} ({count})")
    return " / ".join(parts) if parts else "なし"


def render_analysis_markdown(report: dict[str, Any]) -> str:
    coverage = report.get("coverage") or {}
    segmentation = report.get("segmentation") or {}
    segments = report.get("segments") or {}
    high = segments.get("high_ltv") or {}
    low = segments.get("low_ltv") or {}
    non = segments.get("non_conversion") or {}

    shared_current = sorted(
        set(top_texts(high, "top_current_pains")) &
        set(top_texts(low, "top_current_pains")) &
        set(top_texts(non, "top_current_pains"))
    )

    lines = [
        "# 面談定性比較",
        "",
        f"最終更新: {collapse_ws(report.get('generated_at', ''))[:10]}",
        "",
        "## 目的",
        "",
        "CDP に入った面談定性を `高LTV / 低LTV / 非成約` で比較し、顧客理解を `knowledge` と `rules` に戻す。",
        "",
        "## 正本",
        "",
        "- 機械可読な正本: `System/data/interview_insights_analysis.json`",
        "- 再生成コマンド: `python3 System/interview_insights_sync.py analyze`",
        "",
        "## 現在のカバレッジ",
        "",
        f"- `収録URL`: `{coverage.get('recording_url_rows', 0)}` 行",
        f"- `現在の悩み`: `{coverage.get('current_pains_filled_total', 0)}` 行",
        f"- `理想の未来`: `{coverage.get('ideal_future_filled_total', 0)}` 行",
        f"- `過去の解決策`: `{coverage.get('past_solutions_filled_total', 0)}` 行",
        f"- 定性ありで比較可能な行: `{coverage.get('rows_with_recording_and_qualitative', 0)}`",
        f"- 複数URLを持つ行: `{coverage.get('multi_recording_rows', 0)}`",
        "",
        "## セグメントの切り方",
        "",
        f"- `高LTV`: `{segmentation.get('high_ltv_min')}` 以上",
        f"- `低LTV`: `{segmentation.get('low_ltv_max')}` 以下",
        "- `非成約`: `LTV <= 0`",
        "",
        "## 確定で言えること",
        "",
    ]

    if shared_current:
        lines.append(f"- `現在の悩み` の上位は3セグメントで重なる: {' / '.join(shared_current)}")
    else:
        lines.append("- `現在の悩み` の上位分布だけでは、3セグメントの切り分けが弱い")
    lines.extend(
        [
            "- `現在の悩み` 単独では勝ち顧客と失注顧客を切り分けにくい",
            "- 複数URL行が多いため、同一顧客の収録は行単位で統合して読む前提にする",
            "- `過去の解決策` はまだ薄く、現時点では分析軸として弱い",
            "",
            "## セグメント別の上位項目",
            "",
            f"- 高LTVの `現在の悩み`: {format_top_items(high.get('top_current_pains'))}",
            f"- 低LTVの `現在の悩み`: {format_top_items(low.get('top_current_pains'))}",
            f"- 非成約の `現在の悩み`: {format_top_items(non.get('top_current_pains'))}",
            f"- 高LTVの `理想の未来`: {format_top_items(high.get('top_ideal_futures'))}",
            f"- 非成約の `過去の解決策`: {format_top_items(non.get('top_past_solutions'))}",
            "",
            "## 強い推定",
            "",
            "- 面談定性の差は、`今の悩み` より `理想の未来` と `過去の解決策` に出やすい",
            "- 顧客理解の精度を上げる次の一手は、件数をただ増やすことより `過去の解決策` の埋まり率を上げること",
            "",
            "## 今の使い方",
            "",
            "- CR / LP / 面談導線の人物像を作るとき、`現在の悩み` の頻出語だけで決めない",
            "- 顧客理解の深掘りは、`理想の未来` と `過去の解決策` を優先する",
            "- `過去の解決策` が増えるたびに比較分析を再生成する",
            "",
        ]
    )
    return "\n".join(lines)


def summarize_with_claude_cli(payload: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    prompt = (
        f"{SUMMARY_PROMPT}\n\n"
        "以下の面談情報を分析し、指定スキーマの JSON のみを返してください。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    env.pop("CLAUDECODE", None)
    result = subprocess.run(
        [detect_claude_cli(), "-p", "--model", model, "--max-turns", "3", prompt],
        capture_output=True,
        text=True,
        timeout=240,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed (code={result.returncode}): {result.stderr[:300]}")
    return extract_json_object(result.stdout.strip())


def summarize_insights(payload: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    parsed: dict[str, Any]
    api_key = resolve_anthropic_api_key()
    api_error = ""
    llm_backend = "anthropic_api"
    if api_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=1200,
                system=SUMMARY_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False, indent=2),
                    }
                ],
            )
            parsed = extract_json_object(extract_text_block(response))
        except Exception as exc:
            api_error = str(exc)
            llm_backend = "claude_cli"
            parsed = summarize_with_claude_cli(payload, model=model)
    else:
        llm_backend = "claude_cli"
        parsed = summarize_with_claude_cli(payload, model=model)

    current_pains = [collapse_ws(x) for x in parsed.get("current_pains", []) if collapse_ws(x)]
    ideal_futures = [
        collapse_ws(x)
        for x in parsed.get("ideal_futures", parsed.get("goals", []))
        if collapse_ws(x)
    ]
    past_solutions = [
        collapse_ws(x)
        for x in parsed.get("past_solutions", [])
        if collapse_ws(x)
    ]
    if not past_solutions:
        legacy_candidates = []
        legacy_candidates.extend(parsed.get("anxieties", []) or [])
        legacy_candidates.extend(parsed.get("decision_factors", []) or [])
        past_solutions = [collapse_ws(x) for x in legacy_candidates if collapse_ws(x)]

    current_pains_text = fit_cell_text(
        collapse_ws(parsed.get("current_pains_text", "")) or join_items_for_cell(current_pains),
        CELL_TEXT_MAX_CHARS,
    )
    ideal_future_text = fit_cell_text(
        collapse_ws(parsed.get("ideal_future_text", parsed.get("goals_text", "")))
        or join_items_for_cell(ideal_futures),
        CELL_TEXT_MAX_CHARS,
    )
    past_solutions_text = fit_cell_text(
        collapse_ws(parsed.get("past_solutions_text", "")) or join_items_for_cell(past_solutions),
        PAST_SOLUTIONS_MAX_CHARS,
    )

    return {
        "summary": fit_cell_text(collapse_ws(parsed.get("summary", "")), 120),
        "current_pains_text": current_pains_text,
        "ideal_future_text": ideal_future_text,
        "past_solutions_text": past_solutions_text,
        "current_pains": current_pains,
        "ideal_futures": ideal_futures,
        "past_solutions": past_solutions,
        "customer_type": collapse_ws(parsed.get("customer_type", "")),
        "confidence": collapse_ws(parsed.get("confidence", "")).lower() or "low",
        "evidence_notes": [collapse_ws(x) for x in parsed.get("evidence_notes", []) if collapse_ws(x)],
        "llm_fallback": llm_backend,
        "llm_error": collapse_ws(api_error),
    }


def build_prompt_payload(call_data: dict[str, Any], target: TargetRow) -> dict[str, Any]:
    call_result = call_data.get("callResult") or {}
    call_summary = (call_data.get("callSummary") or {}).get("callSummary") or {}
    transcript_text = build_transcript_text(call_result)
    transcript_excerpt = transcript_text
    if len(transcript_excerpt) > 14000:
        transcript_excerpt = f"{transcript_excerpt[:7000]}\n...\n{transcript_excerpt[-7000:]}"

    topics = []
    for topic in call_summary.get("topics") or []:
        title = collapse_ws(topic.get("title", ""))
        description = collapse_ws(topic.get("description", ""))
        speaker = collapse_ws(topic.get("speakerName", ""))
        if not any([title, description, speaker]):
            continue
        topic_line = " | ".join([x for x in [title, description, speaker] if x])
        topics.append(topic_line)

    return {
        "顧客情報": {
            "customer_id": target.customer_id,
            "email": target.email,
            "line_name": target.line_name,
            "初回流入経路": target.first_route,
            "CR名": target.cr_name,
            "担当営業": target.salesperson,
            "LTV": target.ltv,
        },
        "AILEADメタデータ": {
            "call_title": collapse_ws(call_result.get("callTitle", "")),
            "start_datetime": call_result.get("startDatetime", ""),
            "duration_seconds": call_result.get("duration", 0),
            "participants": [
                {
                    "name": collapse_ws(p.get("participantName", "")),
                }
                for p in (call_result.get("callParticipants") or [])
            ],
        },
        "AILEAD要約": {
            "description": collapse_ws(call_summary.get("description", "")),
            "keywords": [collapse_ws(x) for x in (call_summary.get("keywords") or []) if collapse_ws(x)],
            "topics": topics,
        },
        "Transcript抜粋": transcript_excerpt,
    }


def build_prompt_payload_from_video_result(video_result: dict[str, Any], target: TargetRow) -> dict[str, Any]:
    transcript_excerpt = collapse_ws(video_result.get("transcript_summary", "")) or collapse_ws(
        video_result.get("transcript_text", "")
    )
    if len(transcript_excerpt) > 14000:
        transcript_excerpt = f"{transcript_excerpt[:7000]}\n...\n{transcript_excerpt[-7000:]}"

    return {
        "顧客情報": {
            "customer_id": target.customer_id,
            "email": target.email,
            "line_name": target.line_name,
            "初回流入経路": target.first_route,
            "CR名": target.cr_name,
            "担当営業": target.salesperson,
            "LTV": target.ltv,
        },
        "AILEADメタデータ": {
            "call_title": collapse_ws(video_result.get("title", "")),
            "start_datetime": "",
            "duration_seconds": video_result.get("duration", 0),
            "participants": [],
        },
        "AILEAD要約": {
            "description": collapse_ws(video_result.get("transcript_summary", "")),
            "keywords": [],
            "topics": [],
        },
        "Transcript抜粋": transcript_excerpt,
    }


def build_transcript_text(call_result: dict[str, Any]) -> str:
    merged: list[tuple[str, str]] = []
    items = sorted(
        call_result.get("callTranscripts") or [],
        key=lambda item: (item.get("startTime") or 0, item.get("id") or ""),
    )
    for item in items:
        speaker = collapse_ws(item.get("participantName", "")) or "不明"
        text = collapse_ws(item.get("text", ""))
        if not text:
            continue
        if merged and merged[-1][0] == speaker:
            merged[-1] = (speaker, f"{merged[-1][1]} {text}")
        else:
            merged.append((speaker, text))
    return "\n".join(f"{speaker}: {text}" for speaker, text in merged)


def cache_path_for(call_result_id: str) -> Path:
    return CACHE_DIR / f"{call_result_id}.json"


def detect_chrome_executable() -> str | None:
    if DEFAULT_CHROME_EXECUTABLE.exists():
        return str(DEFAULT_CHROME_EXECUTABLE)
    return None


def list_profile_candidates(chrome_root: Path, preferred_profile: str | None) -> list[str]:
    candidates: list[str] = []
    if preferred_profile:
        candidates.append(preferred_profile)
    if "Default" not in candidates:
        candidates.append("Default")

    local_state = chrome_root / "Local State"
    if local_state.exists():
        try:
            state = json.loads(local_state.read_text(encoding="utf-8"))
        except Exception:
            state = {}
        info_cache = (state.get("profile") or {}).get("info_cache") or {}
        weighted = []
        for key, info in info_cache.items():
            score = 0
            name = collapse_ws((info or {}).get("name", ""))
            user_name = collapse_ws((info or {}).get("user_name", ""))
            combined = f"{name} {user_name}".lower()
            if "addness" in combined or "アドネス" in combined:
                score += 3
            if "team.addness.co.jp" in combined:
                score += 5
            weighted.append((-score, key))
        for _, key in sorted(weighted):
            if key not in candidates:
                candidates.append(key)

    return [key for key in candidates if (chrome_root / key).exists()]


class AileadClient:
    def __init__(self, profile: str | None = None, headless: bool = True):
        self.profile = profile
        self.headless = headless
        self.build_id = ""
        self.session: requests.Session | None = None
        self.active_profile = ""
        self.auth_record: dict[str, Any] | None = None

    def __enter__(self):
        chrome_root = DEFAULT_CHROME_DIR
        if not chrome_root.exists():
            raise AuthError(f"Chrome プロファイルが見つかりません: {chrome_root}")

        cached_auth = load_json(AILEAD_AUTH_PATH, {})
        cached_profile = collapse_ws(cached_auth.get("profile_dir", ""))
        tried_profiles = []
        if cached_profile:
            tried_profiles.append(cached_profile)
        tried_profiles.extend(list_profile_candidates(chrome_root, self.profile))

        seen_profiles: set[str] = set()
        for profile_dir in tried_profiles:
            if not profile_dir or profile_dir in seen_profiles:
                continue
            seen_profiles.add(profile_dir)
            try:
                auth_record = None
                if profile_dir == cached_profile:
                    auth_record = cached_auth.get("auth_record")
                if auth_record:
                    session = self._build_session(profile_dir, auth_record)
                    if session:
                        self.active_profile = profile_dir
                        self.auth_record = auth_record
                        self.session = session
                        return self

                auth_record = self._extract_auth_record_from_indexeddb(profile_dir)
                if auth_record:
                    session = self._build_session(profile_dir, auth_record)
                    if session:
                        self.active_profile = profile_dir
                        self.auth_record = auth_record
                        self.session = session
                        save_json(
                            AILEAD_AUTH_PATH,
                            {
                                "saved_at": now_iso(),
                                "profile_dir": profile_dir,
                                "auth_record": auth_record,
                                "source": "indexeddb_fallback",
                            },
                        )
                        return self

                auth_record = self._extract_auth_record(profile_dir)
                if not auth_record:
                    continue
                session = self._build_session(profile_dir, auth_record)
                if not session:
                    continue
                self.active_profile = profile_dir
                self.auth_record = auth_record
                self.session = session
                save_json(
                    AILEAD_AUTH_PATH,
                    {
                        "saved_at": now_iso(),
                        "profile_dir": profile_dir,
                        "auth_record": auth_record,
                    },
                )
                return self
            except Exception:
                continue

        raise AuthError("AILEAD の認証情報を Chrome プロファイルから取得できませんでした")

    def __exit__(self, exc_type, exc, tb):
        if self.session:
            self.session.close()
        return False

    def _launch_playwright_context(self, user_data_dir: str):
        kwargs: dict[str, Any] = {
            "user_data_dir": user_data_dir,
            "headless": self.headless,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-infobars",
            ],
            "ignore_default_args": ["--enable-automation"],
        }
        executable = detect_chrome_executable()
        if executable:
            kwargs["executable_path"] = executable
        else:
            kwargs["channel"] = "chrome"
        return kwargs

    def _extract_refresh_token_from_blob(self, blob: bytes) -> str | None:
        token_chars = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.")
        search_start = 0
        marker = b"stsTokenManager"
        while True:
            idx = blob.find(marker, search_start)
            if idx == -1:
                break
            chunk = blob[idx : idx + 4096]
            refresh_idx = chunk.find(b"refresh")
            if refresh_idx != -1:
                quote_idx = chunk.find(b'"', refresh_idx)
                if quote_idx != -1:
                    start = quote_idx + 1
                    while start < len(chunk) and chunk[start] not in token_chars:
                        start += 1
                    end = start
                    while end < len(chunk) and chunk[end] in token_chars:
                        end += 1
                    token = chunk[start:end].decode("utf-8", "ignore")
                    if len(token) >= 200:
                        return token
            search_start = idx + len(marker)

        text = blob.decode("utf-8", "ignore")
        fallback = re.search(r'refreshToken"([A-Za-z0-9._\-]{200,})', text)
        if fallback:
            return fallback.group(1)
        return None

    def _extract_auth_record_from_indexeddb(self, profile_dir: str) -> dict[str, Any] | None:
        idx_dir = (
            DEFAULT_CHROME_DIR
            / profile_dir
            / "IndexedDB"
            / "https_dashboard.ailead.app_0.indexeddb.leveldb"
        )
        if not idx_dir.exists():
            return None

        blob_parts: list[bytes] = []
        for path in idx_dir.rglob("*"):
            if not path.is_file():
                continue
            try:
                data = path.read_bytes()
            except Exception:
                continue
            if any(marker in data for marker in (b"authUser", b"stsTokenManager", b"refreshToken")):
                blob_parts.append(data)

        if not blob_parts:
            return None

        blob = b"\n".join(blob_parts)
        api_key_match = re.search(rb"authUser:([^:\s]+):\[DEFAULT\]", blob)
        refresh_token = self._extract_refresh_token_from_blob(blob)
        if not api_key_match or not refresh_token:
            return None

        text = blob.decode("utf-8", "ignore")
        auth_record: dict[str, Any] = {
            "apiKey": api_key_match.group(1).decode("utf-8", "ignore"),
            "stsTokenManager": {
                "refreshToken": refresh_token,
            },
        }
        uid_match = re.search(r'uid"([A-Za-z0-9_-]+)"', text)
        email_match = re.search(r'email"([^"\s]+@[^"\s]+)"', text)
        if uid_match:
            auth_record["uid"] = uid_match.group(1)
        if email_match:
            auth_record["email"] = email_match.group(1)
        return auth_record

    def _extract_auth_record(self, profile_dir: str) -> dict[str, Any] | None:
        chrome_root = DEFAULT_CHROME_DIR
        temp_dir = Path(tempfile.mkdtemp(prefix="ailead_auth_"))
        try:
            local_state = chrome_root / "Local State"
            if local_state.exists():
                shutil.copy2(local_state, temp_dir / "Local State")

            src_profile = chrome_root / profile_dir
            dst_profile = temp_dir / profile_dir
            dst_profile.mkdir(parents=True, exist_ok=True)

            for name in ["Preferences", "Secure Preferences"]:
                src = src_profile / name
                if src.exists():
                    shutil.copy2(src, dst_profile / name)

            for name in ["IndexedDB", "Local Storage", "Session Storage"]:
                src = src_profile / name
                dst = dst_profile / name
                if src.exists():
                    shutil.copytree(
                        src,
                        dst,
                        ignore=shutil.ignore_patterns("LOCK", "*.lock", "Singleton*"),
                        dirs_exist_ok=True,
                    )

            with sync_playwright() as playwright:
                context = playwright.chromium.launch_persistent_context(
                    **self._launch_playwright_context(str(temp_dir))
                )
                try:
                    page = context.pages[0] if context.pages else context.new_page()
                    page.goto(DASHBOARD_URL, wait_until="domcontentloaded", timeout=120000)
                    time.sleep(2)
                    auth_record = page.evaluate(
                        """() => new Promise((resolve) => {
                            const req = indexedDB.open('firebaseLocalStorageDb');
                            req.onerror = () => resolve(null);
                            req.onsuccess = () => {
                                const db = req.result;
                                const tx = db.transaction('firebaseLocalStorage', 'readonly');
                                const store = tx.objectStore('firebaseLocalStorage');
                                const allReq = store.getAll();
                                allReq.onerror = () => resolve(null);
                                allReq.onsuccess = () => {
                                    const row = (allReq.result || []).find((item) =>
                                        (item.fbase_key || '').includes('firebase:authUser')
                                    );
                                    resolve(row?.value || null);
                                };
                            };
                        })"""
                    )
                finally:
                    context.close()
            return auth_record or None
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def _refresh_id_token(self, auth_record: dict[str, Any]) -> str:
        sts = auth_record.get("stsTokenManager") or {}
        refresh_token = sts.get("refreshToken") or ""
        api_key = auth_record.get("apiKey") or ""
        if not refresh_token or not api_key:
            raise AuthError("AILEAD の refresh token または apiKey が不足しています")

        response = requests.post(
            f"https://securetoken.googleapis.com/v1/token?key={api_key}",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        id_token = payload.get("id_token") or payload.get("access_token") or ""
        if not id_token:
            raise AuthError("Firebase token refresh に失敗しました")
        return id_token

    def _build_session(self, profile_dir: str, auth_record: dict[str, Any]) -> requests.Session | None:
        cookie_file = DEFAULT_CHROME_DIR / profile_dir / "Cookies"
        if not cookie_file.exists():
            return None

        jar = browser_cookie3.chrome(
            domain_name="dashboard.ailead.app",
            cookie_file=str(cookie_file),
        )
        cookies = list(jar)
        if not cookies:
            return None

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(cookie.name, cookie.value, domain=cookie.domain, path=cookie.path)

        id_token = self._refresh_id_token(auth_record)
        session.headers.update({"Authorization": f"Bearer {id_token}"})
        return session

    def _ensure_build_id(self, recording_url: str = "") -> str:
        if self.build_id:
            return self.build_id

        target_url = recording_url or DASHBOARD_URL
        response = requests.get(target_url, timeout=30)
        response.raise_for_status()
        match = re.search(r'"buildId":"([^"]+)"', response.text)
        if not match:
            raise RuntimeError("AILEAD buildId を取得できません")
        self.build_id = match.group(1)
        return self.build_id

    def graphql(
        self,
        operation_name: str,
        query: str | None,
        variables: dict[str, Any],
        operation_hash: str,
        recording_url: str = "",
    ) -> dict[str, Any]:
        if not self.session:
            raise RuntimeError("AILEAD session が初期化されていません")

        build_id = self._ensure_build_id(recording_url)
        payload: dict[str, Any] = {
            "operationName": operation_name,
            "variables": variables,
            "extensions": {
                "operationHash": operation_hash,
                "buildId": build_id,
            },
        }
        # AILEAD は persisted query が正本なので、ローカルの query 本文は原則送らない。
        # こうしておくと schema drift が起きても local query の validation error に引っ張られにくい。
        if collapse_ws(query or ""):
            payload["query"] = query

        response = self.session.post(
            GRAPHQL_URL,
            json=payload,
            timeout=60,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"AILEAD GraphQL HTTP {response.status_code}: {collapse_ws(response.text)[:500]}"
            )
        data = response.json()
        if data.get("errors"):
            raise RuntimeError(
                f"AILEAD GraphQL error: {json.dumps(data['errors'], ensure_ascii=False)[:300]}"
            )
        return data

    def fetch_call_package(self, recording_url: str) -> dict[str, Any]:
        recording_url = normalize_recording_url(recording_url)
        call_result_id = extract_call_result_id(recording_url)
        if not call_result_id:
            raise ValueError(f"callResultId を抽出できません: {recording_url}")

        result_data = self.graphql(
            "callResult",
            "",
            {"callResultId": call_result_id},
            CALL_RESULT_HASH,
            recording_url=recording_url,
        )
        summary_data: dict[str, Any] = {}
        try:
            summary_data = self.graphql(
                "callSummary",
                "",
                {"callResultId": call_result_id},
                CALL_SUMMARY_HASH,
                recording_url=recording_url,
            )
        except Exception:
            summary_data = {}

        return {
            "callResultId": call_result_id,
            "callResult": (result_data.get("data") or {}).get("callResult") or {},
            "callSummary": (summary_data.get("data") or {}).get("callResult") or {},
        }


def fetch_video_package(recording_url: str) -> dict[str, Any]:
    script_path = Path(__file__).resolve().parent / "video_reader" / "video_reader.py"
    video_output_base = DATA_DIR / "video_reader_cache"
    video_output_base.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [sys.executable, str(script_path), recording_url, "--no-frames"],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            **os.environ,
            "PYTHONUNBUFFERED": "1",
            "VIDEO_READER_OUTPUT_BASE": str(video_output_base),
        },
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        raise RuntimeError(f"video_reader failed: {(stderr or stdout)[:300]}")
    return extract_json_object(result.stdout.strip())


class CDPInterviewSync:
    def __init__(
        self,
        account: str,
        limit: int,
        dry_run: bool,
        force: bool,
        profile: str | None,
        headless: bool,
        row: int | None = None,
    ):
        self.account = account
        self.limit = limit
        self.dry_run = dry_run
        self.force = force
        self.profile = profile
        self.headless = headless
        self.row = row
        self.client = get_client(account)
        self.spreadsheet = self.client.open_by_key(CDP_SHEET_ID)
        self.worksheet = self.spreadsheet.worksheet(CDP_TAB_NAME)
        self.headers: list[str] = []
        self.header_map: dict[str, int] = {}
        self.current_pains_header = CURRENT_PAINS_HEADER
        self.ideal_future_header = ""
        self.past_solutions_header = ""
        self.refresh_headers()
        self.state = load_json(
            STATE_PATH,
            {
                "last_run": "",
                "calls": {},
            },
        )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def refresh_headers(self) -> None:
        self.headers = self.worksheet.row_values(2)
        self.header_map = {name: idx + 1 for idx, name in enumerate(self.headers) if name}
        self.current_pains_header = CURRENT_PAINS_HEADER
        self.ideal_future_header = self.find_existing_header(*IDEAL_FUTURE_HEADERS)
        if not self.ideal_future_header:
            raise KeyError(f"CDP列が見つかりません: {' / '.join(IDEAL_FUTURE_HEADERS)}")
        self.past_solutions_header = self.find_existing_header(PAST_SOLUTIONS_HEADER) or ""

    def find_existing_header(self, *candidates: str) -> str | None:
        for candidate in candidates:
            if candidate and candidate in self.header_map:
                return candidate
        return None

    def ensure_sheet_schema(self) -> dict[str, Any]:
        changes: list[str] = []
        schema_changed = False
        row1 = self.worksheet.row_values(1)
        row2 = self.worksheet.row_values(2)
        header_map = {name: idx + 1 for idx, name in enumerate(row2) if name}
        updates: list[dict[str, Any]] = []

        if "理想の未来" not in header_map and "目標" in header_map:
            col_number = header_map["目標"]
            updates.append({"range": f"{to_col_letter(col_number)}2", "values": [["理想の未来"]]})
            changes.append("`目標` を `理想の未来` に変更")
            schema_changed = True
            row2[col_number - 1] = "理想の未来"
            header_map["理想の未来"] = col_number
            header_map.pop("目標", None)

        ideal_future_col = header_map.get("理想の未来")
        if not ideal_future_col:
            raise KeyError("CDP列が見つかりません: 理想の未来")

        legacy_headers = ["不安・障壁", "決め手"]
        target_col = ideal_future_col + 1
        need_relocate = (
            header_map.get(PAST_SOLUTIONS_HEADER) != target_col
            or any(header in header_map for header in legacy_headers)
        )

        if need_relocate:
            last_row = len(self.worksheet.col_values(1))
            existing_values: list[list[str]] = []
            current_col = header_map.get(PAST_SOLUTIONS_HEADER)
            if current_col:
                existing_values = self.worksheet.get(
                    f"{to_col_letter(current_col)}3:{to_col_letter(current_col)}{last_row}",
                    value_render_option="FORMATTED_VALUE",
                )

            columns_to_delete = sorted(
                [
                    header_map[header]
                    for header in [PAST_SOLUTIONS_HEADER, *legacy_headers]
                    if header in header_map
                ],
                reverse=True,
            )
            for old_col in columns_to_delete:
                self.delete_column(old_col)

            self.refresh_headers()
            ideal_future_col = self.get_col_number(self.ideal_future_header)
            self.insert_columns_after(ideal_future_col, 1)
            new_updates = [
                {"range": f"{to_col_letter(ideal_future_col + 1)}1", "values": [[QUALITATIVE_GROUP_NAME]]},
                {"range": f"{to_col_letter(ideal_future_col + 1)}2", "values": [[PAST_SOLUTIONS_HEADER]]},
            ]
            if last_row >= 3:
                if existing_values:
                    new_updates.append(
                        {
                            "range": f"{to_col_letter(ideal_future_col + 1)}3:{to_col_letter(ideal_future_col + 1)}{last_row}",
                            "values": existing_values,
                        }
                    )
            updates.extend(new_updates)
            changes.append("`過去の解決策` を `理想の未来` の次に配置")
            schema_changed = True

        if updates:
            self.batch_update_with_retry(updates)

        self.refresh_headers()
        layout_result = self.ensure_qualitative_layout()
        if layout_result["updated"]:
            schema_changed = True
            changes.extend(layout_result["changes"])
        return {"updated": schema_changed, "changes": changes}

    def ensure_qualitative_layout(self) -> dict[str, Any]:
        if not self.past_solutions_header:
            return {"updated": False, "changes": []}

        current_pains_col = self.get_col_number(self.current_pains_header)
        ideal_future_col = self.get_col_number(self.ideal_future_header)
        past_solutions_col = self.get_col_number(self.past_solutions_header)
        flow_start_col = self.get_col_number("初回流入日")

        layout_changed = False
        changes: list[str] = []

        row1 = self.worksheet.row_values(1)
        row1_map = {idx + 1: value for idx, value in enumerate(row1)}
        if row1_map.get(current_pains_col, "") != QUALITATIVE_GROUP_NAME:
            layout_changed = True

        metadata = self.spreadsheet.fetch_sheet_metadata(
            {
                "includeGridData": False,
                "fields": "sheets(properties.sheetId,merges)",
            }
        )
        target_merge = {
            "sheetId": self.worksheet.id,
            "startRowIndex": 0,
            "endRowIndex": 1,
            "startColumnIndex": current_pains_col - 1,
            "endColumnIndex": past_solutions_col,
        }
        desired_merge_exists = False
        requests: list[dict[str, Any]] = []

        for sheet in metadata.get("sheets", []):
            if sheet.get("properties", {}).get("sheetId") != self.worksheet.id:
                continue
            for merge in sheet.get("merges", []):
                if merge.get("startRowIndex") != 0 or merge.get("endRowIndex") != 1:
                    continue
                if not ranges_overlap(
                    merge.get("startColumnIndex", 0),
                    merge.get("endColumnIndex", 0),
                    target_merge["startColumnIndex"],
                    target_merge["endColumnIndex"],
                ):
                    continue
                if merge == target_merge:
                    desired_merge_exists = True
                    continue
                requests.append({"unmergeCells": {"range": merge}})
                layout_changed = True
            break

        if not desired_merge_exists:
            requests.append({"mergeCells": {"range": target_merge, "mergeType": "MERGE_ALL"}})
            layout_changed = True

        black = {"red": 0, "green": 0, "blue": 0}
        thin = {"style": "SOLID", "width": 1, "color": black}
        medium = {"style": "SOLID_MEDIUM", "width": 2, "color": black}
        row_count = self.worksheet.row_count
        requests.extend(
            [
                {
                    "updateBorders": {
                        "range": {
                            "sheetId": self.worksheet.id,
                            "startRowIndex": 0,
                            "endRowIndex": row_count,
                            "startColumnIndex": ideal_future_col - 1,
                            "endColumnIndex": ideal_future_col,
                        },
                        "right": thin,
                    }
                },
                {
                    "updateBorders": {
                        "range": {
                            "sheetId": self.worksheet.id,
                            "startRowIndex": 0,
                            "endRowIndex": row_count,
                            "startColumnIndex": past_solutions_col - 1,
                            "endColumnIndex": past_solutions_col,
                        },
                        "left": thin,
                        "right": medium,
                    }
                },
            ]
        )

        if requests:
            self.spreadsheet.batch_update({"requests": requests})

        self.batch_update_with_retry(
            [
                {"range": f"{to_col_letter(current_pains_col)}1", "values": [[QUALITATIVE_GROUP_NAME]]},
                {"range": f"{to_col_letter(flow_start_col)}1", "values": [["流入情報"]]},
            ]
        )

        if layout_changed:
            changes.append("U〜W を `定性情報` で結合し、W と X の境界線を修正")

        return {"updated": layout_changed, "changes": changes}

    def get_col_number(self, header: str) -> int:
        number = self.header_map.get(header)
        if not number:
            raise KeyError(f"CDP列が見つかりません: {header}")
        return number

    def batch_update_with_retry(self, updates: list[dict[str, Any]], retries: int = 3) -> None:
        last_error: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                self.worksheet.batch_update(updates, value_input_option="USER_ENTERED")
                return
            except Exception as exc:
                last_error = exc
                if attempt >= retries:
                    break
                time.sleep(attempt * 2)
        if last_error:
            raise last_error

    def should_skip_recent_row_state(self, sheet_row: int) -> bool:
        if self.force:
            return False
        row_state = (self.state.get("calls") or {}).get(f"row_{sheet_row}") or {}
        status = collapse_ws(row_state.get("status", ""))
        updated_at = parse_iso_datetime(row_state.get("updated_at", ""))
        if not status or not updated_at:
            return False
        elapsed_hours = max(0.0, (datetime.now() - updated_at).total_seconds() / 3600)
        if status == "error" and elapsed_hours < ROW_ERROR_COOLDOWN_HOURS:
            return True
        if status == "low_confidence" and elapsed_hours < ROW_LOW_CONFIDENCE_COOLDOWN_HOURS:
            return True
        return False

    def cache_supports_target(self, target: TargetRow, insights: dict[str, Any]) -> bool:
        if self.force:
            return False
        if not insights:
            return False
        if self.past_solutions_header and not target.past_solutions:
            if not collapse_ws(insights.get("past_solutions_text", "")) and not insights.get("past_solutions"):
                return False
        return True

    def insert_columns_after(self, col_number: int, count: int) -> None:
        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "insertDimension": {
                            "range": {
                                "sheetId": self.worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": col_number,
                                "endIndex": col_number + count,
                            },
                            "inheritFromBefore": True,
                        }
                    }
                ]
            }
        )

    def delete_column(self, col_number: int) -> None:
        self.spreadsheet.batch_update(
            {
                "requests": [
                    {
                        "deleteDimension": {
                            "range": {
                                "sheetId": self.worksheet.id,
                                "dimension": "COLUMNS",
                                "startIndex": col_number - 1,
                                "endIndex": col_number,
                            }
                        }
                    }
                ]
            }
        )

    def load_targets(self) -> list[TargetRow]:
        last_row = len(self.worksheet.col_values(1))
        if last_row < 3:
            return []

        required_columns = [
            "顧客ID",
            "メールアドレス",
            "LINE名",
            "CR名",
            "初回流入経路",
            "担当営業",
            "LTV",
            "収録URL",
            self.current_pains_header,
            self.ideal_future_header,
        ]
        optional_columns = [header for header in [self.past_solutions_header] if header]
        columns_to_fetch = required_columns + optional_columns
        col_ranges = []
        for header in columns_to_fetch:
            col_ranges.append(
                f"{to_col_letter(self.get_col_number(header))}3:{to_col_letter(self.get_col_number(header))}{last_row}"
            )
        raw_columns = self.worksheet.batch_get(col_ranges, value_render_option="FORMATTED_VALUE")
        row_count = last_row - 2

        def flatten(column_values: list[list[str]]) -> list[str]:
            flat = [row[0] if row else "" for row in column_values]
            if len(flat) < row_count:
                flat.extend([""] * (row_count - len(flat)))
            return flat[:row_count]

        flattened = {
            header: flatten(values)
            for header, values in zip(columns_to_fetch, raw_columns)
        }

        targets: list[TargetRow] = []
        for idx in range(row_count):
            sheet_row = idx + 3
            recording_url = flattened["収録URL"][idx].strip()
            if self.row and sheet_row != self.row:
                continue
            if self.should_skip_recent_row_state(sheet_row):
                continue
            if not extract_supported_recording_urls(recording_url):
                continue
            current_pains = flattened[self.current_pains_header][idx].strip()
            ideal_future = flattened[self.ideal_future_header][idx].strip()
            past_solutions = (
                flattened.get(self.past_solutions_header, [""] * row_count)[idx].strip()
                if self.past_solutions_header
                else ""
            )
            filled_states = [bool(current_pains), bool(ideal_future)]
            if self.past_solutions_header:
                filled_states.append(bool(past_solutions))
            if not self.force and all(filled_states):
                continue
            targets.append(
                TargetRow(
                    sheet_row=sheet_row,
                    customer_id=flattened["顧客ID"][idx].strip(),
                    email=flattened["メールアドレス"][idx].strip(),
                    line_name=flattened["LINE名"][idx].strip(),
                    cr_name=flattened["CR名"][idx].strip(),
                    first_route=flattened["初回流入経路"][idx].strip(),
                    salesperson=flattened["担当営業"][idx].strip(),
                    ltv=flattened["LTV"][idx].strip(),
                    recording_url=recording_url,
                    current_pains=current_pains,
                    ideal_future=ideal_future,
                    past_solutions=past_solutions,
                )
            )

        targets.sort(key=lambda row: row.sheet_row, reverse=True)
        return targets[: self.limit]

    def load_cached_result(self, call_result_id: str) -> dict[str, Any] | None:
        cache_path = cache_path_for(call_result_id)
        if not cache_path.exists():
            return None
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def save_cached_result(self, call_result_id: str, payload: dict[str, Any]) -> None:
        cache_path = cache_path_for(call_result_id)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def build_sheet_updates(self, target: TargetRow, insights: dict[str, Any]) -> list[dict[str, Any]]:
        updates: list[dict[str, Any]] = []

        def queue(header: str, value: str) -> None:
            if not value:
                return
            col_number = self.header_map.get(header)
            if not col_number:
                return
            updates.append(
                {
                    "range": f"{to_col_letter(col_number)}{target.sheet_row}",
                    "values": [[value]],
                }
            )

        if self.force or not target.current_pains:
            queue(self.current_pains_header, insights.get("current_pains_text", ""))
        if self.force or not target.ideal_future:
            queue(
                self.ideal_future_header,
                insights.get("ideal_future_text", insights.get("goals_text", "")),
            )
        if self.past_solutions_header and (self.force or not target.past_solutions):
            queue(
                self.past_solutions_header,
                insights.get(
                    "past_solutions_text",
                    join_items_for_cell(insights.get("past_solutions", [])),
                ),
            )
        if updates and "最終更新日" in self.header_map:
            queue("最終更新日", datetime.now().strftime("%Y/%m/%d"))
        return updates

    def sync(self) -> dict[str, Any]:
        schema_result = self.ensure_sheet_schema()
        targets = self.load_targets()
        if not targets:
            summary = {
                "status": "success",
                "checked": 0,
                "updated": 0,
                "skipped": 0,
                "errors": 0,
                "message": "対象行なし",
            }
            if schema_result.get("changes"):
                summary["schema_changes"] = schema_result["changes"]
            self.state["last_run"] = now_iso()
            save_json(STATE_PATH, self.state)
            return summary

        updates: list[dict[str, Any]] = []
        stats = {
            "status": "success",
            "checked": len(targets),
            "updated": 0,
            "skipped": 0,
            "cached": 0,
            "partial_errors": 0,
            "errors": 0,
            "partial_errors_detail": [],
            "errors_detail": [],
        }

        pending_rows = 0

        def flush_updates() -> None:
            nonlocal updates, pending_rows
            if not updates:
                return
            if not self.dry_run:
                self.batch_update_with_retry(updates)
            updates = []
            pending_rows = 0
            self.state["last_run"] = now_iso()
            save_json(STATE_PATH, self.state)

        with ExitStack() as stack:
            ailead: AileadClient | None = None

            def get_ailead() -> AileadClient:
                nonlocal ailead
                if ailead is None:
                    ailead = stack.enter_context(
                        AileadClient(profile=self.profile, headless=self.headless)
                    )
                return ailead

            for target in targets:
                try:
                    per_recording_insights: list[dict[str, Any]] = []
                    per_recording_errors: list[dict[str, Any]] = []
                    recording_urls = extract_supported_recording_urls(target.recording_url)
                    if not recording_urls:
                        raise ValueError("収録URLから対応URLを抽出できません")

                    for recording_url in recording_urls:
                        record_key = recording_cache_key(recording_url)
                        source = detect_recording_source(recording_url)
                        try:
                            cache = self.load_cached_result(record_key)
                            if cache and self.cache_supports_target(target, cache.get("insights") or {}):
                                insights = cache["insights"]
                                stats["cached"] += 1
                            else:
                                if source == "ailead":
                                    package = get_ailead().fetch_call_package(recording_url)
                                    prompt_payload = build_prompt_payload(package, target)
                                    insights = summarize_insights(prompt_payload)
                                    cache = {
                                        "recording_key": record_key,
                                        "recording_url": recording_url,
                                        "recording_source": source,
                                        "fetched_at": now_iso(),
                                        "target_snapshot": {
                                            "sheet_row": target.sheet_row,
                                            "customer_id": target.customer_id,
                                            "email": target.email,
                                            "line_name": target.line_name,
                                            "cr_name": target.cr_name,
                                            "first_route": target.first_route,
                                            "salesperson": target.salesperson,
                                            "ltv": target.ltv,
                                        },
                                        "metadata": {
                                            "call_title": collapse_ws((package.get("callResult") or {}).get("callTitle", "")),
                                            "start_datetime": (package.get("callResult") or {}).get("startDatetime", ""),
                                            "duration": (package.get("callResult") or {}).get("duration", 0),
                                            "participants": [
                                                {
                                                    "name": collapse_ws(x.get("participantName", "")),
                                                }
                                                for x in ((package.get("callResult") or {}).get("callParticipants") or [])
                                            ],
                                        },
                                        "call_summary": (package.get("callSummary") or {}).get("callSummary") or {},
                                        "transcript_length": len(build_transcript_text(package.get("callResult") or {})),
                                        "transcript_preview": build_transcript_text(package.get("callResult") or {})[:4000],
                                        "insights": insights,
                                    }
                                elif source in {"youtube", "loom"}:
                                    video_result = fetch_video_package(recording_url)
                                    prompt_payload = build_prompt_payload_from_video_result(video_result, target)
                                    insights = summarize_insights(prompt_payload)
                                    transcript_text = collapse_ws(
                                        video_result.get("transcript_summary", "") or video_result.get("transcript_text", "")
                                    )
                                    cache = {
                                        "recording_key": record_key,
                                        "recording_url": recording_url,
                                        "recording_source": source,
                                        "fetched_at": now_iso(),
                                        "target_snapshot": {
                                            "sheet_row": target.sheet_row,
                                            "customer_id": target.customer_id,
                                            "email": target.email,
                                            "line_name": target.line_name,
                                            "cr_name": target.cr_name,
                                            "first_route": target.first_route,
                                            "salesperson": target.salesperson,
                                            "ltv": target.ltv,
                                        },
                                        "metadata": {
                                            "call_title": collapse_ws(video_result.get("title", "")),
                                            "start_datetime": "",
                                            "duration": video_result.get("duration", 0),
                                            "participants": [],
                                        },
                                        "call_summary": {
                                            "description": collapse_ws(video_result.get("transcript_summary", "")),
                                            "keywords": [],
                                            "topics": [],
                                        },
                                        "transcript_length": len(transcript_text),
                                        "transcript_preview": transcript_text[:4000],
                                        "insights": insights,
                                    }
                                else:
                                    raise ValueError(f"未対応の収録URLです: {recording_url}")
                                self.save_cached_result(record_key, cache)

                            per_recording_insights.append(insights)
                            self.state["calls"][record_key] = {
                                "status": "low_confidence" if insights.get("confidence") == "low" else "updated",
                                "updated_at": now_iso(),
                                "sheet_row": target.sheet_row,
                                "recording_url": recording_url,
                                "confidence": insights.get("confidence", ""),
                            }
                        except Exception as exc:
                            per_recording_errors.append(
                                {
                                    "recording_url": recording_url,
                                    "source": source,
                                    "error": str(exc),
                                }
                            )
                            self.state["calls"][record_key] = {
                                "status": "error",
                                "updated_at": now_iso(),
                                "sheet_row": target.sheet_row,
                                "recording_url": recording_url,
                                "error": str(exc),
                            }
                            continue

                    if per_recording_errors:
                        stats["partial_errors"] += len(per_recording_errors)
                        stats["partial_errors_detail"].append(
                            {
                                "sheet_row": target.sheet_row,
                                "recording_urls": recording_urls,
                                "errors": per_recording_errors,
                            }
                        )

                    if not per_recording_insights:
                        raise RuntimeError("有効な収録データを1件も取得できませんでした")

                    insights = combine_insights(per_recording_insights)
                    if insights.get("confidence") == "low":
                        stats["skipped"] += 1
                        self.state["calls"][f"row_{target.sheet_row}"] = {
                            "status": "low_confidence",
                            "updated_at": now_iso(),
                            "sheet_row": target.sheet_row,
                            "recording_urls": recording_urls,
                            "source_count": len(recording_urls),
                            "usable_source_count": len(per_recording_insights),
                            "error_count": len(per_recording_errors),
                            "confidence": insights.get("confidence", ""),
                        }
                        continue

                    row_updates = self.build_sheet_updates(target, insights)
                    if row_updates:
                        updates.extend(row_updates)
                        pending_rows += 1
                        stats["updated"] += 1
                        row_status = "updated"
                    else:
                        stats["skipped"] += 1
                        row_status = "already_filled"

                    if per_recording_errors and row_status == "updated":
                        row_status = "partial_updated"
                    elif per_recording_errors and row_status == "already_filled":
                        row_status = "partial_already_filled"

                    self.state["calls"][f"row_{target.sheet_row}"] = {
                        "status": row_status,
                        "updated_at": now_iso(),
                        "sheet_row": target.sheet_row,
                        "recording_urls": recording_urls,
                        "source_count": len(recording_urls),
                        "usable_source_count": len(per_recording_insights),
                        "error_count": len(per_recording_errors),
                        "confidence": insights.get("confidence", ""),
                    }

                    if pending_rows >= WRITE_FLUSH_ROW_COUNT:
                        flush_updates()
                except Exception as exc:
                    stats["errors"] += 1
                    stats["errors_detail"].append(
                        {
                            "sheet_row": target.sheet_row,
                            "recording_url": target.recording_url,
                            "error": str(exc),
                        }
                    )
                    row_key = recording_cache_key(target.recording_url) or f"row_{target.sheet_row}"
                    self.state["calls"][row_key] = {
                        "status": "error",
                        "updated_at": now_iso(),
                        "sheet_row": target.sheet_row,
                        "recording_url": target.recording_url,
                        "error": str(exc),
                    }

        self.state["last_run"] = now_iso()
        flush_updates()
        save_json(STATE_PATH, self.state)

        if stats["errors"]:
            stats["status"] = "partial_success" if (stats["updated"] or stats["skipped"]) else "error"
        if schema_result.get("changes"):
            stats["schema_changes"] = schema_result["changes"]
        if self.dry_run:
            stats["pending_updates"] = len(updates)
        return stats

    def fetch_url(self, recording_url: str) -> dict[str, Any]:
        recording_urls = extract_supported_recording_urls(recording_url)
        if not recording_urls:
            raise ValueError(f"未対応の収録URLです: {recording_url}")
        dummy = TargetRow(
            sheet_row=0,
            customer_id="",
            email="",
            line_name="",
            cr_name="",
            first_route="",
            salesperson="",
            ltv="",
            recording_url=recording_url,
            current_pains="",
            ideal_future="",
            past_solutions="",
        )
        per_url_results: list[dict[str, Any]] = []
        per_url_insights: list[dict[str, Any]] = []
        per_url_errors: list[dict[str, Any]] = []

        with ExitStack() as stack:
            ailead: AileadClient | None = None

            def get_ailead() -> AileadClient:
                nonlocal ailead
                if ailead is None:
                    ailead = stack.enter_context(
                        AileadClient(profile=self.profile, headless=self.headless)
                    )
                return ailead

            for one_url in recording_urls:
                source = detect_recording_source(one_url)
                try:
                    if source == "ailead":
                        package = get_ailead().fetch_call_package(one_url)
                        payload = build_prompt_payload(package, dummy)
                        metadata = {
                            "call_title": collapse_ws((package.get("callResult") or {}).get("callTitle", "")),
                            "duration": (package.get("callResult") or {}).get("duration", 0),
                        }
                        transcript_preview = build_transcript_text(package.get("callResult") or {})[:4000]
                        record_id = package.get("callResultId")
                    elif source in {"youtube", "loom"}:
                        package = fetch_video_package(one_url)
                        payload = build_prompt_payload_from_video_result(package, dummy)
                        metadata = {
                            "call_title": collapse_ws(package.get("title", "")),
                            "duration": package.get("duration", 0),
                        }
                        transcript_preview = collapse_ws(
                            package.get("transcript_summary", "") or package.get("transcript_text", "")
                        )[:4000]
                        record_id = recording_cache_key(one_url)
                    else:
                        raise ValueError(f"未対応の収録URLです: {one_url}")

                    insights = summarize_insights(payload)
                    per_url_insights.append(insights)
                    per_url_results.append(
                        {
                            "recording_url": one_url,
                            "source": source,
                            "call_result_id": record_id,
                            "metadata": metadata,
                            "transcript_preview": transcript_preview,
                            "insights": insights,
                        }
                    )
                except Exception as exc:
                    per_url_errors.append(
                        {
                            "recording_url": one_url,
                            "source": source,
                            "error": str(exc),
                        }
                    )

        if not per_url_insights:
            raise RuntimeError("有効な収録データを1件も取得できませんでした")

        insights = combine_insights(per_url_insights)
        return {
            "recording_urls": recording_urls,
            "source_count": len(recording_urls),
            "usable_source_count": len(per_url_results),
            "error_count": len(per_url_errors),
            "sources": per_url_results,
            "insights": insights,
            "errors": per_url_errors,
        }

    def status(self) -> dict[str, Any]:
        last_row = len(self.worksheet.col_values(1))
        if last_row < 3:
            data_rows = 0
            url_count = 0
            pain_count = 0
            ideal_future_count = 0
            past_solutions_count = 0
        else:
            row_count = last_row - 2
            col_names = ["収録URL", self.current_pains_header, self.ideal_future_header]
            if self.past_solutions_header:
                col_names.append(self.past_solutions_header)
            ranges = [
                f"{to_col_letter(self.get_col_number(col))}3:{to_col_letter(self.get_col_number(col))}{last_row}"
                for col in col_names
            ]
            fetched = self.worksheet.batch_get(ranges, value_render_option="FORMATTED_VALUE")
            flattened = []
            for col in fetched:
                values = [row[0] if row else "" for row in col]
                if len(values) < row_count:
                    values.extend([""] * (row_count - len(values)))
                flattened.append(values[:row_count])
            url_count = sum(1 for x in flattened[0] if x.strip())
            pain_count = sum(1 for x in flattened[1] if x.strip())
            ideal_future_count = sum(1 for x in flattened[2] if x.strip())
            past_solutions_count = sum(1 for x in flattened[3] if x.strip()) if self.past_solutions_header else 0
            data_rows = row_count

        cache_files = list(CACHE_DIR.glob("*.json"))
        row_states = [
            value
            for key, value in (self.state.get("calls") or {}).items()
            if str(key).startswith("row_")
        ]
        row_status_counts = Counter(collapse_ws(item.get("status", "")) or "unknown" for item in row_states)
        return {
            "data_rows": data_rows,
            "recording_urls": url_count,
            "current_pains_filled": pain_count,
            "ideal_future_filled": ideal_future_count,
            "past_solutions_filled": past_solutions_count,
            "cache_files": len(cache_files),
            "row_state_count": len(row_states),
            "row_status_counts": dict(row_status_counts),
            "last_run": self.state.get("last_run", ""),
        }

    def load_analysis_rows(self) -> list[dict[str, Any]]:
        last_row = len(self.worksheet.col_values(1))
        if last_row < 3:
            return []

        row_count = last_row - 2
        columns = [
            "顧客ID",
            "CR名",
            "初回流入経路",
            "LTV",
            "収録URL",
            self.current_pains_header,
            self.ideal_future_header,
        ]
        if self.past_solutions_header:
            columns.append(self.past_solutions_header)

        ranges = [
            f"{to_col_letter(self.get_col_number(col))}3:{to_col_letter(self.get_col_number(col))}{last_row}"
            for col in columns
        ]
        fetched = self.worksheet.batch_get(ranges, value_render_option="FORMATTED_VALUE")

        flattened: dict[str, list[str]] = {}
        for col_name, col_values in zip(columns, fetched):
            values = [row[0] if row else "" for row in col_values]
            if len(values) < row_count:
                values.extend([""] * (row_count - len(values)))
            flattened[col_name] = values[:row_count]

        rows: list[dict[str, Any]] = []
        for idx in range(row_count):
            current_pains = flattened[self.current_pains_header][idx].strip()
            ideal_future = flattened[self.ideal_future_header][idx].strip()
            past_solutions = (
                flattened.get(self.past_solutions_header, [""] * row_count)[idx].strip()
                if self.past_solutions_header
                else ""
            )
            raw_recording_value = flattened["収録URL"][idx].strip()
            recording_urls = extract_supported_recording_urls(raw_recording_value)
            if not recording_urls:
                continue
            if not any([current_pains, ideal_future, past_solutions]):
                continue

            ltv_text = flattened["LTV"][idx].strip()
            rows.append(
                {
                    "sheet_row": idx + 3,
                    "customer_id": flattened["顧客ID"][idx].strip(),
                    "cr_name": flattened["CR名"][idx].strip(),
                    "first_route": flattened["初回流入経路"][idx].strip(),
                    "ltv_text": ltv_text,
                    "ltv_value": parse_yen_amount(ltv_text),
                    "recording_url": recording_urls[-1],
                    "recording_url_count": len(recording_urls),
                    "current_pains": current_pains,
                    "ideal_future": ideal_future,
                    "past_solutions": past_solutions,
                }
            )
        return rows

    def analyze(
        self,
        output_path: Path = ANALYSIS_PATH,
        markdown_output_path: Path | None = ANALYSIS_MARKDOWN_PATH,
    ) -> dict[str, Any]:
        status_snapshot = self.status()
        rows = self.load_analysis_rows()
        positive_rows = [row for row in rows if row.get("ltv_value") is not None and row["ltv_value"] > 0]
        sorted_positive = sorted(positive_rows, key=lambda row: int(row["ltv_value"]))

        segmentation_mode = "ltv_percentile"
        high_threshold = percentile_value([int(row["ltv_value"]) for row in sorted_positive], 0.75)
        low_threshold = percentile_value([int(row["ltv_value"]) for row in sorted_positive], 0.25)

        if len(sorted_positive) < 6 or high_threshold is None or low_threshold is None or high_threshold <= low_threshold:
            segmentation_mode = "rank_fallback"
            take_n = max(1, len(sorted_positive) // 3) if sorted_positive else 0
            low_rows = sorted_positive[:take_n]
            high_rows = sorted_positive[-take_n:] if take_n else []
        else:
            low_rows = [row for row in sorted_positive if int(row["ltv_value"]) <= int(low_threshold)]
            high_rows = [row for row in sorted_positive if int(row["ltv_value"]) >= int(high_threshold)]

        non_conversion_rows = [row for row in rows if row.get("ltv_value") in (None, 0) or int(row["ltv_value"]) <= 0]

        report = {
            "generated_at": now_iso(),
            "source": {
                "sheet_id": CDP_SHEET_ID,
                "tab_name": CDP_TAB_NAME,
            },
            "coverage": {
                "recording_url_rows": status_snapshot.get("recording_urls", 0),
                "current_pains_filled_total": status_snapshot.get("current_pains_filled", 0),
                "ideal_future_filled_total": status_snapshot.get("ideal_future_filled", 0),
                "past_solutions_filled_total": status_snapshot.get("past_solutions_filled", 0),
                "rows_with_recording_and_qualitative": len(rows),
                "positive_ltv_rows": len(sorted_positive),
                "non_conversion_rows": len(non_conversion_rows),
                "multi_recording_rows": sum(1 for row in rows if int(row.get("recording_url_count", 1)) >= 2),
            },
            "segmentation": {
                "mode": segmentation_mode,
                "low_ltv_max": low_threshold,
                "high_ltv_min": high_threshold,
            },
            "segments": {
                "high_ltv": build_segment_summary(high_rows, sort_key="ltv_value", descending=True),
                "low_ltv": build_segment_summary(low_rows, sort_key="ltv_value", descending=False),
                "non_conversion": build_segment_summary(non_conversion_rows, sort_key="sheet_row", descending=True),
            },
        }

        if output_path:
            save_json(output_path, report)
        if markdown_output_path:
            markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_output_path.write_text(render_analysis_markdown(report), encoding="utf-8")
        return report

    def backfill(self, max_batches: int) -> dict[str, Any]:
        totals = {
            "status": "success",
            "batches": 0,
            "checked": 0,
            "updated": 0,
            "skipped": 0,
            "cached": 0,
            "partial_errors": 0,
            "errors": 0,
            "batch_summaries": [],
        }
        for batch_index in range(1, max_batches + 1):
            summary = self.sync()
            totals["batches"] += 1
            for key in ["checked", "updated", "skipped", "cached", "partial_errors", "errors"]:
                totals[key] += int(summary.get(key, 0) or 0)
            totals["batch_summaries"].append(
                {
                    "batch": batch_index,
                    "status": summary.get("status", "unknown"),
                    "checked": summary.get("checked", 0),
                    "updated": summary.get("updated", 0),
                    "skipped": summary.get("skipped", 0),
                    "errors": summary.get("errors", 0),
                }
            )
            if summary.get("status") == "error" and not summary.get("updated") and not summary.get("skipped"):
                totals["status"] = "partial_success" if totals["updated"] or totals["skipped"] else "error"
            elif summary.get("status") == "partial_success":
                totals["status"] = "partial_success"

            if int(summary.get("checked", 0) or 0) == 0:
                totals["message"] = "対象行なし"
                break
            if int(summary.get("checked", 0) or 0) < self.limit:
                totals["message"] = "対象行を一巡"
                break
        else:
            totals["message"] = "max_batches に到達"
        return totals


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AILEAD 面談データから CDP 定性欄を補完する")
    parser.add_argument("--account", default="kohara", help="sheets_manager のアカウント名")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="1回で処理する最大件数")
    parser.add_argument("--force", action="store_true", help="既存の定性情報があっても上書きする")
    parser.add_argument("--dry-run", action="store_true", help="書き込みをせず更新対象だけ確認する")
    parser.add_argument("--profile", default=None, help="Chrome プロファイル名（Default / Profile 9 など）")
    parser.add_argument("--row", type=int, default=None, help="特定行だけ処理する（シート行番号）")
    parser.add_argument("--headful", action="store_true", help="AILEAD ブラウザを headless でなく起動する")

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("sync", help="CDP の対象行を処理する")
    backfill_parser = subparsers.add_parser("backfill", help="CDP の対象行を複数バッチで進める")
    backfill_parser.add_argument("--max-batches", type=int, default=6, help="最大バッチ数")
    subparsers.add_parser("ensure-schema", help="CDP の定性列を `理想の未来` 構成へ整える")
    fetch_parser = subparsers.add_parser("fetch", help="1件以上の収録URLを抽出して JSON を表示する")
    fetch_parser.add_argument("recording_url", help="AILEAD / YouTube / Loom の収録URL")
    subparsers.add_parser("status", help="CDP とローカルキャッシュの状態を表示する")
    analyze_parser = subparsers.add_parser("analyze", help="LTV 別に面談定性を比較して JSON を出力する")
    analyze_parser.add_argument("--output", default=str(ANALYSIS_PATH), help="分析結果の出力先 JSON")
    analyze_parser.add_argument(
        "--markdown-output",
        default=str(ANALYSIS_MARKDOWN_PATH),
        help="分析サマリの出力先 Markdown",
    )
    subparsers.add_parser("bootstrap-session", help="AILEAD セッションを取得して保存する")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.command == "bootstrap-session":
        with AileadClient(profile=args.profile, headless=not args.headful):
            print(json.dumps({"status": "success", "message": "AILEAD session saved"}, ensure_ascii=False))
        return

    syncer = CDPInterviewSync(
        account=args.account,
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        profile=args.profile,
        headless=not args.headful,
        row=args.row,
    )

    if args.command == "ensure-schema":
        with interview_sync_lock(args.command):
            result = syncer.ensure_sheet_schema()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "sync":
        with interview_sync_lock(args.command):
            result = syncer.sync()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "backfill":
        with interview_sync_lock(args.command):
            result = syncer.backfill(max_batches=args.max_batches)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "fetch":
        result = syncer.fetch_url(args.recording_url)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "status":
        result = syncer.status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.command == "analyze":
        with interview_sync_lock(args.command):
            result = syncer.analyze(
                output_path=Path(args.output) if args.output else ANALYSIS_PATH,
                markdown_output_path=Path(args.markdown_output) if args.markdown_output else ANALYSIS_MARKDOWN_PATH,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return


if __name__ == "__main__":
    try:
        main()
    except ExecutionLockError as exc:
        print(
            json.dumps(
                {
                    "status": "locked",
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        raise SystemExit(2)
