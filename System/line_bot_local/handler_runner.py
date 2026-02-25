"""
handler_runner.py — ツール定義に従って既存ハンドラを実行する汎用ランナー

Coordinator から呼ばれる。ツールごとの実行方法を
tool_registry.json の handler_type に従って振り分ける。

handler_type:
  - subprocess:         外部Pythonスクリプトを実行
  - function:           local_agent.py から渡されたコールバック関数を実行
  - file_read:          ファイルを読み込んで返す
  - action:             L3+ 確認が必要な操作。実行せず提案テキストを返す
  - api_call:           profiles.json の preferred_agent → interface.config に従って外部API呼び出し
  - workflow_endpoint:  ワークフローエンドポイント（Mac Mini Orchestrator等）にHTTP POST
  - mcp:                MCP プロトコル呼び出し（将来用）
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import requests


class HandlerRunner:
    def __init__(self, system_dir: Path, project_root: Path,
                 function_handlers: dict = None):
        """
        system_dir:        System/ ディレクトリのパス
        project_root:      プロジェクトルート（Master/ が直下にある）
        function_handlers:  {tool_name: callable(arguments) -> str} のマッピング
                           local_agent.py から渡される
        """
        self.system_dir = system_dir
        self.project_root = project_root
        self.function_handlers = function_handlers or {}

        # ツールレジストリ読み込み
        registry_path = Path(__file__).parent / "tool_registry.json"
        with open(registry_path, encoding="utf-8") as f:
            self._registry = json.load(f)
        self._tool_map = {t["name"]: t for t in self._registry["tools"]}

        # profiles.json 読み込み（api_call / workflow_endpoint で使用）
        self._profiles = self._load_profiles()

    def _load_profiles(self) -> dict:
        """profiles.json を読み込む"""
        profiles_path = self.project_root / "Master" / "people" / "profiles.json"
        if not profiles_path.exists():
            return {}
        try:
            return json.loads(profiles_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _get_agent_config(self, agent_name: str) -> dict:
        """profiles.json からエージェントの interface.config を取得する"""
        profile = self._profiles.get(agent_name, {})
        return profile.get("latest", {}).get("interface", {}).get("config", {})

    def run(self, tool_name: str, arguments: dict) -> str:
        """ツールを実行して結果テキストを返す"""
        tool_def = self._tool_map.get(tool_name)
        if not tool_def:
            return f"ツール '{tool_name}' は登録されていません"

        handler_type = tool_def.get("handler_type", "")

        try:
            if handler_type == "subprocess":
                return self._run_subprocess(tool_def, arguments)
            elif handler_type == "function":
                return self._run_function(tool_def, arguments)
            elif handler_type == "file_read":
                return self._run_file_read(tool_def, arguments)
            elif handler_type == "action":
                return self._run_action(tool_def, arguments)
            elif handler_type == "api_call":
                return self._run_api_call(tool_def, arguments)
            elif handler_type == "workflow_endpoint":
                return self._run_workflow(tool_def, arguments)
            elif handler_type == "mcp":
                return self._run_mcp(tool_def, arguments)
            else:
                return f"未対応の handler_type: {handler_type}"
        except Exception as e:
            return f"ツール '{tool_name}' の実行中にエラー: {e}"

    # ------------------------------------------------------------------
    # subprocess: 外部Pythonスクリプト実行
    # ------------------------------------------------------------------
    def _run_subprocess(self, tool_def: dict, arguments: dict) -> str:
        handler_path = tool_def.get("handler_path", "")
        script = self.system_dir / handler_path
        if not script.exists():
            return f"スクリプトが見つかりません: {handler_path}"

        tool_name = tool_def["name"]

        # ツールごとにコマンドライン引数を構築
        cmd = [sys.executable, str(script)]

        if tool_name == "calendar":
            action = arguments.get("action", "list")
            cmd.append(action)
            days = arguments.get("days")
            if days and action == "list":
                cmd.append(str(days))

        elif tool_name == "mail":
            action = arguments.get("action", "check")
            cmd.append(action)
            account = arguments.get("account", "personal")
            cmd.append(account)

        elif tool_name == "people":
            query = arguments.get("query", "")
            cmd.append(query)

        elif tool_name == "sheets":
            action = arguments.get("action", "read")
            cmd.append(action)
            sheet_id = arguments.get("sheet_id", "")
            if sheet_id:
                cmd.append(sheet_id)
            range_ = arguments.get("range", "")
            if range_:
                cmd.append(range_)

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(self.system_dir),
        )

        output = result.stdout.strip()
        if result.returncode != 0:
            error = result.stderr.strip()
            if output:
                return f"{output}\n\n（警告: {error}）" if error else output
            return f"実行エラー: {error or '不明なエラー'}"

        return output if output else "（結果なし）"

    # ------------------------------------------------------------------
    # function: local_agent.py のコールバック関数を実行
    # ------------------------------------------------------------------
    def _run_function(self, tool_def: dict, arguments: dict) -> str:
        func_name = tool_def.get("handler_function", "")
        handler = self.function_handlers.get(func_name)
        if not handler:
            return f"関数ハンドラ '{func_name}' が未登録です"

        result = handler(arguments)
        if isinstance(result, tuple):
            # (success, text) 形式の場合
            return result[1] if len(result) > 1 else str(result[0])
        return str(result)

    # ------------------------------------------------------------------
    # file_read: ファイル読み込み
    # ------------------------------------------------------------------
    def _run_file_read(self, tool_def: dict, arguments: dict) -> str:
        handler_path = tool_def.get("handler_path", "")

        # Master/ 配下を探す
        file_path = self.project_root / "Master" / "addness" / handler_path
        if not file_path.exists():
            # System/ 配下も探す
            file_path = self.system_dir / handler_path
        if not file_path.exists():
            return f"ファイルが見つかりません: {handler_path}"

        try:
            content = file_path.read_text(encoding="utf-8")
            # 先頭 4000 文字に制限（トークン節約）
            if len(content) > 4000:
                content = content[:4000] + "\n\n（...以下省略。全 {} 文字）".format(len(content))
            return content
        except Exception as e:
            return f"ファイル読み込みエラー: {e}"

    # ------------------------------------------------------------------
    # action: L3+ 確認が必要。実行せず提案テキストを返す
    # ------------------------------------------------------------------
    def _run_action(self, tool_def: dict, arguments: dict) -> str:
        tool_name = tool_def["name"]

        if tool_name == "send_message":
            recipient = arguments.get("recipient", "不明")
            channel = arguments.get("channel", "line")
            content = arguments.get("content", "")
            return (
                f"【送信提案】\n"
                f"宛先: {recipient}（{channel}）\n"
                f"内容:\n{content}\n\n"
                f"※送信するには甲原さんの承認が必要です"
            )

        elif tool_name == "ask_human":
            recipient = arguments.get("recipient", "不明")
            message = arguments.get("message", "")
            urgency = arguments.get("urgency", "normal")
            return (
                f"【依頼提案】\n"
                f"宛先: {recipient}（緊急度: {urgency}）\n"
                f"内容:\n{message}\n\n"
                f"※送信するには甲原さんの承認が必要です"
            )

        return f"アクション '{tool_name}' は確認が必要です。引数: {json.dumps(arguments, ensure_ascii=False)}"

    # ------------------------------------------------------------------
    # api_call: profiles.json の preferred_agent に基づく外部API呼び出し
    # ------------------------------------------------------------------
    def _run_api_call(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent", "")
        if not agent_name:
            return "preferred_agent が未設定です"

        config = self._get_agent_config(agent_name)
        if not config:
            return f"エージェント '{agent_name}' の設定が profiles.json に見つかりません"

        provider = config.get("provider", "")
        api_key_env = config.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""

        if api_key_env and not api_key:
            return f"APIキーが未設定です（環境変数: {api_key_env}）。設定後に利用可能になります"

        if provider == "perplexity":
            return self._call_perplexity(config, api_key, arguments)
        else:
            # Lubert / 動画AI / 将来の汎用プロバイダー
            return self._call_generic_api(config, api_key, agent_name, arguments)

    def _call_perplexity(self, config: dict, api_key: str, arguments: dict) -> str:
        """Perplexity API（OpenAI互換）でWeb検索を実行"""
        endpoint = config.get("endpoint", "https://api.perplexity.ai/chat/completions")
        query = arguments.get("query", arguments.get("prompt", ""))
        if not query:
            return "検索クエリが指定されていません"

        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.1-sonar-large-128k-online",
                "messages": [{"role": "user", "content": query}],
            },
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content if content else json.dumps(data, ensure_ascii=False)[:2000]

    def _call_generic_api(self, config: dict, api_key: str,
                          agent_name: str, arguments: dict) -> str:
        """汎用API呼び出し。endpoint に POST してレスポンスを返す"""
        endpoint = config.get("endpoint", "")
        if not endpoint:
            return (
                f"エージェント '{agent_name}' の API endpoint が未設定です。"
                f"profiles.json の interface.config.endpoint を設定してください"
            )

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        resp = requests.post(
            endpoint,
            headers=headers,
            json=arguments,
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()

        # よくあるレスポンス形式を試す
        if isinstance(data, dict):
            for key in ("result", "output", "data", "content"):
                if key in data:
                    return str(data[key])[:2000]
            if "choices" in data:
                return data["choices"][0].get("message", {}).get("content", str(data))[:2000]
        return json.dumps(data, ensure_ascii=False)[:2000]

    # ------------------------------------------------------------------
    # workflow_endpoint: ワークフローエンドポイントにHTTP POST
    # ------------------------------------------------------------------
    def _run_workflow(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent", "")
        config = self._get_agent_config(agent_name) if agent_name else {}
        endpoint = config.get("endpoint") or tool_def.get("endpoint", "")

        if not endpoint:
            return "ワークフローエンドポイントが未設定です"

        try:
            resp = requests.post(
                endpoint,
                json=arguments,
                timeout=180,
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("result", data.get("output", ""))
            if result:
                return str(result)[:2000]
            return json.dumps(data, ensure_ascii=False)[:2000]
        except requests.Timeout:
            return f"ワークフロー '{agent_name}' がタイムアウトしました（180秒）"
        except requests.ConnectionError:
            return f"ワークフロー '{agent_name}' に接続できません（endpoint: {endpoint}）"

    # ------------------------------------------------------------------
    # mcp: MCP プロトコル呼び出し（将来用）
    # ------------------------------------------------------------------
    def _run_mcp(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent", "")
        return (
            f"MCP プロトコル（{agent_name or 'unknown'}）は現在準備中です。\n"
            f"profiles.json に MCP 接続情報を設定後、利用可能になります"
        )
