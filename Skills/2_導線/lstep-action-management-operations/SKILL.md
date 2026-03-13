---
name: lstep-action-management-operations
description: Lステップの `アクション管理` で reusable な action を作成、保存、削除まで安全に進める skill。複数の動作をまとめたい時、流入経路やテンプレートやシナリオ step から何度も呼ぶ処理を作りたい時、exact な UI 手順で迷わず再現したい時に使う。
---

# lstep-action-management-operations

## Overview

Lステップの `アクション管理` を、`新規作成 -> 保存 -> 検索 -> 削除` まで exact に再現する skill です。

Addness 固有の current representative、account 選定、命名規則は `Master/knowledge/lstep_structure.md` を正本にする。この skill は、会社をまたいで再利用できる exact 手順だけを持つ。

## 役割

`アクション管理` は、`送信 / 状態変更 / シナリオ制御 / 表示制御` を 1つの reusable macro に束ねるための機能です。

## ゴール

次を迷わずできる状態を作る。
- `アクション管理` の正しい入口を選ぶ
- 最小構成の action を作成する
- 保存後に一覧で検索して確認する
- テスト用なら削除する

## 必要変数

- action 名
- 何をまとめたいか
- reusable にするか inline にするか
- 動作種別
- 送信タイミング
- 条件の有無
- テスト後に残すか削除するか

## 使い分け

- `アクション管理`
  - 何度も使う複合処理
- 流入経路 / テンプレート / シナリオ step の inline action
  - その場限りの処理

迷ったら次で切る。
- 使い回すなら `アクション管理`
- 入口ごとに少しずつ違うなら inline

## Workflow

1. `アクション管理`
2. `新しいアクション`
3. 動作種別を選ぶ
4. `保存するアクション名`
5. 動作の中身を入れる
6. `この条件で決定する`
7. 一覧で `検索` に action 名を入れる
8. `search` を押して存在確認
9. テスト用なら row 右端 `more_vert -> delete 削除 -> 削除する`

## exact 手順

### create

1. `アクション管理`
2. `新しいアクション`
3. 動作種別を選ぶ
4. `保存するアクション名`
5. 動作 block を埋める
6. `この条件で決定する`

代表 URL
- 一覧: `/line/action`

### 最小構成

いま exact に閉じている最小構成は `テキスト送信` です。

1. `新しいアクション`
2. `テキスト送信`
3. `保存するアクション名`
4. `1. テキスト送信`
5. `メッセージ`
6. visible `[contenteditable="true"]` に本文
7. `この条件で決定する`

重要
- `メッセージ` は visible `textarea` ではなく `[contenteditable="true"]` を主入口にする
- `検索` は入力だけでは反映されない。`search` ボタンまで押す

### 一覧で確認

1. 一覧へ戻る
2. `検索` に action 名を入れる
3. `search` を押す
4. row が 1 件に絞れることを確認する

### 削除

1. `検索` に action 名を入れる
2. `search` を押す
3. row 右端 `more_vert`
4. `delete 削除`
5. confirm dialog `削除する`
6. 再度 `検索 -> search`
7. row が消えていることを確認

## current で見えている動作種別

- `テキスト送信`
- `テンプレート送信`
- `タグ操作`
- `友だち情報操作`
- `シナリオ操作`
- `メニュー操作`
- `リマインダ操作`
- `対応マーク・表示操作`
- `イベント予約操作`
- `コンバージョン操作`

## 検証

最低でも次を確認する。
- action 名が役割を表している
- 何をまとめる action か一読で分かる
- 一覧検索で見つかる
- テスト用は削除済み

## NG

- reusable にする必要がないものまで `アクション管理` に寄せる
- action 名が用途を表していない
- selector が絡む複雑な動作を、live 確認なしで正本化する
- テスト用 action を残す

## 正誤判断

正しい状態
- reusable にする理由がある
- action 名だけで用途が分かる
- 最小構成を exact に保存できる
- 一覧検索で確認し、不要なら削除できる

間違った状態
- inline で足りる処理を過剰に reusable 化する
- 動作を増やしすぎて action の責務が曖昧になる
- save できたかを一覧で確認しない

## References

- Addness 固有ルールと current 例は `Master/knowledge/lstep_structure.md`
- exact な representative 例は `references/workflow.md`
