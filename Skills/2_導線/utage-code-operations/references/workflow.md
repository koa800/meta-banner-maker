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

## exact に触る順番

1. 直したい対象を `FV / 計測 / 自動遷移 / page 全体補正` のどれかで固定する
2. `基本情報` と visible CTA で解決しないか先に見る
3. `ページ設定`
4. `カスタムJS` か `カスタムCSS`
5. 必要なら runtime snapshot
6. `プレビュー`
7. 公開URLの実挙動

つまり、最初から code 領域を触らない。

## 30秒レビューの順番

1. 何を直したいかを `FV / 計測 / 自動遷移 / page 全体補正` で切る
2. visible 設定で解決しないか先に見る
3. `js_head / js_body_top / js_body / css / first_view_css` の候補を 1 つに絞る
4. runtime snapshot が必要か判断する
5. 保存後にどの実挙動で確かめるか決める

## 保存前後の最小チェック

### 保存前

- 何を直したいのかを `FV / 計測 / 自動遷移 / page 全体補正` のどれかで言える
- `first_view_css / js_head / js_body_top / js_body / css` のどこを触るべきか理由付きで説明できる

### 保存後

- runtime snapshot で対象 key が変わっていることを確認する
- 公開ページで実際の見た目や遷移が意図通りか確認する

## ここで止めて確認する条件

- visible 設定だけで直るのか、code 領域まで行くべきか判断できない
- `first_view_css` を触りたいが、目的が FV 崩れではない
- `js_head / js_body_top / js_body` のどこに置くべきか説明できない
- 計測タグと自動遷移を同じ欄に入れたくなっている
- runtime snapshot と公開ページの実挙動が食い違う

## 完成条件

- 直したい対象を `FV / 計測 / 自動遷移 / page 全体補正` のどれかで固定できている
- `first_view_css / js_head / js_body_top / js_body / css` のどこを触るか理由付きで説明できる
- 保存後に runtime snapshot と公開ページの実挙動の両方で整合が取れている
- `first_view_css` を主因にする場面と、まず他を疑う場面を分けて言える

## 保存前の最小チェック

- page type や商品の役割を 1 文で言える
- 主CTA、遷移先、action の主従が切れている
- 実 click で確認する前提になっている

## 保存後の最小チェック

- preview または公開ページで実挙動を確認した
- 商品、detail、action、bundle の接続を確認した
- CTA の最終遷移先が意図どおり
