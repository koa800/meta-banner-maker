---
name: mailchimp-content-review-operations
description: Mailchimp の `Journey` と `Campaign` のメール本文を、件名、preview、本文、CTA、hyperlink、認識変換、セグメント適合の観点でレビューする skill。既存メールを分解して何が良くて何が悪いかを言語化したい時、実装前に current quality を benchmark として読みたい時、作成したメールが意図した顧客体験になっているか確認したい時に使う。
---

# mailchimp-content-review-operations

## Overview

Mailchimp のメールを、単なる copy ではなく `コンテンツ` として分解する skill です。

ここでいう `コンテンツ` は、`コミュニケーションの手段であり、ユーザーをこちらが意図した認識に変換するもの` です。したがってレビューの中心は、

- 何の認識を変えたいか
- 誰の温度をどこまで上げたいか
- 何を行動させたいか
- そのために `件名 / preview / 本文 / CTA / hyperlink` をどう使っているか

です。

Addness 固有の current representative、件名例、benchmark は `Project/3_業務自動化/メールマーケティング自動化.md` を正本にする。この skill は、会社をまたいで再利用できる `レビューの型` だけを持つ。

## ツールそのものの役割

Mailchimp のメールは、件名から CTA までを通して、相手の認識と温度を変え、次の行動を起こさせるコンテンツを届ける手段です。

## アドネスでの役割

アドネスでは、Mailchimp を `長文教育と心理変容の本線` として使う。したがってレビューでは、きれいな文章かより先に、

- どの温度の相手か
- 何の誤解を解きたいか
- 今なぜ動くべきか
- Lステップ や UTAGE の次接点へどう滑らかにつなぐか

を確認する。

## 役割

既存メールを分解して、

- 何が良いか
- 何が弱いか
- 何を再現すべきか
- どの認識変換を担っているか

を、実装前に判断できる状態を作る。

## ゴール

次を迷わず言語化できる状態を作る。

- このメールは何のために存在するか
- 誰のどんな認識を変えたいか
- `Journey` と `Campaign` のどちらの文法で書かれているか
- `件名 / preview / 本文 / CTA` の役割がどう分かれているか
- main CTA と補助 CTA の役割が切れているか
- 再現すべき点と変えるべき点を分けられるか

## 必要変数

- そのメールが `Journey` か `Campaign` か
- 対象 audience / tag / segment
- 送る相手の温度
- 変えたい認識
- 起こしたい次行動
- main CTA
- secondary CTA の有無
- `short.io / UTAGE / direct LINE` のどれへ送るか

## レビュー前の最小チェック

- `Journey` か `Campaign` か切れている
- `誰に送るメールか` を `tag / segment / audience` で説明できる
- `変えたい認識` を 1 つに絞れている
- `起こしたい次行動` を 1 つに絞れている
- hyperlink は表示文字列ではなく実URLで確認する前提になっている

## 10秒判断

- `Journey` の content
  - evergreen の認識変換を見たい
- `Campaign` の content
  - 単発配信の認識変換を見たい
- `認識変換型`
  - 理解や誤解修正が主目的
- `温度上昇型`
  - 今動く理由を強めるのが主目的
- `刈り取り型`
  - 個別相談や申込へ押し込むのが主目的

この 10 秒判断が言えない時は、本文を読めても content review にならないので stop する。

## レビューの順番

1. `このメールは何のメールか`
2. `誰に送るか`
3. `何の認識を変えるか`
4. `何を行動させるか`
5. `件名` がその認識変換の入口になっているか
6. `preview` が続きを読む理由になっているか
7. `本文` が認識変換を担っているか
8. `CTA` が文脈と一致しているか
9. `hyperlink` の実遷移先が promise と一致しているか
10. 次の接点につながるか

## 最小 live review

最初の 1 本は `Journey 1通` か `Campaign 1通` のどちらか 1 つだけを end-to-end で読む。

1. `Journey` か `Campaign` を 1 つ選ぶ
2. `件名`
3. `preview`
4. 本文冒頭
5. main CTA 文言
6. actual hyperlink
7. final destination

最初から複数メールを横比較しない。まず 1 通で `何の認識をどう変えて、次に何をさせるか` を言えることを優先する。

## 制作者意図を読む時の問い

最低でも次を 1 つずつ言えるまで下ろす。

1. このメールを送る前、相手は何を誤解している想定か
2. その誤解を、どの paragraph で解こうとしているか
3. 何を信じてもらえれば CTA を押せる前提になるか
4. urgency は `今動く理由` になっているか、ただの圧になっていないか
5. 次の接点で何を感じていてほしい設計か

制作者意図がここまで切れない時は、`文章は読めたが content は読めていない` と扱う。

### 構築精度だけを見る時のチェック

内容の良し悪しと、構築の正しさは分けて見る。まずは次の点が合っているかを先に切る。

1. 形式選択が正しいか
2. main CTA が 1 つに切れているか
3. hyperlink や action の実体が合っているか
4. 入力値や遷移先が実値で正しいか
5. テスト方法が決まっているか
6. 実 click / 実挙動で確認したか
7. 残すべきものと削除すべきものが分かれているか

## 型の切り方

### `Journey` のメール

- evergreen
- 同じ認識変換を何度も流す
- 入口条件とセットで読む

### `Campaign` のメール

- 単発
- 今回だけの segment 配信
- 企画や promotion の文脈で読む

## current でよく出る content 型

### ストーリー教育型

- 人物ストーリー
- 実績
- 世界観
- `今は動かない` を `理解して動く理由がある` に変える

### 直オファー型

- 何の案内かを早く言う
- 期限や urgency を添える
- CTA へ早く寄せる

### 横展開型

- 今の文脈から別オファーへ橋をかける
- 本線を壊さず、`次の選択肢` を見せる

### 締切ブースト型

- urgency
- 取り逃しの不安
- 今動く理由

### 3日間短期刈り取り型

- `あなた向け`
- `反響 / 実例`
- `締切 / urgency`
の順で押し込む

## representative pattern

- `認識変換型`
  - 主目的は `知らない / 半信半疑` を `理解している` に変えること
  - `件名` と `preview` は読む理由を作る
  - 本文はストーリー、実例、authority が主役
- `温度上昇型`
  - すでに理解している相手を `今動く` に寄せる
  - 本文は短め、CTA は早め
  - urgency と具体便益が主役
- `刈り取り型`
  - 個別相談、申込、購入に強く寄せる
  - `main CTA` が本文後半の必然として出る
  - `補助リンク` はあっても弱く置く
- `横展開型`
  - 本線を壊さず別オファーへ橋をかける
  - 相手の現在地と次の枝を自然につなぐ

## representative pattern を読む時の問い

- このメールは `理解させる / 温度を上げる / 刈り取る / 横展開する` のどれか
- `件名 / preview / 本文 / CTA` のうち、何が主役か
- 本文は長いだけでなく、認識変換に必要な順で並んでいるか
- `main CTA` は本文の結論として自然に置かれているか

## 最初の複雑パターン

最初に exact に分解する 1 通は、次のどれか 1 つに絞る。

- `認識変換型`
  - `件名 1 + preview 1 + 本文冒頭 3 段落 + main CTA 1`
- `温度上昇型`
  - `件名 1 + urgency 1 + CTA 1`
- `刈り取り型`
  - `件名 1 + 反響 / 実例 1 + 締切 1 + CTA 1`

最初から
- 複数 CTA
- 横展開
- 長い追伸
- 補助リンク多数
を同時に読まない。まず 1 通で `何の認識を変え、何を行動させるか` を切ることを優先する。

## current representative の読み方

Addness の current では、少なくとも次の 2 系統で読み分ける。

### 全体 promotion 型

- 広い `Subscribed` 母集団へ送る
- `open_rate 9〜11%`
- `click_rate 0.04〜0.21%`
- 本文では
  - 告知
  - urgency
  - 即反応
  を優先しやすい
- current の sent 例では `direct LINE` が main CTA のことが多い

### 高温 segment promotion 型

- `フリープラン` など絞られた母集団へ送る
- `open_rate 38〜46%`
- `click_rate 0.59〜4.99%`
- 本文では
  - 強い urgency
  - 個別感
  - 今動く理由
  を短く強く置く

したがって、Mailchimp の content review では
- `文章が上手いか`
ではなく
- `今の温度の相手に対して圧と長さが合っているか`
を先に見る。

## 症状から最初に疑う場所

- open は取れるのに click が弱い
  - まず `main CTA が 1 つに切れているか`
  - 次に `本文から CTA までの必然`
  - 最後に `actual hyperlink`
- 件名は強いのに downstream が弱い
  - まず `preview`
  - 次に `本文冒頭`
  - その後に `CTA の promise と遷移先`
- 長文なのに読み進められていない感じがする
  - まず `認識変換の順番`
  - 次に `不要な補助情報`
  - `追伸` や補助リンクの多さを最後に疑う
- urgency を入れたのに圧だけ強く見える
  - まず `今動く理由`
  - 次に `誰向けか`
  - `期限だけ先に立っていないか` を見る

## 件名 / preview / 本文 / CTA の見る観点

### 件名

- 開封したくなる理由があるか
- 誇張ではなく、本文の中身と一致しているか
- `誰向けか` が分かるか

### preview

- 件名の続きとして、開封理由を補強しているか
- 本文のネタバレではなく、続きを読みたくなるか

### 本文

- `共感 / 問題提起 / 事実 / 実例 / urgency / CTA前の後押し`
  のどれを担っているか切れるか
- 1通に役割を詰め込みすぎていないか

### CTA

- main CTA が 1 つに切れているか
- 補助 CTA があるなら役割が分かれているか
- CTA 文言が抽象的ではないか

### hyperlink

- 表示文字列ではなく実 URL を click で確認する
- `main CTA = short.io` が原則
- 補助リンクは role が分かれていれば直リンクでもよい

## 良い / 悪いの判断軸

### 良い

- 1通1目的になっている
- 件名から CTA まで役割がつながっている
- 相手の温度に対して文量と圧が適切
- CTA が本文の必然として置かれている
- 次の接点へ文脈が滑らか

### 悪い

- 件名だけ強くて本文が弱い
- 本文は長いが認識変換が起きていない
- CTA が唐突
- main CTA と補助 CTA の役割が混ざる
- hyperlink の実遷移先が文脈とずれる

## exact なレビュー手順

1. 対象メールを開く
2. `件名`
3. `preview`
4. 本文冒頭
5. main CTA
6. 実 hyperlink
7. `report` または `click-details`
8. 次の接点

### 30秒レビューの順番

1. `Journey` か `Campaign` かを切る
2. `誰に送っているか` を `tag / segment / audience` で言う
3. `変えたい認識` を 1 文で言う
4. `件名`
5. `Preview text`
6. 本文冒頭
7. main CTA
8. 実 hyperlink
9. `click-details`
10. 次に渡る接点

必要なら API や helper を併用する。

- content: `campaign content`
- performance: `mailchimp-report-operations`

## current UI で先に固定するラベル

- `Customer Journeys`
- `View Report`
- `Campaign Manager`
- `View report`
- `Email subject`
- `Preview text`
- `Content`
- `Recipients`
- `Open rate`
- `Click rate`
- `click-details`

## output の型

最低限、次の 9 行に落とす。

- 種別 (`Journey` / `Campaign`)
- 目的
- 対象
- 変えたい認識
- 起こしたい行動
- 良い点
- 弱い点
- 再現すべき点
- 変えるならどこか

## 実装前の最小チェック

- 何を benchmark としてレビューするか切っている
- current と legacy を混ぜていない
- 変えたい認識と起こしたい行動を 1 つに絞って読める
- 構築精度と content quality を分けて判定する前提になっている

## Workflow

1. 対象を current / legacy で切る
2. 目的と相手状態を言語化する
3. 構成要素を分解する
4. CTA や action の実体を確認する
5. 良い点、弱い点、再現点、変更点に落とす
6. 必要なら実機や preview で確かめる

## exact 手順

- 一覧や対象行を固定して preview または別窓を開く
- main CTA、actual hyperlink、final destination を分けて確認する
- 構築精度と content quality を分けてメモする
- benchmark にする点と捨てる点を分けて残す

## 保存前の最小チェック

- レビュー結果をどこへ書き戻すか決まっている
- current / legacy の判定が済んでいる
- main CTA と補助要素の主従が切れている
- 実 click で確認すべき箇所を切っている

## 保存後の最小チェック

- 良い点、弱い点、再現点、変更点が 1 行以上で埋まっている
- action や hyperlink の実体まで確認している
- benchmark にする理由を説明できる
- レビュー結果が次の実装判断に使える形になっている

## 完成条件

- 何の認識を変えるコンテンツか 1 文で言える
- 良い点、弱い点、再現点、変更点を残している
- 構築精度と content quality を分けて判断している
- 次の実装判断に使えるレビューになっている

## NG

- 開封率だけで良し悪しを決める
- CTA を見ずに本文だけで判断する
- 表示文字列だけで URL が正しいと判断する
- `current` と `legacy` を混ぜて benchmark にする
- Addness 固有の具体名をそのまま一般 skill に焼き込む

## 正誤判断

正しい状態

- 何の認識を変えたいメールか 1 文で言える
- main CTA を 1 つに切れる
- 件名、preview、本文、CTA の役割を分けて説明できる
- hyperlink 実体まで確認している
- report と content をつなげて次の改善点を言える

間違った状態

- `なんとなく良い文章` で終わる
- CTA の役割が曖昧
- current か legacy か分けずに benchmark にする
- 見えている URL と実際の遷移先を混同する

## ここで止めて確認する条件

- `Journey` か `Campaign` か切れない
- main CTA が複数あって主従が分からない
- direct LINE と short.io のどちらを正とすべきか判断が割れる
- content 上は良さそうだが report が極端に悪く、どこが原因か切れない
- `Email subject` と `Preview text` を確認せず、本文だけでレビューしそう

## References

- Addness 固有の current 例と benchmark は `Project/3_業務自動化/メールマーケティング自動化.md`
- report の exact 手順は `Skills/2_導線/mailchimp-report-operations`
