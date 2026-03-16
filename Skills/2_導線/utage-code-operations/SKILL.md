---
name: utage-code-operations
description: UTAGEページの `カスタムJS` `カスタムCSS` `高速表示モード` `first_view_css` を exact に扱う skill。計測タグ、redirect、演出、FV補正のどこを触るべきか判断したい時に使う。
---

# utage-code-operations

## Overview

UTAGE page の code 領域を、`js_head / js_body_top / js_body / css / first_view_css / is_high_speed_mode` の役割に分けて扱う skill です。

Addness 固有の representative page や current 例は `Master/addness/utage_structure.md` を正本にする。この skill では、どの案件でも再利用できる exact 判断と手順だけを持つ。

## ツールそのものの役割

UTAGE の code 領域は、builder だけでは吸収しきれない計測、redirect、演出、page 補正、FV 補正を担う実装層です。

## アドネスでの役割

アドネスでは code 領域を、見た目を雑に上書きする場所ではなく `builder と接続設定で足りない差分だけを埋める補正層` として扱う。したがって、まず visible settings を見て、それで足りない時だけ `カスタムJS / カスタムCSS / first_view_css` に降りる。

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

## 実装前の最小チェック

- 直したいものが `計測 / redirect / 演出 / page 全体補正 / FV 補正` のどれかに落ちている
- 対象 page を `LP / thanks / content page / ユーザー登録 page` のどれかに切れている
- まず visible settings で吸収できない理由を説明できる

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
8. visible settings だけで終わらず、runtime と公開ページの両方で確認する

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

### representative current contrast

- LP representative
  - `/funnel/d0imwFvGWVbA/page/lvy1yBHf1VvZ/edit`
  - `is_high_speed_mode = 1`
  - `first_view_css あり`
  - `js_head あり`
  - `js_body_top = null`
  - `js_body = null`
  - `css = null`
- ユーザー登録 representative
  - `/funnel/mYSG4RqRbFiH/page/ScGYTZjaPHHX/edit`
  - `is_high_speed_mode = 0`
  - `first_view_css = null`
  - `js_head = null`
  - `js_body_top = null`
  - `js_body = null`

### runtime 確認

- `python3 System/scripts/utage_page_runtime_snapshot.py <edit URL>`
- 既存の edit タブが開いていれば、そのタブへ raw CDP で直接 attach して読む
- 既存 tab が見つからない時だけ、新規 page を開く fallback を使う
- 少なくとも
  - `is_high_speed_mode`
  - `first_view_css`
  - `css`
  - `js_head`
  - `js_body_top`
  - `js_body`
  を一緒に見る
- visible settings と runtime のどちらが正本かで迷ったら、まず runtime と公開挙動を優先する

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

## 保存前の最小チェック

- 直したいものが `計測 / redirect / 演出 / page全体補正 / FV補正` のどれかに落ちている
- `LP / thanks / content page / ユーザー登録 page` のどれかを先に固定している
- `デザイン` と `カスタムCSS` で吸収できない理由を説明できる

## 保存後の最小チェック

- 公開ページで実挙動を確認した
- `runtime snapshot` で intended な field が反映されている
- `bodyタグの最初に挿入するjs` を触った時は、初回表示で挙動を確認した
- `short.io` や LIFF へ飛ぶなら最終遷移先まで確認した

## ここで止めて確認する条件

- `first_view_css` を触りたくなった理由が `何となく崩れている` の段階
- `js_head` と `js_body_top` のどちらに入れるべきか説明できない
- 高速表示モードの ON/OFF を変えないと直らないのか、code 修正で直るのか判断できない
- visible CTA と code による redirect が両方あり、どちらを正にするか決め切れていない

## 完成条件

- 直したい目的から code 領域を先に切れる
- `js_head / js_body_top / js_body / css / first_view_css` を使い分けられる
- visible settings と runtime と公開挙動の 3 点で検証できる

## NG

- まず `first_view_css` から触る
- 計測タグも redirect も演出も全部 `js_body` に入れる
- thanks を LP と同じ見方で触る
- script に direct LINE を持つ CTA page を thanks redirect page と誤認する

## 正誤判断

正しい状態
- page type と直したい目的から、触る場所を先に切れている
- `first_view_css` を最後の要確認として扱えている
- visible settings と runtime と公開ページの 3 点で検証できる

間違った状態
- code 領域の役割を分けずに触る
- 何を直すための code か説明できない

## References

- Addness 固有の representative は `Master/addness/utage_structure.md`
- exact 手順は `references/workflow.md`
