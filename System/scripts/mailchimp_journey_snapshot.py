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
        if journey.get("id") == journey_id:
            return journey
    raise SystemExit(f"Journey not found: {journey_id}")


def find_journey_by_query(session: requests.Session, base_url: str, query: str) -> dict[str, Any]:
    query_lower = query.lower()
    journeys = list_journeys(session, base_url, count=300)
    for journey in journeys:
        if query_lower in (journey.get("journey_name", "").lower()):
            return journey
    raise SystemExit(f"Journey query not found: {query}")


def get_steps(session: requests.Session, base_url: str, journey_id: str) -> list[dict[str, Any]]:
    data = fetch_json(session, f"{base_url}/customer-journeys/journeys/{journey_id}/steps")
    return data.get("steps", [])


def build_snapshot(journey: dict[str, Any], steps: list[dict[str, Any]]) -> dict[str, Any]:
    active_email_steps: list[dict[str, Any]] = []
    trigger_steps: list[dict[str, Any]] = []

    for step in steps:
        step_type = step.get("step_type")
        status = step.get("status")
        if step_type == "action-send_email":
            email = step.get("action_details", {}).get("email", {})
            settings = email.get("settings", {})
            active_email_steps.append(
                {
                    "id": step.get("id"),
                    "title": settings.get("title"),
                    "subject_line": settings.get("subject_line"),
                    "status": status,
                    "queue_count": step.get("stats", {}).get("queue_count"),
                    "emails_sent": email.get("emails_sent"),
                    "pause": email.get("pause"),
                }
            )
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
        "active_email_steps": active_email_steps,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Mailchimp journey snapshot")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--journey-id", help="Journey ID")
    group.add_argument("--query", help="Journey name substring")
    args = parser.parse_args()

    session, base_url = build_session()
    if args.journey_id:
        journey = get_journey(session, base_url, args.journey_id)
    else:
        journey = find_journey_by_query(session, base_url, args.query)
    steps = get_steps(session, base_url, journey["id"])
    print(json.dumps(build_snapshot(journey, steps), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
