# Mac Mini 運用メモ

## 構成

| マシン | 場所 | Tailscale | 用途 |
|--------|------|-----------|------|
| Mac Mini（秘書） | 自宅 | `mac-mini-agent` / `100.96.200.105` | 秘書 + Orchestrator |
| Mac Mini（日向） | 会社 | 別マシン（触らない） | 日向エージェント |

### 秘書 Mac Mini のアカウント方針
- **Claude Code**: 秘書アカウント（koa800.secretary）のみ。甲原のClaude Codeは使わない
- **Chrome**: 秘書プロファイル（ポート9224）がメイン。甲原のGoogleアカウントはWebサイトログイン時のみ使用

### Chrome 構成
| プロファイル | ポート | Google | claude.ai | 用途 |
|------------|--------|--------|-----------|------|
| ポート9223 Chrome | 9223 | koa800sea.nifs | 甲原 | 甲原としてWebサイト操作 |
| `secretary_chrome_profile` | 9224 | koa800.secretary | koa800.secretary | 秘書 Chrome MCP（メイン） |

### Claude Code CLI
- **パス**: `/opt/homebrew/bin/claude`（npm global install）v2.1.63
- **Node.js**: `/opt/homebrew/bin/node` v25.6.1（brew install）
- **Chrome MCP**: `--chrome` フラグで秘書Chrome（port 9224）のMCPツールに接続
- **設定ディレクトリ**: `~/.claude-secretary`（CLAUDE_CONFIG_DIR）

### Claude Code OAuth自動認証
- PKCE自前生成 → Chrome CDPでOAuth承認 → token交換 → `.credentials.json` に直接保存
- Orchestratorが毎朝08:25に自動リフレッシュ（`_refresh_claude_oauth`）

### launchd plist名
- Orchestrator: `com.addness.agent-orchestrator`
- 日向: `com.hinata.agent`
- local_agent: `com.linebot.localagent`
- 秘書Chrome: `com.secretary.chrome`
- サービス監視: `com.addness.service-watchdog`（Orchestrator非依存、5分ごと）

### 手動トリガー
- `curl -X POST http://mac-mini-agent:8500/schedule/run/{task_name}`

## パス構造（重要・頻出トラブル原因）

| 用途 | MacBook | Mac Mini |
|------|---------|----------|
| ソースコード | `~/Desktop/cursor/System/` | `~/agents/System/` |
| local_agent実行 | `~/Library/LineBot/` | `~/agents/line_bot_local/`（plist WorkingDir） |
| local_agent.py 実体 | — | `~/agents/System/line_bot_local/local_agent.py` |
| local_agent.py シンボリックリンク | — | `~/agents/line_bot_local/local_agent.py` → 実体 |
| credentials | `System/credentials/` | `~/agents/System/credentials/` |
| Orchestrator | — | `~/agents/System/mac_mini/agent_orchestrator/` |
| Orchestratorログ | — | `~/agents/System/mac_mini/agent_orchestrator/logs/` |
| git_pull_sync.sh | — | `~/agents/System/mac_mini/git_pull_sync.sh` |

## qa_monitor_state.json のパス問題（2026-02-25 解決）

- `qa_monitor.py` の `STATE_FILE = Path(__file__).parent / "qa_monitor_state.json"`
- Mac Miniでは実体が `~/agents/System/line_bot_local/` にあるため state は `~/agents/System/line_bot_local/qa_monitor_state.json` に書かれる
- しかし plist の WorkingDir は `~/agents/line_bot_local/` → ランタイムデータはこちらに溜まる
- **両方のパスにstateが必要**。initしたら両方にコピーすること
- stateが消えると過去のQ&A全件（6926件超）が新規として通知される大事故になる

## rsync で絶対に削除してはいけないファイル（2026-02-26 事故）

- `rsync --delete` で `qa_monitor_state.json`, `contact_state.json`, `config.json` が削除されQ&A全件再通知の大事故発生
- **rsync に `--exclude` を必ず付けること**:
  ```bash
  rsync -av --delete \
    --exclude='*.log' --exclude='__pycache__' \
    --exclude='qa_monitor_state.json' --exclude='contact_state.json' \
    --exclude='config.json' --exclude='*.db' \
    ~/agents/_repo/System/line_bot_local/ ~/agents/line_bot_local/
  ```
- `--delete` を使う場合、stateファイルは全て除外する
- 復旧: `cd ~/agents/line_bot_local && ~/agent-env/bin/python3 qa_monitor.py init`

## credentials が Mac Mini に同期されない問題

- `credentials/` は `.gitignore` 対象 → git pull では同期されない
- `token.json` 等は `scp` で手動コピーが必要
- Mac Mini に Google API ライブラリ（`google-auth`, `google-api-python-client`）がシステムPythonにインストールされていない
- `qa_monitor.py init` は MacBook で実行して state ファイルを scp するのが確実

## git_pull_sync が反映されない場合

- bareリポジトリ (`~/agents/_repo/`) の fetch + rsync だが、rsyncエラーが出ることがある
- 緊急時は `scp` で直接ファイルを転送するのが最速
- Orchestrator再起動: `ssh koa800@mac-mini-agent "launchctl unload ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist && launchctl load ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist"`

## local_agent.py が起動しない場合

- `~/agents/line_bot_local/agent_error.log` を確認
- よくある原因: シンボリックリンク切れ（`local_agent.py` → `~/agents/System/line_bot_local/local_agent.py`）
- 修復: `ln -sf ~/agents/System/line_bot_local/local_agent.py ~/agents/line_bot_local/local_agent.py`
- **qa_monitor.py 等の依存モジュールもシンボリックリンクが必要**:
  ```bash
  cd ~/agents/line_bot_local
  for f in ~/agents/System/line_bot_local/*.py; do
    ln -sf "$f" "$(basename $f)"
  done
  ```

## token.json の配置（3箇所必要）

launchd環境ではシンボリックリンクの `__file__` 解決が通常と異なるため、以下の全箇所に配置:
- `~/agents/System/credentials/token.json`（resolve()パス）
- `~/agents/credentials/token.json`（非resolve()パス）
- qa_monitor.py は4候補を順番に探索するよう修正済み（2026-02-25）

## Python 3.12 パッケージ（Mac Mini）

- `google-auth`, `google-api-python-client` を `--break-system-packages` でインストール済み
- パス: `/opt/homebrew/Cellar/python@3.12/3.12.12_2/`
