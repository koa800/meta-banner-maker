---
name: utage-code-operations
description: UTAGEページの `カスタムJS` `カスタムCSS` `高速表示モード` `first_view_css` を exact に扱う skill。計測タグ、redirect、演出、FV補正のどこを触るべきか判断したい時に使う。
---

# utage-code-operations

## Overview

UTAGE page の code 領域を、`js_head / js_body_top / js_body / css / first_view_css / is_high_speed_mode` の役割に分けて扱う skill です。

Addness 固有の representative page や current 例は `Master/addness/utage_structure.md` を正本にする。この skill では、どの案件でも再利用できる exact 判断と手順だけを持つ。

## 役割

UTAGE の code 領域は、builder だけでは吸収しきれない
- 計測
- redirect
- 演出
- page 補正
- FV 補正
を担う実装層です。

## ゴール

次を迷わずできる状態を作る。
- `カスタムJS`
- `カスタムCSS`
- `高速表示モード`
の正しい入口を選ぶ
- `js_head / js_body_top / js_body / css / first_view_css`
のどれを触るべきか判断する
- page type ごとに code 領域の主戦場を見分ける

## 必要変数

- 対象 page の種類
  - LP
  - thanks
  - content page
  - ユーザー登録 page
- 何を直したいか
  - 計測タグ
  - 自動遷移
  - 演出
  - page 全体補正
  - FV 崩れ
- 高速表示モードを使っているか

## 判断フレーム

### `js_head` を使う時

- GTM
- pixel
- 計測タグ

### `js_body_top` を使う時

- body 開始直後に動かないと意味が薄い処理
- thanks の自動遷移
- 初回即時演出

### `js_body` を使う時

- 遅れても体験が壊れない補助処理
- footer 側で十分な script

### `css` を使う時

- page 全体補正
- 余白
- block の見た目調整

### `first_view_css` を疑う時

- LP の FV 崩れ
- 高速表示レイヤー側の見た目補正

通常の見た目調整では、まず `デザイン` と `カスタムCSS` を優先し、`first_view_css` は最後に回す。

## Workflow

1. 対象 page を `LP / thanks / content page / ユーザー登録` に切る
2. 何を直したいかを切る
3. まず `デザイン`
4. 次に `カスタムCSS`
5. 次に `カスタムJS`
   - `js_head`
   - `js_body_top`
   - `js_body`
6. それでも足りず、FV 崩れが高速表示レイヤー側なら `first_view_css` を要確認で扱う
7. `高速表示モード` の ON/OFF も確認する

## exact 手順

### current menu

- `基本情報`
- `デザイン`
- `高速表示モード`
- `メタデータ・検索`
- `カスタムJS`
- `カスタムCSS`
- `表示期限`
- `ワンタイムオファー`
- `パスワード保護`
- `広告連携`
- `ポップアップ`
- `エディター設定`

### current save route

- `カスタムJS` = `/update/js`
- `カスタムCSS` = `/update/css`
- `高速表示モード` = `/update/speed`

### `カスタムJS` の3領域

- `headタグの最後に挿入するjs` = `js_head`
- `bodyタグの最初に挿入するjs` = `js_body_top`
- `bodyタグの最後に挿入するjs` = `js_body`

### `高速表示モード`

- visible field は `is_high_speed_mode` の切替
- `first_view_css` 自体は独立 editor として visible ではない

### `first_view_css`

- current の理解では page object / editor runtime 側の保持物
- public page では `<head>` 冒頭の `<style>` として展開される
- 独立 menu ではなく、高速表示レイヤー側の FV 補正として扱う

## page type ごとの基本

### LP

- まず `デザイン`
- 次に `カスタムCSS`
- 計測は `js_head`
- FV 崩れだけ `first_view_css`

### thanks

- `js_body_top` を先に疑う
- 自動遷移の主戦場

### content page

- visible CTA と `js_body_top` を先に見る
- 安易に `first_view_css` を疑わない

## 検証

最低でも次を確認する。
- 何を直したいかに対して、触る領域を説明できる
- `js_head / js_body_top / js_body / css / first_view_css`
  を使い分けられる
- public page で intended な挙動になる

## NG

- まず `first_view_css` から触る
- 計測タグも redirect も演出も全部 `js_body` に入れる
- thanks を LP と同じ見方で触る
- script に direct LINE を持つ CTA page を thanks redirect page と誤認する

## 正誤判断

正しい状態
- page type と直したい目的から、触る場所を先に切れている
- `first_view_css` を最後の要確認として扱えている

間違った状態
- code 領域の役割を分けずに触る
- 何を直すための code か説明できない

## References

- Addness 固有の representative は `Master/addness/utage_structure.md`
- exact 手順は `references/workflow.md`
