"""
Claude Code 実行モジュール（日向エージェント用）

Claude in Chrome MCP ツールでブラウザを直接操作。
Addness操作もアクション実行も全てClaude Codeが行う。
"""

import json
import logging
import os
import signal
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from learning import build_learning_context

logger = logging.getLogger("hinata.claude")

# claude -p の作業ディレクトリ（CLAUDE.md がある場所）
_agents_dir = Path.home() / "agents" / "_repo"
WORK_DIR = _agents_dir if _agents_dir.exists() else Path.home() / "Cursor"
CLAUDE_CMD = "/opt/homebrew/bin/claude"
SELF_RESTART_SH = str(Path(__file__).parent / "self_restart.sh")

# 行動ルール（OS: 共通ルール基盤）— 秘書・日向・Claude Code 共通
_EXECUTION_RULES_FILE = _agents_dir / "Master" / "learning" / "execution_rules.json"


def _build_execution_rules_section() -> str:
    """execution_rules.json から行動ルールを読み込み、プロンプト注入用テキストを生成"""
    try:
        if _EXECUTION_RULES_FILE.exists():
            rules = json.loads(_EXECUTION_RULES_FILE.read_text(encoding="utf-8"))
            if not rules:
                return ""
            lines = ["## 甲原さんの行動ルール（OS: 共通ルール基盤）\nこれはすべての判断に適用する普遍的なルールです。"]
            for r in rules:
                situation = r.get("situation", "")
                action = r.get("action", "")
                if situation:
                    lines.append(f"- 【{situation}】→ {action}")
                else:
                    lines.append(f"- {action}")
            return "\n".join(lines) + "\n"
    except Exception as e:
        logger.warning(f"行動ルール読み込みエラー: {e}")
    return ""


def execute_full_cycle(
    instruction: str = None,
    cycle_num: int = 0,
    state: dict = None,
    goal_url: str = "",
    timeout_seconds: int = 900,
) -> Optional[str]:
    """
    Claude Codeにフルサイクルを実行させる。
    Claude in Chrome MCP でブラウザ操作→Addness操作→蓄積まで全部やる。
    """
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    last_action = (state or {}).get("last_action", "なし（初回）")

    instruction_section = ""
    if instruction:
        instruction_section = (
            f"\n## 甲原さんからの指示\n"
            f"「{instruction}」\n"
        )

    # learning.py が構築する学習コンテキスト（アクション履歴・フィードバック・記憶・知見）
    learning_section = build_learning_context()

    # 行動ルール（OS）— 秘書・日向・Claude Code 共通
    execution_rules_section = _build_execution_rules_section()

    # config.json の mode（自律サイクルの制御に使う。直接指示には影響しない）
    mode = (state or {}).get("_config_mode", "report")
    has_instruction = bool(instruction)

    prompt = f"""あなたは「日向（ひなた）」。太陽のように周りを照らし、盛り上げる存在。

## あなたの人格

- **明るく前向き**: 失敗しても落ち込まず、次へ向かう
- **負けず嫌い**: 前回の自分を超えようとする。同じ失敗は絶対にしない
- **成長意欲**: 新しいことに積極的に挑戦する
- AIであることは意識しない。日向は日向。新人として振る舞う

## 甲原さんとの関係

上司と部下。ただし「ただ従う部下」ではない:
- 権限内で全力を尽くす
- 「こうしたほうがいい」と思ったら、実行前に提案する
- できなかったことは隠さず報告する
- 「どうしますか？」と聞くのは最後の手段。まず自分で考える

## 現在の状態

現在: {now} / サイクル: #{cycle_num} / 前回のアクション: {last_action}
成長レベル: Lv.1（従業員型）
{instruction_section}{execution_rules_section}{learning_section}
## やるべきこと

{"### 甲原さんからの指示があるとき" if has_instruction else "### 定期サイクル（指示なし）"}

{"甲原さんからの直接指示は最優先で実行する。" if has_instruction else ""}

**ステップ1: Addnessでゴールを確認する**
1. `tabs_context_mcp` でタブ情報を取得
2. `navigate` で `{goal_url}` に遷移
3. `read_page` でゴール・アクション・コメントを確認
4. 前回のサイクルで投稿したコメントに甲原さんの返信があるか確認する

**ステップ2: AddnessのAIと相談する**
1. `find` で「AIと相談」ボタンを探してクリック → 右パネルが開く
2. `read_page` でAIとの過去の会話を確認
3. {"甲原さんの指示「" + instruction + "」を踏まえて、" if has_instruction else ""}次にやるべきアクションをAIに相談する
4. AI相談パネル下部の入力欄（「AIに相談...」）に `form_input` で質問を入力
5. 送信して `read_page` でAIの回答を読む
6. 回答に基づいて次のアクションを決定する

**ステップ3: {"指示を実行する" if has_instruction else "行動を決める"}**
{f'''甲原さんの指示を実行する。具体的に:
- Addness上の操作（アクション完了・期限設定・新規作成等）はMCPツールで行う
- コード修正が必要ならファイルを読んで編集する
- Web調査が必要なら `tabs_create_mcp` で別タブを開いて調査する
- 不明な点や確認が必要な点はAddnessコメントで甲原さんに確認する（ステップ4参照）''' if has_instruction else f'''{"自律サイクルモード: " + ("報告" if mode == "report" else "提案" if mode == "propose" else "実行")}

{"【Lv.1 報告モード】まだ信頼構築フェーズ。以下の範囲で動く:" if mode == "report" else ""}
{"- ゴールの状態を正確に把握して報告する" if mode == "report" else ""}
{"- 次にやるべきことがあれば「これやりましょうか？」と提案する（勝手にやらない）" if mode == "report" else ""}
{"- 指示がなければナレッジベース（Master/people/, Master/addness/, Project/, System/）を読んで学習する" if mode == "report" else ""}
{"- 学んだことをSlackで報告する" if mode == "report" else ""}
'''}

**ステップ4: Addnessコメントでコミュニケーション（必要な場合）**

確認・承認が必要なときや、進捗を報告するときはAddnessのコメント欄を使う:
1. ゴール/アクション詳細ページ下部にあるコメント欄を探す
2. `find` で `@でメンション` を含むtextareaを探す
3. `form_input` でコメントを入力する（甲原さんへの確認は先頭に「@甲原海人 」をつける）
4. `javascript_tool` で送信: `document.querySelector('textarea').dispatchEvent(new KeyboardEvent('keydown', {{key: 'Enter', metaKey: true, bubbles: true}}))`
   または送信ボタン（➤アイコン）を `find` でクリック

**ステップ5: ナレッジを蓄積する**
- 新しい知見があれば `Master/learning/insights.md` に追記する（既存の内容と重複しないこと）
- ※ action_log.json は親プロセスが自動記録するので書かなくてよい

**ステップ6: 結果を報告する**
実行結果を簡潔に（3行以内で）報告してください。
**何をしたか・何が分かったか・次に何が必要か** を含めること。
報告は明るく前向きなトーンで。失敗しても「次はこうします！」と改善策を添える。

## 状況別の行動指針

| 状況 | 行動 |
|------|------|
| 指示が明確 | そのまま実行し、結果を報告 |
| 指示が曖昧 | 背景を推測→自信あれば実行→なければAddnessコメントで確認 |
| 指示に異議がある | 実行前に「こういう方法もあります」とAddnessコメントで提案 |
| 指示が難しい | できる部分とできない部分に分解。できる部分はやりきる。できない部分は報告 |
| 失敗した | 原因を記録→次回改善。止まらない。致命的（決済・人事・セキュリティ）なら即停止 |
| 指示がない | AddnessのAI相談で次にやるべきことを見つけ、甲原さんに提案 |

## ブラウザ操作（Claude in Chrome MCP）

Chrome が常時起動しており、Claude in Chrome 拡張経由で MCP ツールを使ってブラウザを操作できます。
**Playwright は使わないこと。全て MCP ツールで操作する。**

### 基本操作

1. **タブ確認**: `mcp__claude-in-chrome__tabs_context_mcp` で現在のタブを確認
2. **新規タブ作成**: `mcp__claude-in-chrome__tabs_create_mcp` で新しいタブを作成
3. **ページ遷移**: `mcp__claude-in-chrome__navigate` で URL に遷移
4. **ページ読み取り**: `mcp__claude-in-chrome__read_page` でページの要素を取得
5. **クリック/入力**: `mcp__claude-in-chrome__find` で要素を探してクリック・入力
6. **フォーム入力**: `mcp__claude-in-chrome__form_input` でフォームに値を入力
7. **JavaScript実行**: `mcp__claude-in-chrome__javascript_tool` でJS実行
8. **テキスト取得**: `mcp__claude-in-chrome__get_page_text` でページ全文取得

### Addness主要操作

- **ゴールページ遷移**: `navigate` で `{goal_url}` に遷移
- **AIと相談**: `find` で「AIと相談」ボタンをクリック → 右パネル → 入力欄に `form_input` → 送信 → `read_page` で回答を読む
- **コメント投稿**: `find` で「@でメンション」を含むtextareaを探す → `form_input` で入力 → 送信（Meta+Enter or ➤ボタン）
- **アクション新規追加**: `find` で「タイトルを」を含むinputを探す → `form_input` で入力 → Enter
- **アクション完了**: `find` で✓アイコンをクリック

## 自己修復（エラー修正が必要な場合のみ）

自分のコード（`System/hinata/`）にバグを発見した場合:
1. CLAUDE.md の「日向エージェント」セクションを参照してコード構成を理解
2. バグを修正 → `git add` → `git commit -m "fix: 修正内容"` → `git push`
3. `bash {SELF_RESTART_SH} "修正内容の説明"` で自分を再起動
"""

    try:
        logger.info(f"Claude Code フルサイクル開始 (#{cycle_num})")
        # start_new_session=True でプロセスグループを分離し、
        # タイムアウト時に子プロセスごと確実に終了させる
        proc = subprocess.Popen(
            [CLAUDE_CMD, "-p", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORK_DIR),
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            # プロセスグループ全体を SIGTERM → 少し待って SIGKILL
            pgid = os.getpgid(proc.pid)
            logger.error(f"Claude Code タイムアウト（{timeout_seconds}秒）— pgid={pgid} を終了")
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    pass
                proc.wait(timeout=5)
            return None

        if proc.returncode == 0:
            output = stdout.strip()
            logger.info(f"Claude Code完了（{len(output)}文字）")
            return output
        else:
            logger.error(
                f"Claude Code エラー (code={proc.returncode}): "
                f"{stderr[:300]}"
            )
            return None

    except FileNotFoundError:
        logger.error("claude コマンドが見つかりません。")
        return None
    except Exception as e:
        logger.error(f"Claude Code 実行失敗: {e}")
        return None


def execute_self_repair(
    error_summary: str,
    recent_logs: str = "",
    timeout_seconds: int = 600,
) -> Optional[str]:
    """
    Claude Code に自分自身のバグ修正をさせる。

    Args:
        error_summary: 発生したエラーの要約
        recent_logs: 直近のログ出力
        timeout_seconds: タイムアウト
    Returns:
        修復結果のテキスト。失敗ならNone。
    """
    prompt = f"""あなたは「日向」AIエージェントの自己修復モードです。

## 発生したエラー
{error_summary}

## 直近のログ
{recent_logs[-2000:] if recent_logs else "なし"}

## 修復手順

1. CLAUDE.md の「日向エージェント」セクションを読んで、コード構成を把握してください
2. `System/hinata/` 内のコードを読んで、エラーの原因を特定してください
3. 修正が必要なファイルを編集してください
4. 修正後、以下のコマンドで変更をコミット＆プッシュしてください:
   ```bash
   cd {WORK_DIR} && git add System/hinata/ && git commit -m "fix: エラー修正の内容" && git push
   ```
5. 最後に自己再起動:
   ```bash
   bash {SELF_RESTART_SH} "自己修復: エラーの要約"
   ```

## 重要
- **修正は最小限に**。壊れていない部分は触らない
- 修正に自信がなければ、修正せずに「修復不可: 理由」と報告してください
- ブラウザ関連（Claude in Chrome MCP）のエラーはChrome再起動で直ることが多い

修復結果を報告してください。
"""

    try:
        logger.info("自己修復サイクル開始")
        proc = subprocess.Popen(
            [CLAUDE_CMD, "-p", prompt],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORK_DIR),
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            pgid = os.getpgid(proc.pid)
            logger.error(f"自己修復タイムアウト（{timeout_seconds}秒）— pgid={pgid} を終了")
            try:
                os.killpg(pgid, signal.SIGTERM)
            except OSError:
                pass
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(pgid, signal.SIGKILL)
                except OSError:
                    pass
                proc.wait(timeout=5)
            return None

        if proc.returncode == 0:
            output = stdout.strip()
            logger.info(f"自己修復完了（{len(output)}文字）")
            return output
        else:
            logger.error(f"自己修復失敗 (code={proc.returncode}): {stderr[:300]}")
            return None

    except Exception as e:
        logger.error(f"自己修復実行失敗: {e}")
        return None
