"""
Conversation Engine v2 — LLMが自律的にツールを使い、会話する
キーワードマッチではなく、LLMが文脈を理解して判断する。
"""

import json
import logging
import subprocess
import traceback
from pathlib import Path
from typing import Optional, Callable

import llm_router
import memory_manager

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAX_TOOL_ROUNDS = 5  # ツール呼び出しの最大ラウンド数


# ---------------------------------------------------------------------------
# システムプロンプト構築
# ---------------------------------------------------------------------------

def _load_identity() -> str:
    """IDENTITY.md を読み込む"""
    path = REPO_ROOT / "Master" / "self_clone" / "kohara" / "IDENTITY.md"
    if path.exists():
        return path.read_text(encoding="utf-8")[:3000]
    return ""


def _load_execution_rules() -> str:
    """execution_rules.json を読み込んでMarkdownに変換"""
    path = REPO_ROOT / "Master" / "learning" / "execution_rules.json"
    if not path.exists():
        return ""
    try:
        rules = json.loads(path.read_text(encoding="utf-8"))
        lines = ["## 行動ルール（OS）"]
        for rule in rules:
            situation = rule.get("situation", "")
            action = rule.get("action", "")
            lines.append(f"- **{situation}**: {action}")
        return "\n".join(lines)
    except Exception:
        return ""


def build_system_prompt(channel_type: str, sender_context: str = "") -> str:
    """チャネルタイプに応じたシステムプロンプトを構築"""
    identity = _load_identity()
    rules = _load_execution_rules()
    memory = memory_manager.load_long_term_memory()

    if channel_type == "secretary_group":
        return _build_secretary_prompt(identity, rules, memory)
    elif channel_type == "mention":
        return _build_mention_prompt(identity, rules, memory, sender_context)
    elif channel_type == "qa":
        return _build_qa_prompt(memory)
    else:
        return _build_secretary_prompt(identity, rules, memory)


def _build_secretary_prompt(identity: str, rules: str, memory: str) -> str:
    return f"""あなたはアドネス株式会社のAI秘書です。甲原さん（こうはらさん）のパートナーとして動きます。

## あなたの役割
- 甲原さんとの自然な会話を通じて、業務をサポートする
- 必要なデータは自分で判断してツールで取得する
- 重要な情報は記憶に残し、不要な情報は忘れる
- 「言われたことをやる」だけでなく、気づいたことがあれば自分から提案する

## 口調・スタイル
- フランクで親しみやすい口調（敬語は最低限）
- 簡潔に。長文は避ける。LINEでの会話なので短めに
- 数値は具体的に。曖昧な表現は避ける
- 選択肢を出すときは自分の意見も添える

## 記憶の使い方
- 会話の中で重要な情報（方針決定、好み、約束）があったら update_memory ツールで覚える
- 不要になった情報は update_memory ツールで削除する
- 「覚えておいて」と言われたら必ず覚える

{rules}

## 現在の記憶
{memory}

## 甲原さんの人格・価値観（参考）
{identity[:1500]}
"""


def _build_mention_prompt(identity: str, rules: str, memory: str, sender_context: str) -> str:
    return f"""あなたは甲原海人（こうはらかいと）です。LINEグループでメンションされたメッセージに返信します。

## 最重要ルール
- 甲原さん本人として返信する。「秘書」や「AI」であることは絶対に出さない
- IDENTITY.md の口調・価値観を忠実に再現する

## 甲原さんの口調・人格
{identity[:2000]}

## 送信者情報
{sender_context}

## 行動ルール
{rules}

## 秘書の記憶（参考）
{memory[:1000]}
"""


def _build_qa_prompt(memory: str) -> str:
    return f"""あなたはアドネス株式会社のカスタマーサポート担当です。受講生からの質問に丁寧に回答します。

## 回答ルール
- 正確な情報を提供する。分からないことは「確認します」と伝える
- 専門用語は避け、分かりやすい言葉で説明する
- search_qa ツールで過去の回答を検索し、一貫性のある回答をする
- search_knowledge ツールでナレッジベースも参照する

## 参考情報
{memory[:500]}
"""


# ---------------------------------------------------------------------------
# ツール定義
# ---------------------------------------------------------------------------

V2_TOOLS = [
    {
        "name": "get_kpi_data",
        "description": "アドネスの事業KPI（集客数・CPA・ROAS・売上・広告費・媒体別実績・月別推移）を取得して分析する。「数字どう？」「最近の状況は？」など数値に関する質問で使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "KPIに関する質問（例: '今月のROASは？', '前月比でどう？'）",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "get_calendar",
        "description": "Googleカレンダーの予定を取得する。今日・明日・今週の予定確認で使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "取得したい予定の範囲（例: '今日', '今週', '明日の午後'）",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_email",
        "description": "未読・返信待ちメールの状況を確認する。「メール溜まってない？」「返信忘れてるのない？」で使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "account": {
                    "type": "string",
                    "description": "メールアカウント（'personal' or 'team'）",
                    "default": "personal",
                }
            },
        },
    },
    {
        "name": "read_spreadsheet",
        "description": "Googleスプレッドシートのデータを読み取る。特定のシートの情報が必要なとき使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "sheet_id": {
                    "type": "string",
                    "description": "スプレッドシートID",
                },
                "tab_name": {
                    "type": "string",
                    "description": "タブ名（省略時は最初のタブ）",
                },
            },
            "required": ["sheet_id"],
        },
    },
    {
        "name": "search_knowledge",
        "description": "Skills/やMaster/のナレッジベースから情報を検索する。業務知識・スキル・手順を調べるとき使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "検索キーワード（例: 'LP制作', '広告クリエイティブ', 'デザイン原則'）",
                }
            },
            "required": ["query"],
        },
    },
    {
        "name": "search_qa",
        "description": "過去のQ&A回答データベースから類似質問を検索する。受講生の質問に回答するとき使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "検索する質問文",
                }
            },
            "required": ["question"],
        },
    },
    {
        "name": "update_memory",
        "description": "長期記憶を更新する。重要な情報を覚える、または不要になった情報を忘れる。方針決定・好み・約束・人間関係の変化など、今後も参照する価値がある情報で使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove"],
                    "description": "'add'で記憶追加、'remove'で削除",
                },
                "content": {
                    "type": "string",
                    "description": "追加する内容 or 削除するキーワード",
                },
            },
            "required": ["action", "content"],
        },
    },
    {
        "name": "switch_model",
        "description": "使用するLLMモデルを切り替える。「Opusにして」「GPT-5.4に戻して」などで使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "enum": ["anthropic", "openai"],
                    "description": "プロバイダー名",
                },
                "model": {
                    "type": "string",
                    "description": "モデル名（例: 'claude-opus-4-6', 'gpt-5.4'）",
                },
            },
            "required": ["provider", "model"],
        },
    },
    {
        "name": "generate_image",
        "description": "テキストから画像を生成する。「画像作って」「こんなイメージで」などで使う。",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "画像生成プロンプト（英語推奨）",
                }
            },
            "required": ["prompt"],
        },
    },
]


# ---------------------------------------------------------------------------
# ツール実行
# ---------------------------------------------------------------------------

# ツールハンドラは外部から登録する（local_agent.py の既存関数を流用）
_tool_handlers: dict[str, Callable] = {}


def register_tool_handler(name: str, handler: Callable):
    """ツールハンドラを登録"""
    _tool_handlers[name] = handler


def _execute_tool(name: str, arguments: dict) -> str:
    """ツールを実行して結果を文字列で返す"""
    # 内蔵ツール
    if name == "update_memory":
        return _handle_update_memory(arguments)
    if name == "switch_model":
        return _handle_switch_model(arguments)

    # 外部登録ツール
    handler = _tool_handlers.get(name)
    if handler is None:
        return f"ツール '{name}' は登録されていません。"
    try:
        result = handler(arguments)
        if isinstance(result, dict):
            return json.dumps(result, ensure_ascii=False)
        return str(result) if result else "完了しました。"
    except Exception as e:
        logger.error(f"ツール実行エラー [{name}]: {e}\n{traceback.format_exc()}")
        return f"エラー: {e}"


def _handle_update_memory(arguments: dict) -> str:
    action = arguments.get("action", "add")
    content = arguments.get("content", "")
    if action == "add":
        memory_manager.append_memory(content)
        return f"記憶しました: {content}"
    elif action == "remove":
        removed = memory_manager.remove_memory(content)
        return f"削除しました: {content}" if removed else f"該当する記憶が見つかりませんでした: {content}"
    return "不明なアクション"


def _handle_switch_model(arguments: dict) -> str:
    provider = arguments.get("provider", "")
    model = arguments.get("model", "")
    return llm_router.switch_model(provider, model)


# ---------------------------------------------------------------------------
# メイン会話処理
# ---------------------------------------------------------------------------

def process_message(
    message: str,
    channel_id: str,
    channel_type: str = "secretary_group",
    sender_name: str = "",
    sender_context: str = "",
) -> str:
    """
    メッセージを処理して応答を返す。
    v2のメインエントリポイント。

    Args:
        message: ユーザーのメッセージ
        channel_id: チャネルID（グループID等）
        channel_type: "secretary_group" / "mention" / "qa"
        sender_name: 送信者名
        sender_context: 送信者のプロファイル情報

    Returns:
        応答テキスト
    """
    # 1. システムプロンプト構築
    system_prompt = build_system_prompt(channel_type, sender_context)

    # 2. 短期記憶（会話履歴）をロード
    conversation_history = memory_manager.load_conversation(channel_id, channel_type)

    # 3. ユーザーメッセージを会話履歴に追加
    conversation_history.append({"role": "user", "content": message})

    # 4. ツール選択（チャネルタイプに応じて制限）
    tools = _get_tools_for_channel(channel_type)

    # 5. LLMとの会話ループ（ツール呼び出しがある限り繰り返す）
    response_text = _conversation_loop(system_prompt, conversation_history, tools)

    # 6. アシスタントの応答を会話履歴に追加して保存
    conversation_history.append({"role": "assistant", "content": response_text})
    memory_manager.save_conversation(channel_id, conversation_history, channel_type)

    return response_text


def _get_tools_for_channel(channel_type: str) -> list[dict]:
    """チャネルタイプに応じて使えるツールを制限"""
    if channel_type == "secretary_group":
        return V2_TOOLS  # 全ツール
    elif channel_type == "mention":
        # メンション返信ではデータ取得とナレッジのみ
        allowed = {"get_kpi_data", "get_calendar", "check_email", "search_knowledge", "update_memory"}
        return [t for t in V2_TOOLS if t["name"] in allowed]
    elif channel_type == "qa":
        # Q&Aではナレッジ検索のみ
        allowed = {"search_qa", "search_knowledge"}
        return [t for t in V2_TOOLS if t["name"] in allowed]
    return V2_TOOLS


def _conversation_loop(system: str, messages: list[dict], tools: list[dict]) -> str:
    """
    LLMとの会話ループ。
    ツール呼び出しがある限り、実行→結果をフィード→再度LLM呼び出しを繰り返す。
    """
    working_messages = list(messages)

    for round_num in range(MAX_TOOL_ROUNDS):
        response = llm_router.chat(
            system=system,
            messages=working_messages,
            tools=tools,
        )

        # ツール呼び出しがなければ、テキスト応答を返して終了
        if not response["tool_calls"]:
            return response.get("text") or "（応答なし）"

        # ツール呼び出しあり → 実行して結果をフィード
        # アシスタントのレスポンスを messages に追加（Anthropic形式）
        assistant_content = []
        if response.get("text"):
            assistant_content.append({"type": "text", "text": response["text"]})
        for tc in response["tool_calls"]:
            assistant_content.append({
                "type": "tool_use",
                "id": tc["id"],
                "name": tc["name"],
                "input": tc["arguments"],
            })
        working_messages.append({"role": "assistant", "content": assistant_content})

        # ツール結果を user メッセージとして追加
        tool_results = []
        for tc in response["tool_calls"]:
            logger.info(f"ツール実行: {tc['name']}({tc['arguments']})")
            result = _execute_tool(tc["name"], tc["arguments"])
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tc["id"],
                "content": result[:3000],  # 結果が長すぎる場合は切り詰め
            })
        working_messages.append({"role": "user", "content": tool_results})

    # ラウンド上限に達した場合
    logger.warning(f"ツール呼び出しが{MAX_TOOL_ROUNDS}ラウンドに達しました")
    # 最後のレスポンスのテキストを返す
    final = llm_router.chat(system=system, messages=working_messages, tools=[])
    return final.get("text") or "（処理が完了しませんでした。もう一度お試しください。）"
