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
USAGE_PATH = Path(__file__).resolve().parent.parent / "data" / "api_usage.json"

# モデル別の料金（$/1M tokens）
_PRICING = {
    "gpt-5.4-pro": {"input": 30.0, "output": 180.0},
    "gpt-5.4": {"input": 2.5, "output": 20.0},
    "gpt-4.1": {"input": 1.0, "output": 4.0},
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4},
    "o3": {"input": 10.0, "output": 40.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-haiku-4-5-20251001": {"input": 0.8, "output": 4.0},
}
_LOW_BALANCE_THRESHOLD = 5.0  # $5以下で通知


def _load_config() -> dict:
    """設定ファイルを読み込む（毎回読み直して即時反映）"""
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_config(config: dict):
    """設定ファイルを書き込む"""
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def _load_usage() -> dict:
    """使用量データを読み込む"""
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if USAGE_PATH.exists():
        try:
            return json.loads(USAGE_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"initial_balance": 19.92, "total_spent": 0.0, "daily": {}, "last_notified": ""}


def _save_usage(data: dict):
    """使用量データを保存"""
    USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USAGE_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _track_usage(model: str, input_tokens: int, output_tokens: int):
    """API呼び出しのコストを記録し、残高が低ければ通知"""
    pricing = _PRICING.get(model, {"input": 5.0, "output": 20.0})
    cost = (input_tokens * pricing["input"] + output_tokens * pricing["output"]) / 1_000_000

    usage = _load_usage()
    usage["total_spent"] = usage.get("total_spent", 0.0) + cost

    today = time.strftime("%Y-%m-%d")
    daily = usage.get("daily", {})
    daily[today] = daily.get(today, 0.0) + cost
    usage["daily"] = daily

    # 古い日次データを削除（30日分だけ保持）
    sorted_days = sorted(daily.keys())
    if len(sorted_days) > 30:
        for old_day in sorted_days[:-30]:
            del daily[old_day]

    _save_usage(usage)

    # 残高チェック
    estimated_balance = usage.get("initial_balance", 20.0) - usage["total_spent"]
    if estimated_balance <= _LOW_BALANCE_THRESHOLD:
        _notify_low_balance(usage, estimated_balance)

    logger.info(f"API使用: {model} in={input_tokens} out={output_tokens} cost=${cost:.4f} balance≈${estimated_balance:.2f}")


def _notify_low_balance(usage: dict, balance: float):
    """残高が低いときにLINE通知"""
    # 重複通知抑制（12時間以内）
    last = usage.get("last_notified", "")
    if last:
        try:
            elapsed = time.time() - time.mktime(time.strptime(last, "%Y-%m-%d %H:%M"))
            if elapsed < 43200:
                return
        except (ValueError, TypeError):
            pass

    # 日次平均を計算して残り日数を推定
    daily = usage.get("daily", {})
    recent_days = sorted(daily.keys())[-7:]  # 直近7日
    if recent_days:
        avg_daily = sum(daily[d] for d in recent_days) / len(recent_days)
        days_left = balance / avg_daily if avg_daily > 0 else 999
        pace_info = f"\n直近の消費ペース: 1日あたり約${avg_daily:.2f}（残り約{days_left:.0f}日）"
    else:
        pace_info = ""

    try:
        # LINE通知（send_line_notifyを動的にインポート）
        import subprocess, sys
        notify_script = Path(__file__).resolve().parent.parent / "mac_mini" / "agent_orchestrator" / "notifier.py"
        msg = (
            f"OpenAI APIの残高が少なくなっています。\n"
            f"推定残高: ${balance:.2f}{pace_info}\n"
            f"チャージ: https://platform.openai.com/settings/organization/billing"
        )
        subprocess.Popen(
            [sys.executable, "-c",
             f"import sys; sys.path.insert(0, '{notify_script.parent}');"
             f"from notifier import send_line_notify; send_line_notify('''{msg}''')"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        usage["last_notified"] = time.strftime("%Y-%m-%d %H:%M")
        _save_usage(usage)
        logger.warning(f"OpenAI残高低下通知: ${balance:.2f}")
    except Exception as e:
        logger.error(f"残高通知エラー: {e}")


def set_initial_balance(balance: float):
    """残高をリセット（チャージ後に呼ぶ）"""
    usage = _load_usage()
    usage["initial_balance"] = balance
    usage["total_spent"] = 0.0
    usage["last_notified"] = ""
    _save_usage(usage)
    logger.info(f"残高を${balance:.2f}にリセットしました")


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

    # 使用量トラッキング
    if hasattr(response, "usage") and response.usage:
        _track_usage(model, response.usage.input_tokens, response.usage.output_tokens)

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
        converted = _convert_message_to_openai(msg)
        # tool_result の場合は複数メッセージに展開される
        if isinstance(converted, list):
            oai_messages.extend(converted)
        else:
            oai_messages.append(converted)

    kwargs = {
        "model": model,
        "messages": oai_messages,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = _convert_tools_to_openai(tools)

    response = client.chat.completions.create(**kwargs)

    # 使用量トラッキング
    if hasattr(response, "usage") and response.usage:
        _track_usage(model, response.usage.prompt_tokens, response.usage.completion_tokens)

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

        # user の tool_result ブロック → OpenAIでは各resultが個別のtoolメッセージ
        if role == "user":
            tool_msgs = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    tool_msgs.append({
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": block.get("content", ""),
                    })
            if tool_msgs:
                return tool_msgs  # リストとして返す（呼び出し元でextend）

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
