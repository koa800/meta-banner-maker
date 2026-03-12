#!/usr/bin/env python3

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional
from urllib import error as urlerror
from urllib import request as urlrequest


PROJECT_DIR = Path(__file__).resolve().parents[2]
RUNTIME_DIR = PROJECT_DIR / "System" / "data" / "ai_router"
BATCH_INDEX_FILE = RUNTIME_DIR / "batch_index.json"
WORK_INDEX_FILE = RUNTIME_DIR / "work_index.json"
SKILL_CANDIDATE_INDEX_FILE = RUNTIME_DIR / "skill_candidate_index.json"
EVENTS_FILE = RUNTIME_DIR / "events.jsonl"


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def normalize(text: Any) -> str:
    return " ".join(str(text or "").split())


def compact_text(text: Any, limit: int = 160) -> str:
    value = normalize(text)
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


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


def append_event(event_type: str, **payload: Any) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    record = {"ts": now_iso(), "event": event_type}
    record.update(payload)
    with EVENTS_FILE.open("a") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def ensure_runtime() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not BATCH_INDEX_FILE.exists():
        write_json(BATCH_INDEX_FILE, {})
    if not WORK_INDEX_FILE.exists():
        write_json(WORK_INDEX_FILE, {})
    if not SKILL_CANDIDATE_INDEX_FILE.exists():
        write_json(SKILL_CANDIDATE_INDEX_FILE, {})
    if not EVENTS_FILE.exists():
        EVENTS_FILE.write_text("")


def load_batches() -> dict[str, Any]:
    ensure_runtime()
    data = load_json(BATCH_INDEX_FILE, {})
    return data if isinstance(data, dict) else {}


def save_batches(data: dict[str, Any]) -> None:
    write_json(BATCH_INDEX_FILE, data)


def load_works() -> dict[str, Any]:
    ensure_runtime()
    data = load_json(WORK_INDEX_FILE, {})
    return data if isinstance(data, dict) else {}


def save_works(data: dict[str, Any]) -> None:
    write_json(WORK_INDEX_FILE, data)


def load_skill_candidates() -> dict[str, Any]:
    ensure_runtime()
    data = load_json(SKILL_CANDIDATE_INDEX_FILE, {})
    return data if isinstance(data, dict) else {}


def save_skill_candidates(data: dict[str, Any]) -> None:
    write_json(SKILL_CANDIDATE_INDEX_FILE, data)


def make_batch_id(title: str) -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{abs(hash(normalize(title))) % 0xFFFFF:05x}"


def payload_preview(payload: Any, limit: int = 180) -> str:
    if isinstance(payload, (dict, list)):
        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    else:
        text = str(payload or "")
    return compact_text(text, limit=limit)


def parse_payload(raw: str) -> Any:
    text = raw or ""
    if text.startswith("@"):
        return load_json(Path(text[1:]), "")
    try:
        return json.loads(text)
    except Exception:
        return text


def stable_signature(payload: Any) -> str:
    try:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    except TypeError:
        serialized = str(payload)
    return hashlib.sha1(serialized.encode("utf-8", errors="ignore")).hexdigest()


def item_signature(title: str, payload: Any, source_ref: str = "", external_id: str = "") -> str:
    seed = {
        "external_id": normalize(external_id),
        "source_ref": normalize(source_ref),
        "title": normalize(title),
        "payload": payload,
    }
    return stable_signature(seed)


def resolve_project_path(raw: str) -> Path:
    path = Path(normalize(raw))
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def batch_source_files(batch: dict[str, Any]) -> list[Path]:
    source = normalize(batch.get("source", ""))
    if not source:
        return []
    if source.startswith("cmd:") or source.startswith("url:") or source.startswith("http://") or source.startswith("https://"):
        return []
    if any(token in source for token in "*?[]"):
        return sorted(path for path in PROJECT_DIR.glob(source) if path.is_file())
    path = resolve_project_path(source)
    if path.is_file():
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.jsonl"))
    return []


def raw_records_from_payload(payload: Any, source_ref: str, source_path: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    items = payload
    if isinstance(payload, dict) and isinstance(payload.get("items"), list):
        items = payload.get("items") or []
    elif not isinstance(payload, list):
        items = [payload]

    for idx, item in enumerate(items, start=1):
        if isinstance(item, dict):
            title = (
                item.get("title")
                or item.get("name")
                or item.get("prompt")
                or item.get("subject")
                or item.get("id")
                or payload_preview(item, limit=80)
            )
            external_id = item.get("external_id") or item.get("id") or ""
            inner_source_ref = item.get("source_ref") or item.get("url") or item.get("sheet_row") or source_ref
        else:
            title = payload_preview(item, limit=80) or f"item {idx}"
            external_id = ""
            inner_source_ref = source_ref
        records.append(
            {
                "title": str(title or f"item {idx}"),
                "payload": item,
                "source_ref": str(inner_source_ref or source_ref),
                "external_id": str(external_id or ""),
                "source_signature": item_signature(str(title or f"item {idx}"), item, source_ref=str(inner_source_ref or source_ref), external_id=str(external_id or "")),
                "source_path": source_path,
            }
        )
    return records


def parse_records_text(text: str, source_ref: str, source_path: str = "") -> list[dict[str, Any]]:
    body = str(text or "").strip()
    if not body:
        return []

    try:
        payload = json.loads(body)
    except Exception:
        payload = None

    if payload is not None:
        return raw_records_from_payload(payload, source_ref=source_ref, source_path=source_path)

    records: list[dict[str, Any]] = []
    for idx, raw_line in enumerate(body.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            payload = line
        records.extend(raw_records_from_payload(payload, source_ref=f"{source_ref}#L{idx}", source_path=source_path))
    return records


def load_batch_source_records(batch: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str], str]:
    source = normalize(batch.get("source", ""))
    if not source:
        return [], [], "source not set"

    if source.startswith("cmd:"):
        command = source[4:].strip()
        if not command:
            return [], [source], "empty command source"
        try:
            result = subprocess.run(
                command,
                cwd=str(PROJECT_DIR),
                shell=True,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return [], [source], "command timeout"
        if result.returncode != 0:
            error_text = normalize(result.stderr or result.stdout) or f"exit={result.returncode}"
            return [], [source], f"command failed / {compact_text(error_text, 160)}"
        return parse_records_text(result.stdout, source_ref=source, source_path=source), [source], ""

    if source.startswith("url:") or source.startswith("http://") or source.startswith("https://"):
        url = source[4:].strip() if source.startswith("url:") else source
        if not url:
            return [], [source], "empty url source"
        try:
            with urlrequest.urlopen(url, timeout=30) as response:
                body = response.read().decode("utf-8", errors="replace")
        except urlerror.URLError as exc:
            return [], [url], f"url fetch failed / {compact_text(str(exc), 160)}"
        return parse_records_text(body, source_ref=url, source_path=url), [url], ""

    files = batch_source_files(batch)
    if not files:
        return [], [], "source not found"

    records: list[dict[str, Any]] = []
    refs: list[str] = []
    for path in files:
        try:
            ref = str(path.relative_to(PROJECT_DIR))
        except ValueError:
            ref = str(path)
        refs.append(ref)
        records.extend(parse_jsonl_items(path))
    return records, refs, ""


def item_counts(batch: dict[str, Any]) -> dict[str, int]:
    counts = {"pending": 0, "running": 0, "completed": 0, "failed": 0}
    for item in batch.get("items", []) or []:
        status = str(item.get("status") or "pending")
        if status not in counts:
            status = "pending"
        counts[status] += 1
    counts["total"] = sum(counts.values())
    return counts


def batch_summary(batch: dict[str, Any]) -> str:
    counts = item_counts(batch)
    title = normalize(batch.get("title", "")) or str(batch.get("batch_id", ""))
    batch_type = normalize(batch.get("batch_type", ""))
    parts = [title]
    if batch_type:
        parts.append(batch_type)
    parts.append(f"{counts['pending']} pending")
    if counts["running"]:
        parts.append(f"{counts['running']} running")
    if counts["completed"]:
        parts.append(f"{counts['completed']} done")
    if counts["failed"]:
        parts.append(f"{counts['failed']} failed")
    return " / ".join(parts)[:180]


def update_batch_runtime(batch: dict[str, Any]) -> dict[str, Any]:
    counts = item_counts(batch)
    running = next((item for item in batch.get("items", []) if item.get("status") == "running"), {})
    batch.setdefault("source_last_synced_at", "")
    batch.setdefault("source_last_sync_summary", "")
    batch.setdefault("source_last_sync_files", [])
    batch["updated_at"] = now_iso()
    batch["counts"] = counts
    batch["summary"] = batch_summary(batch)
    batch["active_item_id"] = str(running.get("item_id") or "")
    batch["active_item_title"] = str(running.get("title") or "")
    if counts["total"] and counts["pending"] == 0 and counts["running"] == 0 and counts["failed"] == 0:
        batch["status"] = "completed"
    elif counts["running"] or counts["pending"] or counts["failed"]:
        batch["status"] = "active"
    else:
        batch["status"] = batch.get("status") or "draft"
    return batch


def ensure_work_batch_fields(work: dict[str, Any]) -> dict[str, Any]:
    work.setdefault("batch_ids", [])
    work.setdefault("current_batch_id", "")
    work.setdefault("current_batch_title", "")
    work.setdefault("current_batch_summary", "")
    work.setdefault("current_batch_item_id", "")
    work.setdefault("current_batch_item_title", "")
    work.setdefault("current_batch_item_status", "")
    return work


def attach_batch_to_work(
    works: dict[str, Any],
    batch: dict[str, Any],
    work_id: str,
    item: Optional[dict[str, Any]] = None,
    clear_item: bool = False,
) -> dict[str, Any]:
    work = works.get(work_id)
    if not isinstance(work, dict):
        return {}
    work = ensure_work_batch_fields(work)
    if batch["batch_id"] not in work["batch_ids"]:
        work["batch_ids"].append(batch["batch_id"])
    work["current_batch_id"] = batch["batch_id"]
    work["current_batch_title"] = batch.get("title", "")
    work["current_batch_summary"] = batch_summary(batch)
    if item:
        work["current_batch_item_id"] = str(item.get("item_id") or "")
        work["current_batch_item_title"] = str(item.get("title") or "")
        work["current_batch_item_status"] = str(item.get("status") or "")
    elif clear_item:
        work["current_batch_item_id"] = ""
        work["current_batch_item_title"] = ""
        work["current_batch_item_status"] = ""
    work["updated_at"] = now_iso()
    works[work_id] = work
    return work


def clear_batch_item_from_works(works: dict[str, Any], batch_id: str, item_id: str) -> None:
    for work_id, work in works.items():
        if not isinstance(work, dict):
            continue
        work = ensure_work_batch_fields(work)
        if work.get("current_batch_id") != batch_id:
            continue
        if item_id and work.get("current_batch_item_id") != item_id:
            continue
        work["current_batch_item_id"] = ""
        work["current_batch_item_title"] = ""
        work["current_batch_item_status"] = ""
        work["current_batch_summary"] = work.get("current_batch_summary", "")
        work["updated_at"] = now_iso()
        works[work_id] = work


def batch_search_text(batch: dict[str, Any]) -> str:
    parts = [
        batch.get("batch_id", ""),
        batch.get("title", ""),
        batch.get("batch_type", ""),
        batch.get("source", ""),
        batch.get("schema_hint", ""),
        batch.get("work_id", ""),
    ]
    for item in batch.get("items", []) or []:
        parts.extend(
            [
                item.get("item_id", ""),
                item.get("title", ""),
                item.get("source_ref", ""),
                item.get("external_id", ""),
                payload_preview(item.get("payload", ""), limit=120),
            ]
        )
    return "\n".join(normalize(part).lower() for part in parts if normalize(part))


def batch_match_score(query: str, batch: dict[str, Any]) -> tuple[float, str]:
    text = normalize(query).lower()
    if not text:
        return 0.0, "none"
    batch_id = str(batch.get("batch_id", "")).lower()
    title = normalize(batch.get("title", "")).lower()
    batch_type = normalize(batch.get("batch_type", "")).lower()
    source = normalize(batch.get("source", "")).lower()
    search_text = batch_search_text(batch)

    if batch_id == text:
        return 1.0, "batch_id_exact"
    if batch_id.startswith(text):
        return 0.99, "batch_id_prefix"
    if title and title == text:
        return 0.98, "title_exact"
    if title and text in title:
        return 0.95, "title_contains"
    if batch_type and text == batch_type:
        return 0.94, "type_exact"
    if batch_type and text in batch_type:
        return 0.92, "type_contains"
    if source and text in source:
        return 0.91, "source_contains"
    if search_text and text in search_text:
        return 0.9, "text_contains"

    ratio = max(
        SequenceMatcher(None, text, title or "").ratio(),
        SequenceMatcher(None, text, batch_type or "").ratio(),
        SequenceMatcher(None, text, source or "").ratio(),
    )
    if ratio >= 0.72:
        return ratio, "similarity"
    return 0.0, "none"


def build_batch_candidate(batch: dict[str, Any], score: float = 0.0, match_type: str = "") -> dict[str, Any]:
    counts = item_counts(batch)
    return {
        "batch_id": batch.get("batch_id", ""),
        "title": batch.get("title", ""),
        "batch_type": batch.get("batch_type", ""),
        "preferred_tool": batch.get("preferred_tool", ""),
        "status": batch.get("status", ""),
        "summary": batch_summary(batch),
        "updated_at": batch.get("updated_at", ""),
        "work_id": batch.get("work_id", ""),
        "counts": counts,
        "score": round(score, 4),
        "match_type": match_type,
        "active_item_id": batch.get("active_item_id", ""),
        "active_item_title": batch.get("active_item_title", ""),
    }


def find_batch_candidates(query: str, batches: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    text = normalize(query)
    rows: list[tuple[float, str, dict[str, Any]]] = []
    for batch_id, batch in batches.items():
        if not isinstance(batch, dict):
            continue
        if not text:
            rank = 1.0
            match_type = "recent"
        else:
            rank, match_type = batch_match_score(text, batch)
            if rank <= 0:
                continue
        rows.append((rank, normalize(batch.get("updated_at", "")), build_batch_candidate(batch, rank, match_type)))
    if text:
        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
    else:
        rows.sort(key=lambda item: item[1], reverse=True)
    return [row[2] for row in rows[:limit]]


def resolve_batch_query(query: str, batches: dict[str, Any], limit: int = 5) -> dict[str, Any]:
    text = normalize(query)
    if not text:
        candidates = find_batch_candidates("", batches, limit=limit)
        selected = candidates[0] if candidates else {}
        return {
            "query": text,
            "selected_batch_id": selected.get("batch_id", ""),
            "candidate_count": len(candidates),
            "selected_batch": selected,
            "candidates": candidates,
            "ambiguous": False,
        }
    candidates = find_batch_candidates(text, batches, limit=limit)
    if not candidates:
        return {
            "query": text,
            "selected_batch_id": "",
            "candidate_count": 0,
            "selected_batch": {},
            "candidates": [],
            "ambiguous": False,
        }
    top = candidates[0]
    second_score = candidates[1]["score"] if len(candidates) > 1 else 0.0
    selected: dict[str, Any] = {}
    if top["match_type"] in {"batch_id_exact", "batch_id_prefix", "title_exact", "type_exact"}:
        selected = top
    elif top["score"] >= 0.9 and (len(candidates) == 1 or top["score"] - second_score >= 0.08):
        selected = top
    return {
        "query": text,
        "selected_batch_id": selected.get("batch_id", ""),
        "candidate_count": len(candidates),
        "selected_batch": selected,
        "candidates": candidates,
        "ambiguous": not bool(selected) and len(candidates) > 1,
    }


def next_item_id(batch: dict[str, Any]) -> str:
    max_seq = 0
    for item in batch.get("items", []) or []:
        raw = str(item.get("item_id") or "")
        try:
            seq = int(raw.rsplit("-", 1)[-1])
        except ValueError:
            continue
        max_seq = max(max_seq, seq)
    return f"{batch['batch_id']}-{max_seq + 1:03d}"


def create_item(
    batch: dict[str, Any],
    title: str,
    payload: Any,
    source_ref: str = "",
    external_id: str = "",
    source_signature: str = "",
    source_path: str = "",
) -> dict[str, Any]:
    signature = normalize(source_signature) or item_signature(title, payload, source_ref=source_ref, external_id=external_id)
    return {
        "item_id": next_item_id(batch),
        "title": normalize(title) or payload_preview(payload, limit=80) or "untitled item",
        "payload": payload,
        "payload_preview": payload_preview(payload, limit=220),
        "source_ref": normalize(source_ref),
        "external_id": normalize(external_id),
        "source_signature": signature,
        "source_path": normalize(source_path),
        "status": "pending",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "attempts": 0,
        "result_summary": "",
        "result_ref": "",
        "error": "",
        "claimed_at": "",
        "claimed_by_work_id": "",
        "claimed_by_tool": "",
        "completed_at": "",
    }


def parse_jsonl_items(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    try:
        display_path = str(path.relative_to(PROJECT_DIR))
    except ValueError:
        display_path = str(path)
    for idx, raw_line in enumerate(path.read_text(errors="replace").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            payload = line
        if isinstance(payload, dict):
            title = (
                payload.get("title")
                or payload.get("name")
                or payload.get("prompt")
                or payload.get("subject")
                or payload.get("id")
                or payload_preview(payload, limit=80)
            )
            source_ref = payload.get("source_ref") or payload.get("url") or payload.get("sheet_row") or display_path
            external_id = payload.get("external_id") or payload.get("id") or ""
        else:
            title = payload_preview(payload, limit=80) or f"item {idx}"
            source_ref = display_path
            external_id = ""
        signature = item_signature(str(title or f"item {idx}"), payload, source_ref=str(source_ref or ""), external_id=str(external_id or ""))
        items.append(
            {
                "title": str(title or f"item {idx}"),
                "payload": payload,
                "source_ref": str(source_ref or ""),
                "external_id": str(external_id or ""),
                "source_signature": signature,
                "source_path": display_path,
            }
        )
    return items


def existing_item_signatures(batch: dict[str, Any]) -> set[str]:
    signatures: set[str] = set()
    for item in batch.get("items", []) or []:
        signature = normalize(item.get("source_signature", ""))
        if not signature:
            signature = item_signature(
                str(item.get("title") or ""),
                item.get("payload"),
                source_ref=str(item.get("source_ref") or ""),
                external_id=str(item.get("external_id") or ""),
            )
        if signature:
            signatures.add(signature)
    return signatures


def append_unique_items(batch: dict[str, Any], raws: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    imported: list[dict[str, Any]] = []
    skipped = 0
    signatures = existing_item_signatures(batch)
    for raw in raws:
        signature = normalize(raw.get("source_signature", "")) or item_signature(
            str(raw.get("title") or ""),
            raw.get("payload"),
            source_ref=str(raw.get("source_ref") or ""),
            external_id=str(raw.get("external_id") or ""),
        )
        if signature in signatures:
            skipped += 1
            continue
        item = create_item(
            batch,
            str(raw.get("title") or ""),
            raw.get("payload"),
            source_ref=str(raw.get("source_ref") or ""),
            external_id=str(raw.get("external_id") or ""),
            source_signature=signature,
            source_path=str(raw.get("source_path") or ""),
        )
        batch.setdefault("items", []).append(item)
        imported.append(item)
        signatures.add(signature)
    return imported, skipped


def update_source_sync_state(batch: dict[str, Any], refs: list[Any], imported_count: int, skipped_count: int, error: str = "") -> dict[str, Any]:
    file_refs: list[str] = []
    for ref in refs:
        if isinstance(ref, Path):
            try:
                file_refs.append(str(ref.relative_to(PROJECT_DIR)))
            except ValueError:
                file_refs.append(str(ref))
        else:
            file_refs.append(str(ref))
    batch["source_last_synced_at"] = now_iso()
    if error:
        batch["source_last_sync_summary"] = f"sync error / {error}"
    else:
        batch["source_last_sync_summary"] = f"{imported_count} imported / {skipped_count} skipped"
    batch["source_last_sync_files"] = file_refs[:20]
    return batch


def sync_batch_source(batch: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], int, list[str]]:
    raws, refs, error = load_batch_source_records(batch)
    if error:
        return update_source_sync_state(batch, refs, 0, 0, error=error), [], 0, refs

    imported, skipped = append_unique_items(batch, raws)
    batch = update_batch_runtime(batch)
    batch = update_source_sync_state(batch, refs, len(imported), skipped)
    return batch, imported, skipped, refs


def build_skill_candidate(batch: dict[str, Any]) -> dict[str, Any]:
    counts = item_counts(batch)
    completed_items = [item for item in batch.get("items", []) or [] if item.get("status") == "completed"]
    reasons: list[str] = []
    missing: list[str] = []

    if counts["completed"] >= 3:
        reasons.append(f"同型タスクの完了実績が {counts['completed']} 件ある")
    else:
        missing.append("完了済み item が 3 件未満")
    if normalize(batch.get("schema_hint", "")):
        reasons.append(f"schema_hint がある: {compact_text(batch.get('schema_hint', ''), 90)}")
    else:
        missing.append("schema_hint が未設定")
    if normalize(batch.get("source", "")):
        reasons.append(f"source がある: {compact_text(batch.get('source', ''), 90)}")
    else:
        missing.append("source が未設定")
    if normalize(batch.get("batch_type", "")):
        reasons.append(f"batch_type: {compact_text(batch.get('batch_type', ''), 60)}")

    status = "ready" if counts["completed"] >= 3 else "draft"
    examples = [
        {
            "item_id": str(item.get("item_id") or ""),
            "title": str(item.get("title") or ""),
            "result_summary": str(item.get("result_summary") or ""),
            "source_ref": str(item.get("source_ref") or ""),
        }
        for item in completed_items[-3:]
    ]
    summary = " / ".join(
        part
        for part in [
            normalize(batch.get("title", "")) or str(batch.get("batch_id", "")),
            f"{counts['completed']} done",
            reasons[0] if reasons else "",
            f"不足: {missing[0]}" if missing else "昇格候補 ready",
        ]
        if part
    )[:180]
    return {
        "candidate_id": f"skill-{batch.get('batch_id', '')}",
        "batch_id": batch.get("batch_id", ""),
        "work_id": batch.get("work_id", ""),
        "title": normalize(batch.get("title", "")) or str(batch.get("batch_id", "")),
        "status": status,
        "summary": summary,
        "completed_count": counts["completed"],
        "reasons": reasons,
        "missing_requirements": missing,
        "examples": examples,
        "updated_at": now_iso(),
    }


def sync_skill_candidate(batch: dict[str, Any]) -> dict[str, Any]:
    candidates = load_skill_candidates()
    existing = candidates.get(batch.get("batch_id", ""), {}) if isinstance(candidates.get(batch.get("batch_id", ""), {}), dict) else {}
    if item_counts(batch)["completed"] <= 0 and not existing:
        return {}
    candidate = build_skill_candidate(batch)
    candidate["created_at"] = existing.get("created_at") or now_iso()
    for key in ("promoted_at", "promoted_path", "promoted_category", "promoted_slug", "promoted_title"):
        if existing.get(key):
            candidate[key] = existing[key]
    if candidate.get("promoted_path"):
        candidate["status"] = "promoted"
    candidates[batch.get("batch_id", "")] = candidate
    save_skill_candidates(candidates)
    return candidate


def render_skill_markdown(batch: dict[str, Any], candidate: dict[str, Any], category: str, slug: str, title: str) -> str:
    skill_id = f"skill_{slug.replace('-', '_')}"
    batch_type = normalize(batch.get("batch_type", "")) or "随時"
    source = normalize(batch.get("source", "")) or "-"
    schema_hint = normalize(batch.get("schema_hint", "")) or "-"
    reasons = list(candidate.get("reasons") or [])
    missing = list(candidate.get("missing_requirements") or [])
    examples = list(candidate.get("examples") or [])
    today = datetime.now().astimezone().strftime("%Y-%m-%d")
    lines = [
        f"# {title}",
        "",
        f"> batch `{batch.get('batch_id','')}` から昇格した structured skill",
        "",
        "## メタ情報",
        "",
        "| 項目 | 値 |",
        "|------|-----|",
        f"| ID | {skill_id} |",
        f"| カテゴリ | {category} |",
        f"| 頻度 | {batch_type or '随時'} |",
        "| 現状 | 半自動 |",
        "| 担当 | Codex / Claude Code |",
        "| 承認 | 事後確認 |",
        f"| 参照知識 | System/data/ai_router/skill_candidate_index.json, System/data/ai_router/batch_index.json |",
        f"| 最終更新 | {today} |",
        "",
        "## トリガー（いつ・何が起きたら実行するか）",
        "",
        f"- batch `{batch.get('batch_id','')}` と同型の仕事がまとまって発生した時",
        f"- source: `{source}` から item を同期して処理したい時",
        "",
        "## インプット（何が必要か）",
        "",
        f"- source: `{source}`",
        f"- schema_hint: `{schema_hint}`",
        "- batch item の payload / source_ref / external_id",
        "",
        "## 手順（ステップバイステップ）",
        "",
        "### Step 1: source から item を同期する",
        "- `ai batch sync <batch>` で source の差分を batch に投入する",
        "- `cmd:` / `url:` / JSONL file / directory のどれで同期するかを先に固定する",
        "",
        "### Step 2: active item を処理する",
        "- `ai batch start <batch> --launch` または `ai batch next <batch>` で active item を取得する",
        "- `payload` と `source_ref` を見て、同型処理として実行する",
        "",
        "### Step 3: 結果を記録する",
        "- 成功時は `ai batch done <item_id> --summary \"...\"`",
        "- 失敗時は `ai batch fail <item_id> --error \"...\"`",
        "- release が必要な時は `ai batch release <item_id>`",
        "",
        "## 判断基準",
        "",
    ]
    if reasons:
        lines.extend(f"- {reason}" for reason in reasons)
    else:
        lines.append("- 同型性が崩れる場合は skill として扱わず個別対応に戻す")
    if missing:
        lines.append("")
        lines.append("## まだ不足しているもの")
        lines.append("")
        lines.extend(f"- {item}" for item in missing)
    lines.extend(
        [
            "",
            "## 代表例",
            "",
        ]
    )
    if examples:
        for example in examples:
            lines.append(f"- {example.get('item_id','')} / {example.get('title','')}")
            if normalize(example.get("result_summary", "")):
                lines.append(f"  - result: {example.get('result_summary','')}")
            if normalize(example.get("source_ref", "")):
                lines.append(f"  - source_ref: {example.get('source_ref','')}")
    else:
        lines.append("- 代表例はまだありません")
    lines.extend(
        [
            "",
            "## エラー時の対処",
            "",
            "| エラー | 原因 | 対処 |",
            "|--------|------|------|",
            "| source sync 失敗 | source が見つからない / command 失敗 / URL取得失敗 | `ai batch show <batch>` で source と sync summary を確認する |",
            "| item 処理失敗 | payload の形式差分 | `ai batch fail` で理由を残し、schema_hint を見直す |",
            "",
            "## 改善ログ",
            "",
            "| 日付 | 変更内容 |",
            "|------|----------|",
            f"| {today} | batch `{batch.get('batch_id','')}` から初回昇格 |",
            "",
        ]
    )
    return "\n".join(lines)


def get_batch_or_error(batch_id: str, batches: dict[str, Any]) -> dict[str, Any]:
    batch = batches.get(batch_id)
    if not isinstance(batch, dict):
        raise ValueError(f"unknown batch_id: {batch_id}")
    return update_batch_runtime(batch)


def output_json(payload: dict[str, Any]) -> int:
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def candidate_search_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate.get("candidate_id", ""),
        candidate.get("batch_id", ""),
        candidate.get("work_id", ""),
        candidate.get("title", ""),
        candidate.get("summary", ""),
        candidate.get("promoted_category", ""),
        candidate.get("promoted_slug", ""),
        candidate.get("promoted_path", ""),
    ]
    parts.extend(candidate.get("reasons") or [])
    parts.extend(candidate.get("missing_requirements") or [])
    return "\n".join(normalize(part).lower() for part in parts if normalize(part))


def find_skill_candidates(query: str, candidates: dict[str, Any], limit: int = 20) -> list[dict[str, Any]]:
    text = normalize(query).lower()
    rows: list[tuple[str, dict[str, Any]]] = []
    for candidate in candidates.values():
        if not isinstance(candidate, dict):
            continue
        if text and text not in candidate_search_text(candidate):
            continue
        rows.append((normalize(candidate.get("updated_at", "")), candidate))
    rows.sort(key=lambda item: item[0], reverse=True)
    return [row[1] for row in rows[:limit]]


def cmd_list(args: argparse.Namespace) -> int:
    batches = load_batches()
    candidates = find_batch_candidates(args.query or "", batches, limit=args.limit)
    return output_json({"query": normalize(args.query or ""), "count": len(candidates), "batches": candidates})


def cmd_resolve(args: argparse.Namespace) -> int:
    batches = load_batches()
    return output_json(resolve_batch_query(args.query or "", batches, limit=args.limit))


def cmd_create(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch_id = make_batch_id(args.title)
    batch = {
        "batch_id": batch_id,
        "title": normalize(args.title) or "untitled batch",
        "batch_type": normalize(args.batch_type),
        "preferred_tool": args.tool if args.tool in {"codex", "claude"} else "codex",
        "source": normalize(args.source),
        "schema_hint": normalize(args.schema_hint),
        "work_id": normalize(args.work_id),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "draft",
        "items": [],
        "counts": {"pending": 0, "running": 0, "completed": 0, "failed": 0, "total": 0},
        "summary": "",
        "active_item_id": "",
        "active_item_title": "",
    }
    batch = update_batch_runtime(batch)
    batches[batch_id] = batch
    if batch["work_id"]:
        attach_batch_to_work(works, batch, batch["work_id"], clear_item=True)
        save_works(works)
    save_batches(batches)
    append_event("batch_created", batch_id=batch_id, title=batch["title"], preferred_tool=batch["preferred_tool"])
    return output_json({"batch": batch})


def cmd_show(args: argparse.Namespace) -> int:
    batches = load_batches()
    candidates = load_skill_candidates()
    batch = get_batch_or_error(args.batch_id, batches)
    items = list(batch.get("items", []) or [])
    if args.only_active:
        items = [item for item in items if item.get("status") == "running"]
    if args.item_limit > 0:
        items = items[: args.item_limit]
    payload = {
        "batch": batch,
        "items": items,
        "counts": item_counts(batch),
        "active_item": next((item for item in batch.get("items", []) if item.get("status") == "running"), {}),
        "skill_candidate": candidates.get(batch.get("batch_id", ""), {}),
    }
    return output_json(payload)


def cmd_attach_work(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    work = works.get(args.work_id)
    if not isinstance(work, dict):
        return output_json({"error": f"unknown work_id: {args.work_id}"})
    batch["work_id"] = args.work_id
    running = next((item for item in batch.get("items", []) if item.get("status") == "running"), None)
    attach_batch_to_work(works, batch, args.work_id, item=running, clear_item=running is None)
    batches[batch["batch_id"]] = update_batch_runtime(batch)
    save_batches(batches)
    save_works(works)
    append_event("batch_attached", batch_id=batch["batch_id"], work_id=args.work_id)
    return output_json({"batch": batch, "work": works.get(args.work_id, {})})


def cmd_add_item(args: argparse.Namespace) -> int:
    batches = load_batches()
    batch = get_batch_or_error(args.batch_id, batches)
    payload = parse_payload(args.payload)
    item = create_item(batch, args.title, payload, source_ref=args.source_ref, external_id=args.external_id)
    batch.setdefault("items", []).append(item)
    batch = update_batch_runtime(batch)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    append_event("batch_item_added", batch_id=batch["batch_id"], item_id=item["item_id"], title=item["title"])
    return output_json({"batch": batch, "item": item})


def cmd_import_jsonl(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    path = Path(args.path)
    if not path.exists():
        return output_json({"error": f"missing file: {path}"})
    imported, skipped = append_unique_items(batch, parse_jsonl_items(path))
    batch = update_batch_runtime(batch)
    batch = update_source_sync_state(batch, [path], len(imported), skipped)
    if batch.get("work_id"):
        running = next((item for item in batch.get("items", []) if item.get("status") == "running"), None)
        attach_batch_to_work(works, batch, str(batch.get("work_id")), item=running, clear_item=running is None)
        save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    candidate = sync_skill_candidate(batch)
    append_event("batch_imported", batch_id=batch["batch_id"], imported=len(imported), skipped=skipped, path=str(path))
    return output_json(
        {
            "batch": batch,
            "imported_count": len(imported),
            "skipped_count": skipped,
            "items": imported[:10],
            "skill_candidate": candidate,
        }
    )


def cmd_sync_source(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    batch, imported, skipped, files = sync_batch_source(batch)
    if batch.get("work_id"):
        running = next((item for item in batch.get("items", []) if item.get("status") == "running"), None)
        attach_batch_to_work(works, batch, str(batch.get("work_id")), item=running, clear_item=running is None)
        save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    candidate = sync_skill_candidate(batch)
    append_event(
        "batch_source_synced",
        batch_id=batch["batch_id"],
        imported=len(imported),
        skipped=skipped,
        files=len(files),
        summary=batch.get("source_last_sync_summary", ""),
    )
    return output_json(
        {
            "batch": batch,
            "imported_count": len(imported),
            "skipped_count": skipped,
            "files": [str(path) for path in files],
            "items": imported[:10],
            "skill_candidate": candidate,
        }
    )


def cmd_list_skill_candidates(args: argparse.Namespace) -> int:
    candidates = load_skill_candidates()
    rows = find_skill_candidates(args.query or "", candidates, limit=args.limit)
    return output_json({"query": normalize(args.query or ""), "count": len(rows), "skill_candidates": rows})


def cmd_show_skill_candidate(args: argparse.Namespace) -> int:
    batches = load_batches()
    candidates = load_skill_candidates()
    batch = get_batch_or_error(args.batch_id, batches)
    candidate = candidates.get(args.batch_id, {}) if isinstance(candidates.get(args.batch_id, {}), dict) else {}
    if not candidate:
        candidate = sync_skill_candidate(batch)
    return output_json({"batch": batch, "skill_candidate": candidate})


def cmd_promote_skill_candidate(args: argparse.Namespace) -> int:
    batches = load_batches()
    candidates = load_skill_candidates()
    batch = get_batch_or_error(args.batch_id, batches)
    candidate = candidates.get(args.batch_id, {}) if isinstance(candidates.get(args.batch_id, {}), dict) else {}
    if not candidate:
        candidate = sync_skill_candidate(batch)
    if not candidate:
        return output_json({"error": "skill candidate not found"})
    if candidate.get("status") != "ready" and not args.force:
        return output_json({"error": "skill candidate is not ready. use --force to override", "skill_candidate": candidate})

    category = normalize(args.category)
    slug = normalize(args.slug)
    title = normalize(args.title) or normalize(candidate.get("title", "")) or slug
    skill_dir = PROJECT_DIR / "Skills" / category / slug
    skill_path = skill_dir / "SKILL.md"
    if skill_path.exists() and not args.force:
        return output_json({"error": f"skill already exists: {skill_path}", "skill_candidate": candidate})

    skill_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_skill_markdown(batch, candidate, category=category, slug=slug, title=title)
    skill_path.write_text(markdown + ("\n" if not markdown.endswith("\n") else ""))

    candidate["status"] = "promoted"
    candidate["promoted_at"] = now_iso()
    candidate["promoted_path"] = str(skill_path)
    candidate["promoted_category"] = category
    candidate["promoted_slug"] = slug
    candidate["promoted_title"] = title
    candidates[args.batch_id] = candidate
    save_skill_candidates(candidates)
    append_event("skill_candidate_promoted", batch_id=args.batch_id, category=category, slug=slug, path=str(skill_path))
    return output_json({"batch": batch, "skill_candidate": candidate, "skill_path": str(skill_path)})


def cmd_claim_next(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    items = batch.get("items", []) or []
    item = next((entry for entry in items if entry.get("status") == "running"), None)
    claimed_new = False
    if item is None:
        item = next((entry for entry in items if entry.get("status") == "pending"), None)
        if item:
            item["status"] = "running"
            item["attempts"] = int(item.get("attempts", 0)) + 1
            item["claimed_at"] = now_iso()
            item["claimed_by_work_id"] = normalize(args.work_id)
            item["claimed_by_tool"] = normalize(args.tool)
            item["updated_at"] = now_iso()
            claimed_new = True
    batch = update_batch_runtime(batch)
    if args.work_id:
        attach_batch_to_work(works, batch, args.work_id, item=item, clear_item=item is None)
        save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    if item:
        append_event(
            "batch_item_claimed",
            batch_id=batch["batch_id"],
            item_id=item["item_id"],
            claimed_new=claimed_new,
            work_id=normalize(args.work_id),
            tool=normalize(args.tool),
        )
    return output_json({"batch": batch, "item": item or {}, "claimed_new": claimed_new})


def find_item(batch: dict[str, Any], item_id: str) -> Optional[dict[str, Any]]:
    if item_id:
        return next((item for item in batch.get("items", []) if item.get("item_id") == item_id), None)
    active_item_id = str(batch.get("active_item_id") or "")
    if active_item_id:
        return next((item for item in batch.get("items", []) if item.get("item_id") == active_item_id), None)
    return next((item for item in batch.get("items", []) if item.get("status") == "running"), None)


def cmd_complete_item(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    item = find_item(batch, args.item_id)
    if not item:
        return output_json({"error": "item not found"})
    item["status"] = "completed"
    item["result_summary"] = normalize(args.summary)
    item["result_ref"] = normalize(args.result_ref)
    item["error"] = ""
    item["completed_at"] = now_iso()
    item["updated_at"] = now_iso()
    batch = update_batch_runtime(batch)
    clear_batch_item_from_works(works, batch["batch_id"], str(item.get("item_id") or ""))
    if batch.get("work_id"):
        attach_batch_to_work(works, batch, str(batch["work_id"]), clear_item=True)
    save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    candidate = sync_skill_candidate(batch)
    append_event("batch_item_completed", batch_id=batch["batch_id"], item_id=item["item_id"], summary=item["result_summary"])
    return output_json({"batch": batch, "item": item, "skill_candidate": candidate})


def cmd_fail_item(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    item = find_item(batch, args.item_id)
    if not item:
        return output_json({"error": "item not found"})
    item["status"] = "failed"
    item["error"] = normalize(args.error)
    item["updated_at"] = now_iso()
    batch = update_batch_runtime(batch)
    clear_batch_item_from_works(works, batch["batch_id"], str(item.get("item_id") or ""))
    if batch.get("work_id"):
        attach_batch_to_work(works, batch, str(batch["work_id"]), clear_item=True)
    save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    candidate = sync_skill_candidate(batch)
    append_event("batch_item_failed", batch_id=batch["batch_id"], item_id=item["item_id"], error=item["error"])
    return output_json({"batch": batch, "item": item, "skill_candidate": candidate})


def cmd_release_item(args: argparse.Namespace) -> int:
    batches = load_batches()
    works = load_works()
    batch = get_batch_or_error(args.batch_id, batches)
    item = find_item(batch, args.item_id)
    if not item:
        return output_json({"error": "item not found"})
    item["status"] = "pending"
    item["claimed_at"] = ""
    item["claimed_by_work_id"] = ""
    item["claimed_by_tool"] = ""
    item["updated_at"] = now_iso()
    batch = update_batch_runtime(batch)
    clear_batch_item_from_works(works, batch["batch_id"], str(item.get("item_id") or ""))
    if batch.get("work_id"):
        attach_batch_to_work(works, batch, str(batch["work_id"]), clear_item=True)
    save_works(works)
    batches[batch["batch_id"]] = batch
    save_batches(batches)
    candidate = sync_skill_candidate(batch)
    append_event("batch_item_released", batch_id=batch["batch_id"], item_id=item["item_id"])
    return output_json({"batch": batch, "item": item, "skill_candidate": candidate})


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--query", default="")
    list_parser.add_argument("--limit", type=int, default=20)

    resolve_parser = subparsers.add_parser("resolve")
    resolve_parser.add_argument("--query", default="")
    resolve_parser.add_argument("--limit", type=int, default=5)

    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--title", required=True)
    create_parser.add_argument("--tool", default="codex")
    create_parser.add_argument("--type", dest="batch_type", default="")
    create_parser.add_argument("--source", default="")
    create_parser.add_argument("--schema-hint", default="")
    create_parser.add_argument("--work-id", default="")

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("--batch-id", required=True)
    show_parser.add_argument("--item-limit", type=int, default=10)
    show_parser.add_argument("--only-active", action="store_true")

    attach_parser = subparsers.add_parser("attach-work")
    attach_parser.add_argument("--batch-id", required=True)
    attach_parser.add_argument("--work-id", required=True)

    add_item = subparsers.add_parser("add-item")
    add_item.add_argument("--batch-id", required=True)
    add_item.add_argument("--title", required=True)
    add_item.add_argument("--payload", required=True)
    add_item.add_argument("--source-ref", default="")
    add_item.add_argument("--external-id", default="")

    import_jsonl = subparsers.add_parser("import-jsonl")
    import_jsonl.add_argument("--batch-id", required=True)
    import_jsonl.add_argument("--path", required=True)

    sync_source = subparsers.add_parser("sync-source")
    sync_source.add_argument("--batch-id", required=True)

    list_skill_candidates = subparsers.add_parser("list-skill-candidates")
    list_skill_candidates.add_argument("--query", default="")
    list_skill_candidates.add_argument("--limit", type=int, default=20)

    show_skill_candidate = subparsers.add_parser("show-skill-candidate")
    show_skill_candidate.add_argument("--batch-id", required=True)

    promote_skill_candidate = subparsers.add_parser("promote-skill-candidate")
    promote_skill_candidate.add_argument("--batch-id", required=True)
    promote_skill_candidate.add_argument("--category", required=True)
    promote_skill_candidate.add_argument("--slug", required=True)
    promote_skill_candidate.add_argument("--title", default="")
    promote_skill_candidate.add_argument("--force", action="store_true")

    claim_next = subparsers.add_parser("claim-next")
    claim_next.add_argument("--batch-id", required=True)
    claim_next.add_argument("--work-id", default="")
    claim_next.add_argument("--tool", default="")

    complete_item = subparsers.add_parser("complete-item")
    complete_item.add_argument("--batch-id", required=True)
    complete_item.add_argument("--item-id", default="")
    complete_item.add_argument("--summary", required=True)
    complete_item.add_argument("--result-ref", default="")

    fail_item = subparsers.add_parser("fail-item")
    fail_item.add_argument("--batch-id", required=True)
    fail_item.add_argument("--item-id", default="")
    fail_item.add_argument("--error", required=True)

    release_item = subparsers.add_parser("release-item")
    release_item.add_argument("--batch-id", required=True)
    release_item.add_argument("--item-id", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "list":
        return cmd_list(args)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "create":
        return cmd_create(args)
    if args.command == "show":
        return cmd_show(args)
    if args.command == "attach-work":
        return cmd_attach_work(args)
    if args.command == "add-item":
        return cmd_add_item(args)
    if args.command == "import-jsonl":
        return cmd_import_jsonl(args)
    if args.command == "sync-source":
        return cmd_sync_source(args)
    if args.command == "list-skill-candidates":
        return cmd_list_skill_candidates(args)
    if args.command == "show-skill-candidate":
        return cmd_show_skill_candidate(args)
    if args.command == "promote-skill-candidate":
        return cmd_promote_skill_candidate(args)
    if args.command == "claim-next":
        return cmd_claim_next(args)
    if args.command == "complete-item":
        return cmd_complete_item(args)
    if args.command == "fail-item":
        return cmd_fail_item(args)
    if args.command == "release-item":
        return cmd_release_item(args)
    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
