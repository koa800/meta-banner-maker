# AI秘書作成

## 基本情報

| 項目 | 内容 |
|------|------|
| プロジェクト名 | AI秘書作成 |
| 開始日 | 2026年2月18日 |
| 最終更新 | 2026年2月26日（OSすり合わせセッション・意図ベース学習・タスク結果フィードバック追加） |
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
                               │                                │
                               │  【v3】Claude Code 自律モード   │
                               │  - claude -p (CLI) で自律実行   │
                               │  - 返信案: プロファイル自動検索  │
                               │  - タスク: スクリプト実行・Web検索│
                               │  - Bash/WebSearch/Read/Grep 全解放│
                               │  - ~/.claude-secretary/ で認証分離│
                               │  - 失敗時: 既存API/Coordinator │
                               │    にフォールバック              │
                               │                                │
                               │  【v2】Coordinator（司令塔）    │
                               │  - coordinator.py              │
                               │  - handler_runner.py           │
                               │  - tool_registry.json (13ツール)│
                               │  - ゴール→分解→委任→統合→報告  │
                               │  → 詳細: Project/ゴール実行     │
                               │    エンジン設計.md              │
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
7. **ゴール実行エンジン接続（execute_goal）**: LINE→Render(app.py)→task_queue→local_agent.py→coordinator.py→LINE通知のE2Eフロー完了。調査・リサーチ系タスクをCoordinatorにルーティング。MacBookは`~/Library/LineBot/`にデプロイ（TCC制限対策）

### Phase 3: Mac Mini 常駐エージェント（完了）
7. **launchd常駐**: Mac Mini `~/agents/line_bot_local/local_agent.py` をlaunchdで自動起動
8. **Mac Mini TCC回避**: macOS TCC制限のため `~/agents/` を作業ディレクトリとして使用
9. **デプロイ完了通知**: Render起動時にLINEへ通知（gunicorn multi-worker対応・重複防止）

### Phase 4: 人物プロファイル × フィードバック学習（完了）
10. **per-personプロファイル**: 56名の `comm_profile`（返信スタイル・挨拶・敬語レベル・個別性格対応）を手動最適化済み
    - **敬語レベル3段階**: `formality` フィールド（`low`=タメ口 / `medium`=親しみやすい敬語 / `high`=丁寧語）をプロンプトに明示注入
    - **個別性格対応**: 一人ひとりの性格・関係性に合わせた `style_note`・`tone_keywords`・`avoid` を設定（繊細→優しく、志高い→鼓舞、賢い→厳密、など）
    - **出力ルール**: 「【最重要】敬語レベルを厳守」指示により、タメ口の相手に敬語が混入する問題を解消
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

### Phase 8: Claude Code 自律モード（完了）
33. **Claude Code CLI統合**: `claude -p`（非対話モード）で返信案生成・タスク実行を自律的に実行。ファイル読み取り・Grep検索・スクリプト実行・Web検索を自分で判断して使用
34. **返信案のハイブリッド生成**: Pythonが事前に送信者プロファイル・学習データを計算 → Claude Codeが自律的にprofiles.json検索・goal-tree.md参照で追加文脈を取得 → マーカー（`===REPLY_START===`/`===REPLY_END===`）で返信文を抽出。失敗時は既存Claude API直接呼び出しにフォールバック
35. **汎用タスク実行**: LINEからの自然言語指示をClaude Codeが自律実行。sheets_manager.py/mail_manager.py/Google API等のスクリプトをBashで実行可能。破壊的操作（ファイル削除・git操作・デプロイ・プロセスkill・環境変数変更）は明示的に禁止
36. **認証分離**: `~/.claude-secretary/`（甲原アカウント MAX）で日向エージェント（`~/.claude/`）と完全分離。`CLAUDE_CONFIG_DIR`環境変数でsubprocess起動時に切り替え
37. **bypassPermissions**: `~/.claude-secretary/settings.json`でBash/WebSearch/Read等の全ツール解放。rm/sudo/kill/force-push等の破壊的操作のみask制限
38. **人名ハルシネーション防止**: profiles.jsonから全メンバー名を抽出し「社内メンバー一覧」としてプロンプトに注入。「人名ルール: profiles.jsonに存在する正確な名前のみ使用」を出力ルールに追加

### Phase 7: 積み上がる学習（完了）
29. **人ごとの会話記憶**: 返信案生成のたびに `contact_state.json` へ会話要約を保存（1人最大20件）。次回の返信プロンプトに直近5件の過去会話を注入し、文脈の連続性を向上。旧形式（タイムスタンプ文字列）からの自動マイグレーション対応
30. **Q&A回答スタイル学習**: Q&A承認時にAI案と異なる修正があれば `qa_feedback.json`（Render永続ディスク）に自動保存（最大30件）。次のQ&A回答生成時に直近5件の修正例をプロンプトに注入し、回答スタイルを学習
31. **返信スタイル自動学習**: 毎週日曜10:00の `weekly_profile_learning` 内で `reply_feedback.json` の修正パターンをClaude Haikuで分析し、再利用可能なスタイルルールを `Master/learning/style_rules.json` に自動生成。highconfidenceルールは全返信プロンプトに注入
32. **comm_profile自動更新**: 同じく `weekly_profile_learning` 内で、修正パターンが3件以上ある人物の `comm_profile`（tone_keywords, style_note）をClaude Haikuで分析・自動更新。`profiles.json` にマージ書き込み

---

## コマンドリファレンス（秘書グループ内）

### 返信承認

| コマンド | 動作 |
|----------|------|
| `1` | 返信案を承認して送信（引用リプライで対象特定推奨） |
| `2 [送りたい内容]` | 修正した内容で送信（AI案と異なれば自動学習） |
| `❌ {ID}` | キャンセル |
| `リスト` / `一覧` | 未返信メンション一覧 |

> ※ 返信案メッセージに**引用返信**して `1` / `2 [内容]` を送ると、対象が自動特定される
> ※ 未返信が複数ある場合、引用リプライなしの `1` は確認メッセージを表示（誤送信防止）

### フィードバック・学習

| コマンド | 動作 | 適用範囲 |
|----------|------|---------|
| `fb [内容]` | スタイルノートとして保存 | **全員への返信**に適用 |
| `ルール [内容]` | タスク実行の行動ルールとして保存 | **全タスク実行+返信案生成**に適用 |
| `2 [修正]` で承認 | 修正例として保存（AI案と異なる場合） | その人優先・他も参照（最大5件） |
| `1` で承認 | 成功例として保存（AI案が正解だったパターン） | その人優先・他も参照（最大3件） |
| `メモ [人名]: [内容]` | プロファイルに文脈メモを追加 | その人への返信に適用 |
| タスク完了通知に引用👍 | 良い結果として意図学習 | 同種タスクの判断基準に適用 |
| タスク完了通知に引用👎+理由 | 改善点として意図学習 | 同種タスクの判断基準に適用 |

### OSすり合わせ

| コマンド | 動作 |
|----------|------|
| `OSすり合わせ` / `OS同期` / `OSアップデート` | 脳のOS認識同期セッションを開始。現在の理解を報告し、薄い部分を質問 |

> AI秘書 = 甲原さんのクローン。意思決定・人との関わり方・判断基準のOSを定期的にすり合わせて認識ギャップを0にする。
> 結果は `Master/self_clone/kohara/BRAIN_OS.md` に蓄積。

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
| 「〇〇を調べて」「〇〇をリサーチして」等 | ゴール実行エンジン（Coordinator）経由でWeb検索・ツール呼び出し→統合結果をLINE返答（execute_goal） |

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

### ローカル側（MacBook LaunchAgent）
| パス | 説明 |
|------|------|
| `~/Library/LineBot/local_agent.py` | **実行ファイル**（MacBook launchdから起動。TCC制限のため~/Desktop/から直接読めないため~/Library/LineBot/に配置） |
| `~/Library/LineBot/coordinator.py` | Coordinator（ゴール実行エンジン司令塔） |
| `~/Library/LineBot/handler_runner.py` | ハンドラランナー |
| `~/Library/LineBot/tool_registry.json` | ツール定義（13ツール） |
| `~/Library/LineBot/data/` | データキャッシュ（Master/等のコピー。post-commitフックで自動同期） |
| `System/line_bot_local/sync_data.sh` | データファイル同期（Master/配下等。local_agent.pyはgit管理に統一済み） |
| `System/kpi_processor.py` | KPI投入エンジン（import/process/check_today/refresh） |
| `System/csv_sheet_sync.py` | CSV同期・日別月別構築・KPIキャッシュ生成（LaunchAgent連携） |
| `System/kpi_summary.json` | KPIキャッシュ（`fetch_addness_kpi()`が参照、自動生成） |
| `System/looker_csv_downloader.py` | Looker Studio CSVダウンローダー（Cursor連携） |

### Claude Code 認証（Mac Mini）
| パス | 説明 |
|------|------|
| `~/.claude-secretary/settings.json` | 秘書用Claude Code権限設定（bypassPermissions + 破壊的操作ask制限） |
| `~/.claude-secretary/.credentials.json` | 秘書用OAuth認証情報（甲原アカウント MAX） |
| `~/agents/_repo/System/credentials/` → `~/agents/System/credentials/` | シンボリックリンク（client_secret.json等） |
| `~/agents/_repo/System/data/` → `~/agents/System/data/` | シンボリックリンク（kpi_summary.json等） |
| `~/agents/_repo/System/config/` → `~/agents/System/config/` | シンボリックリンク（ai_news.json等） |

### 知識ベース（Master/）
| パス | 説明 |
|------|------|
| `Master/people/profiles.json` | 58名のプロファイル（comm_profile + group_insights含む） |
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

#### `comm_profile` スキーマ（profiles.json内）

各人物の `latest.comm_profile` に以下が設定される:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `formality` | string | 敬語レベル: `low`（タメ口）/ `medium`（親しみやすい敬語）/ `high`（丁寧語） |
| `greeting` | string | 推奨挨拶（例: 「お疲れ様！」「お疲れ様です！」） |
| `style_note` | string | その人への言葉選びの方針（プロンプトに直接注入） |
| `tone_keywords` | string[] | 口調キーワード（例: タメ口, ポジティブ, 厳密） |
| `avoid` | string[] | 避けるべき表現（例: 敬語, 強い言い方） |
| `context_notes` | array | `/メモ` コマンドで追加された文脈メモ |
| `auto_generated` | bool | `false`=手動最適化済み / `true`=ルールベース自動生成 |

#### コミュニケーションスタイル一覧（2026-02-23 全員手動最適化済み）

**丁寧語（1名）**

| 名前 | カテゴリ | スタイル |
|------|---------|---------|
| 三上 功太 | 上司 | 丁寧だが堅くなく、提案型。数字・具体例で説得力。「どうでしょうか？」で締める |

**親しみやすい敬語（21名）**

| 名前 | カテゴリ | スタイル |
|------|---------|---------|
| 山内悠人 | 横（並列） | クリティカル・短くシンプル・ポジティブ丁寧 |
| Maeda Nobumi | 横（並列） | 同上 |
| 竹内翼 | 横（並列） | 同上 |
| 西村優月 | 横（並列） | 同上 |
| 大塚蔵人 | 横（並列） | 同上 |
| 創太 | 横（並列） | 同上 |
| 三上大慈 | 横（並列） | 同上 |
| 小川幸一 | 横（並列） | 同上 |
| 小林真之 | 外部パートナー | 丁寧だが親しみも。ビジネスライク |
| 宮代優成 | 直下（横に近い） | クリティカル・陽気なのでポジティブ |
| 山田優斗 | 直下（横に近い） | 分かりやすくクリティカル |
| 橋本陸 | 直下（横に近い） | 相手に合わせ、無理に引っ張らず気遣い |
| 長屋友美 | 直下（横に近い） | 同上 |
| 金谷美依 | 直下 | →タメ口欄参照 |
| 中里真美 | 直下 | 堅くなりすぎず親しみやすい丁寧語 |
| 田邊雄大 | 直下 | 同上 |
| 富田悠斗 | 直下 | 同上 |
| 横江菜月 | 直下 | 同上 |
| NAMI NKAMEME | 直下 | 丁寧語ベース、たまにタメ口。年配への敬意 |
| 池本まい | 直下 | フランクにポジティブ |
| 佐々木まなみ | 直下 | フランクにポジティブ |

**タメ口（34名）**

| 名前 | 性格・特徴 | 言葉選びの方針 |
|------|-----------|--------------|
| しおり | 一番近しい存在 | 自然体で飾らない。普段の会話そのまま |
| KENTA | 繊細 | 優しく柔らかい。強い言い方・がっつり表現NG |
| 鈴木織大 | メンタル強い | スパスパ伝える。ポジティブに鼓舞 |
| 五月女隆真 | 前向き | 「ノリノリでやろう」系の鼓舞。ネガティブ時は優しくor詰める |
| NOBUTERU CHIBA | 機械的 | 言葉選び厳密。正確・具体的に |
| 三井瑛登 | 賢い（関わり浅い） | 優しく。考えさせる質問を投げかける |
| 宮本寧々 | 元気 | シンプル・短く・分かりやすく |
| 森本雄紀 | 賢い | 厳密・クリティカル・曖昧さ排除 |
| 小澤 和樹 | めちゃ元気 | 「どんどん行こう」「引っ張っていこう」で鼓舞 |
| 内田裕樹 | エネルギッシュ | 「ガンガン行きましょう」ポジティブ全開 |
| 金谷美依 | — | 「頑張ってね」「応援してるよ」励まし・温かみ |
| 坂井柾駿 | — | 相手の雰囲気に合わせる。気遣い |
| 小笠原龍一 | — | 丁寧な言葉でクリティカルに |
| 川口健輔 | — | 同上 |
| 鞘野 緑 | — | 丁寧・わかりやすく・優しく親しみやすい |
| 宮本 楓 | — | 同上 |
| 駒井志帆 | — | 厳密・クリティカル・正確重視 |
| 三浦拓実 | 志が高い | 「ガンガン行こう」ポジティブ鼓舞 |
| 落合真琴 | 繊細（家族あり） | 優しく。家族を気にかける。温かみ |
| 鎌田由布子 | — | 「周りの役に立とう」「成長していこう」前向き |
| 荻野豪太 | 仕事好き | アイデア共有「こういうの作ろう」「どんどんやろう」 |
| ジェイン 可菜 | 繊細 | 優しくポジティブ。温かく励ます |
| 山口 桜介 | 荻野さんの部下 | 「ついていって」「チャレンジしよう」成長促進 |
| MAYANK JAIN | 前向き | ポジティブ・明るく鼓舞 |
| NAOKI | — | 「頼むよ」期待と信頼を込める |
| 新井 知之 | — | 期待込め「デカいことやっていこう」前向きスケール大 |
| 野口颯斗 | 繊細 | 「チャレンジしよう」前向き。優しく背中を押す |
| 髙橋海斗 | 本質を求める | 「こうしたらうまくいくよ」考えさせるフィードバック |
| 楢木野萌 | キラキラ・ノリ良い | ノリでコミュニケーション。テンション高め |
| 伊藤開己 | — | 「人の役に立て」「チャレンジしよう」背中を押す |
| 崎原大地 | 本質を求める | 本質的フィードバック＋「頼むよ」期待 |
| 伴亮太 | 知的好奇心・思慮深い | クリティカル・最先端情報を提供。知的刺激 |
| 園部優士 | — | 「やっていこう」前向き・ポジティブ鼓舞 |
| 浅田 輝哉 | — | 厳密・明確・正確。間違いのない言葉 |
| 西畑宏哉 | — | 親しみやすい。依頼時は厳密に要件定義 |

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

**post-commitフック自動同期（Desktop → ~/Library/LineBot/data/）:**
- Master/配下のデータキャッシュをコミット時に自動コピー
- MacBook LaunchAgentがTCC制限で~/Desktop/を読めないための対策

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
| macOS TCC（Mac Mini） | launchd から Desktop は直接アクセス不可。`~/agents/` をデプロイ先に使用（Library版は廃止済み） |
| macOS TCC（MacBook） | LaunchAgentから `~/Desktop/` は直接アクセス不可。`~/Library/LineBot/` にデプロイ。`data/` にMaster/等のキャッシュコピーを配置し、post-commitフックで自動同期 |
| LINE webhook重複 | 同一 message_id のタスクは1件のみキューイング済み |
| Mac Mini TCC制限 | LaunchAgent から `~/Desktop/` は直接アクセス不可。`~/agents/` を作業ディレクトリに使用。plistが古いパス（`~/Library/LineBot/`等）を参照していた場合、`git_pull_sync.sh`の`ensure_plist_path`が自動修正。plist再生成時は`config.json`から`ANTHROPIC_API_KEY`/`AGENT_TOKEN`/`LINE_BOT_SERVER_URL`も自動設定 |
| MacBook↔Mac Mini同期 | GitHub push/pull方式。post-commitで自動push→Mac Mini Orchestratorが5分ごとにgit pull→ローカルrsyncでデプロイ。外出先からも同期可能。旧rsync over SSH方式（sync_from_macbook.sh）は2026-02-22に無効化済み |
| git_pull_sync rsync除外 | `*.db`（SQLiteランタイムDB）を除外リストに追加。rsync `--delete`でagent.dbが毎回削除されるバグを修正済み（2026-02-22） |
| Orchestrator SYSTEM_DIR | tools.py の SYSTEM_DIR は __file__ ベースで動的解決（Desktop/Mac Mini両対応）。ハードコードしないこと |
| local_agent.py _SYSTEM_DIR | スクリプト呼び出しパスも __file__ ベースで動的解決済み。`mail_manager.py` の存在チェックでDesktop/Mac Miniを自動判別（`_AGENT_DIR.parent` → なければ `parent/System/`）|
| LINE Notify廃止 | LINE Notify は2025年3月終了。Render `/notify` エンドポイント + LINE Messaging API push_message で代替 |
| Google OAuth token.json | `~/agents/token.json` に保存。access tokenは1時間で失効するがrefresh_tokenで自動更新。oauth_health_checkが毎朝9時に監視 |
| MacBook機種変更 | `Project/MacBook移行ガイド.md` 参照。Mac Mini側は完全自律稼働のため影響なし。SSHキーとpost-commitフックの再設定のみ必要 |
| 手元PCのスリープ・閉じ蓋 | 定常タスク（Orchestrator・LINE local・メール・日報・Q&A等）は**Mac Mini**で稼働。手元のMacBookをスリープ/閉じ蓋しても**これらの仕組みは止まらない**。閉じ蓋でもスリープしないようにするには下記「クラムシェルモード」を参照 |
| Chatwork Webhook設定 | Chatwork管理画面 → Webhook設定 → イベント `mention_to_me` → URL: Chatwork Webhook URL |
| Chatwork account_id | `curl -H "x-chatworktoken: TOKEN" https://api.chatwork.com/v2/me` で取得 |
| Chatwork送信者紐付け | `people-identities.json` の `chatwork_account_id` フィールドに相手のaccount_idを設定してプロファイル逆引き可能に |
| スプレッドシート文脈 | `people-profiles.json` の `related_sheets` にシートID・シート名・説明を設定。返信案生成時に `sheets_manager.py json` で自動取得 |
| Addness KPIシート | `【アドネス全体】数値管理シート`（ID: `1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA`）。タブ: 元データ / スキルプラス（日別）/ スキルプラス（月別）。`csv_sheet_sync.py` がCSV同期→日別月別構築→KPIキャッシュ生成を連鎖実行。詳細は `Project/数値管理自動化.md` を参照。kohara アカウントで読み書き |
| KPIデータ開示制御 | 事業KPI（売上・広告費・ROAS等）は内部メンバーのみ開示。外部パートナー・未登録者には `fetch_addness_kpi()` のデータ注入をスキップ。ただしプロファイルの `related_sheets` に登録されたシートデータは外部にも開示可 |
| タスク失敗通知 | Orchestratorのタスクが失敗するとLINE通知（2時間レート制限）。health_check/oauth_health_checkは除外 |
| 自動復旧（health_check） | local_agent停止検知→launchctl自動再起動→LINE報告。Q&Aモニター4時間以上停止→local_agent再起動。メール通知失敗→5秒後に1回リトライ |

### MacBook を閉じてもスリープしない（クラムシェルモード）

**MacBook 単体（ケーブル・外付けなし）では、蓋を閉じてもスリープしない設定は Apple の仕様で提供されていない。** 蓋を閉じてスリープしないようにできるのは、外付けディスプレイ＋キーボード・マウス＋電源を使う**クラムシェルモード**のみ。

手元の MacBook で「蓋を閉じたまま電源オンで動かし続けたい」場合は、**クラムシェルモード**を使う。ソフトの設定は不要で、以下を接続してから蓋を閉じるだけ。

#### 準備するもの

| 必須 | 内容 |
|------|------|
| ✅ | 電源アダプタ（充電ケーブル） |
| ✅ | 外部ディスプレイ（HDMI / USB-C / Thunderbolt のどれかで接続） |
| ✅ | 外部キーボード（Bluetooth または USB） |
| ✅ | 外部マウス または トラックパッド（Bluetooth または USB） |

#### やること（手順）

1. **MacBook の蓋は開けたまま**、以下をすべて接続する。
   - 電源アダプタを接続する
   - 外部ディスプレイのケーブルを接続する（画面が映ることを確認）
   - 外部キーボードを接続（またはペアリング）する
   - 外部マウス（またはトラックパッド）を接続（またはペアリング）する
2. 外部ディスプレイにウィンドウが表示されていることを確認する。
3. **そのまま蓋を閉じる。**
4. 外部キーボードで操作するか、マウスを動かす → 外部ディスプレイに表示が出ていればクラムシェルモードになっている。

※ 初回だけ「蓋を開けた状態で」上記を接続してから閉じると確実。2回目以降は、接続済みの状態で蓋を閉じるだけでよい。

#### 注意

- 蓋を閉じたまま長時間使うと通気が悪くなり発熱しやすい。MacBook の下にスタンドを置くなど、底面にすき間をあけて排熱するとよい。
- 「ディスプレイがオフのときにMacを自動的にスリープさせない」だけでは、**蓋を閉じたときのスリープは防げない**（蓋閉じ＝ディスプレイオフとみなされるため）。クラムシェルは「電源＋外付けディスプレイ＋外付けキーボード・マウス」の3つが必須。

---

## Mac Mini エージェント構成

### 稼働中サービス

| LaunchAgent | 役割 | ポート |
|------------|------|--------|
| `com.linebot.localagent` | LINE Bot ポーリング・返信案生成 | — |
| `com.addness.agent-orchestrator` | タスクスケジューラ・修復エージェント・git同期 | 8500 |
| `com.prevent.sleep` | Macスリープ防止（caffeinate） | — |

### Orchestratorスケジュール（業務カレンダー）

#### タスク重さの目安

| 重さ | 意味 | 目安時間 | API呼び出し |
|------|------|---------|------------|
| 🟢 軽い | ローカル処理のみ、すぐ終わる | ~30秒 | なし or 1回 |
| 🟡 中くらい | API数回呼ぶ、少し時間かかる | 30秒〜2分 | 2〜5回 |
| 🔴 重い | API大量呼び出し、時間かかる | 2〜5分 | 5回以上 |

#### 毎日のスケジュール

| 時刻 | タスク | 重さ | やること | LINE通知 |
|------|--------|------|---------|---------|
| 03:00 | `log_rotate` | 🟢 | ログ圧縮（50MB超→gz、30日超削除） | なし |
| 06:30 | `sheets_sync` | 🔴 | Googleスプレッドシート全同期→KPIキャッシュ再生成 | ✅ あり |
| 08:00 | `addness_fetch` ※3日ごと | 🟡 | Addnessゴールツリー取得 | ✅ あり |
| 08:10 | `ai_news` | 🟡 | Web検索でAI関連ニュース収集 | なし |
| 08:30 | `daily_addness_digest` | 🟡 | ゴール進捗+今日の予定まとめ | ✅ あり |
| 09:00 | `addness_goal_check` | 🟢 | やることリスト更新 | ✅ あり |
| 09:10 | `oauth_health_check` | 🟢 | Google認証トークン確認 | エラー時のみ |
| 3h毎 :00 | `mail_inbox_personal` | 🟡 | 個人メール確認・分類 | 返信待ちあれば |
| 3h毎 :05 | `mail_inbox_kohara` | 🟡 | koharaメール確認・分類 | 返信待ちあれば |
| 12:00 | `kpi_daily_import` | 🟡 | CSVからスプレッドシートへKPI取込 | ✅ あり |
| 21:00 | `daily_report` | 🟢 | 日次タスク集計 | ✅ あり |
| 21:10 | `daily_group_digest` | 🟡 | グループLINE未読ダイジェスト | ✅ あり |
| 22:00 | `kpi_nightly_cache` | 🟢 | KPIキャッシュ再生成 | なし |

#### 常時動いているもの（バックグラウンド）

| 間隔 | タスク | 重さ | やること |
|------|--------|------|---------|
| 5分ごと | `health_check` | 🟢 | 死活監視・自動復旧（停止検知→再起動→LINE通知） |
| 5分ごと | `git_pull_sync` | 🟢 | GitHubからpull→rsyncデプロイ→サービス再起動 |
| 30分ごと | `render_health_check` | 🟢 | Renderサーバー死活監視（ダウン時LINE通知） |
| 30分ごと | `repair_check` | 🟢 | ログからエラー検知→修復提案 |

#### 週次タスク

| 曜日 | 時刻 | タスク | 重さ | やること | LINE通知 |
|------|------|--------|------|---------|---------|
| 月曜 | 09:00 | `weekly_idea_proposal` | 🟢 | バックログからP0/P1を1件提案 | ✅ あり |
| 月曜 | 09:30 | `weekly_stats` | 🟡 | 週次サマリー（成功率・Q&A件数・Addness鮮度） | ✅ あり |
| 水曜 | 10:00 | `weekly_content_suggestions` | 🟡 | AIニュースからコンテンツ更新提案 | ✅ あり |
| 日曜 | 10:00 | `weekly_profile_learning` | 🔴 | グループ会話分析→profiles.json書き込み + 返信スタイルルール抽出→style_rules.json + comm_profile自動更新 | ✅ あり |

#### 1日のタイムライン

```
 3:00 ┃🟢 ログ圧縮
 6:30 ┃🔴 データ準備 ━━━━━━━━━━━━ (重い・最大2分) 📱
 8:00 ┃🟡 Addnessゴール取得 (3日ごと) 📱
 8:10 ┃🟡 AIニュース収集
 8:30 ┃🟡 朝のブリーフィング 📱
 9:00 ┃🟢 ゴール整理 📱  ＋[月] アイデア提案 📱
 9:10 ┃🟢 Google認証チェック
 9:30 ┃🟡 [月] 週次レポート 📱
10:00 ┃🟡 [水] コンテンツ提案 📱 / 🔴 [日] プロファイル学習 📱
      ┃  ── ここから空き時間 ──
12:00 ┃🟡 KPIデータ投入
      ┃  ── 午後は空き（メール確認が3時間ごとに入るだけ）──
21:00 ┃🟢 日次レポート 📱
21:10 ┃🟡 グループLINEダイジェスト 📱
22:00 ┃🟢 KPIキャッシュ再生成

 ＋ 常時: 死活監視(5分) / GitHub同期(5分) / Render監視(30分) / エラー検知(30分)
 ＋ 3時間ごと: メール確認 x2（:00 個人 / :05 kohara）
```

#### 空き時間（新タスクを入れやすい時間帯）

| 時間帯 | 空き具合 | 備考 |
|--------|---------|------|
| 3:00〜6:00 | ⬜⬜⬜ 完全に空き | 深夜。重いタスクも影響なし |
| 7:00〜8:00 | ⬜⬜⬜ 空き | データ準備の後、朝タスク前 |
| 10:00〜12:00 | ⬜⬜ ほぼ空き | 水曜・日曜は週次タスクあり |
| 12:30〜21:00 | ⬜⬜⬜ 大きく空き | メール確認のみ。新タスクに最適 |
| 22:30〜3:00 | ⬜⬜⬜ 完全に空き | 深夜帯 |

**新タスク配置のルール:**
1. 🔴重いタスク → 前後5分空ける
2. 🟡中くらい → 前後3分空ける
3. 🟢軽い → 連続OK
4. 月曜 9:00〜10:00 は週次集中 → 避ける
5. 3時間ごとの :00 と :05 はメール確認 → :10 以降に配置

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
| `/tasks/<id>/start` | POST | タスク処理開始（早い者勝ち: 処理中なら409） |
| `/tasks/<id>/complete` | POST | タスク完了報告→LINE通知 |
| `/qa/new` | POST | 新着Q&A受け取り・AI回答生成 |

### コード同期アーキテクチャ

```
MacBook (どこからでも)
  │
  ├── コミット → post-commit フック → git push origin main  [自動]
  │                                 → ~/Library/LineBot/ にコード+データ同期 [自動]
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
- [x] notification_ids保存堅牢化（`push_message_with_http_info`の`sent_messages`が空の場合に`raw_data`パースでフォールバック。全5箇所の通知ID保存を`_extract_sent_message_id()`に統一。失敗時に警告ログ出力）
- [x] 返信先グループフォールバック改善（引用返信で`notification_ids`特定失敗時、`_find_pending_by_quote_context()`で準備完了のpending1件なら安全に使用。複数件は警告付きで最新選択）
- [x] handle_approve_mention先頭4文字衝突修正（LINEメッセージIDが連番のため複数pendingで先頭4文字が衝突→生成中のメッセージを誤選択する問題を修正。reply_suggestion準備完了のものを優先選択するよう変更）
- [x] フィードバック保存エラーハンドリング（`save_feedback_example`にtry/except追加。Mac Miniでパス不正時もタスクが「タスクエラー」にならない）
- [x] plist環境変数自動設定（`ensure_plist_path`がplist再生成時に`config.json`から`ANTHROPIC_API_KEY`/`AGENT_TOKEN`/`LINE_BOT_SERVER_URL`を読み取って埋め込み）
- [x] LINE→ゴール実行エンジン（Coordinator）接続完了（app.pyのexecute_goalツール定義改善→調査・リサーチ系を確実にルーティング。Render環境変数にANTHROPIC_API_KEY追加。E2Eフロー: LINE→Render→task_queue→local_agent→coordinator→LINE通知）
- [x] MacBook LaunchAgent ~/Library/LineBot/ デプロイ対応（TCC制限により~/Desktopをlaunchdから直接読めないため、コード+データをコピー配置。post-commitフックで自動同期）
- [x] 2台のPC間のタスク取り合い防止（MacBookとMac Miniが同じタスクを二重処理しないよう、start_taskで早い者勝ち方式を実装。処理中タスクには409を返す。X-Agent-IDヘッダーでマシン識別）
- [x] タスク担当をMac Miniに一本化（MacBookの`config.json`で`task_polling: false`に設定。LINEからのタスクはMac Miniだけが処理する。MacBookはCursorからの直接操作専用）
- [x] LP構成案（generate_lp_draft）・動画台本（generate_video_script）ツール削除（不要）
- [x] 情報開示ルール（相手カテゴリ別）: 甲原のみ→全情報OK / 内部メンバー→事業数値・進捗OK、予定・プライベートNG / 外部→一般知識のみ。返信案生成プロンプトに自動注入
- [x] 曖昧な指示へのヒヤリング: 「広告どう？」等の抽象質問には選択肢を提示して聞き返す
- [x] 深掘り質問の制限: データ取得系は即実行、確認は最大1回に制限（質問より行動を優先）
- [x] 番号選択バグ修正: AI秘書が提示した番号リストに「2」「3」で回答するとメッセージ送信コマンドと誤認されていた問題を修正（メンション/Q&A文脈のみコマンド扱い）
- [x] ai_news Anthropic API切替: OpenAI→Anthropic（claude-haiku-4-5）、Slack送信はSLACK_AI_TEAM_WEBHOOK_URL環境変数にフォールバック
- [x] Claude Code自律モード統合（Phase 8）: 返信案生成・タスク実行でClaude Code CLIを優先使用。プロファイル自動検索・スクリプト実行・Web検索が可能に。失敗時は既存API/Coordinatorにフォールバック
- [x] Claude Code認証分離: `~/.claude-secretary/`（甲原アカウント koa800sea.nifs@gmail.com MAX）で日向エージェント（`~/.claude/`）と完全分離
- [x] Claude Code bypassPermissions設定: Bash/WebSearch/Read等の全ツール解放。破壊的操作（rm/sudo/kill/force-push等）のみask制限
- [x] Mac Mini _repo シンボリックリンク整備: `credentials/` `data/` `config/` を `~/agents/System/` にリンク。Claude Codeからsheets_manager.py等が正常動作
- [x] 人名ハルシネーション防止: 返信案プロンプトに社内メンバー一覧を注入 + 人名ルール（profiles.jsonに存在する正確な名前のみ使用）を追加

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
