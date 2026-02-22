#!/bin/bash
# LINE Bot エージェント データ同期スクリプト
# launchd（TCC制限あり）のため、このスクリプトをTerminalから手動実行する

PROJECT_ROOT="/Users/koa800/Desktop/cursor"
LIB_DATA="/Users/koa800/Library/LineBot/data"
LIB_AGENT="/Users/koa800/Library/LineBot/local_agent.py"
DESKTOP_AGENT="$PROJECT_ROOT/System/line_bot_local/local_agent.py"

echo "🔄 LINE Bot データ同期中..."
mkdir -p "$LIB_DATA"

# --- people-profiles.json は双方向同期（LINEメモが含まれるため） ---
PROFILES_SRC="$PROJECT_ROOT/Master/people/profiles.json"
PROFILES_DST="$LIB_DATA/people-profiles.json"
if [ -f "$PROFILES_DST" ]; then
    LIB_TIME=$(stat -f "%m" "$PROFILES_DST" 2>/dev/null || echo 0)
    DST_TIME=$(stat -f "%m" "$PROFILES_SRC" 2>/dev/null || echo 0)
    if [ "$LIB_TIME" -gt "$DST_TIME" ]; then
        cp "$PROFILES_DST" "$PROFILES_SRC" && echo "✅ profiles.json (Library→Desktop: メモ保持)"
    else
        cp "$PROFILES_SRC" "$PROFILES_DST" && echo "✅ profiles.json (Desktop→Library)"
    fi
else
    cp "$PROFILES_SRC" "$PROFILES_DST" 2>/dev/null && echo "✅ profiles.json (初回)"
fi

cp "$PROJECT_ROOT/Master/people/identities.json" "$LIB_DATA/people-identities.json" 2>/dev/null && echo "✅ identities.json"
cp "$PROJECT_ROOT/Master/self_clone/kohara/IDENTITY.md" "$LIB_DATA/IDENTITY.md" 2>/dev/null && echo "✅ IDENTITY.md"
cp "$PROJECT_ROOT/Master/self_clone/kohara/SELF_PROFILE.md" "$LIB_DATA/SELF_PROFILE.md" 2>/dev/null && echo "✅ SELF_PROFILE.md"

# フィードバック学習データを双方向同期（Library ↔ Desktop/Master）
if [ -f "$LIB_DATA/reply_feedback.json" ]; then
    LIB_TIME=$(stat -f "%m" "$LIB_DATA/reply_feedback.json" 2>/dev/null || echo 0)
    DST_FILE="$PROJECT_ROOT/Master/learning/reply_feedback.json"
    DST_TIME=$(stat -f "%m" "$DST_FILE" 2>/dev/null || echo 0)
    if [ "$LIB_TIME" -gt "$DST_TIME" ]; then
        cp "$LIB_DATA/reply_feedback.json" "$DST_FILE" && echo "✅ reply_feedback.json (Library→Desktop)"
    else
        cp "$DST_FILE" "$LIB_DATA/reply_feedback.json" 2>/dev/null && echo "✅ reply_feedback.json (Desktop→Library)"
    fi
elif [ -f "$PROJECT_ROOT/Master/learning/reply_feedback.json" ]; then
    cp "$PROJECT_ROOT/Master/learning/reply_feedback.json" "$LIB_DATA/reply_feedback.json" && echo "✅ reply_feedback.json (Desktop→Library)"
fi

# NOTE: local_agent.py の実行は ~/agents/line_bot_local/ から行う（git_pull_sync.sh が plist を自動修正済み）
# Library版は廃止。git同期版が正式な実行パス。
echo ""
echo "✅ 同期完了！"
echo "   データ: $LIB_DATA"
echo "   ※ local_agent.py は ~/agents/line_bot_local/ で git 同期管理されます"
