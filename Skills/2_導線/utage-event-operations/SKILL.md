---
name: utage-event-operations
description: UTAGE の `イベント` を一覧確認、設定確認、申込者確認まで安全に進める skill。UTAGE で `セミナー・説明会` や 1on1 の event を作る時、event が配信 root なのか申込 container なのかを誤らず扱いたい時、exact な route と設定項目で確認したい時に使う。
---

# utage-event-operations

## Overview

UTAGE の `イベント` を、単なる一覧確認ではなく `event 一覧 -> applicant -> item / register / form / config` の順に exact に扱う skill です。

Addness 固有の代表 event や current 運用は `Master/addness/utage_structure.md` を正本にする。この skill では、どの案件でも再利用できる exact 手順だけを持つ。

## 役割

UTAGE の `イベント` は、配信そのものではなく、申込、日程、参加情報、申込者管理を束ねる container として使う機能です。

## ゴール

次を迷わずできる状態を作る。
- `イベント` の current route を正しく開く
- event の設定を確認する
- `申込者` を確認する
- event が `配信 root` なのか `申込 container` なのかを説明できる

## 必要変数

- event 名
- event 種類
- 参加費
- 決済連携設定
- 連携配信シナリオの有無
- 申込後の動作設定
- 申込フォームの有無
- applicant 管理の必要有無

## 判断フレーム

### event を使う時

- セミナー
- 説明会
- 1on1
- 申込 / 予約 / 参加情報管理

### event を配信 root と誤らない

current の Addness では、少なくとも代表例の `スキル習得セミナー` は、event config 自体が配信 root ではありません。  
配信連携は別レイヤーで持つ前提で読みます。

## Workflow

1. `イベント`
2. 一覧から対象 event を探す
3. `申込者`
4. `item`
5. `register`
6. `form`
7. `config`
8. event が担う役割を判定する

## exact 手順

### current route

- 一覧
  - `/event`
- applicant
  - `/event/{event_id}/applicant`
- item
  - `/item`
- register
  - `/register`
- form
  - `/form`
- config
  - `/config`

### current で見る代表ラベル

最低でも次を確認する。
- `種類`
- `参加費`
- `決済連携設定`
- `連携配信シナリオ`
- `申込後の動作設定`

### 代表例の current 読み方

代表的な event は少なくとも次です。
- `AIは教えてくれない！会社に依存しない生き方を実現する「スキル習得セミナー」`
- `【スキルプラス スタンダード】新入生1on1`
- `【スキルプラス プライム】新入生1on1`
- `【スキルプラス】月報1on1`
- `【スキルプラス】目標設定FB1on1`
- `スキルプラスBOTCHAN`

current の representative 設定例
- `種類`
  - `セミナー・説明会`
- `参加費`
  - `無料`
- `決済連携設定`
  - `デフォルト`
- `連携配信シナリオ`
  - 空
- `申込後の動作設定`
  - `しない`

## 検証

最低でも次を確認する。
- event 名が正しい
- event 種類が正しい
- 有料 / 無料が正しい
- 申込者一覧を見られる
- event を配信 root と誤読していない

## NG

- event を配信 root だと決めつける
- `申込後の動作設定` だけ見て、全体の役割を判断する
- `連携配信シナリオ` が空でも異常と決めつける

## 正誤判断

正しい状態
- 一覧、申込者、config の route を迷わず開ける
- event の役割を `申込 / 参加情報 container` として説明できる
- 配信レイヤーと event レイヤーを分けて読める

間違った状態
- event の中だけで配信が全部完結している前提で考える
- `連携配信シナリオ` の有無だけで current / legacy を決める

## References

- Addness 固有の代表例は `Master/addness/utage_structure.md`
