"""
Claude Code 実行モジュール（日向エージェント用）

常駐ブラウザにCDP接続して、Addness操作もアクション実行も全てClaude Codeが行う。
"""

import json
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hinata.claude")

# claude -p の作業ディレクトリ（CLAUDE.md がある場所）
_agents_dir = Path.home() / "agents" / "_repo"
WORK_DIR = _agents_dir if _agents_dir.exists() else Path.home() / "Cursor"
CLAUDE_CMD = "/opt/homebrew/bin/claude"
_venv_python = Path.home() / "hinata-venv" / "bin" / "python"
PYTHON_CMD = str(_venv_python) if _venv_python.exists() else "python3"
ADDNESS_CLI = str(Path(__file__).parent / "addness_cli.py")
SELF_RESTART_SH = str(Path(__file__).parent / "self_restart.sh")
CDP_URL = "http://localhost:9222"

# 学習ファイルのパス
_learning_dir = WORK_DIR / "Master" / "learning"
ACTION_LOG_PATH = _learning_dir / "action_log.json"
INSIGHTS_PATH = _learning_dir / "insights.md"


def _load_recent_actions(n: int = 5) -> str:
    """action_log.json から直近N件のアクション履歴を読み込む。"""
    try:
        if not ACTION_LOG_PATH.exists():
            return ""
        with open(ACTION_LOG_PATH, "r", encoding="utf-8") as f:
            logs = json.load(f)
        if not logs:
            return ""
        recent = logs[-n:]
        lines = []
        for entry in recent:
            lines.append(
                f"- [{entry.get('date', '?')}] #{entry.get('cycle', '?')}: "
                f"{entry.get('action', '?')} → {entry.get('result', '?')[:100]}"
            )
        return "\n".join(lines)
    except Exception as e:
        logger.warning(f"アクションログ読み込み失敗: {e}")
        return ""


def _load_insights() -> str:
    """insights.md の内容を読み込む。"""
    try:
        if not INSIGHTS_PATH.exists():
            return ""
        text = INSIGHTS_PATH.read_text(encoding="utf-8").strip()
        if len(text) > 1500:
            text = text[:1500] + "\n... (省略)"
        return text
    except Exception as e:
        logger.warning(f"インサイト読み込み失敗: {e}")
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
    常駐ブラウザにCDP接続して、Addness操作→実行→蓄積まで全部やる。
    """
    now = datetime.now().strftime("%Y/%m/%d %H:%M")
    last_action = (state or {}).get("last_action", "なし（初回）")

    instruction_section = ""
    if instruction:
        instruction_section = (
            f"\n## 甲原さんからの指示\n"
            f"「{instruction}」\n"
        )

    # 学習コンテキストを構築
    learning_section = ""
    recent_actions = _load_recent_actions(5)
    insights = _load_insights()
    if recent_actions or insights:
        learning_section = "\n## 過去の学習コンテキスト\n"
        if recent_actions:
            learning_section += f"\n### 直近のアクション履歴\n{recent_actions}\n"
        if insights:
            learning_section += f"\n### 蓄積された知見\n{insights}\n"
        learning_section += (
            "\n上記の履歴・知見を踏まえて行動してください。"
            "同じ失敗を繰り返さず、過去の成功パターンを活用すること。\n"
        )

    prompt = f"""あなたは「日向」というAIエージェントです。
現在: {now} / サイクル: #{cycle_num} / 前回のアクション: {last_action}
{instruction_section}{learning_section}
## 常駐ブラウザへの接続

Addnessにログイン済みのブラウザが常時起動しています。
以下のPythonコードで接続してください（**閉じないこと**）:

```python
from playwright.sync_api import sync_playwright
pw = sync_playwright().start()
browser = pw.chromium.connect_over_cdp("{CDP_URL}")
page = browser.contexts[0].pages[0]

# 操作が終わったら接続だけ切断（ブラウザは閉じない）
browser.close()  # これは接続を切るだけ。ブラウザは残る
pw.stop()
```

- Python: {PYTHON_CMD}
- **browser.close() は「接続切断」であり「ブラウザを閉じる」ではない**。必ず呼ぶこと
- context.close() は **絶対に呼ばないこと**（ブラウザが閉じてしまう）

## Addness UI操作リファレンス

詳細は `Master/addness/ui_operations.md` を参照。主要な操作:

- **ゴールページ遷移**: `page.goto("{goal_url}")`
- **アクション新規追加**: `page.locator('input[placeholder*="タイトルを"]').scroll_into_view_if_needed()` → fill → Enter
- **アクション完了**: 行の✓アイコンをクリック（x=1135, 各行y=289+66*行番号）
- **アクション「...」メニュー**: x=1209 をクリック → 完了/アサイン/期日設定/削除等
- **ゴール「...」メニュー**: x=1204, y=125 → KPI設定/期日設定/完了等
- **期日設定**: メニュー→「期日を設定」→ YYYY/MM/DD入力 → 保存
- **KPI設定**: ゴール「...」→「KPIを設定する」→ タイトル・単位・目標数値 → 完了
- **AIと相談**: `page.locator('text=AIと相談').click()` → 右パネル
- **コメント投稿**: `textarea[placeholder*="@でメンション"]` に入力 → Meta+Enter

## 実行手順

### ステップ1: Addnessでゴールとアクションを確認
1. ブラウザに接続する
2. ゴールページに遷移: `page.goto("{goal_url}")`
3. ゴールの内容、現在のアクション、コメントを確認する
4. 「AIと相談」を開いてアクションについて相談する
5. 甲原さんからのコメント指示があればそれも踏まえる

### ステップ2: アクションを実行
- AIと相談で決まったアクションを実行する
- Addness上の操作（アクション完了・期限設定・新規作成等）もこのブラウザで行う
- Web調査やファイル作成が必要なら自分で判断して実行
- 甲原さんへの確認が必要なら、Addnessでコメント（@甲原海人をつける）

### ステップ3: ナレッジを蓄積
- `Master/learning/action_log.json` — 配列にアクション履歴を追記
  フォーマット: {{"date": "YYYY/MM/DD HH:MM", "cycle": N, "action": "...", "result": "...", "instruction": "..."}}
- `Master/learning/insights.md` — 得られた知見があれば追記
- 新しいスキルやナレッジは `Skills/` や `Master/knowledge/` に適切に保存

### ステップ4: 結果を報告
実行結果を簡潔に（3行以内で）報告してください。

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
- ブラウザ関連（CDP/Playwright）のエラーは再起動で直ることが多い

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
