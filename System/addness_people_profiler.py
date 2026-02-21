#!/usr/bin/env python3
"""
Addness 人物プロファイル生成スクリプト

対象者の決定ロジック:
  1. 甲原海人のゴールサブツリー以下の全担当者（深さ無制限）
  2. 甲原海人と同じ親ゴールを持つ並列担当者（横の人たち）
  3. 上司（ルートゴール保持者: 三上功太）
  4. addness_config.json の manual_people に手動登録した人

出力:
  Master/people-profiles.json  → 構造化データ（スナップショット蓄積）
  Master/people-profiles.md    → 人が読めるプロファイル集（Cursor参照用）
"""

import json
import logging
import os
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("addness_people_profiler")

import anthropic

# ---- パス設定 ----
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_PATH = SCRIPT_DIR / "addness_data" / "latest.json"
CONFIG_PATH = SCRIPT_DIR / "addness_config.json"
PROFILES_JSON = PROJECT_ROOT / "Master" / "people-profiles.json"
PROFILES_MD = PROJECT_ROOT / "Master" / "people-profiles.md"
IDENTITIES_JSON = PROJECT_ROOT / "Master" / "people-identities.json"

# 甲原海人のゴールID（固定）
KOHARA_ID = "69bbece5-9ff7-4f96-b7f8-0227d0560f9c"
KOHARA_NAME = "甲原海人"
# 組織ルートゴールID
ROOT_GOAL_ID = "45e3a49b-4818-429d-936e-913d41b5d833"

# ---- スキル領域キーワードマッピング ----
DOMAIN_KEYWORDS = {
    "広告・クリエイティブ": ["広告", "CR", "クリエイティブ", "バナー", "リール", "撮影", "台本"],
    "LP・ライティング": ["LP", "ランディング", "ライティング", "コピー", "文言", "セールス"],
    "動画・映像": ["動画", "編集", "VSL", "映像", "サムネ"],
    "マーケティング・導線設計": ["マーケ", "導線", "集客", "ROAS", "オプトイン", "アップセル", "サブスク"],
    "エンジニアリング・実装": ["実装", "開発", "コーディング", "デプロイ", "バグ", "API", "バッチ", "マージ"],
    "デザイン": ["デザイン", "UI", "UX", "デザイナー"],
    "数値管理・分析": ["数値", "KPI", "管理シート", "計測", "ウォッチ", "集計"],
    "企画・戦略": ["企画", "設計", "戦略", "計画", "スキーム", "全体像"],
    "CS・受講生対応": ["受講生", "質問回答", "サポート", "オンボーディング", "カスタマー"],
    "コンテンツ・教材": ["コース", "教材", "カリキュラム", "コンテンツ", "アクションマップ"],
    "採用・組織": ["採用", "研修", "メンバー", "組織", "1on1"],
    "営業・セールス": ["営業", "セールス", "契約", "成約", "法人"],
    "AI・自動化": ["AI", "自動", "ChatGPT", "Claude", "プロンプト", "生成"],
}

# カテゴリ定義
CATEGORY_SELF = "本人"
CATEGORY_BOSS = "上司"
CATEGORY_PARALLEL = "横（並列）"
CATEGORY_MEMBER = "直下メンバー"
CATEGORY_MANUAL = "手動追加"


def get_api_key() -> str:
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


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_latest_json() -> dict:
    if not DATA_PATH.exists():
        print(f"エラー: {DATA_PATH} が見つかりません。先に addness_fetcher.py を実行してください。")
        sys.exit(1)
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ---- 対象者の決定 ----

def collect_relevant_persons(api: dict, manual_people: list, excluded_people: list) -> dict:
    """
    対象者とそのカテゴリを決定する。
    返り値: { "氏名": {"category": "...", "relationship": "...", "notes": ""} }
    """
    excluded = set(excluded_people)
    relevant: dict = {}

    def get_preview(goal_id: str) -> dict:
        key = f"/api/v1/team/objectives/{goal_id}/preview"
        val = api.get(key, {})
        return val.get("data", val) if isinstance(val, dict) else {}

    # ── ① 本人: 甲原海人 ──
    relevant[KOHARA_NAME] = {"category": CATEGORY_SELF, "relationship": "本人", "notes": ""}

    # ── ② 上司: ルートゴール保持者 ──
    root_d = get_preview(ROOT_GOAL_ID)
    boss_name = (root_d.get("owner") or {}).get("name", "")
    if boss_name and boss_name != KOHARA_NAME and boss_name not in excluded:
        relevant[boss_name] = {"category": CATEGORY_BOSS, "relationship": "上司", "notes": ""}

    # ── ② 並列ゴール担当者: ルート直下の兄弟ゴール ──
    for c in root_d.get("children", []):
        cid = c.get("id", "")
        owner = (c.get("owner") or {}).get("name", "")
        title = c.get("title", "")
        if owner and owner != KOHARA_NAME and cid != KOHARA_ID and owner not in excluded:
            if owner not in relevant:
                relevant[owner] = {
                    "category": CATEGORY_PARALLEL,
                    "relationship": "横（並列）",
                    "notes": f"並列ゴール: {title[:40]}",
                }

    # ── ③ 甲原海人のサブツリー内の全担当者（深さ無制限・BFS）──
    visited_ids = set()
    queue = [KOHARA_ID]
    while queue:
        gid = queue.pop(0)
        if gid in visited_ids:
            continue
        visited_ids.add(gid)
        d = get_preview(gid)
        for child in d.get("children", []):
            cid = child.get("id", "")
            owner = (child.get("owner") or {}).get("name", "")
            if owner and owner != KOHARA_NAME and owner not in excluded and owner not in relevant:
                relevant[owner] = {
                    "category": CATEGORY_MEMBER,
                    "relationship": "直下メンバー",
                    "notes": "",
                }
            if cid:
                queue.append(cid)

    # ── ④ 手動追加 ──
    for entry in manual_people:
        name = entry.get("name", "").strip()
        if not name or name.startswith("_") or name in excluded:
            continue
        if name not in relevant:
            relevant[name] = {
                "category": CATEGORY_MANUAL,
                "relationship": entry.get("relationship", "手動追加"),
                "notes": entry.get("notes", ""),
            }

    return relevant


# ---- ゴール収集 ----

def extract_goals_per_person(api: dict, relevant_names: set) -> dict:
    """
    対象者のゴールを2段階で収集する。

    Pass 1: previewの直接オーナー（自身がオーナーのゴール）
    Pass 2: previewのchildren配列（親のpreviewに記録された子ゴール）
             → previewが個別取得できなかった人のゴールを補完

    返り値: { "氏名": {"completed": [...], "active": [...], "exploring": [...]} }
    """
    persons: dict = {name: {"completed": [], "active": [], "exploring": []} for name in relevant_names}
    seen: dict = {name: set() for name in relevant_names}  # 重複防止用

    def classify_and_add(owner: str, title: str, description: str, status: str, phase: str, due_date: str):
        if not owner or owner not in persons or not title:
            return
        if title in seen[owner]:
            return
        seen[owner].add(title)
        goal = {"title": title, "description": description, "due_date": due_date}
        if status == "COMPLETED":
            persons[owner]["completed"].append(goal)
        elif phase == "PROCESS":
            persons[owner]["active"].append(goal)
        else:
            persons[owner]["exploring"].append(goal)

    for key, val in api.items():
        if "/objectives/" not in key or not key.endswith("/preview"):
            continue
        d = val.get("data", val) if isinstance(val, dict) else val
        if not isinstance(d, dict):
            continue

        # Pass 1: previewのオーナー自身（本人も含む）
        owner = (d.get("owner") or {}).get("name", "").strip()
        classify_and_add(
            owner,
            d.get("title", "").strip(),
            d.get("description", "").strip(),
            (d.get("status") or "").upper(),
            (d.get("phase") or "").upper(),
            d.get("dueDate", ""),
        )

        # Pass 2: childrenに記録された子ゴール（個別previewがない人の補完）
        for c in d.get("children", []):
            if not isinstance(c, dict):
                continue
            c_owner = (c.get("owner") or {}).get("name", "").strip()
            classify_and_add(
                c_owner,
                c.get("title", "").strip(),
                c.get("description", "").strip(),
                (c.get("status") or "").upper(),
                (c.get("phase") or "").upper(),
                c.get("dueDate", ""),
            )

    return persons


# ---- スキル推定 ----

def infer_domains(goals: list) -> list:
    scores: dict = defaultdict(int)
    for g in goals:
        text = g.get("title", "") + " " + g.get("description", "")
        for domain, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                if kw in text:
                    scores[domain] += 1
    ranked = sorted(scores.items(), key=lambda x: -x[1])
    return [d for d, cnt in ranked if cnt >= 1][:5]


def generate_capability_summary(name: str, goals_data: dict, api_key: str) -> str:
    if not api_key:
        return ""
    completed_titles = [g["title"] for g in goals_data["completed"][:20]]
    active_titles = [g["title"] for g in goals_data["active"][:10]]
    if not completed_titles and not active_titles:
        return ""
    is_self = (name == KOHARA_NAME)
    exploring_titles = [g["title"] for g in goals_data.get("exploring", [])[:20]]

    if is_self:
        prompt = f"""以下は {name} さん自身のAddnessゴールデータです。

【実行中ゴール】
{chr(10).join(f'- {t}' for t in active_titles)}

【検討中（着手できていない）ゴール】
{chr(10).join(f'- {t}' for t in exploring_titles)}

【完了済みゴール（直近）】
{chr(10).join(f'- {t}' for t in completed_titles)}

このデータをもとに、以下を出力してください。

【能力サマリー】
この人がどんな能力・専門性を持っているか3〜4文で。ゴール羅列でなく本質を。

【得意領域 Top5】
箇条書き5つ。具体的に。

【放置中ゴール（要委託検討）】
検討中ゴールの中で、着手できていない・他の人に任せられそうなものを最大5つピックアップして理由とともに箇条書きで。"""
    else:
        prompt = f"""以下は {name} さんのAddnessゴールツリーのデータです。

【完了済みゴール（直近）】
{chr(10).join(f'- {t}' for t in completed_titles)}

【実行中ゴール】
{chr(10).join(f'- {t}' for t in active_titles)}

このデータから、{name} さんがどのような能力・専門性を持っているかを、3〜4文で簡潔にまとめてください。
箇条書きではなく文章で。ゴールの羅列ではなく、能力の本質を表現してください。"""
    client = anthropic.Anthropic(api_key=api_key)
    # レート制限対策: 最大3回リトライ
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1000 if is_self else 300,
                messages=[{"role": "user", "content": prompt}],
            )
            time.sleep(0.5)  # 連続呼び出し間隔
            return message.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  レート制限 ({name}): {wait}秒待機...")
            time.sleep(wait)
        except Exception as e:
            print(f"  Claude API エラー ({name}): {e}")
            return ""
    return ""


# ---- プロファイル構築 ----

def load_identities() -> dict:
    """people-identities.json を読み込む。存在しない場合は空dict。"""
    if IDENTITIES_JSON.exists():
        with open(IDENTITIES_JSON, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def sync_identities(profiles: dict):
    """
    新しく検出された人を people-identities.json に追加（既存エントリは上書きしない）。
    削除された人のエントリは残す（手動で入力した情報を消さないため）。
    """
    identities = load_identities()
    added = []
    for name in profiles:
        if name not in identities:
            identities[name] = {
                "line_display_name": "",
                "line_my_name": "",
                "email": "",
                "birthday": "",
                "notes": "",
            }
            added.append(name)
    if added:
        print(f"  people-identities.json に追加: {added}")
    with open(IDENTITIES_JSON, "w", encoding="utf-8") as f:
        json.dump(identities, f, ensure_ascii=False, indent=2)


def build_profiles(relevant: dict, goals_per_person: dict, api_key: str, today: str, existing: dict = None) -> dict:
    profiles = {}
    total = len(relevant)
    identities = load_identities()

    for i, (name, meta) in enumerate(relevant.items(), 1):
        print(f"  [{i}/{total}] {name} ({meta['category']})...")
        goals_data = goals_per_person.get(name, {"completed": [], "active": [], "exploring": []})

        completed = goals_data["completed"]
        active = goals_data["active"]
        exploring = goals_data["exploring"]

        domains = infer_domains(completed + active)

        # 既存サマリーを引き継ぎ、ゴール数に変化があった場合のみ再生成
        prev_summary = (existing or {}).get(name, {}).get("latest", {}).get("capability_summary", "")
        prev_completed = (existing or {}).get(name, {}).get("latest", {}).get("workload", {}).get("completed", -1)
        needs_regen = (not prev_summary) or (len(completed) != prev_completed)

        summary = prev_summary
        if needs_regen and len(completed) + len(active) >= 3:
            new_summary = generate_capability_summary(name, goals_data, api_key)
            summary = new_summary if new_summary else prev_summary

        # people-identities.json の情報をマージ
        identity = identities.get(name, {})

        profiles[name] = {
            "name": name,
            "snapshot_date": today,
            "category": meta["category"],
            "relationship": meta["relationship"],
            "notes": meta["notes"],
            # 識別情報（people-identities.json から）
            "line_display_name": identity.get("line_display_name", ""),  # 相手が設定した名前
            "line_my_name": identity.get("line_my_name", ""),            # 自分が設定した名前
            "email": identity.get("email", ""),
            "birthday": identity.get("birthday", ""),
            "identity_notes": identity.get("notes", ""),
            "workload": {
                "active": len(active),
                "exploring": len(exploring),
                "completed": len(completed),
            },
            "inferred_domains": domains,
            "capability_summary": summary,
            "active_goals": active[:15],
            "completed_goals": completed[:30],
        }

    return profiles


def accumulate_profiles(new_profiles: dict, today: str) -> dict:
    accumulated = {}
    if PROFILES_JSON.exists():
        with open(PROFILES_JSON, "r", encoding="utf-8") as f:
            accumulated = json.load(f)

    # 対象外になった人を除去（manual_people 以外）
    new_names = set(new_profiles.keys())
    remove_names = [
        name for name, data in accumulated.items()
        if name not in new_names
        and data.get("latest", {}).get("category") != CATEGORY_MANUAL
    ]
    for name in remove_names:
        del accumulated[name]
        print(f"  除外: {name}")

    for name, profile in new_profiles.items():
        if name not in accumulated:
            accumulated[name] = {"latest": profile, "history": []}

        prev = accumulated[name].get("latest", {})
        if prev.get("snapshot_date") != today:
            history_entry = {
                "date": prev.get("snapshot_date", ""),
                "active": prev.get("workload", {}).get("active", 0),
                "completed": prev.get("workload", {}).get("completed", 0),
            }
            if history_entry["date"]:
                accumulated[name].setdefault("history", []).append(history_entry)
                accumulated[name]["history"] = accumulated[name]["history"][-90:]

        accumulated[name]["latest"] = profile

    return accumulated


# ---- Markdown 生成 ----

CATEGORY_ORDER = [CATEGORY_SELF, CATEGORY_BOSS, CATEGORY_PARALLEL, CATEGORY_MEMBER, CATEGORY_MANUAL]


def render_markdown(accumulated: dict, today: str) -> str:
    # カテゴリ別に分類
    by_category: dict = defaultdict(list)
    for name, data in accumulated.items():
        cat = data.get("latest", {}).get("category", CATEGORY_MEMBER)
        by_category[cat].append(name)

    lines = [
        "# 人物プロファイル集",
        "",
        f"| | |",
        "|---|---|",
        f"| 最終更新 | {today} |",
        f"| 登録人数 | {len(accumulated)}人 |",
        "",
        "---",
        "",
    ]

    for cat in CATEGORY_ORDER:
        members = sorted(by_category.get(cat, []))
        if not members:
            continue

        lines.append(f"## {cat}（{len(members)}人）")
        lines.append("")

        for name in members:
            data = accumulated[name]
            p = data.get("latest", {})
            wl = p.get("workload", {})
            domains = p.get("inferred_domains", [])
            summary = p.get("capability_summary", "")
            active_goals = p.get("active_goals", [])
            completed_goals = p.get("completed_goals", [])
            notes = p.get("notes", "")
            history = data.get("history", [])

            lines.append(f"### {name}")
            lines.append("")
            lines.append(f"**更新**: {p.get('snapshot_date', today)}　**区分**: {cat}")
            lines.append(
                f"**稼働状況**: 実行中 {wl.get('active', 0)}件 ／ "
                f"検討中 {wl.get('exploring', 0)}件 ／ "
                f"完了済み {wl.get('completed', 0)}件"
            )
            if notes:
                lines.append(f"**備考**: {notes}")

            # 識別情報
            line_display = p.get("line_display_name", "")
            line_my = p.get("line_my_name", "")
            email = p.get("email", "")
            birthday = p.get("birthday", "")
            identity_notes = p.get("identity_notes", "")
            id_parts = []
            if line_display:
                id_parts.append(f"LINE表示名: {line_display}")
            if line_my:
                id_parts.append(f"自分の設定名: {line_my}")
            if email:
                id_parts.append(f"Mail: {email}")
            if birthday:
                id_parts.append(f"誕生日: {birthday}")
            if id_parts:
                lines.append(f"**識別情報**: {' ｜ '.join(id_parts)}")
            if identity_notes:
                lines.append(f"**人物メモ**: {identity_notes}")
            lines.append("")

            if domains:
                lines.append("**推定スキル領域**")
                for d in domains:
                    lines.append(f"- {d}")
                lines.append("")

            if summary:
                lines.append("**能力サマリー**")
                lines.append(summary)
                lines.append("")

            if active_goals:
                lines.append("**実行中の主要ゴール**")
                for g in active_goals[:8]:
                    lines.append(f"- {g['title']}")
                lines.append("")

            if completed_goals:
                lines.append("**直近の完了実績**")
                for g in completed_goals[:10]:
                    lines.append(f"- {g['title']}")
                lines.append("")

            if len(history) >= 2:
                oldest = history[0]
                diff = wl.get("completed", 0) - oldest.get("completed", 0)
                if diff > 0:
                    lines.append(
                        f"**成長トレンド**: {oldest['date']} → {today}: 完了ゴール **+{diff}件**"
                    )
                    lines.append("")

            lines.append("---")
            lines.append("")

    lines.append("> `System/addness_people_profiler.py` によって自動生成。手動編集不可。")
    return "\n".join(lines)


# ---- メイン ----

def main():
    print(f"[{datetime.now().isoformat()}] addness_people_profiler 開始")

    today = datetime.now().strftime("%Y/%m/%d")
    config = load_config()
    api_key = get_api_key()

    if api_key:
        print("  Anthropic APIキー: 取得済み（能力サマリーを生成します）")
    else:
        print("  Anthropic APIキー: 未設定（能力サマリーをスキップします）")

    print("データ読み込み中...")
    data = load_latest_json()
    api = data.get("api_responses", {})

    # 除外リストと手動追加リストを設定から取得
    excluded_people = config.get("excluded_people", [])
    manual_people = [
        p for p in config.get("manual_people", [])
        if isinstance(p, dict) and not p.get("name", "").startswith("_") and p.get("name")
    ]
    if excluded_people:
        print(f"  除外設定: {excluded_people}")
    if manual_people:
        print(f"  手動追加: {[p['name'] for p in manual_people]}")

    # 対象者を決定
    print("対象者を決定中...")
    relevant = collect_relevant_persons(api, manual_people, excluded_people)
    print(f"  対象: {len(relevant)}人")

    # カテゴリ別サマリー表示
    from collections import Counter
    cat_counts = Counter(v["category"] for v in relevant.values())
    for cat in CATEGORY_ORDER:
        if cat in cat_counts:
            print(f"    {cat}: {cat_counts[cat]}人")

    # ゴール収集
    print("ゴールデータ収集中...")
    goals_per_person = extract_goals_per_person(api, set(relevant.keys()))

    # 既存プロファイルを読み込み（サマリー保持のため）
    existing_profiles = {}
    if PROFILES_JSON.exists():
        with open(PROFILES_JSON, "r", encoding="utf-8") as f:
            existing_profiles = json.load(f)

    # プロファイル構築
    print("プロファイル生成中...")
    new_profiles = build_profiles(relevant, goals_per_person, api_key, today, existing_profiles)

    # スナップショット蓄積
    print("スナップショット蓄積中...")
    accumulated = accumulate_profiles(new_profiles, today)

    # people-identities.json に新メンバーを追加（既存データは保持）
    sync_identities(new_profiles)

    # 保存
    (PROJECT_ROOT / "Master").mkdir(parents=True, exist_ok=True)

    with open(PROFILES_JSON, "w", encoding="utf-8") as f:
        json.dump(accumulated, f, ensure_ascii=False, indent=2, default=str)
    print(f"  → {PROFILES_JSON}")

    md_content = render_markdown(accumulated, today)
    PROFILES_MD.write_text(md_content, encoding="utf-8")
    print(f"  → {PROFILES_MD}")

    print(f"\n完了: {len(accumulated)}人のプロファイルを保存しました")
    print(f"[{datetime.now().isoformat()}] 完了")


if __name__ == "__main__":
    main()
