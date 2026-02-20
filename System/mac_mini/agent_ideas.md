# Mac mini AIエージェント アイデアバックログ

> **使い方**: Mac miniが定期的にここを読んで「次にこれをやりませんか？」と提案する。
> アイデアを思いついたら追加する。完了したものは `[x]` にする。
> 最終更新: 2026-02-21 (P2バナー構成案生成・スケジュール修正)

---

## 優先度の軸：スキルプラス事業ゴール

**KPI**: ROAS ≥100%, 月間1,000ユーザー, CPA ≤2,500円, CVR ≥15%
**直近期限**: 2026/02/28 サブスク+アフィリエイト

---

## 🔴 P0 | インフラ（完了）

- [x] `local_agent.py` をMac miniに移行する（~/agents/line_bot_local/local_agent.py）
- [x] Mac mini Orchestratorが実際に稼働しているか確認・起動（com.addness.agent-orchestrator）
- [x] 環境変数・OAuthトークンをMac miniに移行（AGENT_TOKEN・ANTHROPIC_API_KEY設定済み）
- [x] ヘルスチェック通知がLINEに届いているか確認

---

## 🟠 P1 | ゴール直結・即効（事業KPIに直結）

### 日次報告の自動化
- [x] **毎朝8:30 日次サマリーをLINE送信**: 今日の期限タスク + 期限超過ゴール一覧 + Addness上の自分担当タスク
  - *根拠*: Addness上に期限超過が多数。毎日の見落とし防止

### Q&A自動回答（広告コース）
- [x] **qa_monitor.pyを本番稼働させる**: スタンダードコース・広告コースの質問を自動検知→回答案生成→承認→送信
  - *根拠*: 5-10分/日の削減 + 回答漏れゼロへ。学習体験に直結

### メール自動処理
- [x] **重要メール検知→返信案をLINE通知**: GmailでCV・契約・メディア依頼などを検知したら即通知
  - *根拠*: 3分/日の作業 + 見落とし防止

### 期限管理エージェント
- [x] **毎週月曜9:00 期限超過・今週期限ゴールをLINE通知**: Addnessから自動取得して整理
  - *根拠*: オンボーディング最適化(2/14期限超過)、アップセルシナリオ(2/7期限超過)等が放置されている

---

## 🟡 P2 | 高付加価値エージェント

### 広告パフォーマンス監視
- [ ] **Meta/TikTok/YouTube広告のROAS・CPA日次監視**: 閾値を下回ったらLINE即時アラート
  - *根拠*: ROAS目標400%+達成のためのボトルネック早期発見
- [ ] **広告レポートシートへの自動入力**: Sheetsに毎日の主要KPIを自動転記

### LP・CR制作支援
- [x] **LPコピー自動ドラフト**: 「LP作成: [条件]」でファーストビュー見出し3案+CTA+ベネフィット訴求を生成（local_agent.py `generate_lp_draft`）
  - *根拠*: LP実装が複数期限超過。制作スピードアップが最短経路
- [x] **動画スクリプト自動生成**: 「スクリプト作成: [条件]」でTikTok/YouTube広告台本を自動生成（`generate_video_script`）
- [x] **バナー構成案バリエーション生成**: 10本同時にコンセプト案を出す（`generate_banner_concepts`）

### 報告シート自動入力
- [ ] **日次KPI報告（1分の作業）を自動化**: Addness/広告媒体からデータを取得してシートに記入
  - *根拠*: 毎日1分でも「やらなければならない」タスクの認知負荷を削除

---

## 🟢 P3 | プロアクティブ・中期

### アフィリエイト管理
- [ ] **アフィリエイト登録者数・売上の週次モニタリング通知**（2/28期限）
- [ ] **アフィリエイト用コンテンツ自動整備提案**: 成約率が低いアフィリエイターへの支援コンテンツを自動生成

### 顧客ライフサイクル管理
- [ ] **解約リスクユーザー検知エージェント**: ログイン頻度が下がったユーザーを検知→フォローアップ
- [ ] **ゴール達成率モニタリング**: Addness上で学習が止まっている生徒の早期アラート

### コミュニケーション最適化
- [x] **ミーティング前準備エージェント**: カレンダー参加者をpeople-profiles.jsonでルックアップしカテゴリ付きで朝の通知に表示（`_notify_today_calendar` 強化）
- [x] **フォローアップ提案**: contact_state.jsonに接触記録→週次statsにカテゴリ別閾値(上司30日/横21日/メンバー14日)でLINE通知

### コンテンツ管理
- [ ] **AI学習コンテンツ更新監視**: 競合コンテンツ・最新AI情報を週1でスキャンして更新提案
- [ ] **東北大学研究コラボ進捗リマインダー**（2026/08/31期限）

---

## 🔵 P4 | 長期・実験的

- [ ] **AddnessゴールツリーのSlackへの自動ブリーフィング共有**
- [ ] **TV出演・メディア対応スケジュール管理エージェント**（フジテレビ等）
- [ ] **Vidu動画パイプライン自動化**: クリエイティブ台本→動画生成→確認まで自動
- [ ] **Pinecone Q&A同期の自動化**（週1で全QAをベクトルDB更新）
- [ ] **L-step開封率・反応率週次サマリー**
- [ ] **競合比較エージェント**: スキルプラスvs競合3-5社の価格・訴求の差分を月1でまとめる

---

## 💡 積み残しアイデア（未分類）

- Mac miniが「今週のボトルネック」をAddnessゴールから分析して提案する
- LINEから「次に何すべき？」と聞いたらAddnessゴール+メール+カレンダーを総合して答える
- 報告シートの記入をLINEから音声/テキストでできるようにする
- 生徒の質問傾向をベクトル検索で分析して「よくある質問集」を自動更新する

---

## ✅ 完了

### P0 インフラ
- `local_agent.py` をMac miniに移行（~/agents/line_bot_local/local_agent.py）
- Mac mini Orchestrator起動（com.addness.agent-orchestrator, port 8500）
- 環境変数・OAuthトークンをMac miniに移行（AGENT_TOKEN・ANTHROPIC_API_KEY）
- ヘルスチェック通知がLINEに届いているか確認

### P1 ゴール直結
- 毎朝8:30 Addness日次ダイジェストをLINE送信（`daily_addness_digest`）
- 毎週月曜9:00 未着手P0/P1アイデアをLINEで提案（`weekly_idea_proposal`）
- 重要メール検知→返信待ち件数をLINE通知（scheduler.py `_notify_mail_result`）
- qa_monitor.py 本番稼働（config.json `qa_monitor_enabled: true`）

### リスク対策（2026-02-21）
- **Google OAuth監視**: 毎朝9:00 token.jsonとGoogle API認証チェック、失敗時LINE通知（`oauth_health_check`）
- **同期失敗通知**: sync_from_macbook.shの同期エラー時にLINE通知
- **API使用量警告**: 直近1時間のAPI使用量が90%超でLINE通知（health_check強化）
- **MacBook移行ガイド**: `Project/MacBook移行ガイド.md` 作成（1ヶ月後の機種変更に対応）

### P2/P3 エージェント機能（2026-02-21）
- **calendar_list バグ修正**: `tools.py` でdays=1のとき今日の日付を自動設定
- **日次ダイジェスト+カレンダー**: 朝8:30の通知に今日の予定を追加（参加者プロファイル付き）
- **context_query コマンド**: LINEから「次何？」でAddness+メール+Claudeが優先行動を回答
- **generate_lp_draft コマンド**: 「LP作成: [条件]」でLP構成案・キャッチコピー自動生成
- **calendar_manager.py 参加者表示**: list_eventsで参加者(self以外)をdisplayName表示
- **generate_video_script コマンド**: 「スクリプト作成: [条件]」でTikTok/YouTube広告台本を自動生成
- **calendar tokenハング防止**: tools.pyでtoken未存在時に即座にToolResult(success=False)返却
- **フォローアップ追跡**: local_agent.pyのreply_suggestion後にcontact_state.jsonへ接触時刻記録
- **週次フォローアップ通知**: scheduler.py _check_follow_up_suggestionsでカテゴリ別閾値チェック
- **generate_banner_concepts コマンド**: 「バナー作成: [条件]」でバナー広告コンセプト5案自動生成（ヘッドライン+ビジュアル+CTA）
- **addness_goal_check スケジュール**: Orchestratorで毎朝9時にaddness_to_context実行（定期実行統合完了）

---

## 定期提案スケジュール（Orchestratorに設定）

| タイミング | 内容 |
|-----------|------|
| 毎週月曜 9:00 | このバックログから未着手P0/P1を1件ピックアップして「これをやりませんか？」通知 |
| 毎月1日 | P2以下から優先度を再評価して提案 |
