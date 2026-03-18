#!/usr/bin/env python3
"""TikTok for Business の認証コードを Gmail から取得する。"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import message_from_bytes
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "System"))

import mail_manager  # noqa: E402


JST = timezone(timedelta(hours=9))
DEFAULT_ACCOUNT = "adteam"
CODE_PATTERNS = [
    re.compile(r"\b(\d{6})\b"),
    re.compile(r"verification code[^0-9]*(\d{6})", re.IGNORECASE),
    re.compile(r"認証コード[^0-9]*(\d{6})"),
    re.compile(r"verification code[^A-Za-z0-9]*([A-Za-z0-9]{6})", re.IGNORECASE),
    re.compile(r"TikTok Marketing API:\s*([A-Za-z0-9]{6})", re.IGNORECASE),
    re.compile(r"ログイン用コード[^A-Za-z0-9]*([A-Za-z0-9]{6})"),
    re.compile(r"\b([A-Za-z0-9]{6})\b"),
]
SUBJECT_KEYWORDS = ["TikTok", "verification", "認証", "code"]
FROM_KEYWORDS = ["tiktok"]


@dataclass
class TikTokVerificationCode:
    code: str
    message_id: str
    internal_date: str
    subject: str
    from_header: str


def decode_message(service, message_id: str) -> tuple[str, str, str]:
    payload = service.users().messages().get(userId="me", id=message_id, format="raw").execute()
    raw = payload.get("raw", "")
    if not raw:
        return "", "", ""
    mime = message_from_bytes(base64.urlsafe_b64decode(raw.encode("utf-8")))
    subject = str(mime.get("Subject") or "")
    from_header = str(mime.get("From") or "")
    body_parts: list[str] = []
    if mime.is_multipart():
        for part in mime.walk():
            if part.get_content_type() == "text/plain":
                try:
                    body_parts.append(part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", errors="ignore"))
                except Exception:
                    continue
    else:
        try:
            body_parts.append(mime.get_payload(decode=True).decode(mime.get_content_charset() or "utf-8", errors="ignore"))
        except Exception:
            pass
    return subject, from_header, "\n".join(body_parts)


def extract_code(text: str) -> str:
    for pattern in CODE_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)
    return ""


def latest_tiktok_code(
    *,
    account: str = DEFAULT_ACCOUNT,
    max_results: int = 10,
    max_age_minutes: int = 30,
) -> TikTokVerificationCode | None:
    service = mail_manager.get_gmail_service(account)
    query = "newer_than:1d"
    payload = service.users().messages().list(userId="me", q=query, maxResults=max_results).execute()
    messages = payload.get("messages") or []

    threshold = datetime.now(JST) - timedelta(minutes=max_age_minutes)

    for item in messages:
        message_id = str(item.get("id") or "")
        meta = service.users().messages().get(
            userId="me",
            id=message_id,
            format="metadata",
            metadataHeaders=["Subject", "From"],
        ).execute()
        internal_date = meta.get("internalDate")
        dt = None
        if internal_date:
            try:
                dt = datetime.fromtimestamp(int(internal_date) / 1000, JST)
            except Exception:
                dt = None
        if dt is not None and dt < threshold:
            continue

        headers = {h.get("name", ""): h.get("value", "") for h in meta.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        from_header = headers.get("From", "")
        blob = f"{subject}\n{from_header}"
        if not any(k.lower() in blob.lower() for k in SUBJECT_KEYWORDS + FROM_KEYWORDS):
            continue

        full_subject, full_from, body = decode_message(service, message_id)
        code = extract_code(f"{full_subject}\n{full_from}\n{body}")
        if not code:
            continue

        return TikTokVerificationCode(
            code=code,
            message_id=message_id,
            internal_date=dt.isoformat() if dt else "",
            subject=full_subject,
            from_header=full_from,
        )
    return None


def wait_for_tiktok_code(
    *,
    account: str = DEFAULT_ACCOUNT,
    max_age_minutes: int = 30,
    timeout_seconds: int = 120,
    poll_interval_seconds: int = 5,
) -> TikTokVerificationCode | None:
    started_at = datetime.now(JST)
    while (datetime.now(JST) - started_at).total_seconds() <= timeout_seconds:
        item = latest_tiktok_code(account=account, max_age_minutes=max_age_minutes)
        if item is not None:
            return item
        if poll_interval_seconds > 0:
            import time

            time.sleep(poll_interval_seconds)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok 認証コード取得 helper")
    parser.add_argument("--account", default=DEFAULT_ACCOUNT)
    parser.add_argument("--max-age-minutes", type=int, default=30)
    parser.add_argument("--wait-seconds", type=int, default=0)
    parser.add_argument("--poll-interval-seconds", type=int, default=5)
    args = parser.parse_args()

    if args.wait_seconds > 0:
        item = wait_for_tiktok_code(
            account=args.account,
            max_age_minutes=args.max_age_minutes,
            timeout_seconds=args.wait_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    else:
        item = latest_tiktok_code(
            account=args.account,
            max_age_minutes=args.max_age_minutes,
        )

    if item is None:
        print(json.dumps({"found": False}, ensure_ascii=False, indent=2))
        return

    print(
        json.dumps(
            {
                "found": True,
                "code": item.code,
                "internal_date": item.internal_date,
                "subject": item.subject,
                "from": item.from_header,
                "message_id": item.message_id,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
