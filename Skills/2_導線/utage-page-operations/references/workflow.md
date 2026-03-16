# UTAGE ページ運用 exact メモ

## current でよく使う route

- ファネル一覧: `/funnel`
- ページ一覧: `/funnel/{funnel_id}/page`
- ページ編集: `/funnel/{funnel_id}/page/{page_id}/edit`
- `登録経路` 一覧: `/funnel/{funnel_id}/tracking`
- `登録経路` 追加: `/funnel/{funnel_id}/tracking/create`
- data: `/funnel/{funnel_id}/data`
- data daily: `/funnel/{funnel_id}/data/daily`
- tracking: `/funnel/{funnel_id}/tracking`

## representative route

- AI 代表
  - ファネル: `AI：メインファネル_Meta広告`
  - ページ一覧: `/funnel/TXUOxBYkYr9e/page`
  - ページ編集: `/funnel/TXUOxBYkYr9e/page/GaXTNREaZQ5C/edit`
  - preview: `/page/GaXTNREaZQ5C?preview=true`
  - runtime helper 実測
    - `title = AIカレッジ_FB広告_optin2_長め_みかみ式_緑LPテイスト_FV AI美女2_分野を問わない_累計10万人_お詫び`
    - `is_high_speed_mode = 1`
    - `first_view_css` あり
    - `css = null`
    - `js_head / js_body_top / js_body` あり
    - `js_head` には `Google Tag Manager / Meta Pixel / TikTok Pixel`
    - `js_body` には `email domain typo check / Yahoo メール弾き`
- スキルプラス代表
  - ファネル: `スキルプラス_Meta広告`
  - ページ一覧: `/funnel/d0imwFvGWVbA/page`
  - ページ編集: `/funnel/d0imwFvGWVbA/page/lvy1yBHf1VvZ/edit`
  - preview: `/page/lvy1yBHf1VvZ?preview=true`
  - runtime helper 実測
    - `title = メインLP_みかみさんFV_オレンジボタン_要素並び替え_特典(30億社長)_新テイスト荻野_AMAZON_CTAテスト②_ベネフィット追加_権威東北大学_全CR配信`
    - `is_high_speed_mode = 1`
    - `first_view_css` あり
    - `css = null`
    - `js_head` あり
    - `js_body_top / js_body = null`
    - `js_head` には `TikTok Pixel / Meta Pixel / 著名人用 Meta Pixel`

## 公開ページの署名を読む時の current 基準

- helper
  - `python3 System/scripts/utage_public_page_signature.py <public_url>`
- まず見る値
  - `first_style_len`
  - `script_tag_count`
  - `shortio_url_count`
  - `follow_token_count`
  - `auto_redirect_hits`
- 読み方
  - `follow_token_count > 0` かつ `auto_redirect_hits` に `liff.line.me`
    - `LINEへ送るページ` の可能性が高い
  - `first_style_len` が大きく、`googletagmanager` があり、`follow_token_count = 0`
    - `FV補正が厚いLP` を疑う
  - `script_tag_count` が多くても、`follow_token_count = 0` かつ short.io / LIFF が無い
    - まず `content / transition page` を疑う
  - `auto_redirect_hits` に `location.href` があるだけ
    - それだけでは redirect page の根拠にしない
  - `first_style_len = 0` で `script_tag_count` も少なく、redirect も short.io も LIFF も無い
    - `コンテンツを見せるだけの page` を疑う

## representative public page の読み方

- `スキルプラス thank you redirect = https://school.addness.co.jp/p/E6g12WwMhDWI`
  - `follow=%40` あり
  - `liff.line.me` あり
  - `js_body_top` で自動遷移させる thank you 型
- `共通ファン化動画 = https://school.addness.co.jp/p/q84ikoiP7swW`
  - `first_style_len = 0`
  - `script_tag_count = 6`
  - redirect / short.io / LIFF なし
  - content page と読む
- `AIキャンプ campaign CTA page = https://school.addness.co.jp/p/nWmuzGZoQEdD`
  - `follow_token_count = 1`
  - `auto_redirect_hits = liff.line.me`
  - LINE 遷移型
- `センサーズ 15分OTO = https://school.addness.co.jp/p/ggDUz4esErGX`
  - `script_tag_count = 17`
  - `auto_redirect_hits = location.href`
  - `follow=%40 = 0`
  - short.io / LIFF なし
  - redirect page ではなく content / transition page と読む

## 30秒レビューの順番

1. `ファネル`
2. `ページ一覧`
3. 対象行の `管理名称`
4. この page の役割
   - `LP`
   - `thanks`
   - `ユーザー登録`
   - `content`
5. 主CTA
6. `シナリオ`
7. `アクション`
8. 遷移先
9. 必要なら `ページ設定`
10. 公開ページで主CTAを押す

## page edit の current UI

### editor 上部で最初に確認するラベル

- `戻る`
- `PC`
- `SP`
- `ページ設定`
- `AIアシスト`
- `要素一覧`
- `プレビュー`
- `保存`

スキルプラス代表例では、これに加えて `ポップアップ` が見える。

### settings menu

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

### `基本情報`

- `管理名称`
- `ページタイトル`

### `デザイン`

- `ページ幅(PC)`
- `ページスワイプ`
- `ページ枠(PC)`

### `高速表示モード`

- `利用しない`
- `利用する（β版機能）`

### `カスタムJS`

- `headタグの最後に挿入するjs`
- `bodyタグの最初に挿入するjs`
- `bodyタグの最後に挿入するjs`

### `カスタムCSS`

- `css`

## page edit の exact 作業順

1. `ファネル`
2. `ページ一覧`
3. 対象行の `管理名称`
4. `編集`
5. `基本情報`
6. visible 主CTA
7. `ページ設定`
8. `シナリオ`
9. `アクション`
10. 遷移先
11. `プレビュー`
12. 公開URLの実 click

つまり、見た目の調整より先に
- この page は何の役割か
- 何を押させるか
- 押した後にどこへ送るか
を固定する。

## representative の読み方

### `LP`

- 主CTA
- `form`
- `シナリオ`
- `アクション`
- 次ページ

### `thanks`

- visible CTA
- `bodyタグの最初に挿入するjs`

### `ユーザー登録`

- `シナリオ`
- `アクション`
- `商品`
- 会員サイト解放

## 保存前の最小チェック

- その page の役割を `LP / thanks / ユーザー登録 / content` のどれかで言える
- 主CTAが何か言える
- `シナリオ / アクション / 遷移先` のうち、何を触るべき page か分かっている
- `登録経路` を増やす理由がある
- `カスタムJS / カスタムCSS / first_view_css` を触る理由がある
- `基本情報` と `ページ設定` だけで足りるのか、code 領域まで触るのかを言える

## 保存後の最小チェック

- `プレビュー` か公開URLで主CTAを押す
- 想定した `short.io / LIFF / UTAGE 次ページ` に着地する
- `bodyタグの最初に挿入するjs` を使う page は、自動遷移の実挙動まで確認する
- 表示文字列ではなく、実際の hyperlink / button action を確認する
- 変更対象が `登録経路` なら `データ(合算)` または `データ(日別)` で見え方も確認する
- `短縮URL` を使う page は、`short.io -> final destination` まで確認する

## ここで止めて確認する条件

- 既存 page を直すべきか、新規 page を増やすべきか曖昧
- `登録経路` で足りるのか、page を分けるべきか曖昧
- current representative と違う code 領域を触ろうとしている
- 主CTA が `LINE / フォーム / 購入 / スクロール / ポップアップ` のどれか判定できない
- 公開ページでの実 click と editor 上の設定が食い違う
- `基本情報 / デザイン / 高速表示モード` で直るのか、`カスタムJS / カスタムCSS / first_view_css` まで触るべきか判断できない
- どの code 領域を主因として触るか 1 つに絞れない

## code 領域を触る前の最小チェック

1. `基本情報 / デザイン / 高速表示モード` だけでは足りない理由を言える
2. 触る候補が
   - `カスタムCSS`
   - `カスタムJS`
   - `first_view_css`
   のどれか 1 つに絞れている
3. 公開ページで intended でない実挙動を再現済み
4. `short.io / direct LIFF / UTAGE 次ページ`
   の接続問題ではないと切れている

## `登録経路`

- 同じページに対して複数作れる
- 目的は `どこから来たかを分けて見ること`
- `広告IDだから必ず切る` ではない
- `流入元を切り分けて見たい時に作る分析軸` として扱う
- 代表値
  - `Meta広告-AI-LP1-CR01015`
  - `Meta広告-スキルプラス-LP4-CR00001`

## 保存前後の最小チェックリスト

### 保存前

- この page の役割を `LP / thanks / ユーザー登録 / content` のどれかで言える
- 主CTAが何か言える
- `シナリオ / アクション / 遷移先` がどこにあるか言える
- `登録経路` を増やす理由を説明できる

### 保存後

- `プレビュー` か公開URLで主CTAを押す
- 想定した `short.io / LIFF / UTAGE 次ページ` に着地する
- `bodyタグの最初に挿入するjs` を使う page は、自動遷移の実挙動まで確認する
- 表示文字列ではなく実際の hyperlink / button action を確認する

## exact smoke 手順

1. 対象 `ファネル`
2. `ページ一覧`
3. 対象行の `編集`
4. `基本情報`
5. visible 主CTA
6. `シナリオ`
7. `アクション`
8. `遷移先`
9. 公開ページで主CTAを押す
10. final destination まで確認

## 注意

- `location.href` や `setTimeout` の文字列だけで redirect page と断定しない
- `見えている URL` と `実際の hyperlink` は別物になりうる
- まず実 click、次に short.io、次に public signature、その後に edit/runtime を見る

## Addness 側で見るべき補足

- どの group に置くか
- current / legacy の読み分け
- `登録経路` を切る目的
- 画像CTA中心の運用
- short.io を使うか

## 完成条件

- 対象 page を `LP / thanks / ユーザー登録 / content` のどれかで固定できている
- 主CTA と `シナリオ / アクション / 遷移先` の関係を説明できる
- `登録経路` を作るか page を増やすかの判断理由を言える
- `プレビュー` または公開URLで主CTAの実挙動を確認している
- `short.io` を使う page は final destination まで確認している
