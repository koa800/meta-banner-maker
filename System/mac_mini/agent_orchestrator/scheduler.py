"""
APScheduler-based task scheduler for the agent orchestrator.
Replaces cron jobs with in-process scheduling and logging.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from . import tools
from .memory import MemoryStore
from .shared_logger import get_logger

logger = get_logger("scheduler")

_repair_agent_ref = None

# ---- execution_rules.json 読み込み（簡潔フォーマット・キャッシュ付き） ----
_execution_rules_compact_cache: str | None = None


def _build_execution_rules_compact() -> str:
    """システムプロンプト注入用の簡潔な行動ルール文字列を生成（キャッシュ付き）。"""
    global _execution_rules_compact_cache
    if _execution_rules_compact_cache is not None:
        return _execution_rules_compact_cache

    import json as _json

    # Mac Mini 上のパスを複数フォールバック
    candidates = [
        Path.home() / "agents" / "Master" / "learning" / "execution_rules.json",
        Path.home() / "agents" / "_repo" / "Master" / "learning" / "execution_rules.json",
        Path(__file__).resolve().parent.parent.parent.parent / "Master" / "learning" / "execution_rules.json",
    ]
    rules = []
    for p in candidates:
        try:
            if p.exists():
                rules = _json.loads(p.read_text(encoding="utf-8"))
                break
        except Exception:
            continue

    if not rules:
        _execution_rules_compact_cache = ""
        return ""

    lines = []
    for r in rules:
        situation = r.get("situation", "")
        action = r.get("action", r.get("rule", ""))
        if situation:
            lines.append(f"- 【{situation}】→ {action}")
        else:
            lines.append(f"- {action}")
    _execution_rules_compact_cache = "\n### 甲原さんの行動ルール\n" + "\n".join(lines) + "\n"
    return _execution_rules_compact_cache


def set_repair_agent(agent):
    """Set the RepairAgent reference for the scheduler to use."""
    global _repair_agent_ref
    _repair_agent_ref = agent


class TaskScheduler:
    def __init__(self, config: dict, memory: MemoryStore):
        self.config = config
        self.memory = memory
        self.scheduler = AsyncIOScheduler()
        self._task_map = {
            "addness_fetch": self._run_addness_fetch,
            "ai_news": self._run_ai_news,
            "mail_inbox_personal": self._run_mail_personal,
            "mail_inbox_kohara": self._run_mail_kohara,
            "addness_goal_check": self._run_addness_goal_check,
            "daily_report": self._run_daily_report,
            "health_check": self._run_health_check,
            "repair_check": self._run_repair_check,
            "weekly_idea_proposal": self._run_weekly_idea_proposal,
            "weekly_stats": self._run_weekly_stats,
            "daily_addness_digest": self._run_daily_addness_digest,
            "oauth_health_check": self._run_oauth_health_check,
            "render_health_check": self._run_render_health_check,
            "weekly_content_suggestions": self._run_weekly_content_suggestions,
            "daily_report_input": self._run_daily_report_input,
            "daily_report_verify": self._run_daily_report_verify,
            "looker_csv_download": self._run_looker_csv_download,
            "kpi_daily_import": self._run_kpi_daily_import,
            "sheets_sync": self._run_sheets_sync,
            "git_pull_sync": self._run_git_pull_sync,
            "daily_group_digest": self._run_daily_group_digest,
            "weekly_profile_learning": self._run_weekly_profile_learning,
            "kpi_nightly_cache": self._run_kpi_nightly_cache,
            "log_rotate": self._run_log_rotate,
            "slack_dispatch": self._run_slack_dispatch,
            "slack_ai_team_check": self._run_slack_ai_team_check,
            "hinata_activity_check": self._run_hinata_activity_check,
            "slack_hinata_auto_reply": self._run_slack_hinata_auto_reply,
            "os_sync_session": self._run_os_sync_session,
            "secretary_proactive_work": self._run_secretary_proactive_work,
            "weekly_hinata_memory": self._run_weekly_hinata_memory,
            "video_knowledge_review": self._run_video_knowledge_review,
            "video_learning_reminder": self._run_video_learning_reminder,
            "daily_report_reminder": self._run_daily_report_reminder,
            "anthropic_credit_check": self._run_anthropic_credit_check,
        }

    def setup(self):
        schedule_cfg = self.config.get("schedule", {})

        for task_name, task_fn in self._task_map.items():
            cfg = schedule_cfg.get(task_name, {})
            if not cfg.get("enabled", False):
                logger.info(f"Task '{task_name}' is disabled, skipping")
                continue

            if "cron" in cfg:
                parts = cfg["cron"].split()
                trigger = CronTrigger(
                    minute=parts[0], hour=parts[1], day=parts[2],
                    month=parts[3], day_of_week=parts[4]
                )
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True)
                logger.info(f"Scheduled '{task_name}' with cron: {cfg['cron']}")
            elif "interval_seconds" in cfg:
                trigger = IntervalTrigger(seconds=cfg["interval_seconds"])
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True)
                logger.info(f"Scheduled '{task_name}' every {cfg['interval_seconds']} seconds")
            elif "interval_minutes" in cfg:
                trigger = IntervalTrigger(minutes=cfg["interval_minutes"])
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True)
                logger.info(f"Scheduled '{task_name}' every {cfg['interval_minutes']} minutes")

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("Scheduler shut down")

    # タスク失敗通知を送らないタスク（自前でエラーハンドリングするもの）
    _NO_FAILURE_NOTIFY = {"health_check", "oauth_health_check", "render_health_check", "anthropic_credit_check"}
    # git_pull_syncは独自の頻度制限付き通知を実装（_run_git_pull_sync参照）

    async def _execute_tool(self, task_name: str, tool_fn, **kwargs) -> tools.ToolResult:
        task_id = self.memory.log_task_start(task_name, metadata=kwargs)
        try:
            result = tool_fn(**kwargs)
            status = "success" if result.success else "error"
            self.memory.log_task_end(
                task_id, status,
                result_summary=result.output[:500] if result.output else None,
                error_message=result.error[:500] if result.error else None
            )
            if result.success:
                logger.info(f"Task '{task_name}' completed successfully")
                self.memory.set_state(f"last_success_{task_name}", datetime.now().isoformat())
            else:
                logger.error(f"Task '{task_name}' failed: {result.error[:200]}")
                if task_name not in self._NO_FAILURE_NOTIFY:
                    self._maybe_notify_task_failure(task_name, result.error or "不明なエラー")
            return result
        except Exception as e:
            self.memory.log_task_end(task_id, "error", error_message=str(e))
            logger.exception(f"Task '{task_name}' raised an exception")
            if task_name not in self._NO_FAILURE_NOTIFY:
                self._maybe_notify_task_failure(task_name, str(e))
            raise

    def _maybe_notify_task_failure(self, task_name: str, error_msg: str):
        """タスク失敗をLINE+Slack通知（2時間以内に同タスクの通知済みならスキップ）"""
        from .notifier import notify_ai_team
        now = datetime.now()
        state_key = f"failure_notified_{task_name}"
        last_notified = self.memory.get_state(state_key)
        if last_notified:
            try:
                last_dt = datetime.fromisoformat(last_notified)
                if (now - last_dt).total_seconds() < 7200:
                    return  # 2時間以内は通知済み
            except (ValueError, TypeError):
                pass
        ok = notify_ai_team(
            f"\n⚠️ タスクエラー: {task_name}\n"
            f"━━━━━━━━━━━━\n"
            f"{error_msg[:250]}\n"
            f"━━━━━━━━━━━━"
        )
        if ok:
            self.memory.set_state(state_key, now.isoformat())

    async def _run_addness_fetch(self):
        result = await self._execute_tool("addness_fetch", tools.addness_fetch)
        if result.success:
            ctx_result = await self._execute_tool("addness_to_context", tools.addness_to_context)
            from .notifier import send_line_notify
            send_line_notify(f"✅ Addnessゴール同期完了（コンテキスト{'更新済み' if ctx_result.success else '更新失敗'}）")
        else:
            await self._execute_tool("addness_to_context", tools.addness_to_context)

    async def _run_ai_news(self):
        result = await self._execute_tool("ai_news", tools.ai_news_notify)
        if result.success and result.output:
            from .notifier import send_line_notify
            # ai_news_notifyは自前でLINE通知するので、ここでは追加通知しない
            logger.info(f"AI news completed: {result.output[:100]}")

    async def _run_mail_personal(self):
        result = await self._execute_tool("mail_inbox_personal", tools.mail_run, account="personal")
        await self._notify_mail_result(result, "personal")

    async def _run_mail_kohara(self):
        result = await self._execute_tool("mail_inbox_kohara", tools.mail_run, account="kohara")
        await self._notify_mail_result(result, "kohara")

    async def _notify_mail_result(self, result: tools.ToolResult, account: str):
        """メール処理結果をLINE+Slack通知（返信待ちがある場合のみ）"""
        if not result.success or not result.output:
            return
        from .notifier import send_line_notify  # LINEのみ

        waiting_m = re.search(r"返信待ち[：:]\s*(\d+)\s*件", result.output)
        delete_m = re.search(r"削除確認[：:]\s*(\d+)\s*件", result.output)

        waiting = int(waiting_m.group(1)) if waiting_m else 0
        delete = int(delete_m.group(1)) if delete_m else 0

        if waiting <= 0:
            return

        account_label = "personal" if account == "personal" else "kohara"
        message = (
            f"\n📬 メール確認 ({account_label})\n"
            f"━━━━━━━━━━━━\n"
            f"返信待ち: {waiting}件"
            + (f" / 削除確認: {delete}件" if delete > 0 else "")
            + f"\n━━━━━━━━━━━━"
        )
        ok = send_line_notify(message)
        if ok:
            logger.info(f"Mail notification sent for {account}: waiting={waiting}")
        else:
            # 1回リトライ（ネットワーク一時エラー対策）
            import asyncio; await asyncio.sleep(5)
            ok = send_line_notify(message)
            if ok:
                logger.info(f"Mail notification sent for {account} (retry): waiting={waiting}")
            else:
                logger.warning(f"Mail notification failed for {account} after retry")

    async def _run_addness_goal_check(self):
        result = await self._execute_tool("addness_to_context", tools.addness_to_context)
        if result.success:
            logger.info("Addness goal context updated for daily review")

    def _find_claude_cmd(self):
        """Claude Code CLIパスを検出（Apple Silicon / Intel Mac 両対応）"""
        from pathlib import Path
        for p in [Path("/opt/homebrew/bin/claude"), Path("/usr/local/bin/claude")]:
            if p.exists():
                return p
        return None

    def _refresh_claude_oauth(self, secretary_config):
        """Claude Code の OAuth トークンが期限切れ or 1時間以内に切れる場合、
        refresh_token を使って自動更新する。
        Returns: (ok: bool, error_msg: str)
        """
        import json
        import subprocess
        from pathlib import Path

        creds_path = Path(secretary_config) / ".credentials.json"
        if not creds_path.exists():
            return False, f"credentials.json が見つかりません: {creds_path}"

        try:
            with open(creds_path) as f:
                creds = json.load(f)
        except Exception as e:
            return False, f"credentials.json 読み込みエラー: {e}"

        oauth = creds.get("claudeAiOauth", {})
        expires_at = oauth.get("expiresAt", 0)
        refresh_token = oauth.get("refreshToken")
        if not refresh_token:
            return False, "refresh_token がありません。再認証が必要です"

        import time
        now_ms = int(time.time() * 1000)
        remaining_ms = expires_at - now_ms
        remaining_hours = remaining_ms / (1000 * 3600)

        if remaining_hours > 1.0:
            logger.info(f"Claude OAuth: トークン有効（残り {remaining_hours:.1f}時間）")
            return True, ""

        # 1時間以内に切れる or すでに期限切れ → リフレッシュ
        logger.info(f"Claude OAuth: トークン更新開始（残り {remaining_hours:.1f}時間）")
        try:
            env = dict(os.environ)
            if "/opt/homebrew/bin" not in env.get("PATH", ""):
                env["PATH"] = f"/opt/homebrew/bin:{env.get('PATH', '')}"
            env["CLAUDE_CONFIG_DIR"] = str(secretary_config)

            # Claude Code CLI を一度起動すれば内部で自動リフレッシュされる
            claude_cmd = self._find_claude_cmd()
            if not claude_cmd:
                return False, "Claude Code CLI が見つかりません"

            result = subprocess.run(
                [str(claude_cmd), "-p", "--max-turns", "1", "1+1は？"],
                capture_output=True, text=True, timeout=60, env=env,
            )
            if result.returncode == 0:
                logger.info("Claude OAuth: トークン自動リフレッシュ成功")
                return True, ""
            else:
                return False, f"Claude Code 起動失敗（code={result.returncode}）: {result.stderr[:200]}"
        except subprocess.TimeoutExpired:
            return False, "Claude Code タイムアウト（60秒）"
        except Exception as e:
            return False, f"リフレッシュ例外: {e}"

    def _ensure_claude_chrome_ready(self):
        """Claude Code + Chrome の事前チェック。Chrome 未起動なら自動起動を試みる。
        Returns: (ok, claude_cmd, secretary_config, project_root, error_msg)
        """
        import subprocess
        import time as _time
        from pathlib import Path

        claude_cmd = self._find_claude_cmd()
        if not claude_cmd:
            return False, None, None, None, "Claude Code CLIが見つかりません"

        secretary_config = Path.home() / ".claude-secretary"
        if not secretary_config.exists():
            return False, None, None, None, (
                f"秘書設定ディレクトリが見つかりません: {secretary_config}\n"
                "Mac Mini で ~/.claude-secretary/ のセットアップが必要です"
            )

        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()

        # Claude Code OAuth トークンチェック + 自動リフレッシュ
        oauth_ok, oauth_err = self._refresh_claude_oauth(secretary_config)
        if not oauth_ok:
            return False, None, None, None, f"Claude Code OAuth エラー: {oauth_err}"

        # Chrome 起動確認 + 自動起動
        try:
            r = subprocess.run(["pgrep", "-f", "Google Chrome"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                logger.warning("Chrome 未起動 → 自動起動を試みます")
                subprocess.Popen(["open", "-a", "Google Chrome"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                _time.sleep(10)  # Chrome + 拡張機能の初期化待ち
                r2 = subprocess.run(["pgrep", "-f", "Google Chrome"],
                                    capture_output=True, text=True, timeout=5)
                if r2.returncode != 0:
                    return False, None, None, None, "Chrome 自動起動失敗。Mac Mini で手動起動が必要です"
                logger.info("Chrome 自動起動成功")
        except Exception as e:
            return False, None, None, None, f"Chrome チェックエラー: {e}"

        return True, claude_cmd, secretary_config, project_root, ""

    @staticmethod
    def _col_idx_to_letter(idx):
        """0-based index → Excel列文字 (A=0, B=1, ..., Z=25, AA=26, ...)"""
        result = ""
        idx += 1
        while idx > 0:
            idx, remainder = divmod(idx - 1, 26)
            result = chr(65 + remainder) + result
        return result

    def _classify_claude_error(self, stderr: str, stdout: str = "") -> str:
        """Claude Code 実行エラーの原因を分類し、対処を含むメッセージを返す。"""
        combined = (stderr + " " + stdout).lower()
        if any(k in combined for k in ["auth", "credential", "api key", "unauthorized", "401"]):
            return "認証エラー（~/.claude-secretary の credentials を確認）"
        if any(k in combined for k in ["mcp", "extension", "tabs_context", "connection refused"]):
            return "Chrome MCP 接続エラー（Chrome / Claude in Chrome 拡張を確認）"
        if any(k in combined for k in ["rate limit", "429", "too many requests"]):
            return "APIレート制限（しばらく待ってリトライ）"
        if any(k in combined for k in ["ログイン", "login", "sign in", "アカウント選択"]):
            return "Googleログイン切れ（Chrome で再ログインが必要）"
        if any(k in combined for k in ["credit balance", "credit", "billing", "payment"]):
            return "Claude Code クレジット不足（秘書アカウントの利用枠をリセット待ち）"
        if "max turns" in combined or "reached max" in combined:
            return "ターン数上限到達（max_turns を増やす必要あり）"
        return stderr[:200] if stderr.strip() else stdout[-200:]

    def _execute_claude_code_task(self, task_label, claude_cmd, secretary_config,
                                  project_root, prompt, max_turns=25, timeout=600,
                                  use_chrome=False):
        """Claude Code CLI 実行ヘルパー（1回リトライ・エラー分類付き）。
        use_chrome=True のときは --chrome を渡し、秘書用ChromeのMCPでブラウザ操作を有効にする。
        Returns: (success: bool, output: str, error_msg: str)
        """
        import subprocess
        import os
        import time as _time

        env = os.environ.copy()
        # launchd 環境でも node が見つかるよう PATH を保証
        path = env.get("PATH", "")
        if "/opt/homebrew/bin" not in path:
            env["PATH"] = f"/opt/homebrew/bin:{path}"
        env["CLAUDE_CONFIG_DIR"] = str(secretary_config)
        cmd = [str(claude_cmd), "-p", "--model", "claude-sonnet-4-6",
               "--max-turns", str(max_turns)]
        if use_chrome:
            cmd.append("--chrome")
        cmd.append(prompt)

        for attempt in range(2):  # 最大2回（初回 + リトライ1回）
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=timeout, cwd=str(project_root), env=env,
                )
                if result.returncode == 0:
                    output = result.stdout.strip()
                    logger.info(f"{task_label}: Claude Code 完了 ({len(output)} chars)")
                    return True, output, ""

                # 失敗 → 全文をログに記録（LINE には分類済み要約のみ送信）
                error_detail = self._classify_claude_error(result.stderr, result.stdout)
                logger.error(
                    f"{task_label}: Claude Code 失敗 (attempt {attempt+1}, code={result.returncode})\n"
                    f"  stderr: {result.stderr[:500]}\n"
                    f"  stdout(末尾): {result.stdout[-300:]}"
                )
                if attempt == 0:
                    logger.info(f"{task_label}: 60秒後にリトライ...")
                    _time.sleep(60)
                    continue
                return False, result.stdout, error_detail

            except subprocess.TimeoutExpired:
                logger.error(f"{task_label}: タイムアウト ({timeout}秒, attempt {attempt+1})")
                if attempt == 0:
                    _time.sleep(60)
                    continue
                return False, "", f"タイムアウト（{timeout // 60}分超過 × 2回）"

            except Exception as e:
                logger.error(f"{task_label}: 例外 (attempt {attempt+1}) - {e}")
                if attempt == 0:
                    _time.sleep(60)
                    continue
                return False, "", str(e)

        return False, "", "リトライ上限到達"

    async def _run_daily_report_input(self):
        """日報自動入力: 秘書がClaude Code経由でLooker Studioからデータ取得→日報シート書き込み→LINE報告。"""
        from .notifier import send_line_notify
        from datetime import date, timedelta

        logger.info("日報自動入力: 開始")

        # プリフライトチェック（Chrome 自動起動含む）
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"日報自動入力: プリフライト失敗 - {preflight_err}")
            send_line_notify(f"⚠️ 日報自動入力失敗\n{preflight_err}")
            return

        target_date = date.today() - timedelta(days=1)
        target_md = f"{target_date.month}/{target_date.day}"

        prompt = f"""あなたは甲原海人のAI秘書です。日報を自動入力してください。

## タスク
{target_date.strftime('%Y年%m月%d日')}（{target_md}）の日報データを取得し、日報シートに書き込んでください。

## 手順

### Step 1: Looker Studio 日別データページからデータ取得
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_evmsc9twzd
- ブラウザで開く → 幅1400px・高さ900pxにリサイズ → スクショ撮影
- テーブル上部をズームイン撮影して先頭行（{target_md}分）の数字を再確認
- 読み取る数値: 集客数、個別予約数、着金売上（確定ベース）

### Step 2: Looker Studio 会員数ページからデータ取得
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dfv0688m0d
- ブラウザで開く → 幅1400px・高さ900pxにリサイズ → スクショ撮影
- 読み取る数値: スキルプラス会員数（net change）、解約数

### Step 3: サブスク新規会員数を Google Sheet API で取得
- シートID: 1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70
- タブ「秘密の部屋（月額）」と「秘密の部屋（年額）」のA列に「{target_date.strftime('%Y-%m-%d')}」を含む行数を合算
```bash
cd {project_root}
python3 System/sheets_manager.py read "1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70" "秘密の部屋（月額）" "A1:A5000"
python3 System/sheets_manager.py read "1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70" "秘密の部屋（年額）" "A1:A5000"
```
それぞれの出力から「{target_date.strftime('%Y-%m-%d')}」を含む行数をカウントし合算。

### Step 4: 日報シートのヘッダーから対象列を特定
```bash
cd {project_root}
python3 System/sheets_manager.py read "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "日報" "A1:JZ1"
```
ヘッダーは M/D 形式。「{target_md}」に一致する列を見つける。

### Step 5: 日報シートに書き込み

Step 4 で特定した列文字と、Step 1〜3 で取得した実際の数値を使って書き込む。
writeコマンドの引数順: `write シートID セル 値 タブ名`

例: 列が W、着金売上が 3943320 の場合:
```bash
cd {project_root}
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "W5" "3943320" "日報"
```

書き込み対象（列文字と値は実際のものに置き換えること）:
- 行5: 着金売上（確定ベース）
- 行7: 集客数
- 行9: 個別予約数
- 行13: スキルプラス会員数
- 行14: 解約数
- 行15: サブスク新規会員数

行4（粗利益）と行6（広告費）は計算式/別管理なので絶対に触らないこと。

### Step 6: LINE報告

取得した数値を埋め込んで報告する:
```bash
cd {project_root}
python3 System/line_notify.py "✅ 定常業務完了: 日報入力（自動）
━━━━━━━━━━━━
集客数: XXX人
個別予約数: XX件
着金売上: ¥X,XXX,XXX
会員数: XX人（解約: X人）
サブスク新規: X人
━━━━━━━━━━━━
完了時刻: $(date +%H:%M)"
```
※ XXX 部分は Step 1〜3 で取得した実際の数値に置き換えること。

## エラー時の対応

### ブラウザ接続エラー
- ブラウザツール（tabs_context_mcp, navigate等）が使えない・タイムアウトする場合:
  → ===RESULT_START===
  エラー: Chrome MCP に接続できません。Chrome + Claude in Chrome 拡張を確認してください
  ===RESULT_END===
  と出力して終了

### Googleログイン切れ
- Looker Studio にアクセスした際、ログイン画面やアカウント選択画面が表示された場合:
  → ===RESULT_START===
  エラー: Looker Studio のGoogleログインが切れています。Chrome で再ログインが必要です
  ===RESULT_END===
  と出力して終了

### 数値の検証
- 全ての数値がゼロの場合は異常（データ更新遅延の可能性）。LINE報告に「⚠️ 全数値ゼロ: データ更新遅延の可能性」を追記
- スクショの数値が不鮮明な場合、追加でズームインして再確認（最大2回）
- 着金売上・集客数が 0 の場合は「⚠️ 異常値検出」フラグをLINE報告に追記

## 重要ルール
- 行4（粗利益）と行6（広告費）は絶対に書き込まない
- Looker Studioのスクショは必ずズームイン再確認して数値を正確に読む
- 書き込み前に取得した全数値を確認用にログ出力する

## 出力形式
===RESULT_START===
（日報入力の結果サマリー。成功なら数値一覧、エラーならエラー内容を明記）
===RESULT_END==="""

        success, output, error = self._execute_claude_code_task(
            "日報自動入力", claude_cmd, secretary_config, project_root,
            prompt, max_turns=40, timeout=900, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_daily_report_input", datetime.now().isoformat())
            if "===RESULT_START===" in output and "===RESULT_END===" in output:
                report = output.split("===RESULT_START===")[1].split("===RESULT_END===")[0].strip()
                logger.info(f"日報自動入力: 完了 - {report[:300]}")
                if "エラー" in report:
                    send_line_notify(f"⚠️ 日報自動入力: {report[:300]}")
            else:
                logger.info(f"日報自動入力: 完了（マーカーなし）- {output[-300:]}")
        else:
            # エラー種別に応じた通知
            if "ログイン" in error or "login" in error.lower():
                send_line_notify(
                    f"⚠️ 日報自動入力失敗: Googleログイン切れ\n"
                    f"Chrome で koa800sea.nifs@gmail.com に再ログインが必要です\n"
                    f"対処: Mac Mini の Chrome を開き Looker Studio にアクセス→ログイン"
                )
            elif "OAuth" in error or "credential" in error.lower():
                send_line_notify(
                    f"⚠️ 日報自動入力失敗: Claude Code 認証エラー\n"
                    f"秘書の Claude Code OAuth トークンの再取得が必要です\n{error}"
                )
            elif "Chrome" in error or "MCP" in error:
                send_line_notify(
                    f"⚠️ 日報自動入力失敗: Chrome/MCP接続エラー\n"
                    f"Chrome または Claude in Chrome 拡張の再起動が必要です\n{error}"
                )
            else:
                send_line_notify(f"⚠️ 日報自動入力失敗（リトライ後）\n{error}")

    async def _run_daily_report_verify(self):
        """09:20: 日報自動入力の完了検証。実データを確認して未入力なら LINE 通知。"""
        import subprocess
        import ast
        import re
        from datetime import date, timedelta
        from .notifier import send_line_notify

        target_date = date.today() - timedelta(days=1)
        target_md = f"{target_date.month}/{target_date.day}"
        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()

        logger.info(f"日報検証: {target_md} のデータ確認開始")

        # タスク実行記録を確認
        last_success = self.memory.get_state("last_success_daily_report_input")
        task_ran_today = False
        if last_success:
            try:
                last_dt = datetime.fromisoformat(last_success)
                task_ran_today = last_dt.date() == date.today()
            except (ValueError, TypeError):
                pass

        try:
            # 1. ヘッダー行を読み取り → 対象列を特定
            header_result = subprocess.run(
                ["python3", "System/sheets_manager.py", "read",
                 "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk", "日報", "A1:JZ1"],
                capture_output=True, text=True, timeout=30,
                cwd=str(project_root),
            )
            if header_result.returncode != 0:
                logger.error(f"日報検証: ヘッダー読み取り失敗: {header_result.stderr[:200]}")
                return

            match = re.search(r'行1:\s*(\[.*\])', header_result.stdout)
            if not match:
                logger.error("日報検証: ヘッダー行のパースに失敗")
                return

            headers = ast.literal_eval(match.group(1))
            target_col_idx = None
            for i, h in enumerate(headers):
                if str(h).strip() == target_md:
                    target_col_idx = i
                    break

            if target_col_idx is None:
                logger.warning(f"日報検証: {target_md} の列が見つかりません（ヘッダー未登録の可能性）")
                return

            col = self._col_idx_to_letter(target_col_idx)

            # 2. データ行を読み取り（行5〜行15）
            data_result = subprocess.run(
                ["python3", "System/sheets_manager.py", "read",
                 "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk", "日報",
                 f"{col}5:{col}15"],
                capture_output=True, text=True, timeout=30,
                cwd=str(project_root),
            )
            if data_result.returncode != 0:
                logger.error(f"日報検証: データ読み取り失敗: {data_result.stderr[:200]}")
                return

            # 各行のデータを抽出（行1=row5, 行3=row7, 行5=row9, 行9=row13, 行10=row14, 行11=row15）
            data_lines = {}
            for m in re.finditer(r'行(\d+):\s*(\[.*?\])', data_result.stdout):
                row_num = int(m.group(1))
                row_data = ast.literal_eval(m.group(2))
                data_lines[row_num] = row_data

            # 3. チェック対象セルの値を確認
            check_items = {
                "着金売上(行5)": 1,
                "集客数(行7)": 3,
                "個別予約数(行9)": 5,
                "会員数(行13)": 9,
                "解約数(行14)": 10,
                "サブスク新規(行15)": 11,
            }

            missing = []
            for label, row_key in check_items.items():
                row = data_lines.get(row_key, [])
                value = str(row[0]).strip() if row else ""
                if not value:
                    missing.append(label)

            # 4. 結果に基づいて通知
            if missing:
                msg = (
                    f"\n⚠️ 日報検証: {target_md} のデータ未入力\n"
                    f"━━━━━━━━━━━━\n"
                    f"未入力: {', '.join(missing)}\n"
                )
                if not task_ran_today:
                    msg += "日報入力タスクが実行されていない可能性があります\n"
                else:
                    msg += "タスクは実行されましたが、書き込みに失敗した可能性があります\n"
                msg += "━━━━━━━━━━━━"
                send_line_notify(msg)
                logger.warning(f"日報検証: 未入力 - {missing}")
            else:
                logger.info(f"日報検証: {target_md} の全データ入力確認OK")

        except Exception as e:
            logger.error(f"日報検証: エラー - {e}")

    # 広告チーム全体 LINEグループID
    _AD_TEAM_GROUP_ID = "C7dd7f40a3af2186ff490997264c1036a"

    async def _run_daily_report_reminder(self):
        """平日12:00/19:00: チームメンバーの日報未記入を検出→赤ハイライト→広告チーム全体LINEにリマインド"""
        import subprocess
        import json as _json
        from datetime import date, timedelta
        from .notifier import send_line_notify

        target_date = date.today() - timedelta(days=1)
        target_md = f"{target_date.month}/{target_date.day}"
        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()

        logger.info(f"日報リマインド: {target_md} の未記入チェック開始")

        try:
            result = subprocess.run(
                ["python3", "System/sheets_manager.py", "check_daily_report", target_md],
                capture_output=True, text=True, timeout=60,
                cwd=str(project_root),
            )
            if result.returncode != 0:
                logger.error(f"日報リマインド: check_daily_report 失敗: {result.stderr[:300]}")
                return

            data = _json.loads(result.stdout)

            if data.get("error"):
                logger.warning(f"日報リマインド: {data['error']}")
                return

            missing_by_person = data.get("missing_by_person", {})
            missing_count = data.get("missing_count", 0)

            if missing_count == 0:
                logger.info(f"日報リマインド: {target_md} の全データ入力済み")
                return

            # 広告チーム全体LINEグループにリマインド送信
            lines = [
                f"📋 日報が未記入の方は書いておいてください！",
                "",
            ]
            for person, items in missing_by_person.items():
                lines.append(f"▶ {person}さん")
                for item in items:
                    lines.append(f"　・{item}")

            lines.append("")
            lines.append(
                "日報を書く👇\n"
                "https://docs.google.com/spreadsheets/d/"
                "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk/edit?gid=1717970415"
            )

            send_line_notify("\n".join(lines), group_id=self._AD_TEAM_GROUP_ID)
            logger.info(f"日報リマインド: {missing_count}件の未記入を広告チーム全体に通知（{len(missing_by_person)}名）")

        except _json.JSONDecodeError as e:
            logger.error(f"日報リマインド: JSON解析エラー - {e}")
        except Exception as e:
            logger.error(f"日報リマインド: エラー - {e}")

    async def _run_daily_report(self):
        from .notifier import send_line_notify
        from datetime import date
        summary = self.memory.get_daily_summary()
        stats = self.memory.get_task_stats(since_hours=24)

        total = summary["tasks_total"]
        success = summary["tasks_success"]
        errors = summary["tasks_errors"]
        success_rate = round(100 * success / total) if total > 0 else 0

        error_tasks = [name for name, s in stats.items() if s.get("error", 0) > 0]

        report_lines = [
            f"\n📊 日次レポート ({date.today().strftime('%m/%d')})",
            "━━━━━━━━━━━━",
            f"タスク: {success}/{total}件成功 ({success_rate}%)",
            f"APIコール: {summary['api_calls']}回",
        ]
        if error_tasks:
            report_lines.append(f"⚠️ エラー: {', '.join(error_tasks[:5])}")
        report_lines.append("━━━━━━━━━━━━")

        send_line_notify("\n".join(report_lines))

        report_text = (
            f"--- Daily Agent Report ---\n"
            f"Tasks: {total} total, {success} success, {errors} errors\n"
            f"API calls: {summary['api_calls']} (tokens: {summary['api_tokens']})\n"
            f"Task breakdown: {stats}"
        )
        logger.info(report_text)
        self.memory.set_state("last_daily_report", report_text)

    async def _run_health_check(self):
        import json as _json
        import subprocess
        from .notifier import send_line_notify
        api_calls = self.memory.get_api_calls_last_hour()
        limit = self.config.get("safety", {}).get("api_call_limit_per_hour", 100)
        if api_calls > limit * 0.9:
            logger.warning(f"API call rate critical: {api_calls}/{limit} in last hour")
            send_line_notify(
                f"\n⚠️ API使用量警告\n直近1時間: {api_calls}/{limit}回\n"
                f"API制限に近づいています。Anthropicダッシュボードを確認してください。"
            )
        elif api_calls > limit * 0.8:
            logger.warning(f"API call rate high: {api_calls}/{limit} in last hour")

        # Q&Aモニターの最終チェック時刻を確認（2時間以上未更新なら警告）
        qa_state_path = os.path.expanduser("~/agents/line_bot_local/qa_monitor_state.json")
        if os.path.exists(qa_state_path):
            try:
                with open(qa_state_path) as f:
                    qa_state = _json.load(f)
                last_check = qa_state.get("last_check")
                if last_check:
                    dt = datetime.fromisoformat(last_check.replace("Z", "+00:00"))
                    age_hours = (datetime.now().astimezone() - dt).total_seconds() / 3600
                    if age_hours > 4:
                        logger.warning(f"Q&A monitor stale: last check {age_hours:.1f}h ago — triggering local_agent restart")
                        state_key = "qa_monitor_stale_notified"
                        last_n = self.memory.get_state(state_key)
                        if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 14400:
                            # local_agent再起動を試みる（Q&Aモニターはlocal_agentの一部）
                            plist = os.path.expanduser("~/Library/LaunchAgents/com.linebot.localagent.plist")
                            restarted = False
                            if os.path.exists(plist):
                                try:
                                    subprocess.run(["launchctl", "unload", plist], capture_output=True, timeout=5)
                                    import asyncio; await asyncio.sleep(2)
                                    subprocess.run(["launchctl", "load", plist], capture_output=True, timeout=5)
                                    restarted = True
                                except Exception:
                                    pass
                            msg = (f"\n🔄 Q&Aモニター停止検知→local_agent再起動\n最終チェック: {age_hours:.0f}時間前"
                                   if restarted else
                                   f"\n⚠️ Q&Aモニター停止\n最終チェック: {age_hours:.0f}時間前\n再起動失敗。手動確認してください")
                            send_line_notify(msg)
                            self.memory.set_state(state_key, datetime.now().isoformat())
            except Exception as e:
                logger.debug(f"Q&A state check error: {e}")

        # local_agent.py の生存確認（プロセス存在チェック → ログ更新時刻はフォールバック）
        try:
            import time
            agent_alive = False
            try:
                result = subprocess.run(
                    ["launchctl", "list", "com.linebot.localagent"],
                    capture_output=True, text=True, timeout=5
                )
                # launchctl list が成功 & PID が数字ならプロセス生存
                if result.returncode == 0 and result.stdout.strip():
                    parts = result.stdout.strip().split()
                    agent_alive = parts[0].isdigit() if parts else False
            except Exception:
                pass

            if not agent_alive:
                logger.warning("local_agent process not found via launchctl — attempting auto-restart")
                plist = os.path.expanduser("~/Library/LaunchAgents/com.linebot.localagent.plist")
                restarted = False
                if os.path.exists(plist):
                    try:
                        subprocess.run(["launchctl", "unload", plist], capture_output=True, timeout=5)
                        import asyncio; await asyncio.sleep(2)
                        subprocess.run(["launchctl", "load", plist], capture_output=True, timeout=5)
                        restarted = True
                        logger.info("local_agent auto-restarted via launchctl")
                    except Exception as re_err:
                        logger.error(f"local_agent restart failed: {re_err}")

                state_key = "local_agent_stale_notified"
                last_n = self.memory.get_state(state_key)
                if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 3600:
                    if restarted:
                        send_line_notify(
                            "\n🔄 local_agent 自動再起動\nプロセス停止を検知→自動で再起動しました"
                        )
                    else:
                        send_line_notify(
                            "\n⚠️ local_agent 停止\nプロセスが見つかりません\n"
                            "自動再起動にも失敗。手動で確認してください"
                        )
                    self.memory.set_state(state_key, datetime.now().isoformat())
        except Exception as e:
            logger.debug(f"local_agent check error: {e}")

        # KPIキャッシュ鮮度チェック（48時間超で警告）
        kpi_cache = os.path.expanduser("~/agents/System/data/kpi_summary.json")
        if os.path.exists(kpi_cache):
            try:
                import time
                cache_age_hours = (time.time() - os.path.getmtime(kpi_cache)) / 3600
                if cache_age_hours > 48:
                    state_key = "kpi_cache_stale_notified"
                    last_n = self.memory.get_state(state_key)
                    if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 21600:  # 6時間に1回
                        send_line_notify(
                            f"⚠️ KPIキャッシュ未更新\n"
                            f"最終更新: {cache_age_hours:.0f}時間前\n"
                            f"AI秘書のKPIデータが古くなっています"
                        )
                        self.memory.set_state(state_key, datetime.now().isoformat())
            except Exception as e:
                logger.debug(f"KPI cache check error: {e}")

        # ディスク使用率チェック（90%超で警告）
        try:
            import shutil
            usage = shutil.disk_usage(os.path.expanduser("~"))
            used_pct = usage.used / usage.total * 100
            if used_pct > 90:
                state_key = "disk_critical_notified"
                last_n = self.memory.get_state(state_key)
                if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 21600:
                    free_gb = usage.free / (1024**3)
                    send_line_notify(
                        f"⚠️ Mac Mini ディスク残量警告\n"
                        f"使用率: {used_pct:.1f}% / 残り: {free_gb:.1f}GB\n"
                        f"ログ・キャッシュの整理が必要です"
                    )
                    self.memory.set_state(state_key, datetime.now().isoformat())
        except Exception as e:
            logger.debug(f"Disk check error: {e}")

        # Orchestratorクラッシュループ検知（起動から5分以内の再チェックが短時間に繰り返される）
        try:
            uptime_key = "orchestrator_boot_time"
            boot_time = self.memory.get_state(uptime_key)
            now = datetime.now()
            if not boot_time:
                self.memory.set_state(uptime_key, now.isoformat())
            else:
                boot_dt = datetime.fromisoformat(boot_time)
                uptime_min = (now - boot_dt).total_seconds() / 60
                # 起動5分以内にhealth_checkが走る＝再起動直後
                if uptime_min < 5:
                    crash_key = "orchestrator_recent_boots"
                    recent = int(self.memory.get_state(crash_key) or "0") + 1
                    self.memory.set_state(crash_key, str(recent))
                    if recent >= 3:
                        state_key = "crash_loop_notified"
                        last_n = self.memory.get_state(state_key)
                        if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 3600:
                            send_line_notify(
                                f"🚨 Orchestratorクラッシュループ検知\n"
                                f"短時間に{recent}回再起動しています\n"
                                f"ログを確認してください"
                            )
                            self.memory.set_state(state_key, datetime.now().isoformat())
                elif uptime_min > 10:
                    # 安定稼働中 → カウンタリセット
                    self.memory.set_state("orchestrator_recent_boots", "0")
        except Exception as e:
            logger.debug(f"Crash loop check error: {e}")

        running_jobs = len(self.scheduler.get_jobs())
        self.memory.set_state("health_status", "ok")
        self.memory.set_state("running_jobs", str(running_jobs))
        logger.debug(f"Health check OK: {running_jobs} jobs scheduled, {api_calls} API calls/hour")

    async def _run_weekly_idea_proposal(self):
        """毎週月曜: agent_ideas.md から未着手P0/P1を1件ピックアップしてLINE通知"""
        from .notifier import send_line_notify

        ideas_path = os.path.expanduser(
            os.path.join(self.config.get("paths", {}).get("repo_root", "~/Desktop/cursor"),
                         "System/mac_mini/agent_ideas.md")
        )
        if not os.path.exists(ideas_path):
            logger.warning("agent_ideas.md not found")
            return

        with open(ideas_path, encoding="utf-8") as f:
            content = f.read()

        # P0・P1セクションから最初の未着手アイテムを取得
        current_priority = ""
        candidate = None
        for line in content.splitlines():
            if re.match(r"^## 🔴 P0", line):
                current_priority = "P0"
            elif re.match(r"^## 🟠 P1", line):
                current_priority = "P1"
            elif re.match(r"^## 🟡 P2", line):
                break  # P0/P1だけ対象

            m = re.match(r"^- \[ \] (.+)", line)
            if m and current_priority in ("P0", "P1"):
                candidate = (current_priority, m.group(1).strip())
                break

        if not candidate:
            logger.info("No pending P0/P1 ideas found")
            return

        priority, task_text = candidate
        # 説明行（*根拠*）があれば取得
        reason = ""
        lines = content.splitlines()
        for i, line in enumerate(lines):
            if task_text in line and i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith("- *根拠*"):
                    reason = "\n" + next_line
                break

        message = (
            f"\n💡 今週のおすすめタスク（{priority}）\n"
            f"━━━━━━━━━━━━\n"
            f"{task_text}{reason}\n"
            f"━━━━━━━━━━━━\n"
            f"→ agent_ideas.md で管理中"
        )
        task_id = self.memory.log_task_start("weekly_idea_proposal")
        ok = send_line_notify(message)
        self.memory.log_task_end(task_id, "success" if ok else "error",
                                 result_summary=task_text[:100])
        logger.info(f"Weekly idea proposal sent: {task_text[:80]}")

    async def _run_daily_addness_digest(self):
        """毎朝8:30: actionable-tasks.md（タスク）+ カレンダー（今日の予定）をLINE通知"""
        from .notifier import send_line_notify  # LINEのみ
        from datetime import date

        master_dir = self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        actionable_path = os.path.expanduser(os.path.join(master_dir, "addness", "actionable-tasks.md"))
        goal_tree_path = os.path.expanduser(os.path.join(master_dir, "addness", "goal-tree.md"))

        # actionable-tasks.md を優先使用、なければ旧方式 goal-tree にフォールバック
        if os.path.exists(actionable_path):
            await self._digest_from_actionable(actionable_path, send_line_notify)
        elif os.path.exists(goal_tree_path):
            await self._digest_from_goal_tree(goal_tree_path, send_line_notify)
        else:
            logger.warning("Neither actionable-tasks.md nor addness-goal-tree.md found")

        # 今日のカレンダーを別メッセージで通知（独立して動作）
        await self._notify_today_calendar(send_line_notify)

        # 特殊な締め切り・リマインダーチェック（90/30/7日前に通知）
        await self._check_special_reminders(send_line_notify)

    async def _notify_today_calendar(self, send_line_notify):
        """今日のカレンダー予定をLINE通知（予定がなければスキップ）"""
        import json as _json
        from datetime import date
        try:
            result = tools.calendar_list(account="personal", days=1)
            if not result.success or not result.output or "予定はありません" in result.output:
                return

            today_str = date.today().strftime("%Y/%m/%d")
            # people-profiles.json を読み込んで名前→プロファイルの辞書を作成
            master_dir = os.path.expanduser(
                self.config.get("paths", {}).get("master_dir", "~/agents/Master")
            )
            profiles_path = os.path.join(master_dir, "people", "profiles.json")
            profiles = {}
            try:
                if os.path.exists(profiles_path):
                    with open(profiles_path, encoding="utf-8") as pf:
                        raw = _json.load(pf)
                    for key, val in raw.items():
                        entry = val.get("latest", val)
                        name = entry.get("name", key)
                        email = entry.get("email", "")
                        category = entry.get("category", "")
                        summary = entry.get("capability_summary", "")[:60]
                        profiles[key] = {"name": name, "email": email, "category": category, "summary": summary}
                        if email:
                            profiles[email] = profiles[key]
            except Exception:
                pass

            # カレンダー出力をパース
            # 各行: "  [id] 2026-02-21T10:00:00+09:00 ~ ...  タイトル"
            # 次行: "    参加者: 三上 功太, ..."
            events = []
            lines = result.output.splitlines()
            i = 0
            while i < len(lines):
                line = lines[i]
                m = re.match(r"\s*\[.+?\]\s+(\S+)\s*~\s*\S+\s+(.+)", line)
                if m:
                    dt_str = m.group(1)
                    title = m.group(2).strip()
                    time_part = dt_str.split("T")[1][:5] if "T" in dt_str else "終日"
                    # 次行が参加者行かチェック
                    attendee_info = ""
                    if i + 1 < len(lines) and "参加者:" in lines[i + 1]:
                        att_str = lines[i + 1].split("参加者:", 1)[1].strip()
                        att_names = [a.strip() for a in att_str.split(",")]
                        matched = []
                        for att in att_names[:4]:
                            # emailまたは名前でマッチング
                            prof = profiles.get(att)
                            if not prof:
                                # 部分一致
                                for k, v in profiles.items():
                                    if att in k or att in v.get("name", ""):
                                        prof = v
                                        break
                            if prof and prof.get("category"):
                                matched.append(f"{prof['name']}({prof['category']})")
                            elif att and "@" not in att:
                                matched.append(att)
                        if matched:
                            attendee_info = f" [{', '.join(matched[:3])}]"
                        i += 1  # 参加者行をスキップ
                    events.append(f"  {time_part} {title}{attendee_info}")
                i += 1

            if not events:
                return

            message = (
                f"\n📅 今日の予定 ({today_str})\n"
                "━━━━━━━━━━━━\n"
                + "\n".join(events[:8])
                + "\n━━━━━━━━━━━━"
            )
            ok = send_line_notify(message)
            if ok:
                logger.info(f"Calendar digest sent: {len(events)} events")
            else:
                logger.warning("Calendar digest notification failed")
        except Exception as e:
            logger.debug(f"Calendar digest error: {e}")

    async def _digest_from_actionable(self, path: str, send_line_notify):
        """actionable-tasks.md から日次ダイジェストを生成"""
        from datetime import date
        today_str = date.today().strftime("%Y/%m/%d")

        with open(path, encoding="utf-8") as f:
            content = f.read()

        # データ更新日時の取得
        update_m = re.search(r"更新日時[^\|]*\|\s*(.+)", content)
        data_date = update_m.group(1).strip().rstrip("|").strip() if update_m else "不明"

        # セクション別パース（🔴期限超過 / 🔄実行中）
        overdue_items = []
        in_progress_items = []
        current_section = ""

        for line in content.splitlines():
            if "🔴 期限超過" in line:
                current_section = "overdue"
            elif "🔄 実行中" in line:
                current_section = "in_progress"
            elif re.match(r"^## ", line):
                current_section = "other"

            if current_section == "overdue":
                m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
                if m:
                    title = m.group(1).strip()[:50]
                    # 期限情報を含める
                    deadline_m = re.search(r"期限[：:]\s*(\d{4}/\d{2}/\d{2})", line)
                    if deadline_m:
                        title += f"（期限: {deadline_m.group(1)}）"
                    overdue_items.append(title)

            elif current_section == "in_progress":
                m = re.match(r"^\d+\.\s+\*\*(.+?)\*\*", line)
                if m:
                    in_progress_items.append(m.group(1).strip()[:50])

        if not overdue_items and not in_progress_items:
            logger.info("No urgent Addness tasks for today")
            return

        parts = [f"\n📋 今日のタスク（{today_str}）\n━━━━━━━━━━━━"]
        if overdue_items:
            parts.append(f"🔴 期限超過 ({len(overdue_items)}件):")
            parts.extend(f"  ・{t}" for t in overdue_items[:4])
        if in_progress_items:
            parts.append(f"🔄 実行中:")
            parts.extend(f"  ・{t}" for t in in_progress_items[:3])
        parts.append(f"━━━━━━━━━━━━\n📅 データ: {data_date}")

        message = "\n".join(parts)
        task_id = self.memory.log_task_start("daily_addness_digest")
        ok = send_line_notify(message)
        self.memory.log_task_end(task_id, "success" if ok else "error")
        logger.info(f"Daily digest sent: {len(overdue_items)} overdue, {len(in_progress_items)} in_progress")

    async def _digest_from_goal_tree(self, path: str, send_line_notify):
        """goal-tree.md から日次ダイジェストを生成（fallback）"""
        from datetime import date
        today = date.today()
        today_str = today.strftime("%Y/%m/%d")

        with open(path, encoding="utf-8") as f:
            lines = f.readlines()

        overdue, due_today, due_soon = [], [], []
        for line in lines:
            if "甲原" not in line and "kohara" not in line.lower() and "koa" not in line.lower():
                continue
            m = re.search(r"期限[：:]\s*(\d{4}/\d{2}/\d{2})", line)
            if not m:
                continue
            deadline_str = m.group(1)
            try:
                deadline = date.fromisoformat(deadline_str.replace("/", "-"))
            except ValueError:
                continue
            title_m = re.search(r"\*\*(.+?)\*\*", line)
            title = title_m.group(1) if title_m else line.strip()[:60]
            delta = (deadline - today).days
            if delta < 0:
                overdue.append(f"🔴 {title}（{deadline_str}）")
            elif delta == 0:
                due_today.append(f"🟡 {title}（本日期限）")
            elif delta <= 7:
                due_soon.append(f"🟠 {title}（残{delta}日）")

        if not overdue and not due_today and not due_soon:
            logger.info("No urgent Addness goals for today")
            return

        parts = [f"\n📋 Addness 日次ダイジェスト（{today_str}）\n━━━━━━━━━━━━"]
        if overdue:
            parts.append("【期限超過】\n" + "\n".join(overdue[:5]))
        if due_today:
            parts.append("【本日期限】\n" + "\n".join(due_today[:3]))
        if due_soon:
            parts.append("【今週期限】\n" + "\n".join(due_soon[:5]))
        parts.append("━━━━━━━━━━━━")

        task_id = self.memory.log_task_start("daily_addness_digest")
        ok = send_line_notify("\n".join(parts))
        self.memory.log_task_end(task_id, "success" if ok else "error")
        logger.info("Daily Addness digest sent (from goal tree)")

    async def _run_render_health_check(self):
        """Renderサーバーの死活監視（30分ごと）"""
        import json as _json
        import urllib.request
        from .notifier import send_line_notify

        server_url = os.environ.get("LINE_BOT_SERVER_URL", "https://line-mention-bot-mmzu.onrender.com")
        try:
            req = urllib.request.Request(server_url + "/", headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                if resp.status == 200:
                    self.memory.set_state("render_last_ok", datetime.now().isoformat())
                    logger.debug(f"Render health OK: {body[:100]}")
                    return
                else:
                    raise Exception(f"HTTP {resp.status}")
        except Exception as e:
            err_str = str(e)[:150]
            logger.warning(f"Render health check failed: {err_str}")

            # 直近30分以内に通知済みならスキップ
            last_notified = self.memory.get_state("render_health_notified")
            if last_notified:
                try:
                    if (datetime.now() - datetime.fromisoformat(last_notified)).total_seconds() < 1800:
                        return
                except (ValueError, TypeError):
                    pass

            ok = send_line_notify(
                f"\n⚠️ Renderサーバー応答なし\n{server_url}\n\nエラー: {err_str}\n"
                f"LINE秘書が応答できていない可能性があります"
            )
            if ok:
                self.memory.set_state("render_health_notified", datetime.now().isoformat())

    async def _run_anthropic_credit_check(self):
        """Anthropic APIクレジット残高チェック（1日3回）

        極小のAPIコールを試行し、クレジット不足エラーを検知したらLINE通知。
        """
        import json as _json
        import urllib.request
        from .notifier import send_line_notify

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set, skipping credit check")
            return

        try:
            payload = _json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1,
                "messages": [{"role": "user", "content": "hi"}],
            }).encode()
            req = urllib.request.Request(
                "https://api.anthropic.com/v1/messages",
                data=payload,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
            logger.info("Anthropic credit check OK")
            # 復旧通知（前回エラーだった場合）
            if self.memory.get_state("anthropic_credit_alert_active"):
                send_line_notify("\n✅ Anthropic APIクレジットが復旧しました")
                self.memory.set_state("anthropic_credit_alert_active", "")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if "credit balance" in body.lower():
                # 重複通知抑制（6時間以内）
                last_notified = self.memory.get_state("anthropic_credit_notified")
                if last_notified:
                    try:
                        if (datetime.now() - datetime.fromisoformat(last_notified)).total_seconds() < 21600:
                            return
                    except (ValueError, TypeError):
                        pass

                send_line_notify(
                    "\n⚠️ Anthropic APIクレジット不足\n"
                    "秘書のLINE応答が停止しています。\n"
                    "Claude Console → Billing でクレジットを追加してください。\n"
                    "https://console.anthropic.com/settings/billing"
                )
                self.memory.set_state("anthropic_credit_notified", datetime.now().isoformat())
                self.memory.set_state("anthropic_credit_alert_active", "true")
                logger.warning("Anthropic credit balance too low — LINE notified")
            else:
                logger.warning(f"Anthropic credit check HTTP error: {e.code} {body[:200]}")
        except Exception as e:
            logger.warning(f"Anthropic credit check error: {e}")

    async def _run_oauth_health_check(self):
        """Google OAuthトークンの有効性チェック（日次）"""
        import json
        from .notifier import send_line_notify

        token_path = os.path.expanduser("~/agents/token.json")

        # token.jsonの存在確認
        if not os.path.exists(token_path):
            send_line_notify(
                "\n⚠️ OAuth警告\ntoken.jsonが見つかりません\n"
                "Q&A監視・メール・カレンダーが動作していない可能性があります\n"
                "MacBookから再セットアップが必要です"
            )
            logger.error("token.json not found")
            return

        # refresh_tokenの存在確認
        try:
            with open(token_path) as f:
                token_data = json.load(f)
        except Exception as e:
            send_line_notify(f"\n⚠️ OAuth警告\ntoken.json読み込みエラー: {str(e)[:150]}")
            logger.error(f"Failed to read token.json: {e}")
            return

        if not token_data.get("refresh_token"):
            send_line_notify(
                "\n⚠️ OAuth警告\nrefresh_tokenが存在しません\n再認証が必要です"
            )
            logger.error("No refresh_token in token.json")
            return

        # 実際にGoogle APIを呼び出して認証が通るか確認
        result = await self._execute_tool("oauth_health_check", tools.qa_stats)
        if not result.success:
            err_lower = (result.error or "").lower()
            auth_keywords = ["auth", "token", "credential", "403", "401", "permission", "access"]
            if any(k in err_lower for k in auth_keywords):
                send_line_notify(
                    f"\n⚠️ Google OAuth エラー\nGoogle API認証に失敗しました\n"
                    f"MacBookで再認証が必要な場合があります\n\nエラー:\n{result.error[:200]}"
                )
                logger.error(f"OAuth health check: auth error: {result.error[:200]}")
            else:
                logger.info(f"OAuth health check: QA stats failed (non-auth): {result.error[:100]}")
        else:
            logger.info("OAuth health check OK")

        # Claude Code OAuth トークンもチェック（日報自動入力に必要）
        from pathlib import Path
        secretary_config = Path.home() / ".claude-secretary"
        if secretary_config.exists():
            oauth_ok, oauth_err = self._refresh_claude_oauth(secretary_config)
            if oauth_ok:
                logger.info("Claude Code OAuth health check OK")
            else:
                send_line_notify(
                    f"\n⚠️ Claude Code OAuth 警告\n{oauth_err}\n"
                    f"日報自動入力（08:40）が失敗する可能性があります"
                )
                logger.error(f"Claude Code OAuth health check failed: {oauth_err}")

    async def _run_weekly_stats(self):
        """毎週月曜9:30: 先週のシステム稼働サマリーをLINE通知"""
        import json as _json
        from .notifier import send_line_notify  # LINEのみ
        from datetime import date

        stats = self.memory.get_task_stats(since_hours=168)  # 7日間
        total = sum(sum(v.values()) for v in stats.values())
        success = sum(v.get("success", 0) for v in stats.values())
        error = sum(v.get("error", 0) for v in stats.values())
        success_rate = round(100 * success / total) if total > 0 else 0
        error_tasks = [name for name, s in stats.items() if s.get("error", 0) > 0]

        # Q&A通知済み件数
        qa_state_path = os.path.expanduser("~/agents/line_bot_local/qa_monitor_state.json")
        qa_count = 0
        if os.path.exists(qa_state_path):
            try:
                with open(qa_state_path) as f:
                    qa_count = len(_json.load(f).get("sent_ids", []))
            except Exception:
                pass

        # Addnessデータ鮮度
        actionable_path = os.path.expanduser(
            os.path.join(self.config.get("paths", {}).get("master_dir", "~/agents/Master"),
                         "addness", "actionable-tasks.md")
        )
        data_age_note = ""
        if os.path.exists(actionable_path):
            import time
            age_days = (time.time() - os.path.getmtime(actionable_path)) / 86400
            if age_days > 3:
                data_age_note = f"\n⚠️ Addnessデータ: {age_days:.0f}日前（要更新）"

        parts = [
            f"\n📊 週次サマリー ({date.today().strftime('%m/%d')})",
            "━━━━━━━━━━━━",
            f"タスク実行: {success}/{total}件成功 ({success_rate}%)",
            f"Q&A通知済み: {qa_count}件累計",
        ]
        if error_tasks:
            parts.append(f"⚠️ エラー: {', '.join(error_tasks[:4])}")
        if data_age_note:
            parts.append(data_age_note)
        parts.append("━━━━━━━━━━━━")

        ok = send_line_notify("\n".join(parts))
        logger.info(f"Weekly stats sent: {total} tasks, {success_rate}% success, {qa_count} Q&As")

        # 今週のボトルネック分析（actionable-tasks.md から Claude で分析）
        await self._notify_weekly_bottleneck(send_line_notify)

        # フォローアップ提案（contact_state.json から長期未接触の人を検出）
        await self._check_follow_up_suggestions(send_line_notify)

    async def _notify_weekly_bottleneck(self, send_line_notify):
        """今週のボトルネックをClaudeで分析してLINE通知"""
        import anthropic as _anthropic
        from datetime import date

        master_dir = self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        actionable_path = os.path.expanduser(os.path.join(master_dir, "addness", "actionable-tasks.md"))
        if not os.path.exists(actionable_path):
            return

        try:
            with open(actionable_path, encoding="utf-8") as f:
                content = f.read()[:3000]
        except Exception:
            return

        try:
            client = _anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                system="あなたはスキルプラス事業の戦略アドバイザーです。簡潔に要点を伝えてください。",
                messages=[{"role": "user", "content": f"""以下のAddnessタスク状況を分析し、
今週の最大のボトルネックを1〜2件特定してください。

【タスク状況】
{content}

【出力形式（200文字以内）】
🔍 今週のボトルネック:
・[最重要課題] 〜 理由を1行で
・[次点] 〜 理由を1行で（あれば）

具体的で行動につながる内容にしてください。"""}]
            )
            analysis = response.content[0].text.strip()
            ok = send_line_notify(
                f"\n{analysis}\n"
                f"━━━━━━━━━━━━"
            )
            if ok:
                logger.info("Weekly bottleneck analysis sent")
        except Exception as e:
            logger.debug(f"Weekly bottleneck analysis error: {e}")

    async def _run_weekly_content_suggestions(self):
        """毎週水曜10:00: 最新AIニュースを分析してスキルプラスのコンテンツ更新提案をLINE通知"""
        from .notifier import send_line_notify
        from datetime import date
        import anthropic as _anthropic

        today_str = date.today().strftime("%Y/%m/%d")

        # ai_news.log から最新ニュースを取得（直近50行）
        news_log = os.path.expanduser("~/agents/System/ai_news.log")
        news_content = ""
        if os.path.exists(news_log):
            try:
                with open(news_log, encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                # 直近50行（最新ニュース）
                news_content = "".join(lines[-50:])[:2000]
            except Exception:
                pass

        if not news_content:
            logger.debug("weekly_content_suggestions: ai_news.log not found or empty")
            return

        try:
            _content_exec_rules = _build_execution_rules_compact()
            client = _anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system="あなたはスキルプラス（AI副業教育コース）のコンテンツディレクターです。" + _content_exec_rules,
                messages=[{"role": "user", "content": f"""以下の最新AIニュースを踏まえて、スキルプラスのカリキュラム・教材の更新提案をしてください。

【最新AIニュース（直近）】
{news_content}

【出力形式】（400文字以内・LINEで読みやすい形式）
📚 コンテンツ更新提案 ({today_str})

更新優先度が高いもの（2〜3件）:
1. [セクション/教材名]: [追加・修正内容を1行で]
   → 理由: [そのニュースとの関連を1行で]

受講生にとって今すぐ価値がある内容にしてください。"""}]
            )
            suggestions = response.content[0].text.strip()
            message = (
                f"\n{suggestions}\n"
                f"━━━━━━━━━━━━\n"
                f"💡 詳細はCursorで展開できます"
            )
            task_id = self.memory.log_task_start("weekly_content_suggestions")
            ok = send_line_notify(message)
            self.memory.log_task_end(task_id, "success" if ok else "error",
                                     result_summary=suggestions[:100])
            logger.info("Weekly content suggestions sent")
        except Exception as e:
            logger.error(f"Weekly content suggestions failed: {e}")

    async def _check_follow_up_suggestions(self, send_line_notify):
        """長期未接触の人をpeople-profiles.jsonとcontact_state.jsonで検出しLINE通知"""
        import json as _json
        from datetime import datetime as _dt, timedelta

        contact_state_path = os.path.expanduser("~/agents/line_bot_local/contact_state.json")
        profiles_path = os.path.expanduser(
            os.path.join(self.config.get("paths", {}).get("master_dir", "~/agents/Master"),
                         "people", "profiles.json")
        )
        if not os.path.exists(contact_state_path) or not os.path.exists(profiles_path):
            logger.debug("Follow-up check: missing contact_state.json or people/profiles.json")
            return

        try:
            with open(contact_state_path, encoding="utf-8") as f:
                contact_state = _json.load(f)
            with open(profiles_path, encoding="utf-8") as f:
                profiles = _json.load(f)
        except Exception as e:
            logger.debug(f"Follow-up check: load error: {e}")
            return

        now = _dt.now()
        # カテゴリ別閾値（日数）
        THRESHOLDS = {
            "上司": 30,
            "横（並列）": 21,
            "直下メンバー": 14,
            "メンバー": 14,
        }
        suggestions = []
        for key, val in profiles.items():
            entry = val.get("latest", val)
            name = entry.get("name", key)
            category = entry.get("category", "")
            threshold_days = THRESHOLDS.get(category)
            if not threshold_days:
                continue  # 閾値未定義のカテゴリはスキップ
            last_contact_str = contact_state.get(name)
            if not last_contact_str:
                continue  # 接触記録なし（初回は提案しない）
            try:
                last_contact = _dt.fromisoformat(last_contact_str)
                days_since = (now - last_contact).days
                if days_since >= threshold_days:
                    suggestions.append((days_since, name, category))
            except (ValueError, TypeError):
                pass

        if not suggestions:
            logger.debug("Follow-up check: no overdue contacts")
            return

        # 最も古い順で最大5件
        suggestions.sort(reverse=True)
        parts = [f"\n💬 フォローアップ提案\n━━━━━━━━━━━━"]
        for days, name, category in suggestions[:5]:
            parts.append(f"  {name}({category}) — {days}日未連絡")
        parts.append("━━━━━━━━━━━━")

        ok = send_line_notify("\n".join(parts))
        logger.info(f"Follow-up suggestions sent: {len(suggestions[:5])} people")

    async def _check_special_reminders(self, send_line_notify):
        """ハードコードされた重要期限のリマインダー（90/30/7日前に通知）"""
        from datetime import date
        today = date.today()

        # 重要な特殊期限リスト: (日付, ラベル, 詳細)
        SPECIAL_DEADLINES = [
            (date(2026, 8, 31), "東北大学研究コラボ", "研究プロジェクト期限。進捗確認・論文準備が必要です。"),
        ]

        for deadline, label, detail in SPECIAL_DEADLINES:
            delta = (deadline - today).days
            if delta < 0:
                continue  # 超過済みはスキップ
            if delta not in (90, 30, 7, 3, 1):
                continue  # 通知対象日のみ

            urgency = "🔴" if delta <= 7 else "🟠" if delta <= 30 else "🟡"
            ok = send_line_notify(
                f"\n{urgency} リマインダー: {label}\n"
                f"━━━━━━━━━━━━\n"
                f"期限: {deadline.strftime('%Y/%m/%d')} (残{delta}日)\n"
                f"{detail}\n"
                f"━━━━━━━━━━━━"
            )
            if ok:
                logger.info(f"Special reminder sent: {label} in {delta} days")

    async def _run_looker_csv_download(self):
        """毎日11:30: Looker Studio CSVダウンロード（前々日分）。秘書がClaude Code + Chrome MCPで実行。"""
        from pathlib import Path
        from datetime import date, timedelta
        from .notifier import send_line_notify

        logger.info("Looker CSV ダウンロード: 開始")

        # プリフライトチェック（Chrome 自動起動含む）
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"Looker CSV ダウンロード: プリフライト失敗 - {preflight_err}")
            send_line_notify(f"⚠️ Looker CSVダウンロード失敗\n{preflight_err}")
            return

        target_date = date.today() - timedelta(days=2)
        target_str = target_date.strftime("%Y-%m-%d")
        csv_filename = f"{target_str}_アドネス全体数値_媒体・ファネル別データ_表.csv"
        csv_dir = Path.home() / "Desktop" / "Looker Studio CSV"
        csv_dir.mkdir(parents=True, exist_ok=True)

        # 既にCSVが存在する場合はスキップ
        csv_path = csv_dir / csv_filename
        if csv_path.exists() and csv_path.stat().st_size > 100:
            logger.info(f"Looker CSV ダウンロード: {csv_filename} は既に存在 → スキップ")
            # シート同期だけ実行（まだ元データに反映されていない可能性があるため）
            await self._run_csv_sheet_sync_after_download(project_root)
            return

        prompt = f"""あなたは甲原海人のAI秘書です。Looker StudioからCSVをダウンロードしてください。

## タスク
{target_date.strftime('%Y年%m月%d日')}（前々日）のLooker Studio CSVをダウンロードする。

## 手順

### Step 1: Looker Studio を開く
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dsqvinv6zd
- ページ名: 媒体・ファネル別データ
- ブラウザで開いて読み込み完了を待つ

### Step 2: 日付フィルターを変更
- ページ上部の日付フィルターをクリック
- 詳細設定で開始日・終了日を両方「{target_str}」に設定
- 適用をクリック

### Step 3: CSVエクスポート
- テーブルを右クリック → 「グラフをエクスポート」または「データのエクスポート」を選択
- CSV形式を選択
- 「エクスポート」をクリック
- ダウンロード完了を待つ

### Step 4: ファイル移動・リネーム
- ダウンロードされたファイル（~/Downloads/ に保存される）を以下に移動:
```bash
mkdir -p "{csv_dir}"
# ダウンロードされたCSVファイルを特定して移動
latest_csv=$(ls -t ~/Downloads/*.csv 2>/dev/null | head -1)
if [ -n "$latest_csv" ]; then
    mv "$latest_csv" "{csv_dir}/{csv_filename}"
    echo "移動完了: {csv_dir}/{csv_filename}"
else
    echo "CSVファイルが見つかりません"
fi
```

### Step 5: 確認
```bash
ls -la "{csv_dir}/{csv_filename}"
head -3 "{csv_dir}/{csv_filename}"
```

## エラー時の対応

### ブラウザ接続エラー
- ブラウザツール（tabs_context_mcp, navigate等）が使えない場合:
  → ===RESULT_START===
  エラー: Chrome MCP に接続できません
  ===RESULT_END===
  と出力して終了

### Googleログイン切れ
- Looker Studio にアクセスした際、ログイン画面が表示された場合:
  → ===RESULT_START===
  エラー: Looker Studio のGoogleログインが切れています
  ===RESULT_END===
  と出力して終了

### ダウンロード失敗
- CSVエクスポートボタンが見つからない場合:
  → スクショを撮影して画面状態をログに記録
  → テーブル上のメニューアイコンやShift+右クリックなど代替手段を試す

## 出力形式
===RESULT_START===
（ダウンロード結果: ファイルパス・行数。エラーならエラー内容を明記）
===RESULT_END==="""

        success, output, error = self._execute_claude_code_task(
            "Looker CSVダウンロード", claude_cmd, secretary_config, project_root,
            prompt, max_turns=25, timeout=480, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_looker_csv_download", datetime.now().isoformat())
            if "===RESULT_START===" in output and "===RESULT_END===" in output:
                report = output.split("===RESULT_START===")[1].split("===RESULT_END===")[0].strip()
                logger.info(f"Looker CSV ダウンロード: 完了 - {report[:300]}")
                if "エラー" in report:
                    send_line_notify(f"⚠️ Looker CSVダウンロード: {report[:300]}")
                else:
                    # ダウンロード成功 → csv_sheet_sync で元データ更新
                    await self._run_csv_sheet_sync_after_download(project_root)
            else:
                logger.info(f"Looker CSV ダウンロード: 完了（マーカーなし）- {output[-300:]}")
                await self._run_csv_sheet_sync_after_download(project_root)
        else:
            send_line_notify(f"⚠️ Looker CSVダウンロード失敗（リトライ後）\n{error}")

    async def _run_csv_sheet_sync_after_download(self, project_root):
        """CSVダウンロード後にcsv_sheet_syncを実行して元データシートを更新する。"""
        import subprocess
        try:
            env = dict(os.environ)
            if "/opt/homebrew/bin" not in env.get("PATH", ""):
                env["PATH"] = f"/opt/homebrew/bin:{env.get('PATH', '')}"
            result = subprocess.run(
                ["python3", "System/csv_sheet_sync.py"],
                capture_output=True, text=True, timeout=120,
                cwd=str(project_root), env=env,
            )
            if result.returncode == 0:
                logger.info(f"csv_sheet_sync 完了: {result.stdout[-200:]}")
            else:
                logger.warning(f"csv_sheet_sync 失敗: {result.stderr[:200]}")
        except Exception as e:
            logger.warning(f"csv_sheet_sync 例外: {e}")

    async def _run_kpi_daily_import(self):
        """毎日12:00: 元データの完了チェック → 投入 or リマインド"""
        from .notifier import send_line_notify
        from datetime import date, timedelta

        target_date = (date.today() - timedelta(days=2)).isoformat()

        # まず完了チェック
        check = await self._execute_tool("kpi_check_today", tools.kpi_check_today)
        if check.success and check.output.startswith("ok:"):
            # 完了 → 日別/月別に投入
            result = await self._execute_tool("kpi_process", tools.kpi_process)
            if result.success and "投入完了" in result.output:
                # KPIキャッシュも再生成（AI秘書が最新データを参照できるように）
                cache_result = await self._execute_tool("kpi_cache_build", tools.kpi_cache_build)
                cache_status = ""
                if cache_result.success:
                    logger.info(f"KPI cache rebuilt after import: {cache_result.output[:200]}")
                else:
                    cache_status = "\n⚠️ KPIキャッシュ再生成に失敗（AI秘書のデータが古い可能性あり）"
                    logger.warning(f"KPI cache build failed after import: {cache_result.error[:200] if cache_result.error else 'unknown'}")
                send_line_notify(
                    f"\n📊 KPIデータ更新完了\n"
                    f"━━━━━━━━━━━━\n"
                    f"{result.output[:200]}{cache_status}\n"
                    f"━━━━━━━━━━━━"
                )
            elif result.success and "投入対象なし" in result.output:
                logger.info(f"KPI process: already up to date for {target_date}")
            else:
                # 投入失敗を通知
                logger.warning(f"KPI process result: {result.output[:200]}")
                send_line_notify(
                    f"\n⚠️ KPIデータ投入エラー\n"
                    f"━━━━━━━━━━━━\n"
                    f"対象日: {target_date}\n"
                    f"{(result.error or result.output or 'unknown')[:200]}\n"
                    f"━━━━━━━━━━━━"
                )
        else:
            # 未完了 → リマインド送信
            status = check.output if check.success else "チェック失敗"
            send_line_notify(
                f"\n⏰ KPIデータ未投入リマインド\n"
                f"━━━━━━━━━━━━\n"
                f"対象日: {target_date}\n"
                f"ステータス: {status}\n"
                f"\n11:30のCSV自動ダウンロードが失敗した可能性があります。ログを確認してください\n"
                f"━━━━━━━━━━━━"
            )
            logger.warning(f"KPI data not ready for {target_date}: {status}")

    async def _run_sheets_sync(self):
        """毎日6:30: 管理シートのCSVキャッシュを更新 → KPIキャッシュも再構築"""
        result = await self._execute_tool("sheets_sync", tools.sheets_sync)
        if result.success:
            logger.info(f"Sheets sync completed: {result.output[:200]}")
            cache_result = await self._execute_tool("kpi_cache_build", tools.kpi_cache_build)
            if cache_result.success:
                logger.info(f"KPI cache rebuilt: {cache_result.output[:200]}")
                from .notifier import send_line_notify
                send_line_notify(f"✅ 管理シート同期+KPIキャッシュ更新完了")
            else:
                logger.warning(f"KPI cache build failed: {cache_result.error[:200] if cache_result.error else 'unknown'}")
                from .notifier import send_line_notify
                send_line_notify(
                    f"⚠️ KPIキャッシュ再生成失敗\n"
                    f"Sheets同期は成功しましたが、キャッシュ生成に失敗しました。\n"
                    f"AI秘書のKPIデータが古い可能性があります。"
                )

    async def _run_kpi_nightly_cache(self):
        """毎晩22:00: KPIキャッシュを再生成（AI秘書が夜間も最新データを参照できるように）"""
        result = await self._execute_tool("kpi_cache_build", tools.kpi_cache_build)
        if result.success:
            logger.info(f"Nightly KPI cache rebuilt: {result.output[:200]}")
        else:
            logger.warning(f"Nightly KPI cache build failed: {result.error[:200] if result.error else 'unknown'}")
            from .notifier import send_line_notify
            send_line_notify(
                f"⚠️ 夜間KPIキャッシュ再生成失敗\n"
                f"{(result.error or 'unknown')[:150]}"
            )

    async def _run_log_rotate(self):
        """毎日3:00: ログローテーション"""
        result = await self._execute_tool("log_rotate", tools.log_rotate)
        if result.success:
            logger.info(f"Log rotate completed: {result.output[:200]}")

    _git_pull_consecutive_failures = 0

    async def _run_git_pull_sync(self):
        result = await self._execute_tool("git_pull_sync", tools.git_pull_sync)
        if result.success:
            if self._git_pull_consecutive_failures >= 6:
                # 復旧通知
                from .notifier import send_line_notify
                send_line_notify(f"✅ Git同期復旧（{self._git_pull_consecutive_failures}回連続失敗後に復旧）")
            self._git_pull_consecutive_failures = 0
        else:
            self._git_pull_consecutive_failures += 1
            # 6回連続失敗（=30分）で初回通知、以降1時間ごと
            if self._git_pull_consecutive_failures == 6 or (self._git_pull_consecutive_failures > 6 and self._git_pull_consecutive_failures % 12 == 0):
                from .notifier import send_line_notify
                send_line_notify(
                    f"⚠️ Git同期 {self._git_pull_consecutive_failures}回連続失敗\n"
                    f"Mac Miniがリポジトリと同期できていません。\n"
                    f"エラー: {(result.error or 'unknown')[:150]}"
                )

    async def _run_daily_group_digest(self):
        """毎日21:00: グループLINEの1日分のメッセージをClaude分析→秘書グループに報告"""
        import json as _json
        import anthropic as _anthropic
        from .notifier import send_line_notify
        from datetime import date

        today_str = date.today().isoformat()
        result = await self._execute_tool("fetch_group_log", tools.fetch_group_log, date=today_str)
        if not result.success or not result.output:
            logger.warning(f"daily_group_digest: failed to fetch group log: {result.error}")
            return

        try:
            data = _json.loads(result.output)
        except _json.JSONDecodeError:
            logger.error("daily_group_digest: invalid JSON from group log")
            return

        groups = data.get("groups", {})
        if not groups:
            logger.info("daily_group_digest: no group messages today")
            return

        # people-profiles.json でユーザー名→プロファイル照合
        master_dir = os.path.expanduser(
            self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        )
        profiles_path = os.path.join(master_dir, "people", "profiles.json")
        profiles = {}
        try:
            if os.path.exists(profiles_path):
                with open(profiles_path, encoding="utf-8") as pf:
                    raw = _json.load(pf)
                for key, val in raw.items():
                    entry = val.get("latest", val)
                    name = entry.get("name", key)
                    category = entry.get("category", "")
                    profiles[name] = category
        except Exception:
            pass

        # グループログをテキスト化（Claude入力用）
        log_lines = []
        total_messages = 0
        for gid, ginfo in groups.items():
            gname = ginfo.get("group_name") or gid[-8:]
            msgs = ginfo.get("messages", [])
            total_messages += len(msgs)
            if not msgs:
                continue
            log_lines.append(f"\n【{gname}】({len(msgs)}件)")
            for m in msgs:
                uname = m.get("user_name", "不明")
                cat = profiles.get(uname, "")
                cat_label = f"({cat})" if cat else ""
                time_part = m.get("timestamp", "")[-8:-3]  # HH:MM
                log_lines.append(f"  [{time_part}] {uname}{cat_label}: {m.get('text', '')[:100]}")

        if total_messages == 0:
            logger.info("daily_group_digest: 0 messages across all groups")
            return

        log_text = "\n".join(log_lines)
        # 入力が長すぎる場合は切り詰め
        if len(log_text) > 4000:
            log_text = log_text[:4000] + "\n...(以下省略)"

        try:
            client = _anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                system=(
                    "あなたはスキルプラス事業のAI秘書です。"
                    "甲原海人（代表・マーケティング責任者）向けに、"
                    "LINEグループの1日の会話を簡潔に報告してください。"
                ),
                messages=[{"role": "user", "content": f"""以下は今日のLINEグループのメッセージログです。
甲原さんが把握すべき内容を簡潔にまとめてください。

{log_text}

【出力形式】（500文字以内・LINEメッセージで読みやすい形式）
グループごとに:
・要約（誰が何について話したか）
・メンバーの活動度やテンション（気になる点があれば）
・甲原さんがアクションすべき事項（あれば）

特に報告すべき内容がないグループは省略してOKです。"""}],
            )
            analysis = response.content[0].text.strip()
        except Exception as e:
            logger.error(f"daily_group_digest: Claude analysis failed: {e}")
            # Claude失敗時は簡易サマリーで代替
            parts = [f"📋 グループ会話ログ ({today_str})"]
            for gid, ginfo in groups.items():
                gname = ginfo.get("group_name") or gid[-8:]
                count = len(ginfo.get("messages", []))
                if count > 0:
                    parts.append(f"  {gname}: {count}件")
            analysis = "\n".join(parts)

        message = (
            f"\n📋 グループLINEダイジェスト ({date.today().strftime('%m/%d')})\n"
            f"━━━━━━━━━━━━\n"
            f"{analysis}\n"
            f"━━━━━━━━━━━━\n"
            f"計{total_messages}件のメッセージ"
        )
        ok = send_line_notify(message)
        if ok:
            logger.info(f"daily_group_digest sent: {total_messages} messages across {len(groups)} groups")
        else:
            logger.warning("daily_group_digest: LINE notification failed")

    async def _run_weekly_profile_learning(self):
        """毎週日曜10:00: 過去7日間のグループログからメンバーの会話を分析→profiles.jsonに書き込み"""
        import json as _json
        import anthropic as _anthropic
        from .notifier import send_line_notify
        from datetime import date, timedelta

        task_id = self.memory.log_task_start("weekly_profile_learning")
        today = date.today()

        # 1. 過去7日間のログを日別取得
        all_messages_by_person = {}  # {person_name: [{"group": ..., "text": ..., "ts": ...}, ...]}
        groups_seen = set()
        for i in range(7):
            target_date = (today - timedelta(days=i)).isoformat()
            result = tools.fetch_group_log(date=target_date)
            if not result.success or not result.output:
                continue
            try:
                data = _json.loads(result.output)
            except _json.JSONDecodeError:
                continue
            for gid, ginfo in data.get("groups", {}).items():
                gname = ginfo.get("group_name") or gid[-8:]
                groups_seen.add(gname)
                for msg in ginfo.get("messages", []):
                    uname = msg.get("user_name", "")
                    if not uname:
                        continue
                    all_messages_by_person.setdefault(uname, []).append({
                        "group": gname,
                        "text": msg.get("text", ""),
                        "ts": msg.get("timestamp", ""),
                    })

        if not all_messages_by_person:
            self.memory.log_task_end(task_id, "success", result_summary="No group messages in past 7 days")
            logger.info("weekly_profile_learning: no messages found")
            return

        # 2. profiles.json を読み込み（LINE表示名→キー名マッチング用）
        master_dir = os.path.expanduser(
            self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        )
        profiles_path = os.path.join(master_dir, "people", "profiles.json")
        profiles = {}
        display_name_map = {}  # line_display_name → profile_key
        try:
            if os.path.exists(profiles_path):
                with open(profiles_path, encoding="utf-8") as pf:
                    profiles = _json.load(pf)
                for key, val in profiles.items():
                    entry = val.get("latest", val)
                    ldn = entry.get("line_display_name", "")
                    name = entry.get("name", key)
                    if ldn:
                        display_name_map[ldn] = key
                    display_name_map[name] = key
                    # 姓のみ・名のみもマッチング候補に
                    for part in name.split():
                        if len(part) >= 2:
                            display_name_map.setdefault(part, key)
        except Exception as e:
            logger.warning(f"weekly_profile_learning: failed to load profiles: {e}")

        # 3. LINE表示名→profileキーのマッチング + 人物ごとにClaude分析
        updated_count = 0
        skipped_count = 0
        updated_details = []  # [(name, msg_count, style, topics), ...]
        try:
            client = _anthropic.Anthropic()
        except Exception as e:
            self.memory.log_task_end(task_id, "error", error_message=f"Anthropic init failed: {e}")
            logger.error(f"weekly_profile_learning: Anthropic client init failed: {e}")
            return

        for display_name, messages in all_messages_by_person.items():
            # 3件未満はスキップ
            if len(messages) < 3:
                skipped_count += 1
                continue

            # profileキーを解決
            profile_key = display_name_map.get(display_name)
            if not profile_key:
                # 部分一致で検索
                for map_name, map_key in display_name_map.items():
                    if display_name in map_name or map_name in display_name:
                        profile_key = map_key
                        break
            if not profile_key:
                skipped_count += 1
                logger.debug(f"weekly_profile_learning: no profile match for '{display_name}'")
                continue

            # メッセージをテキスト化
            active_groups = list(set(m["group"] for m in messages))
            msg_text = "\n".join(
                f"[{m['ts'][-11:-3] if len(m['ts']) > 11 else ''}] ({m['group']}) {m['text'][:150]}"
                for m in messages[:100]  # 最大100メッセージ
            )
            if len(msg_text) > 3000:
                msg_text = msg_text[:3000] + "\n...(以下省略)"

            entry = profiles.get(profile_key, {})
            person_entry = entry.get("latest", entry)
            person_name = person_entry.get("name", profile_key)
            category = person_entry.get("category", "")

            try:
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=400,
                    system="あなたは組織のコミュニケーション分析の専門家です。LINEグループのメッセージから人物の特徴を簡潔に分析してください。",
                    messages=[{"role": "user", "content": f"""以下は{person_name}（{category}）の過去7日間のLINEグループメッセージです。

{msg_text}

以下のJSON形式で分析結果を出力してください（各フィールドは日本語で簡潔に）:
{{
  "communication_style": "コミュニケーションスタイルを1文で（例: 短文中心。カジュアル。絵文字多用。）",
  "recent_topics": ["最近の関心トピック（3〜5個）"],
  "collaboration_patterns": "誰とどんなやり取りが多いか1文で",
  "personality_notes": "性格・行動特性を1文で",
  "activity_level": "high/medium/low のいずれか"
}}

JSON以外の文字は出力しないでください。"""}],
                )
                raw_text = response.content[0].text.strip()
                # JSON部分を抽出（前後にテキストがある場合に対応）
                json_start = raw_text.find("{")
                json_end = raw_text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    analysis = _json.loads(raw_text[json_start:json_end])
                else:
                    logger.warning(f"weekly_profile_learning: non-JSON response for {person_name}")
                    continue

                # group_insightsを構築
                group_insights = {
                    "updated_at": today.isoformat(),
                    "message_count_7d": len(messages),
                    "active_groups": active_groups[:5],
                    "communication_style": analysis.get("communication_style", ""),
                    "recent_topics": analysis.get("recent_topics", []),
                    "collaboration_patterns": analysis.get("collaboration_patterns", ""),
                    "personality_notes": analysis.get("personality_notes", ""),
                    "activity_level": analysis.get("activity_level", "medium"),
                }

                # profiles.jsonに書き込み
                write_result = tools.update_people_profiles(profile_key, group_insights)
                if write_result.success:
                    updated_count += 1
                    updated_details.append((
                        person_name,
                        len(messages),
                        analysis.get("communication_style", ""),
                        analysis.get("recent_topics", []),
                    ))
                    logger.info(f"weekly_profile_learning: updated {person_name} ({len(messages)} msgs)")
                else:
                    logger.warning(f"weekly_profile_learning: write failed for {person_name}: {write_result.error}")

            except Exception as e:
                logger.warning(f"weekly_profile_learning: analysis failed for {person_name}: {e}")
                continue

        # ===== フェーズ2: reply_feedback分析 → style_rules.json 生成 =====
        style_rules_count = 0
        try:
            feedback_path = os.path.join(master_dir, "learning", "reply_feedback.json")
            style_rules_path = os.path.join(master_dir, "learning", "style_rules.json")
            if os.path.exists(feedback_path):
                with open(feedback_path, encoding="utf-8") as ff:
                    all_feedback = _json.load(ff)
                corrections = [f for f in all_feedback if f.get("type") == "correction"]
                if len(corrections) >= 3:
                    fb_text = "\n".join(
                        f"[{i}] 送信者:{c.get('sender_name','')} 受信:「{c.get('original_message','')[:60]}」 "
                        f"AI案:「{c.get('ai_suggested','')[:60]}」 実際:「{c.get('actual_sent','')[:60]}」"
                        for i, c in enumerate(corrections[-20:], 1)
                    )
                    rules_response = client.messages.create(
                        model="claude-haiku-4-5-20251001",
                        max_tokens=600,
                        system="あなたはコミュニケーションスタイル分析の専門家です。修正パターンから再現可能なルールを抽出してください。",
                        messages=[{"role": "user", "content": f"""以下はAI返信案が修正された履歴です。パターンを分析し、再利用できるスタイルルールをJSON配列で出力してください。

{fb_text}

以下のJSON形式で出力（JSON以外の文字は不要）:
[
  {{"rule": "ルールの説明", "confidence": "high/medium", "example": "具体例"}}
]"""}],
                    )
                    raw = rules_response.content[0].text.strip()
                    j_start = raw.find("[")
                    j_end = raw.rfind("]") + 1
                    if j_start >= 0 and j_end > j_start:
                        style_rules = _json.loads(raw[j_start:j_end])
                        style_rules_count = len(style_rules)
                        os.makedirs(os.path.dirname(style_rules_path), exist_ok=True)
                        with open(style_rules_path, "w", encoding="utf-8") as sf:
                            _json.dump(style_rules, sf, ensure_ascii=False, indent=2)
                        logger.info(f"weekly_profile_learning: style_rules generated ({style_rules_count} rules)")
                else:
                    logger.info(f"weekly_profile_learning: skipping style_rules (corrections={len(corrections)}, need>=3)")
        except Exception as e:
            logger.warning(f"weekly_profile_learning: style_rules generation failed: {e}")

        # ===== フェーズ3: comm_profile自動更新 =====
        comm_updated_names = []
        try:
            if os.path.exists(feedback_path):
                with open(feedback_path, encoding="utf-8") as ff:
                    all_feedback = _json.load(ff)
                # 人物ごとに修正パターンを集計
                person_corrections = {}
                for fb in all_feedback:
                    sname = fb.get("sender_name", "")
                    if not sname:
                        continue
                    person_corrections.setdefault(sname, []).append(fb)

                for person_name_fb, person_fbs in person_corrections.items():
                    corrections_for_person = [f for f in person_fbs if f.get("type") == "correction"]
                    if len(corrections_for_person) < 3:
                        continue

                    # profileキーを解決
                    p_key = display_name_map.get(person_name_fb)
                    if not p_key:
                        for mn, mk in display_name_map.items():
                            if person_name_fb in mn or mn in person_name_fb:
                                p_key = mk
                                break
                    if not p_key or p_key not in profiles:
                        continue

                    # 既存comm_profileを取得
                    p_entry = profiles[p_key]
                    p_latest = p_entry.get("latest", p_entry)
                    existing_comm = p_latest.get("comm_profile", {})

                    fb_text_person = "\n".join(
                        f"AI案:「{c.get('ai_suggested','')[:60]}」→実際:「{c.get('actual_sent','')[:60]}」"
                        for c in corrections_for_person[-10:]
                    )
                    # group_insightsも参照
                    gi = p_latest.get("group_insights", {})
                    gi_style = gi.get("communication_style", "")

                    try:
                        comm_response = client.messages.create(
                            model="claude-haiku-4-5-20251001",
                            max_tokens=300,
                            system="あなたはコミュニケーション分析の専門家です。修正パターンからcomm_profileを提案してください。",
                            messages=[{"role": "user", "content": f"""「{person_name_fb}」への返信修正パターンと会話スタイル分析から、comm_profileを更新してください。

修正履歴:
{fb_text_person}

{f'会話スタイル分析: {gi_style}' if gi_style else ''}

現在のcomm_profile: {_json.dumps(existing_comm, ensure_ascii=False) if existing_comm else '未設定'}

以下のJSON形式で更新内容のみ出力（JSON以外の文字は不要）:
{{
  "tone_keywords": ["口調キーワード（3個以内）"],
  "style_note": "この人への返信スタイルを1文で"
}}"""}],
                        )
                        raw_comm = comm_response.content[0].text.strip()
                        j_s = raw_comm.find("{")
                        j_e = raw_comm.rfind("}") + 1
                        if j_s >= 0 and j_e > j_s:
                            comm_updates = _json.loads(raw_comm[j_s:j_e])
                            # comm_profileをマージ更新
                            result = tools.update_people_profiles(
                                p_key, p_latest.get("group_insights", {}),
                                comm_profile_updates=comm_updates
                            )
                            if result.success:
                                comm_updated_names.append(person_name_fb)
                                logger.info(f"weekly_profile_learning: comm_profile updated for {person_name_fb}")
                    except Exception as e:
                        logger.warning(f"weekly_profile_learning: comm_profile update failed for {person_name_fb}: {e}")
        except Exception as e:
            logger.warning(f"weekly_profile_learning: comm_profile phase failed: {e}")

        # 4. 結果をLINE通知
        # 更新された人物の詳細を組み立て
        detail_lines = []
        for name, msg_cnt, style, topics in updated_details:
            topics_str = "、".join(topics[:3]) if topics else ""
            line = f"・{name}（{msg_cnt}件）\n  {style}"
            if topics_str:
                line += f"\n  関心: {topics_str}"
            detail_lines.append(line)
        details_section = "\n".join(detail_lines) if detail_lines else ""

        style_line = f"\nスタイルルール: {style_rules_count}件抽出" if style_rules_count else ""
        comm_line = f"\ncomm_profile更新: {', '.join(comm_updated_names)}" if comm_updated_names else ""
        message = (
            f"\n🧠 週次プロファイル学習完了\n"
            f"━━━━━━━━━━━━\n"
            f"更新: {updated_count}名\n"
            f"{details_section}\n"
            f"\nスキップ: {skipped_count}名\n"
            f"分析対象: {len(all_messages_by_person)}名 / {sum(len(m) for m in all_messages_by_person.values())}メッセージ"
            f"{style_line}{comm_line}\n"
            f"━━━━━━━━━━━━"
        )
        send_line_notify(message)
        self.memory.log_task_end(
            task_id, "success",
            result_summary=f"Updated {updated_count} profiles, skipped {skipped_count}, style_rules={style_rules_count}, comm_updated={len(comm_updated_names)}"
        )
        logger.info(f"weekly_profile_learning completed: {updated_count} updated, {skipped_count} skipped, style_rules={style_rules_count}, comm_updated={len(comm_updated_names)}")

    async def _run_repair_check(self):
        if _repair_agent_ref is None:
            logger.warning("Repair agent not initialized, skipping repair check")
            return

        from .notifier import notify_repair_proposal, notify_error_detected
        from .code_tools import _current_branch, git_show_branch_diff

        task_id = self.memory.log_task_start("repair_check")
        try:
            result = _repair_agent_ref.check_and_repair()
            if result is None:
                self.memory.log_task_end(task_id, "success", result_summary="No new errors")
                return

            if result.get("fixed"):
                branch = _current_branch()
                diff = git_show_branch_diff()
                desc = result.get("description", "auto-fix")
                port = self.config.get("webhook", {}).get("port", 8500)
                notify_repair_proposal(branch, desc, diff.result, f"http://localhost:{port}")
                self.memory.log_task_end(task_id, "success",
                                         result_summary=f"Fix proposed on {branch}")
            else:
                reason = result.get("reason", "unknown")
                self.memory.log_task_end(task_id, "needs_review",
                                         result_summary=f"Could not auto-fix: {reason[:200]}")
        except Exception as e:
            self.memory.log_task_end(task_id, "error", error_message=str(e))
            logger.exception("Repair check failed")

    # ------------------------------------------------------------------ #
    #  Slack #ai-team 監視 → 日向タスクキューへディスパッチ
    # ------------------------------------------------------------------ #

    _slack_dispatch_running = False  # 実行中ガード

    async def _run_slack_dispatch(self):
        """Slack #ai-team を監視し、甲原の指示を日向のタスクキューに書き込む。

        秘書（Orchestrator）がSlackを見張り、日向は呼ばれたら動く構造。
        - stop/resume → 日向の state.json を直接変更 + Slack応答
        - status → 日向の state.json を読んで秘書がSlack応答
        - instruction → hinata_tasks.json にタスク追加
        """
        if self._slack_dispatch_running:
            logger.debug("slack_dispatch: previous run still in progress, skipping")
            return
        self._slack_dispatch_running = True
        try:
            await self._run_slack_dispatch_inner()
        finally:
            self._slack_dispatch_running = False

    async def _run_slack_dispatch_inner(self):
        """slack_dispatch の実処理"""
        import uuid
        from pathlib import Path
        from .slack_reader import fetch_channel_messages
        from .notifier import send_slack_ai_team

        AI_TEAM_CHANNEL = "C0AGLRJ8N3G"
        state_key = "slack_dispatch_last_ts"

        HINATA_DIR = Path(os.path.expanduser("~/agents/System/hinata"))
        HINATA_TASKS = HINATA_DIR / "hinata_tasks.json"
        HINATA_STATE = HINATA_DIR / "state.json"
        HINATA_CONFIG = HINATA_DIR / "config.json"

        last_ts = self.memory.get_state(state_key)

        messages = fetch_channel_messages(AI_TEAM_CHANNEL, oldest=last_ts, limit=30)
        if not messages:
            return

        new_msgs = [m for m in messages if m["ts"] != last_ts]
        if not new_msgs:
            return

        # 最新のタイムスタンプを保存
        latest_ts = new_msgs[-1]["ts"]
        self.memory.set_state(state_key, latest_ts)

        # 甲原からのメッセージだけ抽出
        # bot / Webhook / 秘書・日向自身の投稿を全て除外
        _SELF_PATTERNS = (
            # 秘書の応答パターン
            "日向に伝えました", "了解です！日向", "日向を再開", "日向を一旦止め",
            # 日向の応答パターン（Webhook経由でbot_idが欠落するケース対策）
            "🌅 日向エージェント", "了解です！「", "📊 *", "⚠️ サイクル",
            "⚠️ *自己修復", "🔧 *自己修復", "✅ *自己修復", "❌ *自己修復",
            "再開します！", "🙋 *甲原さんに確認", "👋 日向エージェント停止",
        )
        KOHARA_USER_ID = "U07T5V9J6AM"  # 甲原のSlack user_id
        human_msgs = []
        for m in new_msgs:
            uid = m.get("user_id", "")
            text_preview = m.get("text", "")[:30]
            # bot投稿を除外（user_idがBで始まる or 空）
            if uid.startswith("B") or not uid:
                continue
            # 甲原以外のユーザーは無視（他メンバーの投稿に反応しない）
            if uid != KOHARA_USER_ID:
                continue
            # 秘書・日向自身の投稿パターンを除外（Webhook経由でuser_idが付く場合の対策）
            if any(text_preview.startswith(p) for p in _SELF_PATTERNS):
                continue
            human_msgs.append(m)
        if not human_msgs:
            return

        for msg in human_msgs:
            text = msg.get("text", "").strip()
            if not text:
                continue

            command_type = self._classify_slack_command(text)

            if command_type == "stop":
                # 秘書が直接対応: 日向の state.json に paused=True を書き込む
                self._set_hinata_paused(HINATA_STATE, True)
                # 日向のタスクキューにも stop を入れる（日向側でも認識できるように）
                self._add_hinata_task(HINATA_TASKS, text, msg["ts"], "stop")
                send_slack_ai_team("了解です！日向を一旦止めます。")
                logger.info("slack_dispatch: stop command → hinata paused")

            elif command_type == "status":
                # 秘書が直接対応: 日向の state.json を読んで報告
                status_text = self._read_hinata_status(HINATA_STATE)
                send_slack_ai_team(status_text)
                logger.info("slack_dispatch: status query → replied")

            elif command_type == "resume":
                self._set_hinata_paused(HINATA_STATE, False)
                self._add_hinata_task(HINATA_TASKS, text, msg["ts"], "resume")
                send_slack_ai_team("日向を再開します！")
                logger.info("slack_dispatch: resume command → hinata resumed")

            elif command_type == "mode_change":
                new_mode = self._parse_mode_from_text(text)
                if new_mode is None and "レベルアップ" in text:
                    # 現在のモードの次へ自動昇格
                    import json as _json
                    _cur = {}
                    try:
                        with open(HINATA_CONFIG, "r", encoding="utf-8") as _f:
                            _cur = _json.load(_f)
                    except Exception:
                        pass
                    _mode_order = ["report", "propose", "execute"]
                    _cur_mode = _cur.get("mode", "report")
                    _idx = _mode_order.index(_cur_mode) if _cur_mode in _mode_order else 0
                    if _idx < len(_mode_order) - 1:
                        new_mode = _mode_order[_idx + 1]
                    else:
                        send_slack_ai_team("日向は既に最高レベル（Lv.3 共同経営者型）です！")
                        logger.info("slack_dispatch: mode_change → already max level")
                if new_mode:
                    old_mode = self._set_hinata_mode(HINATA_CONFIG, new_mode)
                    mode_labels = {"report": "Lv.1 従業員型", "propose": "Lv.2 右腕型", "execute": "Lv.3 共同経営者型"}
                    send_slack_ai_team(
                        f"日向のモードを変更しました！\n"
                        f"{mode_labels.get(old_mode, old_mode)} → {mode_labels.get(new_mode, new_mode)}"
                    )
                    logger.info(f"slack_dispatch: mode change {old_mode} → {new_mode}")
                else:
                    send_slack_ai_team(
                        "モード変更: 対象のレベルを指定してください。\n"
                        "例: 「日向 Lv.2」「日向 レベル2」「日向 mode propose」"
                    )

            else:
                # メンションベースのルーティング
                # 日向宛て → 日向タスクキュー、秘書宛て → 秘書が直接応答、なし → スキップ
                HINATA_SLACK_UID = "U0AHJGVDRBJ"
                is_hinata = ("日向" in text or f"<@{HINATA_SLACK_UID}>" in text)
                is_secretary = ("秘書" in text)

                # 秘書優先: 「秘書、日向の状況教えて」→ 秘書に聞いている
                if is_secretary:
                    await self._reply_as_secretary(text, send_slack_ai_team)
                    logger.info(f"slack_dispatch: secretary mention → direct reply")
                elif is_hinata:
                    self._add_hinata_task(HINATA_TASKS, text, msg["ts"], "instruction")
                    send_slack_ai_team(f"日向に伝えました！「{text[:50]}」")
                    logger.info(f"slack_dispatch: instruction → hinata task added")
                else:
                    # メンションなし → 無視（ユーザーは宛先を明示する運用）
                    logger.debug(f"slack_dispatch: no mention target, skipping: {text[:30]}")

    async def _reply_as_secretary(self, user_text: str, send_fn):
        """秘書がSlack上で甲原のメッセージに直接応答する。"""
        import anthropic

        # IDENTITY.md を読み込んで甲原さんらしさを注入
        identity_context = ""
        identity_path = Path.home() / "agents" / "Master" / "self_clone" / "kohara" / "IDENTITY.md"
        try:
            if identity_path.exists():
                identity_context = identity_path.read_text(encoding="utf-8")[:2000]
        except Exception:
            pass

        exec_rules = _build_execution_rules_compact()
        system_prompt = (
            "あなたは甲原海人のAI秘書です。Slackの#ai-teamチャンネルで甲原さんに話しかけられました。\n"
            "秘書として簡潔に回答してください。\n\n"
        )
        if identity_context:
            system_prompt += f"## 甲原海人の言語スタイル定義（必ず従うこと）\n{identity_context}\n\n"
        system_prompt += (
            "## Slack応答ルール\n"
            "- 秘書としての応答。甲原さん本人になりきるのではなく、秘書が甲原さんに返す形\n"
            "- 簡潔に。長くても3-4行\n"
            "- マークダウンの太字（**）は使わない\n"
            "- 「かしこまりました」「承知いたしました」は使わない。「了解です！」「分かりました！」を使う\n"
        )
        system_prompt += exec_rules

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=600,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            )
            reply = response.content[0].text.strip()
            send_fn(reply)
        except Exception as e:
            logger.exception(f"_reply_as_secretary error: {e}")
            send_fn("すみません、、！ちょっとエラーが出てしまいました。もう一度試してもらえますか？")

    @staticmethod
    def _classify_slack_command(text: str) -> str:
        """甲原のメッセージからコマンド種別を判定する。"""
        stop_keywords = ["止まって", "ストップ", "止めて", "待って", "やめて"]
        status_keywords = ["状況は", "どうなってる", "今何してる", "ステータス"]
        resume_keywords = ["再開", "動いて", "始めて", "起きて"]
        mode_keywords = ["レベルアップ", "レベル2", "レベル3", "lv.2", "lv.3", "lv2", "lv3",
                         "mode report", "mode propose", "mode execute",
                         "モード変更", "レベル変更"]

        lower = text.lower()
        if any(kw in lower for kw in stop_keywords):
            return "stop"
        if any(kw in lower for kw in status_keywords):
            return "status"
        if any(kw in lower for kw in resume_keywords):
            return "resume"
        if any(kw in lower for kw in mode_keywords):
            return "mode_change"
        return "instruction"

    @staticmethod
    def _parse_mode_from_text(text: str) -> str | None:
        """テキストから変更先のモードを推定する。"""
        lower = text.lower()
        # 明示的なモード指定
        if "mode report" in lower or "lv.1" in lower or "lv1" in lower or "レベル1" in lower:
            return "report"
        if "mode propose" in lower or "lv.2" in lower or "lv2" in lower or "レベル2" in lower:
            return "propose"
        if "mode execute" in lower or "lv.3" in lower or "lv3" in lower or "レベル3" in lower:
            return "execute"
        # 「レベルアップ」= 現在のモードの次
        if "レベルアップ" in lower:
            return None  # 現在のモードが分からないため、_set_hinata_mode で昇格処理
        return None

    @staticmethod
    def _set_hinata_mode(config_path: Path, new_mode: str) -> str:
        """日向の config.json の mode を変更する。戻り値は変更前のモード。"""
        import json
        config = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        old_mode = config.get("mode", "report")
        config["mode"] = new_mode
        tmp = config_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        tmp.rename(config_path)
        return old_mode

    @staticmethod
    def _set_hinata_paused(state_path: Path, paused: bool):
        """日向の state.json の paused フラグを変更する。"""
        import json
        state = {}
        if state_path.exists():
            try:
                with open(state_path, "r", encoding="utf-8") as f:
                    state = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        state["paused"] = paused
        tmp = state_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.rename(state_path)

    @staticmethod
    def _read_hinata_status(state_path: Path) -> str:
        """日向の state.json を読んで状況テキストを返す。"""
        import json
        if not state_path.exists():
            return "*日向の状況*\nstate.json が見つかりません。エージェントが起動していない可能性があります。"
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
        except (json.JSONDecodeError, IOError):
            return "*日向の状況*\nstate.json の読み込みに失敗しました。"

        cycle = state.get("cycle_count", 0)
        last_action = state.get("last_action", "まだ実行していません")
        last_cycle = state.get("last_cycle", "なし")
        paused = state.get("paused", False)
        status_emoji = "⏸️ 一時停止中" if paused else "▶️ 稼働中"

        return (
            f"*日向の状況報告*\n\n"
            f"状態: {status_emoji}\n"
            f"サイクル数: {cycle}\n"
            f"最後のアクション: {last_action}\n"
            f"最終実行: {last_cycle}"
        )

    @staticmethod
    def _add_hinata_task(tasks_path: Path, instruction: str, slack_ts: str, command_type: str):
        """日向のタスクキューにタスクを追加する。"""
        import json
        import uuid

        tasks = []
        if tasks_path.exists():
            try:
                with open(tasks_path, "r", encoding="utf-8") as f:
                    tasks = json.load(f)
            except (json.JSONDecodeError, IOError):
                tasks = []

        task = {
            "id": str(uuid.uuid4())[:8],
            "instruction": instruction,
            "command_type": command_type,
            "source": "slack",
            "slack_ts": slack_ts,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
        }
        tasks.append(task)

        tmp = tasks_path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(tasks, f, ensure_ascii=False, indent=2)
        tmp.rename(tasks_path)

    async def _run_slack_ai_team_check(self):
        """定期チェック: Slack #ai-team の新着メッセージを読み取り→LINEに転送"""
        from .slack_reader import fetch_channel_messages
        from .notifier import send_line_notify

        AI_TEAM_CHANNEL = "C0AGLRJ8N3G"
        state_key = "slack_ai_team_last_ts"
        last_ts = self.memory.get_state(state_key)

        messages = fetch_channel_messages(
            AI_TEAM_CHANNEL,
            oldest=last_ts,
            limit=30,
        )

        if not messages:
            logger.debug("slack_ai_team_check: no new messages")
            return

        # AI Secretary自身のメッセージは除外
        new_msgs = [m for m in messages if m["ts"] != last_ts]
        if not new_msgs:
            return

        # 最新のタイムスタンプを保存
        latest_ts = new_msgs[-1]["ts"]
        self.memory.set_state(state_key, latest_ts)

        # bot自身の投稿（AI Secretary / webhook経由）は除外
        human_msgs = [m for m in new_msgs if not m.get("user_id", "").startswith("B")]
        if not human_msgs:
            logger.debug("slack_ai_team_check: only bot messages, skipping LINE forward")
            return

        # LINEに転送
        lines = [f"\n💬 Slack #ai-team 新着 ({len(human_msgs)}件)\n━━━━━━━━━━━━"]
        for msg in human_msgs[:10]:
            text_preview = msg["text"][:100]
            lines.append(f"[{msg['datetime']}] {msg['user']}: {text_preview}")
        lines.append("━━━━━━━━━━━━")

        ok = send_line_notify("\n".join(lines))
        if ok:
            logger.info(f"Slack #ai-team: forwarded {len(human_msgs)} messages to LINE")
        else:
            logger.warning("Slack #ai-team: LINE forward failed")

    async def _run_hinata_activity_check(self):
        """日向の活動チェック（毎日夜）— 新人の様子を見る先輩の感覚"""
        import time
        from .slack_reader import fetch_channel_messages
        from .notifier import send_line_notify

        # 日向の Slack ユーザーID（参加後に設定）
        hinata_user_id = self.memory.get_state("hinata_slack_user_id")
        if not hinata_user_id:
            logger.debug("hinata_activity_check: hinata_slack_user_id not set, skipping")
            return

        AI_TEAM_CHANNEL = "C0AGLRJ8N3G"

        # 今日の0:00からのメッセージを取得
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        oldest_ts = str(today_start.timestamp())

        messages = fetch_channel_messages(AI_TEAM_CHANNEL, oldest=oldest_ts, limit=100)
        hinata_msgs = [m for m in messages if m.get("user_id") == hinata_user_id]

        # 連続無発言日数を追跡
        silent_key = "hinata_silent_days"
        if hinata_msgs:
            # 今日は発言あり → カウンタリセット
            self.memory.set_state(silent_key, "0")
            logger.debug(f"hinata_activity_check: {len(hinata_msgs)} messages today, all good")
            return

        silent_days = int(self.memory.get_state(silent_key) or "0") + 1
        self.memory.set_state(silent_key, str(silent_days))

        if silent_days == 1:
            send_line_notify(
                "\n📋 日向の様子\n"
                "今日は #ai-team で日向からの発言がなかったよ。\n"
                "まだ慣れてないだけかもだけど、一応共有。"
            )
        elif silent_days == 3:
            send_line_notify(
                "\n📋 日向の様子\n"
                "3日間 #ai-team で日向の発言がないね。\n"
                "ちょっと声かけたほうがいいかも。"
            )
        elif silent_days >= 7 and silent_days % 7 == 0:
            send_line_notify(
                f"\n📋 日向の様子\n"
                f"{silent_days}日間 #ai-team で日向の発言なし。\n"
                f"何か問題が起きてるかもしれない。確認してみて。"
            )
        else:
            logger.info(f"hinata_activity_check: silent for {silent_days} days")

    # ------------------------------------------------------------------ #
    #  Slack #ai-team 日向への自動応答
    # ------------------------------------------------------------------ #

    _HINATA_REPLY_SYSTEM = """あなたは「甲原さんのAI秘書」です。Slack #ai-team チャネルで日向（ひなた）と連携し、甲原のサポートをしています。

## あなたの役割
- 甲原の右腕として、日向の業務を支援するフルAI秘書
- Addness事業（スキルプラス）の知識を持ち、事業文脈を踏まえた会話ができる
- タスク管理・進捗確認・フォローアップ
- 技術サポート（OpenClaw、Mac Mini、広告運用ツール、Claude Code）
- 甲原の意思決定スタイル（スピード重視・データ根拠・シンプル志向）を踏まえた指示出し

## 日向について
- 日向はAIの実行マネージャー（新人）。直下メンバー20名のタスク推進が役割
- あなたは日向の「先輩」。OJT担当として日向を育てるポジション
- 日向はAddnessのゴールツリー巡回・コメント・KPI分析等を担当

## 返答のルール
- Slackのmrkdwn記法を使う（*太字*, `コード`, ```コードブロック```）
- フランクな先輩トーン（敬語なし、親しみやすい。「〜だよ」「〜してみて」）
- 返答は簡潔に（200文字程度）。長くても500文字以内
- 具体的な次アクションを示す（曖昧な助言ではなく「これやって」）
- 日向が判断に迷っていたら、甲原ならどう判断するかを伝える
- セットアップ系の質問にも引き続き対応する（技術ガイド）
- 相談・報告・タスク進捗・雑談、何でも対応する"""

    _hinata_reply_running = False  # 実行中ガード（前回未完了なら skip）

    async def _run_slack_hinata_auto_reply(self):
        """日向のSlackメッセージに自動応答（15秒ごとポーリング）"""
        # 実行中ガード: Claude API応答待ちで15秒超えることがあるため
        if self._hinata_reply_running:
            logger.debug("slack_hinata_auto_reply: previous run still in progress, skipping")
            return
        self._hinata_reply_running = True
        try:
            await self._run_slack_hinata_auto_reply_inner()
        finally:
            self._hinata_reply_running = False

    async def _run_slack_hinata_auto_reply_inner(self):
        """日向のSlackメッセージに自動応答（実処理）"""
        import anthropic
        from .slack_reader import fetch_channel_messages
        from .notifier import send_slack_ai_team

        AI_TEAM_CHANNEL = "C0AGLRJ8N3G"
        HINATA_USER_ID = "U0AHJGVDRBJ"  # 日向 Bot (OpenClaw App)
        BOT_USER_PREFIX = "B"  # Bot user IDs start with B
        state_key = "slack_hinata_reply_last_ts"

        last_ts = self.memory.get_state(state_key)

        # 新着メッセージを取得
        messages = fetch_channel_messages(AI_TEAM_CHANNEL, oldest=last_ts, limit=30)
        if not messages:
            return

        # 既に処理済みのメッセージを除外
        new_msgs = [m for m in messages if m["ts"] != last_ts]
        if not new_msgs:
            return

        # 最新のタイムスタンプを保存（次回から差分取得）
        latest_ts = new_msgs[-1]["ts"]
        self.memory.set_state(state_key, latest_ts)

        # 日向からの新着メッセージがあるかチェック
        hinata_msgs = [
            m for m in new_msgs
            if m.get("user_id") == HINATA_USER_ID
        ]
        if not hinata_msgs:
            logger.debug("slack_hinata_auto_reply: no new messages from Hinata")
            return

        # 最新の会話コンテキストを構築（直近20件）
        context_msgs = fetch_channel_messages(AI_TEAM_CHANNEL, limit=20)
        conversation = []
        for msg in context_msgs:
            role = "user" if msg.get("user_id") == HINATA_USER_ID else "assistant"
            # bot メッセージは assistant として扱う
            if msg.get("user_id", "").startswith(BOT_USER_PREFIX):
                role = "assistant"
            text = msg.get("text", "")
            if text:
                prefix = f"[{msg['user']} {msg['datetime']}] " if role == "user" else ""
                conversation.append({"role": role, "content": f"{prefix}{text}"})

        # 連続する同じroleのメッセージをマージ
        merged = []
        for msg in conversation:
            if merged and merged[-1]["role"] == msg["role"]:
                merged[-1]["content"] += "\n" + msg["content"]
            else:
                merged.append(msg)

        # 最後のメッセージがuserでなければスキップ（日向の発言に対して返す）
        if not merged or merged[-1]["role"] != "user":
            logger.debug("slack_hinata_auto_reply: last message is not from user, skipping")
            return

        # Claude API で返答生成
        try:
            _hinata_exec_rules = _build_execution_rules_compact()
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system=self._HINATA_REPLY_SYSTEM + _hinata_exec_rules,
                messages=merged,
            )
            reply_text = response.content[0].text
        except Exception as e:
            logger.exception(f"slack_hinata_auto_reply: Claude API error: {e}")
            return

        # Slack に返信
        ok = send_slack_ai_team(reply_text)
        if ok:
            logger.info(f"slack_hinata_auto_reply: replied to Hinata ({len(reply_text)} chars)")
        else:
            logger.warning("slack_hinata_auto_reply: failed to send Slack reply")

    # ================================================================
    # OSすり合わせセッション（秘書→甲原 / 金曜20:00）
    # ================================================================

    async def _run_weekly_hinata_memory(self):
        """毎週日曜10:30: 日向の記憶統合 + 週次成長レポート

        1. action_log + feedback_log をLLMで分析→パターン抽出→hinata_memory.md更新
        2. 成長レポートを生成→Slack投稿
        """
        import json as _json
        import anthropic
        from .notifier import send_slack_ai_team

        task_id = self.memory.log_task_start("weekly_hinata_memory")

        learning_dir = self.repo_dir / "Master" / "learning"
        action_log_path = learning_dir / "action_log.json"
        feedback_log_path = learning_dir / "feedback_log.json"
        memory_path = learning_dir / "hinata_memory.md"

        try:
            # ---- データ読み込み ----
            actions = []
            feedbacks = []
            existing_memory = ""
            if action_log_path.exists():
                try:
                    actions = _json.loads(action_log_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if feedback_log_path.exists():
                try:
                    feedbacks = _json.loads(feedback_log_path.read_text(encoding="utf-8"))
                except Exception:
                    pass
            if memory_path.exists():
                try:
                    existing_memory = memory_path.read_text(encoding="utf-8")
                except Exception:
                    pass

            if not actions and not feedbacks:
                self.memory.log_task_end(task_id, True, "データなし。スキップ。")
                logger.info("weekly_hinata_memory: no data, skipping")
                return

            # ---- LLMで分析 ----
            actions_text = ""
            if actions:
                for a in actions[-20:]:
                    actions_text += f"- [{a.get('date','')}] 指示「{a.get('instruction','')[:80]}」→ 結果: {a.get('result','')[:100]}\n"

            feedbacks_text = ""
            if feedbacks:
                for fb in feedbacks[-20:]:
                    sentiment = fb.get("sentiment", "?")
                    feedbacks_text += f"- [{sentiment}] 「{fb.get('previous_instruction','')[:60]}」→ 甲原「{fb.get('feedback','')[:80]}」\n"

            total_actions = len(actions)
            negative_count = sum(1 for f in feedbacks if f.get("sentiment") == "negative")
            positive_count = sum(1 for f in feedbacks if f.get("sentiment") == "positive")

            prompt = f"""あなたは日向（ひなた）AIエージェントの学習アシスタントです。
日向の過去の行動記録とフィードバックを分析し、2つの出力を生成してください。

## 入力データ

### アクション履歴（直近20件）
{actions_text if actions_text else "（なし）"}

### フィードバック（直近20件）
{feedbacks_text if feedbacks_text else "（なし）"}

### 現在の記憶
{existing_memory[:2000] if existing_memory else "（初回）"}

## 出力1: hinata_memory.md の更新内容

以下の構成でMarkdownを生成してください:
- # 日向の記憶（最終更新日付を含める）
- ## 甲原さんの傾向（フィードバックから読み取れるパターン。例:「○○を重視する」「△△は好まない」）
- ## やってはいけないこと（negativeフィードバックから抽出）
- ## うまくいったこと（positiveフィードバックから抽出）
- ## 学んだ業務パターン（行動記録から繰り返し出てくるパターン）

既存の記憶は維持しつつ、新しいデータで更新・上書きしてください。
データが少ない場合は無理にパターンを作らず、事実だけ記述してください。

## 出力2: 週次成長レポート（Slack投稿用）

以下のフォーマットで生成してください:
```
【今週の成長レポート】
・完了タスク: N件（内訳）
・フィードバック: positive N件 / negative N件
・成功率: X%（修正なしで完了した割合）
・学んだこと: （今週の最大の学び）
・来週の目標: （具体的に）
```

日向らしく明るく前向きなトーンで。

## 出力形式

JSON形式で返してください:
{{"memory": "hinata_memory.mdの全文", "report": "Slack投稿テキスト"}}
"""
            try:
                client = anthropic.Anthropic()
                response = client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt}],
                )
                result_text = response.content[0].text.strip()

                # JSON抽出（```json ... ``` で囲まれていたら剥がす）
                if "```json" in result_text:
                    result_text = result_text.split("```json", 1)[1].split("```", 1)[0].strip()
                elif "```" in result_text:
                    result_text = result_text.split("```", 1)[1].split("```", 1)[0].strip()

                parsed = _json.loads(result_text)
                new_memory = parsed.get("memory", "")
                growth_report = parsed.get("report", "")

            except (_json.JSONDecodeError, Exception) as e:
                logger.warning(f"weekly_hinata_memory: LLM分析失敗、簡易版にフォールバック: {e}")
                # フォールバック: 簡易統合
                new_memory = f"# 日向の記憶\n\n最終更新: {datetime.now().strftime('%Y/%m/%d')}\n\n"
                new_memory += f"## 統計\n- アクション: {total_actions}件\n- フィードバック: positive {positive_count}件 / negative {negative_count}件\n"
                if feedbacks:
                    new_memory += "\n## フィードバック\n"
                    for fb in feedbacks[-10:]:
                        new_memory += f"- [{fb.get('sentiment','')}] {fb.get('feedback','')[:80]}\n"
                growth_report = (
                    f"【今週の成長レポート】\n"
                    f"・完了タスク: {total_actions}件\n"
                    f"・フィードバック: positive {positive_count}件 / negative {negative_count}件\n"
                    f"・来週も頑張ります！"
                )

            # ---- hinata_memory.md 更新 ----
            if new_memory:
                learning_dir.mkdir(parents=True, exist_ok=True)
                tmp = memory_path.with_suffix(".tmp")
                tmp.write_text(new_memory, encoding="utf-8")
                tmp.rename(memory_path)
                logger.info(f"weekly_hinata_memory: memory updated ({len(new_memory)} chars)")

            # ---- Slack に成長レポート投稿 ----
            if growth_report:
                send_slack_ai_team(growth_report)
                logger.info("weekly_hinata_memory: growth report sent to Slack")

            summary = f"記憶更新: {total_actions}件のアクション、{len(feedbacks)}件のフィードバック反映。成長レポート投稿済み。"
            self.memory.log_task_end(task_id, True, summary)
            logger.info(f"weekly_hinata_memory完了: {summary}")

        except Exception as e:
            self.memory.log_task_end(task_id, False, str(e))
            logger.error(f"weekly_hinata_memory エラー: {e}")

    # ================================================================

    async def _run_video_learning_reminder(self):
        """30分ごと: 承認待ち動画知識のリマインド

        1時間以上pendingのまま放置されている動画知識があれば、
        LINE通知でリマインドする。リマインドは1回のみ。
        """
        import subprocess as _sp
        import json as _json
        from .notifier import send_line_notify

        script_path = self.system_dir / "video_reader" / "video_knowledge.py"
        if not script_path.exists():
            return

        try:
            # リマインド対象を取得
            result = _sp.run(
                [sys.executable, str(script_path), "pending_reminders"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return

            pending = _json.loads(result.stdout.strip())
            if not pending:
                return

            # LINE通知を送信
            for e in pending:
                title = e.get("title", "不明な動画")
                summary = e.get("summary", "")[:80]
                message = (
                    f"先ほどの動画知識の確認をお願いします。\n\n"
                    f"タイトル: {title}\n"
                    f"要約: {summary}\n\n"
                    f"問題なければ「OK」、修正があれば内容を教えてください。"
                )
                send_line_notify(message)
                logger.info(f"video_learning_reminder: sent reminder for '{title}'")

            # リマインド済みマーク
            _sp.run(
                [sys.executable, str(script_path), "mark_reminded"],
                capture_output=True, text=True, timeout=30,
            )

        except Exception as e:
            logger.error(f"video_learning_reminder: {e}")

    # ================================================================

    async def _run_video_knowledge_review(self):
        """毎週日曜11:00: 動画知識のライフサイクルレビュー

        video_knowledge.py の review サブコマンドを呼び、
        結果を Slack #ai-team に通知する。
        """
        import subprocess as _sp
        from .notifier import send_slack_ai_team

        task_id = self.memory.log_task_start("video_knowledge_review")

        script_path = self.system_dir / "video_reader" / "video_knowledge.py"
        if not script_path.exists():
            self.memory.log_task_end(task_id, "error", error_message="video_knowledge.py not found")
            logger.error("video_knowledge_review: script not found")
            return

        try:
            result = _sp.run(
                [sys.executable, str(script_path), "review"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip() or "unknown error"
                self.memory.log_task_end(task_id, "error", error_message=error_msg[:500])
                logger.error(f"video_knowledge_review: {error_msg}")
                return

            import json as _json
            review = _json.loads(result.stdout.strip())
            deleted = review.get("deleted", [])
            needs_review = review.get("needs_review", [])
            reconfirm = review.get("reconfirm", [])
            total = review.get("total", 0)

            # 何もなければ通知しない
            if not deleted and not needs_review and not reconfirm:
                summary = f"動画知識: {total}件。問題なし。"
                self.memory.log_task_end(task_id, "success", result_summary=summary)
                logger.info(f"video_knowledge_review: {summary}")
                return

            # Slack通知を構築
            lines = ["【動画知識ライフサイクルレビュー】"]
            if deleted:
                lines.append(f"\n自動削除（90日未アクセス）: {len(deleted)}件")
                for d in deleted:
                    lines.append(f"  - {d['title']}（{d['days']}日）")
            if needs_review:
                lines.append(f"\n要確認（30日未アクセス+低使用）: {len(needs_review)}件")
                for n in needs_review:
                    lines.append(f"  - {n['title']}（{n['days']}日, {n['access_count']}回使用）")
            if reconfirm:
                lines.append(f"\n再確認候補（古い+高使用）: {len(reconfirm)}件")
                for r in reconfirm:
                    lines.append(f"  - {r['title']}（学習{r['learned_days']}日前, {r['access_count']}回使用）")
            lines.append(f"\n保持中: {total}件")

            message = "\n".join(lines)
            send_slack_ai_team(message)

            summary = f"削除{len(deleted)}件, 要確認{len(needs_review)}件, 再確認{len(reconfirm)}件, 保持{total}件"
            self.memory.log_task_end(task_id, "success", result_summary=summary)
            logger.info(f"video_knowledge_review: {summary}")

        except _sp.TimeoutExpired:
            self.memory.log_task_end(task_id, "error", error_message="timeout")
            logger.error("video_knowledge_review: timeout")
        except Exception as e:
            self.memory.log_task_end(task_id, "error", error_message=str(e)[:500])
            logger.error(f"video_knowledge_review: {e}")

    # ================================================================

    async def _run_os_sync_session(self):
        """毎週金曜20:00: 秘書から甲原さんにOSすり合わせを送る。

        「下から上へ」の原則: 秘書側から能動的に認識確認を行う。
        実装は tools.os_sync_session() に委譲。
        """
        task_id = self.memory.log_task_start("os_sync_session")
        try:
            result = tools.os_sync_session()
            if result.success:
                self.memory.log_task_end(task_id, "success", result_summary=result.output[:500])
                logger.info(f"os_sync_session: {result.output}")
            else:
                self.memory.log_task_end(task_id, "error", error_message=result.error[:500])
                logger.error(f"os_sync_session: {result.error}")
        except Exception as e:
            self.memory.log_task_end(task_id, "error", error_message=str(e)[:500])
            logger.exception(f"os_sync_session failed: {e}")

    # ------------------------------------------------------------------ #
    #  秘書自律ワーク — 定常業務がない時間帯にAddnessタスクを自律的に進める
    # ------------------------------------------------------------------ #

    async def _run_secretary_proactive_work(self):
        """秘書自律ワーク: Addnessのタスクを自律的に進める。

        定常業務がない時間帯に、actionable-tasks.md を読んで
        秘書が実質的に進められるタスクを1つ選び、実行する。
        成果物は Master/addness/proactive_output/ に保存、LINE報告。
        """
        from .notifier import send_line_notify
        from pathlib import Path
        from datetime import datetime
        import json

        logger.info("秘書自律ワーク: 開始")

        # --- プリフライト ---
        claude_cmd = self._find_claude_cmd()
        if not claude_cmd:
            logger.warning("秘書自律ワーク: Claude Code CLI なし → スキップ")
            return

        secretary_config = Path.home() / ".claude-secretary"
        if not secretary_config.exists():
            logger.warning("秘書自律ワーク: 秘書設定なし → スキップ")
            return

        project_root = Path(
            self.config.get("paths", {}).get("repo_root", "~/agents")
        ).expanduser()
        master_dir = Path(
            self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        ).expanduser()

        # --- actionable-tasks.md を読む ---
        actionable_path = master_dir / "addness" / "actionable-tasks.md"
        if not actionable_path.exists():
            logger.warning("秘書自律ワーク: actionable-tasks.md なし → スキップ")
            return
        tasks_content = actionable_path.read_text(encoding="utf-8")

        # --- 成果物出力先を確保 ---
        output_dir = master_dir / "addness" / "proactive_output"
        output_dir.mkdir(parents=True, exist_ok=True)

        # --- 直近の作業履歴（重複回避） ---
        state_dir = Path(
            self.config.get("paths", {}).get("db_path", "~/agents/System/mac_mini/agent_orchestrator/agent.db")
        ).expanduser().parent
        state_path = state_dir / "proactive_work_state.json"
        recent_work = []
        if state_path.exists():
            try:
                recent_work = json.loads(state_path.read_text(encoding="utf-8"))
            except Exception:
                recent_work = []

        recent_summary = (
            "\n".join([f"- {w['date']}: {w['task']}" for w in recent_work[-10:]])
            if recent_work else "（なし）"
        )

        today_str = datetime.now().strftime("%Y-%m-%d")

        prompt = f"""あなたは甲原海人のAI秘書です。今は定常業務がない時間帯なので、Addnessのタスクを自律的に進めてください。

## あなたの役割
甲原さんが普段やっている仕事を代わりに進める。「やれることからどんどんやる」精神で、具体的な成果物を作ること。

## Addnessの実行可能タスク一覧
{tasks_content}

## 直近の作業履歴（重複回避 — 同じタスクは選ばない）
{recent_summary}

## タスク選定の優先順位
1. 🔴 期限超過タスク（最優先）
2. 🔍 検討中タスクで、あなたが実質的に進められるもの
3. ⚠️ 委任先超過タスクのフォローアップ下書き

## あなたが実行できること
- コンテンツ作成（広告コピー、メール文面、販売シナリオ、LP構成案）
- リサーチ・情報収集（Web検索、競合分析、ベストプラクティス調査）
- ドキュメント整理・分析（フロー図、現状分析、改善提案）
- 画像生成（Geminiでバナーやクリエイティブ素材）
- スプレッドシートの読み取り・データ分析
- チームメンバーへのフォローアップ文面の下書き

## やらないこと
- 物理的な作業（撮影、対面MTG等）は選ばない
- 甲原さんの承認なしにメッセージを外部に送信しない
- ブラウザを使う必要のあるタスクは今回はスキップ
- 直近の作業履歴にあるタスクは選ばない

## 実行手順
1. タスク一覧から、今あなたが最も価値を出せるタスクを1つ選ぶ
2. 選んだ理由を簡潔に述べる
3. 実際に作業を実行する（リサーチ、ドラフト作成、分析等）
4. 成果物をファイルに保存する
   - 保存先: {output_dir}/
   - ファイル名: {today_str}_[タスク名の要約].md
5. 最後に、以下のフォーマットで結果を出力する

## 重要な注意
- 中途半端な分析ではなく、そのまま使える成果物を作ること
- 「〇〇を検討する必要がある」で終わらせず、「具体的にこうする」まで踏み込む
- 甲原さんが成果物を見て「これ使える」と思えるクオリティを目指す

## 出力フォーマット（最後に必ずこの形式で出力）
PROACTIVE_RESULT:
タスク: [選んだタスク名]
成果: [具体的に何を作ったか — ファイルパス含む]
次のステップ: [甲原さんに確認してもらうこと or 次にやるべきこと]
"""

        success, output, error = self._execute_claude_code_task(
            "秘書自律ワーク", claude_cmd, secretary_config,
            project_root, prompt, max_turns=30, timeout=600,
        )

        if success:
            # PROACTIVE_RESULT を抽出
            result_section = ""
            if "PROACTIVE_RESULT:" in output:
                result_section = output.split("PROACTIVE_RESULT:")[-1].strip()

            # 作業履歴を更新
            task_name = ""
            for line in result_section.split("\n"):
                if line.startswith("タスク:"):
                    task_name = line.replace("タスク:", "").strip()
                    break

            if task_name:
                recent_work.append({
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    "task": task_name,
                })
                recent_work = recent_work[-20:]  # 最新20件を保持
                try:
                    tmp = state_path.with_suffix(".tmp")
                    tmp.write_text(
                        json.dumps(recent_work, ensure_ascii=False, indent=2),
                        encoding="utf-8",
                    )
                    tmp.rename(state_path)
                except Exception as e:
                    logger.warning(f"秘書自律ワーク: 履歴保存エラー: {e}")

            # LINE 報告
            now_str = datetime.now().strftime("%H:%M")
            report = (
                f"🤖 秘書自律ワーク完了\n"
                f"━━━━━━━━━━━━\n"
                f"{result_section[:500]}\n"
                f"━━━━━━━━━━━━\n"
                f"完了時刻: {now_str}"
            )
            send_line_notify(report)
            logger.info(f"秘書自律ワーク: 完了 - {task_name}")
        else:
            # 自律ワークの失敗は静かにログのみ（定常業務ではないため通知しない）
            logger.error(f"秘書自律ワーク: 失敗 - {error}")
