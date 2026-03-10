---
name: meta-cr-failure-analysis
description: Meta広告CRの失敗を、勝ちCRの基準と比較して「どこで崩れたか」で分類し、knowledge や rules 候補に圧縮する。自社の CR raw、Looker スナップショット、勝ちCR一覧を見て、失敗パターンを抽出したいときに使う。
---

# Meta CR Failure Analysis

Meta広告CRの失敗分析は、`誰が作ったか` ではなく `どこで崩れたか` を先に切る。
この Skill は、勝ちCRの基準と失敗サンプルを比較し、失敗形を `knowledge` に戻すための型。

## 入力

- 勝ち基準: `System/data/cr_bigwinners_raw.csv`
- 失敗分析の正本: `System/data/meta_cr_dashboard/full_failure_raw_*.csv`
- fallback: `Master/addness/meta_ads_cr_dashboard.md`
- Looker Studio の正本アカウント: `kohara.kaito@team.addness.co.jp`
- 出力先:
  - `Master/knowledge/広告CR失敗パターン.md`
  - `System/data/meta_cr_dashboard/failure_summary.json`
  - `System/data/meta_cr_dashboard/video_signal_summary.json`

基本は `CR一覧の long-range full raw` を取ってから読む。`meta_ads_cr_dashboard.md` は fallback の初回分析用。
Meta広告のCR分析は、数値だけでなく `実際の動画内容` まで読む。特に `CTRとフック率は通るがオプトイン以降で失敗` では、冒頭の広さとオーディエンス学習のズレを確認する。

## 失敗CRの定義

- `1年後悔` `林さん` のような CR系統ラベルそのものを `失敗CR` と呼ばない
- `失敗CR` は、`大当たりCR / 当たりCR` には入らない側にある CR 個体を指す
- full raw を読むときは、`大当たり / 当たり` を勝ち側、その他を非勝ち側として分ける
- 実務上の評価単位は、少なくとも `クリエイティブ / 広告IDまたは広告セットID / オーディエンス / LP / 期間`
- `完全に同じCR` で `大当たり / はずれ` が混在するときは、まず `運用差` を疑う
- `フックが全然違う` なら、テーマやCR系統ラベルが近くても `別CR` として扱う
- 同じCR系統でも `勝ちCR` と `失敗CR` は混在する
- CR系統ラベルは `比較ラベル` として使い、ラベルだけで勝ち負けを断定しない

## まず切る変数

- 広告集客で大きく切る変数は `CR / 運用 / LP`
- ただし、CR には `旬` がある。時代や時期によって見られ方は変わる
- したがって実務上は `CR / 運用 / LP / 時期` の4軸で切る
- `今見られている` を `恒久的に強い` と誤認しない
- `時期` を読むときは、単なる日付比較ではなく `社会背景 / 市場背景 / 旬` まで観察対象に含める
- CR系統を読むときは `CR系統 × 月 × 崩れ方` を並べ、`CTRとフック率は通るがオプトイン以降で失敗 -> フックで離脱` のような変化を `旬切れ / 既視感` の候補として見る
- 既視感は自社の露出増だけでなく、`他社模倣によるフォーマット摩耗` でも起こる。市場全体で同じ型が増えたら、新規性低下によるスキップ増を疑う

## Looker 作業ルール

- 既に開いている認証済みタブを再利用する。ページを何度も開き直さない
- `u/1` など account index 付き URL を新規に踏まず、account index を外した URL か認証済みタブの複製を使う
- `アクセスが拒否されました` が出たら、まずアカウント文脈ズレを疑う
- `CR一覧` は `2023/01/01 - 今日` のように長めの期間へ広げてから CSV エクスポートする
- エクスポートはブラウザ既定保存先を当てにせず、Playwright の `download.save_as()` で `System/data/meta_cr_dashboard/` に直接保存する

## 手順

1. まず勝ち基準を作る。
   `CTR / フック率 / CPA` の中央値と四分位を基準にする。

2. 失敗サンプルを `どこで崩れたか` で切る。
   最初の分類はこれだけでよい。
   - `フックで離脱`
   - `見られるがクリックされない`
   - `クリックされるがCPAが高い`
   - `CTRとフック率は通るがオプトイン以降で失敗`

3. 次に `同一アセット比較` を入れる。
   ここが入らないと、`同じCRなのにCTRやCPAが違う理由` を creative 単体の問題と誤認しやすい。
   分解順はこれで固定する。
   - `同じ動画URL/画像 × 同日 × 同LP` → オーディエンスや広告セット差を疑う
   - `同じ動画URL/画像 × LP違い` → LP とオファーの期待値差を疑う
   - `同テーマ × 冒頭違い` → 冒頭構成差を疑う
   - Meta では `同じクリエイティブ × 同じオーディエンス` でも `広告ID / 広告セットID` が変わると配信面が少しブレる。広告ID差は別条件として扱う。

4. CR系統ラベルの偏りを見る。
   ただし、単語単体で勝ち負けを断定しない。
   `失敗側に偏るCR系統` と `勝ち負け混在のCR系統` を分ける。

5. `CR系統 × 月` を見る。
   - `いつ強いか / いつ弱いか` を月単位で観察する
   - その月の `社会背景 / 市場背景 / 旬` をメモする
   - 例えば `年末の後悔訴求` のように、時期とメッセージが噛み合っていないかを確認する

6. まず `knowledge` に留める。
   1回の比較結果は rules に上げない。
   同じ失敗形が複数回の比較で繰り返し出て、LP や下流売上とも噛み合ったときだけ rules 候補に上げる。

7. full raw を取る。認証済みの `CR一覧` タブが開いている状態なら、これで long-range CSV を保存できる。

```bash
python3 System/meta_cr_dashboard_sync.py capture-full-raw --date-start 2023-01-01 --output "System/data/meta_cr_dashboard/full_failure_raw_latest.csv"
```

8. 取れた CSV をそのまま食わせる。

```bash
python3 System/meta_cr_dashboard_sync.py analyze --failure-csv "System/data/meta_cr_dashboard/full_failure_raw_latest.csv"
```

9. `CTRとフック率は通るがオプトイン以降で失敗` を見始めたら、動画URLをそのまま文字起こしする。最初は冒頭 20-45秒で十分。

```bash
python3 System/meta_cr_dashboard_sync.py video-backfill --failure-csv "System/data/meta_cr_dashboard/full_failure_raw_latest.csv" --limit 15 --bucket "CTRとフック率は通るがオプトイン以降で失敗" --max-seconds 20
python3 System/meta_cr_dashboard_sync.py analyze --failure-csv "System/data/meta_cr_dashboard/full_failure_raw_latest.csv"
```

`video-backfill` は `動画URL -> Whisper文字起こし -> broad marker / audience scope 集計` を行う。結果は `Master/knowledge/広告CR失敗パターン.md` の「動画内容まで読んだ所見」に反映される。
一部の動画URLが `403` などで読めないときは、そのURLだけ `video_cache/<asset>/error.json` に記録して全体は止めずに継続する。

10. 失敗バケットをまたいで `全件` 読みたいときは、`--all-buckets` を必ず付ける。

```bash
python3 System/meta_cr_dashboard_sync.py video-backfill --failure-csv "System/data/meta_cr_dashboard/full_failure_raw_latest.csv" --limit 10000 --all-buckets --max-seconds 20
python3 System/meta_cr_dashboard_sync.py analyze --failure-csv "System/data/meta_cr_dashboard/full_failure_raw_latest.csv"
```

fallback の 24件スナップショットだけで初回分析したいときはこうする。

```bash
python3 System/meta_cr_dashboard_sync.py analyze
```

## 読み方

- `高フック` でも負けることは普通にある。フック率だけで勝ち負けを決めない。
- `CTRとフック率は通るがオプトイン以降で失敗` が多いなら、CR単体より `LP / オファー / 導線 / ターゲット層` を先に疑う。
- `CTRとフック率は通るがオプトイン以降で失敗` を読むときは、`実際の冒頭文` を見ずに終わらない。広い危機訴求、著名人、無料特典などが `狙っているターゲット層を広く取っている` のか、`狙っていない層の比率を増やしている` のかを確認する。
- SNS広告では、`広いフック -> 広いオーディエンス` そのものを悪としない。失敗として疑うのは、`広いフック -> 狙っていない層の増加 -> 浅い反応層への学習` のパターン。
- `クリックされるがCPAが高い` は、クリックはされるので `オプトイン率の低さ` か `ターゲット層の質` を疑う。
- `同じクリエイティブなのに数字が違う` ときは、先に `オーディエンス / 広告ID / 広告セットID / LP / 時期 / 冒頭` を切る。creative 単体の優劣に直行しない。
- `同じCR` を見るときも、`CR自体 / 運用差 / LP差 / 時期差` を分ける。順番を飛ばさない。
- `完全に同じCR` に `大当たり / はずれ` が混ざるなら、creative の善し悪しより先に `運用差` を読む。
- `同一CRで勝ち負け混在` の一覧を先に出し、CR系統分析より先に `運用差` を切る。
- 母数を広げた分析では、`失敗の件数が多いCR系統` と `失敗に偏るCR系統` を分けて読む。絶対件数だけで断定しない。
- `1年後悔` や `林さん` のような勝ち負け混在CR系統は、`系統そのものが失敗` ではなく `どの条件の個体が失敗したか` を読む。
- `誰が作ったか` の集計は補助。主分析にしない。

## 仮説段階での確認ルール

失敗パターンを `knowledge候補` としてまとめる段階では、一般論だけでユーザーに聞かない。必ず `具体情報 + 自分の考え + 確認したいズレ` をセットで持っていく。

### 必ず添えるもの

- `具体情報`
  - どの動画か: `広告名 / 動画URL or asset / failure_bucket`
  - 数値: `CTR / CPA / フック率 / 消化金額`
  - 中身: `冒頭抜粋 / broad_hits / narrow_hits / audience_scope`
- `自分の考え`
  - 何が起きたと見たか
  - なぜそう見たか
  - どの失敗パターン候補に近いか
- `確認したい論点`
  - 自分の解釈のどこが合っているか
  - どこが浅いか
  - 別の見方があるか

### 良い聞き方

```md
この動画は `250801/鈴木織大/1年後悔（LP変更）/LP2-CR00613` で、
- failure_bucket: CTRとフック率は通るがオプトイン以降で失敗
- CTR: 1.17
- CPA: 3341
- フック率: 28.0
- 冒頭: 「また一週間無駄にしたんだ…」
- broad_hits: 広い危機訴求 / 広い属性呼びかけ

自分は、
`広い危機訴求で反応は取れるが、広く集めすぎて浅い層に学習し、後ろで弱くなった`
と見ました。

この見立ては合っていますか。
もしズレているなら、
- どこが本質ではないか
- 本当は何を原因として見るべきか
を教えてください。
```

### 悪い聞き方

- `この失敗って何が原因だと思いますか？`
- `一般的にMeta広告で失敗する理由は何ですか？`
- `この動画は広い訴求だからダメですよね？`

証拠なし、仮説なし、誘導だけの聞き方はしない。

## やらないこと

- 製作者別の偏りを主因として扱わない
- 単語単体で `この言い回しは絶対ダメ` と断定しない
- 1回のスナップショットだけで rules 化しない

## 昇格条件

- 同じ失敗形が複数スナップショットで出る
- その失敗形が次の判断を変える
- `対象条件 / やり方 / 失敗しやすい条件` を分けて説明できる

この3つが揃ったら `rules` 候補に上げる。
