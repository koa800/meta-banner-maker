import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent.parent
SYSTEM_DIR = ROOT_DIR / "System"
LINE_BOT_LOCAL_DIR = SYSTEM_DIR / "line_bot_local"
LINE_BOT_APP_PATH = SYSTEM_DIR / "line_bot" / "app.py"
HANDLER_RUNNER_PATH = LINE_BOT_LOCAL_DIR / "handler_runner.py"
LOCAL_AGENT_PATH = LINE_BOT_LOCAL_DIR / "local_agent.py"

for path in (SYSTEM_DIR, LINE_BOT_LOCAL_DIR):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def load_module(module_name: str, file_path: Path):
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class RuntimePolicyTest(unittest.TestCase):
    def test_extra_disclosure_requires_exception(self):
        handler_runner = load_module("handler_runner_test_case_1", HANDLER_RUNNER_PATH)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handler_runner._RUNTIME_DATA_DIR = tmp_path
            handler_runner._CONTACT_STATE_PATH = tmp_path / "contact_state.json"
            handler_runner._DISCLOSURE_EXCEPTION_PATH = tmp_path / "disclosure_exceptions.json"
            handler_runner._CONTACT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "外部先": {
                            "send_authority": {"level": "Lv3"},
                            "delivery_targets": {"email": {"address": "outside@example.com"}},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            handler_runner.resolve_human_entity = lambda name: (
                "外部先",
                {"name": "外部先", "category": "外部パートナー", "email": "outside@example.com"},
            )

            runner = handler_runner.HandlerRunner(system_dir=SYSTEM_DIR, project_root=ROOT_DIR)
            policy = runner._evaluate_send_policy(
                "外部先",
                "この数値も共有します",
                disclosure_subject="KPI共有",
                requested_scopes=["strategy"],
            )

            self.assertTrue(policy["approval_required"])
            self.assertIn("例外承認待ち", policy["rule_note"])

    def test_inferred_disclosure_risk_requires_approval_without_declared_scope(self):
        handler_runner = load_module("handler_runner_test_case_inferred_risk", HANDLER_RUNNER_PATH)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handler_runner._RUNTIME_DATA_DIR = tmp_path
            handler_runner._CONTACT_STATE_PATH = tmp_path / "contact_state.json"
            handler_runner._DISCLOSURE_EXCEPTION_PATH = tmp_path / "disclosure_exceptions.json"
            handler_runner._OUTBOUND_AUDIT_LOG_PATH = tmp_path / "outbound_message_audit.jsonl"
            handler_runner._CONTACT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "外部先": {
                            "send_authority": {"level": "Lv3"},
                            "delivery_targets": {"email": {"address": "outside@example.com"}},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            handler_runner.resolve_human_entity = lambda name: (
                "外部先",
                {"name": "外部先", "category": "外部パートナー", "email": "outside@example.com"},
            )

            runner = handler_runner.HandlerRunner(system_dir=SYSTEM_DIR, project_root=ROOT_DIR)
            policy = runner._evaluate_send_policy(
                "外部先",
                "今月のKPIと売上の方針も共有します",
            )

            self.assertTrue(policy["approval_required"])
            self.assertIn("内容から追加開示候補を検知", policy["rule_note"])
            self.assertIn("strategy", policy["inferred_disclosure_risks"])

    def test_one_time_disclosure_exception_is_consumed_after_send(self):
        handler_runner = load_module("handler_runner_test_case_2", HANDLER_RUNNER_PATH)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handler_runner._RUNTIME_DATA_DIR = tmp_path
            handler_runner._CONTACT_STATE_PATH = tmp_path / "contact_state.json"
            handler_runner._DISCLOSURE_EXCEPTION_PATH = tmp_path / "disclosure_exceptions.json"
            handler_runner._CONTACT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "直下先": {
                            "send_authority": {"level": "Lv3"},
                            "delivery_targets": {"email": {"address": "member@example.com"}},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            handler_runner._DISCLOSURE_EXCEPTION_PATH.write_text(
                json.dumps(
                    [
                        {
                            "exception_id": "ex-1",
                            "recipient": "直下先",
                            "subject": "人物見立て共有",
                            "allowed_scope": "対人見立て",
                            "scope_tokens": ["people_insight"],
                            "approval_type": "今回限り",
                            "approved_at": "2026-03-17T10:00:00",
                            "consumed_at": "",
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            handler_runner.resolve_human_entity = lambda name: (
                "直下先",
                {"name": "直下先", "category": "直下メンバー", "email": "member@example.com"},
            )

            runner = handler_runner.HandlerRunner(system_dir=SYSTEM_DIR, project_root=ROOT_DIR)
            runner._dispatch_outbound_message = lambda channel, content, policy: ("sent", "送信済み")

            result = runner._run_action(
                {"name": "send_message"},
                {
                    "recipient": "直下先",
                    "channel": "email",
                    "content": "この伝え方で進めて",
                    "disclosure_subject": "人物見立て共有",
                    "disclosure_scope": ["people_insight"],
                },
            )

            self.assertIn("送信完了", result)
            entries = json.loads(handler_runner._DISCLOSURE_EXCEPTION_PATH.read_text(encoding="utf-8"))
            self.assertTrue(entries[0]["consumed_at"])

    def test_outbound_audit_log_is_written_on_sent_message(self):
        handler_runner = load_module("handler_runner_test_case_audit", HANDLER_RUNNER_PATH)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            handler_runner._RUNTIME_DATA_DIR = tmp_path
            handler_runner._CONTACT_STATE_PATH = tmp_path / "contact_state.json"
            handler_runner._DISCLOSURE_EXCEPTION_PATH = tmp_path / "disclosure_exceptions.json"
            handler_runner._OUTBOUND_AUDIT_LOG_PATH = tmp_path / "outbound_message_audit.jsonl"
            handler_runner._CONTACT_STATE_PATH.write_text(
                json.dumps(
                    {
                        "並列先": {
                            "send_authority": {"level": "Lv3"},
                            "delivery_targets": {"email": {"address": "peer@example.com"}},
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            handler_runner.resolve_human_entity = lambda name: (
                "並列先",
                {
                    "name": "並列先",
                    "category": "並列メンバー",
                    "base_audience": "並列",
                    "email": "peer@example.com",
                },
            )

            runner = handler_runner.HandlerRunner(system_dir=SYSTEM_DIR, project_root=ROOT_DIR)
            runner._dispatch_outbound_message = lambda channel, content, policy: ("sent", "送信済み")

            result = runner._run_action(
                {"name": "send_message"},
                {
                    "recipient": "並列先",
                    "channel": "email",
                    "content": "共有ありがとうございます。確認しました。",
                },
            )

            self.assertIn("送信完了", result)
            log_lines = handler_runner._OUTBOUND_AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(log_lines), 1)
            payload = json.loads(log_lines[0])
            self.assertEqual(payload["result"], "sent")
            self.assertEqual(payload["canonical_name"], "並列先")
            self.assertEqual(payload["channel"], "email")

    def test_manual_delivery_target_registration_supports_unknown_person(self):
        local_agent = load_module("local_agent_test_case", LOCAL_AGENT_PATH)

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            local_agent._RUNTIME_DATA_DIR = tmp_path
            local_agent.CONTACT_STATE_FILE = tmp_path / "contact_state.json"
            local_agent._resolve_person_identity = lambda sender_name="", chatwork_account_id="": (None, None, set())

            canonical_key, entry = local_agent._register_delivery_target(
                person_name="新規外部",
                channel="email",
                primary_value="new@example.com",
                note="手動登録",
            )

            self.assertEqual(canonical_key, "新規外部")
            self.assertEqual(entry["delivery_targets"]["email"]["address"], "new@example.com")

            inspected_key, targets = local_agent._inspect_delivery_target("新規外部")
            self.assertEqual(inspected_key, "新規外部")
            self.assertEqual(targets["email"]["address"], "new@example.com")

    def test_contact_route_endpoint_prefers_cache_and_falls_back_to_pending(self):
        app_module = load_module("line_bot_app_test_case", LINE_BOT_APP_PATH)
        app_module.verify_agent_token = lambda: True
        app_module.load_data = lambda: None
        app_module.save_data = lambda: None
        app_module.resolve_human_entity = lambda name: (
            "三上 功太",
            {"name": "三上 功太", "line_display_name": "みかみさん"},
        )
        client = app_module.app.test_client()

        app_module.contact_routes = {
            "三上功太": {
                "canonical_name": "三上 功太",
                "aliases": ["三上功太", "みかみさん"],
                "delivery_targets": {
                    "line": {
                        "user_id": "U999",
                        "group_id": "G999",
                        "last_seen_at": "2026-03-17T12:00:00",
                    },
                    "chatwork": {"room_id": "", "account_id": "", "last_seen_at": ""},
                },
                "updated_at": "2026-03-17T12:00:00",
            }
        }
        app_module.pending_messages = {}

        resp = client.get("/api/contact-route?recipient=みかみさん")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_json()["delivery_targets"]["line"]["user_id"], "U999")

        app_module.contact_routes = {}
        app_module.pending_messages = {
            "msg1": {
                "platform": "chatwork",
                "sender_name": "みかみさん",
                "group_id": "R321",
                "chatwork_room_id": "R321",
                "chatwork_account_id": "A321",
                "timestamp": "2026-03-17T13:00:00",
            }
        }

        resp = client.get("/api/contact-route?recipient=三上 功太")
        self.assertEqual(resp.status_code, 200)
        payload = resp.get_json()
        self.assertEqual(payload["delivery_targets"]["chatwork"]["room_id"], "R321")
        self.assertIn("三上功太", app_module.contact_routes)


if __name__ == "__main__":
    unittest.main()
