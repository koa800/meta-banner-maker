#!/bin/bash
#
# メインPC → Mac Mini へのトークン転送スクリプト
#
# メインPC上で実行する。
#
# 使い方:
#   chmod +x transfer_tokens.sh
#   ./transfer_tokens.sh <mac-mini-user>@<mac-mini-ip>
#
# 例:
#   ./transfer_tokens.sh koa800@192.168.1.100
#

set -e

if [ -z "$1" ]; then
    echo "使い方: $0 <user>@<mac-mini-ip>"
    echo "例:     $0 koa800@192.168.1.100"
    exit 1
fi

MAC_MINI="$1"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DST_DIR="Desktop/cursor/System"

echo "========================================"
echo "  トークン・設定ファイル転送"
echo "========================================"
echo ""
echo "転送元: $SRC_DIR"
echo "転送先: $MAC_MINI:~/$DST_DIR"
echo ""

FILES_TO_TRANSFER=(
    "client_secret_personal.json"
    "addness_config.json"
    "addness_session.json"
    "line_bot_local/config.json"
)

# token*.json と *_config.json を動的に収集
for f in "$SRC_DIR"/token*.json; do
    [ -f "$f" ] && FILES_TO_TRANSFER+=("$(basename "$f")")
done

echo "転送するファイル:"
for f in "${FILES_TO_TRANSFER[@]}"; do
    if [ -f "$SRC_DIR/$f" ]; then
        echo "  [OK] $f"
    else
        echo "  [--] $f (存在しない、スキップ)"
    fi
done
echo ""

read -p "転送を開始しますか？ (y/N): " confirm
if [ "$confirm" != "y" ] && [ "$confirm" != "Y" ]; then
    echo "キャンセルしました"
    exit 0
fi

echo ""
echo "転送中..."

for f in "${FILES_TO_TRANSFER[@]}"; do
    if [ -f "$SRC_DIR/$f" ]; then
        # サブディレクトリを含む場合は先にディレクトリを作成
        dir_part=$(dirname "$f")
        if [ "$dir_part" != "." ]; then
            ssh "$MAC_MINI" "mkdir -p ~/$DST_DIR/$dir_part"
        fi
        scp "$SRC_DIR/$f" "$MAC_MINI:~/$DST_DIR/$f"
        echo "  -> $f 転送完了"
    fi
done

# mail_inbox_data ディレクトリも転送
if [ -d "$SRC_DIR/mail_inbox_data" ]; then
    echo "  -> mail_inbox_data/ 転送中..."
    scp -r "$SRC_DIR/mail_inbox_data" "$MAC_MINI:~/$DST_DIR/"
    echo "  -> mail_inbox_data/ 転送完了"
fi

# addness_data ディレクトリも転送
if [ -d "$SRC_DIR/addness_data" ]; then
    echo "  -> addness_data/ 転送中..."
    scp -r "$SRC_DIR/addness_data" "$MAC_MINI:~/$DST_DIR/"
    echo "  -> addness_data/ 転送完了"
fi

# addness_chrome_profile ディレクトリも転送
if [ -d "$SRC_DIR/addness_chrome_profile" ]; then
    echo "  -> addness_chrome_profile/ 転送中..."
    scp -r "$SRC_DIR/addness_chrome_profile" "$MAC_MINI:~/$DST_DIR/"
    echo "  -> addness_chrome_profile/ 転送完了"
fi

# qa_sync ディレクトリも転送
if [ -d "$SRC_DIR/qa_sync" ]; then
    echo "  -> qa_sync/ 転送中..."
    scp -r "$SRC_DIR/qa_sync" "$MAC_MINI:~/$DST_DIR/"
    echo "  -> qa_sync/ 転送完了"
fi

# rclone設定の転送
RCLONE_CONF="$HOME/.config/rclone/rclone.conf"
if [ -f "$RCLONE_CONF" ]; then
    echo "  -> rclone設定を転送中..."
    ssh "$MAC_MINI" "mkdir -p ~/.config/rclone"
    scp "$RCLONE_CONF" "$MAC_MINI:~/.config/rclone/rclone.conf"
    echo "  -> rclone.conf 転送完了"
fi

echo ""
echo "========================================"
echo "  転送完了"
echo "========================================"
echo ""
echo "Mac Mini側で確認:"
echo "  ssh $MAC_MINI"
echo "  ls -la ~/$DST_DIR/token*.json"
echo "  ls -la ~/$DST_DIR/addness_config.json"
