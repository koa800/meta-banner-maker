#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional


PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_DIR / "System" / "data" / "ai_router"
HANDOFF_DIR = RUNTIME_DIR / "handoffs"
STATE_FILE = RUNTIME_DIR / "state.json"
WORK_INDEX_FILE = RUNTIME_DIR / "work_index.json"
SESSION_LINKS_FILE = RUNTIME_DIR / "session_links.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"
CURRENT_WORK_MIRROR_FILE = RUNTIME_DIR / "current_work.md"
LEGACY_ROOT_HANDOFF_FILE = PROJECT_DIR / ".ai_handoff.md"
LEGACY_OUTPUT_HANDOFF_FILE = PROJECT_DIR / "Master" / "output" / "ai_handoff.md"
LEGACY_HOME_STATE_FILE = Path.home() / ".ai_state.json"

SECTION_KEYS = {
    "目的": "purpose",
    "確定事項": "confirmed",
    "完了したこと": "completed",
    "未完了": "remaining",
    "判断とその理由（最重要）": "decisions",
    "参照先": "references",
    "変更したファイル": "changed_files",
    "次の担当へ": "next",
}
SECTION_TITLES = {value: key for key, value in SECTION_KEYS.items()}

CONTINUATION_MARKERS = {
    "続けて",
    "進めて",
    "この件",
    "この件で",
    "その件",
    "さっきの",
    "前の続き",
    "前回の続き",
    "同じ件",
}

CAPABILITY_PATTERNS = {
    "browser_required": re.compile(
        r"ブラウザ|Looker|Chrome|MCP|DOM|スクリーンショット|スクショ|画面確認|ページを開|クリック|browse|open page|screenshot",
        re.IGNORECASE,
    ),
    "ui_verification_required": re.compile(
        r"画面確認|遷移|見て|確認して|実挙動|クリック|ログイン|スクショ|DOM|UI",
        re.IGNORECASE,
    ),
    "code_edit_required": re.compile(
        r"実装|修正|追加|改善|リファクタ|バグ|コード|script|スクリプト|git|コミット|テスト|build|デプロイ|ファイル",
        re.IGNORECASE,
    ),
    "external_ui_write_required": re.compile(
        r"登録|入力|作成|追加して|追加してください|紐づけ|設定|更新して|変更して|送信|アップロード|会員サイト",
        re.IGNORECASE,
    ),
    "analysis_only": re.compile(
        r"分析|整理|調査|俯瞰|提案|教えて|どう思う|レビュー|洞察",
        re.IGNORECASE,
    ),
}


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def parse_json_arg(raw: str, default: Any) -> Any:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    decoder = json.JSONDecoder()
    try:
        value, _ = decoder.raw_decode(text)
        return value
    except json.JSONDecodeError:
        for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
            try:
                return json.loads(line)
            except Exception:
                continue
    return default


def append_event(event_type: str, **payload: Any) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_iso(), "event": event_type}
    record.update(payload)
    with EVENTS_FILE.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    HANDOFF_DIR.mkdir(parents=True, exist_ok=True)

    if not STATE_FILE.exists():
        state = {
            "current_tool": "none",
            "current_work_id": "",
            "switched_at": "",
            "last_prompt": "",
        }
        if LEGACY_HOME_STATE_FILE.exists():
            legacy = load_json(LEGACY_HOME_STATE_FILE, {})
            if isinstance(legacy, dict):
                state["current_tool"] = legacy.get("current_tool", state["current_tool"])
                state["switched_at"] = legacy.get("switched_at", state["switched_at"])
        write_json(STATE_FILE, state)

    for path in (WORK_INDEX_FILE, SESSION_LINKS_FILE):
        if not path.exists():
            write_json(path, {})

    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("")


def load_state() -> dict[str, Any]:
    ensure_runtime()
    state = load_json(STATE_FILE, {})
    if not isinstance(state, dict):
        state = {}
    state.setdefault("current_tool", "none")
    state.setdefault("current_work_id", "")
    state.setdefault("switched_at", "")
    state.setdefault("last_prompt", "")
    return state


def save_state(state: dict[str, Any]) -> None:
    write_json(STATE_FILE, state)


def load_work_index() -> dict[str, Any]:
    ensure_runtime()
    data = load_json(WORK_INDEX_FILE, {})
    return data if isinstance(data, dict) else {}


def save_work_index(data: dict[str, Any]) -> None:
    write_json(WORK_INDEX_FILE, data)


def load_session_links() -> dict[str, Any]:
    ensure_runtime()
    data = load_json(SESSION_LINKS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_session_links(data: dict[str, Any]) -> None:
    write_json(SESSION_LINKS_FILE, data)


def normalize(text: str) -> str:
    return " ".join(str(text or "").split())


def clean_prompt(prompt: str) -> str:
    text = normalize(prompt)
    patterns = [
        r"^ユーザーからの指示:\s*",
        r"^(?:この件|このタスク|この仕事)\s*(?:を)?",
        r"(?:お願いします|お願い|して|してください|下さい)$",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text)
    return normalize(text)


def prompt_title(prompt: str) -> str:
    text = clean_prompt(prompt)
    return text[:100] if text else "未分類の仕事"


def handoff_digest(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


def handoff_path_for(work_id: str) -> Path:
    return HANDOFF_DIR / f"{work_id}.md"


def handoff_template(title: str, work_id: str) -> str:
    return "\n".join(
        [
            "# 引き継ぎメモ",
            "",
            "## 目的",
            title,
            "",
            "## 確定事項",
            "",
            "## 完了したこと",
            "",
            "## 未完了",
            "- 未着手",
            "",
            "## 判断とその理由（最重要）",
            "",
            "## 参照先",
            f"- work_id: {work_id}",
            "",
            "## 変更したファイル",
            "",
            "## 次の担当へ",
            f"- この仕事の正本 handoff は `System/data/ai_router/handoffs/{work_id}.md`",
            "",
        ]
    )


def mirror_text_to_current_work(text: str) -> None:
    CURRENT_WORK_MIRROR_FILE.parent.mkdir(parents=True, exist_ok=True)
    CURRENT_WORK_MIRROR_FILE.write_text(text)


def load_current_work_mirror_text() -> str:
    if CURRENT_WORK_MIRROR_FILE.exists():
        return CURRENT_WORK_MIRROR_FILE.read_text(errors="replace")
    if LEGACY_ROOT_HANDOFF_FILE.exists():
        return LEGACY_ROOT_HANDOFF_FILE.read_text(errors="replace")
    if LEGACY_OUTPUT_HANDOFF_FILE.exists():
        return LEGACY_OUTPUT_HANDOFF_FILE.read_text(errors="replace")
    return ""


def parse_handoff_text(text: str) -> dict[str, Any]:
    sections: dict[str, Any] = {
        "purpose": "",
        "confirmed": [],
        "completed": [],
        "remaining": [],
        "decisions": [],
        "references": [],
        "changed_files": [],
        "next": [],
    }
    current_key = ""
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current_key = SECTION_KEYS.get(line[3:].strip(), "")
            continue
        if not current_key:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if current_key == "purpose":
            sections["purpose"] = f"{sections['purpose']} {stripped}".strip()
            continue
        if stripped.startswith("- "):
            sections[current_key].append(stripped[2:].strip())
        elif sections[current_key]:
            sections[current_key][-1] = f"{sections[current_key][-1]} {stripped}".strip()
    return sections


def compact_text_item(text: str, max_chars: int = 220) -> str:
    text = normalize(text)
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def rewrite_snapshot_item(text: str, target: str) -> str:
    text = normalize(text)
    if not text:
        return ""
    text = re.sub(r"^[\-\*\u30fb]+\s*", "", text)
    text = re.sub(
        r"^(?:目的|確定事項|完了したこと|未完了|判断とその理由（最重要）|判断と理由|参照先|変更したファイル|次の担当へ)\s*[:：-]\s*",
        "",
        text,
    )
    if target in {"remaining", "next"}:
        text = re.sub(r"^(?:残件|未完了|次にやること|次の担当へ)\s*[:：-]\s*", "", text)
    elif target == "completed":
        text = re.sub(r"^(?:完了|完了したこと|対応済み|実施済み)\s*[:：-]\s*", "", text)
    return compact_text_item(text, max_chars=180 if target in {"remaining", "next"} else 220)


def item_priority(text: str, target: str) -> int:
    lowered = item_key(text)
    score = 0
    if target in {"remaining", "next"}:
        if any(token in lowered for token in ("確認", "実地", "追加", "接続", "同期", "検証", "昇格", "移行", "review", "promote")):
            score += 4
        if any(token in lowered for token in ("未", "残", "まだ", "次", "必要", "対応")):
            score += 3
    elif target == "completed":
        if any(token in lowered for token in ("追加", "更新", "実装", "対応", "作成", "検証", "同期", "導入")):
            score += 3
    elif target == "decisions":
        if any(token in lowered for token in ("ため", "ので", "方針", "優先", "避け", "残す", "理由")):
            score += 4
    elif target == "references":
        if "work_id:" in lowered:
            score += 5
        if "session_id:" in lowered:
            score += 4
        if "system/" in lowered or "project/" in lowered or "master/" in lowered:
            score += 2
    elif target == "changed_files":
        if re.search(r"\.(py|sh|md|json|ya?ml|toml)", lowered):
            score += 5
    if "`" in text:
        score += 1
    if len(text) <= 140:
        score += 1
    return score


def prioritize_items(items: list[str], target: str, limit: int, prefer_recent: bool = False) -> list[str]:
    chosen: dict[str, tuple[int, int, str]] = {}
    for idx, raw in enumerate(items):
        text = rewrite_snapshot_item(raw, target)
        if not text:
            continue
        key = item_key(text)
        if not key:
            continue
        recency = -idx if prefer_recent else idx
        candidate = (item_priority(text, target), recency, text)
        current = chosen.get(key)
        if current is None or candidate[0] > current[0] or (candidate[0] == current[0] and candidate[1] < current[1]):
            chosen[key] = candidate
    ranked = sorted(chosen.values(), key=lambda item: (-item[0], item[1], item[2]))
    return [text for _, _, text in ranked[:limit]]


def dedupe_items(items: list[str], limit: int, max_chars: int = 220, prefer_recent: bool = False) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    source = list(reversed(items)) if prefer_recent else list(items)
    for raw in source:
        text = compact_text_item(raw, max_chars=max_chars)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
        if len(out) >= limit:
            break
    if prefer_recent:
        out.reverse()
    return out


def item_key(text: str) -> str:
    return normalize(text).lower()


def is_reference_item(text: str) -> bool:
    lowered = item_key(text)
    return bool(
        re.search(r"https?://", text)
        or re.search(r"`[^`]+`", text)
        or any(token in lowered for token in ("work_id:", "session_id:", "alias:", "system/", "project/", "master/"))
    )


def is_changed_file_item(text: str) -> bool:
    lowered = item_key(text)
    return bool(
        re.search(r"`[^`]+\.(?:py|sh|md|json|ya?ml|toml)`", text)
        or re.search(r"(system|project|master)/.+\.(py|sh|md|json|ya?ml|toml)", lowered)
    )


def classify_snapshot_item(text: str, fallback: str) -> str:
    lowered = item_key(text)
    open_markers = ("未", "まだ", "次に", "残", "確認", "実地", "自動化", "進める", "追加する")
    done_markers = ("完了", "追加し", "追加した", "更新し", "更新した", "実装", "対応", "作成", "変更し", "変更した")
    if is_reference_item(text):
        return "references" if fallback != "changed_files" else fallback
    if is_changed_file_item(text):
        return "changed_files"
    if any(token in lowered for token in ("判断", "理由", "方針", "ため", "なので", "優先", "避け", "残す")):
        return "decisions"
    if fallback == "completed":
        return "remaining" if any(token in lowered for token in open_markers) else "completed"
    if fallback in {"remaining", "next"}:
        if any(token in lowered for token in done_markers) and not any(token in lowered for token in open_markers):
            return "completed"
        return fallback
    if any(token in lowered for token in open_markers):
        return "remaining" if fallback != "next" else "next"
    if any(token in lowered for token in done_markers):
        return "completed"
    return fallback


def remove_resolved_open_items(items: list[str], completed: list[str]) -> list[str]:
    completed_keys = {item_key(item) for item in completed if item_key(item)}
    out: list[str] = []
    for item in items:
        key = item_key(item)
        if not key:
            continue
        if key == "未着手" and (completed or len(items) > 1):
            continue
        if any(key == done or key in done or done in key for done in completed_keys):
            continue
        out.append(item)
    return out


def canonicalize_snapshot(work: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    rebuilt: dict[str, Any] = {
        "purpose": snapshot.get("purpose") or work.get("purpose") or work.get("title", ""),
        "confirmed": [],
        "completed": [],
        "remaining": [],
        "decisions": [],
        "references": [],
        "changed_files": [],
        "next": [],
    }

    for section in ("confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        for raw in list(snapshot.get(section) or []):
            text = normalize(raw)
            if not text:
                continue
            target = classify_snapshot_item(text, section)
            rebuilt[target].append(text)

    current_batch_id = normalize(work.get("current_batch_id", ""))
    current_batch_summary = normalize(work.get("current_batch_summary", ""))
    current_batch_item_title = normalize(work.get("current_batch_item_title", ""))
    if current_batch_item_title:
        batch_next = f"current batch item を進める: {current_batch_item_title}"
        if current_batch_id:
            batch_next = f"{batch_next} ({current_batch_id})"
        rebuilt["remaining"].insert(0, batch_next)
        rebuilt["next"].insert(0, batch_next)
    if current_batch_id:
        batch_ref = f"current batch: {current_batch_id}"
        if current_batch_summary:
            batch_ref = f"{batch_ref} / {compact_text_item(current_batch_summary, max_chars=150)}"
        rebuilt["references"].append(batch_ref)

    rebuilt["completed"] = prioritize_items(rebuilt["completed"], "completed", limit=10, prefer_recent=True)
    rebuilt["remaining"] = remove_resolved_open_items(prioritize_items(rebuilt["remaining"], "remaining", limit=6), rebuilt["completed"])
    rebuilt["next"] = remove_resolved_open_items(prioritize_items(rebuilt["next"], "next", limit=5), rebuilt["completed"])
    rebuilt["confirmed"] = prioritize_items(rebuilt["confirmed"], "confirmed", limit=6)
    rebuilt["decisions"] = prioritize_items(rebuilt["decisions"], "decisions", limit=6, prefer_recent=True)
    rebuilt["references"] = prioritize_items(rebuilt["references"], "references", limit=6)
    rebuilt["changed_files"] = prioritize_items(rebuilt["changed_files"], "changed_files", limit=6, prefer_recent=True)

    if not rebuilt["remaining"] and rebuilt["next"]:
        rebuilt["remaining"] = rebuilt["next"][:3]
    if not rebuilt["next"] and rebuilt["remaining"]:
        rebuilt["next"] = rebuilt["remaining"][:3]

    load_summary = normalize(work.get("last_session_load_summary", ""))
    if load_summary and all(load_summary not in item for item in rebuilt["decisions"]):
        rebuilt["decisions"].append(f"直近 session load: {load_summary}。current work handoff を正本に継続する")
        rebuilt["decisions"] = dedupe_items(rebuilt["decisions"], limit=6, prefer_recent=True)

    work_id = work["work_id"]
    handoff_rel_path = f"System/data/ai_router/handoffs/{work_id}.md"
    handoff_ref = f"`{handoff_rel_path}`"
    if f"work_id: {work_id}" not in rebuilt["references"]:
        rebuilt["references"].insert(0, f"work_id: {work_id}")
    if all(handoff_ref not in item for item in rebuilt["next"]):
        rebuilt["next"].insert(0, f"この仕事の正本 handoff は {handoff_ref}")
    rebuilt["references"] = dedupe_items(rebuilt["references"], limit=6)
    rebuilt["next"] = dedupe_items(rebuilt["next"], limit=5)
    rebuilt["purpose"] = compact_text_item(rebuilt["purpose"], max_chars=240)
    return rebuilt


def render_handoff_text(work: dict[str, Any], snapshot: dict[str, Any]) -> str:
    work_id = work["work_id"]
    sections = canonicalize_snapshot(work, snapshot)

    lines = ["# 引き継ぎメモ", ""]
    for key in ("purpose", "confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        lines.append(f"## {SECTION_TITLES[key]}")
        if key == "purpose":
            if sections["purpose"]:
                lines.append(sections["purpose"])
        else:
            for item in sections[key]:
                lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def detect_capabilities(prompt: str) -> dict[str, bool]:
    text = clean_prompt(prompt)
    capabilities = {name: bool(pattern.search(text)) for name, pattern in CAPABILITY_PATTERNS.items()}
    if capabilities["browser_required"]:
        capabilities["ui_verification_required"] = True
    if capabilities["external_ui_write_required"] and capabilities["browser_required"]:
        capabilities["ui_verification_required"] = True
    if capabilities["code_edit_required"]:
        capabilities["analysis_only"] = False
    return capabilities


def choose_tool(capabilities: dict[str, bool], default_tool: str = "") -> str:
    if default_tool in {"codex", "claude"}:
        if capabilities["browser_required"] or capabilities["external_ui_write_required"] or capabilities["ui_verification_required"]:
            return "claude"
        return default_tool
    if capabilities["browser_required"] or capabilities["external_ui_write_required"] or capabilities["ui_verification_required"]:
        return "claude"
    return "codex"


def similarity_score(prompt: str, work: dict[str, Any]) -> float:
    text = clean_prompt(prompt)
    if not text:
        return 0.0
    candidates = [
        normalize(work.get("title", "")),
        normalize(work.get("purpose", "")),
        normalize(work.get("latest_preview", "")),
        normalize(work.get("last_prompt", "")),
    ]
    best = 0.0
    for candidate in candidates:
        if not candidate:
            continue
        if text in candidate or candidate in text:
            best = max(best, 0.95)
        else:
            best = max(best, SequenceMatcher(None, text, candidate).ratio())
    return best


def should_stick_to_current(prompt: str, current_work: Optional[dict[str, Any]]) -> bool:
    if not current_work:
        return False
    text = clean_prompt(prompt)
    if not text:
        return True
    if text in CONTINUATION_MARKERS:
        return True
    if any(marker in text for marker in CONTINUATION_MARKERS):
        return True
    return similarity_score(text, current_work) >= 0.72


def resolve_existing_work(prompt: str, state: dict[str, Any], works: dict[str, Any]) -> Optional[dict[str, Any]]:
    current_work_id = state.get("current_work_id", "")
    current_work = works.get(current_work_id) if current_work_id else None
    if should_stick_to_current(prompt, current_work):
        return current_work

    text = clean_prompt(prompt)
    if not text:
        return current_work

    scored: list[tuple[float, str, dict[str, Any]]] = []
    for work_id, work in works.items():
        if not isinstance(work, dict):
            continue
        scored.append((similarity_score(text, work), work_id, work))

    scored.sort(key=lambda item: (item[0], normalize(item[2].get("updated_at", ""))), reverse=True)
    if scored and scored[0][0] >= 0.82:
        return scored[0][2]
    return None


def work_search_text(work: dict[str, Any]) -> str:
    parts = [
        work.get("work_id", ""),
        work.get("title", ""),
        work.get("purpose", ""),
        work.get("latest_preview", ""),
        work.get("last_prompt", ""),
        work.get("current_batch_id", ""),
        work.get("current_batch_title", ""),
        work.get("current_batch_item_id", ""),
        work.get("current_batch_item_title", ""),
    ]
    for key in ("confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        parts.extend(work.get(key) or [])
    return "\n".join(normalize(part).lower() for part in parts if normalize(part))


def work_summary(work: dict[str, Any]) -> str:
    title = normalize(work.get("title", ""))
    purpose = normalize(work.get("purpose", ""))
    latest_preview = normalize(work.get("latest_preview", ""))
    remaining = [normalize(item) for item in (work.get("remaining") or []) if normalize(item)]
    completed = [normalize(item) for item in (work.get("completed") or []) if normalize(item)]
    prefixes: list[str] = []
    if work.get("compaction_required"):
        prefixes.append("[compact]")
    if work.get("current_batch_id"):
        prefixes.append("[batch]")
    prefix = (" ".join(prefixes) + " ") if prefixes else ""

    if title and purpose and title != purpose:
        base = f"{prefix}{title} / {purpose}"
    else:
        base = prefix + (title or purpose or latest_preview or str(work.get("work_id", "")))

    if remaining:
        return f"{base} / 残: {remaining[0]}"[:140]
    if completed:
        return f"{base} / 完: {completed[-1]}"[:140]
    return base[:140]


def work_match_score(query: str, work: dict[str, Any]) -> tuple[float, str]:
    text = normalize(query).lower()
    if not text:
        return 0.0, "none"

    work_id = str(work.get("work_id", "")).lower()
    title = normalize(work.get("title", "")).lower()
    purpose = normalize(work.get("purpose", "")).lower()
    latest_preview = normalize(work.get("latest_preview", "")).lower()
    last_prompt = normalize(work.get("last_prompt", "")).lower()
    search_text = work_search_text(work)

    if work_id == text:
        return 1.0, "work_id_exact"
    if work_id.startswith(text):
        return 0.99, "work_id_prefix"
    if title and title == text:
        return 0.98, "title_exact"
    if purpose and purpose == text:
        return 0.97, "purpose_exact"
    if latest_preview and latest_preview == text:
        return 0.96, "preview_exact"
    if title and text in title:
        return 0.95, "title_contains"
    if purpose and text in purpose:
        return 0.94, "purpose_contains"
    if latest_preview and text in latest_preview:
        return 0.93, "preview_contains"
    if last_prompt and text in last_prompt:
        return 0.92, "prompt_contains"
    if search_text and text in search_text:
        return 0.90, "text_contains"

    ratio = similarity_score(query, work)
    if ratio >= 0.72:
        return ratio, "similarity"
    return 0.0, "none"


def work_updated_sort_value(work: dict[str, Any]) -> str:
    return normalize(work.get("updated_at", "")) or normalize(work.get("created_at", ""))


def build_work_candidate(
    work: dict[str, Any],
    current_work_id: str,
    score: float = 0.0,
    match_type: str = "",
) -> dict[str, Any]:
    work_id = str(work.get("work_id", ""))
    return {
        "work_id": work_id,
        "title": work.get("title", ""),
        "purpose": work.get("purpose", ""),
        "summary": work_summary(work),
        "updated_at": work_updated_sort_value(work),
        "last_tool": work.get("last_tool") or work.get("default_tool") or "",
        "status": work.get("status", ""),
        "current": work_id == current_work_id,
        "score": round(score, 4),
        "match_type": match_type,
        "handoff_path": work.get("handoff_path", ""),
    }


def find_work_candidates(
    query: str,
    works: dict[str, Any],
    current_work_id: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    text = normalize(query)
    rows: list[tuple[float, str, dict[str, Any]]] = []

    for work_id, work in works.items():
        if not isinstance(work, dict):
            continue
        if not text:
            rank = 1.0 if work_id == current_work_id else 0.5
            match_type = "current" if work_id == current_work_id else "recent"
        else:
            rank, match_type = work_match_score(text, work)
            if rank <= 0:
                continue
        rows.append((rank, work_updated_sort_value(work), build_work_candidate(work, current_work_id, rank, match_type)))

    if text:
        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    else:
        rows.sort(key=lambda item: (1 if item[2]["current"] else 0, item[1]), reverse=True)
    return [item[2] for item in rows[:limit]]


def resolve_work_query(
    query: str,
    state: dict[str, Any],
    works: dict[str, Any],
    limit: int = 5,
) -> dict[str, Any]:
    current_work_id = state.get("current_work_id", "")
    text = normalize(query)

    if not text:
        current_work = works.get(current_work_id) if current_work_id else None
        selected = build_work_candidate(current_work, current_work_id, 1.0, "current") if isinstance(current_work, dict) else {}
        return {
            "query": text,
            "current_work_id": current_work_id,
            "selected_work_id": selected.get("work_id", ""),
            "selected_tool": selected.get("last_tool", ""),
            "match_type": selected.get("match_type", ""),
            "candidate_count": 1 if selected else 0,
            "selected_work": selected,
            "candidates": [selected] if selected else [],
            "ambiguous": False,
        }

    candidates = find_work_candidates(text, works, current_work_id, limit=limit)
    if not candidates:
        return {
            "query": text,
            "current_work_id": current_work_id,
            "selected_work_id": "",
            "selected_tool": "",
            "match_type": "none",
            "candidate_count": 0,
            "selected_work": {},
            "candidates": [],
            "ambiguous": False,
        }

    top = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    exact_match_types = {"work_id_exact", "work_id_prefix", "title_exact", "purpose_exact", "preview_exact"}

    selected: dict[str, Any] = {}
    if top["match_type"] in exact_match_types:
        selected = top
    elif top["match_type"] in {"title_contains", "purpose_contains", "preview_contains", "prompt_contains", "text_contains"}:
        if len(candidates) == 1 or top["score"] - second_score >= 0.08:
            selected = top
    elif top["match_type"] == "similarity":
        if top["score"] >= 0.88 and (len(candidates) == 1 or top["score"] - second_score >= 0.08):
            selected = top

    return {
        "query": text,
        "current_work_id": current_work_id,
        "selected_work_id": selected.get("work_id", ""),
        "selected_tool": selected.get("last_tool", ""),
        "match_type": selected.get("match_type", ""),
        "candidate_count": len(candidates),
        "selected_work": selected,
        "candidates": candidates,
        "ambiguous": not bool(selected) and len(candidates) > 1,
    }


def create_work(prompt: str, selected_tool: str, capabilities: dict[str, bool]) -> dict[str, Any]:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    title = prompt_title(prompt)
    work_id = f"{stamp}-{abs(hash(title)) % 0xFFFFF:05x}"
    handoff_path = handoff_path_for(work_id)
    text = handoff_template(title, work_id)
    handoff_path.write_text(text)
    mirror_text_to_current_work(text)
    return {
        "work_id": work_id,
        "title": title,
        "default_tool": selected_tool,
        "last_tool": selected_tool,
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "handoff_path": str(handoff_path),
        "latest_preview": title,
        "last_prompt": clean_prompt(prompt),
        "capabilities": capabilities,
        "purpose": title,
        "confirmed": [],
        "completed": [],
        "remaining": ["未着手"],
        "decisions": [],
        "references": [f"work_id: {work_id}"],
        "changed_files": [],
        "next": [f"最新 handoff は System/data/ai_router/handoffs/{work_id}.md を参照"],
        "last_handoff_sha1": handoff_digest(text),
        "last_session_load": {},
        "last_session_load_summary": "",
        "compaction_required": False,
        "compaction_summary": "",
        "compaction_requested_at": "",
        "compaction_source_session_id": "",
        "compaction_source_tool": "",
        "compaction_handoff_sha1": "",
        "batch_ids": [],
        "current_batch_id": "",
        "current_batch_title": "",
        "current_batch_summary": "",
        "current_batch_item_id": "",
        "current_batch_item_title": "",
        "current_batch_item_status": "",
    }


def sync_work_to_root(work: dict[str, Any]) -> str:
    path = Path(work["handoff_path"])
    if path.exists():
        text = path.read_text(errors="replace")
    else:
        text = handoff_template(work.get("title", "未分類の仕事"), work["work_id"])
        path.write_text(text)
    mirror_text_to_current_work(text)
    return text


def update_work_with_session_data(work: dict[str, Any], session_data: dict[str, Any], session_id: str, tool: str, handoff_text: str) -> dict[str, Any]:
    if not isinstance(session_data, dict):
        return work

    metrics = session_data.get("metrics")
    if isinstance(metrics, dict) and metrics:
        work["last_session_metrics"] = metrics

    load = session_data.get("load")
    if isinstance(load, dict) and load:
        work["last_session_load"] = load
        work["last_session_load_summary"] = str(load.get("summary") or "")
        if load.get("should_compact"):
            work["compaction_required"] = True
            work["compaction_summary"] = str(load.get("summary") or "")
            work["compaction_requested_at"] = now_iso()
            work["compaction_source_session_id"] = session_id
            work["compaction_source_tool"] = tool
            work["compaction_handoff_sha1"] = handoff_digest(handoff_text)

    start = session_data.get("start")
    end = session_data.get("end")
    if start:
        work["last_session_start"] = start
    if end:
        work["last_session_end"] = end

    preview = normalize(session_data.get("preview", ""))
    if preview:
        work["latest_preview"] = prompt_title(preview)
    return work


def sync_text_to_work(work: dict[str, Any], text: str) -> dict[str, Any]:
    snapshot = parse_handoff_text(text)
    current_digest = handoff_digest(text)
    work["updated_at"] = now_iso()
    work["purpose"] = snapshot.get("purpose") or work.get("purpose") or work.get("title", "")
    for key in ("confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        work[key] = list(snapshot.get(key) or [])
    if work.get("purpose"):
        work["latest_preview"] = work["purpose"][:100]
    if work.get("compaction_required") and current_digest and current_digest != work.get("compaction_handoff_sha1", ""):
        work["compaction_required"] = False
        work["compaction_summary"] = ""
        work["compaction_requested_at"] = ""
        work["compaction_source_session_id"] = ""
        work["compaction_source_tool"] = ""
        work["compaction_handoff_sha1"] = ""
    elif not work.get("compaction_required") and not work.get("compaction_requested_at"):
        work["compaction_source_tool"] = ""
    work["last_handoff_sha1"] = current_digest
    return work


def sync_root_to_work(work: dict[str, Any]) -> dict[str, Any]:
    text = load_current_work_mirror_text()
    if not text:
        text = handoff_template(work.get("title", "未分類の仕事"), work["work_id"])
        mirror_text_to_current_work(text)
    handoff_path = Path(work["handoff_path"])
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(text)
    return sync_text_to_work(work, text)


def status_payload() -> dict[str, Any]:
    state = load_state()
    works = load_work_index()
    current_work = works.get(state.get("current_work_id", ""), {})
    payload = dict(state)
    payload["current_work"] = current_work if isinstance(current_work, dict) else {}
    payload["handoff_path"] = current_work.get("handoff_path", "") if isinstance(current_work, dict) else ""
    return payload


def cmd_status(_: argparse.Namespace) -> int:
    print(json.dumps(status_payload(), ensure_ascii=False))
    return 0


def cmd_list_works(args: argparse.Namespace) -> int:
    state = load_state()
    works = load_work_index()
    candidates = find_work_candidates(args.query or "", works, state.get("current_work_id", ""), limit=args.limit)

    if not works:
        print("登録された仕事はまだありません。")
        return 0
    if args.query and not candidates:
        print(f"一致する仕事はありません: {normalize(args.query)}")
        return 0

    print("current  updated_at    tool     work_id                 summary")
    print("-" * 120)
    for candidate in candidates:
        mark = "*" if candidate["current"] else " "
        updated_at = candidate["updated_at"]
        if updated_at:
            try:
                updated_at = datetime.fromisoformat(updated_at.replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")
            except ValueError:
                updated_at = updated_at[:16]
        else:
            updated_at = "-"
        tool = candidate["last_tool"] or "-"
        summary = candidate["summary"] or candidate["title"] or candidate["work_id"]
        print(f"{mark:<8} {updated_at:<13} {tool:<8} {candidate['work_id']:<23} {summary}")
    return 0


def cmd_resolve_work(args: argparse.Namespace) -> int:
    state = load_state()
    works = load_work_index()
    payload = resolve_work_query(args.query or "", state, works, limit=args.limit)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_prepare(args: argparse.Namespace) -> int:
    ensure_runtime()
    state = load_state()
    works = load_work_index()
    prompt = args.prompt or ""
    capabilities = detect_capabilities(prompt)

    work = resolve_existing_work(prompt, state, works) if prompt or state.get("current_work_id") else None
    if not work and prompt:
        selected_tool = args.tool if args.tool in {"codex", "claude"} else choose_tool(capabilities)
        work = create_work(prompt, selected_tool, capabilities)
        works[work["work_id"]] = work
        append_event("work_created", work_id=work["work_id"], title=work["title"], tool=selected_tool)
    elif work:
        work["updated_at"] = now_iso()
        work["last_prompt"] = clean_prompt(prompt) or work.get("last_prompt", "")
        work["capabilities"] = capabilities if prompt else work.get("capabilities", {})
        works[work["work_id"]] = work

    selected_tool = args.tool if args.tool in {"codex", "claude"} else choose_tool(capabilities, work.get("default_tool", "") if work else "")

    if work:
        work["last_tool"] = selected_tool
        work.setdefault("default_tool", selected_tool)
        work["updated_at"] = now_iso()
        works[work["work_id"]] = work
        sync_work_to_root(work)
        state["current_work_id"] = work["work_id"]
    state["current_tool"] = selected_tool
    state["switched_at"] = now_iso()
    state["last_prompt"] = clean_prompt(prompt)
    save_state(state)
    save_work_index(works)

    append_event(
        "launch_prepared",
        work_id=state.get("current_work_id", ""),
        selected_tool=selected_tool,
        forced_tool=args.tool,
        prompt=prompt_title(prompt),
    )

    payload = {
        "selected_tool": selected_tool,
        "current_work_id": state.get("current_work_id", ""),
        "capabilities": capabilities,
        "current_work": works.get(state.get("current_work_id", ""), {}) if state.get("current_work_id") else {},
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def cmd_activate_work(args: argparse.Namespace) -> int:
    ensure_runtime()
    state = load_state()
    works = load_work_index()
    work = works.get(args.work_id)
    if not isinstance(work, dict):
        print(json.dumps({"error": f"unknown work_id: {args.work_id}"}, ensure_ascii=False))
        return 1

    selected_tool = args.tool if args.tool in {"codex", "claude"} else work.get("last_tool") or work.get("default_tool") or "codex"
    work["last_tool"] = selected_tool
    work["updated_at"] = now_iso()
    works[args.work_id] = work

    state["current_work_id"] = args.work_id
    state["current_tool"] = selected_tool
    state["switched_at"] = now_iso()
    if args.prompt:
        state["last_prompt"] = clean_prompt(args.prompt)
    save_state(state)
    save_work_index(works)
    sync_work_to_root(work)
    append_event("work_activated", work_id=args.work_id, tool=selected_tool)
    print(json.dumps({"current_work_id": args.work_id, "selected_tool": selected_tool, "current_work": work}, ensure_ascii=False))
    return 0


def cmd_activate_session(args: argparse.Namespace) -> int:
    ensure_runtime()
    links = load_session_links()
    works = load_work_index()
    state = load_state()

    link = links.get(args.session_id, {}) if isinstance(links.get(args.session_id, {}), dict) else {}
    work_id = link.get("work_id", "")
    work = works.get(work_id) if work_id else None
    if not isinstance(work, dict):
        prompt = args.preview or ""
        work = resolve_existing_work(prompt, state, works)
    if not work and args.preview:
        capabilities = detect_capabilities(args.preview)
        selected_tool = args.tool if args.tool in {"codex", "claude"} else choose_tool(capabilities)
        work = create_work(args.preview, selected_tool, capabilities)
        works[work["work_id"]] = work
        append_event("work_created_for_session", work_id=work["work_id"], session_id=args.session_id, tool=selected_tool)
    elif not work and state.get("current_work_id"):
        work = works.get(state["current_work_id"])

    if not isinstance(work, dict):
        print(json.dumps({"error": "no work available for session"}, ensure_ascii=False))
        return 1

    selected_tool = args.tool if args.tool in {"codex", "claude"} else link.get("tool") or work.get("last_tool") or work.get("default_tool") or "codex"
    work["last_tool"] = selected_tool
    work["updated_at"] = now_iso()
    works[work["work_id"]] = work
    save_work_index(works)

    state["current_work_id"] = work["work_id"]
    state["current_tool"] = selected_tool
    state["switched_at"] = now_iso()
    state["last_prompt"] = clean_prompt(args.preview or "")
    save_state(state)
    sync_work_to_root(work)
    append_event("session_activated", work_id=work["work_id"], session_id=args.session_id, tool=selected_tool)

    print(json.dumps({"current_work_id": work["work_id"], "selected_tool": selected_tool, "current_work": work}, ensure_ascii=False))
    return 0


def cmd_sync_root(args: argparse.Namespace) -> int:
    ensure_runtime()
    state = load_state()
    works = load_work_index()
    work_id = args.work_id or state.get("current_work_id", "")
    work = works.get(work_id)
    if not isinstance(work, dict):
        print(json.dumps({"error": "no current work"}, ensure_ascii=False))
        return 1
    work = sync_root_to_work(work)
    works[work_id] = work
    save_work_index(works)
    append_event("handoff_synced", work_id=work_id)
    print(json.dumps({"current_work_id": work_id, "current_work": work}, ensure_ascii=False))
    return 0


def cmd_record_session(args: argparse.Namespace) -> int:
    ensure_runtime()
    state = load_state()
    works = load_work_index()
    links = load_session_links()
    session_data = load_json(Path(args.session_json[1:]), {}) if args.session_json.startswith("@") else None
    if session_data is None:
        session_data = parse_json_arg(args.session_json or "{}", {})
    work_id = state.get("current_work_id", "")
    work = works.get(work_id) if work_id else None
    if not isinstance(work, dict) and args.preview:
        capabilities = detect_capabilities(args.preview)
        selected_tool = args.tool if args.tool in {"codex", "claude"} else choose_tool(capabilities)
        work = create_work(args.preview, selected_tool, capabilities)
        works[work["work_id"]] = work
        work_id = work["work_id"]
        state["current_work_id"] = work_id
        save_state(state)
    if not isinstance(work, dict):
        print(json.dumps({"error": "no current work"}, ensure_ascii=False))
        return 1

    work["last_tool"] = args.tool
    work["last_session_id"] = args.session_id
    work["updated_at"] = now_iso()
    if args.preview:
        work["latest_preview"] = prompt_title(args.preview)
    work = update_work_with_session_data(
        work,
        session_data if isinstance(session_data, dict) else {},
        args.session_id,
        args.tool,
        load_current_work_mirror_text(),
    )
    works[work["work_id"]] = work
    save_work_index(works)

    links[args.session_id] = {
        "work_id": work["work_id"],
        "tool": args.tool,
        "preview": prompt_title(args.preview or work.get("latest_preview", "")),
        "updated_at": now_iso(),
    }
    save_session_links(links)
    append_event(
        "session_recorded",
        work_id=work["work_id"],
        session_id=args.session_id,
        tool=args.tool,
        compaction_required=bool(work.get("compaction_required")),
        load_summary=work.get("last_session_load_summary", ""),
    )
    print(json.dumps({"work_id": work["work_id"], "current_work": work}, ensure_ascii=False))
    return 0


def cmd_compact_handoff(args: argparse.Namespace) -> int:
    ensure_runtime()
    state = load_state()
    works = load_work_index()
    work_id = args.work_id or state.get("current_work_id", "")
    work = works.get(work_id)
    if not isinstance(work, dict):
        print(json.dumps({"error": "no current work"}, ensure_ascii=False))
        return 1

    is_current = work_id == state.get("current_work_id", "")
    if is_current:
        source_text = load_current_work_mirror_text()
    else:
        handoff_path = Path(work.get("handoff_path", ""))
        source_text = handoff_path.read_text(errors="replace") if handoff_path.exists() else ""

    if not source_text:
        source_text = handoff_template(work.get("title", "未分類の仕事"), work_id)

    compacted = render_handoff_text(work, parse_handoff_text(source_text))
    handoff_path = Path(work["handoff_path"])
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_path.write_text(compacted)
    if is_current:
        mirror_text_to_current_work(compacted)
    work = sync_text_to_work(work, compacted)
    works[work_id] = work
    save_work_index(works)
    append_event("handoff_compacted", work_id=work_id, is_current=is_current, compacted_lines=len(compacted.splitlines()))
    print(json.dumps({"work_id": work_id, "current_work": work, "compacted_lines": len(compacted.splitlines())}, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status")

    list_works = subparsers.add_parser("list-works")
    list_works.add_argument("--query", default="")
    list_works.add_argument("--limit", type=int, default=20)

    resolve_work = subparsers.add_parser("resolve-work")
    resolve_work.add_argument("--query", default="")
    resolve_work.add_argument("--limit", type=int, default=5)

    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--prompt", default="")
    prepare.add_argument("--tool", default="auto")

    activate_work = subparsers.add_parser("activate-work")
    activate_work.add_argument("--work-id", required=True)
    activate_work.add_argument("--tool", default="")
    activate_work.add_argument("--prompt", default="")

    activate_session = subparsers.add_parser("activate-session")
    activate_session.add_argument("--session-id", required=True)
    activate_session.add_argument("--tool", default="")
    activate_session.add_argument("--preview", default="")

    sync_root = subparsers.add_parser("sync-root")
    sync_root.add_argument("--work-id", default="")

    record_session = subparsers.add_parser("record-session")
    record_session.add_argument("--session-id", required=True)
    record_session.add_argument("--tool", required=True)
    record_session.add_argument("--preview", default="")
    record_session.add_argument("--session-json", default="{}")

    compact_handoff = subparsers.add_parser("compact-handoff")
    compact_handoff.add_argument("--work-id", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "status":
        return cmd_status(args)
    if args.command == "list-works":
        return cmd_list_works(args)
    if args.command == "resolve-work":
        return cmd_resolve_work(args)
    if args.command == "prepare":
        return cmd_prepare(args)
    if args.command == "activate-work":
        return cmd_activate_work(args)
    if args.command == "activate-session":
        return cmd_activate_session(args)
    if args.command == "sync-root":
        return cmd_sync_root(args)
    if args.command == "record-session":
        return cmd_record_session(args)
    if args.command == "compact-handoff":
        return cmd_compact_handoff(args)
    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
