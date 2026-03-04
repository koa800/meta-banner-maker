# MacBook移行ガイド

最終更新: 2026-02-21（GitHub同期移行に伴い簡素化）

## 概要

MacBookを新しい機種に交換する際の手順。**Mac Miniは影響なし**（全データ・サービスはMac Miniで独立稼働）。

---

## 実際に必要なもの（最小セット）

| 種別 | 必要なもの | 理由 |
|------|------------|------|
| **必須** | `cursor` リポジトリの最新 push | 新MacBookでは `git clone` のみで復元可能 |
| **必須** | post-commit フック 1ファイル | `.git/hooks/` はリポジトリに含まれないため手動復元（内容は `git push origin main` のみ） |
| **推奨** | SSH鍵（旧の移行 or 新規生成） | Mac Mini へのデバッグ接続用。同期自体はGitHub経由なので不要 |
| **推奨** | `~/.claude/` のバックアップ | Claude Code の設定・MEMORY。無くても新規セットアップ可 |
| **条件付き** | `token_calendar_personal.json` | 朝の予定通知を使う場合のみ。初回は MacBook で OAuth 後に Mac Mini へ scp |

**不要なもの（移行しなくてよい）**

- Q&Aデータ・LINE秘書学習データ・Addnessゴール・agent.db・token.json → すべて Mac Mini / Render / GitHub 側にある

---

## 移行前チェックリスト（旧MacBookで作業）

### 1. SSHキーのバックアップ
```bash
# 旧MacBookのSSH鍵をバックアップ
cp ~/.ssh/id_rsa ~/Desktop/ssh_backup_id_rsa
cp ~/.ssh/id_rsa.pub ~/Desktop/ssh_backup_id_rsa.pub
cp ~/.ssh/config ~/Desktop/ssh_backup_config 2>/dev/null
```
※ あるいは新MacBookで新規生成して Mac Mini に公開鍵を追加する（下記参照）

### 2. Claude Code設定のバックアップ
```bash
# MEMORY.md・設定ファイルを含む ~/.claude/ をバックアップ
cp -r ~/.claude ~/Desktop/claude_backup/
```

### 3. post-commit フックのバックアップ
```bash
# gitに含まれないため個別バックアップが必要
cp /Users/koa800/Desktop/cursor/.git/hooks/post-commit ~/Desktop/post-commit-backup
```

### 4. Gitリポジトリのプッシュ確認
```bash
cd /Users/koa800/Desktop/cursor
git status   # 未コミットの変更がないか確認
git push origin main
```

---

## 移行後セットアップ（新MacBookで作業）

### ステップ1: Homebrewとgitのインストール
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git
```

### ステップ2: リポジトリのクローン
```bash
mkdir -p ~/Desktop
cd ~/Desktop
git clone <GitHubリポジトリURL> cursor
cd cursor
git submodule update --init
```

### ステップ3: post-commit フックの設置
```bash
# post-commit フックを作成（git push するだけのシンプルなフック）
cat > ~/Desktop/cursor/.git/hooks/post-commit << 'HOOK'
#!/bin/bash
LOG_FILE="$HOME/Desktop/cursor-sync.log"
(
  git push origin main 2>> "$LOG_FILE" &
) &
HOOK
chmod +x ~/Desktop/cursor/.git/hooks/post-commit
```

### ステップ4: Claude Code の設定復元
```bash
# バックアップから復元
cp -r ~/Desktop/claude_backup ~/.claude
```
または新規セットアップ（`~/.claude/settings.json` で bypassPermissions を設定）。

#### Claude Code の認証（Max プランで使う）

Claude Code は **Max プラン（月額定額）** で認証して使う。API 従量課金にしないこと。

```bash
claude
# → 「1. Claude account with subscription」を選択してブラウザで Max アカウントにログイン
```

**重要: `.zshrc` に `ANTHROPIC_API_KEY` を export しないこと。**
設定されていると Claude Code が API 従量課金に切り替わる。
他スクリプト（line_bot_local 等）は Secret Manager から自動取得する仕組みがあるため影響なし。

詳細: `.cursor/rules/claude-code-max-cursor-terminal.mdc`

### ステップ5: SSH鍵の設定

**オプションA: 旧鍵を新MacBookに移行**
```bash
mkdir -p ~/.ssh
cp ~/Desktop/ssh_backup_id_rsa ~/.ssh/id_rsa
cp ~/Desktop/ssh_backup_id_rsa.pub ~/.ssh/id_rsa.pub
chmod 600 ~/.ssh/id_rsa
```

**オプションB: 新規生成して Mac Mini に登録**
```bash
# 新規生成
ssh-keygen -t ed25519 -C "new-macbook"

# Mac Mini に公開鍵を追加
ssh-copy-id koa800@mac-mini-agent.local
# または手動: cat ~/.ssh/id_ed25519.pub | ssh koa800@mac-mini-agent.local "cat >> ~/.ssh/authorized_keys"
```

### ステップ6: 動作確認
```bash
# post-commit フックのテスト（空コミット）
cd ~/Desktop/cursor
git commit --allow-empty -m "post-commit フックテスト"
# → git log origin/main で push されていることを確認

# （任意）Mac Mini に接続できるか確認
ssh koa800@mac-mini-agent.local "echo 接続OK"
```

---

## Mac Mini 側の対応（影響なし）

Mac Miniのサービスはすべて自律稼働しており、**MacBook交換時の作業不要**。

| サービス | 状態 |
|---------|------|
| Orchestrator (port 8500) | 継続稼働 |
| local_agent (LINE秘書) | 継続稼働 |
| git_pull_sync (5分ごと) | GitHubからpull→デプロイ。MacBook無関係で動作 |
| Google OAuth token.json | ~/agents/token.json で管理済み |

同期はGitHub経由のため、**新MacBookのホスト名やSSH設定はMac Mini側に影響しない**。

---

## Google Calendar OAuth セットアップ（Mac Mini）

カレンダー機能（朝の予定通知）を使うためには、Mac Miniで一度だけOAuth認証が必要。

```bash
# MacBookで実行（ブラウザが開く）
cd ~/Desktop/cursor/System
python3 calendar_manager.py --account personal list

# 認証完了後、token_calendar_personal.json が生成される
# Mac Mini にコピー
scp System/token_calendar_personal.json koa800@mac-mini-agent.local:~/agents/System/
```

> 注意: `client_secret_personal.json` が `client_secret.json` と別になっている場合は
> `calendar_manager.py` の `CLIENT_SECRET_PATH` を変更するか、`client_secret_personal.json` を `client_secret.json` にコピー。

---

## 移行後の最終確認

- [ ] `git push` が正常に動作する
- [ ] post-commit フック実行後、Mac Mini のログに同期完了が記録される
- [ ] Claude Code が正常に起動する（`claude` コマンド）
- [ ] Claude Code が「Opus · Claude Max」と表示される（API Usage Billing でないこと）
- [ ] `.zshrc` に `ANTHROPIC_API_KEY` が **含まれていない**ことを確認
- [ ] Mac Mini の Orchestrator ログに問題がない
- [ ] LINE秘書への通知が届く
- [ ] Google Calendar OAuth セットアップ（`token_calendar_personal.json` を Mac Mini にコピー）

---

## 自動化されているもの（移行で止まらない）

いずれも **Mac Mini または Render 上で動いており、MacBook交換時は何もしなくてよい**。新MacBookでSSH・post-commitが復活すれば、5分同期とコミット時同期が再開する。

| 種別 | 実行間隔 | 内容 |
|------|----------|------|
| **Orchestrator** | 5分ごと | `git_pull_sync`（GitHubからpull→ローカルデプロイ→サービス再起動） |
| **Orchestrator** | 5分ごと | `health_check`（API使用量・Q&A・local_agent停止を検知してLINE警告） |
| **Orchestrator** | 30分ごと | `repair_check`（ログエラー検知・修復提案）, `render_health_check`（Render死活） |
| **Orchestrator** | 毎時 :00 / :30 | `mail_inbox_personal` / `mail_inbox_kohara`（メール取得・分類・返信待ちLINE通知） |
| **Orchestrator** | 毎朝 8:00 | `ai_news`（AIニュース要約・通知）, `addness_fetch`（3日ごと: ゴールツリー取得） |
| **Orchestrator** | 毎朝 8:30 / 9:00 | `daily_addness_digest`（期限超過通知）, `addness_goal_check`（actionable再生成）, `oauth_health_check` |
| **Orchestrator** | 毎週月 9:00 / 9:30 | `weekly_idea_proposal`, `weekly_stats`（週次サマリーLINE） |
| **Orchestrator** | 毎週水 10:00 | `weekly_content_suggestions`（AIニュース分析・コンテンツ提案） |
| **Orchestrator** | 毎夜 21:00 | `daily_report`（日次タスク集計LINE） |
| **MacBook側** | コミット時 | post-commit フック → `git push origin main`（Mac Miniは5分以内にpullして反映） |
| **LINE秘書** | 常駐 | local_agent がRenderをポーリング・返信案生成・Claude API呼び出し |
| **その他** | — | Q&A自動回答（検知→回答案→承認→L-step送信）, OAuth refresh_token 自動更新 |

---

## 重要: 移行が不要なもの

以下はすべて Mac Mini または GitHub に保存されているため、**新MacBookでは何もしなくてよい**:

- SkillPlus Q&Aデータ（Mac Miniの qa_sync/）
- LINE秘書の学習データ（Renderの永続ディスク）
- Addnessゴールツリー（Mac Miniの ~/agents/Master/）
- Google OAuth token.json（Mac Miniの ~/agents/token.json）
- Orchestratorの実行履歴DB（Mac Miniの agent.db）
