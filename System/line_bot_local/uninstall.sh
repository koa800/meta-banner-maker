#!/bin/bash
# LINE Bot Local Agent - アンインストールスクリプト

PLIST_NAME="com.linebot.localagent.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "========================================"
echo "LINE Bot Local Agent アンインストーラー"
echo "========================================"
echo ""

if [ -f "$PLIST_DST" ]; then
    echo "🛑 サービスを停止..."
    launchctl unload "$PLIST_DST" 2>/dev/null
    
    echo "🗑️  設定ファイルを削除..."
    rm "$PLIST_DST"
    
    echo ""
    echo "✅ アンインストール完了！"
else
    echo "⚠️  サービスはインストールされていません"
fi
