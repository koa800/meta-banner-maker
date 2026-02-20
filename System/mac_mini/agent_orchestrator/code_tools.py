"""
Code Agent tools for autonomous bug fixing.

Provides sandboxed file/git/test operations that Claude API tool_use can invoke.
All write operations are restricted to feature branches — never writes to main directly.
"""

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(os.path.expanduser("~/Desktop/cursor"))
ALLOWED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
    ".md", ".txt", ".sh", ".html", ".css", ".env.example",
}
BLOCKED_PATTERNS = [
    r"\.env$", r"client_secret.*\.json$", r"token.*\.json$",
    r"session\.json$", r"credentials\.json$",
]


@dataclass
class ToolOutput:
    success: bool
    result: str
    error: str = ""


def _is_safe_path(filepath: str) -> bool:
    """Ensure path is within repo and not a secret file."""
    resolved = (REPO_ROOT / filepath).resolve()
    if not str(resolved).startswith(str(REPO_ROOT.resolve())):
        return False
    for pat in BLOCKED_PATTERNS:
        if re.search(pat, str(resolved)):
            return False
    return True


def _run_git(args: list[str], cwd: str = None) -> ToolOutput:
    """Run a git command safely."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True, text=True, timeout=30,
            cwd=cwd or str(REPO_ROOT),
        )
        return ToolOutput(
            success=result.returncode == 0,
            result=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return ToolOutput(success=False, result="", error="Git command timed out")
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def _current_branch() -> str:
    out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    return out.result if out.success else "unknown"


def _is_on_feature_branch() -> bool:
    branch = _current_branch()
    return branch not in ("main", "master", "unknown")


# ── Tool implementations (called by Claude via tool_use) ──

def read_file(path: str, start_line: int = 0, end_line: int = 0) -> ToolOutput:
    """Read a file's contents. Optionally specify line range."""
    if not _is_safe_path(path):
        return ToolOutput(success=False, result="", error=f"Access denied: {path}")

    full_path = REPO_ROOT / path
    if not full_path.exists():
        return ToolOutput(success=False, result="", error=f"File not found: {path}")

    try:
        text = full_path.read_text(encoding="utf-8")
        lines = text.split("\n")

        if start_line > 0 or end_line > 0:
            s = max(0, start_line - 1)
            e = end_line if end_line > 0 else len(lines)
            numbered = [f"{i+s+1:4d}| {l}" for i, l in enumerate(lines[s:e])]
            return ToolOutput(success=True, result="\n".join(numbered))

        if len(lines) > 500:
            numbered = [f"{i+1:4d}| {l}" for i, l in enumerate(lines[:500])]
            return ToolOutput(
                success=True,
                result="\n".join(numbered) + f"\n... ({len(lines) - 500} more lines)"
            )

        numbered = [f"{i+1:4d}| {l}" for i, l in enumerate(lines)]
        return ToolOutput(success=True, result="\n".join(numbered))
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def write_file(path: str, content: str) -> ToolOutput:
    """Write content to a file. Only allowed on feature branches."""
    if not _is_on_feature_branch():
        return ToolOutput(
            success=False, result="",
            error=f"Write blocked: currently on '{_current_branch()}'. Must be on a feature branch."
        )
    if not _is_safe_path(path):
        return ToolOutput(success=False, result="", error=f"Access denied: {path}")

    full_path = REPO_ROOT / path
    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return ToolOutput(success=True, result=f"Written {len(content)} bytes to {path}")
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def patch_file(path: str, old_text: str, new_text: str) -> ToolOutput:
    """Replace a specific text occurrence in a file. Safer than full file writes."""
    if not _is_on_feature_branch():
        return ToolOutput(
            success=False, result="",
            error=f"Patch blocked: currently on '{_current_branch()}'. Must be on a feature branch."
        )
    if not _is_safe_path(path):
        return ToolOutput(success=False, result="", error=f"Access denied: {path}")

    full_path = REPO_ROOT / path
    if not full_path.exists():
        return ToolOutput(success=False, result="", error=f"File not found: {path}")

    try:
        text = full_path.read_text(encoding="utf-8")
        count = text.count(old_text)
        if count == 0:
            return ToolOutput(success=False, result="", error="old_text not found in file")
        if count > 1:
            return ToolOutput(success=False, result="", error=f"old_text found {count} times (must be unique)")

        new_content = text.replace(old_text, new_text, 1)
        full_path.write_text(new_content, encoding="utf-8")
        return ToolOutput(success=True, result=f"Patched {path}: replaced 1 occurrence")
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def list_files(directory: str, pattern: str = "*") -> ToolOutput:
    """List files in a directory, optionally filtered by glob pattern."""
    dir_path = REPO_ROOT / directory
    if not dir_path.exists():
        return ToolOutput(success=False, result="", error=f"Directory not found: {directory}")

    try:
        files = sorted(str(p.relative_to(REPO_ROOT)) for p in dir_path.rglob(pattern) if p.is_file())
        if len(files) > 200:
            files = files[:200]
            files.append(f"... (truncated, >200 files)")
        return ToolOutput(success=True, result="\n".join(files))
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def search_code(pattern: str, path: str = ".", max_results: int = 30) -> ToolOutput:
    """Search for a regex pattern in the codebase using ripgrep."""
    search_path = str(REPO_ROOT / path)
    try:
        result = subprocess.run(
            ["rg", "--no-heading", "--line-number", "--max-count", str(max_results), pattern, search_path],
            capture_output=True, text=True, timeout=15,
        )
        output = result.stdout.strip()
        if not output:
            return ToolOutput(success=True, result="No matches found")

        cleaned = output.replace(str(REPO_ROOT) + "/", "")
        lines = cleaned.split("\n")
        if len(lines) > max_results:
            lines = lines[:max_results]
        return ToolOutput(success=True, result="\n".join(lines))
    except FileNotFoundError:
        result = subprocess.run(
            ["grep", "-rn", "--include=*.py", pattern, search_path],
            capture_output=True, text=True, timeout=15,
        )
        return ToolOutput(success=True, result=result.stdout.strip()[:3000])
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def git_status() -> ToolOutput:
    """Get current git status."""
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    status = _run_git(["status", "--short"])
    return ToolOutput(
        success=True,
        result=f"Branch: {branch.result}\n{status.result}"
    )


def git_diff(staged: bool = False) -> ToolOutput:
    """Show git diff (staged or unstaged)."""
    args = ["diff", "--stat"]
    if staged:
        args.append("--cached")
    stat = _run_git(args)

    detail_args = ["diff"]
    if staged:
        detail_args.append("--cached")
    detail = _run_git(detail_args)

    combined = detail.result
    if len(combined) > 5000:
        combined = combined[:5000] + "\n... (diff truncated)"
    return ToolOutput(success=True, result=f"{stat.result}\n\n{combined}")


def git_create_branch(branch_name: str) -> ToolOutput:
    """Create and switch to a new feature branch from main."""
    if not branch_name.startswith("fix/") and not branch_name.startswith("agent/"):
        branch_name = f"fix/{branch_name}"

    current = _current_branch()
    if current != "main" and current != "master":
        stash = _run_git(["stash"])
        checkout = _run_git(["checkout", "main"])
        if not checkout.success:
            checkout = _run_git(["checkout", "master"])

    result = _run_git(["checkout", "-b", branch_name])
    if result.success:
        return ToolOutput(success=True, result=f"Created and switched to branch: {branch_name}")
    return result


def git_commit(message: str) -> ToolOutput:
    """Stage all changes and commit on the current feature branch."""
    if not _is_on_feature_branch():
        return ToolOutput(
            success=False, result="",
            error=f"Commit blocked: on '{_current_branch()}'. Must be on a feature branch."
        )

    add = _run_git(["add", "-A"])
    if not add.success:
        return add

    return _run_git(["commit", "-m", message])


def git_show_branch_diff() -> ToolOutput:
    """Show all changes on current branch vs main."""
    diff = _run_git(["diff", "main...HEAD"])
    if not diff.success:
        diff = _run_git(["diff", "master...HEAD"])
    if len(diff.result) > 8000:
        return ToolOutput(success=True, result=diff.result[:8000] + "\n... (truncated)")
    return diff


def run_test(test_path: str = "", timeout: int = 120) -> ToolOutput:
    """Run Python tests. If test_path is empty, runs all tests found."""
    python = os.path.expanduser("~/agent-env/bin/python3")
    if not os.path.exists(python):
        python = "python3"

    cmd = [python, "-m", "pytest", "-x", "-v", "--tb=short"]
    if test_path:
        cmd.append(str(REPO_ROOT / test_path))
    else:
        cmd.append(str(REPO_ROOT / "System"))

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        output = result.stdout + "\n" + result.stderr
        if len(output) > 5000:
            output = output[:5000] + "\n... (truncated)"
        return ToolOutput(
            success=result.returncode == 0,
            result=output.strip(),
            error="" if result.returncode == 0 else f"Tests failed (exit code {result.returncode})"
        )
    except subprocess.TimeoutExpired:
        return ToolOutput(success=False, result="", error=f"Tests timed out after {timeout}s")
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


def run_syntax_check(path: str) -> ToolOutput:
    """Run Python syntax check on a file."""
    python = os.path.expanduser("~/agent-env/bin/python3")
    if not os.path.exists(python):
        python = "python3"

    full_path = REPO_ROOT / path
    if not full_path.exists():
        return ToolOutput(success=False, result="", error=f"File not found: {path}")

    try:
        result = subprocess.run(
            [python, "-m", "py_compile", str(full_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return ToolOutput(success=True, result=f"Syntax OK: {path}")
        return ToolOutput(success=False, result="", error=result.stderr.strip())
    except Exception as e:
        return ToolOutput(success=False, result="", error=str(e))


# ── Claude API tool_use schema definitions ──

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read contents of a file in the repository. Returns numbered lines. Optionally read a specific line range.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root (e.g. 'System/line_bot/app.py')"},
                "start_line": {"type": "integer", "description": "Start line number (1-indexed). 0 = from beginning.", "default": 0},
                "end_line": {"type": "integer", "description": "End line number. 0 = until end.", "default": 0},
            },
            "required": ["path"],
        },
    },
    {
        "name": "patch_file",
        "description": "Replace a specific text in a file. The old_text must appear exactly once. Only works on feature branches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "old_text": {"type": "string", "description": "Exact text to find and replace (must be unique in file)"},
                "new_text": {"type": "string", "description": "Replacement text"},
            },
            "required": ["path", "old_text", "new_text"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file (create or overwrite). Only works on feature branches. Prefer patch_file for small changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from repo root"},
                "content": {"type": "string", "description": "Full file content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files in a directory, optionally filtered by glob pattern.",
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {"type": "string", "description": "Relative directory path (e.g. 'System/line_bot/')"},
                "pattern": {"type": "string", "description": "Glob pattern filter (e.g. '*.py')", "default": "*"},
            },
            "required": ["directory"],
        },
    },
    {
        "name": "search_code",
        "description": "Search for a regex pattern in the codebase. Returns matching lines with file paths and line numbers.",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex pattern to search for"},
                "path": {"type": "string", "description": "Subdirectory to search in (default: entire repo)", "default": "."},
                "max_results": {"type": "integer", "description": "Max matches to return", "default": 30},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "git_status",
        "description": "Show current branch and uncommitted changes.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "git_diff",
        "description": "Show detailed diff of current changes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "description": "If true, show only staged changes", "default": False},
            },
        },
    },
    {
        "name": "git_create_branch",
        "description": "Create a new feature branch from main and switch to it. Branch names are auto-prefixed with 'fix/'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "branch_name": {"type": "string", "description": "Branch name (e.g. 'mail-timeout-error')"},
            },
            "required": ["branch_name"],
        },
    },
    {
        "name": "git_commit",
        "description": "Stage all changes and commit. Only works on feature branches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message describing the fix"},
            },
            "required": ["message"],
        },
    },
    {
        "name": "git_show_branch_diff",
        "description": "Show all changes on current feature branch compared to main.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "run_test",
        "description": "Run pytest on the codebase or a specific test file.",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Specific test file path (empty = run all)", "default": ""},
            },
        },
    },
    {
        "name": "run_syntax_check",
        "description": "Check Python syntax of a file without executing it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path to Python file"},
            },
            "required": ["path"],
        },
    },
]

TOOL_DISPATCH = {
    "read_file": lambda **kw: read_file(kw["path"], kw.get("start_line", 0), kw.get("end_line", 0)),
    "patch_file": lambda **kw: patch_file(kw["path"], kw["old_text"], kw["new_text"]),
    "write_file": lambda **kw: write_file(kw["path"], kw["content"]),
    "list_files": lambda **kw: list_files(kw["directory"], kw.get("pattern", "*")),
    "search_code": lambda **kw: search_code(kw["pattern"], kw.get("path", "."), kw.get("max_results", 30)),
    "git_status": lambda **kw: git_status(),
    "git_diff": lambda **kw: git_diff(kw.get("staged", False)),
    "git_create_branch": lambda **kw: git_create_branch(kw["branch_name"]),
    "git_commit": lambda **kw: git_commit(kw["message"]),
    "git_show_branch_diff": lambda **kw: git_show_branch_diff(),
    "run_test": lambda **kw: run_test(kw.get("test_path", "")),
    "run_syntax_check": lambda **kw: run_syntax_check(kw["path"]),
}


def execute_tool(tool_name: str, tool_input: dict) -> ToolOutput:
    """Dispatch a tool call from Claude API response."""
    fn = TOOL_DISPATCH.get(tool_name)
    if not fn:
        return ToolOutput(success=False, result="", error=f"Unknown tool: {tool_name}")
    try:
        return fn(**tool_input)
    except Exception as e:
        return ToolOutput(success=False, result="", error=f"Tool execution error: {e}")
