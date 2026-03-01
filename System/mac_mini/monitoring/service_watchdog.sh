#!/bin/bash
# service_watchdog.sh — Orchestrator 非依存のサービス監視
# launchd で5分ごとに実行。bash + launchctl のみで依存ゼロ。
# 監視対象: local_agent, Orchestrator
# 停止検知時: launchctl load で復旧 + LINE 通知

set -u

DEPLOY_DIR="$HOME/agents"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$SCRIPT_DIR/service_watchdog.log"

# --- ログ ---
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# ログローテーション（200行）
if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt 200 ]; then
  tail -n 100 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

# --- LINE 通知（git_pull_sync.sh と同じパターン） ---
notify_line() {
  local message="$1"
  local config_file="$DEPLOY_DIR/line_bot_local/config.json"
  [ -f "$config_file" ] || return 0
  local server_url token escaped_msg
  server_url=$(python3 -c "import json; print(json.load(open('$config_file')).get('server_url',''))" 2>/dev/null || echo "")
  token=$(python3 -c "import json; print(json.load(open('$config_file')).get('agent_token',''))" 2>/dev/null || echo "")
  [ -n "$server_url" ] || return 0
  escaped_msg=$(printf '%s' "$message" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null) || return 0
  curl -s -X POST "$server_url/notify" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $token" \
    -d "{\"message\": $escaped_msg}" >/dev/null 2>&1 &
}

# --- サービス監視 ---
check_and_recover() {
  local label="$1"
  local plist="$HOME/Library/LaunchAgents/${label}.plist"

  if ! [ -f "$plist" ]; then
    log "SKIP: plist が存在しない: $plist"
    return 0
  fi

  # launchctl list で PID を取得（1列目が PID、"-" なら停止中）
  local pid
  pid=$(launchctl list 2>/dev/null | grep "$label" | awk '{print $1}')

  if [ -z "$pid" ]; then
    # launchctl list にすら出ない → load されていない
    log "DOWN: $label（未登録）→ load で復旧"
    launchctl load "$plist" 2>/dev/null || true
    notify_line "🚨 サービス自動復旧
━━━━━━━━━━━━
サービス: $label
状態: 未登録 → load で復旧
時刻: $(date '+%m/%d %H:%M')"
    return 1
  fi

  if [ "$pid" = "-" ] || [ "$pid" = "0" ]; then
    # 登録はされているが停止中 → unload/load で再起動
    log "DOWN: $label（停止中, PID=$pid）→ 再起動"
    launchctl unload "$plist" 2>/dev/null || true
    sleep 2
    launchctl load "$plist" 2>/dev/null || true
    notify_line "🚨 サービス自動復旧
━━━━━━━━━━━━
サービス: $label
状態: 停止 → 再起動
時刻: $(date '+%m/%d %H:%M')"
    return 1
  fi

  # 正常稼働中
  return 0
}

# --- メイン ---
RECOVERED=0

for SERVICE in "com.linebot.localagent" "com.addness.agent-orchestrator"; do
  if ! check_and_recover "$SERVICE"; then
    RECOVERED=$((RECOVERED + 1))
  fi
done

if [ "$RECOVERED" -eq 0 ]; then
  # 正常時は定期的にログ（10回に1回だけ）
  # 最終正常ログの行数で判定
  NORMAL_COUNT=$(grep -c "OK: 全サービス稼働中" "$LOG_FILE" 2>/dev/null || echo "0")
  if [ "$((NORMAL_COUNT % 10))" -eq 0 ]; then
    log "OK: 全サービス稼働中"
  fi
else
  log "ALERT: ${RECOVERED}件のサービスを復旧"
fi
