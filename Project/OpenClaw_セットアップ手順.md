# 日向（OpenClaw）Mac Mini セットアップ手順

## 前提条件

- Mac Mini（Apple Silicon推奨）
- macOSソフトウェアアップデート完了
- インターネット接続済み
- Slack #ai-team チャネル作成済み
- 日向のGoogle Workspaceアカウント作成済み

---

## Step 1: 基本ツールのインストール

### Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

インストール後、表示される指示に従いPATHを設定：
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
eval "$(/opt/homebrew/bin/brew shellenv)"
```

### Node.js 22+

```bash
brew install node@22
```

keg-onlyの場合はPATHに追加：
```bash
echo 'export PATH="/opt/homebrew/opt/node@22/bin:$PATH"' >> ~/.zprofile
source ~/.zprofile
```

確認：
```bash
node --version  # v22.x.x であること
npm --version
```

---

## Step 2: OpenClaw インストール

### インストーラー実行

```bash
curl -fsSL https://openclaw.ai/install.sh | bash
```

### オンボーディング（対話形式）

```bash
openclaw onboard --install-daemon
```

`--install-daemon` で launchd サービスが自動登録され、24時間稼働になる。

オンボーディングで聞かれる項目：

| 質問 | 設定値 |
|------|--------|
| Model provider | Anthropic (Claude) |
| API key | Claude Max プランのAPIキー |
| Workspace | `~/.openclaw/workspace` |
| Gateway bind | `0.0.0.0:3001`（Tailscale経由でアクセスする場合） |
| Gateway auth | `token`（トークンを設定） |

---

## Step 3: Slack 連携

### Slack アプリの設定

1. https://api.slack.com/apps にアクセス（日向のGoogle Workspaceアカウントで）
2. **Create New App** → **From scratch**
3. App Name: `日向` / Workspace: Addnessのワークスペース
4. **Incoming Webhooks** を有効化
5. **Add New Webhook to Workspace** → #ai-team を選択 → **Allow**
6. 生成されたWebhook URLをメモ

### OpenClaw の Slack チャネル設定

```bash
npx clawdhub@latest install slack-integration
```

または `openclaw.json` に直接設定：

```json5
{
  "channels": {
    "slack": {
      "enabled": true,
      // Slack App の設定に従って認証情報を記入
    }
  }
}
```

※ 詳細は `openclaw onboard` の対話形式で設定可能。

---

## Step 4: Claude Code Skill インストール

日向がClaude Codeでタスクを実行するためのスキル。

```bash
git clone https://github.com/Enderfga/openclaw-claude-code-skill.git ~/.openclaw/skills/claude-code-skill
cd ~/.openclaw/skills/claude-code-skill
npm install
npm run build
```

セッション開始テスト：
```bash
claude-code-skill session-start test -d ~/test-project
```

---

## Step 5: 環境変数の設定

### ~/.openclaw/.env

```bash
# Claude API（Maxプラン）
ANTHROPIC_API_KEY=sk-ant-...

# OpenClaw Gateway認証
OPENCLAW_GATEWAY_TOKEN=（オンボーディングで生成された値）
```

### AI秘書Mac Mini側の環境変数

AI秘書のMac MiniのOrchestratorに、Slack #ai-team のWebhook URLを追加。

launchd plistに追加（`/tmp/fix_plist.py` パターン）：
```
SLACK_AI_TEAM_WEBHOOK_URL=https://hooks.slack.com/services/T.../B.../...
```

追加後、Orchestratorを再起動：
```bash
launchctl unload ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist
launchctl load ~/Library/LaunchAgents/com.addness.agent-orchestrator.plist
```

---

## Step 6: 動作確認

### OpenClaw が起動しているか

```bash
openclaw status
```

### Slack テスト送信

Slackで日向に DM を送り、応答があるか確認。

### AI秘書側のSlack通知テスト

AI秘書Mac Miniで：
```bash
cd ~/agents/System/mac_mini/agent_orchestrator
python3 -c "from notifier import send_slack_ai_team; send_slack_ai_team('テスト通知: AI秘書からSlack #ai-teamへの送信確認')"
```

Slack #ai-team にメッセージが届けば成功。

---

## Step 7: スケジュール設定

OpenClawのスケジューリングは `openclaw.json` または cron で設定。

日向の日次/週次サイクル：

```json5
{
  "schedule": {
    // 日次タスク
    "daily_addness_check": { "cron": "0 8 * * *", "task": "Addnessゴールツリー巡回" },
    "daily_addness_comment": { "cron": "30 8 * * *", "task": "期限超過タスクにコメント" },
    "daily_ad_data": { "cron": "0 9 * * *", "task": "広告データ収集" },
    "daily_comment_review": { "cron": "0 12 * * *", "task": "コメント返信確認" },
    "daily_report": { "cron": "0 17 * * *", "task": "日次レポート作成" },
    "daily_reminder": { "cron": "30 17 * * *", "task": "翌日期限タスクリマインド" },

    // 週次タスク
    "weekly_progress": { "cron": "0 9 * * 1", "task": "週次進捗レポート" },
    "weekly_ad_analysis": { "cron": "0 10 * * 3", "task": "広告パフォーマンス分析" },
    "weekly_preview": { "cron": "0 15 * * 5", "task": "来週タスクプレビュー" }
  }
}
```

---

## Step 8: Tailscale 接続（任意）

AI秘書Mac Miniとの通信用。

```bash
brew install tailscale
# Tailscaleアカウントでログイン
# MagicDNS で hinata-mac-mini 等のホスト名を設定
```

---

## セットアップ完了チェックリスト

- [ ] Node.js 22+ インストール済み
- [ ] OpenClaw インストール＋daemon登録済み
- [ ] Slack連携設定済み（日向がSlackで応答する）
- [ ] Claude Code Skillインストール済み
- [ ] 環境変数設定済み（ANTHROPIC_API_KEY等）
- [ ] AI秘書側にSLACK_AI_TEAM_WEBHOOK_URL設定済み
- [ ] AI秘書→Slack #ai-team テスト送信成功
- [ ] 日向→Slack応答テスト成功
- [ ] スケジュール設定済み（日次/週次）
- [ ] Tailscale接続（任意）

---

## トラブルシューティング

| 問題 | 対処 |
|------|------|
| `openclaw` コマンドが見つからない | `source ~/.zprofile` でPATHを再読み込み |
| daemonが起動しない | `launchctl list | grep openclaw` で確認。`openclaw onboard --install-daemon` を再実行 |
| Slack応答がない | `openclaw logs` でエラー確認。Slack App のトークン期限切れの可能性 |
| Claude APIエラー | `ANTHROPIC_API_KEY` が正しいか確認。Maxプランの利用上限確認 |
| セキュリティ警告 | OpenClaw 最新版を使用（CVE-2026-25253対応済みか確認） |

---

## 参考リンク

- [OpenClaw公式ドキュメント](https://docs.openclaw.ai/)
- [OpenClaw Mac Mini セットアップガイド](https://aiopenclaw.org/blog/openclaw-mac-mini-complete-guide)
- [Claude Code Skill](https://github.com/Enderfga/openclaw-claude-code-skill)
- [ClawHub（スキル一覧）](https://clawhub.com)
