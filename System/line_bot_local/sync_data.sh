#!/bin/bash
# LINE Bot エージェント データ同期スクリプト
# launchd（TCC制限あり）のため、このスクリプトをTerminalから手動実行する

PROJECT_ROOT="/Users/koa800/Desktop/cursor"
LIB_DATA="/Users/koa800/Library/LineBot/data"
LIB_AGENT="/Users/koa800/Library/LineBot/local_agent.py"
DESKTOP_AGENT="$PROJECT_ROOT/System/line_bot_local/local_agent.py"

echo "🔄 LINE Bot データ同期中..."
mkdir -p "$LIB_DATA"

# データファイル同期
cp "$PROJECT_ROOT/Master/people-profiles.json" "$LIB_DATA/people-profiles.json" 2>/dev/null && echo "✅ people-profiles.json"
cp "$PROJECT_ROOT/Master/people-identities.json" "$LIB_DATA/people-identities.json" 2>/dev/null && echo "✅ people-identities.json"
cp "$PROJECT_ROOT/Master/self_clone/projects/kohara/1_Core/IDENTITY.md" "$LIB_DATA/IDENTITY.md" 2>/dev/null && echo "✅ IDENTITY.md"

# local_agent.py は Library版を維持（パス設定が異なるため上書きしない）
echo ""
echo "✅ 同期完了！"
echo "   データ: $LIB_DATA"
echo "   ※ local_agent.py はLibrary専用版を維持（上書きしません）"
