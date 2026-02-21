"""
Integration tests for the agent orchestrator components.
Verifies that shared_logger, code_tools, repair_agent, notifier, and memory
work together correctly without external dependencies.
"""

import json
import os
import sys
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


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
    test_repair_agent_no_errors()
    test_repair_agent_dedup()
    print("\n✓ All integration tests passed!")
