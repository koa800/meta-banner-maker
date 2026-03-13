---
name: lstep-standard-message-operations
description: Lステップの `標準メッセージ` を新規作成、テスト送信、削除まで安全に進める skill。説明中心の message、補足案内、simple CTA を exact な UI 手順で作りたい時、既存の良い標準メッセージを分解したい時に使う。
---

# lstep-standard-message-operations

## Overview

Lステップの `標準メッセージ` を、`作成 -> テスト送信 -> 削除` まで exact に再現する skill です。

Addness 固有の account 選定、命名規則、current representative、テスト送信先は `Master/knowledge/lstep_structure.md` を正本にする。この skill は、会社をまたいで再利用できる exact 手順だけを持つ。

## 役割

`標準メッセージ` は、長めの説明、補足、simple CTA を friction 低く伝えるための基本 message type です。

## ゴール

次を迷わずできる状態を作る。
- `テンプレート -> 新しいテンプレート -> 標準メッセージ` の正しい入口を選ぶ
- `テンプレート名` と本文を入れて保存する
- 一覧行右端 `... -> テスト送信`
- テスト用なら `... -> 削除`

## 必要変数

- テンプレート名
- 何を説明したいか
- 次に何をしてほしいか
- CTA の有無
- テスト送信先
- テスト後に残すか削除するか

## 使い分け

- `標準メッセージ`
  - 長めの説明
  - 補足
  - simple CTA
- `カルーセルメッセージ(新方式)`
  - 複数 card を並べて選ばせたい
- `フレックスメッセージ`
  - 視覚階層を強く出したい
- `テンプレートパック`
  - 複数 step を束ねたい

`標準メッセージ` を選ぶのは、
- まず text で理解させたい
- CTA が 1 つで十分
- visual を前面に出しすぎない方が自然
な時です。

## Workflow

1. `テンプレート`
2. `新しいテンプレート`
3. `標準メッセージ`
4. `テンプレート名`
5. 本文を入れる
6. `テンプレート登録`
7. 一覧に戻る
8. 行右端 `... -> テスト送信`
9. 実機確認
10. テスト用なら `... -> 削除`

## exact 手順

### create

1. `テンプレート`
2. `新しいテンプレート`
3. `標準メッセージ`
4. `テンプレート名`
5. visible editor の `.ProseMirror` に本文を入れる
6. `テンプレート登録`

代表 route
- 新規: `/line/template/new?group=0`
- 既存: `/line/template/edit/{template_id}?group={group_id}`

重要
- hidden `textarea[name="text_text"]` ではなく `.ProseMirror` を基準に作業する
- `下書き保存` ではなく `テンプレート登録` を本線とする

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
- 冒頭 1-2 行で誰向けか分かる
- 何をすべきかが明確
- CTA が 1 つに絞れている
- 実機で押した時の挙動が正しい
- テスト用は削除済み

## NG

- 長文すぎて main CTA が埋もれる
- visual 訴求が必要なのに `標準メッセージ` に押し込む
- hidden textarea だけ見て保存できたと判断する
- `テスト送信` をしない
- テスト用 item を残す

## 正誤判断

正しい状態
- `標準メッセージ` を選ぶ理由がある
- text で理解させる役割が明確
- CTA が 1 つに絞れている
- 実機でそのまま伝わる

間違った状態
- 説明、訴求、複数 CTA を全部 1 通に詰め込む
- `フレックスメッセージ` や `カルーセルメッセージ(新方式)` の方が適しているのに text に寄せる
- current representative を見ずに雑に増やす

## References

- Addness 固有ルールと current 例は `Master/knowledge/lstep_structure.md`
- exact な representative 例は `references/workflow.md`
