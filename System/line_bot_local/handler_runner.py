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
        self._tool_map = {t["name"]: t for t in self._registry.get("tools", [])}

        # profiles.json 読み込み（api_call / workflow_endpoint で使用）
        self._profiles = self._load_profiles()

        # subprocess 用の環境変数を構築（config.json から APIキーを注入）
        self._subprocess_env = self._build_subprocess_env()

    def _load_profiles(self) -> dict:
        """profiles.json を読み込む"""
        profiles_path = self.project_root / "Master" / "people" / "profiles.json"
        if not profiles_path.exists():
            return {}
        try:
            return json.loads(profiles_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _build_subprocess_env(self) -> dict:
        """subprocess 実行用の環境変数を構築。config.json のキーを注入する"""
        env = os.environ.copy()
        config_path = Path(__file__).parent / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                # config.json の APIキーを環境変数に注入（未設定の場合のみ）
                if cfg.get("anthropic_api_key") and not env.get("ANTHROPIC_API_KEY"):
                    env["ANTHROPIC_API_KEY"] = cfg["anthropic_api_key"]
            except Exception:
                pass
        return env

    def _get_agent_config(self, agent_name: str) -> dict:
        """profiles.json からエージェントの interface.config を取得する"""
        profile = self._profiles.get(agent_name, {})
        return profile.get("latest", {}).get("interface", {}).get("config", {})

    def _get_agent_transfer(self, agent_name: str) -> dict:
        """profiles.json からエージェントの transfer 情報を取得する"""
        profile = self._profiles.get(agent_name, {})
        return profile.get("latest", {}).get("transfer", {})

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
            elif handler_type == "claude_search":
                return self._run_claude_search(arguments)
            elif handler_type == "api_call":
                return self._run_api_call(tool_def, arguments)
            elif handler_type == "workflow_endpoint":
                return self._run_workflow(tool_def, arguments)
            elif handler_type == "mcp":
                return self._run_mcp(tool_def, arguments)
            else:
                return f"未対応の handler_type です: {handler_type}"
        except requests.Timeout:
            return f"ツール '{tool_name}' がタイムアウトしました。時間をおいて再度お試しください"
        except requests.ConnectionError:
            return f"ツール '{tool_name}' の接続先に到達できません。ネットワーク状態を確認してください"
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "不明"
            return f"ツール '{tool_name}' の API 呼び出しでエラーが発生しました（HTTP {status}）"
        except subprocess.TimeoutExpired:
            return f"ツール '{tool_name}' の実行がタイムアウトしました（120秒）"
        except Exception as e:
            err_type = type(e).__name__
            return f"ツール '{tool_name}' の実行中にエラーが発生しました: {err_type}: {e}"

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
            # calendar_manager.py list は日付(YYYY-MM-DD)を受け取る。未指定なら30日分
            days = arguments.get("days")
            if days and action == "list":
                from datetime import datetime, timedelta
                target = (datetime.now() + timedelta(days=int(days) - 1)).strftime("%Y-%m-%d")
                cmd.append(target)

        elif tool_name == "mail":
            action = arguments.get("action", "check")
            # tool_registry の "check" → mail_manager.py の "status" にマッピング
            mail_cmd = "status" if action == "check" else action
            cmd.append(mail_cmd)
            account = arguments.get("account", "personal")
            cmd.extend(["--account", account])

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

        elif tool_name == "video_reader":
            url = arguments.get("url", "")
            if url:
                cmd.append(url)

        elif tool_name == "save_video_learning":
            cmd.append("save")
            cmd.append(json.dumps(arguments, ensure_ascii=False))

        # video_reader は動画DL+フレーム抽出で時間がかかる
        timeout = 600 if tool_name == "video_reader" else 120

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(self.system_dir),
            env=self._subprocess_env,
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

        try:
            result = handler(arguments)
        except Exception as e:
            return f"関数 '{func_name}' の実行中にエラーが発生しました: {e}"

        if isinstance(result, tuple):
            # (success, text) 形式の場合
            return result[1] if len(result) > 1 else str(result[0])
        if result is None:
            return "（結果なし）"
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
    # claude_search: Claude API の web_search ツールで検索
    # ------------------------------------------------------------------
    def _run_claude_search(self, arguments: dict) -> str:
        """Claude API の web_search ツールを使ってWeb検索する"""
        import anthropic

        query = arguments.get("query", "")
        if not query:
            return "検索クエリが指定されていません"

        # APIキー取得（環境変数 → config.json）
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            config_path = Path(__file__).parent / "config.json"
            if config_path.exists():
                try:
                    cfg = json.loads(config_path.read_text(encoding="utf-8"))
                    api_key = cfg.get("anthropic_api_key", "")
                except Exception:
                    pass
        if not api_key:
            return "ANTHROPIC_API_KEY が未設定です"

        try:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=1024,
                tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
                messages=[{"role": "user", "content": query}],
            )
        except anthropic.APIError as e:
            return f"Claude Web検索でエラーが発生しました: {e}"
        except Exception as e:
            return f"Web検索中に予期しないエラーが発生しました: {e}"

        # レスポンスからテキスト部分を抽出
        results = []
        for block in response.content:
            if hasattr(block, "text"):
                results.append(block.text)
        return "\n".join(results) if results else "検索結果が取得できませんでした"

    # ------------------------------------------------------------------
    # api_call: profiles.json の preferred_agent に基づく外部API呼び出し
    # ------------------------------------------------------------------
    def _run_api_call(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent") or ""
        tool_name = tool_def.get("name", "")
        if not agent_name:
            return (
                f"ツール '{tool_name}' の担当 AI が未設定です。"
                f"profiles.json にエージェントを登録し、"
                f"tool_registry.json の preferred_agent を設定してください"
            )

        config = self._get_agent_config(agent_name)
        if not config:
            return (
                f"エージェント '{agent_name}' の接続設定が profiles.json に見つかりません。"
                f"interface.config を確認してください"
            )

        provider = config.get("provider", "")
        api_key_env = config.get("api_key_env", "")
        api_key = os.environ.get(api_key_env, "") if api_key_env else ""

        if api_key_env and not api_key:
            return (
                f"'{agent_name}' の APIキーが未設定です"
                f"（環境変数 {api_key_env} を設定してください）"
            )

        if provider == "perplexity":
            return self._call_perplexity(config, api_key, arguments)
        else:
            return self._call_generic_api(config, api_key, agent_name, arguments)

    def _call_perplexity(self, config: dict, api_key: str, arguments: dict) -> str:
        """Perplexity API（OpenAI互換）でWeb検索を実行"""
        endpoint = config.get("endpoint", "https://api.perplexity.ai/chat/completions")
        model = config.get("model", "llama-3.1-sonar-large-128k-online")
        query = arguments.get("query", arguments.get("prompt", ""))
        if not query:
            return "検索クエリが指定されていません"

        try:
            resp = requests.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": query}],
                },
                timeout=60,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return "Perplexity API がタイムアウトしました（60秒）。時間をおいて再度お試しください"
        except requests.ConnectionError:
            return "Perplexity API に接続できません。ネットワーク状態を確認してください"
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "不明"
            if status == 401:
                return "Perplexity API の認証に失敗しました。APIキーを確認してください"
            elif status == 429:
                return "Perplexity API のレート制限に達しました。しばらくお待ちください"
            return f"Perplexity API でエラーが発生しました（HTTP {status}）"

        try:
            data = resp.json()
        except ValueError:
            return "Perplexity API のレスポンスが不正です"

        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content if content else "（検索結果が空でした）"

    def _call_generic_api(self, config: dict, api_key: str,
                          agent_name: str, arguments: dict) -> str:
        """汎用API呼び出し。endpoint に POST してレスポンスを返す"""
        endpoint = config.get("endpoint", "")
        if not endpoint:
            return (
                f"エージェント '{agent_name}' の API エンドポイントが未設定です。"
                f"profiles.json の interface.config.endpoint を設定してください"
            )

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            resp = requests.post(
                endpoint,
                headers=headers,
                json=arguments,
                timeout=120,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return f"'{agent_name}' の API がタイムアウトしました（120秒）"
        except requests.ConnectionError:
            return f"'{agent_name}' の API に接続できません（{endpoint}）"
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "不明"
            if status == 401:
                return f"'{agent_name}' の API 認証に失敗しました。APIキーを確認してください"
            elif status == 429:
                return f"'{agent_name}' の API レート制限に達しました。しばらくお待ちください"
            return f"'{agent_name}' の API でエラーが発生しました（HTTP {status}）"

        try:
            data = resp.json()
        except ValueError:
            return f"'{agent_name}' の API レスポンスが不正です"

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
    # transfer_status によるコードレベルの制御も行う
    # ------------------------------------------------------------------
    def _run_workflow(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent", "")
        config = self._get_agent_config(agent_name) if agent_name else {}
        endpoint = config.get("endpoint") or tool_def.get("endpoint", "")

        if not endpoint:
            return f"ワークフロー '{agent_name or tool_def.get('name', '')}' のエンドポイントが未設定です"

        # --- transfer_status によるコードレベル制御 ---
        if agent_name:
            transfer = self._get_agent_transfer(agent_name)
            t_status = transfer.get("transfer_status", "")
            t_target = transfer.get("transferable_to", "")

            if t_status and t_target:
                # Phase 3/4: AI は実行しない。人間に委任する
                if "Phase 3" in t_status or "Phase 4" in t_status:
                    return (
                        f"ワークフロー '{agent_name}' は現在 {t_status} です。\n"
                        f"{t_target} さんに直接依頼してください（ask_human ツールを使用）"
                    )
                # Phase 2: 実行するが、人間確認が必要な旨を付記
                phase2_note = ""
                if "Phase 2" in t_status:
                    phase2_note = f"\n\n※ このワークフローは移譲中（{t_status}）です。結果を {t_target} さんにも確認してもらってください"

        try:
            resp = requests.post(
                endpoint,
                json=arguments,
                timeout=180,
            )
            resp.raise_for_status()
        except requests.Timeout:
            return f"ワークフロー '{agent_name}' がタイムアウトしました（180秒）"
        except requests.ConnectionError:
            return f"ワークフロー '{agent_name}' に接続できません。Mac Mini の稼働状態を確認してください"
        except requests.HTTPError as e:
            status = e.response.status_code if e.response is not None else "不明"
            return f"ワークフロー '{agent_name}' でエラーが発生しました（HTTP {status}）"

        try:
            data = resp.json()
        except ValueError:
            return f"ワークフロー '{agent_name}' のレスポンスが不正です"

        result = data.get("result", data.get("output", ""))
        result_text = str(result)[:2000] if result else json.dumps(data, ensure_ascii=False)[:2000]

        # Phase 2 の場合は確認依頼を付記
        if agent_name:
            transfer = self._get_agent_transfer(agent_name)
            t_status = transfer.get("transfer_status", "")
            t_target = transfer.get("transferable_to", "")
            if "Phase 2" in t_status and t_target:
                result_text += f"\n\n※ 移譲中（{t_status}）: {t_target} さんにも結果を確認してもらってください"

        return result_text

    # ------------------------------------------------------------------
    # mcp: MCP プロトコル呼び出し（将来用）
    # ------------------------------------------------------------------
    def _run_mcp(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent", "")
        return (
            f"MCP ツール（{agent_name or '未指定'}）は現在準備中です。\n"
            f"profiles.json に MCP 接続情報を設定後、利用可能になります"
        )
