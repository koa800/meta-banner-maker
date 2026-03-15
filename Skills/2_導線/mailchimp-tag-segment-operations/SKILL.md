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

## 実装前の最小チェック

- `Journey` 用の state か、`Campaign` 用の単発条件か切れているか
- audience を先に固定したか
- `誰に送りたいか` を 1 文で説明できるか
- tag 名を英語で `media_funnel_event` に落とせるか
- exclude が必要か先に切ったか

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

## current rule

- Mailchimp の tag 名は英語で作る
- 基本構造は `media_funnel_event`
- 例
  - `meta_ai_optin`
- `x_skillplus_webinar1_optin`
- `linead_sns_consult_reserve`

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

## ベストな活用場面

- evergreen の入口条件を `Tag added` で固定したい時
- 単発配信の対象を `saved segment / tag / exclude` で明確に切りたい時
- downstream の `Journey` と `Campaign` の入口を混ぜずに管理したい時

## よくあるエラー

- evergreen 用の state を campaign 向けの一時条件として切ってしまう
- 日本語のまま tag 名を作ろうとする
- `saved segment` で済むのに、不要な新規 tag を増やす
- `Exclude` を後回しにして、送ってはいけない相手を外し忘れる

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

間違った状態
- tag 名から意味が読めない
- `誰に送るか` が UI 上の設定頼みで、口頭で説明できない

## ここで止めて確認する条件

- その tag が evergreen の state なのか、単発配信条件なのか切れない
- 既存 tag を流用すべきか新規作成すべきか判断できない
- 日本語でしか意味を保てず、英語命名に落とせない
- `誰に送るか` と `誰を除外するか` の境界が曖昧
- `saved segment` で切るべきか `Tag added` で切るべきか、Journey と Campaign の入口が混ざる

## References

- Addness 固有の representative は `Project/3_業務自動化/メールマーケティング自動化.md`
- current 運用の補足は `Master/addness/README.md`
