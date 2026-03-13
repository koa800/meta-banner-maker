# UTAGE code 領域 exact メモ

## current menu

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

## current save route

- `カスタムJS` = `/update/js`
- `カスタムCSS` = `/update/css`
- `高速表示モード` = `/update/speed`

## `カスタムJS` の current 分担

- `headタグの最後に挿入するjs` = `js_head`
- `bodyタグの最初に挿入するjs` = `js_body_top`
- `bodyタグの最後に挿入するjs` = `js_body`

## `first_view_css` の current 理解

- visible な独立 menu ではない
- editor runtime の Vue 側に `data.page.first_view_css` として保持される
- public page では `<head>` 冒頭の style として展開される
- つまり `高速表示レイヤーの FV 補正` として読む

## Addness 側での重要解釈

- LP の FV 崩れは `first_view_css` を疑う価値がある
- thanks の自動遷移はまず `js_body_top`
- 計測タグは `js_head`
- page 全体補正は `カスタムCSS`
- content page は `first_view_css` より visible CTA と `js_body_top` を先に見る
