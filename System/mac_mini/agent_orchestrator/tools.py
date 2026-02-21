"""
Tool wrappers for the agent orchestrator.
Each tool wraps an existing script in System/ with a uniform interface.
"""

import subprocess
import os
import sys
import logging
from dataclasses import dataclass
from typing import Optional

from .shared_logger import get_logger

logger = get_logger("tools")

_orch_dir = os.path.dirname(os.path.abspath(__file__))   # agent_orchestrator/
SYSTEM_DIR = os.path.dirname(os.path.dirname(_orch_dir))  # System/
VENV_PYTHON = os.path.expanduser("~/agent-env/bin/python3")


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""
    return_code: int = 0


def _run_script(script_path: str, args: list = None, timeout: int = 300, cwd: str = None) -> ToolResult:
    """Run a Python script with the agent venv interpreter."""
    python = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
    cmd = [python, script_path] + (args or [])
    work_dir = cwd or os.path.dirname(script_path)
    script_name = os.path.basename(script_path)

    logger.info(f"Running: {script_name}", extra={"script": script_path, "args": args})
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        if result.returncode != 0:
            stderr_lines = result.stderr.strip().split("\n")
            logger.error(
                f"Script failed: {script_name}",
                extra={
                    "script": script_path,
                    "return_code": result.returncode,
                    "stderr_tail": "\n".join(stderr_lines[-10:]),
                    "error": {
                        "type": "ScriptError",
                        "message": stderr_lines[-1] if stderr_lines else "unknown",
                        "traceback": stderr_lines[-15:],
                    },
                },
            )
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
            return_code=result.returncode
        )
    except subprocess.TimeoutExpired:
        logger.error(
            f"Script timeout: {script_name}",
            extra={
                "script": script_path,
                "timeout": timeout,
                "error": {"type": "TimeoutError", "message": f"Timeout after {timeout}s"},
            },
        )
        return ToolResult(success=False, output="", error=f"Timeout after {timeout}s", return_code=-1)
    except Exception as e:
        logger.exception(
            f"Script exception: {script_name}",
            extra={
                "script": script_path,
                "error": {"type": type(e).__name__, "message": str(e)},
            },
        )
        return ToolResult(success=False, output="", error=str(e), return_code=-1)


# --------------- Mail ---------------

def mail_run(account: str = "personal") -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "mail_manager.py"),
        ["--account", account, "run"]
    )

def mail_status(account: str = "personal") -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "mail_manager.py"),
        ["--account", account, "status"]
    )


# --------------- Calendar ---------------

def calendar_list(account: str = "personal", days: int = 7, target_date: str = None) -> ToolResult:
    """カレンダーの予定を取得。
    target_date: 特定日 (YYYY-MM-DD)。未指定の場合は本日から days 日分（ただし calendar_manager.py
    は target_date なしで次30日分を返す）。days=1 かつ target_date 未指定なら今日の日付を使用。
    """
    from datetime import date
    # OAuthトークンが存在しない場合は即座にエラー返却（ヘッドレス環境でのハング防止）
    token_file = "token_calendar.json" if account == "kohara" else f"token_calendar_{account}.json"
    token_path = os.path.join(SYSTEM_DIR, token_file)
    if not os.path.exists(token_path):
        return ToolResult(
            success=False, output="",
            error=f"Calendar token not found: {token_path} — run calendar auth setup first",
            return_code=1
        )
    args = ["--account", account, "list"]
    if target_date:
        args.append(target_date)
    elif days == 1:
        args.append(date.today().isoformat())
    # days>1 の場合は target_date なしで次30日分を返す（calendar_manager.py の仕様）
    return _run_script(os.path.join(SYSTEM_DIR, "calendar_manager.py"), args)


# --------------- Sheets ---------------

def sheets_read(url_or_id: str, sheet_name: str = None, range_str: str = None) -> ToolResult:
    args = ["read", url_or_id]
    if sheet_name:
        args.append(sheet_name)
    if range_str:
        args.append(range_str)
    return _run_script(os.path.join(SYSTEM_DIR, "sheets_manager.py"), args)


# --------------- Docs ---------------

def docs_read(url_or_id: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "docs_manager.py"),
        ["read", url_or_id]
    )


# --------------- AI News ---------------

def ai_news_notify() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "ai_news_notifier.py"), timeout=600)


# --------------- Addness ---------------

def addness_fetch() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "addness_fetcher.py"), timeout=600)

def addness_to_context() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "addness_to_context.py"))


# --------------- Q&A ---------------

def qa_search(query: str, top_k: int = 5) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "qa_search.py"),
        ["search", query, str(top_k)]
    )

def qa_answer(question: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "qa_search.py"),
        ["answer", question]
    )

def qa_stats() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "qa_search.py"), ["stats"])


# --------------- Who to Ask ---------------

def who_to_ask(task_description: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "who_to_ask.py"),
        [task_description]
    )


# --------------- KPI ---------------

def kpi_refresh() -> ToolResult:
    """日別タブの既存データから月別タブを再計算"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["refresh"])


def kpi_process() -> ToolResult:
    """元データの完了エントリを検知 → CSVから日別/月別に投入"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["process"])


def kpi_check_today() -> ToolResult:
    """2日前の日付が元データで完了になっているかチェック"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["check_today"])


# --------------- Utility ---------------

def shell_command(cmd: str, timeout: int = 60) -> ToolResult:
    """Run an arbitrary shell command (use with caution)."""
    logger.warning(f"Shell command: {cmd}", extra={"command": cmd})
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            logger.error(
                f"Shell command failed",
                extra={
                    "command": cmd,
                    "return_code": result.returncode,
                    "error": {"type": "ShellError", "message": result.stderr.strip()[-200:]},
                },
            )
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
            return_code=result.returncode
        )
    except subprocess.TimeoutExpired:
        logger.error(f"Shell timeout", extra={
            "command": cmd, "error": {"type": "TimeoutError", "message": f"Timeout after {timeout}s"},
        })
        return ToolResult(success=False, output="", error=f"Timeout after {timeout}s", return_code=-1)
    except Exception as e:
        logger.exception(f"Shell exception", extra={
            "command": cmd, "error": {"type": type(e).__name__, "message": str(e)},
        })
        return ToolResult(success=False, output="", error=str(e), return_code=-1)


# --------------- Git Sync ---------------

def git_pull_sync() -> ToolResult:
    """GitHubからpull → ローカルデプロイ"""
    sync_script = os.path.join(SYSTEM_DIR, "mac_mini", "git_pull_sync.sh")
    return shell_command(f"bash {sync_script}", timeout=120)


TOOL_REGISTRY = {
    "mail_run": {"fn": mail_run, "description": "受信メールの処理・自動返信下書き作成"},
    "mail_status": {"fn": mail_status, "description": "メール処理のステータス確認"},
    "calendar_list": {"fn": calendar_list, "description": "今後の予定一覧を取得"},
    "sheets_read": {"fn": sheets_read, "description": "Googleスプレッドシートのデータを読み取り"},
    "docs_read": {"fn": docs_read, "description": "Googleドキュメントの内容を読み取り"},
    "ai_news_notify": {"fn": ai_news_notify, "description": "最新AIニュースの収集・要約・通知"},
    "addness_fetch": {"fn": addness_fetch, "description": "Addnessからゴールツリーデータをスクレイピング"},
    "addness_to_context": {"fn": addness_to_context, "description": "Addnessデータをコンテキスト用マークダウンに変換"},
    "qa_search": {"fn": qa_search, "description": "Q&Aナレッジベースを検索"},
    "qa_answer": {"fn": qa_answer, "description": "質問に対してAI回答を生成"},
    "qa_stats": {"fn": qa_stats, "description": "Q&Aナレッジベースの統計情報"},
    "who_to_ask": {"fn": who_to_ask, "description": "タスクに最適な担当者を推薦"},
    "kpi_refresh": {"fn": kpi_refresh, "description": "KPI月別タブを日別データから再計算"},
    "kpi_process": {"fn": kpi_process, "description": "元データ完了分をCSVから日別/月別に投入"},
    "kpi_check_today": {"fn": kpi_check_today, "description": "2日前のKPIデータ完了チェック"},
    "git_pull_sync": {"fn": git_pull_sync, "description": "GitHubからpull→ローカルデプロイ"},
}
