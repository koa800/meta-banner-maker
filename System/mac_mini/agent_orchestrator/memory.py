"""
SQLite-based memory store for the agent orchestrator.
Tracks task executions, outcomes, and agent state.
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from contextlib import contextmanager


class MemoryStore:
    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _init_db(self):
        """Create tables if they don't exist. Safe to call multiple times (idempotent)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'started',
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    duration_seconds REAL,
                    result_summary TEXT,
                    error_message TEXT,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS api_calls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    provider TEXT NOT NULL,
                    called_at TEXT NOT NULL,
                    tokens_used INTEGER DEFAULT 0,
                    cost_estimate REAL DEFAULT 0.0,
                    task_name TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_log_name ON task_log(task_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_log_started ON task_log(started_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_api_calls_time ON api_calls(called_at)")
            conn.commit()
        finally:
            conn.close()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except sqlite3.OperationalError as e:
            conn.rollback()
            if "no such table" in str(e):
                # テーブルが消えていた場合は再作成してから再スロー
                conn.close()
                self._init_db()
            raise
        finally:
            conn.close()

    def log_task_start(self, task_name: str, metadata: dict = None) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO task_log (task_name, status, started_at, metadata) VALUES (?, 'started', ?, ?)",
                (task_name, datetime.now().isoformat(), json.dumps(metadata or {}))
            )
            return cur.lastrowid

    def log_task_end(self, task_id: int, status: str, result_summary: str = None, error_message: str = None):
        now = datetime.now()
        with self._conn() as conn:
            row = conn.execute("SELECT started_at FROM task_log WHERE id = ?", (task_id,)).fetchone()
            duration = None
            if row:
                started = datetime.fromisoformat(row["started_at"])
                duration = (now - started).total_seconds()

            conn.execute(
                "UPDATE task_log SET status=?, finished_at=?, duration_seconds=?, result_summary=?, error_message=? WHERE id=?",
                (status, now.isoformat(), duration, result_summary, error_message, task_id)
            )

    def log_api_call(self, provider: str, tokens_used: int = 0, cost_estimate: float = 0.0, task_name: str = None):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO api_calls (provider, called_at, tokens_used, cost_estimate, task_name) VALUES (?, ?, ?, ?, ?)",
                (provider, datetime.now().isoformat(), tokens_used, cost_estimate, task_name)
            )

    def get_api_calls_last_hour(self) -> int:
        cutoff = (datetime.now() - timedelta(hours=1)).isoformat()
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM api_calls WHERE called_at > ?", (cutoff,)).fetchone()
            return row["cnt"]

    def get_state(self, key: str, default: str = None) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM agent_state WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else default

    def set_state(self, key: str, value: str):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO agent_state (key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, datetime.now().isoformat())
            )

    def get_recent_tasks(self, limit: int = 20) -> list:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM task_log ORDER BY started_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    def get_task_stats(self, since_hours: int = 24) -> dict:
        cutoff = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT task_name, status, COUNT(*) as cnt FROM task_log WHERE started_at > ? GROUP BY task_name, status",
                (cutoff,)
            ).fetchall()
            stats = {}
            for r in rows:
                name = r["task_name"]
                if name not in stats:
                    stats[name] = {}
                stats[name][r["status"]] = r["cnt"]
            return stats

    def get_daily_summary(self) -> dict:
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        with self._conn() as conn:
            tasks = conn.execute(
                "SELECT COUNT(*) as total, SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as success, "
                "SUM(CASE WHEN status='error' THEN 1 ELSE 0 END) as errors FROM task_log WHERE started_at > ?",
                (today,)
            ).fetchone()
            api = conn.execute(
                "SELECT COUNT(*) as calls, SUM(tokens_used) as tokens FROM api_calls WHERE called_at > ?",
                (today,)
            ).fetchone()
            return {
                "tasks_total": tasks["total"] or 0,
                "tasks_success": tasks["success"] or 0,
                "tasks_errors": tasks["errors"] or 0,
                "api_calls": api["calls"] or 0,
                "api_tokens": api["tokens"] or 0,
            }
