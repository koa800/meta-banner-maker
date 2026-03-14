---
name: zapier-webhook-mailchimp-relay-operations
description: Zapier の `Webhooks by Zapier` と `Mailchimp Add/Update Subscriber` を使う relay を読み、作り、検証する skill。UTAGE などの webhook event を Mailchimp の audience と tag に変換したい時、Addness の current relay family を exact に読みたい時、relay を壊さずに追加・確認したい時に使う。
---

# zapier-webhook-mailchimp-relay-operations

## Overview

Zapier の current 主戦場である `Webhook -> Mailchimp Add/Update Subscriber` relay を、一覧の読み方から editor の確認、最小構成の relay 設計まで exact に扱う skill です。

Addness 固有の Zap 名、tag 名、folder 運用、current representative は `Master/addness/zapier_structure.md` を正本にする。この skill は、会社をまたいで再利用できる relay 手順だけを持つ。

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

### create builder の見方

新規 builder を開いたら、最初に次を見る。
- `Untitled Zap`
- `Draft`
- `Trigger`
- `Action`

その後、Addness の current ではまず次を選ぶ。
- `Webhooks by Zapier`
- `Catch Hook`
- `Mailchimp`
- `Add/Update Subscriber`

folder は step ではなく `Zap details` 側で管理する。
- `Folder`
- current の新規は原則 `甲原`

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

## cleanup

exploratory な draft を開いただけなら、その場で削除する。
- builder 右上または title menu
- `Delete Zap`

`Untitled Zap` を残さない。

## NG

- tag の意味が曖昧なまま relay を増やす
- email mapping を固定文字列だと思い込む
- audience を確認せずに進める
- current relay を読まずに別 family を増やす
- Addness 固有 tag 名を skill 内に焼き込む
- folder を決めずに新規 Zap を作る
- `Untitled Zap` の draft を残す

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

## References

- Addness 固有の current 例と判断は `Master/addness/zapier_structure.md`
- representative な exact 手順は `references/workflow.md`
