# learning レイヤー

最終更新: 2026-03-08

`Master/learning/` は、運用から生まれた学習データの置き場です。4層そのものではなく、`前提` と `rules` を育てるための更新材料を持つ補助層です。

## 主なファイル

- `execution_rules.json`
  行動OSの Single Source of Truth
- `style_rules.json`
  返信スタイルの自動学習結果
- `reply_feedback.json`
  実際の返信修正ログ
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

## 注意

- ここにあるものは「学習中の材料」も含む
- 最終判断の正本にしたいものは、必要に応じて `前提` や `rules` に引き上げる
- 単発ログだけで終わらせず、再利用できる形に圧縮して戻す
