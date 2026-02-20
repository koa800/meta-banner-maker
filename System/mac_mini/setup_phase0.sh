#!/bin/bash
#
# Phase 0: Mac Mini macOS 基本設定スクリプト
#
# Mac Mini のモニターに接続した状態で実行する。
# macOS 初期設定ウィザード完了後に実行すること。
#
# 使い方:
#   chmod +x setup_phase0.sh
#   ./setup_phase0.sh
#

set -e

echo "========================================"
echo "  Mac Mini Agent - Phase 0 セットアップ"
echo "========================================"
echo ""

# ---- ホスト名設定 ----
echo "[1/7] ホスト名を設定..."
sudo scutil --set HostName mac-mini-agent
sudo scutil --set LocalHostName mac-mini-agent
sudo scutil --set ComputerName "Mac Mini Agent"
echo "  -> mac-mini-agent"

# ---- スリープ無効化 ----
echo "[2/7] スリープを無効化..."
# AC電源接続時: ディスプレイ/ディスク/システムのスリープをすべて無効
sudo pmset -a displaysleep 0
sudo pmset -a disksleep 0
sudo pmset -a sleep 0
# スタンバイも無効
sudo pmset -a standby 0
sudo pmset -a autopoweroff 0
# Wake on network access を有効化（リモートアクセス時に起きる）
sudo pmset -a womp 1
echo "  -> スリープ無効、Wake on LAN 有効"

# ---- SSH (リモートログイン) 有効化 ----
echo "[3/7] SSH (リモートログイン) を有効化..."
sudo systemsetup -setremotelogin on
echo "  -> SSH 有効"

# ---- 画面共有 有効化 ----
echo "[4/7] 画面共有を有効化..."
sudo defaults write /var/db/launchd.db/com.apple.launchd/overrides.plist com.apple.screensharing -dict Disabled -bool false
sudo launchctl load -w /System/Library/LaunchDaemons/com.apple.screensharing.plist 2>/dev/null || true
echo "  -> 画面共有 有効（VNC: vnc://$(hostname -I 2>/dev/null || echo '<IP>')）"

# ---- 自動アップデート無効化 ----
echo "[5/7] 自動ソフトウェアアップデートを無効化..."
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticDownload -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate AutomaticallyInstallMacOSUpdates -bool false
sudo defaults write /Library/Preferences/com.apple.SoftwareUpdate CriticalUpdateInstall -bool false
sudo defaults write /Library/Preferences/com.apple.commerce AutoUpdate -bool false
echo "  -> 自動アップデート無効（予期せぬ再起動を防止）"

# ---- 電源喪失後の自動起動 ----
echo "[6/7] 電源復帰時の自動起動を有効化..."
sudo pmset -a autorestart 1
echo "  -> 停電復帰後に自動で電源ON"

# ---- ファイアウォール設定 ----
echo "[7/7] ファイアウォールを有効化（SSH/VNC 許可）..."
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setallowsigned on
echo "  -> ファイアウォール有効（署名済みアプリは許可）"

echo ""
echo "========================================"
echo "  Phase 0 完了"
echo "========================================"
echo ""
echo "このMac MiniのIPアドレス:"
ifconfig | grep "inet " | grep -v 127.0.0.1 | awk '{print "  " $2}'
echo ""
echo "メインPCから接続:"
echo "  ssh $(whoami)@<上記IPアドレス>"
echo ""
echo "次のステップ:"
echo "  1. ルーター設定でこのIPを固定（DHCP予約）する"
echo "  2. メインPCから SSH 接続を確認する"
echo "  3. setup_phase1.sh を実行する"
