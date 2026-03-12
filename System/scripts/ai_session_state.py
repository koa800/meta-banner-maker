#!/usr/bin/env python3

import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional


PROJECT_DIR = Path(__file__).resolve().parents[2]
CODEX_SESSIONS_DIR = Path.home() / ".codex" / "sessions"
CLAUDE_HISTORY_FILE = Path.home() / ".claude" / "history.jsonl"
SESSION_ALIAS_FILE = PROJECT_DIR / "Master" / "output" / "session_aliases.json"
SESSION_INDEX_FILE = PROJECT_DIR / "Master" / "output" / "session_restore_index.json"
JST = timezone(timedelta(hours=9))


def normalize(text: Any) -> str:
    return " ".join(str(text or "").split())


def is_meaningful(text: str) -> bool:
    text = normalize(text)
    if len(text) < 10:
        return False
    if text.startswith("/"):
        return False
    return text not in {"続けて", "進めて", "了解です", "了解", "OK", "ありがとう", "あとでよいよ"}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_alias_state() -> tuple[dict[str, tuple[str, str, str]], dict[str, list[str]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    aliases = load_json(SESSION_ALIAS_FILE)
    index = load_json(SESSION_INDEX_FILE)
    alias_to_target: dict[str, tuple[str, str, str]] = {}
    aliases_by_sid: dict[str, list[str]] = {}
    records_by_alias: dict[str, dict[str, Any]] = {}

    for alias, record in aliases.items():
        if not isinstance(record, dict):
            continue
        sid = record.get("session_id")
        tool = record.get("tool")
        if not alias or not sid or not tool:
            continue
        alias_to_target[alias.lower()] = (str(tool), str(sid), str(alias))
        aliases_by_sid.setdefault(str(sid), []).append(str(alias))
        records_by_alias[str(alias)] = record

    index_records = {sid: record for sid, record in index.items() if isinstance(record, dict)}
    return alias_to_target, aliases_by_sid, records_by_alias, index_records


def load_index_records() -> dict[str, dict[str, Any]]:
    data = load_json(SESSION_INDEX_FILE)
    return {sid: record for sid, record in data.items() if isinstance(record, dict)}


def merged_record(
    sid: str,
    aliases_by_sid: dict[str, list[str]],
    records_by_alias: dict[str, dict[str, Any]],
    index_records: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    if isinstance(index_records.get(sid), dict):
        record.update(index_records[sid])
    aliases = aliases_by_sid.get(sid, [])
    if aliases and isinstance(records_by_alias.get(aliases[0]), dict):
        record.update(records_by_alias[aliases[0]])
    if aliases:
        record["alias"] = aliases[0]
        record["aliases"] = aliases
    record["session_id"] = sid
    return record


def session_record_search_text(record: dict[str, Any]) -> str:
    parts = [record.get("title", ""), record.get("purpose", "")]
    for key in ("confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        parts.extend(record.get(key) or [])
    return "\n".join(normalize(part).lower() for part in parts if normalize(part))


def session_preview(record: dict[str, Any], fallback: str) -> str:
    title = normalize(record.get("title", ""))
    purpose = normalize(record.get("purpose", ""))
    remaining = [normalize(item) for item in (record.get("remaining") or []) if normalize(item)]
    if title and purpose and title != purpose:
        return f"{title} / {purpose}"[:120]
    if purpose and remaining:
        return f"{purpose} / 残: {remaining[0]}"[:120]
    if title and remaining:
        return f"{title} / 残: {remaining[0]}"[:120]
    if title:
        return title[:120]
    if purpose:
        return purpose[:120]
    return fallback[:120]


def duration_minutes(start: str, end: str) -> int:
    if not start or not end:
        return 0
    try:
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
    except ValueError:
        return 0
    if end_dt < start_dt:
        return 0
    return int((end_dt - start_dt).total_seconds() // 60)


def evaluate_load(tool: str, metrics: dict[str, Any]) -> dict[str, Any]:
    score = 0
    reasons: list[str] = []

    if tool == "codex":
        user_turns = int(metrics.get("user_turns", 0))
        assistant_turns = int(metrics.get("assistant_turns", 0))
        tool_calls = int(metrics.get("tool_calls", 0))
        duration = int(metrics.get("duration_minutes", 0))
        response_items = int(metrics.get("response_items", 0))

        if user_turns >= 20:
            score += 3
            reasons.append(f"user_turns={user_turns}")
        elif user_turns >= 12:
            score += 2
            reasons.append(f"user_turns={user_turns}")
        elif user_turns >= 8:
            score += 1
            reasons.append(f"user_turns={user_turns}")

        if tool_calls >= 80:
            score += 3
            reasons.append(f"tool_calls={tool_calls}")
        elif tool_calls >= 40:
            score += 2
            reasons.append(f"tool_calls={tool_calls}")
        elif tool_calls >= 20:
            score += 1
            reasons.append(f"tool_calls={tool_calls}")

        if duration >= 180:
            score += 3
            reasons.append(f"duration={duration}m")
        elif duration >= 90:
            score += 2
            reasons.append(f"duration={duration}m")
        elif duration >= 45:
            score += 1
            reasons.append(f"duration={duration}m")

        if response_items >= 180:
            score += 2
            reasons.append(f"response_items={response_items}")
        elif response_items >= 120:
            score += 1
            reasons.append(f"response_items={response_items}")

        if assistant_turns >= 16:
            score += 1
            reasons.append(f"assistant_turns={assistant_turns}")

        stat_summary = f"{user_turns}入力 / {tool_calls}call / {duration}分"
    else:
        history_entries = int(metrics.get("history_entries", 0))
        meaningful_entries = int(metrics.get("meaningful_entries", 0))
        duration = int(metrics.get("duration_minutes", 0))

        if meaningful_entries >= 30:
            score += 3
            reasons.append(f"meaningful_entries={meaningful_entries}")
        elif meaningful_entries >= 18:
            score += 2
            reasons.append(f"meaningful_entries={meaningful_entries}")
        elif meaningful_entries >= 10:
            score += 1
            reasons.append(f"meaningful_entries={meaningful_entries}")

        if duration >= 180:
            score += 3
            reasons.append(f"duration={duration}m")
        elif duration >= 90:
            score += 2
            reasons.append(f"duration={duration}m")
        elif duration >= 45:
            score += 1
            reasons.append(f"duration={duration}m")

        if history_entries >= 40:
            score += 2
            reasons.append(f"history_entries={history_entries}")
        elif history_entries >= 24:
            score += 1
            reasons.append(f"history_entries={history_entries}")

        stat_summary = f"{meaningful_entries}入力 / {duration}分"

    if score >= 6:
        level = "severe"
    elif score >= 4:
        level = "high"
    elif score >= 2:
        level = "medium"
    else:
        level = "light"

    should_fork = level in {"high", "severe"}
    should_compact = level in {"medium", "high", "severe"}
    label = f"{level}{'*' if should_fork else ''}"
    summary = f"{label} / {stat_summary}"
    if should_fork:
        summary = f"{summary} / auto-fork"
    elif should_compact:
        summary = f"{summary} / compact"

    return {
        "level": level,
        "label": label,
        "score": score,
        "should_fork": should_fork,
        "should_compact": should_compact,
        "reasons": reasons,
        "summary": summary,
    }


def analyze_codex_session(path: Path) -> Optional[dict[str, Any]]:
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None

    sid = ""
    start = ""
    end = ""
    first_user = ""
    last_user = ""
    last_meaningful_user = ""
    response_items = 0
    user_turns = 0
    assistant_turns = 0
    developer_messages = 0
    reasoning_items = 0
    tool_calls = 0

    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue

        if obj.get("type") == "session_meta":
            payload = obj.get("payload", {})
            sid = str(payload.get("id") or sid)
            raw_start = payload.get("timestamp")
            if raw_start:
                start = str(raw_start)

        ts = obj.get("timestamp")
        if ts:
            end = str(ts)

        if obj.get("type") != "response_item":
            continue

        response_items += 1
        payload = obj.get("payload", {})
        payload_type = str(payload.get("type") or "")
        role = str(payload.get("role") or "")

        if payload_type == "message":
            if role == "user":
                content = normalize(" ".join((chunk.get("text") or chunk.get("output_text") or "") for chunk in payload.get("content", [])))
                if content and not content.startswith("# AGENTS.md instructions"):
                    user_turns += 1
                    if not first_user:
                        first_user = content
                    last_user = content
                    if is_meaningful(content):
                        last_meaningful_user = content
            elif role == "assistant":
                assistant_turns += 1
            elif role == "developer":
                developer_messages += 1
        elif payload_type == "reasoning":
            reasoning_items += 1
        elif payload_type.endswith("_call") or payload_type == "function_call":
            tool_calls += 1

    if not sid or not end:
        return None

    if start:
        start_iso = start.replace("Z", "+00:00")
    else:
        start_iso = end.replace("Z", "+00:00")
    end_iso = end.replace("Z", "+00:00")
    preview = last_meaningful_user or last_user or first_user or "(no summary)"

    metrics = {
        "response_items": response_items,
        "user_turns": user_turns,
        "assistant_turns": assistant_turns,
        "developer_messages": developer_messages,
        "reasoning_items": reasoning_items,
        "tool_calls": tool_calls,
        "duration_minutes": duration_minutes(start_iso, end_iso),
    }
    return {
        "tool": "codex",
        "session_id": sid,
        "start": start_iso,
        "end": end_iso,
        "preview": preview[:120],
        "metrics": metrics,
        "load": evaluate_load("codex", metrics),
    }


def analyze_claude_sessions() -> list[dict[str, Any]]:
    if not CLAUDE_HISTORY_FILE.exists():
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for line in CLAUDE_HISTORY_FILE.read_text(errors="replace").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue

        if obj.get("project") != str(PROJECT_DIR):
            continue

        sid = obj.get("sessionId")
        raw_ts = obj.get("timestamp")
        if not sid or raw_ts is None:
            continue

        try:
            dt = datetime.fromtimestamp(raw_ts / 1000, tz=timezone.utc)
        except Exception:
            continue

        display = normalize(obj.get("display", ""))
        record = grouped.setdefault(
            str(sid),
            {
                "tool": "claude",
                "session_id": str(sid),
                "start_dt": dt,
                "end_dt": dt,
                "preview": "",
                "fallback_preview": "",
                "search_text_parts": [],
                "history_entries": 0,
                "meaningful_entries": 0,
            },
        )
        if dt < record["start_dt"]:
            record["start_dt"] = dt
        if dt >= record["end_dt"]:
            record["end_dt"] = dt
            if display and is_meaningful(display):
                record["preview"] = display[:120]
            elif display:
                record["fallback_preview"] = display[:120]
        if display:
            record["search_text_parts"].append(display.lower())
        record["history_entries"] += 1
        if is_meaningful(display):
            record["meaningful_entries"] += 1

    out: list[dict[str, Any]] = []
    for record in grouped.values():
        start_iso = record["start_dt"].isoformat()
        end_iso = record["end_dt"].isoformat()
        metrics = {
            "history_entries": record["history_entries"],
            "meaningful_entries": record["meaningful_entries"],
            "duration_minutes": duration_minutes(start_iso, end_iso),
        }
        out.append(
            {
                "tool": "claude",
                "session_id": record["session_id"],
                "start": start_iso,
                "end": end_iso,
                "preview": (record["preview"] or record["fallback_preview"] or "(no summary)")[:120],
                "search_text": "\n".join(record["search_text_parts"]),
                "metrics": metrics,
                "load": evaluate_load("claude", metrics),
            }
        )
    return out


def load_all_sessions() -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    if CODEX_SESSIONS_DIR.exists():
        for path in CODEX_SESSIONS_DIR.rglob("*.jsonl"):
            record = analyze_codex_session(path)
            if record:
                sessions.append(record)
    sessions.extend(analyze_claude_sessions())
    return sessions


def enrich_session_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    alias_to_target, aliases_by_sid, records_by_alias, index_records = load_alias_state()
    enriched: list[dict[str, Any]] = []
    for record in records:
        sid = record["session_id"]
        merged = merged_record(sid, aliases_by_sid, records_by_alias, index_records)
        preview = session_preview(merged, record.get("preview", ""))
        item = dict(record)
        item["aliases"] = aliases_by_sid.get(sid, [])
        item["alias"] = item["aliases"][0] if item["aliases"] else ""
        item["preview"] = preview
        item["record"] = merged
        item["search_text"] = "\n".join(
            part for part in [normalize(record.get("search_text", "")).lower(), session_record_search_text(merged)] if part
        )
        enriched.append(item)
    return enriched


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}

    for record in records:
        key = (record.get("tool", ""), record.get("session_id", ""))
        current = deduped.get(key)
        if current is None:
            deduped[key] = dict(record)
            continue

        current_end = normalize(current.get("end", ""))
        record_end = normalize(record.get("end", ""))
        if record_end > current_end:
            primary = dict(record)
            secondary = current
        else:
            primary = current
            secondary = record

        merged = dict(primary)
        current_start = normalize(primary.get("start", ""))
        other_start = normalize(secondary.get("start", ""))
        if other_start and (not current_start or other_start < current_start):
            merged["start"] = other_start

        combined_aliases = sorted({*(primary.get("aliases", []) or []), *(secondary.get("aliases", []) or [])})
        if combined_aliases:
            merged["aliases"] = combined_aliases
            merged["alias"] = combined_aliases[0]

        search_parts = [normalize(primary.get("search_text", "")), normalize(secondary.get("search_text", ""))]
        merged["search_text"] = "\n".join(part for part in search_parts if part)
        deduped[key] = merged

    return list(deduped.values())


def filter_records(records: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    query_lc = normalize(query).lower()
    if not query_lc:
        return records

    alias_to_target, _, _, _ = load_alias_state()
    exact_alias_target = alias_to_target.get(query_lc)
    is_sid = bool(re.fullmatch(r"[0-9a-fA-F-]{36}", query_lc))

    out: list[dict[str, Any]] = []
    for record in records:
        sid = record["session_id"]
        alias_text = " ".join(record.get("aliases", [])).lower()
        if exact_alias_target:
            if exact_alias_target[0] == record["tool"] and exact_alias_target[1] == sid:
                out.append(record)
            continue
        if is_sid:
            if sid.lower() == query_lc:
                out.append(record)
            continue
        haystack = "\n".join(
            [
                sid.lower(),
                alias_text,
                normalize(record.get("preview", "")).lower(),
                normalize(record.get("search_text", "")).lower(),
            ]
        )
        if query_lc in haystack:
            out.append(record)
    return out


def sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda record: record.get("end", ""), reverse=True)


def serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool": record["tool"],
        "session_id": record["session_id"],
        "preview": record.get("preview", ""),
        "start": record.get("start", ""),
        "end": record.get("end", ""),
        "alias": record.get("alias", ""),
        "aliases": record.get("aliases", []),
        "metrics": record.get("metrics", {}),
        "load": record.get("load", {}),
        "record": record.get("record", {}),
    }


def find_session_record(tool: str, session_id: str = "") -> Optional[dict[str, Any]]:
    sessions = sort_records(dedupe_records(enrich_session_records(load_all_sessions())))
    if session_id:
        for record in sessions:
            if record.get("session_id") == session_id and record.get("tool") == tool:
                return record
        return None
    for record in sessions:
        if record.get("tool") == tool:
            return record
    return None


def snapshot_has_content(record: dict[str, Any]) -> bool:
    if not isinstance(record, dict) or not record:
        return False
    if normalize(record.get("purpose", "")):
        return True
    for key in ("confirmed", "completed", "remaining", "decisions", "references", "changed_files", "next"):
        if record.get(key):
            return True
    return False


def build_verify_payload(tool: str, session_record: Optional[dict[str, Any]], snapshot_record: dict[str, Any]) -> dict[str, Any]:
    preview = normalize((session_record or {}).get("preview", ""))
    snapshot_title = normalize(snapshot_record.get("title", ""))
    snapshot_purpose = normalize(snapshot_record.get("purpose", ""))
    session_metrics = snapshot_record.get("session_metrics") if isinstance(snapshot_record, dict) else {}
    session_load = snapshot_record.get("session_load") if isinstance(snapshot_record, dict) else {}
    checks = {
        "snapshot_content": snapshot_has_content(snapshot_record),
        "session_metrics": isinstance(session_metrics, dict) and bool(session_metrics),
        "session_load": isinstance(session_load, dict) and bool(session_load),
        "work_link": bool(normalize(snapshot_record.get("work_id", ""))),
        "title_or_preview": bool(snapshot_title or snapshot_purpose or preview),
    }
    ok = bool(session_record) and bool(snapshot_record) and all(checks.values())
    return {
        "tool": tool,
        "session_id": (session_record or {}).get("session_id", "") or snapshot_record.get("session_id", ""),
        "session_found": bool(session_record),
        "snapshot_found": bool(snapshot_record),
        "preview": preview,
        "snapshot_title": snapshot_title,
        "snapshot_purpose": snapshot_purpose,
        "work_id": snapshot_record.get("work_id", ""),
        "handoff_file": snapshot_record.get("handoff_file", ""),
        "updated_at": snapshot_record.get("updated_at", ""),
        "load_summary": (session_record or {}).get("load", {}).get("summary", ""),
        "snapshot_load_summary": session_load.get("summary", "") if isinstance(session_load, dict) else "",
        "checks": checks,
        "ok": ok,
    }


def load_short_label(record: dict[str, Any]) -> str:
    load = record.get("load", {})
    return str(load.get("label") or "light")


def fmt_ts(value: str) -> str:
    if not value:
        return "-"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value[:16]
    return dt.astimezone(JST).strftime("%m-%d %H:%M")


def cmd_latest(args: argparse.Namespace) -> int:
    sessions = sort_records(dedupe_records(enrich_session_records(load_all_sessions())))
    for record in sessions:
        if record["tool"] == args.tool:
            print(json.dumps(serialize_record(record), ensure_ascii=False))
            return 0
    print("{}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    sessions = sort_records(filter_records(dedupe_records(enrich_session_records(load_all_sessions())), args.query or ""))
    if not sessions:
        label = normalize(args.query or "recent")
        print(f"一致するセッションがありません: {label}")
        return 1

    print("tool     last_active   started      load      session_id                             alias                 summary")
    print("-" * 156)
    for record in sessions[: args.limit]:
        alias = ",".join(record.get("aliases", [])[:2])[:20] or "-"
        print(
            f"{record['tool']:<8} {fmt_ts(record.get('end', '')):<12} {fmt_ts(record.get('start', '')):<12} "
            f"{load_short_label(record):<9} {record['session_id']:<36} {alias:<20} {record.get('preview', '')}"
        )
    return 0


def cmd_resolve(args: argparse.Namespace) -> int:
    query = normalize(args.query)
    if not query:
        print("クエリが空です。", file=sys.stderr)
        return 1

    alias_to_target, aliases_by_sid, records_by_alias, index_records = load_alias_state()
    query_lc = query.lower()
    exact_alias_target = alias_to_target.get(query_lc)

    sessions = sort_records(filter_records(dedupe_records(enrich_session_records(load_all_sessions())), query))

    if exact_alias_target and not sessions:
        tool, sid, alias = exact_alias_target
        merged = merged_record(sid, aliases_by_sid, records_by_alias, index_records)
        fallback = session_preview(merged, f"alias:{alias}")
        print(
            json.dumps(
                {
                    "tool": tool,
                    "session_id": sid,
                    "preview": fallback,
                    "start": "",
                    "end": "",
                    "alias": alias,
                    "aliases": aliases_by_sid.get(sid, [alias]),
                    "metrics": merged.get("session_metrics", {}),
                    "load": merged.get("session_load", {}),
                    "record": merged,
                },
                ensure_ascii=False,
            )
        )
        return 0

    if len(sessions) == 1:
        print(json.dumps(serialize_record(sessions[0]), ensure_ascii=False))
        return 0

    if not sessions:
        print(f"一致するセッションがありません: {query}", file=sys.stderr)
        return 1

    print(f"候補が複数あります: {query}", file=sys.stderr)
    for record in sessions[:10]:
        print(
            f"- {record['tool']} {record['session_id']} [{load_short_label(record)}] {record.get('preview', '')}",
            file=sys.stderr,
        )
    return 2


def cmd_verify(args: argparse.Namespace) -> int:
    session_record = find_session_record(args.tool, args.session_id or "")
    resolved_session_id = args.session_id or (session_record.get("session_id", "") if session_record else "")
    snapshot_index = load_index_records()
    snapshot_record = snapshot_index.get(resolved_session_id, {}) if resolved_session_id else {}
    print(json.dumps(build_verify_payload(args.tool, session_record, snapshot_record), ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    latest = subparsers.add_parser("latest")
    latest.add_argument("--tool", required=True, choices=["codex", "claude"])

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--query", default="")
    list_parser.add_argument("--limit", type=int, default=20)

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("--query", required=True)

    verify = subparsers.add_parser("verify")
    verify.add_argument("--tool", required=True, choices=["codex", "claude"])
    verify.add_argument("--session-id", default="")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "latest":
        return cmd_latest(args)
    if args.command == "list":
        return cmd_list(args)
    if args.command == "resolve":
        return cmd_resolve(args)
    if args.command == "verify":
        return cmd_verify(args)
    parser.error(f"unknown command: {args.command}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
