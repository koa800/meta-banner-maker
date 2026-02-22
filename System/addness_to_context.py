#!/usr/bin/env python3
"""
Addness → コンテキスト変換スクリプト

addness_data/latest.json を読み込み:
  1. .cursor/rules/addness-goals.mdc  → Cursorに常時注入されるサマリー
  2. Skills/addness-goal-tree.md              → 完全ツリー（手動参照用）
  3. LINE Notify で更新通知

APIエンドポイント: /api/v1/team/daily_focus_objectives/tree
フィールド: id, title, description, dueDate, status, phase, owner.name, children[]
"""

import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger("addness_to_context")

import requests

# ---- パス設定 ----
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = SCRIPT_DIR / "config" / "addness.json"
DATA_PATH = SCRIPT_DIR / "addness_data" / "latest.json"
CURSOR_RULES_DIR = PROJECT_ROOT / ".cursor" / "rules"
MASTER_DIR = PROJECT_ROOT / "Master" / "addness"

# Addness のツリーエンドポイント
TREE_ENDPOINT = "/api/v1/team/daily_focus_objectives/tree"


# ---- データ構造 ----

@dataclass
class GoalNode:
    title: str
    purpose: str = ""
    assignee: str = ""
    due_date: str = ""
    status: str = ""
    phase: str = ""
    children: list = field(default_factory=list)

    def is_overdue(self) -> bool:
        if not self.due_date:
            return False
        try:
            due = datetime.strptime(self.due_date, "%Y/%m/%d").date()
            return due < date.today()
        except Exception:
            return False

    def is_due_this_week(self) -> bool:
        if not self.due_date:
            return False
        try:
            due = datetime.strptime(self.due_date, "%Y/%m/%d").date()
            delta = (due - date.today()).days
            return 0 <= delta <= 7
        except Exception:
            return False


# ---- ユーティリティ ----

def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_latest_json() -> dict:
    if not DATA_PATH.exists():
        print(f"エラー: {DATA_PATH} が見つかりません")
        print("先に addness_fetcher.py を実行してください")
        sys.exit(1)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def format_date(raw) -> str:
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt.strftime("%Y/%m/%d")
    except Exception:
        m = re.search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", str(raw))
        return m.group().replace("-", "/") if m else ""


def status_label(status: str, phase: str) -> str:
    """Addness の status/phase を日本語表示に変換"""
    s = (status or "").upper()
    p = (phase or "").upper()
    if s == "COMPLETED":
        return "✅ 完了"
    if s == "NONE" and p == "PROCESS":
        return "🔄 実行中"
    if s == "NONE" and p == "EXPLORE":
        return "🔍 検討中"
    if s == "NONE":
        return "📌 未着手"
    return s or p or ""


def count_nodes(nodes: list) -> int:
    total = len(nodes)
    for n in nodes:
        total += count_nodes(n.children)
    return total


def collect_due_soon(nodes: list) -> list:
    result = []
    for n in nodes:
        if n.due_date and (n.is_due_this_week() or n.is_overdue()):
            result.append(n)
        result.extend(collect_due_soon(n.children))
    return result


# ---- Addness 専用パーサー ----

def parse_node(raw: dict) -> GoalNode:
    """Addness API の objectives ノードを GoalNode に変換"""
    owner = raw.get("owner") or {}
    node = GoalNode(
        title=raw.get("title") or "",
        purpose=raw.get("description") or "",
        assignee=owner.get("name") or "",
        due_date=format_date(raw.get("dueDate")),
        status=raw.get("status") or "",
        phase=raw.get("phase") or "",
    )
    for child_raw in raw.get("children") or []:
        if isinstance(child_raw, dict) and child_raw.get("title"):
            node.children.append(parse_node(child_raw))
    return node


def extract_from_addness_api(data: dict) -> tuple:
    """
    /api/v1/team/daily_focus_objectives/tree から完全ツリーを抽出
    Addness 専用・最優先で使用
    """
    api = data.get("api_responses", {})
    tree_data = api.get(TREE_ENDPOINT)
    if not tree_data:
        # 部分一致でも探す
        for key, val in api.items():
            if "tree" in key and "objectives" in key:
                tree_data = val
                break

    if not tree_data:
        return [], ""

    items = tree_data.get("data") or []
    if not isinstance(items, list) or not items:
        return [], ""

    nodes = [parse_node(item) for item in items if isinstance(item, dict) and item.get("title")]
    return nodes, f"Addness API ({TREE_ENDPOINT})"


def extract_fallback(data: dict) -> tuple:
    """APIが取れなかった場合のフォールバック（ページテキスト）"""
    headings = data.get("page_text", {}).get("headings", [])
    nodes = [
        GoalNode(title=h["text"])
        for h in headings[:15]
        if h.get("text") and len(h["text"]) > 2
    ]
    if nodes:
        return nodes, "ページ見出し（要再取得）"
    return [GoalNode(title="データなし（addness_fetcher.py を再実行してください）")], "不明"


def extract_from_previews(data: dict) -> tuple:
    """
    /api/v1/team/objectives/{id}/preview から担当者・説明・完了基準付きの完全ツリーを構築する。
    preview.data = {id, title, description, status, phase, dueDate, owner, children[]}
    children[] = 直接の子ゴール（各フィールド付き）
    """
    api = data.get("api_responses", {})

    # preview データを収集
    previews: dict = {}  # goalId -> goal data
    for key, val in api.items():
        if "/objectives/" not in key or not key.endswith("/preview"):
            continue
        d = val.get("data", val) if isinstance(val, dict) else val
        if isinstance(d, dict) and d.get("id"):
            previews[d["id"]] = d

    if not previews:
        return [], ""

    # ルートを特定（parentObjectiveId が None）
    root_goals = [d for d in previews.values() if not d.get("parentObjectiveId")]
    if not root_goals:
        # フォールバック: 他の誰かの子になっていないゴール
        all_child_ids: set = set()
        for d in previews.values():
            for c in d.get("children", []):
                if isinstance(c, dict) and c.get("id"):
                    all_child_ids.add(c["id"])
        root_goals = [d for d in previews.values() if d["id"] not in all_child_ids]

    def parse_preview_node(goal_data: dict, visited: set) -> "GoalNode":
        gid = goal_data.get("id", "")
        if gid in visited:
            return None
        visited = visited | {gid}
        owner = goal_data.get("owner") or {}
        node = GoalNode(
            title=goal_data.get("title", ""),
            purpose=goal_data.get("description", ""),
            assignee=owner.get("name", ""),
            due_date=format_date(goal_data.get("dueDate")),
            status=goal_data.get("status", ""),
            phase=goal_data.get("phase", ""),
        )
        for child in goal_data.get("children", []):
            if not isinstance(child, dict) or not child.get("title"):
                continue
            cid = child.get("id", "")
            if cid in visited:
                continue
            # 子のpreviewがあればそちらを優先（より深い階層まで取得できる）
            if cid in previews:
                child_node = parse_preview_node(previews[cid], visited)
            else:
                child_owner = child.get("owner") or {}
                child_node = GoalNode(
                    title=child.get("title", ""),
                    purpose=child.get("description", ""),
                    assignee=child_owner.get("name", ""),
                    due_date=format_date(child.get("dueDate")),
                    status=child.get("status", ""),
                    phase=child.get("phase", ""),
                )
            if child_node:
                node.children.append(child_node)
        return node

    nodes = [parse_preview_node(g, set()) for g in root_goals if g.get("title")]
    nodes = [n for n in nodes if n]

    if nodes:
        total = count_nodes(nodes)
        return nodes, f"Preview API（{len(previews)}プレビュー/{total}ノード）"
    return [], ""


def extract_from_goal_pages(data: dict) -> tuple:
    """
    ancestors API + ゴールページDOMから組織全体ツリーを再構築する。

    処理の流れ:
    1. /api/v1/team/objectives/{id}/ancestors → 各ゴールの直接の親IDを特定
    2. サイドバーIDセットを作成（ページ横断で共通のナビゲーション項目）
    3. /goal_pages/children_links → サイドバーIDを除いた実際の子リンクを補完
    4. ルートIDを「最も多く親として参照されるID」で特定
    5. ルートからツリーを構築
    """
    from collections import Counter
    api = data.get("api_responses", {})

    # ゴールIDとタイトルのマッピング
    goal_titles: dict = {}  # goalId -> title

    # `ancestors` レスポンスから直接の親子関係を構築
    parent_of: dict = {}  # childId -> parentId
    for key, val in api.items():
        if "/objectives/" not in key or not key.endswith("/ancestors"):
            continue
        # URLからchild_idを抽出
        parts = key.rstrip("/").split("/")
        child_id = next(
            (p for p in parts if len(p) == 36 and p.count("-") == 4), None
        )
        if not child_id:
            continue
        ancestors_list = val.get("data", val) if isinstance(val, dict) else val
        if not isinstance(ancestors_list, list) or len(ancestors_list) < 2:
            # 要素が1つ以下 = ルートゴール（親なし）→スキップ
            continue
        # ancestors リストはルートから並び、末尾はゴール自身: [root, ..., parent, self]
        # 直接の親 = 末尾から2番目
        immediate = ancestors_list[-2]
        if not isinstance(immediate, dict):
            continue
        pid = immediate.get("id")
        ptitle = immediate.get("title", "")
        if pid:
            parent_of[child_id] = pid
            if ptitle and pid not in goal_titles:
                goal_titles[pid] = ptitle

    # サイドバーからゴールIDとタイトルを収集
    sidebar_ids: set = set()
    for key in ("/sidebar/all_links", "/sidebar/goals"):
        src = api.get(key, {})
        items = src.get("items", []) if isinstance(src, dict) else []
        for item in items:
            gid = item.get("goalId")
            title = item.get("title", "")
            if gid and title:
                goal_titles[gid] = title
                sidebar_ids.add(gid)

    if not parent_of and not sidebar_ids:
        return [], ""

    # ルートIDを特定（アンセスタデータで最も多く参照される親）
    root_id = None
    if parent_of:
        root_id = Counter(parent_of.values()).most_common(1)[0][0]

    # ルートのタイトルを daily_focus tree から補完
    if root_id and root_id not in goal_titles:
        tree_data = api.get(TREE_ENDPOINT, {})
        for item in (tree_data.get("data") or []):
            if isinstance(item, dict) and item.get("id") == root_id:
                goal_titles[root_id] = item.get("title", "")
                break

    # 親子関係マップを構築（ancestors データ優先）
    children_of: dict = {}  # parentId -> [childId]
    for child_id, par_id in parent_of.items():
        children_of.setdefault(par_id, [])
        if child_id not in children_of[par_id]:
            children_of[par_id].append(child_id)

    # 各ゴールページのDOMリンクで子を補完（サイドバーIDは除外）
    exclude_ids = sidebar_ids | ({root_id} if root_id else set())
    children_links: dict = api.get("/goal_pages/children_links", {})
    for par_id, links in children_links.items():
        for item in links:
            cid = item.get("goalId")
            title = item.get("title", "")
            if not cid or not title:
                continue
            if cid == par_id or cid in exclude_ids:
                continue
            if cid not in goal_titles:
                goal_titles[cid] = title
            children_of.setdefault(par_id, [])
            if cid not in children_of[par_id]:
                children_of[par_id].append(cid)

    if not root_id:
        return [], ""

    # ツリー構築
    def build_node(goal_id: str, visited: set) -> "GoalNode":
        if goal_id in visited:
            return None
        visited = visited | {goal_id}
        title = goal_titles.get(goal_id, goal_id[:8])
        node = GoalNode(title=title)
        for cid in children_of.get(goal_id, []):
            child = build_node(cid, visited)
            if child:
                node.children.append(child)
        return node

    root_node = build_node(root_id, set())
    if root_node:
        total = count_nodes([root_node])
        return [root_node], f"アンセスタ＋ページ巡回（{total}ノード/{len(goal_titles)}ゴール）"
    return [], ""


def _enrich_tree(page_nodes: list, focus_map: dict) -> list:
    """
    ゴールページ由来のノードに daily_focus の詳細情報をマージする。

    ルール:
    - metadata（担当者・期限・説明・ステータス）は focus から補完
    - ページに子がない場合は focus の子をそのまま使用
    - ページに子がある場合はページの子を enrich し、focus にしかない子を追加
    """
    def enrich(node: "GoalNode", visited: set) -> "GoalNode":
        if node.title in visited:
            return node
        visited = visited | {node.title}
        if node.title in focus_map:
            focused = focus_map[node.title]
            # metadata 補完
            node.purpose = node.purpose or focused.purpose
            node.assignee = node.assignee or focused.assignee
            node.due_date = node.due_date or focused.due_date
            node.status = node.status or focused.status
            node.phase = node.phase or focused.phase
            if not node.children:
                # ページで子が取れなかった → focus の子をそのまま使用
                node.children = focused.children
            else:
                # ページの子を再帰 enrich し、focus にしかない子を末尾に追加
                page_child_titles = {c.title for c in node.children}
                node.children = [enrich(c, visited) for c in node.children]
                for fc in focused.children:
                    if fc.title not in page_child_titles:
                        node.children.append(fc)
        else:
            node.children = [enrich(c, visited) for c in node.children]
        return node

    return [enrich(n, set()) for n in page_nodes]


def build_goal_tree(data: dict) -> tuple:
    # 優先度1: Preview API（担当者・説明・完了基準付き、組織全体）
    preview_nodes, preview_source = extract_from_previews(data)

    # 優先度2: daily_focus API（深い階層の詳細あり、ユーザースコープ）
    focus_nodes, focus_source = extract_from_addness_api(data)

    # 優先度3: ゴールページ巡回データ（構造のみ）
    page_nodes, page_source = extract_from_goal_pages(data)

    # preview + focus のマージ（previewが浅い子を focus で補完）
    if preview_nodes and focus_nodes:
        focus_map: dict = {}

        def index_focus(ns: list):
            for n in ns:
                focus_map[n.title] = n
                index_focus(n.children)

        index_focus(focus_nodes)
        merged = _enrich_tree(preview_nodes, focus_map)
        total = count_nodes(merged)
        print(f"  マージ完了: {preview_source} + {focus_source} → {total}ノード")
        return merged, f"統合（{preview_source}）"

    if preview_nodes:
        total = count_nodes(preview_nodes)
        print(f"  データソース: {preview_source} → {total}ノード")
        return preview_nodes, preview_source

    if page_nodes and focus_nodes:
        focus_map2: dict = {}

        def index_focus2(ns: list):
            for n in ns:
                focus_map2[n.title] = n
                index_focus2(n.children)

        index_focus2(focus_nodes)
        merged2 = _enrich_tree(page_nodes, focus_map2)
        total2 = count_nodes(merged2)
        print(f"  マージ完了: {page_source} + {focus_source} → {total2}ノード")
        return merged2, f"統合（{page_source}）"

    if page_nodes:
        print(f"  データソース: {page_source}")
        return page_nodes, page_source

    if focus_nodes:
        print(f"  データソース: {focus_source}")
        return focus_nodes, focus_source

    print("  警告: Addness APIデータが見つかりません。フォールバック使用")
    return extract_fallback(data)


# ---- Markdown 生成 ----

def _node_to_mdc(node: GoalNode, level: int) -> list:
    """Cursor rules 用の軽量サマリー行"""
    prefix = "#" * min(level + 2, 6) if level < 3 else "-"
    indent = "  " * max(0, level - 2) if level >= 3 else ""

    parts = [node.title]
    if node.assignee:
        parts.append(f"担当:{node.assignee}")
    if node.due_date:
        flag = "🔴" if node.is_overdue() else ("⚡" if node.is_due_this_week() else "")
        parts.append(f"期限:{node.due_date}{flag}")
    st = status_label(node.status, node.phase)
    if st:
        parts.append(st)

    lines = [f"{indent}{prefix} {'｜'.join(parts)}"]
    for child in node.children:
        lines.extend(_node_to_mdc(child, level + 1))
    return lines


# 自分（甲原海人）の担当ゴールかどうかを判定するキーワード
USER_ASSIGNEE_KEYWORDS = ["甲原"]


def _is_user_goal(node: GoalNode) -> bool:
    return any(kw in (node.assignee or "") for kw in USER_ASSIGNEE_KEYWORDS)


def _node_to_full_md(node: GoalNode, level: int, in_user_subtree: bool = False) -> list:
    """
    Skills 用の詳細形式。
    - 甲原海人担当ゴールとその配下: タイトル + 説明文全文
    - 並列の他ゴール: タイトル + 担当 + 期限のみ（説明なし）
    """
    heading = "#" * min(level + 2, 6)
    st = status_label(node.status, node.phase)

    lines = [f"{heading} {st} {node.title}"]

    # 自分の担当ゴール、または自分の配下にいる場合
    is_my_subtree = in_user_subtree or _is_user_goal(node)

    meta = []
    if node.assignee:
        meta.append(f"**担当**: {node.assignee}")
    if node.due_date:
        flag = "（🔴期限超過）" if node.is_overdue() else ("（⚡今週期限）" if node.is_due_this_week() else "")
        meta.append(f"**期限**: {node.due_date}{flag}")
    if meta:
        lines.append("　".join(meta))

    if node.purpose:
        desc_lines = [l.strip() for l in node.purpose.strip().split("\n") if l.strip()]
        if is_my_subtree:
            # 甲原海人配下: 説明文を全文表示
            lines.append("> " + "\n> ".join(desc_lines))
        else:
            # 並列ゴール: 最初の2行のみ
            preview = "\n> ".join(desc_lines[:2])
            if len(desc_lines) > 2:
                preview += f"\n> ...（全{len(desc_lines)}行）"
            lines.append(f"> {preview}")

    for child in node.children:
        lines.append("")
        lines.extend(_node_to_full_md(child, level + 1, in_user_subtree=is_my_subtree))
    return lines


def render_mdc(nodes: list, meta: dict) -> str:
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    lines = [
        "---",
        'description: "Addnessゴールツリー（自動生成・3日ごと更新）"',
        "alwaysApply: true",
        "---",
        "",
        f"# Addness ゴールツリー（{now_str} 更新）",
        "",
        f"データ: {meta.get('data_source', '')}",
        "",
    ]
    for node in nodes:
        lines.extend(_node_to_mdc(node, 0))
        lines.append("")
    lines += [
        "---",
        "*自動生成ファイル。手動編集不可。*",
    ]
    return "\n".join(lines)


def render_full_md(nodes: list, meta: dict) -> str:
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    total = count_nodes(nodes)
    lines = [
        "# Addness ゴールツリー（完全版）",
        "",
        f"| | |",
        "|---|---|",
        f"| 最終更新 | {now_str} |",
        f"| 取得元 | {meta.get('source_url', '')} |",
        f"| ノード数 | {total} 件 |",
        "",
        "---",
        "",
    ]
    for node in nodes:
        lines.extend(_node_to_full_md(node, 0))
        lines.append("")
    lines += [
        "---",
        "> `System/addness_to_context.py` によって自動生成。手動編集不可。",
    ]
    return "\n".join(lines)


# ---- Slack通知 ----

def build_notification(nodes: list, meta: dict, data_source: str) -> str:
    now_str = datetime.now().strftime("%Y/%m/%d %H:%M")
    total = count_nodes(nodes)
    due_soon = collect_due_soon(nodes)

    root_title = nodes[0].title[:25] if nodes else "不明"
    lines = [
        f"*【Addness ゴールツリー更新】* {now_str}",
        "",
        f":dart: {root_title}",
        f":bar_chart: ノード数: {total}件",
    ]
    if due_soon:
        lines.append(f":zap: 今週・期限超過: {len(due_soon)}件")

    if due_soon:
        lines.append("\n*要対応*")
        for n in due_soon[:5]:
            flag = ":red_circle:" if n.is_overdue() else ":zap:"
            assignee = f"({n.assignee})" if n.assignee else ""
            lines.append(f"{flag} {n.title[:22]} {n.due_date} {assignee}")

    lines += [
        "",
        "> `Master/addness/goal-tree.md` に保存済み",
    ]
    return "\n".join(lines)


def send_slack_notify(webhook_url: str, message: str, channel: str = "") -> bool:
    try:
        import json as _json
        payload = {"text": message}
        if channel:
            payload["channel"] = channel
        resp = requests.post(
            webhook_url,
            headers={"Content-Type": "application/json"},
            data=_json.dumps(payload),
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  Slack通知エラー: {resp.status_code} {resp.text}")
            return False
        return True
    except Exception as e:
        print(f"  Slack送信エラー: {e}")
        return False


# ---- メイン ----

def main():
    print(f"[{datetime.now().isoformat()}] addness_to_context 開始")

    config = load_config()
    raw = load_latest_json()

    print("ゴールツリー抽出中...")
    nodes, data_source = build_goal_tree(raw)

    meta = {
        "source_url": raw.get("source_url", ""),
        "fetched_at": raw.get("fetched_at", ""),
        "data_source": data_source,
    }

    total = count_nodes(nodes)
    print(f"  → {total} ノード取得")

    # .cursor/rules/addness-goals.mdc
    CURSOR_RULES_DIR.mkdir(parents=True, exist_ok=True)
    mdc_path = CURSOR_RULES_DIR / "addness-goals.mdc"
    mdc_path.write_text(render_mdc(nodes, meta), encoding="utf-8")
    print(f"  → {mdc_path}")

    # Master/addness/goal-tree.md
    MASTER_DIR.mkdir(parents=True, exist_ok=True)
    master_path = MASTER_DIR / "goal-tree.md"
    master_path.write_text(render_full_md(nodes, meta), encoding="utf-8")
    print(f"  → {master_path}")

    # Slack通知
    slack_webhook = config.get("slack_webhook_url", "")
    slack_channel = config.get("slack_channel", "")
    if slack_webhook:
        print("Slack通知送信中...")
        ok = send_slack_notify(slack_webhook, build_notification(nodes, meta, data_source), slack_channel)
        print("  → 送信成功" if ok else "  → 送信失敗")
    else:
        print("Slack通知スキップ（slack_webhook_url 未設定）")

    print(f"[{datetime.now().isoformat()}] 完了")


if __name__ == "__main__":
    main()
