# Orchestrator スケジュール・設定

## スケジュール一覧（定常通知はすべてLINEのみ）

### 朝の流れ
- 06:30: sheets_sync（データ準備）
- 2時間ごと: cdp_sync（CDP同期: データソース→マスタ + 経路別タブ→集客データ。変更時LINE通知）
- 07:00: looker_session_keepalive（CDP でLooker Studioを開いてGoogleセッション維持）
- 3日ごと 08:00: addness_fetch（Addnessゴールツリー取得）
- 08:10: ai_news
- 月曜 08:20: anthropic_credit_check（Anthropic APIクレジット残高チェック → 不足時LINE通知）
- 08:25: oauth_health_check（Google + Gmail personal/kohara + Claude Code OAuth 検査・自動リフレッシュ）
- 08:30: daily_addness_digest（朝ブリーフィング + カレンダー）
- 08:40: daily_report_input（Chrome MCP。max_turns=40, timeout=15分）
- 09:00: addness_goal_check
- 09:20: daily_report_verify（日報データ検証）

### 日中
- 30分ごと: secretary_goal_progress（秘書ゴール進行モード。空き時間判定あり。旧secretary_proactive_workを置き換え）
- 平日 12:00/19:00: daily_report_reminder（チームメンバー日報未記入リマインド）
- 11:30: looker_csv_download（Chrome MCP。前々日分。max_turns=25, timeout=8分）
- 12:00: kpi_daily_import（CSV → スプレッドシート取り込み）
- 12:05: kpi_anomaly_check（KPI異常検知 → 異常時のみLINE通知。媒体ドリルダウン+仮説生成）
- 3時間ごと: mail_inbox_personal + mail_inbox_kohara（:00/:05。kohara実行時にDS.INSIGHTメール自動転送チェックも実施。LINE通知は返信待ちありでも12時間クールダウン）

### 夜
- 21:10: daily_group_digest（グループ名ベースで、会話内容・秘書メモ・見るべき点を要約） / 22:00: kpi_nightly_cache

### 週次
- 月曜 9:00: weekly_idea_proposal / 9:30: weekly_stats
- 水曜 10:00: weekly_content_suggestions
- 金曜 15:00: meeting_report（経営会議資料自動作成。Chrome MCP。max_turns=40, timeout=15分）
- 金曜 20:00: os_sync_session（秘書→甲原のOSすり合わせ）
- 日曜 10:00: weekly_profile_learning / ~~10:30: weekly_hinata_memory~~（日向停止中） / 11:00: video_knowledge_review（動画知識ライフサイクルレビュー） / 11:30: ds_insight_biweekly_report（隔週。DS.INSIGHTデータ取得→レポート→LINE通知）

### 月次
- 毎月3日 09:30: monthly_invoice_submission（請求書作成・提出。INVOY→承認→フォーム→Drive）

### 深夜
- 03:00: log_rotate（ログ圧縮）

### 常時
- 5分ごと: health_check + git_pull_sync（学習データ自動push付き）
- ~~15秒ごと: slack_dispatch + slack_hinata_auto_reply~~（2026-03-06 日向一時停止。スキル整備後に再開）
- 30分ごと: ~~repair_check~~（2026-03-02無効化） + render_health_check + video_learning_reminder（承認待ち動画知識リマインド）

## Looker Studio / 日報

- **CSV保存先**: `~/Desktop/Looker Studio CSV/`（前々日分）。**日報の対象日は前日**
- **日報入力先**: 報告シート `16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk`「日報」タブ
- **Googleログイン切れ時**: 自動ログイン（koa800sea.nifs → kohara.kaito の順で試行。2FAはLINE通知→iPhone承認）
- **セッション維持**: 07:00に毎日CDP経由でLooker Studioを開いてセッションリフレッシュ
- **認証情報**: `System/credentials/kohara_google.txt`（.gitignore、Mac Miniには scp で配置）
- **詳細手順**: `Master/knowledge/定常業務.md` 参照

## API → Claude Code CLI 移行（2026-03-02）

非リアルタイムのバッチ/スケジュールタスクはAnthropic API直接呼び出しからClaude Code CLI（サブスク課金）に移行済み。

| タスク | 移行前 | 移行後 |
|--------|--------|--------|
| weekly_bottleneck | Anthropic API (haiku) | CLI (sonnet, max_turns=3) |
| weekly_content_suggestions | Anthropic API (haiku) | CLI (sonnet, max_turns=3) |
| daily_group_digest | Anthropic API (haiku) | CLI (sonnet, max_turns=3) |
| weekly_hinata_memory | Anthropic API (sonnet) | CLI (sonnet, max_turns=3, JSON出力マーカー) |
| os_sync_session | Anthropic API (sonnet) | CLI (sonnet, max_turns=3) |
| ai_news要約 | REST API (haiku) | CLI (sonnet, max_turns=3) |
| sns_analyzer分析 | REST API (sonnet) | CLI (sonnet, max_turns=3) |
| repair_check | Anthropic API | **無効化**（手動`claude -p`で代替） |

**APIのまま残すもの**: Render(app.py), local_agent, handler_runner, qa_handler, content_analyzer, generate_comm_profiles, addness_people_profiler, Slack即時応答, anthropic_credit_check, weekly_profile_learning, who_to_ask

## Renderデータ永続化

- `DATA_DIR=/data` + Render永続ディスク（pending/actions/tasks/sent_group_messages/qa_feedback の各JSON）
