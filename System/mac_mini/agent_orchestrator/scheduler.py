from __future__ import annotations
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
            "cdp_sync": self._run_cdp_sync,
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
            "secretary_goal_progress": self._run_secretary_goal_progress,
            "weekly_hinata_memory": self._run_weekly_hinata_memory,
            "video_knowledge_review": self._run_video_knowledge_review,
            "video_learning_reminder": self._run_video_learning_reminder,
            "daily_report_reminder": self._run_daily_report_reminder,
            "anthropic_credit_check": self._run_anthropic_credit_check,
            "looker_session_keepalive": self._run_looker_session_keepalive,
            "kpi_anomaly_check": self._run_kpi_anomaly_check,
            "monthly_invoice_submission": self._run_monthly_invoice_submission,
            "ds_insight_biweekly_report": self._run_ds_insight_biweekly_report,
            "ds_insight_mail_collect": self._run_ds_insight_mail_collect,
            "ds_insight_weekly_digest": self._run_ds_insight_weekly_digest,
            "meeting_report": self._run_meeting_report,
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
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True, misfire_grace_time=60)
                logger.info(f"Scheduled '{task_name}' with cron: {cfg['cron']}")
            elif "interval_seconds" in cfg:
                trigger = IntervalTrigger(seconds=cfg["interval_seconds"])
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True, misfire_grace_time=30)
                logger.info(f"Scheduled '{task_name}' every {cfg['interval_seconds']} seconds")
            elif "interval_minutes" in cfg:
                trigger = IntervalTrigger(minutes=cfg["interval_minutes"])
                self.scheduler.add_job(task_fn, trigger, id=task_name, name=task_name, replace_existing=True, misfire_grace_time=120)
                logger.info(f"Scheduled '{task_name}' every {cfg['interval_minutes']} minutes")

    def start(self):
        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self):
        self.scheduler.shutdown()
        logger.info("Scheduler shut down")

    # タスク失敗通知を送らないタスク（自前でエラーハンドリングするもの）
    _NO_FAILURE_NOTIFY = {"health_check", "oauth_health_check", "render_health_check", "anthropic_credit_check", "secretary_goal_progress"}
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
            f"{task_name} でエラーが出ました。\n"
            f"{error_msg[:250]}"
        )
        if ok:
            self.memory.set_state(state_key, now.isoformat())

    async def _run_addness_fetch(self):
        result = await self._execute_tool("addness_fetch", tools.addness_fetch)
        if result.success:
            ctx_result = await self._execute_tool("addness_to_context", tools.addness_to_context)
            from .notifier import send_line_notify
            if not ctx_result.success:
                send_line_notify("Addnessのゴール同期はできましたが、コンテキスト更新に失敗しました。")
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

    async def _run_ds_insight_mail_collect(self):
        """DS.INSIGHTメール回収（通知せず蓄積、失敗時3時間後にリトライ）"""
        import asyncio
        success = await self._collect_dsinsight_emails()
        if not success:
            logger.info("DS.INSIGHTメール回収失敗、3時間後にリトライ")
            await asyncio.sleep(3 * 3600)
            await self._collect_dsinsight_emails()

    async def _run_ds_insight_weekly_digest(self):
        """DS.INSIGHT週次レポート（金曜10:00、1週間分をまとめて要約→LINE通知）"""
        import json
        from pathlib import Path
        from .notifier import send_line_notify

        pool_path = Path(self.config.get("paths", {}).get("system_dir", "~/agents/System")).expanduser() / "data" / "ds_insight_weekly_pool.json"
        if not pool_path.exists():
            logger.info("DS.INSIGHT週次レポート: 今週のメールなし")
            return

        try:
            with open(pool_path) as f:
                pool = json.load(f)

            if not pool:
                logger.info("DS.INSIGHT週次レポート: 今週のメールなし")
                return

            # 全メールをまとめてClaude Haikuで週次要約
            summary = self._summarize_dsinsight_weekly(pool)
            message = f"📊 DS.INSIGHT 週次レポート\n━━━━━━━━━━\n{summary}"
            send_line_notify(message)
            logger.info(f"DS.INSIGHT週次レポート送信完了（{len(pool)}件のメールを要約）")

            # 市場トレンド知識を更新（秘書・日向の頭の中に入る形で蓄積）
            from datetime import date
            self._update_market_knowledge(pool, summary, date.today().isoformat())

            # 週次プールをクリア（知識ファイルに反映済み）
            pool_path.write_text("[]")

        except Exception as e:
            logger.error(f"DS.INSIGHT週次レポートエラー: {e}")

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
        message = f"メールに返信待ちが{waiting}件あります（{account_label}）"
        if delete > 0:
            message += f"\n削除確認も{delete}件あります。"
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

    def _summarize_dsinsight_weekly(self, emails: list) -> str:
        """1週間分のDS.INSIGHTメールをまとめてClaude Haikuで要約"""
        import anthropic

        # メールを種別ごとに整理して1つのテキストにまとめる
        email_texts = []
        for em in emails:
            email_texts.append(f"【{em['subject']}】\n{em['body'][:1500]}")
        combined = "\n\n---\n\n".join(email_texts)

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=800,
                system="""あなたはAddnessの広告マーケティング秘書です。
DS.INSIGHT（Yahoo!検索データ分析ツール）から今週届いたメール通知をまとめて、
1つの週次レポートとして甲原さんに報告します。

■ 甲原さんが知りたいこと:
- 「スキルプラス」のブランド認知は伸びてる？落ちてる？
- AI・副業・スキルアップ・リスキリング市場に変化はある？
- 広告やコンテンツで今すぐ動くべきことはある？

■ レポート構成:
1. 今週のハイライト（最も重要な変化を1-2行で）
2. 検索トレンド変化（数値変化は具体的に↑↓で）
3. 注目の新規キーワード（あれば）
4. 動くべきこと（アクション提案があれば1-2行で）

■ ルール:
- 甲原さんが知りたいことにダイレクトに答える
- 変化がないものは書かない（「変化なし」の羅列は不要）
- 全体として簡潔に。長くても15行以内""",
                messages=[{"role": "user", "content": f"今週届いたDS.INSIGHTメール（{len(emails)}通）:\n\n{combined[:4000]}"}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            logger.warning(f"DS.INSIGHT週次要約失敗（件名一覧で代替）: {e}")
            subjects = "\n".join(f"・{em['subject']}" for em in emails)
            return f"AI要約に失敗しました。今週のメール:\n{subjects}"

    def _update_market_knowledge(self, emails: list, weekly_summary: str, week_date: str):
        """DS.INSIGHTデータを市場トレンド知識ファイルに反映（秘書・日向が参照可能に）"""
        import anthropic
        from pathlib import Path

        knowledge_path = Path(self.config.get("paths", {}).get("project_root", "~/agents")).expanduser() / "Master" / "addness" / "market_trends.md"

        # 既存の知識を読み込む
        existing = ""
        if knowledge_path.exists():
            existing = knowledge_path.read_text()

        # メール原文を整理
        email_texts = []
        for em in emails:
            email_texts.append(f"【{em['subject']}】\n{em['body'][:1500]}")
        combined = "\n\n---\n\n".join(email_texts)

        try:
            client = anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1500,
                system="""あなたはAddnessの市場分析担当です。
DS.INSIGHTの最新データをもとに、市場トレンドの知識ファイルを更新します。

■ このファイルの目的:
- 秘書や日向（AIエージェント）が広告CR企画・コンテンツ提案・リサーチ時に参照する「市場の頭の中」
- 単なる記録ではなく、意思決定に使える知識として蓄積する

■ 更新ルール:
- 「最新の市場認識」セクションは毎週上書き（常に最新状態を反映）
- 「トレンド変遷」セクションは追記（時系列で市場の動きが追える）
- 「示唆・仮説」セクションはデータから導ける推測を書く（例: 「AI資格の検索が伸びている→資格訴求のCRが刺さる可能性」）
- 変化がないものは書かない
- 具体的なKWと数値変化は必ず残す

■ 出力形式:
market_trends.md の全文をそのまま出力してください。既存の内容をベースに更新してください。""",
                messages=[{"role": "user", "content": f"""既存の知識ファイル:
```
{existing[:3000] if existing else "(新規作成)"}
```

今週のDS.INSIGHTデータ（{week_date}週）:
{combined[:3000]}

今週の要約:
{weekly_summary}"""}]
            )

            updated = response.content[0].text.strip()
            # マークダウンコードブロックで囲まれている場合は除去
            if updated.startswith("```"):
                lines = updated.split("\n")
                updated = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])

            knowledge_path.write_text(updated)
            logger.info(f"市場トレンド知識を更新: {knowledge_path}")

            # git add（git_pull_syncが次回コミット&pushする）
            import subprocess
            project_root = knowledge_path.parent.parent.parent
            subprocess.run(["git", "add", str(knowledge_path)], cwd=project_root, capture_output=True)

        except Exception as e:
            logger.warning(f"市場トレンド知識の更新失敗: {e}")

    async def _collect_dsinsight_emails(self) -> bool:
        """DS.INSIGHTメールを回収して週次プールに蓄積（通知はしない）"""
        import json
        from pathlib import Path

        try:
            result = await self._execute_tool("dsinsight_mail_check", tools.dsinsight_mail_check)
            if not result.success or result.output == "DS.INSIGHTメールなし":
                return True  # メールなしは成功扱い

            items = json.loads(result.output)
            if not items:
                return True

            system_dir = Path(self.config.get("paths", {}).get("system_dir", "~/agents/System")).expanduser()

            # 転送済みID管理（重複防止）
            forwarded_path = system_dir / "data" / "ds_insight_forwarded_ids.json"
            forwarded_path.parent.mkdir(parents=True, exist_ok=True)
            forwarded_ids = set()
            if forwarded_path.exists():
                with open(forwarded_path) as f:
                    forwarded_ids = set(json.load(f))

            new_items = [item for item in items if item["id"] not in forwarded_ids]
            if not new_items:
                return True

            # 週次プールに蓄積
            pool_path = system_dir / "data" / "ds_insight_weekly_pool.json"
            pool = []
            if pool_path.exists():
                with open(pool_path) as f:
                    pool = json.load(f)

            for item in new_items:
                pool.append({"subject": item["subject"], "body": item["body"], "id": item["id"]})
                forwarded_ids.add(item["id"])
                logger.info(f"DS.INSIGHTメール回収: {item['subject']}")

            with open(pool_path, "w") as f:
                json.dump(pool, f, ensure_ascii=False)
            with open(forwarded_path, "w") as f:
                json.dump(list(forwarded_ids)[-100:], f)

            return True

        except Exception as e:
            logger.error(f"DS.INSIGHTメール回収エラー: {e}")
            return False

    async def _run_ds_insight_biweekly_report(self):
        """隔週DS.INSIGHTレポート生成（日曜 11:30）"""
        import json
        import subprocess
        from datetime import date
        from pathlib import Path
        from .notifier import send_line_notify

        # 隔週判定（3/8日曜を基準週）
        weeks_since = (date.today() - date(2026, 3, 8)).days // 7
        if weeks_since % 2 != 0:
            logger.info("DS.INSIGHTレポート: 今週はスキップ（隔週判定）")
            return

        ok, claude_cmd, secretary_config, project_root, err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"DS.INSIGHTレポート: 環境準備失敗 - {err}")
            send_line_notify(f"⚠️ DS.INSIGHTレポート生成失敗: {err}")
            return

        # 前回データ読み込み
        data_path = Path(self.config.get("paths", {}).get("system_dir", "~/agents/System")).expanduser() / "data" / "ds_insight_last.json"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        last_data = ""
        if data_path.exists():
            with open(data_path) as f:
                last_data = f.read()

        last_context = f"\n\n前回データ:\n{last_data}" if last_data else "\n\n（初回実行のため前回データなし）"

        prompt = f"""DS.INSIGHT（https://dsinsight.yahoo.co.jp/）にアクセスして以下のデータを取得し、レポートを生成してください。

## 取得データ
1. Basic: 「スキルプラス」「AI 副業」「副業」の検索ボリューム + 共起KW上位10件
2. Journey: 「スキルプラス」の前後検索KW（ランキング上位10件、重複Vol・特徴度・検索時間差）
3. Trend: AI・副業カテゴリの急上昇KW上位5件 + トレンドマップの注目KW

## レポートフォーマット（ハイブリッド型）
- 定点観測: 各KWの検索ボリューム推移
- 変化検知: 前回比で大きく変動したKW・新規出現KW
- インサイト: ビジネスに活かせる気づき（1〜2行）

## 出力要件
- 990文字以内（LINE通知用）
- 改行と区切り線で読みやすく
- 数値は前回比を示す（↑↓→）
{last_context}

## データ保存
取得した数値データをJSON形式で {data_path} に保存してください。
フォーマット: {{"date": "YYYY-MM-DD", "keywords": {{"KW名": {{"volume": 数値}}}}, "trend_keywords": ["KW1", "KW2"]}}
"""

        try:
            env = {
                **subprocess.os.environ,
                "CLAUDE_CONFIG_DIR": str(secretary_config),
                "PATH": f"/opt/homebrew/bin:{subprocess.os.environ.get('PATH', '')}",
            }
            env.pop("ANTHROPIC_API_KEY", None)

            cmd = [
                str(claude_cmd), "-p",
                "--model", "claude-sonnet-4-6",
                "--max-turns", "15",
                "--chrome",
                prompt,
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600,
                cwd=str(project_root), env=env,
            )

            if result.returncode != 0:
                logger.error(f"DS.INSIGHTレポート: Claude Code失敗 (code={result.returncode})")
                send_line_notify(f"⚠️ DS.INSIGHTレポート生成失敗: Claude Code エラー")
                return

            output = result.stdout.strip()
            if not output:
                logger.warning("DS.INSIGHTレポート: Claude Code出力なし")
                send_line_notify("⚠️ DS.INSIGHTレポート: 出力が空でした")
                return

            # レポートをLINE送信（990文字制限）
            report = output[:990]
            send_line_notify(f"📊 DS.INSIGHTレポート\n\n{report}")
            logger.info("DS.INSIGHTレポート送信完了")

        except subprocess.TimeoutExpired:
            logger.error("DS.INSIGHTレポート: タイムアウト（600秒）")
            send_line_notify("⚠️ DS.INSIGHTレポート: タイムアウト")
        except Exception as e:
            logger.error(f"DS.INSIGHTレポート: 例外 - {e}")
            send_line_notify(f"⚠️ DS.INSIGHTレポート生成失敗: {e}")

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

    def _prepare_claude_env(self):
        """Claude Code CLI の事前チェック（Chromeなし版）。"""
        from pathlib import Path
        claude_cmd = self._find_claude_cmd()
        if not claude_cmd:
            return False, None, None, None, "Claude Code CLIが見つかりません"
        secretary_config = Path.home() / ".claude-secretary"
        if not secretary_config.exists():
            return False, None, None, None, f"秘書設定ディレクトリが見つかりません: {secretary_config}"
        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()
        oauth_ok, oauth_err = self._refresh_claude_oauth(secretary_config)
        if not oauth_ok:
            return False, None, None, None, f"Claude Code OAuth エラー: {oauth_err}"
        return True, claude_cmd, secretary_config, project_root, ""

    def _build_google_login_instructions(self) -> str:
        """Looker Studio ログイン切れ時の自動ログイン手順（プロンプト注入用）。"""
        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()
        creds_file = project_root / "System" / "credentials" / "kohara_google.txt"
        return f"""### Googleログイン切れの場合（自動復旧）
Looker Studio にアクセスした際、ログイン画面やアカウント選択画面が表示された場合は、
エラーとして終了せず、以下の手順で自動ログインを試みてください。

1. 認証情報を読み込む:
```bash
cat {creds_file}
```
この出力がGoogleアカウントのパスワードです。

2. ログインフロー（第1候補: koa800sea.nifs@gmail.com）:
   - アカウント選択画面 → `koa800sea.nifs@gmail.com` を選択。なければ「別のアカウントを使用」
   - メール入力画面 → `koa800sea.nifs@gmail.com` を入力して「次へ」
   - パスワード入力画面 → 上記で読み取ったパスワードを入力して「次へ」
   - 2段階認証画面が表示されたら:
     a. LINEで通知:
        ```bash
        cd {project_root}
        python3 System/line_notify.py "🔐 Googleログイン: 2段階認証の承認をお願いします（iPhoneに通知が届いています）"
        ```
     b. 90秒待機（sleep 90）
     c. ページの状態を確認。まだ認証画面なら追加で60秒待機
   - ログイン成功 → Looker Studio に自動遷移するので、元のタスクを続行

3. koa800sea.nifs でログイン失敗した場合:
   - `kohara.kaito@team.addness.co.jp` で同じパスワードを使ってリトライ

4. 両方失敗した場合のみ:
   → ===RESULT_START===
   エラー: Googleログイン失敗（自動復旧できませんでした）
   ===RESULT_END===
   と出力して終了"""

    async def _run_looker_session_keepalive(self):
        """Looker Studio の Google セッションを維持。Chrome CDP でページを開いて閉じる。"""
        import json
        import subprocess
        import time as _time
        import urllib.request

        CHROME_PORT = 9224  # 秘書Chrome
        LOOKER_URLS = [
            "https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_evmsc9twzd",
            "https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dfv0688m0d",
        ]

        logger.info("Looker セッション維持: 開始")

        # Chrome 起動確認
        try:
            r = subprocess.run(["pgrep", "-f", "Google Chrome"],
                               capture_output=True, timeout=5)
            if r.returncode != 0:
                logger.info("Looker セッション維持: Chrome 未起動 → スキップ")
                return
        except Exception:
            return

        opened_tabs = []
        for url in LOOKER_URLS:
            try:
                req = urllib.request.Request(
                    f"http://localhost:{CHROME_PORT}/json/new?{url}")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    tab_info = json.loads(resp.read())
                    tab_id = tab_info.get("id", "")
                    if tab_id:
                        opened_tabs.append(tab_id)
            except Exception as e:
                logger.warning(f"Looker セッション維持: タブ作成失敗 - {e}")

        if not opened_tabs:
            logger.warning("Looker セッション維持: タブを開けませんでした")
            return

        # ページ読み込み待ち
        _time.sleep(20)

        # タブを閉じる
        for tab_id in opened_tabs:
            try:
                close_req = urllib.request.Request(
                    f"http://localhost:{CHROME_PORT}/json/close/{tab_id}")
                urllib.request.urlopen(close_req, timeout=10)
            except Exception:
                pass

        logger.info(f"Looker セッション維持: 完了（{len(opened_tabs)}ページ）")

    @staticmethod
    def _col_idx_to_letter(idx):
        """0-based index → Excel列文字 (A=0, B=1, ..., Z=25, AA=26, ...)"""
        result = ""
        idx += 1
        while idx > 0:
            idx, remainder = divmod(idx - 1, 26)
            result = chr(65 + remainder) + result
        return result

    # ---- 自動修復対象タスク / 修復不可エラー ----
    _REPAIRABLE_TASKS = {
        "日報自動入力", "Looker CSVダウンロード", "KPI日次インポート",
        "日報入力検証", "シート同期", "KPI夜間キャッシュ",
    }
    _NON_REPAIRABLE_ERRORS = {
        "認証エラー", "Chrome MCP 接続エラー", "Googleログイン切れ",
        "APIレート制限", "Claude Code クレジット不足",
    }

    def _check_task_health(self, task_name: str, success: bool, task_log_id: int,
                           max_turns: int, timeout: int, error_type: str = ""):
        """タスク実行後の健全性チェック。異常検知時に日向へ修復タスクを投入する。"""
        # 修復対象外タスクはスキップ
        if task_name not in self._REPAIRABLE_TASKS:
            return

        # 環境エラー（コード修正では直らない）はスキップ
        if error_type:
            for pattern in self._NON_REPAIRABLE_ERRORS:
                if pattern in error_type:
                    logger.info(f"_check_task_health: {task_name} は環境エラーのため修復対象外 ({error_type})")
                    return

        # 24時間以内に同タスクの修復を投入済みならスキップ
        last_repair = self.memory.get_state(f"last_repair_{task_name}")
        if last_repair:
            from datetime import timedelta
            try:
                last_dt = datetime.fromisoformat(last_repair)
                if datetime.now() - last_dt < timedelta(hours=24):
                    logger.info(f"_check_task_health: {task_name} は24h以内に修復投入済み。スキップ")
                    return
            except ValueError:
                pass

        diagnosis = None

        if not success:
            # 連続失敗チェック（2回以上で修復投入）
            streak = self.memory.get_task_failure_streak(task_name)
            if streak >= 2:
                recent = self.memory.get_recent_task_runs(task_name, limit=5)
                diagnosis = {
                    "task_name": task_name,
                    "trigger": "consecutive_failures",
                    "failure_streak": streak,
                    "error_type": error_type,
                    "recent_runs": [
                        {"status": r["status"], "error": r.get("error_message", ""), "at": r["started_at"]}
                        for r in recent
                    ],
                }
        else:
            # 成功だが duration > timeout * 0.8 → 次回タイムアウトの予兆
            runs = self.memory.get_recent_task_runs(task_name, limit=1)
            if runs and runs[0].get("duration_seconds"):
                duration = runs[0]["duration_seconds"]
                if duration > timeout * 0.8:
                    diagnosis = {
                        "task_name": task_name,
                        "trigger": "slow_execution",
                        "duration_seconds": duration,
                        "timeout": timeout,
                        "threshold": timeout * 0.8,
                    }

        if diagnosis:
            self._dispatch_repair_to_hinata(task_name, diagnosis)

    def _dispatch_repair_to_hinata(self, task_name: str, diagnosis: dict):
        """日向に修復タスクを投入する。"""
        import json

        HINATA_TASKS = Path(os.path.expanduser("~/agents/System/hinata/hinata_tasks.json"))

        # hinata_tasks.json に同タスクの pending repair がないか重複チェック
        if HINATA_TASKS.exists():
            try:
                existing = json.loads(HINATA_TASKS.read_text(encoding="utf-8"))
                for t in existing:
                    if (t.get("command_type") == "repair"
                            and t.get("status") == "pending"
                            and task_name in t.get("instruction", "")):
                        logger.info(f"_dispatch_repair: {task_name} の修復タスクが既にpending。スキップ")
                        return
            except (json.JSONDecodeError, IOError):
                pass

        instruction = json.dumps(diagnosis, ensure_ascii=False)
        self._add_hinata_task(HINATA_TASKS, instruction, "", "repair", source="orchestrator")

        # 重複防止タイムスタンプを記録
        self.memory.set_state(f"last_repair_{task_name}", datetime.now().isoformat())

        # Slack に検知報告（ログ目的）
        trigger = diagnosis.get("trigger", "unknown")
        try:
            from .notifier import send_slack_ai_team
            if trigger == "consecutive_failures":
                send_slack_ai_team(
                    f"🔧 *自動修復検知*: {task_name}\n"
                    f"連続{diagnosis.get('failure_streak', '?')}回失敗。日向に修復タスクを投入しました。"
                )
            elif trigger == "slow_execution":
                send_slack_ai_team(
                    f"⏱️ *予防修復検知*: {task_name}\n"
                    f"実行時間 {diagnosis.get('duration_seconds', 0):.0f}秒（閾値: {diagnosis.get('threshold', 0):.0f}秒）。"
                    f"日向に予防修復タスクを投入しました。"
                )
        except Exception as e:
            logger.warning(f"_dispatch_repair: Slack通知失敗: {e}")

        logger.info(f"_dispatch_repair: {task_name} の修復タスクを日向に投入 (trigger={trigger})")

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
                                  use_chrome=False, model="claude-sonnet-4-6"):
        """Claude Code CLI 実行ヘルパー（1回リトライ・エラー分類付き）。
        use_chrome=True のときは --chrome を渡し、秘書用ChromeのMCPでブラウザ操作を有効にする。
        model: 使用するモデル（デフォルト: claude-sonnet-4-6）
        Returns: (success: bool, output: str, error_msg: str)
        """
        import subprocess
        import os
        import time as _time

        # メトリクス記録: 開始
        task_log_id = self.memory.log_task_start(task_label)

        env = os.environ.copy()
        # launchd 環境でも node が見つかるよう PATH を保証
        path = env.get("PATH", "")
        if "/opt/homebrew/bin" not in path:
            env["PATH"] = f"/opt/homebrew/bin:{path}"
        env["CLAUDE_CONFIG_DIR"] = str(secretary_config)
        cmd = [str(claude_cmd), "-p", "--model", model,
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
                    # メトリクス記録: 成功
                    self.memory.log_task_end(task_log_id, "success", result_summary=output[:300])
                    self._check_task_health(task_label, True, task_log_id, max_turns, timeout)
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
                # メトリクス記録: 失敗
                self.memory.log_task_end(task_log_id, "error", error_message=error_detail)
                self._check_task_health(task_label, False, task_log_id, max_turns, timeout, error_detail)
                return False, result.stdout, error_detail

            except subprocess.TimeoutExpired:
                logger.error(f"{task_label}: タイムアウト ({timeout}秒, attempt {attempt+1})")
                if attempt == 0:
                    _time.sleep(60)
                    continue
                err = f"タイムアウト（{timeout // 60}分超過 × 2回）"
                self.memory.log_task_end(task_log_id, "error", error_message=err)
                self._check_task_health(task_label, False, task_log_id, max_turns, timeout, err)
                return False, "", err

            except Exception as e:
                logger.error(f"{task_label}: 例外 (attempt {attempt+1}) - {e}")
                if attempt == 0:
                    _time.sleep(60)
                    continue
                err = str(e)
                self.memory.log_task_end(task_log_id, "error", error_message=err)
                self._check_task_health(task_label, False, task_log_id, max_turns, timeout, err)
                return False, "", err

        self.memory.log_task_end(task_log_id, "error", error_message="リトライ上限到達")
        self._check_task_health(task_label, False, task_log_id, max_turns, timeout, "リトライ上限到達")
        return False, "", "リトライ上限到達"

    async def _run_daily_report_input(self):
        """日報自動入力: Looker Studioからデータ取得→日報シート書き込み→LINE報告。

        事前計算（Python側）:
        - サブスク新規会員数: sheets_manager.py で直接取得
        - 対象列: ヘッダー行から特定 → 列文字に変換
        これにより Claude Code CLI のターン消費を大幅削減。
        """
        import subprocess
        import ast
        from .notifier import send_line_notify
        from datetime import date, timedelta

        logger.info("日報自動入力: 開始")

        # プリフライトチェック（Chrome 自動起動含む）
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"日報自動入力: プリフライト失敗 - {preflight_err}")
            send_line_notify(f"日報の自動入力を始めようとしましたが、準備段階で失敗しました。\n{preflight_err}")
            return

        target_date = date.today() - timedelta(days=1)
        target_md = f"{target_date.month}/{target_date.day}"
        target_ymd = target_date.strftime('%Y-%m-%d')

        # ── 事前計算 1: サブスク新規会員数 ──
        subscription_new = 0
        subscription_err = None
        try:
            for tab_name in ["秘密の部屋（月額）", "秘密の部屋（年額）"]:
                result = subprocess.run(
                    ["python3", "System/sheets_manager.py", "read",
                     "1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70",
                     tab_name, "A1:A5000"],
                    capture_output=True, text=True, timeout=30,
                    cwd=str(project_root),
                )
                if result.returncode == 0:
                    subscription_new += result.stdout.count(target_ymd)
                else:
                    logger.warning(f"日報自動入力: サブスクシート({tab_name})読み取り失敗: {result.stderr[:100]}")
            logger.info(f"日報自動入力: サブスク新規会員数 = {subscription_new}")
        except Exception as e:
            subscription_err = str(e)
            logger.error(f"日報自動入力: サブスク事前計算失敗 - {e}")

        # ── 事前計算 2: 対象列の特定 ──
        target_col = None
        col_err = None
        try:
            header_result = subprocess.run(
                ["python3", "System/sheets_manager.py", "read",
                 "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk", "日報", "A1:JZ1"],
                capture_output=True, text=True, timeout=30,
                cwd=str(project_root),
            )
            if header_result.returncode == 0:
                match = re.search(r'行1:\s*(\[.*\])', header_result.stdout)
                if match:
                    headers = ast.literal_eval(match.group(1))
                    for i, h in enumerate(headers):
                        if str(h).strip() == target_md:
                            target_col = self._col_idx_to_letter(i)
                            break
                    if target_col:
                        logger.info(f"日報自動入力: 対象列 = {target_col}（{target_md}）")
                    else:
                        col_err = f"ヘッダーに {target_md} が見つかりません"
                        logger.error(f"日報自動入力: {col_err}")
                else:
                    col_err = "ヘッダー行のパースに失敗"
                    logger.error(f"日報自動入力: {col_err}")
            else:
                col_err = f"ヘッダー読み取り失敗: {header_result.stderr[:100]}"
                logger.error(f"日報自動入力: {col_err}")
        except Exception as e:
            col_err = str(e)
            logger.error(f"日報自動入力: 列特定の事前計算失敗 - {e}")

        # 対象列が特定できなければ中断
        if not target_col:
            send_line_notify(f"日報の自動入力を始めようとしましたが、日報シートの対象列が特定できませんでした。\n{col_err}")
            return

        # ── サブスク部分の指示 ──
        if subscription_err:
            subscription_instruction = f"""サブスク新規会員数は事前計算に失敗しました。以下のコマンドで取得してください:
```bash
cd {project_root}
python3 System/sheets_manager.py read "1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70" "秘密の部屋（月額）" "A1:A5000"
python3 System/sheets_manager.py read "1gOVSt0PDub3-W8fBglKnuUAIub3FOyv-1X8CdFEvm70" "秘密の部屋（年額）" "A1:A5000"
```
それぞれの出力から「{target_ymd}」を含む行数をカウントし合算。"""
        else:
            subscription_instruction = f"サブスク新規会員数は事前計算済み: **{subscription_new}人**（そのまま使用してください）"

        # ── CLI プロンプト（大幅簡素化） ──
        prompt = f"""あなたは甲原海人のAI秘書です。日報を自動入力してください。

## タスク
{target_date.strftime('%Y年%m月%d日')}（{target_md}）の日報データを取得し、日報シートに書き込んでください。

## 事前計算済み情報
- 対象列: **{target_col}**（日報シートの {target_md} 列）
- {subscription_instruction}

## 手順

### Step 1: Looker Studio 日別データページからデータ取得
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_evmsc9twzd
- ブラウザで開く
- javascript_tool で以下を実行してページテキストを取得:
```javascript
await new Promise(r => setTimeout(r, 10000)); document.body.innerText
```
- 取得したテキストから {target_md} の行を探し、以下の数値を読み取る:
  - 集客数、個別予約数、着金売上（確定ベース）
- テキストで数値が取得できない場合 → get_page_text で再試行
- それでも取得できない場合 → スクショ撮影して目視確認（最終手段）

### Step 2: Looker Studio 会員数ページからデータ取得
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dfv0688m0d
- ブラウザで開く
- javascript_tool で以下を実行してページテキストを取得:
```javascript
await new Promise(r => setTimeout(r, 10000)); document.body.innerText
```
- 取得したテキストからスキルプラス会員数（net change）と解約数を読み取る
- テキストで数値が取得できない場合 → get_page_text で再試行
- それでも取得できない場合 → スクショ撮影して目視確認（最終手段）

### Step 3: 日報シートに書き込み

列 = {target_col} を使い、Step 1〜2 で取得した数値と事前計算済みのサブスク新規会員数を書き込む。
writeコマンドの引数順: `write シートID セル 値 タブ名`

```bash
cd {project_root}
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}5" "【着金売上の値】" "日報"
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}7" "【集客数の値】" "日報"
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}9" "【個別予約数の値】" "日報"
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}13" "【会員数の値】" "日報"
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}14" "【解約数の値】" "日報"
python3 System/sheets_manager.py write "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "{target_col}15" "{subscription_new}" "日報"
```
※ 【】内は Step 1〜2 で取得した実際の数値に置き換えること。サブスク新規（行15）は上記の値をそのまま使用。

行4（粗利益）と行6（広告費）は計算式/別管理なので絶対に触らないこと。

### Step 4: LINE報告

取得した数値を埋め込んで報告する:
```bash
cd {project_root}
python3 System/line_notify.py "日報入力が完了しました。

集客数: XXX人
個別予約数: XX件
着金売上: ¥X,XXX,XXX
会員数: XX人（解約: X人）
サブスク新規: {subscription_new}人"
```
※ XXX 部分は Step 1〜2 で取得した実際の数値に置き換えること。

## エラー時の対応

### ブラウザ接続エラー
- ブラウザツール（tabs_context_mcp, navigate等）が使えない・タイムアウトする場合:
  → ===RESULT_START===
  エラー: Chrome MCP に接続できません。Chrome + Claude in Chrome 拡張を確認してください
  ===RESULT_END===
  と出力して終了

{self._build_google_login_instructions()}

### 数値の検証
- 全ての数値がゼロの場合は異常（データ更新遅延の可能性）。LINE報告に「⚠️ 全数値ゼロ: データ更新遅延の可能性」を追記
- 着金売上・集客数が 0 の場合は「⚠️ 異常値検出」フラグをLINE報告に追記

## 重要ルール
- 行4（粗利益）と行6（広告費）は絶対に書き込まない
- 書き込み前に取得した全数値を確認用にログ出力する

## 出力形式
===RESULT_START===
（日報入力の結果サマリー。成功なら数値一覧、エラーならエラー内容を明記）
===RESULT_END==="""

        success, output, error = self._execute_claude_code_task(
            "日報自動入力", claude_cmd, secretary_config, project_root,
            prompt, max_turns=20, timeout=600, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_daily_report_input", datetime.now().isoformat())
            if "===RESULT_START===" in output and "===RESULT_END===" in output:
                report = output.split("===RESULT_START===")[1].split("===RESULT_END===")[0].strip()
                logger.info(f"日報自動入力: 完了 - {report[:300]}")
                if "エラー" in report:
                    send_line_notify(f"日報の自動入力でエラーがありました。\n{report[:300]}")
            else:
                logger.info(f"日報自動入力: 完了（マーカーなし）- {output[-300:]}")
        else:
            # エラー種別に応じた通知
            if "ログイン" in error or "login" in error.lower():
                send_line_notify(
                    "日報の自動入力が失敗しました。Googleのログインが切れているようです。\n"
                    "Mac MiniのChromeでLooker Studioに再ログインしてください。\n"
                    "（koa800sea.nifs → kohara.kaito の順で試す）"
                )
            elif "OAuth" in error or "credential" in error.lower():
                send_line_notify(
                    f"日報の自動入力が失敗しました。秘書の認証トークンが切れています。\n"
                    f"再取得が必要です。"
                )
            elif "Chrome" in error or "MCP" in error:
                send_line_notify(
                    "日報の自動入力が失敗しました。Chromeとの接続がうまくいきませんでした。\n"
                    "Chromeの再起動が必要です。"
                )
            else:
                send_line_notify(f"日報の自動入力がリトライ後も失敗しました。\n{error[:200]}")

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
                send_line_notify(f"日報の検証でつまずきました。シートのヘッダーが読めませんでした。")
                return

            match = re.search(r'行1:\s*(\[.*\])', header_result.stdout)
            if not match:
                logger.error("日報検証: ヘッダー行のパースに失敗")
                send_line_notify("日報の検証でつまずきました。シートの構造が変わっている可能性があります。")
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
                send_line_notify("日報の検証でつまずきました。データの読み取りに失敗しています。")
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

            # 4. 結果に基づいて通知 + 自動リトライ
            if missing:
                # 既にリトライ済みなら通知のみ
                retry_done = self.memory.get_state("daily_report_retry_date") == str(date.today())
                if retry_done:
                    msg = (
                        f"{target_md}の日報がまだ入っていません（自動リトライ後も未完了）\n"
                        f"未入力: {', '.join(missing)}"
                    )
                    send_line_notify(msg)
                    logger.warning(f"日報検証: リトライ後も未入力 - {missing}")
                else:
                    # 自動リトライ実行
                    logger.info(f"日報検証: 未入力検知 {missing} → daily_report_input を自動再実行")
                    send_line_notify(
                        f"{target_md}の日報に未入力がありました。\n"
                        f"{', '.join(missing)} が空なので、自動で再入力します。"
                    )
                    self.memory.set_state("daily_report_retry_date", str(date.today()))
                    await self._run_daily_report_input()
            else:
                logger.info(f"日報検証: {target_md} の全データ入力確認OK")

        except Exception as e:
            logger.error(f"日報検証: エラー - {e}")
            send_line_notify(f"日報の検証中に想定外のエラーが出ました。\n{str(e)[:150]}")

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
                send_line_notify(f"日報リマインドの未記入チェックでエラーが出ました。")
                return

            data = _json.loads(result.stdout)

            if data.get("error"):
                logger.warning(f"日報リマインド: {data['error']}")
                send_line_notify(f"日報リマインドの確認中にエラーがありました。\n{data['error'][:150]}")
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
            send_line_notify(f"日報リマインドでデータの読み取りに失敗しました。")
        except Exception as e:
            logger.error(f"日報リマインド: エラー - {e}")
            send_line_notify(f"日報リマインド中に想定外のエラーが出ました。")

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
            f"今日の稼働報告です（{date.today().strftime('%m/%d')}）",
            f"タスク {success}/{total}件成功（{success_rate}%）",
        ]
        if error_tasks:
            report_lines.append(f"エラーあり: {', '.join(error_tasks[:5])}")

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
                f"APIの使用量が多くなっています（直近1時間: {api_calls}/{limit}回）\n"
                f"制限に近いので少し注意が必要です。"
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
                            msg = (f"Q&Aモニターが{age_hours:.0f}時間止まっていたので再起動しました。"
                                   if restarted else
                                   f"Q&Aモニターが{age_hours:.0f}時間止まっています。再起動も失敗したので手動で確認が必要です。")
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

                # 自動再起動失敗時のみ通知（成功時は通知しない）
                if not restarted:
                    state_key = "local_agent_stale_notified"
                    last_n = self.memory.get_state(state_key)
                    if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 3600:
                        send_line_notify(
                            "ローカルエージェントが止まっています。再起動も失敗したので手動で確認が必要です。"
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
                            f"KPIデータが{cache_age_hours:.0f}時間前から更新されていません。秘書の数値回答が古い可能性があります。"
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
                        f"Mac Miniのディスクが残り{free_gb:.1f}GBです（使用率{used_pct:.0f}%）。整理が必要です。"
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
                                f"Orchestratorが短時間に{recent}回再起動しています。何か問題が起きているかもしれません。"
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
            f"今週やるといいかもしれないタスクです（{priority}）\n\n"
            f"{task_text}{reason}"
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
                f"今日の予定です。\n\n"
                + "\n".join(events[:8])
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

        parts = [f"おはようございます。今日のタスク状況です。"]
        if overdue_items:
            parts.append(f"\n期限超過（{len(overdue_items)}件）")
            parts.extend(f"  {t}" for t in overdue_items[:4])
        if in_progress_items:
            parts.append(f"\n実行中")
            parts.extend(f"  {t}" for t in in_progress_items[:3])

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

        parts = [f"Addnessのタスク状況です。"]
        if overdue:
            parts.append("\n期限超過\n" + "\n".join(overdue[:5]))
        if due_today:
            parts.append("\n本日期限\n" + "\n".join(due_today[:3]))
        if due_soon:
            parts.append("\n今週期限\n" + "\n".join(due_soon[:5]))

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
                "Renderサーバーから応答がありません。LINE秘書が止まっている可能性があります。"
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
                send_line_notify("AnthropicのAPIクレジットが復旧しました。")
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
                    "AnthropicのAPIクレジットが不足しています。秘書の応答が止まっています。\n"
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
                "認証ファイルが見つかりません。Q&A監視・メール・カレンダーが動いていない可能性があります。\n"
                "MacBookから再セットアップが必要です。"
            )
            logger.error("token.json not found")
            return

        # refresh_tokenの存在確認
        try:
            with open(token_path) as f:
                token_data = json.load(f)
        except Exception as e:
            send_line_notify(f"認証ファイルの読み込みでエラーが出ました。")
            logger.error(f"Failed to read token.json: {e}")
            return

        if not token_data.get("refresh_token"):
            send_line_notify(
                "認証トークンが見つかりません。再認証が必要です。"
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
                    "Google APIの認証に失敗しました。MacBookで再認証が必要かもしれません。"
                )
                logger.error(f"OAuth health check: auth error: {result.error[:200]}")
            else:
                logger.info(f"OAuth health check: QA stats failed (non-auth): {result.error[:100]}")
        else:
            logger.info("OAuth health check OK")

        # Gmail OAuthトークンもチェック（メール確認に必要）
        gmail_tokens = {
            "personal": os.path.expanduser("~/agents/System/credentials/token_gmail_personal.json"),
            "kohara": os.path.expanduser("~/agents/System/credentials/token_gmail.json"),
        }
        for account_name, gmail_token_path in gmail_tokens.items():
            if not os.path.exists(gmail_token_path):
                send_line_notify(f"Gmail({account_name})のトークンファイルがありません。メール確認が動いていません。")
                logger.error(f"Gmail token not found: {gmail_token_path}")
                continue
            try:
                from google.oauth2.credentials import Credentials
                from google.auth.transport.requests import Request
                creds = Credentials.from_authorized_user_file(gmail_token_path)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    with open(gmail_token_path, "w") as f:
                        f.write(creds.to_json())
                    logger.info(f"Gmail({account_name}) token refreshed successfully")
                elif creds and creds.valid:
                    logger.info(f"Gmail({account_name}) token OK")
                else:
                    send_line_notify(f"Gmail({account_name})の認証が無効です。MacBookで再認証してください。\n`python3 System/mail_manager.py --account {account_name} run`")
                    logger.error(f"Gmail({account_name}) token invalid (no refresh_token or not valid)")
            except Exception as e:
                err_msg = str(e)
                if "invalid_grant" in err_msg or "revoked" in err_msg:
                    send_line_notify(f"Gmail({account_name})のトークンが無効化されています。MacBookで再認証が必要です。\n`python3 System/mail_manager.py --account {account_name} run`")
                else:
                    send_line_notify(f"Gmail({account_name})のトークン検証でエラー: {err_msg[:100]}")
                logger.error(f"Gmail({account_name}) token check failed: {err_msg[:200]}")

        # Claude Code OAuth トークンもチェック（日報自動入力に必要）
        from pathlib import Path
        secretary_config = Path.home() / ".claude-secretary"
        if secretary_config.exists():
            oauth_ok, oauth_err = self._refresh_claude_oauth(secretary_config)
            if oauth_ok:
                logger.info("Claude Code OAuth health check OK")
            else:
                send_line_notify(
                    "秘書の認証トークンに問題があります。日報の自動入力が失敗する可能性があります。"
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
            f"今週の稼働まとめです（{date.today().strftime('%m/%d')}）",
            f"タスク {success}/{total}件成功（{success_rate}%）",
            f"Q&A通知: {qa_count}件",
        ]
        if error_tasks:
            parts.append(f"エラーあり: {', '.join(error_tasks[:4])}")
        if data_age_note:
            parts.append(data_age_note)

        ok = send_line_notify("\n".join(parts))
        logger.info(f"Weekly stats sent: {total} tasks, {success_rate}% success, {qa_count} Q&As")

        # 今週のボトルネック分析（actionable-tasks.md から Claude で分析）
        await self._notify_weekly_bottleneck(send_line_notify)

        # フォローアップ提案（contact_state.json から長期未接触の人を検出）
        await self._check_follow_up_suggestions(send_line_notify)

    async def _notify_weekly_bottleneck(self, send_line_notify):
        """今週のボトルネックをClaude Code CLIで分析してLINE通知"""
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
            ok, claude_cmd, secretary_config, project_root, err = self._prepare_claude_env()
            if not ok:
                logger.debug(f"Weekly bottleneck: CLI準備失敗: {err}")
                return

            prompt = f"""あなたはスキルプラス事業の戦略アドバイザーです。簡潔に要点を伝えてください。

以下のAddnessタスク状況を分析し、今週の最大のボトルネックを1〜2件特定してください。

【タスク状況】
{content}

【出力形式（200文字以内）】
🔍 今週のボトルネック:
・[最重要課題] 〜 理由を1行で
・[次点] 〜 理由を1行で（あれば）

具体的で行動につながる内容にしてください。"""

            success, analysis, error = self._execute_claude_code_task(
                "weekly_bottleneck", claude_cmd, secretary_config,
                project_root, prompt, max_turns=3, timeout=120,
            )
            if success and analysis:
                ok = send_line_notify(analysis)
                if ok:
                    logger.info("Weekly bottleneck analysis sent")
            else:
                logger.debug(f"Weekly bottleneck: CLI失敗: {error}")
        except Exception as e:
            logger.debug(f"Weekly bottleneck analysis error: {e}")

    async def _run_weekly_content_suggestions(self):
        """毎週水曜10:00: 最新AIニュースを分析してスキルプラスのコンテンツ更新提案をLINE通知"""
        from .notifier import send_line_notify
        from datetime import date

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
            ok_env, claude_cmd, secretary_config, project_root, err = self._prepare_claude_env()
            if not ok_env:
                logger.error(f"weekly_content_suggestions: CLI準備失敗: {err}")
                return

            _content_exec_rules = _build_execution_rules_compact()

            prompt = f"""あなたはスキルプラス（AI副業教育コース）のコンテンツディレクターです。{_content_exec_rules}

以下の最新AIニュースを踏まえて、スキルプラスのカリキュラム・教材の更新提案をしてください。

【最新AIニュース（直近）】
{news_content}

【出力形式】（400文字以内・LINEで読みやすい形式）
📚 コンテンツ更新提案 ({today_str})

更新優先度が高いもの（2〜3件）:
1. [セクション/教材名]: [追加・修正内容を1行で]
   → 理由: [そのニュースとの関連を1行で]

受講生にとって今すぐ価値がある内容にしてください。"""

            success, suggestions, error = self._execute_claude_code_task(
                "weekly_content_suggestions", claude_cmd, secretary_config,
                project_root, prompt, max_turns=3, timeout=120,
            )
            if success and suggestions:
                message = suggestions
                task_id = self.memory.log_task_start("weekly_content_suggestions")
                ok = send_line_notify(message)
                self.memory.log_task_end(task_id, "success" if ok else "error",
                                         result_summary=suggestions[:100])
                logger.info("Weekly content suggestions sent")
            else:
                logger.error(f"weekly_content_suggestions: CLI失敗: {error}")
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
        parts = ["しばらく連絡を取っていない方がいます。"]
        for days, name, category in suggestions[:5]:
            parts.append(f"  {name}さん（{category}）— {days}日")

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

            ok = send_line_notify(
                f"{label}の期限まで残り{delta}日です（{deadline.strftime('%m/%d')}）\n"
                f"{detail}"
            )
            if ok:
                logger.info(f"Special reminder sent: {label} in {delta} days")

    def _find_missing_csv_dates(self, csv_dir, lookback_days=7):
        """直近N日間でCSVが不足している日付リストを返す（古い順）。"""
        from pathlib import Path
        from datetime import date, timedelta

        csv_dir = Path(csv_dir)
        missing = []
        for i in range(lookback_days, 1, -1):  # lookback_days日前 → 2日前（古い順）
            d = date.today() - timedelta(days=i)
            d_str = d.strftime("%Y-%m-%d")
            csv_path = csv_dir / f"{d_str}_アドネス全体数値_媒体・ファネル別データ_表.csv"
            if not csv_path.exists() or csv_path.stat().st_size <= 100:
                missing.append(d)
        return missing

    async def _run_looker_csv_download(self):
        """毎日11:30: Looker Studio CSVダウンロード（前々日分 + 不足分バックフィル）。秘書がClaude Code + Chrome MCPで実行。"""
        from pathlib import Path
        from datetime import date, timedelta
        from .notifier import send_line_notify

        logger.info("Looker CSV ダウンロード: 開始")

        # プリフライトチェック（Chrome 自動起動含む）
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"Looker CSV ダウンロード: プリフライト失敗 - {preflight_err}")
            send_line_notify(f"Looker CSVのダウンロード準備で失敗しました。\n{preflight_err}")
            return

        csv_dir = Path.home() / "Desktop" / "Looker Studio CSV"
        csv_dir.mkdir(parents=True, exist_ok=True)

        # 直近7日間の不足日付を検出（バックフィル）
        missing_dates = self._find_missing_csv_dates(csv_dir, lookback_days=7)

        if not missing_dates:
            logger.info("Looker CSV ダウンロード: 不足なし → シート同期のみ実行")
            await self._run_csv_sheet_sync_after_download(project_root)
            return

        logger.info(f"Looker CSV ダウンロード: 不足 {len(missing_dates)} 日分 → {[d.isoformat() for d in missing_dates]}")

        # 複数日分のダウンロード手順を生成
        date_steps = ""
        for idx, d in enumerate(missing_dates, 1):
            d_str = d.strftime("%Y-%m-%d")
            csv_filename = f"{d_str}_アドネス全体数値_媒体・ファネル別データ_表.csv"
            date_steps += f"""
### 日付 {idx}: {d.strftime('%Y年%m月%d日')}
1. 日付フィルターをクリック → 詳細設定で開始日・終了日を両方「{d_str}」に設定 → 適用
2. テーブルを右クリック → 「グラフをエクスポート」または「データのエクスポート」→ CSV → エクスポート
3. ダウンロード完了を待つ
4. ファイル移動:
```bash
latest_csv=$(ls -t ~/Downloads/*.csv 2>/dev/null | head -1)
if [ -n "$latest_csv" ]; then
    mv "$latest_csv" "{csv_dir}/{csv_filename}"
    echo "移動完了: {csv_dir}/{csv_filename}"
fi
```
5. 確認:
```bash
ls -la "{csv_dir}/{csv_filename}"
head -3 "{csv_dir}/{csv_filename}"
```
"""

        prompt = f"""あなたは甲原海人のAI秘書です。Looker StudioからCSVをダウンロードしてください。

## タスク
不足している {len(missing_dates)} 日分のCSVをダウンロードする。

## 手順

### Step 1: Looker Studio を開く
- URL: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dsqvinv6zd
- ページ名: 媒体・ファネル別データ
- ブラウザで開いて読み込み完了を待つ

### Step 2: 以下の日付ごとにCSVをダウンロード
**重要: 1日分ダウンロードしたら、同じページのまま日付フィルターだけ変更して次をダウンロードする。ページ遷移不要。**
{date_steps}

## エラー時の対応

### ブラウザ接続エラー
- ブラウザツール（tabs_context_mcp, navigate等）が使えない場合:
  → ===RESULT_START===
  エラー: Chrome MCP に接続できません
  ===RESULT_END===
  と出力して終了

{self._build_google_login_instructions()}

### ダウンロード失敗
- CSVエクスポートボタンが見つからない場合:
  → スクショを撮影して画面状態をログに記録
  → テーブル上のメニューアイコンやShift+右クリックなど代替手段を試す
- **1日分が失敗しても、残りの日付は続行してください**

## 出力形式
===RESULT_START===
（ダウンロード結果: 各日付のファイルパス・行数。エラーがあった日付はエラー内容を明記）
===RESULT_END==="""

        # 複数日ダウンロードの場合はターン数・タイムアウトを増やす
        extra_turns = min(len(missing_dates) - 1, 4) * 8  # 追加日分のターン
        max_turns = 25 + extra_turns
        timeout = 480 + min(len(missing_dates) - 1, 4) * 180  # 追加日分のタイムアウト

        success, output, error = self._execute_claude_code_task(
            "Looker CSVダウンロード", claude_cmd, secretary_config, project_root,
            prompt, max_turns=max_turns, timeout=timeout, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_looker_csv_download", datetime.now().isoformat())
            if "===RESULT_START===" in output and "===RESULT_END===" in output:
                report = output.split("===RESULT_START===")[1].split("===RESULT_END===")[0].strip()
                logger.info(f"Looker CSV ダウンロード: 完了 - {report[:300]}")
                if "エラー" in report:
                    send_line_notify(f"Looker CSVダウンロードでエラーがありました。\n{report[:300]}")
                # エラーの有無に関わらずシート同期を実行（一部成功している可能性）
                await self._run_csv_sheet_sync_after_download(project_root)
            else:
                logger.info(f"Looker CSV ダウンロード: 完了（マーカーなし）- {output[-300:]}")
                await self._run_csv_sheet_sync_after_download(project_root)

            # ダウンロード後に残っている不足を確認 → 通知
            still_missing = self._find_missing_csv_dates(csv_dir, lookback_days=7)
            if still_missing:
                dates_str = ", ".join(d.isoformat() for d in still_missing)
                send_line_notify(f"Looker CSVダウンロード後も {len(still_missing)} 日分が不足: {dates_str}")
                logger.warning(f"Looker CSV: still missing after download: {dates_str}")
        else:
            send_line_notify(f"Looker CSVのダウンロードがリトライ後も失敗しました。\n{error[:200]}")

    async def _run_csv_sheet_sync_after_download(self, project_root):
        """CSVダウンロード後にcsv_sheet_syncを実行して元データシートを更新する。"""
        import subprocess
        from .notifier import send_line_notify
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
                send_line_notify("CSVからシートへの同期が失敗しました。KPIデータが更新されていない可能性があります。")
        except Exception as e:
            logger.warning(f"csv_sheet_sync 例外: {e}")
            send_line_notify("CSVからシートへの同期中にエラーが出ました。")

    async def _run_kpi_daily_import(self):
        """毎日12:00: 元データの全未処理分を投入（day-2に限らずバックフィル）"""
        from .notifier import send_line_notify

        # process は元データの「完了」エントリを全て検出して日別に投入する
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
                f"KPIデータの更新が完了しました。{cache_status}"
            )
        elif result.success and "投入対象なし" in result.output:
            logger.info(f"KPI process: no pending entries to import")
        else:
            # 投入失敗を通知
            logger.warning(f"KPI process result: {result.output[:200]}")
            send_line_notify(
                f"KPIデータの投入でエラーが出ました。\n{result.output[:200] if result.output else result.error[:200] if result.error else '不明'}"
            )

    async def _run_sheets_sync(self):
        """毎日6:30: 管理シートのCSVキャッシュを更新 → KPIキャッシュも再構築"""
        result = await self._execute_tool("sheets_sync", tools.sheets_sync)
        if result.success:
            logger.info(f"Sheets sync completed: {result.output[:200]}")
            cache_result = await self._execute_tool("kpi_cache_build", tools.kpi_cache_build)
            if cache_result.success:
                logger.info(f"KPI cache rebuilt: {cache_result.output[:200]}")
                from .notifier import send_line_notify
                send_line_notify("管理シートの同期とKPIキャッシュの更新が完了しました。")
            else:
                logger.warning(f"KPI cache build failed: {cache_result.error[:200] if cache_result.error else 'unknown'}")
                from .notifier import send_line_notify
                send_line_notify(
                    "管理シートの同期はできましたが、KPIキャッシュの更新に失敗しました。秘書の数値が古い可能性があります。"
                )

    async def _run_cdp_sync(self):
        """2時間ごと: CDP同期（データソース→マスタ + 経路別タブ→集客データ）"""
        import subprocess
        import re as _re
        script = str(Path(__file__).resolve().parent.parent.parent / "cdp_sync.py")
        try:
            proc = subprocess.run(
                ["python3", script, "sync"],
                capture_output=True, text=True, timeout=600,
                cwd=str(Path(script).parent),
            )
            output = proc.stdout if proc.stdout else ""
            if proc.returncode == 0:
                logger.info(f"CDP sync completed: {output[-500:]}")
                # 同期結果を解析してLINE通知（変更があった場合のみ）
                changes = []
                m = _re.search(r"更新: (\d+)件", output)
                if m and int(m.group(1)) > 0:
                    changes.append(f"マスタ更新 {m.group(1)}件")
                m = _re.search(r"新規: (\d+)件", output)
                if m and int(m.group(1)) > 0:
                    changes.append(f"マスタ新規 {m.group(1)}件")
                m = _re.search(r"(\d+) 件を集客データシートに追加", output)
                if m:
                    changes.append(f"集客データ {m.group(1)}件追加")
                m = _re.search(r"集客データシートから(\d+)行削除", output)
                if m:
                    changes.append(f"集客データ {m.group(1)}件昇格削除")
                # ソースエラーの検出（個別ソースの停止）
                error_lines = _re.findall(r"エラー: (\d+)件", output)
                error_count = int(error_lines[0]) if error_lines else 0
                aborted = _re.findall(r"ソース変更により中断: (\d+)件", output)
                aborted_count = int(aborted[0]) if aborted else 0
                if error_count > 0 or aborted_count > 0:
                    changes.append(f"エラー {error_count + aborted_count}件")
                # 未同期ソースの検出（鮮度チェック）
                stale_lines = _re.findall(r"  - (.+)", output)
                stale_lines = [s for s in stale_lines if "未同期" in s or "日未同期" in s]
                if stale_lines:
                    changes.append(f"未同期ソース {len(stale_lines)}件")
                if changes:
                    from .notifier import send_line_notify
                    msg = f"CDP同期完了: {' / '.join(changes)}"
                    alerts = []
                    if error_count > 0 or aborted_count > 0:
                        alerts.append("🔴 ソースエラーが発生。データソース管理のステータスを確認してください")
                    if stale_lines:
                        alerts.append("⚠️ 未同期ソース:\n" + "\n".join(
                            f"・{s}" for s in stale_lines[:5]))
                    if alerts:
                        msg += "\n\n" + "\n\n".join(alerts)
                    send_line_notify(msg)
            else:
                error = proc.stderr[-300:] if proc.stderr else ""
                logger.warning(f"CDP sync failed: {error}")
                from .notifier import send_line_notify
                send_line_notify(f"CDP同期でエラーが発生しました: {error[:200]}")
        except subprocess.TimeoutExpired:
            logger.warning("CDP sync timed out after 10 minutes")
            from .notifier import send_line_notify
            send_line_notify("CDP同期がタイムアウトしました（10分）")

    async def _run_kpi_nightly_cache(self):
        """毎晩22:00: KPIキャッシュを再生成（AI秘書が夜間も最新データを参照できるように）"""
        result = await self._execute_tool("kpi_cache_build", tools.kpi_cache_build)
        if result.success:
            logger.info(f"Nightly KPI cache rebuilt: {result.output[:200]}")
        else:
            logger.warning(f"Nightly KPI cache build failed: {result.error[:200] if result.error else 'unknown'}")
            from .notifier import send_line_notify
            send_line_notify("夜間のKPIキャッシュ更新に失敗しました。")

    async def _run_kpi_anomaly_check(self):
        """KPI投入後: 異常検知 → LINE通知（異常がある場合のみ）"""
        result = await self._execute_tool("kpi_anomaly_check", tools.kpi_anomaly_check)
        if result.success:
            output = result.output.strip()
            if "異常なし" in output:
                logger.info("KPI anomaly check: no anomalies")
            elif output:
                # 異常検知あり → LINE通知
                from .notifier import send_line_notify
                send_line_notify(output)
                logger.info(f"KPI anomaly detected and notified: {output[:200]}")
        else:
            logger.warning(f"KPI anomaly check failed: {result.error[:200] if result.error else 'unknown'}")

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
                send_line_notify(f"Git同期が復旧しました（{self._git_pull_consecutive_failures}回失敗後）。")
            self._git_pull_consecutive_failures = 0
        else:
            self._git_pull_consecutive_failures += 1
            # 6回連続失敗（=30分）で初回通知、以降1時間ごと
            if self._git_pull_consecutive_failures == 6 or (self._git_pull_consecutive_failures > 6 and self._git_pull_consecutive_failures % 12 == 0):
                from .notifier import send_line_notify
                send_line_notify(
                    f"Git同期が{self._git_pull_consecutive_failures}回連続で失敗しています。Mac Miniにコードの変更が反映されていません。"
                )

    async def _run_daily_group_digest(self):
        """毎日21:00: グループLINEの1日分のメッセージをClaude Code CLI分析→秘書グループに報告"""
        import json as _json
        from .notifier import send_line_notify
        from datetime import date

        today_str = date.today().isoformat()
        result = await self._execute_tool("fetch_group_log", tools.fetch_group_log, date=today_str)
        if not result.success or not result.output:
            logger.warning(f"daily_group_digest: failed to fetch group log: {result.error}")
            send_line_notify("グループLINEのログ取得に失敗しました。ダイジェストを作れませんでした。")
            return

        try:
            data = _json.loads(result.output)
        except _json.JSONDecodeError:
            logger.error("daily_group_digest: invalid JSON from group log")
            send_line_notify("グループLINEのログデータがうまく読めませんでした。")
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
            ok_env, claude_cmd, secretary_config, project_root, env_err = self._prepare_claude_env()
            if not ok_env:
                raise RuntimeError(f"CLI準備失敗: {env_err}")

            prompt = f"""あなたはスキルプラス事業のAI秘書です。甲原海人（代表・マーケティング責任者）向けに、LINEグループの1日の会話を簡潔に報告してください。

以下は今日のLINEグループのメッセージログです。
甲原さんが把握すべき内容を簡潔にまとめてください。

{log_text}

【出力形式】（500文字以内・LINEメッセージで読みやすい形式）
グループごとに:
・要約（誰が何について話したか）
・メンバーの活動度やテンション（気になる点があれば）
・甲原さんがアクションすべき事項（あれば）

特に報告すべき内容がないグループは省略してOKです。"""

            success, cli_output, error = self._execute_claude_code_task(
                "daily_group_digest", claude_cmd, secretary_config,
                project_root, prompt, max_turns=3, timeout=120,
            )
            if success and cli_output:
                analysis = cli_output
            else:
                raise RuntimeError(f"CLI失敗: {error}")
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
            f"今日のグループLINEまとめです（{total_messages}件）\n\n"
            f"{analysis}"
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
            f"週次プロファイル学習が完了しました。\n"
            f"更新: {updated_count}名 / スキップ: {skipped_count}名\n"
            f"{details_section}"
            f"{style_line}{comm_line}"
        )
        send_line_notify(message)
        self.memory.log_task_end(
            task_id, "success",
            result_summary=f"Updated {updated_count} profiles, skipped {skipped_count}, style_rules={style_rules_count}, comm_updated={len(comm_updated_names)}"
        )
        logger.info(f"weekly_profile_learning completed: {updated_count} updated, {skipped_count} skipped, style_rules={style_rules_count}, comm_updated={len(comm_updated_names)}")

    async def _run_repair_check(self):
        # 2026-03-02 API消費削減のため無効化。手動修復は claude -p で代替。
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
    def _add_hinata_task(tasks_path: Path, instruction: str, slack_ts: str,
                         command_type: str, source: str = "slack"):
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
            "source": source,
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
        lines = [f"Slack #ai-team に新着が{len(human_msgs)}件あります。\n"]
        for msg in human_msgs[:10]:
            text_preview = msg["text"][:100]
            lines.append(f"[{msg['datetime']}] {msg['user']}: {text_preview}")

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
                "今日は #ai-team で日向からの発言がなかったです。まだ慣れていないだけかもしれませんが、一応共有します。"
            )
        elif silent_days == 3:
            send_line_notify(
                "3日間 #ai-team で日向の発言がありません。声をかけたほうがいいかもしれません。"
            )
        elif silent_days >= 7 and silent_days % 7 == 0:
            send_line_notify(
                f"{silent_days}日間 #ai-team で日向の発言がありません。何か問題が起きているかもしれません。"
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

以下のマーカーで囲んだJSON形式で返してください（マーカー行以外のテキストは出力しないでください）:
===JSON_START===
{{"memory": "hinata_memory.mdの全文", "report": "Slack投稿テキスト"}}
===JSON_END===
"""
            try:
                ok_env, claude_cmd, secretary_config, project_root, env_err = self._prepare_claude_env()
                if not ok_env:
                    raise RuntimeError(f"CLI準備失敗: {env_err}")

                success, result_text, cli_error = self._execute_claude_code_task(
                    "weekly_hinata_memory", claude_cmd, secretary_config,
                    project_root, prompt, max_turns=3, timeout=180,
                )
                if not success:
                    raise RuntimeError(f"CLI失敗: {cli_error}")

                # ===JSON_START=== / ===JSON_END=== マーカーでJSON抽出
                if "===JSON_START===" in result_text and "===JSON_END===" in result_text:
                    result_text = result_text.split("===JSON_START===", 1)[1].split("===JSON_END===", 1)[0].strip()
                # フォールバック: ```json ... ``` で囲まれていたら剥がす
                elif "```json" in result_text:
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
                f"自律ワークが完了しました。\n\n"
                f"{result_section[:500]}"
            )
            send_line_notify(report)
            logger.info(f"秘書自律ワーク: 完了 - {task_name}")
        else:
            # 自律ワークの失敗は静かにログのみ（定常業務ではないため通知しない）
            logger.error(f"秘書自律ワーク: 失敗 - {error}")

    # ================================================================
    # 秘書ゴール進行モード
    # ================================================================

    def _is_free_for_goal_progress(self) -> bool:
        """空き時間判定。定常業務の時間帯やクールダウン中は False を返す。"""
        now = datetime.now()
        h, m = now.hour, now.minute
        t = h * 60 + m  # 分換算

        # 深夜・早朝（22:00-07:00）はスキップ
        if h >= 22 or h < 7:
            logger.debug("ゴール進行: 深夜・早朝 → スキップ")
            return False

        # 定常業務の時間帯（±15分バッファ）をブロック
        blocked_ranges = [
            (8 * 60 + 10, 9 * 60 + 35),   # 08:10-09:35: OAuth→日報入力→日報検証
            (11 * 60 + 15, 12 * 60 + 15),  # 11:15-12:15: Looker CSV→KPIインポート
            (20 * 60 + 45, 21 * 60 + 25),  # 20:45-21:25: 日次レポート
        ]
        for start, end in blocked_ranges:
            if start <= t <= end:
                logger.debug(f"ゴール進行: 定常業務時間帯 ({start//60}:{start%60:02d}-{end//60}:{end%60:02d}) → スキップ")
                return False

        # 前回実行から20分以内は再実行しない
        last_run = self.memory.get_state("goal_progress_last_run")
        if last_run:
            try:
                last_dt = datetime.fromisoformat(last_run)
                elapsed = (now - last_dt).total_seconds()
                if elapsed < 1200:  # 20分 = 1200秒
                    logger.debug(f"ゴール進行: クールダウン中（前回から{elapsed/60:.0f}分）→ スキップ")
                    return False
            except (ValueError, TypeError):
                pass

        return True

    def _load_goal_progress_state(self) -> dict:
        """MemoryStore からゴール進行の状態を復元する。"""
        import json as _json
        raw = self.memory.get_state("goal_progress_state")
        if raw:
            try:
                return _json.loads(raw)
            except Exception:
                pass
        return {
            "current_phase": "check_goal",
            "completion_criteria": [],
            "action_items": [],
            "current_action_index": 0,
            "cycle_count": 0,
            "last_action_result": "",
            "consecutive_failures": 0,
        }

    def _save_goal_progress_state(self, state: dict):
        """MemoryStore にゴール進行の状態を保存する。"""
        import json as _json
        self.memory.set_state("goal_progress_state", _json.dumps(state, ensure_ascii=False))

    def _record_secretary_action(self, cycle: int, result: str):
        """秘書のアクション履歴を Master/learning/secretary_action_log.json に記録（最大50件）。"""
        import json as _json
        from pathlib import Path

        log_path = Path(
            self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        ).expanduser() / "learning" / "secretary_action_log.json"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        entries = []
        if log_path.exists():
            try:
                entries = _json.loads(log_path.read_text(encoding="utf-8"))
            except Exception:
                entries = []

        entries.append({
            "cycle": cycle,
            "timestamp": datetime.now().isoformat(),
            "result": result[:500],
        })
        entries = entries[-50:]  # 最新50件を保持

        tmp = log_path.with_suffix(".tmp")
        tmp.write_text(_json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(log_path)

    def _build_secretary_learning_context(self) -> str:
        """プロンプト注入用の学習コンテキストを構築する。"""
        import json as _json
        from pathlib import Path

        sections = []

        # 1. 甲原さんの行動ルール（既存の関数を再利用）
        rules = _build_execution_rules_compact()
        if rules:
            sections.append(rules)

        master_dir = Path(
            self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        ).expanduser()

        # 2. 直近5件のアクション履歴
        log_path = master_dir / "learning" / "secretary_action_log.json"
        if log_path.exists():
            try:
                entries = _json.loads(log_path.read_text(encoding="utf-8"))
                recent = entries[-5:]
                if recent:
                    lines = [f"- サイクル#{e['cycle']} ({e['timestamp'][:16]}): {e['result'][:150]}" for e in recent]
                    sections.append("\n### 直近のアクション履歴\n" + "\n".join(lines))
            except Exception:
                pass

        # 3. 秘書の学習記憶
        memory_path = master_dir / "learning" / "secretary_memory.md"
        if memory_path.exists():
            try:
                content = memory_path.read_text(encoding="utf-8").strip()
                if content:
                    sections.append(f"\n### 秘書の学習記憶\n{content[:1000]}")
            except Exception:
                pass

        return "\n".join(sections)

    def _parse_goal_progress_result(self, output: str, prev_state: dict) -> dict:
        """Claude Code 出力をパースしてゴール進行状態を更新する。"""
        import json as _json
        state = dict(prev_state)

        # ===GOAL_PROGRESS_START=== ... ===GOAL_PROGRESS_END=== を抽出
        start_marker = "===GOAL_PROGRESS_START==="
        end_marker = "===GOAL_PROGRESS_END==="
        if start_marker in output and end_marker in output:
            block = output.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
            try:
                parsed = _json.loads(block)
                if "phase" in parsed:
                    state["current_phase"] = parsed["phase"]
                if "completion_criteria" in parsed:
                    state["completion_criteria"] = parsed["completion_criteria"]
                if "action_items" in parsed:
                    state["action_items"] = parsed["action_items"]
                if "current_action_index" in parsed:
                    state["current_action_index"] = parsed["current_action_index"]
                if "result_summary" in parsed:
                    state["last_action_result"] = parsed["result_summary"]
            except _json.JSONDecodeError:
                # JSON でなくても result_summary だけ拾う
                state["last_action_result"] = block[:300]

        state["cycle_count"] = prev_state.get("cycle_count", 0) + 1
        return state

    def _build_goal_progress_prompt(self, state: dict, learning_context: str) -> str:
        """秘書ゴール進行モードのプロンプトを構築する。"""
        from pathlib import Path

        now = datetime.now().strftime("%Y/%m/%d %H:%M")
        cycle = state.get("cycle_count", 0)
        phase = state.get("current_phase", "check_goal")
        last_result = state.get("last_action_result", "なし（初回）")
        criteria = state.get("completion_criteria", [])
        actions = state.get("action_items", [])
        action_idx = state.get("current_action_index", 0)

        project_root = Path(self.config.get("paths", {}).get("repo_root", "~/agents")).expanduser()
        creds_file = project_root / "System" / "credentials" / "kohara_google.txt"

        # 進捗情報
        progress_section = ""
        if criteria:
            criteria_str = "\n".join([f"  - {c}" for c in criteria])
            progress_section += f"\n### 完了基準\n{criteria_str}\n"
        if actions:
            action_lines = []
            for i, a in enumerate(actions):
                mark = "✅" if i < action_idx else ("▶️" if i == action_idx else "⬜")
                action_lines.append(f"  {mark} {i+1}. {a}")
            progress_section += f"\n### アクション一覧（進捗）\n" + "\n".join(action_lines) + "\n"

        prompt = f"""あなたは甲原海人のAI秘書です。定常業務がない空き時間なので、Addnessの「定常業務の自動化」ゴールを自律的に進めてください。

## 現在の状態

現在: {now} / サイクル: #{cycle} / フェーズ: {phase}
前回の結果: {last_result}
{progress_section}
{learning_context}

## ゴール進行の手順

あなたは以下のフェーズに沿って動きます。現在のフェーズ「{phase}」から再開してください。

### フェーズ: check_goal
1. `tabs_context_mcp` でタブ情報を取得
2. `tabs_create_mcp` で新しいタブを作成
3. `navigate` で Addness のゴールページに遷移:
   https://app.addness.co.jp/goals/01JMCKB7NB5B4X3RJDSZ5QZ6ZC
4. `read_page` でゴールの状態・アクション・コメントを確認
5. 現状を把握したら次のフェーズへ

### フェーズ: define_criteria
1. ゴールの内容を踏まえて、具体的な「完了基準」を3〜5個定義する
2. 完了基準は測定可能で、1つのサイクル（15分）で進められる粒度にする

### フェーズ: list_actions
1. 完了基準を達成するための具体的なアクション一覧を作成する
2. 各アクションは1サイクル（15分）以内で完了できる粒度にする
3. 優先度順に並べる

### フェーズ: execute
1. 未完了アクションの中から次のアクション（index={action_idx}）を1つ実行する
2. コード修正・ファイル作成・Web調査・ブラウザ操作など、必要な手段を使って実行する
3. 実行後、結果を記録する
4. 全アクション完了時は check_goal に戻る

### フェーズ: report
1. 今回のサイクルで何をしたか・何が分かったか・次に何が必要かをまとめる
2. check_goal に戻る

## ブラウザ操作（Chrome MCP）

1. **タブ確認**: `mcp__claude-in-chrome__tabs_context_mcp`
2. **新規タブ**: `mcp__claude-in-chrome__tabs_create_mcp`
3. **ページ遷移**: `mcp__claude-in-chrome__navigate`
4. **ページ読み取り**: `mcp__claude-in-chrome__read_page`
5. **クリック/入力**: `mcp__claude-in-chrome__find`
6. **フォーム入力**: `mcp__claude-in-chrome__form_input`
7. **JavaScript**: `mcp__claude-in-chrome__javascript_tool`
8. **テキスト取得**: `mcp__claude-in-chrome__get_page_text`

## Addness ログイン

ログインが必要な場合:
1. 認証情報を読み込む: `cat {creds_file}`
2. koa800sea.nifs@gmail.com でGoogleログイン
3. 2段階認証が出たら:
   ```bash
   cd {project_root}
   python3 System/line_notify.py "🔐 Googleログイン: 2段階認証の承認をお願いします"
   ```
   90秒待機 → 確認

## 制約

- **Addnessにコメントを投稿しない**（確認・報告はLINE経由で行う）
- **決済しない**（金銭が発生する操作は禁止）
- **承認が必要な作業**（外部へのメッセージ送信、本番環境変更等）は実行せず、LINEで甲原さんに確認する
- **1サイクル最大15分** で区切る。完了しなくても途中経過を記録して終了する

## 出力フォーマット

最後に必ず以下の形式で出力してください:

===GOAL_PROGRESS_START===
{{
  "phase": "(次のフェーズ名: check_goal / define_criteria / list_actions / execute / report)",
  "completion_criteria": ["基準1", "基準2"],
  "action_items": ["アクション1", "アクション2"],
  "current_action_index": 0,
  "result_summary": "今回やったことの要約（3行以内）"
}}
===GOAL_PROGRESS_END===
"""
        return prompt

    async def _run_secretary_goal_progress(self):
        """秘書ゴール進行モード: 空き時間にAddnessのゴールを自律的に進める。"""
        from .notifier import send_line_notify

        logger.info("秘書ゴール進行: 開始チェック")

        # 空き時間判定
        if not self._is_free_for_goal_progress():
            return

        # プリフライトチェック（Chrome + OAuth）
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.warning(f"秘書ゴール進行: プリフライト失敗 → スキップ - {preflight_err}")
            return

        logger.info("秘書ゴール進行: 実行開始")
        self.memory.set_state("goal_progress_last_run", datetime.now().isoformat())

        # 状態復元 + 学習コンテキスト構築
        state = self._load_goal_progress_state()
        learning_context = self._build_secretary_learning_context()

        # プロンプト構築
        prompt = self._build_goal_progress_prompt(state, learning_context)

        # Claude Code 実行
        success, output, error = self._execute_claude_code_task(
            "秘書ゴール進行", claude_cmd, secretary_config,
            project_root, prompt, max_turns=30, timeout=900,
            use_chrome=True,
        )

        if success:
            # 結果パース → 状態更新
            new_state = self._parse_goal_progress_result(output, state)
            new_state["consecutive_failures"] = 0
            self._save_goal_progress_state(new_state)

            # アクション記録
            result_summary = new_state.get("last_action_result", "")
            self._record_secretary_action(new_state["cycle_count"], result_summary)

            # LINE報告
            now_str = datetime.now().strftime("%H:%M")
            report = (
                f"ゴール進行が完了しました（サイクル#{new_state['cycle_count']}）\n\n"
                f"{result_summary[:400]}"
            )
            send_line_notify(report)
            logger.info(f"秘書ゴール進行: 完了 - サイクル#{new_state['cycle_count']}")
        else:
            # 失敗 → 連続失敗カウント
            state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
            self._save_goal_progress_state(state)

            logger.error(f"秘書ゴール進行: 失敗 ({state['consecutive_failures']}回連続) - {error}")

            # 連続3回失敗でLINE通知
            if state["consecutive_failures"] >= 3:
                send_line_notify(
                    f"秘書のゴール進行が{state['consecutive_failures']}回連続で失敗しています。\n"
                    f"{error[:200]}"
                )
                # カウントリセット（通知後は再カウント）
                state["consecutive_failures"] = 0
                self._save_goal_progress_state(state)

    async def _run_monthly_invoice_submission(self):
        """毎月3日: 請求書作成・提出（INVOY → Google Forms → Drive）。

        Skills/5_数値・業務/請求書提出_アドネス.md のワークフローに従い、
        Claude Code CLI + Chrome MCP でブラウザ操作を行う。
        甲原さんの承認ゲート（LINE OK返信）を含むため、
        承認待ちの間は中断し、承認後に手動再開が必要。
        """
        import subprocess
        from .notifier import send_line_notify
        from datetime import date

        logger.info("請求書提出: 開始")

        # プリフライトチェック
        ok, claude_cmd, secretary_config, project_root, preflight_err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"請求書提出: プリフライト失敗 - {preflight_err}")
            send_line_notify(f"請求書の自動提出を始めようとしましたが、準備段階で失敗しました。\n{preflight_err}")
            return

        today = date.today()
        # 請求対象は前月
        if today.month == 1:
            target_year = today.year - 1
            target_month = 12
        else:
            target_year = today.year
            target_month = today.month - 1

        # 支払月（当月）のヘッダー表記: YY/MM 末払い
        payment_header = f"{today.year % 100}/{today.month:02d}"

        # ── 事前計算: スプレッドシートから報酬単価を取得 ──
        unit_price = None
        price_err = None
        try:
            result = subprocess.run(
                ["python3", "System/sheets_manager.py", "read",
                 "1Bmbeglbhf62NeiJUHpai63DITrMDC3WSr09jJD8YhaM",
                 "Sheet1", "A4:Z5"],
                capture_output=True, text=True, timeout=30,
                cwd=str(project_root),
            )
            if result.returncode == 0:
                import re as _re
                # ヘッダー行から該当月の列インデックスを探す
                header_match = _re.search(r'行4:\s*(\[.*?\])', result.stdout)
                data_match = _re.search(r'行5:\s*(\[.*?\])', result.stdout)
                if header_match and data_match:
                    import ast
                    headers = ast.literal_eval(header_match.group(1))
                    data = ast.literal_eval(data_match.group(1))
                    for i, h in enumerate(headers):
                        if payment_header in str(h):
                            if i < len(data) and data[i]:
                                unit_price = str(data[i]).replace(",", "").replace("¥", "").strip()
                            break
                    if unit_price:
                        logger.info(f"請求書提出: 報酬単価 = {unit_price}")
                    else:
                        price_err = f"ヘッダー '{payment_header}' に対応する値が見つかりません"
                else:
                    price_err = "シートのパースに失敗"
            else:
                price_err = f"シート読み取り失敗: {result.stderr[:100]}"
        except Exception as e:
            price_err = str(e)
            logger.error(f"請求書提出: 単価取得失敗 - {e}")

        if price_err:
            logger.warning(f"請求書提出: 単価事前取得失敗 - {price_err}")

        # ── 単価情報の指示文 ──
        if unit_price:
            price_instruction = f"業務委託報酬の単価は事前取得済み: **¥{int(unit_price):,}**（税抜）。そのまま使用してください。"
        else:
            price_instruction = f"""業務委託報酬の単価は事前取得に失敗しました。以下で手動取得してください:
1. ブラウザで請求金額管理シートを開く: https://docs.google.com/spreadsheets/d/1Bmbeglbhf62NeiJUHpai63DITrMDC3WSr09jJD8YhaM/edit
2. 行4のヘッダーから「{payment_header} 末払い」の列を探す
3. 行5（甲原海人）のその列の値を単価として使用"""

        # ── CLI プロンプト ──
        prompt = f"""あなたは甲原海人のAI秘書です。毎月の請求書を作成・提出してください。

## タスク
{target_year}年{target_month}月分の請求書を2通（業務委託報酬・経費立替）作成し、甲原さんの承認を得てから提出する。

## スキルファイル
詳細な手順は Skills/5_数値・業務/請求書提出_アドネス.md を必ず読んでから作業を開始してください。

## 事前取得情報
- 請求対象: {target_year}年{target_month}月分
- {price_instruction}
- 経費立替: ¥2,000（Facebook広告代、毎月固定）

## 実行手順

### Step 1: INVOY で請求書作成
1. ブラウザで INVOY にアクセス: https://www.invoy.jp/login?next=/dashboard/
   - Google ログイン（koa800sea.nifs@gmail.com）が必要な場合がある
2. 「発行」→「請求書」で **アドネス株式会社** のテンプレートを **複製**して2通作成:

#### 業務委託報酬
- 発行日: {today.strftime('%Y年%m月%d日')}（今日）
- お支払い期限: {today.year}年{today.month}月末日
- 件名: 業務委託報酬　{target_year}年{target_month:02d}月分
- 品目明細の単価: {f'¥{int(unit_price):,}' if unit_price else '（スプレッドシートから取得）'}

#### 経費立替
- 発行日: {today.strftime('%Y年%m月%d日')}（今日）
- お支払い期限: {today.year}年{today.month}月末日
- 件名: 経費立替　{target_year}年{target_month:02d}月分
- 品目明細の単価: ¥2,000

3. 各請求書をPDFでダウンロード
4. ファイル名をリネーム:
   - `{target_year}年{target_month}月請求書_甲原海人.pdf`
   - `{target_year}年{target_month}月経費建替_甲原海人.pdf`

### Step 2: 甲原さんに確認依頼
1. PDFをRenderにアップロード:
```bash
cd {project_root}
curl -s -X POST https://line-mention-bot-mmzu.onrender.com/api/upload \\
  -H "Authorization: Bearer $(cat System/config/line_bot_config.json | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"agent_token\",\"\"))')" \\
  -F "file=@ダウンロードしたPDFのパス"
```
2. LINE秘書グループに確認依頼を送信:
```bash
curl -s -X POST https://line-mention-bot-mmzu.onrender.com/api/notify_owner \\
  -H "Content-Type: application/json" \\
  -H "Authorization: Bearer $(cat System/config/line_bot_config.json | python3 -c 'import sys,json; print(json.load(sys.stdin).get(\"agent_token\",\"\"))')" \\
  -d '{{"message": "請求書を作成しました。確認をお願いします。\\n\\n1. 業務委託報酬（¥XXX）\\n2. 経費立替（¥2,200）\\n\\nPDF: [URL]\\n\\nOKであればこのメッセージに「OK」と返信してください。", "label": "請求書確認"}}'
```

**★ ここで処理を中断してください。甲原さんの承認を待ちます。★**

### Step 3: Google Drive に PDF 保存（承認後）
承認後、PDF を Google Drive にアップロード:
```bash
cd {project_root}
python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
with open('System/credentials/token_drive_personal.json') as f:
    t = json.load(f)
creds = Credentials(token=t['token'], refresh_token=t['refresh_token'],
                     token_uri=t['token_uri'], client_id=t['client_id'],
                     client_secret=t['client_secret'], scopes=t['scopes'])
service = build('drive', 'v3', credentials=creds)
folder_id = '1s64JH0T4nWlDIZV6QgAOvg9xDPV1pBAD'
for fname in ['{target_year}年{target_month}月請求書_甲原海人.pdf', '{target_year}年{target_month}月経費建替_甲原海人.pdf']:
    media = MediaFileUpload(fname, mimetype='application/pdf')
    r = service.files().create(body={{'name': fname, 'parents': [folder_id]}}, media_body=media, fields='id,name').execute()
    print(f'アップロード完了: {{r[\"name\"]}} (ID: {{r[\"id\"]}})')
"
```
※ PDFのパスはダウンロードしたディレクトリに合わせること。

### Step 4: 提出フォームで2回提出（承認後）
Google Forms で業務委託報酬と経費立替をそれぞれ提出する。
手順の詳細は Skills/5_数値・業務/請求書提出_アドネス.md の Step 5 を参照。

===RESULT_START===
請求書確認依頼をLINEに送信しました。甲原さんの「OK」返信を待っています。
承認後、以下のコマンドで提出処理を再開してください:
「請求書提出の続きをやって」
===RESULT_END===

## エラー時の対応
- ブラウザ接続エラー → LINE通知して終了
- INVOY ログイン失敗 → Google再ログインが必要な旨をLINE通知
- スプレッドシート取得失敗 → ブラウザで直接確認

{self._build_google_login_instructions()}

## 重要ルール
- **承認前に絶対にフォーム提出しない**
- 業務委託と経費のPDFを取り違えないこと
- 請求書の日付・件名・金額を必ず目視確認してからPDF化すること"""

        success, output, error = self._execute_claude_code_task(
            "請求書提出", claude_cmd, secretary_config, project_root,
            prompt, max_turns=25, timeout=900, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_monthly_invoice", datetime.now().isoformat())
            if "===RESULT_START===" in output and "===RESULT_END===" in output:
                report = output.split("===RESULT_START===")[1].split("===RESULT_END===")[0].strip()
                logger.info(f"請求書提出: 完了 - {report[:300]}")
            else:
                logger.info(f"請求書提出: 完了（マーカーなし）- {output[-300:]}")
        else:
            send_line_notify(f"請求書の自動提出が失敗しました。\n{error[:200]}")

    # ================================================================
    # 経営会議資料 自動作成（毎週金曜 15:00）
    # ================================================================
    async def _run_meeting_report(self):
        """経営会議資料を自動作成: Lookerスクショ取得→数値読取→Google Docs挿入→LINE通知"""
        from .notifier import send_line_notify
        from datetime import date, timedelta

        logger.info("経営会議資料: 開始")

        ok, claude_cmd, secretary_config, project_root, err = self._ensure_claude_chrome_ready()
        if not ok:
            logger.error(f"経営会議資料: プリフライト失敗 - {err}")
            send_line_notify(f"経営会議資料の自動作成を開始しましたが、準備に失敗しました。\n{err}")
            return

        # 日付計算
        today = date.today()
        meeting_date = today  # 金曜日=会議当日
        # 月次期間: 当月1日〜会議2日前（水曜）
        month_start = today.replace(day=1)
        month_end = today - timedelta(days=2)  # 水曜日
        # 週次期間: 木曜〜水曜（7日間）
        week_end = today - timedelta(days=2)  # 水曜日
        week_start = week_end - timedelta(days=6)  # 木曜日

        # Lookerフィルターのオフセット計算（今日からの日数差）
        month_offset_start = (today - month_start).days
        month_offset_end = (today - month_end).days
        week_offset_start = (today - week_start).days
        week_offset_end = (today - week_end).days

        meeting_md = f"{meeting_date.month}/{meeting_date.day}"
        month_start_md = f"{month_start.month}/{month_start.day}"
        month_end_md = f"{month_end.month}/{month_end.day}"
        week_start_md = f"{week_start.month}/{week_start.day}"
        week_end_md = f"{week_end.month}/{week_end.day}"

        prompt = f"""あなたは甲原海人のAI秘書です。経営会議資料を自動作成してください。

## 概要
毎週金曜の経営会議に向けた広告チーム報告資料を Google Docs に作成します。

## 日付情報
- 今日: {today.strftime('%Y/%m/%d')}（金曜日・会議当日）
- 月次期間: {month_start.strftime('%Y/%m/%d')}〜{month_end.strftime('%Y/%m/%d')}
- 週次期間: {week_start.strftime('%Y/%m/%d')}〜{week_end.strftime('%Y/%m/%d')}
- Google Doc ID: 18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s

## 手順

### Step 1: Looker Studioからスクショ取得

#### スクショ取得の共通手順（全スクショ共通）

**screencaptureの座標計算は不安定なので使わない。以下の「全画面キャプチャ→PILでcrop」方式を必ず使うこと。**

1. Chromeをアクティブにして全画面キャプチャ:
```bash
osascript -e 'tell application "Google Chrome" to activate' && sleep 1.5 && screencapture -x -o /tmp/chrome_fullscreen.png
```
2. PILでKPIカード領域をcrop:
```python
from PIL import Image
img = Image.open('/tmp/chrome_fullscreen.png')
# KPIカード2行（上段4枚+下段5枚）のみを切り取る
# サイドバー右端〜ランキング左端、カードラベル上〜カード値下
crop = img.crop((560, 760, 2280, 1210))
crop.save('/tmp/output.png')
```
3. 切り取った画像をReadツールで確認し、以下を検証:
   - 9枚のカードが全て含まれているか（左端の「集客数」、右端の「返金額」）
   - 余計な要素（「重要数値」ヘッダー、注釈テキスト、集客数推移グラフ、ランキング）が入っていないか
   - 切れていたらcrop座標を調整して再実行
4. crop座標の目安（3024x1964 全画面の場合）:
   - KPIカード: x=560〜2280, y=760〜1210
   - 12週グラフ: 4グラフ全体が収まる範囲（ページ遷移後に同様に撮影→確認→crop）
   - 画面サイズが異なる場合はMCP screenshotで位置を確認してから調整

#### 1-1. 月次KPI
1. ブラウザで Looker Studio を開く: https://lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_ghqtl90f1d
2. 日付フィルターをクリック
3. javascript_tool でオフセット変更:
```javascript
const inputs = document.querySelectorAll('input[type="number"]');
const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
setter.call(inputs[0], '{month_offset_start}');
inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
inputs[0].dispatchEvent(new Event('change', {{ bubbles: true }}));
setter.call(inputs[1], '{month_offset_end}');
inputs[1].dispatchEvent(new Event('input', {{ bubbles: true }}));
inputs[1].dispatchEvent(new Event('change', {{ bubbles: true }}));
```
4. 「適用」ボタンをクリック → 3秒待機
5. 上記の共通手順で全画面キャプチャ → PILでKPIカード領域をcrop → /tmp/meeting_monthly_kpi.png

#### 1-2. 12週グラフ
1. 左メニュー「過去12週実績」をクリック
2. 上記の共通手順で全画面キャプチャ → PILで4グラフ領域をcrop → /tmp/meeting_12week.png

#### 1-3. 週次KPI（7日間）
1. 「広告チーム報告」のコピーに戻る
2. フィルターを7日間に変更（開始={week_offset_start}、終了={week_offset_end}）
3. 「適用」→ 3秒待機
4. 上記の共通手順で全画面キャプチャ → PILでKPIカード領域をcrop → /tmp/meeting_weekly_kpi.png
5. フィルターを元に戻す（リセットボタンをクリック）

### Step 2: 数値読み取り
スクショから月次・週次のKPI数値を読み取る:
- 集客数、個別予約数、着金売上、ROAS（前期比%付き）
- 広告費、CPA、個別予約CPO、粗利、返金額

### Step 3: Google Docs に資料作成
`System/mac_mini/tools/meeting_report_v4.py` の create_report() をベースに:
1. 前回セクション削除（delete_current_section）
2. テキスト・テーブル挿入
3. フォーマット適用
4. セル内容を実際の数値で埋める

タイトル: {today.strftime('%Y/%m/%d')}　アドネス経営会議
月次進捗期間: ({month_start_md}〜{month_end_md})
過去7日間期間: ({week_start_md}〜{week_end_md})

### Step 4: スクショ画像の貼り付け
各プレースホルダーテキストを画像で置き換え:
```bash
osascript -e 'set the clipboard to (read (POSIX file "/tmp/meeting_monthly_kpi.png") as «class PNGf»)'
```
→ Google Docsで「[月次KPIスクショ]」テキストを選択 → Cmd+V
→ 同様に12週グラフ、7日間KPIも貼り付け

### Step 5: AI判定
読み取った数値から:
- **5段階評価**: 月目標（着金売上4億円/月、集客4万人/月）に対する達成ペースで判定
  - 5=大幅超過, 4=達成ペース, 3=ギリギリ, 2=やや未達, 1=全然ダメ
- **着地予想**: (実績 / 経過日数) × 月の日数
- **プロジェクト評価**: 数値推定。判断不能なら「（確認）」
- **ボトルネック**: 数値悪化ポイント

KPI基準: ①着金売上（最重要）②ROAS（300%=OK, 350%=良）③集客数 ④CPA（3000以下=良）

### Step 6: LINE報告
```bash
cd {project_root}
python3 System/line_notify.py "経営会議資料の下書きができました
→ https://docs.google.com/document/d/18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s/edit

総評: X/5 — 〇〇〇
補足・修正があれば返信してください"
```

{self._build_google_login_instructions()}

## 注意事項
- screenshotの結果をそのまま貼り付けない。必ず「全画面キャプチャ→PILでcrop」で切り取ってから使う
- MCP座標からのscreencapture座標計算は不安定なので使わない
- 画像貼り付けはクリップボード経由（osascript → Cmd+V）
- 切り取った画像は必ずReadツールで確認してから貼り付ける
- エラー時はLINE通知して終了"""

        success, output, error = self._execute_claude_code_task(
            "経営会議資料", claude_cmd, secretary_config, project_root,
            prompt, max_turns=40, timeout=900, use_chrome=True,
        )

        if success:
            self.memory.set_state("last_success_meeting_report", datetime.now().isoformat())
            logger.info(f"経営会議資料: 完了")
        else:
            send_line_notify(f"経営会議資料の自動作成が失敗しました。\n{error[:200]}")
            logger.error(f"経営会議資料: 失敗 - {error[:300]}")
