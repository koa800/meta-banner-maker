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
- まずここを疑うのは `LP の FV 崩れ / FV の見え方調整` の時
- `thanks` や `content page` では、まず `js_body_top` や visible CTA を先に疑う

## runtime 補助

- `python3 System/scripts/utage_page_runtime_snapshot.py <edit URL>`
- 既存の edit タブが開いていれば raw CDP でその tab から読む
- tab が無い時だけ新規 page を開く fallback を使う
- 抜ける代表値
  - `is_high_speed_mode`
  - `first_view_css`
  - `css`
  - `js_head`
  - `js_body_top`
  - `js_body`
- visible settings だけで判断せず、runtime と公開ページで整合を取る

## Addness 側での重要解釈

- LP の FV 崩れは `first_view_css` を疑う価値がある
- thanks の自動遷移はまず `js_body_top`
- 計測タグは `js_head`
- page 全体補正は `カスタムCSS`
- content page は `first_view_css` より visible CTA と `js_body_top` を先に見る

## 保存前後の最小チェック

### 保存前

- 何を直したいのかを `FV / 計測 / 自動遷移 / page 全体補正` のどれかで言える
- `first_view_css / js_head / js_body_top / js_body / css` のどこを触るべきか理由付きで説明できる

### 保存後

- runtime snapshot で対象 key が変わっていることを確認する
- 公開ページで実際の見た目や遷移が意図通りか確認する
