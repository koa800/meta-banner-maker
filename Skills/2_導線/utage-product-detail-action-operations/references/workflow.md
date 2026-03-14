# UTAGE 商品・detail・action exact メモ

## current でよく使う route

- 商品一覧: `/product`
- 商品追加: `/product/create`
- 商品編集: `/product/{product_id}/edit`
- 商品詳細管理: `/product/{product_id}/detail`
- detail 追加: `/product/{product_id}/detail/create`
- detail 編集: `/product/{product_id}/detail/{detail_id}/edit`
- action 編集: `/action/{action_id}/edit`
- 会員サイト一覧: `/site`
- バンドルコース一覧: `/site/{site_id}/bundle`
- bundle 編集: `/site/{site_id}/bundle/{bundle_id}/edit`

## representative route

- detail 代表 1
  - 商品: `スキルプラス継続利用`
  - 商品編集: `/product/YrrE8PeeH7eV/edit`
  - detail 一覧: `/product/YrrE8PeeH7eV/detail`
  - detail 編集: `/product/YrrE8PeeH7eV/detail/kj2InFQxaIcr/edit`
- detail 代表 2
  - 商品: `【クレカ】スキルプラス スタンダード ユーザー登録`
  - 商品編集: `/product/ZqK5nHoXmlNo/edit`
  - detail 一覧: `/product/ZqK5nHoXmlNo/detail`
  - detail 編集: `/product/ZqK5nHoXmlNo/detail/PteW7rhpdmo6/edit`
- action 代表
  - `スキルプラス保管庫解放アクション`
  - `/action/sxJIs4cUbbBz/edit`
- bundle 代表
  - `スキルプラス講義保管庫全開放`
  - `/site/BQys60HDeOWP/bundle/m5HcpQJqJ6MA/edit`

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

detail 代表 2 では、少なくとも次が current 実値として確認できている。
- `支払方法 = クレジットカード払い`
- `決済代行会社 = UnivaPay`
- `支払回数 = 継続課金`
- `表示名 = 保証登録（180日後に自動課金）`
- `表示価格 = 無料`
- `購入後シナリオ = 【クレカ一括】　スキルプラス　スタンダード　ユーザー登録`
- `購入後アクション = スキルプラス保管庫解放アクション`

## detail を見る時の current ラベル

- `名称`
- `支払方法`
- `支払回数`
- `価格`
- `オーダーバンプ`
- `表示/非表示`

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

## 保存前後の最小チェックリスト

### 保存前

- `商品本体 / 商品詳細管理 / 購入後アクション / バンドルコース` を別物として説明できる
- 何が変わるから別商品にするのか説明できる
- 会員サイト解放先が正しい bundle まで言える

### 保存後

- detail 一覧に `名称 / 支払方法 / 支払回数 / 価格 / オーダーバンプ / 表示/非表示` が意図通り出ている
- `購入後アクション` の中で `webhook / Googleスプレッドシートへ追記 / バンドルコースへ登録` のどれが使われているか確認する
- bundle 編集画面で、解放したい course 名まで確認する

## Addness 側で見るべき補足

- どの group の商品か
- current / legacy の読み分け
- 会員サイト解放先が変わるなら原則別商品
- `detail + action` が本体
