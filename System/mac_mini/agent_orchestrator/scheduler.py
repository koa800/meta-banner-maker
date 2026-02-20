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
        """タスク失敗をLINE通知（2時間以内に同タスクの通知済みならスキップ）"""
        from .notifier import send_line_notify
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
        ok = send_line_notify(
            f"\n⚠️ タスクエラー: {task_name}\n"
            f"━━━━━━━━━━━━\n"
            f"{error_msg[:250]}\n"
            f"━━━━━━━━━━━━"
        )
        if ok:
            self.memory.set_state(state_key, now.isoformat())

    async def _run_addness_fetch(self):
        await self._execute_tool("addness_fetch", tools.addness_fetch)
        await self._execute_tool("addness_to_context", tools.addness_to_context)

    async def _run_ai_news(self):
        await self._execute_tool("ai_news", tools.ai_news_notify)

    async def _run_mail_personal(self):
        result = await self._execute_tool("mail_inbox_personal", tools.mail_run, account="personal")
        await self._notify_mail_result(result, "personal")

    async def _run_mail_kohara(self):
        result = await self._execute_tool("mail_inbox_kohara", tools.mail_run, account="kohara")
        await self._notify_mail_result(result, "kohara")

    async def _notify_mail_result(self, result: tools.ToolResult, account: str):
        """メール処理結果をLINE通知（返信待ちがある場合のみ）"""
        if not result.success or not result.output:
            return
        from .notifier import send_line_notify

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

        # local_agent.py の生存確認（agent.log 更新時刻チェック）
        agent_log = os.path.expanduser("~/agents/line_bot_local/agent.log")
        if os.path.exists(agent_log):
            try:
                import time
                log_age_min = (time.time() - os.path.getmtime(agent_log)) / 60
                if log_age_min > 30:
                    logger.warning(f"local_agent may be stale: log not updated for {log_age_min:.0f} min")
                    state_key = "local_agent_stale_notified"
                    last_n = self.memory.get_state(state_key)
                    if not last_n or (datetime.now() - datetime.fromisoformat(last_n)).total_seconds() > 3600:
                        send_line_notify(
                            f"\n⚠️ local_agent 停止の可能性\nログが{log_age_min:.0f}分間更新されていません\n"
                            f"com.linebot.localagent を確認してください"
                        )
                        self.memory.set_state(state_key, datetime.now().isoformat())
            except Exception as e:
                logger.debug(f"local_agent log check error: {e}")

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
        from .notifier import send_line_notify
        from datetime import date

        master_dir = self.config.get("paths", {}).get("master_dir", "~/agents/Master")
        actionable_path = os.path.expanduser(os.path.join(master_dir, "actionable-tasks.md"))
        goal_tree_path = os.path.expanduser(os.path.join(master_dir, "addness-goal-tree.md"))

        # actionable-tasks.md を優先使用、なければ旧方式 goal-tree にフォールバック
        if os.path.exists(actionable_path):
            await self._digest_from_actionable(actionable_path, send_line_notify)
        elif os.path.exists(goal_tree_path):
            await self._digest_from_goal_tree(goal_tree_path, send_line_notify)
        else:
            logger.warning("Neither actionable-tasks.md nor addness-goal-tree.md found")

        # 今日のカレンダーを別メッセージで通知（独立して動作）
        await self._notify_today_calendar(send_line_notify)

    async def _notify_today_calendar(self, send_line_notify):
        """今日のカレンダー予定をLINE通知（予定がなければスキップ）"""
        from datetime import date
        try:
            result = tools.calendar_list(account="personal", days=1)
            if not result.success or not result.output or "予定はありません" in result.output:
                return

            today_str = date.today().strftime("%Y/%m/%d")
            # 各行: "  [id] 2026-02-21T10:00:00+09:00 ~ ...  タイトル"
            events = []
            for line in result.output.splitlines():
                m = re.match(r"\s*\[.+?\]\s+(\S+)\s*~\s*\S+\s+(.+)", line)
                if m:
                    dt_str = m.group(1)
                    title = m.group(2).strip()
                    # 時刻抽出 (T付きならhh:mm、日付のみなら "終日")
                    if "T" in dt_str:
                        time_part = dt_str.split("T")[1][:5]  # "10:00"
                    else:
                        time_part = "終日"
                    events.append(f"  {time_part} {title}")

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
        """毎週月曜9:30: 先週のシステム稼働サマリーをLINE通知"""
        import json as _json
        from .notifier import send_line_notify
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
                         "actionable-tasks.md")
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
