---
name: mailchimp-journey-operations
description: Mailchimpの `Customer Journeys` で evergreen な自動メール導線を作成、編集、検証する skill。Mailchimpで同じシナリオを継続的に流す時、`Tag added` などの trigger から flow を組みたい時、step の current / legacy を見分けながら安全に修正したい時に使う。
---

# mailchimp-journey-operations

## Overview

Mailchimp の `Customer Journeys` を、`Build from scratch` から `trigger / filter / email step / report` まで exact 手順で扱う skill です。

Addness 固有の naming、current representative、CTA ルールは `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill は、どの案件でも再利用できる exact 手順だけを持つ。

## ツールそのものの役割

`Customer Journeys` は、条件を満たした相手に対して同じメール体験を自動で継続配信する機能です。

## アドネスでの役割

アドネスでは `Journey` を、単発配信ではなく evergreen な教育導線の本線として使う。つまり、毎回手で送るものではなく、`同じ認識変換を何度も自動で流す` ための実行面です。

## 役割

`Journey` は、同じ顧客体験を継続的に自動で流す evergreen 用の flow です。

## ゴール

次を迷わずできる状態を作る。
- `Journey` で作るべき案件かを切る
- `Build from scratch` から draft flow に入る
- `Choose a trigger` で正しい入口を選ぶ
- `Tag added` などの条件を設定する
- email step を追加し、保存前の確認点を押さえる
- report で current を読む

## 必要変数

- flow 名
- audience
- trigger の種類
- trigger に使う tag
- filter が必要か
- 誰に何の認識を変えたいか
- main CTA
- どこへ送るか
- evergreen でよいか

## 依頼を受けたら最初に埋める項目

- flow 名
- `Audience`
- trigger の種類
- trigger に使う tag
- `Filter who can enter` の有無
- 1 通目で何の認識を変えるか
- main CTA の short.io
- `From name / From email address / Reply to email address`
- exploratory draft にするか、そのまま実装へ進むか

## 実装前の最小チェック

- この施策が evergreen で回るべきか決まっている
- audience と trigger tag を英語で確定している
- 1 通ごとに何の認識を変えるかを説明できる
- main CTA の short.io を先に用意している
- `Journey` ではなく `Campaign` にすべき可能性を先に潰している

## 入口選択の exact な問い

- 今やりたいのは `同じ顧客体験を自動で繰り返し流す` か
  - なら `Customer Journeys`
- 今やりたいのは `今回だけ送る` か
  - それはこの skill ではなく `Campaign`
- 今やりたいのは `誰に送るかの条件だけ作る` か
  - それはこの skill ではなく `tag / saved segment`
- 今やりたいのは `結果を読む` か
  - それはこの skill ではなく `report`

つまり、この skill の入口は `evergreen の自動化かどうか` で決まる。

## 判断フレーム

## 10秒判断

- Journey
  - 同じ認識変換を evergreen で回す
  - 入口条件を tag で切れる
- Campaign
  - 今回だけの promotion や告知
  - segment や exclude が主役
- tag/segment 先行
  - 先に state layer を確定しないと本文に入れない

この 10 秒判断が言えない時は、`Build from scratch` を押さない。

### Journey を使う

次の条件をすべて満たすなら `Journey` を優先する。
- 同じ顧客体験を何度も流す
- 入口条件が tag や状態で切れる
- 手動で毎回送るのではなく自動で回したい

### Journey を使わない

次のどれかが `yes` なら、まず `Campaign` を疑う。
- 今回だけの promotion
- 今回だけの segment 配信
- evergreen ではない

## Workflow

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Choose a trigger`
6. trigger 設定
7. 必要なら `Filter who can enter`
8. email step を追加
9. subject / preview / content を作る
10. `Save and exit` 系で戻る前に検証する
11. exploratory な draft を作っただけなら、同セッションで `Actions -> Delete -> Delete flow` まで戻す

## 最小 live test

最初の 1 本は `trigger まで作って cleanup` を優先する。

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`
7. `Tag added`
8. `Set a tag`
9. 必要なら `Filter who can enter`
10. `Save Trigger`
11. 一覧へ戻る
12. exploratory なら `Actions -> Delete -> Delete flow`

最初から複数 email step や branch を足さない。まず `Build from scratch -> trigger -> cleanup` が無迷いで閉じることを優先する。

## 最小 email step live test

trigger が無迷いで閉じるようになったら、次は `email step 1 本だけ` を足す最小 live test に進む。

1. builder に戻る
2. `Send email` を 1 step だけ追加
3. `Subject line`
4. `Preview text`
5. `From name`
6. `From email address`
7. `Reply to email address`
8. 本文は `main CTA 1 つ` だけで閉じる
9. `Send Test Emails`
10. actual hyperlink を click で確認
11. exploratory なら `Actions -> Delete -> Delete flow`

最初から 2 通目、delay、branch、goal を足さない。`trigger -> 1 email step -> cleanup` が無迷いで閉じることを優先する。

### save を伴う最小 live test の条件

次をすべて満たす時だけ、email step まで進める。
- trigger tag の意味を 1 文で言える
- evergreen で流す理由を 1 文で言える
- main CTA の short.io を先に用意している
- exploratory draft を自分で削除できる

上の条件が欠ける時は、Journey の live test は `trigger まで` で止める。

## email step 追加後の rollback

exploratory に email step を足した時は、必ず同じ session で rollback 条件まで見る。

1. builder 上で step が 1 本だけ増えていることを確認
2. `Send Test Emails` の結果を確認
3. 実 click で actual hyperlink を確認
4. 使わない draft なら一覧へ戻る
5. `Actions`
6. `Delete`
7. `Delete flow`

`step を消したつもり` で終わらない。flow ごと削除して、一覧から消えたところまで確認する。

## 最小 downstream smoke

email step まで作ったら、builder 内だけで終わらせない。

1. `Send Test Emails`
2. `Subject line`
3. `Preview text`
4. main CTA の表示文言
5. actual hyperlink
6. short.io の最終遷移先
7. downstream の `UTAGE / LINE / 外部ページ`

actual hyperlink と最終遷移先が intended でない限り、builder 上で見た目が良くても完了にしない。

## 最小 live change

既存 current の Journey を触る時は、最初の 1 回を `1 field だけ変える` に制限する。

1. 対象 `Customer Journeys > 行名`
2. builder を開く
3. 対象 step を 1 つ固定
4. 変更対象を 1 つに固定
   - `Subject line`
   - `Preview text`
   - main CTA の表示文言
   のような downstream の切り分けがしやすい field を優先
5. `Send Test Emails`
6. actual hyperlink を確認
7. 一覧へ戻る
8. `View Report` で intended な flow を開いていることを再確認

最初から trigger tag、filter、複数 email step、branch を同時に変えない。最初は `1 step 1 field` で change-safe な edit を通す。

## 複雑パターンを足す順

複雑化は、次の順で 1 つずつ足す。

1. `Tag added`
2. `Filter who can enter`
3. `Send email` 1 本
4. 2 通目
5. `Delay`
6. `Branch`
7. `Goal`

最初に `入口条件`, 次に `本文`, その後に `時間差` と `分岐` を足す。`trigger / filter / 複数 email / branch` を同時に触ると、どこで evergreen の意味が崩れたか切れなくなる。

## Journey state を汚さない current rule

- `Journey` の入口条件は `trigger` と `Filter who can enter` で閉じる
- `Campaign` で使う `saved segment` や単発配信の絞り込み発想を、そのまま `Journey` の入口条件に持ち込まない
- `Journey` で新規 tag を作る時は、その tag が
  - 何の event か
  - downstream で何を起動するか
  を 1 文で言えない限り作らない
- `Build from scratch` を押す前に
  - `evergreen で回す理由`
  - `trigger tag の意味`
  - `Filter who can enter の役割`
  を 1 本で言えないなら止まる

## current の exact route

- create 入口:
  - `/customer-journey/create-new-journey/`
- builder:
  - `/customer-journey/builder?id={journey_id}`

current では、`Build from scratch` を押して trigger 選択に入り始めた時点で draft が作られる前提で扱う。

## 認証フロー

current の Addness では、Mailchimp ログイン時に 2 段階認証が入ることがある。

1. `Send code via SMS`
2. `Mailchimp認証` の LINE グループでコード確認
3. `verify` 画面へ入力

`login` を抜けたように見えても `verify` が残っている時は、`Customer Journeys` や builder へ進まない。

## exact 手順

### create

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`

### trigger

current でよく使う代表。
- `Tag added`

`Tag added` を選ぶと、少なくとも次が出る。
- `Set a tag`
- `Filter who can enter`
- `Save Trigger`

### builder

journey 名クリックで current の builder に入る。
- `Send Test Emails`
- `View Report`
- `Pause & Edit`
- `Save and close flow`
- 右側には
  - `Data`
  - `Settings`
  が出る

### builder で最初に固定する順

1. journey 名
2. `Data`
3. `Settings`
4. trigger block
5. `Filter who can enter`
6. email step の順番
7. 各 step の main CTA

current の builder は step を足し始めると情報量が一気に増える。したがって、先に `trigger / filter / email順` を 1 行で言える状態にしてから本文へ入る。

### `Send Test Emails` を使う exact 順

1. builder 上部の `Send Test Emails`
2. 対象 step を確認
3. `Subject line`
4. `Preview text`
5. 本文冒頭
6. main CTA の表示文言
7. actual hyperlink
8. short.io の最終遷移先

`Send Test Emails` は、件名や本文を読む前に `actual hyperlink` を潰すために使う。表示文言だけ見て完了にしない。

### email editor で最初に見るラベル

email step に入ったら、まず次のラベルを固定する。

- `Subject line`
- `Preview text`
- `From name`
- `From email address`
- `Reply to email address`
- `Send Test Emails`

この 6 つが曖昧なまま本文へ入らない。current では、ここが曖昧だと「本文は作れたが配信として成立しない」事故になりやすい。

### cleanup

探索目的で draft flow を作っただけなら、一覧へ戻って次で後片付けする。
- `Actions`
- `Delete`
- `Delete flow`

`Build from scratch` は trigger を選び始めた時点で draft を作るので、保存していないつもりでも残る前提で扱う。

### current 判定

`last_started_at` だけで current と判断しない。最低でも次を見る。
- journey status が `sending`
- step status が `active`
- `queue_count > 0`

## Campaign 的な条件が混ざっていないかを見る順

1. `trigger` が event 起点になっているか
2. `Filter who can enter` が入口後の絞り込みだけになっているか
3. `saved segment` 前提の発想で audience を切っていないか
4. 各 email step の役割が
   - `本線ストーリー型`
   - `直オファー型`
   - `横展開型`
   - `個別3日間型`
   のどれかに寄っているか
5. `Journey` 全体が evergreen の説明になっているか

`今回だけこの人たちに送りたい` が主語に出た時点で、まず `Campaign` を疑う。

## content を読む時の基本順

1. 誰に送る flow か
2. 何の認識を変える flow か
3. その 1 通は何の役割か
4. main CTA は何か
5. 実際の hyperlink はどこへ飛ぶか

`step がある` だけでは読まない。必ず `1通ごとの役割` まで切る。

## representative content pattern

current の evergreen は、少なくとも次の 4 型で読む。

- `本線ストーリー型`
  - 人物ストーリー
  - authority
  - open loop
- `直オファー型`
  - 温度が上がった人へ直接 CTA を置く
- `横展開型`
  - 別オファーや別枝へ送る
- `個別3日間型`
  - 個別相談や締切系 CTA を短期で押し込む

同じ `Journey` の中でも、各 email step はこのどれかで役割を切って読む。

## representative pattern

### 本線教育型

- 目的
  - 長めの教育で認識を段階的に変える
- 先に見る場所
  - trigger
  - email step の順番
  - `本線ストーリー型`
- 向いている場面
  - evergreen 教育
  - 7桁本線

### 短期刈り取り型

- 目的
  - 温度がある相手を短期間で個別相談や申込へ寄せる
- 先に見る場所
  - trigger tag
  - 1通目から3通目の役割差
  - main CTA
- 向いている場面
  - 個別3日間
  - 締切系

### 横展開型

- 目的
  - main 導線を壊さず別オファーへ橋をかける
- 先に見る場所
  - 元の文脈
  - 横展開先のオファー
  - CTA の自然さ
- 向いている場面
  - フリープラン
  - セミナー
  - 別枝オファー

## representative pattern を読む時の問い

- この Journey は `本線教育 / 短期刈り取り / 横展開` のどれか
- trigger は、その体験を流し始める入口として自然か
- 各 email step の役割は 1 通ごとに切れているか
- main CTA はその step の結論になっているか
- 次の接点へ滑らかに渡っているか

## 最初の複雑パターン

最初に live で詰める複雑パターンは、`trigger + filter + email step 1本` だけで閉じる。

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Choose a trigger`
6. `Tag added`
7. `Set a tag`
8. `Filter who can enter`
9. `Save Trigger`
10. `Send email` を 1 本だけ追加
11. `Subject line`
12. `Preview text`
13. `From name`
14. `From email address`
15. `Reply to email address`
16. `Send Test Emails`
17. actual hyperlink を確認
18. exploratory なら `Actions -> Delete -> Delete flow`

最初から
- 2通目
- `Delay`
- `Branch`
- `Goal`
を同時に足さない。

## ベストな活用場面

- 同じ教育導線を evergreen で繰り返し流したい時
- `Tag added` などの state を入口にして、同じ認識変換を自動で回したい時
- 個別3日間のような短期刈り取りを、毎回手動ではなく自動で回したい時

## よくあるエラー

- 単発 promotion を `Journey` で作ってしまう
- `last_started_at` だけで current 判定してしまう
- `copy` という名前だけで legacy 扱いする
- trigger tag の意味が曖昧なまま flow を足す
- main CTA の actual hyperlink を click で確認していない

## エラー時の切り分け順

1. それが evergreen か単発配信かを切る
2. journey status が `sending` か見る
3. step status と `queue_count` を確認する
4. trigger tag の意味と downstream の役割を確認する
5. main CTA の actual hyperlink と final destination を確認する

## current で起きやすいエラー

- `Journey` なのに `Campaign` の発想で `saved segment` を持ち込む
- trigger tag の意味が曖昧なまま `Tag added` を選ぶ
- `Send Test Emails` をせずに本文だけ見て完了にする
- 表示文字列だけ見て、actual hyperlink を click で確認しない
- exploratory draft を一覧に残す

この 5 つは、current の exact 性を下げる代表エラーとして扱う。

## 30秒レビューの順番

1. `Automations`
2. journey 名
3. `Audience`
4. trigger
5. `Filter who can enter`
6. email step の順番
7. main CTA

## sample quality のチェック

`Journey` の live test では、sample や test data の質も見る。

1. trigger に使う tag が intended event を表しているか
2. audience が current の母集団と一致しているか
3. `Send Test Emails` の対象で intended な本文と CTA が見えるか
4. actual hyperlink が intended short.io か
5. cleanup まで戻せるか

sample が intended event を表していない時は、本文に入らず stop する。

## 検証

最低でも次を確認する。
- trigger が意図どおり
- tag 名が正しい
- main CTA が正しい
- hyperlink の実 URL が正しい
- report で `sent / open / click` が追える

## 保存前の最小チェック

- `Journey` を使う理由を 1 文で言える
- trigger tag を英語で確定している
- `誰に何の認識を変えたいか` を 1 通単位で説明できる
- main CTA を `short.io` で用意している

## 保存後の最小チェック

- builder 上で trigger と step の並びが意図どおり
- exploratory draft なら `Actions -> Delete -> Delete flow` まで戻した
- 残す flow なら `View Report` へ入れることを確認した
- hyperlink は表示文字列ではなく実 click で確認した

## 構築精度だけを見る時のチェック

1. `Journey` を使う理由が `evergreen` で 1 文になっているか
2. `Audience` と trigger tag が英語で固定されているか
3. `Filter who can enter` の有無を、必要性つきで説明できるか
4. 各 email step が `本線教育 / 短期刈り取り / 横展開` のどれかで役割分離されているか
5. main CTA の表示文言と actual hyperlink が一致しているか
6. `View Report` で後追いできる前提まで含めて保存できているか
7. exploratory draft なら、同セッションで `Delete flow` まで戻せるか

## report を読む exact 順

1. `View Report`
2. `Started`
3. `In Progress`
4. `Completed`
5. 各 email step の `queue_count`
6. `sent`
7. `open`
8. `click`
9. main CTA の `click-details`

`last_started_at` だけで current 判定しない。必ず `queue_count` と step 単位の `sent / open / click` をセットで見る。

## 完成条件

- evergreen 用の flow だと説明できる
- trigger / filter / email step の順が崩れていない
- main CTA と actual hyperlink を分けて確認済み
- report で `sent / open / click` を読める

## ここで止めて確認する条件

- `Journey` と `Campaign` のどちらか迷う
- trigger tag を新規作成すべきか既存流用すべきか説明できない
- `copy` 付き flow を current と legacy のどちらで読むか判断できない
- main CTA を short.io にできない事情がある
- `Filter who can enter` に単発 campaign の配信条件みたいな発想が入り始めた

## hyperlink 検証

- 表示文字列ではなく、実際に CTA を押した時の遷移先で判定する
- Addness の current 標準は `main CTA = short.io`
- 例外を除き、新規作成時は direct LIFF を標準にしない

## 症状から最初に疑う場所

- flow は作れたが evergreen に見えない
  - まず trigger tag の意味
  - 次に `Filter who can enter`
  - その後に `Journey` ではなく `Campaign` にすべき可能性
- `open` は出るのに `click` が弱い
  - まず main CTA の数
  - 次に actual hyperlink
  - その後に 1 通目で変えたい認識と CTA の自然さ
- `click` はあるのに downstream が弱い
  - まず short.io の最終遷移先
  - 次に `UTAGE / LINE / 外部ページ` の着地体験
  - その後に email 本文の約束と landing の一致
- `copy` 付き flow を見て current か迷う
  - まず `queue_count`
  - 次に `sent / open / click`
  - 名前だけで legacy と決めない
- trigger は作れたが email step に進むのが不安
  - まず `main CTA の short.io`
  - 次に `Subject line / Preview text`
  - その後に `Send Test Emails` までで閉じる最小構成を疑う

## NG

- evergreen でないのに `Journey` を使う
- `copy` という名前だけで legacy と決めつける
- `last_started_at` だけで current 判定する
- main CTA を short.io でなく直書きにする
- 表示文字列だけ見て hyperlink の実URLを確認しない

## 正誤判断

正しい状態
- `Journey` を使う理由を説明できる
- trigger を UI ラベルで説明できる
- current / legacy を queue と sent で切れる
- 実際の CTA をクリックして意図どおり動く
- exploratory draft を残さずに閉じられる

間違った状態
- 単発配信を `Journey` に入れる
- step 名だけで current と判断する
- draft を current 実績と混ぜる

## References

- Addness 固有の current 例と判断は `Project/3_業務自動化/メールマーケティング自動化.md`
- representative な exact 手順は `references/workflow.md`
