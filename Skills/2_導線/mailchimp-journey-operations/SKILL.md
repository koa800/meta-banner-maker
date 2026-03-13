---
name: mailchimp-journey-operations
description: Mailchimpの `Customer Journeys` で evergreen な自動メール導線を作成、編集、検証する skill。Mailchimpで同じシナリオを継続的に流す時、`Tag added` などの trigger から flow を組みたい時、step の current / legacy を見分けながら安全に修正したい時に使う。
---

# mailchimp-journey-operations

## Overview

Mailchimp の `Customer Journeys` を、`Build from scratch` から `trigger / filter / email step / report` まで exact 手順で扱う skill です。

Addness 固有の naming、current representative、CTA ルールは `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill は、どの案件でも再利用できる exact 手順だけを持つ。

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

### current 判定

`last_started_at` だけで current と判断しない。最低でも次を見る。
- journey status が `sending`
- step status が `active`
- `queue_count > 0`

## 検証

最低でも次を確認する。
- trigger が意図どおり
- tag 名が正しい
- main CTA が正しい
- hyperlink の実 URL が正しい
- report で `sent / open / click` が追える

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

間違った状態
- 単発配信を `Journey` に入れる
- step 名だけで current と判断する
- draft を current 実績と混ぜる

## References

- Addness 固有の current 例と判断は `Project/3_業務自動化/メールマーケティング自動化.md`
- representative な exact 手順は `references/workflow.md`
