#!/bin/bash
# MacBook に Mac Mini 外部監視を launchd でインストールする。
# スクリプトを ~/.config/addness/monitoring/ にデプロイし、
# macOS の TCC（Desktop アクセス制限）を回避する。
#
# Usage: bash install_watchdog.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

DEPLOY_DIR="$HOME/.config/addness/monitoring"
PLIST_NAME="com.addness.mac-mini-watchdog"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"

if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
    echo "既存ジョブを停止..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

mkdir -p "$DEPLOY_DIR"

cp "$SCRIPT_DIR/external_watchdog.py" "$DEPLOY_DIR/external_watchdog.py"

LINE_CFG="$REPO_ROOT/System/line_bot_local/config.json"
if [ -f "$LINE_CFG" ]; then
    cp "$LINE_CFG" "$DEPLOY_DIR/line_config.json"
    echo "LINE設定をデプロイ: $DEPLOY_DIR/line_config.json"
fi

LOG_FILE="$DEPLOY_DIR/watchdog.log"

cat > "$PLIST_DST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>${DEPLOY_DIR}/external_watchdog.py</string>
    </array>
    <key>StartInterval</key>
    <integer>600</integer>
    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>
    <key>RunAtLoad</key>
    <true/>
</dict>
</plist>
PLIST

launchctl load "$PLIST_DST"

echo ""
echo "✅ Watchdog インストール完了"
echo "   デプロイ先: $DEPLOY_DIR/"
echo "   10分ごとに Mac Mini の死活監視を実行します"
echo "   ログ: $LOG_FILE"
echo ""
echo "管理コマンド:"
echo "   状態確認: launchctl list | grep $PLIST_NAME"
echo "   停止:     launchctl unload $PLIST_DST"
echo "   手動実行: python3 $DEPLOY_DIR/external_watchdog.py"
echo "   ログ確認: tail -20 $LOG_FILE"
