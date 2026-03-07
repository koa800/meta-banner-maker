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
import os
import re
import time
from datetime import datetime
from pathlib import Path

import anthropic

from clone_registry import build_agent_summary
from handler_runner import HandlerRunner

# Coordinator が使う LLM モデル
COORDINATOR_MODEL = "claude-haiku-4-5-20251001"
COORDINATOR_MAX_TOKENS = 2000
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


def _load_agent_summary(project_root: Path) -> str:
    """agent_registry.json を優先し、必要なら legacy から導出したサマリーを返す。"""
    return build_agent_summary()


def _load_video_knowledge(project_root: Path, goal_text: str = "") -> str:
    """ゴールテキストに関連する動画知識を検索して注入する。
    pendingエントリがあればその情報も注入する（承認フロー用）。"""
    knowledge_path = Path.home() / "agents" / "data" / "video_knowledge.json"
    if not knowledge_path.exists():
        return ""
    try:
        entries = json.loads(knowledge_path.read_text(encoding="utf-8"))
    except Exception:
        return ""
    if not entries:
        return ""

    parts = []
    changed = False

    # --- pendingエントリの情報を注入（承認フロー用） ---
    pending = [e for e in entries if e.get("status") == "pending"]
    if pending:
        lines = ["【承認待ちの知識】"]
        for e in pending:
            source_type = e.get("source_type", "video")
            lines.append(f"  種別: {source_type}")
            lines.append(f"  タイトル: {e.get('title', '')}")
            lines.append(f"  要約: {e.get('summary', '')}")
            procs = e.get("key_processes", [])
            if procs:
                lines.append(f"  手順: {' → '.join(procs)}")
            kps = e.get("key_points", [])
            if kps:
                lines.append(f"  ポイント: {' / '.join(kps)}")
            uc = e.get("use_context", "")
            if uc:
                lines.append(f"  活用場面: {uc}")
        lines.append("ユーザーが「OK」「覚えて」「それでいい」等と言ったら confirm_video_learning を呼ぶこと。")
        lines.append("修正指示があれば update_video_learning で修正してから再度確認を取ること。")
        parts.append("\n".join(lines))

    # --- confirmedエントリから関連性ベースで注入 ---
    confirmed = [e for e in entries if e.get("status", "confirmed") == "confirmed"]
    if confirmed:
        if goal_text:
            query_lower = goal_text.lower()
            query_words = set(query_lower.split())

            scored = []
            for e in confirmed:
                score = 0
                title = (e.get("title") or "").lower()
                summary = (e.get("summary") or "").lower()
                url = (e.get("url") or "").lower()
                procs = " ".join(e.get("key_processes", [])).lower()
                use_ctx = (e.get("use_context") or "").lower()
                kps = " ".join(e.get("key_points", [])).lower()

                # URL直接マッチは高スコア
                if url and url in query_lower:
                    score += 100

                # 単語マッチ
                for word in query_words:
                    if len(word) < 2:
                        continue
                    if word in title:
                        score += 3
                    if word in summary:
                        score += 2
                    if word in procs:
                        score += 2
                    if word in use_ctx:
                        score += 2
                    if word in kps:
                        score += 2

                if score > 0:
                    scored.append((score, e))

            if scored:
                scored.sort(key=lambda x: x[0], reverse=True)
                selected = [e for _, e in scored[:5]]

                # access_count / last_accessed を更新
                now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                selected_ids = {e.get("id") for e in selected}
                for e in entries:
                    if e.get("id") in selected_ids:
                        e["access_count"] = e.get("access_count", 0) + 1
                        e["last_accessed"] = now_str
                changed = True
            else:
                selected = []
        else:
            # ゴールテキストがない場合: 全件（最大10件、新しい順）
            selected = confirmed[-10:]

        if selected:
            lines = ["【関連する知識】"]
            for i, e in enumerate(selected, 1):
                source_type = e.get("source_type", "video")
                source_label = {"loom": "Loom", "youtube": "YouTube"}.get(e.get("source", ""), e.get("source", ""))
                type_label = {"video": source_label, "image": "画像", "screenshot": "スクショ", "document": "文書"}.get(source_type, source_label)
                date = e.get("learned_at", "")[:10]
                lines.append(f"[{i}] {e.get('title', '')} ({type_label}, {date})")
                lines.append(f"  要約: {e.get('summary', '')}")
                procs = e.get("key_processes", [])
                if procs:
                    lines.append(f"  手順: {' → '.join(procs)}")
                uc = e.get("use_context", "")
                if uc:
                    lines.append(f"  活用場面: {uc}")
            parts.append("\n".join(lines))

    if changed:
        _save_video_knowledge(knowledge_path, entries)

    return "\n\n".join(parts)


def _save_video_knowledge(path: Path, data: list):
    """video_knowledge.json をアトミック書き込みで保存"""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(path)


def _build_system_prompt(sender_name: str = "", project_root: Path = None, goal_text: str = "") -> str:
    """Coordinator 用のシステムプロンプトを構築する"""
    prompt = """あなたは甲原海人のAI秘書システムの Coordinator です。

【最重要ルール: 認識のすり合わせ】
ゴールを受け取ったら、まず自分の認識を提示して確認を取ること。
自分が合っていると思い込まない。必ず認識のズレがないか確認する。

「認識が合っている」とは、以下の3つが揃っている状態を指す:
  - 視野: 何を見ているか（対象範囲。抜け漏れがないか）
  - 視座: どの立場から見ているか（誰の目線で考えるか）
  - 視点: 何に注目しているか（優先すべきポイントは何か）

確認の仕方:
  ✕「このタスクを実行していいですか？」← 許可を求めるのはNG
  ○「この認識で合っていますか？」← 視野・視座・視点のすり合わせをする

例:
  ゴール「来週の商談に備えて」に対して:
  ✕「カレンダーを確認して商談準備メモを作成してよいですか？」
  ○「来週の商談 = カレンダーにある予定のことですね。
     【視野】参加者情報・過去のやり取り・関連数値
     【視座】甲原さんが商談で主導権を持てる状態にする
     【視点】先方への未返信（見積もり）が最優先
     この認識で合っていますか？」

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
2. 情報取得系のツール（calendar, mail, kpi, people, addness, sheets, search）は並列で呼んでOK
3. draft_reply, analyze, generate_image, generate_video は、必要な情報が揃ってから呼ぶ
4. send_message, ask_human は「送信提案」を返すだけ。実際の送信はユーザーの承認後
5. 最終報告は簡潔に。箇条書きで。LINEメッセージとして読みやすい形式で
6. ツールが不要な簡単な質問には、ツールを呼ばず直接回答してもOK

【生成AI系ツール】
- search: Web検索が必要なとき（最新情報、企業調査、市場動向）→ Perplexity に委任
- generate_image: 画像・バナー制作 → Lubert に委任
- generate_video: 動画制作 → 動画AI に委任（未設定の場合はその旨を返す）
- APIキーが未設定のツールは、未設定である旨をユーザーに報告する

【ワークフロー移譲ルール】
agent_registry.json の transfer.transfer_status に応じて、ワークフローの振り先を自動で変える:
- Phase 1（AI全自動）: ワークフローに直接実行を委任
- Phase 2（AI実行+人間確認）: ワークフローを実行し、結果を transfer_target の人間にも共有
- Phase 3（人間実行+AIサポート）: transfer_target の人間に依頼し、AIはサポート情報を提供
- Phase 4（完全自走）: transfer_target の人間に直接依頼。AIは不要

【動画学習フロー】
LoomやYouTubeのURLが送られて「見ておいて」「確認して」等の指示があったら:
1. video_reader ツールで内容を取得
2. transcript_summary（あれば優先）または transcript_text から内容を理解し、要約+手順を箇条書きで報告
3. 同じツールループ内で save_video_learning(status="pending") を呼んで即保存
4. 報告 + 「この内容で覚えていいですか？修正があれば教えてください」
※ 承認は必須。「OK」「覚えて」「それでいい」等の返事が来たら confirm_video_learning で確定する
※ 修正指示が来たら update_video_learning で修正後、再度確認を取る
※ 承認なしに confirm してはいけない。承認待ちの知識はシステムプロンプトに表示される

【画像・ドキュメント学習フロー】
「覚えて」「学んで」等の指示 + 画像URL/ドキュメントURLがあったら:
1. analyze_content(url=画像URL, instruction=ユーザーの補足があれば渡す) で内容を分析
2. 分析結果(title, summary, key_points, use_context)を確認
3. save_video_learning(status="pending", source_type="image", use_context=分析結果のuse_context, key_points=分析結果のkey_points) で即保存
4. 報告: タイトル・要約・ポイント・活用場面を提示 + 「この内容で覚えていいですか？」
※ 承認が必要。OKが来たら confirm_video_learning で確定
※ 修正があれば update_video_learning で更新
重要: use_context（この知識がどの場面で使えるか）を必ず分析・保存すること。
ユーザーが「それでOK」と一発承認できる精度を目指す。

【禁止】
- 認識確認なしに曖昧なゴールを実行すること
- 「実行していいですか？」という許可型の質問
- 不要なツール呼び出し（聞かれていない情報まで取りに行かない）
- 1回のゴールで10回以上のツール呼び出し"""

    if sender_name:
        prompt += f"\n\n【送信者】\n{sender_name}（秘書グループからの指示）"

    # agent_registry.json からエージェント一覧を注入
    if project_root:
        agent_summary = _load_agent_summary(project_root)
        if agent_summary:
            prompt += f"\n\n{agent_summary}"
            prompt += "\n\n上記エージェントの得意分野を踏まえてツールを選択すること。人間に依頼する場合は ask_human ツールを使う。"

        # 過去の動画知識を関連性ベースで注入
        video_knowledge = _load_video_knowledge(project_root, goal_text)
        if video_knowledge:
            prompt += f"\n\n{video_knowledge}"

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
    # APIキー: 環境変数 → config.json の順で取得
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                api_key = cfg.get("anthropic_api_key", "")
            except Exception:
                pass
    if not api_key:
        return False, "ANTHROPIC_API_KEY が未設定です。環境変数または config.json を確認してください"
    try:
        client = anthropic.Anthropic(api_key=api_key)
    except Exception as e:
        return False, f"Claude API クライアントの初期化に失敗しました: {e}"

    # ツールレジストリ読み込み
    registry_path = Path(__file__).parent / "tool_registry.json"
    try:
        with open(registry_path, encoding="utf-8") as f:
            registry = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return False, f"tool_registry.json の読み込みに失敗しました: {e}"

    claude_tools = _build_claude_tools(registry)
    system_prompt = _build_system_prompt(sender_name, project_root, goal_text=goal)

    # ハンドラランナー
    try:
        runner = HandlerRunner(
            system_dir=system_dir,
            project_root=project_root,
            function_handlers=function_handlers or {},
        )
    except Exception as e:
        return False, f"HandlerRunner の初期化に失敗しました: {e}"

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
        except anthropic.APITimeoutError:
            return False, "Claude API がタイムアウトしました。時間をおいて再度お試しください"
        except anthropic.APIConnectionError:
            return False, "Claude API に接続できません。ネットワーク状態を確認してください"
        except anthropic.APIError as e:
            return False, f"Claude API エラーが発生しました: {e}"
        except Exception as e:
            return False, f"Coordinator の処理中に予期しないエラーが発生しました: {type(e).__name__}: {e}"

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

                    result_text = runner.run(tool_name, tool_input) or "（結果なし）"

                    # 結果を文字数制限（トークン節約）
                    # video_reader は transcript を含むため上限を緩和
                    max_len = 4000 if tool_name == "video_reader" else 2000
                    if len(result_text) > max_len:
                        result_text = result_text[:max_len] + "\n\n（...省略）"

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
