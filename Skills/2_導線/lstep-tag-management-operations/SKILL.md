---
name: lstep-tag-management-operations
description: Lステップの `タグ管理` を新規作成、確認、削除まで安全に進める skill。Lステップで状態管理用タグを exact な UI 手順で作りたい時、タグの最小検証をしたい時、テスト用タグを残さず後片付けしたい時に使う。
---

# lstep-tag-management-operations

## Overview

Lステップの `タグ管理` を、`新しいタグ` の作成だけでなく `一覧確認 -> 削除` まで exact に再現する skill です。

Addness 固有の命名規則、folder の読み方、current / legacy の判断は `Master/knowledge/lstep_structure.md` を正本にする。この skill は、会社をまたいで再利用できる exact 手順だけを持つ。

## 役割

`タグ管理` は、友だちの状態、属性、進行位置をラベルとして持つ機能です。

## ゴール

次を迷わずできる状態を作る。
- `タグ管理` の正しい入口を選ぶ
- 必要な folder を開く
- `新しいタグ`
- 一覧で確認する
- テスト用なら削除する

## 必要変数

- タグ名
- どの folder に置くか
- 何の状態を表すタグか
- テスト用か本番用か

## Workflow

1. `タグ管理`
2. 必要な folder を開く
3. `新しいタグ`
4. `タグ名`
5. `作成`
6. 一覧で確認
7. テスト用なら削除

## exact 手順

### create

1. `タグ管理`
2. 必要な folder を開く
3. `新しいタグ`
4. dialog `タグの新規作成`
5. field `タグ名`
6. `作成`

### 削除

1. 対象 row 右端 `more_vert`
2. `削除`
3. 一覧再読込後に row が消えていることを確認する

## 検証

最低でも次を確認する。
- folder が正しい
- タグ名が正しい
- 一覧に出る
- テスト用なら削除済み

## NG

- folder を開かずに作って置き場所を誤る
- 命名をその場のメモで決める
- visible 一覧が空だから何も使っていないと決める
- テスト用タグを残す

## 正誤判断

正しい状態
- 何の状態を表すタグか説明できる
- 正しい folder で作っている
- 一覧で作成確認している
- テスト用は削除済み

間違った状態
- folder 無視で作る
- 用途の曖昧な名前を付ける
- 作っただけで action 側との関係を見ない

## References

- Addness 固有ルールと current 例は `Master/knowledge/lstep_structure.md`
- exact な representative 例は `references/workflow.md`
