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

## ファイル・フォルダ追加ルール

**新しいファイルやフォルダを作る前に、以下を必ず確認する。ノイズは積み重なるほど悪影響が大きい。**

1. **既存ファイルへの追記で済まないか？** → 済むなら新規作成しない
2. **一時的なものではないか？** → テスト・検証・草稿は作業後に削除する。残さない
3. **重複していないか？** → 同じ内容が別の場所に既にあるなら作らない
4. **置き場所は正しいか？** → 業務知識は `Skills/`、インフラは `Master/knowledge/`、プロジェクト進行は `Project/`
5. **名前は明確か？** → `Untitled`、`テスト`、`tmp` のような曖昧な名前で残さない

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
├── hinata_agent.py      # メインループ（タスクキュー監視 + サイクル実行 + アクション記録）
├── claude_executor.py   # Claude Code CLI 呼び出し + プロンプト構築（MCP ツール指示）
├── learning.py          # 学習エンジン（記録・フィードバック検出・記憶統合・コンテキスト構築）
├── slack_comm.py        # Slack送信専用（Webhook送信のみ。受信はOrchestratorが担当）
├── addness_browser.py   # （レガシー）Playwright版。現在はClaude in Chrome MCPを使用
├── self_restart.sh      # 自己再起動（git pull → launchctl reload）
├── config.json          # 設定（ゴールURL・サイクル間隔・稼働時間）
├── state.json           # 実行状態（サイクル数・最終アクション・paused）
├── hinata_tasks.json    # タスクキュー（Orchestratorが書き込み、日向が読む）
└── logs/                # ログ出力先

Master/learning/
├── action_log.json      # アクション履歴（親プロセスが自動記録、最大50件）
├── feedback_log.json    # フィードバック履歴（甲原の修正/承認を自動検出、最大50件）
├── hinata_memory.md     # 日向の成長する記憶（フィードバックから学んだパターン）
└── insights.md          # 業務の知見（Claude Codeが追記）
```

### 学習ループ

```
甲原「Xをして」→ 日向が実行 → 結果を action_log に自動記録
                                         ↓
甲原「違う、Yだよ」→ フィードバック自動検出 → feedback_log に記録
                                         ↓
                        次回プロンプトに反映 → 日向が同じ失敗を繰り返さない
                                         ↓
                    週次で記憶を統合 → hinata_memory.md に蓄積 → 長期記憶化
```

- **アクション記録**: hinata_agent.py（親プロセス）が確実に書く。Claude Code に任せない
- **フィードバック検出**: 指示のテキストから感情を自動判定（positive/negative）
- **コンテキスト注入**: learning.py が直近アクション+フィードバック+記憶+知見をプロンプトに注入

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
| `MCP ツール接続失敗` | Chrome or Claude in Chrome 拡張が停止 | Chrome を再起動（`com.hinata.chrome` LaunchAgent） |
| `tabs_context_mcp エラー` | タブグループが存在しない | `createIfEmpty: true` で新規作成 |
| `Claude Code タイムアウト` | プロンプトが重すぎる or ネットワーク遅延 | `claude_executor.py` の `timeout_seconds` を調整 |
| `Addnessログイン失敗` | セッション切れ | Chrome で再ログインが必要（Google認証情報は `credentials/hinata_google.json`） |
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
- ブラウザは Chrome + Claude in Chrome MCP で操作（Playwright は不要）
- Chrome 自動起動: `com.hinata.chrome` LaunchAgent（`--no-sandbox --disable-gpu --remote-debugging-port=9223`）

### launchd 設定（Mac Mini 全サービス）

| サービス | ラベル | plist |
|----------|--------|-------|
| 日向エージェント | `com.hinata.agent` | `~/Library/LaunchAgents/com.hinata.agent.plist` |
| Orchestrator | `com.addness.agent-orchestrator` | `~/Library/LaunchAgents/com.addness.agent-orchestrator.plist` |
| ローカルエージェント | `com.linebot.localagent` | `~/Library/LaunchAgents/com.linebot.localagent.plist` |
| Chrome（日向用） | `com.hinata.chrome` | `~/Library/LaunchAgents/com.hinata.chrome.plist` |

全サービス共通: RunAtLoad=true, KeepAlive（異常終了時のみ自動再起動）
