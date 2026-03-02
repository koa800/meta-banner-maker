#!/usr/bin/env python3
from __future__ import annotations
"""
Addness 実行可能タスク抽出

Goal Tree から「今すぐ実行できるタスク」を抽出する。

抽出条件:
  1. 甲原海人が担当 or 配下のゴール
  2. 完了していない
  3. リーフノード（子がすべて完了、または子なし）→ 実行可能
  4. 期日・緊急度でソート

出力:
  - Master/addness/actionable-tasks.md : ツール非依存の実行可能タスク一覧
  - .cursor/rules/addness-actionable.mdc : Cursor自動注入用
"""

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_PATH = SCRIPT_DIR / "addness_data" / "latest.json"
MASTER_DIR = PROJECT_ROOT / "Master" / "addness"
CURSOR_RULES_DIR = PROJECT_ROOT / ".cursor" / "rules"

USER_KEYWORDS = ["甲原"]


@dataclass
class Task:
    title: str
    assignee: str = ""
    due_date: str = ""
    status: str = ""
    phase: str = ""
    description: str = ""
    parent_chain: list = field(default_factory=list)
    depth: int = 0
    has_active_children: bool = False
    priority_score: float = 0.0

    @property
    def status_label(self) -> str:
        s = (self.status or "").upper()
        p = (self.phase or "").upper()
        if s == "COMPLETED":
            return "完了"
        if s == "NONE" and p == "PROCESS":
            return "実行中"
        if s == "NONE" and p == "EXPLORE":
            return "検討中"
        return s or p or "不明"

    @property
    def is_completed(self) -> bool:
        return (self.status or "").upper() == "COMPLETED"

    @property
    def is_executing(self) -> bool:
        return (self.phase or "").upper() == "PROCESS"

    @property
    def is_exploring(self) -> bool:
        return (self.phase or "").upper() == "EXPLORE"

    def days_until_due(self) -> int | None:
        if not self.due_date:
            return None
        try:
            for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
                try:
                    due = datetime.strptime(self.due_date, fmt).date()
                    return (due - date.today()).days
                except ValueError:
                    continue
        except Exception:
            pass
        return None

    @property
    def is_overdue(self) -> bool:
        d = self.days_until_due()
        return d is not None and d < 0

    @property
    def is_due_this_week(self) -> bool:
        d = self.days_until_due()
        return d is not None and 0 <= d <= 7


def format_date(raw) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%Y/%m/%d")
    except Exception:
        import re
        m = re.search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", str(raw))
        return m.group().replace("-", "/") if m else ""


def is_user_assigned(assignee: str) -> bool:
    return any(kw in (assignee or "") for kw in USER_KEYWORDS)


def load_data() -> dict:
    if not DATA_PATH.exists():
        print(f"エラー: {DATA_PATH} が見つかりません")
        print("先に addness_fetcher.py を実行してください")
        sys.exit(1)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_tasks_from_previews(data: dict) -> list[Task]:
    """Preview APIデータから全タスクをフラットに抽出"""
    api = data.get("api_responses", {})
    previews: dict = {}
    for key, val in api.items():
        if "/objectives/" not in key or not key.endswith("/preview"):
            continue
        d = val.get("data", val) if isinstance(val, dict) else val
        if isinstance(d, dict) and d.get("id"):
            previews[d["id"]] = d

    if not previews:
        return []

    tasks: list[Task] = []
    visited: set = set()

    def walk(goal: dict, parent_chain: list, depth: int):
        gid = goal.get("id", "")
        if gid in visited:
            return
        visited.add(gid)

        owner = goal.get("owner") or {}
        children = goal.get("children") or []

        active_children = [
            c for c in children
            if isinstance(c, dict) and (c.get("status") or "").upper() != "COMPLETED"
        ]

        task = Task(
            title=goal.get("title", ""),
            assignee=owner.get("name", ""),
            due_date=format_date(goal.get("dueDate")),
            status=goal.get("status", ""),
            phase=goal.get("phase", ""),
            description=goal.get("description", "") or "",
            parent_chain=parent_chain.copy(),
            depth=depth,
            has_active_children=len(active_children) > 0,
        )
        tasks.append(task)

        for child in children:
            if not isinstance(child, dict) or not child.get("title"):
                continue
            cid = child.get("id", "")
            if cid in previews:
                walk(previews[cid], parent_chain + [task.title], depth + 1)
            else:
                walk(child, parent_chain + [task.title], depth + 1)

    roots = [d for d in previews.values() if not d.get("parentObjectiveId")]
    if not roots:
        all_child_ids: set = set()
        for d in previews.values():
            for c in d.get("children", []):
                if isinstance(c, dict) and c.get("id"):
                    all_child_ids.add(c["id"])
        roots = [d for d in previews.values() if d["id"] not in all_child_ids]

    for root in roots:
        walk(root, [], 0)

    return tasks


def compute_priority(task: Task) -> float:
    """
    優先度スコアを算出。高いほど優先。

    重み付け:
    - 実行可能（リーフ）: +50
    - 自分の担当: +30
    - 実行中: +20, 検討中: +10
    - 期限超過: +40, 今週期限: +25
    - 説明あり: +10（実行しやすさ）
    """
    score = 0.0

    if not task.has_active_children:
        score += 50
    if is_user_assigned(task.assignee):
        score += 30
    if task.is_executing:
        score += 20
    elif task.is_exploring:
        score += 10

    if task.is_overdue:
        score += 40
    elif task.is_due_this_week:
        score += 25
    elif task.due_date:
        score += 5

    if task.description:
        score += 10

    return score


def filter_actionable(tasks: list[Task]) -> list[Task]:
    """
    実行可能タスクを抽出（直接担当のみ）:
    1. 甲原海人が直接担当
    2. 完了していない
    3. リーフノード（未完了の子がない）= 今すぐ着手できる
    """
    actionable = []
    for t in tasks:
        if t.is_completed:
            continue
        if not is_user_assigned(t.assignee):
            continue
        if not t.has_active_children:
            t.priority_score = compute_priority(t)
            actionable.append(t)

    actionable.sort(key=lambda t: -t.priority_score)
    return actionable


def filter_watching(tasks: list[Task]) -> list[Task]:
    """
    ウォッチ対象（自分が直接担当だが、子タスクが動いている中間ノード）
    """
    watch = []
    for t in tasks:
        if t.is_completed:
            continue
        if is_user_assigned(t.assignee) and t.has_active_children:
            t.priority_score = compute_priority(t)
            watch.append(t)
    watch.sort(key=lambda t: -t.priority_score)
    return watch


def filter_delegated_blocked(tasks: list[Task]) -> list[Task]:
    """
    委任先の期限超過タスク: 自分が上位の担当だが、実際のリーフは別の人に委任されていて期限超過。
    フォロー・エスカレーション判断用。
    """
    user_titles: set = {t.title for t in tasks if is_user_assigned(t.assignee)}
    blocked = []
    for t in tasks:
        if t.is_completed or t.has_active_children:
            continue
        if is_user_assigned(t.assignee):
            continue
        if not t.is_overdue:
            continue
        if any(p in user_titles for p in t.parent_chain):
            t.priority_score = compute_priority(t)
            blocked.append(t)
    blocked.sort(key=lambda t: -t.priority_score)
    return blocked[:20]


def render_actionable_md(actionable: list[Task], watching: list[Task], delegated_blocked: list[Task], fetched_at: str) -> str:
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        "# 実行可能タスク一覧（甲原海人）",
        "",
        f"| 項目 | 値 |",
        "|---|---|",
        f"| 更新日時 | {now} |",
        f"| データ取得 | {fetched_at} |",
        f"| 実行可能タスク数 | {len(actionable)} |",
        f"| ウォッチ中ゴール数 | {len(watching)} |",
        f"| 委任先超過タスク | {len(delegated_blocked)} |",
        "",
    ]

    overdue = [t for t in actionable if t.is_overdue]
    due_soon = [t for t in actionable if t.is_due_this_week and not t.is_overdue]
    executing = [t for t in actionable if t.is_executing and not t.is_overdue and not t.is_due_this_week]
    exploring = [t for t in actionable if t.is_exploring and not t.is_overdue and not t.is_due_this_week]
    rest = [t for t in actionable if t not in overdue and t not in due_soon and t not in executing and t not in exploring]

    def render_task(t: Task, idx: int) -> list[str]:
        ctx = " > ".join(t.parent_chain[-2:]) if t.parent_chain else ""
        ls = []
        due_str = ""
        if t.due_date:
            d = t.days_until_due()
            if d is not None and d < 0:
                due_str = f" **期限: {t.due_date}（{abs(d)}日超過）**"
            elif d is not None and d <= 7:
                due_str = f" 期限: {t.due_date}（残{d}日）"
            else:
                due_str = f" 期限: {t.due_date}"
        assignee_str = f" 担当: {t.assignee}" if t.assignee else ""
        ls.append(f"{idx}. **{t.title}**{due_str}{assignee_str}")
        if ctx:
            ls.append(f"   - 上位: {ctx}")
        if t.description:
            desc_preview = t.description.strip().replace("\n", " ")[:120]
            ls.append(f"   - 概要: {desc_preview}")
        return ls

    if overdue:
        lines.append("## 🔴 期限超過（即対応）")
        lines.append("")
        for i, t in enumerate(overdue, 1):
            lines.extend(render_task(t, i))
            lines.append("")

    if due_soon:
        lines.append("## ⚡ 今週期限")
        lines.append("")
        for i, t in enumerate(due_soon, 1):
            lines.extend(render_task(t, i))
            lines.append("")

    if executing:
        lines.append("## 🔄 実行中")
        lines.append("")
        for i, t in enumerate(executing, 1):
            lines.extend(render_task(t, i))
            lines.append("")

    if exploring:
        lines.append("## 🔍 検討中（着手可能）")
        lines.append("")
        for i, t in enumerate(exploring[:20], 1):
            lines.extend(render_task(t, i))
            lines.append("")
        if len(exploring) > 20:
            lines.append(f"   _...他{len(exploring) - 20}件_")
            lines.append("")

    if rest:
        lines.append("## 📌 その他")
        lines.append("")
        for i, t in enumerate(rest[:10], 1):
            lines.extend(render_task(t, i))
            lines.append("")
        if len(rest) > 10:
            lines.append(f"   _...他{len(rest) - 10}件_")
            lines.append("")

    if watching:
        lines.append("---")
        lines.append("")
        lines.append("## 👁 ウォッチ中（子タスクが進行中）")
        lines.append("")
        for i, t in enumerate(watching[:15], 1):
            active_label = f"[{t.status_label}]"
            due_str = f" 期限: {t.due_date}" if t.due_date else ""
            lines.append(f"{i}. {active_label} **{t.title}**{due_str}")
        if len(watching) > 15:
            lines.append(f"   _...他{len(watching) - 15}件_")
        lines.append("")

    if delegated_blocked:
        lines.append("---")
        lines.append("")
        lines.append("## ⚠️ 委任先で期限超過（フォロー推奨）")
        lines.append("")
        for i, t in enumerate(delegated_blocked, 1):
            d = abs(t.days_until_due() or 0)
            ctx = " > ".join(t.parent_chain[-2:]) if t.parent_chain else ""
            lines.append(f"{i}. **{t.title}** [{t.due_date}, {d}日超過] 担当: {t.assignee}")
            if ctx:
                lines.append(f"   - 上位: {ctx}")
        lines.append("")

    lines.append("---")
    lines.append("> `System/addness_task_extractor.py` で自動生成。")
    return "\n".join(lines)


def render_cursor_mdc(actionable: list[Task], watching: list[Task]) -> str:
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        "---",
        'description: "Addness実行可能タスク（自動抽出）"',
        "alwaysApply: true",
        "---",
        "",
        f"# 甲原海人の実行可能タスク（{now} 更新）",
        "",
    ]

    top_tasks = actionable[:15]

    overdue = [t for t in top_tasks if t.is_overdue]
    due_soon = [t for t in top_tasks if t.is_due_this_week and not t.is_overdue]
    other = [t for t in top_tasks if t not in overdue and t not in due_soon]

    if overdue:
        lines.append("## 🔴 期限超過")
        for t in overdue:
            d = abs(t.days_until_due() or 0)
            lines.append(f"- {t.title}｜{t.due_date}（{d}日超過）｜{t.assignee}")
        lines.append("")

    if due_soon:
        lines.append("## ⚡ 今週期限")
        for t in due_soon:
            d = t.days_until_due() or 0
            lines.append(f"- {t.title}｜{t.due_date}（残{d}日）｜{t.assignee}")
        lines.append("")

    if other:
        lines.append("## 実行可能")
        for t in other:
            status = "🔄" if t.is_executing else "🔍"
            due = f"｜期限:{t.due_date}" if t.due_date else ""
            lines.append(f"- {status} {t.title}｜{t.assignee}{due}")
        lines.append("")

    lines.append(f"合計: 実行可能{len(actionable)}件 / ウォッチ{len(watching)}件")
    lines.append("")
    lines.append("詳細: `Master/addness/actionable-tasks.md`")
    lines.append("")
    lines.append("---")
    lines.append("*自動生成。手動編集不可。*")
    return "\n".join(lines)


def main():
    print(f"[{datetime.now().isoformat()}] タスク抽出開始")

    data = load_data()
    fetched_at = data.get("fetched_at", "不明")
    print(f"  データ取得日時: {fetched_at}")

    print("タスク抽出中...")
    all_tasks = extract_tasks_from_previews(data)
    print(f"  全タスク: {len(all_tasks)}件")

    actionable = filter_actionable(all_tasks)
    watching = filter_watching(all_tasks)
    delegated = filter_delegated_blocked(all_tasks)
    print(f"  実行可能: {len(actionable)}件")
    print(f"  ウォッチ: {len(watching)}件")
    print(f"  委任先超過: {len(delegated)}件")

    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    md_path = MASTER_DIR / "actionable-tasks.md"
    md_path.write_text(render_actionable_md(actionable, watching, delegated, fetched_at), encoding="utf-8")
    print(f"  → {md_path}")

    CURSOR_RULES_DIR.mkdir(parents=True, exist_ok=True)
    mdc_path = CURSOR_RULES_DIR / "addness-actionable.mdc"
    mdc_path.write_text(render_cursor_mdc(actionable, watching), encoding="utf-8")
    print(f"  → {mdc_path}")

    if actionable:
        print("\n--- TOP 5 実行可能タスク ---")
        for i, t in enumerate(actionable[:5], 1):
            due = f" [{t.due_date}]" if t.due_date else ""
            score = f" (score:{t.priority_score:.0f})"
            print(f"  {i}. {t.title}{due}{score}")

    print(f"\n[{datetime.now().isoformat()}] 完了")


if __name__ == "__main__":
    main()
