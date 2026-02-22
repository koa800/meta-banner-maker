#!/usr/bin/env python3
"""
LINE通知ヘルパー — Cursor環境からLINE秘書グループにメッセージを送信する。

使い方:
    python3 System/line_notify.py "メッセージ本文"
    python3 System/line_notify.py --file /path/to/message.txt

config.json の agent_token を使って Render サーバーの /notify エンドポイントに送信する。
"""

import json
import os
import sys
import requests

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "line_bot_local", "config.json")
MAX_MESSAGE_LEN = 990


def _load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)


def send(message: str) -> bool:
    cfg = _load_config()
    token = cfg.get("agent_token", "")
    server = cfg.get("server_url", "")

    if not token or not server:
        print("ERROR: agent_token or server_url missing in config.json", file=sys.stderr)
        return False

    if len(message) > MAX_MESSAGE_LEN:
        message = message[:MAX_MESSAGE_LEN] + "\n...(truncated)"

    try:
        resp = requests.post(
            f"{server}/notify",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message},
            timeout=40,
        )
        if resp.status_code == 200:
            print("✅ LINE通知送信完了")
            return True
        else:
            print(f"ERROR: status={resp.status_code} body={resp.text[:200]}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 line_notify.py \"メッセージ\" | --file path", file=sys.stderr)
        sys.exit(1)

    if sys.argv[1] == "--file":
        if len(sys.argv) < 3:
            print("Usage: python3 line_notify.py --file /path/to/message.txt", file=sys.stderr)
            sys.exit(1)
        with open(sys.argv[2]) as f:
            message = f.read().strip()
    else:
        message = " ".join(sys.argv[1:])

    success = send(message)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
