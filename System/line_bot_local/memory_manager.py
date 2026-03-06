"""
Memory Manager — 秘書の記憶システム
短期記憶（会話履歴）と長期記憶（secretary_memory.md）を管理する。
"""

import json
import os
import time
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# 記憶ファイルのパス（git管理外）
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MEMORY_FILE = DATA_DIR / "secretary_memory.md"
CONVERSATIONS_DIR = DATA_DIR / "conversations"

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
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)


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
    MEMORY_FILE.write_text(content, encoding="utf-8")
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


def remove_memory(keyword: str) -> bool:
    """キーワードを含む記憶エントリを削除"""
    current = load_long_term_memory()
    lines = current.split("\n")
    new_lines = [line for line in lines if keyword not in line]
    if len(new_lines) == len(lines):
        return False
    save_long_term_memory("\n".join(new_lines))
    return True


# ---------------------------------------------------------------------------
# 短期記憶（会話履歴）
# ---------------------------------------------------------------------------

def _conversation_path(channel_id: str) -> Path:
    """チャネルIDから会話履歴ファイルのパスを生成"""
    safe_id = channel_id.replace("/", "_").replace("\\", "_")
    return CONVERSATIONS_DIR / f"{safe_id}.json"


def load_conversation(channel_id: str, channel_type: str = "default") -> list[dict]:
    """会話履歴を読み込む。タイムアウトしていたらリセット。"""
    _ensure_dirs()
    path = _conversation_path(channel_id)
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


def save_conversation(channel_id: str, messages: list[dict], channel_type: str = "default"):
    """会話履歴を保存"""
    _ensure_dirs()
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

    path = _conversation_path(channel_id)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def add_to_conversation(channel_id: str, role: str, content: str, channel_type: str = "default"):
    """会話履歴に1メッセージ追加"""
    messages = load_conversation(channel_id, channel_type)
    messages.append({"role": role, "content": content})
    save_conversation(channel_id, messages, channel_type)


def clear_conversation(channel_id: str):
    """会話履歴をクリア"""
    path = _conversation_path(channel_id)
    if path.exists():
        path.unlink()


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

def get_memory_stats() -> dict:
    """記憶の統計情報を返す"""
    memory = load_long_term_memory()
    lines = memory.strip().split("\n") if memory.strip() else []

    conversations = []
    if CONVERSATIONS_DIR.exists():
        conversations = list(CONVERSATIONS_DIR.glob("*.json"))

    return {
        "memory_lines": len(lines),
        "memory_limit": MAX_MEMORY_LINES,
        "active_conversations": len(conversations),
        "memory_file": str(MEMORY_FILE),
    }
