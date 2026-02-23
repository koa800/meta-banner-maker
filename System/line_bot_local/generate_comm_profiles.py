#!/usr/bin/env python3
"""
人物プロファイルにcomm_profile（コミュニケーションスタイル）を自動生成する。
既存の category/relationship/active_goals/capability_summary から
ルールベース + 必要に応じてClaude APIで生成。

使い方:
  python3 generate_comm_profiles.py           # 全員をルールベースで生成
  python3 generate_comm_profiles.py --claude  # Claude APIで詳細生成（要APIキー）
  python3 generate_comm_profiles.py --show 山田太郎  # 特定の人のプロファイルを表示
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROFILES_JSON = PROJECT_ROOT / "Master" / "people" / "profiles.json"

# カテゴリ別の返信スタイル定義
STYLE_BY_CATEGORY = {
    "上司": {
        "formality": "high",
        "greeting": "お疲れ様です！",
        "style": "丁寧だが堅くなく、提案型。数字・具体例を使って説得力を出す。「どうでしょうか？」で締める。絵文字は控えめ（🙇‍♂️ など）。",
        "tone_keywords": ["親しみやすく丁寧", "提案型", "数字で裏付け", "気遣いを一言添える"],
        "avoid": ["過度な謙遜", "曖昧な返し", "長すぎる説明"],
    },
    "横（並列）": {
        "formality": "medium",
        "greeting": "○○さんお疲れ様です！",
        "style": "フランクで気軽。名前呼びで始める。依頼は背景・理由をセットで伝える。「可能でしょうか？」「よろしくお願いします！」",
        "tone_keywords": ["フランク", "率直", "協力的", "背景込みで伝える"],
        "avoid": ["一方的な指示口調", "感謝なしの依頼"],
    },
    "直下メンバー": {
        "formality": "low",
        "greeting": "お疲れ様！",
        "style": "タメ口で話す。「です」「ます」は使わない。かなりフランク。テンポよく短く。感嘆符・強調多め。温度感と情熱を忘れない。",
        "tone_keywords": ["タメ口", "フランク", "テンポよく", "感嘆符多め", "情熱的"],
        "avoid": ["敬語（です・ます）", "冷たい事務的な返し", "距離感のある丁寧語"],
    },
    "メンバー": {
        "formality": "low",
        "greeting": "お疲れ様！",
        "style": "タメ口で話す。「です」「ます」は使わない。かなりフランク。テンポよく短く。感嘆符・強調多め。",
        "tone_keywords": ["タメ口", "フランク", "テンポよく", "感嘆符多め"],
        "avoid": ["敬語（です・ます）", "冷たい事務的な返し", "距離感のある丁寧語"],
    },
    "外部パートナー": {
        "formality": "medium-high",
        "greeting": "お疲れ様です！",
        "style": "丁寧だが親しみも入れる。ビジネスライクに。提案は具体的に。",
        "tone_keywords": ["丁寧", "ビジネスライク", "具体的"],
        "avoid": ["過度にカジュアル", "フランクすぎる"],
    },
}

DEFAULT_STYLE = {
    "formality": "medium",
    "greeting": "お疲れ様です！",
    "style": "相手との関係性に応じたトーンで。親しみやすく、具体的に。",
    "tone_keywords": ["親しみやすく", "具体的"],
    "avoid": ["過度に丁寧すぎる", "冷たい返し"],
}


def generate_comm_profile_rule_based(profile: dict) -> dict:
    """ルールベースでcomm_profileを生成"""
    category = profile.get("category", "")
    style_def = STYLE_BY_CATEGORY.get(category, DEFAULT_STYLE)

    # 現在のフォーカストピック（active_goals から抽出）
    active_goals = profile.get("active_goals", [])
    current_focus = [g["title"][:40] for g in active_goals[:3] if g.get("title")]

    # スキルドメイン
    domains = profile.get("inferred_domains", [])

    # identity_notes や notes
    extra_notes = []
    if profile.get("identity_notes"):
        extra_notes.append(profile["identity_notes"][:100])
    if profile.get("notes"):
        extra_notes.append(profile["notes"][:100])

    return {
        "formality": style_def["formality"],
        "greeting": style_def["greeting"],
        "style_note": style_def["style"],
        "tone_keywords": style_def["tone_keywords"],
        "avoid": style_def.get("avoid", []),
        "current_focus": current_focus,
        "domains": domains[:5],
        "extra_notes": extra_notes,
        "context_notes": [],  # LINEメモコマンドで追加される欄
        "generated_at": datetime.now().isoformat(),
        "auto_generated": True,
    }


def generate_comm_profile_claude(profile: dict, api_key: str) -> dict:
    """Claude APIを使って詳細なcomm_profileを生成"""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        name = profile.get("name", "不明")
        category = profile.get("category", "")
        capability = profile.get("capability_summary", "")[:300]
        goals_text = "\n".join([f"- {g['title']}" for g in profile.get("active_goals", [])[:5]])
        domains = ", ".join(profile.get("inferred_domains", [])[:5])

        prompt = f"""以下のメンバープロファイルをもとに、甲原海人（Addness代表）がLINEでこの人に返信する際の最適なコミュニケーションスタイルを生成してください。

【メンバー情報】
名前: {name}
関係: {category}
スキル・専門: {domains}
能力サマリー: {capability}
現在の取り組み:
{goals_text or '（情報なし）'}

【出力フォーマット（JSON）】
{{
  "style_note": "この人への最適な返信スタイルを2-3文で",
  "tone_keywords": ["キーワード1", "キーワード2", "キーワード3"],
  "best_opener": "最適な書き出しの例",
  "current_focus_context": "今この人が注力していることを踏まえた関係の文脈（1文）",
  "avoid": ["避けるべき表現・スタイル"]
}}

JSONのみを出力してください。"""

        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        # JSON部分を抽出
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            text = text.split("```")[1].split("```")[0].strip()

        claude_data = json.loads(text)

        # ルールベースのデータと統合
        base = generate_comm_profile_rule_based(profile)
        base.update(claude_data)
        base["auto_generated"] = False  # Claude生成
        base["generated_at"] = datetime.now().isoformat()
        return base

    except Exception as e:
        print(f"    Claude APIエラー: {e} → ルールベースにフォールバック")
        return generate_comm_profile_rule_based(profile)


def show_profile(name_query: str, data: dict):
    """特定人物のプロファイルを表示"""
    for key, value in data.items():
        profile = value.get("latest", value)
        name = profile.get("name", key)
        if name_query.lower() in name.lower() or name_query.lower() in key.lower():
            print(f"\n=== {name} ===")
            print(json.dumps(profile.get("comm_profile", "（未生成）"), ensure_ascii=False, indent=2))
            return
    print(f"'{name_query}' が見つかりません")


def main():
    use_claude = "--claude" in sys.argv
    show_query = None

    if "--show" in sys.argv:
        idx = sys.argv.index("--show")
        if idx + 1 < len(sys.argv):
            show_query = sys.argv[idx + 1]

    if not PROFILES_JSON.exists():
        print(f"❌ {PROFILES_JSON} が見つかりません")
        sys.exit(1)

    with open(PROFILES_JSON, "r", encoding="utf-8") as f:
        data = json.load(f)

    if show_query:
        show_profile(show_query, data)
        return

    api_key = ""
    if use_claude:
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            # config.jsonから取得
            config_file = Path(__file__).parent / "config.json"
            if config_file.exists():
                with open(config_file) as f:
                    cfg = json.load(f)
                api_key = cfg.get("anthropic_api_key", "")
        if not api_key:
            print("❌ ANTHROPIC_API_KEY が設定されていません")
            sys.exit(1)
        print(f"🤖 Claude APIモードで生成します（{len(data)}名）")
    else:
        print(f"📋 ルールベースでcomm_profileを生成します（{len(data)}名）")

    updated = 0
    skipped = 0

    for key, value in data.items():
        # latest フィールドを取得
        if "latest" in value:
            profile = value["latest"]
        else:
            profile = value

        name = profile.get("name", key)

        # 本人（甲原海人）はスキップ
        if profile.get("category") == "本人":
            print(f"  ⏩ {name} (本人) スキップ")
            skipped += 1
            continue

        # --force なしの場合、既存のComm Profile（手動生成）はスキップ
        existing = profile.get("comm_profile", {})
        if existing and not existing.get("auto_generated", True) and "--force" not in sys.argv:
            print(f"  ✅ {name}: 手動設定済みのためスキップ（--force で上書き可）")
            skipped += 1
            continue

        print(f"  🔄 {name} ({profile.get('category', '?')})", end="")

        if use_claude:
            comm_profile = generate_comm_profile_claude(profile, api_key)
        else:
            comm_profile = generate_comm_profile_rule_based(profile)

        profile["comm_profile"] = comm_profile
        if "latest" in value:
            value["latest"] = profile
        else:
            data[key] = profile

        updated += 1
        print(f" → 生成完了")

    # 保存
    with open(PROFILES_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 完了: {updated}名を生成、{skipped}名をスキップ")
    print(f"   保存先: {PROFILES_JSON}")

    if not use_claude:
        print(f"\n💡 より詳細な生成は: python3 generate_comm_profiles.py --claude")
        print(f"   特定の人を確認: python3 generate_comm_profiles.py --show 山田太郎")


if __name__ == "__main__":
    main()
