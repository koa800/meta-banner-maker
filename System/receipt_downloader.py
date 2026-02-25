#!/usr/bin/env python3
"""
Gmail から領収書メールを検索し、添付をダウンロードしてフォルダに整理する。
個人アカウント (koa800sea.nifs@gmail.com) で実行。

使い方:
  python3 receipt_downloader.py "Payment receipt"   # 件名で検索して最新1件の添付を保存
  python3 receipt_downloader.py "Payment receipt" --from creem  # 送信者を絞る
"""
import argparse
import base64
import re
import sys
from pathlib import Path

# mail_manager の認証・サービス取得を流用
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
from mail_manager import get_credentials, get_gmail_service, get_header, parse_sender

# 領収書の保存先: ワークスペース (cursor) 直下の Receipts/年/月
RECEIPTS_BASE = BASE_DIR.parent / "Receipts"


def list_attachments(service, msg):
    """メッセージの payload から part を走査し (attachmentId, filename, mimeType) のリストを返す"""
    payload = msg.get("payload", {})
    parts = payload.get("parts", [])
    if not parts and payload.get("body", {}).get("attachmentId"):
        # 単一 part が body にある場合
        filename = next(
            (h["value"] for h in payload.get("headers", []) if h.get("name", "").lower() == "content-disposition"),
            "attachment",
        )
        match = re.search(r'filename="?([^";\s]+)"?', filename, re.I)
        filename = match.group(1) if match else "attachment"
        return [(payload["body"]["attachmentId"], filename, payload.get("mimeType", "application/octet-stream"))]
    out = []
    for part in parts:
        body = part.get("body", {})
        if not body.get("attachmentId"):
            continue
        filename = part.get("filename") or "attachment"
        # Content-Disposition から filename を取得
        for h in part.get("headers", []):
            if h.get("name", "").lower() == "content-disposition":
                m = re.search(r'filename="?([^";\s]+)"?', h.get("value", ""), re.I)
                if m:
                    filename = m.group(1)
                break
        out.append((body["attachmentId"], filename, part.get("mimeType", "application/octet-stream")))
    return out


def download_attachment(service, user_id, message_id, attachment_id):
    """1つの添付を取得してバイト列で返す"""
    resp = service.users().messages().attachments().get(
        userId=user_id, messageId=message_id, id=attachment_id
    ).execute()
    data = resp.get("data")
    if not data:
        return None
    return base64.urlsafe_b64decode(data)


def get_body_html_or_plain(msg):
    """メール本文を HTML 優先で取得"""
    payload = msg.get("payload", {})
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace"), payload.get("mimeType", "text/plain")
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace"), "text/html"
    for part in payload.get("parts", []):
        if part.get("mimeType") == "text/plain" and part.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace"), "text/plain"
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Gmail から領収書メールの添付をダウンロードして整理")
    parser.add_argument("query", nargs="?", default="Payment receipt", help="Gmail 検索クエリ（件名など）")
    parser.add_argument("--from", dest="from_addr", default="", help="送信者で絞る（例: creem）")
    parser.add_argument("--max", type=int, default=1, help="取得するメール数（デフォルト1）")
    args = parser.parse_args()

    q = args.query
    if args.from_addr:
        q = f"from:{args.from_addr} {q}"

    service = get_gmail_service("personal")
    result = service.users().messages().list(userId="me", q=q, maxResults=args.max).execute()
    messages = result.get("messages", [])
    if not messages:
        print(f"該当メールがありません: {q}")
        return 1

    saved = []
    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"], format="full").execute()
        subject = get_header(msg, "Subject")
        date_str = get_header(msg, "Date")
        # 日付から 2026/02 のようなフォルダ名を推測（簡易）
        year_month = "2026-02"
        if date_str:
            match = re.search(r"(\d{4})[-\s]?(\d{1,2})", date_str)
            if match:
                year_month = f"{match.group(1)}-{match.group(2).zfill(2)}"
        dest_dir = RECEIPTS_BASE / year_month.replace("-", "/")
        dest_dir.mkdir(parents=True, exist_ok=True)

        attachments = list_attachments(service, msg)
        if attachments:
            for att_id, filename, mime in attachments:
                data = download_attachment(service, "me", msg["id"], att_id)
                if data:
                    safe_name = re.sub(r'[^\w\s\-\.]', "_", filename)
                    if not safe_name.strip():
                        ext = ".pdf" if "pdf" in (mime or "") else ".bin"
                        safe_name = f"receipt_{msg['id'][:8]}{ext}"
                    out_path = dest_dir / safe_name
                    out_path.write_bytes(data)
                    saved.append(str(out_path))
                    print(f"保存: {out_path}")
        else:
            body, mime = get_body_html_or_plain(msg)
            if body:
                ext = ".html" if (mime and "html" in mime) else ".txt"
                out_path = dest_dir / f"receipt_{msg['id'][:8]}_body{ext}"
                out_path.write_text(body, encoding="utf-8")
                saved.append(str(out_path))
                print(f"添付なしのため本文を保存: {out_path}")
            else:
                print("添付も本文も取得できませんでした。")

    if saved:
        print(f"\n領収書を {len(saved)} 件保存しました。")
        print(f"フォルダ: {dest_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
