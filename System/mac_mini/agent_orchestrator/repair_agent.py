"""
Self-healing repair agent.

Monitors structured error logs, diagnoses root causes using Claude API tool_use,
proposes fixes on feature branches, and requests human approval via LINE
before merging.

Lifecycle:
  1. Poll errors.jsonl for new errors since last check
  2. Cluster related errors → single repair session per root cause
  3. Claude analyzes error + reads relevant code via code_tools
  4. Claude proposes a fix (patch_file / write_file) on a feature branch
  5. Syntax check + tests run automatically
  6. If tests pass → send diff + explanation to LINE for approval
  7. On approval callback → merge branch to main
  8. On rejection → delete branch, log for human review
"""

import json
import os
import hashlib
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .shared_logger import get_logger, read_recent_errors
from .code_tools import (
    TOOL_DEFINITIONS, execute_tool, ToolOutput,
    git_create_branch, git_commit, git_show_branch_diff,
    git_status, run_test, run_syntax_check,
    _run_git, _current_branch, REPO_ROOT,
)
from .memory import MemoryStore

logger = get_logger("repair_agent")

MAX_TOOL_ROUNDS = 15
MAX_ERRORS_PER_SESSION = 5
COOLDOWN_MINUTES = 30


def _error_fingerprint(error: dict) -> str:
    """Create a dedup key from error type + file + line."""
    parts = [
        error.get("error", {}).get("type", ""),
        error.get("file", ""),
        str(error.get("line", "")),
    ]
    return hashlib.md5("|".join(parts).encode()).hexdigest()[:12]


def _format_errors_for_prompt(errors: list[dict]) -> str:
    """Format error log entries into a readable prompt section."""
    sections = []
    for i, err in enumerate(errors, 1):
        ts = err.get("ts", "?")
        msg = err.get("msg", "?")
        file = err.get("file", "?")
        line = err.get("line", "?")
        error_info = err.get("error", {})
        exc_type = error_info.get("type", "?")
        exc_msg = error_info.get("message", "?")
        tb = error_info.get("traceback", [])
        tb_str = "".join(tb[-5:]) if tb else "(no traceback)"

        sections.append(
            f"### Error {i}\n"
            f"- Time: {ts}\n"
            f"- File: {file}:{line}\n"
            f"- Type: {exc_type}\n"
            f"- Message: {exc_msg}\n"
            f"- Log message: {msg}\n"
            f"```\n{tb_str}```"
        )
    return "\n\n".join(sections)


def _build_system_prompt() -> str:
    return """You are a code repair agent for a Python project (an AI secretary system).
Your job is to diagnose errors from structured logs and fix the root cause.

RULES:
1. Read the error details carefully. Use read_file and search_code to understand the context.
2. Identify the root cause — don't just suppress the error.
3. Create a feature branch with git_create_branch before making any changes.
4. Use patch_file for targeted fixes (preferred) or write_file for new files.
5. After making changes, run run_syntax_check on modified files.
6. Then run run_test to verify nothing is broken.
7. Finally, use git_commit with a clear message describing the fix.
8. Keep changes minimal and focused. Don't refactor unrelated code.
9. If you're unsure about the fix, explain your uncertainty — the human will review.

SAFETY:
- NEVER modify .env files, secret files, or credential files.
- NEVER write directly to main branch — always use feature branches.
- NEVER delete files unless clearly necessary.
- If tests fail after your fix, explain what happened and revert if needed.

RESPONSE FORMAT:
After fixing, provide a JSON summary:
{"fixed": true, "files_changed": ["path1", "path2"], "description": "What was fixed and why"}
If you cannot fix it:
{"fixed": false, "reason": "Why the fix couldn't be applied", "suggestion": "What a human should do"}"""


class RepairAgent:
    def __init__(self, memory: MemoryStore, config: dict):
        self.memory = memory
        self.config = config
        self._seen_fingerprints: set[str] = set()
        self._last_check = datetime.now()
        self._load_seen()

    def _load_seen(self):
        """Load previously handled error fingerprints from state."""
        raw = self.memory.get_state("repair_seen_fingerprints", "[]")
        try:
            self._seen_fingerprints = set(json.loads(raw))
        except json.JSONDecodeError:
            self._seen_fingerprints = set()

    def _save_seen(self):
        recent = list(self._seen_fingerprints)[-200:]
        self.memory.set_state("repair_seen_fingerprints", json.dumps(recent))

    def check_and_repair(self) -> Optional[dict]:
        """Main entry point: check for new errors and attempt repair."""
        errors = read_recent_errors(max_lines=30)
        if not errors:
            logger.info("No errors found in log")
            return None

        new_errors = []
        for err in errors:
            fp = _error_fingerprint(err)
            if fp not in self._seen_fingerprints:
                new_errors.append(err)
                self._seen_fingerprints.add(fp)

        if not new_errors:
            logger.info("No new (unseen) errors")
            return None

        self._save_seen()
        errors_to_fix = new_errors[:MAX_ERRORS_PER_SESSION]
        logger.info(f"Found {len(errors_to_fix)} new error(s) to analyze",
                     extra={"count": len(errors_to_fix)})

        task_id = self.memory.log_task_start("repair_agent", metadata={
            "error_count": len(errors_to_fix),
            "fingerprints": [_error_fingerprint(e) for e in errors_to_fix],
        })

        try:
            result = self._run_repair_session(errors_to_fix)
            status = "success" if result.get("fixed") else "needs_review"
            self.memory.log_task_end(task_id, status, result_summary=json.dumps(result)[:500])
            return result
        except Exception as e:
            logger.exception("Repair session failed", extra={"error": str(e)})
            self.memory.log_task_end(task_id, "error", error_message=str(e))
            self._cleanup_branch()
            return {"fixed": False, "reason": f"Repair agent crashed: {e}"}

    def _run_repair_session(self, errors: list[dict]) -> dict:
        """Run a full repair session with Claude API."""
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return {"fixed": False, "reason": "ANTHROPIC_API_KEY not set"}

        try:
            import anthropic
        except ImportError:
            return {"fixed": False, "reason": "anthropic package not installed"}

        client = anthropic.Anthropic(api_key=api_key)
        model = self.config.get("llm", {}).get("model", "claude-sonnet-4-20250514")

        error_text = _format_errors_for_prompt(errors)
        messages = [
            {
                "role": "user",
                "content": (
                    f"The following errors were detected in the agent system. "
                    f"Please diagnose the root cause and fix them.\n\n{error_text}"
                ),
            }
        ]

        logger.info("Starting Claude repair session", extra={"model": model})

        for round_num in range(MAX_TOOL_ROUNDS):
            response = client.messages.create(
                model=model,
                max_tokens=4096,
                system=_build_system_prompt(),
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )

            self.memory.log_api_call(
                provider="anthropic",
                tokens_used=response.usage.input_tokens + response.usage.output_tokens,
                task_name="repair_agent",
            )

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                return self._extract_result(assistant_content)

            if response.stop_reason != "tool_use":
                logger.warning(f"Unexpected stop reason: {response.stop_reason}")
                return self._extract_result(assistant_content)

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    logger.info(f"Round {round_num+1}: tool={block.name}",
                                extra={"tool": block.name, "input_keys": list(block.input.keys())})

                    output = execute_tool(block.name, block.input)

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": output.result if output.success else f"ERROR: {output.error}",
                        "is_error": not output.success,
                    })

            messages.append({"role": "user", "content": tool_results})

        logger.warning("Repair session hit max tool rounds")
        return {"fixed": False, "reason": "Hit maximum tool rounds without completing"}

    def _extract_result(self, content) -> dict:
        """Extract the structured JSON result from Claude's final response."""
        text_parts = [b.text for b in content if hasattr(b, "text")]
        full_text = "\n".join(text_parts)

        import re
        json_match = re.search(r'\{[^{}]*"fixed"\s*:\s*(true|false)[^{}]*\}', full_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        return {
            "fixed": False,
            "reason": "Could not parse structured result",
            "raw_response": full_text[:1000],
        }

    def _cleanup_branch(self):
        """Return to main and delete any broken feature branch."""
        branch = _current_branch()
        if branch not in ("main", "master", "unknown"):
            _run_git(["checkout", "main"])
            _run_git(["branch", "-D", branch])
            logger.info(f"Cleaned up branch: {branch}")

    def get_pending_fix_summary(self) -> Optional[str]:
        """Get a summary of the current fix for LINE approval."""
        branch = _current_branch()
        if branch in ("main", "master", "unknown"):
            return None

        diff = git_show_branch_diff()
        status = git_status()

        return (
            f"🔧 自動修復提案\n"
            f"ブランチ: {branch}\n\n"
            f"{status.result}\n\n"
            f"変更内容:\n{diff.result[:2000]}"
        )

    def approve_and_merge(self) -> ToolOutput:
        """Merge the current feature branch into main after approval."""
        branch = _current_branch()
        if branch in ("main", "master", "unknown"):
            return ToolOutput(success=False, result="", error="No feature branch to merge")

        checkout = _run_git(["checkout", "main"])
        if not checkout.success:
            return ToolOutput(success=False, result="", error=f"Failed to checkout main: {checkout.error}")

        merge = _run_git(["merge", "--no-ff", branch, "-m", f"Merge {branch}: auto-repair"])
        if not merge.success:
            _run_git(["merge", "--abort"])
            _run_git(["checkout", branch])
            return ToolOutput(success=False, result="", error=f"Merge conflict: {merge.error}")

        _run_git(["branch", "-d", branch])
        logger.info(f"Merged and deleted branch: {branch}")
        return ToolOutput(success=True, result=f"Merged {branch} into main")

    def reject_and_cleanup(self, reason: str = "") -> ToolOutput:
        """Reject the fix: delete the branch and return to main."""
        branch = _current_branch()
        if branch in ("main", "master", "unknown"):
            return ToolOutput(success=False, result="", error="No feature branch to reject")

        _run_git(["checkout", "main"])
        _run_git(["branch", "-D", branch])
        logger.info(f"Rejected and deleted branch: {branch}", extra={"reason": reason})
        return ToolOutput(success=True, result=f"Rejected fix on {branch}")
