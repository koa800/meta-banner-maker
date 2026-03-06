# 高レベル設計提案

> ステータス: draft（人間確認必要）
> 前提: 既存アーキテクチャを最大限継承する

---

## 1. 設計の出発点

既に動いているものを壊さない。新たに作るのは「Cursor上で対話的に業務を代行する基盤」。

### 既存システムとの役割分担

| 実行環境 | 役割 | 動作モード |
|---------|------|----------|
| **Mac Mini** | 定常業務の自動実行（スケジュール駆動） | バックグラウンド・常時稼働 |
| **Cursor (MacBook)** | 対話的な業務代行（ユーザー駆動） | フォアグラウンド・セッション型 |
| **Render** | LINE/Chatwork Webhook中継 | 常時稼働 |

### 共有するもの（Single Source of Truth）

| 資産 | 場所 | 共有方法 |
|------|------|---------|
| 行動ルール | `execution_rules.json` | git同期 |
| 人物プロファイル | `profiles.json` | git同期 |
| ツール定義 | `tool_registry.json` | git同期 |
| KPIデータ | `kpi_summary.json` | git同期 + Sheets API |
| 知識ベース | `Skills/` + `Master/` | git同期 |
| 長期記憶 | `secretary_memory.md` | git同期（日次バックアップ） |

---

## 2. エージェント基盤の構成要素

### 2.1 Coordinator（既存継承）

`coordinator.py` のアーキテクチャをそのまま継承:
- ゴール → 意図理解 → ツール選択 → 実行 → 統合 → 報告
- profiles.json + tool_registry.json で拡張
- 確認レベル L1-L5

**Cursor基盤での変更点:**
- 入力: LINE → Cursor上の対話
- 出力: LINE通知 → Cursor上のレスポンス
- 承認: LINE「1」「2」→ Cursor上の対話的承認

### 2.2 LLMルーター（既存継承）

`llm_router.py` のアーキテクチャを継承:
- `llm_router.json` で設定管理
- GPT-5.4 → Opus → Sonnet のフォールバック
- 自然言語でモデル切替

### 2.3 記憶システム（既存継承）

`memory_manager.py` の3層構造を継承:
- 短期記憶: セッション内会話
- 長期記憶: `secretary_memory.md`
- 知識: `Skills/` + `Master/`（search_knowledgeツール経由）

### 2.4 ツール群（既存スクリプト活用）

| ツール名 | 既存スクリプト | 確認レベル |
|---------|-------------|----------|
| get_kpi_data | kpi_summary.json / csv_sheet_sync.py | L1 |
| get_calendar | calendar_manager.py | L1 |
| check_email | mail_manager.py | L1 |
| read_spreadsheet | sheets_manager.py | L1 |
| search_knowledge | Skills/ + Master/ 検索 | L1 |
| search_qa | qa_handler.py (Pinecone) | L1 |
| analyze | Claude API (tool_use) | L2 |
| draft_reply | Claude API + IDENTITY.md | L2 |
| generate_image | Gemini API | L2 |
| cdp_query | cdp_sync.py | L1 |
| addness_check | addness_to_context.py | L1 |
| send_message | LINE/Chatwork/メール | L3 |
| update_memory | secretary_memory.md 更新 | L1 |

### 2.5 ブラウザ操作

Chrome MCP を継続使用:
- Looker Studio操作
- Addness操作
- 広告管理画面操作（将来）

---

## 3. 状態管理ファイル配置

```
cursor/
├── docs/agent_requirements/    # 要件定義（今回作成）
├── System/
│   ├── config/
│   │   ├── llm_router.json     # LLMモデル設定（既存）
│   │   └── agent_config.json   # エージェント基盤設定（新規候補）
│   ├── data/
│   │   ├── secretary_memory.md # 長期記憶（既存）
│   │   └── agent_state.json   # エージェント実行状態（新規候補）
│   └── line_bot_local/
│       ├── coordinator.py      # Coordinator（既存）
│       ├── llm_router.py      # LLMルーター（既存）
│       ├── conversation.py     # 会話エンジン（既存）
│       └── memory_manager.py  # 記憶管理（既存）
├── Master/
│   ├── learning/
│   │   └── execution_rules.json  # 行動ルール（既存）
│   └── people/
│       └── profiles.json          # 統一エージェントスキーマ（既存）
└── Skills/                        # 業務知識（既存）
```

**方針:** 既存の `System/line_bot_local/` 内のモジュールをインポート可能な形で再利用。新規コードは最小限。

---

## 4. 初期実装の推奨スコープ

### Phase 0: 基盤整備（コード変更なし）

1. 既存 coordinator.py / llm_router.py / tool_registry.json の動作確認
2. Cursor上からの呼び出しインターフェース検討
3. 不足しているツール定義の洗い出し

### Phase 1: Tier 1業務のAI化（B1+B2, F2+F3）

1. **広告数値日次確認**: KPIキャッシュ → AIが分析・判断提案 → Cursor上で承認
2. **ゴール進捗確認**: Addness API → AIがサマリ・異常検知 → Cursor上で確認

### Phase 2: 知識活用（C1, B5）

1. **CR企画**: Skills/ のフレームワーク + Meta広告分析データ → AIが企画案生成
2. **広告リサーチ**: DPro + Web検索 → AIが競合分析レポート生成

---

## 5. 判断保留事項

| 項目 | 選択肢 | 推奨 | 理由 |
|------|--------|------|------|
| Cursor内の呼び出し方法 | A: Cursorルール + Claude Code / B: 専用CLI / C: MCP | A | 既存インフラ活用。追加コスト最小 |
| Mac Mini連携方法 | A: git同期のみ / B: API呼び出し / C: SSH | A | 既存の5分pullで十分。リアルタイム不要 |
| 記憶の保存場所 | A: System/data/ / B: Master/learning/ | A | git管理外で自由に読み書き可能 |
