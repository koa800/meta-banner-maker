# Claude Code ルール（このプロジェクト専用）

## ドキュメント更新ルール

**コードや設定を変更・追加したら、必ず関連ドキュメントも同じセッション内で最新化すること。**

### 対象ドキュメント

| ファイル | 更新トリガー |
|---------|------------|
| `Project/AI秘書作成.md` | `System/line_bot/app.py` または `System/line_bot_local/local_agent.py` を変更したとき |
| `Project/質問自動回答プロジェクト.md` | Q&A関連（`qa_handler.py`, `qa_monitor.py`, `qa_search.py`）を変更したとき |
| `Project/メール自動管理.md` | メール関連（`mail_manager.py`, `mail_inbox_*.py`）を変更したとき |
| `Project/数値管理自動化.md` | 数値管理関連（`csv_sheet_sync.py`, `sheets_manager.py`, `sheets_sync.py`）を変更したとき |
| `Project/定常業務.md` | 日報入力手順・Looker Studio CSV取得手順・完了報告フォーマットを変更したとき |

### 更新の原則

- **古い情報は残さない**: 変更箇所は上書き・削除して最新状態にする
- **完了済みは [x]**: 実装済み機能はチェックボックスを必ず [x] にする
- **最終更新日を更新**: ファイル冒頭の「最終更新」日付を変更日に更新する
- **ステータスを正確に**: 完了・開発中・廃止を正確に反映する

### 更新する内容の例

- 新機能を追加 → 機能一覧・コマンドリファレンスに追記
- バグ修正 → 注意事項・既知の制限を更新
- ファイルを追加・削除 → ファイル構成表を更新
- 環境変数を追加 → 環境変数一覧を更新
- アーキテクチャ変更 → 図・説明を更新

---

## プロジェクト構成

```
cursor/
├── Project/              # プロジェクトドキュメント（常に最新を維持）
├── Master/               # 知識ベース（people/, addness/, self_clone/, learning/, sheets/）
├── System/               # 実装ファイル
│   ├── credentials/      # OAuth トークン・クライアントシークレット（.gitignore）
│   ├── config/           # アプリ固有設定 JSON（.gitignore 対象あり）
│   ├── data/             # ランタイムデータ・キャッシュ（.gitignore）
│   ├── line_bot/         # Render (Flask) サーバー（git サブモジュール）
│   ├── line_bot_local/   # PC常駐エージェント
│   ├── addness_mcp_server/ # Addness MCP サーバー（git サブモジュール）
│   └── mac_mini/         # Mac Mini Orchestrator（スケジューラ・ツール群）
│       └── monitoring/   # 外部死活監視（MacBook → Mac Mini）
└── Skills/               # ナレッジ・スキル定義
```

### System/ 内のパス規約

| ディレクトリ | 内容 | Git 管理 |
|---|---|---|
| `credentials/` | `client_secret*.json`, `token*.json` | **除外** |
| `config/` | `addness.json`, `sns_analyzer.json`, `ai_news.json` | **一部除外** |
| `data/` | `kpi_summary.json`, `addness_session.json` | **除外** |

Python スクリプトからのパス解決は `Path(__file__).resolve().parent` を起点にする。

## コミットルール

- `System/line_bot/` への変更は `cd System/line_bot && git add . && git commit` でサブモジュールに個別コミット
- その後 `git push origin main` で Render に自動デプロイ
- メインリポジトリ側も変更があれば別途コミット
- コミット後は `post-commit` フックで自動 push → Mac Mini が5分以内に git pull で同期

## 技術選定の思考フロー

**思考の起点は常に「中から外」。手元の資産から出発し、外に探しに行くのは最後。**

```
1. 今何を持っている？（APIキー・認証情報・既存サービス・ライブラリ）
2. 持っているもので実現できないか？
3. できる → それを使う。終わり。
4. できない → 初めて外部の選択肢を探す
```

「〇〇といえば△△」という一般知識から入らない。必ず手元の棚卸しから始める。

### 判断軸（優先順位順）

1. **既存インフラの活用** — 新しいサービス・ツールの導入より、すでに使っているもので解決する
2. **スケーラビリティ** — マシンやメンバーが増えても設定変更が最小限で済むか
3. **シンプルさ** — 可動部品（依存サービス・認証・ネットワーク要件）が少ないほど良い
4. **可逆性** — 失敗しても元に戻せるか。段階的に移行できるか
