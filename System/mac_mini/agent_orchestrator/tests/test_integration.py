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
from pathlib import Path
from unittest.mock import patch, MagicMock

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
    test_meeting_report_skips_outside_friday()
    test_repair_agent_no_errors()
    test_repair_agent_dedup()
    print("\n✓ All integration tests passed!")
