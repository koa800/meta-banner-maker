#!/bin/bash
# LINE Bot Local Agent - インストールスクリプト

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.linebot.localagent.plist"
PLIST_SRC="$SCRIPT_DIR/$PLIST_NAME"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

echo "========================================"
echo "LINE Bot Local Agent インストーラー"
echo "========================================"
echo ""

# 依存関係のインストール
echo "📦 依存関係をインストール中..."
pip3 install -q -r "$SCRIPT_DIR/requirements.txt"

# ログディレクトリの作成
echo "📁 ログディレクトリを作成..."
mkdir -p "$SCRIPT_DIR/logs"

# LaunchAgentsディレクトリの確認
mkdir -p "$HOME/Library/LaunchAgents"

# 既存のサービスを停止
if launchctl list | grep -q "com.linebot.localagent"; then
    echo "🛑 既存のサービスを停止..."
    launchctl unload "$PLIST_DST" 2>/dev/null
fi

# plistファイルをコピー
echo "📋 サービス設定をインストール..."
cp "$PLIST_SRC" "$PLIST_DST"

# サービスを開始
echo "🚀 サービスを開始..."
launchctl load "$PLIST_DST"

echo ""
echo "✅ インストール完了！"
echo ""
echo "【認証】ANTHROPIC_API_KEY と LOCAL_AGENT_TOKEN が必要です。"
echo "  - Secret Manager を使う: run_agent.sh が gcloud で自動取得を試みます。"
echo "  - 使わない場合: config.json に設定するか、run_agent.sh 先頭で export してください。"
echo "  詳細: System/secret_manager_README.md"
echo ""
echo "【状態確認】"
echo "  launchctl list | grep linebot"
echo ""
echo "【ログ確認】"
echo "  tail -f $SCRIPT_DIR/logs/agent.log"
echo ""
echo "【サービス停止】"
echo "  launchctl unload $PLIST_DST"
echo ""
echo "【サービス開始】"
echo "  launchctl load $PLIST_DST"
echo ""
