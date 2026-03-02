#!/usr/bin/env python3
"""
AI関連ニュースをGoogle Newsで検索し、日本語要約してSlackに通知するスクリプト
"""

import json
import logging
import os
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger("ai_news_notifier")

CONFIG_PATH = Path(__file__).parent / "config" / "ai_news.json"


def load_config():
    """設定ファイルを読み込む"""
    if not CONFIG_PATH.exists():
        print(f"Error: 設定ファイルが見つかりません: {CONFIG_PATH}", file=sys.stderr)
        print("config/ai_news.json を作成してください", file=sys.stderr)
        sys.exit(1)
    
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_google_news_rss(keyword: str) -> list[dict]:
    """
    Google News RSSからニュースを取得
    
    Args:
        keyword: 検索キーワード
    
    Returns:
        list[dict]: ニュース記事のリスト
    """
    encoded_keyword = urllib.parse.quote(keyword)
    url = f"https://news.google.com/rss/search?q={encoded_keyword}&hl=en-US&gl=US&ceid=US:en"
    
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error("Google News取得エラー", extra={"keyword": keyword, "error": {"type": type(e).__name__, "message": str(e)}})
        print(f"Warning: Google News fetch error for '{keyword}': {e}")
        return []
    
    articles = []
    try:
        root = ET.fromstring(response.content)
        channel = root.find("channel")
        if channel is None:
            return []
        
        for item in channel.findall("item"):
            title = item.find("title")
            link = item.find("link")
            pub_date = item.find("pubDate")
            source = item.find("source")
            
            articles.append({
                "title": title.text if title is not None else "",
                "link": link.text if link is not None else "",
                "pub_date": pub_date.text if pub_date is not None else "",
                "source": source.text if source is not None else "",
            })
    except ET.ParseError as e:
        logger.error("XMLパースエラー", extra={"keyword": keyword, "error": {"type": "ParseError", "message": str(e)}})
        print(f"Warning: XML parse error for '{keyword}': {e}")
        return []
    
    return articles


def fetch_all_news(config: dict) -> list[dict]:
    """
    設定されたキーワードでニュースを収集
    
    Returns:
        list[dict]: 重複除去されたニュース記事のリスト
    """
    keywords = config.get("search_keywords", [
        "OpenAI",
        "Anthropic Claude",
        "Google Gemini",
        "ChatGPT",
        "AI artificial intelligence",
    ])
    
    all_articles = []
    seen_titles = set()
    
    for keyword in keywords:
        print(f"  検索中: {keyword}")
        articles = fetch_google_news_rss(keyword)
        
        for article in articles:
            # タイトルで重複チェック（類似タイトルも除外）
            title_normalized = re.sub(r'\s+', ' ', article["title"].lower().strip())
            if title_normalized not in seen_titles:
                seen_titles.add(title_normalized)
                all_articles.append(article)
    
    # 最大件数に絞る
    max_articles = config.get("max_articles", 20)
    return all_articles[:max_articles]


def _run_claude_cli(prompt: str, model: str = "claude-sonnet-4-6",
                    max_turns: int = 3, timeout: int = 120) -> str:
    """Claude Code CLI でテキスト生成。サブスク課金でAPI消費なし。"""
    import subprocess as _sp
    env = os.environ.copy()
    path = env.get("PATH", "")
    if "/opt/homebrew/bin" not in path:
        env["PATH"] = f"/opt/homebrew/bin:{path}"
    claude_cmd = "/opt/homebrew/bin/claude"
    cmd = [claude_cmd, "-p", "--model", model, "--max-turns", str(max_turns), prompt]
    result = _sp.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed (code={result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()


def summarize_with_claude_cli(articles: list[dict], config: dict) -> str:
    """Claude Code CLI で記事を日本語要約（サブスク課金・API消費なし）"""
    articles_text = "\n".join([
        f"- {a['title']} ({a['source']})"
        for a in articles
    ])

    prompt = f"""あなたはAI業界に詳しいテックライターです。英語のニュース見出しを日本語で分かりやすく要約します。専門用語は適切に解説してください。

以下はGoogle Newsから収集したAI関連の最新ニュース見出しです。
これらを日本語で要約し、重要なニュースや発表をまとめてください。

要約のフォーマット:
- 箇条書きで主要なニュースを5-8個程度
- 各項目は1-2文で簡潔に日本語で説明
- 特に重要なものには 🔥 をつける
- 情報源も含める
- 冒頭に「📅 {datetime.now().strftime('%Y/%m/%d')} のAIニュースまとめ」というタイトル

---
{articles_text}
---"""

    return _run_claude_cli(prompt, model="claude-sonnet-4-6", max_turns=3, timeout=120)


def send_to_slack(message: str, config: dict) -> bool:
    """
    Slack Webhookで通知を送信
    
    Returns:
        bool: 送信成功かどうか
    """
    webhook_url = config.get("slack_webhook_url", "").strip()
    if not webhook_url:
        webhook_url = os.environ.get("SLACK_AI_TEAM_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("Slack Webhook URL 未設定 → Slack通知スキップ")
        return False
    
    payload = {
        "text": message,
        "unfurl_links": False,
        "unfurl_media": False,
    }
    
    # チャンネル指定がある場合
    if config.get("slack_channel"):
        payload["channel"] = config["slack_channel"]
    
    response = requests.post(
        webhook_url,
        json=payload,
        timeout=30,
    )
    
    if response.status_code != 200:
        logger.error("Slack送信エラー", extra={
            "status_code": response.status_code,
            "error": {"type": "SlackError", "message": response.text[:300]},
        })
        print(f"Slack送信エラー: {response.status_code} - {response.text}")
        return False
    
    return True


def main():
    """メイン処理"""
    print(f"[{datetime.now().isoformat()}] AI News Notifier 開始")
    
    try:
        # 設定読み込み
        config = load_config()
        print("設定ファイル読み込み完了")
        
        # Google News検索
        print("Google Newsで検索中...")
        articles = fetch_all_news(config)
        print(f"  → {len(articles)} 件の記事を取得")
        
        if not articles:
            print("記事が見つかりませんでした。終了します。")
            return
        
        # 要約
        print("Claude Code CLIで要約中...")
        summary = summarize_with_claude_cli(articles, config)
        print("  → 要約完了")
        
        # Slack送信
        print("Slackに送信中...")
        slack_ok = send_to_slack(summary, config)

        if slack_ok:
            print("✅ Slack送信完了！")
        else:
            print("⚠️ Slack送信スキップ/失敗（要約自体は成功）")

        # 要約結果を stdout に出力（orchestrator が output として取得）
        print(f"\n{summary}")
            
    except Exception as e:
        logger.exception("AI News Notifier メイン処理エラー", extra={
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        error_msg = f"❌ エラーが発生しました: {e}"
        print(error_msg)
        
        # エラー時もSlackに通知（Webhook URLが設定されていれば）
        try:
            config = load_config()
            if config.get("slack_webhook_url") and config.get("notify_on_error", True):
                send_to_slack(f"⚠️ AI News Notifier エラー\n```{e}```", config)
        except:
            pass
        
        sys.exit(1)
    
    print(f"[{datetime.now().isoformat()}] 完了")


if __name__ == "__main__":
    main()
