#!/usr/bin/env python3
"""MacBook ↔ Mac Mini 同期ステータス確認スクリプト"""

import json
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta

REPO_DIR = "/Users/koa800/Desktop/cursor"
MAC_MINI_URL = "http://mac-mini-agent.local:8500/sync-status"
JST = timezone(timedelta(hours=9))


def git_cmd(*args):
    return subprocess.check_output(
        ["git"] + list(args), cwd=REPO_DIR, text=True, stderr=subprocess.DEVNULL
    ).strip()


def get_macbook_status():
    head = git_cmd("rev-parse", "HEAD")
    head_msg = git_cmd("log", "-1", "--format=%s", "HEAD")
    head_date = git_cmd("log", "-1", "--format=%ci", "HEAD")

    git_cmd("fetch", "origin", "main")
    origin = git_cmd("rev-parse", "origin/main")
    origin_msg = git_cmd("log", "-1", "--format=%s", "origin/main")
    origin_date = git_cmd("log", "-1", "--format=%ci", "origin/main")

    return {
        "local": {"commit": head, "message": head_msg, "date": head_date},
        "origin": {"commit": origin, "message": origin_msg, "date": origin_date},
        "pushed": head == origin,
    }


def get_mac_mini_status():
    try:
        req = urllib.request.Request(MAC_MINI_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {"_reachable": True, "_error": "endpoint_not_deployed"}
        return None
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def fmt_commit(commit):
    return commit[:7] if commit else "?"


def print_status():
    print("\n" + "=" * 56)
    print("  📡 同期ステータス")
    print("=" * 56)

    mb = get_macbook_status()
    mm = get_mac_mini_status()

    local_short = fmt_commit(mb["local"]["commit"])
    origin_short = fmt_commit(mb["origin"]["commit"])

    print(f"\n  💻 MacBook (HEAD)")
    print(f"     commit: {local_short}  {mb['local']['message']}")
    print(f"     date:   {mb['local']['date']}")

    if mb["pushed"]:
        print(f"\n  ☁️  GitHub (origin/main)   ✅ 一致")
    else:
        print(f"\n  ☁️  GitHub (origin/main)   ⚠️  未push")
        print(f"     commit: {origin_short}  {mb['origin']['message']}")
        ahead = git_cmd("rev-list", "--count", "origin/main..HEAD")
        behind = git_cmd("rev-list", "--count", "HEAD..origin/main")
        if int(ahead) > 0:
            print(f"     → {ahead} commit(s) ahead")
        if int(behind) > 0:
            print(f"     → {behind} commit(s) behind")

    if mm is None:
        print(f"\n  🖥️  Mac Mini               ❌ 接続不可")
        print(f"     → {MAC_MINI_URL} にアクセスできません")
    elif mm.get("_error") == "endpoint_not_deployed":
        print(f"\n  🖥️  Mac Mini               ⏳ デプロイ待ち")
        print(f"     → Orchestrator稼働中だが /sync-status 未デプロイ")
    elif mm.get("mac_mini") is None:
        print(f"\n  🖥️  Mac Mini               ⚠️  ステータスファイル未生成")
        print(f"     → 次回の git_pull_sync 実行で生成されます")
    else:
        mini = mm["mac_mini"]
        mini_short = fmt_commit(mini.get("commit", ""))
        checked = mini.get("checked_at_jst", "不明")

        if mini.get("commit") == mb["origin"]["commit"]:
            sync_icon = "✅ 同期済み"
        else:
            sync_icon = "⚠️  未同期"

        print(f"\n  🖥️  Mac Mini               {sync_icon}")
        print(f"     commit: {mini_short}  {mini.get('message', '')}")
        print(f"     最終確認: {checked}")
        if mini.get("changed_files", 0) > 0:
            print(f"     前回同期: {mini['changed_files']}ファイル更新")

    all_synced = (
        mb["pushed"]
        and mm is not None
        and mm.get("mac_mini") is not None
        and mm["mac_mini"].get("commit") == mb["origin"]["commit"]
    )

    print("\n" + "-" * 56)
    if all_synced:
        print("  ✅ MacBook → GitHub → Mac Mini  全て同期済み")
    else:
        print("  ⚠️  同期に差分があります")
    print("-" * 56 + "\n")

    return 0 if all_synced else 1


if __name__ == "__main__":
    sys.exit(print_status())
