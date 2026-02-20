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
import requests
from datetime import datetime, timedelta
from pathlib import Path

# ---- プロファイルパス ----
_AGENT_DIR = Path(__file__).parent
_PROJECT_ROOT = _AGENT_DIR.parent.parent
PEOPLE_PROFILES_JSON = _PROJECT_ROOT / "Master" / "people-profiles.json"
PEOPLE_IDENTITIES_JSON = _PROJECT_ROOT / "Master" / "people-identities.json"
SELF_IDENTITY_MD = _PROJECT_ROOT / "Master" / "self_clone" / "projects" / "kohara" / "1_Core" / "IDENTITY.md"


def _load_self_identity() -> str:
    """甲原海人の言語スタイル定義を読み込む"""
    try:
        if SELF_IDENTITY_MD.exists():
            return SELF_IDENTITY_MD.read_text(encoding="utf-8")
    except Exception:
        pass
    return ""

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
    """macOSデスクトップ通知を表示"""
    # メッセージ内の特殊文字をエスケープ
    message = message.replace('"', '\\"').replace('\n', ' ')
    title = title.replace('"', '\\"')
    
    sound_cmd = 'sound name "Glass"' if sound else ""
    
    script = f'''
    display notification "{message}" with title "{title}" {sound_cmd}
    '''
    
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except Exception as e:
        print(f"通知エラー: {e}")


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


def lookup_sender_profile(sender_name: str):
    """LINE送信者名からプロファイルを逆引き。Noneなら未登録。"""
    if not sender_name:
        return None

    identities = _load_json_safe(PEOPLE_IDENTITIES_JSON)
    profiles = _load_json_safe(PEOPLE_PROFILES_JSON)

    # identities で line_display_name / line_my_name → Addness名 を逆引き
    matched_key = None
    for addness_name, info in identities.items():
        if sender_name in (info.get("line_display_name", ""), info.get("line_my_name", "")):
            matched_key = addness_name
            break

    # identitiesで見つからなければAddness名と直接比較
    if not matched_key and sender_name in profiles:
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

        # ===== 返信案生成タスクの専用処理 =====
        if function_name == "generate_reply_suggestion":
            original_message = arguments.get("original_message", task.get("original_text", ""))
            message_id = arguments.get("message_id", "")
            group_name = arguments.get("group_name", "")
            msg_id_short = message_id[:4] if message_id else "----"

            # プロファイルから送信者情報を取得
            profile = lookup_sender_profile(sender_name)
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

            prompt = f"""あなたは甲原海人本人として返信を書きます。
以下の【言語スタイル定義】に厳密に従い、甲原海人が実際に送るようなメッセージを生成してください。

【言語スタイル定義】
{identity_style}

---

【送信者情報】
{sender_name}{category_line}
{profile_info}

【受信メッセージ】
グループ: {group_name}
内容: {original_message}

【出力ルール】
- 甲原海人が実際に送る文章のみ出力（説明・前置き不要）
- 50文字以内を目安に簡潔に
- 相手との関係性（{tone_guide or '関係性に応じたトーン'}）を反映
- スタイル定義の口調・語尾の癖をそのまま再現する

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
            profile_badge = f"👤 {sender_name}{category_line}" if profile else f"👤 {sender_name}"
            result = (
                f"💡 返信案\n"
                f"{profile_badge}\n"
                f"\n"
                f"グループ: {group_name}\n"
                f"「{original_message[:80]}{'...' if len(original_message) > 80 else ''}」\n"
                f"\n"
                f"返信案:\n{reply_suggestion}\n"
                f"\n"
                f"─────────────\n"
                f"このメッセージにリプライ:\n"
                f"1 → 承認して送信\n"
                f"2 [別の内容] → 編集して送信"
            )
            return True, result

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
    
    print("📋 日報入力タスク: 常にCursorで処理")
    
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
                    
                    # 日報入力などCursorが必要なタスク、またはClaude APIが使えない場合はCursorで処理
                    cursor_required_tasks = ["input_daily_report"]
                    use_cursor = (auto_mode == "cursor") or (function_name in cursor_required_tasks) or (not claude_api_available)
                    
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
