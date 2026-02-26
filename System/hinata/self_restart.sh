#!/bin/bash
# 日向エージェント自己再起動スクリプト
# Claude Codeがコード修正後にこのスクリプトを呼ぶことで、自分自身を再起動する
#
# 使い方: bash /path/to/self_restart.sh [reason]
# 例: bash self_restart.sh "slack_comm.pyのバグ修正後"

LABEL="com.hinata.agent"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$(dirname "$0")/logs"

mkdir -p "$LOG_DIR"

REASON="${1:-不明}"
echo "$(date '+%Y-%m-%d %H:%M:%S') [self_restart] 再起動開始: ${REASON}" >> "$LOG_DIR/restart.log"

# git pull で最新コードを取得
cd "$HOME/agents/_repo" && git pull origin main 2>&1 >> "$LOG_DIR/restart.log"

# launchd で再起動（unload → load）
launchctl unload "$PLIST" 2>/dev/null
sleep 2
launchctl load "$PLIST" 2>&1

echo "$(date '+%Y-%m-%d %H:%M:%S') [self_restart] 再起動完了" >> "$LOG_DIR/restart.log"
