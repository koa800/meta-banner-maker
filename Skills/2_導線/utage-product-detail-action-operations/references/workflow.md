# UTAGE 商品・detail・action exact メモ

## current でよく使う route

- 商品一覧: `/product`
- 商品追加: `/product/create`
- 商品詳細管理: `/product/{product_id}/detail`
- detail 追加: `/product/{product_id}/detail/create`
- action 編集: `/action/{action_id}/edit`
- 会員サイト一覧: `/site`
- バンドルコース一覧: `/site/{site_id}/bundle`
- bundle 編集: `/site/{site_id}/bundle/{bundle_id}/edit`

## 商品本体

`商品追加` で最初に決めるもの。
- `商品名`
- `重複購入`
- `販売上限`
- `発行事業者`

## detail

`商品詳細管理 -> 追加` で決めるもの。
- `名称`
- `支払方法`
- `決済代行会社`
- `決済連携設定`
- `支払回数`
- `金額`
- `表示名`
- `表示価格`
- `購入後シナリオ`
- `購入後アクション`

## `購入後アクション` の見方

まず `アクション設定` で次を確認する。
- `バンドルコースへ登録`
- `webhook`
- `Googleスプレッドシートへ追記`

## bundle の見方

`会員サイト > バンドルコース` で確認する。
- bundle 名
- その bundle に入る course 群

bundle 名だけで判断しない。

## exact smoke 手順

1. `商品管理`
2. 対象行
3. `商品詳細管理`
4. 対象 detail
5. `購入後アクション`
6. `アクション設定`
7. `会員サイト > バンドルコース`
8. 解放先 course まで確認

## Addness 側で見るべき補足

- どの group の商品か
- current / legacy の読み分け
- 会員サイト解放先が変わるなら原則別商品
- `detail + action` が本体
