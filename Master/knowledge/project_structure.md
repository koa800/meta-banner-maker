# プロジェクト構成・アーキテクチャ

## ディレクトリ構成

- `System/line_bot/` → Render (Flask) サーバー。**Gitサブモジュール**。デプロイは `cd System/line_bot && git push origin main`
- `System/line_bot_local/` → PC常駐エージェント（ソース）
- `Master/people/profiles.json` → 58名のプロファイル（comm_profile含む）
- `Master/learning/reply_feedback.json` → 返信修正フィードバック（correction/approval）
- `Master/learning/style_rules.json` → 返信スタイルルール（weekly_profile_learningで自動生成）
- `Project/AI秘書作成.md` → AI秘書システムのメインドキュメント

## 積み上がる学習（Phase 7, 2026-02-25 実装完了）

| 機能 | タイミング | 保存先 | 注入先 |
|------|----------|--------|--------|
| 人ごとの会話記憶 | 返信案生成のたび | `contact_state.json`（1人20件） | 返信プロンプトに直近5件 |
| Q&A回答スタイル学習 | Q&A修正承認のたび | `qa_feedback.json`（Render永続ディスク, 30件） | Q&A生成プロンプトに直近5件 |
| 返信スタイル自動学習 | 日曜10:00 | `Master/learning/style_rules.json` | 全返信プロンプト（highconfidence） |
| comm_profile自動更新 | 日曜10:00 | `profiles.json` のcomm_profile | 返信プロンプト |

- `weekly_profile_learning` は3フェーズ構成: ①グループ会話分析 ②style_rules生成 ③comm_profile更新
- ②③はreply_feedbackのcorrectionが3件以上必要（不足時は正しくスキップ）
- LINE通知に更新者名・スタイル・関心トピックを詳細表示するよう改善済み

## ゴール実行エンジン（AI秘書 v2）（2026-02-25 Phase 3 完了）

- **思想**: AI秘書は「全部やる人」ではなく「正しい相手に正しく頼む人」
- **フロー**: LINE → app.py(execute_goal) → task_queue → local_agent.py → coordinator.py → LINE通知
- **ツール追加**: tool_registry.json に1件追加するだけ（コード変更不要）
- **未接続**: 画像生成（Lubert）/ 動画生成（動画AI未設定）
- **画像学習パイプライン**: 画像送信+「覚えて」→Claude Vision分析→構造化知識→承認→保存

## 行動ルール（OS）の共有構造

- **Single Source of Truth**: `Master/learning/execution_rules.json`
- **秘書（Render）**: 起動時に自動同期。**秘書（local_agent）/日向**: `build_execution_rules_section()` で動的読み込み
- **確認チャンネル**: 秘書=LINE / 日向=Slack / Claude Code=Claude Code上
