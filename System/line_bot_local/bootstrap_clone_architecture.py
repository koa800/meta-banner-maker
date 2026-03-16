#!/usr/bin/env python3
"""
既存 profiles.json を元に、新しい clone architecture の雛形を生成する。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from clone_registry import (
    COMPANY_DIR,
    BRAINS_DIR,
    REGISTRIES_DIR,
    DEFAULT_AWAKENED_SELF,
    DEFAULT_HINATA_PERSONA,
    default_hinata_manifest,
    default_kohara_manifest,
    derive_agent_registry_from_legacy,
    derive_people_public_from_legacy,
    load_legacy_profiles,
)


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_json_if_missing(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text_if_missing(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def bootstrap() -> None:
    legacy_profiles = load_legacy_profiles()
    people_public = derive_people_public_from_legacy(legacy_profiles)
    agent_registry = derive_agent_registry_from_legacy(legacy_profiles, people_public)

    _write_json(COMPANY_DIR / "people_public.json", people_public)
    _write_json(REGISTRIES_DIR / "agent_registry.json", agent_registry)
    _write_json_if_missing(BRAINS_DIR / "kohara" / "brain_manifest.json", default_kohara_manifest())
    _write_json_if_missing(BRAINS_DIR / "hinata" / "brain_manifest.json", default_hinata_manifest())

    _write_text_if_missing(BRAINS_DIR / "kohara" / "awakened_self.md", DEFAULT_AWAKENED_SELF)
    _write_text_if_missing(BRAINS_DIR / "hinata" / "persona.md", DEFAULT_HINATA_PERSONA)

    _write_json_if_missing(
        BRAINS_DIR / "kohara" / "people_private.json",
        {
            "version": "2026-03-17",
            "owner": "self",
            "disclosure_level": "self-only",
            "approval_required": "always",
            "audience": ["僕"],
            "people": {},
            "pending_hypotheses": [],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )
    _write_json_if_missing(
        BRAINS_DIR / "hinata" / "people_private.json",
        {
            "version": "2026-03-17",
            "owner": "internal",
            "disclosure_level": "role-limited",
            "approval_required": "always",
            "audience": ["僕", "上司", "並列"],
            "people": {},
            "pending_hypotheses": [],
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        },
    )

    print("clone architecture bootstrap complete")
    print(f"- {COMPANY_DIR / 'people_public.json'}")
    print(f"- {REGISTRIES_DIR / 'agent_registry.json'}")
    print(f"- {BRAINS_DIR / 'kohara' / 'brain_manifest.json'}")
    print(f"- {BRAINS_DIR / 'hinata' / 'brain_manifest.json'}")


if __name__ == "__main__":
    bootstrap()
