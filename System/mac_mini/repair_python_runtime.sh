#!/bin/bash
# repair_python_runtime.sh — Mac Mini の Python ランタイムと常駐サービスを再整備する
#
# 目的:
# - Homebrew python@3.12 を確認
# - ~/agent-env を 3.10+ で揃える
# - 依存パッケージを再投入する
# - local_agent / orchestrator / service_watchdog を再インストールする
# - 最後に python_runtime_status.py で状態を確認する
#
# Usage:
#   bash repair_python_runtime.sh
#   bash repair_python_runtime.sh --dry-run
#   bash repair_python_runtime.sh --skip-playwright

set -euo pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SYSTEM_DIR="$REPO_ROOT/System"
LINE_AGENT_SOURCE_DIR="$SYSTEM_DIR/line_bot_local"
LINE_AGENT_RUNTIME_DIR="$REPO_ROOT/line_bot_local"
ORCH_DIR="$SYSTEM_DIR/mac_mini"
MONITOR_DIR="$SYSTEM_DIR/mac_mini/monitoring"
STATUS_SCRIPT="$SYSTEM_DIR/scripts/python_runtime_status.py"
VENV_PATH="$HOME/agent-env"
VENV_PYTHON="$VENV_PATH/bin/python3"
DRY_RUN=0
SKIP_PLAYWRIGHT=0
BREW_PYTHON=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-playwright)
      SKIP_PLAYWRIGHT=1
      ;;
    *)
      echo "未知の引数です: $arg" >&2
      exit 1
      ;;
  esac
done

log() {
  printf '%s\n' "$1"
}

run_cmd() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

python_meets_min() {
  local python_bin="$1"
  [ -x "$python_bin" ] || return 1
  "$python_bin" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null
}

resolve_brew_python() {
  local prefix=""
  if command -v brew >/dev/null 2>&1; then
    prefix="$(brew --prefix python@3.12 2>/dev/null || true)"
    if [ -n "$prefix" ] && [ -x "$prefix/bin/python3.12" ]; then
      printf '%s\n' "$prefix/bin/python3.12"
      return 0
    fi
  fi

  if command -v python3.12 >/dev/null 2>&1; then
    command -v python3.12
    return 0
  fi

  return 1
}

ensure_brew_python() {
  if BREW_PYTHON="$(resolve_brew_python 2>/dev/null || true)"; then
    if [ -n "$BREW_PYTHON" ]; then
      return 0
    fi
  fi

  if [ "$DRY_RUN" -eq 1 ]; then
    BREW_PYTHON="/opt/homebrew/bin/python3.12"
    log "python@3.12 をインストールします"
    run_cmd brew install python@3.12
    return 0
  fi

  if ! command -v brew >/dev/null 2>&1; then
    echo "brew が見つかりません。setup_phase1.sh か Homebrew 導入を先に行ってください。" >&2
    exit 1
  fi

  log "python@3.12 をインストールします"
  run_cmd brew install python@3.12
}

ensure_agent_env() {
  if python_meets_min "$VENV_PYTHON"; then
    log "agent-env は既に 3.10+ です: $VENV_PYTHON"
    return 0
  fi

  if [ -d "$VENV_PATH" ]; then
    log "既存の agent-env を再作成します"
    run_cmd rm -rf "$VENV_PATH"
  fi

  log "agent-env を $BREW_PYTHON で作成します"
  run_cmd "$BREW_PYTHON" -m venv "$VENV_PATH"
}

install_python_dependencies() {
  log "Python 依存関係を更新します"
  run_cmd "$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel
  run_cmd "$VENV_PYTHON" -m pip install -r "$LINE_AGENT_SOURCE_DIR/requirements.txt"
  run_cmd "$VENV_PYTHON" -m pip install -r "$ORCH_DIR/agent_orchestrator/requirements.txt"
  run_cmd "$VENV_PYTHON" -m pip install playwright apscheduler fastapi uvicorn watchdog pyyaml aiohttp aiosqlite

  if [ "$SKIP_PLAYWRIGHT" -eq 0 ]; then
    run_cmd "$VENV_PYTHON" -m playwright install chromium
  else
    log "Playwright の browser install はスキップします"
  fi
}

reinstall_services() {
  if [ -d "$LINE_AGENT_RUNTIME_DIR" ]; then
    log "line_bot_local の install 用ファイルを runtime copy に反映します"
    run_cmd cp "$LINE_AGENT_SOURCE_DIR/install.sh" "$LINE_AGENT_RUNTIME_DIR/install.sh"
    run_cmd cp "$LINE_AGENT_SOURCE_DIR/run_agent.sh" "$LINE_AGENT_RUNTIME_DIR/run_agent.sh"
    run_cmd chmod +x "$LINE_AGENT_RUNTIME_DIR/install.sh" "$LINE_AGENT_RUNTIME_DIR/run_agent.sh"
  fi

  log "local_agent を再インストールします"
  if [ -x "$LINE_AGENT_RUNTIME_DIR/install.sh" ]; then
    run_cmd bash "$LINE_AGENT_RUNTIME_DIR/install.sh"
  else
    run_cmd bash "$LINE_AGENT_SOURCE_DIR/install.sh"
  fi

  log "orchestrator を再インストールします"
  run_cmd bash "$ORCH_DIR/install_orchestrator.sh"

  log "service_watchdog を再インストールします"
  run_cmd bash "$MONITOR_DIR/install_service_watchdog.sh"
}

show_status() {
  log "Python ランタイム診断を実行します"
  run_cmd python3 "$STATUS_SCRIPT"
}

main() {
  log "=== Python ランタイム修復を開始します ==="
  if [ "$DRY_RUN" -eq 1 ]; then
    log "dry-run モードです。実際の変更は行いません。"
  fi

  ensure_brew_python
  ensure_agent_env
  install_python_dependencies
  reinstall_services
  show_status

  log "=== Python ランタイム修復が完了しました ==="
}

main "$@"
