#!/usr/bin/env python3
"""
PC常駐エージェント - LINE AI秘書のローカル実行部
Renderサーバーからタスクをポーリングして自動実行
Claude APIを直接呼び出して処理し、結果をLINEに自動報告
Q&A質問監視機能も統合
"""

import os
import sys
import json
import time
import subprocess
import threading
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ---- プロファイルパス ----
_AGENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent
# System/ ディレクトリを動的に解決（Desktop: parent.parent, Mac Mini: parent.parent/System/）
_SYSTEM_DIR = _AGENT_DIR.parent
if not (_SYSTEM_DIR / "mail_manager.py").exists():
    _SYSTEM_DIR = _SYSTEM_DIR / "System"
PEOPLE_PROFILES_JSON = _PROJECT_ROOT / "Master" / "people-profiles.json"
PEOPLE_IDENTITIES_JSON = _PROJECT_ROOT / "Master" / "people-identities.json"
SELF_IDENTITY_MD = _PROJECT_ROOT / "Master" / "self_clone" / "projects" / "kohara" / "1_Core" / "IDENTITY.md"
SELF_PROFILE_MD = _PROJECT_ROOT / "Master" / "self_clone" / "projects" / "kohara" / "1_Core" / "SELF_PROFILE.md"
FEEDBACK_FILE = _PROJECT_ROOT / "Master" / "reply_feedback.json"  # フィードバック学習データ


def _load_self_identity() -> str:
    """甲原海人の言語スタイル定義を読み込む"""
    try:
        if SELF_IDENTITY_MD.exists():
            return SELF_IDENTITY_MD.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""


def _load_self_profile() -> str:
    """甲原海人のコアプロファイル（価値観・判断軸・哲学）を読み込む"""
    try:
        if SELF_PROFILE_MD.exists():
            content = SELF_PROFILE_MD.read_text(encoding="utf-8")
            if "↓ ここに記入 ↓" in content and content.count("-\n") > 5:
                return ""
            return content
    except Exception:
        pass
    return ""


def load_feedback_examples() -> list:
    """保存済みフィードバック例を読み込む"""
    try:
        if FEEDBACK_FILE.exists():
            return json.loads(FEEDBACK_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return []


def save_feedback_example(fb: dict):
    """フィードバックを保存（最大50件、古いものを削除）"""
    examples = load_feedback_examples()
    examples.append(fb)
    examples = examples[-50:]
    FEEDBACK_FILE.write_text(
        json.dumps(examples, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def build_feedback_prompt_section(sender_name: str = "", sender_category: str = "") -> str:
    """プロンプトに注入するフィードバックセクションを生成"""
    examples = load_feedback_examples()
    if not examples:
        return ""

    note_parts = []
    for fb in examples:
        if fb.get("type") == "note":
            note_parts.append(f"・{fb.get('note', '')}")

    corrections = [f for f in examples if f.get("type") == "correction"]
    sorted_corrections = sorted(
        corrections,
        key=lambda f: (f.get("sender_name") == sender_name, f.get("timestamp", "")),
        reverse=True
    )[:5]

    parts = []
    for i, fb in enumerate(sorted_corrections, 1):
        orig = fb.get("original_message", "")[:50]
        ai_s = fb.get("ai_suggested", "")[:60]
        actual = fb.get("actual_sent", "")[:60]
        sname = fb.get("sender_name", "不明")
        parts.append(
            f"[修正例{i}] 送信者: {sname}\n"
            f"  受信: 「{orig}」\n"
            f"  AI案（不採用）: 「{ai_s}」\n"
            f"  実際に送った返信: 「{actual}」"
        )

    section = ""
    if note_parts or parts:
        section = "\n【過去の学習データ（優先して参考にすること）】\n"
        if note_parts:
            section += "スタイルノート:\n" + "\n".join(note_parts) + "\n"
        if parts:
            section += "\n".join(parts) + "\n"
    return section

# Anthropic SDK
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

# Q&A監視モジュール
try:
    from qa_monitor import (
        get_sheets_service,
        check_new_questions,
        mark_as_sent,
        update_answer_status,
        write_answer_to_sheet,
    )
    QA_MONITOR_AVAILABLE = True
except ImportError:
    QA_MONITOR_AVAILABLE = False

# 設定
CONFIG_FILE = Path(__file__).parent / "config.json"
DEFAULT_CONFIG = {
    "server_url": "https://line-ai-secretary.onrender.com",
    "poll_interval": 30,  # 秒
    "agent_token": "",    # 認証トークン（Render側と同じ値を設定）
    "cursor_workspace": str(Path(__file__).parent.parent.parent),  # /Users/koa800/Desktop/cursor
    "anthropic_api_key": "",  # Anthropic APIキー
    "auto_mode": "claude",  # "claude" = Claude API直接, "cursor" = Cursor経由
    "qa_monitor_enabled": True,  # Q&A監視を有効化
    "qa_poll_interval": 60,  # Q&Aポーリング間隔（秒）
}

# グローバル設定
config = {}


def load_config():
    """設定を読み込む"""
    global config
    
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = DEFAULT_CONFIG.copy()
        save_config()
        print(f"設定ファイルを作成しました: {CONFIG_FILE}")
        print("server_url と agent_token を設定してください")
    
    return config


def save_config():
    """設定を保存"""
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def get_headers():
    """APIリクエスト用ヘッダー（agent_token は config または環境変数 LOCAL_AGENT_TOKEN）"""
    headers = {"Content-Type": "application/json"}
    token = (config.get("agent_token") or os.environ.get("LOCAL_AGENT_TOKEN") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_tasks():
    """サーバーからタスクを取得"""
    try:
        url = f"{config['server_url']}/tasks"
        response = requests.get(url, headers=get_headers(), timeout=35)  # Renderスリープ解除待ち
        
        if response.status_code == 200:
            data = response.json()
            return data.get("tasks", [])
        elif response.status_code == 401:
            print("⚠️  認証エラー: agent_token を確認してください")
        else:
            print(f"⚠️  タスク取得エラー: {response.status_code}")
        
    except requests.exceptions.ConnectionError:
        print("🔄 サーバーに接続できません（スリープ中の可能性）")
    except Exception as e:
        print(f"⚠️  エラー: {e}")
    
    return []


def start_task(task_id: str):
    """タスク処理開始を報告"""
    try:
        url = f"{config['server_url']}/tasks/{task_id}/start"
        response = requests.post(url, headers=get_headers(), timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️  開始報告エラー: {e}")
        return False


def complete_task(task_id: str, success: bool, message: str, error: str = None, extra: dict = None):
    """タスク完了を報告"""
    try:
        url = f"{config['server_url']}/tasks/{task_id}/complete"
        data = {
            "success": success,
            "message": message
        }
        if error:
            data["error"] = error
        if extra:
            data.update(extra)

        response = requests.post(url, json=data, headers=get_headers(), timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"⚠️  完了報告エラー: {e}")
        return False


# ===== デスクトップ通知 =====

def show_notification(title: str, message: str, sound: bool = True):
    """macOSデスクトップ通知を表示（別スレッドで実行: LaunchAgentでのハング対策）"""
    def _notify():
        try:
            _msg = message.replace('"', '\\"').replace('\n', ' ')
            _title = title.replace('"', '\\"')
            sound_cmd = 'sound name "Glass"' if sound else ""
            script = f'display notification "{_msg}" with title "{_title}" {sound_cmd}'
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, timeout=5
            )
        except Exception:
            pass
    threading.Thread(target=_notify, daemon=True).start()


# ===== Cursor自動実行 =====

def send_to_cursor(instruction: str) -> bool:
    """CursorにAppleScriptで指示を送る（クリップボード経由）"""
    import subprocess
    
    try:
        # 1. クリップボードに指示を設定（pbcopy経由、UTF-8対応）
        pbcopy_proc = subprocess.Popen(
            ["pbcopy"],
            stdin=subprocess.PIPE,
            env={**os.environ, "LANG": "en_US.UTF-8"}
        )
        pbcopy_proc.communicate(input=instruction.encode("utf-8"))
        
        # 2. Cursorをアクティブにしてペースト
        script = '''
        tell application "Cursor" to activate
        delay 0.8
        tell application "System Events"
            -- Cmd+L でAIチャット入力欄にフォーカス
            keystroke "l" using command down
            delay 0.5
            -- クリップボードから貼り付け
            keystroke "v" using command down
            delay 0.3
            -- Enterで送信
            key code 36
        end tell
        '''
        
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            env={**os.environ, "LANG": "en_US.UTF-8"}
        )
        
        if result.returncode == 0:
            print(f"   ✅ Cursorに指示を送信しました")
            return True
        else:
            print(f"   ❌ AppleScriptエラー: {result.stderr}")
            return False
    except Exception as e:
        print(f"   ❌ Cursor実行エラー: {e}")
        return False


def format_task_for_cursor(task: dict) -> str:
    """タスクをCursor用の指示文に変換"""
    function_name = task.get("function")
    arguments = task.get("arguments", {})
    original_text = task.get("original_text", "")

    if function_name == "input_daily_report":
        date = arguments.get("date", "")
        return f"日報報告して（{date}）"

    if function_name == "generate_reply_suggestion":
        sender = arguments.get("sender_name", "不明")
        msg = arguments.get("original_message", original_text)
        return f"「{sender}」からのメッセージへの返信案を生成: {msg[:60]}"

    # その他のタスクは元のテキストをそのまま使用
    return original_text or f"タスク: {function_name}"


# ===== 人物プロファイル参照 =====

def _load_json_safe(path: Path) -> dict:
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def lookup_sender_profile(sender_name: str, chatwork_account_id: str = ""):
    """送信者名またはChatwork account_idからプロファイルを逆引き。Noneなら未登録。"""
    if not sender_name and not chatwork_account_id:
        return None

    identities = _load_json_safe(PEOPLE_IDENTITIES_JSON)
    profiles = _load_json_safe(PEOPLE_PROFILES_JSON)

    matched_key = None

    # chatwork_account_id で逆引き（Chatworkメンションの場合）
    if chatwork_account_id:
        for addness_name, info in identities.items():
            if str(info.get("chatwork_account_id", "")) == str(chatwork_account_id):
                matched_key = addness_name
                break

    # identities で line_display_name / line_my_name → Addness名 を逆引き
    if not matched_key and sender_name:
        for addness_name, info in identities.items():
            if sender_name in (info.get("line_display_name", ""), info.get("line_my_name", ""),
                               info.get("chatwork_display_name", "")):
                matched_key = addness_name
                break

    # identitiesで見つからなければAddness名と直接比較
    if not matched_key and sender_name and sender_name in profiles:
        matched_key = sender_name

    if matched_key and matched_key in profiles:
        return profiles[matched_key].get("latest", {})
    return None


def build_sender_context(sender_name: str) -> str:
    """送信者プロファイルをシステムプロンプト用テキストに変換"""
    profile = lookup_sender_profile(sender_name)
    if not profile:
        return ""

    lines = [f"\n--- 送信者プロファイル: {sender_name} ---"]
    cat = profile.get("category", "")
    rel = profile.get("relationship", "")
    if cat or rel:
        lines.append(f"関係: {cat}{'  ' + rel if rel else ''}")

    domains = profile.get("inferred_domains", [])
    if domains:
        lines.append(f"スキル領域: {', '.join(domains)}")

    summary = profile.get("capability_summary", "")
    if summary:
        lines.append(f"能力サマリー: {summary}")

    wl = profile.get("workload", {})
    if wl:
        lines.append(f"稼働状況: 実行中{wl.get('active', 0)}件 / 完了済み{wl.get('completed', 0)}件")

    identity = profile.get("identity", {})
    id_notes = identity.get("notes", "") if isinstance(identity, dict) else ""
    if id_notes:
        lines.append(f"メモ: {id_notes}")

    active = profile.get("active_goals", [])
    if active:
        titles = [g["title"] for g in active[:3]]
        lines.append(f"現在進行中のゴール: {' / '.join(titles)}")

    lines.append("---")
    return "\n".join(lines)


def fetch_sheet_context(related_sheets: list) -> str:
    """related_sheetsのスプレッドシートからデータを取得し、文脈テキストを生成"""
    if not related_sheets:
        return ""

    sheets_manager_path = _SYSTEM_DIR / "sheets_manager.py"
    if not sheets_manager_path.exists():
        print(f"   ⚠️ sheets_manager.py が見つかりません: {sheets_manager_path}")
        return ""

    parts = []
    for sheet_info in related_sheets[:2]:  # 最大2シートまで
        sheet_id = sheet_info.get("id", "")
        sheet_name = sheet_info.get("sheet_name", "")
        description = sheet_info.get("description", "")
        if not sheet_id:
            continue

        try:
            cmd = [sys.executable, str(sheets_manager_path), "json", sheet_id]
            if sheet_name:
                cmd.append(sheet_name)
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30, encoding="utf-8"
            )
            if result.returncode == 0 and result.stdout.strip():
                raw = result.stdout.strip()
                # JSONパースして直近データを抽出
                try:
                    rows = json.loads(raw)
                    # 直近3行のデータを取得（月次データの場合は最新月が末尾）
                    recent = rows[-3:] if len(rows) > 3 else rows
                    sheet_text = json.dumps(recent, ensure_ascii=False, indent=1)
                except (json.JSONDecodeError, TypeError):
                    sheet_text = raw

                # トークン節約のため1500文字以内にトランケート
                if len(sheet_text) > 1500:
                    sheet_text = sheet_text[:1500] + "\n...(truncated)"

                header = f"📊 {description or sheet_name or sheet_id}"
                parts.append(f"{header}\n{sheet_text}")
            else:
                err = result.stderr.strip()[:100] if result.stderr else ""
                print(f"   ⚠️ シートデータ取得失敗: {sheet_id} / {err}")
        except subprocess.TimeoutExpired:
            print(f"   ⚠️ シートデータ取得タイムアウト: {sheet_id}")
        except Exception as e:
            print(f"   ⚠️ シートデータ取得エラー: {sheet_id} / {e}")

    if not parts:
        return ""
    return "\n\n".join(parts)


# ===== Claude API直接呼び出し =====

def call_claude_api(instruction: str, task: dict):
    """Claude APIを直接呼び出してタスクを実行"""
    if not ANTHROPIC_AVAILABLE:
        return False, "anthropicライブラリがインストールされていません。pip install anthropic を実行してください。"
    
    api_key = (config.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return False, "anthropic_api_key または環境変数 ANTHROPIC_API_KEY が設定されていません。"
    
    try:
        client = anthropic.Anthropic(api_key=api_key)

        # タスク情報
        function_name = task.get("function", "unknown")
        arguments = task.get("arguments", {})

        # 送信者プロファイルを取得（複数のキーを試す）
        sender_name = (
            arguments.get("sender_name")
            or arguments.get("sender_display_name")
            or arguments.get("user_name")
            or task.get("sender_name")
            or task.get("user_name")
            or ""
        )

        # ===== 人物メモ保存タスク =====
        if function_name == "save_person_memo":
            person_name = arguments.get("person_name", "")
            memo = arguments.get("memo", "")
            if person_name and memo:
                profiles = _load_json_safe(PEOPLE_PROFILES_JSON)
                identities = _load_json_safe(PEOPLE_IDENTITIES_JSON)
                matched_key = None
                for key, info in identities.items():
                    if person_name in (info.get("line_display_name", ""), info.get("line_my_name", ""),
                                       key, info.get("real_name", "")):
                        matched_key = key
                        break
                if not matched_key:
                    for key in profiles:
                        if person_name in key or key in person_name:
                            matched_key = key
                            break
                if matched_key and matched_key in profiles:
                    entry = profiles[matched_key]
                    profile_data = entry.get("latest", entry)
                    if "comm_profile" not in profile_data:
                        profile_data["comm_profile"] = {"context_notes": []}
                    if "context_notes" not in profile_data["comm_profile"]:
                        profile_data["comm_profile"]["context_notes"] = []
                    note_entry = {"content": memo, "added_at": datetime.now().isoformat()}
                    profile_data["comm_profile"]["context_notes"].append(note_entry)
                    profile_data["comm_profile"]["context_notes"] = profile_data["comm_profile"]["context_notes"][-20:]
                    if "latest" in entry:
                        entry["latest"] = profile_data
                    else:
                        profiles[matched_key] = profile_data
                    PEOPLE_PROFILES_JSON.write_text(json.dumps(profiles, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"   📌 メモ保存: {matched_key} → 「{memo[:40]}」")
                    return True, f"📌 {matched_key}さんのメモを保存しました"
                else:
                    return False, f"⚠️  「{person_name}」さんのプロファイルが見つかりません"
            return True, "メモ保存完了"

        # ===== フィードバック保存タスク =====
        if function_name == "capture_feedback":
            fb_type = arguments.get("type", "note")
            fb_data = {
                **{k: v for k, v in arguments.items() if k != "type"},
                "type": fb_type,
                "timestamp": datetime.now().isoformat(),
            }
            save_feedback_example(fb_data)
            if fb_type == "note":
                note_preview = fb_data.get("note", "")[:40]
                print(f"   📝 スタイルノート保存: 「{note_preview}」")
                return True, f"📝 スタイルノート保存済み"
            else:
                sender = fb_data.get("sender_name", "")
                actual = fb_data.get("actual_sent", "")[:30]
                print(f"   📝 修正例保存: {sender} → 「{actual}」")
                return True, f"📝 修正例を学習しました"

        # ===== 返信案生成タスクの専用処理 =====
        if function_name == "generate_reply_suggestion":
            original_message = arguments.get("original_message", task.get("original_text", ""))
            quoted_text = arguments.get("quoted_text", "")  # 引用返信の場合のボット返信テキスト
            context_messages = arguments.get("context_messages", [])  # メンション直前の会話文脈
            message_id = arguments.get("message_id", "")
            group_name = arguments.get("group_name", "")
            msg_id_short = message_id[:4] if message_id else "----"
            platform = arguments.get("platform", "line")
            cw_account_id = arguments.get("chatwork_account_id", "")

            # プロファイルから送信者情報を取得（Chatwork account_idでも検索）
            profile = lookup_sender_profile(sender_name, chatwork_account_id=cw_account_id)
            profile_info = ""
            category_line = ""
            if profile:
                cat = profile.get("category", "")
                rel = profile.get("relationship", "")
                domains = ", ".join(profile.get("inferred_domains", []))
                summary = profile.get("capability_summary", "")
                category_line = f"（{cat}{'・' + rel if rel else ''}{'・' + domains[:30] if domains else ''}）"
                profile_info = f"\n【送信者プロファイル】\n関係: {cat} {rel}\n"
                if domains:
                    profile_info += f"スキル: {domains}\n"
                if summary:
                    profile_info += f"能力: {summary[:100]}\n"

            # 関係性に応じたトーン指示
            tone_guide = ""
            if profile:
                cat = profile.get("category", "")
                if cat == "上司":
                    tone_guide = "相手は上司なので、丁寧で敬意ある返信にする。"
                elif cat == "横（並列）":
                    tone_guide = "相手は同僚なので、フレンドリーかつビジネスライクな返信にする。"
                elif cat in ("直下メンバー", "メンバー"):
                    tone_guide = "相手はメンバーなので、親しみやすく明確な返信にする。"

            # 甲原海人の言語スタイル定義を読み込む（空の場合は最低限のインラインフォールバック）
            identity_style = _load_self_identity()
            if not identity_style:
                identity_style = (
                    "【甲原海人の基本スタイル】\n"
                    "- 文末に「！」を多用（テンション・明るさの表現）\n"
                    "- 「、、」（読点2つ）で溜め・気遣いを表現\n"
                    "- 上司: 丁寧だが堅くなく、提案型。「お疲れ様です！」で始める\n"
                    "- 同僚: フランク。「○○さんお疲れ様です！」で始める\n"
                    "- 部下: かなりフランク。敬語なし or 最低限\n"
                    "- NG: 「かしこまりました」「承知いたしました」\n"
                    "- OK: 「了解です！」「分かりました！」「どうでしょうか？」"
                )

            # ── 全情報を収集してプロンプトを構築 ──
            self_profile = _load_self_profile()
            sender_cat = profile.get("category", "") if profile else ""
            comm_profile = profile.get("comm_profile", {}) if profile else {}
            comm_style_note = comm_profile.get("style_note", "")
            comm_greeting = comm_profile.get("greeting", "")
            active_goals = (profile.get("active_goals", []) if profile else [])[:3]
            goals_context = ""
            if active_goals:
                goals_list = "\n".join([f"  ・{g['title'][:40]}" for g in active_goals])
                goals_context = f"\n現在取り組み中:\n{goals_list}"
            context_notes = comm_profile.get("context_notes", []) if comm_profile else []
            notes_text = ""
            if context_notes:
                recent_notes = context_notes[-5:]
                notes_text = "\nメモ:\n" + "\n".join([f"  ・{n.get('content', n) if isinstance(n, dict) else n}" for n in recent_notes])
            feedback_section = build_feedback_prompt_section(sender_name, sender_cat)
            self_profile_section = ""
            if self_profile:
                self_profile_section = f"\n【甲原海人のコアプロファイル（価値観・判断軸・哲学）】\n{self_profile}\n"

            quoted_section = ""
            if quoted_text:
                quoted_section = f"\n【引用元（ボットが送った返信・この内容へのリプライです）】\n{quoted_text}\n"

            context_section = ""
            if context_messages:
                ctx_text = "\n".join(context_messages)
                context_section = f"\n【メンション直前の会話文脈（参考）】\n{ctx_text}\n"

            # スプレッドシートデータを取得（related_sheetsがあるプロファイルの場合）
            sheet_section = ""
            if profile:
                related_sheets = profile.get("related_sheets", [])
                if related_sheets:
                    sheet_data = fetch_sheet_context(related_sheets)
                    if sheet_data:
                        sheet_section = f"\n【関連データ】\n{sheet_data}\n"
                        print(f"   📊 シートデータ取得完了: {len(sheet_data)}文字")

            # Chatworkの場合のプラットフォーム注記
            platform_note = ""
            if platform == "chatwork":
                platform_note = "- 返信先はChatwork（LINEではない）。Chatworkの文体・フォーマットに合わせる\n"

            prompt = f"""あなたは甲原海人本人として返信を書きます。
以下の全情報を統合し、甲原海人が実際に送るようなメッセージを生成してください。

【言語スタイル定義】
{identity_style}
{self_profile_section}{feedback_section}
---

【送信者: {sender_name}】{category_line}
返信スタイル: {comm_style_note or tone_guide or '関係性に応じたトーンで'}
推奨挨拶: {comm_greeting or 'お疲れ様！'}
{goals_context}{notes_text}
{profile_info}
{context_section}{quoted_section}{sheet_section}
【受信メッセージ】
グループ: {group_name}
内容: {original_message}

【出力ルール】
- 甲原海人が実際に送る文章のみ出力（説明・前置き不要）
- 50文字以内を目安に簡潔に（ただし関連データに基づく数字を含める場合は長くてOK）
- 相手固有のスタイルノートと口調の癖をそのまま再現する
- メモ・現在の取り組みがあれば文脈として活用する
- 関連データがある場合は具体的な数字を引用して根拠のある返信にする
- 絶対に使わない表現: 「そっかー」「そっかぁ」「そうなんだー」「〜だよね」「〜だよー」「わかるー」「たしかにー」等の長音カジュアル表現
- 絶対に使わない絵文字: 😊 😄 😆 🥰 ☺️ 🤗（ニコニコ系は全て禁止。使えるのは😭🙇‍♂️🔥のみ）
{platform_note}{('- 会話文脈を踏まえた流れのある返信にすること' if context_messages else '')}{('- 引用元の内容を踏まえた返信にすること' if quoted_text else '')}
返信文:"""

            response = client.messages.create(
                model="claude-sonnet-4-6",  # 口調再現は精度重視でSonnet
                max_tokens=200,
                system="あなたは甲原海人です。定義されたスタイルで返信文のみを出力してください。",
                messages=[{"role": "user", "content": prompt}]
            )

            reply_suggestion = response.content[0].text.strip()

            # raw_reply をタスク引数に一時保存（execute_task_with_claude が complete_task に渡す）
            task.setdefault("arguments", {})["_raw_reply"] = reply_suggestion

            # 秘書グループ向けの整形済みメッセージを生成
            platform_tag = "[CW] " if platform == "chatwork" else ""
            profile_badge = f"👤 {sender_name}{category_line}" if profile else f"👤 {sender_name}"
            quoted_line = ""
            if quoted_text:
                q_preview = quoted_text[:50] + "..." if len(quoted_text) > 50 else quoted_text
                quoted_line = f"📌 引用元: 「{q_preview}」\n"
            sheet_note = "📊 シートデータ参照済み\n" if sheet_section else ""
            result = (
                f"{'💬 引用返信案' if quoted_text else '💡 返信案'} {platform_tag}\n"
                f"{profile_badge}\n"
                f"\n"
                f"グループ: {group_name}\n"
                f"「{original_message[:80]}{'...' if len(original_message) > 80 else ''}」\n"
                f"{quoted_line}{sheet_note}"
                f"\n"
                f"返信案:\n{reply_suggestion}\n"
                f"\n"
                f"─────────────\n"
                f"このメッセージにリプライ:\n"
                f"1 → 承認して送信\n"
                f"2 [別の内容] → 編集して送信"
            )
            # 接触記録を更新（フォローアップ追跡用）
            if sender_name:
                _contact_state_path = Path(__file__).parent / "contact_state.json"
                try:
                    contact_state = {}
                    if _contact_state_path.exists():
                        contact_state = json.loads(_contact_state_path.read_text(encoding="utf-8"))
                    contact_state[sender_name] = datetime.now().isoformat()
                    _contact_state_path.write_text(json.dumps(contact_state, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

            return True, result

        # ===== LP自動ドラフト生成タスク =====
        if function_name == "generate_lp_draft":
            product = arguments.get("product", "スキルプラス")
            target_audience = arguments.get("target_audience", "副業・起業希望者")
            message_axis = arguments.get("message_axis", "")
            tone = arguments.get("tone", "実績重視・親しみやすい")

            # ブランドコンテキストを読み込む（SELF_PROFILE.md）
            brand_context = ""
            try:
                profile_path = _PROJECT_ROOT / "Master" / "self_clone" / "projects" / "kohara" / "1_Core" / "SELF_PROFILE.md"
                if profile_path.exists():
                    brand_context = profile_path.read_text(encoding="utf-8")[:800]
            except Exception:
                pass

            lp_prompt = f"""あなたは高変換率LPのコピーライターです。
以下の条件で日本語LPの構成案・コピーを作成してください。

【商品・サービス】{product}
【ターゲット】{target_audience}
【訴求軸】{message_axis or '未指定（最も効果的な軸を選んでください）'}
【トーン】{tone}

【ブランド背景】
{brand_context or '（なし）'}

【出力形式】（LINEで読めるよう500文字以内に収める）
1. ファーストビュー見出し案（3パターン）
2. サブキャッチ（1行）
3. CTA（ボタン文言）案（2パターン）
4. 推奨ベネフィット訴求（3点）

実践的なコピーを出力してください。"""

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=700,
                system="あなたはROAS・CVR改善実績のあるLPコピーライターです。具体的で変換率の高いコピーを作成してください。",
                messages=[{"role": "user", "content": lp_prompt}]
            )
            draft = response.content[0].text.strip()
            result_text = f"📝 LPドラフト: {product}\n━━━━━━━━━━━━\n{draft}\n━━━━━━━━━━━━\n💡 フル版はCursorで展開できます"
            return True, result_text

        # ===== 動画スクリプト自動生成タスク =====
        if function_name == "generate_video_script":
            product = arguments.get("product", "スキルプラス")
            video_type = arguments.get("video_type", "TikTok広告15秒")
            target_audience = arguments.get("target_audience", "副業・起業希望者")
            hook = arguments.get("hook", "")

            # ブランドコンテキスト
            brand_context = ""
            try:
                profile_path = _PROJECT_ROOT / "Master" / "self_clone" / "projects" / "kohara" / "1_Core" / "SELF_PROFILE.md"
                if profile_path.exists():
                    brand_context = profile_path.read_text(encoding="utf-8")[:500]
            except Exception:
                pass

            script_prompt = f"""あなたは高転換率の動画広告クリエイターです。
以下の条件で日本語の動画台本を作成してください。

【商品・サービス】{product}
【動画タイプ】{video_type}
【ターゲット】{target_audience}
【フック・訴求】{hook or '最も効果的な冒頭フックを選んでください'}

【ブランド背景】
{brand_context or '（なし）'}

【出力形式】（LINEで読めるよう500文字以内）
- 冒頭フック（0〜3秒）:
- 問題提起（3〜8秒）:
- 解決策提示（8〜12秒）:
- CTA（12〜15秒）:
- ナレーション例（自然な口語体で）

TikTok/Instagram向けの引きの強い台本を作成してください。"""

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=700,
                system="あなたは短尺動画広告の台本クリエイターです。視聴者が思わず止まるフックと行動喚起を作成してください。",
                messages=[{"role": "user", "content": script_prompt}]
            )
            script = response.content[0].text.strip()
            result_text = f"🎬 動画台本: {product} ({video_type})\n━━━━━━━━━━━━\n{script}\n━━━━━━━━━━━━\n💡 Cursorで拡張版を作成できます"
            return True, result_text

        # ===== バナー構成案生成タスク =====
        if function_name == "generate_banner_concepts":
            product = arguments.get("product", "スキルプラス")
            platform = arguments.get("platform", "Meta広告")
            target_audience = arguments.get("target_audience", "副業・起業希望者")
            count = min(int(arguments.get("count", 5)), 10)

            banner_prompt = f"""あなたは高CTR・高CVRの広告バナーを設計するクリエイティブディレクターです。
以下の条件でバナー広告のコンセプト案を{count}パターン生成してください。

【商品・サービス】{product}
【掲載プラットフォーム】{platform}
【ターゲット層】{target_audience}

【各パターンの出力形式】
パターンX:
- ヘッドライン: （キャッチコピー・15文字以内）
- サブコピー: （補足・20文字以内）
- ビジュアル: （画像・動画の構成案を1文で）
- CTA: （ボタン文言）
- 訴求軸: （この案が刺さる理由を1行で）

多様な訴求軸（実績数字・感情・ベネフィット・緊急性など）でバリエーションを出してください。
LINEで読める形式で、合計600文字以内に収めてください。"""

            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=800,
                system="あなたはROAS・CTR改善実績のある広告クリエイティブディレクターです。具体的で成果の出るバナー案を作成してください。",
                messages=[{"role": "user", "content": banner_prompt}]
            )
            concepts = response.content[0].text.strip()
            result_text = f"🎨 バナー構成案: {product} ({platform})\n━━━━━━━━━━━━\n{concepts}\n━━━━━━━━━━━━\n💡 採用案はCursorで画像生成プロンプトに展開できます"
            return True, result_text

        # ===== 委託先推薦タスク（「誰に頼む？」等） =====
        if function_name == "who_to_ask":
            task_description = arguments.get("task_description", instruction)
            who_to_ask_py = _SYSTEM_DIR / "who_to_ask.py"
            if not who_to_ask_py.exists():
                return False, "who_to_ask.pyが見つかりません"
            try:
                import subprocess, sys as _sys
                r = subprocess.run(
                    [_sys.executable, str(who_to_ask_py), task_description],
                    capture_output=True, text=True, timeout=60
                )
                if r.returncode == 0 and r.stdout.strip():
                    result_text = f"👥 委託先推薦\n━━━━━━━━━━━━\n{r.stdout.strip()[:700]}\n━━━━━━━━━━━━"
                    return True, result_text
                else:
                    err = r.stderr.strip()[:200] if r.stderr else "不明なエラー"
                    return False, f"who_to_ask エラー: {err}"
            except Exception as e:
                return False, f"who_to_ask 実行エラー: {str(e)}"


        # ===== Q&A状況確認タスク =====
        if function_name == "qa_status":
            qa_state_path = _AGENT_DIR / "qa_monitor_state.json"
            if not qa_state_path.exists():
                return False, "qa_monitor_state.jsonが見つかりません\n（qa_monitorがまだ実行されていないか無効です）"
            try:
                state = json.loads(qa_state_path.read_text(encoding="utf-8"))
                last_check = state.get("last_check", "不明")
                sent_ids = state.get("sent_ids", [])
                pending = state.get("pending_approvals", {})
                # last_check を読みやすく
                try:
                    from datetime import datetime as _dt
                    lc = _dt.fromisoformat(last_check.replace("Z", "+00:00"))
                    last_check_str = lc.strftime("%m/%d %H:%M")
                    age_min = int((_dt.now().astimezone() - lc).total_seconds() / 60)
                    last_check_str += f" ({age_min}分前)"
                except Exception:
                    last_check_str = last_check[:16]

                parts = [
                    f"📊 Q&A状況",
                    f"━━━━━━━━━━━━",
                    f"通知済み: {len(sent_ids)}件累計",
                    f"保留中回答: {len(pending)}件",
                    f"最終チェック: {last_check_str}",
                    f"━━━━━━━━━━━━",
                ]
                if pending:
                    parts.append("【保留中】")
                    for qid, qdata in list(pending.items())[:3]:
                        q = qdata.get("question", "")[:30]
                        parts.append(f"  {qid}: {q}...")
                return True, "\n".join(parts)
            except Exception as e:
                return False, f"Q&A状況取得エラー: {str(e)}"

        # ===== Orchestrator状態確認タスク =====
        if function_name == "orchestrator_status":
            orch_base = "http://localhost:8500"
            try:
                # ヘルスチェック
                health_resp = requests.get(f"{orch_base}/health", timeout=5)
                health = health_resp.json() if health_resp.status_code == 200 else {}
                # スケジュール状態
                sched_resp = requests.get(f"{orch_base}/schedule/status", timeout=5)
                schedule = sched_resp.json() if sched_resp.status_code == 200 else {}

                today = health.get("today", {})
                total = today.get("tasks_total", "?")
                success = today.get("tasks_success", "?")
                errors = today.get("tasks_errors", "?")

                # 直近5ジョブの次回実行時刻
                jobs = schedule.get("jobs", [])
                upcoming = sorted(
                    [j for j in jobs if j.get("next_run")],
                    key=lambda j: j["next_run"]
                )[:3]
                sched_lines = [
                    f"  {j['id']}: {j['next_run'][11:16]}"
                    for j in upcoming
                ]

                parts = [
                    f"🤖 Orchestrator状態",
                    f"━━━━━━━━━━━━",
                    f"本日: {success}/{total}件成功 ({errors}件エラー)",
                    f"スケジュール済み: {schedule.get('total', '?')}ジョブ",
                    "",
                    f"直近スケジュール:",
                ]
                parts.extend(sched_lines or ["  （取得失敗）"])
                parts.append("━━━━━━━━━━━━")
                return True, "\n".join(parts)
            except Exception as e:
                return False, f"Orchestrator接続エラー: {str(e)[:150]}\n（Mac Mini Orchestratorが起動していない可能性があります）"

        # ===== Addness同期タスク =====
        if function_name == "addness_sync":
            addness_to_context_py = _SYSTEM_DIR / "addness_to_context.py"
            if not addness_to_context_py.exists():
                return False, "addness_to_context.pyが見つかりません"
            try:
                import subprocess, sys as _sys
                r = subprocess.run(
                    [_sys.executable, str(addness_to_context_py)],
                    capture_output=True, text=True, timeout=120
                )
                if r.returncode != 0:
                    return False, f"Addness同期エラー: {r.stderr.strip()[:300]}"
                # actionable-tasks.md の先頭要約を返す
                actionable_path = _PROJECT_ROOT / "Master" / "actionable-tasks.md"
                summary = ""
                if actionable_path.exists():
                    lines = actionable_path.read_text(encoding="utf-8").splitlines()
                    # 期限超過件数と実行中件数をカウント
                    overdue_count = sum(1 for l in lines if "🔴" in l)
                    inprog_count = sum(1 for l in lines if "🔄" in l)
                    # 更新日時を取得
                    from datetime import datetime as _dt
                    mtime = actionable_path.stat().st_mtime
                    updated = _dt.fromtimestamp(mtime).strftime("%m/%d %H:%M")
                    summary = f"🔴 期限超過: {overdue_count}件 / 🔄 実行中: {inprog_count}件\n更新: {updated}"
                return True, f"✅ Addness同期完了\n━━━━━━━━━━━━\n{summary or 'データを更新しました'}\n━━━━━━━━━━━━"
            except Exception as e:
                return False, f"Addness同期実行エラー: {str(e)}"

        # ===== メール即時確認タスク =====
        if function_name == "mail_check":
            account = arguments.get("account", "personal")
            if account not in ("personal", "kohara"):
                account = "personal"
            mail_py = _SYSTEM_DIR / "mail_manager.py"
            if not mail_py.exists():
                return False, "mail_manager.pyが見つかりません"
            try:
                import subprocess, sys as _sys
                r = subprocess.run(
                    [_sys.executable, str(mail_py), "--account", account, "run"],
                    capture_output=True, text=True, timeout=120
                )
                if r.returncode == 0 and r.stdout.strip():
                    return True, f"📬 メール確認 ({account})\n━━━━━━━━━━━━\n{r.stdout.strip()[:600]}\n━━━━━━━━━━━━"
                else:
                    err = r.stderr.strip()[:300] if r.stderr else "処理完了（結果なし）"
                    return False, f"メール確認エラー: {err}"
            except Exception as e:
                return False, f"メール確認実行エラー: {str(e)}"

        # ===== コンテキスト分析タスク（「次に何すべき？」等） =====
        if function_name == "context_query":
            question = arguments.get("question", instruction)

            # actionable-tasks.md を読み込む
            actionable_path = _PROJECT_ROOT / "Master" / "actionable-tasks.md"
            actionable_content = ""
            if actionable_path.exists():
                try:
                    actionable_content = actionable_path.read_text(encoding="utf-8")[:3000]
                except Exception:
                    pass

            # mail_manager.py で返信待ち件数を取得
            mail_status_text = ""
            try:
                import subprocess, sys as _sys
                mail_py = _SYSTEM_DIR / "mail_manager.py"
                if mail_py.exists():
                    r = subprocess.run(
                        [_sys.executable, str(mail_py), "--account", "personal", "status"],
                        capture_output=True, text=True, timeout=30
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        mail_status_text = f"\n【メール状況（personal）】\n{r.stdout.strip()[:300]}"
            except Exception:
                pass

            # 日時
            today_str = datetime.now().strftime("%Y/%m/%d (%A)")

            context_prompt = f"""あなたは甲原海人のAI秘書です。
今日の日付: {today_str}

以下の情報をもとに、「{question}」に答えてください。

【Addnessゴール・タスク状況】
{actionable_content or '（データなし）'}
{mail_status_text}

【回答ルール】
- 今すぐやるべきことを優先度順に3〜5件リスト
- 各項目に理由or期限を添える
- 500文字以内、LINEで読みやすい形式
"""
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=600,
                system="あなたは甲原海人のAI秘書です。質問に対してコンパクトで実用的な回答をしてください。",
                messages=[{"role": "user", "content": context_prompt}]
            )
            return True, response.content[0].text.strip()

        # ===== その他タスクの汎用処理 =====
        sender_context = build_sender_context(sender_name)

        # システムプロンプト
        system_prompt = """あなたはLINE経由で指示を受けるAI秘書です。
ユーザーからの指示に対して、簡潔で実用的な回答を返してください。
回答はLINEで送信されるため、以下に注意してください：
- 長すぎる回答は避ける（500文字以内推奨）
- 絵文字は控えめに
- 箇条書きを活用して読みやすく
"""
        if sender_context:
            system_prompt += sender_context

        user_message = f"""指示: {instruction}

タスク種別: {function_name}
パラメータ: {json.dumps(arguments, ensure_ascii=False)}

この指示に対して適切に対応してください。"""

        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        result_text = response.content[0].text
        return True, result_text
        
    except anthropic.AuthenticationError:
        return False, "APIキーが無効です。anthropic_api_keyを確認してください。"
    except anthropic.RateLimitError:
        return False, "APIレート制限に達しました。しばらく待ってから再試行してください。"
    except Exception as e:
        return False, f"Claude APIエラー: {str(e)}"


def execute_task_with_claude(task: dict):
    """タスクをClaude APIで自動実行"""
    instruction = format_task_for_cursor(task)
    function_name = task.get("function", "")

    print(f"   🤖 Claude APIで処理中...")
    success, result = call_claude_api(instruction, task)

    if success:
        print(f"   ✅ Claude API応答を受信")
        # generate_reply_suggestion は raw_reply と source_message_id もサーバーに渡す
        if function_name == "generate_reply_suggestion":
            arguments = task.get("arguments", {})
            raw_reply = arguments.get("_raw_reply", "")
            source_message_id = arguments.get("message_id", "")
            return True, result, {"raw_reply": raw_reply, "source_message_id": source_message_id}
        return True, result, {}
    else:
        print(f"   ❌ Claude APIエラー: {result}")
        return False, result, {}


# ===== 保留タスクファイル =====

PENDING_TASKS_FILE = Path.home() / ".cursor_pending_tasks.json"


def save_pending_task(task: dict):
    """保留タスクをファイルに保存"""
    tasks = []
    if PENDING_TASKS_FILE.exists():
        try:
            with open(PENDING_TASKS_FILE, "r", encoding="utf-8") as f:
                tasks = json.load(f)
        except:
            tasks = []
    
    tasks.append(task)
    
    with open(PENDING_TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)


def get_pending_tasks() -> list:
    """保留タスクを取得"""
    if PENDING_TASKS_FILE.exists():
        try:
            with open(PENDING_TASKS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def clear_pending_tasks():
    """保留タスクをクリア"""
    if PENDING_TASKS_FILE.exists():
        PENDING_TASKS_FILE.unlink()


# ===== Q&A監視 =====

def send_question_to_server(question_data: dict) -> bool:
    """新着質問をRenderサーバーに送信"""
    try:
        url = f"{config['server_url']}/qa/new"
        # デバッグ: 送信データを確認
        print(f"   📤 送信データ:")
        print(f"      id: {question_data.get('id', 'N/A')}")
        print(f"      user_id: {question_data.get('user_id', 'EMPTY!')}")
        print(f"      user_name: {question_data.get('user_name', 'N/A')}")
        
        response = requests.post(
            url,
            json=question_data,
            headers=get_headers(),
            timeout=30
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"   ⚠️ サーバーエラー: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ⚠️ 送信エラー: {e}")
        return False


def check_and_process_new_questions(sheets_service):
    """新着質問をチェックして処理"""
    print("🔍 Q&Aチェック中...")
    questions = check_new_questions(sheets_service)
    
    if not questions:
        print("   ✨ 新着質問なし")
        return 0
    
    print(f"\n📩 {len(questions)} 件の新着質問を検出")
    
    processed = 0
    for q in questions:
        print(f"   質問 {q['id']}: {q['question'][:40]}...")
        
        # サーバーに送信
        if send_question_to_server(q):
            mark_as_sent(q["id"])
            processed += 1
            print(f"   ✅ サーバーに送信完了")
            
            show_notification(
                "📩 新着質問",
                f"{q['user_name']}: {q['question'][:30]}..."
            )
        else:
            print(f"   ❌ 送信失敗")
    
    return processed


def fetch_approved_qa():
    """承認済みQ&A一覧を取得"""
    try:
        url = f"{config['server_url']}/qa/approved"
        response = requests.get(url, headers=get_headers(), timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            return data.get("items", [])
        else:
            return []
    except Exception as e:
        print(f"   ⚠️ 承認済みQ&A取得エラー: {e}")
        return []


def mark_sheet_updated(qa_id: str):
    """スプレッドシート更新完了をサーバーに通知"""
    try:
        url = f"{config['server_url']}/qa/mark-updated"
        response = requests.post(
            url,
            json={"id": qa_id},
            headers=get_headers(),
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        print(f"   ⚠️ 更新マークエラー: {e}")
        return False


def write_approved_answers_to_sheet(sheets_service):
    """承認済みQ&Aの回答をスプレッドシートに書き込み"""
    approved_items = fetch_approved_qa()
    
    if not approved_items:
        return 0
    
    print(f"\n📝 {len(approved_items)} 件の回答をスプレッドシートに書き込み")
    
    updated = 0
    for item in approved_items:
        row_index = item.get("row_index")
        sheet_name = item.get("sheet_name")
        qa_id = item.get("id")
        answer = item.get("answer", "")
        
        if not row_index or not sheet_name:
            print(f"   ⚠️ ID:{qa_id} - シート名または行番号が不明")
            continue
        
        print(f"   {sheet_name} 行{row_index}: 回答書き込み中...")
        
        if write_answer_to_sheet(sheets_service, sheet_name, row_index, answer):
            if mark_sheet_updated(qa_id):
                updated += 1
                print(f"   ✅ 書き込み完了")
            else:
                print(f"   ⚠️ サーバー通知失敗")
        else:
            print(f"   ❌ スプレッドシート書き込み失敗")
    
    return updated


# ===== メインループ =====

def run_agent():
    """エージェントを実行（完全自動モード）"""
    auto_mode = config.get("auto_mode", "claude")
    qa_enabled = config.get("qa_monitor_enabled", True) and QA_MONITOR_AVAILABLE
    qa_interval = config.get("qa_poll_interval", 60)
    
    print("=" * 50)
    print("🤖 LINE AI秘書 ローカルエージェント")
    print("=" * 50)
    print(f"サーバー: {config['server_url']}")
    print(f"ポーリング間隔: {config['poll_interval']}秒")
    print(f"実行モード: {auto_mode}")
    print(f"Q&A監視: {'有効' if qa_enabled else '無効'}")
    print()
    
    claude_api_available = bool(config.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY"))
    
    if auto_mode == "claude":
        if not claude_api_available:
            print("⚠️  anthropic_api_key / ANTHROPIC_API_KEY が設定されていません")
            print("   → Cursorが必要なタスク（日報入力等）のみ処理します")
        else:
            print("🤖 Claude APIモード: タスクを自動で処理し、結果をLINEに返信します")
    else:
        print("🚀 Cursorモード: タスクを受信したら自動でCursorに送信します")
    
    print("📋 日報入力タスク: Cursor専用（LINEからはガイドメッセージを返す）")
    
    print()
    print("Ctrl+C で終了")
    print("=" * 50)
    print()
    
    # 起動通知
    mode_text = "Claude API" if auto_mode == "claude" else "Cursor"
    show_notification("LINE AI秘書", f"ローカルエージェント起動（{mode_text}モード）", sound=False)
    
    # Q&A監視用のGoogle Sheets接続
    sheets_service = None
    if qa_enabled:
        sheets_service = get_sheets_service()
        if sheets_service:
            print("📋 Q&A監視: Google Sheets接続OK")
        else:
            print("⚠️ Q&A監視: Google Sheets接続失敗（Q&A監視は無効）")
            qa_enabled = False
    
    last_qa_check = datetime.now()
    
    while True:
        try:
            # ===== タスクポーリング =====
            tasks = fetch_tasks()
            
            if tasks:
                print(f"\n📥 {len(tasks)} 件のタスクを受信")
                
                for task in tasks:
                    task_id = task["id"]
                    function_name = task["function"]
                    instruction = format_task_for_cursor(task)
                    
                    print(f"\n📋 新しいタスク: {task_id}")
                    print(f"   種類: {function_name}")
                    print(f"   指示: {instruction}")
                    
                    # 処理開始を報告
                    start_task(task_id)

                    # 日報入力: Looker Studio・b-dash のブラウザ操作が必要なためCursor専用
                    if function_name == "input_daily_report":
                        complete_task(task_id, True,
                                      "📊 日報入力はLooker Studio・b-dashのブラウザ操作が必要なため、LINEからは実行できません。\nCursorを開いて「日報報告して」と入力してください。")
                        print(f"   ℹ️ 日報入力はCursor専用 → 案内メッセージをLINEに送信")
                        continue

                    # Claude APIが使えない場合はCursorで処理
                    use_cursor = (auto_mode == "cursor") or (not claude_api_available)
                    
                    if not use_cursor:
                        # ===== Claude APIで自動処理 =====
                        show_notification(
                            "🤖 LINE AI秘書 - 処理中",
                            f"Claude APIで処理: {instruction}"
                        )
                        
                        success, result, extra = execute_task_with_claude(task)

                        if success:
                            # 成功 → 結果をLINEに送信（extra があれば raw_reply 等も付加）
                            complete_task(task_id, True, result, None, extra or None)
                            show_notification(
                                "✅ LINE AI秘書 - 完了",
                                f"タスク完了: {instruction[:30]}..."
                            )
                            print(f"   ✅ 完了 → LINEに結果を送信しました")
                        else:
                            # 失敗 → エラーをLINEに送信
                            complete_task(task_id, False, "処理に失敗しました", result)
                            show_notification(
                                "❌ LINE AI秘書 - エラー",
                                f"エラー: {result[:50]}..."
                            )
                            print(f"   ❌ エラー → LINEに通知しました")
                    
                    else:
                        # ===== Cursorに送信（従来モード） =====
                        show_notification(
                            "🚀 LINE AI秘書 - 自動実行開始",
                            f"Cursorに送信中: {instruction}"
                        )
                        
                        # 保留タスクとして保存
                        task["cursor_instruction"] = instruction
                        save_pending_task(task)
                        
                        print(f"   🚀 Cursorに自動送信中...")
                        if send_to_cursor(instruction):
                            print(f"   ✅ Cursorへの送信完了")
                            print(f"   ⏳ Cursorが実行中... 完了したらLINEに報告してください:")
                            print(f"      python local_agent.py done {task_id}")
                        else:
                            print(f"   ❌ Cursorへの送信失敗")
                            complete_task(task_id, False, "⚠️ Cursorが起動していません\nPCでCursorを開いてからもう一度送ってください！", "AppleScriptエラー")
            
            # ===== Q&A監視 =====
            if qa_enabled and sheets_service:
                now = datetime.now()
                if (now - last_qa_check).total_seconds() >= qa_interval:
                    # 新着質問をチェック
                    check_and_process_new_questions(sheets_service)
                    # 承認済みQ&Aの回答をスプレッドシートに書き込み
                    write_approved_answers_to_sheet(sheets_service)
                    last_qa_check = now
            
            time.sleep(config["poll_interval"])
            
        except KeyboardInterrupt:
            print("\n\n👋 エージェントを終了します")
            break
        except Exception as e:
            print(f"⚠️  エラー: {e}")
            time.sleep(config["poll_interval"])


def main():
    """エントリーポイント"""
    load_config()
    
    # コマンドライン引数の処理
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "config":
            # 秘密は表示しない（ログ・画面に残さない）
            disp = {k: ("***" if (k in ("anthropic_api_key", "agent_token") and v) else v) for k, v in config.items()}
            print(json.dumps(disp, indent=2, ensure_ascii=False))
            return
        
        elif cmd == "set" and len(sys.argv) >= 4:
            key = sys.argv[2]
            value = sys.argv[3]
            if key in ("anthropic_api_key", "agent_token") and value:
                print("⚠️  セキュリティ: 本番では環境変数 ANTHROPIC_API_KEY / LOCAL_AGENT_TOKEN または Secret Manager の利用を推奨します。")
            # 数値に変換可能なら変換
            try:
                value = int(value)
            except ValueError:
                pass
            
            config[key] = value
            save_config()
            print(f"設定を更新: {key} = {value}")
            return
        
        elif cmd == "test":
            print("🔍 接続テスト...")
            try:
                url = f"{config['server_url']}/tasks"
                response = requests.get(url, headers=get_headers(), timeout=10)
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"✅ 接続成功 - {data.get('count', 0)} 件のタスクがあります")
                elif response.status_code == 401:
                    print("❌ 認証エラー - agent_token を確認してください")
                elif response.status_code == 404:
                    print("❌ エンドポイントが見つかりません（デプロイ中の可能性）")
                else:
                    print(f"❌ エラー: HTTP {response.status_code}")
            except requests.exceptions.ConnectionError:
                print("❌ サーバーに接続できません")
            except Exception as e:
                print(f"❌ エラー: {e}")
            return
        
        elif cmd == "done":
            # タスク完了報告
            task_id_arg = sys.argv[2] if len(sys.argv) > 2 else ""
            message_arg = sys.argv[3] if len(sys.argv) > 3 else ""
            
            # task_idが空または指定なしの場合は最新のタスクを使用
            if not task_id_arg:
                tasks = get_pending_tasks()
                if tasks:
                    task_id = tasks[-1]["id"]
                    # メッセージは2番目の引数が空なら3番目、それもなければデフォルト
                    message = message_arg or "タスクが完了しました"
                else:
                    print("❌ 保留中のタスクがありません")
                    return
            else:
                task_id = task_id_arg
                message = message_arg or "タスクが完了しました"
            
            if complete_task(task_id, True, f"✅ {message}", None):
                print(f"✅ タスク {task_id} の完了をLINEに通知しました")
                # 保留タスクから削除
                tasks = [t for t in get_pending_tasks() if t["id"] != task_id]
                with open(PENDING_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, ensure_ascii=False, indent=2)
            else:
                print(f"❌ 完了報告に失敗しました")
            return
        
        elif cmd == "error":
            # エラー報告
            task_id_arg = sys.argv[2] if len(sys.argv) > 2 else ""
            error_msg_arg = sys.argv[3] if len(sys.argv) > 3 else ""
            
            # task_idが空または指定なしの場合は最新のタスクを使用
            if not task_id_arg:
                tasks = get_pending_tasks()
                if tasks:
                    task_id = tasks[-1]["id"]
                    error_msg = error_msg_arg or "エラーが発生しました"
                else:
                    print("❌ 保留中のタスクがありません")
                    return
            else:
                task_id = task_id_arg
                error_msg = error_msg_arg or "エラーが発生しました"
            
            if complete_task(task_id, False, "タスクでエラーが発生しました", error_msg):
                print(f"⚠️ タスク {task_id} のエラーをLINEに通知しました")
                # 保留タスクから削除
                tasks = [t for t in get_pending_tasks() if t["id"] != task_id]
                with open(PENDING_TASKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(tasks, f, ensure_ascii=False, indent=2)
            else:
                print(f"❌ エラー報告に失敗しました")
            return
        
        elif cmd == "list":
            # 保留タスク一覧
            tasks = get_pending_tasks()
            if tasks:
                print("📋 保留中のタスク:")
                for task in tasks:
                    print(f"  - {task['id']}: {task.get('cursor_instruction', task.get('function'))}")
            else:
                print("✨ 保留中のタスクはありません")
            return
        
        else:
            print(f"""
使い方:
  python local_agent.py          # エージェント起動（タスクをポーリング）
  python local_agent.py test     # 接続テスト
  python local_agent.py list     # 保留タスク一覧
  python local_agent.py done [TASK_ID] [メッセージ]  # タスク完了報告
  python local_agent.py error TASK_ID "エラー内容"   # エラー報告
  python local_agent.py config   # 設定を表示
  python local_agent.py set KEY VALUE  # 設定を変更
            """)
            return
    
    run_agent()


if __name__ == "__main__":
    main()
