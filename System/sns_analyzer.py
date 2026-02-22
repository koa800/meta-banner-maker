#!/usr/bin/env python3
"""
SNS分析ツール — Instagram公開データからターゲットインサイトを分析

Usage:
    # Mode A: ユーザー分析
    python sns_analyzer.py @username
    python sns_analyzer.py https://instagram.com/username/
    python sns_analyzer.py @username --no-cache --json --max 100

    # Mode B: 投稿いいねからターゲット発掘
    python sns_analyzer.py --post https://instagram.com/p/XXXXX --persona "20代女性、美容に興味"
    python sns_analyzer.py --post https://instagram.com/p/XXXXX --persona "20代女性" --top 5
"""

from __future__ import annotations

import abc
import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# Paths & logging
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
CONFIG_FILE = SCRIPT_DIR / "config" / "sns_analyzer.json"
CACHE_DIR = SCRIPT_DIR / "sns_analyzer_cache"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("sns_analyzer")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "apify_api_token": "",
    "anthropic_api_key": "",
    "cache_ttl_days": 7,
    "apify_actors": {
        "following": "datadoping/instagram-following-scraper",
        "profile": "apify/instagram-profile-scraper",
        "likers": "scraping_solutions/instagram-engagers-likers-and-commenters-no-cookies",
    },
    "default_max_following": 300,
    "default_top_users": 5,
    "apify_poll_interval_sec": 5,
    "apify_timeout_sec": 300,
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        merged = {**DEFAULT_CONFIG, **cfg}
        return merged
    return DEFAULT_CONFIG.copy()


def get_anthropic_api_key(config: dict) -> str:
    key = config.get("anthropic_api_key", "").strip()
    if key:
        return key
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


def get_apify_token(config: dict) -> str:
    token = config.get("apify_api_token", "").strip()
    if token:
        return token
    return os.environ.get("APIFY_API_TOKEN", "").strip()


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
class CacheManager:
    def __init__(self, cache_dir: Path, ttl_days: int = 7):
        self.cache_dir = cache_dir
        self.ttl = timedelta(days=ttl_days)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, namespace: str, key: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]", "_", key)
        return self.cache_dir / f"{namespace}_{safe}.json"

    def get(self, namespace: str, key: str):
        path = self._key_path(namespace, key)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        cached_at = datetime.fromisoformat(data["cached_at"])
        if datetime.now() - cached_at > self.ttl:
            path.unlink(missing_ok=True)
            return None
        return data["value"]

    def put(self, namespace: str, key: str, value):
        path = self._key_path(namespace, key)
        payload = {"cached_at": datetime.now().isoformat(), "value": value}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# DataProvider ABC
# ---------------------------------------------------------------------------
class DataProvider(abc.ABC):
    @abc.abstractmethod
    def get_following_list(self, username: str, max_count: int) -> list[dict]:
        """Return list of {username, full_name, biography, ...}"""

    @abc.abstractmethod
    def get_profile_details(self, usernames: list[str]) -> list[dict]:
        """Return detailed profiles for given usernames"""

    @abc.abstractmethod
    def get_post_likers(self, post_url: str, max_count: int) -> list[dict]:
        """Return list of users who liked the post"""


# ---------------------------------------------------------------------------
# Apify Provider
# ---------------------------------------------------------------------------
APIFY_BASE = "https://api.apify.com/v2"


class ApifyProvider(DataProvider):
    def __init__(self, token: str, config: dict):
        self.token = token
        self.actors = config.get("apify_actors", DEFAULT_CONFIG["apify_actors"])
        self.poll_interval = config.get("apify_poll_interval_sec", 5)
        self.timeout = config.get("apify_timeout_sec", 300)

    def _run_actor(self, actor_id: str, input_data: dict) -> list[dict]:
        """Start an actor, poll until done, return dataset items."""
        # Apify API requires "~" separator for namespaced actors (e.g. apify~instagram-scraper)
        safe_id = actor_id.replace("/", "~")
        url = f"{APIFY_BASE}/acts/{safe_id}/runs"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

        logger.info(f"Apify: starting actor {actor_id}")
        resp = requests.post(url, headers=headers, json=input_data, timeout=60)
        if resp.status_code != 201:
            raise RuntimeError(f"Apify actor start failed ({resp.status_code}): {resp.text[:300]}")

        run_data = resp.json()["data"]
        run_id = run_data["id"]
        dataset_id = run_data["defaultDatasetId"]
        logger.info(f"Apify: run {run_id} started, polling...")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            time.sleep(self.poll_interval)
            status_resp = requests.get(
                f"{APIFY_BASE}/actor-runs/{run_id}",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=30,
            )
            status = status_resp.json()["data"]["status"]
            if status == "SUCCEEDED":
                break
            if status in ("FAILED", "ABORTED", "TIMED-OUT"):
                raise RuntimeError(f"Apify run {run_id} ended with status: {status}")
        else:
            raise TimeoutError(f"Apify run {run_id} timed out after {self.timeout}s")

        items_resp = requests.get(
            f"{APIFY_BASE}/datasets/{dataset_id}/items",
            headers={"Authorization": f"Bearer {self.token}"},
            params={"format": "json"},
            timeout=60,
        )
        items_resp.raise_for_status()
        items = items_resp.json()
        logger.info(f"Apify: got {len(items)} items from {actor_id}")
        return items

    def get_following_list(self, username: str, max_count: int) -> list[dict]:
        # datadoping/instagram-following-scraper: requires min max_count=50
        effective_max = max(max_count, 50)
        input_data = {
            "usernames": [username],
            "max_count": effective_max,
        }
        raw = self._run_actor(self.actors["following"], input_data)
        results = []
        for item in raw:
            if not item.get("username"):
                continue
            results.append({
                "username": item.get("username", ""),
                "full_name": item.get("full_name", ""),
                "biography": "",  # following scraper doesn't return bio
                "is_verified": item.get("is_verified", False),
                "followers_count": 0,  # not returned by this actor
                "profile_pic_url": item.get("profile_pic_url", ""),
                "is_private": item.get("is_private", False),
            })
        return results[:max_count]

    def get_profile_details(self, usernames: list[str]) -> list[dict]:
        input_data = {"usernames": usernames}
        raw = self._run_actor(self.actors["profile"], input_data)
        results = []
        for item in raw:
            results.append({
                "username": item.get("username", ""),
                "full_name": item.get("fullName", item.get("full_name", "")),
                "biography": item.get("biography", item.get("bio", "")),
                "is_verified": item.get("isVerified", item.get("verified", False)),
                "followers_count": item.get("followersCount", item.get("follower_count", 0)),
                "following_count": item.get("followingCount", item.get("following_count", 0)),
                "posts_count": item.get("postsCount", item.get("media_count", 0)),
                "external_url": item.get("externalUrl", item.get("external_url", "")),
                "is_private": item.get("isPrivate", item.get("is_private", False)),
                "is_business": item.get("isBusinessAccount", item.get("is_business", False)),
                "category": item.get("businessCategoryName", item.get("category", "")),
                "recent_posts": _extract_recent_posts(item),
            })
        return results

    def get_post_likers(self, post_url: str, max_count: int) -> list[dict]:
        # scraping_solutions/instagram-engagers-likers-and-commenters-no-cookies
        input_data = {
            "Posts": [post_url],
            "results_limit": max_count,
        }
        raw = self._run_actor(self.actors["likers"], input_data)
        results = []
        for item in raw:
            if not item.get("username"):
                continue
            results.append({
                "username": item.get("username", ""),
                "full_name": item.get("full_name", item.get("fullName", "")),
                "biography": item.get("biography", item.get("bio", "")),
                "is_verified": item.get("is_verified", item.get("isVerified", False)),
                "followers_count": item.get("followers_count", item.get("followersCount", 0)),
                "is_private": item.get("is_private", item.get("isPrivate", False)),
                "profile_pic_url": item.get("profile_pic_url", item.get("profilePicUrl", "")),
            })
        return results


def _extract_recent_posts(profile: dict) -> list[dict]:
    """Extract recent post captions/types from profile data if available."""
    posts = []
    for key in ("latestPosts", "edge_owner_to_timeline_media", "posts"):
        raw_posts = profile.get(key)
        if isinstance(raw_posts, dict):
            raw_posts = raw_posts.get("edges", [])
        if isinstance(raw_posts, list):
            for p in raw_posts[:6]:
                node = p.get("node", p)
                caption = ""
                cap_data = node.get("caption", node.get("edge_media_to_caption", ""))
                if isinstance(cap_data, dict):
                    edges = cap_data.get("edges", [])
                    if edges:
                        caption = edges[0].get("node", {}).get("text", "")
                elif isinstance(cap_data, str):
                    caption = cap_data
                posts.append({
                    "caption": caption[:200] if caption else "",
                    "type": node.get("type", node.get("__typename", "")),
                    "likes": node.get("likesCount", node.get("edge_liked_by", {}).get("count", 0)) if isinstance(node.get("edge_liked_by"), dict) else node.get("likesCount", 0),
                })
            break
    return posts


# ---------------------------------------------------------------------------
# Claude analysis
# ---------------------------------------------------------------------------
CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"


def _call_claude(api_key: str, system: str, user_msg: str, max_tokens: int = 4096) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": "claude-sonnet-4-20250514",
        "max_tokens": max_tokens,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}],
    }
    resp = requests.post(CLAUDE_API_URL, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text[:500]}")
    data = resp.json()
    return data["content"][0]["text"]


def classify_followings(api_key: str, followings: list[dict]) -> dict:
    """Classify following accounts into categories using Claude."""
    system = (
        "あなたはSNSアカウント分析の専門家です。\n"
        "与えられたInstagramアカウントのリストを、以下のカテゴリに分類してください。\n"
        "1つのアカウントは1つのカテゴリのみに分類。\n\n"
        "カテゴリ例: Fashion, Beauty, Food/Gourmet, Travel, Fitness/Health, "
        "Entertainment/Celebrity, Music, Art/Design, Tech, Business/Entrepreneur, "
        "Education, Lifestyle, News/Media, Sports, Gaming, Pets/Animals, "
        "Photography, Automotive, Kids/Parenting, Brand/Official, Other\n\n"
        "必ず以下のJSON形式で回答してください（他のテキストは不要）:\n"
        '{"classified": [{"username": "...", "category": "...", "subcategory": "..."}, ...]}'
    )

    BATCH_SIZE = 50
    all_classified = []

    for i in range(0, len(followings), BATCH_SIZE):
        batch = followings[i:i + BATCH_SIZE]
        accounts_text = "\n".join(
            f"- @{a['username']} | {a.get('full_name', '')} | bio: {a.get('biography', '')[:100]} | "
            f"verified: {a.get('is_verified', False)} | followers: {a.get('followers_count', 0)}"
            for a in batch
        )
        user_msg = f"以下の{len(batch)}アカウントを分類してください:\n\n{accounts_text}"

        logger.info(f"Claude: classifying batch {i // BATCH_SIZE + 1} ({len(batch)} accounts)")
        raw = _call_claude(api_key, system, user_msg)

        try:
            parsed = json.loads(_extract_json(raw))
            all_classified.extend(parsed.get("classified", []))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse classification response: {e}")
            for a in batch:
                all_classified.append({"username": a["username"], "category": "Other", "subcategory": ""})

    # Aggregate
    categories = {}
    for item in all_classified:
        cat = item.get("category", "Other")
        if cat not in categories:
            categories[cat] = {"count": 0, "subcategories": {}, "accounts": []}
        categories[cat]["count"] += 1
        sub = item.get("subcategory", "")
        if sub:
            categories[cat]["subcategories"][sub] = categories[cat]["subcategories"].get(sub, 0) + 1
        categories[cat]["accounts"].append(item["username"])

    return {"classified": all_classified, "categories": categories, "total": len(all_classified)}


def match_personas(api_key: str, users: list[dict], persona: str) -> list[dict]:
    """Score users against a persona description using Claude."""
    system = (
        "あなたはターゲティング分析の専門家です。\n"
        "与えられたInstagramユーザーのリストを、指定されたペルソナとの適合度で0-100のスコアで評価してください。\n"
        "bio、フォロワー数、アカウント特性から推定してください。\n\n"
        "必ず以下のJSON形式で回答してください（他のテキストは不要）:\n"
        '{"scored": [{"username": "...", "score": 85, "reason": "..."}, ...]}'
    )

    BATCH_SIZE = 30
    all_scored = []

    for i in range(0, len(users), BATCH_SIZE):
        batch = users[i:i + BATCH_SIZE]
        users_text = "\n".join(
            f"- @{u['username']} | {u.get('full_name', '')} | bio: {u.get('biography', '')[:150]} | "
            f"followers: {u.get('followers_count', 0)} | private: {u.get('is_private', False)}"
            for u in batch
        )
        user_msg = (
            f"ペルソナ: {persona}\n\n"
            f"以下の{len(batch)}ユーザーを評価してください:\n\n{users_text}"
        )

        logger.info(f"Claude: persona matching batch {i // BATCH_SIZE + 1} ({len(batch)} users)")
        raw = _call_claude(api_key, system, user_msg)

        try:
            parsed = json.loads(_extract_json(raw))
            all_scored.extend(parsed.get("scored", []))
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to parse persona matching response: {e}")
            for u in batch:
                all_scored.append({"username": u["username"], "score": 0, "reason": "parse error"})

    all_scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return all_scored


def generate_report_a(api_key: str, username: str, followings: list[dict], classification: dict) -> str:
    """Generate Mode A analysis report."""
    system = (
        "あなたは広告クリエイティブ戦略のコンサルタントです。\n"
        "Instagramユーザーのフォローデータ分析結果から、広告制作に役立つインサイトレポートを生成してください。\n"
        "日本語で回答してください。Markdownフォーマットで出力してください。"
    )

    # Top categories
    sorted_cats = sorted(
        classification["categories"].items(),
        key=lambda x: x[1]["count"],
        reverse=True,
    )
    cat_summary = "\n".join(
        f"- {cat}: {data['count']}件 ({data['count'] * 100 // max(classification['total'], 1)}%)"
        + (f" [サブ: {', '.join(f'{k}({v})' for k, v in sorted(data['subcategories'].items(), key=lambda x: -x[1])[:3])}]" if data["subcategories"] else "")
        for cat, data in sorted_cats[:15]
    )

    # Notable accounts (verified or high followers)
    notable = [f for f in followings if f.get("is_verified") or f.get("followers_count", 0) > 100000]
    notable_text = "\n".join(
        f"- @{a['username']} ({a.get('full_name', '')}) - followers: {a.get('followers_count', 0):,} - bio: {a.get('biography', '')[:80]}"
        for a in sorted(notable, key=lambda x: x.get("followers_count", 0), reverse=True)[:20]
    )

    user_msg = (
        f"# 分析対象: @{username}\n\n"
        f"## フォロー数: {len(followings)}アカウント（分析: {classification['total']}件）\n\n"
        f"## カテゴリ分布:\n{cat_summary}\n\n"
        f"## 注目アカウント（認証済み/高フォロワー）:\n{notable_text or '（なし）'}\n\n"
        "以下の構成でレポートを生成してください:\n"
        "1. フォロー概要（総数、カテゴリ分布の傾向）\n"
        "2. 興味関心マップ（上位カテゴリ + サブカテゴリの解説）\n"
        "3. コンテンツ消費傾向（どんなコンテンツを日常的に見ているか）\n"
        "4. 注目フォロー先（ブランド・インフルエンサーの特徴）\n"
        "5. 広告クリエイティブへの示唆（トーン、メッセージング、フォーマット推奨）\n"
        "6. ペルソナサマリー（この人物像を1-2段落で描写）"
    )

    logger.info("Claude: generating Mode A report")
    return _call_claude(api_key, system, user_msg, max_tokens=4096)


def generate_report_b(
    api_key: str,
    post_url: str,
    persona: str,
    scored_users: list[dict],
    user_analyses: list[dict],
) -> str:
    """Generate Mode B integrated report."""
    system = (
        "あなたは広告クリエイティブ戦略のコンサルタントです。\n"
        "投稿のいいねユーザー分析から、ターゲット層の統合インサイトレポートを生成してください。\n"
        "日本語で回答してください。Markdownフォーマットで出力してください。"
    )

    # Aggregate category data across all analyzed users
    all_categories = {}
    for analysis in user_analyses:
        cls = analysis.get("classification", {})
        for cat, data in cls.get("categories", {}).items():
            if cat not in all_categories:
                all_categories[cat] = 0
            all_categories[cat] += data["count"]

    sorted_cats = sorted(all_categories.items(), key=lambda x: -x[1])
    cat_text = "\n".join(f"- {cat}: {count}件" for cat, count in sorted_cats[:15])

    # Common followings (followed by 2+ analyzed users)
    follow_counts = {}
    for analysis in user_analyses:
        for f in analysis.get("followings", []):
            uname = f["username"]
            if uname not in follow_counts:
                follow_counts[uname] = {"count": 0, "data": f}
            follow_counts[uname]["count"] += 1
    common = sorted(
        [(u, d) for u, d in follow_counts.items() if d["count"] >= 2],
        key=lambda x: -x[1]["count"],
    )
    common_text = "\n".join(
        f"- @{u} ({d['data'].get('full_name', '')}) - {d['count']}/{len(user_analyses)}人がフォロー"
        for u, d in common[:20]
    )

    matched_text = "\n".join(
        f"- @{u['username']} (スコア: {u.get('score', 0)}) - {u.get('reason', '')}"
        for u in scored_users[:10]
    )

    user_msg = (
        f"# 投稿: {post_url}\n"
        f"# ペルソナ条件: {persona}\n\n"
        f"## ペルソナマッチユーザー:\n{matched_text}\n\n"
        f"## 統合カテゴリ分布（{len(user_analyses)}人のフォロー先を集計）:\n{cat_text}\n\n"
        f"## 共通フォロー先（2人以上が共通してフォロー）:\n{common_text or '（なし）'}\n\n"
        "以下の構成でレポートを生成してください:\n"
        "1. いいねユーザー概要（取得数、ペルソナマッチ数）\n"
        "2. マッチしたユーザー一覧（スコア順、各ユーザーの特徴）\n"
        "3. 共通フォロー先ランキング（複数ユーザーが共通してフォロー）\n"
        "4. 統合カテゴリ分布（全ユーザーのフォロー先を合算した傾向）\n"
        "5. ターゲット層の共通インサイト\n"
        "6. 広告クリエイティブへの示唆（トーン、メッセージング、フォーマット推奨）"
    )

    logger.info("Claude: generating Mode B report")
    return _call_claude(api_key, system, user_msg, max_tokens=6000)


def _extract_json(text: str) -> str:
    """Extract JSON from Claude response that may contain markdown fences."""
    # Try to find JSON in code blocks
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try to find raw JSON object
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        return m.group(0)
    return text


# ---------------------------------------------------------------------------
# Input parsing
# ---------------------------------------------------------------------------
def parse_username(input_str: str) -> str | None:
    """Extract username from @handle or Instagram URL."""
    input_str = input_str.strip()
    if input_str.startswith("@"):
        return input_str[1:].strip("/")
    m = re.match(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?", input_str)
    if m:
        uname = m.group(1)
        if uname not in ("p", "reel", "stories", "explore"):
            return uname
    return None


def parse_post_url(url: str) -> str | None:
    """Validate Instagram post URL."""
    m = re.match(r"https?://(?:www\.)?instagram\.com/(?:p|reel)/([A-Za-z0-9_-]+)", url)
    return url if m else None


# ---------------------------------------------------------------------------
# Mode A: User analysis
# ---------------------------------------------------------------------------
def run_mode_a(
    username: str,
    provider: DataProvider,
    cache: CacheManager | None,
    api_key: str,
    max_following: int,
    output_json: bool = False,
) -> dict:
    """Analyze a single user's following list."""
    print(f"\n{'='*60}")
    print(f"  Mode A: @{username} のフォロー分析")
    print(f"{'='*60}\n")

    # 1. Get following list (with cache)
    followings = None
    if cache:
        followings = cache.get("following", username)
        if followings:
            logger.info(f"Cache hit: {username} following ({len(followings)} accounts)")

    if followings is None:
        print(f"[1/4] フォローリスト取得中... (最大{max_following}件)")
        followings = provider.get_following_list(username, max_following)
        if cache:
            cache.put("following", username, followings)
    else:
        print(f"[1/4] フォローリスト: キャッシュから{len(followings)}件読み込み")

    if not followings:
        print("エラー: フォローリストを取得できませんでした（非公開アカウントの可能性）")
        return {"error": "no_followings"}

    print(f"      → {len(followings)}アカウント取得")

    # 2. Enrich profiles (get bio etc. from profile scraper)
    needs_enrichment = any(not f.get("biography") for f in followings)
    if needs_enrichment:
        enriched = None
        if cache:
            enriched = cache.get("profiles", username)
        if enriched is None:
            public_usernames = [f["username"] for f in followings if not f.get("is_private")]
            if public_usernames:
                print(f"[2/4] プロフィール詳細取得中... ({len(public_usernames)}件)")
                try:
                    profiles = provider.get_profile_details(public_usernames)
                    profile_map = {p["username"]: p for p in profiles}
                    for f in followings:
                        if f["username"] in profile_map:
                            p = profile_map[f["username"]]
                            f["biography"] = p.get("biography", "")
                            f["followers_count"] = p.get("followers_count", 0)
                            f["is_verified"] = p.get("is_verified", False)
                    if cache:
                        cache.put("profiles", username, followings)
                except Exception as e:
                    logger.warning(f"Profile enrichment failed: {e}")
                    print(f"      ⚠ プロフィール詳細取得に失敗（分類精度が低下します）: {e}")
            else:
                print("[2/4] プロフィール詳細: 公開アカウントなし、スキップ")
        else:
            followings = enriched
            print(f"[2/4] プロフィール詳細: キャッシュから読み込み")
    else:
        print("[2/4] プロフィール詳細: 既に取得済み")

    # 3. Classify followings
    classification = None
    if cache:
        classification = cache.get("classification", username)
        if classification:
            logger.info(f"Cache hit: {username} classification")

    if classification is None:
        print(f"[3/4] カテゴリ分類中... ({len(followings)}件をClaude分析)")
        classification = classify_followings(api_key, followings)
        if cache:
            cache.put("classification", username, classification)
    else:
        print("[3/4] カテゴリ分類: キャッシュから読み込み")

    # 4. Generate report
    print("[4/4] レポート生成中...")
    report = generate_report_a(api_key, username, followings, classification)

    result = {
        "username": username,
        "following_count": len(followings),
        "classification": classification,
        "report": report,
        "followings": followings,
    }

    if output_json:
        print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'─'*60}")
        print(report)
        print(f"{'─'*60}")

    return result


# ---------------------------------------------------------------------------
# Mode B: Post likers → persona matching → analysis
# ---------------------------------------------------------------------------
def run_mode_b(
    post_url: str,
    persona: str,
    provider: DataProvider,
    cache: CacheManager | None,
    api_key: str,
    max_likers: int,
    top_n: int,
    max_following: int,
    output_json: bool = False,
) -> dict:
    """Analyze post likers, match personas, analyze top matches."""
    print(f"\n{'='*60}")
    print(f"  Mode B: 投稿いいね → ターゲット発掘")
    print(f"  投稿: {post_url}")
    print(f"  ペルソナ: {persona}")
    print(f"{'='*60}\n")

    # 1. Get post likers
    cache_key = hashlib.md5(post_url.encode()).hexdigest()[:12]
    likers = None
    if cache:
        likers = cache.get("likers", cache_key)
        if likers:
            logger.info(f"Cache hit: likers for {post_url} ({len(likers)} users)")

    if likers is None:
        print(f"[1/5] いいねユーザー取得中... (最大{max_likers}件)")
        likers = provider.get_post_likers(post_url, max_likers)
        if cache:
            cache.put("likers", cache_key, likers)
    else:
        print(f"[1/5] いいねユーザー: キャッシュから{len(likers)}件読み込み")

    if not likers:
        print("エラー: いいねユーザーを取得できませんでした")
        return {"error": "no_likers"}

    print(f"      → {len(likers)}ユーザー取得")

    # 2. Persona matching
    print(f"[2/5] ペルソナマッチング中... ({len(likers)}人をスコアリング)")
    scored = match_personas(api_key, likers, persona)
    matched = [u for u in scored if u.get("score", 0) >= 50]
    print(f"      → スコア50以上: {len(matched)}人")

    if not matched:
        print("警告: ペルソナにマッチするユーザーが見つかりませんでした（スコア50以上がゼロ）")
        print("      スコア上位5人で続行します")
        matched = scored[:5]

    # 3. Select top N for deeper analysis
    top_users = matched[:top_n]
    print(f"[3/5] 上位{len(top_users)}人を詳細分析対象に選定")
    for u in top_users:
        print(f"      - @{u['username']} (スコア: {u.get('score', 0)}) {u.get('reason', '')}")

    # 4. Run Mode A for each top user
    print(f"\n[4/5] 上位{len(top_users)}人のフォロー分析...")
    user_analyses = []
    for idx, user in enumerate(top_users, 1):
        uname = user["username"]
        print(f"\n  --- [{idx}/{len(top_users)}] @{uname} ---")

        # Check if account is private
        matching_liker = next((l for l in likers if l["username"] == uname), {})
        if matching_liker.get("is_private", False):
            print(f"  @{uname} は非公開アカウントのためスキップ")
            continue

        try:
            analysis = run_mode_a(
                uname, provider, cache, api_key, max_following, output_json=False
            )
            if "error" not in analysis:
                user_analyses.append(analysis)
        except Exception as e:
            logger.warning(f"Failed to analyze @{uname}: {e}")
            print(f"  @{uname} の分析に失敗: {e}")

    if not user_analyses:
        print("\nエラー: 分析可能なユーザーがいませんでした")
        return {"error": "no_analyzable_users"}

    # 5. Generate integrated report
    print(f"\n[5/5] 統合レポート生成中... ({len(user_analyses)}人分)")
    report = generate_report_b(api_key, post_url, persona, scored, user_analyses)

    result = {
        "post_url": post_url,
        "persona": persona,
        "total_likers": len(likers),
        "matched_count": len(matched),
        "analyzed_users": len(user_analyses),
        "scored_users": scored[:20],
        "user_analyses": [
            {"username": a["username"], "classification": a["classification"]}
            for a in user_analyses
        ],
        "report": report,
    }

    if output_json:
        # Trim for JSON output (followings can be huge)
        print("\n" + json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print("  統合インサイトレポート")
        print(f"{'='*60}\n")
        print(report)
        print(f"\n{'─'*60}")

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="SNS分析ツール — Instagram公開データからターゲットインサイトを分析",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "例:\n"
            "  python sns_analyzer.py @username              # Mode A: ユーザー分析\n"
            "  python sns_analyzer.py @username --max 100    # 最大100フォロー分析\n"
            "  python sns_analyzer.py --post URL --persona P # Mode B: ターゲット発掘\n"
        ),
    )
    parser.add_argument("target", nargs="?", help="@username or Instagram profile URL (Mode A)")
    parser.add_argument("--post", type=str, help="Instagram post URL (Mode B)")
    parser.add_argument("--persona", type=str, help="Persona description for Mode B matching")
    parser.add_argument("--top", type=int, default=None, help="Number of top users to analyze in Mode B")
    parser.add_argument("--max", type=int, default=None, help="Max followings/likers to fetch")
    parser.add_argument("--max-likers", type=int, default=1000, help="Max likers to fetch in Mode B")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cache")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Determine mode
    is_mode_b = bool(args.post)
    if is_mode_b and not args.persona:
        parser.error("--persona は --post と一緒に指定してください")
    if not is_mode_b and not args.target:
        parser.error("@username または --post URL を指定してください")

    # Load config
    config = load_config()

    # Validate API keys
    apify_token = get_apify_token(config)
    if not apify_token:
        print("エラー: Apify APIトークンが設定されていません")
        print(f"  → {CONFIG_FILE} の apify_api_token を設定するか、環境変数 APIFY_API_TOKEN を設定してください")
        sys.exit(1)

    api_key = get_anthropic_api_key(config)
    if not api_key:
        print("エラー: Anthropic APIキーが設定されていません")
        print(f"  → {CONFIG_FILE} の anthropic_api_key を設定するか、環境変数 ANTHROPIC_API_KEY を設定してください")
        sys.exit(1)

    # Setup provider & cache
    provider = ApifyProvider(apify_token, config)
    cache = None if args.no_cache else CacheManager(CACHE_DIR, config.get("cache_ttl_days", 7))
    max_following = args.max or config.get("default_max_following", 300)

    if is_mode_b:
        # Mode B
        post_url = parse_post_url(args.post)
        if not post_url:
            print(f"エラー: 有効なInstagram投稿URLではありません: {args.post}")
            sys.exit(1)

        top_n = args.top or config.get("default_top_users", 5)
        run_mode_b(
            post_url=post_url,
            persona=args.persona,
            provider=provider,
            cache=cache,
            api_key=api_key,
            max_likers=args.max_likers,
            top_n=top_n,
            max_following=max_following,
            output_json=args.json,
        )
    else:
        # Mode A
        username = parse_username(args.target)
        if not username:
            print(f"エラー: ユーザー名を解析できません: {args.target}")
            print("  → @username または https://instagram.com/username/ の形式で指定してください")
            sys.exit(1)

        run_mode_a(
            username=username,
            provider=provider,
            cache=cache,
            api_key=api_key,
            max_following=max_following,
            output_json=args.json,
        )


if __name__ == "__main__":
    main()
