#!/usr/bin/env python3
"""Mailchimp Journey の current snapshot を JSON で出す。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "System" / "config" / "mailchimp.json"


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text())


def build_session() -> tuple[requests.Session, str]:
    config = load_config()
    api_key = config["api_key"]
    server_prefix = config["server_prefix"]
    session = requests.Session()
    session.auth = ("anystring", api_key)
    session.headers.update({"Content-Type": "application/json"})
    base_url = f"https://{server_prefix}.api.mailchimp.com/3.0"
    return session, base_url


def fetch_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    response = session.get(url, params=params, timeout=60)
    response.raise_for_status()
    return response.json()


def list_journeys(session: requests.Session, base_url: str, count: int = 200) -> list[dict[str, Any]]:
    data = fetch_json(
        session,
        f"{base_url}/customer-journeys/journeys",
        params={"count": count},
    )
    return data.get("journeys", [])


def get_journey(session: requests.Session, base_url: str, journey_id: str) -> dict[str, Any]:
    journeys = list_journeys(session, base_url, count=300)
    for journey in journeys:
        if str(journey.get("id")) == str(journey_id):
            return journey
    raise SystemExit(f"Journey not found: {journey_id}")


def find_journey_by_query(session: requests.Session, base_url: str, query: str) -> dict[str, Any]:
    query_lower = query.lower()
    journeys = list_journeys(session, base_url, count=300)
    for journey in journeys:
        if query_lower in (journey.get("journey_name", "").lower()):
            return journey
    raise SystemExit(f"Journey query not found: {query}")


def get_steps(session: requests.Session, base_url: str, journey_id: str, timeout: int = 60) -> list[dict[str, Any]]:
    response = session.get(f"{base_url}/customer-journeys/journeys/{journey_id}/steps", timeout=timeout)
    response.raise_for_status()
    data = response.json()
    return data.get("steps", [])


def classify_email_step(journey_status: str, step: dict[str, Any]) -> str:
    step_status = step.get("status")
    queue_count = (step.get("stats") or {}).get("queue_count") or 0
    if journey_status != "sending":
        return "journey_not_sending"
    if step_status != "active" and queue_count > 0:
        return "paused_with_queue"
    if step_status != "active":
        return "step_not_active"
    if queue_count <= 0:
        return "queue_zero"
    return "current"


def summarize_email_step(journey: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    email = step.get("action_details", {}).get("email", {})
    settings = email.get("settings", {})
    row = {
        "journey_id": journey.get("id"),
        "journey_name": journey.get("journey_name"),
        "journey_status": journey.get("status"),
        "id": step.get("id"),
        "title": settings.get("title"),
        "subject_line": settings.get("subject_line"),
        "status": step.get("status"),
        "queue_count": step.get("stats", {}).get("queue_count"),
        "emails_sent": email.get("emails_sent"),
        "pause": email.get("pause"),
    }
    row["state_reason"] = classify_email_step(journey.get("status"), step)
    return row


def build_snapshot(journey: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    email_steps: list[dict[str, Any]] = []
    current_email_steps: list[dict[str, Any]] = []
    trigger_steps: list[dict[str, Any]] = []

    for step in steps:
        step_type = step.get("step_type")
        status = step.get("status")
        if step_type == "action-send_email":
            row = summarize_email_step(journey, step)
            row.pop("journey_id", None)
            row.pop("journey_name", None)
            row.pop("journey_status", None)
            email_steps.append(row)
            if row["state_reason"] == "current":
                current_email_steps.append(row)
        elif step_type and step_type.startswith("trigger-"):
            trigger_steps.append(
                {
                    "id": step.get("id"),
                    "step_type": step_type,
                    "title": step.get("title"),
                    "status": status,
                }
            )

    return {
        "id": journey.get("id"),
        "journey_name": journey.get("journey_name"),
        "status": journey.get("status"),
        "created_at": journey.get("created_at"),
        "last_started_at": journey.get("stats", {}).get("last_started_at"),
        "stats": journey.get("stats", {}),
        "trigger_steps": trigger_steps,
        "email_step_summary": {
            "total": len(email_steps),
            "current": len(current_email_steps),
            "queue_positive_active": sum(1 for step in email_steps if step.get("status") == "active" and (step.get("queue_count") or 0) > 0),
            "paused_with_queue": sum(1 for step in email_steps if step.get("state_reason") == "paused_with_queue"),
            "queue_zero": sum(1 for step in email_steps if step.get("state_reason") == "queue_zero"),
        },
        "current_email_steps": current_email_steps,
        "email_steps": email_steps,
    }


def build_current_matrix(session: requests.Session, base_url: str, count: int) -> dict[str, Any]:
    journeys = list_journeys(session, base_url, count=max(count * 5, count))
    journeys = sorted(
        [
            journey
            for journey in journeys
            if journey.get("status") == "sending"
            and (
                ((journey.get("stats") or {}).get("in_progress") or 0) > 0
                or ((journey.get("stats") or {}).get("started") or 0) != ((journey.get("stats") or {}).get("completed") or 0)
            )
        ],
        key=lambda journey: (
            -int(((journey.get("stats") or {}).get("in_progress") or 0)),
            -int(((journey.get("stats") or {}).get("started") or 0)),
        ),
    )[:count]
    current_rows: list[dict[str, Any]] = []
    paused_with_queue_rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    for journey in journeys:
        try:
            steps = get_steps(session, base_url, str(journey.get("id")), timeout=12)
        except Exception as exc:
            errors.append(
                {
                    "journey_id": journey.get("id"),
                    "journey_name": journey.get("journey_name"),
                    "error": str(exc),
                }
            )
            continue
        for step in steps:
            if step.get("step_type") != "action-send_email":
                continue
            row = summarize_email_step(journey, step)
            if row["state_reason"] == "current":
                current_rows.append(row)
            elif row["state_reason"] == "paused_with_queue":
                paused_with_queue_rows.append(row)

    current_rows.sort(key=lambda row: (-int(row.get("queue_count") or 0), str(row.get("journey_name") or "")))
    paused_with_queue_rows.sort(key=lambda row: (-int(row.get("queue_count") or 0), str(row.get("journey_name") or "")))
    return {
        "journey_count": len(journeys),
        "current_count": len(current_rows),
        "paused_with_queue_count": len(paused_with_queue_rows),
        "current_rows": current_rows,
        "paused_with_queue_rows": paused_with_queue_rows,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp journey snapshot")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--journey-id", help="Journey ID")
    group.add_argument("--query", help="Journey name substring")
    group.add_argument("--list-current", action="store_true", help="Current email step を横断取得")
    parser.add_argument("--count", type=int, default=30, help="Journey scan count for --list-current")
    args = parser.parse_args()

    session, base_url = build_session()
    if args.list_current:
        print(json.dumps(build_current_matrix(session, base_url, count=args.count), ensure_ascii=False, indent=2))
        return
    if args.journey_id:
        journey = get_journey(session, base_url, args.journey_id)
    else:
        if not args.query:
            raise SystemExit("`--journey-id` `--query` `--list-current` のいずれかが必要です。")
        journey = find_journey_by_query(session, base_url, args.query)
    steps = get_steps(session, base_url, journey["id"])
    print(json.dumps(build_snapshot(journey, steps), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
