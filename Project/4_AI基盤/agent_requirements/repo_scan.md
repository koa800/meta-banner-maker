# リポジトリスキャン結果

> 調査日: 2026-03-07
> 目的: AIエージェント基盤の要件定義に関係する主要ファイルの特定

---

## 1. 業務棚卸し・AI化方針（最重要）

| ファイル | 役割 | 鮮度 |
|---------|------|------|
| `Master/knowledge/業務棚卸し_AI化優先順位.md` | **全106業務の棚卸し + 自動化レベル定義 + 優先順位（Tier 1-4）** | 2026-03-03 |
| `Master/knowledge/秘書の視界マップ.md` | 秘書が見えている/見えていないデータの可視化。ブラインドスポット一覧 | 2026-03-03 |
| `Master/knowledge/環境マップ.md` | MacBook/Mac Mini/Render/GitHub の全体構成図。認証・データフロー | 最新 |

---

## 2. 既存AIエージェント設計・実装（継承候補）

| ファイル | 役割 | ステータス |
|---------|------|----------|
| `Project/4_AI基盤/AI秘書作成.md` | AI秘書の全機能仕様書（Phase 1-12、58機能） | 継続開発中 |
| `Project/4_AI基盤/秘書v2_設計書.md` | 秘書v2（会話型AI秘書）の設計書。LLMルーター・記憶システム・tool_use | v2実装済み |
| `Project/4_AI基盤/日向エージェント.md` | 自律型AIエージェント「日向」の設計書。成長モデル・権限設計 | Phase 1稼働中（一時停止） |
| `Project/4_AI基盤/ゴール実行エンジン設計.md` | Coordinator + profiles.json + tool_registry.json の統一アーキテクチャ | Phase 3実装完了 |
| `Project/4_AI基盤/CDP.md` | 顧客マスターデータ（58列・57,750人）の設計・同期 | 初回同期完了・運用中 |

---

## 3. 業務自動化プロジェクト（対象業務の実装状況）

| ファイル | 対象業務 | ステータス |
|---------|---------|----------|
| `Project/3_業務自動化/数値管理自動化.md` | KPI日次収集・集計・可視化（Looker→CSV→Sheets→キャッシュ） | 完了・運用中 |
| `Project/3_業務自動化/メール自動管理.md` | Gmail自動分類・学習型削除・返信案生成 | 完了 |
| `Project/3_業務自動化/メールマーケティング自動化.md` | CDP→Mailchimp→AIライティング→配信 | 設計完了・着手待ち |
| `Project/3_業務自動化/経営会議資料_自動作成.md` | 毎週金曜の経営会議資料をAI自動生成 | v1完了 |
| `Project/3_業務自動化/LP自動生成_依頼ブリーフ.md` | LP自動生成のテンプレート依頼仕様 | 設計中 |

---

## 4. CS・集客プロジェクト

| ファイル | 対象業務 | ステータス |
|---------|---------|----------|
| `Project/2_CS/質問自動回答プロジェクト.md` | 受講生Q&A自動回答（Pinecone + GPT-4o-mini） | 運用中 |
| `Project/2_CS/スキルプラス_オンボーディング.md` | 受講生オンボーディング設計 | — |
| `Project/2_CS/アクションマップ作成.md` | アクションマップ設計 | — |
| `Project/2_CS/サポートLINE_イベント情報設計.md` | サポートLINEイベント設計 | — |
| `Project/1_集客/口コミ発生プロジェクト.md` | UGC/口コミ施策 | — |
| `Project/1_集客/ターゲット分析ツール作成.md` | ターゲット分析ツール | — |
| `Project/1_集客/DS.INSIGHT定期レポート.md` | DS.INSIGHTレポート自動化 | — |

---

## 5. スキル・ナレッジ（AIの業務知識源）

| ディレクトリ | 内容 | ファイル数 |
|------------|------|----------|
| `Skills/1_広告/` | CR企画・リサーチ・日次確認・制作フロー・思想 | 5 |
| `Skills/2_導線/` | LP制作5STEP・コンセプトメイク・販売導線設計 | 3 |
| `Skills/3_セールス/` | リストマーケティング・セールス | 1 |
| `Skills/4_CS/` | 過去の質問回答・アクションマップFB | 2 |
| `Skills/5_数値・業務/` | 請求書提出・業務情報マップ・スプレッドシート参照 | 3 |
| `Skills/6_システム/` | AIツール・ブラウザ自動操作・設計書作成・SS設計ルール | 4 |
| `Skills/共通/` | ビジネス基礎・ワークフローの考え方・デザイン | 3 |

---

## 6. 実装コード（System/）

| ディレクトリ | 内容 | 主要ファイル |
|------------|------|------------|
| `System/line_bot/` | Render (Flask) サーバー（サブモジュール） | `app.py`, `qa_handler.py` |
| `System/line_bot_local/` | Mac Mini常駐エージェント | `local_agent.py`, `coordinator.py`, `conversation.py`, `llm_router.py`, `memory_manager.py` |
| `System/mac_mini/agent_orchestrator/` | Orchestrator（スケジューラ・15+タスク） | `scheduler.py`, `config.yaml` |
| `System/hinata/` | 日向エージェント | `hinata_agent.py`, `claude_executor.py`, `learning.py` |
| `System/addness_mcp_server/` | Addness MCP サーバー（サブモジュール） | — |
| `System/` (root) | 各種ツールスクリプト | `csv_sheet_sync.py`, `cdp_sync.py`, `mail_manager.py`, `sheets_manager.py`, `kpi_anomaly_detector.py` |

---

## 7. 知識ベース（Master/）

| ディレクトリ | 内容 |
|------------|------|
| `Master/knowledge/` | 環境マップ・定常業務・orchestrator・dev_patterns・mac_mini・accounts・lstep_structure |
| `Master/addness/` | ファネル構造・ゴールツリー・Meta広告分析・UI操作・市場トレンド |
| `Master/people/` | profiles.json（58名のプロファイル） |
| `Master/learning/` | action_log・feedback_log・hinata_memory・insights・execution_rules・style_rules |
| `Master/self_clone/kohara/` | IDENTITY.md・SOUL.md・BRAIN_OS.md・SELF_PROFILE.md・USER.md |
| `Master/sheets/` | スプレッドシートCSVキャッシュ |

---

## 8. 設定・ルール

| ファイル | 役割 |
|---------|------|
| `CLAUDE.md` | プロジェクト専用指示書（ドキュメント更新ルール・構成・技術選定フロー） |
| `~/.claude/CLAUDE.md` | グローバル指示書（言語設定・Cursorルール同期） |
| `~/.claude/projects/.../memory/MEMORY.md` | 自動メモリ（行動ルールOS・ユーザー設定） |
| `Master/learning/execution_rules.json` | 行動ルール（OS）のSingle Source of Truth |
