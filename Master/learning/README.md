# learning レイヤー

最終更新: 2026-03-17

## 情報ラベル

- 所有元: internal
- 開示レベル: role-limited
- 承認必須: conditional
- 共有先: 僕 / 上司 / 並列

`Master/learning/` は、運用から生まれた学習データの置き場です。4層そのものではなく、`前提` と `rules` を育てるための更新材料を持つ補助層です。

## 情報ラベルの既定値

- `execution_rules.json`
  - 所有元: `internal`
  - 開示レベル: `role-limited`
  - 承認必須: `conditional`
  - 共有先: `僕 / 上司 / 並列`
- `style_rules.json` と reply / action / feedback 系ログ、`hinata_memory.md`, `insights.md`
  - 所有元: `self`
  - 開示レベル: `self-only`
  - 承認必須: `always`
  - 共有先: `僕`

この階層の JSON は実装都合で top-level 構造を変えにくいため、個別ラベルではなく path 既定値で監査する。

## 主なファイル

- `execution_rules.json`
  行動OSの Single Source of Truth
- `style_rules.json`
  返信スタイルの自動学習結果
- `reply_feedback.json`
  実際の返信修正ログ。送信者・媒体・文脈プレビュー・補正ラベルも含む
- `action_log.json`
  行動ログ
- `feedback_log.json`
  フィードバックログ
- `hinata_memory.md`
  日向の運用記憶
- `insights.md`
  小さな知見メモ

## 役割

- 実運用で得た変化可能な学習データを持つ
- 自動学習や週次バッチの入力になる
- `前提` と `rules` を更新するための材料になる

## `reply_feedback.json` の見方

- `事実`
  受信文、AI案、実際に送った文、送信者、媒体、グループ名
- `観察`
  `context_preview`、`length_delta`、`change_labels`
- `使い道`
  次回の返信案プロンプトに直接注入する
  週次学習で `style_rules.json` と `comm_profile` 更新の材料に使う
  確認済みのパターンだけを `self_clone` や `rules` に昇格する

## 運用メモ

- `fb [内容]`
  全体ルールとして残す
- `fb [人名]: [内容]`
  その人向けの補正メモとして残す
- `2 [修正]`
  実際の文面差分から補正傾向を自動抽出する
- `1`
  採用された成功例として残す

## 注意

- ここにあるものは「学習中の材料」も含む
- 最終判断の正本にしたいものは、必要に応じて `前提` や `rules` に引き上げる
- 単発ログだけで終わらせず、再利用できる形に圧縮して戻す
