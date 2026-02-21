"""
Main orchestrator process for the Mac Mini AI agent.
Combines scheduled tasks, a webhook listener, and an LLM-driven brain.
"""

import asyncio
import logging
import os
import signal
import sys
import yaml
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .memory import MemoryStore
from .scheduler import TaskScheduler
from .repair_agent import RepairAgent
from .shared_logger import get_logger, setup_error_log
from .notifier import (
    notify_repair_proposal, notify_repair_result,
    notify_error_detected, send_line_notify,
)
from .code_tools import _current_branch, git_show_branch_diff
from . import tools

logger = get_logger("orchestrator")

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


class AgentOrchestrator:
    def __init__(self, config: dict):
        self.config = config
        self.memory = MemoryStore(config["paths"]["db_path"])
        self.task_scheduler = TaskScheduler(config, self.memory)
        self.repair_agent = RepairAgent(self.memory, config)
        self.app = self._create_app()
        self._shutdown_event = asyncio.Event()

    def _create_app(self) -> FastAPI:
        app = FastAPI(title="Mac Mini Agent", docs_url="/docs")

        @app.get("/health")
        async def health():
            summary = self.memory.get_daily_summary()
            return {
                "status": "ok",
                "agent": self.config["agent"]["name"],
                "today": summary,
            }

        @app.get("/sync-status")
        async def sync_status():
            import json
            import subprocess
            status_path = os.path.expanduser(
                "~/agents/System/mac_mini/agent_orchestrator/sync_status.json"
            )
            repo_dir = os.path.expanduser("~/agents/_repo")
            result = {"mac_mini": None, "repo_head": None}
            if os.path.exists(status_path):
                with open(status_path) as f:
                    result["mac_mini"] = json.load(f)
            try:
                head = subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=repo_dir, text=True
                ).strip()
                msg = subprocess.check_output(
                    ["git", "log", "-1", "--format=%s", "HEAD"], cwd=repo_dir, text=True
                ).strip()
                ts = subprocess.check_output(
                    ["git", "log", "-1", "--format=%ci", "HEAD"], cwd=repo_dir, text=True
                ).strip()
                result["repo_head"] = {"commit": head, "message": msg, "date": ts}
            except Exception:
                pass
            return result

        @app.get("/tasks")
        async def tasks():
            return self.memory.get_recent_tasks(limit=50)

        @app.get("/stats")
        async def stats():
            return self.memory.get_task_stats(since_hours=24)

        @app.post("/run/{task_name}")
        async def run_task(task_name: str):
            if task_name not in tools.TOOL_REGISTRY:
                return JSONResponse(status_code=404, content={"error": f"Unknown task: {task_name}"})

            api_calls = self.memory.get_api_calls_last_hour()
            limit = self.config.get("safety", {}).get("api_call_limit_per_hour", 100)
            if api_calls >= limit:
                return JSONResponse(status_code=429, content={"error": "API call limit reached"})

            entry = tools.TOOL_REGISTRY[task_name]
            task_id = self.memory.log_task_start(task_name, metadata={"trigger": "webhook"})
            try:
                result = entry["fn"]()
                status = "success" if result.success else "error"
                self.memory.log_task_end(
                    task_id, status,
                    result_summary=result.output[:500] if result.output else None,
                    error_message=result.error[:500] if result.error else None
                )
                return {
                    "task": task_name,
                    "status": status,
                    "output": result.output[:1000],
                    "error": result.error[:500] if result.error else None,
                }
            except Exception as e:
                self.memory.log_task_end(task_id, "error", error_message=str(e))
                return JSONResponse(status_code=500, content={"error": str(e)})

        @app.post("/webhook/line")
        async def line_webhook(request: Request):
            body = await request.json()
            self.memory.set_state("last_line_webhook", str(body)[:1000])
            logger.info(f"LINE webhook received: {str(body)[:200]}")
            return {"status": "received"}

        # ── Repair Agent endpoints ──

        @app.post("/repair/run")
        async def repair_run():
            """Trigger a repair check manually."""
            result = self.repair_agent.check_and_repair()
            if result and result.get("fixed"):
                branch = _current_branch()
                diff = git_show_branch_diff()
                desc = result.get("description", "auto-fix")
                base_url = f"http://localhost:{self.config.get('webhook', {}).get('port', 8500)}"
                notify_repair_proposal(branch, desc, diff.result, base_url)
            return {"result": result}

        @app.post("/repair/approve")
        async def repair_approve():
            """Approve and merge the current repair branch."""
            branch = _current_branch()
            output = self.repair_agent.approve_and_merge()
            action = "merged" if output.success else "failed"
            notify_repair_result(branch, action, output.result or output.error)
            return {"success": output.success, "message": output.result, "error": output.error}

        @app.post("/repair/reject")
        async def repair_reject(request: Request):
            """Reject the current repair and delete the branch."""
            body = {}
            try:
                body = await request.json()
            except Exception:
                pass
            reason = body.get("reason", "rejected by user")
            branch = _current_branch()
            output = self.repair_agent.reject_and_cleanup(reason)
            notify_repair_result(branch, "rejected", reason)
            return {"success": output.success, "message": output.result}

        @app.get("/repair/status")
        async def repair_status():
            """Get current repair branch status and pending diff."""
            summary = self.repair_agent.get_pending_fix_summary()
            return {"has_pending_fix": summary is not None, "summary": summary}

        @app.get("/schedule/status")
        async def schedule_status():
            """Get schedule status: next run time and last execution for all jobs."""
            jobs = self.task_scheduler.scheduler.get_jobs()
            result = []
            for job in jobs:
                next_run = job.next_run_time
                last_run = self.memory.get_state(f"last_success_{job.id}")
                last_err = self.memory.get_state(f"failure_notified_{job.id}")
                result.append({
                    "id": job.id,
                    "next_run": next_run.isoformat() if next_run else None,
                    "last_success": last_run,
                    "last_failure_notified": last_err,
                })
            return {"jobs": result, "total": len(result)}

        @app.post("/schedule/run/{task_name}")
        async def schedule_run(task_name: str):
            """Manually trigger a scheduled task by name."""
            task_fn = self.task_scheduler._task_map.get(task_name)
            if task_fn is None:
                available = list(self.task_scheduler._task_map.keys())
                return JSONResponse(
                    status_code=404,
                    content={"error": f"Unknown task: {task_name}", "available": available}
                )
            # バックグラウンドで非同期実行（レスポンスをブロックしない）
            asyncio.create_task(task_fn())
            logger.info(f"Manual trigger: {task_name}")
            return {"status": "triggered", "task": task_name}

        return app

    async def start(self):
        logger.info("Starting Agent Orchestrator...")

        from .scheduler import set_repair_agent
        set_repair_agent(self.repair_agent)

        self.task_scheduler.setup()
        self.task_scheduler.start()

        webhook_cfg = self.config.get("webhook", {})
        if webhook_cfg.get("enabled", False):
            config = uvicorn.Config(
                self.app,
                host=webhook_cfg.get("host", "0.0.0.0"),
                port=webhook_cfg.get("port", 8500),
                log_level="info",
            )
            server = uvicorn.Server(config)
            logger.info(f"Webhook server starting on {webhook_cfg['host']}:{webhook_cfg['port']}")
            await server.serve()
        else:
            logger.info("Webhook disabled, running scheduler only")
            await self._shutdown_event.wait()

    def stop(self):
        logger.info("Shutting down Agent Orchestrator...")
        self.task_scheduler.shutdown()
        self._shutdown_event.set()


def setup_logging(level: str = "INFO"):
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO), format=log_format)

    log_dir = os.path.expanduser(
        os.environ.get("AGENT_LOG_DIR",
                       os.path.join(os.path.dirname(__file__), "logs"))
    )
    os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.FileHandler(os.path.join(log_dir, "orchestrator.log"))
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format))
    logging.getLogger().addHandler(file_handler)

    setup_error_log()


def main():
    config = load_config()
    setup_logging(config.get("agent", {}).get("log_level", "INFO"))

    orchestrator = AgentOrchestrator(config)

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        orchestrator.stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(orchestrator.start())
    except KeyboardInterrupt:
        orchestrator.stop()


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    main()
