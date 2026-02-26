# Claude Code ルール（このプロジェクト専用）

## ドキュメント更新ルール

**コードや設定を変更・追加したら、必ず関連ドキュメントも同じセッション内で最新化すること。**

### 対象ドキュメント

| ファイル | 更新トリガー |
|---------|------------|
| `Project/AI秘書作成.md` | `System/line_bot/app.py` または `System/line_bot_local/local_agent.py` を変更したとき |
| `Project/質問自動回答プロジェクト.md` | Q&A関連（`qa_handler.py`, `qa_monitor.py`, `qa_search.py`）を変更したとき |
| `Project/メール自動管理.md` | メール関連（`mail_manager.py`, `mail_inbox_*.py`）を変更したとき |
| `Project/数値管理自動化.md` | 数値管理関連（`csv_sheet_sync.py`, `sheets_manager.py`, `sheets_sync.py`）を変更したとき |
| `Project/定常業務.md` | 日報入力手順・Looker Studio CSV取得手順・完了報告フォーマットを変更したとき |

### 更新の原則

- **古い情報は残さない**: 変更箇所は上書き・削除して最新状態にする
- **完了済みは [x]**: 実装済み機能はチェックボックスを必ず [x] にする
- **最終更新日を更新**: ファイル冒頭の「最終更新」日付を変更日に更新する
- **ステータスを正確に**: 完了・開発中・廃止を正確に反映する

### 更新する内容の例

- 新機能を追加 → 機能一覧・コマンドリファレンスに追記
- バグ修正 → 注意事項・既知の制限を更新
- ファイルを追加・削除 → ファイル構成表を更新
- 環境変数を追加 → 環境変数一覧を更新
- アーキテクチャ変更 → 図・説明を更新

---

## プロジェクト構成

```
cursor/
├── Project/              # プロジェクトドキュメント（常に最新を維持）
├── Master/               # 知識ベース（people/, addness/, self_clone/, learning/, sheets/）
├── System/               # 実装ファイル
│   ├── credentials/      # OAuth トークン・クライアントシークレット（.gitignore）
│   ├── config/           # アプリ固有設定 JSON（.gitignore 対象あり）
│   ├── data/             # ランタイムデータ・キャッシュ（.gitignore）
│   ├── line_bot/         # Render (Flask) サーバー（git サブモジュール）
│   ├── line_bot_local/   # PC常駐エージェント
│   ├── addness_mcp_server/ # Addness MCP サーバー（git サブモジュール）
│   └── mac_mini/         # Mac Mini Orchestrator（スケジューラ・ツール群）
│       └── monitoring/   # 外部死活監視（MacBook → Mac Mini）
└── Skills/               # ナレッジ・スキル定義
```

### System/ 内のパス規約

| ディレクトリ | 内容 | Git 管理 |
|---|---|---|
| `credentials/` | `client_secret*.json`, `token*.json` | **除外** |
| `config/` | `addness.json`, `sns_analyzer.json`, `ai_news.json` | **一部除外** |
| `data/` | `kpi_summary.json`, `addness_session.json` | **除外** |

Python スクリプトからのパス解決は `Path(__file__).resolve().parent` を起点にする。

## コミットルール

- `System/line_bot/` への変更は `cd System/line_bot && git add . && git commit` でサブモジュールに個別コミット
- その後 `git push origin main` で Render に自動デプロイ
- メインリポジトリ側も変更があれば別途コミット
- コミット後は `post-commit` フックで自動 push → Mac Mini が5分以内に git pull で同期

## 技術選定の思考フロー

**思考の起点は常に「中から外」。手元の資産から出発し、外に探しに行くのは最後。**

```
1. 今何を持っている？（APIキー・認証情報・既存サービス・ライブラリ）
2. 持っているもので実現できないか？
3. できる → それを使う。終わり。
4. できない → 初めて外部の選択肢を探す
```

「〇〇といえば△△」という一般知識から入らない。必ず手元の棚卸しから始める。

### 判断軸（優先順位順）

1. **既存インフラの活用** — 新しいサービス・ツールの導入より、すでに使っているもので解決する
2. **スケーラビリティ** — マシンやメンバーが増えても設定変更が最小限で済むか
3. **シンプルさ** — 可動部品（依存サービス・認証・ネットワーク要件）が少ないほど良い
4. **可逆性** — 失敗しても元に戻せるか。段階的に移行できるか

---

## 日向エージェント（Mac Mini 常駐 AI）

### 概要

日向（ひなた）は Mac Mini で常時稼働する自律型AIエージェント。
「自分で考えて動く」が役割。Addnessのゴール推進、調査、コード修正を担当。

### 役割分担（B. 役割ベース）

| 担当 | 役割 | Slack監視 |
|------|------|-----------|
| **AI秘書** | 人とのやり取り（LINE・Slack監視・返信・Q&A） | 秘書が #ai-team を監視 |
| **日向** | 自分で考えて動く（Addness・調査・コード修正） | 秘書から指示を受ける側 |
| **Orchestrator** | 決まった仕事を決まった時間に（同期・監視・レポート） | `slack_dispatch` で秘書→日向の橋渡し |

### 指示フロー

```
甲原 → Slack #ai-team に書き込み
  → Orchestrator の slack_dispatch（15秒ごと）が監視
    → stop/status → 秘書が直接 Slack に応答
    → instruction → hinata_tasks.json にタスク追加
      → 日向が15秒ごとにタスクキューを確認
      → Claude Code で実行 → Slack に結果報告
        → 秘書（slack_hinata_auto_reply）が報告に返答
```

### コード構成

```
System/hinata/
├── hinata_agent.py      # メインループ（ブラウザ維持 + タスクキュー監視 + サイクル実行）
├── claude_executor.py   # Claude Code CLI 呼び出し + プロンプト構築
├── slack_comm.py        # Slack送信専用（Webhook送信のみ。受信はOrchestratorが担当）
├── addness_browser.py   # Playwright永続コンテキスト + CDP + Addnessログイン
├── addness_cli.py       # CLI ユーティリティ（手動ログイン等）
├── self_restart.sh      # 自己再起動（git pull → launchctl reload）
├── config.json          # 設定（ゴールURL・サイクル間隔・稼働時間）
├── state.json           # 実行状態（サイクル数・最終アクション・paused）
├── hinata_tasks.json    # タスクキュー（Orchestratorが書き込み、日向が読む）
└── logs/                # ログ出力先
```

### タスクキュー（hinata_tasks.json）

Orchestrator の `slack_dispatch` が書き込み、日向が読む。同一マシン上のファイルベースキュー。

```json
[
  {
    "id": "abc12345",
    "instruction": "甲原のメッセージ",
    "command_type": "instruction",
    "source": "slack",
    "slack_ts": "1234567890.123456",
    "status": "pending",
    "created_at": "2026-02-26T10:30:00"
  }
]
```

- status: `pending` → `processing` → `completed` / `failed`
- command_type: `instruction` / `stop` / `resume`
- 完了から1時間で自動クリーンアップ

### 自己修復ガイド（Claude Code がバグ修正するとき用）

**よくあるエラーと修正方法:**

| エラー | 原因 | 修正方法 |
|--------|------|----------|
| `Slack送信失敗` | Webhook URL 未設定 or 期限切れ | `slack_comm.py` の `_SLACK_WEBHOOK_URL` を確認 |
| `CDP接続失敗` | ブラウザが再起動された | `hinata_agent.py` が自動復旧するので待つ |
| `context.close() でブラウザ終了` | `browser.close()` と間違えた | CDP接続は `browser.close()` で切断。`context.close()` は絶対に使わない |
| `Claude Code タイムアウト` | プロンプトが重すぎる or ネットワーク遅延 | `claude_executor.py` の `timeout_seconds` を調整 |
| `Addnessログイン失敗` | セッション切れ | ブラウザプロファイルにセッションが残っていれば自動復旧。なければ手動ログイン必要 |
| `コマンド分類ミス` | `_classify_slack_command` のキーワードが不適切 | `scheduler.py` の `_classify_slack_command` を修正（Orchestrator側） |
| `タスクが届かない` | Orchestratorの `slack_dispatch` が停止 | config.yaml で `slack_dispatch.enabled: true` を確認 |

**修正後の再起動手順:**

1. コード修正 → `git add` → `git commit` → `git push`
2. `bash System/hinata/self_restart.sh "修正内容の説明"`
3. Mac Mini 上で `launchctl unload` → `load` が自動実行される

**重要な注意事項:**
- `~/agents/System/hinata` は `~/agents/_repo/System/hinata` へのシンボリックリンク
- git push すれば Mac Mini の `git_pull_sync`（5分ごと）で自動反映
- 即時反映が必要なら `self_restart.sh` を使う
- ブラウザは `launch_persistent_context` で永続プロファイルを使用（`System/data/hinata_chrome_profile/`）

### launchd 設定

- ラベル: `com.hinata.agent`
- plist: `~/Library/LaunchAgents/com.hinata.agent.plist`
- RunAtLoad=true, KeepAlive（異常終了時のみ自動再起動）, ThrottleInterval=60秒
