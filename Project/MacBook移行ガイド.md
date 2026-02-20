# MacBook移行ガイド

最終更新: 2026-02-21

## 概要

MacBookを新しい機種に交換する際の手順。**Mac Miniは影響なし**（全データ・サービスはMac Miniで独立稼働）。

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
# バックアップから復元
cp ~/Desktop/post-commit-backup ~/Desktop/cursor/.git/hooks/post-commit
chmod +x ~/Desktop/cursor/.git/hooks/post-commit
```
または [.git/hooks/post-commit の内容](../.git/hooks/post-commit) を参照して手動作成。

### ステップ4: Claude Code の設定復元
```bash
# バックアップから復元
cp -r ~/Desktop/claude_backup ~/.claude
```
または新規セットアップ（`~/.claude/settings.json` で bypassPermissions を設定）。

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
# Mac Mini に接続できるか確認
ssh koa800@mac-mini-agent.local "echo 接続OK"

# post-commit フックのテスト（空コミット）
cd ~/Desktop/cursor
git commit --allow-empty -m "post-commit フックテスト"
# → cursor-sync.log に同期ログが記録されることを確認
```

---

## Mac Mini 側の対応（影響なし）

Mac Miniのサービスはすべて自律稼働しており、**MacBook交換時の作業不要**。

| サービス | 状態 |
|---------|------|
| Orchestrator (port 8500) | 継続稼働 |
| local_agent (LINE秘書) | 継続稼働 |
| 5分ごとの自動同期 | 新MacBookが応答するまでSKIP |
| Google OAuth token.json | ~/agents/token.json で管理済み |

新MacBookのhostnameが変わる場合は、Mac Mini の `sync_from_macbook.sh` の `MACBOOK=` 変数を更新が必要：
```bash
# Mac Mini で実行
# MacBook-Pro-9.local → 新しいホスト名に変更
ssh koa800@mac-mini-agent.local "
  sed -i '' 's/MacBook-Pro-9.local/新ホスト名.local/' ~/agents/sync_from_macbook.sh
"
```

新MacBookのmDNSホスト名確認:
```bash
# 新MacBookで実行
scutil --get LocalHostName
# → この値.local が mDNS ホスト名
```

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
- [ ] Mac Mini の Orchestrator ログに問題がない
- [ ] LINE秘書への通知が届く
- [ ] Google Calendar OAuth セットアップ（`token_calendar_personal.json` を Mac Mini にコピー）

---

## 重要: 移行が不要なもの

以下はすべて Mac Mini または GitHub に保存されているため、**新MacBookでは何もしなくてよい**:

- SkillPlus Q&Aデータ（Mac Miniの qa_sync/）
- LINE秘書の学習データ（Renderの永続ディスク）
- Addnessゴールツリー（Mac Miniの ~/agents/Master/）
- Google OAuth token.json（Mac Miniの ~/agents/token.json）
- Orchestratorの実行履歴DB（Mac Miniの agent.db）
