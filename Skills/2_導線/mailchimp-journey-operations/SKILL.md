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

## 実装前の最小チェック

- この施策が evergreen で回るべきか決まっている
- audience と trigger tag を英語で確定している
- 1 通ごとに何の認識を変えるかを説明できる
- main CTA の short.io を先に用意している
- `Journey` ではなく `Campaign` にすべき可能性を先に潰している

## 判断フレーム

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

## current の exact route

- create 入口:
  - `/customer-journey/create-new-journey/`
- builder:
  - `/customer-journey/builder?id={journey_id}`

current では、`Build from scratch` を押して trigger 選択に入り始めた時点で draft が作られる前提で扱う。

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

## 30秒レビューの順番

1. `Automations`
2. journey 名
3. `Audience`
4. trigger
5. `Filter who can enter`
6. email step の順番
7. main CTA

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

## hyperlink 検証

- 表示文字列ではなく、実際に CTA を押した時の遷移先で判定する
- Addness の current 標準は `main CTA = short.io`
- 例外を除き、新規作成時は direct LIFF を標準にしない

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
