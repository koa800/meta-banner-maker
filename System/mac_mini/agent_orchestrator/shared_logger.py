"""
Structured error logging for all agent scripts.
Provides JSON-structured logs that the repair agent can parse to diagnose and fix bugs.

Usage in any script:
    from mac_mini.agent_orchestrator.shared_logger import get_logger
    logger = get_logger("script_name")

    logger.info("Processing started", extra={"user": "kohara", "count": 5})
    try:
        ...
    except Exception as e:
        logger.exception("Failed to process", extra={"input": data[:200]})
"""

import json
import logging
import os
import traceback
import sys
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

LOG_DIR = Path(os.environ.get(
    "AGENT_LOG_DIR",
    os.path.join(os.path.dirname(__file__), "logs")
))
ERROR_LOG = LOG_DIR / "errors.jsonl"
ALL_LOG = LOG_DIR / "all.jsonl"

LOG_DIR.mkdir(parents=True, exist_ok=True)


class StructuredFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "file": record.pathname,
            "line": record.lineno,
            "func": record.funcName,
            "msg": record.getMessage(),
        }

        if hasattr(record, "extra_data"):
            entry["data"] = record.extra_data

        if record.exc_info and record.exc_info[1]:
            exc = record.exc_info[1]
            entry["error"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        return json.dumps(entry, ensure_ascii=False, default=str)


class ExtraAdapter(logging.LoggerAdapter):
    """Adapter that merges 'extra' dict into log records for structured output."""

    def process(self, msg, kwargs):
        extra_data = kwargs.pop("extra", None)
        if extra_data:
            kwargs.setdefault("extra", {})["extra_data"] = extra_data
        return msg, kwargs


def get_logger(name: str, level: str = "DEBUG") -> ExtraAdapter:
    """Create a structured logger that writes JSON to both console and file."""
    logger = logging.getLogger(f"agent.{name}")

    if logger.handlers:
        return ExtraAdapter(logger, {})

    logger.setLevel(getattr(logging, level.upper(), logging.DEBUG))
    logger.propagate = False

    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%H:%M:%S"
    ))
    logger.addHandler(console)

    all_handler = RotatingFileHandler(
        str(ALL_LOG), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    all_handler.setLevel(logging.DEBUG)
    all_handler.setFormatter(StructuredFormatter())
    logger.addHandler(all_handler)

    err_handler = RotatingFileHandler(
        str(ERROR_LOG), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(StructuredFormatter())
    logger.addHandler(err_handler)

    return ExtraAdapter(logger, {})


def setup_error_log():
    """Attach the structured error handler to the root logger.

    Call once at startup so that even libraries using the standard root logger
    have their ERROR+ messages captured in errors.jsonl for the repair agent.
    """
    root = logging.getLogger()
    tag = "_structured_error_attached"
    if getattr(root, tag, False):
        return
    err_handler = RotatingFileHandler(
        str(ERROR_LOG), maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(StructuredFormatter())
    root.addHandler(err_handler)
    setattr(root, tag, True)


def read_recent_errors(max_lines: int = 50) -> list[dict]:
    """Read recent errors from the JSONL error log. Used by the repair agent."""
    if not ERROR_LOG.exists():
        return []

    lines = ERROR_LOG.read_text(encoding="utf-8").strip().split("\n")
    recent = lines[-max_lines:]
    errors = []
    for line in recent:
        try:
            errors.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return errors


def read_errors_for_file(filepath: str, max_lines: int = 20) -> list[dict]:
    """Read errors related to a specific file path."""
    all_errors = read_recent_errors(max_lines=200)
    return [e for e in all_errors if filepath in e.get("file", "")][:max_lines]
