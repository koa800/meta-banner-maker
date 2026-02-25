"""Smoke tests: verify imports and path resolution after restructuring."""

import os
import sys
from pathlib import Path

SYSTEM_DIR = Path(__file__).resolve().parent.parent / "System"
sys.path.insert(0, str(SYSTEM_DIR))


def test_credentials_dir_exists():
    assert (SYSTEM_DIR / "credentials").is_dir()


def test_config_dir_exists():
    assert (SYSTEM_DIR / "config").is_dir()


def test_data_dir_exists():
    assert (SYSTEM_DIR / "data").is_dir()


def test_sheets_manager_paths():
    from sheets_manager import CLIENT_SECRET_PATH, ACCOUNTS
    assert "credentials" in str(CLIENT_SECRET_PATH)
    assert "credentials" in str(ACCOUNTS["kohara"])


def test_docs_manager_paths():
    from docs_manager import CLIENT_SECRET_PATH, ACCOUNTS
    assert "credentials" in str(CLIENT_SECRET_PATH)
    assert "credentials" in str(ACCOUNTS["kohara"])


def test_mail_manager_paths():
    from mail_manager import ACCOUNTS, CLIENT_SECRETS
    assert "credentials" in str(ACCOUNTS["kohara"])
    assert "credentials" in str(CLIENT_SECRETS["kohara"])


def test_calendar_manager_paths():
    from calendar_manager import CLIENT_SECRET_PATH
    assert "credentials" in str(CLIENT_SECRET_PATH)


def test_addness_config_path():
    from addness_to_context import CONFIG_PATH
    assert str(CONFIG_PATH).endswith("config/addness.json")


def test_kpi_output_path():
    from kpi_cache_builder import DEFAULT_OUTPUT
    assert "data/kpi_summary.json" in str(DEFAULT_OUTPUT)


def test_sns_analyzer_config_path():
    from sns_analyzer import CONFIG_FILE
    assert str(CONFIG_FILE).endswith("config/sns_analyzer.json")


def test_addness_session_path():
    from addness_fetcher import SESSION_PATH
    assert "data/addness_session.json" in str(SESSION_PATH)


def test_gitmodules_exists():
    gitmodules = Path(__file__).resolve().parent.parent / ".gitmodules"
    assert gitmodules.is_file()
    content = gitmodules.read_text()
    assert "System/line_bot" in content
    assert "System/addness_mcp_server" in content
