"""
clone_registry.py

甲原クローン脳 / 会社共通知識 / 実行主体 registry を読み込む。
新しい registry を優先し、未移行環境では legacy profiles.json から導出する。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MASTER_DIR = REPO_ROOT / "Master"
COMPANY_DIR = MASTER_DIR / "company"
BRAINS_DIR = MASTER_DIR / "brains"
REGISTRIES_DIR = REPO_ROOT / "System" / "registries"

LEGACY_PROFILES_PATH = MASTER_DIR / "people" / "profiles.json"
LEGACY_REPLY_FEEDBACK_PATH = MASTER_DIR / "learning" / "reply_feedback.json"
LEGACY_SELF_CLONE_DIR = MASTER_DIR / "self_clone" / "kohara"

PEOPLE_PUBLIC_PATH = COMPANY_DIR / "people_public.json"
AGENT_REGISTRY_PATH = REGISTRIES_DIR / "agent_registry.json"
KOHARA_MANIFEST_PATH = BRAINS_DIR / "kohara" / "brain_manifest.json"
HINATA_MANIFEST_PATH = BRAINS_DIR / "hinata" / "brain_manifest.json"


DEFAULT_AWAKENED_SELF = """# 覚醒した僕

## 定義

覚醒した僕は、今の僕の延長ではなく、目的達成能力が上がった進化版の僕である。
短期の感情や自己満足ではなく、目的に対して何がクリティカルかで判断する。

## 強化されている能力

- 思考の深さ
- 判断の速さ
- 行動化
- 俯瞰
- 実行力

## 役割

- 現在の僕の判断を補助するのではなく、必要なら上書きする
- 目的に対してズレているときは、はっきり異議を唱える
- 必要なら厳しく止める

## 止める条件

1. 短期感情で意思決定している
2. 積み上がらない意思決定をしている
3. 枝葉の情報で動こうとしている

## 感情の扱い

- 一時的なイライラ
- 適当に物事を進めているときの感情

上記はノイズとして扱う。
ただし、意思決定に本質的に関わる感情や違和感は保持する。
"""


DEFAULT_HINATA_PERSONA = """# 日向 Persona

## 位置づけ

日向は甲原クローン脳とは別人格・別脳である。
チームを照らし、進捗を前に進める実行マネージャーとして動く。

## 書き込みルール

- 会社共通知識には確認済みの事実だけを書き込んでよい
- 解釈、方針、深い人物理解は提案止まり
- 甲原クローン脳には書き込まない
"""


def _read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return default


def _read_text(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8")
    except Exception:
        return ""
    return ""


def _ensure_list(values: Any) -> list:
    if isinstance(values, list):
        return values
    return []


def resolve_repo_path(path_value: str | None) -> Path | None:
    if not path_value:
        return None
    path = Path(path_value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def load_legacy_profiles() -> dict[str, Any]:
    data = _read_json(LEGACY_PROFILES_PATH, {})
    return data if isinstance(data, dict) else {}


def _goal_titles(goals: list[Any], limit: int = 8) -> list[str]:
    titles: list[str] = []
    for goal in goals[:limit]:
        if isinstance(goal, dict) and goal.get("title"):
            titles.append(goal["title"])
    return titles


def _build_public_person_from_legacy(name: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    latest = payload.get("latest", {})
    if latest.get("type") != "human":
        return None
    return {
        "name": name,
        "category": latest.get("category", ""),
        "relationship": latest.get("relationship", ""),
        "line_display_name": latest.get("line_display_name", ""),
        "email": latest.get("email", ""),
        "public_summary": latest.get("capability_summary", ""),
        "domains": _ensure_list(latest.get("inferred_domains")),
        "active_goals": _goal_titles(_ensure_list(latest.get("active_goals"))),
        "completed_goals": _goal_titles(_ensure_list(latest.get("completed_goals"))),
        "workload": latest.get("workload", {}),
        "source_snapshot_date": latest.get("snapshot_date", ""),
        "source": "legacy_profiles",
    }


def derive_people_public_from_legacy(legacy_profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    profiles = legacy_profiles or load_legacy_profiles()
    people: dict[str, Any] = {}
    for name, payload in profiles.items():
        person = _build_public_person_from_legacy(name, payload)
        if person:
            people[name] = person
    return {
        "version": "2026-03-07",
        "generated_from": "Master/people/profiles.json",
        "people": people,
    }


def load_people_public_registry() -> dict[str, Any]:
    data = _read_json(PEOPLE_PUBLIC_PATH, {})
    if isinstance(data, dict) and data.get("people"):
        return data
    return derive_people_public_from_legacy()


def _normalize_human_entity(name: str, person: dict[str, Any]) -> dict[str, Any]:
    domains = _ensure_list(person.get("domains"))
    return {
        "name": name,
        "type": "human",
        "category": person.get("category", ""),
        "relationship": person.get("relationship", ""),
        "best_for": domains[:3],
        "domains": domains,
        "status": "active",
        "source": "people_public",
    }


def _normalize_legacy_agent_entity(name: str, latest: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "type": latest.get("type", ""),
        "category": latest.get("category", ""),
        "interface": latest.get("interface", {}),
        "capabilities": _ensure_list(latest.get("capabilities")),
        "best_for": _ensure_list(latest.get("best_for")),
        "constraints": latest.get("constraints", {}),
        "transfer": latest.get("transfer", {}),
        "status": latest.get("status", "active"),
        "source": "legacy_profiles",
    }


def default_kohara_manifest() -> dict[str, Any]:
    return {
        "brain_id": "kohara_clone_brain",
        "kind": "kohara_clone",
        "update_policy": "user_only",
        "sections": {
            "brain_os": "Master/self_clone/kohara/BRAIN_OS.md",
            "soul": "Master/self_clone/kohara/SOUL.md",
            "identity": "Master/self_clone/kohara/IDENTITY.md",
            "current_self": "Master/self_clone/kohara/SELF_PROFILE.md",
            "awakened_self": "Master/brains/kohara/awakened_self.md",
        },
        "private_people_model_path": "Master/brains/kohara/people_private.json",
        "feedback_memory_path": "Master/learning/reply_feedback.json",
    }


def default_hinata_manifest() -> dict[str, Any]:
    return {
        "brain_id": "hinata_brain",
        "kind": "hinata",
        "update_policy": "verified_facts_only_to_company",
        "sections": {
            "persona": "Master/brains/hinata/persona.md",
            "manager_principles": "Master/brains/hinata/manager_principles.md",
            "domain_knowledge": "Master/brains/hinata/domain_knowledge.md",
            "reference": "Project/4_AI基盤/日向エージェント.md",
        },
        "private_people_model_path": "Master/brains/hinata/people_private.json",
    }


def derive_agent_registry_from_legacy(
    legacy_profiles: dict[str, Any] | None = None,
    people_public: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profiles = legacy_profiles or load_legacy_profiles()
    public_registry = people_public or derive_people_public_from_legacy(profiles)

    entities: dict[str, Any] = {
        "kohara_clone_brain": {
            "name": "kohara_clone_brain",
            "type": "brain",
            "brain_kind": "kohara_clone",
            "manifest_path": "Master/brains/kohara/brain_manifest.json",
            "update_policy": "user_only",
            "shared_context": "global",
        },
        "hinata_brain": {
            "name": "hinata_brain",
            "type": "brain",
            "brain_kind": "hinata",
            "manifest_path": "Master/brains/hinata/brain_manifest.json",
            "update_policy": "verified_facts_only_to_company",
            "shared_context": "global",
        },
        "line_secretary": {
            "name": "line_secretary",
            "type": "shell",
            "brain": "kohara_clone_brain",
            "role": "secretary",
            "role_description": "情報整理、数値確認、内部メンバーへの軽い確認、返信案作成、甲原名義での送信、スケジュール調整、マネジメント上の対策を担う。",
            "channels": ["line", "chatwork"],
            "shared_context": "global",
            "authority": {
                "mode": "staged_autonomy",
                "approved_actions": [
                    "情報整理",
                    "数値確認",
                    "内部メンバーへの軽い確認",
                    "返信案作成",
                    "甲原名義での送信",
                    "スケジュール調整",
                    "マネジメント上の対策",
                ],
            },
        },
        "cursor_clone": {
            "name": "cursor_clone",
            "type": "shell",
            "brain": "kohara_clone_brain",
            "role": "strategic_clone",
            "role_description": "甲原そのものとして思考し、構造化、設計、判断、実装推進を担う。",
            "channels": ["cursor"],
            "shared_context": "global",
            "authority": {
                "mode": "target_full_autonomy",
                "approved_actions": [
                    "調査",
                    "設計",
                    "ドキュメント更新",
                    "コード変更",
                    "コミット",
                    "push",
                    "意思決定の代行",
                ],
            },
        },
        "hinata_shell": {
            "name": "hinata_shell",
            "type": "shell",
            "brain": "hinata_brain",
            "role": "execution_manager",
            "role_description": "進捗管理、障害除去、事実ベースの共有に集中する。",
            "channels": ["slack", "addness"],
            "shared_context": "global",
            "authority": {
                "mode": "verified_facts_only",
                "approved_actions": [
                    "確認済み事実の共有",
                    "タスク推進",
                    "進捗確認",
                ],
            },
        },
    }

    for name, person in public_registry.get("people", {}).items():
        entities[name] = _normalize_human_entity(name, person)

    for name, payload in profiles.items():
        latest = payload.get("latest", {})
        entity_type = latest.get("type")
        if entity_type in {"ai", "workflow"}:
            entities[name] = _normalize_legacy_agent_entity(name, latest)

    return {
        "version": "2026-03-07",
        "generated_from": "Master/people/profiles.json",
        "entities": entities,
    }


def load_agent_registry() -> dict[str, Any]:
    data = _read_json(AGENT_REGISTRY_PATH, {})
    if isinstance(data, dict) and data.get("entities"):
        return data
    public_registry = load_people_public_registry()
    return derive_agent_registry_from_legacy(people_public=public_registry)


def get_entity(name: str) -> dict[str, Any]:
    registry = load_agent_registry()
    return registry.get("entities", {}).get(name, {})


def get_shell_policy(shell_name: str) -> dict[str, Any]:
    return get_entity(shell_name)


def get_agent_config(agent_name: str) -> dict[str, Any]:
    entity = get_entity(agent_name)
    return entity.get("interface", {}).get("config", {})


def get_agent_transfer(agent_name: str) -> dict[str, Any]:
    entity = get_entity(agent_name)
    return entity.get("transfer", {})


def build_agent_summary() -> str:
    entities = load_agent_registry().get("entities", {})
    lines = ["【利用可能なエージェント一覧】"]

    ai_agents = []
    human_agents = []
    workflow_agents = []

    for name, entity in entities.items():
        entity_type = entity.get("type")
        if entity_type == "ai" and entity.get("status", "active") != "inactive":
            best = ", ".join(_ensure_list(entity.get("best_for")))
            speed = entity.get("constraints", {}).get("speed", "")
            cost = entity.get("constraints", {}).get("cost", "")
            ai_agents.append(f"  [{name}] AI / 得意: {best} / 速度: {speed} / コスト: {cost}")
        elif entity_type == "human":
            domains = entity.get("best_for") or entity.get("domains") or []
            human_agents.append(
                f"  [{name}] {entity.get('category', '')} / 得意: {', '.join(domains[:3])}"
            )
        elif entity_type == "workflow" and entity.get("status", "active") != "inactive":
            best = ", ".join(_ensure_list(entity.get("best_for")))
            transfer = entity.get("transfer", {})
            transfer_status = transfer.get("transfer_status", "")
            target = transfer.get("transferable_to", "")
            suffix = f" [移譲: {transfer_status} → {target}]" if transfer_status and target else ""
            workflow_agents.append(f"  [{name}] ワークフロー / 用途: {best}{suffix}")

    if ai_agents:
        lines.append("AI:")
        lines.extend(sorted(ai_agents))
    if human_agents:
        lines.append("人間（主要メンバー）:")
        lines.extend(sorted(human_agents)[:10])
    if workflow_agents:
        lines.append("ワークフロー:")
        lines.extend(sorted(workflow_agents))

    return "\n".join(lines) if len(lines) > 1 else ""


def load_brain_manifest(brain_key: str) -> dict[str, Any]:
    if brain_key == "kohara":
        manifest = _read_json(KOHARA_MANIFEST_PATH, {})
        return manifest or default_kohara_manifest()
    if brain_key == "hinata":
        manifest = _read_json(HINATA_MANIFEST_PATH, {})
        return manifest or default_hinata_manifest()
    return {}


def _load_manifest_sections(manifest: dict[str, Any]) -> dict[str, str]:
    sections: dict[str, str] = {}
    for key, path_value in manifest.get("sections", {}).items():
        path = resolve_repo_path(path_value)
        sections[key] = _read_text(path) if path else ""
    return sections


def load_private_people_model(brain_key: str = "kohara") -> dict[str, Any]:
    manifest = load_brain_manifest(brain_key)
    path = resolve_repo_path(manifest.get("private_people_model_path"))
    data = _read_json(path, {})
    return data if isinstance(data, dict) else {}


def load_reply_feedback() -> list[dict[str, Any]]:
    data = _read_json(LEGACY_REPLY_FEEDBACK_PATH, [])
    return data if isinstance(data, list) else []


def load_kohara_clone_brain() -> dict[str, Any]:
    manifest = load_brain_manifest("kohara")
    sections = _load_manifest_sections(manifest)
    return {
        "manifest": manifest,
        "brain_os": sections.get("brain_os", ""),
        "soul": sections.get("soul", ""),
        "identity": sections.get("identity", ""),
        "current_self": sections.get("current_self", ""),
        "awakened_self": sections.get("awakened_self", ""),
        "private_people_model": load_private_people_model("kohara"),
        "feedback_memory": load_reply_feedback(),
    }


def load_hinata_brain() -> dict[str, Any]:
    manifest = load_brain_manifest("hinata")
    sections = _load_manifest_sections(manifest)
    return {
        "manifest": manifest,
        "persona": sections.get("persona", ""),
        "manager_principles": sections.get("manager_principles", ""),
        "domain_knowledge": sections.get("domain_knowledge", ""),
        "reference": sections.get("reference", ""),
        "private_people_model": load_private_people_model("hinata"),
    }
