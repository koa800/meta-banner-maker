"""
Integration tests for the agent orchestrator components.
Verifies that shared_logger, code_tools, repair_agent, notifier, and memory
work together correctly without external dependencies.
"""

import json
import asyncio
import importlib
import os
import sys
import tempfile
import shutil
import types
from datetime import datetime as real_datetime
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))


def _load_scheduler_module():
    """apscheduler 非依存で scheduler モジュールを読み込む。"""
    fake_apscheduler = types.ModuleType("apscheduler")
    fake_schedulers = types.ModuleType("apscheduler.schedulers")
    fake_asyncio = types.ModuleType("apscheduler.schedulers.asyncio")
    fake_triggers = types.ModuleType("apscheduler.triggers")
    fake_cron = types.ModuleType("apscheduler.triggers.cron")
    fake_interval = types.ModuleType("apscheduler.triggers.interval")

    class DummyScheduler:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs
            self.jobs = []

        def add_job(self, *args, **kwargs):
            self.jobs.append({"args": args, "kwargs": kwargs})

        def start(self):
            return None

        def shutdown(self):
            return None

    class DummyTrigger:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    fake_asyncio.AsyncIOScheduler = DummyScheduler
    fake_cron.CronTrigger = DummyTrigger
    fake_interval.IntervalTrigger = DummyTrigger

    module_map = {
        "apscheduler": fake_apscheduler,
        "apscheduler.schedulers": fake_schedulers,
        "apscheduler.schedulers.asyncio": fake_asyncio,
        "apscheduler.triggers": fake_triggers,
        "apscheduler.triggers.cron": fake_cron,
        "apscheduler.triggers.interval": fake_interval,
    }

    with patch.dict(sys.modules, module_map):
        sys.modules.pop("agent_orchestrator.scheduler", None)
        return importlib.import_module("agent_orchestrator.scheduler")


def test_shared_logger_writes_jsonl():
    """Structured logger writes valid JSON lines to error log."""
    from agent_orchestrator.shared_logger import get_logger, ERROR_LOG

    logger = get_logger("test_integration_logger")
    logger.error("test error message", extra={"foo": "bar"})

    assert ERROR_LOG.exists(), "errors.jsonl should be created"
    lines = ERROR_LOG.read_text().strip().split("\n")
    last = json.loads(lines[-1])
    assert last["level"] == "ERROR"
    assert "test error message" in last["msg"]
    print("  [PASS] shared_logger writes JSONL")


def test_memory_store_roundtrip():
    """MemoryStore can log tasks and retrieve state."""
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        mem = MemoryStore(db_path)
        tid = mem.log_task_start("test_task", metadata={"source": "test"})
        mem.log_task_end(tid, "success", result_summary="all good")

        tasks = mem.get_recent_tasks(limit=1)
        assert len(tasks) == 1
        assert tasks[0]["task_name"] == "test_task"
        assert tasks[0]["status"] == "success"

        mem.set_state("test_key", "test_value")
        assert mem.get_state("test_key") == "test_value"
        print("  [PASS] MemoryStore roundtrip")
    finally:
        os.unlink(db_path)


def test_code_tools_read_file():
    """code_tools.read_file can read an existing file."""
    from agent_orchestrator.code_tools import read_file

    result = read_file(os.path.abspath(__file__))
    assert result.success, f"Should read self: {result.error}"
    assert "test_code_tools_read_file" in result.result
    print("  [PASS] code_tools.read_file works")


def test_code_tools_safety_rejects_secrets():
    """code_tools.write_file rejects writes to sensitive files."""
    from agent_orchestrator.code_tools import write_file

    result = write_file("/tmp/test.env", "SECRET=bad")
    assert not result.success, "Should reject .env files"
    assert "Blocked" in result.error or "blocked" in result.error.lower()
    print("  [PASS] code_tools rejects secret writes")


def test_code_tools_tool_dispatch():
    """TOOL_DISPATCH can resolve all defined tools."""
    from agent_orchestrator.code_tools import TOOL_DISPATCH, TOOL_DEFINITIONS

    defined_names = {t["name"] for t in TOOL_DEFINITIONS}
    dispatch_names = set(TOOL_DISPATCH.keys())
    assert defined_names == dispatch_names, (
        f"Mismatch: defined={defined_names - dispatch_names}, dispatch={dispatch_names - defined_names}"
    )
    print("  [PASS] TOOL_DISPATCH matches TOOL_DEFINITIONS")


def test_notifier_without_token():
    """Notifier gracefully fails when LINE_NOTIFY_TOKEN is missing."""
    from agent_orchestrator.notifier import send_line_notify

    with patch.dict(os.environ, {"LINE_NOTIFY_TOKEN": ""}, clear=False):
        result = send_line_notify("test message")
        assert result is False
    print("  [PASS] notifier handles missing token")


def test_scheduler_formats_cdp_sync_success_message():
    """CDP同期の成功通知は要点だけを短く返す。"""
    scheduler_module = _load_scheduler_module()

    output = """
=== 自動同期完了 ===
更新: 12件
新規: 3件
5 件を集客データシートに追加
集客データシートから2行削除
自動修復: 1件
"""
    message = scheduler_module._build_cdp_sync_message(output)

    assert message is not None
    assert "CDP同期が終わりました" in message
    assert "・マスタ更新 12件" in message
    assert "・マスタ新規 3件" in message
    assert "・集客データ追加 5件" in message
    assert "・集客データ昇格削除 2件" in message
    assert "・自動修復 1件" in message
    assert "次に見てほしいこと" not in message
    print("  [PASS] scheduler formats compact CDP success message")


def test_cdp_sync_finds_best_header_match():
    """CDP列名の小変更は自動修復候補を推定できる。"""
    from cdp_sync import find_best_header_match

    headers = [
        "登録日時",
        "【メールアドレス】",
        "電話番号を教えてください",
        "お名前（フルネーム）",
    ]

    assert find_best_header_match("メールアドレス", headers, "メールアドレス") == "【メールアドレス】"
    assert find_best_header_match("電話番号", headers, "電話番号") == "電話番号を教えてください"
    print("  [PASS] cdp_sync finds best header match")


def test_scheduler_formats_cdp_sync_attention_message():
    """CDP同期の確認依頼はリンクと次アクションを含める。"""
    scheduler_module = _load_scheduler_module()

    output = """
=== 自動同期完了 ===
更新: 8件
エラー: 1件

⚠️ 未同期ソース: 1件
  - UTAGE/友だちリスト: 7日未同期
"""

    with patch.object(
        scheduler_module,
        "_build_cdp_attention_links",
        return_value=[
            ("CDP / データソース管理", "https://example.com/cdp"),
            ("UTAGE / 友だちリスト（7日未同期）", "https://example.com/source"),
        ],
    ):
        message = scheduler_module._build_cdp_sync_message(output)

    assert message is not None
    assert "CDP同期で確認が必要です" in message
    assert "・エラー 1件" in message
    assert "・未同期ソース 1件" in message
    assert "次に見てほしいこと" in message
    assert "https://example.com/cdp" in message
    assert "https://example.com/source" in message
    print("  [PASS] scheduler formats actionable CDP attention message")


def test_scheduler_normalizes_cron_weekday_for_apscheduler():
    """週次cronの曜日番号は通常cron基準で解釈する。"""
    scheduler_module = _load_scheduler_module()

    trigger = scheduler_module._build_cron_trigger_from_expr("0 15 * * 5")
    weekday_trigger = scheduler_module._build_cron_trigger_from_expr("0 12 * * 1-5")

    assert trigger.kwargs["day_of_week"] == "fri"
    assert weekday_trigger.kwargs["day_of_week"] == "mon-fri"
    assert str(trigger.kwargs["timezone"]) == "Asia/Tokyo"
    print("  [PASS] scheduler normalizes cron weekday and timezone")


def test_scheduler_setup_uses_catchup_defaults():
    """cron/interval タスクは取りこぼしに強い job option で登録する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {
                "paths": {"db_path": db_path},
                "schedule": {
                    "daily_report_input": {"cron": "40 8 * * *", "enabled": True},
                    "health_check": {"interval_minutes": 5, "enabled": True},
                },
            },
            MemoryStore(db_path),
        )
        scheduler.setup()

        jobs = {job["kwargs"]["id"]: job["kwargs"] for job in scheduler.scheduler.jobs}
        assert jobs["daily_report_input"]["misfire_grace_time"] == 1800
        assert jobs["daily_report_input"]["coalesce"] is True
        assert jobs["daily_report_input"]["max_instances"] == 1
        assert jobs["health_check"]["misfire_grace_time"] == 300
        assert jobs["health_check"]["coalesce"] is True
        print("  [PASS] scheduler uses catch-up defaults")
    finally:
        os.unlink(db_path)


def test_find_claude_cmd_supports_shell_path():
    """Claude CLI は PATH 上の ~/.local/bin なども検出できる。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        with tempfile.TemporaryDirectory() as td:
            claude_path = Path(td) / "claude"
            claude_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            claude_path.chmod(0o755)

            with patch("shutil.which", return_value=str(claude_path)):
                assert scheduler._find_claude_cmd() == claude_path

        print("  [PASS] scheduler finds Claude CLI from shell PATH")
    finally:
        os.unlink(db_path)


def test_resolve_claude_config_dir_falls_back_to_default_config():
    """秘書用 config が未完成なら ~/.claude を使う。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            secretary_dir = fake_home / ".claude-secretary"
            default_dir = fake_home / ".claude"
            secretary_dir.mkdir()
            (secretary_dir / ".claude.json").write_text("{}", encoding="utf-8")
            default_dir.mkdir()
            (default_dir / "settings.json").write_text("{}", encoding="utf-8")

            with patch("pathlib.Path.home", return_value=fake_home):
                assert scheduler._resolve_claude_config_dir() == default_dir

        print("  [PASS] scheduler falls back to ~/.claude when secretary config lacks auth files")
    finally:
        os.unlink(db_path)


def test_refresh_claude_oauth_falls_back_to_cli_check_without_credentials():
    """credentials 不在時は CLI healthcheck で代替確認する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        scheduler._run_claude_cli_healthcheck = MagicMock(return_value=(True, ""))

        with tempfile.TemporaryDirectory() as td:
            config_dir = Path(td)
            ok, err = scheduler._refresh_claude_oauth(config_dir)

        assert ok is True
        assert err == ""
        scheduler._run_claude_cli_healthcheck.assert_called_once_with(config_dir)
        print("  [PASS] scheduler uses CLI healthcheck when credentials file is missing")
    finally:
        os.unlink(db_path)


def test_start_claude_auth_login_flow_launches_cli_login():
    """Claude 認証復旧は auth login を自動起動して承認だけ依頼できる。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        secretary_config = Path("/tmp/.claude-secretary")
        scheduler._find_claude_cmd = MagicMock(return_value=Path("/tmp/claude"))
        scheduler._build_claude_secretary_env = MagicMock(return_value={"PATH": "/tmp"})

        with patch("subprocess.Popen") as mock_popen:
            status, detail = scheduler._start_claude_auth_login_flow(secretary_config)

        assert status == "started"
        assert detail == ""
        mock_popen.assert_called_once()
        popen_args = mock_popen.call_args.args[0]
        assert popen_args == [
            "/tmp/claude",
            "auth",
            "login",
            "--email",
            "koa800.secretary@gmail.com",
        ]
        print("  [PASS] scheduler launches Claude auth login for approval-only recovery")
    finally:
        os.unlink(db_path)


def test_execute_claude_code_task_fails_fast_when_bridge_is_down():
    """Chrome bridge 不通なら Claude CLI を叩く前に止める。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        scheduler._ensure_claude_chrome_bridge = MagicMock(return_value=(False, "bridge down"))
        scheduler._check_task_health = MagicMock()

        success, output, error = scheduler._execute_claude_code_task(
            "daily_report_input",
            "/tmp/claude",
            "/tmp/.claude-secretary",
            "/tmp",
            "test prompt",
            use_chrome=True,
        )

        assert success is False
        assert output == ""
        assert error == "bridge down"
        scheduler._check_task_health.assert_called_once()
        print("  [PASS] chrome bridge failure stops Claude task early")
    finally:
        os.unlink(db_path)


def test_routine_watchdog_reruns_missing_task_once():
    """watchdog は未実行の定常を1回だけ補走する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            base = real_datetime(2026, 3, 9, 9, 5)
            return base if tz is None else base.replace(tzinfo=tz)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {
                "paths": {"db_path": db_path},
                "schedule": {"daily_report_input": {"enabled": True}},
            },
            MemoryStore(db_path),
        )
        runner = AsyncMock()

        with patch.object(scheduler_module, "datetime", FakeDateTime):
            asyncio.run(
                scheduler._ensure_routine_slot_completed(
                    task_name="daily_report_input",
                    success_state_key="last_success_daily_report_input",
                    check_after=(9, 0),
                    runner=runner,
                )
            )
            asyncio.run(
                scheduler._ensure_routine_slot_completed(
                    task_name="daily_report_input",
                    success_state_key="last_success_daily_report_input",
                    check_after=(9, 0),
                    runner=runner,
                )
            )

        assert runner.await_count == 1
        print("  [PASS] routine watchdog reruns missing task once")
    finally:
        os.unlink(db_path)


def test_routine_watchdog_retries_after_cooldown_until_limit():
    """watchdog はクールダウン後に再試行し、上限回数で止まる。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    class FakeDateTime(real_datetime):
        current = real_datetime(2026, 3, 9, 9, 5)

        @classmethod
        def now(cls, tz=None):
            base = cls.current
            return base if tz is None else base.replace(tzinfo=tz)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {
                "paths": {"db_path": db_path},
                "schedule": {"daily_report_input": {"enabled": True}},
            },
            MemoryStore(db_path),
        )
        runner = AsyncMock()

        with patch.object(scheduler_module, "datetime", FakeDateTime):
            for minute in (5, 9, 16, 27, 38):
                FakeDateTime.current = real_datetime(2026, 3, 9, 9, minute)
                asyncio.run(
                    scheduler._ensure_routine_slot_completed(
                        task_name="daily_report_input",
                        success_state_key="last_success_daily_report_input",
                        check_after=(9, 0),
                        runner=runner,
                        max_retries=3,
                        retry_cooldown_minutes=10,
                    )
                )

        assert runner.await_count == 3
        print("  [PASS] routine watchdog retries after cooldown until limit")
    finally:
        os.unlink(db_path)


def test_routine_watchdog_notifies_once_when_retry_limit_reached():
    """watchdog は上限到達後に1回だけ失敗通知する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    class FakeDateTime(real_datetime):
        current = real_datetime(2026, 3, 9, 9, 5)

        @classmethod
        def now(cls, tz=None):
            base = cls.current
            return base if tz is None else base.replace(tzinfo=tz)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {
                "paths": {"db_path": db_path},
                "schedule": {"daily_report_input": {"enabled": True}},
            },
            MemoryStore(db_path),
        )
        scheduler._maybe_notify_task_failure = MagicMock()
        runner = AsyncMock()

        with patch.object(scheduler_module, "datetime", FakeDateTime):
            for minute in (5, 16, 27, 38, 49):
                FakeDateTime.current = real_datetime(2026, 3, 9, 9, minute)
                asyncio.run(
                    scheduler._ensure_routine_slot_completed(
                        task_name="daily_report_input",
                        success_state_key="last_success_daily_report_input",
                        check_after=(9, 0),
                        runner=runner,
                        max_retries=3,
                        retry_cooldown_minutes=10,
                    )
                )

        assert runner.await_count == 3
        scheduler._maybe_notify_task_failure.assert_called_once()
        assert "自動補走後も未完了" in scheduler._maybe_notify_task_failure.call_args[0][1]
        print("  [PASS] routine watchdog notifies once after retry limit")
    finally:
        os.unlink(db_path)


def test_startup_recovery_reruns_missed_task_without_waiting_for_health_check():
    """再起動直後は health_check を待たずに当日分の取りこぼしを補う。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            base = real_datetime(2026, 3, 9, 9, 5)
            return base if tz is None else base.replace(tzinfo=tz)

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {
                "paths": {"db_path": db_path},
                "schedule": {"daily_report_input": {"enabled": True}},
            },
            MemoryStore(db_path),
        )
        scheduler._run_daily_report_input = AsyncMock()

        with patch.object(scheduler_module, "datetime", FakeDateTime):
            asyncio.run(scheduler.run_startup_recovery())

        assert scheduler._run_daily_report_input.await_count == 1
        assert scheduler.memory.get_state("last_startup_recovery_check")
        print("  [PASS] startup recovery reruns missed task immediately")
    finally:
        os.unlink(db_path)


def test_launchctl_service_running_accepts_plist_style_pid_output():
    """launchctl list の plist 形式出力でも local_agent を生存判定できる。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler(
            {"paths": {"db_path": db_path}, "schedule": {}},
            MemoryStore(db_path),
        )
        list_output = MagicMock(returncode=0, stdout='{\n\t"PID" = 46347;\n\t"Label" = "com.linebot.localagent";\n};\n')
        print_output = MagicMock(returncode=1, stdout="")

        with patch("subprocess.run", side_effect=[list_output, print_output]):
            assert scheduler._launchctl_service_running("com.linebot.localagent") is True

        print("  [PASS] launchctl plist-style PID output is treated as alive")
    finally:
        os.unlink(db_path)


def test_meeting_report_skips_outside_friday():
    """経営会議資料は金曜以外なら実行前に止める。"""
    scheduler_module = _load_scheduler_module()

    class FakeDateTime:
        @classmethod
        def now(cls, tz=None):
            from datetime import datetime

            return datetime(2026, 3, 7, 15, 0, tzinfo=tz)

    scheduler = scheduler_module.TaskScheduler({"schedule": {}}, MagicMock())
    scheduler._ensure_claude_chrome_ready = MagicMock(return_value=(True, "", {}, "", ""))

    with patch.object(scheduler_module, "datetime", FakeDateTime):
        asyncio.run(scheduler._run_meeting_report())

    scheduler._ensure_claude_chrome_ready.assert_not_called()
    print("  [PASS] meeting_report skips on non-Friday")


def test_daily_report_input_oauth_failure_requests_approval_only():
    """日報の preflight で Claude 認証が切れたら承認だけ依頼する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        secretary_config = Path("/tmp/.claude")
        scheduler._ensure_claude_chrome_ready = MagicMock(
            return_value=(False, Path("/tmp/claude"), secretary_config, Path("/tmp/repo"), "Claude Code OAuth エラー: expired")
        )
        scheduler._request_claude_approval_only = MagicMock()

        with patch("agent_orchestrator.notifier.send_line_notify") as mock_notify:
            asyncio.run(scheduler._run_daily_report_input())

        scheduler._request_claude_approval_only.assert_called_once_with("日報の自動入力", secretary_config)
        mock_notify.assert_not_called()
        print("  [PASS] daily_report_input requests approval-only Claude recovery on preflight auth failure")
    finally:
        os.unlink(db_path)


def test_looker_csv_download_login_failure_requests_approval_only():
    """Looker CSV が Google ログインで止まったら承認だけ依頼する。"""
    scheduler_module = _load_scheduler_module()
    from agent_orchestrator.memory import MemoryStore

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        scheduler = scheduler_module.TaskScheduler({"paths": {"db_path": db_path}, "schedule": {}}, MemoryStore(db_path))
        scheduler._ensure_claude_chrome_ready = MagicMock(
            return_value=(True, Path("/tmp/claude"), Path("/tmp/.claude"), Path("/tmp/repo"), "")
        )
        scheduler._find_missing_csv_dates = MagicMock(return_value=[real_datetime(2026, 3, 9).date()])
        scheduler._execute_claude_code_task = MagicMock(return_value=(False, "", "Googleログイン切れ"))
        scheduler._request_google_approval_only = MagicMock()

        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            (fake_home / "Desktop").mkdir(parents=True, exist_ok=True)
            with patch("pathlib.Path.home", return_value=fake_home):
                with patch("agent_orchestrator.notifier.send_line_notify") as mock_notify:
                    asyncio.run(scheduler._run_looker_csv_download())

        scheduler._request_google_approval_only.assert_called_once_with(
            "Looker CSVのダウンロード",
            scheduler_module._LOOKER_CSV_REPORT_URL,
            "manual_approval_google_looker_csv",
        )
        mock_notify.assert_not_called()
        print("  [PASS] looker_csv_download requests approval-only Google recovery on login failure")
    finally:
        os.unlink(db_path)


def test_repair_agent_no_errors():
    """RepairAgent returns None when there are no errors."""
    from agent_orchestrator.memory import MemoryStore
    from agent_orchestrator.repair_agent import RepairAgent

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        mem = MemoryStore(db_path)
        config = {"llm": {"model": "claude-sonnet-4-20250514"}}
        agent = RepairAgent(mem, config)

        with patch("agent_orchestrator.repair_agent.read_recent_errors", return_value=[]):
            result = agent.check_and_repair()
        assert result is None, "Should return None when no errors"
        print("  [PASS] RepairAgent handles no-error case")
    finally:
        os.unlink(db_path)


def test_repair_agent_dedup():
    """RepairAgent deduplicates errors by fingerprint."""
    from agent_orchestrator.memory import MemoryStore
    from agent_orchestrator.repair_agent import RepairAgent, _error_fingerprint

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    try:
        mem = MemoryStore(db_path)
        config = {"llm": {"model": "claude-sonnet-4-20250514"}}
        agent = RepairAgent(mem, config)

        fake_error = {
            "ts": "2026-02-20T10:00:00Z",
            "msg": "test error",
            "file": "/test/foo.py",
            "line": 42,
            "error": {"type": "ValueError", "message": "bad value"},
        }

        with patch("agent_orchestrator.repair_agent.read_recent_errors", return_value=[fake_error]):
            with patch.object(agent, "_run_repair_session", return_value={"fixed": False, "reason": "test"}):
                result1 = agent.check_and_repair()

        assert result1 is not None, "First check should process the error"

        with patch("agent_orchestrator.repair_agent.read_recent_errors", return_value=[fake_error]):
            result2 = agent.check_and_repair()

        assert result2 is None, "Second check should skip the same error (dedup)"
        print("  [PASS] RepairAgent deduplicates errors")
    finally:
        os.unlink(db_path)


if __name__ == "__main__":
    print("Running integration tests...\n")
    test_shared_logger_writes_jsonl()
    test_memory_store_roundtrip()
    test_code_tools_read_file()
    test_code_tools_safety_rejects_secrets()
    test_code_tools_tool_dispatch()
    test_notifier_without_token()
    test_scheduler_formats_cdp_sync_success_message()
    test_cdp_sync_finds_best_header_match()
    test_scheduler_formats_cdp_sync_attention_message()
    test_scheduler_normalizes_cron_weekday_for_apscheduler()
    test_scheduler_setup_uses_catchup_defaults()
    test_find_claude_cmd_supports_shell_path()
    test_resolve_claude_config_dir_falls_back_to_default_config()
    test_refresh_claude_oauth_falls_back_to_cli_check_without_credentials()
    test_start_claude_auth_login_flow_launches_cli_login()
    test_execute_claude_code_task_fails_fast_when_bridge_is_down()
    test_routine_watchdog_reruns_missing_task_once()
    test_routine_watchdog_retries_after_cooldown_until_limit()
    test_routine_watchdog_notifies_once_when_retry_limit_reached()
    test_startup_recovery_reruns_missed_task_without_waiting_for_health_check()
    test_launchctl_service_running_accepts_plist_style_pid_output()
    test_meeting_report_skips_outside_friday()
    test_daily_report_input_oauth_failure_requests_approval_only()
    test_looker_csv_download_login_failure_requests_approval_only()
    test_repair_agent_no_errors()
    test_repair_agent_dedup()
    print("\n✓ All integration tests passed!")
