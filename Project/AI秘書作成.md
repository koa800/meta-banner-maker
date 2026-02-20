# AI秘書作成

## 基本情報

| 項目 | 内容 |
|------|------|
| プロジェクト名 | AI秘書作成 |
| 開始日 | 2026年2月18日 |
| 最終更新 | 2026年2月21日（Mac Mini Orchestratorデプロイ・LINE通知切り替え完了） |
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
                               └──────────────────────────────┘
                                              │
                                   ポーリング │ (10秒間隔)
                                              ▼
                               ┌──────────────────────────────┐
                               │  PC常駐エージェント (Mac)       │
                               │  ~/Library/LineBot/local_agent.py │
                               │  - Claude Sonnet で返信案生成  │
                               │  - フィードバック学習          │
                               │  - people-profiles.json参照   │
                               └──────────────────────────────┘
                                              │
                               launchd常駐    │ データ参照
                                              ▼
                               ┌──────────────────────────────┐
                               │  Master/ (知識ベース)          │
                               │  - people-profiles.json (54名) │
                               │  - IDENTITY.md (言語スタイル)   │
                               │  - SELF_PROFILE.md (自己像)    │
                               │  - reply_feedback.json (学習)  │
                               └──────────────────────────────┘
```

---

## 実装済み機能一覧

### Phase 1: メンション検知・返信案生成（完了）
1. **メンション検知**: グループ内で特定の名前を検知（TARGET_NAMES）
2. **AI返信案生成**: Claude Sonnet 4.6 で返信文を自動生成
3. **承認ワークフロー**: 秘書グループで `1`（承認）/ `2 [修正]`（編集）/ `❌`（キャンセル）
4. **即時通知**: メンション検知後すぐに「⏳ 生成中」を通知、生成完了後に返信案を更新

### Phase 2: 自然言語タスク実行（完了）
5. **Googleカレンダー連携**: 「明日14時に会議入れて」で予定追加
6. **PC委譲タスク**: 日報入力などの複雑タスクをCursorに転送

### Phase 3: PC常駐エージェント（完了）
7. **launchd常駐**: `~/Library/LineBot/local_agent.py` をlaunchdで自動起動
8. **Desktop TCC回避**: macOS TCC制限のため `~/Library/LineBot/` を起点とし、Desktop配下はキャッシュ経由でアクセス
9. **デプロイ完了通知**: Render起動時にLINEへ通知（gunicorn multi-worker対応・重複防止）

### Phase 4: 人物プロファイル × フィードバック学習（完了）
10. **per-personプロファイル**: 54名の `comm_profile`（返信スタイル・挨拶・文脈）を自動生成・参照
11. **フィードバックループ**:
    - `fb [内容]` → スタイルノート（全返信に適用）
    - `2 [修正]` → 修正例として自動学習（AI案と異なる場合のみ）
    - 学習データは `reply_feedback.json` に蓄積、次回返信案のプロンプトに注入
12. **メモコマンド**: `メモ [人名]: [内容]` → その人のプロファイルに文脈メモを追記
13. **IDENTITY.md**: 甲原海人の言語スタイル定義（口癖・トーン・関係性別ルール）
14. **SELF_PROFILE.md**: 甲原海人のコアプロファイル（価値観・判断軸・哲学）記入済み

### Phase 5: 高度な返信文脈認識（完了）
15. **引用返信（リプライ）検知**: ボットが送信したメッセージへのLINE引用返信を自動検知し、新しい返信案を生成
16. **会話文脈取り込み**: メンション直前の発言（最大10件）をバッファリングし、Claude プロンプトに「直前の文脈」として注入
17. **重複タスク防止**: 同一 `message_id` の `generate_reply_suggestion` タスクは1件のみキューイング

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
| `2 [修正]` で承認 | 修正例として保存 | その人優先・他も参照（最大5件） |
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
| 「日報入れて」 | 日報入力をCursorに委譲 |

---

## ファイル構成

### クラウド側（Render）
| パス | 説明 |
|------|------|
| `System/line_bot/app.py` | メインアプリ（Webhook・タスクAPI・通知） |
| `System/line_bot/qa_handler.py` | Q&A処理ハンドラ |
| `System/line_bot/requirements.txt` | Python依存関係 |

### ローカル側（PC常駐エージェント）
| パス | 説明 |
|------|------|
| `~/Library/LineBot/local_agent.py` | **実行ファイル**（launchdから起動） |
| `~/Library/LineBot/data/` | キャッシュデータ（TCC回避用） |
| `~/Library/LineBot/logs/agent.log` | 実行ログ |
| `~/Library/LaunchAgents/com.linebot.localagent.plist` | launchd設定 |
| `System/line_bot_local/local_agent.py` | Desktop版（開発・編集用） |
| `System/line_bot_local/sync_data.sh` | Desktop ↔ Library 双方向同期 |

### 知識ベース（Master/）
| パス | 説明 |
|------|------|
| `Master/people-profiles.json` | 54名のプロファイル（comm_profile含む） |
| `Master/people-identities.json` | 人物識別データ |
| `Master/reply_feedback.json` | フィードバック学習データ（修正例・スタイルノート） |
| `Master/self_clone/projects/kohara/1_Core/IDENTITY.md` | 甲原海人の言語スタイル定義 |
| `Master/self_clone/projects/kohara/1_Core/SELF_PROFILE.md` | 甲原海人のコアプロファイル |

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
| Webhook URL | https://line-mention-bot-mmzu.onrender.com/callback |
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
| `LOCAL_AGENT_TOKEN` | PC常駐エージェント認証用 |
| `GOOGLE_CREDENTIALS_JSON` | Google Calendar用サービスアカウント |
| `GOOGLE_CALENDAR_ID` | カレンダーID |
| `PINECONE_API_KEY` | Pinecone API認証（Q&A） |
| `LSTEP_API_TOKEN` | L-step API認証 |
| `LSTEP_ENDPOINT_URL` | L-step エンドポイントURL |
| `DATA_DIR` | データ保存ディレクトリ（`/data` = Render永続ディスク） |

---

## 注意事項・既知の制限

| 項目 | 内容 |
|------|------|
| Render プラン | Starter（$7/月）。Zero Downtime デプロイ・スリープなし |
| Macスリープ対策 | launchd plist に `caffeinate -s` を追加。エージェント起動中はMacスリープ防止 |
| データ永続化 | Render永続ディスク `/data` を使用。`DATA_DIR=/data` 環境変数で設定済み。デプロイ後も状態が消えない |
| macOS TCC | launchd から Desktop は直接アクセス不可。Library 版でキャッシュ経由でアクセス |
| LINE webhook重複 | 同一 message_id のタスクは1件のみキューイング済み |
| Mac Mini TCC制限 | LaunchAgent から `~/Desktop/` は直接アクセス不可。`~/agents/` を作業ディレクトリに使用 |
| Mac Mini rsync | TCC制限でcron rsyncが失敗するため、Desktop MacのGit post-commitフックから rsync を実行 |
| LINE Notify廃止 | LINE Notify は2025年3月終了。Render `/notify` エンドポイント + LINE Messaging API push_message で代替 |

---

## Mac Mini エージェント構成

### 稼働中サービス

| LaunchAgent | 役割 | ポート |
|------------|------|--------|
| `com.linebot.localagent` | LINE Bot ポーリング・返信案生成 | — |
| `com.addness.agent-orchestrator` | タスクスケジューラ・修復エージェント | 8500 |
| `com.prevent.sleep` | Macスリープ防止（caffeinate） | — |

### Orchestrator 通知フロー

```
Mac Mini Orchestrator
  → POST /notify (Bearer AGENT_TOKEN)
    → Render app.py /notify endpoint
      → LINE Messaging API push_message
        → SECRETARY_GROUP_ID（秘書グループ）
```

### 関連ファイル（Mac Mini）

| パス | 説明 |
|------|------|
| `System/mac_mini/agent_orchestrator/` | Orchestratorパッケージ |
| `System/mac_mini/agent_orchestrator/notifier.py` | LINE通知ディスパッチャ（Render経由） |
| `System/mac_mini/agent_orchestrator/config.yaml` | エージェント設定（パス・スケジュール等） |
| `~/agents/sync_agent.sh` | local_agent.py タイムスタンプ同期（Mac Mini上） |
| `.git/hooks/post-commit` | コミット時にDesktopからMac MiniへrsyncするGitフック |

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
- [x] Mac Mini rsync TCC制限対応（Git post-commitフックでDesktop→Mac MiniへrsyncをDesktop側から実行）

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
