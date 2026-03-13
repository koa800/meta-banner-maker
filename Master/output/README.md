# output レイヤー

最終更新: 2026-03-14

ここは、実際に出した成果物と、その結果を残す場所です。大事なのは「出したもの」より「次回の判断に戻せる形で残すこと」です。

## 置くもの

- LP案
- コピー案
- メッセージ案
- 企画案
- リサーチアウトプット
- 経理実績に紐づく領収書・請求書
- それぞれの結果レビュー
- 単年の経理判断ログ

## 置かないもの

- まだ出していない思考メモだけの草案
- 汎用原理だけを抜き出した知識
- 禁止事項だけのルール集

## 残し方

- 成果物そのもの
- 何のために作ったか
- 誰に向けたか
- どんな仮説で作ったか
- 結果がどうだったか
- knowledge に戻す学び
- rules に戻す禁止・推奨

## CRレビューの入力元

- 広告CRのレビューは `Looker Studio / 広告管理画面 / 経路別数値` を一次入力元にしてよい
- ただし、数値で言えるのは `何が外れたか` まで。`なぜ外れたか` は `観察` と `解釈` を分けて書く
- `低反応` `反応はあるが後ろが悪い` `CPAは許容でもLTVが悪い` のように失敗の型を分けて残す
- Looker 数値だけで原因を断定しない。必要なら LP / 面談定性 / 下流売上と重ねる

テンプレートは `Master/output/OUTPUT_REVIEW_TEMPLATE.md` を使う。`市場 / 状態 / 問題 / 課題 / 供給 / オファー / 取引成立 / 3つの壁` まで必ず落とす。

LP を個別レビューするときは `Master/output/LP_REVIEW_TEMPLATE.md` を使う。

## 確度の扱い

- `確定`: 数値・構造・一次ソースで裏が取れている
- `強い推定`: 複数の事実からかなり妥当だが、直接証明はない
- `仮説`: 次回の検証前提で置く作業仮説

`事実 -> 観察 -> 解釈 -> 確度` を分けて残し、推測だけで `rules` に上げない。

## 昇格判断

- `output 止まり`: 単発の成果物、または仮説が多く再利用条件がまだ見えていない
- `knowledge 候補`: 事実と観察は残せるが、まだ禁止や推奨に圧縮できない
- `rules 候補`: `確定` または `強い推定` が 2件以上あり、次回の判断を変える禁止・推奨に圧縮できる
- `Skills 候補`: 人や案件をまたいで 3回以上再利用でき、条件と手順を独立した形で説明できる

迷ったら 1段階下に留める。早すぎる昇格より、遅い昇格の方が被害が小さい。

## 命名の基本

- `YYYY-MM-DD_件名.md` で残す
- 既存資産を整理しただけのものも、再利用判断に効くならここへ残す

## 直近の蓄積

- [2026-03-13_Lステップカレンダー予約運用ログ.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-13_Lステップカレンダー予約運用ログ.md)
- [2026-03-08_広告導線ルール抽出.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_広告導線ルール抽出.md)
- [2026-03-08_失敗CRパターン抽出.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_失敗CRパターン抽出.md)
- [2026-03-08_実データ残差分と収集戦略.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_実データ残差分と収集戦略.md)
- [2026-03-08_LP失敗レビュー設計.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_LP失敗レビュー設計.md)
- [2026-03-08_LP3_ヒカルさんLP_初回レビュー.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_LP3_ヒカルさんLP_初回レビュー.md)
- [2026-03-08_LP1_尻込み系_比較レビュー.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_LP1_尻込み系_比較レビュー.md)
- [2026-03-08_LP2_無料ウェビナー型_初回レビュー.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-08_LP2_無料ウェビナー型_初回レビュー.md)
- [2026-03-09_面談定性比較初回分析.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-09_面談定性比較初回分析.md)
- [2026-03-11_Meta広告判断テンプレ適用例.md](/Users/koa800/Desktop/cursor/Master/output/2026-03-11_Meta広告判断テンプレ適用例.md)
- [2026-03-10_2025確定申告_判断ログ.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_2025確定申告_判断ログ.md)
- [2026-03-10_2025確定申告_税額テーブル.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_2025確定申告_税額テーブル.md)
- [2026-03-10_確定申告提出前チェックリスト.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_確定申告提出前チェックリスト.md)
- [2026-03-10_freee自動登録ルール実装表.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_freee自動登録ルール実装表.md)
- [2026-03-10_freee自動登録ルール入力手順.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_freee自動登録ルール入力手順.md)
- [2026-03-10_オフライン証憑投入手順.md](/Users/koa800/Desktop/cursor/Master/output/経理/2026-03-10_オフライン証憑投入手順.md)

## legacy 出力先

自動生成の一部はまだ `Master/addness/proactive_output/` に出力される。既存コード参照を壊さないための互換であり、今後は `output/` を正本入口として扱う。

Mac Mini Orchestrator の `秘書自律ワーク` は、legacy 側に保存しつつ `Master/output/` にもレビューを自動ミラーする。

自動ミラーされたレビューは、最初は原則 `output 止まり` として扱う。`rules` や `Skills` に上げるのは、人が結果を見て根拠件数を積んだ後に行う。

legacy 側の説明は [proactive_output/README.md](/Users/koa800/Desktop/cursor/Master/addness/proactive_output/README.md) を参照する。
