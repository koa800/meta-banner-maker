---
name: mailchimp-tag-segment-operations
description: Mailchimpで `tag` と `saved segment` を current 運用に沿って扱う skill。英語 tag の命名、誰に送るかの切り方、Campaign や Journey の入口条件を安全に決めたい時に使う。
---

# mailchimp-tag-segment-operations

## Overview

Mailchimp の `tag` と `saved segment` を、current 運用に沿って exact に扱う skill です。

Addness 固有の current 例、代表 tag、配信実績のある segment は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill では、どの案件でも再利用できる tag / segment の判断と操作の型だけを持つ。

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

## 検証

最低でも次を確認する。
- tag 名が英語である
- `media_funnel_event` の構造で読める
- Journey なら trigger tag を説明できる
- Campaign なら `saved segment / tag / exclude` を 1 回で説明できる

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

## References

- Addness 固有の representative は `Project/3_業務自動化/メールマーケティング自動化.md`
- current 運用の補足は `Master/addness/README.md`
