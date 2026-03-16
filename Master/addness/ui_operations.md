# Addness 操作ガイド

最終更新: 2026-03-17

## 情報ラベル

- 所有元: internal
- 開示レベル: task-limited
- 承認必須: conditional
- 共有先: 僕 / 上司 / 並列 / 直下

**UI は頻繁に変わる前提で扱う。UI手順は補助であり、正本は API / activity log / server action に置く。**

## 操作方針

優先順位:

1. 読み取りは API を使う
2. 書き込みは公開 API があればそれを使う
3. 公開 API がなければ goal ページの Next.js server action を再生する
4. UI クリックは server action や endpoint を見つけるための fallback として使う

現時点の Codex / 秘書向け操作入口:

- `System/hinata/addness_cli.py`
  - `search-goals`
  - `get-goal`
  - `create-goal`
  - `update-goal-title`
  - `update-goal-status`
  - `update-goal-due-date`
  - `update-goal-description`
  - `list-comments`
  - `reparent-goal`
  - `post-comment`
  - `resolve-comment`
  - `delete-comment`
  - `archive-goal`
  - `delete-goal`
  - `list-ai-threads`
  - `get-ai-messages`
  - `start-ai-session`
  - `send-ai-message`
  - `consult`
  - `smoke-test`
  - `current-member`
  - `member-activity`
  - `activity-summary`
- `System/line_bot_local/tool_registry.json`
  - 秘書向けの操作ツールは `addness_ops`

## 行動ログベースの優先操作

`activity-logs/by-member` で 甲原海人 の直近500件を集計した current の優先操作は次:

- `objective.created`
- `objective.title_updated`
- `objective.status_changed`
- `ai.session_started`
- `ai.message_sent`
- `comment.resolved`
- `objective.deleted`
- `comment.created`
- `objective.due_date_changed`
- `objective.relation_changed`
- `objective.archived`

ガードレール:

- `deleted` 系は不可逆なので自動化の既定対象にしない
- `ai.*` は Addness 側コストが乗るので明示指示がある時だけ使う
- `delete_goal` は `confirm=true` / `--yes` に加えて `expected_title` / `--expected-title` で対象一致を確認する
- `delete_goal` は `テスト` 配下以外を既定で拒否する。必要時だけ `allow_non_test_goal` / `--allow-non-test-goal` を付ける
- `delete_comment` は `confirm=true` / `--yes` なしでは実行しない
- `relation_changed` `title_updated` `due_date_changed` `status_changed` は CLI / 秘書側で実装済み

## 定期運用

- 監査ログ:
  - `System/data/addness_audit_log.jsonl`
  - write 系操作の `who / when / goal / details` を追記する
- 行動ログサマリ:
  - `System/data/addness_activity_summary_latest.json`
  - `activity-summary --save-report` の latest を保持する
- スモークテスト:
  - `System/data/addness_smoke_test_latest.json`
  - `smoke-test` が `テスト` 配下で `作成 -> 更新 -> コメント -> AI -> アーカイブ -> 削除` を日次で検証する
- Mac Mini orchestrator:
  - `addness_smoke_test` を毎日 06:45
  - `addness_activity_watch` を毎日 08:55

## 主要 API / endpoint

- 現在メンバー:
  - `GET /api/v1/team/organizations/{organization_id}/current_member`
- 個人行動ログ:
  - `GET /api/v1/team/organizations/{organization_id}/activity-logs/by-member?member_id={member_id}&limit={n}&offset={n}`
- ゴール詳細:
  - `GET https://vt.api.addness.com/api/v2/objectives/{goal_id}`
- 子ゴール一覧:
  - `GET https://vt.api.addness.com/api/v2/objectives/{goal_id}/children?limit=100&offset=0`
- ゴール作成:
  - `POST https://vt.api.addness.com/api/v2/objectives`
  - body 例:
    - `{"organizationId":"{org_id}","parentObjectiveId":"{parent_goal_id}","title":"テスト","orderNo":1}`
- ゴール更新:
  - `PATCH https://vt.api.addness.com/api/v2/objectives/{goal_id}`
  - title 変更:
    - `{"title":"新しいタイトル"}`
  - 完了 / 未完了:
    - `{"completedAt":"2026-03-11T12:41:32.887Z"}`
    - `{"completedAt":null}`
  - 期日設定:
    - `{"dueDate":"2026-03-31T00:00:00Z"}`
  - 運用定義として `期日を消す` は扱わない。不要になったらゴールごと削除する
- 完了の基準:
  - `PATCH https://vt.api.addness.com/api/v1/team/objectives/{goal_id}`
  - body:
    - `{"description":"完了の基準 API テスト"}`
  - **current では「完了の基準」 = objective.description**
- ゴールアーカイブ:
  - `POST https://vt.api.addness.com/api/v2/objectives/archive`
  - body:
    - `{"objectiveIds":["{goal_id}"]}`
- ゴール削除:
  - `DELETE https://vt.api.addness.com/api/v2/objectives/delete`
  - body:
    - `{"objectiveIds":["{goal_id}"]}`
- コメント一覧:
  - `GET https://vt.api.addness.com/api/v2/objectives/{goal_id}/comments?resolved=false&limit=20&offset=0&sort=desc`
- コメント作成:
  - `POST https://vt.api.addness.com/api/v1/team/comments`
  - body:
    - `{"commentableType":"objective","commentableId":"{goal_id}","content":"本文","mentions":[],"files":[]}`
- コメント解決:
  - `PATCH https://vt.api.addness.com/api/v1/team/comments/{comment_id}/resolve`
- コメント削除:
  - `DELETE https://vt.api.addness.com/api/v1/team/comments/{comment_id}`
- ゴール検索:
  - `GET https://vt.api.addness.com/api/v1/team/search?q=...`
- goal 単位の activity history:
  - `GET /api/v1/team/organizations/{organization_id}/activity-logs/objectives/{goal_id}?limit={n}`
- AI thread 一覧:
  - `GET https://vt.api.addness.com/api/v1/team/ai/threads?limit=20&offset=0&objectiveId={goal_id}&threadScope=objective`
- AI thread 取得:
  - `GET https://vt.api.addness.com/api/v1/team/ai/threads/{thread_id}`
- AI thread messages:
  - `GET https://vt.api.addness.com/api/v1/team/ai/threads/{thread_id}/messages?limit=1000`
- AI session 作成:
  - `POST https://vt.api.addness.com/api/v1/team/ai/threads`
  - body 例:
    - `{"title":"新しいチャット","metadata":{"objective_id":"{goal_id}","thread_scope":"objective","thread_origin":"goal_detail","thread_purpose":"brainstorm"}}`
- 運用定義として AI thread 自体の削除は扱わない。必要な時は新しい thread を開始する
- AI message 送信:
  - `POST /api/ai/threads/{thread_id}/chat`
  - FormData 例:
    - `message`
    - `mode=hearing_mode`
    - `model=gemini-3.1-flash-lite-preview`
    - `mentionedObjectiveIds=["{goal_id}"]`
    - `mentionedMemberIds=[]`
    - `mentionedSkillIds=[]`
    - `userLocalTime=2026-03-11T12:46:07.591Z`
    - `timezone=Asia/Tokyo`

## server action の current 注意点

- 親ゴール変更 UI の検索は completed goal を拾わない
  - 実際の検索クエリには `#goal:-completed` が入る
- 親変更は単純な REST update ではなく Next.js server action
  - `POST /goals/{goal_id}`
  - `Accept: text/x-component`
  - `Next-Action`
  - `Next-Router-State-Tree`
  - body 例:
    - `["{goal_id}", {"newParentObjectiveId":"{parent_goal_id}"}]`

## UI を使う時の原則

- まず page load 時の fetch / xhr を観察して endpoint を特定する
- `Activity history` は折りたたみなので、開いてから request を見る
- 一度動いた UI 手順を正本にせず、対応する endpoint / payload を正本に昇格する
- UI だけで完結する手順書は長持ちしないので、同じセッションで API 情報まで残す

## URL構造

| ページ | URL |
|-------|-----|
| ゴール一覧 | `https://www.addness.com/goals` |
| 特定のゴール | `https://www.addness.com/goals/{goal_id}` |
| アクション（サブゴール） | `https://www.addness.com/goals/{action_id}` |

日向のゴール: `https://www.addness.com/goals/2486eec7-95e3-4d5d-8a9f-d1c899c70f40`

## MCP ツール一覧

| ツール | 用途 |
|-------|------|
| `tabs_context_mcp` | 現在のタブ情報を取得（tabId が必要） |
| `tabs_create_mcp` | 新しいタブを作成 |
| `navigate` | URL に遷移 |
| `read_page` | ページの要素を取得 |
| `find` | 要素を探してクリック・入力 |
| `form_input` | フォームに値を入力 |
| `javascript_tool` | JavaScript を実行 |
| `get_page_text` | ページ全文テキスト取得 |

## ゴールページのレイアウト

```
┌──────────────────────────────────────────────────────────────┐
│ パンくず: 『スキルプラス』をス... > 誰が作っても...          │
│                                                              │
│ [P あとN日] [📅 >]              [👤名前] [👤👤+N] [...]     │
│                                                              │
│               ゴールタイトル                                  │
│                                                              │
│ [完了基準パネル（📅 > で展開/折りたたみ）]                     │
│   【完了基準】1. ... 2. ... 3. ... 4. ...                    │
│   【スコープ】...                                            │
│                                                              │
│ ○ 完了済み(N件) ○ アーカイブ(N件) [共有] [📅] [AIと相談]     │
│                                                              │
│ [👤] ゴール名1  [P あとN日] [●N/M] [💬N] [✓] [✏️] [...]     │
│ [👤] ゴール名2  [P あとN日] [●N/M] [💬N] [✓] [✏️] [...]     │
│ ...                                                          │
│                                                              │
│ [@でメンション/CmdかCtrl＋Enterでコメントを送信]              │
│ [+]                                            [🎙️] [➤]     │
└──────────────────────────────────────────────────────────────┘
```

**`●N/M` は KPI の進捗表示で、テキストの「完了の基準」とは別。**

## 主要操作（MCP版）

### ゴールページに遷移する

```
1. tabs_context_mcp でタブ情報を取得
2. navigate で https://www.addness.com/goals/{goal_id} に遷移
3. read_page でページ内容を確認
```

### AIと相談する

```
1. `AIと相談` を開く
2. `新しい会話` を押す
3. 用途を選ぶ
   - `壁打ち` -> `thread_purpose=brainstorm`
   - `完了条件` -> `thread_purpose=completion_criteria`
   - `タスク化` -> `thread_purpose=task_breakdown`
   - `実行` -> `thread_purpose=execution`
4. 初回送信時に `POST /api/v1/team/ai/threads` が走る
5. その後 `POST /api/ai/threads/{thread_id}/chat` に FormData で送る
6. 回答取得は `GET /api/v1/team/ai/threads/{thread_id}/messages?limit=1000` を正本にする
```

- 右側パネルに過去の AI 会話スレッドが表示される
- current の送信ボタンは `aria-label="Send message"`
- current の初期 model は `gemini-3.1-flash-lite-preview`

### コメントを投稿する

ゴール/アクション詳細ページ下部のコメント欄:

```
1. find で「@でメンション」を含むtextareaを探す
2. form_input でコメントを入力
   - 甲原さんへの確認: 先頭に「@甲原海人 」をつける
3. 送信方法（いずれか）:
   a. find で送信ボタン（➤アイコン）を探してクリック
   b. javascript_tool で Meta+Enter を送信:
      document.querySelector('textarea').dispatchEvent(
        new KeyboardEvent('keydown', {key: 'Enter', metaKey: true, bubbles: true})
      )
```

### コメントを読む（返信確認）

```
1. read_page でゴールページ全体を読む
2. コメント欄にある投稿を確認
3. 「甲原海人」の名前が含まれるコメントを探す
4. 前回のサイクルで自分が投稿したコメントへの返信を確認
```

### アクションを新規追加する

```
1. find で「タイトルを」を含むinput要素を探す
2. form_input でアクション名を入力（「〜する」の形）
3. Enter キーで確定
```

### アクションを完了にする

```
1. find で対象アクション行の✓アイコンを探してクリック
```

### 期日を設定する

```
1. find で対象アクション/ゴールの「...」メニューをクリック
2. find で「期日を設定」をクリック
3. form_input で日付を入力（YYYY/MM/DD 形式）
4. find で「保存」ボタンをクリック
```

### ゴール「...」メニュー項目

| メニュー項目 | 操作内容 |
|------------|--------|
| **完了** | ゴールを完了状態にする |
| **Objective付け替え** | 親ゴール（Objective）を変更 |
| **期日を設定** | YYYY/MM/DD形式で期日入力 → 保存 |
| **成果物をアップロード** | ファイルアップロード |
| **KPIを設定する** | KPI追加ダイアログ |
| **繰り返し** | サブメニューあり |
| **関連するゴールを追加** | 関連ゴールのリンク |
| **URLをコピー** | ゴールURLをクリップボードにコピー |
| **ゴールの一括編集** | 複数アクションの一括編集モード |
| **AIエージェントをアサイン** | AIエージェント割り当て |
| **アーカイブ** | ゴールをアーカイブ |
| **削除** | ゴール削除（赤字） |

## アクション詳細ページ

アクション名をクリックすると詳細ページに遷移（URLは `/goals/{action_id}`）。

構成:
- パンくず（スキルプラス > 親ゴール > アクション名）
- アクションタイトル
- サブアクション追加フィールド
- コメント欄
- Activity history

## 左サイドバー

| アイコン | 機能 |
|---------|------|
| ロゴ | ホーム |
| ◎ ゴール | ゴール一覧 |
| 🔔 通知 | 通知一覧 |
| ✉️ 実行 | 実行一覧 |
| 👥 メンバー | メンバー管理 |
| ❓ ヘルプ | ヘルプ |

## 操作のコツ

1. **MCP の `find` は柔軟** — テキストやプレースホルダーで要素を特定できる
2. **`read_page` で状態を確認してから操作** — いきなりクリックせず、まずページの状態を把握する
3. **SPA なのでページ遷移後は少し待つ** — `navigate` 後に `read_page` で内容確認
4. **座標クリックは避ける** — `find` でテキストやセレクターで要素を特定するのが安全
5. **コメント送信は2つの方法** — ➤ボタンクリック or Meta+Enter（javascript_tool）
