#!/usr/bin/env python3
"""Addness automation 用の Python ランタイム解決ヘルパー。"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


HOME = Path.home()
DEFAULT_MIN_VERSION = "3.10"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Resolve the preferred Python runtime for Addness automation."
    )
    parser.add_argument("--min", default=DEFAULT_MIN_VERSION, help="Preferred minimum version. Default: 3.10")
    parser.add_argument("--strict", action="store_true", help="Exit 1 when the selected runtime is below --min.")
    parser.add_argument("--print-path", action="store_true", help="Print only the selected interpreter path.")
    parser.add_argument("--print-version", action="store_true", help="Print only the selected interpreter version.")
    parser.add_argument("--json", action="store_true", help="Print resolver result as JSON.")
    return parser.parse_args()


def normalize_version(value):
    parts = []
    for part in str(value).split("."):
        digits = "".join(ch for ch in part if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def candidate_specs():
    env_python = os.environ.get("ADDNESS_PYTHON", "").strip()
    specs = []
    if env_python:
        specs.append({"label": "env:ADDNESS_PYTHON", "value": env_python, "kind": "path"})

    specs.extend(
        [
            {"label": "venv:agent-env", "value": str(HOME / "agent-env" / "bin" / "python3"), "kind": "path"},
            {"label": "brew:/opt/homebrew/bin/python3.12", "value": "/opt/homebrew/bin/python3.12", "kind": "path"},
            {"label": "brew:/opt/homebrew/bin/python3.11", "value": "/opt/homebrew/bin/python3.11", "kind": "path"},
            {"label": "brew:/opt/homebrew/bin/python3.10", "value": "/opt/homebrew/bin/python3.10", "kind": "path"},
            {"label": "brew:/usr/local/bin/python3.12", "value": "/usr/local/bin/python3.12", "kind": "path"},
            {"label": "brew:/usr/local/bin/python3.11", "value": "/usr/local/bin/python3.11", "kind": "path"},
            {"label": "brew:/usr/local/bin/python3.10", "value": "/usr/local/bin/python3.10", "kind": "path"},
        ]
    )

    if sys.executable:
        specs.append({"label": "sys.executable", "value": sys.executable, "kind": "path"})

    specs.extend(
        [
            {"label": "command:python3.12", "value": "python3.12", "kind": "command"},
            {"label": "command:python3.11", "value": "python3.11", "kind": "command"},
            {"label": "command:python3.10", "value": "python3.10", "kind": "command"},
            {"label": "command:python3", "value": "python3", "kind": "command"},
        ]
    )
    return specs


def resolve_candidate(spec):
    if spec["kind"] == "path":
        path = Path(spec["value"]).expanduser()
        if not path.exists():
            return None
        return {
            "invoke_path": str(path),
            "resolved_path": str(path.resolve()),
        }

    resolved = shutil.which(spec["value"])
    if not resolved:
        return None
    return {
        "invoke_path": resolved,
        "resolved_path": str(Path(resolved).resolve()),
    }


def inspect_candidate(spec, candidate):
    probe = subprocess.run(
        [
            candidate["invoke_path"],
            "-c",
            (
                "import json,platform,sys;"
                "print(json.dumps({"
                "'path': sys.executable,"
                "'version': platform.python_version(),"
                "'major': sys.version_info[0],"
                "'minor': sys.version_info[1],"
                "'micro': sys.version_info[2]"
                "}))"
            ),
        ],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if probe.returncode != 0:
        return None
    data = json.loads(probe.stdout.strip())
    data["label"] = spec["label"]
    data["requested"] = spec["value"]
    data["resolved_path"] = candidate["resolved_path"]
    return data


def collect_candidates():
    seen = set()
    results = []
    for spec in candidate_specs():
        candidate = resolve_candidate(spec)
        if not candidate or candidate["resolved_path"] in seen:
            continue
        seen.add(candidate["resolved_path"])
        info = inspect_candidate(spec, candidate)
        if info:
            results.append(info)
    return results


def choose_runtime(candidates, min_version):
    minimum = normalize_version(min_version)
    selected = None
    for candidate in candidates:
        version = normalize_version(candidate["version"])
        candidate["meets_min"] = version >= minimum
        if selected is None and candidate["meets_min"]:
            selected = candidate
    if selected is None and candidates:
        selected = candidates[0]
    return selected


def main():
    args = parse_args()
    candidates = collect_candidates()
    selected = choose_runtime(candidates, args.min)
    result = {
        "selected": selected,
        "min_version": args.min,
        "strict": args.strict,
        "candidates": candidates,
    }

    if not selected:
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    meets_min = selected.get("meets_min", False)
    if args.print_path:
        if args.strict and not meets_min:
            return 1
        print(selected["path"])
        return 0

    if args.print_version:
        if args.strict and not meets_min:
            return 1
        print(selected["version"])
        return 0

    if args.json or (not args.print_path and not args.print_version):
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.strict and not meets_min:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
