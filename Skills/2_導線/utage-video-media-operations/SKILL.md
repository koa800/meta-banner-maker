---
name: utage-video-media-operations
description: UTAGEの `動画管理` と `メディア管理` を exact 手順で扱う skill。動画のアップロード、サムネイル変更、チャプター設定、分析確認、画像等の asset 管理を安全に進めたい時に使う。
---

# utage-video-media-operations

## Overview

UTAGE の `動画管理` と `メディア管理` を、asset library として安全に扱う skill です。

Addness 固有の folder 名、current 代表 asset、どの page / 会員サイトで使っているかは `Master/addness/utage_structure.md` を正本にする。この skill では、どの案件でも再利用できる exact 手順だけを持つ。

## 役割

`動画管理` と `メディア管理` は、LP、会員サイト、講義、セールス page で使う画像・動画の source asset を管理する層です。

## ゴール

次を迷わずできる状態を作る。
- `メディア管理` で画像や資料を上げる
- `動画管理` で動画を上げる
- `サムネイル変更` をする
- `チャプター設定` をする
- `分析` で視聴維持率を見る
- どの asset をどこで再利用しているか、事故なく扱う

## 必要変数

- 対象が `メディア` か `動画` か
- asset 名
- 入れたい folder
- 用途
  - LP
  - 会員サイト
  - 講義
  - セールス
- 動画なら
  - サムネイル変更が必要か
  - チャプターが必要か
  - 分析を見るか

## 判断フレーム

### `メディア管理` を使う時

次のどれかなら `メディア管理` を使う。
- 画像
- PDF
- 資料
- page 内で使う静的 asset

### `動画管理` を使う時

次のどれかなら `動画管理` を使う。
- 講義動画
- セミナー動画
- アーカイブ動画
- page や会員サイトに埋め込む動画

### `チャプター設定` を先に疑う時

次のどれかなら `チャプター設定` を先に見る。
- 長尺講義
- セミナーアーカイブ
- 視聴体験を上げたい
- 動画内の区切りを明示したい

### `分析` を先に見る時

次のどれかなら `分析` を先に見る。
- どこで離脱しているか知りたい
- CTA 手前まで見られているか知りたい
- 長尺講義の retention を見たい

## Workflow

1. `メディア管理` または `動画管理`
2. folder を確認
3. `新規アップロード` または `新規フォルダ`
4. 動画なら一覧カードから
   - `サムネイル変更`
   - `チャプター設定`
   - `分析`
   を必要に応じて触る
5. page / 会員サイト側で参照する
6. 使わない test asset は残さない

## exact 手順

### current route

- メディア一覧: `/media`
- 動画一覧: `/media/video`

### 一覧で触る基本操作

メディア管理
- `新規アップロード`
- `新規フォルダ`

動画管理
- `新規アップロード`
- `新規フォルダ`
- `開く`
- `名称変更`
- `サムネイル変更`
- `チャプター設定`
- `分析`
- `ダウンロード`
- `削除`

### メディア管理

- upload input は `file[]`
- 複数ファイルを同時に扱う前提
- まず folder を決めてから上げる

### 動画管理

- upload input は `file`
- 事前に `動画形式のファイルのみ` の validation が走る
- 一覧カード footer に `埋め込み用URL` がある

### サムネイル変更

- modal で開く
- action は `/video/thumbnail/upload`
- 入力は
  - `file`
  - `video_id`

### チャプター設定

- modal で開く
- 初回表示時に `/media/video/chapter/load`
- 保存先は `/video/chapter/update`
- 入力は
  - `chapter`
  - `video_id`
- 書式は 1 行ごとに
  - `00:00 はじめに`
  - `07:15 5つの集客メソッド`
  のような `時刻 + 見出し`

### 分析

- modal で開く
- 期間指定は
  - `date_from`
  - `date_to`
  - `表示`
- 取得先は `/media/video/analytics`
- current で見る値
  - `インプレッション数`
  - `視聴数`
  - `視聴維持率`
- line chart は
  - 横軸 `play_positions`
  - 縦軸 `play_rates`

## 検証

最低でも次を確認する。
- asset が正しい folder にある
- 動画なら `埋め込み用URL` が取れる
- `サムネイル変更` は intended な見た目になっている
- `チャプター設定` は `時刻 + 見出し` で保存できている
- `分析` は intended 期間で読める
- test asset を残していない

## NG

- page 側で毎回ファイルを持ち直し、media/video を source of truth にしない
- folder を見ずに upload する
- 長尺動画なのに `チャプター設定` や `分析` を一度も見ない
- asset 名や用途を確認せずに流用する

## 正誤判断

正しい状態
- `メディア` と `動画` の役割を分けている
- folder を先に決めて upload している
- 動画なら `サムネイル / チャプター / 分析` を必要に応じて見ている

間違った状態
- asset を置いた場所が分からない
- 動画を上げただけで終わる
- どこで再利用されるか分からないまま差し替える

## References

- Addness 固有の folder と representative は `Master/addness/utage_structure.md`
- representative な exact 手順は `references/workflow.md`
