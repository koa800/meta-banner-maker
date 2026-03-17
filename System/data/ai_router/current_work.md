# 引き継ぎメモ

最終更新: 2026-03-18

## 目的

- `アドネス株式会社` の KPI 基盤を `データソース -> 収集データ -> 加工データ -> 統合データ -> KPIダッシュボード` の流れで整備する
- `KPIダッシュボード` は表示層に徹し、各加工シートを正本として日次更新する
- Claude Code でも、そのまま続きの実装と運用確認に入れる状態にする

## 確定事項

- シート命名ルール
  - `【アドネス株式会社】<領域>（収集）`
  - `【アドネス株式会社】<領域>（加工）`
  - `【アドネス株式会社】<領域>（統合）`
  - `KPIダッシュボード` と `共通除外マスタ` は例外
- 集客
  - 主系統は `【アドネス株式会社】集客データ_メール集計（加工）`
  - 旧 `UUメールアドレス` と `全メール登録数` は legacy。定期更新停止済み
- 個別予約
  - `【アドネス株式会社】個別面談データ（収集） / 個別予約通知ログ`
    を Slack 通知の正本として使う
  - `2026/03/17` 以降は Slack 通知ベース
  - 同一人物の通知が `同日10分以内` に連続した場合は `1件`
  - `個別予約数（UU）` は未接続。LSTEP live 補完と統合キー確定まで保留
- 会員
  - 収集: `【アドネス株式会社】会員データ（収集） / 会員イベント`
  - 加工: `【アドネス株式会社】会員データ（加工） / 日別会員数値`
  - 日付は `2025/01/01` 開始
  - 未来日は入れない。`今日以前に確定したイベント` のみ計上
  - `クーリングオフ数`
    - 定義: `入金あり契約から7日以内に契約解除を申し出たユーザー数`
    - 集計元は `お客様相談窓口_進捗管理シート` のクーリングオフ集計を正とする
  - `中途解約数`
    - 定義: `サポート期間が終了する前に契約解除が確定した会員数`
  - `契約数`
    - 定義: `スキルプラスの契約書を締結したユーザー数`
- 定義一覧
  - すべて `マスタデータ / 定義一覧` に集約
  - 他シートの `定義` タブは削除済み
- 除外
  - `【アドネス株式会社】共通除外マスタ` を正本化済み
  - `除外リスト` と `無条件除外ルール` を各集計が参照する構成

## 完了したこと

- `【アドネス株式会社】集客データ_メールアドレス（収集）`
  - `【アドネス株式会社】顧客データ_メールアドレスのみ（統合）`
  - `【アドネス株式会社】顧客データ_複数イベント（統合）`
  - `【アドネス株式会社】集客データ_メール集計（加工）`
  の流れを整備
- `【アドネス株式会社】個別面談データ（収集）`
  - `個別予約通知ログ / データソース管理 / データ追加ルール`
  を整備
- `【アドネス株式会社】個別面談データ（加工）`
  - `日別個別予約数 / 日別個別予約数（UU） / 個別予約サマリー / データソース管理 / データ追加ルール`
  を整備
- `【アドネス株式会社】会員データ（収集）`
  - `会員イベント / データソース管理 / データ追加ルール`
  を整備
- `【アドネス株式会社】会員データ（加工）`
  - `日別会員数値 / 会員サマリー / データソース管理 / データ追加ルール`
  を整備
  - `2015年/2016年` の異常日付を排除
  - 未来日計上を排除
- `【アドネス株式会社】KPIダッシュボード`
  - `スキルプラス事業サマリー / 日別数値 / データソース管理`
  へ整理
  - `集客数 / 集客数（UU） / 個別予約数 / 会員数 / 中途解約数 / クーリングオフ数`
    を接続済み
- `【アドネス株式会社】共通除外マスタ`
  - `除外リスト / 無条件除外ルール / データソース管理 / データ追加ルール`
  を整備
- スプレッドシート作成ルール
  - 主要タブは左
  - ヘッダーは青背景/白文字/太字/12pt
  - 行は縦に伸ばしすぎない
  - 不要列・不要行は削除
  - 数値は 4 桁以上カンマ
  を明文化済み

## 未完了

- `【アドネス株式会社】広告費データ（加工）`
  - 未着手。次の主タスク
- `【アドネス株式会社】着金売上データ（加工）`
  - 未着手
- `【アドネス株式会社】KPIダッシュボード`
  - `広告費 / 着金売上 / CPA / 個別予約CPO / ROAS` は未接続
- `個別予約数（UU）`
  - 統合キー未確定のため保留
- `LSTEP live 補完`
  - 保留
  - `個別予約通知ログ` の `メールアドレス / 電話番号` の live 取得は未実装完了
- `LINE集客`
  - 収集/加工の全体統合は未着手

## 判断とその理由（最重要）

- `KPIダッシュボード` に元データや複雑なロジックを入れない
  - 理由: 表示層を軽く保ち、壊れた時の切り分けを簡単にするため
- `収集データ -> 加工データ -> 統合データ` の順序を崩さない
  - 理由: `統合データから加工データを作る` 設計にすると、責務が混ざりやすい
- `定義一覧` は 1 箇所へ集約
  - 理由: シートごとに定義がズレるのを防ぐため
- `個別予約数` は Slack 通知を正本へ寄せる
  - 理由: `★【個別予約完了】★` 自体は累積タグで、イベント件数の正本に向かないため
- `会員数` は未来日を持たない
  - 理由: まだ会員と確定していない未来イベントを KPI に混ぜるのは誤りだから
- `収集データは事実の日付`
  - `加工データは毎回再計算`
  - 理由: 入力遅延があっても、後から過去日付を正しく補正できるため
- `共通除外マスタ` は独立正本
  - 理由: 集客/個別予約/決済/会員で同じ除外基準を使えるため
- 旧シートは消さず legacy 化
  - 理由: 2025年以前や再検証で参照する可能性があるため

## 参照先

- `マスタデータ / 定義一覧`
  - https://docs.google.com/spreadsheets/d/1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w/edit
- `【アドネス株式会社】KPIダッシュボード`
  - https://docs.google.com/spreadsheets/d/1utCt9ex0puEi3-oxcjq9v37Jt-9X_dpSjPowZBsHeqA/edit
- `【アドネス株式会社】集客データ_メール集計（加工）`
  - https://docs.google.com/spreadsheets/d/13HS9KmlTdxQwMMaK45H3Ga1mMTUiJdhYKWnrExge_yY/edit
- `【アドネス株式会社】個別面談データ（収集）`
  - https://docs.google.com/spreadsheets/d/12bYadR0cgi24t4tz8GeESlsKffmNkkTHprI4ray_Sq4/edit
- `【アドネス株式会社】個別面談データ（加工）`
  - https://docs.google.com/spreadsheets/d/1ip_RARDHmQvTjmaVavw1L71ltPrn4Kg6sa__njqyQZ8/edit
- `【アドネス株式会社】会員データ（収集）`
  - https://docs.google.com/spreadsheets/d/1VwAO5rxib8pcR7KgGn-T3HKP7FaHqZmUhIBddo3okyw/edit
- `【アドネス株式会社】会員データ（加工）`
  - https://docs.google.com/spreadsheets/d/1OFKvyQsydPmTqd9MwSMX53MXxG9ASfkFquyf4PV-M8E/edit
- `【アドネス株式会社】共通除外マスタ`
  - https://docs.google.com/spreadsheets/d/1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw/edit
- `README`
  - `/Users/koa800/Desktop/cursor/Master/sheets/README.md`
- `KPIダッシュボード完成形設計`
  - `/Users/koa800/Desktop/cursor/Project/4_AI基盤/KPIダッシュボード完成形設計.md`
- `用語定義`
  - `/Users/koa800/Desktop/cursor/Master/前提/用語定義.md`

## 変更したファイル

- `/Users/koa800/Desktop/cursor/System/kpi_dashboard_layout_setup.py`
- `/Users/koa800/Desktop/cursor/System/booking_notification_log_sync.py`
- `/Users/koa800/Desktop/cursor/System/booking_metrics_sheet_sync.py`
- `/Users/koa800/Desktop/cursor/System/membership_collection_sheet_setup.py`
- `/Users/koa800/Desktop/cursor/System/membership_metrics_sheet_sync.py`
- `/Users/koa800/Desktop/cursor/System/common_exclusion_master_setup.py`
- `/Users/koa800/Desktop/cursor/Master/sheets/README.md`
- `/Users/koa800/Desktop/cursor/Project/4_AI基盤/KPIダッシュボード完成形設計.md`
- `/Users/koa800/Desktop/cursor/Master/前提/用語定義.md`
- `/Users/koa800/Desktop/cursor/Master/前提/用語定義.json`

## 次の担当へ

- まず `【アドネス株式会社】広告費データ（加工）` の要件定義から始める
- 進め方は毎回
  - 目的
  - 正本
  - タブ構成
  - 防止策
  - 検知
  - 自動更新
  の順で固める
- `LSTEP live 補完` と `個別予約数（UU）` は今は後回し
- `KPIダッシュボード` の未接続項目は、`広告費` と `着金売上` が固まってから接続する
- 作業ツリーには handoff と無関係の既存 dirty 変更がある
  - まとめてコミットしない
  - 今回の handoff 関連だけ分けて扱う

