# AIエージェント基盤 要件定義書 draft_v1

> 作成日: 2026-03-07
> ステータス: draft（人間確認必要）
> Source of Truth: `Master/knowledge/業務棚卸し_AI化優先順位.md`

---

## 1. 目的

甲原海人のPC上のマーケティング業務の多くをAIが代行できる状態を作る。

**ビジョン（ゴール実行エンジン設計.mdより）:**
- 甲原さんが注力すること: クリエイティブ / 意思決定の設計 / オフラインの人間関係
- それ以外は全てシステムが回す

**現状:**
- 全106業務中、75%（79件）がLv.0（手動）
- Lv.3以上（全自動）は13%（14件）のみ
- 秘書v2、ゴール実行エンジン、日向エージェントが個別に存在するが、統一基盤はない

---

## 2. 既存資産の棚卸し（中から外の原則）

### 2.1 既に動いているもの（継承必須）

| システム | 場所 | 状態 | AI化レベル |
|---------|------|------|----------|
| AI秘書（LINE/Chatwork応答） | line_bot + line_bot_local | 運用中 | Lv.2-3 |
| 秘書v2エンジン（会話型） | conversation.py, llm_router.py, memory_manager.py | 有効化済み | Lv.2-3 |
| ゴール実行エンジン（Coordinator） | coordinator.py + profiles.json + tool_registry.json | Phase 3完了 | Lv.2 |
| 日向エージェント | hinata_agent.py + claude_executor.py | Phase 1（一時停止） | Lv.1 |
| Orchestrator（スケジューラ） | agent_orchestrator/ | 15+タスク稼働中 | Lv.3-4 |
| Q&A自動回答 | qa_handler.py + qa_monitor.py + Pinecone | 運用中 | Lv.2 |
| KPIパイプライン | csv_sheet_sync.py + kpi_anomaly_detector.py | 運用中 | Lv.3 |
| CDP同期 | cdp_sync.py | 運用中 | Lv.3 |
| メール自動管理 | mail_manager.py | 運用中 | Lv.2 |
| 経営会議資料自動作成 | meeting_report_v4.py | v1完了 | Lv.2 |
| 日報自動入力 | Orchestrator daily_report_input | 運用中 | Lv.3 |
| KPI異常検知 | kpi_anomaly_detector.py | 運用中 | Lv.3 |
| 行動ルール共有 | execution_rules.json | 運用中 | Lv.4 |

### 2.2 設計済み・未着手

| 機能 | 設計ファイル | ブロッカー |
|------|-----------|----------|
| メールマーケティング自動化 | `Project/3_業務自動化/メールマーケティング自動化.md` | 着手待ち |
| LP自動生成 | `Project/3_業務自動化/LP自動生成_依頼ブリーフ.md` | デザイナーのテンプレート待ち |

### 2.3 Cursor内のエージェント基盤として必要な新規要素

既存資産は **Mac Mini常駐型**（line_bot_local + Orchestrator + hinata）。
今回の目的は **Cursor内で動くAIエージェント基盤** — つまりMacBook上での対話的な業務代行。

既存のMac Mini常駐システムとの関係を明確にする必要がある（→ issues.md #1）。

---

## 3. 対象業務（Source of Truthから抽出）

### 3.1 Tier 1: 最優先（CPA改善 + 毎日の時間創出）

| 業務ID | 業務 | 現レベル | 目標レベル | 既存資産 |
|--------|------|---------|----------|---------|
| B1+B2 | 広告数値の日次確認+パフォーマンス判断 | Lv.0 | Lv.2 | KPIキャッシュ・異常検知あり。CR単位のデータが**未接続** |
| F2+F3 | 日次ゴール進捗確認+期限超過管理 | Lv.1 | Lv.2 | Addness API接続済み。日向が一部カバー（停止中） |
| F5 | Addnessコメント・FB記入 | Lv.1 | Lv.2 | 日向のAddnessコメント機能あり（停止中） |
| B3 | 広告数値レポート作成 | Lv.1 | Lv.3 | weekly_stats・経営会議資料あり |
| C1 | 広告CR企画 | Lv.0 | Lv.1 | Skills/にフレームワークあり。Meta広告分析データあり |
| B5 | 広告リサーチ | Lv.0 | Lv.1 | DPro接続済み。リサーチスキル定義あり |

### 3.2 Tier 2: 個別予約率改善 + 解約率低下

| 業務ID | 業務 | 現レベル | 目標レベル | 既存資産 |
|--------|------|---------|----------|---------|
| D8 | 導線全体の数値分析 | Lv.0 | Lv.2 | CDPあり。ファネル構造定義あり |
| E1/E2 | LINE/メルマガシナリオ設計 | Lv.0 | Lv.1 | Mailchimp設計完了。Lステップ構造定義あり |
| I1 | 受講生Q&A回答 | Lv.2 | Lv.3→Lv.4 | Q&A自動回答稼働中 |
| I6 | 中途解約数値追跡 | Lv.0 | Lv.3 | CDPに解約日カラムあり |
| D1/D2 | LP制作・改善 | Lv.0 | Lv.1 | LP5STEPスキルあり |
| C5 | CR効果検証 | Lv.0 | Lv.2 | KPIデータあり |

### 3.3 Tier 3: 成約率改善 + スケール準備

| 業務ID | 業務 | 現レベル | 目標レベル |
|--------|------|---------|----------|
| G2 | セミナー→成約の導線改善 | Lv.0 | Lv.1 |
| D3 | セミナー導線設計 | Lv.0 | Lv.1 |
| C2 | 動画広告CR制作 | Lv.1 | Lv.2 |
| B7-B14 | 各媒体の入稿・設定変更 | Lv.0 | Lv.2 |
| K3 | メール対応の判断精度向上 | Lv.2 | Lv.3 |

### 3.4 Tier 4: 長期（全体最適 + 意思決定AI化）

| 業務ID | 業務 | 現レベル | 目標レベル |
|--------|------|---------|----------|
| D4/D5 | サブスク/アップセル導線設計 | Lv.0 | Lv.1 |
| L9 | 深い分析（LTV・コホート） | Lv.0 | Lv.2 |
| A1-A3 | 事業P&L・施策優先順位 | Lv.0 | Lv.1 |

### 3.5 既にLv.3-4（維持・改善のみ）

| 業務ID | 業務 | 現レベル |
|--------|------|---------|
| K4 | Slack監視→振り分け | Lv.3 |
| K5 | グループチャットダイジェスト | Lv.3 |
| L1 | 日報数値入力 | Lv.3 |
| L2 | 日報未記入リマインド | Lv.4 |
| L3 | KPI CSV取得→シート反映 | Lv.3 |
| L4 | KPI異常値検知 | Lv.3 |
| L5 | 週次統計レポート | Lv.3 |
| L6 | 日次完了報告 | Lv.3 |
| M4 | 障害対応 | Lv.3 |
| M5-M7 | 死活監視・ログ・OAuth | Lv.4 |

---

## 4. 前提・制約条件

### 4.1 思想（CLAUDE.md + MEMORY.mdから抽出）

| 原則 | 内容 | 具体的制約 |
|------|------|----------|
| 中から外 | 手元の資産から出発。外部は最後 | 新サービス導入前に既存で解決できないか確認必須 |
| 下から上へ | 甲原さんにアクションを求める設計は禁止 | AIが能動的に動く構図 |
| 記録ではなく知識 | JSONに溜めるだけでなく、判断に使える形で蓄積 | マークダウン知識ファイルとして書き出す |
| 0.1%のこだわり | 99.9%が流す細部にこだわる | 「後で直す」禁止 |
| ガードレール | 承認済み範囲内=自律OK / 範囲外=確認 | 金銭・対人送信（秘書G/Slack以外）・不可逆削除は確認必須 |

### 4.2 技術的制約

| 制約 | 詳細 |
|------|------|
| 実行環境 | MacBook（開発・創造）+ Mac Mini（自動化・常駐） |
| デプロイ | git push → post-commitフックで自動push → Mac Miniが5分でpull |
| 認証 | Google OAuth（token.json群）/ Anthropic API / LINE / Slack Webhook |
| LLMモデル | GPT-5.4（デフォルト）/ Claude Opus 4.6 / Claude Sonnet 4.6（フォールバック順） |
| コスト上限 | 月5万円（~$330）まで許容 |
| 秘書認証分離 | `~/.claude-secretary/`（秘書）と `~/.claude/`（日向/Claude Code）で完全分離 |
| サブモジュール | `System/line_bot/` は独立git。個別commit→push→Render自動デプロイ |
| TCC制限 | Mac Miniでは `~/agents/` を作業ディレクトリとして使用（Desktop読み取り不可） |

### 4.3 承認ポイント（ガードレール表から）

| 領域 | 自律OK | 確認必要 |
|------|--------|---------|
| コード | 読み書き・コミット・push | — |
| ドキュメント | 読み書き・更新 | — |
| 外部サービス | 既存APIの読み取り・書き込み | 新規サービス導入・設定変更 |
| 金銭 | — | 全て確認 |
| 対人送信 | LINE秘書グループ・Slack #ai-team | それ以外の宛先 |
| データ | 作成・更新 | 不可逆な削除 |
| 認証情報 | 既存トークンの使用 | 新規取得・権限変更 |

---

## 5. 既存アーキテクチャの継承候補

### 5.1 ゴール実行エンジン（最有力な継承候補）

`Project/4_AI基盤/ゴール実行エンジン設計.md` の設計は、Cursor内エージェント基盤と思想が合致する:

- **Coordinator** = 自分では何も実行しない。振り分けと統合だけ
- **profiles.json** = 人間もAIもワークフローも同じスキーマで管理
- **tool_registry.json** = ツール追加はJSON編集のみ。コード変更不要
- **確認レベル** = L1（黙って実行）〜L5（人間判断）の5段階
- **耐久性** = AIツール・モデル・メンバー・通信手段が変わってもコード変更ゼロ

### 5.2 秘書v2エンジン

`Project/4_AI基盤/秘書v2_設計書.md` の記憶システム・LLMルーターも継承候補:

- **LLMルーター** = 設定ファイル1つでモデル切替。フォールバック自動
- **3層記憶** = 短期（会話）+ 長期（エピソード）+ 知識（Skills/Master/）
- **tool_use** = LLMが文脈判断でツールを自律選択

### 5.3 日向の学習ループ

`Project/4_AI基盤/日向エージェント.md` の学習エンジンも参考:

- **action_log** → **feedback_log** → **memory** の3段階蓄積
- フィードバック自動検出 + プロンプト注入 + 週次統合

---

## 6. 高レベルアーキテクチャ（提案）

### 6.1 既存との関係

```
┌─ Cursor（MacBook）──────────────────────────┐
│                                               │
│  AIエージェント基盤（今回作るもの）              │
│  ├─ Coordinator（ゴール実行エンジン継承）        │
│  ├─ LLMルーター（秘書v2継承）                   │
│  ├─ 記憶システム（秘書v2継承）                   │
│  ├─ Skills/（既存ナレッジ参照）                  │
│  └─ ツール群（既存スクリプト呼び出し）            │
│                                               │
│  既存: line_bot_local, Orchestrator（Mac Mini）  │
│  → 共存。基盤はCursor上の対話的操作に特化         │
│                                               │
└───────────────────────────────────────────────┘
```

### 6.2 責務の候補

| 責務 | 既存 | 新規基盤での位置づけ |
|------|------|-------------------|
| オーケストレーション | Orchestrator (Mac Mini) | Cursor上: Coordinator。Mac Mini: Orchestratorは維持 |
| リサーチ | Perplexity API / Claude Code | Coordinator経由でtool_use |
| 推論・分析 | Claude API / LLMルーター | LLMルーター継承 |
| 実行 | 各種スクリプト + Chrome MCP | tool_registry.json経由 |
| 承認 | LINE承認ワークフロー | Cursor UI上で対話的承認 |
| 記録・学習 | execution_rules.json + learning/ | 記憶システム継承 |

### 6.3 プロバイダー構成（候補）

| プロバイダー | 既存 | 提案 |
|------------|------|------|
| coding_provider | Claude Code CLI | Claude Code（Cursor統合） |
| browser_provider | Claude in Chrome MCP | Chrome MCP継続 |
| memory_provider | secretary_memory.md + contact_state.json | 統合記憶ファイル（secretary_memory.md拡張） |
| approval_provider | LINE承認（1/2/却下） | Cursor上の対話的承認 + LINE併用 |
| data_provider | Sheets API + KPIキャッシュ + CDP | 既存スクリプト群をtoolとして登録 |

### 6.4 状態管理（候補）

| ファイル | 役割 | 既存対応 |
|---------|------|---------|
| mission.md | 現在のミッション・コンテキスト | なし（新規） |
| context.md | 長期記憶・学習結果 | secretary_memory.md |
| state.json | 実行状態・進捗 | state.json（hinata） |
| logs/ | アクションログ | action_log.json |
| research/ | 調査結果の蓄積 | insights.md |
| artifacts/ | 生成物（レポート・資料等） | なし（新規） |
| memory/ | プロジェクト固有メモリ | MEMORY.md |

---

## 7. 未確定事項

→ `issues.md` に詳細記載

1. Cursor内基盤とMac Mini常駐システムの関係（共存/統合/置換）
2. 対象業務の具体的な着手順序（Tier 1内の優先度）
3. 広告CR単位のデータ接続方法（最大のブラインドスポット）
4. 日向エージェントの再開方針
5. コスト配分（GPT-5.4 vs Opus 4.6の使い分け基準）
