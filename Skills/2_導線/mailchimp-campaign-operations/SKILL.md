---
name: mailchimp-campaign-operations
description: Mailchimpの `Campaign Manager` で単発の regular campaign を作成、編集、検証する skill。Mailchimpで今回だけの promotion や segment 配信をしたい時、対象条件を切って 1 回だけ送りたい時、本文と main CTA を exact に検証したい時に使う。
---

# mailchimp-campaign-operations

## Overview

Mailchimp の `Campaign Manager` で、単発の `regular` campaign を exact 手順で扱う skill です。

Addness 固有の current representative、main CTA ルール、良い / 悪いの判断は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill は、どの案件でも再利用できる exact 手順だけを持つ。

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

## exact 手順

### create

1. `Campaign Manager`
2. `Create`
3. `Regular`
4. audience 選択
5. segment 設定
6. `Campaign name`

### content

作る前に固定する。
- 今回何の認識を変えるか
- 1通で何を行動させるか
- main CTA は何か

### CTA

- main CTA は `short.io` を正にする
- 表示文字列ではなく hyperlink の実URLを click で確認する

## 検証

最低でも次を確認する。
- segment が正しい
- campaign 名が正しい
- main CTA が short.io
- 実 hyperlink が意図どおり
- report で `sent / open / click` が見える

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

間違った状態
- audience / segment より先に本文から作り始める
- 1 通で複数オファーを混ぜる
- click 前に hyperlink 実体を確認しない

## References

- Addness 固有の current 例と判断は `Project/3_業務自動化/メールマーケティング自動化.md`
- representative な exact 手順は `references/workflow.md`
