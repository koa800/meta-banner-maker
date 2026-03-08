# プロジェクト構成・アーキテクチャ

## Master 4層アーキテクチャ

- `Master/前提/` → 用語定義・目的・価値観・判断軸など、AIが考える前に揃えるもの
- `Master/knowledge/` → 事実・観察・過去LP・導線・数値などの知識
- `Master/rules/` → 成功失敗から抽出した再現ルール・NG
- `Master/output/` → 実際に出した成果物と、その結果レビュー

既存運用との対応:

- `self_clone/`, `brains/`, `people/`, `company/` は主に `前提` の詳細層
- `addness/`, `knowledge/`, `sheets/` は主に `knowledge` の詳細層
- `learning/` は `前提` と `rules` を補助する学習層
- `addness/proactive_output/` は `output` の legacy 出力先

## ディレクトリ構成

- `cursor/` root 直下の意味付きフォルダは `Master/` `Project/` `Skills/` `System/` の4本を正本とする
- root 直下の例外は `.git/` `.claude/` `.cursor/` `.vscode/` と制御ファイル (`AGENTS.md`, `CLAUDE.md`, `pyproject.toml`, `.gitignore`, `.gitmodules`) だけ
- root 構成の検知は `python3 System/root_layout_check.py` を使う。逸脱があれば修正してから完了扱いにする

- `System/line_bot/` → Render (Flask) サーバー。**Gitサブモジュール**。デプロイは `cd System/line_bot && git push origin main`
- `System/line_bot_local/` → PC常駐エージェント（ソース）
- `System/quick_translator/` → Chrome拡張（テキスト選択→自動翻訳ポップアップ、Manifest V3）
- `System/clip_translator/` → macOSメニューバー常駐アプリ（Cmd+C→翻訳通知、rumps + launchd自動起動）
- `System/root_layout_check.py` → root 直下の構成逸脱を検知するガードスクリプト
- `Master/前提/用語定義.md` → 甲原さんが使う言葉のローカル正本。Google Sheets `言葉の定義` から同期
- `Master/people/identities.json` → 識別レイヤー（LINE表示名 / Chatwork ID / メール等）
- `Master/people/profiles.json` → legacy運用レイヤー（comm_profile / group_insights を含む厚いプロファイル）
- `Master/people/profiles.md` → `profiles.json` の人間向け表示レイヤー
- `Master/company/people_public.json` → 会社共通で参照する人物情報の正規レイヤー
- `Master/brains/kohara/people_private.json` → 甲原クローン脳だけが持つ私的人物理解
- `System/registries/agent_registry.json` → 人間 / AI / shell / brain の実行主体 registry
- `Master/learning/reply_feedback.json` → 返信修正フィードバック（correction/approval）
- `Master/learning/style_rules.json` → 返信スタイルルール（weekly_profile_learningで自動生成）
- `Master/rules/rules.md` → 成果物運用から増えていく再現ルール・NG の受け皿
- `Master/output/` → 成果物と結果レビューの入口
- `Master/output/経理/領収書/` → Gmail から取得した領収書・請求書の正本置き場
- `Master/self_clone/kohara/USER.md` → 甲原クローンの判断スタンス。再利用可能な業務原理の正本は `Skills/` に置き、ここには「何を重く見るか」だけを残す
- `Project/4_AI基盤/AI秘書作成.md` → AI秘書システムのメインドキュメント
- `Project/4_AI基盤/agent_requirements/` → エージェント要件・設計メモのプロジェクト正本

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

## 日向学習データの同期

- `Master/learning/` 配下の学習データ（action_log.json, feedback_log.json, hinata_memory.md, insights.md）は Mac Mini 上で書き込まれる
- `git_pull_sync.sh` が fetch/reset の**前に**ローカル変更を自動 commit & push することで GitHub と同期
- 同期頻度: 5分ごと（git_pull_sync のスケジュールに統合）
- push 失敗時はログ記録のみで次回リトライ（pull はブロックしない）

## 行動ルール（OS）の共有構造

- **Single Source of Truth**: `Master/learning/execution_rules.json`
- **秘書（Render）**: 起動時に自動同期。**秘書（local_agent）/日向**: `build_execution_rules_section()` で動的読み込み
- **確認チャンネル**: 秘書=LINE / 日向=Slack / Claude Code=Claude Code上
