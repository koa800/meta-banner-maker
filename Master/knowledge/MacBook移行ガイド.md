# MacBook移行ガイド

最終更新: 2026-03-13

## 概要

MacBook を新しい機種に交換する時の手順。
Mac Mini と Render は継続稼働するので、停止前提の作業は不要。

今回の推奨方針は次です。

1. 基本の移行手段は macOS の `移行アシスタント`
2. 旧MacBookの home 配下も移る前提で進める
3. ただし、`cursor/` 側に別バックアップを残して保険を持つ
4. 移行後の最初の入口は Cursor のターミナルで `System/scripts/macbook_post_migration_check.sh`

重要なのは、`旧MacBookを最新OSにすること` 自体を主目的にしないこと。
移行を安定させる優先順位は、`新MacBookが旧MacBook以上のmacOSで受け入れられること` と、`移行後に Cursor から復元確認できること`。
時間に余裕がない状態で、旧MacBookに大きい OS 更新を先に当てるのは、時間と失敗面を増やしやすい。
旧MacBookの OS 更新は `必要ならやる` でよく、`移行の必須条件` ではない。

今回の前提で重要なのは次の 2 層です。

1. `cursor/` 配下の正本
2. `~/.codex/` と `~/.claude/` にある実行環境固有データ

`ai` の current work / batch / handoff / session snapshot は、正本をリポジトリ側に寄せた。
そのため、新 MacBook でも `git clone` 後に `ai doctor` と `ai restore` で復元しやすい。

ただし、元の会話をそのまま `resume` したいなら、`~/.codex/sessions/` または `~/.claude/history.jsonl` も移す必要がある。
移さなくても、保存済み snapshot と handoff から `rehydrate` で続行はできる。

---

## 正本とローカル依存の切り分け

### リポジトリ側の正本

これらは `git clone` で復元される。

| パス | 役割 |
|------|------|
| `System/data/ai_router/work_index.json` | current work 一覧 |
| `System/data/ai_router/batch_index.json` | batch queue 正本 |
| `System/data/ai_router/skill_candidate_index.json` | skill 候補正本 |
| `System/data/ai_router/handoffs/` | per-work handoff 正本 |
| `.ai_handoff.md` | current work の mirror |
| `Master/output/session_aliases.json` | session 別名 |
| `Master/output/session_restore_index.json` | session snapshot 要約 |

### ローカル依存

これらは home 配下にあるので、必要なら個別に移す。

| パス | 必須度 | 理由 |
|------|--------|------|
| `~/.codex/config.toml` | 必須 | `approval_policy` / `sandbox_mode` など実行設定 |
| `~/.codex/auth.json` | 推奨 | Codex 再ログインを省ける |
| `~/.codex/sessions/` | 条件付き | 旧 session を live resume したい時だけ必要 |
| `~/.codex/skills/` | 推奨 | `Skills/` へのリンク状態の確認用 |
| `~/.claude/` | 推奨 | Claude Code の設定 |
| `~/.claude/history.jsonl` | 条件付き | Claude の旧 session を live resume したい時だけ必要 |
| `.git/hooks/post-commit` | 必須 | commit 後の自動 push |

---

## 移行前に旧MacBookでやること

### 0. OS 更新の判断

推奨は次です。

- 最優先は `新MacBook` 側が `旧MacBook以上の macOS` であること
- `旧MacBook` の大きい OS 更新は、時間に余裕がある時だけ行う
- 旧MacBookが今の状態で安定していて、移行アシスタントが使えるなら、そのまま移行してよい

つまり、`旧MacBookを最新OSにしないと移行できない` とは考えない。
先にやるべきなのは OS 更新より、push と復元素材の保全。

### 1. GitHub 側へ必ず push する

```bash
cd /Users/koa800/Desktop/cursor
git status
git push origin main
```

未コミット変更がある場合は、移行前に commit するか、最低でも何が未保存か把握してから移る。

### 2. `ai` の復元素材が揃っているか確認する

```bash
cd /Users/koa800/Desktop/cursor
System/scripts/ai doctor
System/scripts/ai status
```

ここで最低限見たいもの:

- `work_index.json`
- `batch_index.json`
- `skill_candidate_index.json`
- `handoffs/`
- `session_aliases.json`
- `session_restore_index.json`
- `.git/hooks/post-commit`
- `~/.codex/config.toml`
- latest session verify

### 3. `~/.codex/` を退避する

live resume を残したいなら `sessions/` まで含めて丸ごと退避してよい。

```bash
mkdir -p ~/Desktop/migration_backup
cp ~/.codex/config.toml ~/Desktop/migration_backup/codex-config.toml
cp ~/.codex/auth.json ~/Desktop/migration_backup/codex-auth.json 2>/dev/null || true
cp -R ~/.codex/sessions ~/Desktop/migration_backup/codex-sessions 2>/dev/null || true
cp -R ~/.codex/skills ~/Desktop/migration_backup/codex-skills 2>/dev/null || true
```

### 4. `~/.claude/` を退避する

```bash
cp -R ~/.claude ~/Desktop/migration_backup/claude-home 2>/dev/null || true
cp ~/.claude/history.jsonl ~/Desktop/migration_backup/claude-history.jsonl 2>/dev/null || true
```

### 5. post-commit フックを退避する

```bash
cp /Users/koa800/Desktop/cursor/.git/hooks/post-commit ~/Desktop/migration_backup/post-commit
```

### 6. SSH鍵を退避する

```bash
mkdir -p ~/Desktop/migration_backup/ssh
cp ~/.ssh/id_rsa ~/Desktop/migration_backup/ssh/id_rsa 2>/dev/null || true
cp ~/.ssh/id_rsa.pub ~/Desktop/migration_backup/ssh/id_rsa.pub 2>/dev/null || true
cp ~/.ssh/id_ed25519 ~/Desktop/migration_backup/ssh/id_ed25519 2>/dev/null || true
cp ~/.ssh/id_ed25519.pub ~/Desktop/migration_backup/ssh/id_ed25519.pub 2>/dev/null || true
cp ~/.ssh/config ~/Desktop/migration_backup/ssh/config 2>/dev/null || true
```

---

## 新MacBookでのセットアップ

### 移行アシスタントを使う場合の推奨順

今回の標準ルートはこれです。

1. 新MacBookを起動し、必要なら `新MacBook` 側だけ先に OS を更新する
2. `移行アシスタント` で旧MacBookから `アプリ / ユーザー / その他のファイルとフォルダ / コンピュータとネットワーク設定` を移す
3. 移行完了後、新MacBookで Cursor を起動する
4. Cursor のターミナルで次を実行する

```bash
cd ~/Desktop/cursor
System/scripts/macbook_post_migration_check.sh
```

5. スクリプトの確認が通ったら、続けたい仕事を復元する

```bash
System/scripts/ai restore <別名>
```

6. もし home 配下や repo 状態の移行漏れがあれば、`System/data/migration_backup_*` の退避物で補う

`移行アシスタント` で十分に移った場合は、以下の手動復元は不要。
以降の節は、`移行アシスタントで不足した時の保険` として使う。

### 1. 最低限のツールを入れる

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git
```

Codex CLI / Claude Code の実行ファイルは、ふだん使っている方法で入れる。
`ai doctor` は `PATH` を優先し、見つからなければ `~/.npm-global/bin/codex` と `~/.local/bin/claude` も確認する。

### 2. リポジトリを clone する

```bash
mkdir -p ~/Desktop
cd ~/Desktop
git clone <GitHubリポジトリURL> cursor
cd cursor
git submodule update --init
```

### 3. post-commit フックを戻す

バックアップがあるならそれを戻す。
無い場合は最低限 `git push origin main` が走る状態を作る。

```bash
cp ~/Desktop/migration_backup/post-commit ~/Desktop/cursor/.git/hooks/post-commit 2>/dev/null || true
chmod +x ~/Desktop/cursor/.git/hooks/post-commit
```

### 4. `~/.codex/` を戻す

```bash
mkdir -p ~/.codex
cp ~/Desktop/migration_backup/codex-config.toml ~/.codex/config.toml 2>/dev/null || true
cp ~/Desktop/migration_backup/codex-auth.json ~/.codex/auth.json 2>/dev/null || true
cp -R ~/Desktop/migration_backup/codex-sessions ~/.codex/sessions 2>/dev/null || true
cp -R ~/Desktop/migration_backup/codex-skills ~/.codex/skills 2>/dev/null || true
```

`auth.json` を戻さない場合は、Codex を一度起動して再ログインする。

### 5. `~/.claude/` を戻す

```bash
cp -R ~/Desktop/migration_backup/claude-home ~/.claude 2>/dev/null || true
cp ~/Desktop/migration_backup/claude-history.jsonl ~/.claude/history.jsonl 2>/dev/null || true
```

### 6. Claude Code を Max で認証する

```bash
claude
```

`Claude account with subscription` を選び、Max アカウントで認証する。
`.zshrc` に `ANTHROPIC_API_KEY` を export しないこと。

### 7. SSH鍵を戻す

```bash
mkdir -p ~/.ssh
cp ~/Desktop/migration_backup/ssh/* ~/.ssh/ 2>/dev/null || true
chmod 600 ~/.ssh/id_rsa 2>/dev/null || true
chmod 600 ~/.ssh/id_ed25519 2>/dev/null || true
```

必要なら新規生成して Mac Mini に公開鍵を追加する。

---

## `ai` の復元確認

### 最低ライン

```bash
cd ~/Desktop/cursor
System/scripts/macbook_post_migration_check.sh
System/scripts/ai doctor
System/scripts/ai status
System/scripts/ai works
System/scripts/ai sessions
```

### 旧 session をそのまま再開したい時

`~/.codex/sessions/` または `~/.claude/history.jsonl` を戻しているなら、通常どおり `resume` / `fork` が使える。

```bash
System/scripts/ai restore <別名 or session_id>
System/scripts/ai restore --fork <別名 or session_id>
```

### session 履歴を持ってこなかった時

この場合でも、`session_restore_index.json` と handoff があれば `ai restore` は新規セッションを `rehydrate` で起動する。
つまり、元 session を live resume はできないが、保存済みの `目的 / 完了 / 未完了 / 判断` を注入して続行できる。

推奨入口:

```bash
System/scripts/ai pins
System/scripts/ai restore <別名>
```

### session snapshot の検証

live session がある環境では、保存経路も確認しておく。

```bash
System/scripts/ai session verify codex
System/scripts/ai session verify claude
```

`codex` / `claude` の latest session が無い場合は `not_found` でよい。
`live-ready` は、その Mac に live session 履歴が来ているので旧MacBook不要の状態を意味する。
`review` が出る場合だけ、session snapshot 保存やローカル履歴の有無を確認する。

---

## batch / skill 候補の移行確認

batch と skill 候補の正本はリポジトリ側にある。
そのため `git clone` 後に index はそのまま見える。

```bash
System/scripts/ai batches
System/scripts/ai batch skills
System/scripts/ai batch skill show <batch>
```

必要なら `Skills/` への昇格も新 MacBook 側で続行できる。

```bash
System/scripts/ai batch skill promote <batch> <category> <slug> --title "Skill title"
```

---

## Mac Mini 側の対応

原則不要。

| サービス | 状態 |
|---------|------|
| Orchestrator | 継続稼働 |
| local_agent | 継続稼働 |
| git_pull_sync | GitHub から pull し続ける |
| token / DB / 学習データ | Mac Mini / Render 側に残る |

MacBook 交換で止まるのは、MacBook 側の commit / push / local CLI 作業だけ。

---

## Google Calendar OAuth

カレンダー機能を使うなら、必要に応じて再度 token を Mac Mini に渡す。

```bash
cd ~/Desktop/cursor/System
python3 calendar_manager.py --account personal list
scp System/token_calendar_personal.json koa800@mac-mini-agent.local:~/agents/System/
```

---

## 最終チェックリスト

- [ ] `git push` が通る
- [ ] `.git/hooks/post-commit` が復元されている
- [ ] `codex` と `claude` が起動する
- [ ] `System/scripts/macbook_post_migration_check.sh` が通る
- [ ] `System/scripts/ai doctor` が `doctor_result: ok`
- [ ] `System/scripts/ai status` で current work と handoff が見える
- [ ] `System/scripts/ai works` / `System/scripts/ai sessions` が期待どおり表示される
- [ ] 旧 session をそのまま使いたいなら `~/.codex/sessions/` または `~/.claude/history.jsonl` を戻している
- [ ] 戻していない場合でも、`ai restore <別名>` が snapshot rehydrate で続行できる
- [ ] `System/scripts/ai batches` / `ai batch skills` が見える
- [ ] `.zshrc` に `ANTHROPIC_API_KEY` を入れていない

---

## 重要メモ

- `session_restore_index.json` は live session そのものではない。要約と復元メモの正本
- 生の `resume` が必要なら、`~/.codex/sessions/` または `~/.claude/history.jsonl` が必要
- それが無くても、current work handoff と session snapshot があれば仕事は継続できる
- 移行後の最初の確認順は `ai doctor -> ai status -> ai pins -> ai restore <別名>` が基本
