"""
Claude Code 実行モジュール（日向エージェント用）

常駐ブラウザにCDP接続して、Addness操作もアクション実行も全てClaude Codeが行う。
"""

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("hinata.claude")

WORK_DIR = Path.home() / "Cursor"
CLAUDE_CMD = "/opt/homebrew/bin/claude"
PYTHON_CMD = str(Path.home() / "hinata-venv" / "bin" / "python")
ADDNESS_CLI = str(Path(__file__).parent / "addness_cli.py")
CDP_URL = "http://localhost:9222"


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

    prompt = f"""あなたは「日向」というAIエージェントです。
現在: {now} / サイクル: #{cycle_num} / 前回のアクション: {last_action}
{instruction_section}
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
- 甲原さんへの確認が必要なら、Addnessでコメント（@甲原 をつける）

### ステップ3: ナレッジを蓄積
- `Master/learning/action_log.json` — 配列にアクション履歴を追記
  フォーマット: {{"date": "YYYY/MM/DD HH:MM", "cycle": N, "action": "...", "result": "...", "instruction": "..."}}
- `Master/learning/insights.md` — 得られた知見があれば追記
- 新しいスキルやナレッジは `Skills/` や `Master/knowledge/` に適切に保存

### ステップ4: 結果を報告
実行結果を簡潔に（3行以内で）報告してください。
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
