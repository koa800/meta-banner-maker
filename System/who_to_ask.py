#!/usr/bin/env python3
"""
委託先検索スクリプト

人物プロファイルを参照し、アイデア・タスクを実行してもらうのに
最適な担当者候補をClaude APIで推薦する。

使い方:
  python3 who_to_ask.py "Instagram用の広告CRを10本作りたい"
  python3 who_to_ask.py  # 引数なしで対話モード
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

import anthropic

logger = logging.getLogger("who_to_ask")

# ---- パス設定 ----
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
PROFILES_JSON = PROJECT_ROOT / "Master" / "people" / "profiles.json"


def get_api_key() -> str:
    """ANTHROPIC_API_KEY を環境変数 → Secret Manager の順で取得"""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return key
    try:
        result = subprocess.run(
            ["gcloud", "secrets", "versions", "access", "latest", "--secret=ANTHROPIC_API_KEY"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def load_profiles() -> dict:
    if not PROFILES_JSON.exists():
        print(f"エラー: {PROFILES_JSON} が見つかりません。")
        print("先に addness_people_profiler.py を実行してください。")
        sys.exit(1)
    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def build_profiles_summary(profiles: dict) -> str:
    """Claude に渡すプロファイルサマリーを構築"""
    lines = []
    for name, data in profiles.items():
        p = data.get("latest", {})
        wl = p.get("workload", {})
        domains = p.get("inferred_domains", [])
        summary = p.get("capability_summary", "")
        active_goals = p.get("active_goals", [])
        completed_goals = p.get("completed_goals", [])

        lines.append(f"【{name}】")
        lines.append(
            f"稼働状況: 実行中{wl.get('active', 0)}件 / "
            f"完了済み{wl.get('completed', 0)}件"
        )
        if domains:
            lines.append(f"スキル領域: {', '.join(domains)}")
        if summary:
            lines.append(f"能力サマリー: {summary}")
        if active_goals:
            titles = [g["title"] for g in active_goals[:5]]
            lines.append(f"実行中の主要ゴール: {' / '.join(titles)}")
        if completed_goals:
            titles = [g["title"] for g in completed_goals[:8]]
            lines.append(f"直近の完了実績: {' / '.join(titles)}")
        lines.append("")

    return "\n".join(lines)


def ask_who(task: str, api_key: str, profiles: dict) -> str:
    """Claude APIに委託先を推薦させる"""
    profiles_text = build_profiles_summary(profiles)

    prompt = f"""あなたはチームのリソース管理アドバイザーです。
以下のメンバープロファイルを参照し、指定されたタスクを実行するのに最適な担当者を推薦してください。

=== メンバープロファイル ===
{profiles_text}

=== 実行したいタスク ===
{task}

=== 出力形式 ===
以下の形式で回答してください:

【第1候補】 氏名
確度: ★★★★☆（5段階）
根拠:
- （具体的な根拠を箇条書きで2〜3点）
稼働余裕: （現在の稼働状況から見た余裕度）

【第2候補】 氏名
（同様の形式）

【補足】
（候補選定で考慮したポイント、注意点など）"""

    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


def main():
    # タスク取得（引数 or 対話入力）
    if len(sys.argv) > 1:
        task = " ".join(sys.argv[1:])
    else:
        print("実行したいタスク・アイデアを入力してください:")
        task = input("> ").strip()
        if not task:
            print("タスクが入力されていません。")
            sys.exit(1)

    print(f"\n検索中: 「{task}」\n")

    # APIキー取得
    api_key = get_api_key()
    if not api_key:
        print("エラー: ANTHROPIC_API_KEY が取得できません。")
        print("環境変数を設定するか、gcloud でSecret Managerにアクセスできることを確認してください。")
        sys.exit(1)

    # プロファイル読み込み
    profiles = load_profiles()
    print(f"プロファイル読み込み: {len(profiles)}人\n")
    print("=" * 60)

    # Claude に推薦させる
    result = ask_who(task, api_key, profiles)
    print(result)
    print("=" * 60)


if __name__ == "__main__":
    main()
