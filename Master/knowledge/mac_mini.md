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

### Looker Studio のログインアカウント
- **第1候補**: `koa800sea.nifs@gmail.com`（閲覧権限付与済み・ポート9223で自動ログイン可）
- **第2候補**: `kohara.kaito@team.addness.co.jp`（元の権限者。koa800sea.nifsでダメな場合こちらで）
- セッション切れ時は Mac Mini の Chrome で Looker Studio にアクセスし再ログイン

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

### 現在の正本ルール（2026-03-11更新）
- `install_orchestrator.sh` / `git_pull_sync.sh` / `service_watchdog.sh` / `health_check.sh` は、スクリプト自身が置かれた repo root を deploy root として解決する
- `orchestrator.py` / `scheduler.py` / `tools.py` も `ADDNESS_DEPLOY_ROOT` を優先して `System/` / `Master/` / `Skills/` を解決する
- `ADDNESS_DEPLOY_ROOT` を渡した場合だけ、その値を優先する
- deploy root は固定ではない。2026-03-11 21時時点の実機 launchd は `~/agents` で稼働中。`~/Desktop/cursor` から再インストールした場合だけそちらへ切り替わる
- Orchestrator の `/health` は `config_path` / `project_root` / `schedule_enabled` を返す

| 用途 | MacBook | Mac Mini |
|------|---------|----------|
| ソースコード | `~/Desktop/cursor/System/` | `$DEPLOY_ROOT/System/`（現行: `~/agents/System/`） |
| local_agent実行 | `~/Library/LineBot/` | `$DEPLOY_ROOT/line_bot_local/`（現行: `~/agents/line_bot_local/`） |
| local_agent.py 正本 | `~/Desktop/cursor/System/line_bot_local/local_agent.py` | `$DEPLOY_ROOT/System/line_bot_local/local_agent.py` |
| local_agent.py 配置先 | — | `$DEPLOY_ROOT/line_bot_local/local_agent.py`（`git_pull_sync.sh` が同期） |
| credentials | `System/credentials/` | `$DEPLOY_ROOT/System/credentials/`（現行: `~/agents/System/credentials/`） |
| Orchestrator | — | `$DEPLOY_ROOT/System/mac_mini/agent_orchestrator/`（現行: `~/agents/System/mac_mini/agent_orchestrator/`） |
| Orchestratorログ | — | `$DEPLOY_ROOT/System/mac_mini/agent_orchestrator/logs/`（現行: `~/agents/System/mac_mini/agent_orchestrator/logs/`） |
| git_pull_sync.sh | — | `$DEPLOY_ROOT/System/mac_mini/git_pull_sync.sh`（現行: `~/agents/System/mac_mini/git_pull_sync.sh`） |

## qa_monitor_state.json のパス問題（2026-02-25 解決）

- 現行コードでは `qa_monitor.py` / `local_agent.py` ともに runtime state を `~/agents/data/` に集約している
- `qa_monitor_state.json` の正本は `~/agents/data/qa_monitor_state.json`
- `contact_state.json` / `os_sync_state.json` / `config.json` も同じ `~/agents/data/` に置かれる
- deploy root は `~/Desktop/cursor` だが、runtime data は `~/agents/data` に残るので混同しないこと
- stateが消えると過去のQ&A全件（6926件超）が新規として通知される大事故になる

## rsync で絶対に削除してはいけないファイル（2026-02-26 事故）

- `rsync --delete` で `qa_monitor_state.json`, `contact_state.json`, `config.json` が削除されQ&A全件再通知の大事故発生
- **rsync に `--exclude` を必ず付けること**:
  ```bash
  rsync -av --delete \
    --exclude='*.log' --exclude='__pycache__' \
    --exclude='qa_monitor_state.json' --exclude='contact_state.json' \
    --exclude='config.json' --exclude='*.db' \
    $DEPLOY_ROOT/_repo/System/line_bot_local/ $DEPLOY_ROOT/line_bot_local/
  ```
- `--delete` を使う場合、stateファイルは全て除外する
- 復旧: `cd $DEPLOY_ROOT/line_bot_local && ~/agent-env/bin/python3 qa_monitor.py init`

## credentials が Mac Mini に同期されない問題

- `credentials/` は `.gitignore` 対象 → git pull では同期されない
- `token.json` 等は `scp` で手動コピーが必要
- Mac Mini に Google API ライブラリ（`google-auth`, `google-api-python-client`）がシステムPythonにインストールされていない
- `qa_monitor.py init` は MacBook で実行して state ファイルを scp するのが確実

### 検知の仕組み（2026-03-05追加）

- 毎朝08:25の `oauth_health_check` が Gmail トークン（personal/kohara）の存在と有効性を自動検証
- トークン期限切れ・無効化・ファイル不在時はLINE通知（復旧コマンド付き）
- 復旧手順: MacBook の対話ターミナルで `python3 System/mail_manager.py --account {account} run` → 再認証 → `scp` で Mac Mini に転送
- 非対話実行の `mail_manager.py run` は browser を開かず、Slack に再認証必要だけ通知して終了する

## git_pull_sync が反映されない場合

- bareリポジトリは `$DEPLOY_ROOT/_repo/`。現行稼働では `~/agents/_repo/`
- 2026-03-11 以降の `git_pull_sync.sh` は `~/agents` 固定ではなく、スクリプト配置から deploy root を決める
- 緊急時は `scp` で直接ファイルを転送するのが最速
- Orchestrator再起動: `ssh koa800@mac-mini-agent "launchctl unload ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist && launchctl load ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist"`

## local_agent.py が起動しない場合

- `$DEPLOY_ROOT/line_bot_local/agent_error.log` を確認
- よくある原因: 同期先 `$DEPLOY_ROOT/line_bot_local/` が古い、または rsync 後に必要ファイルが欠けている
- 修復: `rsync` を再実行し、`$DEPLOY_ROOT/System/line_bot_local/` から `$DEPLOY_ROOT/line_bot_local/` へ再同期する
- **qa_monitor.py 等の依存モジュールもシンボリックリンクが必要**:
  ```bash
  cd $DEPLOY_ROOT/line_bot_local
  rsync -av --exclude='config.json' --exclude='*.log' \
    $DEPLOY_ROOT/System/line_bot_local/ ./
  ```

## token.json の配置（3箇所必要）

launchd環境ではシンボリックリンクの `__file__` 解決が通常と異なるため、以下の全箇所に配置:
- `$DEPLOY_ROOT/System/credentials/token.json`
- `$DEPLOY_ROOT/credentials/token.json`
- qa_monitor.py は4候補を順番に探索するよう修正済み（2026-02-25）

## Python 3.12 パッケージ（Mac Mini）

- `google-auth`, `google-api-python-client` を `--break-system-packages` でインストール済み
- パス: `/opt/homebrew/Cellar/python@3.12/3.12.12_2/`
