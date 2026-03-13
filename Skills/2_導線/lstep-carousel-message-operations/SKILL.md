---
name: lstep-carousel-message-operations
description: Lステップの `カルーセルメッセージ(新方式)` を新規作成、テスト送信、削除まで安全に進める skill。複数カードの比較や選択肢提示、または 1 panel の視覚訴求 + CTA を exact な UI 手順で作りたい時に使う。
---

# lstep-carousel-message-operations

## Overview

Lステップの `カルーセルメッセージ(新方式)` を、`作成 -> テスト送信 -> 削除` まで exact に再現する skill です。

Addness 固有の account 選定、命名規則、current representative、テスト送信先は `Master/knowledge/lstep_structure.md` を正本にする。この skill は、会社をまたいで再利用できる exact 手順だけを持つ。

## 役割

`カルーセルメッセージ(新方式)` は、複数 card を並べて比較・選択させるか、1 panel に視覚訴求と CTA をまとめるための message type です。

## ゴール

次を迷わずできる状態を作る。
- `テンプレート -> 新しいテンプレート -> カルーセルメッセージ(新方式)` の正しい入口を選ぶ
- `テンプレート名` と最低限の panel 情報を入れて保存する
- 一覧行右端 `... -> テスト送信`
- テスト用なら `... -> 削除`

## 必要変数

- テンプレート名
- panel 数
- 各 panel の役割
- タイトル
- 本文
- CTA 文言
- action 種別
- テスト送信先
- テスト後に残すか削除するか

## 使い分け

- `標準メッセージ`
  - 説明中心
- `カルーセルメッセージ(新方式)`
  - 複数 card の比較 / 選択
  - 1 panel の視覚訴求 + CTA
- `フレックスメッセージ`
  - 1画面の視覚階層を強く出したい
- `テンプレートパック`
  - 複数 step を束ねたい

`カルーセルメッセージ(新方式)` を選ぶのは、
- card を並べた方が分かりやすい
- panel ごとに役割を分けたい
- 1 panel で画像 + 本文 + CTA を compact に見せたい
時です。

## Workflow

1. `テンプレート`
2. `新しいテンプレート`
3. `カルーセルメッセージ(新方式)`
4. `テンプレート名`
5. panel に必要情報を入れる
6. `テンプレート登録`
7. 一覧に戻る
8. 行右端 `... -> テスト送信`
9. 実機確認
10. テスト用なら `... -> 削除`

## exact 手順

### create

1. `テンプレート`
2. `新しいテンプレート`
3. `カルーセルメッセージ(新方式)`
4. `テンプレート名`
5. `パネル #1`
6. 必要なら `タイトル`
7. visible `ProseMirror` に `本文`
8. `選択肢名`
9. 必要なら `アクション設定`
10. `テンプレート登録`

代表 route
- 新規: `/line/template/edit_v2/new?group=0`
- 既存: `/line/template/edit_v2/{template_id}`

重要
- 本文入力欄は `textarea` ではなく `ProseMirror`
- `タイトル` と `アクション設定` は空でも最小保存が通る current 例がある

### テスト送信

1. 一覧行右端 `...`
2. `テスト送信`
3. `テスト送信先選択`
4. 送信先行の左端 checkbox label を押して選択
5. `テスト`
6. 実機確認

### 削除

1. 一覧行右端 `...`
2. `削除`
3. confirm dialog `削除する`
4. 一覧再読込

## 検証

最低でも次を確認する。
- panel 数が意図どおり
- 各 panel の役割が重複していない
- CTA 文言で迷わない
- action が正しく動く
- テスト用は削除済み

## NG

- 比較や選択肢ではないのに card を増やしすぎる
- panel ごとの役割が重複する
- `標準メッセージ` で十分な内容を無理にカルーセル化する
- `テスト送信` をしない
- テスト用 item を残す

## 正誤判断

正しい状態
- `カルーセルメッセージ(新方式)` を選ぶ理由がある
- panel ごとの役割が明確
- CTA が一読で分かる
- 実機で迷わず押せる

間違った状態
- card を増やしただけで比較にも segmentation にもなっていない
- 本文や CTA が panel ごとに重複する
- current representative を見ずに雑に流用する

## References

- Addness 固有ルールと current 例は `Master/knowledge/lstep_structure.md`
- exact な representative 例は `references/workflow.md`
