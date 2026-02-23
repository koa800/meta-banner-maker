"""
APScheduler-based task scheduler for the agent orchestrator.
Replaces cron jobs with in-process scheduling and logging.
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

import os
import re
from datetime import datetime

from . import tools
from .memory import MemoryStore
from .shared_logger import get_logger

logger = get_logger("scheduler")

_repair_agent_ref = None


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
            "kpi_daily_import": self._run_kpi_daily_import,
            "sheets_sync": self._run_sheets_sync,
            "git_pull_sync": self._run_git_pull_sync,
            "daily_group_digest": self._run_daily_group_digest,
            "weekly_profile_learning": self._run_weekly_profile_learning,
            "kpi_nightly_cache": self._run_kpi_nightly_cache,
            "log_rotate": self._run_log_rotate,
            "slack_ai_team_check": self._run_slack_ai_team_check,
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
    _NO_FAILURE_NOTIFY = {"health_check", "oauth_health_check", "render_health_check"}
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
        from .notifier import notify_ai_team as send_line_notify  # LINE+Slack同時送信

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
            logger.warning(f"Mail notification failed for {account}")

    async def _run_addness_goal_check(self):
        result = await self._execute_tool("addness_to_context", tools.addness_to_context)
        if result.success:
            logger.info("Addness goal context updated for daily review")

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
                        logger.warning(f"Q&A monitor stale: last check {age_hours:.1f}h ago")
                        state_key = "qa_monitor_stale_notified"
                        last_n = self.memory.get_state(state_key)
                        if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 14400:
                            send_line_notify(
                                f"\n⚠️ Q&Aモニター停止の可能性\n最終チェック: {age_hours:.0f}時間前\n"
                                f"local_agent.py が正常に動作しているか確認してください"
                            )
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
                logger.warning("local_agent process not found via launchctl")
                state_key = "local_agent_stale_notified"
                last_n = self.memory.get_state(state_key)
                if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 3600:
                    send_line_notify(
                        "\n⚠️ local_agent 停止\nプロセスが見つかりません\n"
                        "com.linebot.localagent を確認してください"
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
        """毎朝8:30: actionable-tasks.md（タスク）+ カレンダー（今日の予定）をLINE+Slack通知"""
        from .notifier import notify_ai_team as send_line_notify  # LINE+Slack同時送信
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

    async def _run_weekly_stats(self):
        """毎週月曜9:30: 先週のシステム稼働サマリーをLINE+Slack通知"""
        import json as _json
        from .notifier import notify_ai_team as send_line_notify  # LINE+Slack同時送信
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
            client = _anthropic.Anthropic()
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                system="あなたはスキルプラス（AI副業教育コース）のコンテンツディレクターです。",
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
                f"\nLooker StudioからCSVエクスポートをお願いします\n"
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
                    logger.info(f"weekly_profile_learning: updated {person_name} ({len(messages)} msgs)")
                else:
                    logger.warning(f"weekly_profile_learning: write failed for {person_name}: {write_result.error}")

            except Exception as e:
                logger.warning(f"weekly_profile_learning: analysis failed for {person_name}: {e}")
                continue

        # 4. 結果をLINE通知
        message = (
            f"\n🧠 週次プロファイル学習完了\n"
            f"━━━━━━━━━━━━\n"
            f"更新: {updated_count}名\n"
            f"スキップ: {skipped_count}名（3件未満 or プロファイル未登録）\n"
            f"分析対象: {len(all_messages_by_person)}名 / {sum(len(m) for m in all_messages_by_person.values())}メッセージ\n"
            f"━━━━━━━━━━━━"
        )
        send_line_notify(message)
        self.memory.log_task_end(
            task_id, "success",
            result_summary=f"Updated {updated_count} profiles, skipped {skipped_count}"
        )
        logger.info(f"weekly_profile_learning completed: {updated_count} updated, {skipped_count} skipped")

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
