---
name: mailchimp-tag-segment-operations
description: Mailchimpで `tag` と `saved segment` を current 運用に沿って扱う skill。英語 tag の命名、誰に送るかの切り方、Campaign や Journey の入口条件を安全に決めたい時に使う。
---

# mailchimp-tag-segment-operations

## Overview

Mailchimp の `tag` と `saved segment` を、current 運用に沿って exact に扱う skill です。

Addness 固有の current 例、代表 tag、配信実績のある segment は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill では、どの案件でも再利用できる tag / segment の判断と操作の型だけを持つ。

## ツールそのものの役割

`tag` と `saved segment` は、誰に送るか、誰を除外するか、どの自動化へ入れるかを定義する state layer です。

## アドネスでの役割

アドネスでは `tag` と `saved segment` を、単なる分類ではなく `どの認識変換を次に流すか` を決める入口条件として使う。`Journey` の state と `Campaign` の単発対象を混ぜないのが重要です。

## 役割

`tag` と `saved segment` は、誰に送るかを定義する state layer です。

## ゴール

次を迷わずできる状態を作る。
- 新しい `tag` 名を正しく決める
- `Journey` の trigger tag を切る
- `Campaign` の `saved segment / tag / exclude` を切る
- `誰に送るか` を 1 回で説明できる

## 必要変数

- Journey か Campaign か
- audience
- 媒体
- ファネル
- イベント
- 誰に送りたいか
- 除外したい人がいるか

## 依頼を受けたら最初に埋める項目

- `Journey` か `Campaign` か
- `Audience`
- 送りたい相手
- 除外したい相手
- `tag` で持つ state か
- `saved segment` で切る一時条件か
- tag 名候補
  - `media_funnel_event`
- downstream の `Journey / Campaign`

## 実装前の最小チェック

- `Journey` 用の state か、`Campaign` 用の単発条件か切れているか
- audience を先に固定したか
- `誰に送りたいか` を 1 文で説明できるか
- tag 名を英語で `media_funnel_event` に落とせるか
- exclude が必要か先に切ったか

## 入口選択の exact な問い

- 今やりたいのは `evergreen flow の入口条件を作る` ことか
  - なら `tag`
- 今やりたいのは `今回だけ送る対象条件を切る` ことか
  - なら `saved segment` または `tag + exclude`
- 今やりたいのは `実際に配信文を作る` ことか
  - それはこの skill ではなく `Journey` または `Campaign`
- 今やりたいのは `結果を読む` ことか
  - それはこの skill ではなく `report`

つまり、この skill の入口は `state を作るか、配信対象を切るか` で決まる。

## 判断フレーム

### `tag` を先に切る時

次のどれかなら `tag` を先に決める。
- Journey の trigger を作る
- downstream で状態を引き回したい
- 他システムから relay してくる event を固定したい

### `saved segment` を先に切る時

次のどれかなら `saved segment` を先に見る。
- 1回きりの Campaign
- 既存 audience の中から複数条件で絞る
- exclude を含めた配信対象を repeatable にしたい

## `tag` と `saved segment` を混ぜない原則

- `tag`
  - evergreen の state を持たせる
  - `Journey` の入口や downstream state に使う
- `saved segment`
  - 今回だけ送る母集団を切る
  - `Campaign` の対象条件に使う

`同じ人が何に入ったか` を持ちたいなら `tag`。`今回だけ誰に送るか` を切りたいなら `saved segment`。

## current rule

- Mailchimp の tag 名は英語で作る
- 基本構造は `media_funnel_event`
- 例
  - `meta_ai_optin`
- `x_skillplus_webinar1_optin`
- `linead_sns_consult_reserve`

## 新規 tag / 既存 tag / saved segment の切り方

## 10秒判断

- 新規 `tag`
  - downstream の `Journey` 入口として新しい state が必要
  - 既存 tag 名では event の意味が崩れる
- 既存 `tag`
  - 既に current で同じ event meaning を持っている
  - 新規に増やすと state が分散する
- `saved segment`
  - 今回だけの配信対象条件
  - 複数条件の掛け合わせや除外が主役

まず `evergreen の state` か `単発配信の対象条件` かを切る。ここを曖昧にしたまま UI を開かない。

### 命名の最小型

- `media_funnel_event`
- 例
  - `meta_ai_optin`
  - `x_skillplus_webinar1_optin`
  - `linead_sns_consult_reserve`

`媒体 / ファネル / イベント` の 3 要素で 1 回で読めない時は、tag 名を確定しない。

## representative pattern

### Journey state 型

- 目的
  - evergreen の入口条件を作る
- 先に見る場所
  - `Tag added`
  - trigger tag 名
  - downstream の Journey 名
- 向いている場面
  - opt-in
  - 購入後 state
  - 継続教育

### Campaign targeting 型

- 目的
  - 1回きりの配信対象を切る
- 先に見る場所
  - `Audience`
  - `Segment or Tag`
  - `Exclude`
- 向いている場面
  - 単発 promotion
  - 再案内
  - 告知

### Exclusion 型

- 目的
  - 送りたくない人を外して配信事故を防ぐ
- 先に見る場所
  - exclude 条件
  - 既存 state との競合
- 向いている場面
  - 購入者除外
  - 予約済み除外
  - 高温リストの保護

## representative pattern を読む時の問い

- これは `Journey state / Campaign targeting / Exclusion` のどれか
- tag を作るべきか、saved segment を使うべきか
- この条件は evergreen の state か、一時的な配信条件か
- downstream で何を起動または除外したいのか
- tag 名を見て `媒体 / ファネル / イベント` を 1 回で言えるか
- `一度きりの配信条件` を state として残そうとしていないか

## ベストな活用場面

- evergreen の入口条件を `Tag added` で固定したい時
- 単発配信の対象を `saved segment / tag / exclude` で明確に切りたい時
- downstream の `Journey` と `Campaign` の入口を混ぜずに管理したい時

## よくあるエラー

- evergreen 用の state を campaign 向けの一時条件として切ってしまう
- 日本語のまま tag 名を作ろうとする
- `saved segment` で済むのに、不要な新規 tag を増やす
- `Exclude` を後回しにして、送ってはいけない相手を外し忘れる
- event meaning が固まっていないのに exploratory な新規 tag を作って state を汚す

## エラー時の切り分け順

1. それが `Journey` 入口か `Campaign` 対象条件かを切る
2. audience を固定する
3. 新規 tag が必要か、既存 tag か saved segment で足りるかを判定する
4. `誰に送るか` と `誰を除外するか` を 1 文ずつ言う
5. downstream の `Journey / Campaign` 側で intended な条件になっているか確認する

## Workflow

1. `Journey` か `Campaign` かを決める
2. audience を決める
3. `tag` か `saved segment` かを決める
4. `media_funnel_event` で名前を切る
5. 送らない相手がいるなら `Exclude` まで切る
6. `誰に送るか` を 1 回で説明できるか確認する

探索だけの段階では、新規 tag や saved segment を増やさない。意味が 1 文で固定できるまで、既存一覧の読解で止める。

## 最小 live test

最初の 1 本は `新規追加しない判断` を先に確定する。

1. `Journey` か `Campaign` かを切る
2. `Audience`
3. 既存 `tag`
4. 既存 `saved segment`
5. `Exclude`
6. `誰に送るか`
7. `誰を除外するか`

## 最小 downstream smoke

条件を切ったら、必ず downstream 側で意味を確認する。

1. intended な `tag` か `saved segment`
2. `Journey` なら intended な trigger 条件か
3. `Campaign` なら intended な `Segment or Tag / Exclude` 条件か
4. 一時条件を恒久 state にしていないか

条件が intended な配信面で自然に読めない時は、命名か切り方をやり直す。

まず `既存 tag / 既存 saved segment で足りるか` を読む。最初から新規 tag や new segment を作らない。

## 最小 live create

新規作成を伴う最初の 1 本は、`tag` と `saved segment` を別テストとして扱う。

### `tag` の最小 live create

1. `Customer Journeys`
2. intended な `Journey`
3. `Build from scratch`
4. `Choose a trigger`
5. `Tag added`
6. 新規 tag 名を `media_funnel_event` で確定
7. `Set a tag`
8. `Save Trigger`
9. downstream の `Journey` 側で trigger として読めるか確認

### `saved segment` の最小 live create

1. `Campaign Manager`
2. `Create`
3. `Regular email`
4. `Audience`
5. `Segment or Tag`
6. `Create segment`
7. 条件を 1 つだけで作る
8. `Save segment`
9. 対象人数が intended か確認

#### live 確認済みの補助経路

- helper: `python3 System/scripts/mailchimp_segment_helper.py create-static-empty --name ZZ_TEST_SEGMENT_...`
- rollback: `python3 System/scripts/mailchimp_segment_helper.py delete --id <segment_id>`
- これは API 側の create / delete exact 性を確認する補助経路で、UI 上の `Campaign Manager -> Segment or Tag -> Create segment` を置き換えるものではない
- 2026-03-16 は `zz_test_segment_20260316_exact` を create し、`id=4641613` を delete して `status_code=204` まで確認済み

#### `tag` の補助経路

- 一覧読解:
  - `python3 System/scripts/mailchimp_tag_helper.py list-tags --limit 10`
- safe test member 候補探索:
  - `python3 System/scripts/mailchimp_tag_helper.py search-members --query "@team.addness.co.jp" --limit 10`
  - `python3 System/scripts/mailchimp_tag_helper.py search-members --query "koa800" --limit 10`
- 2026-03-16 の live exact:
  - `koa800sea.nifs+1006@gmail.com`
  - `status=pending`
  - `tags_count=0`
  - この member で `zz_test_tag_20260316_exact` を `add-tag -> member確認(tags_count=1) -> remove-tag -> member確認(tags_count=0)` まで通した
- safe test member がある時だけ:
  - add:
    - `python3 System/scripts/mailchimp_tag_helper.py add-tag --email <safe_test_member> --tag zz_test_xxx`
  - rollback:
    - `python3 System/scripts/mailchimp_tag_helper.py remove-tag --email <safe_test_member> --tag zz_test_xxx`
- これは API 側の add / remove exact 性を確認する補助経路で、UI 上の `Tag added` や `Segment or Tag` の役割判断そのものを置き換えるものではない

最初から `tag` と `saved segment` を同時に新規作成しない。どちらの state layer を増やすかを 1 回で切ることを優先する。

## 最初の複雑パターン

最初に live で詰める複雑パターンは、`saved segment + Exclude` の 2 条件だけで閉じる。

1. `Campaign Manager`
2. exploratory draft を 1 本だけ作る
3. `Audience`
4. `Segment or Tag`
5. `saved segment`
6. `Exclude`
7. 対象人数が intended か確認
8. exploratory なら draft を削除

最初から
- 新規 `tag`
- 複数の `saved segment`
- 多段の exclude
を同時に足さない。

### save を伴う最小 live test の条件

次をすべて満たす時だけ、新規 tag か new saved segment を作る。
- `Journey state` か `Campaign targeting` かを 1 文で言える
- `media_funnel_event` で英語名を確定している
- downstream の `Journey / Campaign` 側で、その条件が何を起動または除外するか言える
- 既存 tag / saved segment で足りない理由を言える

上の条件が欠ける時は、tag/segment の live test は `既存一覧読解` までで止める。

## 最小 rollback

exploratory に state を増やした時は、`残さない` を先に優先する。

### `saved segment`

1. exploratory な draft または対象 campaign
2. `Segment or Tag`
3. exploratory に作った条件
4. `Delete` または未保存のまま閉じる
5. 対象人数が元に戻ることを確認

### `tag`

1. exploratory に trigger へ入れた tag 名
2. `Tag added`
3. 元の tag へ戻す、または exploratory flow を `Delete flow`
4. downstream でその tag が残っていないことを確認

`saved segment` は campaign 側から消し、`tag` は flow 側の入口条件から戻す。意味の違う state layer を同じ cleanup 手順で扱わない。

safe test member がある時は、rollback の実装面を API helper で補助できる。
- `python3 System/scripts/mailchimp_tag_helper.py remove-tag --email <safe_test_member> --tag zz_test_xxx`
- 2026-03-16 は `koa800sea.nifs+1006@gmail.com` で rollback 後 `tags_count=0` に戻ることまで確認済み

## 変更後の最小 smoke

条件を変えた後は、`作れた` では閉じない。

1. intended な `Audience`
2. intended な `Tag added` または `Segment or Tag`
3. intended な `Exclude`
4. intended な対象人数または trigger 意味
5. downstream の `Journey / Campaign`

この 5 つを 1 文で言えない時は、新しい state を増やさない。

## exact 手順

### Journey 側

1. `Build from scratch`
2. `Name flow`
3. `Audience`
4. `Choose a trigger`
5. `Tag added`
6. `Set a tag`
7. `Filter who can enter`
8. `Save Trigger`

### Campaign 側

1. `Campaign Manager`
2. `Create`
3. `Regular email`
4. `Audience`
5. `Segment or Tag`
6. 必要なら `Exclude`

### current UI で先に固定するラベル

- `Audience`
- `Segment or Tag`
- `Exclude`
- `Tags`
- `Saved segments`
- `Create segment`
- `Save segment`
- `Tag added`
- `Set a tag`
- `Filter who can enter`
- `Save Trigger`

### exact に見る順番

1. `Journey` か `Campaign` か切る
2. `Audience`
3. `Tag added` か `Segment or Tag` か切る
4. 新規作成か既存流用かを切る
5. `Exclude` が必要か切る
6. `誰に送るか`
7. `誰を除外するか`
8. downstream の `Journey / Campaign` を言えるか確認する

### exploratory 時の cleanup 原則

- 意味が 1 文で固定できる前に、新規 `tag` や `saved segment` を増やさない
- exploratory に `Create segment` を開いた時は、保存せずに閉じる
- downstream の event meaning が固定するまで、既存一覧の読解だけで止める

### new tag を作る前の exact チェック

1. `媒体 / ファネル / イベント` を英語で 1 回で言える
2. 既存 tag で同じ meaning がない
3. その tag が `Journey` の入口か `Campaign` の対象条件か切れている
4. downstream の `Journey / Campaign` 名を言える

### saved segment を作る前の exact チェック

1. 単発配信である
2. `Audience`
3. `Segment or Tag`
4. `Exclude`
   の 3 層で条件を説明できる
5. この条件が evergreen state ではない

### `Exclude` を決める前の exact チェック

1. `誰を送らないか` を 1 文で言える
2. `購入済み / 予約済み / 別 branch 進行中`
   のどれに近いか切れている
3. `Exclude` しないと起きる事故を言える

### 30秒レビューの順番

1. `Audience`
2. `Journey` か `Campaign` か
3. `Tag added` か `Segment or Tag` か
4. 新規か既存流用か
5. `Exclude`
6. `誰に送るか`
7. `誰を除外するか`
8. downstream の `Journey / Campaign`

### current UI で先に固定するラベル

- `Customer Journeys`
- `Build from scratch`
- `Choose a trigger`
- `Tag added`
- `Set a tag`
- `Filter who can enter`
- `Save Trigger`
- `Campaign Manager`
- `Create`
- `Regular email`
- `Audience`
- `Segment or Tag`
- `Exclude`

## 検証

最低でも次を確認する。
- tag 名が英語である
- `media_funnel_event` の構造で読める
- Journey なら trigger tag を説明できる
- Campaign なら `saved segment / tag / exclude` を 1 回で説明できる

## 保存前の最小チェック

- tag か saved segment のどちらを作るべきか説明できるか
- `誰に送らないか` も必要なら決めているか

## 保存後の最小チェック

- tag 名や segment 条件を見て `誰に送るか` を 1 回で言えるか
- Journey / Campaign の downstream 条件と矛盾していないか
- 同じ meaning の state を重複作成していないか
- exploratory に開いた `Create segment` や未保存条件を残していないか
- `tag` と `saved segment` の役割を逆転させていないか

## 症状から最初に疑う場所

- `誰に送るか` が UI を見ないと説明できない
  - まず `tag` 名
  - 次に `saved segment` の条件
  - その後に `Exclude` の要否
- `Journey` が想定外に動く
  - まず trigger `tag`
  - 次に downstream の `Journey` 条件
  - その後に `Campaign` 用の一時条件を混ぜていないか
- `saved segment` を作ったのに人数が意図より少ない
  - まず `Audience`
  - 次に条件の積み方
  - その後に `Exclude`
- 新しい `tag` を切りたくなるが意味が揺れる
  - まず `媒体 / ファネル / イベント` の 1 meaning
  - その後に既存 tag 流用の可否

## 構築精度だけを見る時のチェック

1. `tag` か `saved segment` のどちらを作るか 1 文で説明できるか
2. `tag` 名が英語で 1 meaning か
3. `saved segment` の条件が一時配信専用になっているか
4. `Journey` 用 state と `Campaign` 用母集団を混ぜていないか
5. exploratory に増やした条件や state を cleanup できるか

## 完成条件

- tag 名だけで `媒体 / ファネル / イベント` が読める
- saved segment と exclude の役割を説明できる
- Journey と Campaign の入口を混同しない

## NG

- 日本語 tag を作る
- `copy` や暫定文字列を本番 tag 名に使う
- `誰に送るか` を説明できないまま segment を切る
- Journey 用の state と Campaign 用の一時配信条件を混ぜる

## 正誤判断

正しい状態
- tag 名だけで `媒体 / ファネル / イベント` が読める
- Campaign で `saved segment / exclude` が役割分担できている
- exploratory な新規 state を増やさず、意味が固まってから保存している

間違った状態
- tag 名から意味が読めない
- `誰に送るか` が UI 上の設定頼みで、口頭で説明できない
- `Journey` 入口と `Campaign` 対象条件を同じ tag で雑に兼用する

## ここで止めて確認する条件

- その tag が evergreen の state なのか、単発配信条件なのか切れない
- 既存 tag を流用すべきか新規作成すべきか判断できない
- 日本語でしか意味を保てず、英語命名に落とせない
- `誰に送るか` と `誰を除外するか` の境界が曖昧
- `saved segment` で切るべきか `Tag added` で切るべきか、Journey と Campaign の入口が混ざる
- `一度きりの配信条件` を `tag` で恒久 state 化しそう

## downstream smoke

保存後は、作った state が intended な使われ方をするかを最小確認する。

### `tag`

1. `Customer Journeys`
2. intended な flow
3. `Tag added`
4. 新規 tag 名
5. `Filter who can enter`

### `saved segment`

1. `Campaign Manager`
2. intended な draft または送信対象 row
3. `Audience`
4. `Segment or Tag`
5. `Exclude`
6. 対象人数

state を作って終わりにしない。`下流でその条件が intended に読めるか` まで確認して smoke 完了とする。

## References

- Addness 固有の representative は `Project/3_業務自動化/メールマーケティング自動化.md`
- current 運用の補足は `Master/addness/README.md`
