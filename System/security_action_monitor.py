#!/usr/bin/env python3
"""
SECURITY ACTION の自己宣言IDメールを監視し、状態を更新する。

役割:
- 個人Gmailから SECURITY ACTION / 自己宣言ID のメールを検索
- 自己宣言ID（4で始まる11桁）を抽出
- 初回検知時のみ状態ファイルを更新
- 補助金メモの監視ステータス欄を自動更新
"""

from __future__ import annotations

import base64
import html
import json
import re
import socket
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from mail_manager import get_gmail_service, get_header, parse_sender  # noqa: E402

STATE_PATH = BASE_DIR / "data" / "security_action_monitor.json"
RADAR_PATH = BASE_DIR.parent / "Master" / "output" / "経理" / "2026-03-10_補助金減免レーダー.md"

STATUS_START = "<!-- SECURITY_ACTION_STATUS_START -->"
STATUS_END = "<!-- SECURITY_ACTION_STATUS_END -->"
ID_PATTERN = re.compile(r"\b4\d{10}\b")


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_state() -> dict:
    if not STATE_PATH.exists():
        return {
            "last_checked_at": "",
            "found": False,
            "self_declaration_id": "",
            "message_id": "",
            "subject": "",
            "sender": "",
            "mail_date": "",
            "detected_at": "",
            "last_error": "",
        }
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_checked_at": "",
            "found": False,
            "self_declaration_id": "",
            "message_id": "",
            "subject": "",
            "sender": "",
            "mail_date": "",
            "detected_at": "",
            "last_error": "",
        }


def _save_state(state: dict) -> None:
    _ensure_parent(STATE_PATH)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _decode_part_data(data: str) -> str:
    try:
        return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _payload_text(payload: dict) -> str:
    texts: list[str] = []

    def walk(part: dict) -> None:
        mime = (part.get("mimeType") or "").lower()
        body = part.get("body", {})
        data = body.get("data")
        if data and mime.startswith("text/"):
            text = _decode_part_data(data)
            if "html" in mime:
                text = html.unescape(re.sub(r"<[^>]+>", " ", text))
            if text:
                texts.append(text)
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload or {})
    return "\n".join(texts)


def _update_radar_status(state: dict) -> None:
    if not RADAR_PATH.exists():
        return

    text = RADAR_PATH.read_text(encoding="utf-8")
    detected = "未検知"
    detected_detail = "メール待ち"
    if state.get("found") and state.get("self_declaration_id"):
        detected = state["self_declaration_id"]
        detected_detail = (
            f"件名: {state.get('subject', '')}\n"
            f"- 検知日時: `{state.get('detected_at', '')}`\n"
            f"- 送信元: `{state.get('sender', '')}`\n"
            f"- 次の状態: `IT導入補助金の対象ツール精査に進める`"
        )

    block = (
        f"{STATUS_START}\n"
        f"- 監視: `有効`\n"
        f"- 最新検知: `{detected}`\n"
        f"- 詳細:\n"
        f"  {detected_detail.replace(chr(10), chr(10) + '  ')}\n"
        f"- 最終確認: `{state.get('last_checked_at', '')}`\n"
        f"- 最新エラー: `{state.get('last_error', '') or 'なし'}`\n"
        f"{STATUS_END}"
    )

    if STATUS_START in text and STATUS_END in text:
        text = re.sub(
            rf"{re.escape(STATUS_START)}.*?{re.escape(STATUS_END)}",
            block,
            text,
            flags=re.S,
        )
    else:
        text += f"\n\n## SECURITY ACTION 自動監視\n\n{block}\n"

    RADAR_PATH.write_text(text, encoding="utf-8")


def _search_security_action_mail() -> dict | None:
    previous_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(15)
    service = get_gmail_service("personal")
    try:
        query = '("SECURITY ACTION" OR "自己宣言ID") newer_than:60d'
        result = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
        messages = result.get("messages", [])

        for item in messages:
            msg = service.users().messages().get(userId="me", id=item["id"], format="full").execute()
            subject = get_header(msg, "Subject")
            sender = parse_sender(msg.get("payload", {}).get("headers", []))
            mail_date = get_header(msg, "Date")
            snippet = msg.get("snippet", "") or ""
            body = _payload_text(msg.get("payload", {}))
            combined = "\n".join([subject, snippet, body])
            match = ID_PATTERN.search(combined)
            if not match:
                continue
            return {
                "message_id": item["id"],
                "subject": subject,
                "sender": sender,
                "mail_date": mail_date,
                "self_declaration_id": match.group(0),
            }
        return None
    finally:
        socket.setdefaulttimeout(previous_timeout)


def main() -> int:
    now = datetime.now().isoformat(timespec="seconds")
    state = _load_state()
    state["last_checked_at"] = now
    state["last_error"] = ""

    try:
        found = _search_security_action_mail()
    except Exception as e:
        state["last_error"] = str(e)
        _save_state(state)
        _update_radar_status(state)
        print(
            json.dumps(
                {
                    "status": "error",
                    "new_id_detected": False,
                    "error": str(e),
                    "last_checked_at": now,
                },
                ensure_ascii=False,
            )
        )
        return 0
    if not found:
        _save_state(state)
        _update_radar_status(state)
        print(
            json.dumps(
                {
                    "status": "not_found",
                    "new_id_detected": False,
                    "self_declaration_id": state.get("self_declaration_id", ""),
                    "last_checked_at": now,
                },
                ensure_ascii=False,
            )
        )
        return 0

    new_id_detected = found["self_declaration_id"] != state.get("self_declaration_id")
    state.update(found)
    state["found"] = True
    if new_id_detected:
        state["detected_at"] = now
    elif not state.get("detected_at"):
        state["detected_at"] = now

    _save_state(state)
    _update_radar_status(state)

    print(
        json.dumps(
            {
                "status": "found",
                "new_id_detected": new_id_detected,
                "self_declaration_id": state["self_declaration_id"],
                "message_id": state["message_id"],
                "subject": state["subject"],
                "sender": state["sender"],
                "mail_date": state["mail_date"],
                "detected_at": state["detected_at"],
                "last_checked_at": state["last_checked_at"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
