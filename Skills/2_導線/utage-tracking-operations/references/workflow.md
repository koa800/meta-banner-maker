# UTAGE 登録経路 workflow

## current で固定している事実

- representative funnel
  - `AI：メインファネル_Meta広告`
  - funnel id = `TXUOxBYkYr9e`
- 主要 route
  - `データ(合算) = /funnel/TXUOxBYkYr9e/data`
  - `データ(日別) = /funnel/TXUOxBYkYr9e/data/daily`
  - `登録経路 = /funnel/TXUOxBYkYr9e/tracking`
  - `追加 = /funnel/TXUOxBYkYr9e/tracking/create`
  - `グループ管理 = /funnel/TXUOxBYkYr9e/tracking/group`
  - `表示順変更 = /funnel/TXUOxBYkYr9e/tracking/sort`

## live で確認した exact 手順

1. funnel を開く
2. `登録経路`
3. `追加`
4. create 画面で visible field
   - `グループ`
   - `管理名称`
   - `ファネルステップ`
   - `ページ`
5. 保存
6. `データ(合算)` と `データ(日別)` で `登録経路` 条件を確認
7. 必要なら `グループ管理`
8. 必要なら `表示順変更`

## 読み方

- `登録経路` は広告IDだから必ず切る機能ではない
- 基本思想は `どこからユーザーが訪れたかを知りたい時に切る`
- 同じページを使うなら、まずページ複製ではなく `登録経路` を検討する
