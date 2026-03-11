# アドネス UTAGE構造と運用ルール

最終更新: 2026-03-11

## 目的

アドネス株式会社における UTAGE の current 実装を、構造だけでなく「どこに何を作るのが正しいか」という作法まで分かる形で整理する。

この文書は、今後の以下の実務の前提に使う。

- ファネル作成
- ページ作成
- メール / LINE配信の設定
- 商品設定
- アクション設定
- 会員サイト修正
- イベント設定
- 動画 / メディア管理

## 今回の確認範囲

### ファネル

- 【センサーズ関連】※責任者：宮代
- 【書籍導線】※責任者：甲原
- 【スキルプラスライトプラン導線】※責任者：甲原
- 【スキルプラスセミナー導線】※責任者：甲原
- 【スキルプラス関連】※責任者：宮代
- 【共通ファネル用】※責任者：宮代
- 【AIカレッジ関連】※責任者：宮代

### メール・LINE配信

- 未分類
- 【スキルプラス導線】

## 結論

- メール配信の本体は UTAGE ではなく Mailchimp として見るのが正しい。UTAGE のメール・LINE配信は、主配信というより `メールアドレスのプール / backup / 一部補助配信` として使っている。
- UTAGE は `ファネル` と `配信アカウント` が別物で、見た目の LP 導線と、実際のメール / LINE 自動化の root が分かれている。
- UTAGE の主用途は `ページ作成` `会員サイト` `商品管理` `アクション設定` である。
- ファネルは `事業 / 媒体 / 役割` で切られている。ページはファネルの中に置かれ、ページ単位で `シナリオ / 外部連携フォーム / アクション / 商品` を接続する。
- メール / LINE 配信は `配信アカウント` が root で、シナリオ作成、配信、テンプレート、LINE設定はここにぶら下がる。
- `未分類` に残っている `センサーズ / AIカレッジ / デザジュク / アドプロ / ギブセル` は、current の別事業運用名ではなく、スキルプラス統合前の旧スクール名の legacy 命名である。
- current のメール配信で主に使っている root は `未分類` 内の `【成約時→センキューメール一覧】` と `🚧🚧【広告用全体メルマガ_統合用】🚧🚧`。
- `【スキルプラス導線】` は relevant な設定群として存在するが、少なくとも current のメール配信主運用 root とは見なさない。
- `スキルプラス【公式】` は current のメール配信主運用ではない。UTAGE 内には LINE / 会員サイト周辺設定が残っているが、mail root として扱わない。
- relevant な UTAGE 配信アカウントでは、`LINEテンプレート` は使っているが `リッチメニュー` は 0 件だった。少なくとも current 実装の中心はリッチメニューではない。
- アクションは shared library で、`Googleスプレッドシートへ追記` `webhook` `バンドルコースへ登録` が current の主力。つまり、外部連携、データ蓄積、講義保管庫解放が UTAGE の重要責務になっている。

## ログイン

- operator login URL は `System/credentials/utage.json` に保存している
- 自動ログイン補助:
  - `python3 System/scripts/utage_login_helper.py --target <開きたいURL>`
- できること
  - 既存 Chrome CDP セッションを再利用する
  - 未ログイン時は `email / password` を自動入力する
  - ログイン後に target URL をそのまま開く

## 1. ファネル

### 構造

- 一覧: `/funnel`
- ファネル共通設定: `/funnel/{funnel_id}/edit`
- ページ一覧: `/funnel/{funnel_id}/page`
- ページ編集: `/funnel/{funnel_id}/page/{page_id}/edit`
- マップ: `/funnel/{funnel_id}/map`
- 数値: `/funnel/{funnel_id}/data`, `/data/daily`
- トラッキング: `/funnel/{funnel_id}/tracking`
- 登録経路: ページ設定内の `登録経路`

### current の target group と代表ファネル

#### 【書籍導線】※責任者：甲原

- `起業の本質_YouTube広告`
- `起業の本質_LINE導線用`

#### 【スキルプラスライトプラン導線】※責任者：甲原

- `ライトプラン_Meta広告`
- `ライトプラン_X広告`
- `ライトプラン_共通ページ`

#### 【スキルプラスセミナー導線】※責任者：甲原

- `スキルプラスHP`
- `スキルプラス_リスティング広告`
- `スキルプラス_ディスプレイ広告`
- `スキルプラス_YouTube広告_自社運用用`
- `スキルプラス_YouTube広告_フレッド様運用用`
- `スキルプラス_Yahoo!広告`
- `スキルプラス_Meta広告`
- `スキルプラス_X広告`
- `スキルプラス_LINE広告`
- `スキルプラス_TikTok広告`
- `スキルプラス_SNS`
- `スキルプラス_NewsPicks`
- `スキルプラス_TVer広告`
- `スキルプラス_SEO`
- `スキルプラス_アフィリエイト広告`
- `スキルプラス_アフィリエイト広告（受講生用）`
- `スキルプラス【公式】限定コンテンツ`

#### 【スキルプラス関連】※責任者：宮代

- `【スキルプラス】ユーザー登録ページ`
- `【スタートダッシュ】ユーザー登録ページ`
- `【事業構築コース】ユーザー登録ページ`
- `【AIXコンサルタントコース】ユーザー登録ページ`
- `【広告運用コース】ユーザー登録ページ`
- `【営業代行コース】ユーザー登録ページ`
- `【デザインコース】ユーザー登録ページ`
- `【SPスタートダッシュコースのみ】ユーザー登録ページ`
- `【保管庫成約】保管庫解放ページ`
- `【保管庫】契約締結後未入金者保管庫解放`
- `スキルプラス継続利用【スタートダッシュ】`
- `スキルプラス継続利用【スタンダード】`
- `スキルプラス継続利用【エリート】`
- `スキルプラス継続利用【プライム】`

#### 【共通ファネル用】※責任者：宮代

- `共通使用ファネル`
- `メインコンテンツ_視聴ページ`
- `センサーズ_ダイナマイト合宿講義`
- `AIカレッジ_AIXコンサルタント合宿講義`
- `AIカレッジ_ゼロから始める本質のAI完全攻略_合宿講義`
- `デザジュク_限界突破デザイン合宿講義`
- `SNS_Meta_7桁_合宿`
- `SNS_ TikTok_7桁_合宿`

#### 【AIカレッジ関連】※責任者：宮代

- `AI：メインファネル_LINE導線用`
- `AI：メインファネル_YouTube広告`
- `AI：Agファネル_YouTube広告`
- `AI：メインファネル_Meta広告`
- `AI：メインファネル_X広告`
- `AI：メインファネル_Yahoo!広告`
- `AI：メインファネル_LINE広告`
- `AI：メインファネル_リスティング広告`
- `AI：メインファネル_TikTok広告`
- `AI：AIX合宿【アフィリエイト対象】`
- `AI：RT企画`
- `AIカレッジ：顧客感想LP`
- `AIカレッジ：面談希望者特典LP`
- `AIカレッジ：メインファネル_ディスプレイ`

### 抽出した作法

- ファネル名は `事業名_媒体` または `事業名：メインファネル_媒体` が基本。
- current の本番ファネルはほぼ `公開` / `本番モード`。共通設定の `公開終了日時` や `リダイレクトURL` は空が多い。
- `共通ページ` や `関連` グループは「単独集客」ではなく、販売ページ、講義視聴ページ、会員登録ページの shared library として使っている。
- ページを作るときは、見た目だけではなく `scenario_id_str` `form_id_str` `action_id` `payment_product_id_str` まで接続して初めて成立する。
- `登録経路` は重要機能。1つのページに対して複数の登録経路を作成でき、同じページ訪問でも「どこから来たか」を経路別に分けて計測できる。
- current の Meta広告 AIファネルや SNSファネルでは、登録経路が大量に作られている前提で読む。これはページを複製しているのではなく、同一ページへの流入を経路別に分析するため。
- `登録経路` は「広告 ID だから必ず分ける」機能ではない。基本思想は「どこからユーザーが訪れたのかを知りたい時に分ける」で、その結果として広告 ID 単位で切るケースが多い。
- つまり、UTAGE のページ分析では `ページURL` だけでなく `登録経路名` まで見ないと、current の流入差分を正しく読めない。
- 同一事業でも `媒体別 main funnel` と `共通ページ` が分かれているため、新規作成時はまず「新しい媒体導線を作るのか」「既存の共通ページを使うのか」を切り分ける必要がある。

### representative page の current 接続例

#### 書籍: `起業の本質_YouTube広告`

- step: `【起業の本質】LP1`
- page: `【起業の本質】LP1`
- 更新: `2026-01-04`
- current 実装:
  - 画像 CTA の `form` が 4 箇所
  - scenario: `YouTube広告_起業の本質_オプトインシナリオ`
  - action: `★使用中★　起業の本質_YouTube広告：オプトイン　※変更時、森本雄紀に確認`
  - 遷移先: `https://school.addness.co.jp/p/VFULDbrjjmHj`
- 解釈:
  - 書籍系 LP も、見た目は画像中心だが実態は `画像フォーム CTA + scenario + action + 次ページ` の接続で成立している

#### ライトプラン: `ライトプラン_Meta広告`

- step: `Meta広告_秘密の部屋_オプトインLP1`
- page: `オプトインLP_3つの秘訣_CTA0円ウェビナーを見る`
- 更新: `2026-01-31`
- current 実装:
  - `無料ウェビナーを受講する` の `form` が 4 箇所
  - scenario: `Meta広告_秘密の部屋_オプトイン`
  - action: `★使用中★　Meta広告_秘密の部屋_オプトイン　※変更時、森本雄紀に確認`
  - 遷移先は 2 系統
    - `https://school.addness.co.jp/p/9K3dUyLbuQat`
    - `https://school.addness.co.jp/p/E6g12WwMhDWI`

#### ライトプラン: `サンクスページ`

- step: `Meta広告_ライトプラン_サンクスページ（LINE登録）`
- page: `サンクスページ`
- 更新: `2026-01-06`
- current 実装:
  - visible button 1 箇所
  - LIFF 直リンク: `follow=@496sircr&lp=HXCxrP`
- 解釈:
  - サンクスは自動リダイレクトではなく、ボタン遷移の current 例がある

#### スキルプラス: `スキルプラス_Meta広告`

- step: `Meta広告_スキルプラス_オプトインLP4_セミナー導線`
- page: `メインLP_みかみさんFV_オレンジボタン_要素並び替え_特典(30億社長)_新テイスト荻野_AMAZON_CTAテスト②_ベネフィット追加_権威東北大学_全CR配信`
- 更新: `2026-02-15`
- current 実装:
  - `無料ウェビナーを受講する` の `form` が 4 箇所
  - scenario: `Meta広告_スキルプラス_ウェビナー①オプトインシナリオ`
  - action: `★使用中★　スキルプラス（セミナー導線）Meta広告：オプトイン　※変更時、森本雄紀に確認※`
  - 遷移先: `https://school.addness.co.jp/p/E6g12WwMhDWI`
- 解釈:
  - スキルプラスの current LP も、ボタン画像に form を載せる構造が基本

#### スキルプラス: `サンクスページ _自動リダイレクト`

- step: `【スキルプラス】サンクスページ（LINE登録）`
- page: `サンクスページ _自動リダイレクト`
- 更新: `2025-12-26`
- current 実装:
  - visible CTA はなし
  - `js_body_top` で 1.6 秒後に LIFF へ自動遷移
  - redirect: `https://liff.line.me/2006618892-P3oWzoBb/landing?follow=%40496sircr&lp=i0nQbh&liff_id=2006618892-P3oWzoBb`
- 解釈:
  - UTAGE の current サンクスページは、ページ内要素ではなく page-level script で自動遷移させるパターンもある

#### スキルプラス関連: `【スキルプラス】ユーザー登録ページ`

- step: `【フルサポ/オールイン】ユーザー登録`
- page: `スキルプラス -ユーザー登録ページ-`
- 更新: `2025-12-05`
- current 実装:
  - `無料でユーザー登録を完了する` の `form` が 1 箇所
  - scenario: `【フルサポートプラン】スキルプラス スタンダード ユーザー登録`
  - action: `スキルプラス保管庫解放アクション`
  - 遷移先: `https://school.addness.co.jp/p/0QcxPfyZVEZj`
- 解釈:
  - ユーザー登録ページは、mail opt-in よりも `会員登録 scenario + 保管庫解放 action` が主目的

#### 共通: `共通使用ファネル`

- step: `新・ファン化動画視聴ページ`
- page: `新・ファン化動画視聴ページ`
- 更新: `2025-06-06`
- current 実装:
  - `comment` 要素の CTA が 2 系統
    - UTAGE ページ: `https://school.addness.co.jp/p/q84ikoiP7swW`
    - LIFF: `follow=@303zgzwt&lp=qLUvPk`
- 解釈:
  - 共通ページは単純な LP ではなく、UTAGE 内遷移と LINE 遷移が混在する shared page として使っている

#### AI: `AI：メインファネル_Meta広告`

- step: `Meta広告_AI_オプトインLP1`
- page: `AIカレッジ_FB広告_optin2_長め_みかみ式_緑LPテイスト_FV AI美女2_分野を問わない_累計10万人`
- 更新: `2026-02-25`
- current 実装:
  - `無料ウェビナーを見る` の `form` が 2 箇所
  - scenario: `AIカレッジ：FB広告【7桁オプトインシナリオ】`
  - action: `★使用中★　AIカレッジFB：オプトイン　※変更時、宮代に確認※`
  - 遷移先: `https://school.addness.co.jp/p/BDDVNnsFzVO9`

#### AI: `AIカレッジ_Thanksページ(15分)`

- step: `AI合宿_Thanksページ`
- page: `AIカレッジ_Thanksページ(15分)`
- 更新: `2024-02-23`
- current 実装:
  - visible button 1 箇所
  - Short.io: `https://skill.addness.co.jp/meta-ai6`
- 解釈:
  - AI の current thanks は、Short.io を経由した CTA ボタンの例として読める

### funnel データ画面の current の見方

- representative funnel として `AI：メインファネル_Meta広告` を live で確認
  - funnel id: `TXUOxBYkYr9e`
- 主要 route
  - `データ(合算) = /funnel/TXUOxBYkYr9e/data`
  - `データ(日別) = /funnel/TXUOxBYkYr9e/data/daily`
  - `登録経路 = /funnel/TXUOxBYkYr9e/tracking`
- `データ(合算)` と `データ(日別)` は、どちらも
  - `期間`
  - `集計方法`
  - `登録経路`
  を条件に持つ
- つまり UTAGE 側の訪問 / CV 分析は
  - funnel 単位
  - 日別か合算か
  - 登録経路単位
  で切るのが基本
- `登録経路` 画面では
  - 登録経路名
  - 接続ページ名
  が並ぶため、広告 ID 単位の分析軸をここで持てる
- `追加` は `https://school.addness.co.jp/funnel/{funnel_id}/tracking/create`
- `グループ管理` は `.../tracking/group`
- `表示順変更` は `.../tracking/sort`
- create 画面では少なくとも
  - `グループ`
  - `管理名称`
  - `ファネルステップ`
  - `ページ`
  を設定する
- つまり `登録経路` は、単なるラベルではなく
  - どの step に属するか
  - どの page を指すか
  まで紐づけて作る実体
- 動線データ基盤を作るとき、UTAGE 側で取りに行くべき数値の入口はまずこの 3 画面

#### 【センサーズ関連】※責任者：宮代

- `SNS：メインファネル_LINE導線用`
- `SNS：メインファネル_Meta広告`
- `SNS_Meta広告_7桁_園部`
- `SNS：メインファネル_YouTube広告`
- `SNS：Agファネル_YouTube広告`
- `SNS：メインファネル_X広告`
- `SNS_X_7桁`
- `SNS：メインファネル_LINE広告`
- `SNS：メインファネル_TikTok広告`
- `SNS_TikTok広告_7桁`
- `SNS：メインファネル_リスティング広告`
- `SNS：ダイナマイト合宿【アフィリエイト対象】`
- `SNS：LP(バズカレに流してもらう用)`
- `SNS：メインファネル_口コミ`

#### 補足

- `【センサーズ関連】` は過去のメインファネル群として理解するのが正しい。
- current の事業名は統合されていても、UTAGE 内では旧スクール名のまま重要資産が残っている。
- そのため、古いから無視する対象ではなく、`導線の型` と `旧 main 運用の正本` を読む場所として価値が高い。

### `登録経路` の current 実例

- `AI：メインファネル_Meta広告`
  - 登録経路件数: `3802`
  - 例:
    - `Meta広告-AI-LP1-CR01015`
    - `Meta広告-AI-LP1-CR01868`
    - `AIカレッジFBオプトB_クリエイティブ600（広告テキストテスト用）`
  - 同じ LP step に対して `?ftid=` が違う URL を大量に切っている

- `スキルプラス_Meta広告`
  - 登録経路件数: `663`
  - 例:
    - `Meta広告-スキルプラス-LP4-CR00001`
    - `Meta広告-スキルプラス-LP4-CR00002`
  - current でも、ページ複製より `同一ページ + 登録経路分岐` の分析がかなり強い
  - ただし、これは「広告 ID だから必ず分ける」のではなく、「流入元を分けて見たいから分ける」運用の current 実例

### page editor の current settings UI

- representative editor:
  - `https://school.addness.co.jp/funnel/TXUOxBYkYr9e/page/bDbOI7aX59IL/edit`
- `ページ設定` は別画面ではなく、current editor 内の settings menu
- menu として visible なのは
  - `基本情報`
  - `デザイン`
  - `高速表示モード`
  - `メタデータ・検索`
  - `カスタムJS`
  - `カスタムCSS`
  - `表示期限`
  - `ワンタイムオファー`
  - `パスワード保護`
  - `広告連携`
  - `ポップアップ`
  - `エディター設定`
- `基本情報`
  - `管理名称`
  - `ページタイトル`
- `デザイン`
  - `ページ幅(PC)`
  - `ページスワイプ`
  - `ページ枠(PC)`
- `高速表示モード`
  - visible field は `is_high_speed_mode` の切替のみ
  - `利用しない`
  - `利用する（β版機能）`
- `メタデータ・検索`
  - `タイトル`
  - `説明`
  - `OG画像(og:image)URL`
  - `検索エンジンに表示 / 非表示`
- `カスタムJS`
  - `headタグの最後に挿入するjs`
  - `bodyタグの最初に挿入するjs`
  - `bodyタグの最後に挿入するjs`
  - `script タグも含めて記載`
- `カスタムCSS`
  - `css`
  - `style タグは不要`

## 2. メール・LINE配信

### 構造

- 一覧: `/account`
- シナリオ一覧: `/account/{account_id}/scenario`
- シナリオ設定: `/account/{account_id}/scenario/{scenario_id}/edit`
- 読者 / フロー表示: `/reader`
- 一斉送信: `/broadcast/create`
- LINE一斉送信: `/broadcast/line/create`
- フォーム: `/form/edit`, `/form/line/edit`, `/forms`, `/form/tag`
- LINE管理: `/line/friend`, `/line/autoreply`, `/line/richmenu`, `/line/template`

### `未分類` グループの役割

`未分類` は名前と実態がズレている。

ここに並ぶ `センサーズ / AIカレッジ / デザジュク / アドプロ / ギブセル` は current の別事業ではなく、スキルプラス統合前の旧スクール名で残っている legacy 命名である。

中には separator 的な命名が残っており、内部的にはこの単位で運用を分けている。

- `【スキルプラス成約時送付用】`
- `【広告用メルマガ】`
- `【センサーズメルマガ】`
- `【AIカレッジメルマガ】`
- `【デザジュクメルマガ】`
- `【アドプロ関連】`
- `【ギブセルメルマガ】`
- `【直個別メルマガ】`
- `【その他】`

current で主に使っている root は、ユーザー確認ベースでは以下の 2 つ。

- `【成約時→センキューメール一覧】`
- `🚧🚧【広告用全体メルマガ_統合用】🚧🚧`

広告媒体ごとの mail-only アカウントは残っているが、`存在している = current 主運用` とは読まない。

Mailchimp が主配信なので、UTAGE account 側は「完全な配信本体」ではなく、

- backup 的なメールアドレス保持
- thanks / 補助シナリオ
- old route の保持

の役割も混ざっている前提で読む。

#### 代表アカウント

- `【成約時→センキューメール一覧】`
- `🚧🚧【広告用全体メルマガ_統合用】🚧🚧`
- `AIカレッジ：共通メルマガフォルダ`
- `AIカレッジ：YouTube広告メルマガフォルダ`
- `AIカレッジ：FB広告メルマガフォルダ`
- `AIカレッジ：X広告メルマガフォルダ`
- `AIカレッジ：Yahoo広告メルマガフォルダ`
- `AIカレッジ：LINE広告メルマガフォルダ`

#### AIカレッジ：FB広告メルマガフォルダの current 構成

- `AIカレッジ_Facebook広告_7桁のオプトイン`
- `AIカレッジ_Facebook広告_オプトイン時_個別3日間シナリオ`
- `AIカレッジ_Facebook広告_AI合宿購入_秘密の部屋未入会`
- `AIカレッジFB広告_電話番号シナリオ`
- `AI_FB広告_AI合宿_15min_thanksメール`
- `Ai_FB広告_Ai合宿_3day_thanksメール`
- `AI_FB広告_秘密の部屋_thanksメール_OTO`
- `AI_FB広告_秘密の部屋_thanksメール_メルマガ再セールス`

#### 抽出した作法

- current と legacy をまず分ける。旧スクール名アカウントが多いため、名前だけで「今使っている」と判定しない。
- current の mail root は、まず `【成約時→センキューメール一覧】` と `🚧🚧【広告用全体メルマガ_統合用】🚧🚧` を見る。
- mail-only アカウントを媒体別フォルダとして切る構造自体は残っている。
- AI のシナリオ名は `事業_媒体_イベント` の粒度で揃っている。
- 1つの広告媒体アカウントの中に、オプトイン、個別3日間、電話番号、購入後 thanks まで束ねる。
- シナリオグループは AI current では `メルマガ` が基本。

### `【スキルプラス導線】` グループの役割

スキルプラス関連の設定群として重要だが、少なくとも current のメール配信主運用 root とは扱わない。

#### アカウント

- `スキルプラス【公式】` `メール・LINE併用`
- `スキルプラス導線` `メールのみ`
- `SLSテスト` `メール・LINE併用`

#### `スキルプラス導線` の current シナリオ

- `全シナリオ合算`
- `リスティング広告_スキルプラス_メインLP後シナリオ`
- `ディスプレイ広告_スキルプラス_メインLP後シナリオ`
- `YouTube広告_スキルプラス_メインLP後シナリオ`
- `Yahoo!広告_スキルプラス_メインLP後シナリオ`
- `Meta広告_スキルプラス_メインLP後シナリオ`
- `LINE広告_スキルプラス_メインLP後シナリオ`
- `TikTok広告_スキルプラス_メインLP後シナリオ`
- `𝕏広告_スキルプラス_メインLP後シナリオ`
- `TVer広告_スキルプラス_メインLP後シナリオ`
- `Meta広告_スキルプラス_BOTCHAN経由後_リマインド`
- `アフィリエイト広告_直個別導線_オプトインシナリオ`
- `Meta広告_スキルプラス_ウェビナー①オプトインシナリオ`
- `YouTube広告（自社）_スキルプラス_ウェビナー①オプトインシナリオ`
- `YouTube広告（フレッド様）_スキルプラス_ウェビナー①オプトインシナリオ`
- `Yahoo広告_スキルプラス_ウェビナー①オプトインシナリオ`

#### シナリオグループ

- `Meta広告_スキルプラス_メインLP後シナリオ` -> `無料体験会ファネル`
- `Meta広告_スキルプラス_ウェビナー①オプトインシナリオ` -> `ウェビナーファネル`

#### 抽出した作法

- スキルプラスの mail シナリオは `媒体_事業_イベント` の命名が current。
- `メインLP後シナリオ` と `ウェビナー①オプトインシナリオ` で枝を分ける。
- funnel group と scenario group が対応していて、無料体験会枝とウェビナー枝を UTAGE 側で切っている。
- ただし current 主運用判定は別で、ユーザー確認上は `未分類` 側の統合 root を優先する。
- つまり、ここは `作り方の参照元` としては useful だが、`今この account から主送信している` とまでは言わない。

### `スキルプラス【公式】` の役割

`スキルプラス【公式】` は hybrid account で、UTAGE 内に LINE / 会員サイト周辺メッセージ設定が残っている。

ただし、ユーザー確認ベースでは current のメール配信主運用ではない。

#### シナリオ

- `「紹介コード」持ってる人用シナリオ`
- `「紹介コード」持ってない人用シナリオ`
- `会員サイトログイン情報共有メッセージ`
- `限定コンテンツシナリオ`
- `LINE広告_プレゼント企画（10大特典）`

#### LINE current 利用状況

- LINEテンプレート: 9件
- 自動応答: 7件
- リッチメニュー: 0件
- LINE友だち一覧: 50件表示まで確認

#### テンプレート current 例

- `1/17_広報×セミナー企画`
  - グループ: `自動応答`
- `「紹介コード」持っている方への流入直後メッセージ`
  - グループ: `流入時`

#### 抽出した作法

- current の LINE施策は、`スキルプラス導線` ではなく `スキルプラス【公式】` 側で運用されている。
- relevant な UTAGE account では、少なくとも現在 `リッチメニュー` は未使用。今後リッチメニュー作業をする場合は、UTAGE で新設するのか Lステップ 側で持つのかを最初に確認する必要がある。

## 3. 会員サイト

### 構造

- 一覧: `/site`
- コース一覧: `/site/{site_id}/course`
- コース編集: `/site/{site_id}/course/{course_id}/edit`
- レッスン一覧: `/site/{site_id}/course/{course_id}/lesson`
- 設定: `/config`, `/payment`, `/category`, `/page`, `/url`, `/news`

### current の代表サイト

- `スキルプラス - 受講生サイト`
  - コース数: 250
- `AIカレッジ講義保管庫`
  - コース数: 35
- `スキルプラス【フリープラン】- 受講生サイト`
- `AI秘密の部屋`
- `スキルプラス【公式】限定コンテンツ`

### current で特に押さえるべき 3 サイト

#### `スキルプラス - 受講生サイト`

- site id: `BQys60HDeOWP`
- コース: `250`
- バンドルコース: `7`
- 固定ページ: `0`
- お知らせ: `64`
- current の見え方:
  - main の講義保管庫として使っている
  - 固定ページより `コース` と `お知らせ` の比重が高い
  - `スキルプラス講義保管庫全開放` の登録受講生は `5777`

#### `スキルプラス - スキルプラス受講生サイト_`

- site id: `4OmwdFs2ji1E`
- コース: `346`
- バンドルコース: `7`
- 固定ページ: `4`
- お知らせ: `0`
- current の見え方:
  - main site より granular な講義単位のコースが多い
  - `AIビジネスコース_参考資料集` や `よくある質問` など、固定ページ運用が main より強い
  - `デモ用` 受講生 1件だけで、学習設計や資料置き場寄りに見える

#### `みかみの秘密の部屋`

- site id: `s6L6YA3VJsbk`
- コース: `6`
- バンドルコース: `4`
- 固定ページ: `1`
- お知らせ: `0`
- current の見え方:
  - `秘密の部屋【講義視聴ページ】` を中心に回る専用 site
  - `みかみの『秘密の部屋』` の登録受講生は `4414`
  - 固定ページは `ログイン出来ない方はコチラ！` のみで、サポート導線が最小限に絞られている

### 会員サイトで先に見る順番

1. `bundle`
   - どの束で受講解放しているかを見る
2. `course`
   - 実際に見せる講義の単位を見る
3. `lesson`
   - 1講義の開放条件、本文、コメント設定を見る
4. `user`
   - 受講者運用の粒度を見る
5. `page / news`
   - 補助ページと告知運用を見る
6. `config / payment / url`
   - site 全体設定、課金連動、ログイン導線を確認する

### current で見えた設定項目

#### コース基本情報編集

- `コース名`
- `管理名称`
- `種類`
- `リンク先URL`
- `リンクの開き方`
- `コース画像`
- `ボタンテキスト`
- `進捗率`
- `動画自動再生/視聴完了設定`
- `カテゴリ`
- `未ログイン時の閲覧`
- `ステータス`
- `常時表示オファー`
- `期間限定オファー`
- `受講対象者`
- `受講スタイル`
- `開放日(開始日)`

#### レッスン基本情報編集

- `グループ`
- `レッスン名`
- `種類`
- `リッチテキスト / コンテンツエディター`
- `コンテンツ`
- `ステータス`
- `コメント機能`
- `受講対象者`
- `開放日(開始日)`
- `開放前の表示`

#### バンドルコース編集

- `バンドルコース名`
- `追加するコース`

#### 固定ページ編集

- `タイトル`
- `種類`
- `内容`
- `ステータス`
- `公開範囲`

#### お知らせ編集

- `タイトル`
- `種類`
- `内容`
- `公開対象`
- `ステータス`
- `公開日時`

#### site 全体設定

- `サイト名`
- `Copyright表記`
- `アカウント自動発行時仮パスワード`
- `新規ユーザーへのパスワード変更の強制`
- `head / body への JavaScript 挿入`
- `ログインなしでの閲覧`
- `ブックマーク機能`
- `検索エンジンへの表示`
- `メモ`

#### 課金連動設定

- `課金連動`
- `受講生側での課金停止`
- `解約手続きに伴う注意事項`
- `解約フォーム項目`
- `通知先メールアドレス`

#### URL 設定

- `ログインURL`
- `プレビューURL`

#### カテゴリ

- create 画面の入力は `名称` のみ
- current で確認した 3 サイトでは、`category` 一覧は全て `0件`
- つまり current の会員サイト運用では、カテゴリ分けより `bundle / course / lesson` の設計が主

### 抽出した作法

- スキルプラスは巨大な main site にかなりのコースを統合している。
- AI は専用の講義保管庫を別 site として持つ。
- `未使用` や `コピー` を名前に明記した site が残っている。新規作成時は current site に寄せ、 copy 系を増やしすぎない方が安全。
- 会員サイト解放は `商品購入 -> アクション -> バンドルコースへ登録` でつなぐのが current の重要パターン。
- `スキルプラス - 受講生サイト` は main の講義とお知らせ運用が中心。
- `スキルプラス - スキルプラス受講生サイト_` は固定ページや granular な教材設計の参照元として useful。
- `みかみの秘密の部屋` は少数コース + 少数 bundle で回る専用 site として見ると分かりやすい。
- 会員サイト修正を頼まれたら、まず `bundle` を見て、次に `course`、最後に `lesson` を触る。いきなり本文から直さない方が安全。

## 4. イベント

### 構造

- 一覧: `/event`
- applicant: `/event/{event_id}/applicant`
- item: `/item`
- register: `/register`
- form: `/form`
- config: `/config`

### current の代表イベント

- `AIは教えてくれない！会社に依存しない生き方を実現する「スキル習得セミナー」`
- `【スキルプラス スタンダード】新入生1on1`
- `【スキルプラス プライム】新入生1on1`
- `【スキルプラス】月報1on1`
- `【スキルプラス】目標設定FB1on1`
- `スキルプラスBOTCHAN`

### current 設定例

- 種類: `セミナー・説明会`
- 参加費: `無料`
- 決済連携設定: `デフォルト`
- 連携配信シナリオ: 空
- 申込後の動作設定: `しない`

### 抽出した作法

- event は current では「申し込み・日程・参加情報の container」として使っている。
- 少なくとも `スキル習得セミナー` では、event config 自体が配信 root ではない。配信連携は別レイヤーで持っている前提で見るべき。

## 5. 商品管理

### 構造

- 一覧: `/product`
- 基本設定: `/product/{product_id}/edit`
- 詳細価格: `/product/{product_id}/detail`

### current 代表例

- `スキルプラス継続利用`
  - 重複購入: 許可
  - 販売上限: 指定なし
  - detail:
    - `クレジットカード払い`
    - `継続課金`
    - `21780円 / 月`
- `【クレカ】スキルプラス スタンダード ユーザー登録`
  - product list:
    - row route: `/product/ZqK5nHoXmlNo/detail`
    - edit route: `/product/ZqK5nHoXmlNo/edit`
  - product edit:
    - 重複購入: `禁止する`
    - 販売上限: `指定しない`
    - 発行事業者: `アドネス株式会社`
    - form action: `POST /product/ZqK5nHoXmlNo`
  - detail edit:
    - detail list route: `/product/ZqK5nHoXmlNo/detail`
    - detail create route: `/product/ZqK5nHoXmlNo/detail/create`
    - detail edit route: `/product/ZqK5nHoXmlNo/detail/PteW7rhpdmo6/edit`
    - form action: `POST /product/ZqK5nHoXmlNo/detail/PteW7rhpdmo6`
    - 名称: `【クレカ一括】スキルプラス スタンダード ユーザー登録`
    - 支払方法: `クレジットカード払い`
    - 決済代行会社: `UnivaPay`
    - 決済連携設定: `【ユニバペイ連携】→アドネス株式会社`
    - 支払回数: `継続課金`
    - 金額: `21780円`
    - 課金サイクル: `毎月`
    - 連携フォームへの表示: `表示する`
    - 表示名: `保証登録（180日後に自動課金）`
    - 表示価格: `無料`
    - 購入後シナリオ: `【クレカ一括】　スキルプラス　スタンダード　ユーザー登録`
    - 購入後アクション: `スキルプラス保管庫解放アクション`
    - 登録時シナリオ: `登録しない`
    - 登録時アクション: `実行しない`
    - display:
      - 表示名: `保証登録（180日後に自動課金）`
      - 表示価格: `無料`
- `AIカレッジ関連：FB広告_7桁_AI合宿_15min【ユニバペイ連携】`
- `AIカレッジ関連：FB広告_7桁_秘密の部屋(OTO)【ユニバペイ連携】`
- `センサーズ関連：FB広告_秘密の部屋(OTO)【ユニバペイ連携】`

### 抽出した作法

- 商品は `事業 / 媒体 / オファー / OTO or メール` まで分けて作ることが多い。
- 同じ `秘密の部屋` でも媒体別、導線別、OTO別に商品が分かれている。
- つまり商品は「商材マスタ」より「決済接続の単位」として切っている。
- 新しく商品を販売するときは、まず `商品本体` を `/product/create` で作り、その後 `detail` 側を `/product/{product_id}/detail/create` で作る前提で考える。
- current では `重複購入 = 許可する` `販売上限 = 指定しない` が代表例だった。
- 継続課金系は detail 側で `クレジットカード払い / 継続課金 / 価格` を持つ。つまり、新規販売時に本当に重要なのは product 本体より detail 設定。
- current の user registration 系では、detail 側で `購入後シナリオ` と `購入後アクション` を決めている。つまり、決済設定だけでなく `購入後に誰をどこへ通すか` まで detail が担う。
- 新規商品を作るときは、最低でも `product create/edit -> detail create/edit -> 購入後シナリオ / 購入後アクション -> site unlock` の4点をセットで確認しないと完成にならない。

## 6. アクション設定

### 構造

- 一覧: `/action`
- 編集: `/action/{action_id}/edit`

### current 代表例

#### `★使用中★　AIカレッジFB：オプトイン　※変更時、宮代に確認※`

- 種類: `webhook`
- URL: `https://utage-action-db-apurikeshiyon.onrender.com/webhook`
- current payload:
  - `%name%`
  - `%mail%`
  - `%phone%`
  - `%referer%`
  - `%funnel_tracking_name%`
  - `%funnel_id%`
  - `%funnel_step_id%`
  - `%funnel_page_id%`
  - `%utm_source%` など

#### `スキルプラス保管庫解放アクション`

- action edit route: `/action/sxJIs4cUbbBz/edit`
- form action: `POST /action/sxJIs4cUbbBz`
- detail 0:
  - 種類: `バンドルコースへ登録`
  - 登録先 site: `スキルプラス - 受講生サイト`
  - 登録先 bundle: `スキルプラス講義保管庫全開放`
  - selected value:
    - `detail[0][type] = bundle_course`
    - `detail[0][bundle_course_id] = 33006`
- detail 1:
  - 種類: `webhook`
  - URL: `https://hooks.zapier.com/hooks/catch/6467520/2ekkd16/`
  - selected value:
    - `detail[1][type] = webhook`
    - `detail[1][url] = https://hooks.zapier.com/hooks/catch/6467520/2ekkd16/`
  - payload sample:
    - `メールアドレス = %mail%`

#### `【プライム】スキルプラス 講義保管庫解放アクション`

- detail 0:
  - 種類: `バンドルコースへ登録`
  - 登録先 site: `スキルプラス - 受講生サイト`
  - 登録先 bundle: `スキルプラス講義保管庫全開放`
- detail 1:
  - 種類: `バンドルコースへ登録`
  - 登録先 site: `スキルプラス - 受講生サイト`
  - 登録先 bundle: `プライム会員限定`
- detail 2:
  - 種類: `webhook`
  - URL: `https://hooks.zapier.com/hooks/catch/6467520/2ekkd16/`

#### `AIカレッジバックエンド：スタンダード`

- 種類: `Googleスプレッドシートへ追記`
- 実行内容:
  - 氏名
  - メール
  - 電話番号
  - referer
  - funnel tracking
  - UTM
  - purchase / subscription / product 情報
  をスプレッドシートへ記録
- 同一 action 内で `バンドルコースへ登録` も併用

#### `SPSエバー導線_事業構築オプトイン`

- 種類: `Googleスプレッドシートへ追記`
- 併用:
  - `webhook`
  - Zapier hook
- つまり、UTAGE オプトイン後に
  - スプレッドシート記録
  - webhook 連携
  を action 側でまとめて実行している

### 抽出した作法

- current の重要アクションは `Googleスプレッドシートへ追記` `webhook` `バンドルコースへ登録`。
- `★使用中★ ... ※変更時、宮代に確認※` の命名は「本番中の重要アクション」だと読める。
- funnel / page / utm の tracking 文字列を action payload に積んでいるので、アクションは単なる次画面遷移ではなく、計測の要でもある。
- 新規導線設定では、page 側に action を刺す前提で考える。特に
  - スプレッドシートへ落とす
  - webhook で外部連携する
  - 講義保管庫を解放する
  の3系統が current の主要パターン。
- `会員サイト解放` は action 単体で閉じない。current の代表例では
  - `product detail` で `購入後シナリオ` と `購入後アクション` を選ぶ
  - その action が `スキルプラス - 受講生サイト` の `スキルプラス講義保管庫全開放` bundle を追加する
  - 同時に Zapier webhook も飛ばす
  という3段構造だった。
- したがって、新規販売で迷わない順番は
  1. `product 本体`
  2. `detail の決済行`
  3. `detail の購入後シナリオ / 購入後アクション`
  4. `action の bundle / webhook`
  5. `site 側の bundle 名`
  の順で確認するのがズレにくい。

### 商品販売設定の current 標準手順

1. `商品管理 -> 商品追加` で `/product/create` を開く
2. `商品名 / 重複購入 / 販売上限 / 発行事業者` を決めて保存する
3. 保存後の `商品詳細管理` で `/product/{product_id}/detail` を開く
4. `追加` から `/product/{product_id}/detail/create` を開く
5. detail で
   - `名称`
   - `支払方法`
   - `決済代行会社`
   - `決済連携設定`
   - `支払回数`
   - `金額`
   - `表示名 / 表示価格`
   を決める
6. 同じ detail で `購入後の動作設定` を決める
   - `購入後シナリオ`
   - `購入後アクション`
   - 必要なら `期限切れメール` や `継続課金停止時` も決める
7. `購入後アクション` で指定した action を `/action/{action_id}/edit` で開く
8. action 側で
   - `バンドルコースへ登録`
   - `webhook`
   - `スプレッドシート追記`
   の有無を確認する
9. `会員サイト -> /site/{site_id}/bundle` で bundle 名が正しいか確認する
10. ここまでそろって初めて `商品設定が完了` とみなす

## 7. 動画管理 / メディア管理

### メディア管理

- 一覧: `/media`
- current folder 例:
  - `AIカレッジ`
  - `AIビジネスコース`
  - `スキルプラス事業部_シーライクス参考`
  - `自己成長セミナー（CTA：スキルプラススタートダッシュ）`

### 動画管理

- 一覧: `/media/video`
- current folder 例:
  - `スキルプラス`
  - `スキルプラス_ショート動画コース`
  - `ライトプラン導線`
  - `秘密の部屋 導線`
  - `ゼロから始めるAI完全攻略3日間合宿`
  - `AIビジネスコース`
  - `生成AI CAMP`

### 抽出した作法

- 動画とメディアは、ファネルや会員サイトで再利用する asset library として独立管理している。
- `導線` `講義` `会員サイト` の中間資産をここに置いているので、ページ修正時は先に media/video 側に asset があるか確認した方が安全。
- メディア管理は `新規アップロード` と `新規フォルダ` が基本操作。
- 動画管理も `新規アップロード` と `新規フォルダ` が基本操作で、一覧カードの footer に `埋め込み用URL` がある。
- メディア管理の upload input は `file[]`。複数ファイルを同時に扱う前提で読む。
- 動画管理の upload input は `file`。アップロード前に `動画形式のファイルのみ` をチェックし、件数チェックも走る。

### 動画管理の UI 操作粒度

#### 一覧で触る基本操作

- `開く`
- `名称変更`
- `サムネイル変更`
- `チャプター設定`
- `分析`
- `ダウンロード`
- `削除`

#### サムネイル変更

- modal で開く
- action: `/video/thumbnail/upload`
- 入力:
  - `file`
  - `video_id`
- 用途:
  - 動画そのものは差し替えず、一覧・埋め込み表示の見え方だけ調整する

#### チャプター設定

- modal で開く
- action: `/video/chapter/update`
- 初回表示時に `/media/video/chapter/load` を叩き、既存チャプターを読み込む
- 入力:
  - `chapter` textarea
  - `video_id`
- placeholder 例:
  - `00:00 はじめに`
  - `07:15 5つの集客メソッド`
  - `15:20 まとめ`
- current の理解:
  - 1行に `時刻 + 見出し` を書く形式
  - 既存値を load して上書き保存する UI
  - つまり、単なる表示文ではなく動画ナビゲーションの設定値として扱う
- 実値例:
  - `20260203_スキルプラスのこれまで_Addnessに繋がるビジョン_この会社がどこに向かうか.mov`
  - `video_id = IVrMCzvoMWMC`
  - `/media/video/chapter/load` の返り値は `chapter = null`
  - つまり、current では長尺動画でもチャプター未設定のものがある

#### 分析

- modal で開く
- 期間指定:
  - `date_from`
  - `date_to`
  - `表示`
- 取得先:
  - `/media/video/analytics`
- 返却データ:
  - `play`
  - `play_unique`
  - `impression`
  - `impression_unique`
  - `play_rates`
  - `play_counts`
  - `play_positions`
- modal 内で見ている値:
  - `インプレッション数`
  - `視聴数`
  - `視聴維持率`
- グラフ:
  - line chart
  - `play_positions` を横軸
  - `play_rates` を縦軸
  - tooltip は `% + counts` を表示
- current の理解:
  - どの位置でどれだけ離脱しているかを見る用途
  - 期間フィルタで recent data だけに絞れる
- 実値例:
  - 動画: `20260203_スキルプラスのこれまで_Addnessに繋がるビジョン_この会社がどこに向かうか.mov`
  - `video_id = IVrMCzvoMWMC`
  - 全期間で
    - `impression = 89`
    - `impression_unique = 44`
    - `play = 61`
    - `play_unique = 36`
  - 維持率は
    - `00:00:00 = 93.88%`
    - `00:24:33 = 30.61%`
    - `00:58:55 = 24.49%`
    - `01:01:22 = 12.24%`
  - つまり、UTAGE の分析画面は「再生されたか」だけでなく、「長尺のどこで落ちるか」まで current に見られる

#### どんな時に触るか

- チャプター設定:
  - セミナーアーカイブ
  - 長尺講義
  - 講義保管庫の視聴体験を上げたいとき
- 分析:
  - 動画ごとの視聴維持率確認
  - 離脱ポイント確認
  - CTA 手前まで見られているかの確認
- サムネイル変更:
  - LP / 会員サイト / 動画一覧でのクリック率や認知を上げたいとき

## 8. アドネス流の UTAGE作法

1. まず `グループ` で置き場所を決める。  
   事業、責任者、媒体で分けられているので、同じ商材でもどこに置くべきかを先に切る。

2. `ファネル` と `配信アカウント` を混同しない。  
   LP や販売ページは funnel。メール / LINE の自動化 root は account。

3. `ページ作成 = デザイン` ではなく `接続作業`。  
   少なくとも `シナリオ / 外部連携フォーム / アクション / 商品 / リダイレクト` の接続まで見て初めて完成。

4. ページを増やすかどうかは、`ページそのものの変更有無` で決める。  
   同じページを使うなら登録経路を増やす。ページの中身が変わるなら新規ページを作る。コンセプトが大きく変わるページも新規ページで分ける。

5. A/Bテストは、基本的に同一ページ内で行う。  
   ただし、クリエイティブごとに最適化した LP を作る場合は A/Bテストではなく別ページにする。FV だけを比較したいときは、FV の A/Bテストとして分ける。

6. `登録経路` はページ分析の単位として扱う。  
   同じページでも登録経路を分ければ、流入元や分析軸を分けて追える。Meta広告 AI / SNS のような大量導線は、まず登録経路を見る。分ける基準は `どこから来たかを知りたいか` であり、広告 ID 単位はその具体例。

7. ページ名は `媒体名 / LP名 / ファネル名` が一目で分かるように付ける。  
   A/Bテスト時は、最後に `何のABテストか` を必ず付ける。FV なら `FV変更` のように、テスト対象を名前で読める状態にする。

8. ページ内要素は、デザイナー作成画像を貼る運用が基本。  
   ボタン CTA も画像として置き、その画像に遷移先リンクやシナリオ設定を載せる。UTAGE 上で細かく組むより、画像と接続設定で作る前提。

9. Short.io は、`無効化リスクがあるリンク` と `クリック分析したいリンク` に使う。  
   特に公式LINEや Lステップ の流入経路は、BAN などで URL が失効しうるため Short.io を優先する。今の主理由は分析よりも、失効時に差し替えられる安全性。

10. `form` は表の導線、`action` は裏側の処理として切り分ける。  
   current では次の見方がズレにくい。  
   - LP の画像 CTA に載っている `form` は、`どのシナリオへ入れるか` `どのページへ送るか` を決める入口  
   - `action` は、その後ろで `スプレッドシート追記` `webhook` `バンドルコース解放` を実行する裏処理  
   - 例1: 書籍 LP や AI Meta LP は、`画像 CTA form + scenario + action + 次ページ` のセット  
   - 例2: スキルプラスのユーザー登録ページは、`form = ユーザー登録`、`action = 講義保管庫解放` の分担  
   - 例3: thanks ページは、`form` も `action` も使わず、`js_body_top` の自動リダイレクトだけで成り立つこともある

11. `商品` と `アクション` は shared library として扱う。  
   funnel の中で都度作るのではなく、既存 current を探してから使う。

12. `講義保管庫解放` は account より action/site/product の連携で見る。  
   受講生体験は site にあり、解放条件は action と product にある。

13. `イベント` は申込 container。配信 root と決めつけない。  
   reminder や follow は他レイヤーにある前提で確認する。

14. 商品を新しく分ける基準は、設定の差分があるかどうか。  
   価格、商品名、流すシナリオ、商品設定画面の構成のどれかが変わるなら、別商品として分ける。

15. 会員サイトの開放先が違う場合も、基本は別商品に寄せる。  
   current 運用では、商品設定の差分が 1 つでもあれば別商品にする思想が強い。`detail` や `action` の差し替えで吸収するより、商品を分けて誤配布や誤解放を防ぐ方を優先する。

16. `★使用中★` や `未使用` の命名を判断材料に使う。  
   current と legacy の仕分けが命名に出ている箇所が多い。

17. page-level の `HTML / CSS / JS` も current 実装の一部として扱う。  
   UTAGE はブロック配置だけでなく、page object の `first_view_css` `css` `js_head` `js_body_top` `js_body` でかなり補正している。

18. UI 操作レベルでは、code 領域は `ページ設定` 配下で分けて触る。  
   current edit 画面の menu は次の構成だった。  
   - `ページ設定 -> デザイン`  
   - `ページ設定 -> 高速表示モード`  
   - `ページ設定 -> カスタムJS`  
   - `ページ設定 -> カスタムCSS`

18. `ページ設定 -> カスタムJS` は、3か所を分けて書く。  
   form action は `/update/js`。画面上の label は次の3つ。  
   - `headタグの最後に挿入するjs` = `js_head`  
   - `bodyタグの最初に挿入するjs` = `js_body_top`  
   - `bodyタグの最後に挿入するjs` = `js_body`  
   note には `scriptタグも含めて記載してください` と出ていた。

19. `ページ設定 -> カスタムCSS` は page 全体の CSS を書く場所。  
   form action は `/update/css`。field は `css` の1つで、note は `styleタグは不要です` だった。

20. `ページ設定 -> デザイン` は code 領域ではなく、page shell 側を触る。  
   form action は `/update/pcwidth`。current UI では次だけが出ていた。  
   - `ページ幅(PC)` = `pc_width`  
   - `ページスワイプ` = `swipe_type`  
   - `ページ枠(PC)` = `border_type`  
   - `背景色` = `background_color`  
   - `背景画像URL` = `background_image_src`  
   - `背景画像スタイル` = `background_image_style`

21. `ページ設定 -> 高速表示モード` は ON/OFF だけを持つ。  
   form action は `/update/speed`、field は `is_high_speed_mode` だけだった。  
   つまり、`高速表示を使うかどうか` と `カスタムCSS / JS をどう書くか` は別メニューで管理されている。

22. current page editor の save form は route ごとに分かれている。  
   representative page で確認できたのは次の 5 本。
   - `基本情報` = `/update/basic`
   - `デザイン` = `/update/pcwidth`
   - `カスタムJS` = `/update/js`
   - `カスタムCSS` = `/update/css`
   - `高速表示モード` = `/update/speed`
   つまり code 領域の current 実装では、`js_head / js_body_top / js_body / css / is_high_speed_mode` をそれぞれ専用 form で保存する。

23. `first_view_css` は current page editor の visible settings としては出てこなかった。  
   representative editor で確認できた current menu は `基本情報 / デザイン / 高速表示モード / メタデータ・検索 / カスタムJS / カスタムCSS / 表示期限 / ワンタイムオファー / パスワード保護 / 広告連携 / ポップアップ / エディター設定` で、`first_view_css` は独立項目として存在しない。  
   また `高速表示モード` panel で visible だった field は `is_high_speed_mode` の切替だけだった。  
   一方で editor runtime の Vue app には `#app.__vue_app__._container._vnode.component.data.page.first_view_css` として実値が載っていた。public page でも `<head>` 冒頭の `<style>` として展開されていた。  
   なので current の理解としては、`first_view_css` は page object / editor runtime 側で保持されるファーストビュー用 CSS で、`css` のような独立 editor ではなく、高速表示の内部保持物として扱われている。

24. `first_view_css` は LP 見た目の補正に使う。  
   AI Meta と スキルプラス Meta の current LP では、`first_view_css` にかなり長い CSS が入っていた。public page ではこれが head 冒頭の style として出ていた。

25. `js_head` は計測タグ置き場として使う。  
   AI Meta では Google Tag Manager と複数 Pixel、スキルプラス Meta では TikTok Pixel が入っていた。

26. `js_body_top` / `js_body` は演出や自動遷移に使う。  
   スキルプラスの自動リダイレクト thanks は `js_body_top` で LIFF へ遷移、共通のファン化動画視聴ページでは `js_body_top` でスクロール演出を実装していた。public page でも `js_body_top` は `<body>` 開始直後に出ていた。

27. code 領域は「全部 JS/CSS に逃がす」のではなく、役割で分ける。  
   current の representative page を踏まえると、使い分けは次の理解がズレにくい。  
   - `first_view_css`
     - LP のファーストビューだけを早い段階で整える  
     - 例: AI Meta LP の FV 補正  
   - `css`
     - page 全体の見た目補正  
     - 例: 余白、ブロック位置、全体色や幅の補正  
   - `js_head`
     - 計測タグや pixel のように、早いタイミングで head に置く必要があるもの  
     - 例: GTM、TikTok Pixel  
   - `js_body_top`
     - body 開始直後に動かす必要があるもの  
     - 例: thanks の自動リダイレクト、初回表示直後の演出  
   - `js_body`
     - 早い初期実行が不要な page interaction  
     - 例: 下部の補助処理、遅延実行でよい振る舞い  

28. `js_body_top` と `js_body` は、優先度で切る。  
   - 直後に動かないと意味が薄いものは `js_body_top`  
   - 遅れても体験が壊れないものは `js_body`  
   current 実装では、スキルプラス thanks の `LIFF 自動遷移` は `js_body_top`、共通ファン化動画のような page 演出も `js_body_top` 側で持っていた。  

29. `first_view_css` は「見た目を少し直したい」時に雑に触る場所ではない。  
   current では editor visible field に出ず、runtime 内部保持のため、次の理解が安全。  
   - LP のファーストビューが大きく崩れていて、しかも高速表示側の見え方を触る必要がある時だけ対象にする  
   - 通常の見た目調整は、まず `デザイン` と `カスタムCSS` で吸収する  

30. current の code 改修判断は、まずこの順で考える。  
   1. `デザイン` だけで足りるか  
   2. page 全体補正なら `カスタムCSS` か  
   3. 計測タグなら `js_head` か  
   4. 自動遷移や初回即時処理なら `js_body_top` か  
   5. それ以外の補助処理なら `js_body` か  
   6. それでも足りず、FV の崩れを高速表示レイヤーで触る必要があるなら `first_view_css` を要確認で扱う  

31. representative public page の code 署名を見ておくと、判断がかなり速くなる。  
   - `スキルプラス thank you redirect = https://school.addness.co.jp/p/E6g12WwMhDWI`  
     - `first_view_css` の style 長はほぼ空  
     - `googletagmanager` が入る  
     - `js_body_top` 系で LIFF 自動遷移がある  
     - つまり `thanks で即 LINE へ送る page` の正解例  
   - `共通ファン化動画 = https://school.addness.co.jp/p/q84ikoiP7swW`  
     - `googletagmanager` は入る  
     - LIFF 自動遷移はない  
     - つまり `コンテンツを見せる page` では、同じ shared page でも redirect を前提にしない  
   - `AI Meta LP = https://school.addness.co.jp/page/TB6cCsrphNCi`  
     - `first_view_css` の style 長が大きい  
     - `googletagmanager` が入る  
     - 自動遷移はない  
     - つまり `FV 補正 + 計測` が主役の LP 例  
   - `センサーズ 15分OTO = https://school.addness.co.jp/p/ggDUz4esErGX`  
     - `googletagmanager` が 2 本入る  
     - LIFF 直遷移や short.io は見えない  
     - つまり `即 LINE へ飛ばす page` ではなく、UTAGE 内で次の説明や動画を見せる content page と読む方がズレにくい  
   - `センサーズ ロードマップ作成会 main = https://school.addness.co.jp/p/1hHdsZDzq7hp`  
     - `googletagmanager` が 2 本入る  
     - HTML 内には `follow=@804mrsmd&lp=QBbEoM` が 3 回前後埋まっている  
     - つまり page-level 自動遷移ではなく、visible CTA 側に停止中 LIFF が残っている例  
   - `センサーズ ロードマップ作成会 variant = https://school.addness.co.jp/page/vQ8ZuYjSpxuh`  
     - `googletagmanager` が 2 本入る  
     - HTML 内には `follow=@804mrsmd&lp=aYvC7j` が 3 回前後埋まっている  
     - main と同じ役割の variant page でも、CTA に停止中 LIFF が直書きされていることがある  

32. good / bad は「どこに書くか」で判断する。  
   - 良い  
     - thanks で `LIFF 自動遷移` を `js_body_top` に置く  
     - LP の `FV 崩れ` を `first_view_css` で吸収する  
     - GTM や pixel を `js_head` に置く  
     - content page は `計測 + CTA` を主にし、不要な redirect を入れない  
   - 悪い  
     - 軽い余白修正まで `first_view_css` に逃がす  
     - redirect が不要な content page に `js_body_top` で強制遷移を入れる  
     - 計測タグも redirect も animation も全部 `js_body` に詰める  
     - ロードマップ作成会のような CTA page で、停止中 LIFF を visible button 側に直書きしたまま残す  

## 9. まだ未確定の点

- relevant funnel の各ページ名一覧を、この文書にはまだ全件転記していない。
- hidden / legacy page や old copy が current とどこでつながるかは、必要な導線ごとに追加確認が必要。
- UTAGE 内 relevant account では `リッチメニュー` は 0 件だったが、今後新規でどちらに持つべきかは案件ごとに `UTAGE / Lステップ` を確認した方が安全。

## 10. 良い / 悪い / NG 判断ログ（暫定）

### 良い

- ページそのものが変わるときだけ新規ページを作る
- 同じページに流すだけなら `登録経路` を増やす
- クリエイティブごとに最適化する LP は、A/B テストではなく別ページにする
- ボタン CTA は画像として置き、`form / scenario / action / 遷移先` をその上で接続する
- 公式LINE や Lステップ 流入経路のように失効リスクがあるリンクは Short.io を使う
- 会員サイト修正は、`bundle -> course -> lesson` の順に見る
- 商品設定は `detail` まで見て初めて完成と考える
- code 改修は、まず `デザイン / カスタムCSS / js_head / js_body_top / js_body` のどこかで吸収し、`first_view_css` は最後の要確認に回す

### 悪い

- 広告 ID の違いだけでページを複製する
- current / legacy の見極めなしに旧スクール名の asset をそのまま流用する
- 会員サイトを本文から先に触って、bundle 解放条件を後で確認する
- `商品本体` だけ見て detail の支払方法や回数を確認しない
- `visible button` と `js 自動遷移` が同居している page を、どちらが主導線か確認せずに直す
- 体験の役割を分けずに、計測タグも演出も自動遷移も全部 `js_body` へ寄せる
- テキストリンクやハイパーリンクの表示文字列だけ見て、内部 URL を確認しない

### NG

- 失効リスクがある LINE / LIFF を直リンクのまま本番導線に置く
- 停止中 LINE や old LIFF を current page に残したまま公開する
- `★使用中★` アクションを、影響範囲を見ずに触る
- `未使用` `コピー` `旧` と明示された site / page / product を、current の正本として扱う
- current の page で `登録経路` を使うべきところを、安易に別ページで増やして分析軸を壊す
- `first_view_css` の保存経路や内部保持を理解しないまま、本番 page で直接いじる
- ボタン画像やテキストに URL を設置したあと、実際に押して最終遷移先を確認しない
- short.io を使う導線なのに、UTAGE 側の見た目だけ見て `正しい` と判断する

### 要確認で止めるべきもの

- hidden / legacy landing や old page と current の接続点
- `first_view_css` の生成や保存経路そのものを変える改修
- 商品と detail のどちらで吸収すべきか迷うケース
- 会員サイトの新設と既存 site 追加のどちらが正しいか曖昧なケース

## 11. 今後の実務で見ればいい場所

### 新しい funnel を作るとき

- まず `funnel group`
- 次に representative funnel の共通設定
- その後 page edit で `scenario / form / action / product`

### 新しい mail / LINE 配信を作るとき

- まず `account group`
- 次に representative scenario の group と命名
- LINE なら `スキルプラス【公式】` の template / autoreply を見る

### 講義保管庫や会員サイトを触るとき

- `site`
- `product`
- `action`

この 3 つをセットで見る。
