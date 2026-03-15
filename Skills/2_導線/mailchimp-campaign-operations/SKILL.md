---
name: mailchimp-campaign-operations
description: Mailchimpの `Campaign Manager` で単発の regular campaign を作成、編集、検証する skill。Mailchimpで今回だけの promotion や segment 配信をしたい時、対象条件を切って 1 回だけ送りたい時、本文と main CTA を exact に検証したい時に使う。
---

# mailchimp-campaign-operations

## Overview

Mailchimp の `Campaign Manager` で、単発の `regular` campaign を exact 手順で扱う skill です。

Addness 固有の current representative、main CTA ルール、良い / 悪いの判断は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill は、どの案件でも再利用できる exact 手順だけを持つ。

## ツールそのものの役割

`Campaign` は、対象 audience や segment を切って、その時だけ送る単発配信の機能です。

## アドネスでの役割

アドネスでは `Campaign` を、promotion や告知などの単発施策で使う。evergreen 導線ではなく、`今回だけ何を認識させ、どの行動をさせるか` を切って打つ実行面です。

## 役割

`Campaign` は、今回だけの segment 配信や promotion を 1 回だけ送るための単発配信面です。

## ゴール

次を迷わずできる状態を作る。
- `Campaign Manager` から `regular` campaign を作る
- audience と segment を先に固定する
- content を作る
- main CTA を short.io で置く
- hyperlink mismatch を防ぐ
- report で `sent / open / click` を読む

## 必要変数

- campaign 名
- 対象 audience
- segment 条件
- 何を認識させたいか
- main CTA
- short.io の有無
- 送るのが今回だけか

## 実装前の最小チェック

- 今回だけ送る配信だと説明できる
- audience と segment を先に確定している
- 1 通で変えたい認識と起こしたい行動を 1 つに絞っている
- main CTA の short.io を先に用意している
- 補助リンクを入れるなら、main CTA と役割を分けている

## 判断フレーム

### Campaign を使う

次の条件をすべて満たすなら `Campaign` を優先する。
- 今回だけ送る
- 対象を segment で切る
- promotion や告知など単発性が高い

### Campaign を使わない

次のどれかが `yes` なら `Journey` を疑う。
- 同じ flow を繰り返し自動で流す
- trigger による evergreen 運用がしたい

## Workflow

1. `Campaign Manager`
2. `Create`
3. `Regular`
4. audience を選ぶ
5. segment を切る
6. `Campaign name`
7. content を作る
8. main CTA を確認する
9. test または preview で hyperlink を確認する
10. report で結果を読む
11. exploratory な draft を作っただけなら同セッションで削除する

## current の exact route

- 一覧:
  - `/campaigns`
- create 入口:
  - `Campaign Manager -> Create -> Regular`
  - current route は `campaigns/#/create-campaign`

current では、単発配信の exploratory draft を残さないことを前提にする。

## exact 手順

### create

1. `Campaign Manager`
2. `Create`
3. `Regular`
4. audience 選択
5. segment 設定
6. `Campaign name`

この順番を崩さない。current では `誰に送るか` を先に固定しないと、本文がぶれやすい。

### editor で実際に見るラベル

- `Campaign name`
- `Audience`
- `Segment or Tag`
- `Exclude`
- `Subject line`
- `Preview text`
- `From name`
- `From email address`
- `Reply to email address`
- `Preview`
- `Send a test email`
- `Review and Send`

このラベルを最初に探せることを exact 性の基準にする。

### content

作る前に固定する。
- 今回何の認識を変えるか
- 1通で何を行動させるか
- main CTA は何か

### content の意図を読む時の順番

1. 誰に送っているか
2. 今回だけ送る理由は何か
3. 何の認識を変えたいか
4. 何を行動させたいか
5. main CTA は何か
6. 補助リンクは何のために置くか

この順を飛ばして、件名や見た目だけで良し悪しを判定しない。

current representative の読み方
- 全体 promotion
  - 広い `Subscribed` 母集団
  - `open_rate 9〜11%`
  - `click_rate 0.04〜0.21%`
- 高温セグメント promotion
  - `フリープラン` など絞られた母集団
  - `open_rate 38〜46%`
  - `click_rate 0.59〜4.99%`

representative を読む時も、まず
- `広い母集団への告知`
- `高温セグメントへの刈り取り`
のどちらかに切る。

rate だけを見て良し悪しを決めない。`誰に / 何を / 今回だけ` を先に固定する。

つまり current の `regular campaign` は
- `全体へ広く打つ単発告知`
- `高温セグメントへ強く打つ単発告知`
の 2 型で読むと速い。

### cleanup

live で exploratory draft を作った時は、配信せずに後片付けする。
- UI で current の削除導線が安定して取れている時は、一覧から削除する
- 削除導線が揺れる時は API 側の `create -> content -> delete` 検証に切り替える

`作成したが送らない draft` を残さないのが原則。

### current representative の見方

current の `regular` は、少なくとも次の 2 系統で読む。

- 全体 promotion
  - 広い母集団に単発告知を打つ
  - `open_rate 9〜11%`
  - `click_rate 0.04〜0.21%`
- 高温 segment promotion
  - `フリープラン` など既に温度が高い母集団へ打つ
  - `open_rate 38〜46%`
  - `click_rate 0.59〜4.99%`

rate の良し悪しは、必ず `誰に送ったか` とセットで読む。

## representative pattern

- `全体告知型`
  - 広い audience へ 1 回だけ告知する
  - `Recipients` が大きく、`Open rate` は低めでも成立する
  - 主目的は広く知らせること
- `高温セグメント刈り取り型`
  - `フリープラン` など温度が高い segment に絞る
  - `Open rate` と `Click rate` が高く出やすい
  - 主目的は個別相談や申込を取り切ること
- `補助リンク併用型`
  - main CTA のほかに `会社HP` や補足ページを置く
  - report を読む時は main CTA と secondary CTA を必ず分離する

## representative pattern を読む時の問い

- この campaign は `知らせる` のか `刈り取る` のか
- `Recipients` の大きさと目的は噛み合っているか
- main CTA は 1 つに絞れているか
- secondary CTA は主目的を邪魔していないか

## ベストな活用場面

- 今回だけ送る promotion や告知を打ちたい時
- 高温セグメントだけを切って、強い single CTA で刈り取りたい時
- evergreen ではなく、日時やオファーがその時限りの配信をしたい時

## よくあるエラー

- `Audience` や `Segment or Tag` より先に本文を作り始める
- main CTA を複数にして、何をしてほしいかがぼやける
- `Preview` や `Send a test email` を飛ばして hyperlink mismatch を起こす
- `Recipients` の母数と目的が噛み合っていない

## エラー時の切り分け順

1. それが単発配信か evergreen かを切る
2. `Audience / Segment or Tag / Exclude` を固定する
3. `Subject line / Preview text` と本文の約束が一致しているか見る
4. main CTA の actual hyperlink と final destination を確認する
5. `Recipients / Open rate / Click rate / click-details` まで見て、どこで落ちたか切る

### CTA

- main CTA は `short.io` を正にする
- 表示文字列ではなく hyperlink の実URLを click で確認する
- `会社HP` のような補助リンクは直リンクでもよいが、main CTA と混同しない
- secondary CTA がある時は
  - `main CTA`
  - `補助リンク`
 で役割を分けて読む

### preview / test で最低限見ること

- subject
- preview text
- main CTA の表示文言
- 実 hyperlink の遷移先
- secondary CTA の有無
- short.io なら short.io の最終遷移先

### editor の exact smoke 順

1. `Campaign name`
2. `Audience`
3. `Segment or Tag`
4. `Exclude`
5. `Subject line`
6. `Preview text`
7. `From name`
8. `From email address`
9. `Reply to email address`
10. 冒頭 3 行
11. main CTA の表示文言
12. actual hyperlink
13. `short.io`
14. final destination
15. `Preview`
16. `Send a test email`
17. `Review and Send`

### `Review and Send` 前の exact 順

1. `Recipients`
2. audience
3. segment
4. exclude 条件
5. `Subject line`
6. `Preview text`
7. main CTA の表示文言
8. main CTA の actual hyperlink
9. secondary CTA の actual hyperlink
10. short.io の最終遷移先

current の `regular campaign` は、本文の出来より先に `Recipients` と actual hyperlink を潰す。

### main CTA の current rule

- historical な sent campaign では `direct LINE` が多い
- ただし今後こちらが新規で作る時の標準は `main CTA = short.io`
- `会社HP` などの補助リンクは secondary CTA としてのみ許容する

## 30秒レビューの順番

1. `Campaign Manager`
2. campaign 名
3. audience
4. segment / exclude
5. `Subject line`
6. main CTA
7. `Review and Send` 前の actual hyperlink

## 検証

最低でも次を確認する。
- segment が正しい
- campaign 名が正しい
- main CTA が short.io
- 実 hyperlink が意図どおり
- report で `sent / open / click` が見える
- `click-details` で main CTA と secondary CTA を分けて読める

## 保存前の最小チェック

- `Campaign` を使う理由を 1 文で言える
- audience と segment を先に固定している
- 1 通の目的を 1 つに絞っている
- main CTA の short.io を用意している

## 保存後の最小チェック

- preview または test で hyperlink 実体を確認した
- main CTA と secondary CTA を分けて説明できる
- exploratory draft なら削除まで戻した
- 送る campaign なら `Recipients / Open rate / Click rate / click-details` の見る順を先に固定した

## 構築精度だけを見る時のチェック

1. `Campaign` を使う理由が `単発配信` で 1 文になっているか
2. `Audience` と `Segment or Tag` と `Exclude` の関係を 1 回で言えるか
3. `Subject line` と `Preview text` が同じ約束をしているか
4. main CTA が 1 つに絞れていて、`short.io` で統一されているか
5. secondary CTA があるなら、main CTA を邪魔しない位置づけになっているか
6. `Preview` または `Send a test email` で actual hyperlink まで確認したか
7. exploratory draft なら `Delete campaign` まで戻せるか

### current の exact draft cleanup

1. `Campaign Manager`
2. exploratory draft の row
3. row menu から `Delete`
4. confirm dialog の `Delete campaign`

delete 導線が揺れる時は、API の `create -> content -> delete` を fallback にする。

## 完成条件

- `Campaign` を使う理由を説明できる
- audience / segment / exclude を 1 回で言える
- main CTA が short.io で統一されている
- preview または test で actual hyperlink を確認済み

## ここで止めて確認する条件

- audience / segment より先に本文を作り始めている
- 1 通で複数オファーを混ぜたくなっている
- main CTA を short.io にできない事情がある
- 補助リンクの方が main CTA より強く見える
- segment と exclude がぶつかっていて、実際に誰へ送るか 1 文で言えない

## 命名

- Mailchimp は英語で運用する前提にする
- 新規 tag や segment は、日本語ではなく英語で切る

## NG

- 単発配信でないのに `Campaign` に寄せる
- segment を後回しにする
- direct LIFF を標準にする
- 表示文字列だけ見て URL が正しいと判断する

## 正誤判断

正しい状態
- `Campaign` を使う理由を説明できる
- audience と segment を先に固定している
- 1通の目的が 1 つに絞られている
- main CTA が short.io で統一されている
- exploratory draft を残さずに閉じられる

間違った状態
- audience / segment より先に本文から作り始める
- 1 通で複数オファーを混ぜる
- click 前に hyperlink 実体を確認しない

## References

- Addness 固有の current 例と判断は `Project/3_業務自動化/メールマーケティング自動化.md`
- representative な exact 手順は `references/workflow.md`
