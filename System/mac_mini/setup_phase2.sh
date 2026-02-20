#!/bin/bash
#
# Phase 2: 既存スクリプト群の移行と稼働確認
#
# Mac Mini 上で実行する。
# Phase 1 + トークン転送完了後に実行すること。
#
# 使い方:
#   chmod +x setup_phase2.sh
#   ./setup_phase2.sh
#

set -e

REPO_DIR="$HOME/Desktop/cursor"
SYSTEM_DIR="$REPO_DIR/System"
VENV_PATH="$HOME/agent-env"

echo "========================================"
echo "  Mac Mini Agent - Phase 2 移行・稼働確認"
echo "========================================"
echo ""

if [ ! -d "$SYSTEM_DIR" ]; then
    echo "エラー: $SYSTEM_DIR が見つかりません。Phase 1 を先に完了してください。"
    exit 1
fi

# ---- 仮想環境の有効化 ----
if [ -d "$VENV_PATH" ]; then
    source "$VENV_PATH/bin/activate"
    echo "仮想環境: $VENV_PATH (有効)"
else
    echo "警告: 仮想環境が見つかりません。システムPython3を使用します。"
fi

# ---- ステップ 1: トークンファイルの確認 ----
echo ""
echo "[1/5] トークンファイルの確認..."
MISSING=0
for f in client_secret_personal.json addness_config.json; do
    if [ -f "$SYSTEM_DIR/$f" ]; then
        echo "  [OK] $f"
    else
        echo "  [NG] $f が見つかりません"
        MISSING=1
    fi
done

TOKEN_COUNT=$(ls "$SYSTEM_DIR"/token*.json 2>/dev/null | wc -l | tr -d ' ')
echo "  token*.json: ${TOKEN_COUNT}個"

if [ "$MISSING" -eq 1 ]; then
    echo ""
    echo "  警告: 一部のトークンファイルが不足しています。"
    echo "  メインPCから transfer_tokens.sh を実行してください。"
fi

# ---- ステップ 2: 動作テスト ----
echo ""
echo "[2/5] AI News Notifier テスト..."
cd "$SYSTEM_DIR"
if python3 -c "import openai; import requests" 2>/dev/null; then
    echo "  依存関係OK。手動実行テスト:"
    echo "    cd $SYSTEM_DIR && python3 ai_news_notifier.py"
else
    echo "  依存関係が不足しています。pip install openai requests を実行してください。"
fi

echo ""
echo "[3/5] Addness フェッチャーテスト..."
if python3 -c "import playwright" 2>/dev/null; then
    echo "  Playwright OK。手動実行テスト:"
    echo "    cd $SYSTEM_DIR && python3 addness_fetcher.py"
else
    echo "  Playwright が見つかりません。pip install playwright && playwright install chromium を実行してください。"
fi

echo ""
echo "[4/5] メール管理テスト..."
if python3 -c "from google.oauth2.credentials import Credentials" 2>/dev/null; then
    echo "  Google API OK。手動実行テスト:"
    echo "    cd $SYSTEM_DIR && python3 mail_manager.py run --dry-run"
else
    echo "  google-auth が見つかりません。pip install google-api-python-client google-auth-oauthlib を実行してください。"
fi

# ---- ステップ 3: Cron ジョブ設定 ----
echo ""
echo "[5/5] Cron ジョブの設定..."
echo ""
echo "以下のcronスクリプトを個別に実行してセットアップしてください:"
echo ""
echo "  # Addness データ取得 (3日ごと 朝8:00)"
echo "  cd $SYSTEM_DIR && bash setup_addness_cron.sh"
echo ""
echo "  # AI ニュース通知 (毎日 朝8:00)"
echo "  cd $SYSTEM_DIR && bash setup_ai_news_cron.sh"
echo ""
echo "  # メール受信管理 (毎時)"
echo "  cd $SYSTEM_DIR && bash setup_mail_inbox_cron.sh"
echo ""

# ---- ステップ 4: LaunchAgent パスの更新 ----
echo "LINE Bot ローカルエージェントの LaunchAgent 設定..."
LOCAL_AGENT_DIR="$SYSTEM_DIR/line_bot_local"
PLIST_FILE="$LOCAL_AGENT_DIR/com.linebot.localagent.plist"

if [ -f "$PLIST_FILE" ]; then
    CURRENT_USER=$(whoami)
    CURRENT_HOME="$HOME"

    # plist内のパスをMac Miniのユーザーに合わせて更新
    if grep -q "/Users/koa800" "$PLIST_FILE"; then
        sed -i '' "s|/Users/koa800|$CURRENT_HOME|g" "$PLIST_FILE"
        echo "  -> plist のパスを $CURRENT_HOME に更新"
    fi

    echo ""
    echo "  エージェントのインストール:"
    echo "    cd $LOCAL_AGENT_DIR && bash install.sh"
else
    echo "  plist ファイルが見つかりません: $PLIST_FILE"
fi

echo ""
echo "========================================"
echo "  Phase 2 セットアップガイド完了"
echo "========================================"
echo ""
echo "各テストを手動で実行し、正常に動作することを確認してください。"
echo "確認後、Phase 3 のエージェントオーケストレーターをセットアップします:"
echo "  cd $SYSTEM_DIR/mac_mini && bash setup_phase3.sh"
