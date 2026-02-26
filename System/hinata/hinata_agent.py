#!/usr/bin/env python3
"""
日向（ひなた） — 自律型AIエージェント

ブラウザを常時開いた状態で稼働。
Addnessの操作もアクション実行も全てClaude Codeが行う。
hinata_agent.py はブラウザの維持とSlack監視だけ。

フロー:
  Slack指示 → Claude Code起動
    → 常駐ブラウザ(CDP)でAddness操作（AI相談・完了・期限設定等）
    → アクション実行
    → ナレッジ蓄積
    → Slack報告
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright

from addness_browser import launch_browser, setup_page, login, find_my_goal
from claude_executor import execute_full_cycle, execute_self_repair
from slack_comm import (
    send_message,
    send_report,
    check_for_commands,
)

# ---- 設定 ----
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "config.json"
STATE_PATH = SCRIPT_DIR / "state.json"
LOG_DIR = SCRIPT_DIR / "logs"
SLACK_POLL_INTERVAL = 15
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
        "last_slack_ts": None,
    }


def save_state(state: dict):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def is_work_hours(config: dict) -> bool:
    now = datetime.now().hour
    work = config.get("work_hours", {"start": 8, "end": 22})
    return work["start"] <= now < work["end"]


def get_interval(config: dict) -> int:
    if is_work_hours(config):
        return config.get("cycle_interval_minutes", 30) * 60
    else:
        return config.get("night_interval_minutes", 120) * 60


# ====================================================================
# サイクル実行（全てClaude Code経由）
# ====================================================================

def run_cycle(config: dict, state: dict, instruction: str = None) -> dict:
    """Claude Codeにフルサイクルを任せる。失敗時はExceptionをraiseする。"""
    cycle_num = state.get("cycle_count", 0) + 1
    logger.info(f"===== サイクル #{cycle_num} 開始 =====")

    my_goal_url = config.get("my_goal_url", "")
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
        send_report(f"サイクル #{cycle_num} 完了", result[:500])
        state["last_action"] = result[:200]
        save_state(state)
        return state
    else:
        logger.warning(f"サイクル #{cycle_num} 失敗")
        send_message(f"⚠️ サイクル #{cycle_num} の実行に失敗しました。")
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
    """
    自己修復サイクルを実行する。

    Returns:
        True: 修復を試みた（成功かどうかは結果次第）
        False: 修復不可能
    """
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
# Slackコマンド処理
# ====================================================================

def handle_command(command: dict, config: dict, state: dict) -> dict:
    cmd_type = command["command_type"]
    text = command["text"]

    if cmd_type == "stop":
        send_message("了解です！一旦止まります。次の指示をお待ちしています。")
        logger.info("甲原からの停止指示")
        return state

    elif cmd_type == "status":
        last = state.get("last_action", "まだ実行していません")
        cycle = state.get("cycle_count", 0)
        last_time = state.get("last_cycle", "なし")
        send_message(
            f"*日向の状況報告*\n\n"
            f"サイクル数: {cycle}\n"
            f"最後のアクション: {last}\n"
            f"最終実行: {last_time}"
        )
        return state

    elif cmd_type == "run_action":
        send_message("はい！アクションを進めます。")
        try:
            return run_cycle(config, state)
        except Exception as e:
            logger.error(f"run_action サイクルエラー: {e}")
            return state

    elif cmd_type == "instruction":
        send_message(f"了解です！「{text[:50]}」に取り組みます。")
        try:
            return run_cycle(config, state, instruction=text)
        except Exception as e:
            logger.error(f"instruction サイクルエラー: {e}")
            return state

    return state


# ====================================================================
# エントリーポイント
# ====================================================================

def main():
    config = load_config()
    state = load_state()

    logger.info("=" * 60)
    logger.info("日向エージェント起動")
    logger.info(f"サイクル間隔: {config.get('cycle_interval_minutes', 30)}分")
    logger.info(f"Slack確認間隔: {SLACK_POLL_INTERVAL}秒")
    logger.info("=" * 60)

    send_message("🌅 日向エージェント起動しました！Slackで指示をくだされば動きます。")

    # 起動時は現在時刻にリセット
    state["last_slack_ts"] = str(time.time())
    save_state(state)

    with sync_playwright() as playwright:
        headless = config.get("headless", False)
        context = launch_browser(playwright, headless=headless)
        page = setup_page(context)

        start_url = config.get("addness_start_url", "https://www.addness.com")
        if not login(page, start_url):
            logger.error("Addnessログインに失敗。終了します。")
            send_message("❌ Addnessログインに失敗しました。")
            context.close()
            sys.exit(1)

        logger.info("Addnessログイン完了。ブラウザ常駐開始。（CDP: localhost:9222）")

        # ゴールページに遷移して待機
        my_goal_url = config.get("my_goal_url")
        if my_goal_url:
            find_my_goal(page, my_goal_url=my_goal_url)

        next_cycle_time = time.time() + get_interval(config)
        paused = False
        consecutive_errors = 0
        last_error_summary = ""

        try:
            while True:
                # ---- Slack コマンド確認 ----
                try:
                    command = check_for_commands(state.get("last_slack_ts", "0"))
                    if command:
                        state["last_slack_ts"] = command["ts"]
                        save_state(state)

                        if command["command_type"] == "stop":
                            handle_command(command, config, state)
                            paused = True
                        else:
                            if command["command_type"] in ("run_action", "instruction"):
                                paused = False
                            state = handle_command(command, config, state)
                            next_cycle_time = time.time() + get_interval(config)
                            # 指示実行が成功したらエラーカウントリセット
                            consecutive_errors = 0
                except Exception as e:
                    logger.error(f"Slackコマンド処理エラー: {e}")

                # ---- 定期サイクル ----
                if not paused and time.time() >= next_cycle_time:
                    try:
                        state = run_cycle(config, state)
                        consecutive_errors = 0  # 成功したらリセット
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
                        consecutive_errors = 0  # リセット（修復成否問わず無限ループ防止）
                        if repaired:
                            # self_restart.sh で再起動されるため、ここには戻らない可能性がある
                            # 戻った場合は次のサイクルで再試行
                            logger.info("自己修復完了。次のサイクルで再試行します。")

                    interval = get_interval(config)
                    next_cycle_time = time.time() + interval
                    next_str = datetime.fromtimestamp(next_cycle_time).strftime("%H:%M")
                    logger.info(f"次のサイクル: {next_str}（{interval // 60}分後）")

                time.sleep(SLACK_POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("日向エージェント停止（手動停止）")
            send_message("👋 日向エージェント停止しました。")
        finally:
            context.close()


if __name__ == "__main__":
    if "--login" in sys.argv:
        PYTHON_CMD = str(Path.home() / "hinata-venv" / "bin" / "python")
        ADDNESS_CLI = str(SCRIPT_DIR / "addness_cli.py")
        subprocess.run([PYTHON_CMD, ADDNESS_CLI, "login"])
    else:
        main()
