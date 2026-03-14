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
