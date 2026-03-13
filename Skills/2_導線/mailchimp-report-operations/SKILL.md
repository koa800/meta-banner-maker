---
name: mailchimp-report-operations
description: Mailchimpで送信後の `report` を exact に読む skill。送信数、開封率、クリック率、click-details、main CTA を current 手順で確認したい時に使う。
---

# mailchimp-report-operations

## Overview

Mailchimp の `report` を、`送信 -> 開封 -> クリック -> click-details` の順で読む skill です。

Addness 固有の representative report と benchmark は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill では、どの案件でも再利用できる report 読みの型だけを持つ。

## 役割

`report` は、配信結果から `どの認識変換が起きて、どこで弱かったか` を読む layer です。

## ゴール

次を迷わずできる状態を作る。
- 送信結果の current report を開く
- `open / click / click-details` を読む
- main CTA が何だったかを判断する
- 次にどこを見るべきかを決める

## 必要変数

- Journey か Campaign か
- campaign_id または journey_id
- 何を main CTA と想定していたか
- short.io / UTAGE / direct LINE のどれが main か

## Workflow

1. 対象が `Journey report` か `Campaign report` かを決める
2. まず `sent`
3. 次に `open`
4. 次に `click`
5. 最後に `click-details`
6. main CTA が
   - `short.io`
   - `UTAGE`
   - `direct LINE`
   のどれかを決める
7. 必要なら downstream を見に行く

## exact 手順

### Journey report

- builder 上で `View Report`
- current で見る項目
  - `Days active`
  - `Total started`
  - `Total in progress`
  - `Total completed`
  - `Open rate`
  - `Click rate`
  - `Unsubscribe rate`
  - `Delivery rate`

### Campaign report

- `Campaign Manager` 一覧から対象 row
- report を開く
- 読む順
  1. `Recipients`
  2. `Open rate`
  3. `Click rate`
  4. `click-details`

### API 側 helper

- `mailchimp_campaign_snapshot.py --campaign-id {id}`
- `mailchimp_journey_snapshot.py --journey-id {id}`

## 検証

最低でも次を確認する。
- `sent` が想定母集団とズレていない
- `open_rate` が segment の温度に対して大きく外れていない
- `click-details` の main URL が想定 CTA と一致する
- `short.io` なら short.io 側、`UTAGE` なら UTAGE 側へ次に進める

## NG

- `open_rate` だけで判断する
- `click-details` を見ずに main CTA を決める
- 本文先頭の href だけで CTA を決め打ちする
- `direct LINE` と `UTAGE` の混在を無視する

## 正誤判断

正しい状態
- `送信 -> 開封 -> クリック -> click-details` の順で読んでいる
- main CTA を URL 実績で説明できる

間違った状態
- クリック先を見ずに効果を判断する
- report を読んだつもりで downstream を見ていない

## References

- representative report は `Project/3_業務自動化/メールマーケティング自動化.md`
- current 運用の補足は `Master/addness/README.md`
