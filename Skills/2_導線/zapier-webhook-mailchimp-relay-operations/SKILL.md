---
name: zapier-webhook-mailchimp-relay-operations
description: Zapier の `Webhooks by Zapier` と `Mailchimp Add/Update Subscriber` を使う relay を読み、作り、検証する skill。UTAGE などの webhook event を Mailchimp の audience と tag に変換したい時、Addness の current relay family を exact に読みたい時、relay を壊さずに追加・確認したい時に使う。
---

# zapier-webhook-mailchimp-relay-operations

## Overview

Zapier の current 主戦場である `Webhook -> Mailchimp Add/Update Subscriber` relay を、一覧の読み方から editor の確認、最小構成の relay 設計まで exact に扱う skill です。

Addness 固有の Zap 名、tag 名、folder 運用、current representative は `Master/addness/zapier_structure.md` を正本にする。この skill は、会社をまたいで再利用できる relay 手順だけを持つ。

## ツールそのものの役割

Zapier は、あるシステムで起きた event を別のシステムへ渡し、state や action を接続する relay system です。

## アドネスでの役割

アドネスでは Zapier を、UTAGE やその他 front system の event を Mailchimp が扱える audience と tag に変換する relay layer として使う。表の顧客体験を作るツールではなく、裏で接続を成立させるシステムです。

## 役割

この relay は、front system で起きた business event を、Mailchimp が扱える audience + tag に変換する。

## ゴール

次を迷わずできる状態を作る。
- 一覧から current relay を読む
- `Webhook -> Mailchimp Add/Update Subscriber` の 2 step 構造を確認する
- audience と tag の意味を確認する
- webhook payload のどの key を email に使うか確認する
- 新規 relay を追加する時に最小構成を外さない

## 必要変数

- Zap 名
- business event の意味
- webhook payload の key
- 送る audience
- 付ける tag
- member status
- update existing の可否
- 既存 relay を触るか新規 relay を作るか

## 依頼を受けたら最初に埋める項目

- source system
  - `UTAGE / Lステップ / Google Sheets / その他`
- business event
  - 何が起きた瞬間を relay したいか
- webhook payload
  - email に使う key
  - 商品やイベントを識別する key
- Mailchimp 側の着地
  - `Audience*`
  - `Tag(s)`
  - downstream が `Journey` か `Campaign` か
- relay 方針
  - `既存 relay 修正 / 新規 relay / relay 不要`
- rollback 方針
  - exploratory なら `Delete Zap` まで戻すか

## 実装前の最小チェック

- その event は `Journey` を起動したいのか、`Campaign` の対象条件を作りたいのか
- Mailchimp 側で付けたい tag 名が、英語で 1 meaning になっているか
- email mapping に使う key が webhook payload で実在するか
- 既存 Zap の変更で済むのか、新規 Zap を切るべきかを 1 文で説明できるか
- downstream 側で `その tag が何を起動するか` を説明できるか

## 入口選択の exact な問い

- 今やりたいのは `既存 relay を読む / 修正する` か
  - なら `一覧 > Name / Apps / Location / Status` から current 行を特定
- 今やりたいのは `新規 relay を作る` か
  - なら `Create Zap`
- 今やりたいのは `relay が必要か自体を判断する` か
  - なら `UTAGE / Lステップ / Mailchimp 側で完結しないか` を先に確認

つまり、この skill では `新規 relay / 既存 relay / relay 不要` を最初に切る。

## 10秒判断

- `既存 relay 修正`
  - event meaning は同じ
  - 変えるのは `Audience* / Subscriber Email* / Tag(s)` の一部
- `新規 relay`
  - event meaning が違う
  - downstream の役割が変わる
- `relay 不要`
  - front system 側だけで閉じる
  - Mailchimp 側の既存条件だけで足りる

この 10 秒判断が言えない時は、`Create Zap` を押さない。

## 最小 live test

最初の 1 本は `webhook -> Mailchimp Add/Update Subscriber` の 2 step だけで閉じる。

1. `Create`
2. `Create Zap`
3. `Untitled Zap`
4. `Folder = 甲原`
5. `Trigger`
6. `Webhooks by Zapier`
7. `Catch Hook`
8. `Test trigger`
9. `Action`
10. `Mailchimp`
11. `Add/Update Subscriber`
12. `Audience*`
13. `Subscriber Email*`
14. `Tag(s)`
15. `Test step`
16. exploratory なら `Delete Zap`

最初から `Paths / Filter / Formatter / Code` を足さない。まず 2 step で event と downstream の意味が閉じるかを見る。

## 最小 live change

既存 current relay を触る時は、最初の 1 回を `1 field だけ変える` に制限する。

1. 対象 row の `Name`
2. `Apps`
3. `Status`
4. editor
5. 変更対象を 1 つに固定
   - `Audience*`
   - `Subscriber Email*`
   - `Tag(s)`
6. `Test step`
7. downstream の Mailchimp 側確認
8. 問題なければ保存

最初から複数 field を同時変更しない。`Audience*` と `Tag(s)` を同時に変えると、問題の切り分けが崩れる。

## 既存 relay change smoke

既存 relay を触った後は、変更箇所だけでなく downstream まで最小確認する。

1. 一覧へ戻る
2. `Name`
3. `Apps`
4. `Status`
5. editor を開き直す
6. 変更した 1 field を再確認
7. `Test step`
8. downstream の Mailchimp 側で intended な `Journey / Campaign` 条件と矛盾しないか確認

`field は変わったが downstream の意味が変わった` を防ぐため、一覧確認だけで終えない。

## 最小 rollback

exploratory に新規 relay を開いた時は、rollback を exact に持つ。

1. `Create Zap`
2. `Untitled Zap`
3. `Folder = 甲原`
4. `Trigger`
5. `Action`
6. 2 step が見えた時点で、使わないなら title menu
7. `Delete`
8. `Delete Zap`

`Draft のまま閉じる` を cleanup とみなさない。一覧から消えたところまで確認して rollback 完了とする。

## 新規 relay の最小 downstream smoke

新規 relay は `step を置けた` で終わらせない。

1. `Untitled Zap` か intended な `Name`
2. `Folder = 甲原`
3. `Trigger`
4. `Action`
5. `Test step`
6. Mailchimp 側の intended な `Audience`
7. intended な `Subscriber Email*`
8. intended な `Tag(s)`
9. downstream の `Journey / Campaign` と意味が矛盾しないこと

`Test step` が成功しても、Mailchimp 側の tag や audience が intended でなければ smoke 完了にしない。

## 複雑 relay を足す順

複雑化は、次の順で 1 つずつ足す。

1. `Webhooks by Zapier / Catch Hook`
2. `Mailchimp / Add or Update Subscriber`
3. `Tag(s)` の意味確認
4. 追加の action
5. `Paths` や例外処理

最初に `受ける`, 次に `Mailchimp へ渡す`, その後に `例外` を足す。`Trigger / 複数 Action / 例外処理` を同時に増やすと、どこで relay meaning が崩れたか切れなくなる。

### `relay 不要` にする判断

次のどれかなら、まず Zapier を増やさない。
- Lステップ 単体で state と action が閉じる
- UTAGE の `購入後アクション` や `バンドルコース` だけで目的を果たせる
- Mailchimp 側の既存 tag / saved segment の組み替えだけで足りる

つまり、`つなげると便利そう` では作らない。`front system 単体では目的を果たせない` 時だけ relay を作る。

### `既存 relay 修正` を優先する判断

次の条件をすべて満たすなら、まず `既存 relay 修正` を優先する。
- business event の意味が同じ
- 変えたいのが
  - `Audience*`
  - `Subscriber Email*`
  - `Tag(s)`
  のいずれか 1 つか少数
- downstream の `Journey / Campaign` 役割を変えない

つまり、event meaning が同じなら relay を増やさず、まず既存 row の修正を疑う。

### `新規 relay` を優先する判断

次のどれかが `yes` なら、`既存 relay 修正` より `新規 relay` を優先する。
- business event の意味が違う
- downstream の `Journey / Campaign` 役割が変わる
- 既存 relay を変えると複数導線へ波及する
- 既存 Zap 名では event meaning を表せない

## Workflow

1. Zap 一覧を開く
2. 対象 row の `Name / Apps / Last modified / Status` を確認する
3. editor を開く
4. step 1 `Webhooks by Zapier / Catch Hook`
5. step 2 `Mailchimp / Add or Update Subscriber`
6. audience / tag / email mapping を確認する
7. 必要なら新規 relay を同じ family で作る
8. downstream の Mailchimp 条件まで確認する

## current の exact route

- 一覧
  - `https://zapier.com/app/assets/zaps`
- editor
  - `https://zapier.com/editor/{zap_id}/published`
- create 入口
  - `https://zapier.com/webintent/create-zap?useCase=from-scratch`

current では `Create` を開いた時点で `Untitled Zap / Draft` が残ることがある。探索だけなら、その場で削除まで戻す前提にする。

## exact 手順

### current の主入口

- 一覧
  - `https://zapier.com/app/assets/zaps`
- editor
  - `https://zapier.com/editor/{zap_id}/published`

### 一覧で最初に見る列

- `Name`
- `Apps`
- `Location`
- `Last modified`
- `Status`
- `Owner`

### current family

Addness の current 主戦場は次。
- `Webhooks by Zapier`
  - `Catch Hook`
- `Mailchimp`
  - `Add/Update Subscriber`

representative family
- オプトイン relay
- 購入 relay
- `秘密の部屋` relay
- `AIコンテンツ完全習得Live / AICAN` relay
- `アクションマップ` relay
- `フリープラン / プロモーション` relay
- `SMS` 例外 relay

## representative pattern

### オプトイン relay 型

- 目的
  - front の登録 event を Mailchimp の `audience + tag` に変換する
- 先に見る場所
  - `Webhooks by Zapier / Catch Hook`
  - `Mailchimp / Add/Update Subscriber`
  - `Audience*`
  - `Subscriber Email*`
  - `Tag(s)`
- 向いている場面
  - LP opt-in
  - フォーム登録

### 購入 relay 型

- 目的
  - 購入 event を Mailchimp 側の購入後 state に変換する
- 先に見る場所
  - webhook payload の商品識別 key
  - `Tag(s)`
  - downstream の Journey 起動条件
- 向いている場面
  - 商品購入
  - 会員化

### promotion relay 型

- 目的
  - 単発 promotion の対象条件を作る
- 先に見る場所
  - event の意味
  - `Tag(s)`
  - `Campaign` 側の segment 条件
- 向いている場面
  - フリープラン
  - プロモーション
  - 期間限定施策

### 例外 relay 型

- 目的
  - Mailchimp 以外の downstream へ例外処理を渡す
- 先に見る場所
  - `Apps`
  - relay 先 API
  - current 本線との切り分け
- 向いている場面
  - SMS
  - Sheets post
  - 一時例外処理

## representative pattern を読む時の問い

- この relay は `オプトイン / 購入 / promotion / 例外` のどれか
- 入力 event を、どの state に変換しているか
- `Audience*` と `Tag(s)` の組み合わせは、その目的に対して自然か
- downstream は `Journey` を起動したいのか、`Campaign` 対象を作りたいのか
- 既存 relay の修正で済むのか、新規 relay に分けるべきか
- 同じ event meaning を別 Zap として増やしていないか

## 最初の複雑パターン

最初に live で詰める複雑パターンは、`trigger 1 + action 2` だけで閉じる。

1. `Create`
2. `Create Zap`
3. `Untitled Zap`
4. `Folder = 甲原`
5. `Trigger`
6. `Webhooks by Zapier`
7. `Catch Hook`
8. `Test trigger`
9. `Action`
10. `Mailchimp`
11. `Add/Update Subscriber`
12. `Audience*`
13. `Subscriber Email*`
14. `Tag(s)`
15. `Test step`
16. 追加 action を 1 本だけ足す
17. downstream の intended meaning を確認
18. exploratory なら `Delete Zap`

最初から
- `Paths`
- `Filter`
- `Formatter`
- 3 本目以降の action
を同時に足さない。

## ベストな活用場面

- front system の event を Mailchimp の state に安全に変換したい時
- `Journey` 起動用 tag を relay で安定供給したい時
- `Campaign` 用の高温セグメントを、別 system からの event で育てたい時

## よくあるエラー

- webhook payload の email key を誤る
- `Audience*` は合っているが `Tag(s)` が downstream の実運用とズレる
- 既存 Zap を流用すべき場面で、新しい relay を乱立させる
- `Untitled Zap / Draft` を残して current relay と混ざる

## エラー時の切り分け順

1. この relay が `オプトイン / 購入 / promotion / 例外` のどれかを切る
2. `Catch Hook` の payload で email key を確認する
3. `Add/Update Subscriber` の `Audience* / Subscriber Email* / Tag(s)` を確認する
4. downstream の Mailchimp 側で、その tag が何を起動または除外するか確認する
5. 新規 relay にすべきか、既存 relay 修正で足りるかを再判定する

### relay を読む時の確認項目

1. step 1 が `Webhooks by Zapier / Catch Hook`
2. step 2 が `Mailchimp / Add/Update Subscriber`
3. audience
4. member status
5. update existing
6. tag
7. email mapping
8. Zap 名と tag の意味が一致しているか
9. downstream の Mailchimp 側で、その tag が何を起動するか

Mailchimp step では、少なくとも次の field label を UI 上で確認する。
- `Audience*`
- `Subscriber Email*`
- `Tag(s)`
- `Status`
- `Update Existing`

### create builder の見方

新規 builder を開いたら、最初に次を見る。
- `Untitled Zap`
- `Draft`
- `Trigger`
- `Action`

### step 内で最初に見る exact ラベル

Trigger 側
- `Choose app & event`
- `Trigger event`
- `Account`
- `Test trigger`

Action 側
- `Choose app & event`
- `Action event`
- `Account`
- `Set up action`
- `Test step`

このラベルが見えない時は、いまいる画面を trigger/action の設定画面だと誤認している可能性を先に疑う。

その後、Addness の current ではまず次を選ぶ。
- `Webhooks by Zapier`
- `Catch Hook`
- `Mailchimp`
- `Add/Update Subscriber`

Mailchimp action の exact 入口で固定するラベル
- `Choose app & event`
- `Action event`
- `Account`
- `Set up action`
- `Audience*`
- `Subscriber Email*`
- `Tag(s)`
- `Status`
- `Update Existing`

folder は step ではなく `Zap details` 側で管理する。
- `Folder`
- current の新規は原則 `甲原`

### 新規 relay の exact 順

1. `Create`
2. `Create Zap`
3. builder 上部で `Untitled Zap` を確認
4. 右上または details 側で `Folder = 甲原`
5. `Trigger`
6. `Webhooks by Zapier`
7. `Catch Hook`
8. `Action`
9. `Mailchimp`
10. `Add/Update Subscriber`
11. `Audience*`
12. `Subscriber Email*`
13. `Tag(s)`
14. `Status`
15. `Update Existing`
16. Zap 名を business event が読める名前へ変更

current の Addness では、`Trigger` より前に `Folder` と `Zap 名の意味` を固定しておくと、draft が増えても事故りにくい。

### publish 前に UI 上で必ず見るラベル

- `Publish`
- `Test trigger`
- `Test step`
- `Audience*`
- `Subscriber Email*`
- `Tag(s)`

`Publish` は `Test trigger` と `Test step` を通してから押す。`Audience* / Subscriber Email* / Tag(s)` を埋めただけで publish しない。

### `Test trigger` を読む時の rule

- sample payload の `メールアドレス` 系 key が intended な field かを先に見る
- 前回の別 event の sample を使い回していないかを見る
- `event meaning` が 1 文で言えない sample なら publish しない

`Test trigger` が通っただけでは完成扱いにしない。sample の意味が current event と一致して初めて次へ進む。

## sample quality のチェック

`Test trigger` と `Test step` は、通ったかどうかだけではなく sample の質で見る。

1. sample payload の event meaning を 1 文で言えるか
2. `Subscriber Email*` に渡す key が intended な email field か
3. `Tag(s)` が downstream の `Journey / Campaign` 条件と一致するか
4. `Audience*` が intended な audience か
5. 例外系 relay なのに `Mailchimp` family と混ざっていないか

どれか 1 つでも曖昧なら、`Publish` を止める。

## 最小 downstream smoke

relay を test したら、その場で次まで確認する。

1. `Test step`
2. `Audience*`
3. `Subscriber Email*`
4. `Tag(s)`
5. Mailchimp 側で intended な audience に入る前提か
6. その tag が intended な `Journey / Campaign` 条件と矛盾しないか

`Zapier 側で success` だけでは完了にしない。Mailchimp 側で意味が通るところまで見て smoke 完了とする。

### account と family の増殖を防ぐ current rule

- `Account *` では、まず既存の `Mailchimp アドネス株式会社` 系 account を流用できるか確認する
- exploratory に `+ Connect a new account` を押さない
- `Mailchimp / Add/Update Subscriber` 以外の family は、既存 current relay で足りない理由を 1 文で言える時だけ使う
- `Paths / Filter / Formatter / Code` を足したくなった時は、まず `既存 relay 修正` と `relay 不要` を再判定する

### 30秒レビューの順番

1. `Name`
2. `Apps`
3. `Location`
4. `Status`
5. step 1 が `Webhooks by Zapier / Catch Hook` か
6. step 2 が `Mailchimp / Add/Update Subscriber` か
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. その tag が downstream で何を起動するか

## publish 前の最小チェック

1. event meaning を 1 文で言える
2. `Folder = 甲原`
3. `Audience*`
4. `Subscriber Email*`
5. `Tag(s)`
6. downstream の `Journey / Campaign` 側で、その tag の役割を言える
7. `Test trigger`
8. `Test step`

`Test trigger` と `Test step` を通さずに `Publish` しない。

## publish を止める条件

次のどれかがある時は、`Publish` しない。

- `Tag(s)` の意味を 1 文で言えない
- downstream の `Journey / Campaign` 名を言えない
- 既存 relay との差分が 1 field を超えている
- `Test trigger` の sample が intended な event か断言できない
- `Test step` を通していない

## editor に入れない時の fallback順

published editor に直接入れない、または `access_issue` が出る時は、次の順で読む。

1. `Assets > Zaps`
2. `Name`
3. `Apps`
4. `Location`
5. `Status`
6. `Folder`
7. 既知の family と照合
8. editor は最後に再試行

つまり、editor が閉じていても `一覧で family を切れるなら作業を止めない`。一方、step の exact 設定値が必要な変更は、その時点で止めて確認する。

## 最小 relay 構成

最低でも次が揃っていることを確認する。
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- audience
- email
- tag

current の Addness では、ここに加えて次が揃うとかなり安全。
- Zap 名だけで event の意味が読める
- `Folder = 甲原`
- `update existing = true`
- email mapping が webhook payload の `メールアドレス` 系 key と一致

## exception family

Addness の current では、次は main family と分けて読む。
- `Google Sheets -> Webhooks by Zapier POST`
- external SMS API 宛て

これは `Mailchimp tag relay` ではなく、業務例外 relay として扱う。

## 検証

最低でも次を確認する。
- Zap 名だけで event の意味が読める
- step 1 と step 2 が正しい family
- audience が意図どおり
- email mapping が webhook payload の正しい key
- tag が downstream の Journey / Campaign 条件と一致している
- 同じ event を別名 relay として重複作成していない
- `SMS` 例外 relay を `Mailchimp tag relay` と混同していない

## 保存前の最小チェック

- `Trigger = Webhooks by Zapier / Catch Hook`
- `Action = Mailchimp / Add/Update Subscriber`
- audience
- email mapping
- tag
が埋まっているか

## 保存後の最小チェック

- 一覧で `Name / Apps / Location / Status` が意図どおりか
- `Folder` が `甲原` か
- downstream の Mailchimp 側で、その tag を条件にした導線が読めるか
- `Account *` が exploratory な新規接続になっていないか
- `Mailchimp / Add/Update Subscriber` 以外の family を増やしていないか
- `Test trigger` の sample が intended な event のものだったか

## 構築精度だけを見る時のチェック

1. この relay が `オプトイン / 購入 / promotion / 例外` のどれかで 1 文になっているか
2. `Trigger` と `Action` が current family から外れていないか
3. `Subscriber Email*` が webhook payload の正しい key を指しているか
4. `Audience*` と `Tag(s)` が downstream の Mailchimp 条件と整合しているか
5. `Folder = 甲原` と Zap 名の event 意味が一致しているか
6. `Test trigger` と `Test step` で最低限の疎通確認ができているか
7. exploratory な `Untitled Zap / Draft` を残さず cleanup できるか
8. `Account *` や app family の選択が current 本線から逸れていないか

## relay 作成後の最終確認順

1. 一覧へ戻る
2. `Name`
3. `Apps`
4. `Location`
5. `Status`
6. editor を開き直す
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. `Update Existing`
11. downstream の Mailchimp 側で、その tag が何を起動するか

## publish 後の smoke

publish した relay は、最低限次の smoke を通す。

1. 一覧で `Status` が intended か
2. `Apps` が `Webhooks by Zapier` と `Mailchimp` の 2 step で閉じているか
3. editor を開き直して `Audience* / Subscriber Email* / Tag(s)` が想定値か
4. downstream の Mailchimp 側で intended な `Journey / Campaign` 条件と一致するか

`Publish できた` を完了にしない。downstream まで見て初めて smoke 完了とする。

この順で見れば、`Zapier 上では正しそうだが downstream が違う` を先に潰せる。

## 危険な新規 relay シグナル

次のどれかがある時は、その場で新規 relay を作らない。

- `Tag(s)` の意味が 1 文で言えない
- 既存 Zap と event meaning が重複して見える
- downstream の `Journey / Campaign` 側で、その tag の役割が読めない
- `Mailchimp / Add/Update Subscriber` 以外の family を使いたくなっている
- `Paths`
  - `Filter`
  - `Formatter`
  - `Code`
  などを足したくなっている
- `Create Zap` を押した理由が `既存 relay を読むのが面倒だから` になっている

この場合は、まず `既存 relay の修正` か `relay 不要` を再判定する。

## 修正か新規かで迷った時の確認順

1. Zap 名だけで event meaning を言う
2. downstream の `Journey / Campaign` 名を言う
3. 変えたい field が
   - `Audience*`
   - `Subscriber Email*`
   - `Tag(s)`
   のどれかを言う
4. 既存 relay を変えた時に、他の導線へ波及するか切る
5. 波及しないなら `既存 relay 修正`
6. 波及するなら `新規 relay`

## 完成条件

- Zap 名だけで event の意味が読める
- `Webhook -> Mailchimp Add/Update Subscriber` の 2 step 構造を説明できる
- audience / email mapping / tag を 1 回で言える
- downstream の Mailchimp 条件まで追える

## cleanup

exploratory な draft を開いただけなら、その場で削除する。
- builder 右上または title menu
- `Delete Zap`
- builder 側で消しにくい時は `Assets > Zaps` の row action を使う

`Untitled Zap` を残さない。

cleanup 前に最低でも次を見る。
- `Folder`
- `Status`
- `Last modified`

つまり、current の published relay を消さずに、探索中の `Untitled Zap / Draft` だけを消す。

current の exact cleanup 導線は
- title menu
- `Delete`
- `Delete Zap?`
- `Delete Zap`
の順で扱う。

assets 一覧 fallback の exact cleanup 導線は
- `Assets > Zaps`
- intended row の `Zap actions`
- `Delete`
- confirm `Delete`

exploratory draft は、builder でも assets 一覧でも消せる。使いにくい方に固執せず、`一覧検索で 0件` まで確認できる導線を正とする。

## 症状から最初に疑う場所

- `Test step` は成功するのに Mailchimp 側で何も起きない
  - まず `Audience*`
  - 次に `Subscriber Email*`
  - 最後に `Tag(s)` と downstream の `Journey / Campaign` 条件
- 既存 relay を直したつもりなのに別導線まで影響しそう
  - まず `Name`
  - 次に event meaning
  - その後に `既存 relay 修正` ではなく `新規 relay` へ切るべきかを疑う
- sample は正しそうだが intent と違う tag が付く
  - まず `Tag(s)`
  - 次に `Journey / Campaign` 側の条件
  - その後に webhook payload の event meaning
- 新規 relay を作り始めたが構成が膨らみ始めた
  - まず `relay 不要`
  - 次に `既存 relay 修正`
  - それでも足りない時だけ `新規 relay`
- `Untitled Zap / Draft` が増えて current が見分けにくい
  - まず `Folder`
  - 次に `Status`
  - exploratory draft ならその場で `Delete Zap`

## NG

- tag の意味が曖昧なまま relay を増やす
- email mapping を固定文字列だと思い込む
- audience を確認せずに進める
- current relay を読まずに別 family を増やす
- Addness 固有 tag 名を skill 内に焼き込む
- folder を決めずに新規 Zap を作る
- `Untitled Zap` の draft を残す
- relay 不要なのに、念のためで Zapier を増やす

## 正誤判断

正しい状態
- `1 event = 1 meaning` で relay を説明できる
- webhook payload からどの key を使っているか分かる
- audience と tag の関係を downstream まで言える
- 一覧を見て、その Zap が
  - オプトイン
  - 購入
  - promotion
  - SMS 例外
  のどれかをすぐ分類できる

間違った状態
- Zap 名はあるが event の意味が曖昧
- audience と tag の整合が取れていない
- relay 先の Mailchimp 条件を見ずに完了扱いにする
- front system 単体で閉じるのに relay を増やして責務を散らす

## ここで止めて確認する条件

- webhook payload の key 名が current 実装と違って見える
- 既存 Zap を変えると、複数の current funnel に波及しそう
- 付けたい tag が Mailchimp 側の current 命名規則に乗っていない
- `Webhooks by Zapier -> Mailchimp Add/Update Subscriber` 以外の family を新規で使いたい
- relay 先が Mailchimp ではなく、外部 API や Google Sheets で本番影響が読みにくい
- `Test trigger` の sample が intended な event か説明できない
- 2 step の最小 relay で閉じるか未確認のまま `Paths / Filter / Formatter / Code` を足したくなっている

## publish 後の最小 downstream smoke

publish 後は、Zapier 上の success だけで完了にしない。

1. `Assets > Zaps`
2. intended な row の `Status`
3. editor を開き直す
4. `Audience*`
5. `Subscriber Email*`
6. `Tag(s)`
7. Mailchimp 側で、その tag が intended な `Journey / Campaign` 条件で読めるか確認

`Publish` の成功は relay 成立の十分条件ではない。Mailchimp 側で intended な state として読めて smoke 完了とする。

## References

- Addness 固有の current 例と判断は `Master/addness/zapier_structure.md`
- representative な exact 手順は `references/workflow.md`
