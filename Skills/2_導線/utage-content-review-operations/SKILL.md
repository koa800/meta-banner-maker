---
name: utage-content-review-operations
description: UTAGE の LP、thanks、content page、ユーザー登録ページを、promise、認識変換、CTA、遷移、コード差し込みまで含めてレビューする skill。既存ページの何が良くて何が悪いかを分解したい時、ページ作成前に benchmark を読みたい時、作成したページが意図した顧客体験になっているか確認したい時に使う。
---

# utage-content-review-operations

## Overview

UTAGE の `ページ` を、見た目ではなく `コンテンツ` として分解する skill です。

ここでいう `コンテンツ` は、`コミュニケーションの手段であり、ユーザーをこちらが意図した認識に変換するもの` です。したがってレビューでは、

- 何の promise を渡しているか
- 何の認識を変えたいか
- 何を押させるか
- そのために `画像 / 見出し / テキスト / 動画 / CTA / 遷移` をどう使っているか

を中心に見る。

Addness 固有の representative funnel、page 名、current 例は `Master/addness/utage_structure.md` を正本にする。この skill は、どの案件でも再利用できる `レビューの型` だけを持つ。

## ツールそのものの役割

UTAGE の `ページ` は、LP、thanks、content page、ユーザー登録ページなどの顧客接点を作り、登録、購入、視聴、会員化を成立させる機能です。

## アドネスでの役割

アドネスでは、UTAGE の `ページ` は `認識変換と行動を接続する execution system` として使う。したがってレビューでは、

- きれいか
- 画像があるか

より先に、

- 何を理解させたいか
- 何を信じさせたいか
- 何を押させたいか
- 次の接点へどう渡すか

を確認する。

## 役割

既存ページを分解して、

- 何が良いか
- 何が弱いか
- どの要素を再現すべきか
- どこを変えると顧客体験が良くなるか

を、実装前に判断できる状態を作る。

## ゴール

次を迷わず言語化できる状態を作る。

- このページは何のために存在するか
- どの page type か
- 変えたい認識は何か
- 主CTA は何か
- promise と CTA が一致しているか
- `登録経路 / form / action / 商品 / 遷移先` の接続が、その content と一致しているか

## 必要変数

- page type
  - `LP`
  - `thanks`
  - `content page`
  - `ユーザー登録`
- 対象ファネル
- 流入元
- promise
- 変えたい認識
- 主CTA
- 次の接点
- `登録経路 / form / action / 商品 / 遷移先`
- `カスタムCSS / カスタムJS / first_view_css` の有無

## レビュー前の最小チェック

- page type を 1 つに切っている
- promise を 1 文で言える
- 主CTA を 1 つに切っている
- 何を変えるためのページか説明できる
- 実 click で最終挙動を確認する前提になっている

## レビューの順番

1. `このページは何のページか`
2. `誰が来るページか`
3. `何を約束しているか`
4. `何の認識を変えたいか`
5. `何を行動させたいか`
6. 主CTA は何か
7. `form / action / 商品 / 遷移先` がその役割と一致しているか
8. 実際に押した時の挙動が promise と一致しているか

## page type ごとの見る場所

### `LP`

- first view の promise
- 誰向けか
- 主CTA
- `form`
- `シナリオ`
- `アクション`
- 次ページ

### `thanks`

- `ありがとう` だけで終わっていないか
- 次に何をしてほしいか明確か
- visible CTA か自動遷移か
- LINE や short.io への橋渡しが滑らかか

### `content page`

- 何を理解させたいか
- 動画やテキストの役割
- CTA の位置と強さ
- script 側 CTA と visible CTA のどちらが主役か

### `ユーザー登録`

- 認識変換より `登録を成立させる` が主役
- `商品詳細管理`
- `購入後アクション`
- `開放するバンドルコース`
を強く確認する

## 良い / 悪いの判断軸

### 良い

- page type に役割が合っている
- first view の promise が明確
- 主CTA が 1 つに切れている
- `form / action / 商品 / 遷移先` が content と一致している
- 次の接点へ文脈が滑らか

### 悪い

- 見た目はきれいだが主CTA が曖昧
- promise と遷移先がずれる
- LP なのに認識変換より説明不足で離脱しやすい
- thanks なのに次行動が弱い
- `ユーザー登録` なのに `商品詳細管理 / 購入後アクション / バンドルコース` を見ずに判断している

## code 領域の読み方

### `カスタムCSS`

- 見た目補正
- builder だけで足りない調整

### `カスタムJS`

- 計測
- バリデーション
- 自動遷移
- 補助的な挙動

### `first_view_css`

- LP の FV を強く作る時の主戦場
- thanks や content page では、まずここを主因にしない

## exact なレビュー手順

1. page list の対象行を固定する
2. `edit`
3. `preview`
4. visible promise を確認
5. 主CTA を確認
6. `form / action / 商品 / 遷移先` を確認
7. 必要なら runtime snapshot
8. 実 click
9. 最終挙動を確認

## current UI で先に固定するラベル

- `ページ一覧`
- `プレビュー`
- `ページ設定`
- `基本情報`
- `デザイン`
- `カスタムCSS`
- `カスタムJS`
- `高速表示モード`
- `保存`

## output の型

最低限、次の 9 行に落とす。

- page type
- 目的
- promise
- 変えたい認識
- 起こしたい行動
- 良い点
- 弱い点
- 再現すべき点
- 変えるならどこか

## NG

- 見た目だけで評価する
- `ページ一覧の行名` と `公開 URL` と `内部タイトル` を混ぜて説明する
- 実 click をせずに正誤判断する
- LP / thanks / content page / ユーザー登録 の役割を混ぜる
- Addness 固有の具体 page 名を一般 skill に焼き込む

## 正誤判断

正しい状態

- page type を 1 つに切れる
- promise と CTA の関係を説明できる
- `form / action / 商品 / 遷移先` を content と一緒に読める
- 実 click まで確認している
- 次の接点へどう渡るか言える

間違った状態

- `なんとなく LP として良い`
で終わる
- code 領域だけ見て判断する
- 遷移先や action を見ずに content だけを benchmark にする

## ここで止めて確認する条件

- page type が切れない
- main CTA が複数あって主従が分からない
- promise と最終遷移先が一致しているか判断できない
- `カスタムJS` が多く、visible UI だけでは主挙動が読めない
- `ページ一覧の行名` を固定せずに、公開 URL や内部タイトルから先に話し始めそう

## References

- Addness 固有の current 例は `Master/addness/utage_structure.md`
- 実装手順は `Skills/2_導線/utage-page-operations`
