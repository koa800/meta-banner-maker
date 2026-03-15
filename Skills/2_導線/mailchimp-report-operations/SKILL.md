---
name: mailchimp-report-operations
description: Mailchimpで送信後の `report` を exact に読む skill。送信数、開封率、クリック率、click-details、main CTA を current 手順で確認したい時に使う。
---

# mailchimp-report-operations

## Overview

Mailchimp の `report` を、`送信 -> 開封 -> クリック -> click-details` の順で読む skill です。

Addness 固有の representative report と benchmark は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill では、どの案件でも再利用できる report 読みの型だけを持つ。

## ツールそのものの役割

`report` は、配信結果を数値で可視化し、どこで反応が落ちたか、どの CTA が機能したかを読む機能です。

## アドネスでの役割

アドネスでは `report` を、単に rate を見る画面ではなく、`どの認識変換が弱く、次にどの接点を直すべきか` を判断する layer として使う。

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

## 実装前の最小チェック

- `Journey report` か `Campaign report` か切れている
- 事前に想定していた `main CTA` を 1 つ言える
- `誰に送った配信か` を `tag / segment / audience` で説明できる
- downstream を次にどこまで追うか決めている

## レビュー前の最小チェック

- その対象が `Journey report` か `Campaign report` か切れているか
- `誰に送ったか` を `tag / segment / audience` で説明できるか
- 事前に想定していた `main CTA` を 1 つ言えるか
- downstream を見に行く優先順が決まっているか

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
7. secondary CTA があるか確認する
8. 必要なら downstream を見に行く

## exact 手順

### Journey report

- `Customer Journeys` 一覧から対象 flow を開く
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
- row 右側の `View report` から report を開く
- 読む順
  1. `Recipients`
  2. `Open rate`
  3. `Click rate`
  4. `click-details`

### current UI で先に固定するラベル

- `Customer Journeys`
- `View Report`
- `Campaign Manager`
- `View report`
- `Recipients`
- `Open rate`
- `Click rate`
- `click-details`
- `Unsubscribe rate`
- `Delivery rate`

### API 側 helper

- `mailchimp_campaign_snapshot.py --campaign-id {id}`
- `mailchimp_journey_snapshot.py --journey-id {id}`

### 30秒レビューの順番

1. `Recipients` で母数確認
2. `Open rate` で温度確認
3. `Click rate` で反応確認
4. `click-details` で main CTA と secondary CTA を分離
5. main CTA の downstream を次に見る

## representative pattern

- `広い母集団の反応確認型`
  - `Recipients` が大きい campaign を読む
  - まず `Open rate` が極端に低すぎないかを見る
  - 次に `Click rate` よりも `click-details` の主導線を確認する
- `高温セグメントの刈り取り確認型`
  - `Recipients` が小さくても、`Open rate` と `Click rate` の質を見る
  - CTA が意図どおりに強く踏まれているかを確認する
- `導線分岐確認型`
  - `short.io / UTAGE / direct LINE` が混在する report を読む
  - 数値より先に `どの family が main CTA か` を切る

## representative pattern を読む時の問い

- この report は `母数の広さ` を見る回か、`刈り取りの強さ` を見る回か
- `main CTA` と `secondary CTA` を分けて説明できるか
- `click-details` の上位 URL は、事前に想定していた導線と一致するか
- 次に見るべき downstream は `short.io / UTAGE / LINE` のどれか

## ベストな活用場面

- 配信後に、どこで反応が落ちたかを素早く見たい時
- `main CTA` と `secondary CTA` のどちらが効いたかを切り分けたい時
- 次に直すべき場所が `件名 / 本文 / CTA / downstream` のどれかを判断したい時

## よくあるエラー

- `Open rate` だけを見て良し悪しを決める
- `click-details` を見ずに main CTA を断定する
- `Journey report` と `Campaign report` を混ぜて benchmark を読む
- `direct LINE` と `UTAGE` と `short.io` の family を分けずに click をまとめる

## エラー時の切り分け順

1. まず `Journey report` か `Campaign report` かを切る
2. `Recipients` で母数を確認する
3. `Open rate` で件名や温度の問題かを見る
4. `Click rate` と `click-details` で main CTA family を確定する
5. main CTA に応じて `short.io / UTAGE / LINE` の downstream を見に行く

## 検証

最低でも次を確認する。
- `sent` が想定母集団とズレていない
- `open_rate` が segment の温度に対して大きく外れていない
- `click-details` の main URL が想定 CTA と一致する
- secondary CTA があるなら、その役割を分けて読む
- `short.io` なら short.io 側、`UTAGE` なら UTAGE 側へ次に進める

## 保存前の最小チェック

- `Recipients / Open rate / Click rate / click-details` を全部見る前提でいる
- `main CTA` と `secondary CTA` を分けて読む前提を持っている
- rate 単体ではなく送付対象とセットで評価するつもりか確認する

## 保存後の最小チェック

- `Recipients`
- `Open rate`
- `Click rate`
- `click-details`
を全部見たか
- `main CTA`
- `secondary CTA`
を分けて説明できるか
- 率だけでなく、`誰に送ったか` とセットで評価しているか

current の読み分け
- 広い母集団への regular campaign
  - `open_rate 9〜11%`
  - `click_rate 0.04〜0.21%`
  を目安に読む
- `フリープラン` など高温セグメントへの regular campaign
  - `open_rate 38〜46%`
  - `click_rate 0.59〜4.99%`
  を目安に読む
- したがって rate 単体で良し悪しを決めず、`誰に送ったか` を先に固定する

### 2026-03 の representative 実例

- `AI全自動PR_3通目(3/15)`
  - `sent = 259,401`
  - `open_rate = 5.45%`
  - `click_rate = 0.056%`
  - main CTA は `direct LINE`
  - follow family は `%40631igmlz`
  - 読み方
    - 広い母集団への後半追撃
    - まず本文改善より `温度の低い母集団へ後半通を打っているか` を疑う
- `AI全自動PR_1通目(3/13)`
  - `sent = 259,813`
  - `open_rate = 10.05%`
  - `click_rate = 0.213%`
  - main CTA は `direct LINE`
  - follow family は `%40631igmlz`
  - 読み方
    - 同じ広い母集団でも、1 通目は 3 通目より自然に反応が高い
    - 1 通目と 3 通目は本文だけでなく `送る順番` もセットで比較する
- `AI全自動PR_1通目(3/13) (copy 01)`
  - `sent = 259,426`
  - `open_rate = 9.10%`
  - `click_rate = 0.251%`
  - main CTA は `direct LINE`
  - follow family は `%40303zgzwt`
  - 読み方
    - `copy` 付きでも `sent > 0` なら current 実績として読む
    - follow family が変わると click の質も変わりうる
- `Resend: AIキャンプ`
  - `sent = 247,861`
  - `open_rate = 5.99%`
  - `click_rate = 0.059%`
  - main CTA は `UTAGE`
  - 読み方
    - `regular campaign` でも `UTAGE` 主導の現役例がある
    - つまり `regular campaign = direct LINE` と決め打ちしない

## current の読み分け

- `direct LINE` は 1 つではない
- 少なくとも current では、`follow=` の family を分けて読む
  - `【みかみ】アドネス株式会社`
  - `みかみ@AI_個別専用`
  - `みかみ@個別専用`
- したがって、`direct LINE` と一括りで終わらせず、どの LINE family に送っているかまで見る

## 完成条件

- `送信 -> 開封 -> クリック -> click-details` の順で report を読める
- main CTA の実 URL を説明できる
- 送付対象の温度差を加味して数値を読める

## NG

- `open_rate` だけで判断する
- `click-details` を見ずに main CTA を決める
- 本文先頭の href だけで CTA を決め打ちする
- `direct LINE` と `UTAGE` の混在を無視する
- main CTA と secondary CTA の役割を混ぜる

## 正誤判断

正しい状態
- `送信 -> 開封 -> クリック -> click-details` の順で読んでいる
- main CTA を URL 実績で説明できる
- `誰に送った campaign か` を rate とセットで説明できる

間違った状態
- クリック先を見ずに効果を判断する
- report を読んだつもりで downstream を見ていない

## ここで止めて確認する条件

- `main CTA` が `short.io / UTAGE / direct LINE` のどれかに切れない
- 同じ report 内で CTA の family が混在していて、主従が分からない
- `click-details` が 0 なのに本文改善なのか配信対象改善なのか判断できない
- current の benchmark と大きくずれているが、送付対象の温度差で説明できない
- `View Report` と `View report` のどちらで開く画面か切れず、Journey と Campaign を混ぜそう

## References

- representative report は `Project/3_業務自動化/メールマーケティング自動化.md`
- current 運用の補足は `Master/addness/README.md`
