# UTAGE content review workflow

## 使うタイミング

- 既存の LP や thanks を benchmark として分解したい時
- 新規ページを作る前に current quality を読みたい時
- 作ったページが意図した顧客体験になっているか確認したい時

## 30秒レビューの順番

1. page type を切る
2. 誰が来るページかを言う
3. promise を 1 文で言う
4. 変えたい認識を 1 文で言う
5. 主CTA を 1 つに切る
6. `form / action / 商品 / 遷移先` を確認する
7. 実 click で最終挙動を見る

## page type ごとの重点

### LP

- first view の promise
- 誰向けか
- 主CTA
- `form`
- `シナリオ`
- `アクション`
- 次ページ

### thanks

- 次に何をしてほしいか
- visible CTA か自動遷移か
- LINE や short.io への橋渡しが滑らかか

### content page

- 何を理解させたいか
- 動画やテキストの役割
- CTA の位置と強さ

### ユーザー登録

- `商品詳細管理`
- `購入後アクション`
- `開放するバンドルコース`
を強く確認する

## code 領域の見方

- `カスタムCSS`
  - 見た目補正
- `カスタムJS`
  - 計測、補助挙動、自動遷移
- `first_view_css`
  - LP の FV を強く作る時の主戦場
  - thanks や content page では、まず主因にしない

## 最低限の output

- page type
- 目的
- promise
- 変えたい認識
- 起こしたい行動
- 良い点
- 弱い点
- 再現すべき点
- 変えるならどこか
