# addness レイヤー

最終更新: 2026-03-08

`Master/addness/` は、Addness 事業の実務 knowledge をまとめる詳細層です。4層で見ると主に `knowledge` に属します。

## このフォルダの役割

- Addness のゴール構造を持つ
- 実行タスクの一覧を持つ
- 導線、Lステップ、広告、リサーチの事実を持つ
- 秘書の自律ワークが参照する運用 knowledge を持つ

## 主なファイル

- `goal-tree.md`
  Addness の全体ゴールツリー。巨大だが最重要の運用 knowledge
- `actionable-tasks.md`
  いま実行対象になっているタスク一覧
- `funnel_structure.md`
  導線・ファネル構造の把握
- `lstep_accounts_analysis.md`
  Lステップ運用とアカウント構造
- `meta_ads_大当たりCR分析.md`
  勝ち CR の分析 knowledge
- `dpro_*.md`, `ds_insight_evaluation.md`, `market_trends.md`
  外部調査・市場観察
- `ui_operations.md`
  Addness UI の操作 knowledge
- `proactive_output/`
  legacy の成果物出力先

## 4層との対応

- 事実・観察・構造理解は `knowledge`
- 勝ち筋や禁止事項に圧縮されたら `rules`
- 実際に出した提案や成果物は本来 `output`

`proactive_output/` は既存コード互換のためここに残っているが、考え方としては `Master/output/` が正本入口。現在の役割は [proactive_output/README.md](/Users/koa800/Desktop/cursor/Master/addness/proactive_output/README.md) に明記した。

## このフォルダに置かないもの

- 甲原固有の人格・価値観
- 汎用化済みの原理
- ルールだけを抜き出した最終版

人格は `前提`、汎用原理は `Skills/`、最終ルールは `Master/rules/` を優先する。
