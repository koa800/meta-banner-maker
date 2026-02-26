#!/bin/bash
# ============================================================
# OpenClaw 削除スクリプト
#
# 日向のMac MiniからOpenClawを完全に削除する。
# ============================================================

set -e

echo "============================="
echo " OpenClaw 削除"
echo "============================="
echo ""

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

# 1. OpenClawプロセスを停止
echo "[1/5] OpenClawプロセスを停止..."
pkill -f openclaw 2>/dev/null && echo "    停止しました" || echo "    実行中のプロセスなし"
pkill -f clawdbot 2>/dev/null || true
pkill -f moltbot 2>/dev/null || true

# 2. LaunchAgentを削除
echo "[2/5] LaunchAgentを削除..."
for plist in ~/Library/LaunchAgents/*claw* ~/Library/LaunchAgents/*moltbot* ~/Library/LaunchAgents/*openclaw*; do
    if [ -f "$plist" ]; then
        launchctl unload "$plist" 2>/dev/null || true
        rm "$plist"
        echo "    削除: $plist"
    fi
done
echo "    完了"

# 3. npmグローバルパッケージを削除
echo "[3/5] npmパッケージを削除..."
npm uninstall -g openclaw 2>/dev/null && echo "    openclaw削除" || echo "    openclaw未インストール"
npm uninstall -g clawdbot 2>/dev/null || true
npm uninstall -g moltbot 2>/dev/null || true

# 4. 設定ディレクトリを削除
echo "[4/5] 設定ディレクトリを削除..."
for dir in ~/.openclaw ~/.clawdbot ~/.moltbot ~/openclaw ~/clawdbot; do
    if [ -d "$dir" ]; then
        rm -rf "$dir"
        echo "    削除: $dir"
    fi
done
echo "    完了"

# 5. 確認
echo "[5/5] 確認..."
if command -v openclaw &>/dev/null; then
    echo "    ⚠️ openclaw がまだ存在します: $(which openclaw)"
else
    echo "    ✅ OpenClawは完全に削除されました"
fi

echo ""
echo "============================="
echo " 削除完了"
echo "============================="
