#!/usr/bin/env python3
"""
ナレッジ同期スクリプト
Google Docsからノウハウを取得してサーバーに同期
"""

import os
import sys
import json
import hashlib
import requests
from pathlib import Path
from datetime import datetime

# 親ディレクトリをパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent))

# 設定
DOCS_TO_SYNC = [
    {
        "name": "過去の質問回答",
        "doc_id": "1PejiD54CIAQmZZdzc-7K-4UyajXPOGXiJdlVRxKiuaU",
    }
]

SKILLS_DIR = Path(__file__).parent.parent / "line_bot" / "skills"
LOCAL_SKILLS_DIR = Path(__file__).parent.parent.parent / "Skills"
STRUCTURED_SKILLS_TO_SYNC = [
    {
        "output_name": "受講生質問回答ルール",
        "parts": [
            Path("4_CS") / "student-question-answering" / "references" / "workflow.md",
        ],
    },
    {
        "output_name": "Meta広告アカウントエラー対応",
        "parts": [
            Path("1_広告") / "meta-ad-account-error-operations" / "references" / "workflow.md",
        ],
    },
]
# 状態ファイル（コードと分離 — rsync --delete でも消えない場所に配置）
_STATE_DIR = Path.home() / "agents" / "data"
_STATE_DIR.mkdir(parents=True, exist_ok=True)
STATE_FILE = _STATE_DIR / "sync_state.json"

# config.json読み込み（状態ファイルと同じ場所に集約）
CONFIG_FILE = _STATE_DIR / "config.json"
config = {}
if CONFIG_FILE.exists():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)


def get_docs_service():
    """Google Docs APIサービスを取得"""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        
        token_file = Path(__file__).parent.parent / "credentials" / "token.json"
        if not token_file.exists():
            print("⚠️ token.json が見つかりません")
            return None
        
        creds = Credentials.from_authorized_user_file(str(token_file))
        return build("docs", "v1", credentials=creds)
    except Exception as e:
        print(f"⚠️ Docs API初期化エラー: {e}")
        return None


def read_doc_content(service, doc_id: str) -> str:
    """Google Docsの内容を読み取り"""
    try:
        doc = service.documents().get(documentId=doc_id).execute()
        content = doc.get("body", {}).get("content", [])
        
        text_parts = []
        for element in content:
            if "paragraph" in element:
                for para_element in element["paragraph"].get("elements", []):
                    if "textRun" in para_element:
                        text_parts.append(para_element["textRun"].get("content", ""))
        
        return "".join(text_parts)
    except Exception as e:
        print(f"⚠️ ドキュメント読み取りエラー: {e}")
        return ""


def get_content_hash(content: str) -> str:
    """コンテンツのハッシュを取得"""
    return hashlib.md5(content.encode()).hexdigest()


def load_state() -> dict:
    """同期状態を読み込み"""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_state(state: dict):
    """同期状態を保存"""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def sync_docs():
    """Google Docsからノウハウを同期"""
    service = get_docs_service()
    if not service:
        return False
    
    state = load_state()
    updated = False
    
    for doc_config in DOCS_TO_SYNC:
        name = doc_config["name"]
        doc_id = doc_config["doc_id"]
        
        print(f"📄 {name} をチェック中...")
        
        content = read_doc_content(service, doc_id)
        if not content:
            continue
        
        content_hash = get_content_hash(content)
        last_hash = state.get(doc_id, {}).get("hash", "")
        
        if content_hash != last_hash:
            print(f"   📝 更新を検出！保存中...")
            
            # Skillsディレクトリに保存
            skill_file = LOCAL_SKILLS_DIR / f"{name}.md"
            skill_file.write_text(content, encoding="utf-8")
            
            # サーバー用ディレクトリにもコピー
            server_skill_file = SKILLS_DIR / f"{name}.md"
            if SKILLS_DIR.exists():
                server_skill_file.write_text(content, encoding="utf-8")
            
            state[doc_id] = {
                "name": name,
                "hash": content_hash,
                "updated_at": datetime.now().isoformat()
            }
            updated = True
            print(f"   ✅ {name} を更新しました")
        else:
            print(f"   ✨ 変更なし")
    
    save_state(state)
    return updated


def sync_local_skills():
    """ローカルのSkillsをサーバーディレクトリにコピー"""
    if not LOCAL_SKILLS_DIR.exists():
        return
    
    if not SKILLS_DIR.exists():
        SKILLS_DIR.mkdir(parents=True, exist_ok=True)

    synced_count = 0
    for skill_file in LOCAL_SKILLS_DIR.glob("*.md"):
        dest_file = SKILLS_DIR / skill_file.name
        content = skill_file.read_text(encoding="utf-8")
        dest_file.write_text(content, encoding="utf-8")
        synced_count += 1

    for skill_config in STRUCTURED_SKILLS_TO_SYNC:
        parts = []
        for relative_path in skill_config["parts"]:
            source_file = LOCAL_SKILLS_DIR / relative_path
            if not source_file.exists():
                print(f"⚠️ structured skill が見つかりません: {relative_path}")
                continue
            parts.append(source_file.read_text(encoding="utf-8").strip())

        if not parts:
            continue

        dest_file = SKILLS_DIR / f"{skill_config['output_name']}.md"
        dest_file.write_text("\n\n".join(parts).strip() + "\n", encoding="utf-8")
        synced_count += 1

    print(f"📚 {synced_count} 件のSkillsを同期しました")


if __name__ == "__main__":
    print("=" * 40)
    print("📚 ナレッジ同期")
    print("=" * 40)
    
    # Google Docsから同期
    sync_docs()
    
    # ローカルSkillsをサーバーディレクトリにコピー
    sync_local_skills()
    
    print("完了")
