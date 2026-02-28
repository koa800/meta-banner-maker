#!/usr/bin/env python3
"""画像・スクリーンショット・ドキュメントをClaude Visionで分析し、構造化知識を返すCLI

使い方:
  python3 content_analyzer.py image <image_url> [instruction]

出力: JSON {"title": "...", "summary": "...", "key_points": [...], "use_context": "..."}
"""

import base64
import json
import os
import sys
from pathlib import Path

import anthropic
import requests


VISION_MODEL = "claude-haiku-4-5-20251001"
VISION_MAX_TOKENS = 1024

ANALYSIS_PROMPT = """この画像を分析して、以下の形式で知識として構造化してください。

1. title: この画像の内容を一言で（例: 「Lステップの配信設定画面」「広告レポートのダッシュボード」）
2. summary: 何が写っているか、要点を3行以内で
3. key_points: 覚えておくべきポイントをリスト化（3-7項目）
4. use_context: この知識はどのような場面で役立つか（例: 「Lステップの配信設定について聞かれたとき」「シナリオ配信の手順を説明するとき」）

{instruction}

以下のJSON形式で返してください。JSON以外の文字は含めないでください。
{{
  "title": "...",
  "summary": "...",
  "key_points": ["...", "..."],
  "use_context": "..."
}}"""


def _get_api_key() -> str:
    """APIキーを取得: 環境変数 → config.json"""
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if key:
        return key
    config_path = Path(__file__).resolve().parent / "line_bot_local" / "config.json"
    if config_path.exists():
        try:
            cfg = json.loads(config_path.read_text(encoding="utf-8"))
            return cfg.get("anthropic_api_key", "")
        except Exception:
            pass
    return ""


def _download_image(url: str) -> tuple:
    """画像をダウンロードして (base64, media_type) を返す"""
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    content_type = resp.headers.get("Content-Type", "image/jpeg")
    if "png" in content_type:
        media_type = "image/png"
    elif "gif" in content_type:
        media_type = "image/gif"
    elif "webp" in content_type:
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"

    b64 = base64.b64encode(resp.content).decode("utf-8")
    return b64, media_type


def analyze_image(image_url: str, instruction: str = "") -> str:
    """画像をClaude Vision (Haiku) で分析 → JSON返却"""
    api_key = _get_api_key()
    if not api_key:
        return json.dumps({"error": "ANTHROPIC_API_KEY が未設定です"}, ensure_ascii=False)

    # 画像をダウンロード+Base64エンコード
    try:
        b64_data, media_type = _download_image(image_url)
    except Exception as e:
        return json.dumps({"error": f"画像のダウンロードに失敗しました: {e}"}, ensure_ascii=False)

    # プロンプト構築
    instruction_text = f"ユーザーの補足指示: {instruction}" if instruction else ""
    prompt = ANALYSIS_PROMPT.format(instruction=instruction_text)

    # Claude Vision API 呼び出し
    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=VISION_MODEL,
            max_tokens=VISION_MAX_TOKENS,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }],
        )
    except Exception as e:
        return json.dumps({"error": f"Claude Vision API エラー: {e}"}, ensure_ascii=False)

    # レスポンスからテキスト抽出
    result_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            result_text += block.text

    # JSON部分を抽出（余計なテキストがあっても対応）
    try:
        # まず全体をパースしてみる
        parsed = json.loads(result_text.strip())
        return json.dumps(parsed, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        # JSON部分を抽出
        import re
        m = re.search(r'\{[\s\S]*\}', result_text)
        if m:
            try:
                parsed = json.loads(m.group(0))
                return json.dumps(parsed, ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                pass
        return json.dumps({"error": "分析結果のパースに失敗しました", "raw": result_text[:500]}, ensure_ascii=False)


def main():
    if len(sys.argv) < 3:
        print("使い方: python3 content_analyzer.py image <image_url> [instruction]", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    if command == "image":
        image_url = sys.argv[2]
        instruction = sys.argv[3] if len(sys.argv) > 3 else ""
        print(analyze_image(image_url, instruction))
    else:
        print(f"不明なコマンド: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
