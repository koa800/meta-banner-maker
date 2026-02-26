"""
学習エンジン（日向エージェント用）

会話を通じて成長する学習ループの中核。
- アクション記録: 親プロセスが確実に書き込む（Claude Code に任せない）
- フィードバック検出: 指示が直前のアクションへの修正かを判定
- 学習コンテキスト構築: プロンプトに注入する記憶・フィードバックを組み立て
- 記憶の統合: 定期的にフィードバックからパターンを抽出
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hinata.learning")

# ---- パス設定 ----
SCRIPT_DIR = Path(__file__).parent
_agents_dir = Path.home() / "agents" / "_repo"
REPO_DIR = _agents_dir if _agents_dir.exists() else Path.home() / "Cursor"
LEARNING_DIR = REPO_DIR / "Master" / "learning"

ACTION_LOG_PATH = LEARNING_DIR / "action_log.json"
FEEDBACK_LOG_PATH = LEARNING_DIR / "feedback_log.json"
MEMORY_PATH = LEARNING_DIR / "hinata_memory.md"
INSIGHTS_PATH = LEARNING_DIR / "insights.md"

MAX_ACTION_LOG = 50  # 保持する最大アクション数
MAX_FEEDBACK_LOG = 50  # 保持する最大フィードバック数

# フィードバック検出用キーワード
_NEGATIVE_KEYWORDS = [
    "違う", "そうじゃない", "的外れ", "ダメ", "やり直し", "間違", "修正して",
    "じゃなくて", "ではなく", "そうじゃなく", "ちがう", "NG",
]
_POSITIVE_KEYWORDS = [
    "いいね", "ありがとう", "完璧", "OK", "おっけー", "グッド", "good",
    "ナイス", "素晴らしい", "正解", "その通り", "それでいい",
]


# ====================================================================
# アクション記録
# ====================================================================

def record_action(
    cycle_num: int,
    instruction: Optional[str],
    result: Optional[str],
    goal_url: str = "",
) -> None:
    """
    サイクル完了後にアクション履歴を記録する。
    hinata_agent.py（親プロセス）から呼ぶ。Claude Code には任せない。
    """
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)

    entry = {
        "date": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "cycle": cycle_num,
        "instruction": (instruction or "定期サイクル")[:200],
        "result": (result or "結果なし")[:500],
        "goal_url": goal_url,
    }

    logs = _load_json(ACTION_LOG_PATH, [])
    logs.append(entry)

    # 古いエントリを削除
    if len(logs) > MAX_ACTION_LOG:
        logs = logs[-MAX_ACTION_LOG:]

    _save_json(ACTION_LOG_PATH, logs)
    logger.info(f"アクション記録: #{cycle_num} {entry['instruction'][:50]}")


# ====================================================================
# フィードバック検出・記録
# ====================================================================

def detect_and_record_feedback(new_instruction: str) -> Optional[dict]:
    """
    新しい指示が、直前のアクションへのフィードバックかを判定する。
    フィードバックなら feedback_log.json に記録し、フィードバック情報を返す。
    """
    logs = _load_json(ACTION_LOG_PATH, [])
    if not logs:
        return None

    last_action = logs[-1]

    # 直前のアクションから30分以内かチェック
    try:
        last_time = datetime.strptime(last_action["date"], "%Y/%m/%d %H:%M")
        minutes_since = (datetime.now() - last_time).total_seconds() / 60
        if minutes_since > 60:
            return None  # 1時間以上前なら無関係
    except (ValueError, KeyError):
        pass

    # フィードバックの種類を判定
    sentiment = _classify_sentiment(new_instruction)
    if sentiment == "neutral":
        return None  # 新しい指示であってフィードバックではない

    feedback = {
        "date": datetime.now().strftime("%Y/%m/%d %H:%M"),
        "previous_action": last_action.get("result", "")[:200],
        "previous_instruction": last_action.get("instruction", "")[:200],
        "feedback": new_instruction[:300],
        "sentiment": sentiment,
    }

    # feedback_log に追加
    feedbacks = _load_json(FEEDBACK_LOG_PATH, [])
    feedbacks.append(feedback)
    if len(feedbacks) > MAX_FEEDBACK_LOG:
        feedbacks = feedbacks[-MAX_FEEDBACK_LOG:]
    _save_json(FEEDBACK_LOG_PATH, feedbacks)

    logger.info(f"フィードバック記録: [{sentiment}] {new_instruction[:50]}")
    return feedback


def _classify_sentiment(text: str) -> str:
    """テキストからフィードバックの感情を判定する。"""
    text_lower = text.lower()

    for kw in _NEGATIVE_KEYWORDS:
        if kw in text_lower:
            return "negative"

    for kw in _POSITIVE_KEYWORDS:
        if kw in text_lower:
            return "positive"

    return "neutral"


# ====================================================================
# 学習コンテキスト構築（プロンプト注入用）
# ====================================================================

def build_learning_context() -> str:
    """
    Claude Code のプロンプトに注入する学習コンテキストを構築する。
    - 直近のアクション履歴（5件）
    - 直近のフィードバック（5件）
    - 蓄積された記憶（hinata_memory.md）
    - insights.md の知見
    """
    sections = []

    # 1. 直近のアクション履歴
    actions_text = _format_recent_actions(5)
    if actions_text:
        sections.append(f"### 直近のアクション履歴\n{actions_text}")

    # 2. 直近のフィードバック（最重要）
    feedback_text = _format_recent_feedback(5)
    if feedback_text:
        sections.append(
            f"### 甲原さんからのフィードバック（必ず反映すること）\n{feedback_text}"
        )

    # 3. 蓄積された記憶
    memory_text = _load_text(MEMORY_PATH, max_chars=2000)
    if memory_text:
        sections.append(f"### 学んだこと（記憶）\n{memory_text}")

    # 4. insights.md
    insights_text = _load_text(INSIGHTS_PATH, max_chars=1000)
    if insights_text:
        sections.append(f"### 業務の知見\n{insights_text}")

    if not sections:
        return ""

    header = (
        "\n## 過去の学習コンテキスト\n\n"
        "以下はあなたの過去の経験です。同じ失敗を繰り返さず、"
        "フィードバックを必ず反映してください。\n\n"
    )
    return header + "\n\n".join(sections) + "\n"


def _format_recent_actions(n: int) -> str:
    """直近N件のアクション履歴をフォーマットする。"""
    logs = _load_json(ACTION_LOG_PATH, [])
    if not logs:
        return ""
    recent = logs[-n:]
    lines = []
    for entry in recent:
        lines.append(
            f"- [{entry.get('date', '?')}] #{entry.get('cycle', '?')}: "
            f"指示「{entry.get('instruction', '?')[:80]}」"
            f" → 結果: {entry.get('result', '?')[:100]}"
        )
    return "\n".join(lines)


def _format_recent_feedback(n: int) -> str:
    """直近N件のフィードバックをフォーマットする。"""
    feedbacks = _load_json(FEEDBACK_LOG_PATH, [])
    if not feedbacks:
        return ""
    recent = feedbacks[-n:]
    lines = []
    for fb in recent:
        sentiment_icon = {"positive": "+", "negative": "-"}.get(
            fb.get("sentiment", ""), "?"
        )
        lines.append(
            f"- [{sentiment_icon}] 私のアクション「{fb.get('previous_instruction', '?')[:60]}」"
            f" → 甲原さん「{fb.get('feedback', '?')[:100]}」"
        )
    return "\n".join(lines)


# ====================================================================
# 記憶の統合（週次で実行）
# ====================================================================

def consolidate_memory() -> str:
    """
    action_log + feedback_log からパターンを抽出し、hinata_memory.md を更新する。
    Orchestrator の週次タスクから呼ばれる想定。
    戻り値は更新内容のサマリー。
    """
    actions = _load_json(ACTION_LOG_PATH, [])
    feedbacks = _load_json(FEEDBACK_LOG_PATH, [])
    existing_memory = _load_text(MEMORY_PATH, max_chars=5000)

    if not actions and not feedbacks:
        return "記録なし。記憶更新スキップ。"

    # 記憶更新用のサマリーを生成
    summary_lines = []
    summary_lines.append(f"# 日向の記憶\n")
    summary_lines.append(f"最終更新: {datetime.now().strftime('%Y/%m/%d %H:%M')}\n")

    # フィードバックからの学び
    if feedbacks:
        summary_lines.append("## フィードバックから学んだこと\n")
        negative_fbs = [f for f in feedbacks if f.get("sentiment") == "negative"]
        positive_fbs = [f for f in feedbacks if f.get("sentiment") == "positive"]

        if negative_fbs:
            summary_lines.append("### やってはいけないこと")
            for fb in negative_fbs[-10:]:
                summary_lines.append(
                    f"- 「{fb.get('previous_instruction', '')[:60]}」に対して"
                    f"「{fb.get('feedback', '')[:80]}」と言われた"
                )
            summary_lines.append("")

        if positive_fbs:
            summary_lines.append("### うまくいったこと")
            for fb in positive_fbs[-10:]:
                summary_lines.append(
                    f"- 「{fb.get('previous_instruction', '')[:60]}」→ 好評"
                )
            summary_lines.append("")

    # アクション履歴のサマリー
    if actions:
        summary_lines.append(f"## アクション統計\n")
        summary_lines.append(f"- 総サイクル数: {len(actions)}")
        if actions:
            summary_lines.append(
                f"- 期間: {actions[0].get('date', '?')} 〜 {actions[-1].get('date', '?')}"
            )
        summary_lines.append("")

    new_memory = "\n".join(summary_lines)
    LEARNING_DIR.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(new_memory, encoding="utf-8")

    logger.info(f"記憶更新完了: {len(feedbacks)}件のフィードバック反映")
    return f"記憶更新: アクション{len(actions)}件、フィードバック{len(feedbacks)}件を反映"


# ====================================================================
# ユーティリティ
# ====================================================================

def _load_json(path: Path, default):
    """JSON ファイルを安全に読み込む。"""
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"JSON読み込み失敗 ({path.name}): {e}")
        return default


def _save_json(path: Path, data):
    """JSON ファイルをアトミックに書き込む。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.rename(path)


def _load_text(path: Path, max_chars: int = 2000) -> str:
    """テキストファイルを安全に読み込む。"""
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8").strip()
        if len(text) > max_chars:
            text = text[:max_chars] + "\n... (省略)"
        return text
    except IOError as e:
        logger.warning(f"テキスト読み込み失敗 ({path.name}): {e}")
        return ""
