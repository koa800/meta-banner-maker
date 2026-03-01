# Orchestrator スケジュール・設定

## スケジュール一覧（定常通知はすべてLINEのみ）

### 朝の流れ
- 06:30: sheets_sync（データ準備）
- 08:10: ai_news
- 08:25: oauth_health_check（Google + Claude Code OAuth 検査・自動リフレッシュ）
- 08:30: daily_addness_digest（朝ブリーフィング + カレンダー）
- 08:40: daily_report_input（Chrome MCP。max_turns=40, timeout=15分）
- 09:00: addness_goal_check
- 09:20: daily_report_verify（日報データ検証）

### 日中
- 平日 10:00/14:00/17:00: secretary_proactive_work（秘書自律ワーク）
- 平日 12:00/19:00: daily_report_reminder（チームメンバー日報未記入リマインド）
- 11:30: looker_csv_download（Chrome MCP。前々日分。max_turns=25, timeout=8分）
- 12:00: kpi_daily_import（CSV → スプレッドシート取り込み）
- 3時間ごと: mail_inbox_personal + mail_inbox_kohara（:00/:05）

### 夜
- 21:00: daily_report / 21:10: daily_group_digest / 22:00: kpi_nightly_cache

### 週次
- 月曜 9:00: weekly_idea_proposal / 9:30: weekly_stats
- 水曜 10:00: weekly_content_suggestions
- 金曜 20:00: os_sync_session（秘書→甲原のOSすり合わせ）
- 日曜 10:00: weekly_profile_learning / 10:30: weekly_hinata_memory / 11:00: video_knowledge_review

### 常時
- 5分ごと: health_check + git_pull_sync
- 15秒ごと: slack_dispatch + slack_hinata_auto_reply
- 30分ごと: repair_check + render_health_check + video_learning_reminder

## Looker Studio / 日報

- **CSV保存先**: `~/Desktop/Looker Studio CSV/`（前々日分）。**日報の対象日は前日**
- **日報入力先**: 報告シート `16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk`「日報」タブ
- **詳細手順**: `Project/定常業務.md` 参照

## Renderデータ永続化

- `DATA_DIR=/data` + Render永続ディスク（pending/actions/tasks/sent_group_messages/qa_feedback の各JSON）
