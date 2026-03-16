"""
handler_runner.py — ツール定義に従って既存ハンドラを実行する汎用ランナー

Coordinator から呼ばれる。ツールごとの実行方法を
tool_registry.json の handler_type に従って振り分ける。

handler_type:
  - subprocess:         外部Pythonスクリプトを実行
  - function:           local_agent.py から渡されたコールバック関数を実行
  - file_read:          ファイルを読み込んで返す
  - action:             権限と送信先に応じて実送信または提案を返す
  - api_call:           agent_registry.json の preferred_agent → interface.config に従って外部API呼び出し
  - workflow_endpoint:  ワークフローエンドポイント（Mac Mini Orchestrator等）にHTTP POST
  - mcp:                MCP プロトコル呼び出し（将来用）
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

import requests

from clone_registry import (
    get_agent_config,
    get_agent_transfer,
    get_shell_policy,
    map_category_to_audience,
    normalize_person_lookup,
    resolve_human_entity,
)


_RUNTIME_DATA_DIR = Path.home() / "agents" / "data"
_CONTACT_STATE_PATH = _RUNTIME_DATA_DIR / "contact_state.json"
_DISCLOSURE_EXCEPTION_PATH = _RUNTIME_DATA_DIR / "disclosure_exceptions.json"
_OUTBOUND_AUDIT_LOG_PATH = _RUNTIME_DATA_DIR / "outbound_message_audit.jsonl"
_MESSAGE_LEVELS = {"Lv0", "Lv1", "Lv2", "Lv3"}
_IMPORTANT_MESSAGE_RULES = (
    ("謝罪や訂正が入る", ("申し訳", "すみません", "お詫び", "訂正", "誤り")),
    ("相手の感情に強く影響する", ("不快", "困らせ", "残念", "クレーム", "怒")),
    ("約束や期限を確定させる", ("期限", "締切", "納期", "本日中", "明日", "来週", "確定", "決定", "約束")),
    ("金額や条件を確定させる", ("円", "万円", "請求", "見積", "契約", "条件", "返金")),
    ("本人の評価や意思として受け取られる", ("方針", "承認", "許可", "判断", "進めます", "やります")),
)
_ROUTINE_MESSAGE_HINTS = (
    "了解",
    "承知",
    "確認しました",
    "共有ありがとう",
    "共有ありがとうございます",
    "受け取りました",
    "進捗共有",
    "リマインド",
    "日程調整",
)
_DISCLOSURE_SCOPE_ALIASES = {
    "operation": "operation",
    "操作手順": "operation",
    "judgment": "judgment",
    "判断基準": "judgment",
    "background": "background",
    "背景": "background",
    "背景事情": "background",
    "strategy": "strategy",
    "数値戦略": "strategy",
    "数値・戦略": "strategy",
    "strategy_need_to_know": "strategy_need_to_know",
    "必要戦略": "strategy_need_to_know",
    "実行に必要な戦略": "strategy_need_to_know",
    "situation": "situation",
    "状況": "situation",
    "required_conditions": "required_conditions",
    "必要条件": "required_conditions",
    "people_insight": "people_insight",
    "対人見立て": "people_insight",
    "hypothesis": "hypothesis",
    "仮説": "hypothesis",
    "未確定仮説": "hypothesis",
}
_BASE_DISCLOSURE_SCOPES = {
    "僕": {"all"},
    "上司": {"operation", "judgment", "background", "strategy"},
    "並列": {"operation", "judgment", "background", "strategy"},
    "直下": {"operation", "judgment", "background", "strategy_need_to_know"},
    "外部": {"situation", "required_conditions"},
}
_DISCLOSURE_GUARD_KEYWORDS = {
    "strategy": ("kpi", "ltv", "roas", "cpa", "売上", "利益", "利益率", "購入率", "オプトイン率", "方針", "戦略"),
    "people_insight": ("強め", "逆効果", "この人は", "言い方", "伝え方", "刺さる", "動く", "人柄"),
    "hypothesis": ("仮説", "推定", "かもしれ", "おそらく", "未確定"),
    "secret": ("パスワード", "token", "secret", "client_secret", "認証情報", "個人情報", "契約条件"),
}


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

        # subprocess 用の環境変数を構築（config.json から APIキーを注入）
        self._subprocess_env = self._build_subprocess_env()
        self._runtime_api_config = self._load_runtime_api_config()

    def _load_profiles(self) -> dict:
        """legacy profiles.json を読み込む（後方互換用）"""
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

    def _load_runtime_api_config(self) -> dict:
        config_path = Path(__file__).parent / "config.json"
        payload = {}
        if config_path.exists():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
            except Exception:
                payload = {}

        return {
            "server_url": os.environ.get("LINE_BOT_SERVER_URL") or payload.get("server_url", ""),
            "agent_token": (
                os.environ.get("AGENT_TOKEN")
                or os.environ.get("LOCAL_AGENT_TOKEN")
                or payload.get("agent_token", "")
            ),
        }

    def _get_agent_config(self, agent_name: str) -> dict:
        """agent_registry からエージェントの interface.config を取得する"""
        return get_agent_config(agent_name)

    def _get_agent_transfer(self, agent_name: str) -> dict:
        """agent_registry からエージェントの transfer 情報を取得する"""
        return get_agent_transfer(agent_name)

    def _load_contact_state(self) -> dict:
        if not _CONTACT_STATE_PATH.exists():
            return {}
        try:
            data = json.loads(_CONTACT_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _save_contact_state(self, contact_state: dict):
        try:
            _RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _CONTACT_STATE_PATH.write_text(
                json.dumps(contact_state, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _load_disclosure_exception_log(self) -> list:
        if not _DISCLOSURE_EXCEPTION_PATH.exists():
            return []
        try:
            data = json.loads(_DISCLOSURE_EXCEPTION_PATH.read_text(encoding="utf-8"))
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def _save_disclosure_exception_log(self, entries: list):
        try:
            _RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
            _DISCLOSURE_EXCEPTION_PATH.write_text(
                json.dumps(entries, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass

    def _append_outbound_audit_log(self, payload: dict):
        try:
            _RUNTIME_DATA_DIR.mkdir(parents=True, exist_ok=True)
            with _OUTBOUND_AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _normalize_contact_state_entry(self, entry) -> dict:
        if isinstance(entry, str):
            entry = {"last_contact": entry}
        if not isinstance(entry, dict):
            entry = {}
        normalized = dict(entry)
        conversations = normalized.get("conversations", [])
        normalized["conversations"] = conversations if isinstance(conversations, list) else []

        send_authority = normalized.get("send_authority", {})
        if not isinstance(send_authority, dict):
            send_authority = {}
        level = str(send_authority.get("level", "")).strip()
        if level in _MESSAGE_LEVELS:
            send_authority["level"] = level
        else:
            send_authority.pop("level", None)
        normalized["send_authority"] = send_authority

        delivery_targets = normalized.get("delivery_targets", {})
        if not isinstance(delivery_targets, dict):
            delivery_targets = {}
        normalized["delivery_targets"] = {
            "line": {
                "user_id": str((delivery_targets.get("line", {}) or {}).get("user_id", "") or ""),
                "group_id": str((delivery_targets.get("line", {}) or {}).get("group_id", "") or ""),
                "last_seen_at": str((delivery_targets.get("line", {}) or {}).get("last_seen_at", "") or ""),
            },
            "chatwork": {
                "room_id": str((delivery_targets.get("chatwork", {}) or {}).get("room_id", "") or ""),
                "account_id": str((delivery_targets.get("chatwork", {}) or {}).get("account_id", "") or ""),
                "last_seen_at": str((delivery_targets.get("chatwork", {}) or {}).get("last_seen_at", "") or ""),
            },
            "email": {
                "address": str((delivery_targets.get("email", {}) or {}).get("address", "") or ""),
                "last_seen_at": str((delivery_targets.get("email", {}) or {}).get("last_seen_at", "") or ""),
            },
        }
        return normalized

    def _merge_delivery_targets(self, base_targets: dict, incoming_targets: dict) -> dict:
        merged = self._normalize_contact_state_entry({"delivery_targets": base_targets}).get("delivery_targets", {})
        source = incoming_targets if isinstance(incoming_targets, dict) else {}
        for channel in ("line", "chatwork", "email"):
            incoming_channel = source.get(channel, {})
            if not isinstance(incoming_channel, dict):
                continue
            merged_channel = dict(merged.get(channel, {}) or {})
            for key, value in incoming_channel.items():
                if value:
                    merged_channel[key] = str(value)
            merged[channel] = merged_channel
        return merged

    def _normalize_disclosure_subject(self, subject: str) -> str:
        return str(subject or "").strip().replace(" ", "").replace("　", "").lower()

    def _parse_disclosure_scopes(self, raw_scopes) -> list[str]:
        values = []
        if isinstance(raw_scopes, str):
            normalized_text = raw_scopes.replace("、", ",").replace("，", ",").replace("・", ",").replace("/", ",")
            values = [item.strip() for item in normalized_text.split(",")]
        elif isinstance(raw_scopes, list):
            values = [str(item).strip() for item in raw_scopes]

        scopes: list[str] = []
        for value in values:
            if not value:
                continue
            scope = _DISCLOSURE_SCOPE_ALIASES.get(value, _DISCLOSURE_SCOPE_ALIASES.get(value.lower(), ""))
            if scope and scope not in scopes:
                scopes.append(scope)
        return scopes

    def _infer_disclosure_risks(self, text: str) -> list[str]:
        content = str(text or "").strip().lower()
        risks: list[str] = []
        if not content:
            return risks
        for scope, keywords in _DISCLOSURE_GUARD_KEYWORDS.items():
            if any(keyword in content for keyword in keywords):
                risks.append(scope)
        return risks

    def _find_matching_disclosure_exception(self, recipient: str, subject: str, requested_scopes: list[str]) -> dict:
        normalized_recipient = normalize_person_lookup(recipient)
        canonical_name, _ = resolve_human_entity(recipient)
        normalized_canonical = normalize_person_lookup(canonical_name or "")
        normalized_subject = self._normalize_disclosure_subject(subject)
        requested_scope_set = set(requested_scopes)
        if not normalized_subject or not requested_scope_set:
            return {}

        entries = self._load_disclosure_exception_log()
        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            entry_recipient = normalize_person_lookup(entry.get("recipient", ""))
            if entry_recipient not in {normalized_recipient, normalized_canonical}:
                continue
            if self._normalize_disclosure_subject(entry.get("subject", "")) != normalized_subject:
                continue
            if entry.get("approval_type") == "今回限り" and entry.get("consumed_at"):
                continue

            entry_scope_tokens = entry.get("scope_tokens", [])
            if not isinstance(entry_scope_tokens, list) or not entry_scope_tokens:
                entry_scope_tokens = self._parse_disclosure_scopes(entry.get("allowed_scope", ""))
            if not requested_scope_set.issubset(set(entry_scope_tokens)):
                continue
            return entry
        return {}

    def _consume_disclosure_exception(self, exception_id: str):
        if not exception_id:
            return
        entries = self._load_disclosure_exception_log()
        changed = False
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("exception_id", "")) != str(exception_id):
                continue
            if entry.get("approval_type") != "今回限り" or entry.get("consumed_at"):
                return
            entry["consumed_at"] = datetime.now().isoformat()
            changed = True
            break
        if changed:
            self._save_disclosure_exception_log(entries)

    def _bootstrap_delivery_targets(self, recipient: str, policy: dict, requested_channel: str = "") -> dict:
        delivery_targets = policy.get("delivery_targets", {}) if isinstance(policy, dict) else {}
        need_line = requested_channel == "line" and not (delivery_targets.get("line", {}) or {}).get("user_id")
        need_chatwork = requested_channel == "chatwork" and not (delivery_targets.get("chatwork", {}) or {}).get("room_id")
        need_any = not requested_channel and not any(
            [
                (delivery_targets.get("line", {}) or {}).get("user_id"),
                (delivery_targets.get("chatwork", {}) or {}).get("room_id"),
                (delivery_targets.get("email", {}) or {}).get("address"),
            ]
        )
        if not (need_line or need_chatwork or need_any):
            return policy

        server_url = str(self._runtime_api_config.get("server_url", "") or "").rstrip("/")
        agent_token = str(self._runtime_api_config.get("agent_token", "") or "")
        if not server_url:
            return policy

        headers = {}
        if agent_token:
            headers["Authorization"] = f"Bearer {agent_token}"

        try:
            resp = requests.get(
                f"{server_url}/api/contact-route",
                headers=headers,
                params={"recipient": recipient},
                timeout=15,
            )
            data = resp.json()
        except Exception:
            return policy

        if not resp.ok or not data.get("success"):
            return policy

        bootstrapped_targets = data.get("delivery_targets", {})
        merged_targets = self._merge_delivery_targets(delivery_targets, bootstrapped_targets)
        updated_policy = dict(policy)
        updated_policy["delivery_targets"] = merged_targets

        canonical_name = str(updated_policy.get("canonical_name", recipient) or recipient)
        contact_state = self._load_contact_state()
        entry = self._normalize_contact_state_entry(contact_state.get(canonical_name))
        entry["delivery_targets"] = merged_targets
        contact_state[canonical_name] = entry
        self._save_contact_state(contact_state)
        return updated_policy

    def _resolve_recipient_policy(self, recipient: str, shell_name: str = "line_secretary") -> dict:
        shell_policy = get_shell_policy(shell_name)
        message_policy = shell_policy.get("message_policy", {}) if isinstance(shell_policy, dict) else {}
        default_level = str(message_policy.get("default_level", "Lv0") or "Lv0")
        canonical_name, entity = resolve_human_entity(recipient)
        category = str(entity.get("category", "")) if entity else ""
        audience = str(entity.get("base_audience", "")) if entity else ""
        if not audience:
            audience = map_category_to_audience(category)

        contact_state = self._load_contact_state()
        entry = None
        if canonical_name and canonical_name in contact_state:
            entry = contact_state.get(canonical_name)
        elif recipient in contact_state:
            entry = contact_state.get(recipient)
        normalized_entry = self._normalize_contact_state_entry(entry)
        send_authority = normalized_entry.get("send_authority", {})
        delivery_targets = normalized_entry.get("delivery_targets", {})
        if isinstance(entity, dict):
            entity_email = str(entity.get("email", "") or "").strip()
            if entity_email and not (delivery_targets.get("email", {}) or {}).get("address"):
                delivery_targets = dict(delivery_targets)
                email_target = dict(delivery_targets.get("email", {}) or {})
                email_target["address"] = entity_email
                delivery_targets["email"] = email_target
        level = str(send_authority.get("level", "")).strip() or default_level
        level_source = "個別設定" if send_authority.get("level") else "既定値"

        return {
            "recipient": recipient,
            "canonical_name": canonical_name or recipient,
            "known_recipient": bool(entity),
            "category": category,
            "audience": audience or "外部",
            "level": level,
            "level_source": level_source,
            "shell_message_policy": message_policy,
            "delivery_targets": delivery_targets,
        }

    def _choose_outbound_channel(self, delivery_targets: dict) -> str:
        candidates = []
        line_target = delivery_targets.get("line", {}) if isinstance(delivery_targets, dict) else {}
        if line_target.get("user_id"):
            candidates.append(("line", str(line_target.get("last_seen_at", "") or "")))
        chatwork_target = delivery_targets.get("chatwork", {}) if isinstance(delivery_targets, dict) else {}
        if chatwork_target.get("room_id"):
            candidates.append(("chatwork", str(chatwork_target.get("last_seen_at", "") or "")))
        email_target = delivery_targets.get("email", {}) if isinstance(delivery_targets, dict) else {}
        if email_target.get("address"):
            candidates.append(("email", str(email_target.get("last_seen_at", "") or "")))
        if not candidates:
            return ""
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates[0][0]

    def _dispatch_outbound_message(self, channel: str, content: str, policy: dict) -> tuple[str, str]:
        server_url = str(self._runtime_api_config.get("server_url", "") or "").rstrip("/")
        agent_token = str(self._runtime_api_config.get("agent_token", "") or "")
        delivery_targets = policy.get("delivery_targets", {}) if isinstance(policy, dict) else {}

        payload = {
            "channel": channel,
            "content": content,
            "recipient": policy.get("canonical_name", policy.get("recipient", "")),
        }

        if channel == "line":
            line_target = delivery_targets.get("line", {}) if isinstance(delivery_targets, dict) else {}
            line_user_id = str(line_target.get("user_id", "") or "").strip()
            if not line_user_id:
                return "deferred", "LINE の user_id が未記録です"
            payload["line_user_id"] = line_user_id
        elif channel == "chatwork":
            chatwork_target = delivery_targets.get("chatwork", {}) if isinstance(delivery_targets, dict) else {}
            room_id = str(chatwork_target.get("room_id", "") or "").strip()
            if not room_id:
                return "deferred", "Chatwork の room_id が未記録です"
            payload["chatwork_room_id"] = room_id
            account_id = str(chatwork_target.get("account_id", "") or "").strip()
            if account_id:
                payload["chatwork_account_id"] = account_id
        elif channel == "email":
            email_target = delivery_targets.get("email", {}) if isinstance(delivery_targets, dict) else {}
            email_address = str(email_target.get("address", "") or "").strip()
            if not email_address:
                return "deferred", "email アドレスが未記録です"
            payload["email_to"] = email_address
            payload["mail_subject"] = str(policy.get("mail_subject", "") or "").strip()
            payload["mail_account"] = str(policy.get("mail_account", "") or "kohara").strip()
        else:
            return "deferred", f"未対応の送信チャネルです: {channel}"

        if not server_url:
            return "failed", "LINE_BOT_SERVER_URL が未設定です"

        headers = {"Content-Type": "application/json"}
        if agent_token:
            headers["Authorization"] = f"Bearer {agent_token}"

        try:
            resp = requests.post(
                f"{server_url}/api/outbound-message",
                headers=headers,
                json=payload,
                timeout=30,
            )
            data = resp.json()
        except requests.Timeout:
            return "failed", "送信 API がタイムアウトしました"
        except requests.ConnectionError:
            return "failed", "送信 API に接続できません"
        except ValueError:
            return "failed", "送信 API のレスポンスが不正です"
        except Exception as e:
            return "failed", f"送信 API 呼び出しでエラー: {e}"

        if resp.ok and data.get("success"):
            sent_id = str(data.get("sent_id", "") or "")
            return "sent", f"送信済み{f'（ID: {sent_id}）' if sent_id else ''}"

        return "failed", str(data.get("error", f"HTTP {resp.status_code}"))

    def _is_important_message(self, text: str, audience: str) -> tuple[bool, list[str]]:
        content = str(text or "").strip()
        reasons: list[str] = []
        if audience == "外部" and content:
            reasons.append("対外連絡は対外的な印象や関係性に影響する")
        for label, keywords in _IMPORTANT_MESSAGE_RULES:
            if any(keyword in content for keyword in keywords):
                reasons.append(label)
        unique_reasons: list[str] = []
        for reason in reasons:
            if reason not in unique_reasons:
                unique_reasons.append(reason)
        return bool(unique_reasons), unique_reasons[:3]

    def _is_routine_message(self, text: str, urgency: str = "normal") -> bool:
        content = str(text or "").strip()
        if not content or urgency == "high":
            return False
        if len(content) > 120 or content.count("\n") >= 3:
            return False
        return any(keyword in content for keyword in _ROUTINE_MESSAGE_HINTS)

    def _evaluate_send_policy(
        self,
        recipient: str,
        message_text: str,
        *,
        urgency: str = "normal",
        shell_name: str = "line_secretary",
        disclosure_subject: str = "",
        requested_scopes=None,
    ) -> dict:
        policy = self._resolve_recipient_policy(recipient, shell_name=shell_name)
        important, important_reasons = self._is_important_message(message_text, policy["audience"])
        routine_candidate = self._is_routine_message(message_text, urgency=urgency)
        message_policy = policy.get("shell_message_policy", {})
        auto_reply_to_superiors = bool(message_policy.get("auto_reply_to_superiors", True))
        requested_scope_tokens = self._parse_disclosure_scopes(requested_scopes)
        base_scopes = _BASE_DISCLOSURE_SCOPES.get(policy["audience"], _BASE_DISCLOSURE_SCOPES["外部"])
        extra_requested_scopes = [
            scope for scope in requested_scope_tokens
            if "all" not in base_scopes and scope not in base_scopes
        ]
        inferred_risks = self._infer_disclosure_risks(message_text)
        uncovered_inferred_risks = [
            scope for scope in inferred_risks
            if scope not in requested_scope_tokens
            and ("all" not in base_scopes and scope not in base_scopes)
        ]
        matched_exception = {}

        approval_required = True
        rule_notes: list[str] = []
        if policy["audience"] == "上司" and not auto_reply_to_superiors:
            approval_required = True
            rule_notes.append("上司への自動返信は無効")
        elif policy["level"] == "Lv0":
            approval_required = True
            rule_notes.append("この相手は下書きのみ")
        elif policy["level"] == "Lv1":
            approval_required = True
            rule_notes.append("この相手は毎回承認後に送信")
        elif policy["level"] == "Lv2":
            approval_required = important or not routine_candidate
            rule_notes.append("定型連絡だけ自動送信可")
        elif policy["level"] == "Lv3":
            approval_required = important
            rule_notes.append("通常連絡まで自動送信可。重要連絡は承認必要")

        if not policy["known_recipient"]:
            suffix = "未登録のため外部扱い"
            rule_notes.append(suffix)

        if extra_requested_scopes:
            if not disclosure_subject:
                approval_required = True
                rule_notes.append("追加開示には disclosure_subject が必要")
            else:
                matched_exception = self._find_matching_disclosure_exception(
                    policy["canonical_name"],
                    disclosure_subject,
                    extra_requested_scopes,
                )
                if matched_exception:
                    rule_notes.append(
                        f"例外承認あり: {matched_exception.get('approval_type', '今回限り')} / {matched_exception.get('subject', disclosure_subject)}"
                    )
                else:
                    approval_required = True
                    rule_notes.append(
                        f"追加開示は例外承認待ち: {disclosure_subject} / {', '.join(extra_requested_scopes)}"
                    )
        if uncovered_inferred_risks:
            approval_required = True
            rule_notes.append(
                f"内容から追加開示候補を検知: {', '.join(uncovered_inferred_risks)}"
            )

        policy.update(
            {
                "important": important,
                "important_reasons": important_reasons,
                "routine_candidate": routine_candidate,
                "approval_required": approval_required,
                "rule_note": " / ".join(rule_notes),
                "disclosure_subject": disclosure_subject,
                "requested_scopes": requested_scope_tokens,
                "extra_requested_scopes": extra_requested_scopes,
                "inferred_disclosure_risks": inferred_risks,
                "matched_disclosure_exception": matched_exception,
                "disclosure_exception_consumable": bool(
                    matched_exception
                    and matched_exception.get("approval_type") == "今回限り"
                    and not matched_exception.get("consumed_at")
                ),
            }
        )
        return policy

    def _format_policy_block(self, policy: dict) -> str:
        recipient_label = policy["canonical_name"]
        if policy["recipient"] != recipient_label:
            recipient_label = f"{policy['recipient']} -> {recipient_label}"

        if policy["category"]:
            audience_line = f"{policy['audience']}（{policy['category']}）"
        else:
            audience_line = f"{policy['audience']}（未登録）"

        lines = [
            f"宛先解決: {recipient_label}",
            f"相手区分: {audience_line}",
            f"送信権限: {policy['level']}（{policy['level_source']}）",
        ]
        available_channels = []
        delivery_targets = policy.get("delivery_targets", {}) if isinstance(policy, dict) else {}
        if (delivery_targets.get("line", {}) or {}).get("user_id"):
            available_channels.append("line")
        if (delivery_targets.get("chatwork", {}) or {}).get("room_id"):
            available_channels.append("chatwork")
        if (delivery_targets.get("email", {}) or {}).get("address"):
            available_channels.append("email")
        lines.append(
            f"送信先情報: {', '.join(available_channels)}"
            if available_channels
            else "送信先情報: 未記録"
        )
        if policy.get("requested_scopes"):
            lines.append(f"開示スコープ: {', '.join(policy['requested_scopes'])}")
        if policy.get("inferred_disclosure_risks"):
            lines.append(f"検知リスク: {', '.join(policy['inferred_disclosure_risks'])}")
        if policy.get("disclosure_subject"):
            lines.append(f"開示対象: {policy['disclosure_subject']}")
        if policy["important"]:
            lines.append("重要連絡判定: 該当")
            lines.append(f"判定理由: {' / '.join(policy['important_reasons'])}")
        elif policy["routine_candidate"]:
            lines.append("連絡種別: 定型連絡候補")
        lines.append(
            "現行ルール: 承認後に送信"
            if policy["approval_required"]
            else "現行ルール: 承認なし送信可の範囲"
        )
        if policy["rule_note"]:
            lines.append(f"補足: {policy['rule_note']}")
        return "\n".join(lines)

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

        elif tool_name == "analyze_content":
            url = arguments.get("url", "")
            if url:
                cmd.append("image")
                cmd.append(url)
            instruction = arguments.get("instruction", "")
            if instruction:
                cmd.append(instruction)

        elif tool_name == "save_video_learning":
            cmd.append("save")
            cmd.append(json.dumps(arguments, ensure_ascii=False))

        elif tool_name == "update_video_learning":
            cmd.append("update_pending")
            cmd.append(json.dumps(arguments, ensure_ascii=False))

        elif tool_name == "confirm_video_learning":
            cmd.append("confirm")

        elif tool_name == "addness_ops":
            action = arguments.get("action", "")
            if action == "current_member":
                cmd.extend(["current-member", "--headless"])
            elif action == "search_goals":
                query = arguments.get("query", "")
                if not query:
                    return "query が必要です"
                cmd.extend(["search-goals", "--query", query, "--headless"])
                limit = arguments.get("limit")
                if limit:
                    cmd.extend(["--limit", str(limit)])
            elif action == "get_goal":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                cmd.extend(["get-goal", "--goal-id", goal_id, "--headless"])
            elif action == "create_goal":
                parent_id = arguments.get("parent_id", "")
                title = arguments.get("title", "")
                if not parent_id or not title:
                    return "parent_id と title が必要です"
                cmd.extend([
                    "create-goal",
                    "--parent-id",
                    parent_id,
                    "--title",
                    title,
                    "--headless",
                ])
                due_date = arguments.get("due_date", "")
                if due_date:
                    cmd.extend(["--due-date", due_date])
                description = arguments.get("description")
                if description is not None:
                    cmd.extend(["--description", str(description)])
                status = arguments.get("status", "")
                if status:
                    cmd.extend(["--status", status])
            elif action == "update_goal_title":
                goal_id = arguments.get("goal_id", "")
                title = arguments.get("title", "")
                if not goal_id or not title:
                    return "goal_id と title が必要です"
                cmd.extend([
                    "update-goal-title",
                    "--goal-id",
                    goal_id,
                    "--title",
                    title,
                    "--headless",
                ])
            elif action == "update_goal_status":
                goal_id = arguments.get("goal_id", "")
                status = arguments.get("status", "")
                if not goal_id or not status:
                    return "goal_id と status が必要です"
                cmd.extend([
                    "update-goal-status",
                    "--goal-id",
                    goal_id,
                    "--status",
                    status,
                    "--headless",
                ])
            elif action == "update_goal_due_date":
                goal_id = arguments.get("goal_id", "")
                due_date = arguments.get("due_date", "")
                if not goal_id or not due_date:
                    return "goal_id と due_date が必要です"
                cmd.extend([
                    "update-goal-due-date",
                    "--goal-id",
                    goal_id,
                    "--due-date",
                    due_date,
                    "--headless",
                ])
            elif action == "update_goal_description":
                goal_id = arguments.get("goal_id", "")
                description = arguments.get("description")
                if not goal_id or description is None:
                    return "goal_id と description が必要です"
                cmd.extend([
                    "update-goal-description",
                    "--goal-id",
                    goal_id,
                    "--description",
                    str(description),
                    "--headless",
                ])
            elif action == "list_comments":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                cmd.extend(["list-comments", "--goal-id", goal_id, "--headless"])
                if arguments.get("resolved"):
                    cmd.append("--resolved")
                limit = arguments.get("limit")
                if limit:
                    cmd.extend(["--limit", str(limit)])
                offset = arguments.get("offset")
                if offset:
                    cmd.extend(["--offset", str(offset)])
                sort = arguments.get("sort", "")
                if sort:
                    cmd.extend(["--sort", sort])
            elif action == "post_comment":
                text = arguments.get("text", "")
                if not text:
                    return "text が必要です"
                cmd.extend(["post-comment", "--text", text, "--headless"])
                goal_id = arguments.get("goal_id", "")
                goal_url = arguments.get("goal_url", "")
                if goal_url:
                    cmd.extend(["--goal-url", goal_url])
                elif goal_id:
                    cmd.extend(["--goal-id", goal_id])
            elif action == "resolve_comment":
                comment_id = arguments.get("comment_id", "")
                if not comment_id:
                    return "comment_id が必要です"
                cmd.extend(["resolve-comment", "--comment-id", comment_id, "--headless"])
            elif action == "delete_comment":
                comment_id = arguments.get("comment_id", "")
                if not comment_id:
                    return "comment_id が必要です"
                if not arguments.get("confirm"):
                    return "delete_comment には confirm=true が必要です"
                cmd.extend(["delete-comment", "--comment-id", comment_id, "--yes", "--headless"])
            elif action == "reparent_goal":
                goal_id = arguments.get("goal_id", "")
                new_parent_id = arguments.get("new_parent_id", "")
                if not goal_id or not new_parent_id:
                    return "goal_id と new_parent_id が必要です"
                cmd.extend([
                    "reparent-goal",
                    "--goal-id",
                    goal_id,
                    "--new-parent-id",
                    new_parent_id,
                    "--headless",
                ])
            elif action == "archive_goal":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                cmd.extend(["archive-goal", "--goal-id", goal_id, "--headless"])
            elif action == "delete_goal":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                if not arguments.get("confirm"):
                    return "delete_goal には confirm=true が必要です"
                expected_title = arguments.get("expected_title", "")
                if not expected_title:
                    return "delete_goal には expected_title が必要です"
                cmd.extend(["delete-goal", "--goal-id", goal_id, "--expected-title", expected_title, "--yes", "--headless"])
                expected_parent_id = arguments.get("expected_parent_id", "")
                if expected_parent_id:
                    cmd.extend(["--expected-parent-id", expected_parent_id])
                if arguments.get("allow_non_test_goal"):
                    cmd.append("--allow-non-test-goal")
            elif action == "list_ai_threads":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                cmd.extend(["list-ai-threads", "--goal-id", goal_id, "--headless"])
                limit = arguments.get("limit")
                if limit:
                    cmd.extend(["--limit", str(limit)])
                offset = arguments.get("offset")
                if offset:
                    cmd.extend(["--offset", str(offset)])
            elif action == "get_ai_messages":
                thread_id = arguments.get("thread_id", "")
                if not thread_id:
                    return "thread_id が必要です"
                cmd.extend(["get-ai-messages", "--thread-id", thread_id, "--headless"])
                limit = arguments.get("limit")
                if limit:
                    cmd.extend(["--limit", str(limit)])
            elif action == "start_ai_session":
                goal_id = arguments.get("goal_id", "")
                if not goal_id:
                    return "goal_id が必要です"
                cmd.extend(["start-ai-session", "--goal-id", goal_id, "--headless"])
                purpose = arguments.get("purpose", "")
                if purpose:
                    cmd.extend(["--purpose", purpose])
                title = arguments.get("title", "")
                if title:
                    cmd.extend(["--title", title])
            elif action == "send_ai_message":
                thread_id = arguments.get("thread_id", "")
                message = arguments.get("message", "")
                if not thread_id or not message:
                    return "thread_id と message が必要です"
                cmd.extend([
                    "send-ai-message",
                    "--thread-id",
                    thread_id,
                    "--message",
                    message,
                    "--headless",
                ])
                goal_id = arguments.get("goal_id", "")
                if goal_id:
                    cmd.extend(["--goal-id", goal_id])
                model = arguments.get("model", "")
                if model:
                    cmd.extend(["--model", model])
                mode = arguments.get("mode", "")
                if mode:
                    cmd.extend(["--mode", mode])
                timeout_seconds = arguments.get("timeout_seconds")
                if timeout_seconds:
                    cmd.extend(["--timeout-seconds", str(timeout_seconds)])
            elif action == "consult_goal":
                cmd.extend(["consult", "--headless"])
                goal_id = arguments.get("goal_id", "")
                goal_url = arguments.get("goal_url", "")
                if goal_url:
                    cmd.extend(["--goal-url", goal_url])
                elif goal_id:
                    cmd.extend(["--goal-id", goal_id])
                thread_id = arguments.get("thread_id", "")
                if thread_id:
                    cmd.extend(["--thread-id", thread_id])
                purpose = arguments.get("purpose", "")
                if purpose:
                    cmd.extend(["--purpose", purpose])
                message = arguments.get("message", "")
                instruction = arguments.get("instruction", "")
                if message:
                    cmd.extend(["--message", message])
                elif instruction:
                    cmd.extend(["--instruction", instruction])
                title = arguments.get("title", "")
                if title:
                    cmd.extend(["--title", title])
                model = arguments.get("model", "")
                if model:
                    cmd.extend(["--model", model])
                mode = arguments.get("mode", "")
                if mode:
                    cmd.extend(["--mode", mode])
                timeout_seconds = arguments.get("timeout_seconds")
                if timeout_seconds:
                    cmd.extend(["--timeout-seconds", str(timeout_seconds)])
            elif action == "activity_summary":
                cmd.extend(["activity-summary", "--headless"])
                member_id = arguments.get("member_id", "")
                if member_id:
                    cmd.extend(["--member-id", member_id])
                pages = arguments.get("pages")
                if pages:
                    cmd.extend(["--pages", str(pages)])
                page_size = arguments.get("page_size")
                if page_size:
                    cmd.extend(["--page-size", str(page_size)])
                if arguments.get("save_report"):
                    cmd.append("--save-report")
            elif action == "smoke_test":
                cmd.extend(["smoke-test", "--headless"])
                parent_id = arguments.get("parent_id", "")
                if parent_id:
                    cmd.extend(["--parent-id", parent_id])
                timeout_seconds = arguments.get("timeout_seconds")
                if timeout_seconds:
                    cmd.extend(["--timeout-seconds", str(timeout_seconds)])
                if arguments.get("keep_artifacts"):
                    cmd.append("--keep-artifacts")
            else:
                return (
                    "addness_ops の action が不正です。"
                    " current_member / search_goals / get_goal / create_goal /"
                    " update_goal_title / update_goal_status / update_goal_due_date /"
                    " update_goal_description / list_comments / post_comment /"
                    " resolve_comment / delete_comment / reparent_goal / archive_goal /"
                    " delete_goal / list_ai_threads / get_ai_messages /"
                    " start_ai_session / send_ai_message / consult_goal /"
                    " activity_summary / smoke_test を使ってください"
                )

        # video_reader と Addness 操作は時間がかかることがある
        timeout = 600 if tool_name == "video_reader" else 300 if tool_name == "addness_ops" else 120

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
    # action: 権限と送信先に応じて実送信または提案を返す
    # ------------------------------------------------------------------
    def _run_action(self, tool_def: dict, arguments: dict) -> str:
        tool_name = tool_def["name"]

        if tool_name == "send_message":
            recipient = arguments.get("recipient", "不明")
            channel = arguments.get("channel", "line")
            content = arguments.get("content", "")
            policy = self._evaluate_send_policy(
                recipient,
                content,
                disclosure_subject=str(arguments.get("disclosure_subject", "") or "").strip(),
                requested_scopes=arguments.get("disclosure_scope"),
            )
            policy = self._bootstrap_delivery_targets(recipient, policy, requested_channel=str(channel))
            policy["mail_subject"] = str(arguments.get("subject", "") or "").strip()
            policy["mail_account"] = str(arguments.get("mail_account", "") or "kohara").strip()
            policy_block = self._format_policy_block(policy)
            if policy["approval_required"]:
                final_note = "※この連絡は甲原さんの承認後に送信してください"
                self._append_outbound_audit_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "recipient": policy["recipient"],
                        "canonical_name": policy["canonical_name"],
                        "audience": policy["audience"],
                        "level": policy["level"],
                        "channel": channel,
                        "result": "proposal",
                        "approval_required": True,
                        "disclosure_subject": policy.get("disclosure_subject", ""),
                        "requested_scopes": policy.get("requested_scopes", []),
                        "rule_note": policy.get("rule_note", ""),
                    }
                )
                return (
                    f"【送信提案】\n"
                    f"{policy_block}\n"
                    f"送信チャネル: {channel}\n"
                    f"内容:\n{content}\n\n"
                    f"{final_note}"
                )

            send_status, send_note = self._dispatch_outbound_message(channel, content, policy)
            if send_status == "sent":
                if policy.get("disclosure_exception_consumable"):
                    self._consume_disclosure_exception(
                        str((policy.get("matched_disclosure_exception") or {}).get("exception_id", "") or "")
                    )
                self._append_outbound_audit_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "recipient": policy["recipient"],
                        "canonical_name": policy["canonical_name"],
                        "audience": policy["audience"],
                        "level": policy["level"],
                        "channel": channel,
                        "result": "sent",
                        "approval_required": False,
                        "disclosure_subject": policy.get("disclosure_subject", ""),
                        "requested_scopes": policy.get("requested_scopes", []),
                        "rule_note": policy.get("rule_note", ""),
                        "exception_id": str((policy.get("matched_disclosure_exception") or {}).get("exception_id", "") or ""),
                    }
                )
                return (
                    f"【送信完了】\n"
                    f"{policy_block}\n"
                    f"送信チャネル: {channel}\n"
                    f"内容:\n{content}\n\n"
                    f"送信結果: {send_note}"
                )
            self._append_outbound_audit_log(
                {
                    "timestamp": datetime.now().isoformat(),
                    "tool": tool_name,
                    "recipient": policy["recipient"],
                    "canonical_name": policy["canonical_name"],
                    "audience": policy["audience"],
                    "level": policy["level"],
                    "channel": channel,
                    "result": send_status,
                    "approval_required": False,
                    "disclosure_subject": policy.get("disclosure_subject", ""),
                    "requested_scopes": policy.get("requested_scopes", []),
                    "rule_note": policy.get("rule_note", ""),
                    "dispatch_note": send_note,
                }
            )
            return (
                f"【送信提案】\n"
                f"{policy_block}\n"
                f"送信チャネル: {channel}\n"
                f"内容:\n{content}\n\n"
                f"※承認なし送信の条件は満たしていますが、自動送信できませんでした\n"
                f"理由: {send_note}"
            )

        elif tool_name == "ask_human":
            recipient = arguments.get("recipient", "不明")
            message = arguments.get("message", "")
            urgency = arguments.get("urgency", "normal")
            channel = arguments.get("channel", "")
            policy = self._evaluate_send_policy(
                recipient,
                message,
                urgency=urgency,
                disclosure_subject=str(arguments.get("disclosure_subject", "") or "").strip(),
                requested_scopes=arguments.get("disclosure_scope"),
            )
            policy = self._bootstrap_delivery_targets(recipient, policy, requested_channel=str(channel or ""))
            policy["mail_subject"] = str(arguments.get("subject", "") or "").strip()
            policy["mail_account"] = str(arguments.get("mail_account", "") or "kohara").strip()
            policy_block = self._format_policy_block(policy)
            selected_channel = str(channel or self._choose_outbound_channel(policy.get("delivery_targets", {})) or "")
            channel_line = f"送信チャネル: {selected_channel}\n" if selected_channel else ""
            if policy["approval_required"]:
                final_note = "※この依頼は甲原さんの承認後に送信してください"
                self._append_outbound_audit_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "recipient": policy["recipient"],
                        "canonical_name": policy["canonical_name"],
                        "audience": policy["audience"],
                        "level": policy["level"],
                        "channel": selected_channel or channel,
                        "result": "proposal",
                        "approval_required": True,
                        "disclosure_subject": policy.get("disclosure_subject", ""),
                        "requested_scopes": policy.get("requested_scopes", []),
                        "rule_note": policy.get("rule_note", ""),
                    }
                )
                return (
                    f"【依頼提案】\n"
                    f"{policy_block}\n"
                    f"緊急度: {urgency}\n"
                    f"{channel_line}"
                    f"内容:\n{message}\n\n"
                    f"{final_note}"
                )

            if not selected_channel:
                self._append_outbound_audit_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "recipient": policy["recipient"],
                        "canonical_name": policy["canonical_name"],
                        "audience": policy["audience"],
                        "level": policy["level"],
                        "channel": "",
                        "result": "deferred",
                        "approval_required": False,
                        "disclosure_subject": policy.get("disclosure_subject", ""),
                        "requested_scopes": policy.get("requested_scopes", []),
                        "rule_note": "利用可能な送信経路が未記録",
                    }
                )
                return (
                    f"【依頼提案】\n"
                    f"{policy_block}\n"
                    f"緊急度: {urgency}\n"
                    f"内容:\n{message}\n\n"
                    f"※承認なし送信の条件は満たしていますが、利用可能な送信経路が未記録です"
                )

            send_status, send_note = self._dispatch_outbound_message(selected_channel, message, policy)
            if send_status == "sent":
                if policy.get("disclosure_exception_consumable"):
                    self._consume_disclosure_exception(
                        str((policy.get("matched_disclosure_exception") or {}).get("exception_id", "") or "")
                    )
                self._append_outbound_audit_log(
                    {
                        "timestamp": datetime.now().isoformat(),
                        "tool": tool_name,
                        "recipient": policy["recipient"],
                        "canonical_name": policy["canonical_name"],
                        "audience": policy["audience"],
                        "level": policy["level"],
                        "channel": selected_channel,
                        "result": "sent",
                        "approval_required": False,
                        "disclosure_subject": policy.get("disclosure_subject", ""),
                        "requested_scopes": policy.get("requested_scopes", []),
                        "rule_note": policy.get("rule_note", ""),
                        "exception_id": str((policy.get("matched_disclosure_exception") or {}).get("exception_id", "") or ""),
                    }
                )
                return (
                    f"【依頼送信完了】\n"
                    f"{policy_block}\n"
                    f"緊急度: {urgency}\n"
                    f"送信チャネル: {selected_channel}\n"
                    f"内容:\n{message}\n\n"
                    f"送信結果: {send_note}"
                )
            self._append_outbound_audit_log(
                {
                    "timestamp": datetime.now().isoformat(),
                    "tool": tool_name,
                    "recipient": policy["recipient"],
                    "canonical_name": policy["canonical_name"],
                    "audience": policy["audience"],
                    "level": policy["level"],
                    "channel": selected_channel,
                    "result": send_status,
                    "approval_required": False,
                    "disclosure_subject": policy.get("disclosure_subject", ""),
                    "requested_scopes": policy.get("requested_scopes", []),
                    "rule_note": policy.get("rule_note", ""),
                    "dispatch_note": send_note,
                }
            )
            return (
                f"【依頼提案】\n"
                f"{policy_block}\n"
                f"緊急度: {urgency}\n"
                f"{channel_line}"
                f"内容:\n{message}\n\n"
                f"※承認なし送信の条件は満たしていますが、自動送信できませんでした\n"
                f"理由: {send_note}"
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
    # api_call: agent_registry の preferred_agent に基づく外部API呼び出し
    # ------------------------------------------------------------------
    def _run_api_call(self, tool_def: dict, arguments: dict) -> str:
        agent_name = tool_def.get("preferred_agent") or ""
        tool_name = tool_def.get("name", "")
        if not agent_name:
            return (
                f"ツール '{tool_name}' の担当 AI が未設定です。"
                f"agent_registry.json にエージェントを登録し、"
                f"tool_registry.json の preferred_agent を設定してください"
            )

        config = self._get_agent_config(agent_name)
        if not config:
            return (
                f"エージェント '{agent_name}' の接続設定が agent_registry.json に見つかりません。"
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
                f"agent_registry.json の interface.config.endpoint を設定してください"
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
            f"agent_registry.json に MCP 接続情報を設定後、利用可能になります"
        )
