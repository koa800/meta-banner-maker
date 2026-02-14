#!/usr/bin/env python3
"""
LP Banner Generator for Meta Ads
=================================
LPのURLを入力すると、ページ内容を解析し、
Meta広告用バナー（1080x1080）の生成プロンプトを3パターン出力するツール。

Usage:
    python3 banner_generator.py "https://example.com/lp"
    python3 banner_generator.py "https://example.com/lp" --json
"""

import sys
import json
import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse


# ============================================================
# 1. LP スクレイピング & 解析
# ============================================================

def fetch_lp(url: str) -> str:
    """LPのHTMLを取得する"""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def extract_text_content(html: str) -> str:
    """HTMLからテキストコンテンツを抽出する（画像ベースLP対応）"""
    soup = BeautifulSoup(html, "html.parser")

    # scriptとstyleを除去
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    # 通常のテキスト
    text = soup.get_text(separator="\n", strip=True)

    # 画像ベースLPの場合、alt属性にコンテンツが入っている
    alt_texts = []
    for img in soup.find_all("img"):
        alt = img.get("alt", "").strip()
        if alt and len(alt) > 5:
            alt_texts.append(alt)

    # altテキストの方がリッチなら結合して使う（日本のLP対策）
    alt_combined = "\n".join(alt_texts)
    if len(alt_combined) > len(text) * 0.5:
        text = text + "\n\n=== 画像内テキスト ===\n" + alt_combined

    # 連続する空行を1行にまとめる
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_meta_info(html: str) -> dict:
    """HTMLからメタ情報を抽出する"""
    soup = BeautifulSoup(html, "html.parser")
    meta = {}

    # title
    title_tag = soup.find("title")
    meta["title"] = title_tag.get_text(strip=True) if title_tag else ""

    # meta description
    desc_tag = soup.find("meta", attrs={"name": "description"})
    meta["description"] = desc_tag.get("content", "") if desc_tag else ""

    # OGP
    og_title = soup.find("meta", attrs={"property": "og:title"})
    meta["og_title"] = og_title.get("content", "") if og_title else ""

    og_desc = soup.find("meta", attrs={"property": "og:description"})
    meta["og_description"] = og_desc.get("content", "") if og_desc else ""

    og_image = soup.find("meta", attrs={"property": "og:image"})
    meta["og_image"] = og_image.get("content", "") if og_image else ""

    return meta


def extract_headings(html: str) -> list:
    """見出しタグを抽出する（画像ベースLP対応）"""
    soup = BeautifulSoup(html, "html.parser")
    headings = []

    # 通常のh1-h3
    for tag in soup.find_all(["h1", "h2", "h3"]):
        text = tag.get_text(strip=True)
        if text:
            headings.append({"level": tag.name, "text": text})

    # 見出しが少ない場合、主要なalt属性を疑似見出しとして使う
    if len(headings) < 3:
        for img in soup.find_all("img"):
            alt = img.get("alt", "").strip()
            if alt and 10 < len(alt) < 80 and not any(h["text"] == alt for h in headings):
                headings.append({"level": "img-alt", "text": alt})

    return headings


def extract_prices(text: str) -> list:
    """テキストから価格情報を抽出する"""
    prices = []
    # 日本円パターン
    patterns = [
        r"[\d,]+円",
        r"¥[\d,]+",
        r"\d+%\s*OFF",
        r"\d+%\s*off",
        r"初回[^\n]*?[\d,]+円",
        r"定期[^\n]*?[\d,]+円",
        r"通常[^\n]*?[\d,]+円",
        r"送料[^\n]*?[\d,]+円",
        r"送料[^\n]*?無料",
    ]
    for pat in patterns:
        matches = re.findall(pat, text)
        prices.extend(matches)
    return list(set(prices))


def extract_selling_points(text: str) -> list:
    """テキストからセールスポイントを抽出する"""
    keywords = []

    # 信頼・権威系
    trust_patterns = [
        r"[^\n]*(?:医薬品|製薬|医療)[^\n]*",
        r"[^\n]*(?:特許|独自開発|日本初|業界初|世界初)[^\n]*",
        r"[^\n]*(?:創業|実績)\d+[^\n]*",
        r"[^\n]*(?:雑誌|メディア|テレビ|TV)[^\n]*掲載[^\n]*",
        r"[^\n]*(?:モンドセレクション|受賞)[^\n]*",
        r"[^\n]*(?:専門家|医師|ドクター)[^\n]*監修[^\n]*",
    ]

    # 安心系
    safety_patterns = [
        r"[^\n]*(?:無添加|オーガニック|天然|自然由来)[^\n]*",
        r"[^\n]*(?:国内製造|日本製|Made in Japan)[^\n]*",
        r"[^\n]*返金保証[^\n]*",
        r"[^\n]*回数[^\n]*縛り[^\n]*(?:なし|ない|ございません)[^\n]*",
    ]

    # 効果・訴求系
    benefit_patterns = [
        r"[^\n]*(?:シワ|しわ|シミ|しみ|美白|美肌|保湿|エイジング)[^\n]*",
        r"[^\n]*(?:ダイエット|痩せ|脂肪|代謝)[^\n]*",
        r"[^\n]*(?:薄毛|育毛|発毛|抜け毛)[^\n]*",
        r"[^\n]*(?:口臭|体臭|デオドラント|ニオイ|臭い)[^\n]*",
        r"[^\n]*(?:便秘|腸内|腸活|乳酸菌)[^\n]*",
        r"[^\n]*(?:睡眠|快眠|不眠)[^\n]*",
        r"[^\n]*(?:効果|実感|改善|予防|ケア)[^\n]*",
    ]

    # 口コミ・実績系
    social_patterns = [
        r"[^\n]*(?:SNS|口コミ|レビュー|話題)[^\n]*",
        r"[^\n]*(?:満足度|リピート率)\s*[\d.]+%[^\n]*",
        r"[^\n]*(?:累計|販売実績)\s*[\d,万]+[^\n]*",
    ]

    all_patterns = trust_patterns + safety_patterns + benefit_patterns + social_patterns
    for pat in all_patterns:
        matches = re.findall(pat, text)
        for m in matches:
            clean = m.strip()
            if 10 < len(clean) < 100:
                keywords.append(clean)

    # 重複排除して上位を返す
    seen = set()
    unique = []
    for k in keywords:
        if k not in seen:
            seen.add(k)
            unique.append(k)
    return unique[:20]


def detect_product_category(text: str) -> str:
    """商品カテゴリを推定する"""
    categories = {
        "スキンケア・美容液": ["美容液", "化粧水", "クリーム", "乳液", "セラム", "スキンケア", "美肌", "シワ", "シミ", "保湿"],
        "サプリメント": ["サプリ", "タブレット", "カプセル", "粒", "栄養機能食品", "健康食品"],
        "ダイエット": ["ダイエット", "痩せ", "脂肪燃焼", "置き換え", "カロリー"],
        "ヘアケア": ["シャンプー", "育毛", "発毛", "ヘアケア", "トリートメント", "薄毛"],
        "健康食品": ["青汁", "酵素", "プロテイン", "乳酸菌", "腸活"],
        "デオドラント": ["体臭", "口臭", "デオドラント", "消臭"],
        "その他": [],
    }
    scores = {cat: 0 for cat in categories}
    text_lower = text.lower()
    for cat, kws in categories.items():
        for kw in kws:
            scores[cat] += text_lower.count(kw)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "その他"


def analyze_lp(url: str) -> dict:
    """LPを総合解析する"""
    html = fetch_lp(url)
    text = extract_text_content(html)
    meta = extract_meta_info(html)
    headings = extract_headings(html)
    prices = extract_prices(text)
    selling_points = extract_selling_points(text)
    category = detect_product_category(text)

    # ドメイン
    domain = urlparse(url).netloc

    return {
        "url": url,
        "domain": domain,
        "meta": meta,
        "headings": headings,
        "prices": prices,
        "selling_points": selling_points,
        "category": category,
        "text_excerpt": text[:3000],
    }


# ============================================================
# 2. バナープロンプト生成
# ============================================================

def build_banner_prompts(analysis: dict) -> list:
    """解析結果からバナー生成用プロンプト3パターンを作成する"""

    # コンテキストを組み立て
    title = analysis["meta"].get("title", "") or analysis["meta"].get("og_title", "")
    description = analysis["meta"].get("description", "") or analysis["meta"].get("og_description", "")
    category = analysis["category"]
    headings_text = " / ".join([h["text"] for h in analysis["headings"][:10]])
    prices_text = " / ".join(analysis["prices"][:10])
    points_text = "\n".join([f"- {p}" for p in analysis["selling_points"][:10]])

    # テキスト抜粋の先頭部分
    excerpt = analysis["text_excerpt"][:1500]

    # ---- 共通コンテキスト ----
    context_block = f"""
=== LP Analysis ===
URL: {analysis['url']}
Title: {title}
Description: {description}
Category: {category}
Headings: {headings_text}
Prices found: {prices_text}
Key selling points:
{points_text}

Page content excerpt:
{excerpt}
""".strip()

    # ---- パターンA: 価格訴求 ----
    prompt_a = f"""A square 1080x1080 Meta/Facebook ad banner for a Japanese product.

DESIGN FOCUS: PRICE / DISCOUNT APPEAL - Make the discount and price the hero element.

Based on this LP analysis, create a banner that emphasizes the price offer:
{context_block}

Layout guidelines:
- Top: Large bold discount text (e.g. "初回限定 XX%OFF") in elegant gold on a deep burgundy/wine-colored gradient background
- Center: Product image visualization - a beautiful product package with premium lighting and decorative elements matching the product category ({category})
- Price area: Discounted price in large white text, with original price shown with strikethrough
- Bottom: One-line trust element from the selling points, with a subtle CTA button
- Overall mood: Premium, trustworthy, luxurious
- Color palette: deep wine red, gold, cream white
- Japanese text should be clean and elegant
- Do NOT include any human faces or photos of people
- All text should be in Japanese based on the LP content"""

    # ---- パターンB: 悩み訴求 ----
    prompt_b = f"""A square 1080x1080 Meta/Facebook ad banner for a Japanese product.

DESIGN FOCUS: EMOTIONAL / CONCERN APPEAL - Speak to the target audience's pain points and desires.

Based on this LP analysis, create a banner that connects emotionally with the target:
{context_block}

Layout guidelines:
- Top area: Emotional headline question that speaks to the target's concerns (derived from the LP's selling points), in elegant serif font, white text
- Background: Soft gradient from deep navy blue to warm rose gold, creating a sophisticated and calming atmosphere
- Center: Visual metaphor showing transformation - abstract before/after concept (do NOT show actual human skin or faces), use light effects to show the "after" state as radiant and glowing
- Bottom section: Product/brand name in gold lettering with category descriptor
- Small badge highlighting key benefit
- Overall mood: Empathetic, hopeful, elegant. Targets emotional connection.
- Japanese text should be clean and elegant
- Do NOT include any human faces or photos of people"""

    # ---- パターンC: 信頼訴求 ----
    prompt_c = f"""A square 1080x1080 Meta/Facebook ad banner for a Japanese product.

DESIGN FOCUS: TRUST / AUTHORITY APPEAL - Emphasize credibility, expertise, and quality.

Based on this LP analysis, create a banner that builds trust and authority:
{context_block}

Layout guidelines:
- Top: Bold headline emphasizing the authority/expertise behind the product (from selling points), clean white text
- Background: Clean, clinical yet luxurious - white to soft cream gradient with subtle geometric patterns suggesting science/research/professionalism
- Center: Product visualization on a minimalist pedestal, with relevant motifs (molecular/scientific for health products, nature for organic, etc.) in soft gold lines
- Key trust badges arranged around the product (e.g., certifications, years in business, unique ingredients, awards)
- Bottom: Safety/quality claims with a gold accent line, plus a small price badge
- Overall mood: Scientific authority, professional trust, premium quality
- Japanese text should be clean and professional
- Do NOT include any human faces or photos of people"""

    return [
        {"pattern": "A", "name": "価格訴求", "focus": "Price/Discount Appeal", "prompt": prompt_a.strip()},
        {"pattern": "B", "name": "悩み訴求", "focus": "Emotional/Concern Appeal", "prompt": prompt_b.strip()},
        {"pattern": "C", "name": "信頼訴求", "focus": "Trust/Authority Appeal", "prompt": prompt_c.strip()},
    ]


# ============================================================
# 3. メイン & 出力
# ============================================================

def print_analysis(analysis: dict):
    """解析結果をわかりやすく表示する"""
    title = analysis["meta"].get("title", "") or analysis["meta"].get("og_title", "")
    print("=" * 60)
    print("  LP ANALYSIS REPORT")
    print("=" * 60)
    print(f"  URL      : {analysis['url']}")
    print(f"  Title    : {title}")
    print(f"  Category : {analysis['category']}")
    print()

    if analysis["prices"]:
        print("  [価格情報]")
        for p in analysis["prices"]:
            print(f"    • {p}")
        print()

    if analysis["selling_points"]:
        print("  [セールスポイント]")
        for sp in analysis["selling_points"][:10]:
            print(f"    • {sp}")
        print()

    if analysis["headings"]:
        print("  [見出し]")
        for h in analysis["headings"][:8]:
            print(f"    [{h['level']}] {h['text']}")
        print()


def print_prompts(prompts: list):
    """プロンプトを表示する"""
    for p in prompts:
        print("=" * 60)
        print(f"  PATTERN {p['pattern']}: {p['name']} ({p['focus']})")
        print("=" * 60)
        print(p["prompt"])
        print()


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 banner_generator.py <LP_URL> [--json]")
        print()
        print("Examples:")
        print('  python3 banner_generator.py "https://example.com/lp"')
        print('  python3 banner_generator.py "https://example.com/lp" --json')
        sys.exit(1)

    url = sys.argv[1]
    output_json = "--json" in sys.argv

    # 進捗はstderrに出力（JSON出力時に混ざらないように）
    sys.stderr.write(f"\n  Fetching & analyzing: {url}\n\n")

    try:
        analysis = analyze_lp(url)
    except Exception as e:
        sys.stderr.write(f"  ERROR: LP取得に失敗しました: {e}\n")
        sys.exit(1)

    prompts = build_banner_prompts(analysis)

    if output_json:
        output = {
            "analysis": {
                "url": analysis["url"],
                "domain": analysis["domain"],
                "meta": analysis["meta"],
                "category": analysis["category"],
                "prices": analysis["prices"],
                "selling_points": analysis["selling_points"],
                "headings": analysis["headings"],
            },
            "prompts": prompts,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print_analysis(analysis)
        print_prompts(prompts)

    if not output_json:
        print("=" * 60)
        print("  DONE! Copy a prompt above and use it with an image generator.")
        print("=" * 60)


if __name__ == "__main__":
    main()
