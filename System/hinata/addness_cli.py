#!/usr/bin/env python3
"""
Addness CLI — Claude Codeから呼び出すAddness操作ツール

Usage:
    python addness_cli.py login                        # 初回ログイン（手動）
    python addness_cli.py consult                      # AIと相談（自動サイクル）
    python addness_cli.py consult --instruction "..."  # 指示付きでAIと相談
    python addness_cli.py check-comments               # コメントから指示を確認
    python addness_cli.py get-goal-info                # ゴール情報を取得
    python addness_cli.py post-comment --text "..."    # コメント投稿
"""

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

from addness_browser import (
    launch_browser,
    setup_page,
    login,
    find_my_goal,
    open_ai_consultation,
    start_ai_conversation,
    send_ai_message,
    post_comment,
    get_goal_info,
    check_comments_for_instructions,
)

SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"


def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _open_addness(playwright, config, headless=None):
    """Addnessにログインしてゴールページまで遷移する。(context, page) を返す。"""
    if headless is None:
        headless = config.get("headless", True)
    context = launch_browser(playwright, headless=headless)
    page = setup_page(context)

    start_url = config.get("addness_start_url", "https://www.addness.com")
    if not login(page, start_url):
        context.close()
        return None, None

    my_goal_url = config.get("my_goal_url")
    goal_url = find_my_goal(page, my_goal_url=my_goal_url)
    if not goal_url:
        context.close()
        return None, None

    return context, page


def cmd_login(_args):
    """初回ログイン（headless=False で手動Google認証）。"""
    config = load_config()
    print("=" * 50)
    print("日向の初回ログイン")
    print("ブラウザが開きます。Googleアカウントでログインしてください。")
    print("=" * 50)

    with sync_playwright() as playwright:
        context = launch_browser(playwright, headless=False)
        page = setup_page(context)
        start_url = config.get("addness_start_url", "https://www.addness.com")
        if login(page, start_url):
            print("\nログイン成功！セッションが保存されました。")
        else:
            print("\nログインに失敗しました。再度実行してください。")
        context.close()


def cmd_consult(args):
    """Addnessの「AIと相談」でアクションを取得する。"""
    config = load_config()

    with sync_playwright() as playwright:
        context, page = _open_addness(playwright, config)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)

        try:
            goal_info = get_goal_info(page)

            if not open_ai_consultation(page):
                print(json.dumps({"error": "「AIと相談」を開けない"}, ensure_ascii=False))
                sys.exit(1)

            start_ai_conversation(page)

            if args.instruction:
                prompt = (
                    f"甲原さんから以下の指示がありました:\n"
                    f"「{args.instruction}」\n\n"
                    f"この指示を踏まえて、今やるべきアクションを1つ決めてください。\n"
                    f"「何をするか」だけ教えてください。やり方は自分で考えます。"
                )
            else:
                prompt = (
                    f"このゴールの完了基準に向けて、今やるべき次のアクションを1つ決めてください。\n"
                    f"「何をするか」だけ教えてください。やり方は自分で考えます。"
                )

            ai_response = send_ai_message(page, prompt)

            result = {
                "goal_title": goal_info.get("title", ""),
                "goal_url": goal_info.get("url", ""),
                "action": ai_response or "",
                "instruction": args.instruction or "",
            }
            print(json.dumps(result, ensure_ascii=False))
        finally:
            context.close()


def cmd_check_comments(_args):
    """ゴールページのコメントから甲原の指示を確認する。"""
    config = load_config()

    with sync_playwright() as playwright:
        context, page = _open_addness(playwright, config)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)

        try:
            instruction = check_comments_for_instructions(page)
            print(json.dumps({"instruction": instruction or ""}, ensure_ascii=False))
        finally:
            context.close()


def cmd_get_goal_info(_args):
    """ゴール情報を取得する。"""
    config = load_config()

    with sync_playwright() as playwright:
        context, page = _open_addness(playwright, config)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)

        try:
            info = get_goal_info(page)
            print(json.dumps(info, ensure_ascii=False))
        finally:
            context.close()


def cmd_post_comment(args):
    """ゴールページにコメントを投稿する。"""
    config = load_config()

    with sync_playwright() as playwright:
        context, page = _open_addness(playwright, config)
        if not page:
            print(json.dumps({"error": "Addnessログインまたはゴール遷移に失敗"}, ensure_ascii=False))
            sys.exit(1)

        try:
            success = post_comment(page, args.text)
            print(json.dumps({"success": success}, ensure_ascii=False))
        finally:
            context.close()


def main():
    parser = argparse.ArgumentParser(description="Addness CLI for Claude Code")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("login", help="初回ログイン（手動）")

    p_consult = subparsers.add_parser("consult", help="AIと相談してアクションを取得")
    p_consult.add_argument("--instruction", default=None, help="甲原からの指示")

    subparsers.add_parser("check-comments", help="コメントから指示を確認")
    subparsers.add_parser("get-goal-info", help="ゴール情報を取得")

    p_comment = subparsers.add_parser("post-comment", help="コメントを投稿")
    p_comment.add_argument("--text", required=True, help="コメント内容")

    args = parser.parse_args()

    commands = {
        "login": cmd_login,
        "consult": cmd_consult,
        "check-comments": cmd_check_comments,
        "get-goal-info": cmd_get_goal_info,
        "post-comment": cmd_post_comment,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
