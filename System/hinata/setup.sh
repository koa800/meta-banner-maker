#!/bin/bash
# ============================================================
# 日向エージェント セットアップスクリプト
#
# 日向のMac Miniで1回だけ実行する。
# 必要なものを全部インストールして、起動できる状態にする。
# ============================================================

set -e

echo "============================="
echo " 日向エージェント セットアップ"
echo "============================="
echo ""

# ---- 1. Homebrew ----
if ! command -v brew &>/dev/null; then
    echo "[1/6] Homebrew をインストール..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc
    eval "$(/opt/homebrew/bin/brew shellenv)"
else
    echo "[1/6] Homebrew ✅"
fi

# PATHを確実に通す
export PATH="/opt/homebrew/bin:$PATH"

# ---- 2. Node.js ----
if ! command -v node &>/dev/null; then
    echo "[2/6] Node.js をインストール..."
    brew install node
else
    echo "[2/6] Node.js ✅ ($(node --version))"
fi

# ---- 3. Python 3.11+ ----
PYTHON_CMD="python3"
PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oE '[0-9]+\.[0-9]+')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -lt 3 ] || ([ "$MAJOR" -eq 3 ] && [ "$MINOR" -lt 11 ]); then
    echo "[3/6] Python 3.11+ をインストール..."
    brew install python@3.13
    PYTHON_CMD="/opt/homebrew/bin/python3.13"
else
    echo "[3/6] Python ✅ ($($PYTHON_CMD --version))"
fi

# ---- 4. Claude Code ----
if ! command -v claude &>/dev/null; then
    echo "[4/6] Claude Code をインストール..."
    npm install -g @anthropic-ai/claude-code
else
    echo "[4/6] Claude Code ✅ ($(claude --version 2>/dev/null || echo 'installed'))"
fi

# ---- 5. Playwright + 依存パッケージ ----
echo "[5/6] Python パッケージをインストール..."
$PYTHON_CMD -m pip install --upgrade pip
$PYTHON_CMD -m pip install playwright

echo "    Chromeブラウザをインストール..."
$PYTHON_CMD -m playwright install chromium
# 実Chrome が既にインストール済みならそちらを使用（bot検知回避に有利）
$PYTHON_CMD -m playwright install chrome 2>/dev/null || echo "    (実Chromeは手動インストールでOK)"

# ---- 6. プロジェクトディレクトリ ----
HINATA_DIR="$HOME/hinata-agent"
echo "[6/6] プロジェクトディレクトリ: $HINATA_DIR"

if [ ! -d "$HINATA_DIR" ]; then
    mkdir -p "$HINATA_DIR"
fi

# hinataのソースコードをコピー（このスクリプトと同じディレクトリから）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp "$SCRIPT_DIR"/hinata_agent.py "$HINATA_DIR/"
cp "$SCRIPT_DIR"/addness_browser.py "$HINATA_DIR/"
cp "$SCRIPT_DIR"/claude_executor.py "$HINATA_DIR/"
cp "$SCRIPT_DIR"/slack_comm.py "$HINATA_DIR/"
cp "$SCRIPT_DIR"/config.json "$HINATA_DIR/"

# ログディレクトリ
mkdir -p "$HINATA_DIR/logs"

echo ""
echo "============================="
echo " セットアップ完了！"
echo "============================="
echo ""
echo "次のステップ:"
echo ""
echo "  1. 環境変数を設定:"
echo "     export SLACK_AI_TEAM_WEBHOOK_URL='...'  "
echo "     export SLACK_USER_TOKEN='...'            "
echo "     export SLACK_BOT_TOKEN='...'             "
echo ""
echo "  2. 初回ログイン（ブラウザが開く。Googleアカウントでログイン）:"
echo "     cd $HINATA_DIR"
echo "     $PYTHON_CMD hinata_agent.py --login"
echo ""
echo "  3. 自動起動を設定:"
echo "     cp $SCRIPT_DIR/com.hinata.agent.plist ~/Library/LaunchAgents/"
echo "     launchctl load ~/Library/LaunchAgents/com.hinata.agent.plist"
echo ""
echo "  4. 手動で起動テスト:"
echo "     cd $HINATA_DIR && $PYTHON_CMD hinata_agent.py"
echo ""
