# 引き継ぎメモ

最終更新: 2026-03-19

## 目的

- `アドネス株式会社` の KPI 基盤を `データソース -> 収集データ -> 加工データ -> 統合データ -> KPIダッシュボード` の流れで整備する
- `KPIダッシュボード` は表示層に徹し、各加工シートを正本として日次更新する

---

## 完了したこと

### 広告データ（収集）— Meta広告

- `【アドネス株式会社】広告データ（収集） / Meta` に28アカウント分の全期間データを取得完了
  - 88,531行。2024/02〜2026/03
  - スキルプラス関連28アカウント（VisionToDo・デザジュク1〜5は除外）
  - 取得項目: 日別×広告ID単位のInsights（インプレッション/リーチ/クリック5種/消化金額/コンバージョンJSON）+ メタデータ（配信ステータス/遷移先URL/動画ID等）
  - スクリプト: `System/scripts/fetch_meta_ads_to_sheet.py`
  - 進捗管理: `System/data/meta_ads_fetch_progress.json`
- TikTok / X の収集は未着手（API調査が必要）
- 委託先（YouTube広告/X広告）はシート記入で受け取り。未着手

### 決済データ（収集）

- `【アドネス株式会社】決済データ（収集）` に全ソースの過去データを取り込み完了
- 2026-03-19 に日次同期を強化し、Drive 日別フォルダ起点で 2026-03-18 までのデータ反映を完了
  - シートID: `1FfGM0HpofM8yayhJniArXp_vQ6-4JRvlp6rxDt-eHTI`
  - 決済データタブ: 275,994行（20列の共通カラム。1行=1イベント）
  - UTAGE補助タブ: 117,568行（UTAGEはUnivaPayと金額重複するため別タブ。登録経路の補助データ）
  - データソース管理タブ / データ追加ルールタブ

- **各ソースの取り込み状況**:

| ソース | 件数 | 期間 | 取り込み元 |
|---|---|---|---|
| UnivaPay | 267,413 | 2024/02〜2026/03 | 管理画面から全期間CSV取得 |
| MOSH | 2,668 | 2025/01〜2026/03 | 管理画面からCSVメール受取 |
| 日本プラム | 2,292 | 全期間 | 全期間CSVフォルダ |
| きらぼし銀行 | 1,793 | 2025/01〜2026/03 | 顧客管理シート「銀行振込」タブ（673行目以降の生データ） |
| CBS | 798 | 2025/01〜2025/11 | 旧データ（242件）+ 顧客管理シート「信販決済」タブ（681行目以降） |
| 京都信販 | 221 | 2025/01〜2025/08 | 旧データ（56件）+ 顧客管理シート「信販決済」タブ |
| INVOY | 776 | 全期間 | 全期間CSVフォルダ |
| CREDIX | 33 | 2026/01〜2026/03 | 旧データ（31件）+ 日別CSVフォルダ（2件）。2025年はサービス未開始 |
| UTAGE補助 | 117,568 | 2024/02〜2026/03 | 全期間CSVフォルダ。¥0取引（カード認証）1,446件除外済み |

- **共通カラム定義（20列）**: `Master/knowledge/payment_systems_definitions.md` に保存
- **各決済システムの公式定義**: 同ファイルに保存（UnivaPayのイベント/ステータス、MOSHの送金ステータス、CREDIXの決済ステータス等）
- **ログイン情報**: `System/credentials/payment_systems.json`

- **スクリプト**:
  - `System/scripts/payment_csv_to_sheet.py`: CSV→20列正規化→シート書き込み
  - `System/scripts/payment_daily_sync.py`: Google Drive日別フォルダ監視→自動取り込み

- **日次同期の現在地**:
  - `payment_daily_sync.py` は Orchestrator 登録済み
  - 監視対象は直近14日の日別フォルダ。`（全期間）` フォルダは自動収集対象外
  - 重複防止は `file_id / file fingerprint / 行 signature` の3段
  - 既知の対象外は `受講生サイト登録CSV` と `データなしメモ（3/18なし, データなし.txt 等）`
  - `未知ファイル / 中身不一致 / 取込失敗` のみ LINE 通知。既知の対象外はログだけ残す
  - 503 の一時エラーに対するリトライと、途中状態を落とさないチェックポイント保存を実装済み

- **収集段階のフィルタ方針**:
  - 収集データにはフィルタしない。全イベント・全ステータスをそのまま入れる
  - UnivaPayの認証プロセス（3-Dセキュア/CVVオーソリ/トークン発行）のみ除外（決済の事実ではないため）
  - きらぼし銀行の法人振込（カ)ニホンプラム等）は除外済み
  - フィルタ（着金確定の判定等）は加工の責務

### 広告費データ（加工）— 暫定版

- `【アドネス株式会社】広告費データ（加工）` を作成済み（数値管理シートを正本にした暫定版）
  - シートID: `1-dEYsY6KB0GF2XRf7PvoxVxhICCamdCBPKxHJRJdUOE`
  - Meta収集データから正本を切り替える作業は未着手
  - KPIダッシュボードに広告費/CPA/個別予約CPOを接続済み

### KPIダッシュボード

- 接続済み: 集客数 / 集客数（UU） / 個別予約数 / 広告費 / CPA / 個別予約CPO / 会員数 / 中途解約数 / クーリングオフ数
- 未接続: 着金売上 / ROAS（決済データの加工が先）

### その他の収集・加工シート（以前から完了済み）

- 集客データ_メール集計（加工）
- 個別面談データ（収集）/ 個別面談データ（加工）
- 会員データ（収集）/ 会員データ（加工）
- 共通除外マスタ

---

## 未完了タスク

### 最優先: 決済データ（加工）

- 収集データから日別着金売上を集計する加工シートを作る
- 加工時の着金確定フィルタ:
  - UnivaPay: イベント=売上。商品名空のリカーリング2回目以降を含めるか要確認
  - 日本プラム: 状態=最終承認
  - MOSH: 決済ステータス=支払い済み
  - きらぼし銀行: 全件（法人除外済み）
  - INVOY: ステータス=入金済
  - CREDIX: 結果=決済完了
  - CBS / 京都信販: 全件
- デザジュク系の除外が必要（デザイン限界突破/コンドウハルキ等）
- 商品名が空でも金額からスキルプラスと分かるもの（¥798,000等）は含める
- 加工完了後、KPIダッシュボードに着金売上/ROASを接続

### 決済データの日次収集ワークフロー

- 日次で Google Drive の日別フォルダを監視し、自動取り込みまで接続済み
- 2026-03-18 までのデータは反映済み
- 残論点は `【データ収集】2026/03/16（全期間）` を削除するか、バックアップ用途で残すかの整理

### 広告データの残り

- TikTok / X のAPI収集: 未着手
- 委託先（YouTube広告/X広告）の取り込み: 未着手
- 広告費データ（加工）の正本切り替え: Meta収集データ→加工シート再構築

### 保留中

- 個別予約数（UU）: 統合キー未確定
- LSTEP live 補完: 保留
- LINE集客: 未着手

---

## 数値管理シートとの突合結果

2025/07〜2026/02の着金売上を数値管理シートと比較検証済み。

- UnivaPayの商品名空（リカーリング2回目以降）とデザジュク系を除外して集計すると、合計で-2.8%（¥7,500万の不足）
- 不足の主因: UnivaPayの商品名が空でも高額（¥798,000等）のバックエンド商品がある。これを含めれば数字は近づく
- 結論: **収集データは揃っている。加工段階でフィルタを正しく設定すれば正確な着金売上が出せる**

---

## 判断とその理由

- `KPIダッシュボード` に元データや複雑なロジックを入れない → 表示層を軽く保つため
- `収集データ -> 加工データ` の順序を崩さない → 責務が混ざるのを防ぐため
- 収集データにはフィルタしない。全イベント・全ステータスを入れる → 加工で柔軟にフィルタできるように
- UTAGE売上一覧は決済データタブとは別タブ → UnivaPayと金額が重複するため。登録経路の補助データ
- きらぼし銀行の法人振込は除外 → 決済売上ではなく企業間の立替金振込
- UnivaPayの認証プロセス（3-Dセキュア等）は収集データから除外 → 決済の事実ではない
- デザジュク系の除外は加工の責務 → 収集には入れておく

---

## 参照先

- `【アドネス株式会社】決済データ（収集）`: https://docs.google.com/spreadsheets/d/1FfGM0HpofM8yayhJniArXp_vQ6-4JRvlp6rxDt-eHTI/edit
- `【アドネス株式会社】広告データ（収集）`: https://docs.google.com/spreadsheets/d/11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo/edit
- `【アドネス株式会社】広告費データ（加工）`: https://docs.google.com/spreadsheets/d/1-dEYsY6KB0GF2XRf7PvoxVxhICCamdCBPKxHJRJdUOE/edit
- `【アドネス株式会社】KPIダッシュボード`: https://docs.google.com/spreadsheets/d/1utCt9ex0puEi3-oxcjq9v37Jt-9X_dpSjPowZBsHeqA/edit
- 決済統合ロジック: https://docs.google.com/spreadsheets/d/1o9ylfSVXd_SzcUdoT1t-hGM9x1TPtwZ4-FpwPgr0EpY/edit
- 顧客管理シート（銀行振込・信販決済の生データ）: https://docs.google.com/spreadsheets/d/1l2gHhdUMfRANEDmZNfgpjx8KZi0yVCEknckjtpvYwBo/edit
- 決済システム定義: `Master/knowledge/payment_systems_definitions.md`
- KPIダッシュボード完成形設計: `Project/4_AI基盤/KPIダッシュボード完成形設計.md`
- スプレッドシート設計スキル: `Skills/6_システム/スプレッドシート設計ルール.md`
- ログイン情報: `System/credentials/payment_systems.json`

## 変更したファイル

- `System/scripts/payment_csv_to_sheet.py`（新規）
- `System/scripts/payment_daily_sync.py`（新規）
- `System/scripts/fetch_meta_ads_to_sheet.py`（新規）
- `System/scripts/fetch_meta_ads_test.py`（新規）
- `System/ad_spend_metrics_sheet_sync.py`（新規）
- `System/kpi_dashboard_layout_setup.py`（変更）
- `Master/knowledge/payment_systems_definitions.md`（新規）
- `Master/sheets/README.md`（変更）
- `System/credentials/payment_systems.json`（新規）
