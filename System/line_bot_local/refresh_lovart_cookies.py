#!/usr/bin/env python3
"""Lovart クッキーを MacBook Chrome から抽出して Mac Mini に転送する。

MacBook 側で実行:
  python3 System/line_bot_local/refresh_lovart_cookies.py

Mac Mini の ~/agents/data/lovart_cookies.json を更新する。
Orchestrator から定期実行するか、画像生成失敗時に手動実行。
"""
import json
import subprocess
import sys
from pathlib import Path

LOCAL_OUT = Path("/tmp/lovart_cookies.json")
REMOTE_PATH = "~/agents/data/lovart_cookies.json"
REMOTE_HOST = "koa800@mac-mini-agent"


def extract_cookies() -> list:
    """MacBook Chrome から lovart.ai のクッキーを復号化して抽出。"""
    try:
        import browser_cookie3
    except ImportError:
        print("browser_cookie3 がありません。インストール: pip3 install browser_cookie3")
        sys.exit(1)

    cookies = []
    for domain in [".lovart.ai", "www.lovart.ai"]:
        try:
            cj = browser_cookie3.chrome(domain_name=domain)
            for c in cj:
                name_domain = (c.name, c.domain)
                if not any((x["name"], x["domain"]) == name_domain for x in cookies):
                    cookies.append({
                        "name": c.name,
                        "value": c.value,
                        "domain": c.domain,
                        "path": c.path,
                        "secure": c.secure,
                        "httpOnly": bool(getattr(c, "_rest", {}).get("HttpOnly", False)),
                        "expires": c.expires if c.expires else -1,
                    })
        except Exception as e:
            print(f"  警告: {domain} のクッキー取得失敗: {e}")

    return cookies


def main():
    print("Lovart クッキーを MacBook Chrome から抽出中...")
    cookies = extract_cookies()

    if not cookies:
        print("クッキーが見つかりません。Chrome で lovart.ai にログインしてください。")
        sys.exit(1)

    # usertoken 確認
    has_token = any(c["name"] == "usertoken" for c in cookies)
    print(f"  クッキー数: {len(cookies)}, usertoken: {'あり' if has_token else 'なし'}")

    if not has_token:
        print("usertoken が見つかりません。Chrome で lovart.ai にログインし直してください。")
        sys.exit(1)

    # ローカル保存
    with open(LOCAL_OUT, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2)
    print(f"  ローカル保存: {LOCAL_OUT}")

    # Mac Mini に転送
    print(f"  Mac Mini ({REMOTE_HOST}) に転送中...")
    result = subprocess.run(
        ["scp", str(LOCAL_OUT), f"{REMOTE_HOST}:{REMOTE_PATH}"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        print("  転送成功！")
    else:
        print(f"  転送失敗: {result.stderr}")
        sys.exit(1)

    print("完了。Lovart 画像生成が利用可能です。")


if __name__ == "__main__":
    main()
