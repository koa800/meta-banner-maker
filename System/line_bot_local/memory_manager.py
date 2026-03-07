"""
Memory Manager — 秘書の記憶システム
短期記憶（会話履歴）と長期記憶（secretary_memory.md）を管理する。
"""

from __future__ import annotations

import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# 記憶ファイルのパス（git管理外）
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_FILE = DATA_DIR / "secretary_memory.md"
LEGACY_CONVERSATIONS_DIR = DATA_DIR / "conversations"
SHELL_STATE_DIR = DATA_DIR / "shell_state"
SHARED_CONTEXT_DIR = DATA_DIR / "shared_context"
SHARED_EVENT_STREAM = SHARED_CONTEXT_DIR / "event_stream.jsonl"
SHARED_ACTIVE_CONTEXT_FILE = SHARED_CONTEXT_DIR / "active_context.json"
PROMOTED_CONTEXT_FILE = SHARED_CONTEXT_DIR / "promoted_context.jsonl"

# 上限
MAX_MEMORY_LINES = 100
SHORT_TERM_MAX = {
    "secretary_group": 20,  # 秘書グループ: 直近20往復
    "default": 10,          # 他グループ: 直近10往復
    "qa": 0,                # Q&A: 履歴を持たない
}
SESSION_TIMEOUT_SEC = 6 * 3600  # 6時間無操作でリセット


def _ensure_dirs():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    SHELL_STATE_DIR.mkdir(parents=True, exist_ok=True)
    SHARED_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)


def _atomic_write_text(path: Path, content: str):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def _atomic_write_json(path: Path, payload: dict[str, Any]):
    _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _load_json(path: Path, default: Any):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


# ---------------------------------------------------------------------------
# 長期記憶
# ---------------------------------------------------------------------------

def load_long_term_memory() -> str:
    """長期記憶ファイルを読み込んで返す"""
    _ensure_dirs()
    if not MEMORY_FILE.exists():
        return ""
    return MEMORY_FILE.read_text(encoding="utf-8")


def save_long_term_memory(content: str):
    """長期記憶ファイルを上書き保存"""
    _ensure_dirs()
    _atomic_write_text(MEMORY_FILE, content)
    logger.info(f"長期記憶を更新しました（{len(content)}文字）")


def append_memory(entry: str):
    """長期記憶に1エントリ追記"""
    current = load_long_term_memory()
    timestamp = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"- [{timestamp}] {entry}"

    if "## 覚えておくべき文脈" in current:
        current = current.replace(
            "## 覚えておくべき文脈",
            f"## 覚えておくべき文脈\n{new_entry}",
        )
    else:
        current += f"\n{new_entry}\n"

    # 行数制限チェック
    lines = current.strip().split("\n")
    if len(lines) > MAX_MEMORY_LINES:
        logger.warning(f"長期記憶が{len(lines)}行 → 上限{MAX_MEMORY_LINES}行を超過。棚卸しが必要です。")

    save_long_term_memory(current)
    record_promoted_context(entry, source="update_memory")


def remove_memory(keyword: str) -> bool:
    """キーワードを含む記憶エントリを削除"""
    current = load_long_term_memory()
    lines = current.split("\n")
    new_lines = [line for line in lines if keyword not in line]
    if len(new_lines) == len(lines):
        return False
    save_long_term_memory("\n".join(new_lines))
    return True


def record_promoted_context(entry: str, source: str = "manual", metadata: dict[str, Any] | None = None):
    """長期記憶に昇格した内容を構造化ログとして残す"""
    _ensure_dirs()
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "entry": entry,
        "metadata": metadata or {},
    }
    with PROMOTED_CONTEXT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 短期記憶（会話履歴）
# ---------------------------------------------------------------------------

def _conversation_dir(shell_name: str) -> Path:
    safe_shell = shell_name.replace("/", "_").replace("\\", "_")
    return SHELL_STATE_DIR / safe_shell / "conversations"


def _conversation_path(channel_id: str, shell_name: str = "line_secretary") -> Path:
    """チャネルIDから会話履歴ファイルのパスを生成"""
    safe_id = channel_id.replace("/", "_").replace("\\", "_")
    return _conversation_dir(shell_name) / f"{safe_id}.json"


def _legacy_conversation_path(channel_id: str) -> Path:
    safe_id = channel_id.replace("/", "_").replace("\\", "_")
    return LEGACY_CONVERSATIONS_DIR / f"{safe_id}.json"


def load_conversation(
    channel_id: str,
    channel_type: str = "default",
    shell_name: str = "line_secretary",
) -> list[dict]:
    """会話履歴を読み込む。タイムアウトしていたらリセット。"""
    _ensure_dirs()
    path = _conversation_path(channel_id, shell_name)
    if not path.exists() and shell_name == "line_secretary":
        path = _legacy_conversation_path(channel_id)
    if not path.exists():
        return []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

    # タイムアウトチェック
    last_ts = data.get("last_updated", 0)
    if time.time() - last_ts > SESSION_TIMEOUT_SEC:
        logger.info(f"会話セッションタイムアウト: {channel_id}")
        return []

    messages = data.get("messages", [])

    # 上限チェック
    max_pairs = SHORT_TERM_MAX.get(channel_type, SHORT_TERM_MAX["default"])
    if max_pairs == 0:
        return []
    max_messages = max_pairs * 2
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    return messages


def save_conversation(
    channel_id: str,
    messages: list[dict],
    channel_type: str = "default",
    shell_name: str = "line_secretary",
):
    """会話履歴を保存"""
    _ensure_dirs()
    _conversation_dir(shell_name).mkdir(parents=True, exist_ok=True)
    max_pairs = SHORT_TERM_MAX.get(channel_type, SHORT_TERM_MAX["default"])
    if max_pairs == 0:
        return

    max_messages = max_pairs * 2
    if len(messages) > max_messages:
        messages = messages[-max_messages:]

    data = {
        "last_updated": time.time(),
        "channel_type": channel_type,
        "messages": messages,
    }

    path = _conversation_path(channel_id, shell_name)
    _atomic_write_json(path, data)

    # 既存運用との互換性のため、LINE秘書は legacy パスにも保存する
    if shell_name == "line_secretary":
        _atomic_write_json(_legacy_conversation_path(channel_id), data)


def add_to_conversation(
    channel_id: str,
    role: str,
    content: str,
    channel_type: str = "default",
    shell_name: str = "line_secretary",
):
    """会話履歴に1メッセージ追加"""
    messages = load_conversation(channel_id, channel_type, shell_name=shell_name)
    messages.append({"role": role, "content": content})
    save_conversation(channel_id, messages, channel_type, shell_name=shell_name)


def clear_conversation(channel_id: str, shell_name: str = "line_secretary"):
    """会話履歴をクリア"""
    path = _conversation_path(channel_id, shell_name)
    if path.exists():
        path.unlink()
    legacy = _legacy_conversation_path(channel_id)
    if shell_name == "line_secretary" and legacy.exists():
        legacy.unlink()


def record_context_event(
    channel_id: str,
    shell_name: str,
    event_type: str,
    content: str,
    metadata: dict[str, Any] | None = None,
):
    """shell を横断して共有する短期文脈イベントを追加する"""
    _ensure_dirs()
    event = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "channel_id": channel_id,
        "shell_name": shell_name,
        "event_type": event_type,
        "content": content,
        "metadata": metadata or {},
    }
    with SHARED_EVENT_STREAM.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


def load_context_events(channel_id: str | None = None, limit: int = 12) -> list[dict[str, Any]]:
    _ensure_dirs()
    if not SHARED_EVENT_STREAM.exists():
        return []

    events: list[dict[str, Any]] = []
    lines = SHARED_EVENT_STREAM.read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if channel_id and event.get("channel_id") != channel_id:
            continue
        events.append(event)
        if len(events) >= limit:
            break
    events.reverse()
    return events


def load_active_context() -> dict[str, Any]:
    data = _load_json(SHARED_ACTIVE_CONTEXT_FILE, {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("global", [])
    data.setdefault("channels", {})
    return data


def save_active_context(data: dict[str, Any]):
    _ensure_dirs()
    _atomic_write_json(SHARED_ACTIVE_CONTEXT_FILE, data)


def update_active_context(
    channel_id: str,
    summary: str,
    shell_name: str = "line_secretary",
    pending_items: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
):
    """各チャネルの現在の共有短期文脈を更新する"""
    data = load_active_context()
    now = datetime.now().isoformat(timespec="seconds")

    channel_entry = data["channels"].setdefault(channel_id, {})
    channel_entry["summary"] = summary
    channel_entry["shell_name"] = shell_name
    channel_entry["updated_at"] = now
    if pending_items is not None:
        channel_entry["pending_items"] = pending_items
    if metadata:
        merged = dict(channel_entry.get("metadata", {}))
        merged.update(metadata)
        channel_entry["metadata"] = merged

    global_entry = {
        "channel_id": channel_id,
        "summary": summary,
        "shell_name": shell_name,
        "updated_at": now,
    }
    remaining = [item for item in data["global"] if item.get("channel_id") != channel_id]
    data["global"] = [global_entry] + remaining[:19]
    save_active_context(data)


def build_shared_context_block(channel_id: str | None = None, limit: int = 8) -> str:
    """system prompt に入れる共有短期文脈の要約を返す"""
    data = load_active_context()
    lines = ["## 共有短期文脈"]

    if channel_id:
        channel_entry = data.get("channels", {}).get(channel_id, {})
        summary = channel_entry.get("summary", "")
        if summary:
            lines.append(f"- このチャネルの現在地: {summary}")
        pending_items = channel_entry.get("pending_items", [])
        for item in pending_items[:3]:
            lines.append(f"- 承認待ち/未完了: {item}")

    global_items = data.get("global", [])[:4]
    for item in global_items:
        if channel_id and item.get("channel_id") == channel_id:
            continue
        summary = item.get("summary")
        if summary:
            lines.append(f"- 他チャネル状況: {summary}")

    events = load_context_events(channel_id=channel_id, limit=limit)
    for event in events[-4:]:
        content = str(event.get("content", "")).replace("\n", " ").strip()
        if not content:
            continue
        lines.append(
            f"- 最近の出来事 ({event.get('shell_name', '')}/{event.get('event_type', '')}): {content[:120]}"
        )

    if len(lines) == 1:
        return ""
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 初期記憶の生成
# ---------------------------------------------------------------------------

def initialize_memory_from_existing():
    """既存の資産から初期長期記憶を生成する（1回だけ実行）"""
    if MEMORY_FILE.exists():
        logger.info("長期記憶ファイルは既に存在します。スキップ。")
        return

    _ensure_dirs()
    repo_root = Path(__file__).resolve().parent.parent.parent

    sections = ["# 秘書の記憶\n"]

    # MEMORY.md からユーザー設定・好みを抽出
    memory_md = repo_root / ".claude" / "projects" / "-Users-koa800-Desktop-cursor" / "memory" / "MEMORY.md"
    if memory_md.exists():
        content = memory_md.read_text(encoding="utf-8")
        sections.append("## 甲原さんの好み・スタイル（MEMORY.mdより引き継ぎ）")
        # ユーザー設定セクションを抽出
        in_section = False
        for line in content.split("\n"):
            if "ユーザー設定・好み" in line:
                in_section = True
                continue
            if in_section and line.startswith("## "):
                break
            if in_section and line.startswith("- "):
                sections.append(line)
        sections.append("")

    # OS（行動ルール）の概要
    sections.append("## 行動原則（OS）")
    sections.append("- 0.1%のこだわり: 細部にこだわり、協働を掛け算にする")
    sections.append("- 質の高い思考: データか深い思考に基づいて判断する")
    sections.append("- 中から外: 手元の資産から出発する")
    sections.append("- 下から上へ: 実行責任はシステム側に置く")
    sections.append("- 記録ではなく知識: 次の判断に使える形で蓄積する")
    sections.append("")

    # 甲原さんの方針・意思決定
    sections.append("## 甲原さんの方針・意思決定")
    sections.append("- 秘書v2への移行を決定（2026-03-07）: 全機能を最高モデルで動かす")
    sections.append("- モデルはGPT-5.4をデフォルト。差し替え可能な設計")
    sections.append("- コストより質を重視。月5万円まで許容")
    sections.append("")

    # 進行中の重要事項
    sections.append("## 進行中の重要事項")
    sections.append("- メールマーケティング自動化: 設計完了、着手予定")
    sections.append("- LPテンプレート: デザイナーに依頼中")
    sections.append("")

    # 人間関係・送信者メモ
    sections.append("## 人間関係・送信者メモ")
    sections.append("- （会話から自動で追加・更新）")
    sections.append("")

    # 覚えておくべき文脈
    sections.append("## 覚えておくべき文脈")
    sections.append("- （会話から自動で追加・削除）")

    content = "\n".join(sections)
    save_long_term_memory(content)
    logger.info("初期長期記憶を生成しました")


# ---------------------------------------------------------------------------
# 棚卸し（日次で呼び出す）
# ---------------------------------------------------------------------------

def run_daily_cleanup():
    """
    日次の記憶棚卸し。
    LLMに現在の記憶を渡して、統合・削除を判断させる。
    Orchestrator の日次ジョブから呼び出す。
    """
    memory = load_long_term_memory()
    if not memory.strip():
        return "記憶が空のためスキップ"

    lines = memory.strip().split("\n")
    if len(lines) <= MAX_MEMORY_LINES // 2:
        return f"記憶が{len(lines)}行（上限の半分以下）のためスキップ"

    try:
        import llm_router

        prompt = f"""以下は秘書の長期記憶です。この記憶を整理してください。

【整理ルール】
- 重複する情報は1つに統合する
- 完了して1週間以上経った単発タスクは削除する
- 時間が経って状況が変わった古い情報は更新 or 削除する
- セクション構造（## 見出し）は維持する
- 上限{MAX_MEMORY_LINES}行以内に収める
- 重要な方針・意思決定は絶対に削除しない

【現在の記憶】
{memory}

整理後の記憶をそのまま出力してください。説明は不要です。"""

        response = llm_router.chat(
            system="あなたは記憶の整理係です。与えられた記憶を整理して返してください。",
            messages=[{"role": "user", "content": prompt}],
        )
        cleaned = response.get("text", "")
        if cleaned and len(cleaned) > 50:
            save_long_term_memory(cleaned)
            new_lines = len(cleaned.strip().split("\n"))
            return f"棚卸し完了: {len(lines)}行 → {new_lines}行"
        return "棚卸し結果が短すぎるためスキップ"
    except Exception as e:
        logger.error(f"棚卸しエラー: {e}")
        return f"棚卸しエラー: {e}"


def get_memory_stats() -> dict:
    """記憶の統計情報を返す"""
    memory = load_long_term_memory()
    lines = memory.strip().split("\n") if memory.strip() else []

    conversations = []
    if SHELL_STATE_DIR.exists():
        conversations = list(SHELL_STATE_DIR.glob("**/*.json"))

    return {
        "memory_lines": len(lines),
        "memory_limit": MAX_MEMORY_LINES,
        "active_conversations": len(conversations),
        "memory_file": str(MEMORY_FILE),
        "shared_context_file": str(SHARED_ACTIVE_CONTEXT_FILE),
        "shared_event_stream": str(SHARED_EVENT_STREAM),
    }
