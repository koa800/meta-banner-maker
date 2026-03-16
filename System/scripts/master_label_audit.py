#!/usr/bin/env python3
"""Master の高リスク資産に情報ラベルが付いているかを検査する。"""

import json
import sys
from pathlib import Path
from typing import Optional


ROOT_DIR = Path(__file__).resolve().parents[2]
REQUIRED_MD_LINES = (
    "## 情報ラベル",
    "- 所有元:",
    "- 開示レベル:",
    "- 承認必須:",
    "- 共有先:",
)
REQUIRED_JSON_KEYS = ("owner", "disclosure_level", "approval_required", "audience")
ALLOWED_OWNER = {"self", "internal", "external-ready"}
ALLOWED_DISCLOSURE = {"self-only", "role-limited", "task-limited", "shareable"}
ALLOWED_APPROVAL = {"always", "conditional", "none"}
ALLOWED_AUDIENCE = {"僕", "上司", "並列", "直下", "外部"}
LEGACY_AUDIT_DIRS = {
    "Master/output": {".md"},
    "Master/addness": {".md"},
    "Master/learning": {".md", ".json"},
    "Master/sheets": {".md", ".json"},
}
PATH_POLICIES = [
    {
        "prefix": "Master/output/経理/",
        "owner": "self",
        "disclosure_level": "self-only",
        "approval_required": "always",
        "audience": ["僕"],
    },
    {
        "prefix": "Master/output/引き継ぎ/",
        "owner": "internal",
        "disclosure_level": "task-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列", "直下"],
    },
    {
        "prefix": "Master/output/",
        "owner": "internal",
        "disclosure_level": "task-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列", "直下"],
    },
    {
        "prefix": "Master/addness/goal-tree.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/actionable-tasks.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/meta_ads_cr_dashboard.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/market_trends.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/ds_insight_evaluation.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/meta_ads_大当たりCR分析.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/dpro_動画広告リサーチ.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/dpro_research_20260304.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/addness/",
        "owner": "internal",
        "disclosure_level": "task-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列", "直下"],
    },
    {
        "prefix": "Master/learning/execution_rules.json",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/learning/README.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/learning/",
        "owner": "self",
        "disclosure_level": "self-only",
        "approval_required": "always",
        "audience": ["僕"],
    },
    {
        "prefix": "Master/sheets/README.md",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
    {
        "prefix": "Master/sheets/",
        "owner": "internal",
        "disclosure_level": "role-limited",
        "approval_required": "conditional",
        "audience": ["僕", "上司", "並列"],
    },
]
TARGETS = [
    "Master/README.md",
    "Master/前提/README.md",
    "Master/前提/判断軸.md",
    "Master/前提/目的.md",
    "Master/前提/優先順位.md",
    "Master/前提/本人基本プロフィール.md",
    "Master/前提/更新ルール.md",
    "Master/knowledge/accounts.md",
    "Master/knowledge/環境マップ.md",
    "Master/knowledge/秘書の視界マップ.md",
    "Master/knowledge/定常業務.md",
    "Master/knowledge/広告CR失敗パターン.md",
    "Master/knowledge/経理月次運用.md",
    "Master/knowledge/経理運用ルール.md",
    "Master/addness/funnel_structure.md",
    "Master/addness/zapier_structure.md",
    "Master/company/people_public.json",
    "Master/brains/kohara/brain_manifest.json",
    "Master/brains/kohara/people_private.json",
    "Master/brains/kohara/awakened_self.md",
    "Master/brains/hinata/brain_manifest.json",
    "Master/brains/hinata/people_private.json",
    "Master/brains/hinata/persona.md",
    "Master/brains/hinata/manager_principles.md",
    "Master/brains/hinata/domain_knowledge.md",
    "Master/self_clone/kohara/IDENTITY.md",
    "Master/self_clone/kohara/BRAIN_OS.md",
    "Master/self_clone/kohara/SELF_PROFILE.md",
    "Master/self_clone/kohara/USER.md",
    "Master/self_clone/kohara/SOUL.md",
    "Master/output/README.md",
    "Master/output/OUTPUT_REVIEW_TEMPLATE.md",
    "Master/output/LP_REVIEW_TEMPLATE.md",
    "Master/output/ai_handoff.md",
    "Master/addness/README.md",
    "Master/addness/ui_operations.md",
    "Master/addness/goal-tree.md",
    "Master/addness/actionable-tasks.md",
    "Master/addness/meta_ads_cr_dashboard.md",
    "Master/learning/README.md",
    "Master/sheets/README.md",
    "Master/rules/README.md",
    "Master/rules/rules.md",
    "Master/rules/開示境界ルール.md",
    "Master/rules/実行主体別の閲覧・出力ルール.md",
]


def _markdown_has_label(text: str) -> bool:
    return all(line in text for line in REQUIRED_MD_LINES)


def _audit_markdown(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return [f"{path.relative_to(ROOT_DIR)}: `{line}` がありません" for line in REQUIRED_MD_LINES if line not in text]


def _audit_json(path: Path) -> list[str]:
    problems: list[str] = []
    data = json.loads(path.read_text(encoding="utf-8"))
    rel = path.relative_to(ROOT_DIR)
    if not isinstance(data, dict):
        return [f"{rel}: top-level object ではありません"]

    for key in REQUIRED_JSON_KEYS:
        if key not in data:
            problems.append(f"{rel}: `{key}` がありません")

    owner = data.get("owner")
    if owner is not None and owner not in ALLOWED_OWNER:
        problems.append(f"{rel}: owner `{owner}` は許可値外です")

    disclosure = data.get("disclosure_level")
    if disclosure is not None and disclosure not in ALLOWED_DISCLOSURE:
        problems.append(f"{rel}: disclosure_level `{disclosure}` は許可値外です")

    approval = data.get("approval_required")
    if approval is not None and approval not in ALLOWED_APPROVAL:
        problems.append(f"{rel}: approval_required `{approval}` は許可値外です")

    audience = data.get("audience")
    if audience is not None:
        if not isinstance(audience, list) or not audience:
            problems.append(f"{rel}: audience は空でない配列である必要があります")
        else:
            invalid = [item for item in audience if item not in ALLOWED_AUDIENCE]
            if invalid:
                problems.append(f"{rel}: audience に不正値があります: {', '.join(map(str, invalid))}")

    return problems


def _validate_policy(policy: dict, rel_path: str) -> list[str]:
    problems: list[str] = []
    if policy.get("owner") not in ALLOWED_OWNER:
        problems.append(f"{rel_path}: policy owner `{policy.get('owner')}` は許可値外です")
    if policy.get("disclosure_level") not in ALLOWED_DISCLOSURE:
        problems.append(f"{rel_path}: policy disclosure_level `{policy.get('disclosure_level')}` は許可値外です")
    if policy.get("approval_required") not in ALLOWED_APPROVAL:
        problems.append(f"{rel_path}: policy approval_required `{policy.get('approval_required')}` は許可値外です")
    audience = policy.get("audience", [])
    if not isinstance(audience, list) or not audience:
        problems.append(f"{rel_path}: policy audience は空でない配列である必要があります")
    else:
        invalid = [item for item in audience if item not in ALLOWED_AUDIENCE]
        if invalid:
            problems.append(f"{rel_path}: policy audience に不正値があります: {', '.join(map(str, invalid))}")
    return problems


def _match_path_policy(rel_path: str) -> Optional[dict]:
    matched = None
    for policy in PATH_POLICIES:
        prefix = policy["prefix"]
        if rel_path.startswith(prefix):
            if matched is None or len(prefix) > len(matched["prefix"]):
                matched = policy
    return matched


def main() -> int:
    problems: list[str] = []
    explicit_targets = set(TARGETS)
    explicit_ok = 0
    for rel_path in TARGETS:
        path = ROOT_DIR / rel_path
        if not path.exists():
            problems.append(f"{rel_path}: 対象ファイルが存在しません")
            continue
        if path.suffix == ".json":
            problems.extend(_audit_json(path))
        else:
            problems.extend(_audit_markdown(path))
        explicit_ok += 1

    inherited_ok = 0
    for rel_dir, allowed_suffixes in LEGACY_AUDIT_DIRS.items():
        base_dir = ROOT_DIR / rel_dir
        if not base_dir.exists():
            problems.append(f"{rel_dir}: 監査対象ディレクトリが存在しません")
            continue
        for path in sorted(base_dir.rglob("*")):
            if not path.is_file() or path.suffix not in allowed_suffixes:
                continue
            rel_path = str(path.relative_to(ROOT_DIR))
            if rel_path in explicit_targets:
                continue
            if path.suffix == ".md":
                text = path.read_text(encoding="utf-8")
                if _markdown_has_label(text):
                    inherited_ok += 1
                    continue
            policy = _match_path_policy(rel_path)
            if policy is None:
                problems.append(f"{rel_path}: 明示ラベルも path 既定値もありません")
                continue
            problems.extend(_validate_policy(policy, rel_path))
            inherited_ok += 1

    if problems:
        print("NG: Master ラベル監査で問題が見つかりました")
        for problem in problems:
            print(f"- {problem}")
        return 1

    print(
        f"OK: 明示ラベル {explicit_ok} 件 + 継承ラベル {inherited_ok} 件を含む "
        f"{explicit_ok + inherited_ok} 件を監査しました"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
