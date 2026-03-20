#!/usr/bin/env python3
"""9224 の Chrome CDP を起動または確認する。"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen


CDP_VERSION_URL = "http://127.0.0.1:9224/json/version"
SYSTEM_DIR = Path(__file__).resolve().parents[1]
DEFAULT_USER_DATA_DIR = SYSTEM_DIR / "data" / "secretary_chrome_profile"
CHROME_BINARY_CANDIDATES = [
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing"),
]


def probe_cdp() -> dict[str, Any] | None:
    try:
        with urlopen(CDP_VERSION_URL, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def find_chrome_binary() -> Path:
    for candidate in CHROME_BINARY_CANDIDATES:
        if candidate.exists():
            return candidate
    raise SystemExit("Google Chrome の binary が見つかりません")


def launch_chrome(user_data_dir: Path) -> subprocess.Popen[bytes]:
    chrome_binary = find_chrome_binary()
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [
            str(chrome_binary),
            "--remote-debugging-port=9224",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def wait_for_cdp(timeout_seconds: float) -> dict[str, Any]:
    started_at = time.time()
    while time.time() - started_at < timeout_seconds:
        payload = probe_cdp()
        if payload:
            return {
                "alive": True,
                "browser": payload.get("Browser"),
                "web_socket_debugger_url": payload.get("webSocketDebuggerUrl"),
            }
        time.sleep(0.5)
    return {"alive": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="9224 の Chrome CDP を起動または確認する")
    parser.add_argument(
        "--user-data-dir",
        default=str(DEFAULT_USER_DATA_DIR),
        help="起動に使う user data dir",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=12,
        help="CDP 起動待ち秒数",
    )
    args = parser.parse_args()

    existing = probe_cdp()
    if existing:
        print(
            json.dumps(
                {
                    "status": "already_alive",
                    "browser": existing.get("Browser"),
                    "web_socket_debugger_url": existing.get("webSocketDebuggerUrl"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    launch_chrome(Path(args.user_data_dir))
    result = wait_for_cdp(args.timeout)
    result["status"] = "launched" if result.get("alive") else "launch_failed"
    result["user_data_dir"] = str(args.user_data_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
