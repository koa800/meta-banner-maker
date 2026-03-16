#!/bin/bash
#
# Phase 1: 開発環境の構築
#
# SSH 経由またはモニター直接で実行する。
# Phase 0 完了後に実行すること。
#
# 使い方:
#   chmod +x setup_phase1.sh
#   ./setup_phase1.sh
#

set -e

echo "========================================"
echo "  Mac Mini Agent - Phase 1 開発環境構築"
echo "========================================"
echo ""

# ---- Xcode Command Line Tools ----
echo "[1/6] Xcode Command Line Tools..."
if xcode-select -p &>/dev/null; then
    echo "  -> 既にインストール済み"
else
    echo "  -> インストール中..."
    xcode-select --install
    echo "  -> インストールダイアログが表示されます。完了後に再度このスクリプトを実行してください。"
    exit 0
fi

# ---- Homebrew ----
echo "[2/6] Homebrew..."
if command -v brew &>/dev/null; then
    echo "  -> 既にインストール済み ($(brew --version | head -1))"
else
    echo "  -> インストール中..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # M1/M2/M4 の場合は /opt/homebrew にインストールされる
    if [ -f /opt/homebrew/bin/brew ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
fi

# ---- 基本パッケージ ----
echo "[3/6] 基本パッケージをインストール..."
brew install git python@3.12 node rclone jq coreutils 2>/dev/null || true
brew install --cask google-cloud-sdk 2>/dev/null || true
echo "  -> git, python3.12, node, rclone, jq, coreutils, gcloud"

# ---- Python 仮想環境 ----
echo "[4/6] Python 仮想環境を作成..."
VENV_PATH="$HOME/agent-env"
BREW_PYTHON="$(brew --prefix python@3.12 2>/dev/null)/bin/python3.12"
if [ ! -x "$BREW_PYTHON" ]; then
    BREW_PYTHON="$(command -v python3.12 2>/dev/null || true)"
fi
if [ -z "$BREW_PYTHON" ] || [ ! -x "$BREW_PYTHON" ]; then
    echo "  -> python3.12 が見つかりません。Homebrew の python@3.12 を確認してください。"
    exit 1
fi

if [ -d "$VENV_PATH" ] && [ -x "$VENV_PATH/bin/python3" ]; then
    if "$VENV_PATH/bin/python3" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
        echo "  -> 既に存在: $VENV_PATH"
    else
        echo "  -> 既存仮想環境が Python 3.10 未満のため再作成します"
        rm -rf "$VENV_PATH"
        "$BREW_PYTHON" -m venv "$VENV_PATH"
        echo "  -> 作成: $VENV_PATH"
    fi
else
    rm -rf "$VENV_PATH"
    "$BREW_PYTHON" -m venv "$VENV_PATH"
    echo "  -> 作成: $VENV_PATH"
fi

if ! "$VENV_PATH/bin/python3" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"; then
    echo "  -> 仮想環境の Python が 3.10 以上ではありません"
    exit 1
fi

source "$VENV_PATH/bin/activate"
"$VENV_PATH/bin/python3" -m pip install --upgrade pip setuptools wheel
echo "  -> pip, setuptools, wheel を更新"

# ---- Google Cloud SDK 初期設定 ----
echo "[5/6] Google Cloud SDK 初期設定..."
if command -v gcloud &>/dev/null; then
    echo "  -> gcloud が利用可能"
    echo "  -> 認証状態を確認..."
    if gcloud auth list --format="value(account)" 2>/dev/null | head -1 | grep -q "@"; then
        echo "  -> 認証済み: $(gcloud auth list --format='value(account)' 2>/dev/null | head -1)"
    else
        echo ""
        echo "  gcloud の認証が必要です。以下を実行してください:"
        echo "    gcloud auth login"
        echo "    gcloud config set project <PROJECT_ID>"
        echo ""
    fi
else
    echo "  -> gcloud が見つかりません。手動でインストールしてください。"
fi

# ---- リポジトリクローン ----
echo "[6/6] リポジトリのクローン..."
REPO_PATH="$HOME/Desktop/cursor"
if [ -d "$REPO_PATH/.git" ]; then
    echo "  -> 既に存在: $REPO_PATH"
    echo "  -> 最新を取得..."
    cd "$REPO_PATH"
    git pull --recurse-submodules
else
    echo "  -> クローン先: $REPO_PATH"
    echo ""
    echo "  以下を実行してリポジトリをクローンしてください:"
    echo "    cd ~/Desktop"
    echo "    git clone --recurse-submodules <リポジトリURL> cursor"
    echo ""
fi

# ---- Python 依存関係 ----
echo ""
echo "Python 依存関係をインストール..."
source "$VENV_PATH/bin/activate"

SYSTEM_DIR="$REPO_PATH/System"
if [ -d "$SYSTEM_DIR" ]; then
    # ローカルエージェント依存関係
    if [ -f "$SYSTEM_DIR/line_bot_local/requirements.txt" ]; then
        "$VENV_PATH/bin/python3" -m pip install -r "$SYSTEM_DIR/line_bot_local/requirements.txt"
        echo "  -> line_bot_local 依存関係インストール済み"
    fi

    # Playwright
    "$VENV_PATH/bin/python3" -m pip install playwright apscheduler fastapi uvicorn watchdog pyyaml aiohttp aiosqlite
    "$VENV_PATH/bin/python3" -m playwright install chromium
    echo "  -> Playwright + オーケストレーター依存関係インストール済み"

    # オーケストレーター依存関係
    if [ -f "$SYSTEM_DIR/mac_mini/agent_orchestrator/requirements.txt" ]; then
        "$VENV_PATH/bin/python3" -m pip install -r "$SYSTEM_DIR/mac_mini/agent_orchestrator/requirements.txt"
        echo "  -> agent_orchestrator 依存関係インストール済み"
    fi
fi

echo ""
echo "========================================"
echo "  Phase 1 完了"
echo "========================================"
echo ""
echo "仮想環境の有効化:"
echo "  source $VENV_PATH/bin/activate"
echo ""
echo "次のステップ:"
echo "  1. メインPCから transfer_tokens.sh でトークンを転送する"
echo "  2. setup_phase2.sh で既存ジョブを移行する"
