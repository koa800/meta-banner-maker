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

## Addness 側の重要解釈

- regular campaign の main CTA は
  - `direct LINE`
  - `UTAGE`
  - `short.io`
  が混在する
- だから本文先頭の href だけで決め打ちしない
- `click-details` の top URL を必ず見る
