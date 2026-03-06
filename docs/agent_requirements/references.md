# 参照ファイル一覧

> 調査日: 2026-03-07
> 目的: 要件定義の根拠として参照した全ファイルと、その使い方

---

## Source of Truth（最優先で参照すべきファイル）

### Tier 1: 業務の全体像を決定する根拠

| ファイル | 根拠としての使い方 | 信頼度 |
|---------|-----------------|--------|
| `Master/knowledge/業務棚卸し_AI化優先順位.md` | **対象業務の確定**。全106業務×自動化レベル×優先順位。AIエージェント基盤の「何を自動化するか」の根拠 | 最高（2026-03-03） |
| `CLAUDE.md` + `MEMORY.md` | **行動原則・制約条件の確定**。OS（7原則）・ガードレール・承認範囲 | 最高（常時更新） |
| `Master/learning/execution_rules.json` | **行動ルールのSingle Source of Truth**。秘書・日向・Claude Code全てに注入 | 最高 |

### Tier 2: 既存システムの継承判断

| ファイル | 根拠としての使い方 | 信頼度 |
|---------|-----------------|--------|
| `Project/4_AI基盤/AI秘書作成.md` | **秘書の全機能仕様**。何が実装済みで何が継承すべきか | 高（2026-03-07） |
| `Project/4_AI基盤/秘書v2_設計書.md` | **v2アーキテクチャ**。LLMルーター・記憶システム・tool_useの設計思想 | 高（2026-03-07） |
| `Project/4_AI基盤/ゴール実行エンジン設計.md` | **Coordinator設計**。profiles.json + tool_registry.jsonの統一スキーマ | 高（Phase 3完了） |
| `Project/4_AI基盤/日向エージェント.md` | **自律エージェントの設計・権限モデル**。成長モデル（Lv.1-3） | 高（一時停止中） |
| `Master/knowledge/環境マップ.md` | **インフラ全体像**。MacBook/Mac Mini/Render/GitHub構成 | 高 |

### Tier 3: 個別業務の実装状況

| ファイル | 根拠としての使い方 | 信頼度 |
|---------|-----------------|--------|
| `Project/4_AI基盤/CDP.md` | CDP設計・同期の詳細。顧客データ基盤の現状 | 高（2026-03-06） |
| `Project/3_業務自動化/数値管理自動化.md` | KPIパイプラインの全体像 | 高（2026-03-06） |
| `Project/3_業務自動化/メール自動管理.md` | メール自動化の完了状況 | 高（完了） |
| `Project/3_業務自動化/メールマーケティング自動化.md` | メルマガ自動化の設計（未着手） | 中（設計のみ） |
| `Project/3_業務自動化/経営会議資料_自動作成.md` | 経営会議資料のv1実装詳細 | 高（2026-03-07） |
| `Project/2_CS/質問自動回答プロジェクト.md` | Q&A自動回答の実装詳細 | 高（運用中） |
| `Master/knowledge/orchestrator.md` | Orchestratorスケジュール全体像 | 高 |
| `Master/knowledge/秘書の視界マップ.md` | データの可視化範囲・ブラインドスポット | 高（2026-03-03） |

### Tier 4: スキル・ナレッジ（参考）

| ファイル | 根拠としての使い方 | 信頼度 |
|---------|-----------------|--------|
| `Skills/1_広告/*.md` | 広告業務のスキル定義。AI化の入力情報 | 中 |
| `Skills/2_導線/*.md` | LP・導線設計のスキル定義 | 中 |
| `Skills/5_数値・業務/*.md` | 数値管理・業務情報 | 中 |
| `Master/addness/funnel_structure.md` | ファネル全体構造 | 中 |
| `Master/addness/goal-tree.md` | Addnessゴールツリー | 中 |
| `Master/knowledge/lstep_structure.md` | Lステップの構造理解 | 中 |

---

## 参照していないが関連する可能性のあるファイル

| ファイル | 理由 |
|---------|------|
| `Master/self_clone/kohara/BRAIN_OS.md` | 甲原さんの思考OS。エージェントの判断基準に影響しうる |
| `Master/addness/meta_ads_大当たりCR分析.md` | CR分析データ。広告AI化の学習データ候補 |
| `Master/addness/dpro_research_20260304.md` | DPro広告リサーチ。B5業務のAI化素材 |
| `Master/knowledge/定常業務.md` | 定常業務の手順書。自動化対象の詳細手順 |
| `.cursor/rules/*.mdc` | Cursorルール（24個）。Claude Code経由でCLAUDE.mdに同期済み |

---

## 矛盾・古い可能性のあるファイル

| ファイル | 懸念 |
|---------|------|
| `Master/knowledge/project_structure.md` | 一部の記述がAI秘書作成.mdと重複。project_structure.md側が古い可能性 |
| `Master/addness/goal-tree.md` | 3日ごとの自動取得だが、最終更新日を要確認 |
| `Master/knowledge/MacBook移行ガイド.md` | 移行完了後は参照価値が低い |
