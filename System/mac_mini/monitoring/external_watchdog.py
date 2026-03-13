#!/usr/bin/env python3
"""
Mac Mini 外部死活監視 — MacBook から Mac Mini の health endpoint を定期監視し、
異常時に LINE 通知を送る。

launchd で10分ごとに実行する想定。
連続 N 回失敗で初回アラート → 復旧で回復通知。

依存: stdlib のみ（requests 不要）。launchd の TCC 制限を避けるため
~/.config/addness/monitoring/ にデプロイして実行する。
"""

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

DEPLOY_DIR = Path.home() / ".config" / "addness" / "monitoring"
STATE_FILE = DEPLOY_DIR / "watchdog_state.json"

MAC_MINI_HOST = os.environ.get("MAC_MINI_HOST", "mac-mini-agent")
MAC_MINI_PORT = int(os.environ.get("MAC_MINI_PORT", "8500"))
HEALTH_URL = f"http://{MAC_MINI_HOST}:{MAC_MINI_PORT}/health"

ALERT_AFTER_FAILURES = 2
TIMEOUT = 15


def _load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"consecutive_failures": 0, "alerted": False, "last_check": None, "last_status": None}


def _save_state(state: dict):
    state["last_check"] = datetime.now().isoformat()
    DEPLOY_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def _load_line_config() -> tuple:
    """line_bot_local/config.json から agent_token と server_url を取得する。"""
    candidates = [
        Path.home() / ".config" / "addness" / "line_config.json",
        Path.home() / "Library" / "LineBot" / "config.json",
        Path.home() / "Desktop" / "cursor" / "System" / "line_bot_local" / "config.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                cfg = json.loads(p.read_text())
                token = str(cfg.get("agent_token", "")).strip()
                server = str(cfg.get("server_url", "")).strip()
                if token and server:
                    return token, server
            except (json.JSONDecodeError, OSError):
                continue
    return "", ""


def _send_line(message: str):
    token, server = _load_line_config()
    if not token or not server:
        print("WARN: LINE config not found, skipping notification", file=sys.stderr)
        return

    if len(message) > 990:
        message = message[:990] + "\n...(truncated)"

    data = json.dumps({"message": message}).encode("utf-8")
    req = urllib.request.Request(
        f"{server}/notify",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            if resp.status == 200:
                print("✅ LINE通知送信完了")
            else:
                print(f"WARN: LINE notify returned {resp.status}", file=sys.stderr)
    except Exception as e:
        print(f"WARN: LINE notify failed: {e}", file=sys.stderr)


def _check_health() -> dict:
    """Returns {"ok": bool, "detail": str, "data": dict|None}."""
    try:
        req = urllib.request.Request(HEALTH_URL, method="GET")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return {"ok": True, "detail": f"HTTP 200 — agent={data.get('agent', '?')}", "data": data}
            return {"ok": False, "detail": f"HTTP {resp.status}", "data": None}
    except urllib.error.URLError as e:
        reason = str(getattr(e, "reason", e))[:200]
        return {"ok": False, "detail": f"Unreachable: {reason}", "data": None}
    except TimeoutError:
        return {"ok": False, "detail": f"Timeout ({TIMEOUT}s)", "data": None}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:200], "data": None}


def main():
    state = _load_state()
    result = _check_health()
    now_str = datetime.now().strftime("%H:%M")

    if result["ok"]:
        if state["alerted"]:
            failures = state["consecutive_failures"]
            _send_line(
                f"✅ Mac Mini 復旧\n"
                f"━━━━━━━━━━━━\n"
                f"ヘルス: {result['detail']}\n"
                f"連続失敗: {failures}回 → 復旧\n"
                f"確認時刻: {now_str}"
            )
        state["consecutive_failures"] = 0
        state["alerted"] = False
        state["last_status"] = "ok"
    else:
        state["consecutive_failures"] += 1
        state["last_status"] = result["detail"]

        if state["consecutive_failures"] >= ALERT_AFTER_FAILURES and not state["alerted"]:
            _send_line(
                f"🚨 Mac Mini 応答なし\n"
                f"━━━━━━━━━━━━\n"
                f"URL: {HEALTH_URL}\n"
                f"原因: {result['detail']}\n"
                f"連続失敗: {state['consecutive_failures']}回\n"
                f"確認時刻: {now_str}\n"
                f"━━━━━━━━━━━━\n"
                f"対処: Mac Miniの電源・ネットワーク・orchestratorプロセスを確認"
            )
            state["alerted"] = True

    _save_state(state)

    status_icon = "✅" if result["ok"] else "❌"
    print(f"{status_icon} [{now_str}] {result['detail']} (failures={state['consecutive_failures']})")


if __name__ == "__main__":
    main()
