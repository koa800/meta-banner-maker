"""
Claude Code 実行モジュール（日向エージェント用）

Claude in Chrome MCP ツールでブラウザを直接操作。
Addness操作もアクション実行も全てClaude Codeが行う。
"""

import logging
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

    prompt = f"""あなたは「日向」というAIエージェントです。
現在: {now} / サイクル: #{cycle_num} / 前回のアクション: {last_action}
{instruction_section}{learning_section}
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

### 操作の流れ

1. まず `tabs_context_mcp` でタブ情報を取得（tabId が必要）
2. 必要に応じて `tabs_create_mcp` で新しいタブを作る
3. `navigate` で目的のURLに遷移
4. `read_page` でページ内容を確認
5. `find` や `form_input` で要素を操作

## Addness UI操作リファレンス

詳細は `Master/addness/ui_operations.md` を参照。主要な操作:

- **ゴールページ遷移**: `navigate` で `{goal_url}` に遷移
- **アクション新規追加**: `find` でタイトル入力欄を探して入力 → Enter
- **アクション完了**: `find` で✓アイコンをクリック
- **AIと相談**: `find` で「AIと相談」ボタンをクリック → 右パネル
- **コメント投稿**: `find` でコメント入力欄を探して入力 → `form_input` で送信

## 実行手順

### ステップ1: Addnessでゴールとアクションを確認
1. `tabs_context_mcp` でタブを確認
2. ゴールページに遷移: `navigate` で `{goal_url}` へ
3. `read_page` でゴールの内容、現在のアクション、コメントを確認
4. 「AIと相談」を開いてアクションについて相談
5. 甲原さんからのコメント指示があればそれも踏まえる

### ステップ2: アクションを実行
- AIと相談で決まったアクションを実行する
- Addness上の操作（アクション完了・期限設定・新規作成等）もMCPツールで行う
- Web調査が必要なら `tabs_create_mcp` で別タブを開いて調査
- 甲原さんへの確認が必要なら、Addnessでコメント（@甲原海人をつける）

### ステップ3: ナレッジを蓄積（任意）
- `Master/learning/insights.md` — 新しい知見があれば追記（既存の内容と重複しないこと）
- ※ action_log.json は自動記録されるので書かなくてよい

### ステップ4: 結果を報告
実行結果を簡潔に（3行以内で）報告してください。
**何をしたか・何が分かったか・次に何が必要か** を含めること。

## 自己修復（エラー修正が必要な場合のみ）

自分のコード（`System/hinata/`）にバグを発見した場合:
1. CLAUDE.md の「日向エージェント」セクションを参照してコード構成を理解
2. バグを修正 → `git add` → `git commit -m "fix: 修正内容"` → `git push`
3. `bash {SELF_RESTART_SH} "修正内容の説明"` で自分を再起動
"""

    try:
        logger.info(f"Claude Code フルサイクル開始 (#{cycle_num})")
        result = subprocess.run(
            [CLAUDE_CMD, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(WORK_DIR),
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            logger.info(f"Claude Code完了（{len(output)}文字）")
            return output
        else:
            logger.error(
                f"Claude Code エラー (code={result.returncode}): "
                f"{result.stderr[:300]}"
            )
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"Claude Code タイムアウト（{timeout_seconds}秒）")
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
        result = subprocess.run(
            [CLAUDE_CMD, "-p", prompt],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(WORK_DIR),
        )

        if result.returncode == 0:
            output = result.stdout.strip()
            logger.info(f"自己修復完了（{len(output)}文字）")
            return output
        else:
            logger.error(f"自己修復失敗 (code={result.returncode}): {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"自己修復タイムアウト（{timeout_seconds}秒）")
        return None
    except Exception as e:
        logger.error(f"自己修復実行失敗: {e}")
        return None
