#!/bin/bash
# LINE Bot Local Agent - インストールスクリプト

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_NAME="com.linebot.localagent.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$PLIST_NAME"

resolve_runtime_resolver() {
    local candidate
    for candidate in \
        "$SCRIPT_DIR/../scripts/python_runtime.py" \
        "$SCRIPT_DIR/../System/scripts/python_runtime.py"
    do
        if [ -f "$candidate" ]; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

resolve_python() {
    local resolver
    resolver="$(resolve_runtime_resolver 2>/dev/null || true)"
    if [ -n "$resolver" ]; then
        /usr/bin/python3 "$resolver" --print-path --min 3.10 2>/dev/null && return 0
    fi

    if [ -x "$HOME/agent-env/bin/python3" ]; then
        echo "$HOME/agent-env/bin/python3"
        return 0
    fi

    command -v python3 2>/dev/null || echo /usr/bin/python3
}

echo "========================================"
echo "LINE Bot Local Agent インストーラー"
echo "========================================"
echo ""

# 依存関係のインストール
echo "📦 依存関係をインストール中..."
PYTHON_BIN="$(resolve_python)"
"$PYTHON_BIN" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

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
chmod +x "$SCRIPT_DIR/run_agent.sh"
cat > "$PLIST_DST" <<PLIST
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
        <string>/bin/bash</string>
        <string>$SCRIPT_DIR/run_agent.sh</string>
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
    <string>$SCRIPT_DIR/logs/agent.log</string>

    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/agent_error.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
        <key>PYTHONUNBUFFERED</key>
        <string>1</string>
        <key>HOME</key>
        <string>$HOME</string>
    </dict>
</dict>
</plist>
PLIST

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
