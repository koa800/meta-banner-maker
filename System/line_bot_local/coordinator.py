"""
coordinator.py — ゴール実行エンジンの司令塔

ゴール（自然言語）を受け取り、分解→委任→統合→報告する。
自分では何も実行しない。tool_registry.json のツール定義に従い、
handler_runner.py を通じてハンドラに委任する。

設計原則:
  - Coordinator はツールの「何ができるか」だけ知っている
  - ツールの「どう実行するか」は handler_runner が担う
  - 新しいツール追加 = tool_registry.json に1件追加するだけ
"""

import json
import re
import time
from pathlib import Path

import anthropic

from handler_runner import HandlerRunner

# Coordinator が使う LLM モデル
COORDINATOR_MODEL = "claude-haiku-4-5-20251001"
COORDINATOR_MAX_TOKENS = 1200
MAX_ROUNDS = 10  # ツール呼び出しループの上限


def _build_claude_tools(registry: dict) -> list:
    """tool_registry.json から Claude API tool_use 形式に変換する"""
    tools = []
    for tool_def in registry["tools"]:
        schema = tool_def.get("input_schema", {"type": "object", "properties": {}})
        tools.append({
            "name": tool_def["name"],
            "description": tool_def["description"],
            "input_schema": schema,
        })
    return tools


def _build_system_prompt(sender_name: str = "") -> str:
    """Coordinator 用のシステムプロンプトを構築する"""
    prompt = """あなたは甲原海人のAI秘書システムの Coordinator です。

【最重要ルール: 認識のすり合わせ】
ゴールを受け取ったら、まず自分の認識を提示して確認を取ること。
自分が合っていると思い込まない。必ず認識のズレがないか確認する。

確認の仕方:
  ✕「このタスクを実行していいですか？」← 許可を求めるのはNG
  ○「この認識で合っていますか？」← 認識のすり合わせをする

例:
  ゴール「来週の商談に備えて」に対して:
  ✕「カレンダーを確認して商談準備メモを作成してよいですか？」
  ○「来週の商談 = カレンダーにある予定のことで、参加者情報・過去のやり取り・関連数値をまとめる、という認識で合っていますか？」

確認が取れたら（「うん」「合ってる」「それで」等の返答があったら）、
すぐにツールを使って実行に移る。

ただし以下は確認不要で即実行してよい:
- 「今日何すればいい？」のような明確な情報取得リクエスト
- 「KPI教えて」のような単純な照会
- 「メール確認して」のような既存コマンド相当のリクエスト

【役割】
ユーザーのゴール（やりたいこと）を理解し、適切なツールを選んで実行し、結果をまとめて報告する。

【ルール】
1. 曖昧なゴールや複数解釈できるゴール → 必ず認識確認してから実行
2. 情報取得系のツール（calendar, mail, kpi, people, addness, sheets）は並列で呼んでOK
3. draft_reply や analyze は、必要な情報が揃ってから呼ぶ
4. send_message, ask_human は「送信提案」を返すだけ。実際の送信はユーザーの承認後
5. 最終報告は簡潔に。箇条書きで。LINEメッセージとして読みやすい形式で
6. ツールが不要な簡単な質問には、ツールを呼ばず直接回答してもOK

【禁止】
- 認識確認なしに曖昧なゴールを実行すること
- 「実行していいですか？」という許可型の質問
- 不要なツール呼び出し（聞かれていない情報まで取りに行かない）
- 1回のゴールで10回以上のツール呼び出し"""

    if sender_name:
        prompt += f"\n\n【送信者】\n{sender_name}（秘書グループからの指示）"

    return prompt


def _strip_markdown_for_line(text: str) -> str:
    """LINE送信前にマークダウン記法を除去"""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'\1', text)
    text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    return text


def execute_goal(
    goal: str,
    sender_name: str = "",
    system_dir: Path = None,
    project_root: Path = None,
    function_handlers: dict = None,
) -> tuple:
    """
    ゴールを受け取り、分解→委任→統合→報告する。

    Args:
        goal:              ユーザーのゴール（自然言語）
        sender_name:       送信者名（プロンプト用）
        system_dir:        System/ ディレクトリのパス
        project_root:      プロジェクトルート
        function_handlers:  {tool_name: callable(arguments) -> str} のマッピング

    Returns:
        (success: bool, result_text: str)
    """
    # --- 初期化 ---
    client = anthropic.Anthropic()

    # ツールレジストリ読み込み
    registry_path = Path(__file__).parent / "tool_registry.json"
    with open(registry_path, encoding="utf-8") as f:
        registry = json.load(f)

    claude_tools = _build_claude_tools(registry)
    system_prompt = _build_system_prompt(sender_name)

    # ハンドラランナー
    runner = HandlerRunner(
        system_dir=system_dir,
        project_root=project_root,
        function_handlers=function_handlers or {},
    )

    # --- ツール呼び出しループ ---
    messages = [{"role": "user", "content": goal}]
    total_tool_calls = 0
    start_time = time.time()

    for round_num in range(MAX_ROUNDS):
        try:
            response = client.messages.create(
                model=COORDINATOR_MODEL,
                max_tokens=COORDINATOR_MAX_TOKENS,
                system=system_prompt,
                tools=claude_tools,
                messages=messages,
            )
        except anthropic.APIError as e:
            return False, f"Claude API エラー: {e}"

        # 完了判定: end_turn → 最終回答
        if response.stop_reason == "end_turn":
            text_parts = []
            for block in response.content:
                if hasattr(block, "text"):
                    text_parts.append(block.text)
            result = "\n".join(text_parts)
            elapsed = time.time() - start_time
            print(f"   🎯 Coordinator 完了: {round_num + 1}ラウンド, "
                  f"{total_tool_calls}ツール呼び出し, {elapsed:.1f}秒")
            return True, _strip_markdown_for_line(result)

        # ツール呼び出し
        if response.stop_reason == "tool_use":
            # assistant の応答をメッセージに追加
            messages.append({
                "role": "assistant",
                "content": [_serialize_content_block(b) for b in response.content],
            })

            # 各ツールを実行
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    total_tool_calls += 1
                    tool_name = block.name
                    tool_input = block.input

                    print(f"   🔧 [{round_num + 1}] {tool_name}({json.dumps(tool_input, ensure_ascii=False)[:100]})")

                    result_text = runner.run(tool_name, tool_input)

                    # 結果を 2000 文字に制限（トークン節約）
                    if len(result_text) > 2000:
                        result_text = result_text[:2000] + "\n\n（...省略）"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                    })

            messages.append({"role": "user", "content": tool_results})
            continue

        # その他の stop_reason
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        if text_parts:
            return True, _strip_markdown_for_line("\n".join(text_parts))
        return True, "（処理が完了しました）"

    # ループ上限到達
    elapsed = time.time() - start_time
    print(f"   ⚠️ Coordinator ループ上限到達: {MAX_ROUNDS}ラウンド, {elapsed:.1f}秒")
    return True, "処理が複雑なため途中で中断しました。もう少し具体的に指示してください。"


def _serialize_content_block(block) -> dict:
    """Anthropic SDK のコンテンツブロックを dict に変換する"""
    if block.type == "text":
        return {"type": "text", "text": block.text}
    elif block.type == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": "text", "text": str(block)}
