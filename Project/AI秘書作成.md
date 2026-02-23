# AI秘書作成

## 基本情報

| 項目 | 内容 |
|------|------|
| プロジェクト名 | AI秘書作成 |
| 開始日 | 2026年2月18日 |
| 最終更新 | 2026年2月23日（学習ループ修正: group_insights返信注入・Q&Aナレッジ蓄積・承認フィードバック学習） |
| ステータス | 🚀 継続開発中 |

---

## アーキテクチャ

```
┌─────────────┐    Webhook     ┌──────────────────────────────┐
│    LINE     │ ─────────────> │       Render (Flask)          │
│  各グループ  │ <──────────── │  - メンション/引用返信検知       │
│  テストグループ│   Push API   │  - タスクキュー管理              │
└─────────────┘               │  - 会話文脈バッファリング        │
                               │  - sent_group_messages 追跡    │
┌─────────────┐   Webhook      │  - Chatwork Webhook受信        │
│  Chatwork   │ ─────────────> │    /chatwork/callback          │
│  各ルーム    │ <──────────── │  - Chatwork API送信             │
└─────────────┘  Chatwork API  └──────────────────────────────┘
                                              │
                                   ポーリング │ (10秒間隔)
                                              ▼
                               ┌──────────────────────────────┐
                               │  Mac Mini 常駐エージェント      │
                               │  ~/agents/line_bot_local/      │
                               │  local_agent.py                │
                               │  - Claude Sonnet で返信案生成  │
                               │  - フィードバック学習          │
                               │  - people-profiles.json参照   │
                               │  - スプレッドシート文脈参照     │
                               │  - Addness KPI自動参照         │
                               │    (kpi_summary.json優先      │
                               │     → Sheets APIフォールバック)  │
                               │    ※外部パートナーには非開示    │
                               └──────────────────────────────┘
                                              │
                               launchd常駐    │ データ参照
                                              ▼
                               ┌──────────────────────────────┐
                               │  Master/ (知識ベース)          │
                               │  - people-profiles.json (54名) │
                               │  - people-identities.json     │
                               │    (chatwork_account_id対応)   │
                               │  - IDENTITY.md (言語スタイル)   │
                               │  - SELF_PROFILE.md (自己像)    │
                               │  - reply_feedback.json (学習)  │
                               └──────────────────────────────┘
```

---

## 知識ベース運用思想

> 詳細ルール: `.cursor/rules/ai-secretary-knowledge.mdc`

知識ベースは「今日の真実」を映す鏡。歴史の記録ではない。

### 定常サイクル（毎日）

```
朝: 全アクションは最新の知識ベースを参照して回答
  ↓
夜: ログを確認 → 古い情報を削除 → 最新に書き換え → 本質だけ残す
  ↓
翌朝: 更新された知識で全アクションが動く
```

**対象ファイル**: `people-profiles.json` / `USER.md` / `SELF_PROFILE.md` / `IDENTITY.md` / `reply_feedback.json`

### 非定常（フィードバック駆動）

抜けている情報やズレている認識を検知したら即修正。

| 検知 | 対処 |
|------|------|
| 返信がズレている | `fb` / `2` コマンドでスタイルノート・修正例を更新 |
| 人物情報が古い | `メモ` コマンドでプロファイル更新 |
| USER.md/SELF_PROFILE.mdがズレている | ユーザー指摘で即書き換え |

---

## 実装済み機能一覧

### Phase 1: メンション検知・返信案生成（完了）
1. **メンション検知**: グループ内で特定の名前を検知（TARGET_NAMES）
2. **AI返信案生成**: Claude Sonnet 4.6 で返信文を自動生成
3. **承認ワークフロー**: 秘書グループで `1`（承認）/ `2 [修正]`（編集）/ `❌`（キャンセル）
4. **即時通知**: メンション検知後すぐに「⏳ 生成中」を通知、生成完了後に返信案を更新

### Phase 2: 自然言語タスク実行（完了）
5. **Googleカレンダー連携**: 「明日14時に会議入れて」で予定追加
6. **PC委譲タスク**: 複雑タスクをCursorに転送（日報入力はLINE非対応・Cursor直接実行）

### Phase 3: Mac Mini 常駐エージェント（完了）
7. **launchd常駐**: Mac Mini `~/agents/line_bot_local/local_agent.py` をlaunchdで自動起動
8. **Mac Mini TCC回避**: macOS TCC制限のため `~/agents/` を作業ディレクトリとして使用
9. **デプロイ完了通知**: Render起動時にLINEへ通知（gunicorn multi-worker対応・重複防止）

### Phase 4: 人物プロファイル × フィードバック学習（完了）
10. **per-personプロファイル**: 54名の `comm_profile`（返信スタイル・挨拶・文脈）を自動生成・参照
11. **フィードバックループ**:
    - `fb [内容]` → スタイルノート（全返信に適用）
    - `2 [修正]` → 修正例として自動学習（AI案と異なる場合のみ）
    - `1`（承認） → 成功例として自動学習（AI案が正解だったパターンを蓄積）
    - 学習データは `reply_feedback.json` に蓄積、次回返信案のプロンプトに注入（修正例 + 成功例の両面から学習）
12. **group_insights → 返信プロンプト注入**: 週次プロファイル学習（`weekly_profile_learning`）が書き込んだ `group_insights`（会話スタイル・最近の関心・協業パターン・性格特性）を返信案生成のプロンプトに自動注入。相手の最新の行動パターンを踏まえた返信を生成
13. **メモコマンド**: `メモ [人名]: [内容]` → その人のプロファイルに文脈メモを追記
14. **IDENTITY.md**: 甲原海人の言語スタイル定義（口癖・トーン・関係性別ルール）
15. **SELF_PROFILE.md**: 甲原海人のコアプロファイル（価値観・判断軸・哲学）記入済み

### Phase 5: 高度な返信文脈認識（完了）
15. **引用返信（リプライ）検知**: ボットが送信したメッセージへのLINE引用返信を自動検知し、新しい返信案を生成
16. **会話文脈取り込み**: メンション直前の発言（最大10件）をバッファリングし、Claude プロンプトに「直前の文脈」として注入
17. **重複タスク防止**: 同一 `message_id` の `generate_reply_suggestion` タスクは1件のみキューイング

### Phase 6: Chatwork連携・スプレッドシート文脈参照（完了）
18. **Chatwork Webhook受信**: `/chatwork/callback` で `mention_to_me` イベントを受信、HMAC-SHA256署名検証
19. **Chatwork返信送信**: 承認後 `send_chatwork_message()` でChatworkルームに返信（`[rp]` タグ付き）
20. **プラットフォーム分岐**: `pending_messages` に `platform` フィールドを追加。承認時にLINE/Chatworkを自動判別して送信先を切り替え
21. **`[CW]`/`[LINE]` バッジ**: 秘書グループの通知・未返信一覧にプラットフォームバッジを表示
22. **Chatwork account_id逆引き**: `people-identities.json` の `chatwork_account_id` フィールドでプロファイル検索可能
23. **スプレッドシート文脈参照**: プロファイルの `related_sheets` にシートIDを登録すると、返信案生成時に自動でデータを取得してプロンプトに注入。数字に基づいた回答が可能
24. **Addness KPI自動参照**: アドネス関連の会話を自動検知し、KPIキャッシュ→CSV再構築→Sheets APIの4段階フォールバックで自動注入。**目標KPI対比**（`config/addness.json`の`kpi_targets`）・**異常値検知**（ROAS<0%等）・**stale警告**（24h超で警告・7日超で拒否）付き。外部パートナー・未登録者にはKPI非開示
25. **KPI日次パイプライン**: Looker StudioからCSVダウンロード→元データシート→日別/月別自動投入。毎日12:00にOrchestratorが完了チェック→投入成功時はKPIキャッシュも再生成→未完了ならLINEリマインド。毎晩22:00にもキャッシュ再生成（1日3回更新）
26. **遠隔エージェント再起動**: LINEから「再起動」と送信するとMac Mini上の`local_agent.py`が`launchctl unload/load`で自動再起動。コード更新後の反映やエラー回復に使用
27. **自動再起動改善**: `git_pull_sync.sh`が`line_bot_local/`配下の`.py`ファイル変更を検知すると自動で`local_agent`を再起動し、LINEに通知（変更ファイル名・コミットハッシュ・時刻を含む）
28. **plistパス自動修正**: `git_pull_sync.sh`が毎回実行時にlaunchctl plistのパス整合性をチェック。Library版（`~/Library/LineBot/`）など古いパスを参照していた場合、正しいデプロイ先（`~/agents/line_bot_local/`）に自動修正＆再起動。config.jsonも旧パスから自動マイグレーション

---

## コマンドリファレンス（秘書グループ内）

### 返信承認

| コマンド | 動作 |
|----------|------|
| `1` | 最新の返信案を承認して送信 |
| `2 [送りたい内容]` | 修正した内容で送信（AI案と異なれば自動学習） |
| `❌ {ID}` | キャンセル |
| `リスト` / `一覧` | 未返信メンション一覧 |

> ※ 返信案メッセージに**引用返信**して `1` / `2 [内容]` を送ると、対象が自動特定される

### フィードバック・学習

| コマンド | 動作 | 適用範囲 |
|----------|------|---------|
| `fb [内容]` | スタイルノートとして保存 | **全員への返信**に適用 |
| `2 [修正]` で承認 | 修正例として保存（AI案と異なる場合） | その人優先・他も参照（最大5件） |
| `1` で承認 | 成功例として保存（AI案が正解だったパターン） | その人優先・他も参照（最大3件） |
| `メモ [人名]: [内容]` | プロファイルに文脈メモを追加 | その人への返信に適用 |

### Q&A操作

| コマンド | 動作 |
|----------|------|
| `✅ Qxxxxxx` | AI回答案を承認して送信 |
| `📝 Qxxxxxx [修正内容]` | 修正して送信 |
| `❌ Qxxxxxx` | キャンセル |
| `Q&A` / `質問` | 保留中Q&A一覧 |

### 自然言語指示

| 指示例 | 動作 |
|--------|------|
| 「明日14時に会議入れて」 | Googleカレンダーに予定追加 |
| 「今日の予定を教えて」 | カレンダー予定を表示 |
| 「日報入れて」 | 「Cursorで実行してください」と案内を返す（Looker Studio・b-dashのブラウザ操作が必要なためLINEから実行不可） |
| 「広告数値の評価をして」「ROAS教えて」 | KPIデータ自動取得→Claudeが分析・トレンド評価・改善提案を返答（kpi_query） |
| 「次何？」「次にやることは？」 | Addness+メール+KPIサマリをClaudeが分析→優先行動リスト返答（context_query） |
| 「LP作成: 商品名 ターゲット」 | LP構成案+キャッチコピー3案+CTA自動生成（generate_lp_draft） |
| 「スクリプト作成: 商品名 [タイプ]」 | 広告動画台本自動生成・フック+問題提起+CTA構成（generate_video_script） |
| 「バナー作成: 商品名 [プラットフォーム]」 | バナー広告コンセプト5案生成・ヘッドライン+ビジュアル+CTA（generate_banner_concepts） |
| 「誰に頼む？ [タスク内容]」 | people-profiles.jsonからタスクに最適な担当者候補をClaude推薦（who_to_ask） |
| 「状態確認」「エージェント状態」 | Orchestratorの稼働状況・本日タスク数・次回スケジュールを返答（orchestrator_status） |
| 「Addness更新」「タスク更新」 | addness_to_context.pyを即時実行→actionable-tasks.md再生成→件数サマリー返答（addness_sync） |
| 「メール確認」「メールチェック」 | mail_manager.py runを即時実行→返信待ち件数と概要を返答（mail_check） |
| 「再起動」「リスタート」「エージェント再起動」 | Mac Mini上のローカルエージェントを遠隔再起動（restart_agent） |

---

## ファイル構成

### クラウド側（Render）
| パス | 説明 |
|------|------|
| `System/line_bot/app.py` | メインアプリ（Webhook・タスクAPI・通知） |
| `System/line_bot/qa_handler.py` | Q&A処理ハンドラ |
| `System/line_bot/requirements.txt` | Python依存関係 |

### ローカル側（Mac Mini 常駐エージェント）
| パス | 説明 |
|------|------|
| `~/agents/line_bot_local/local_agent.py` | **実行ファイル**（Mac Mini launchdから起動。git_pull_syncで自動デプロイ） |
| `~/agents/line_bot_local/logs/agent.log` | 実行ログ（LaunchAgent StandardOutPath） |
| `~/Library/LaunchAgents/com.linebot.localagent.plist` | launchd設定（git_pull_syncが毎回パス整合性チェック＆自動修正） |
| `System/line_bot_local/local_agent.py` | Desktop版（開発・編集用。git push→Mac Miniに自動同期） |
| `System/line_bot_local/sync_data.sh` | データファイル同期（Master/配下等。local_agent.pyはgit管理に統一済み） |
| `System/kpi_processor.py` | KPI投入エンジン（import/process/check_today/refresh） |
| `System/csv_sheet_sync.py` | CSV同期・日別月別構築・KPIキャッシュ生成（LaunchAgent連携） |
| `System/kpi_summary.json` | KPIキャッシュ（`fetch_addness_kpi()`が参照、自動生成） |
| `System/looker_csv_downloader.py` | Looker Studio CSVダウンローダー（Cursor連携） |

### 知識ベース（Master/）
| パス | 説明 |
|------|------|
| `Master/people/profiles.json` | 54名のプロファイル（comm_profile + group_insights含む） |
| `Master/people/identities.json` | 人物識別データ |
| `Master/learning/reply_feedback.json` | フィードバック学習データ（修正例・スタイルノート） |
| `Master/self_clone/kohara/IDENTITY.md` | 甲原海人の言語スタイル定義 |
| `Master/self_clone/kohara/SELF_PROFILE.md` | 甲原海人のコアプロファイル |

#### `group_insights` スキーマ（profiles.json内）

週次プロファイル学習（`weekly_profile_learning`）により、各人物の `latest.group_insights` に以下が書き込まれる:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `updated_at` | string | 最終更新日（YYYY-MM-DD） |
| `message_count_7d` | int | 過去7日間のメッセージ数 |
| `active_groups` | string[] | 発言のあったグループ名（最大5件） |
| `communication_style` | string | コミュニケーションスタイル（1文） |
| `recent_topics` | string[] | 最近の関心トピック（3〜5個） |
| `collaboration_patterns` | string | 誰とどんなやり取りが多いか（1文） |
| `personality_notes` | string | 性格・行動特性（1文） |
| `activity_level` | string | `high` / `medium` / `low` |

---

## データ同期

```bash
# Desktop ↔ Library/LineBot/data/ の手動同期
bash System/line_bot_local/sync_data.sh
```

**双方向同期ファイル:**
- `people-profiles.json` — 新しい方（mtime比較）が勝つ
- `reply_feedback.json` — 新しい方が勝つ

**一方向同期（Desktop → Library）:**
- `IDENTITY.md`
- `SELF_PROFILE.md`
- `people-identities.json`

---

## デプロイ情報

| 項目 | 値 |
|------|------|
| Render URL | https://line-mention-bot-mmzu.onrender.com |
| LINE Webhook URL | https://line-mention-bot-mmzu.onrender.com/callback |
| Chatwork Webhook URL | https://line-mention-bot-mmzu.onrender.com/chatwork/callback |
| タスクAPI | https://line-mention-bot-mmzu.onrender.com/tasks |
| GitHub リポジトリ | koa800/line-mention-bot |
| LINE公式アカウント | @718azmbx |

---

## 環境変数（Render）

| 変数名 | 用途 |
|--------|------|
| `LINE_CHANNEL_SECRET` | LINE Webhook署名検証 |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINE API認証 |
| `OPENAI_API_KEY` | OpenAI API認証（旧・カレンダー用途のみ残存） |
| `ANTHROPIC_API_KEY` | Claude API認証（返信案生成） |
| `OWNER_USER_ID` | オーナー（甲原海人）のLINE User ID |
| `SECRETARY_GROUP_ID` | AI秘書とのやりとり部屋のGroup ID |
| `LOCAL_AGENT_TOKEN` | PC常駐エージェント・Mac Mini Orchestrator認証用（Mac Mini側の `AGENT_TOKEN` と同値） |
| `GOOGLE_CREDENTIALS_JSON` | Google Calendar用サービスアカウント |
| `GOOGLE_CALENDAR_ID` | カレンダーID |
| `PINECONE_API_KEY` | Pinecone API認証（Q&A） |
| `LSTEP_API_TOKEN` | L-step API認証 |
| `LSTEP_ENDPOINT_URL` | L-step エンドポイントURL |
| `CHATWORK_API_TOKEN` | Chatwork APIトークン |
| `CHATWORK_WEBHOOK_TOKEN` | Chatwork Webhook署名検証トークン（Base64） |
| `CHATWORK_ACCOUNT_ID` | 自分のChatwork account_id |
| `DATA_DIR` | データ保存ディレクトリ（`/data` = Render永続ディスク） |

---

## 注意事項・既知の制限

| 項目 | 内容 |
|------|------|
| Render プラン | Starter（$7/月）。Zero Downtime デプロイ・スリープなし |
| Macスリープ対策 | launchd plist に `caffeinate -s` を追加。エージェント起動中はMacスリープ防止 |
| データ永続化 | Render永続ディスク `/data` を使用。`DATA_DIR=/data` 環境変数で設定済み。デプロイ後も状態が消えない。`line_bot_group_log.json`（グループメッセージ日次ログ）も同ディレクトリに保存・日付ローテーション |
| macOS TCC | launchd から Desktop は直接アクセス不可。`~/agents/` をデプロイ先に使用（Library版は廃止済み） |
| LINE webhook重複 | 同一 message_id のタスクは1件のみキューイング済み |
| Mac Mini TCC制限 | LaunchAgent から `~/Desktop/` は直接アクセス不可。`~/agents/` を作業ディレクトリに使用。plistが古いパス（`~/Library/LineBot/`等）を参照していた場合、`git_pull_sync.sh`の`ensure_plist_path`が自動修正 |
| MacBook↔Mac Mini同期 | GitHub push/pull方式。post-commitで自動push→Mac Mini Orchestratorが5分ごとにgit pull→ローカルrsyncでデプロイ。外出先からも同期可能。旧rsync over SSH方式（sync_from_macbook.sh）は2026-02-22に無効化済み |
| git_pull_sync rsync除外 | `*.db`（SQLiteランタイムDB）を除外リストに追加。rsync `--delete`でagent.dbが毎回削除されるバグを修正済み（2026-02-22） |
| Orchestrator SYSTEM_DIR | tools.py の SYSTEM_DIR は __file__ ベースで動的解決（Desktop/Mac Mini両対応）。ハードコードしないこと |
| local_agent.py _SYSTEM_DIR | スクリプト呼び出しパスも __file__ ベースで動的解決済み。`mail_manager.py` の存在チェックでDesktop/Mac Miniを自動判別（`_AGENT_DIR.parent` → なければ `parent/System/`）|
| LINE Notify廃止 | LINE Notify は2025年3月終了。Render `/notify` エンドポイント + LINE Messaging API push_message で代替 |
| Google OAuth token.json | `~/agents/token.json` に保存。access tokenは1時間で失効するがrefresh_tokenで自動更新。oauth_health_checkが毎朝9時に監視 |
| MacBook機種変更 | `Project/MacBook移行ガイド.md` 参照。Mac Mini側は完全自律稼働のため影響なし。SSHキーとpost-commitフックの再設定のみ必要 |
| Chatwork Webhook設定 | Chatwork管理画面 → Webhook設定 → イベント `mention_to_me` → URL: Chatwork Webhook URL |
| Chatwork account_id | `curl -H "x-chatworktoken: TOKEN" https://api.chatwork.com/v2/me` で取得 |
| Chatwork送信者紐付け | `people-identities.json` の `chatwork_account_id` フィールドに相手のaccount_idを設定してプロファイル逆引き可能に |
| スプレッドシート文脈 | `people-profiles.json` の `related_sheets` にシートID・シート名・説明を設定。返信案生成時に `sheets_manager.py json` で自動取得 |
| Addness KPIシート | `【アドネス全体】数値管理シート`（ID: `1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA`）。タブ: 元データ / スキルプラス（日別）/ スキルプラス（月別）。`csv_sheet_sync.py` がCSV同期→日別月別構築→KPIキャッシュ生成を連鎖実行。詳細は `Project/数値管理自動化.md` を参照。kohara アカウントで読み書き |
| KPIデータ開示制御 | 事業KPI（売上・広告費・ROAS等）は内部メンバーのみ開示。外部パートナー・未登録者には `fetch_addness_kpi()` のデータ注入をスキップ。ただしプロファイルの `related_sheets` に登録されたシートデータは外部にも開示可 |
| タスク失敗通知 | Orchestratorのタスクが失敗するとLINE通知（2時間レート制限）。health_check/oauth_health_checkは除外 |

---

## Mac Mini エージェント構成

### 稼働中サービス

| LaunchAgent | 役割 | ポート |
|------------|------|--------|
| `com.linebot.localagent` | LINE Bot ポーリング・返信案生成 | — |
| `com.addness.agent-orchestrator` | タスクスケジューラ・修復エージェント・git同期 | 8500 |
| `com.prevent.sleep` | Macスリープ防止（caffeinate） | — |

### Orchestratorスケジュール

| タスク | スケジュール | 内容 |
|--------|------------|------|
| `mail_inbox_personal` | 3時間ごと :00 | personalメール処理・返信待ちLINE通知 |
| `mail_inbox_kohara` | 3時間ごと :00 | koharaメール処理・返信待ちLINE通知（personalと同時刻） |
| `ai_news` | 毎朝 8:00 | AIニュース収集・要約・通知 |
| `addness_fetch` | 3日ごと 8:00 | Addnessゴールツリー取得 |
| `daily_addness_digest` | 毎朝 8:30 | 期限超過・直近期限ゴールをLINE通知 |
| `addness_goal_check` | 毎朝 9:00 | actionable-tasks.mdをaddness-goal-tree.mdから再生成 |
| `oauth_health_check` | 毎朝 9:00 | Google OAuth有効性チェック・失敗時通知 |
| `weekly_idea_proposal` | 毎週月曜 9:00 | agent_ideas.mdのP0/P1タスクをLINE提案 |
| `weekly_stats` | 毎週月曜 9:30 | 週次サマリー（成功率・Q&A件数・Addness鮮度）をLINE通知 |
| `daily_report` | 毎夜 21:00 | 日次タスク集計をLINE通知 |
| `render_health_check` | 30分ごと | Renderサーバー死活監視・ダウン時LINE通知 |
| `health_check` | 5分ごと | API使用量・Q&Aモニター・local_agent停止を検知してLINE警告 |
| `repair_check` | 30分ごと | ログエラー検知・自動修復提案 |
| `weekly_content_suggestions` | 毎週水曜 10:00 | 最新AIニュースを分析してコンテンツ更新提案をLINE通知 |
| `kpi_daily_import` | 毎日 12:00 | 2日前のKPIデータ完了チェック→投入→KPIキャッシュ再生成→LINE通知（失敗時は個別エラー通知） |
| `kpi_nightly_cache` | 毎晩 22:00 | KPIキャッシュ再生成（AI秘書が夜間も最新データを参照できるように） |
| `sheets_sync` | 毎朝 6:30 | Master/sheets/ CSVキャッシュ最新化→KPIキャッシュ再生成（失敗時はLINE通知） |
| `git_pull_sync` | 5分ごと | GitHubからpull→rsyncデプロイ→サービス再起動→LINE通知（30分連続失敗で警告通知） |
| `daily_group_digest` | 毎夜 21:00 | Renderからグループログ取得→Claude Haiku分析→秘書グループにダイジェスト通知 |
| `weekly_profile_learning` | 毎週日曜 10:00 | 過去7日間のグループログから各メンバーの会話を分析→profiles.jsonに`group_insights`として書き込み |
| `log_rotate` | 毎日 3:00 | ログローテーション（50MB超を圧縮、30日超の古いgzを自動削除） |

### Orchestrator API エンドポイント（port 8500）

| エンドポイント | メソッド | 説明 |
|-------------|---------|------|
| `/health` | GET | ヘルスチェック・本日のタスクサマリー |
| `/tasks` | GET | 直近50件のタスク実行ログ |
| `/stats` | GET | 直近24時間のタスク統計 |
| `/schedule/status` | GET | 全ジョブの次回実行時刻・最終成功 |
| `/schedule/run/{task_name}` | POST | スケジュールタスクを手動トリガー |
| `/run/{tool_name}` | POST | ツールを直接実行（TOOL_REGISTRYに登録されたもの） |
| `/repair/run` | POST | 修復チェックを手動実行 |
| `/repair/status` | GET | 修復ブランチのペンディング状態確認 |

### Orchestrator 通知フロー

```
Mac Mini Orchestrator
  → POST /notify (Bearer AGENT_TOKEN)
    → Render app.py /notify endpoint
      → LINE Messaging API push_message
        → SECRETARY_GROUP_ID（秘書グループ）
```

### Render API（AGENT_TOKEN認証）

| エンドポイント | メソッド | 説明 |
|-------------|---------|------|
| `/notify` | POST | 秘書グループにメッセージ送信 |
| `/api/group-log` | GET | グループメッセージ日次ログ取得（`?date=YYYY-MM-DD`、省略時は当日） |
| `/tasks` | GET | 未処理タスクキュー取得 |
| `/qa/new` | POST | 新着Q&A受け取り・AI回答生成 |

### コード同期アーキテクチャ

```
MacBook (どこからでも)
  │
  ├── コミット → post-commit フック → git push origin main  [自動]
  │
  ▼ GitHub (koa800/meta-banner-maker)
  │
  └── Mac Mini Orchestrator (git_pull_sync, 5分ごと)
       ├── [毎回] plistパス整合性チェック（ensure_plist_path）
       │    └── ~/agents/ 以外のパスを参照 → plist再生成＆再起動→LINE通知
       ├── git fetch → 差分なければ即終了（軽量）
       ├── git reset --hard origin/main
       ├── ローカル rsync → ~/agents/ にデプロイ
       └── 変更ファイルに応じてサービス再起動 + LINE通知
           ├── line_bot_local/*.py 変更 → local_agent 再起動→LINE通知
           ├── agent_orchestrator/ 変更 → Orchestrator 再起動
           └── .restart_local_agent シグナルファイル検知 → 遠隔再起動→LINE通知
```

**同期対象ディレクトリ:** `System/`, `line_bot_local/`, `Master/`, `Project/`, `Skills/`
**除外:** `addness_chrome_profile/`, `addness_data/`, `qa_sync/`, `mail_review_web/`, `*.log`, `*.db`, `addness_session.json`, `config.json`, `contact_state.json`

### 関連ファイル（Mac Mini）

| パス | 説明 |
|------|------|
| `System/mac_mini/agent_orchestrator/` | Orchestratorパッケージ |
| `System/mac_mini/agent_orchestrator/notifier.py` | LINE通知ディスパッチャ（Render経由） |
| `System/mac_mini/agent_orchestrator/config.yaml` | エージェント設定（パス・スケジュール等） |
| `System/mac_mini/git_pull_sync.sh` | GitHub pull→ローカルデプロイスクリプト |
| `.git/hooks/post-commit` | コミット時に自動 `git push origin main` |
| `Project/MacBook移行ガイド.md` | MacBook機種変更時の移行手順書 |

---

## 今後の拡張案

- [x] Googleカレンダー連携
- [x] タスクキューAPI
- [x] PC常駐エージェント（launchd）
- [x] Claude APIでの返信案生成（Sonnet 4.6）
- [x] per-personプロファイル（54名）
- [x] フィードバックループ（fb / 修正例自動学習）
- [x] メモコマンド
- [x] 引用返信（リプライ）検知
- [x] 会話文脈バッファリング（メンション直前10件）
- [x] デプロイ完了通知
- [x] Q&A自動回答システム
- [x] SELF_PROFILE.md の記入（価値観・判断軸）
- [x] Renderスリープ防止（Starter移行済み・スリープなし）
- [x] Macスリープ対策（caffeinate -s でエージェント起動中はスリープ防止）
- [x] 2コマンドのai_suggestion未取得時も学習するよう修正
- [x] 1/2フォールバックを返信案通知時刻で選ぶよう修正（誤送信バグ）
- [x] pending_messages永続化（Render永続ディスク /data）
- [x] オーナー直接送信メッセージへの引用返信も検知するよう修正（sent_group_messages追跡範囲拡張）
- [x] show_notification LaunchAgentハング修正（threading.Thread化でメインスレッドブロッキング解消）
- [x] Mac Mini Agent Orchestratorデプロイ（FastAPI + APScheduler, port 8500）
- [x] LINE Notify廃止対応（Render /notify エンドポイント + LINE Messaging API push_message）
- [x] Mac Mini rsync TCC制限対応（Git post-commitフックでDesktop→Mac MiniへrsyncをDesktop側から実行）→ GitHub同期に移行済み
- [x] SYSTEM_DIR Critical Bug修正（tools.py を __file__ ベースの動的パスに変更・Mac Mini/Desktop両対応）
- [x] メール処理後LINE通知（返信待ちがある場合に秘書グループへ自動通知）
- [x] qa_monitor 本番有効化（config.json `qa_monitor_enabled: true`）
- [x] post-commit hook 拡張（line_bot_local/同期追加・config.json変更時も再起動・Orchestrator変更時も再起動）
- [x] 個人DM対応（メンバーからのDMを秘書グループに通知→承認→返信・学習フロー）
- [x] Addness Goal Tree Watch（タスク自動抽出パイプライン実装完了）
- [x] 個人DM対応（メンバーからのDMを秘書グループに通知→承認→返信・comm_profile活用）
- [x] Mac Mini双方向自動同期（post-commitフック + 5分ごとLaunchAgent）→ GitHub push/pull方式に移行済み
- [x] Orchestrator日次LINEレポート（毎夜9時に成功率・エラー集計を通知）
- [x] タスク失敗LINE通知（失敗時にLINE通知・2時間レート制限で重複防止）
- [x] Google OAuth監視（毎朝9時にtoken.json + API認証テスト・失敗時LINE通知）
- [x] 同期失敗LINE通知（sync_from_macbook.shのrsyncエラー時にLINE通知）
- [x] API使用量警告（直近1時間が90%超でLINE通知）
- [x] スケジュールステータスAPI（GET /schedule/status で全ジョブの次回実行・最終成功を確認可能）
- [x] MacBook移行ガイド作成（`Project/MacBook移行ガイド.md`・1ヶ月後の機種変更向け）
- [x] calendar_listバグ修正（tools.pyのdays=1で今日の日付を自動設定・`"7"`を日付として渡すバグ解消）
- [x] 日次ダイジェスト+カレンダー統合（毎朝8:30の通知に今日の予定を追加）
- [x] ミーティング準備ブリーフィング（カレンダー参加者をpeople-profiles.jsonでルックアップ・カテゴリ付きで表示）
- [x] calendar_manager.py 参加者表示機能追加（list_eventsで参加者displayName出力）
- [x] context_queryコマンド（「次何？」でAddness+メール+KPIサマリ+Claude分析→優先行動リスト返答）
- [x] kpi_queryコマンド（「広告数値」「ROAS」等でKPIデータ自動取得→Claude分析・トレンド評価・改善提案返答）
- [x] restart_agentコマンド（LINEから「再起動」でMac Miniローカルエージェントを遠隔再起動）
- [x] git_pull_sync改善（line_bot_local/*.py変更で自動再起動・LINE通知・遠隔再起動シグナル検知）
- [x] generate_lp_draftコマンド（「LP作成: 商品名」でLP構成案+キャッチコピー自動生成）
- [x] generate_video_scriptコマンド（「スクリプト作成: 商品名」でTikTok/YouTube広告台本自動生成）
- [x] calendar_list トークン未存在時のハング防止（token file存在チェックで即時フェイル）
- [x] generate_banner_conceptsコマンド（「バナー作成: 商品名」でバナー広告コンセプト5案自動生成）
- [x] 特殊期限リマインダー（東北大学研究コラボ2026/08/31の90/30/7/3/1日前にLINE通知）
- [x] 週次ボトルネック分析（weekly_stats実行時にClaudeがactionable-tasks.mdを分析して最大課題を通知）
- [x] weekly_content_suggestionsスケジューラ（毎週水曜10:00にai_news.log分析→コンテンツ更新提案）
- [x] who_to_askコマンド（「誰に頼む？」でpeople-profiles.jsonからタスク担当候補をClaude推薦）
- [x] POST /schedule/run/{task_name}（Orchestratorスケジュールタスクの手動トリガーAPI）
- [x] orchestrator_statusコマンド（「状態確認」でOrchestrator稼働状況・スケジュールをLINE返答）
- [x] addness_syncコマンド（「Addness更新」でaddness_to_context.py即時実行→件数サマリー返答）
- [x] mail_checkコマンド（「メール確認」でmail_manager.py run即時実行→処理結果返答）
- [x] ヘルプコマンド（「ヘルプ」「コマンド一覧」で全機能一覧を表示・Claude API呼び出しなし）
- [x] qa_statusコマンド（「QA状況」でqa_monitor_state.json読み込み→検知件数・保留数・最終チェック返答）
- [x] local_agent.py _SYSTEM_DIR パスバグ修正（who_to_ask/addness_sync/mail_check/context_queryがMac Miniで正常動作）
- [x] 日報入力のLINE対応見直し（AppleScriptエラー→Cursor案内メッセージに変更。Looker Studio・b-dashブラウザ操作必須のためCursor直接実行が正解）
- [x] Chatwork連携（Webhook受信→返信案生成→承認→Chatwork APIで返信。プラットフォーム分岐でLINE/CW自動判別）
- [x] スプレッドシート文脈参照（people-profiles.jsonのrelated_sheetsからシートデータを自動取得→プロンプト注入）
- [x] people-identities.jsonにchatwork_account_id/chatwork_display_nameフィールド追加（全81エントリ）
- [x] 未返信一覧に[CW]/[LINE]プラットフォームバッジ表示
- [x] Addness KPI自動参照（4段階フォールバック: freshキャッシュ→CSV再構築→Sheets API→staleキャッシュ（警告付き）。7日超は使用不可。媒体別・媒体×ファネル別内訳対応。異常値検知・目標KPI対比・stale警告付き。外部パートナー・未登録者にはKPI非開示）
- [x] MacBook↔Mac Mini同期をGitHub経由に移行（rsync over SSH廃止→git push/pull。外出先からも同期可能）
- [x] Mac Mini旧cronジョブ整理（addness/ai_news/mail/sync_agent全5件削除→Orchestrator一元管理）
- [x] agent.db削除バグ修正（git_pull_syncのrsync --deleteがランタイムDBを毎回削除→*.db除外追加）
- [x] plistパス自動修正（git_pull_syncがlaunchctl plistのパス整合性を毎回チェック。Library版など古いパスを検知→正しいデプロイ先に自動修正＆再起動＆LINE通知）
- [x] Library版local_agent.py廃止（sync_data.shの「Library版維持」コメント削除。git同期版が正式な実行パスに統一）
- [x] 旧sync_from_macbook.sh無効化（LaunchAgent unload + .disabled化。GitHub同期に完全移行済み）
- [x] group_insights返信プロンプト注入（週次学習で蓄積された会話スタイル・関心・性格を返信案生成に自動反映。以前は書き込むだけで読み出されていなかった）
- [x] 承認フィードバック学習（「1」承認時にAI案=正解として成功例を蓄積。以前は「2」修正時のみ学習→承認パターンを一切学習できていなかった）
- [x] Q&A承認時Pineconeナレッジ蓄積（承認済み回答をベクトルDBに自動upsert。以前は承認→スプレッドシート書き込みのみでナレッジが蓄積されなかった）
- [x] Slack Webhook URL外部化（addness_config.json/run_addness_pipeline.shから環境変数に移動。GitHub Push Protection対応）
- [x] 管理シート自動同期（`sheets_sync.py`。Master/sheets/README.md登録シートのCSVキャッシュを毎朝6:30に自動更新。Orchestrator統合済み）
- [x] グループLINE監視+日次ダイジェスト（全グループメッセージを永続ログに蓄積→毎夜21:00にClaude Haiku分析→グループ別要約・活動度・アクション事項を秘書グループに通知。`/api/group-log` APIでログ取得可能）
- [x] グループログ30日アーカイブ＋週次プロファイル学習（日次ログを`{DATA_DIR}/group_logs/{YYYY-MM-DD}.json`に自動アーカイブ（30日保持）。毎週日曜10:00にClaude Haikuが過去7日間の会話を人物ごとに分析→`profiles.json`の`group_insights`フィールドに書き込み）

---

## Addness連携（Goal Tree Watch → タスク抽出 → 実行）

### 思想

Addnessはビジョン・ゴール定義・タスク分解の場。Cursor/Claude Code等は実行の場。
この2つをシームレスに繋ぐため、Addnessの構造化されたGoal Treeデータを定期的にウォッチし、「今すぐ実行できるタスク」を抽出してCursor/Claude等に自動提示する。

> **注意**: チャット内容のリアルタイム連携ではなく、Goal Tree（構造化データ）をベースにした連携。

### アーキテクチャ

```
┌────────────────────────┐     Playwright      ┌──────────────────────────────┐
│  Addness ウェブアプリ     │  <── ログイン+巡回  │  addness_fetcher.py          │
│  Goal Tree / Preview API │  ── JSON取得 ──>    │  - セッション管理              │
│  2503ノード / 456プレビュー│                     │  - API Response インターセプト  │
└────────────────────────┘                     │  → addness_data/latest.json   │
                                                └──────────────────────────────┘
                                                               │
                                                     latest.json│
                                                               ▼
                                                ┌──────────────────────────────┐
                                                │  addness_to_context.py        │
                                                │  - GoalNode構造化              │
                                                │  - .cursor/rules/addness-goals.mdc │
                                                │  - Master/addness/goal-tree.md │
                                                └──────────────────────────────┘
                                                               │
                                                     latest.json│
                                                               ▼
                                                ┌──────────────────────────────┐
                                                │  addness_task_extractor.py    │
                                                │  - 実行可能タスク抽出          │
                                                │  - 優先度スコアリング          │
                                                │  - 委任先超過タスク検知         │
                                                │  → Master/addness/actionable-tasks.md │
                                                │  → .cursor/rules/addness-actionable.mdc │
                                                └──────────────────────────────┘
                                                               │
                                                  Cursorルール  │ 自動注入
                                                               ▼
                                                ┌──────────────────────────────┐
                                                │  Cursor / Claude Code         │
                                                │  (MacBook / Mac Mini)         │
                                                │                               │
                                                │  addness-actionable.mdc で     │
                                                │  実行可能タスクを常に認識       │
                                                │  → タスクの実行・実装           │
                                                └──────────────────────────────┘
```

### パイプライン実行

```bash
# 1. Addnessからデータ取得（ブラウザ自動操作）
python3 System/addness_fetcher.py

# 2. Goal Tree構造化 + Cursorルール生成
python3 System/addness_to_context.py

# 3. 実行可能タスク抽出
python3 System/addness_task_extractor.py

# ワンライナー
python3 System/addness_fetcher.py && python3 System/addness_to_context.py && python3 System/addness_task_extractor.py
```

### 出力ファイル

| パス | 説明 |
|------|------|
| `addness_data/latest.json` | 生データ（APIレスポンス全量） |
| `.cursor/rules/addness-goals.mdc` | 全体Goal Tree（Cursor自動注入） |
| `Master/addness/goal-tree.md` | 全体Goal Tree（フル版） |
| `.cursor/rules/addness-actionable.mdc` | 実行可能タスクTOP15（Cursor自動注入） |
| `Master/addness/actionable-tasks.md` | 実行可能タスク全量（詳細版） |

### タスク抽出ロジック

**抽出条件:**
1. 甲原海人が直接担当
2. 完了していない
3. リーフノード（未完了の子がない）= 今すぐ着手できる

**優先度スコアリング:**
- リーフノード: +50
- 直接担当: +30
- 実行中: +20 / 検討中: +10
- 期限超過: +40 / 今週期限: +25
- 説明あり: +10

**カテゴリ分類:**
- 🔴 期限超過（即対応）
- ⚡ 今週期限
- 🔄 実行中
- 🔍 検討中（着手可能）
- ⚠️ 委任先で期限超過（フォロー推奨）
- 👁 ウォッチ中（子タスクが進行中）

### 関連ファイル

| パス | 説明 |
|------|------|
| `System/addness_fetcher.py` | Playwright でAddnessからデータ取得 |
| `System/addness_to_context.py` | GoalNode構造化・ゴールツリー生成 |
| `System/addness_task_extractor.py` | 実行可能タスク抽出・優先度付け |
| `System/addness_session.json` | Addnessセッション（自動管理） |
| `System/addness_config.json` | Addness接続設定 |

### ステータス

- [x] データ取得パイプライン（addness_fetcher.py）
- [x] Goal Tree構造化（addness_to_context.py）
- [x] 実行可能タスク抽出（addness_task_extractor.py）
- [x] Cursorルール自動注入（addness-actionable.mdc）
- [x] 定期実行の自動化（Orchestrator addness_fetch: 3日ごと + addness_goal_check: 毎朝9時）
- [x] Mac Mini からの定期実行統合（com.addness.agent-orchestrator で稼働中）

### 旧MCP Context Pipe（アーカイブ）

初期構想としてMCPサーバー経由でAddnessチャット内容をリアルタイム連携する方式を実装したが、
「チャット内容のリアルタイム同期」よりも「Goal Treeの構造化データからタスクを抽出」する方が本質的と判断し、
Goal Tree Watchアプローチに切り替え。MCPサーバー（`System/addness_mcp_server/`）はRender上に残存。

---

## Q&A自動回答システム

### 概要

受講生からの質問に対して、過去のQ&Aデータを参考にAIが回答案を生成し、承認後にL-step経由で自動返信。

### アーキテクチャ

```
スプレッドシート ← PC常駐エージェント（質問検知・ポーリング）
                          │ 新着質問送信
                          ▼
               Render（類似検索 via Pinecone → AI回答生成 → LINE通知）
                          │
               秘書グループで承認/編集
                          │
               L-step API → 受講生に自動返信
```

### 関連ファイル

| パス | 説明 |
|------|------|
| `System/qa_search.py` | Pinecone連携・ベクトル検索 |
| `System/lstep_api.py` | L-step API連携 |
| `System/qa_sync/sync_to_pinecone.py` | Q&AデータのPinecone同期 |
| `System/line_bot/qa_handler.py` | Q&A処理ハンドラ |
| `System/line_bot_local/qa_monitor.py` | Q&A質問監視モジュール |
