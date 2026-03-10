# Master 設計図

最終更新: 2026-03-11

`Master/` は、AIの脳みその設計図です。目的は「情報を置くこと」ではなく、「使うたびに判断精度が上がる構造を作ること」です。ここで作る脳は `スキルプラス専用` ではなく、甲原さんのOS・信念・今やっていること・これからやりたいことを統合して、世界中の `ありがとう` を増やすための判断を行う脳です。

## 最上位からの流れ

```text
信念
  ↓
世界中の「ありがとう」の数を増やす
  ↓
課題解決
  ↓
事業 / マーケティング / オファー / 取引成立
  ↓
個別事業（例: スキルプラス）
```

- `スキルプラス` は最上位ゴールではなく、今の主要実装の一つ
- 判断は、個別事業より先に `信念 / OS / 最上位ゴール` から下ろす
- 用語定義は `用語定義.md` 冒頭の手動確定概念を優先して読む

## 4層

```text
Master/
├── 前提/       ← 目的・人格・判断軸・用語定義
├── knowledge/  ← 事実・観察・過去事例・一次情報
├── rules/      ← 再現ルール・NG・ガードレール
├── output/     ← 実際に出した成果物と検証ログ
└── legacy層    ← 既存運用を壊さないための詳細ディレクトリ
```

## 各層の役割

- `前提`: AIが考える前に固定すべきもの。用語定義、目的、価値観、判断軸、優先順位。
- `knowledge`: 過去LP、数値、導線、顧客理解、一次観察などの素材。
- `rules`: 成功・失敗から抽出した「こうする」「これはやらない」。
- `output`: 実際に出したLP、文面、企画、提案、その結果。

## 使ったら育てる

```text
output を作る
  ↓
結果と学びを knowledge に残す
  ↓
再発防止や勝ち筋を rules に抽出する
  ↓
人依存でなく再利用できるものは Skills に昇格する
```

- 新しい成果物を出したら、まず `output/` に残す。
- 成果が出た理由や観察は `knowledge/` に残す。
- 二度と外したくない判断や NG は `rules/` に残す。
- 3回以上再利用できる原理になったら `Skills/` に移す。

## 入力元の優先

- `失敗知識` は、まず `数値で外れた事実` と `なぜ外れたかの解釈` を分けて扱う
- 広告CRの失敗知識は `Looker Studio / 広告管理画面 / 経路別数値` を一次入力元にしてよい
- ただし Looker の数値だけで `なぜ外れたか` を断定せず、`事実 -> 観察 -> 解釈 -> 確度` で残す
- CR失敗は `低反応` `高反応だが後ろが悪い` `CPAは良いがLTVが悪い` のように失敗の型を分ける
- LP失敗や導線失敗は、数値だけで切れない部分を面談定性や人の記憶で補完する

## 昇格の目安

- `output 止まり`: 単発の成果物、または仮説中心で再利用条件がまだ見えていない
- `knowledge 候補`: 事実と観察はあるが、まだ禁止や推奨に圧縮できない
- `rules 候補`: `確定` または `強い推定` が 2件以上あり、次回の判断を変える
- `Skills 候補`: 人や案件をまたいで 3回以上再利用でき、条件と手順を独立して説明できる
- `Skills 昇格可`: 上記に加えて、`対象条件` `やり方` `失敗しやすい条件` が分かれており、甲原固有の文脈を外しても機能する
- 甲原さんが `これスキルにして` と明示したものは、再利用回数の目安より優先して昇格候補として扱う

迷ったら 1段階下に留める。

## わかることだけを残す

- `確定`: 数値・構造・一次ソースで裏が取れている
- `強い推定`: 複数の事実からかなり妥当だが、直接証明はない
- `仮説`: 次回の検証前提で置く作業仮説

`事実 -> 観察 -> 解釈 -> 確度` を分ける。分からないことを無理に rules にしない。

## legacy との関係

既存コードが参照しているため、いきなり移動はしません。まずは4層を入口として定義し、既存資産をそこへマッピングします。

- `self_clone/`, `brains/`, `people/`, `company/` は主に `前提` の詳細層
- `addness/`, `sheets/`, `knowledge/` は主に `knowledge` の詳細層
- `learning/` は `rules` と `前提` を補助する学習層
- `addness/proactive_output/` は `output` の legacy 出力先

## legacy 詳細マップ

- `前提` に近い詳細層:
  [前提/README.md](/Users/koa800/Desktop/cursor/Master/前提/README.md),
  [self_clone/README.md](/Users/koa800/Desktop/cursor/Master/self_clone/README.md),
  [brains/README.md](/Users/koa800/Desktop/cursor/Master/brains/README.md),
  [company/README.md](/Users/koa800/Desktop/cursor/Master/company/README.md),
  [people/README.md](/Users/koa800/Desktop/cursor/Master/people/README.md)
- `knowledge` に近い詳細層:
  [knowledge/README.md](/Users/koa800/Desktop/cursor/Master/knowledge/README.md),
  [addness/README.md](/Users/koa800/Desktop/cursor/Master/addness/README.md),
  [sheets/README.md](/Users/koa800/Desktop/cursor/Master/sheets/README.md)
- `rules` を補助する学習層:
  [learning/README.md](/Users/koa800/Desktop/cursor/Master/learning/README.md),
  [rules/rules.md](/Users/koa800/Desktop/cursor/Master/rules/rules.md)
- `output` の入口:
  [output/README.md](/Users/koa800/Desktop/cursor/Master/output/README.md)

## 最初に見る場所

- 全体方針: [Master/README.md](/Users/koa800/Desktop/cursor/Master/README.md)
- 用語定義: [用語定義.md](/Users/koa800/Desktop/cursor/Master/前提/用語定義.md)
- 本人固定プロフィール: [本人基本プロフィール.md](/Users/koa800/Desktop/cursor/Master/前提/本人基本プロフィール.md)
- 目的: [目的.md](/Users/koa800/Desktop/cursor/Master/前提/目的.md)
- 判断軸: [判断軸.md](/Users/koa800/Desktop/cursor/Master/前提/判断軸.md)
- 優先順位: [優先順位.md](/Users/koa800/Desktop/cursor/Master/前提/優先順位.md)
- 前提更新ルール: [更新ルール.md](/Users/koa800/Desktop/cursor/Master/前提/更新ルール.md)
- 面談定性の比較知識: [面談定性比較.md](/Users/koa800/Desktop/cursor/Master/knowledge/面談定性比較.md)
- ルール蓄積: [rules.md](/Users/koa800/Desktop/cursor/Master/rules/rules.md)
- 広告・導線の具体ルール: [広告・導線ルール.md](/Users/koa800/Desktop/cursor/Master/rules/広告・導線ルール.md)
- 成果物運用: [README.md](/Users/koa800/Desktop/cursor/Master/output/README.md)

## 次に整理する対象

- `Master/addness/proactive_output/` を `Master/output/` 正本運用へ寄せる
- 既存の LP / CR の失敗事例を `rules` と `output` に流し込む
- `前提/用語定義` の定義保留語を埋める
- 面談定性比較を継続更新し、`過去の解決策` の件数を増やして `knowledge -> rules` 昇格を進める
