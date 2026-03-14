# Mailchimp report exact メモ

## 読む順番

1. `送信`
2. `開封`
3. `クリック`
4. `click-details`

## Journey report

- builder の `View Report`
- current で見る
  - `Days active`
  - `Total started`
  - `Total in progress`
  - `Total completed`
  - `Open rate`
  - `Click rate`
  - `Unsubscribe rate`
  - `Delivery rate`

## Campaign report

- `Campaign Manager`
- 対象 row の report
- main CTA 判定は `click-details`

## benchmark の見方

- 広い母集団への regular campaign
  - `open_rate 9〜11%`
  - `click_rate 0.04〜0.21%`
- 高温 segment への regular campaign
  - `open_rate 38〜46%`
  - `click_rate 0.59〜4.99%`

rate 単体で良し悪しを決めず、必ず `誰に送ったか` とセットで読む。

## Addness 側の重要解釈

- regular campaign の main CTA は
  - `direct LINE`
  - `UTAGE`
  - `short.io`
  が混在する
- だから本文先頭の href だけで決め打ちしない
- `click-details` の top URL を必ず見る
- `開封率 / クリック率` は、必ず `誰に送ったか` とセットで読む
- `高い / 低い` を rate だけで判定しない
- recent 代表では
  - `AI全自動PR_1通目(3/13) = direct LINE / %40631igmlz`
  - `3/11 AIキャリアセミナーPR_2通目 = direct LINE / %40770dyrre`
  - `3/10 セミナーPR_3通目 (フリープラン) = direct LINE / %40076cqpuk`
  - `Resend: AIキャンプ = UTAGE`
  のように family が分かれる

## 最小判断フレーム

1. 何人に送ったか
2. どんな母集団に送ったか
3. main CTA はどこか
4. 何人が main CTA を押したか
5. その先で何が起きるはずか
