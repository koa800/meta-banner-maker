# DS.INSIGHT 定期レポート

最終更新: 2026-03-05

## 概要

DS.INSIGHT（Yahoo!）の検索データを定期的に取得し、LINE秘書グループに自動通知するプロジェクト。
広告リサーチの定点観測として、検索トレンドの変化を早期検知する。

## Miro（システム構成図）

https://miro.com/app/board/uXjVG3QC6UU=/?focusWidget=3458764662214762145

## 機能一覧

| 機能 | 実行タイミング | ステータス |
|------|-------------|----------|
| [x] 隔週レポート | 隔週日曜 11:30 | 稼働中 |
| [x] メール転送（Basic/Trend） | 3時間ごと（mail_inbox_kohara内） | 稼働中 |

## 監視キーワード

| KW | 監視目的 |
|---|---|
| スキルプラス | ブランド認知の変化検知 |
| AI 副業 | 市場トレンドの変化検知 |
| 副業 | ターゲット需要の変化検知 |

## Trend配信カテゴリー

| カテゴリー | 親カテゴリー | 選定理由 |
|-----------|-----------|---------|
| 教育 | ライフスタイル | スキルアップ・リスキリング需要の検知 |
| 質問・困りごと | ライフスタイル | 「仕事ができない→できる」のニーズ検知 |
| 求人・職種 | ビジネス | 副業・起業・独立の市場動向検知 |

※ 集計期間: 短期トレンド（3ヶ月）

## DS.INSIGHTメール配信スケジュール（公式）

| 曜日 | 種別 | 内容 |
|------|------|------|
| 月曜 | Trend トレンドKW | 登録カテゴリのトレンドKW（ネクストブレイク3+ブレイクエリア3） |
| 火曜 | Basic メールアラート | 過去分析KWの検索Vol変化・属性変化・共起KW変化（変化時のみ） |
| 木曜 | Trend 急上昇KW | 登録カテゴリの急上昇KW上位5個 + AI考察 |

## システム構成

### メール転送（IMAP直接接続）

```
DS.INSIGHT → メール配信 → k.kohara@addness.co.jp（お名前.com）
                                    ↓
                    Mac Mini Orchestrator（3時間ごと）
                    IMAP4_SSL接続 → INBOX検索（直近7日 + 件名"DS.INSIGHT"）
                                    ↓
                    未転送メールを検出（Message-IDで重複防止）
                                    ↓
                    LINE秘書グループに通知 → 甲原さんに届く
```

**LINE通知フォーマット:**
```
📊 DS.INSIGHT通知

[メールの件名]
━━━━━━━━━━
[メール本文の先頭500文字]
```

### 隔週レポート（Claude Code + Chrome MCP）

```
隔週日曜 11:30
  → Claude Code CLI（claude-sonnet-4-6、max-turns=15）
    → Chrome MCP で DS.INSIGHT にアクセス
      → Basic / Journey / Trend データ取得
        → レポート生成 → LINE通知
```

**LINE通知フォーマット:**
```
📊 DS.INSIGHTレポート

[定点観測: 各KWの検索ボリューム推移（↑↓→で前回比）]
[変化検知: 大きく変動したKW・新規出現KW]
[インサイト: ビジネスに活かせる気づき]
```

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `System/mac_mini/agent_orchestrator/tools.py` | `dsinsight_mail_check()`（IMAP接続・メール取得） |
| `System/mac_mini/agent_orchestrator/scheduler.py` | `_check_dsinsight_emails()`（転送処理）/ `_run_ds_insight_biweekly_report()`（隔週レポート） |
| `System/mac_mini/agent_orchestrator/notifier.py` | `send_line_notify()`（LINE送信） |
| `System/credentials/onamae_imap.json` | IMAP認証情報（gitignore済み） |
| `System/data/ds_insight_forwarded_ids.json` | 転送済みMessage-ID管理（最大100件） |
| `System/data/ds_insight_last.json` | 隔週レポートの前回データ（前回比算出用） |
| `Master/addness/ds_insight_evaluation.md` | ツール評価・運用ルール |

## セットアップ

`System/credentials/onamae_imap.json` にパスワードを設定するだけ（設定済み）。

```json
{
  "server": "mail.addness.co.jp",
  "port": 993,
  "username": "k.kohara@addness.co.jp",
  "password": "***"
}
```
