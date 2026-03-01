#!/bin/bash
# install_service_watchdog.sh — Mac Mini でサービス監視をインストール
# 一度だけ実行すれば OK。5分ごとに service_watchdog.sh が走る。
#
# Usage: bash install_service_watchdog.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WATCHDOG_SCRIPT="$SCRIPT_DIR/service_watchdog.sh"
PLIST_NAME="com.addness.service-watchdog"
PLIST_DST="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
LOG_FILE="$SCRIPT_DIR/service_watchdog.log"

if [ ! -f "$WATCHDOG_SCRIPT" ]; then
  echo "エラー: $WATCHDOG_SCRIPT が見つかりません"
  exit 1
fi

chmod +x "$WATCHDOG_SCRIPT"

# 既存ジョブがあれば停止
if launchctl list 2>/dev/null | grep -q "$PLIST_NAME"; then
  echo "既存ジョブを停止..."
  launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

cat > "$PLIST_DST" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${WATCHDOG_SCRIPT}</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${LOG_FILE}</string>
    <key>StandardErrorPath</key>
    <string>${LOG_FILE}</string>
</dict>
</plist>
PLIST

launchctl load "$PLIST_DST"

echo ""
echo "インストール完了: サービス監視 (service_watchdog)"
echo "  plist: $PLIST_DST"
echo "  間隔: 5分ごと"
echo "  監視対象: com.linebot.localagent, com.addness.agent-orchestrator"
echo "  ログ: $LOG_FILE"
echo ""
echo "管理コマンド:"
echo "  状態確認: launchctl list | grep $PLIST_NAME"
echo "  停止:     launchctl unload $PLIST_DST"
echo "  手動実行: bash $WATCHDOG_SCRIPT"
echo "  ログ確認: tail -20 $LOG_FILE"
