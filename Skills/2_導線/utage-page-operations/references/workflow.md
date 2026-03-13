# UTAGE ページ運用 exact メモ

## current でよく使う route

- ファネル一覧: `/funnel`
- ページ一覧: `/funnel/{funnel_id}/page`
- ページ編集: `/funnel/{funnel_id}/page/{page_id}/edit`
- data: `/funnel/{funnel_id}/data`
- data daily: `/funnel/{funnel_id}/data/daily`
- tracking: `/funnel/{funnel_id}/tracking`

## page edit の current UI

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

## `登録経路`

- 同じページに対して複数作れる
- 目的は `どこから来たかを分けて見ること`
- 代表値
  - `Meta広告-AI-LP1-CR01015`
  - `Meta広告-スキルプラス-LP4-CR00001`

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

## Addness 側で見るべき補足

- どの group に置くか
- current / legacy の読み分け
- `登録経路` を切る目的
- 画像CTA中心の運用
- short.io を使うか
