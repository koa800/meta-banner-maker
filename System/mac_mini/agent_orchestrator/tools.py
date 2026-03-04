"""
Tool wrappers for the agent orchestrator.
Each tool wraps an existing script in System/ with a uniform interface.
"""

import subprocess
import os
import sys
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from .shared_logger import get_logger

logger = get_logger("tools")

_orch_dir = os.path.dirname(os.path.abspath(__file__))   # agent_orchestrator/
SYSTEM_DIR = os.path.dirname(os.path.dirname(_orch_dir))  # System/
VENV_PYTHON = os.path.expanduser("~/agent-env/bin/python3")


def _run_claude_cli(prompt: str, model: str = "claude-sonnet-4-6",
                    max_turns: int = 3, timeout: int = 120) -> str:
    """Claude Code CLI でテキスト生成。サブスク課金でAPI消費なし。"""
    env = os.environ.copy()
    path = env.get("PATH", "")
    if "/opt/homebrew/bin" not in path:
        env["PATH"] = f"/opt/homebrew/bin:{path}"
    claude_cmd = "/opt/homebrew/bin/claude"
    cmd = [claude_cmd, "-p", "--model", model, "--max-turns", str(max_turns), prompt]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    if result.returncode != 0:
        raise RuntimeError(f"Claude CLI failed (code={result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()


@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""
    return_code: int = 0


def _run_script(script_path: str, args: list = None, timeout: int = 300, cwd: str = None) -> ToolResult:
    """Run a Python script with the agent venv interpreter."""
    python = VENV_PYTHON if os.path.exists(VENV_PYTHON) else sys.executable
    cmd = [python, script_path] + (args or [])
    work_dir = cwd or os.path.dirname(script_path)
    script_name = os.path.basename(script_path)

    logger.info(f"Running: {script_name}", extra={"script": script_path, "args": args})
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=work_dir,
            env={**os.environ, "PYTHONUNBUFFERED": "1"}
        )
        stderr = result.stderr.strip()
        stdout = result.stdout.strip()
        # stderrが空でスクリプト失敗時はstdoutをエラーメッセージとして使う
        error_msg = stderr if stderr else (stdout if result.returncode != 0 else "")
        if result.returncode != 0:
            error_lines = (stderr or stdout).strip().split("\n")
            logger.error(
                f"Script failed: {script_name}",
                extra={
                    "script": script_path,
                    "return_code": result.returncode,
                    "stderr_tail": "\n".join(error_lines[-10:]),
                    "error": {
                        "type": "ScriptError",
                        "message": error_lines[-1] if error_lines else "unknown",
                        "traceback": error_lines[-15:],
                    },
                },
            )
        return ToolResult(
            success=result.returncode == 0,
            output=stdout,
            error=error_msg,
            return_code=result.returncode
        )
    except subprocess.TimeoutExpired:
        logger.error(
            f"Script timeout: {script_name}",
            extra={
                "script": script_path,
                "timeout": timeout,
                "error": {"type": "TimeoutError", "message": f"Timeout after {timeout}s"},
            },
        )
        return ToolResult(success=False, output="", error=f"Timeout after {timeout}s", return_code=-1)
    except Exception as e:
        logger.exception(
            f"Script exception: {script_name}",
            extra={
                "script": script_path,
                "error": {"type": type(e).__name__, "message": str(e)},
            },
        )
        return ToolResult(success=False, output="", error=str(e), return_code=-1)


# --------------- Mail ---------------

def mail_run(account: str = "personal") -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "mail_manager.py"),
        ["--account", account, "run"]
    )

def mail_status(account: str = "personal") -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "mail_manager.py"),
        ["--account", account, "status"]
    )


def _decode_mime_header(header: str) -> str:
    """MIMEエンコードされたメールヘッダーをデコード"""
    from email.header import decode_header
    parts = []
    for data, charset in decode_header(header):
        if isinstance(data, bytes):
            parts.append(data.decode(charset or "utf-8", errors="replace"))
        else:
            parts.append(data)
    return "".join(parts)


def _get_imap_body(msg, max_len: int = 1000) -> str:
    """メールからtext/plainパートを抽出（マルチパート対応）"""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    return payload.decode(charset, errors="replace")[:max_len]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            return payload.decode(charset, errors="replace")[:max_len]
    return ""


def dsinsight_mail_check() -> ToolResult:
    """IMAP経由でk.kohara@addness.co.jpからDS.INSIGHTメールを検索・取得する（直近7日）"""
    import imaplib
    import email
    import json
    from email.header import decode_header
    from pathlib import Path
    from datetime import datetime, timedelta

    creds_path = Path(SYSTEM_DIR) / "credentials" / "onamae_imap.json"
    if not creds_path.exists():
        return ToolResult(success=False, output="", error="IMAP認証情報なし: onamae_imap.json")

    with open(creds_path) as f:
        creds = json.load(f)

    try:
        conn = imaplib.IMAP4_SSL(creds["server"], creds.get("port", 993))
        conn.login(creds["username"], creds["password"])
        conn.select("INBOX", readonly=True)

        since = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        _, msg_nums = conn.search(None, f'(SINCE {since} SUBJECT "DS.INSIGHT")')

        if not msg_nums[0]:
            conn.logout()
            return ToolResult(success=True, output="DS.INSIGHTメールなし")

        items = []
        for num in msg_nums[0].split()[-10:]:
            _, data = conn.fetch(num, "(RFC822)")
            msg = email.message_from_bytes(data[0][1])
            subject = _decode_mime_header(msg.get("Subject", ""))
            body = _get_imap_body(msg, max_len=1000)
            msg_id = msg.get("Message-ID", num.decode())
            items.append({"id": msg_id, "subject": subject, "body": body})

        conn.logout()
        return ToolResult(success=True, output=json.dumps(items, ensure_ascii=False))

    except Exception as e:
        logger.error(f"DS.INSIGHT IMAP検索エラー: {e}")
        return ToolResult(success=False, output="", error=str(e))


# --------------- Calendar ---------------

def calendar_list(account: str = "personal", days: int = 7, target_date: str = None) -> ToolResult:
    """カレンダーの予定を取得。
    target_date: 特定日 (YYYY-MM-DD)。未指定の場合は本日から days 日分（ただし calendar_manager.py
    は target_date なしで次30日分を返す）。days=1 かつ target_date 未指定なら今日の日付を使用。
    """
    from datetime import date
    # OAuthトークンが存在しない場合は即座にエラー返却（ヘッドレス環境でのハング防止）
    token_file = "token_calendar.json" if account == "kohara" else f"token_calendar_{account}.json"
    token_path = os.path.join(SYSTEM_DIR, token_file)
    if not os.path.exists(token_path):
        return ToolResult(
            success=False, output="",
            error=f"Calendar token not found: {token_path} — run calendar auth setup first",
            return_code=1
        )
    args = ["--account", account, "list"]
    if target_date:
        args.append(target_date)
    elif days == 1:
        args.append(date.today().isoformat())
    # days>1 の場合は target_date なしで次30日分を返す（calendar_manager.py の仕様）
    return _run_script(os.path.join(SYSTEM_DIR, "calendar_manager.py"), args)


# --------------- Sheets ---------------

def sheets_read(url_or_id: str, sheet_name: str = None, range_str: str = None) -> ToolResult:
    args = ["read", url_or_id]
    if sheet_name:
        args.append(sheet_name)
    if range_str:
        args.append(range_str)
    return _run_script(os.path.join(SYSTEM_DIR, "sheets_manager.py"), args)


def sheets_sync(sheet_id: str = None) -> ToolResult:
    """Master/sheets/ の管理シートを同期（CSV キャッシュ更新）"""
    args = []
    if sheet_id:
        args.extend(["--id", sheet_id])
    return _run_script(os.path.join(SYSTEM_DIR, "sheets_sync.py"), args, timeout=600)


# --------------- Docs ---------------

def docs_read(url_or_id: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "docs_manager.py"),
        ["read", url_or_id]
    )


# --------------- AI News ---------------

def ai_news_notify() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "ai_news_notifier.py"), timeout=600)


# --------------- Addness ---------------

def addness_fetch() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "addness_fetcher.py"), timeout=600)

def addness_to_context() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "addness_to_context.py"))


# --------------- Q&A ---------------

def qa_search(query: str, top_k: int = 5) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "qa_search.py"),
        ["search", query, str(top_k)]
    )

def qa_answer(question: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "qa_search.py"),
        ["answer", question]
    )

def qa_stats() -> ToolResult:
    return _run_script(os.path.join(SYSTEM_DIR, "qa_search.py"), ["stats"])


# --------------- Who to Ask ---------------

def who_to_ask(task_description: str) -> ToolResult:
    return _run_script(
        os.path.join(SYSTEM_DIR, "who_to_ask.py"),
        [task_description]
    )


# --------------- KPI ---------------

def kpi_refresh() -> ToolResult:
    """日別タブの既存データから月別タブを再計算"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["refresh"])


def kpi_process() -> ToolResult:
    """元データの完了エントリを検知 → CSVから日別/月別に投入"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["process"])


def kpi_check_today() -> ToolResult:
    """2日前の日付が元データで完了になっているかチェック"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_processor.py"), ["check_today"])


def kpi_cache_build() -> ToolResult:
    """ローカルCSVキャッシュからkpi_summary.jsonを再構築"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_cache_builder.py"), [])


def kpi_anomaly_check() -> ToolResult:
    """KPIデータの異常検知（日別・月別の変動を分析し媒体別にドリルダウン）"""
    return _run_script(os.path.join(SYSTEM_DIR, "kpi_anomaly_detector.py"), ["--verbose"])


# --------------- Utility ---------------

def shell_command(cmd: str, timeout: int = 60) -> ToolResult:
    """Run an arbitrary shell command (use with caution)."""
    logger.warning(f"Shell command: {cmd}", extra={"command": cmd})
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            logger.error(
                f"Shell command failed",
                extra={
                    "command": cmd,
                    "return_code": result.returncode,
                    "error": {"type": "ShellError", "message": result.stderr.strip()[-200:]},
                },
            )
        return ToolResult(
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
            return_code=result.returncode
        )
    except subprocess.TimeoutExpired:
        logger.error(f"Shell timeout", extra={
            "command": cmd, "error": {"type": "TimeoutError", "message": f"Timeout after {timeout}s"},
        })
        return ToolResult(success=False, output="", error=f"Timeout after {timeout}s", return_code=-1)
    except Exception as e:
        logger.exception(f"Shell exception", extra={
            "command": cmd, "error": {"type": type(e).__name__, "message": str(e)},
        })
        return ToolResult(success=False, output="", error=str(e), return_code=-1)


# --------------- Log Rotate ---------------

def log_rotate() -> ToolResult:
    """ログファイルのローテーション（50MB超を圧縮、30日超のgzを削除）"""
    import glob
    import gzip
    import shutil
    from datetime import datetime as _dt

    log_dir = os.path.join(_orch_dir, "logs")
    if not os.path.isdir(log_dir):
        return ToolResult(success=True, output="ログディレクトリなし（スキップ）")

    max_size_mb = 50
    keep_days = 30
    rotated = []

    for logfile in glob.glob(os.path.join(log_dir, "*.log")):
        try:
            size_mb = os.path.getsize(logfile) / (1024 * 1024)
            if size_mb > max_size_mb:
                ts = _dt.now().strftime("%Y%m%d_%H%M%S")
                archive = f"{logfile}.{ts}.gz"
                with open(logfile, "rb") as f_in, gzip.open(archive, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
                # 元ファイルをクリア
                with open(logfile, "w") as f:
                    pass
                rotated.append(f"{os.path.basename(logfile)} ({size_mb:.0f}MB)")
        except Exception as e:
            logger.warning(f"Log rotate error for {logfile}: {e}")

    # 古いgzファイルを削除
    import time
    cutoff = time.time() - keep_days * 86400
    deleted = 0
    for gz in glob.glob(os.path.join(log_dir, "*.gz")):
        try:
            if os.path.getmtime(gz) < cutoff:
                os.unlink(gz)
                deleted += 1
        except Exception as e:
            logger.warning(f"Old gz delete error for {gz}: {e}")

    msg = f"ローテーション: {len(rotated)}ファイル / 削除: {deleted}ファイル"
    if rotated:
        msg += f"\n  対象: {', '.join(rotated)}"
    return ToolResult(success=True, output=msg)


# --------------- Git Sync ---------------

def git_pull_sync() -> ToolResult:
    """GitHubからpull → ローカルデプロイ"""
    sync_script = os.path.join(SYSTEM_DIR, "mac_mini", "git_pull_sync.sh")
    return shell_command(f"bash {sync_script}", timeout=120)


# --------------- Group Log ---------------

def fetch_group_log(date: str = None) -> ToolResult:
    """Renderサーバーから日次グループログを取得"""
    import json as _json
    import requests as _requests

    server_url = os.environ.get("LINE_BOT_SERVER_URL", "https://line-mention-bot-mmzu.onrender.com")
    agent_token = os.environ.get("AGENT_TOKEN", "")
    if not agent_token:
        return ToolResult(success=False, output="", error="AGENT_TOKEN not set")

    params = {}
    if date:
        params["date"] = date
    try:
        resp = _requests.get(
            f"{server_url}/api/group-log",
            headers={"Authorization": f"Bearer {agent_token}"},
            params=params,
            timeout=45,
        )
        if resp.status_code == 200:
            data = resp.json()
            return ToolResult(success=True, output=_json.dumps(data, ensure_ascii=False))
        else:
            return ToolResult(success=False, output="", error=f"HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        return ToolResult(success=False, output="", error=str(e))


# --------------- People Profiles ---------------

def update_people_profiles(person_name: str, group_insights: dict, comm_profile_updates: dict = None) -> ToolResult:
    """profiles.json の指定人物に group_insights / comm_profile を書き込む（既存フィールドには一切触れない）"""
    import json as _json
    import tempfile

    master_dir = os.path.expanduser(
        os.environ.get("MASTER_DIR", "~/agents/Master")
    )
    profiles_path = os.path.join(master_dir, "people", "profiles.json")

    if not os.path.exists(profiles_path):
        return ToolResult(success=False, output="", error=f"profiles.json not found: {profiles_path}")

    try:
        with open(profiles_path, "r", encoding="utf-8") as f:
            profiles = _json.load(f)
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Failed to read profiles.json: {e}")

    if person_name not in profiles:
        return ToolResult(success=False, output="", error=f"Person not found: {person_name}")

    # latest.group_insights を上書き
    entry = profiles[person_name]
    target = entry.get("latest", entry)
    if "latest" in entry:
        entry["latest"]["group_insights"] = group_insights
    else:
        entry["group_insights"] = group_insights

    # comm_profile をマージ更新（オプション）
    updated_parts = ["group_insights"]
    if comm_profile_updates:
        existing_comm = target.get("comm_profile", {})
        existing_comm.update(comm_profile_updates)
        target["comm_profile"] = existing_comm
        updated_parts.append("comm_profile")

    # アトミック書き込み
    try:
        dir_name = os.path.dirname(profiles_path)
        fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                _json.dump(profiles, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, profiles_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return ToolResult(success=True, output=f"Updated {'+'.join(updated_parts)} for {person_name}")
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Failed to write profiles.json: {e}")


def os_sync_session() -> ToolResult:
    """OSすり合わせセッション（秘書→甲原）をLINE通知で実行する。

    BRAIN_OS.md / SELF_PROFILE.md / execution_rules.json 等を読み込み、
    Claude APIで現在の理解をサマリー化してLINEに送信。
    """
    import json as _json
    from .notifier import send_line_notify

    master_dir = os.path.expanduser("~/agents/Master")

    # OS関連ファイルを読み込む
    os_sections = []
    files_to_read = [
        ("価値観・判断軸", os.path.join(master_dir, "self_clone", "kohara", "SELF_PROFILE.md"), 2000),
        ("言語スタイル", os.path.join(master_dir, "self_clone", "kohara", "IDENTITY.md"), 1500),
        ("統合OS", os.path.join(master_dir, "self_clone", "kohara", "BRAIN_OS.md"), 1500),
    ]
    for label, path, limit in files_to_read:
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                if content.strip():
                    os_sections.append((label, content[:limit]))
        except Exception as e:
            logger.warning(f"os_sync_session: {label} read error: {e}")

    # execution_rules.json
    exec_rules = []
    rules_path = os.path.join(master_dir, "learning", "execution_rules.json")
    try:
        if os.path.exists(rules_path):
            with open(rules_path, encoding="utf-8") as f:
                exec_rules = _json.load(f)
            if exec_rules:
                os_sections.append(("行動ルール", _json.dumps(exec_rules, ensure_ascii=False, indent=2)[:1500]))
    except Exception as e:
        logger.warning(f"os_sync_session: execution_rules read error: {e}")

    # action_log.json（直近1週間のアクション履歴）
    action_log_text = ""
    action_log_path = os.path.join(master_dir, "learning", "action_log.json")
    try:
        if os.path.exists(action_log_path):
            with open(action_log_path, encoding="utf-8") as f:
                action_log = _json.load(f)
            if action_log:
                # 直近20件に絞る（プロンプト肥大防止）
                recent_actions = action_log[-20:]
                action_lines = []
                for a in recent_actions:
                    action_lines.append(
                        f"- [{a.get('date', '?')}] 指示「{a.get('instruction', '?')[:80]}」→ 結果: {a.get('result', '?')[:100]}"
                    )
                action_log_text = "\n".join(action_lines)
    except Exception as e:
        logger.warning(f"os_sync_session: action_log read error: {e}")

    # feedback_log.json（フィードバック履歴）
    feedback_log_text = ""
    feedback_log_path = os.path.join(master_dir, "learning", "feedback_log.json")
    try:
        if os.path.exists(feedback_log_path):
            with open(feedback_log_path, encoding="utf-8") as f:
                feedback_log = _json.load(f)
            if feedback_log:
                recent_fb = feedback_log[-10:]
                fb_lines = []
                for fb in recent_fb:
                    icon = "+" if fb.get("sentiment") == "positive" else "-"
                    fb_lines.append(
                        f"- [{icon}] 「{fb.get('previous_instruction', '?')[:60]}」→ 甲原さん「{fb.get('feedback', '?')[:80]}」"
                    )
                feedback_log_text = "\n".join(fb_lines)
    except Exception as e:
        logger.warning(f"os_sync_session: feedback_log read error: {e}")

    if not os_sections:
        return ToolResult(success=False, output="", error="No OS files found")

    os_context = ""
    for label, content in os_sections:
        os_context += f"\n\n### {label}\n{content}"

    # ギャップ照合セクション（アクション履歴がある場合のみ追加）
    gap_section = ""
    if action_log_text:
        gap_section = f"""

## 今週のアクション履歴（OS照合用）

以下は秘書が今週実行したアクションの履歴です。
{action_log_text}
"""
        if feedback_log_text:
            gap_section += f"""
### 甲原さんからのフィードバック
{feedback_log_text}
"""
        gap_section += """
★ 上記のアクション履歴をOSのルール・判断軸と照合し、以下を特定してください:
- OSに書かれたルールに反する判断をしていないか
- OSに記載がない判断パターン（=OSの抜け漏れ）がないか
- フィードバックで指摘された内容がOSに反映されていない箇所はないか
"""

    prompt = f"""あなたは甲原海人のAI秘書です。「OSすり合わせ」の時間です。

あなたの役割は甲原さんのクローン。1ミリたりとも認識がずれてはいけない。
だから自分から甲原さんに「今の理解」を報告し、足りないところを聞く。

以下があなたが現在インストールしている「甲原海人の脳のOS」です。
{os_context}
{gap_section}
## 出力（LINEメッセージ）

構成:
━━━━━━━━━━━━━━━━
🧠 OSすり合わせ
━━━━━━━━━━━━━━━━

（1）今の理解を3-4行で簡潔にサマリー

（2）学習済みルール {len(exec_rules)}件から、特に重要なものを2件ピックアップ

（3）今週のアクション×OS照合の結果（ギャップがあれば報告、なければ「照合OK」と1行で）
  → 「今週こういう判断をしたが、OSに該当ルールがなかった」等を具体的に
  → ギャップがあれば「ルール追加すべきですか？」と確認

（4）「ここ確認したい、、！」として1-2個の具体的な質問
  → 情報が薄い・古い・曖昧な部分を特定して質問にする
  → 答えてもらえたら即学習に使える質問にする

（5）「ずれてるとこあったら教えてください！修正・追加があれば即反映します！」で締める

## ルール
- 800文字以内
- マークダウン記法は使わない。【】★━で装飾
- 秘書が「下から上に」報告する姿勢で書く
- ギャップ報告は具体的に。「〇〇の判断をしたとき、OSには該当ルールがなかった」等
"""

    try:
        cli_prompt = f"あなたは甲原海人のAI秘書。OSすり合わせを秘書側から能動的に行う。\n\n{prompt}"
        os_report = _run_claude_cli(cli_prompt, model="claude-sonnet-4-6", max_turns=3, timeout=120)
    except Exception as e:
        return ToolResult(success=False, output="", error=f"Claude CLI error: {e}")

    sent = send_line_notify(os_report)
    if sent:
        # OS sync state を保存（local_agent が応答を検知するため）
        os_sync_state_path = os.path.expanduser("~/agents/data/os_sync_state.json")
        os.makedirs(os.path.dirname(os_sync_state_path), exist_ok=True)
        sync_state = {
            "status": "pending",
            "sent_at": datetime.now().isoformat(),
            "report": os_report,
        }
        tmp = os_sync_state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(sync_state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, os_sync_state_path)
        logger.info("os_sync_session: state saved (pending)")
        return ToolResult(success=True, output=f"OS sync sent ({len(os_report)} chars)")
    else:
        return ToolResult(success=False, output="", error="LINE send failed")


TOOL_REGISTRY = {
    "mail_run": {"fn": mail_run, "description": "受信メールの処理・自動返信下書き作成"},
    "mail_status": {"fn": mail_status, "description": "メール処理のステータス確認"},
    "calendar_list": {"fn": calendar_list, "description": "今後の予定一覧を取得"},
    "sheets_read": {"fn": sheets_read, "description": "Googleスプレッドシートのデータを読み取り"},
    "sheets_sync": {"fn": sheets_sync, "description": "管理シートのCSVキャッシュを同期"},
    "docs_read": {"fn": docs_read, "description": "Googleドキュメントの内容を読み取り"},
    "ai_news_notify": {"fn": ai_news_notify, "description": "最新AIニュースの収集・要約・通知"},
    "addness_fetch": {"fn": addness_fetch, "description": "Addnessからゴールツリーデータをスクレイピング"},
    "addness_to_context": {"fn": addness_to_context, "description": "Addnessデータをコンテキスト用マークダウンに変換"},
    "qa_search": {"fn": qa_search, "description": "Q&Aナレッジベースを検索"},
    "qa_answer": {"fn": qa_answer, "description": "質問に対してAI回答を生成"},
    "qa_stats": {"fn": qa_stats, "description": "Q&Aナレッジベースの統計情報"},
    "who_to_ask": {"fn": who_to_ask, "description": "タスクに最適な担当者を推薦"},
    "kpi_refresh": {"fn": kpi_refresh, "description": "KPI月別タブを日別データから再計算"},
    "kpi_process": {"fn": kpi_process, "description": "元データ完了分をCSVから日別/月別に投入"},
    "kpi_check_today": {"fn": kpi_check_today, "description": "2日前のKPIデータ完了チェック"},
    "git_pull_sync": {"fn": git_pull_sync, "description": "GitHubからpull→ローカルデプロイ"},
    "fetch_group_log": {"fn": fetch_group_log, "description": "Renderサーバーから日次グループログを取得"},
    "update_people_profiles": {"fn": update_people_profiles, "description": "人物プロファイルにグループインサイトを書き込み"},
    "kpi_cache_build": {"fn": kpi_cache_build, "description": "ローカルCSVキャッシュからkpi_summary.jsonを再構築"},
    "kpi_anomaly_check": {"fn": kpi_anomaly_check, "description": "KPIデータの異常検知・媒体別ドリルダウン"},
    "log_rotate": {"fn": log_rotate, "description": "ログファイルのローテーション（50MB超を圧縮、30日保持）"},
    "os_sync_session": {"fn": os_sync_session, "description": "OSすり合わせセッション（秘書→甲原にLINE通知）"},
}
