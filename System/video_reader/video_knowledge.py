#!/usr/bin/env python3
"""動画学習の保存・読み込みCLI

使い方:
  python3 video_knowledge.py save '{"url":"...","title":"...","summary":"...","key_processes":["手順1"]}'
  python3 video_knowledge.py list
"""

import json
import sys
from datetime import datetime
from pathlib import Path

# 保存先: Master/learning/video_knowledge.json
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent.parent
_KNOWLEDGE_FILE = _PROJECT_ROOT / "Master" / "learning" / "video_knowledge.json"

# Mac Mini 環境フォールバック
if not _KNOWLEDGE_FILE.parent.exists():
    _alt = Path.home() / "agents" / "_repo" / "Master" / "learning" / "video_knowledge.json"
    if _alt.parent.exists():
        _KNOWLEDGE_FILE = _alt

MAX_ENTRIES = 100


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

    entry = {
        "id": entry_id,
        "source": source,
        "title": title,
        "url": url,
        "summary": summary,
        "key_processes": data.get("key_processes", []),
        "learned_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
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


def list_knowledge() -> str:
    """プロンプト注入用のテキストを返す"""
    entries = _load()
    if not entries:
        return ""

    lines = ["【過去に学んだ動画の知識】"]
    for i, e in enumerate(entries, 1):
        source_label = {"loom": "Loom", "youtube": "YouTube"}.get(e.get("source", ""), e.get("source", ""))
        date = e.get("learned_at", "")[:10]
        lines.append(f"[{i}] {e.get('title', '')} ({source_label}, {date})")
        lines.append(f"  要約: {e.get('summary', '')}")
        procs = e.get("key_processes", [])
        if procs:
            lines.append(f"  手順: {' → '.join(procs)}")

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("使い方: python3 video_knowledge.py [save|list]", file=sys.stderr)
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

    elif command == "list":
        result = list_knowledge()
        print(result if result else "（学習済みの動画はありません）")

    else:
        print(f"不明なコマンド: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
