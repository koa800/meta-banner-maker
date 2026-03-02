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
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

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

write_status() {
  local status="$1"
  local commit="$2"
  local msg="$3"
  local changed="${4:-0}"
  # msgに含まれるダブルクォート・バックスラッシュ・改行をエスケープ
  local escaped_msg
  escaped_msg=$(printf '%s' "$msg" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null) || escaped_msg="\"$msg\""
  local escaped_status
  escaped_status=$(printf '%s' "$status" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read()))" 2>/dev/null) || escaped_status="\"$status\""
  cat > "$STATUS_FILE" <<EOJSON
{
  "status": $escaped_status,
  "commit": "$(echo "$commit" | cut -c1-40)",
  "commit_short": "$(echo "$commit" | cut -c1-7)",
  "message": $escaped_msg,
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

# --- plist パス整合性チェック（毎回実行） ---
# Mac Mini の launchctl plist が正しいデプロイ先を指しているか確認し、
# Library版など古いパスを参照していれば自動修正する
ensure_plist_path() {
  local PLIST=~/Library/LaunchAgents/com.linebot.localagent.plist
  local CORRECT_AGENT="$DEPLOY_DIR/line_bot_local/local_agent.py"
  local CORRECT_LOGS="$DEPLOY_DIR/line_bot_local/logs"

  [ -f "$PLIST" ] || return 0

  if grep -q "$CORRECT_AGENT" "$PLIST" 2>/dev/null; then
    return 0
  fi

  log "plist パス不整合を検出 → 修正します"

  mkdir -p "$CORRECT_LOGS"

  # config.json が新パスに無ければ旧パス（Library版）からコピー
  local OLD_CONFIG="$HOME/Library/LineBot/config.json"
  local NEW_CONFIG="$DEPLOY_DIR/line_bot_local/config.json"
  if [ ! -f "$NEW_CONFIG" ] && [ -f "$OLD_CONFIG" ]; then
    cp "$OLD_CONFIG" "$NEW_CONFIG"
    log "config.json を Library版からコピー"
  fi

  launchctl unload "$PLIST" 2>/dev/null || true
  sleep 1

  # config.json から環境変数を読み取り（plistに埋め込む）
  # ※ ANTHROPIC_API_KEY は埋め込まない（local_agent が config.json から直接読む。
  #    plist 経由で混入すると Claude Code CLI が OAuth ではなく API キーを使い障害の原因になる）
  local AGENT_TOKEN_VAL=""
  local LINE_BOT_URL=""
  if [ -f "$NEW_CONFIG" ]; then
    AGENT_TOKEN_VAL=$(python3 -c "import json; print(json.load(open('$NEW_CONFIG')).get('agent_token',''))" 2>/dev/null || echo "")
    LINE_BOT_URL=$(python3 -c "import json; print(json.load(open('$NEW_CONFIG')).get('server_url',''))" 2>/dev/null || echo "")
  fi

  cat > "$PLIST" <<EOPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.linebot.localagent</string>

    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/caffeinate</string>
        <string>-s</string>
        <string>/usr/bin/python3</string>
        <string>-u</string>
        <string>${CORRECT_AGENT}</string>
    </array>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>

    <key>ThrottleInterval</key>
    <integer>15</integer>

    <key>StandardOutPath</key>
    <string>${CORRECT_LOGS}/agent.log</string>

    <key>StandardErrorPath</key>
    <string>${CORRECT_LOGS}/agent_error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>HOME</key>
        <string>$HOME</string>
EOPLIST

  # 環境変数がある場合のみ追加（空のまま書き込まない）
  if [ -n "$AGENT_TOKEN_VAL" ]; then
    cat >> "$PLIST" <<EOENV
        <key>AGENT_TOKEN</key>
        <string>${AGENT_TOKEN_VAL}</string>
EOENV
  fi
  if [ -n "$LINE_BOT_URL" ]; then
    cat >> "$PLIST" <<EOENV
        <key>LINE_BOT_SERVER_URL</key>
        <string>${LINE_BOT_URL}</string>
EOENV
  fi

  cat >> "$PLIST" <<EOPLIST
    </dict>
</dict>
</plist>
EOPLIST

  sleep 1
  launchctl load "$PLIST" 2>/dev/null || true
  log "plist パス修正完了 → エージェント再起動"
  notify_line "🔧 plistパス自動修正＆エージェント再起動
━━━━━━━━━━━━
旧パス → $DEPLOY_DIR/line_bot_local/
時刻: $(date '+%H:%M')"
}

ensure_plist_path

# --- 学習データ push（fetch/reset の前に実行して上書き防止） ---
push_learning_data() {
  local learning_dir="$REPO_DIR/Master/learning"
  [ -d "$learning_dir" ] || return 0

  # 学習ファイルに変更があるか確認
  local changed_files
  changed_files=$(git diff --name-only -- "Master/learning/" 2>/dev/null || echo "")
  local untracked_files
  untracked_files=$(git ls-files --others --exclude-standard -- "Master/learning/" 2>/dev/null || echo "")

  if [ -z "$changed_files" ] && [ -z "$untracked_files" ]; then
    return 0
  fi

  log "学習データ変更検出 → commit & push"
  git add "Master/learning/" 2>> "$LOG_FILE" || { log "WARNING: git add 失敗（学習データ）"; return 0; }
  git commit -m "auto: 日向学習データ同期 ($(date '+%m/%d %H:%M'))" 2>> "$LOG_FILE" || { log "WARNING: git commit 失敗（学習データ）"; return 0; }

  if git push origin main 2>> "$LOG_FILE"; then
    log "学習データ push 完了"
  else
    # push失敗 → コミットを取り消してファイルを退避
    # （この後の git reset --hard でコミットもファイルも消えるため）
    log "WARNING: 学習データ push 失敗 → 一時退避"
    git reset HEAD~1 2>/dev/null || true
    cp -r "$learning_dir" /tmp/hinata_learning_backup 2>/dev/null || true
  fi
}

push_learning_data

# --- fetch して差分チェック（厳密検証） ---
FETCH_STDERR=$(mktemp)
if ! git fetch origin main 2>"$FETCH_STDERR"; then
  FETCH_ERR=$(cat "$FETCH_STDERR")
  rm -f "$FETCH_STDERR"
  log "ERROR: git fetch 失敗: $FETCH_ERR"
  write_status "fetch_failed" "$(git rev-parse HEAD 2>/dev/null || echo 'unknown')" "fetch失敗" 0
  exit 1
fi
rm -f "$FETCH_STDERR"

LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_HEAD=$(git rev-parse origin/main 2>/dev/null || echo "")

if [ -z "$REMOTE_HEAD" ]; then
  log "ERROR: origin/main の解決に失敗（fetch後にrefが見つからない）"
  write_status "fetch_failed" "$LOCAL_HEAD" "origin/main 解決失敗" 0
  exit 1
fi

if [ "$LOCAL_HEAD" = "$REMOTE_HEAD" ]; then
  write_status "synced" "$LOCAL_HEAD" "変更なし" 0
  exit 0
fi

log "変更検出: $LOCAL_HEAD → $REMOTE_HEAD"

# --- 変更ファイル一覧を取得（再起動判定用） ---
CHANGED=$(git diff --name-only "$LOCAL_HEAD" "$REMOTE_HEAD" 2>/dev/null || echo "")

# --- リセット ---
if ! git reset --hard origin/main 2>> "$LOG_FILE"; then
  log "ERROR: git reset --hard 失敗 — rsyncをスキップして安全に終了"
  write_status "reset_failed" "$LOCAL_HEAD" "git reset失敗" 0
  notify_line "⚠️ git reset --hard 失敗
━━━━━━━━━━━━
リポジトリ: $REPO_DIR
古いコードのままデプロイは行いません。
手動確認が必要です。"
  exit 1
fi
log "git reset 完了"

# 学習データの一時退避を復元（push失敗時のみ /tmp に退避されている）
if [ -d /tmp/hinata_learning_backup ]; then
  cp -r /tmp/hinata_learning_backup/* "$REPO_DIR/Master/learning/" 2>/dev/null || true
  rm -rf /tmp/hinata_learning_backup
  log "学習データ復元完了（push失敗分 → 次回再試行）"
fi

# --- ローカル rsync でデプロイ ---

# System/ （line_bot/ と line_bot_local/ は別管理）
rsync -a --delete \
  --exclude "addness_chrome_profile/" \
  --exclude "addness_data/" \
  --exclude "qa_sync/" \
  --exclude "mail_review_web/" \
  --exclude "looker_browser_profile/" \
  --exclude "hinata_old/" \
  --exclude "hinata/logs/" \
  --exclude "__pycache__/" \
  --exclude "*.pyc" \
  --exclude "line_bot/" \
  --exclude "line_bot_local/" \
  --exclude "*.log" \
  --exclude "*.db" \
  --exclude "data/" \
  --exclude "credentials/" \
  --exclude "config/" \
  --exclude "mac_mini/agent_orchestrator/logs/" \
  --exclude "mac_mini/agent_orchestrator/*.db" \
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

PLIST=~/Library/LaunchAgents/com.linebot.localagent.plist

if echo "$CHANGED" | grep -qE "line_bot_local/.*\.py"; then
  CHANGED_PY=$(echo "$CHANGED" | grep "line_bot_local/.*\.py" | sed 's|.*/||' | head -3 | tr '\n' ' ')
  log "local_agent 再起動（変更: ${CHANGED_PY}）"
  launchctl unload "$PLIST" 2>/dev/null || true
  sleep 2
  launchctl load "$PLIST" 2>/dev/null || true
  COMMIT_SHORT=$(echo "$REMOTE_HEAD" | cut -c1-7)
  notify_line "🔄 ローカルエージェント自動再起動
━━━━━━━━━━━━
変更: ${CHANGED_PY}
コミット: ${COMMIT_SHORT}
時刻: $(date '+%H:%M')"
fi

# 遠隔再起動シグナルファイル（local_agentが作成 → ここで検知）
RESTART_SIGNAL="$DEPLOY_DIR/.restart_local_agent"
if [ -f "$RESTART_SIGNAL" ]; then
  log "遠隔再起動リクエスト検知"
  rm -f "$RESTART_SIGNAL"
  launchctl unload "$PLIST" 2>/dev/null || true
  sleep 2
  launchctl load "$PLIST" 2>/dev/null || true
  notify_line "🔄 ローカルエージェント遠隔再起動完了
時刻: $(date '+%H:%M')"
fi

ORCH_PLIST=~/Library/LaunchAgents/com.addness.agent-orchestrator.plist
if echo "$CHANGED" | grep -q "mac_mini/agent_orchestrator/"; then
  log "Orchestrator 再起動（unload/load 方式）"
  (
    sleep 3
    launchctl unload "$ORCH_PLIST" 2>/dev/null || true
    sleep 2
    launchctl load "$ORCH_PLIST" 2>/dev/null || true
    log "Orchestrator 再起動完了"
  ) &
fi

# --- config.json バリデーション ---
_validate_config() {
  local config_file="$DEPLOY_DIR/line_bot_local/config.json"
  if [ ! -f "$config_file" ]; then
    log "WARNING: config.json が存在しません: $config_file"
    notify_line "⚠️ config.json 未設定
━━━━━━━━━━━━
$config_file が存在しません。
手動でセットアップしてください。"
    return 1
  fi

  local missing=""
  for key in server_url agent_token; do
    local val
    val=$(python3 -c "import json; c=json.load(open('$config_file')); print('OK' if c.get('$key') else 'MISSING')" 2>/dev/null || echo "ERROR")
    if [ "$val" != "OK" ]; then
      missing="$missing $key"
    fi
  done

  if [ -n "$missing" ]; then
    log "WARNING: config.json に必須キーが不足:$missing"
    notify_line "⚠️ config.json 設定不足
━━━━━━━━━━━━
不足キー:$missing
ファイル: $config_file"
    return 1
  fi
}
_validate_config || true   # バリデーション失敗でもスクリプトは続行（通知は済んでいる）

CHANGED_COUNT=$(echo "$CHANGED" | wc -l | tr -d ' ')
log "同期完了: ${CHANGED_COUNT}ファイル更新"
write_status "synced" "$REMOTE_HEAD" "同期完了" "$CHANGED_COUNT"
