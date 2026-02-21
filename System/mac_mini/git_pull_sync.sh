#!/bin/bash
# git_pull_sync.sh — GitHub からの pull + ローカルデプロイ
# Mac Mini 上の Orchestrator が5分ごとに実行
# フロー: git fetch → 変更なければ即終了 → git reset --hard → rsync → サービス再起動

set -euo pipefail

REPO_DIR="$HOME/agents/_repo"
DEPLOY_DIR="$HOME/agents"
REPO_URL="https://github.com/koa800/meta-banner-maker.git"
LOG_FILE="$DEPLOY_DIR/System/mac_mini/agent_orchestrator/logs/git_sync.log"
STATUS_FILE="$DEPLOY_DIR/System/mac_mini/agent_orchestrator/sync_status.json"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

write_status() {
  local status="$1"
  local commit="$2"
  local msg="$3"
  local changed="${4:-0}"
  cat > "$STATUS_FILE" <<EOJSON
{
  "status": "$status",
  "commit": "$commit",
  "commit_short": "$(echo "$commit" | cut -c1-7)",
  "message": "$msg",
  "changed_files": $changed,
  "checked_at": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "checked_at_jst": "$(date '+%Y-%m-%d %H:%M:%S')"
}
EOJSON
}

# ログローテーション（500行に圧縮）
if [ -f "$LOG_FILE" ] && [ "$(wc -l < "$LOG_FILE")" -gt 500 ]; then
  tail -n 300 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

# --- 初回: clone ---
if [ ! -d "$REPO_DIR/.git" ]; then
  log "初回 clone: $REPO_URL → $REPO_DIR"
  git clone "$REPO_URL" "$REPO_DIR" 2>> "$LOG_FILE"
  log "clone 完了"
fi

cd "$REPO_DIR"

# --- fetch して差分チェック ---
git fetch origin main 2>> "$LOG_FILE"

LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse origin/main)

if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
  write_status "synced" "$LOCAL_HEAD" "変更なし" 0
  exit 0
fi

log "変更検出: $LOCAL_HEAD → $REMOTE_HEAD"

# --- 変更ファイル一覧を取得（再起動判定用） ---
CHANGED=$(git diff --name-only "$LOCAL_HEAD" "$REMOTE_HEAD" 2>/dev/null || echo "")

# --- リセット ---
git reset --hard origin/main 2>> "$LOG_FILE"
log "git reset 完了"

# --- ローカル rsync でデプロイ ---

# System/ （line_bot/ と line_bot_local/ は別管理）
rsync -a --delete \
  --exclude "addness_chrome_profile/" \
  --exclude "addness_data/" \
  --exclude "qa_sync/" \
  --exclude "mail_review_web/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "line_bot/" \
  --exclude "line_bot_local/" \
  --exclude "*.log" \
  --exclude "*.db" \
  --exclude "addness_session.json" \
  "$REPO_DIR/System/" "$DEPLOY_DIR/System/" \
  && log "System/ OK" || log "ERROR: System/ rsync 失敗"

# line_bot_local/ （状態ファイル除外）
rsync -a \
  --exclude "qa_monitor_state.json" \
  --exclude "contact_state.json" \
  --exclude "*.log" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "config.json" \
  "$REPO_DIR/System/line_bot_local/" "$DEPLOY_DIR/line_bot_local/" \
  && log "line_bot_local/ OK" || log "ERROR: line_bot_local/ rsync 失敗"

# Master/
rsync -a --delete \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  "$REPO_DIR/Master/" "$DEPLOY_DIR/Master/" \
  && log "Master/ OK" || log "ERROR: Master/ rsync 失敗"

# Project/
rsync -a --delete \
  "$REPO_DIR/Project/" "$DEPLOY_DIR/Project/" \
  && log "Project/ OK" || log "ERROR: Project/ rsync 失敗"

# Skills/
rsync -a --delete \
  "$REPO_DIR/Skills/" "$DEPLOY_DIR/Skills/" \
  && log "Skills/ OK" || log "ERROR: Skills/ rsync 失敗"

# --- 変更ファイルに応じてサービス再起動 ---

if echo "$CHANGED" | grep -qE "line_bot_local/(local_agent\.py|config\.json)"; then
  log "local_agent 再起動"
  launchctl unload ~/Library/LaunchAgents/com.linebot.localagent.plist 2>/dev/null || true
  sleep 2
  launchctl load ~/Library/LaunchAgents/com.linebot.localagent.plist 2>/dev/null || true
fi

if echo "$CHANGED" | grep -q "mac_mini/agent_orchestrator/"; then
  log "Orchestrator 再起動（5秒後バックグラウンド）"
  # 自分自身が呼び出し元なので、バックグラウンドで遅延再起動
  (
    sleep 5
    launchctl stop com.addness.agent-orchestrator 2>/dev/null || true
    sleep 2
    launchctl start com.addness.agent-orchestrator 2>/dev/null || true
  ) &
fi

CHANGED_COUNT=$(echo "$CHANGED" | wc -l | tr -d ' ')
log "同期完了: ${CHANGED_COUNT}ファイル更新"
write_status "synced" "$REMOTE_HEAD" "同期完了" "$CHANGED_COUNT"
