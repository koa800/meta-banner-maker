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

## 依頼を受けたら最初に埋める項目

- `Journey report` か `Campaign report` か
- 対象名
  - journey 名 or campaign 名
- 想定していた `main CTA`
- 想定していた downstream
  - `short.io / UTAGE / direct LINE / 外部ページ`
- 今回見たい観点
  - `開封 / クリック / CTA family / downstream`
- どこで離脱していそうかという仮説

## 実装前の最小チェック

- `Journey report` か `Campaign report` か切れている
- 事前に想定していた `main CTA` を 1 つ言える
- `誰に送った配信か` を `tag / segment / audience` で説明できる
- downstream を次にどこまで追うか決めている

## 10秒判断

- `Journey report`
  - evergreen flow 全体の結果を読みたい
- `Campaign report`
  - 単発配信の結果を読みたい
- `short.io family`
  - click の後の link control を見たい
- `UTAGE family`
  - click の後のページ体験を見たい
- `direct LINE family`
  - click の後の LINE 受け皿を見たい

この 10 秒判断が言えない時は、`View Report` や `View report` を押しても rate だけ眺めて終わりやすいので stop する。

## 入口選択の exact な問い

- 今やりたいのは `送った後の結果を読む` ことか
  - なら `report`
- 今やりたいのは `evergreen flow を組む` ことか
  - それはこの skill ではなく `Journey`
- 今やりたいのは `単発配信を作る` ことか
  - それはこの skill ではなく `Campaign`
- 今やりたいのは `誰に送るかの条件を作る` ことか
  - それはこの skill ではなく `tag / saved segment`

つまり、この skill の入口は `結果読解が主目的か` で決まる。

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

## 最小 live review

最初の 1 本は `1 report -> 1 main CTA family -> 1 downstream` だけで閉じる。

1. `Journey report` か `Campaign report` を 1 つ選ぶ
2. `Recipients`
3. `Open rate`
4. `Click rate`
5. `click-details`
6. `main CTA family`
7. downstream を 1 系統だけ確認

最初から複数 campaign や複数 downstream を比較しない。まず 1 本の漏斗を end-to-end で読めることを優先する。

## 最初の複雑パターン

最初に exact に読む 1 本は、次のどれか 1 つに絞る。

- `Journey report`
  - `Open rate + Click rate + click-details + short.io family`
- `Campaign report`
  - `Recipients + Open rate + click-details + direct LINE family`
- `Campaign report`
  - `Recipients + Click rate + click-details + UTAGE family`

最初から
- 複数 CTA family の比較
- 複数 campaign の横比較
- 開封率と downstream の両方を同時改善
をやらない。まず 1 本で `どこが weakest point か` を切ることを優先する。

## main CTA family を切る順

`click-details` を開いたら、まず URL を family で切る。

- `short.io`
- `UTAGE`
- `direct LINE`
- `company / 外部補助リンク`

この順で切り、`一番クリックされたもの` ではなく、`事前に想定した主導線と一致しているか` を先に判定する。

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

`click-details` では、見えていたリンク文言ではなく `actual URL family` を主に読む。表示文言が正しそうでも、実 hyperlink が違えば main CTA 判定をやり直す。

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

## 数値を見た後の改善仮説の切り方

- `Recipients` は十分だが `Open rate` が弱い
  - 件名 / preview text / audience の温度を疑う
- `Open rate` は十分だが `Click rate` が弱い
  - 本文の役割、main CTA の位置、offer の自然さを疑う
- `Click rate` はあるが downstream 行動が弱い
  - `short.io / UTAGE / LINE` の接続後体験を疑う
- `click-details` が main CTA ではなく補助リンクへ寄る
  - primary と secondary の責務分離が崩れている可能性を疑う

## 漏斗診断の最小型

`report` は、数字を並べて終わらせず、どこで離脱しているかを 1 本で切る。

1. `Recipients`
2. `Open rate`
3. `Click rate`
4. `click-details`
5. downstream

この 5 段を、`誰に送ったか / 何を変えたい配信か` とセットで説明できる状態を最低ラインとする。

## 最小 downstream smoke

main CTA family を切ったら、1 系統だけ最後まで確認する。

1. `click-details`
2. main CTA の actual URL
3. `short.io / UTAGE / direct LINE` の family 判定
4. intended な最終着地
5. 想定していた認識変換や行動とズレていないか

report は数字だけで閉じない。`主導線の click が intended な downstream に着くか` まで見て smoke 完了とする。

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

## downstream へ渡す順

main CTA family が決まったら、次は固定順で渡す。

1. `short.io`
   - click 数
   - final destination
2. `UTAGE`
   - 訪問
   - 登録 / 購入 / 遷移
3. `LINE`
   - follow family
   - 予約 / state 変化

`report` 単体で止めず、どの system を次に見るかまで切れた時に読解完了とする。

## `report` を読んだ後の次の一手

- `Open rate` が弱い
  - `Subject line / Preview text / Audience or Segment` を先に疑う
- `Open rate` は十分だが `Click rate` が弱い
  - `本文の役割 / CTA の置き方 / main CTA の一意性` を先に疑う
- click はあるが downstream が弱い
  - `short.io / UTAGE / LINE 受け皿` を先に疑う
- 補助リンクに click が寄る
  - `main CTA と secondary CTA の責務分離` を先に疑う

## 症状から最初に疑う場所

- `Recipients` が想定より少ない
  - `Audience`
  - `Segment or Tag`
  - `Exclude`
  の順で疑う
- `Open rate` が弱い
  - `Subject line`
  - `Preview text`
  - 母集団温度
  の順で疑う
- `Open rate` は十分だが `Click rate` が弱い
  - 本文の役割
  - main CTA の一意性
  - CTA の位置
  の順で疑う
- `Click rate` はあるが downstream 行動が弱い
  - `short.io`
  - `UTAGE`
  - `direct LINE`
  の family を切ってから downstream を疑う
- `click-details` の上位が main CTA ではなく補助リンク
  - `main CTA`
  - `secondary CTA`
  の責務分離を先に疑う

## family ごとの次の一手

### `short.io`

- 先に確認する
  - `title`
  - `originalURL`
  - click 数
- 次に確認する
  - URL管理シート
  - 最終遷移先
- 解釈
  - `Mailchimp 本文は踏まれているが、その先が弱いのか`
  - `そもそも short.io 以前で弱いのか`
  を切る

### `UTAGE`

- 先に確認する
  - intended な `ファネル > ページ一覧の行名`
  - 公開ページ
  - 主CTA の実 click
- 次に確認する
  - `登録`
  - `購入`
  - `次ページ遷移`
  のどれを期待していたか
- 解釈
  - `Mailchimp までは機能しているが、page 側で認識変換か接続が弱い`
  可能性を疑う

### `direct LINE`

- 先に確認する
  - `follow=` family
  - intended な LINE 名
- 次に確認する
  - Lステップ 側の受け皿 account
  - その後の `流入経路 / タグ / 予約`
    の intended path
- 解釈
  - `Mailchimp の本文が弱い` のか
  - `LINE 側の受け皿が弱い` のか
  を分ける

## 漏斗ごとの最初の診断仮説

- `Recipients` が小さい
  - 配信条件
  - `Audience`
  - `saved segment`
  - `tag`
  を先に疑う
- `Open rate` が弱い
  - `Subject line`
  - `Preview text`
  - 母集団温度
  を先に疑う
- `Click rate` が弱い
  - 本文の役割
  - CTA の一意性
  - CTA の位置
  を先に疑う
- `click-details` までは出るが downstream が弱い
  - `short.io`
  - `UTAGE`
  - `direct LINE`
  の family 側を先に疑う

rate を見てすぐ本文改善へ飛ばない。どの段で落ちているかに応じて、先に疑う system を変える。

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

## report 読了後の出力

report を読んだら、最低でも次の 4 行に落とす。

1. 誰に送ったか
2. 何を変えたい配信だったか
3. 一番弱い段はどこか
4. 次に見る system はどこか

この 4 行に落とせない時は、まだ report を「見た」だけで「読めていない」と判断する。

## 読解精度だけを見る時のチェック

1. いま読んでいるのが `Journey report` か `Campaign report` かを最初に固定したか
2. `誰に送ったか` を `audience / segment / tag` のどれかで 1 文にできるか
3. `main CTA` を 1 つに絞れているか
4. `top clicked URL` と `main CTA` を混同していないか
5. `short.io / UTAGE / direct LINE` の family を分けて読めているか
6. 率だけではなく、`誰に / 何を変えたい配信だったか` とセットで解釈しているか
7. 次にどの system を見に行くべきか言えるか
8. `short.io / UTAGE / direct LINE` の family ごとに、次の一手を変えられているか
9. `Recipients -> Open rate -> Click rate -> click-details -> downstream`
   の 5 段で weakest point を言えるか

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

## 構築精度だけを見る時のチェック

1. `Journey report` か `Campaign report` かを最初に切っているか
2. 想定していた `main CTA` を report を開く前に言えるか
3. `sent -> open -> click -> click-details` の順を崩していないか
4. `short.io / UTAGE / direct LINE / 外部ページ` の family を混ぜずに切れているか
5. 数字だけでなく downstream まで確認する前提になっているか
6. 1 本の漏斗を end-to-end で見た後に比較へ進んでいるか

## 完成条件

- `送信 -> 開封 -> クリック -> click-details` の順で report を読める
- main CTA の実 URL を説明できる
- 送付対象の温度差を加味して数値を読める

## 症状から最初に疑う場所

- `open_rate` が低い
  - まず `Subject line`
  - 次に `Preview text`
  - その後に送付対象の温度差
- `open_rate` は悪くないのに `click_rate` が低い
  - まず main CTA の位置
  - 次に main CTA の actual hyperlink
  - その後に offer と本文の自然さ
- クリックはあるのに downstream が弱い
  - まず `click-details` の main CTA family
  - 次に short.io の最終遷移先
  - その後に UTAGE / LINE の受け皿
- `click-details` が読みにくい
  - まず `short.io / UTAGE / direct LINE / 補助リンク`
  の family で切る
  - main と secondary を分けずに数字を眺めない
- rate は良いのに成果が出ない
  - まず送付対象の温度
  - 次に CTA family
  - 最後に downstream の体験

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
