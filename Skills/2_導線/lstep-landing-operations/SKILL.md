---
name: lstep-landing-operations
description: Lステップの `流入経路分析` を新規作成、URLとQRの確認、削除まで安全に進める skill。Lステップで流入元ごとの計測リンクを exact な UI 手順で作りたい時、登録時アクションを持つ landing を作りたい時、テスト用 landing を残さず後片付けしたい時に使う。
---

# lstep-landing-operations

## Overview

Lステップの `流入経路分析` を、`新しい流入経路` の作成だけでなく `URL / QR の確認 -> 削除` まで exact に再現する skill です。

Addness 固有の命名規則、どの account で作るか、current representative は `Master/knowledge/lstep_structure.md` を正本にする。この skill は、会社をまたいで再利用できる exact 手順だけを持つ。

## 役割

`流入経路分析` は、どこから友だち追加されたかを追跡しつつ、登録直後の action を起動する landing 機能です。

## ゴール

次を迷わずできる状態を作る。
- `流入経路分析` の正しい入口を選ぶ
- `新しい流入経路` を作る
- URL と QR を確認する
- 登録時 action の有無を判断する
- テスト用なら削除する

## 必要変数

- 流入経路名
- QRコード表示用テキスト
- どこから来たか
- action を付けるかどうか
- `友だち追加時設定のアクション` を無視するかどうか
- action の実行タイミング
- URL と QR の保管先

## Workflow

1. `流入経路分析`
2. `新しい流入経路`
3. 基本情報を入れる
4. 必要なら action を設定する
5. `登録`
6. 一覧で `URLコピー / QR / 広告挿入タグ` を確認する
7. テスト用なら削除する

## exact 手順

### create

1. `流入経路分析`
2. `新しい流入経路`
3. create 画面で次を入れる
   - `流入経路名`
   - `QRコード表示用テキスト`
   - 必要なら `有効期間(開始)` / `有効期間(終了)`
   - 必要なら `アクション`
4. `友だち追加時設定のアクション`
5. `アクションの実行`
6. `登録`

### action 未設定時

action を入れないまま `登録` を押すと確認 dialog が出る。

- message
  - `アクションが設定されていません。本当に登録しますか？`
- button
  - `キャンセル / OK`

### 作成後の確認

一覧では少なくとも次を確認する。
- `URLコピー`
- `QR`
- `広告挿入タグ`

QR を使う施策では、URL と QR を両方控える。

### 削除

1. 一覧 row 右端 `more_vert`
2. `削除`
3. 一覧再読込後に row が消えていることを確認する

## 検証

最低でも次を確認する。
- 流入経路名が正しい
- 必要なら action が入っている
- URL が発行されている
- QR が開ける
- テスト用なら削除済み

## NG

- 何を分けて取りたいか決めずに作る
- URL だけ控えて QR を見ない
- action 未設定 dialog を見落とす
- `友だち追加時設定のアクション` の挙動を確認しない
- テスト用 landing を残す

## 正誤判断

正しい状態
- 何を分けて計測したい landing か説明できる
- 必要な action だけ入っている
- URL と QR の両方を確認している
- テスト用は削除済み

間違った状態
- 何のための landing か曖昧
- URL だけ作って action や QR を見ない
- test 作成後に row を残す

## References

- Addness 固有ルールと current 例は `Master/knowledge/lstep_structure.md`
- exact な representative 例は `references/workflow.md`
