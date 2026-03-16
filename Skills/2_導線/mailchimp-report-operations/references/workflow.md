# Mailchimp report exact メモ

## 読む順番

1. `送信`
2. `開封`
3. `クリック`
4. `click-details`

## 30秒レビューの順番

1. `Journey report` か `Campaign report` か先に切る
2. 何人に何を変えたい配信かを 1 文で言う
3. main CTA 候補を 1 つに絞る
4. `top clicked URL` と main CTA を分けて見る
5. 次に見るべき page / system を決める

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

## 漏斗診断の順番

1. `Recipients`
2. `Open rate`
3. `Click rate`
4. `click-details`
5. `short.io / UTAGE / direct LINE` の downstream

rate の高低だけで終わらず、どこで離脱しているかをこの順で切る。

## 最小判断フレーム

1. 何人に送ったか
2. どんな母集団に送ったか
3. main CTA はどこか
4. 何人が main CTA を押したか
5. その先で何が起きるはずか

## 保存前の最小チェック

- `Journey report` を見るのか `Campaign report` を見るのか決まっている
- main CTA 候補が 1 つに絞れている
- click 数だけでなく、母集団と送信目的もセットで見る前提になっている

## レビュー後の最小チェック

- `top clicked URL` を main CTA と取り違えていない
- `開封率 / クリック率` の解釈に母集団の温度差を反映している
- 次に見るべきページやシステムが言える
- `Recipients -> Open rate -> Click rate -> click-details -> downstream`
  のどこが weakest point か言える

## 読解精度だけを見る時のチェック

1. いま見ているのが `Journey report` か `Campaign report` か
2. `誰に送ったか` を 1 文で言えるか
3. `main CTA` を 1 つに絞れているか
4. `top clicked URL` と `main CTA` を混同していないか
5. `short.io / UTAGE / direct LINE` の family を分けて説明できるか
6. 次に見るべき system を決められているか

## ここで止めて確認する条件

- click 数はあるが、main CTA が複数あって主軸を決められない
- `direct LINE / short.io / UTAGE` が混在していて、どれを main と読むか曖昧
- `開封率` だけ高く、認識変換が成功したか判断できない
- 数字は見えているが、次に `本文 / CTA / short.io / UTAGE / LINE`
  のどこを直すかに落ちない

## 完成条件

- `Journey report` と `Campaign report` のどちらを読んでいるか明確
- `誰に送ったか / 何を変えたい配信か / main CTA は何か` を 1 文で言える
- `top clicked URL` と main CTA を混同していない
- `開封率 / クリック率` を母集団の温度差込みで解釈できている
- 次に見るべき page や system を特定できている

## 保存後の最小チェック

- preview または test で actual hyperlink を確認した
- `short.io` の final destination まで確認した
- report や click-details の見る順が決まっている
