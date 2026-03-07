# Claude Code ルール（このプロジェクト専用）

最終更新: 2026-03-07

## ルールファイル同期ルール

**CLAUDE.md と AGENTS.md は同じ行動原則を共有する。片方を変更したら、もう片方も必ず同じセッション内で同期する。**

- 行動原則・プロジェクト構成・ドキュメント更新ルール・コミットルール → 両方に反映
- Claude固有（Chrome MCP、日向のClaude Code実行パラメータ等）→ CLAUDE.md のみ
- Codex固有（config.toml設定等）→ AGENTS.md のみ
- 迷ったら両方に書く。片方だけに書いて忘れるより、重複の方がマシ

## 共有資産の正本ルール

**プロジェクト固有の知識・スキル・運用ルールの正本は、必ず `cursor/` 配下に置く。ホームディレクトリ側を正本にしない。**

- 共通知識・再利用スキルの正本は `Skills/` に置く
- Codex 実行都合で `~/.codex/skills/` が必要な場合も、`Skills/` へのシンボリックリンクまたは薄い同期だけを許可する
- `~/.codex/skills/` 側で直接編集して内容を育てることは禁止。変更は必ず `cursor/Skills/` で行う
- Claude Code でも Codex でも、プロジェクト作業時は `AGENTS.md` / `CLAUDE.md` と `Skills/` を優先して読む
- 共有資産を更新したら、必要なリンク・同期状態まで同じセッションで整える

---

## ツール使い分けガイドライン

**原則: 上流 = Codex（GPT 5.4）、下流 = Claude Code（Opus）**

基盤（`cursor/` のファイル・フォルダ）は共有。成果物はファイルに書き出し、どちらからでも引き継げるようにする。

### Claude Code を使う場面（このファイルを読むツール）

| 業務タイプ | 具体例 |
|-----------|--------|
| **ブラウザ操作** | Looker Studio、Addness、広告管理画面（Chrome MCP） |
| **コード実装・修正** | Python/JS の実装、バグ修正、リファクタリング |
| **システム保守** | 秘書・Orchestrator の設定変更、デプロイ |
| **ファイル操作** | 大量ファイルの一括編集、データ変換、git操作 |
| **定常業務の実行** | 日報、KPI取得、メール確認、経営会議資料作成 |

### Codex CLI を使う場面

| 業務タイプ | 具体例 |
|-----------|--------|
| **戦略・意思決定** | 事業方針の壁打ち、施策の優先順位付け、P&L分析 |
| **リサーチ・分析** | 競合分析、市場調査、広告リサーチ（B5）、DPro分析 |
| **企画・設計** | 広告CR企画（C1）、LP設計、導線設計、メールシナリオ設計 |
| **レビュー・判断** | コードレビュー、ドキュメントレビュー、KPI異常の解釈 |

### `ai` コマンド（シームレス切り替え）

ターミナルで `ai` コマンドを使うと、タスク内容に応じて自動で適切なツールが起動する。

```bash
ai "広告CRの競合分析して"     # → Codex（上流: 戦略・分析）
ai "このバグ直して"           # → Claude Code（下流: 実装）
ai codex "企画を練りたい"     # → 明示的にCodex
ai claude "デプロイして"      # → 明示的にClaude Code
ai switch                    # → ツール間切り替え（自動引き継ぎ）
ai                           # → デフォルトでCodex起動
```

### セッション終了時の引き継ぎルール（必須）

**セッションを終了する前に、必ず `~/.ai_handoff.md` に引き継ぎメモを書き出す。これを省略しない。**

引き継ぎメモには以下を必ず含める:

```markdown
# 引き継ぎメモ
## 目的
何のためにこの作業をしていたか

## 完了したこと
- 具体的に何を終わらせたか

## 未完了
- 残っているタスク

## 判断とその理由（最重要）
- なぜその選択をしたか。結論だけでなく背景を書く

## 変更したファイル
- パスと変更内容の概要

## 次の担当へ
- 次にやるべきこと、注意点、前提条件
```

**なぜこれが必須か:** 次のツール（Codex/Claude Code）は別プロセスで起動する。セッション内の会話履歴は引き継がれない。このファイルだけが「前の担当が何を考え、何をしたか」を伝える唯一の手段。人間の引き継ぎ書と同じ。

### Skills/ の置き方

- 人が読む知識は `Skills/<カテゴリ>/<name>.md`
- Codex / Claude の両方で再利用する構造化 skill は `Skills/<カテゴリ>/<skill-name>/SKILL.md` を正本にする
- 構造化 skill の補足は `references/`、UI メタデータは `agents/openai.yaml` に置く
- 実行環境都合で `~/.codex/skills/<skill-name>` が必要なら、`Skills/<カテゴリ>/<skill-name>` へのリンクとして扱う

## 情報密度の原則

**無駄な情報を入れない。次の判断・実行に効かないものは残さない。**

- 同じ内容を複数箇所に重複して持たない。正本に集約し、他はリンクか参照にする
- 一時ファイル、検証ファイル、退避コピーは、役目が終わったら同じセッションで削除する
- 長い説明を足す前に、既存ファイルの整理・圧縮・統合で済まないか先に確認する
- 「念のため」で情報を残さない。本当に再利用するものだけ残す

---

## ユーザー設定

- コミットメッセージは日本語OK
- 非エンジニアのユーザー → 専門用語を避ける
- 変更報告はまず自然文で「何が良くなったか」「何が変わったか」を先に伝える
- ファイル名・英語識別子は必要なときだけ出す。列挙より先に日本語で意味を説明する
- 一目で分かることを優先する。詳細は補足として後ろに回す
- 報告の基本順は「結論 → 何が良くなったか → 必要なら補足」。いきなり実装詳細から入らない
- 「修正しました」「変更しました」で始めず、「今はこうなっています」「これでこうなります」と結果から言う
- ファイル名を複数並べるのは避ける。必要なら最後に「詳細が必要なら見る場所」として少数だけ添える
- 選択肢を出すときは「自分はこう思う」を必ず添える
- サービスは正式名称: Lステップ / UTAGE / 講義保管庫 / スキルプラス
- 事業KPIは外部に非開示

---

## ドキュメント更新ルール

**コードや設定を変更・追加したら、必ず関連ドキュメントも同じセッション内で最新化すること。**

### 対象ドキュメント

| ファイル | 更新トリガー |
|---------|------------|
| `Project/4_AI基盤/AI秘書作成.md` | `System/line_bot/app.py` または `System/line_bot_local/local_agent.py` を変更したとき |
| `Project/2_CS/質問自動回答プロジェクト.md` | Q&A関連（`qa_handler.py`, `qa_monitor.py`, `qa_search.py`）を変更したとき |
| `Project/3_業務自動化/メール自動管理.md` | メール関連（`mail_manager.py`, `mail_inbox_*.py`）を変更したとき |
| `Project/3_業務自動化/数値管理自動化.md` | 数値管理関連（`csv_sheet_sync.py`, `sheets_manager.py`, `sheets_sync.py`）を変更したとき |
| `Project/4_AI基盤/CDP.md` | CDP関連（`cdp_sync.py`）を変更したとき |
| `Master/knowledge/定常業務.md` | 日報入力手順・Looker Studio CSV取得手順・完了報告フォーマットを変更したとき |

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

## ルール設計の原則

**「意識しろ」で終わらせない。手順・禁止・構造で仕組み化する。**

### ルールの書き方

| NG | OK |
|---|---|
| 「見る人のことを考えて」 | 「screenshotをそのまま送ることは禁止。必ずzoomで切り取る」 |
| 「丁寧に確認して」 | 「実行前にdry-runの結果を表示する」 |
| 「わかりやすい名前で」 | 「命名規則: [カテゴリ]_[動詞]_[対象].py」 |

「意識」「考えて」「気をつけて」が含まれていたら、手順か禁止に書き直す。

### ルールを追加するとき

- 既存ルールと統合できないか先に確認する。増やす前にまず統合
- 仕組みを強めた結果、他が弱くなるなら全体最適を優先する

---

## プロジェクト構成

```
cursor/
├── Project/              # プロジェクトドキュメント（機能領域別に分類）
│   ├── 1_集客/           # 広告・集客系プロジェクト
│   ├── 2_CS/             # CS・コンテンツ系プロジェクト
│   ├── 3_業務自動化/      # 業務効率化プロジェクト
│   └── 4_AI基盤/         # AIエージェント・基盤プロジェクト
├── Master/               # 知識ベース（people/, addness/, self_clone/, learning/, sheets/, knowledge/）
├── System/               # 実装ファイル
│   ├── credentials/      # OAuth トークン・クライアントシークレット（.gitignore）
│   ├── config/           # アプリ固有設定 JSON（.gitignore 対象あり）
│   ├── data/             # ランタイムデータ・キャッシュ（.gitignore）
│   ├── line_bot/         # Render (Flask) サーバー（git サブモジュール）
│   ├── line_bot_local/   # PC常駐エージェント
│   ├── addness_mcp_server/ # Addness MCP サーバー（git サブモジュール）
│   ├── quick_translator/  # Chrome拡張（テキスト選択→自動翻訳ポップアップ）
│   ├── clip_translator/   # macOSメニューバーアプリ（Cmd+C→翻訳通知）
│   └── mac_mini/         # Mac Mini Orchestrator（スケジューラ・ツール群）
│       └── monitoring/   # 外部死活監視（MacBook → Mac Mini）
└── Skills/               # ナレッジ・スキル定義（プロジェクト共通の正本）
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
├── claude_executor.py   # Claude Code CLI 呼び出し + プロンプト構築（--chrome リトライ付き）
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
- **データ同期**: `git_pull_sync.sh` が fetch/reset 前に学習データを自動 commit & push（5分ごと）

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
| `MCP ツール接続失敗` | Chrome or Claude in Chrome 拡張が停止 | Chrome を再起動（`com.hinata.chrome` LaunchAgent）。`--chrome` 失敗時は自動で `--chrome` なしにフォールバック |
| `tabs_context_mcp エラー` | タブグループが存在しない | `createIfEmpty: true` で新規作成 |
| `Claude Code 空出力` | Chrome MCP 接続不安定 or 認証エラー | stderr ログで原因確認。`_run_claude_with_retry` が自動リトライ済み |
| `Claude Code タイムアウト` | プロンプトが重すぎる or ネットワーク遅延 | `claude_executor.py` の `timeout_seconds` を調整 |
| `Addnessログイン失敗` | セッション切れ | Chrome で再ログインが必要（Google認証情報は `credentials/hinata_google.json`） |
| `コマンド分類ミス` | `_classify_slack_command` のキーワードが不適切 | `scheduler.py` の `_classify_slack_command` を修正（Orchestrator側） |
| `タスクが届かない` | Orchestratorの `slack_dispatch` が停止 | config.yaml で `slack_dispatch.enabled: true` を確認 |

**Claude Code CLI 実行パラメータ（claude_executor.py）:**
- モデル: `claude-sonnet-4-6`（`--model` で明示）
- 最大ターン: 15（`--max-turns` でAPI暴走防止）
- Chrome MCP: `--chrome` で接続（失敗時は `--chrome` なしで自動リトライ）
- 認証: `CLAUDE_CONFIG_DIR=~/.claude-hinata`（OAuth。`ANTHROPIC_API_KEY` は除外）
- 自己修復: `--chrome` なし（コード修正のみなのでブラウザ不要）

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

---

## ブラウザ操作ルール（Claude in Chrome MCP）

**DOMベース操作を最優先。画像ベース（座標クリック）は最後の手段。**

### 操作の優先順位

1. **DOMベース（速い・正確）** — ボタン、リンク、フォーム入力など通常のWeb要素
2. **画像ベース（遅い・不正確）** — Canvas描画、地図、PDFビューアなどDOM要素がない場合のみ

### DOMベース操作の手順

```
① find("ログインボタン", tabId) → ref_3 が返る
② computer(action: "left_click", ref: "ref_3", tabId)  ← 座標不要
```

- **クリック**: `find` でref取得 → `computer(action: "left_click", ref: "ref_xx")` で直接クリック
- **入力**: `read_page(filter: "interactive")` でref取得 → `form_input(ref: "ref_xx", value: "...")` で直接入力
- **ページ内容の確認**: `read_page` または `get_page_text` を使う

### 画像ベースを使ってよい場面（これ以外では使わない）

- Canvas/地図/グラフ上の特定ポイントをクリックする必要がある場合
- スクリーンショットを撮ること自体が目的の場合（`screenshot` / `zoom`）
- DOMベースで要素が見つからなかった場合のフォールバック

### スクリーンショット

**人に送る・貼り付けるスクショは、必ず `zoom` で切り取ってから使う。`screenshot` の結果をそのまま送ることは禁止。**

手順:
1. `computer(action: "screenshot", tabId)` で全体を撮る（座標把握用。これ自体は送らない）
2. 伝えたい情報の座標範囲を特定する（サイドバー・ナビ・余白は含めない）
3. `computer(action: "zoom", region: [x0, y0, x1, y1], tabId)` で切り取る
4. `zoom` の結果を送る or `upload_image(imageId, tabId, coordinate: [x, y])` で貼り付ける

※ 自分の操作確認用に `screenshot` を見るのはOK。禁止は「そのまま人に送る」こと。

### 禁止事項

- `computer(action: "screenshot")` → 画像を見て座標推定 → `computer(action: "left_click", coordinate: [x, y])` のパターンを通常のWeb操作で使わない
- `find` や `read_page` を試さずにいきなり `screenshot` を撮らない
