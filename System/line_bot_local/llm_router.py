"""
LLM Router — Anthropic / OpenAI 統一インターフェース
設定ファイル1つでモデル切替可能。コード変更不要。
"""

import json
import os
import time
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "llm_router.json"


def _load_config() -> dict:
    """設定ファイルを読み込む（毎回読み直して即時反映）"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(config: dict):
    """設定ファイルを書き込む"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_engine_version() -> str:
    """現在のエンジンバージョンを取得"""
    config = _load_config()
    return config.get("engine_version", "v1")


def get_default_model() -> dict:
    """現在のデフォルトモデルを取得"""
    config = _load_config()
    return config["default_model"]


def switch_model(provider: str, model: str) -> str:
    """モデルを切り替える。成功時はメッセージを返す。"""
    config = _load_config()
    providers = config.get("providers", {})
    if provider not in providers:
        return f"プロバイダー '{provider}' は登録されていません。利用可能: {list(providers.keys())}"
    if model not in providers[provider].get("models", []):
        return f"モデル '{model}' は {provider} に登録されていません。利用可能: {providers[provider]['models']}"
    config["default_model"] = {
        "provider": provider,
        "model": model,
        "max_tokens": config["default_model"].get("max_tokens", 1024),
    }
    _save_config(config)
    return f"{model} に切り替えました。"


def switch_engine_version(version: str) -> str:
    """エンジンバージョンを切り替える（v1/v2）"""
    config = _load_config()
    config["engine_version"] = version
    _save_config(config)
    return f"エンジンを {version} に切り替えました。"


# ---------------------------------------------------------------------------
# Anthropic / OpenAI 統一チャットインターフェース
# ---------------------------------------------------------------------------

def _get_api_key(provider: str) -> str:
    config = _load_config()
    env_var = config["providers"][provider]["api_key_env"]
    key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(f"環境変数 {env_var} が設定されていません")
    return key


def _convert_tools_to_openai(tools: list[dict]) -> list[dict]:
    """Anthropic形式のツール定義をOpenAI形式に変換"""
    openai_tools = []
    for tool in tools:
        schema = tool.get("input_schema", {"type": "object", "properties": {}})
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": schema,
            },
        })
    return openai_tools


def _call_anthropic(
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
) -> dict:
    """Anthropic API を呼び出し、統一フォーマットで返す"""
    import anthropic

    client = anthropic.Anthropic(api_key=_get_api_key("anthropic"))
    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }
    if tools:
        kwargs["tools"] = tools
    response = client.messages.create(**kwargs)

    # 統一フォーマットに変換
    result = {"text": None, "tool_calls": [], "stop_reason": response.stop_reason}
    for block in response.content:
        if block.type == "text":
            result["text"] = block.text
        elif block.type == "tool_use":
            result["tool_calls"].append({
                "id": block.id,
                "name": block.name,
                "arguments": block.input,
            })
    return result


def _call_openai(
    model: str,
    system: str,
    messages: list[dict],
    tools: list[dict],
    max_tokens: int,
) -> dict:
    """OpenAI API を呼び出し、統一フォーマットで返す"""
    from openai import OpenAI

    client = OpenAI(api_key=_get_api_key("openai"))
    oai_messages = [{"role": "system", "content": system}]
    for msg in messages:
        oai_messages.append(_convert_message_to_openai(msg))

    kwargs = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = _convert_tools_to_openai(tools)

    response = client.chat.completions.create(**kwargs)
    choice = response.choices[0]

    result = {"text": None, "tool_calls": [], "stop_reason": choice.finish_reason}
    if choice.message.content:
        result["text"] = choice.message.content
    if choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            result["tool_calls"].append({
                "id": tc.id,
                "name": tc.function.name,
                "arguments": json.loads(tc.function.arguments),
            })
    return result


def _convert_message_to_openai(msg: dict) -> dict:
    """Anthropic形式のメッセージをOpenAI形式に変換"""
    role = msg["role"]
    content = msg.get("content", "")

    # テキストメッセージ
    if isinstance(content, str):
        return {"role": role, "content": content}

    # tool_use結果（Anthropic形式 → OpenAI形式）
    if isinstance(content, list):
        # assistant の tool_use ブロック
        if role == "assistant":
            text_parts = []
            tool_calls = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        text_parts.append(block["text"])
                    elif block.get("type") == "tool_use":
                        tool_calls.append({
                            "id": block["id"],
                            "type": "function",
                            "function": {
                                "name": block["name"],
                                "arguments": json.dumps(block["input"], ensure_ascii=False),
                            },
                        })
            result = {"role": "assistant", "content": "\n".join(text_parts) if text_parts else None}
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        # user の tool_result ブロック
        if role == "user":
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    return {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block.get("content", ""),
                    }

    return {"role": role, "content": str(content)}


def chat(
    system: str,
    messages: list[dict],
    tools: Optional[list[dict]] = None,
    model_override: Optional[dict] = None,
) -> dict:
    """
    統一チャットインターフェース。
    Anthropic/OpenAI を自動切替。フォールバック付き。

    Returns:
        {"text": str|None, "tool_calls": list, "stop_reason": str}
    """
    config = _load_config()
    model_info = model_override or config["default_model"]
    fallback_order = config.get("fallback_order", [])
    max_tokens = model_info.get("max_tokens", config["default_model"].get("max_tokens", 1024))

    # まずデフォルトモデルで試行
    try:
        return _dispatch(model_info["provider"], model_info["model"], system, messages, tools or [], max_tokens)
    except Exception as e:
        logger.warning(f"デフォルトモデル {model_info['model']} 失敗: {e}")

    # フォールバック
    for fallback in fallback_order:
        if fallback["provider"] == model_info["provider"] and fallback["model"] == model_info["model"]:
            continue
        try:
            logger.info(f"フォールバック: {fallback['model']}")
            return _dispatch(fallback["provider"], fallback["model"], system, messages, tools or [], max_tokens)
        except Exception as e:
            logger.warning(f"フォールバック {fallback['model']} も失敗: {e}")

    raise RuntimeError("すべてのモデルが失敗しました")


def _dispatch(provider: str, model: str, system: str, messages: list, tools: list, max_tokens: int) -> dict:
    if provider == "anthropic":
        return _call_anthropic(model, system, messages, tools, max_tokens)
    elif provider == "openai":
        return _call_openai(model, system, messages, tools, max_tokens)
    else:
        raise ValueError(f"未対応のプロバイダー: {provider}")
