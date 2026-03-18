#!/usr/bin/env python3
"""
お名前.com 系メールボックスの即レス基盤ひな型。

- IMAP / SMTP 接続テスト
- 未読メールの取得
- 返信案の生成
- 明示フラグ付きでの返信送信
"""

from __future__ import annotations

import argparse
import email
import imaplib
import json
import os
import re
import smtplib
import ssl
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.policy import default as default_policy
from email.utils import formataddr, make_msgid, parseaddr
from html import unescape
from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = BASE_DIR / "credentials" / "snsers_admin_mailbox.json"
STATE_PATH = BASE_DIR / "data" / "snsers_admin_mailbox_state.json"
LATEST_PATH = BASE_DIR / "data" / "snsers_admin_mailbox_latest.json"
MAIL_MANAGER_CONFIG_PATH = BASE_DIR / "mail_inbox_data" / "config.json"
DEFAULT_IDENTITY_PATH = BASE_DIR.parent / "Master" / "self_clone" / "mikami" / "IDENTITY.md"
JST = timezone(timedelta(hours=9))


def ensure_data_dir() -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_data_dir()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {
            "processed_imap_ids": [],
            "last_checked_at": None,
            "last_sent_at": None,
            "last_review_at": None,
        }
    return load_json(STATE_PATH)


def save_state(state: dict[str, Any]) -> None:
    save_json(STATE_PATH, state)


def load_config(path: Path) -> dict[str, Any]:
    config = load_json(path)
    for section in ("imap", "smtp"):
        if section not in config:
            raise ValueError(f"{section} 設定がありません: {path}")
    config.setdefault("reply_profile", {})
    config.setdefault("escalation", {})
    return config


def load_openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    if MAIL_MANAGER_CONFIG_PATH.exists():
        try:
            return (load_json(MAIL_MANAGER_CONFIG_PATH).get("openai_api_key") or "").strip()
        except Exception:
            return ""
    return ""


def load_identity_context(config: dict[str, Any]) -> str:
    raw_path = (config.get("reply_profile", {}).get("identity_path") or "").strip()
    identity_path = Path(raw_path) if raw_path else DEFAULT_IDENTITY_PATH
    if not identity_path.exists():
        return ""
    try:
        return identity_path.read_text(encoding="utf-8")
    except Exception:
        return ""


def get_persona_name(config: dict[str, Any]) -> str:
    return (config.get("reply_profile", {}).get("persona_name") or "三上功太").strip() or "三上功太"


def decode_mime(value: str) -> str:
    parts = []
    for chunk, encoding in decode_header(value or ""):
        if isinstance(chunk, bytes):
            parts.append(chunk.decode(encoding or "utf-8", errors="replace"))
        else:
            parts.append(chunk)
    return "".join(parts).strip()


def strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?s)<br\s*/?>", "\n", text)
    text = re.sub(r"(?s)</p>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def get_message_text(msg: Message, max_len: int = 4000) -> str:
    plain_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_disposition() == "attachment":
                continue
            content_type = part.get_content_type()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="replace")
            if msg.get_content_type() == "text/html":
                html_parts.append(text)
            else:
                plain_parts.append(text)

    if plain_parts:
        body = "\n".join(part.strip() for part in plain_parts if part.strip())
    else:
        body = strip_html("\n".join(html_parts))

    return (body or "(本文なし)")[:max_len]


def get_attachment_names(msg: Message) -> list[str]:
    attachment_names: list[str] = []
    if not msg.is_multipart():
        return attachment_names
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        filename = decode_mime(part.get_filename() or "")
        attachment_names.append(filename or "(no-name)")
    return attachment_names


def normalize_subject(subject: str) -> str:
    normalized = decode_mime(subject)
    normalized = re.sub(r"^(?:(?:re|fwd?|fw)\s*[:：]\s*)+", "", normalized, flags=re.IGNORECASE)
    return normalized.strip().lower()


def build_reply_subject(subject: str) -> str:
    current = decode_mime(subject)
    if re.match(r"^(?:re)\s*[:：]", current, flags=re.IGNORECASE):
        return current
    return f"Re: {current}" if current else "Re:"


def parse_message_date(value: str) -> datetime | None:
    try:
        parsed = email.utils.parsedate_to_datetime(value)
    except Exception:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(JST)


def is_stale_for_auto_reply(record: dict[str, Any], config: dict[str, Any]) -> bool:
    max_delay = int(config.get("reply_profile", {}).get("max_reply_delay_seconds") or 0)
    if max_delay <= 0:
        return False
    received_at = parse_message_date(record.get("date", ""))
    if received_at is None:
        return False
    return (datetime.now(JST) - received_at).total_seconds() > max_delay


def assess_human_review_need(record: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    lower_text = f"{record['subject']}\n{record['body']}".lower()
    reasons: list[str] = []

    if record.get("has_attachments"):
        reasons.append("添付ファイルあり")

    hard_review_patterns = [
        "返金",
        "解約",
        "クレーム",
        "訴訟",
        "弁護士",
        "消費者センター",
        "詐欺",
        "個人情報",
        "支払ったのに",
    ]
    hard_review_patterns.extend(
        keyword.strip().lower()
        for keyword in (config.get("escalation", {}).get("human_review_required_keywords") or [])
        if keyword and keyword.strip()
    )

    matched_keywords = [keyword for keyword in hard_review_patterns if keyword in lower_text]
    if matched_keywords:
        reasons.append(f"人確認キーワード: {', '.join(sorted(set(matched_keywords)))}")

    if is_stale_for_auto_reply(record, config):
        reasons.append("即レス期限を超過")

    return {
        "needs_review": bool(reasons),
        "reason": " / ".join(reasons) if reasons else "",
        "source": "guardrail" if reasons else "none",
    }


def assess_reply_need(record: dict[str, Any], context: list[dict[str, Any]]) -> dict[str, Any]:
    subject = record["subject"]
    body = record["body"]
    sender = record["from_email"]
    lower_text = f"{subject}\n{body}".lower()

    hard_skip_patterns = [
        "配信解除",
        "unsubscribe",
        "キャンペーン",
        "ボーナス",
        "抽選",
        "本日限定",
        "先着",
    ]
    if any(pattern.lower() in lower_text for pattern in hard_skip_patterns):
        return {"should_reply": False, "reason": "広告・配信系の可能性が高い", "source": "heuristic"}
    if sender.startswith(("no-reply@", "noreply@", "info@", "system-notice@")) and body.count("http") >= 1:
        return {"should_reply": False, "reason": "自動配信メールの可能性が高い", "source": "heuristic"}

    api_key = load_openai_api_key()
    if not api_key:
        return {"should_reply": True, "reason": "API未設定のため要返信扱い", "source": "fallback"}

    try:
        from openai import OpenAI
    except ImportError:
        return {"should_reply": True, "reason": "OpenAI未導入のため要返信扱い", "source": "fallback"}

    client = OpenAI(api_key=api_key)
    context_summary = "\n".join(
        f"- Subject: {item['subject']}\n  Body: {item['body'][:600]}" for item in context
    ) or "なし"
    prompt = f"""次のメールに自動返信すべきか判定してください。

【返信不要に寄せるもの】
- 広告
- メルマガ
- 自動通知
- 配信解除リンク付きの一斉配信

【返信必要に寄せるもの】
- 質問
- 相談
- 個別の依頼
- 日程調整
- 顧客が返答を期待している連絡

Subject: {subject}
From: {sender}
Body:
{body}

過去文脈:
{context_summary}

JSONのみで返してください。
{{"should_reply": true/false, "reason": "短く"}}
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "あなたはメール運用の判定担当です。JSONのみ返してください。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
        max_tokens=120,
    )
    raw = (response.choices[0].message.content or "").strip()
    try:
        parsed = json.loads(raw)
        return {
            "should_reply": bool(parsed.get("should_reply", True)),
            "reason": str(parsed.get("reason", "")),
            "source": "ai",
        }
    except json.JSONDecodeError:
        return {"should_reply": True, "reason": "判定parse失敗のため要返信扱い", "source": "fallback"}


def message_to_record(imap_id: str, msg: Message) -> dict[str, Any]:
    from_name, from_email = parseaddr(msg.get("From", ""))
    reply_to_name, reply_to_email = parseaddr(msg.get("Reply-To", ""))
    to_name, to_email = parseaddr(msg.get("To", ""))
    references = " ".join(
        value
        for value in [msg.get("References", ""), msg.get("In-Reply-To", "")]
        if value
    ).strip()
    attachment_names = get_attachment_names(msg)
    return {
        "imap_id": imap_id,
        "message_id": msg.get("Message-ID", ""),
        "subject": decode_mime(msg.get("Subject", "")),
        "subject_normalized": normalize_subject(msg.get("Subject", "")),
        "from_name": decode_mime(from_name),
        "from_email": from_email.lower(),
        "reply_to_email": reply_to_email.lower(),
        "to_email": to_email.lower(),
        "date": msg.get("Date", ""),
        "references": references,
        "body": get_message_text(msg),
        "has_attachments": bool(attachment_names),
        "attachment_names": attachment_names,
    }


def build_ssl_context() -> ssl.SSLContext:
    return ssl.create_default_context()


def connect_imap(config: dict[str, Any]) -> imaplib.IMAP4_SSL:
    imap_cfg = config["imap"]
    conn = imaplib.IMAP4_SSL(
        imap_cfg["host"],
        int(imap_cfg.get("port", 993)),
        ssl_context=build_ssl_context(),
    )
    conn.login(imap_cfg["username"], imap_cfg["password"])
    return conn


@contextmanager
def imap_session(config: dict[str, Any]):
    conn = connect_imap(config)
    try:
        yield conn
    finally:
        try:
            conn.logout()
        except Exception:
            pass


def connect_smtp(config: dict[str, Any]):
    smtp_cfg = config["smtp"]
    host = smtp_cfg["host"]
    port = int(smtp_cfg.get("port", 465))
    security = (smtp_cfg.get("security") or "ssl").lower()
    if security == "starttls":
        smtp = smtplib.SMTP(host, port, timeout=20)
        smtp.ehlo()
        smtp.starttls(context=build_ssl_context())
        smtp.ehlo()
    else:
        smtp = smtplib.SMTP_SSL(host, port, context=build_ssl_context(), timeout=20)
    smtp.login(smtp_cfg["username"], smtp_cfg["password"])
    return smtp


def test_connection(config: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "imap": {"ok": False, "mailboxes": 0, "message_count": 0},
        "smtp": {"ok": False, "code": None},
    }

    with imap_session(config) as conn:
        boxes = conn.list()[1] or []
        conn.select("INBOX", readonly=True)
        search_data = conn.search(None, "ALL")[1]
        msg_count = len((search_data[0] or b"").split()) if search_data else 0
        result["imap"] = {"ok": True, "mailboxes": len(boxes), "message_count": msg_count}

    with connect_smtp(config) as smtp:
        code, _ = smtp.noop()
        result["smtp"] = {"ok": True, "code": code}

    return result


def fetch_records(conn: imaplib.IMAP4_SSL, ids: list[bytes]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for raw_id in ids:
        imap_id = raw_id.decode()
        status, payload = conn.fetch(raw_id, "(RFC822)")
        if status != "OK" or not payload or not payload[0]:
            continue
        raw_bytes = payload[0][1]
        msg = BytesParser(policy=default_policy).parsebytes(raw_bytes)
        records.append(message_to_record(imap_id, msg))
    return records


def apply_filters(
    records: list[dict[str, Any]],
    from_email: str = "",
    subject_contains: str = "",
) -> list[dict[str, Any]]:
    filtered = records
    if from_email:
        lower_from = from_email.strip().lower()
        filtered = [item for item in filtered if item["from_email"] == lower_from]
    if subject_contains:
        needle = subject_contains.strip().lower()
        filtered = [item for item in filtered if needle in item["subject"].lower()]
    return filtered


def list_unseen(
    config: dict[str, Any],
    limit: int,
    from_email: str = "",
    subject_contains: str = "",
) -> list[dict[str, Any]]:
    with imap_session(config) as conn:
        conn.select("INBOX", readonly=True)
        status, data = conn.search(None, "UNSEEN")
        if status != "OK" or not data or not data[0]:
            return []
        ids = data[0].split()[-limit:]
        records = fetch_records(conn, ids)
        return apply_filters(records, from_email=from_email, subject_contains=subject_contains)


def build_thread_context(conn: imaplib.IMAP4_SSL, target: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    sender = target["from_email"]
    if not sender:
        return []

    conn.select("INBOX", readonly=True)
    status, data = conn.search(None, "FROM", f'"{sender}"')
    if status != "OK" or not data or not data[0]:
        return []

    ids = data[0].split()[-10:]
    records = fetch_records(conn, ids)
    target_subject = target["subject_normalized"]
    filtered = [
        item for item in records
        if item["imap_id"] != target["imap_id"]
        and (
            not target_subject
            or item["subject_normalized"] == target_subject
            or target_subject in item["subject_normalized"]
            or item["subject_normalized"] in target_subject
        )
    ]
    return filtered[-limit:]


def generate_reply_draft(record: dict[str, Any], context: list[dict[str, Any]], config: dict[str, Any]) -> str:
    api_key = load_openai_api_key()
    signature = (config.get("reply_profile", {}).get("signature_text") or "").strip()
    persona_name = get_persona_name(config)
    if not api_key:
        base = [
            "ご連絡ありがとうございます。",
            "内容を確認しました。取り急ぎ受け取りのご連絡です。",
            "詳細はあらためて確認のうえ、必要に応じてすぐにご返信します。",
        ]
        if signature:
            base.extend(["", signature])
        return "\n".join(base)

    try:
        from openai import OpenAI
    except ImportError:
        base = [
            "ご連絡ありがとうございます。",
            "内容を確認しました。取り急ぎ受け取りのご連絡です。",
            "詳細はあらためて確認のうえ、必要に応じてすぐにご返信します。",
        ]
        if signature:
            base.extend(["", signature])
        return "\n".join(base)

    client = OpenAI(api_key=api_key)
    identity = load_identity_context(config)
    context_lines = []
    for item in context:
        context_lines.append(
            f"- Date: {item['date']}\n  Subject: {item['subject']}\n  Body: {item['body'][:1200]}"
        )

    prompt = f"""あなたは{persona_name}として返信するメール返信エージェントです。
目的は、相手に「友達からすぐ返信が来た」ような自然さを出しつつ、必要なら個別相談や商品購入につながる会話を前に進めることです。

【文体の参考】
{identity}

【返信ルール】
- まずは相手の問いや温度感に自然に応じる
- 過度に営業っぽくしない
- ただし会話を前に進められるなら、柔らかく次の行動を促してよい
- メールなので LINE よりは少し丁寧にする
- 相手には {persona_name} 本人から返ってきたと感じさせる
- 署名は本文に含めない

【今回のメール】
From: {record['from_email']}
Subject: {record['subject']}
Body:
{record['body']}

【同一送信者の過去文脈】
{chr(10).join(context_lines) if context_lines else 'なし'}

日本語の返信本文だけを出力してください。
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "あなたは日本語メール返信の実務担当です。本文だけを返してください。"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
        max_tokens=900,
    )
    draft = (response.choices[0].message.content or "").strip()
    if signature:
        draft = f"{draft}\n\n{signature}"
    return draft


def build_reply_email(record: dict[str, Any], draft: str, config: dict[str, Any]) -> EmailMessage:
    reply_profile = config.get("reply_profile", {})
    mailbox_address = config["mailbox_address"]
    from_name = (reply_profile.get("from_name") or "").strip()
    to_address = record["reply_to_email"] or record["from_email"]

    msg = EmailMessage()
    msg["Subject"] = build_reply_subject(record["subject"])
    msg["From"] = formataddr((from_name, mailbox_address)) if from_name else mailbox_address
    msg["To"] = to_address
    msg["Message-ID"] = make_msgid()
    if record["message_id"]:
        msg["In-Reply-To"] = record["message_id"]
        references = " ".join(
            value for value in [record.get("references", ""), record["message_id"]] if value
        ).strip()
        msg["References"] = references
    msg.set_content(draft)
    return msg


def process_next_message(
    config: dict[str, Any],
    send: bool,
    from_email: str = "",
    subject_contains: str = "",
) -> dict[str, Any]:
    state = load_state()
    processed = set(state.get("processed_imap_ids", []))
    records = list_unseen(config, 20, from_email=from_email, subject_contains=subject_contains)
    target = next((record for record in reversed(records) if record["imap_id"] not in processed), None)
    if not target:
        return {"status": "no_unseen"}

    with imap_session(config) as conn:
        context = build_thread_context(conn, target)
    decision = assess_reply_need(target, context)
    review = assess_human_review_need(target, config)
    draft = generate_reply_draft(target, context, config) if decision["should_reply"] else ""

    payload = {
        "status": "drafted",
        "message": target,
        "context": context,
        "decision": decision,
        "review": review,
        "draft": draft,
        "sent": False,
    }

    if review["needs_review"]:
        processed.add(target["imap_id"])
        state["processed_imap_ids"] = sorted(processed, key=int)[-2000:]
        state["last_review_at"] = datetime.now(JST).isoformat()
        state["last_checked_at"] = datetime.now(JST).isoformat()
        save_state(state)
        payload["status"] = "needs_review"
        snapshot({"mode": "run-once", **payload})
        return payload

    if not decision["should_reply"]:
        processed.add(target["imap_id"])
        state["processed_imap_ids"] = sorted(processed, key=int)[-2000:]
        state["last_checked_at"] = datetime.now(JST).isoformat()
        save_state(state)
        payload["status"] = "skipped_no_reply"
        snapshot({"mode": "run-once", **payload})
        return payload

    if send:
        msg = build_reply_email(target, draft, config)
        with connect_smtp(config) as smtp:
            smtp.send_message(msg)
        processed.add(target["imap_id"])
        state["processed_imap_ids"] = sorted(processed, key=int)[-2000:]
        state["last_sent_at"] = datetime.now(JST).isoformat()
        payload["status"] = "sent"
        payload["sent"] = True

    state["last_checked_at"] = datetime.now(JST).isoformat()
    save_state(state)
    snapshot({"mode": "run-once", **payload})
    return payload


def snapshot(payload: dict[str, Any]) -> None:
    payload["saved_at"] = datetime.now(JST).isoformat()
    save_json(LATEST_PATH, payload)


def command_test_connection(config: dict[str, Any]) -> None:
    result = test_connection(config)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_list_unseen(config: dict[str, Any], limit: int, from_email: str = "", subject_contains: str = "") -> None:
    records = list_unseen(config, limit, from_email=from_email, subject_contains=subject_contains)
    snapshot({"mode": "list-unseen", "records": records})
    print(json.dumps({"count": len(records), "records": records}, ensure_ascii=False, indent=2))


def command_draft_latest(
    config: dict[str, Any],
    limit: int,
    from_email: str = "",
    subject_contains: str = "",
) -> None:
    records = list_unseen(config, limit, from_email=from_email, subject_contains=subject_contains)
    drafted: list[dict[str, Any]] = []
    with imap_session(config) as conn:
        for record in records:
            context = build_thread_context(conn, record)
            decision = assess_reply_need(record, context)
            draft = generate_reply_draft(record, context, config) if decision["should_reply"] else ""
            drafted.append({"message": record, "context": context, "decision": decision, "draft": draft})
    snapshot({"mode": "draft-latest", "items": drafted})
    print(json.dumps({"count": len(drafted), "items": drafted}, ensure_ascii=False, indent=2))


def command_run_once(
    config: dict[str, Any],
    send: bool,
    from_email: str = "",
    subject_contains: str = "",
) -> None:
    payload = process_next_message(
        config,
        send=send,
        from_email=from_email,
        subject_contains=subject_contains,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def command_monitor(
    config: dict[str, Any],
    interval_seconds: int,
    max_loops: int,
    from_email: str = "",
    subject_contains: str = "",
) -> None:
    if not config.get("reply_profile", {}).get("auto_send_enabled"):
        print(json.dumps({
            "status": "auto_send_disabled",
            "reason": "reply_profile.auto_send_enabled が false のため monitor は開始しません",
        }, ensure_ascii=False, indent=2))
        return

    loops = 0
    while True:
        payload = process_next_message(
            config,
            send=True,
            from_email=from_email,
            subject_contains=subject_contains,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        loops += 1
        if max_loops > 0 and loops >= max_loops:
            return
        time.sleep(interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="お名前.com メールボックス即レス基盤")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="認証 / 返信ポリシー JSON")

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("test-connection")

    list_parser = subparsers.add_parser("list-unseen")
    list_parser.add_argument("--limit", type=int, default=5)
    list_parser.add_argument("--from-email", default="")
    list_parser.add_argument("--subject-contains", default="")

    draft_parser = subparsers.add_parser("draft-latest")
    draft_parser.add_argument("--limit", type=int, default=1)
    draft_parser.add_argument("--from-email", default="")
    draft_parser.add_argument("--subject-contains", default="")

    run_parser = subparsers.add_parser("run-once")
    run_parser.add_argument("--send", action="store_true", help="返信を実際に送信する")
    run_parser.add_argument("--from-email", default="")
    run_parser.add_argument("--subject-contains", default="")

    monitor_parser = subparsers.add_parser("monitor")
    monitor_parser.add_argument("--interval", type=int, default=15, help="監視間隔（秒）")
    monitor_parser.add_argument("--max-loops", type=int, default=0, help="0で無限監視")
    monitor_parser.add_argument("--from-email", default="")
    monitor_parser.add_argument("--subject-contains", default="")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = load_config(Path(args.config))

    if args.command == "test-connection":
        command_test_connection(config)
    elif args.command == "list-unseen":
        command_list_unseen(
            config,
            args.limit,
            from_email=args.from_email,
            subject_contains=args.subject_contains,
        )
    elif args.command == "draft-latest":
        command_draft_latest(
            config,
            args.limit,
            from_email=args.from_email,
            subject_contains=args.subject_contains,
        )
    elif args.command == "run-once":
        command_run_once(
            config,
            args.send,
            from_email=args.from_email,
            subject_contains=args.subject_contains,
        )
    elif args.command == "monitor":
        command_monitor(
            config,
            interval_seconds=args.interval,
            max_loops=args.max_loops,
            from_email=args.from_email,
            subject_contains=args.subject_contains,
        )


if __name__ == "__main__":
    main()
