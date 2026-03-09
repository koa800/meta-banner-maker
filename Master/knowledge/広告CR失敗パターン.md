# 広告CR失敗パターン

最終更新: 2026-03-09

この文書は Meta広告の CR ダッシュボード raw を集計し、`何が外れたか` を比較するための棚です。
原因断定はここではやらず、LP・面談定性・下流売上と重ねて判断します。

## 現在の状態

- raw 取得口: `meta_cr_dashboard_download`（毎日 11:45）
- 正規化スクリプト: `python3 System/meta_cr_dashboard_sync.py analyze`
- raw 保存先: `~/Desktop/Looker Studio CSV/meta_cr_dashboard/`
- 機械可読な集計: `System/data/meta_cr_dashboard/failure_summary.json`

## 読み方

- まず `高フックでも外れる型` と `低CTRで止まる型` を分ける
- 次に `同じタイトルの派生` が何度も外れていないかを見る
- その後に `LP / ファネル / 製作者` の偏りを確認する
- 数値だけで `なぜダメか` を断定しない

## 次に更新されるもの

- スナップショットCSVの件数
- `はずれ / 微妙 / 許容KPI未達成` の分布
- 失敗候補が偏る LP / ファネル / 製作者
- 繰り返し出る失敗タイトル
- `高フックでも外れた例` と `低CTRの失敗例`
