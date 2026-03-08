# knowledge レイヤー

最終更新: 2026-03-09

`Master/knowledge/` は、システム・運用・環境に関する知識の棚です。4層で見ると `knowledge` の中でも「構造理解」「運用理解」に寄っています。

## 主なカテゴリ

- 構成理解
  - `project_structure.md`
  - `環境マップ.md`
  - `秘書の視界マップ.md`
- 実行基盤
  - `orchestrator.md`
  - `mac_mini.md`
  - `accounts.md`
- 業務運用
  - `定常業務.md`
  - `業務棚卸し_AI化優先順位.md`
- 外部構造把握
  - `lstep_structure.md`
  - `sls_structure.md`
- 開発知識
  - `dev_patterns.md`
  - `MacBook移行ガイド.md`
- 顧客理解比較
  - `面談定性比較.md`
  - `System/data/interview_insights_analysis.json`

## 役割

- システムがどう繋がっているかを把握する
- 日々の運用で必要な手順を明文化する
- 実装や調査の前提になる構造知識を持つ

## 置かないもの

- 甲原固有の価値観やトーン
- 事業成果物そのもの
- 成果物から抽出した最終ルールだけの集約

## 更新原則

- 手順が変わったら古い説明を残さず上書きする
- 一時メモではなく、次回も使う知識だけを残す
- 再利用できる原理に育ったものは `Skills/` へ寄せる

## 面談定性の比較

- CDP の `現在の悩み / 理想の未来 / 過去の解決策 / LTV` から、`高LTV / 低LTV / 非成約` を比較する
- 人が最初に読む知識は `面談定性比較.md`
- 比較結果の機械可読な正本は `System/data/interview_insights_analysis.json`
- `analyze` を走らせると `面談定性比較.md` も同時に更新される
- 再生成コマンドは `python3 System/interview_insights_sync.py analyze`
- この比較で繰り返し出る差分を `knowledge` に留め、再利用条件が固まったものだけ `rules` に上げる
