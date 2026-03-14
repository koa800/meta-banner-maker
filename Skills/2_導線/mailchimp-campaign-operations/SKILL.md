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

### content

作る前に固定する。
- 今回何の認識を変えるか
- 1通で何を行動させるか
- main CTA は何か

current representative の読み方
- 全体 promotion
  - 広い `Subscribed` 母集団
  - `open_rate 9〜11%`
  - `click_rate 0.04〜0.21%`
- 高温セグメント promotion
  - `フリープラン` など絞られた母集団
  - `open_rate 38〜46%`
  - `click_rate 0.59〜4.99%`

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

### main CTA の current rule

- historical な sent campaign では `direct LINE` が多い
- ただし今後こちらが新規で作る時の標準は `main CTA = short.io`
- `会社HP` などの補助リンクは secondary CTA としてのみ許容する

## 検証

最低でも次を確認する。
- segment が正しい
- campaign 名が正しい
- main CTA が short.io
- 実 hyperlink が意図どおり
- report で `sent / open / click` が見える
- `click-details` で main CTA と secondary CTA を分けて読める

## 保存前後の最小チェックリスト

保存前
- `Campaign` を使う理由を 1 文で言える
- audience と segment を先に固定している
- 1 通の目的を 1 つに絞っている
- main CTA の short.io を用意している

保存後
- preview または test で hyperlink 実体を確認した
- main CTA と secondary CTA を分けて説明できる
- exploratory draft なら削除まで戻した
- 送る campaign なら `Recipients / Open rate / Click rate / click-details` の見る順を先に固定した

## ここで止めて確認する条件

- audience / segment より先に本文を作り始めている
- 1 通で複数オファーを混ぜたくなっている
- main CTA を short.io にできない事情がある
- 補助リンクの方が main CTA より強く見える

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
