#!/usr/bin/env python3
"""
日向（ひなた） — 自律型AIエージェント

Chrome + Claude in Chrome MCP でブラウザ操作。
Claude Code が MCP ツール経由でブラウザを直接制御する。
hinata_agent.py はタスクキュー監視とサイクル管理のみ。

フロー:
  秘書(Orchestrator)がSlack監視 → hinata_tasks.json に書き込み
    → 日向がタスクを拾う → Claude Code起動
    → Claude in Chrome MCP でAddness操作（AI相談・完了・期限設定等）
    → アクション実行
    → ナレッジ蓄積
    → Slack報告
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import subprocess as _subprocess

from claude_executor import execute_full_cycle, execute_self_repair, execute_orchestrator_repair
from learning import record_action, detect_and_record_feedback
from slack_comm import send_message, send_report

# ---- 設定 ----
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
STATE_PATH = SCRIPT_DIR / "state.json"
TASKS_PATH = SCRIPT_DIR / "hinata_tasks.json"
LOG_DIR = SCRIPT_DIR / "logs"
TASK_POLL_INTERVAL = 15
MAX_CONSECUTIVE_ERRORS = 3  # この回数連続エラーで自己修復サイクル発動

# ---- ロギング ----
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_DIR / "hinata.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("hinata")


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def load_state() -> dict:
    if STATE_PATH.exists():
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "cycle_count": 0,
        "last_action": None,
        "last_cycle": None,
        "paused": False,
    }


def save_state(state: dict):
    """状態をアトミックに保存（tmp → rename で中間状態を防ぐ）"""
    tmp = STATE_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    tmp.rename(STATE_PATH)


def get_interval(config: dict) -> int:
    """サイクル間隔を返す（24時間稼働）"""
    return config.get("cycle_interval_minutes", 60) * 60


def is_effectively_paused(config: dict, state: dict) -> bool:
    """state.json と config.json の両方を見て停止状態を判定する。"""
    return bool(state.get("paused") or config.get("paused"))


def get_pause_reason(config: dict) -> str:
    reason = str(config.get("pause_reason", "")).strip()
    return reason or "設定で一時停止中"


# ====================================================================
# Chrome 死活監視
# ====================================================================

CHROME_PROFILE_DIR = Path.home() / "agents" / "System" / "data" / "hinata_chrome_profile"


def is_chrome_running() -> bool:
    """Chrome プロセスが起動しているか確認する。"""
    try:
        result = _subprocess.run(
            ["pgrep", "-f", "Google Chrome"],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def is_chrome_cdp_healthy() -> bool:
    """Chrome DevTools Protocol (CDP) ポート 9223 が応答するか確認する。

    プロセスが生きていても MCP 接続が死んでいるケースを検知する。
    """
    try:
        result = _subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
             "--connect-timeout", "3", "--max-time", "5",
             "http://localhost:9223/json/version"],
            capture_output=True, text=True, timeout=10,
        )
        status_code = result.stdout.strip()
        if status_code == "200":
            return True
        logger.warning(f"CDP ヘルスチェック失敗: HTTP {status_code}")
        return False
    except Exception as e:
        logger.warning(f"CDP ヘルスチェック例外: {e}")
        return False


def restart_chrome() -> bool:
    """Chrome を強制終了して再起動する。MCP 接続が不安定な場合に使用。"""
    logger.warning("Chrome を再起動します...")
    try:
        # Chrome を終了（graceful → force）
        _subprocess.run(["pkill", "-f", "Google Chrome"], timeout=5)
        time.sleep(3)
        # まだ残っていたら強制終了
        if is_chrome_running():
            _subprocess.run(["pkill", "-9", "-f", "Google Chrome"], timeout=5)
            time.sleep(2)
    except Exception as e:
        logger.warning(f"Chrome 終了時エラー（続行）: {e}")

    # 再起動
    return _start_chrome()


def _start_chrome() -> bool:
    """Chrome を起動して CDP ポートの疎通を確認する。"""
    try:
        _subprocess.Popen(
            ["open", "-a", "Google Chrome", "--args",
             f"--user-data-dir={CHROME_PROFILE_DIR}",
             "--remote-debugging-port=9223",
             "--no-first-run",
             "--no-default-browser-check"],
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
        )
        # Chrome 起動待ち → CDP 疎通確認（最大30秒）
        for i in range(6):
            time.sleep(5)
            if is_chrome_running() and is_chrome_cdp_healthy():
                logger.info("Chrome 起動成功（CDP 疎通確認済み）")
                return True
            logger.info(f"Chrome 起動待ち... ({(i+1)*5}秒)")

        # プロセスはあるが CDP が応答しない
        if is_chrome_running():
            logger.warning("Chrome プロセスは起動したが CDP ポートが応答しません")
            return True  # プロセスはあるので一応 True
        logger.error("Chrome 起動失敗")
        return False
    except Exception as e:
        logger.error(f"Chrome 起動エラー: {e}")
        return False


def ensure_chrome_running() -> bool:
    """Chrome が正常稼働していなければ起動/再起動する。

    チェック順序:
    1. プロセス存在確認
    2. CDP ポート 9223 疎通確認
    3. 異常時は再起動
    """
    if not is_chrome_running():
        logger.warning("Chrome が起動していません。起動を試みます...")
        ok = _start_chrome()
        if ok:
            send_message("Chrome が落ちていたので再起動しました。")
        else:
            send_message("⚠️ Chrome の起動に失敗しました。手動確認が必要です。")
        return ok

    # プロセスはあるが CDP が死んでいないか確認
    if not is_chrome_cdp_healthy():
        logger.warning("Chrome プロセスは存在するが CDP が応答しません。再起動します...")
        ok = restart_chrome()
        if ok:
            send_message("Chrome の MCP 接続が不安定だったため再起動しました。")
        else:
            send_message("⚠️ Chrome の再起動に失敗しました。手動確認が必要です。")
        return ok

    return True


# ====================================================================
# タスクキュー（hinata_tasks.json）
# ====================================================================

def _load_tasks() -> list:
    """タスクキューを読み込む。"""
    if not TASKS_PATH.exists():
        return []
    try:
        with open(TASKS_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_tasks(tasks: list):
    """タスクキューをアトミックに書き込む。"""
    tmp = TASKS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(tasks, f, ensure_ascii=False, indent=2)
    tmp.rename(TASKS_PATH)


def check_task_queue() -> Optional[dict]:
    """次のpendingタスクを取得する。"""
    tasks = _load_tasks()
    for task in tasks:
        if task.get("status") == "pending":
            return task
    return None


def claim_task(task_id: str):
    """タスクをprocessingに変更する。"""
    tasks = _load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "processing"
            task["started_at"] = datetime.now().isoformat()
            break
    _save_tasks(tasks)


def complete_task(task_id: str, success: bool, result: str):
    """タスクをcompleted/failedに変更する。"""
    tasks = _load_tasks()
    for task in tasks:
        if task.get("id") == task_id:
            task["status"] = "completed" if success else "failed"
            task["completed_at"] = datetime.now().isoformat()
            task["result"] = result[:500]
            break
    _save_tasks(tasks)


def cleanup_old_tasks():
    """完了から1時間以上経ったタスク + 24時間以上放置されたpending/processingタスクを削除する。"""
    tasks = _load_tasks()
    now = datetime.now()
    kept = []
    for task in tasks:
        status = task.get("status", "")
        # 完了/失敗タスク → 1時間で削除
        if status in ("completed", "failed"):
            completed_at = task.get("completed_at", "")
            if completed_at:
                try:
                    dt = datetime.fromisoformat(completed_at)
                    if (now - dt).total_seconds() > 3600:
                        continue
                except ValueError:
                    pass
        # pending/processing が24時間以上 → 孤立タスクとして削除
        elif status in ("pending", "processing"):
            created_at = task.get("created_at", "") or task.get("started_at", "")
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at)
                    if (now - dt).total_seconds() > 86400:
                        logger.warning(f"孤立タスク削除: {task.get('id')} ({task.get('instruction', '')[:30]})")
                        continue
                except ValueError:
                    pass
        kept.append(task)
    if len(kept) != len(tasks):
        _save_tasks(kept)


# ====================================================================
# サイクル実行（全てClaude Code経由）
# ====================================================================

def run_cycle(config: dict, state: dict, instruction: str = None) -> dict:
    """Claude Codeにフルサイクルを任せる。失敗時はExceptionをraiseする。"""
    cycle_num = state.get("cycle_count", 0) + 1
    logger.info(f"===== サイクル #{cycle_num} 開始 =====")

    # フィードバック検出（指示が直前アクションへの修正かを判定）
    if instruction:
        feedback = detect_and_record_feedback(instruction)
        if feedback:
            sentiment = feedback["sentiment"]
            logger.info(f"フィードバック検出: [{sentiment}] {instruction[:50]}")

    my_goal_url = config.get("my_goal_url", "")
    # config の mode を state 経由で claude_executor に渡す
    state["_config_mode"] = config.get("mode", "report")
    result = execute_full_cycle(
        instruction=instruction,
        cycle_num=cycle_num,
        state=state,
        goal_url=my_goal_url,
    )

    state["cycle_count"] = cycle_num
    state["last_cycle"] = datetime.now().isoformat()

    if result:
        logger.info(f"サイクル #{cycle_num} 完了")
        # 親プロセスが確実にアクション記録（Claude Code に任せない）
        record_action(cycle_num, instruction, result, goal_url=my_goal_url)
        send_report(f"サイクル #{cycle_num} 完了", result[:500])
        state["last_action"] = result[:200]
        save_state(state)
        return state
    else:
        logger.warning(f"サイクル #{cycle_num} 失敗（--chrome + リトライ両方失敗）")
        record_action(cycle_num, instruction, "失敗: Claude Codeが結果を返さなかった（chrome + リトライ済み）")
        save_state(state)
        raise RuntimeError(f"サイクル #{cycle_num} でClaude Codeが結果を返しませんでした")


# ====================================================================
# エラー自動修復
# ====================================================================

def _read_recent_logs(n_lines: int = 50) -> str:
    """hinata.log の直近N行を読み込む。"""
    log_file = LOG_DIR / "hinata.log"
    if not log_file.exists():
        return ""
    try:
        lines = log_file.read_text(encoding="utf-8").splitlines()
        return "\n".join(lines[-n_lines:])
    except Exception:
        return ""


def attempt_self_repair(error_summary: str, state: dict) -> bool:
    """自己修復サイクルを実行する。"""
    logger.warning(f"自己修復サイクル開始: {error_summary}")
    send_message(
        f"🔧 *自己修復モード起動*\n\n"
        f"連続エラーが{MAX_CONSECUTIVE_ERRORS}回発生したため、自動でバグ修正を試みます。\n"
        f"エラー: {error_summary[:200]}"
    )

    recent_logs = _read_recent_logs(80)
    result = execute_self_repair(error_summary, recent_logs)

    if result:
        if "修復不可" in result:
            send_message(
                f"⚠️ *自己修復断念*\n\n{result[:500]}\n\n"
                f"甲原さんの確認が必要です。"
            )
            return False
        else:
            send_message(f"✅ *自己修復完了*\n\n{result[:500]}")
            return True
    else:
        send_message(
            "❌ *自己修復失敗*\n\n"
            "Claude Code による修復が失敗しました。甲原さんの確認が必要です。"
        )
        return False


# ====================================================================
# タスク処理
# ====================================================================

def handle_task(task: dict, config: dict, state: dict) -> dict:
    """タスクキューから取得したタスクを処理する。"""
    task_id = task["id"]
    command_type = task.get("command_type", "instruction")
    text = task.get("instruction", "")

    if command_type == "stop":
        logger.info("秘書からの停止指示")
        state["paused"] = True
        save_state(state)
        complete_task(task_id, True, "停止しました")
        return state

    elif command_type == "resume":
        logger.info("秘書からの再開指示")
        if config.get("paused"):
            reason = get_pause_reason(config)
            state["paused"] = True
            save_state(state)
            send_message(f"再開指示を受けましたが、現在は停止方針のため再開しません。{reason}")
            complete_task(task_id, False, f"停止方針のため未再開: {reason}")
            return state

        state["paused"] = False
        save_state(state)
        send_message("再開します！")
        complete_task(task_id, True, "再開しました")
        return state

    elif command_type == "repair":
        claim_task(task_id)
        logger.info(f"Orchestrator からの修復タスク: {text[:100]}")
        try:
            diagnosis = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            diagnosis = {"task_name": "不明", "error_type": text[:200]}

        try:
            result = execute_orchestrator_repair(diagnosis)
            if result:
                if "修復不可" in result:
                    send_message(
                        f"⚠️ *修復断念*: {diagnosis.get('task_name', '不明')}\n\n"
                        f"{result[:400]}\n\n甲原さんの確認が必要です。"
                    )
                    complete_task(task_id, False, result[:500])
                else:
                    send_message(
                        f"✅ *自動修復完了*: {diagnosis.get('task_name', '不明')}\n\n{result[:400]}"
                    )
                    complete_task(task_id, True, result[:500])
            else:
                send_message(
                    f"❌ *修復失敗*: {diagnosis.get('task_name', '不明')}\n\n"
                    f"Claude Code が結果を返しませんでした。甲原さんの確認が必要です。"
                )
                complete_task(task_id, False, "Claude Code が結果を返さなかった")
        except Exception as e:
            logger.error(f"repair タスクエラー: {e}")
            send_message(
                f"❌ *修復エラー*: {diagnosis.get('task_name', '不明')}\n{str(e)[:200]}"
            )
            complete_task(task_id, False, str(e)[:500])
        return state

    elif command_type == "instruction":
        claim_task(task_id)
        # Chrome が起動していなければ起動
        if not ensure_chrome_running():
            complete_task(task_id, False, "Chrome が起動できませんでした")
            send_message("⚠️ Chrome が起動できないため、タスクを実行できませんでした。")
            return state
        send_message(f"了解です！「{text[:50]}」に取り組みます。")
        try:
            state = run_cycle(config, state, instruction=text)
            complete_task(task_id, True, state.get("last_action", ""))
        except Exception as e:
            logger.error(f"instruction タスクエラー: {e}")
            complete_task(task_id, False, str(e)[:500])
        return state

    return state


# ====================================================================
# エントリーポイント
# ====================================================================

def main():
    config = load_config()
    state = load_state()

    logger.info("=" * 60)
    logger.info("日向エージェント起動（Claude in Chrome MCP モード）")
    logger.info(f"サイクル間隔: {config.get('cycle_interval_minutes', 30)}分")
    logger.info(f"タスク確認間隔: {TASK_POLL_INTERVAL}秒")
    logger.info("=" * 60)

    send_message("🌅 日向エージェント起動しました！（Claude in Chrome MCP モード）")

    # paused 状態を維持（停止指示後の再起動で勝手に動き出さない）
    if is_effectively_paused(config, state):
        logger.info(
            "pause 中のため、タスクキュー監視のみ（定期サイクルは停止中）: "
            f"{get_pause_reason(config)}"
        )

    next_cycle_time = time.time() + get_interval(config)
    consecutive_errors = 0
    last_error_summary = ""

    try:
        while True:
            # ---- タスクキュー確認 ----
            try:
                config = load_config()
                # state.json を再読み込み（秘書が paused を変更する可能性）
                state = load_state()
                paused = is_effectively_paused(config, state)

                task = check_task_queue()
                if task:
                    command_type = task.get("command_type", "instruction")

                    if command_type == "stop":
                        handle_task(task, config, state)
                    elif command_type == "resume":
                        handle_task(task, config, state)
                        next_cycle_time = time.time() + get_interval(config)
                    elif paused:
                        reason = get_pause_reason(config)
                        logger.info(
                            f"pause 中のため {command_type} タスクを実行しません: "
                            f"{task.get('id')} ({reason})"
                        )
                        complete_task(task["id"], False, f"停止中のため未実行: {reason}")
                    else:
                        state = handle_task(task, config, state)
                        next_cycle_time = time.time() + get_interval(config)
                        consecutive_errors = 0
            except Exception as e:
                logger.error(f"タスク処理エラー: {e}")

            # ---- 定期サイクル ----
            config = load_config()
            state = load_state()  # paused 状態を再確認
            if not is_effectively_paused(config, state) and time.time() >= next_cycle_time:
                # Chrome が起動しているか確認（落ちていたら再起動）
                if not ensure_chrome_running():
                    logger.error("Chrome が起動できないためサイクルをスキップ")
                    next_cycle_time = time.time() + 300  # 5分後にリトライ
                    time.sleep(TASK_POLL_INTERVAL)
                    continue
                try:
                    state = run_cycle(config, state)
                    consecutive_errors = 0
                except Exception as e:
                    logger.exception(f"サイクル実行エラー: {e}")
                    send_message(f"⚠️ サイクル実行エラー: {str(e)[:200]}")
                    consecutive_errors += 1
                    last_error_summary = str(e)[:500]

                # ---- 連続エラー時の自己修復 ----
                if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                    logger.warning(
                        f"連続エラー {consecutive_errors}回。自己修復を試みます。"
                    )
                    repaired = attempt_self_repair(last_error_summary, state)
                    consecutive_errors = 0
                    if repaired:
                        logger.info("自己修復完了。次のサイクルで再試行します。")

                interval = get_interval(config)
                next_cycle_time = time.time() + interval
                next_str = datetime.fromtimestamp(next_cycle_time).strftime("%H:%M")
                logger.info(f"次のサイクル: {next_str}（{interval // 60}分後）")

            # ---- 古いタスクのクリーンアップ（たまに） ----
            cleanup_old_tasks()

            time.sleep(TASK_POLL_INTERVAL)

    except KeyboardInterrupt:
        logger.info("日向エージェント停止（手動停止）")
        send_message("👋 日向エージェント停止しました。")


if __name__ == "__main__":
    main()
