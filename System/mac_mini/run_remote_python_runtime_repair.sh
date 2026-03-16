#!/bin/bash
# run_remote_python_runtime_repair.sh — MacBook から Mac Mini へ Python ランタイム修復を流す

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REMOTE_HOST="koa800@mac-mini-agent"
REMOTE_ROOT="~/agents"
DRY_RUN=0
SKIP_PLAYWRIGHT=0
STATUS_ONLY=0

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN=1
      ;;
    --skip-playwright)
      SKIP_PLAYWRIGHT=1
      ;;
    --status-only)
      STATUS_ONLY=1
      ;;
    --host=*)
      REMOTE_HOST="${arg#*=}"
      ;;
    --remote-root=*)
      REMOTE_ROOT="${arg#*=}"
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

run_local() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] '
    printf '%q ' "$@"
    printf '\n'
    return 0
  fi
  "$@"
}

run_remote() {
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '[dry-run] ssh %q %q\n' "$REMOTE_HOST" "$1"
    return 0
  fi
  ssh -o BatchMode=yes "$REMOTE_HOST" "$1"
}

sync_file() {
  local local_path="$1"
  local remote_path="$2"
  local remote_dir
  remote_dir="$(dirname "$remote_path")"
  run_remote "mkdir -p $remote_dir"
  run_local scp "$local_path" "${REMOTE_HOST}:${remote_path}"
}

main() {
  log "=== Remote Python runtime repair ==="
  log "host: $REMOTE_HOST"
  log "remote_root: $REMOTE_ROOT"
  if [ "$DRY_RUN" -eq 1 ]; then
    log "dry-run モードです"
  fi

  run_remote "echo ok >/dev/null"

  sync_file "$REPO_ROOT/System/scripts/python_runtime.py" "$REMOTE_ROOT/System/scripts/python_runtime.py"
  sync_file "$REPO_ROOT/System/scripts/python_runtime_status.py" "$REMOTE_ROOT/System/scripts/python_runtime_status.py"
  sync_file "$REPO_ROOT/System/mac_mini/repair_python_runtime.sh" "$REMOTE_ROOT/System/mac_mini/repair_python_runtime.sh"
  sync_file "$REPO_ROOT/System/mac_mini/install_orchestrator.sh" "$REMOTE_ROOT/System/mac_mini/install_orchestrator.sh"
  sync_file "$REPO_ROOT/System/mac_mini/git_pull_sync.sh" "$REMOTE_ROOT/System/mac_mini/git_pull_sync.sh"
  sync_file "$REPO_ROOT/System/mac_mini/monitoring/service_watchdog.sh" "$REMOTE_ROOT/System/mac_mini/monitoring/service_watchdog.sh"
  sync_file "$REPO_ROOT/System/mac_mini/monitoring/install_service_watchdog.sh" "$REMOTE_ROOT/System/mac_mini/monitoring/install_service_watchdog.sh"
  sync_file "$REPO_ROOT/System/mac_mini/agent_orchestrator/__main__.py" "$REMOTE_ROOT/System/mac_mini/agent_orchestrator/__main__.py"
  sync_file "$REPO_ROOT/System/mac_mini/agent_orchestrator/orchestrator.py" "$REMOTE_ROOT/System/mac_mini/agent_orchestrator/orchestrator.py"
  sync_file "$REPO_ROOT/System/mac_mini/agent_orchestrator/scheduler.py" "$REMOTE_ROOT/System/mac_mini/agent_orchestrator/scheduler.py"
  sync_file "$REPO_ROOT/System/mac_mini/agent_orchestrator/tools.py" "$REMOTE_ROOT/System/mac_mini/agent_orchestrator/tools.py"
  sync_file "$REPO_ROOT/System/mac_mini/agent_orchestrator/code_tools.py" "$REMOTE_ROOT/System/mac_mini/agent_orchestrator/code_tools.py"
  sync_file "$REPO_ROOT/System/line_bot_local/run_agent.sh" "$REMOTE_ROOT/System/line_bot_local/run_agent.sh"
  sync_file "$REPO_ROOT/System/line_bot_local/install.sh" "$REMOTE_ROOT/System/line_bot_local/install.sh"
  sync_file "$REPO_ROOT/System/line_bot_local/run_agent.sh" "$REMOTE_ROOT/line_bot_local/run_agent.sh"
  sync_file "$REPO_ROOT/System/line_bot_local/install.sh" "$REMOTE_ROOT/line_bot_local/install.sh"

  run_remote "chmod +x $REMOTE_ROOT/System/mac_mini/repair_python_runtime.sh $REMOTE_ROOT/System/line_bot_local/install.sh $REMOTE_ROOT/System/line_bot_local/run_agent.sh $REMOTE_ROOT/line_bot_local/install.sh $REMOTE_ROOT/line_bot_local/run_agent.sh"

  if [ "$STATUS_ONLY" -eq 1 ]; then
    run_remote "python3 $REMOTE_ROOT/System/scripts/python_runtime_status.py"
    return 0
  fi

  remote_cmd="bash $REMOTE_ROOT/System/mac_mini/repair_python_runtime.sh"
  if [ "$SKIP_PLAYWRIGHT" -eq 1 ]; then
    remote_cmd="$remote_cmd --skip-playwright"
  fi
  run_remote "$remote_cmd"
}

main "$@"
