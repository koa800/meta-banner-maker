# Mailchimp content review workflow

## 使うタイミング

- 既存メールを benchmark として分解したい時
- 新規の `Journey` や `Campaign` を作る前に current quality を読みたい時
- 作ったメールが意図した認識変換になっているか確認したい時

## 30秒レビューの順番

1. `Journey` か `Campaign` かを切る
2. `誰に送るか` を `tag / segment / audience` で言う
3. `変えたい認識` を 1 文で言う
4. `件名`
5. `Preview text`
6. 本文冒頭
7. main CTA
8. 実 hyperlink
9. `click-details`
10. 次の接点

### 構築精度だけを見る時のチェック

内容の良し悪しと、構築の正しさは分けて見る。まずは次の点が合っているかを先に切る。

1. type の選択が正しいか
2. main CTA が 1 つに切れているか
3. hyperlink や action の実体が合っているか
4. 入力値や遷移先が実値で正しいか
5. テスト方法が決まっているか
6. 実 click / 実挙動で確認したか
7. 残すべきものと削除すべきものが分かれているか

## current でよく出る型

### 全体 promotion 型

- 広い母集団へ単発告知を打つ
- `open_rate 9〜11%`
- `click_rate 0.04〜0.21%`
- 告知、urgency、即反応を優先しやすい

### 高温 segment promotion 型

- 温度の高い母集団へ単発告知を打つ
- `open_rate 38〜46%`
- `click_rate 0.59〜4.99%`
- 個別感、 urgency、今動く理由を短く強く置く

### evergreen 教育型

- `Journey` で継続的に流す
- 人物ストーリー、authority、open loop を使う
- 次接点の反応率を上げるための認識変換を担う

## 何を見るか

- 件名が開封理由になっているか
- `Preview text` が件名の続きを補強しているか
- 本文が 1 通 1 目的になっているか
- CTA が 1 つに切れているか
- 表示文字列ではなく実 hyperlink が意図どおりか
- 次の接点に滑らかにつながるか

## `Journey` と `Campaign` の読み分け

### `Journey`

- 前後の step を含めて読む
- この 1 通だけ良くても不十分
- `前の接点で何を感じたか`
- `この 1 通で何を変えるか`
- `次の接点で何をしてほしいか`
を 1 本で見る

### `Campaign`

- 1 通単体で読む
- `今この相手にだけ 1 回送る理由`
- `その 1 通で何を変えるか`
- `main CTA が 1 本に絞れているか`
を先に見る

## 良い / 悪いの exact 判断

### 良い

- 件名の promise を本文冒頭ですぐ回収している
- 本文中の実例やストーリーが main CTA の説得材料になっている
- main CTA と click-details 上の main click URL が一致している
- 次の接点が、本文で作った期待や温度とズレない

### 悪い

- 件名だけ強く、本文の役割が散る
- 本文は教育だが CTA だけ急に hard sell
- `Preview text` が件名と別の promise を出している
- 本文上は short.io に見えるが actual hyperlink が違う

## 完成条件

次を全部言えた時だけ review 完了とする。
- このメールは `Journey` か `Campaign` か
- 誰のどんな状態を変えたいか
- 何の認識をどう変えたいか
- その変化の結果、何を行動させたいか
- 件名、本文冒頭、main CTA が 1 本の意図でつながっているか
- actual hyperlink と final destination が意図どおりか
- 次の接点にどうつながるか

## current で見誤りやすい点

- `open_rate` や `click_rate` だけで良し悪しを決めない
  - broad 配信か高温 segment 配信かで前提が違う
- `copy` や `Resend` でも current 実績になりうる
- 件名が良くても、本文と CTA の promise がズレていると quality は低い
- short.io に見える文言でも、actual hyperlink が別物のことがある
- `Journey` は 1 通単体で完結評価しない
  - 前後の step の中で何を担うかまで見る

## ここで止めて確認する条件

- `Journey` なのに 1 通単体だけで評価したくなっている
- `Campaign` なのに前後文脈ありきでしか成立しない
- broad 配信か高温 segment 配信か曖昧
- 変えたい認識を 1 文で言えない

## 最低限の output

- 種別 (`Journey` / `Campaign`)
- 目的
- 対象
- 変えたい認識
- 起こしたい行動
- 良い点
- 弱い点
- 再現すべき点
- 変えるならどこか

## 保存前の最小チェック

- audience と segment を本文前に固定している
- `Subject line / Preview text / main CTA` の役割を分けている
- main CTA の `short.io` を用意している

## 保存後の最小チェック

- preview または test で actual hyperlink を確認した
- `short.io` の final destination まで確認した
- report や click-details の見る順が決まっている
