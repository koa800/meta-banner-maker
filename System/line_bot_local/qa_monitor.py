#!/usr/bin/env python3
"""
Q&A質問監視モジュール
複数の「回答用」シートをポーリングして新着質問を検知
"""

import os
import sys
import re
import json
import hashlib
from datetime import datetime
from pathlib import Path

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

# Google Sheets API
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

# 設定
QA_SPREADSHEET_ID = "14y1o3dwf0jA_xpVrsHbho8Msu-i56q3CXtsbLNHtUC4"

# 監視対象シートの設定（シートごとにカラムマッピングが異なる）
# Lステップ系シート: F列=目的, G列=やったこと, H列=質問, N列=L-STEPリンク
SHEET_CONFIGS = {
    "回答用：サポートLINE": {
        "col_timestamp": 1,    # B列: 回答日時
        "col_user_name": 4,    # E列: 名前
        "col_user_id": 2,      # C列: 回答者ID（参考用）
        "col_lstep_link": 13,  # N列: L-STEPリンク（member=xxxからUID取得）
        "col_goal": 5,         # F列: 直近ゴール（目的）
        "col_action": 6,       # G列: 達成のための「ToDo」（やったこと）
        "col_question": 7,     # H列: 取り組んだ「結果や疑問点」（質問内容）
        "col_status": 14,      # O列: 回答済み（TRUE/FALSE）
        "col_answer": 16,      # Q列: 回答
        "range": "A:R",
        "source": "Lステップ",
    },
    "回答用：スタンダード": {
        "col_timestamp": 1,    # B列: 回答日時
        "col_user_name": 4,    # E列: 名前
        "col_user_id": 2,      # C列: 回答者ID（参考用）
        "col_lstep_link": 13,  # N列: L-STEPリンク（member=xxxからUID取得）
        "col_goal": 5,         # F列: 直近ゴール（目的）
        "col_action": 6,       # G列: 達成のための「ToDo」（やったこと）
        "col_question": 7,     # H列: 取り組んだ「結果や疑問点」（質問内容）
        "col_status": 14,      # O列: 回答済み（TRUE/FALSE）
        "col_answer": 16,      # Q列: 回答
        "range": "A:R",
        "source": "Lステップ",
    },
    "回答用：エリート": {
        "col_timestamp": 1,    # B列: 回答日時
        "col_user_name": 4,    # E列: 名前
        "col_user_id": 2,      # C列: 回答者ID（参考用）
        "col_lstep_link": 13,  # N列: L-STEPリンク（member=xxxからUID取得）
        "col_goal": 5,         # F列: 直近ゴール（目的）
        "col_action": 6,       # G列: 達成のための「ToDo」（やったこと）
        "col_question": 7,     # H列: 取り組んだ「結果や疑問点」（質問内容）
        "col_status": 14,      # O列: 回答済み（TRUE/FALSE）
        "col_answer": 16,      # Q列: 回答
        "range": "A:R",
        "source": "Lステップ",
    },
    "回答用：プライム": {
        "col_timestamp": 1,    # B列: 回答日時
        "col_user_name": 4,    # E列: 名前
        "col_user_id": 2,      # C列: 回答者ID（参考用）
        "col_lstep_link": 13,  # N列: L-STEPリンク（member=xxxからUID取得）
        "col_goal": 5,         # F列: 直近ゴール（目的）
        "col_action": 6,       # G列: 達成のための「ToDo」（やったこと）
        "col_question": 7,     # H列: 取り組んだ「結果や疑問点」（質問内容）
        "col_status": 14,      # O列: 回答済み（TRUE/FALSE）
        "col_answer": 16,      # Q列: 回答
        "range": "A:R",
        "source": "Lステップ",
    },
    "回答用：SLS": {
        "col_timestamp": 1,    # B列: 回答日時
        "col_user_name": 4,    # E列: お名前
        "col_user_id": 2,      # C列: 回答者ID（参考用）
        "col_lstep_link": 13,  # N列: L-STEPリンク（member=xxxからUID取得）
        "col_goal": -1,        # SLSには目的列なし
        "col_action": -1,      # SLSにはやったこと列なし
        "col_question": 7,     # H列: 質問内容を教えてください！
        "col_status": 9,       # J列: 回答済み（TRUE/FALSE）
        "col_answer": 11,      # L列: 回答
        "range": "A:N",
        "source": "Success Learning AI",
    },
}

# 状態ファイル（コードと分離 — rsync --delete でも消えない場所に配置）
_STATE_DIR = Path.home() / "agents" / "data"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = _STATE_DIR / "qa_monitor_state.json"


_STATE_BACKUP = STATE_FILE.with_suffix(".json.bak")
_STATE_MIN_SENT_IDS = 100  # この件数以下でバックアップにフォールバック


def load_state() -> dict:
    """監視状態を読み込む（破損・消失時はバックアップから自動復元）"""
    state = _try_load_json(STATE_FILE)

    # 整合性チェック: sent_ids が不自然に少ない場合はバックアップから復元
    if state and len(state.get("sent_ids", [])) >= _STATE_MIN_SENT_IDS:
        return state

    # メインファイルが破損 or sent_ids が空 → バックアップを試す
    backup = _try_load_json(_STATE_BACKUP)
    if backup and len(backup.get("sent_ids", [])) >= _STATE_MIN_SENT_IDS:
        print(f"  ⚠️ qa_monitor_state.json が破損または消失 → バックアップから復元（{len(backup.get('sent_ids', []))}件）")
        # バックアップからメインファイルを復元
        _atomic_write(STATE_FILE, backup)
        return backup

    # 両方ない場合（初回起動）
    if state:
        return state
    return {
        "last_check": None,
        "sent_ids": [],
    }


def _try_load_json(path: Path) -> dict | None:
    """JSONファイルを安全に読み込む"""
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        if not content.strip():
            return None
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError):
        return None


def save_state(state: dict):
    """監視状態をアトミックに保存（tmp→rename + バックアップ）"""
    # メインファイルが存在し、十分なsent_idsがあればバックアップ
    if STATE_FILE.exists():
        existing = _try_load_json(STATE_FILE)
        if existing and len(existing.get("sent_ids", [])) >= _STATE_MIN_SENT_IDS:
            _atomic_write(_STATE_BACKUP, existing)
    _atomic_write(STATE_FILE, state)


def _atomic_write(path: Path, data: dict):
    """アトミック書き込み（tmp→rename で中間状態を防ぐ）"""
    tmp = path.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.rename(path)
    except Exception as e:
        print(f"  ⚠️ {path.name} 保存エラー: {e}")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def get_sheets_service():
    """Google Sheets APIサービスを取得"""
    if not GOOGLE_API_AVAILABLE:
        return None

    # credentials/token.json のパスを探す（複数パス対応）
    _parent = Path(__file__).resolve().parent.parent
    candidates = [
        _parent / "credentials" / "token.json",
        _parent / "System" / "credentials" / "token.json",
        Path(__file__).parent.parent / "credentials" / "token.json",
        Path(__file__).parent.parent / "System" / "credentials" / "token.json",
    ]
    token_file = None
    for c in candidates:
        if c.exists():
            token_file = c
            break

    if not token_file:
        return None
    
    try:
        with open(token_file, "r") as f:
            token_data = json.load(f)
        
        credentials = Credentials.from_authorized_user_info(token_data)
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except Exception as e:
        print(f"  ⚠️ Sheets API初期化エラー: {e}")
        return None


def generate_question_id(sheet_name: str, row_data: list, row_index: int, config: dict) -> str:
    """質問IDを生成（シート名を含めてユニークにする）"""
    timestamp = row_data[config["col_timestamp"]] if len(row_data) > config["col_timestamp"] else ""
    unique_str = f"{sheet_name}_{timestamp}_{row_index}"
    return hashlib.md5(unique_str.encode()).hexdigest()[:12]


def check_new_questions(service) -> list[dict]:
    """全監視対象シートから新着質問をチェック
    
    検出条件:
    - 質問内容（H列）が存在する
    - 回答済み（O列/J列）がFALSEまたは空
    - まだサーバーに送信していない（sent_idsに含まれていない）
    """
    state = load_state()
    sent_ids = set(state.get("sent_ids", []))
    all_new_questions = []
    
    for sheet_name, config in SHEET_CONFIGS.items():
        try:
            # データ範囲を取得
            result = service.spreadsheets().values().get(
                spreadsheetId=QA_SPREADSHEET_ID,
                range=f"{sheet_name}!{config['range']}"
            ).execute()
            
            rows = result.get('values', [])
            
            if len(rows) <= 1:
                continue
            
            for i, row in enumerate(rows[1:], start=2):  # ヘッダースキップ
                # 必要なカラムが存在するか確認
                col_question = config["col_question"]
                col_status = config["col_status"]
                
                if len(row) <= col_question:
                    continue
                
                question = row[col_question].strip() if len(row) > col_question else ""
                status = row[col_status].strip().upper() if len(row) > col_status else ""
                
                # 質問があり、回答済みでない行を検出
                if question and status not in ["TRUE", "回答済み"]:
                    # 質問のユニークIDを生成
                    question_id = generate_question_id(sheet_name, row, i, config)
                    
                    # 既にサーバーに送信済みならスキップ
                    if question_id in sent_ids:
                        continue
                    
                    # 目的とやったことを取得（存在する場合）
                    col_goal = config.get("col_goal", -1)
                    col_action = config.get("col_action", -1)
                    goal = row[col_goal].strip() if col_goal >= 0 and len(row) > col_goal else ""
                    action = row[col_action].strip() if col_action >= 0 and len(row) > col_action else ""
                    
                    # L-STEPリンクからmember ID（uid）を抽出
                    col_lstep_link = config.get("col_lstep_link", -1)
                    lstep_uid = ""
                    if col_lstep_link >= 0 and len(row) > col_lstep_link:
                        lstep_link = row[col_lstep_link]
                        # URLから member= の値を抽出
                        match = re.search(r'member=(\d+)', lstep_link)
                        if match:
                            lstep_uid = match.group(1)
                    
                    question_data = {
                        "id": question_id,
                        "sheet_name": sheet_name,
                        "row_index": i,
                        "timestamp": row[config["col_timestamp"]] if len(row) > config["col_timestamp"] else "",
                        "user_name": row[config["col_user_name"]] if len(row) > config["col_user_name"] else "不明",
                        "user_id": lstep_uid,   # L-STEPリンクから抽出したUID
                        "goal": goal,           # F列: 目的
                        "action": action,       # G列: やったこと
                        "question": question,   # H列: 質問
                        "source": config["source"],
                    }
                    all_new_questions.append(question_data)
        
        except Exception as e:
            print(f"  ⚠️ シート「{sheet_name}」のチェックエラー: {e}")
            continue
    
    # 状態を更新
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    
    return all_new_questions


def mark_as_sent(question_id: str):
    """質問IDをサーバー送信済みとしてマーク"""
    state = load_state()
    if "sent_ids" not in state:
        state["sent_ids"] = []
    if question_id not in state["sent_ids"]:
        state["sent_ids"].append(question_id)
    save_state(state)


def update_answer_status(service, sheet_name: str, row_index: int, status: str = "TRUE") -> bool:
    """スプレッドシートの回答済みステータスを更新"""
    if sheet_name not in SHEET_CONFIGS:
        return False
    
    config = SHEET_CONFIGS[sheet_name]
    col_status = config["col_status"]
    
    # 列番号をアルファベットに変換
    col_letter = chr(ord('A') + col_status)
    
    try:
        service.spreadsheets().values().update(
            spreadsheetId=QA_SPREADSHEET_ID,
            range=f"{sheet_name}!{col_letter}{row_index}",
            valueInputOption="USER_ENTERED",
            body={"values": [[status]]}
        ).execute()
        return True
    except Exception as e:
        print(f"  ⚠️ ステータス更新エラー: {e}")
        return False


def write_answer_to_sheet(service, sheet_name: str, row_index: int, answer: str) -> bool:
    """スプレッドシートの「回答」列に回答を書き込み（回答済みは講師が手動でチェック）"""
    if sheet_name not in SHEET_CONFIGS:
        print(f"  ⚠️ 未知のシート: {sheet_name}")
        return False
    
    config = SHEET_CONFIGS[sheet_name]
    col_answer = config.get("col_answer", 16)  # デフォルトはQ列
    
    # 列番号をアルファベットに変換
    answer_letter = chr(ord('A') + col_answer)
    
    try:
        # 回答列に回答を書き込み
        service.spreadsheets().values().update(
            spreadsheetId=QA_SPREADSHEET_ID,
            range=f"{sheet_name}!{answer_letter}{row_index}",
            valueInputOption="USER_ENTERED",
            body={"values": [[answer]]}
        ).execute()
        
        print(f"  ✅ 回答書き込み完了: {sheet_name} 行{row_index} {answer_letter}列")
        return True
    except Exception as e:
        print(f"  ⚠️ スプレッドシート書き込みエラー: {e}")
        return False


def reset_state():
    """監視状態をリセット"""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("✅ 監視状態をリセットしました")


def mark_all_existing_as_processed(service):
    """現在存在するすべての質問を処理済みとしてマーク（sent_idsに登録）"""
    state = load_state()
    sent_ids = set(state.get("sent_ids", []))
    total_marked = 0

    for sheet_name, config in SHEET_CONFIGS.items():
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=QA_SPREADSHEET_ID,
                range=f"{sheet_name}!{config['range']}"
            ).execute()

            rows = result.get('values', [])

            if len(rows) <= 1:
                continue

            for i, row in enumerate(rows[1:], start=2):
                qid = generate_question_id(sheet_name, row, i, config)
                if qid not in sent_ids:
                    sent_ids.add(qid)
                    total_marked += 1

            print(f"  {sheet_name}: {len(rows) - 1} 行")

        except Exception as e:
            print(f"  ⚠️ シート「{sheet_name}」のエラー: {e}")

    state["sent_ids"] = list(sent_ids)
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    print(f"\n✅ 合計 {total_marked} 件を処理済みとしてマークしました")


# CLI用
if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        
        if cmd == "check":
            print("🔍 新着質問をチェック中...")
            print(f"   監視対象: {len(SHEET_CONFIGS)} シート")
            service = get_sheets_service()
            if not service:
                print("❌ Google Sheets APIの初期化に失敗しました")
                sys.exit(1)
            
            questions = check_new_questions(service)
            
            if questions:
                print(f"\n📩 {len(questions)} 件の新着質問:\n")
                for q in questions:
                    print(f"  ID: {q['id']}")
                    print(f"  シート: {q['sheet_name']}")
                    print(f"  ソース: {q['source']}")
                    print(f"  ユーザー: {q['user_name']}")
                    print(f"  質問: {q['question'][:60]}...")
                    print()
            else:
                print("✨ 新着質問はありません")
        
        elif cmd == "reset":
            reset_state()
        
        elif cmd == "init":
            print("📋 既存のデータを処理済みとしてマーク中...")
            service = get_sheets_service()
            if not service:
                print("❌ Google Sheets APIの初期化に失敗しました")
                sys.exit(1)
            mark_all_existing_as_processed(service)
        
        elif cmd == "state":
            state = load_state()
            print(json.dumps(state, indent=2, ensure_ascii=False))
        
        else:
            print("""
使い方:
  python qa_monitor.py check   # 新着質問をチェック
  python qa_monitor.py init    # 既存データを処理済みにマーク（初回セットアップ用）
  python qa_monitor.py state   # 監視状態を表示
  python qa_monitor.py reset   # 監視状態をリセット
""")
    else:
        print("引数を指定してください（check, init, state, reset）")
