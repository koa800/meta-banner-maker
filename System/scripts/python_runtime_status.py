#!/usr/bin/env python3
"""Python ランタイムまわりの実機状態を確認する診断スクリプト。"""

import importlib.util
import json
import plistlib
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RESOLVER_PATH = SCRIPT_DIR / "python_runtime.py"
HOME = Path.home()
MIN_VERSION = "3.10"


def load_resolver():
    spec = importlib.util.spec_from_file_location("python_runtime", RESOLVER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


resolver = load_resolver()


def load_plist(path):
    if not path.exists():
        return None
    with path.open("rb") as handle:
        return plistlib.load(handle)


def version_tuple(value):
    return resolver.normalize_version(value)


def resolver_status():
    candidates = resolver.collect_candidates()
    selected = resolver.choose_runtime(candidates, MIN_VERSION)
    return {
        "selected": selected,
        "candidate_count": len(candidates),
    }


def python_binary_status(path):
    path = Path(path).expanduser()
    if not path.exists():
        return {"exists": False, "path": str(path)}

    try:
        output = path.readlink()
    except OSError:
        output = None

    import subprocess

    probe = subprocess.run(
        [
            str(path),
            "-c",
            "import platform,sys; print(platform.python_version())",
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    version = probe.stdout.strip() if probe.returncode == 0 else "unknown"
    return {
        "exists": True,
        "path": str(path.resolve()),
        "version": version,
        "meets_min": version_tuple(version) >= version_tuple(MIN_VERSION),
        "symlink_target": str(output) if output else "",
    }


def plist_status(path, expected_substrings, label):
    data = load_plist(path)
    if data is None:
        return {
            "label": label,
            "exists": False,
            "path": str(path),
            "program_arguments": [],
            "checks": [],
        }

    args = [str(item) for item in data.get("ProgramArguments", [])]
    checks = []
    joined = " ".join(args)
    for needle in expected_substrings:
        checks.append({"needle": needle, "ok": needle in joined})

    return {
        "label": label,
        "exists": True,
        "path": str(path),
        "program_arguments": args,
        "checks": checks,
        "env_python": data.get("EnvironmentVariables", {}).get("ADDNESS_PYTHON", ""),
    }


def build_report():
    runtime = resolver_status()
    venv = python_binary_status(HOME / "agent-env" / "bin" / "python3")
    local_agent_plist = plist_status(
        HOME / "Library" / "LaunchAgents" / "com.linebot.localagent.plist",
        ["run_agent.sh"],
        "local_agent",
    )
    orchestrator_plist = plist_status(
        HOME / "Library" / "LaunchAgents" / "com.addness.agent-orchestrator.plist",
        ["agent_orchestrator"],
        "orchestrator",
    )
    service_watchdog_plist = plist_status(
        HOME / "Library" / "LaunchAgents" / "com.addness.service-watchdog.plist",
        ["service_watchdog.sh"],
        "service_watchdog",
    )

    suggestions = []
    selected = runtime["selected"]
    if not selected or not selected.get("meets_min"):
        suggestions.append("3.10+ の Python が選べていません。Mac Mini では setup_phase1.sh を再実行してください。")
    if not venv.get("exists"):
        suggestions.append("~/agent-env/bin/python3 がありません。setup_phase1.sh で仮想環境を作成してください。")
    elif not venv.get("meets_min"):
        suggestions.append("~/agent-env/bin/python3 が 3.10 未満です。setup_phase1.sh で仮想環境を作り直してください。")
    if local_agent_plist["exists"] and not all(check["ok"] for check in local_agent_plist["checks"]):
        suggestions.append("local_agent の launchd が旧形式です。System/line_bot_local/install.sh を再実行してください。")
    if not local_agent_plist["exists"]:
        suggestions.append("local_agent の launchd が未インストールです。System/line_bot_local/install.sh を実行してください。")
    if orchestrator_plist["exists"] and not orchestrator_plist.get("env_python"):
        suggestions.append("orchestrator の launchd に ADDNESS_PYTHON がありません。System/mac_mini/install_orchestrator.sh を再実行してください。")
    if not orchestrator_plist["exists"]:
        suggestions.append("orchestrator の launchd が未インストールです。System/mac_mini/install_orchestrator.sh を実行してください。")
    if not service_watchdog_plist["exists"]:
        suggestions.append("service_watchdog の launchd が未インストールです。System/mac_mini/monitoring/install_service_watchdog.sh を実行してください。")

    return {
        "resolver": runtime,
        "agent_env": venv,
        "plists": [local_agent_plist, orchestrator_plist, service_watchdog_plist],
        "suggestions": suggestions,
    }


def format_report(report):
    lines = []
    selected = report["resolver"]["selected"]
    if selected:
        state = "OK" if selected.get("meets_min") else "WARN"
        lines.append(
            f"[resolver] {state} path={selected['path']} version={selected['version']} candidates={report['resolver']['candidate_count']}"
        )
    else:
        lines.append("[resolver] WARN path=none version=none candidates=0")

    agent_env = report["agent_env"]
    if agent_env["exists"]:
        state = "OK" if agent_env.get("meets_min") else "WARN"
        lines.append(f"[agent-env] {state} path={agent_env['path']} version={agent_env['version']}")
    else:
        lines.append(f"[agent-env] WARN missing path={agent_env['path']}")

    for plist in report["plists"]:
        if not plist["exists"]:
            lines.append(f"[{plist['label']}] WARN missing path={plist['path']}")
            continue

        if plist["checks"] and all(check["ok"] for check in plist["checks"]):
            state = "OK"
        else:
            state = "WARN"

        args = " | ".join(plist["program_arguments"])
        lines.append(f"[{plist['label']}] {state} plist={plist['path']}")
        lines.append(f"  args={args}")
        if plist.get("env_python"):
            lines.append(f"  ADDNESS_PYTHON={plist['env_python']}")

    if report["suggestions"]:
        lines.append("")
        lines.append("[next]")
        for suggestion in report["suggestions"]:
            lines.append(f"- {suggestion}")
    else:
        lines.append("")
        lines.append("[next]")
        lines.append("- 追加対応は不要です。")
    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Show Python runtime rollout status.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args()

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(format_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
