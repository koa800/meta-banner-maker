#!/usr/bin/env python3
"""動画学習の保存・読み込み・ライフサイクル管理CLI

使い方:
  python3 video_knowledge.py save '{"url":"...","title":"...","summary":"...","status":"pending"}'
  python3 video_knowledge.py list
  python3 video_knowledge.py update_pending '{"summary":"修正後の要約"}'
  python3 video_knowledge.py confirm
  python3 video_knowledge.py pending_info
  python3 video_knowledge.py pending_reminders
  python3 video_knowledge.py mark_reminded
  python3 video_knowledge.py search 'キーワード'
  python3 video_knowledge.py review
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 保存先: ~/agents/data/video_knowledge.json（ランタイムデータ。git管理外）
_RUNTIME_DATA_DIR = Path.home() / "agents" / "data"
_RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
_KNOWLEDGE_FILE = _RUNTIME_DATA_DIR / "video_knowledge.json"

MAX_ENTRIES = 100
REMINDER_SECONDS = 3600  # 1時間後にリマインド


def _load() -> list:
    if _KNOWLEDGE_FILE.exists():
        try:
            return json.loads(_KNOWLEDGE_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception):
            return []
    return []


def _save(data: list):
    _KNOWLEDGE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _KNOWLEDGE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.rename(_KNOWLEDGE_FILE)


def _generate_id(url: str) -> str:
    """URLからシンプルなIDを生成"""
    import re
    # Loom
    m = re.search(r"loom\.com/share/([a-f0-9]+)", url)
    if m:
        return f"loom_{m.group(1)[:8]}"
    # YouTube
    m = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    if m:
        return f"yt_{m.group(1)}"
    # その他: URLハッシュ
    import hashlib
    return f"vid_{hashlib.md5(url.encode()).hexdigest()[:8]}"


def save(data: dict) -> str:
    """学習内容を保存する"""
    url = data.get("url", "")
    title = data.get("title", "")
    summary = data.get("summary", "")

    if not url or not title or not summary:
        return json.dumps({"status": "error", "message": "url, title, summary は必須です"}, ensure_ascii=False)

    entry_id = _generate_id(url)
    entries = _load()

    # 同じURLの既存エントリを更新
    existing_idx = None
    for i, e in enumerate(entries):
        if e.get("url") == url or e.get("id") == entry_id:
            existing_idx = i
            break

    # ソース判定
    source = "unknown"
    if "loom.com" in url:
        source = "loom"
    elif "youtube.com" in url or "youtu.be" in url:
        source = "youtube"

    # 既存エントリの access_count / last_accessed を保持
    prev_access_count = 0
    prev_last_accessed = None
    if existing_idx is not None:
        prev_access_count = entries[existing_idx].get("access_count", 0)
        prev_last_accessed = entries[existing_idx].get("last_accessed")

    entry = {
        "id": entry_id,
        "source": source,
        "title": title,
        "url": url,
        "summary": summary,
        "key_processes": data.get("key_processes", []),
        "learned_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "status": data.get("status", "confirmed"),
        "access_count": prev_access_count,
        "last_accessed": prev_last_accessed,
        "reminded_at": None,
    }

    if existing_idx is not None:
        entries[existing_idx] = entry
        action = "updated"
    else:
        entries.append(entry)
        action = "saved"

    # 上限超過時は古いものから削除
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    _save(entries)
    return json.dumps({"status": "success", "action": action, "id": entry_id, "title": title}, ensure_ascii=False)


def confirm_pending() -> str:
    """直近のpendingエントリをconfirmedに変更する（承認）"""
    entries = _load()

    # 直近の pending エントリを探す（後ろから検索）
    target_idx = None
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("status") == "pending":
            target_idx = i
            break

    if target_idx is None:
        return json.dumps({"status": "error", "message": "承認待ちのエントリがありません"}, ensure_ascii=False)

    entry = entries[target_idx]
    entry["status"] = "confirmed"
    entries[target_idx] = entry
    _save(entries)
    return json.dumps({
        "status": "success",
        "action": "confirmed",
        "id": entry.get("id", ""),
        "title": entry.get("title", ""),
    }, ensure_ascii=False)


def update_pending(data: dict) -> str:
    """直近のpendingエントリを修正する。summary/key_processes/title を更新"""
    entries = _load()

    # 直近の pending エントリを探す（後ろから検索）
    target_idx = None
    for i in range(len(entries) - 1, -1, -1):
        if entries[i].get("status") == "pending":
            target_idx = i
            break

    if target_idx is None:
        return json.dumps({"status": "error", "message": "修正可能なpendingエントリがありません"}, ensure_ascii=False)

    entry = entries[target_idx]

    # 指定されたフィールドを更新
    if "summary" in data:
        entry["summary"] = data["summary"]
    if "key_processes" in data:
        entry["key_processes"] = data["key_processes"]
    if "title" in data:
        entry["title"] = data["title"]

    # learned_at をリセット（リマインドタイマーをリセット）
    entry["learned_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    entry["reminded_at"] = None  # リマインド済みフラグもリセット

    entries[target_idx] = entry
    _save(entries)
    return json.dumps({
        "status": "success",
        "action": "updated",
        "id": entry.get("id", ""),
        "title": entry.get("title", ""),
    }, ensure_ascii=False)


def get_pending_info() -> str:
    """pendingエントリの情報を返す（Coordinatorのプロンプト注入用）"""
    entries = _load()
    pending = [e for e in entries if e.get("status") == "pending"]
    if not pending:
        return ""

    lines = ["【承認待ちの動画知識】"]
    for e in pending:
        lines.append(f"  タイトル: {e.get('title', '')}")
        lines.append(f"  要約: {e.get('summary', '')}")
        procs = e.get("key_processes", [])
        if procs:
            lines.append(f"  手順: {' → '.join(procs)}")
    lines.append("ユーザーが「OK」「覚えて」「それでいい」等と言ったら confirm_video_learning を呼ぶこと。")
    lines.append("修正指示があれば update_video_learning で修正してから確認を取り直すこと。")
    return "\n".join(lines)


def get_pending_needing_reminder() -> list:
    """1時間経過してリマインド未送信のpendingエントリを返す"""
    entries = _load()
    now = datetime.now()
    result = []

    for e in entries:
        if e.get("status") != "pending":
            continue
        if e.get("reminded_at"):
            continue
        learned_at = e.get("learned_at", "")
        if not learned_at:
            continue
        try:
            dt = datetime.strptime(learned_at, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        if (now - dt).total_seconds() > REMINDER_SECONDS:
            result.append(e)

    return result


def mark_reminded() -> str:
    """リマインド対象のpendingエントリに reminded_at を設定する"""
    entries = _load()
    now = datetime.now()
    now_str = now.strftime("%Y-%m-%dT%H:%M:%S")
    count = 0

    for e in entries:
        if e.get("status") != "pending":
            continue
        if e.get("reminded_at"):
            continue
        learned_at = e.get("learned_at", "")
        if not learned_at:
            continue
        try:
            dt = datetime.strptime(learned_at, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
        if (now - dt).total_seconds() > REMINDER_SECONDS:
            e["reminded_at"] = now_str
            count += 1

    if count > 0:
        _save(entries)
    return json.dumps({"status": "success", "marked": count}, ensure_ascii=False)


def list_knowledge() -> str:
    """プロンプト注入用のテキストを返す（confirmed のみ）"""
    entries = _load()
    confirmed = [e for e in entries if e.get("status", "confirmed") == "confirmed"]
    if not confirmed:
        return ""

    lines = ["【過去に学んだ動画の知識】"]
    for i, e in enumerate(confirmed, 1):
        source_label = {"loom": "Loom", "youtube": "YouTube"}.get(e.get("source", ""), e.get("source", ""))
        date = e.get("learned_at", "")[:10]
        lines.append(f"[{i}] {e.get('title', '')} ({source_label}, {date})")
        lines.append(f"  要約: {e.get('summary', '')}")
        procs = e.get("key_processes", [])
        if procs:
            lines.append(f"  手順: {' → '.join(procs)}")

    return "\n".join(lines)


def search_relevant(query: str, top_n: int = 5) -> str:
    """ゴールテキストとキーワードマッチ。上位N件を返し、access_count をインクリメント"""
    entries = _load()
    confirmed = [e for e in entries if e.get("status", "confirmed") == "confirmed"]
    if not confirmed:
        return ""

    query_lower = query.lower()
    query_words = set(query_lower.split())

    scored = []
    for e in confirmed:
        score = 0
        title = (e.get("title") or "").lower()
        summary = (e.get("summary") or "").lower()
        url = (e.get("url") or "").lower()
        procs = " ".join(e.get("key_processes", [])).lower()

        # URL直接マッチは高スコア
        if url and url in query_lower:
            score += 100

        # 単語マッチ
        for word in query_words:
            if len(word) < 2:
                continue
            if word in title:
                score += 3
            if word in summary:
                score += 2
            if word in procs:
                score += 2

        if score > 0:
            scored.append((score, e))

    if not scored:
        return ""

    # スコア降順でソート、上位N件
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    # access_count / last_accessed を更新
    now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    top_ids = {e.get("id") for _, e in top}
    for e in entries:
        if e.get("id") in top_ids:
            e["access_count"] = e.get("access_count", 0) + 1
            e["last_accessed"] = now_str
    _save(entries)

    # テキスト生成
    lines = ["【関連する動画知識】"]
    for i, (score, e) in enumerate(top, 1):
        source_label = {"loom": "Loom", "youtube": "YouTube"}.get(e.get("source", ""), e.get("source", ""))
        date = e.get("learned_at", "")[:10]
        lines.append(f"[{i}] {e.get('title', '')} ({source_label}, {date})")
        lines.append(f"  要約: {e.get('summary', '')}")
        procs = e.get("key_processes", [])
        if procs:
            lines.append(f"  手順: {' → '.join(procs)}")

    return "\n".join(lines)


def review_stale() -> dict:
    """ライフサイクルレビュー
    - 90日未アクセス → 自動削除
    - 30日未アクセス+使用3回未満 → 要確認
    - 60日前学習+5回以上使用 → 再確認候補（内容が古くなっている可能性）
    """
    entries = _load()
    if not entries:
        return {"deleted": [], "needs_review": [], "reconfirm": [], "total": 0}

    now = datetime.now()
    deleted = []
    needs_review = []
    reconfirm = []
    keep = []

    for e in entries:
        if e.get("status") == "pending":
            keep.append(e)
            continue

        access_count = e.get("access_count", 0)
        last_accessed = e.get("last_accessed")
        learned_at = e.get("learned_at", "")

        # last_accessed がない場合は learned_at を使う
        ref_date_str = last_accessed or learned_at
        if not ref_date_str:
            keep.append(e)
            continue

        try:
            ref_date = datetime.strptime(ref_date_str[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            keep.append(e)
            continue

        days_since = (now - ref_date).days

        # 90日未アクセス → 自動削除
        if days_since >= 90:
            deleted.append({"id": e.get("id"), "title": e.get("title"), "days": days_since})
            continue

        # 30日未アクセス + 使用3回未満 → 要確認
        if days_since >= 30 and access_count < 3:
            needs_review.append({"id": e.get("id"), "title": e.get("title"), "days": days_since, "access_count": access_count})
            keep.append(e)
            continue

        # 60日前学習 + 5回以上使用 → 再確認候補
        try:
            learned_date = datetime.strptime(learned_at[:19], "%Y-%m-%dT%H:%M:%S")
            learned_days = (now - learned_date).days
            if learned_days >= 60 and access_count >= 5:
                reconfirm.append({"id": e.get("id"), "title": e.get("title"), "learned_days": learned_days, "access_count": access_count})
        except ValueError:
            pass

        keep.append(e)

    # 削除対象を除外して保存
    if deleted:
        _save(keep)

    return {
        "deleted": deleted,
        "needs_review": needs_review,
        "reconfirm": reconfirm,
        "total": len(keep),
    }


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 video_knowledge.py [save|list|confirm|update_pending|pending_info|pending_reminders|mark_reminded|search|review]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "save":
        if len(sys.argv) < 3:
            print("save コマンドにはJSON引数が必要です", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            print(f"JSON解析エラー: {e}", file=sys.stderr)
            sys.exit(1)
        print(save(data))

    elif command == "confirm":
        print(confirm_pending())

    elif command == "list":
        result = list_knowledge()
        print(result if result else "（学習済みの動画はありません）")

    elif command == "update_pending":
        if len(sys.argv) < 3:
            print("update_pending コマンドにはJSON引数が必要です", file=sys.stderr)
            sys.exit(1)
        try:
            data = json.loads(sys.argv[2])
        except json.JSONDecodeError as e:
            print(f"JSON解析エラー: {e}", file=sys.stderr)
            sys.exit(1)
        print(update_pending(data))

    elif command == "pending_info":
        result = get_pending_info()
        print(result if result else "（承認待ちの知識はありません）")

    elif command == "pending_reminders":
        result = get_pending_needing_reminder()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif command == "mark_reminded":
        print(mark_reminded())

    elif command == "search":
        if len(sys.argv) < 3:
            print("search コマンドにはクエリ引数が必要です", file=sys.stderr)
            sys.exit(1)
        result = search_relevant(sys.argv[2])
        print(result if result else "（関連する知識が見つかりませんでした）")

    elif command == "review":
        result = review_stale()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print(f"不明なコマンド: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
