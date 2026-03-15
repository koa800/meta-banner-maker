---
name: utage-page-operations
description: UTAGEのページを新規作成、既存流用、登録経路追加、CTA接続、公開後検証まで exact 手順で進める skill。UTAGEで LP、thanks、content page、ユーザー登録ページを作る時、どのページを増やすべきかと登録経路で吸収すべきかを判断したい時、カスタムCSSやカスタムJSをどこで使うか迷わず進めたい時に使う。
---

# utage-page-operations

## Overview

UTAGE の `ファネル > ページ` を、見た目だけでなく `ページの役割 / 主CTA / シナリオ / アクション / 遷移先 / 検証` まで一気通貫で扱う skill です。

Addness 固有のグループ名、current 代表ファネル、命名や account の読み分けは `Master/addness/utage_structure.md` を正本にする。この skill は、どの案件でも再利用できる exact 手順だけを持つ。

## ツールそのものの役割

UTAGE の `ページ` は、LP、thanks、content page、ユーザー登録ページなどの接点を作り、登録、遷移、購入、視聴の起点を成立させる機能です。

## アドネスでの役割

アドネスでは `ページ` を、見せるだけの箱ではなく `認識変換と行動を接続する実行面` として使う。したがって、見た目の前に `主CTA / シナリオ / アクション / 遷移先` を固定してから触る。

## 役割

UTAGE の `ページ` は、顧客接点を `登録する / 押す / 視聴する / 買う / 会員化する` に変換する実行面です。

## ゴール

次を迷わずできる状態を作る。
- `新規ページ / 既存ページ流用 / 登録経路追加` を正しく切る
- `LP / thanks / content page / ユーザー登録` のどれかを先に固定する
- `主CTA -> シナリオ -> アクション -> 遷移先` を崩さず設定する
- 必要な時だけ `カスタムCSS / カスタムJS` を使う
- 実 click で最終挙動を検証する

## 必要変数

- どの `ファネル` に置くか
- 新規ページか、既存ページ流用か、同一ページで `登録経路` を増やすか
- ページの役割
  - `LP`
  - `thanks`
  - `content page`
  - `ユーザー登録`
- 何を変えるのか
  - ページそのもの
  - FV
  - CTA
  - 登録経路
  - シナリオ
  - アクション
  - 商品
- どこへ送るか
  - UTAGE 内次ページ
  - short.io
  - LINE / LIFF
  - 会員サイト
- code 領域が必要か
  - `カスタムCSS`
  - `カスタムJS`
  - `first_view_css`

## 実装前の最小チェック

- どの `ファネル` に置くか決まっている
- `新規ページ / 既存ページ流用 / 登録経路追加` のどれかを先に切っている
- ページの役割を `LP / thanks / content page / ユーザー登録` のどれかで言える
- `主CTA / シナリオ / アクション / 遷移先` の主従が決まっている
- code 領域を触る理由を 1 文で説明できる

## 判断フレーム

### 新規ページ

次のどれかが `yes` なら、まず新規ページを疑う。
- ページそのものの内容が変わる
- コンセプトが大きく変わる
- クリエイティブごとに最適化した LP を作る

### 既存ページ流用

次の条件をすべて満たすなら、既存ページ流用を疑う。
- ページの役割が同じ
- 主CTAの役割も同じ
- 見せたい promise も大きく変わらない
- 変わるのが一部文言や接続だけ

### 登録経路追加

次の条件をすべて満たすなら、ページ複製より `登録経路` を優先する。
- 同じページを使う
- どこから来たかを分けて見たい
- 分析したい軸が `媒体 / クリエイティブ / 設置場所 / 広告ID` のいずれかにある

`広告ID` は current の代表例であって、登録経路の目的そのものではない。先に `何を見分けたいか` を決め、その結果として広告ID単位に切るかを判断する。

## Workflow

1. 対象 `ファネル` を開く
2. `ページ一覧` で対象行を確認する
3. `新規ページ / 既存流用 / 登録経路追加` を決める
4. ページの役割を 1 つに決める
5. `主CTA` を決める
6. `シナリオ / アクション / 遷移先` を決める
7. 必要なら `デザイン -> カスタムCSS -> カスタムJS` の順で触る
8. 公開ページで主CTAを押し、最終挙動を確認する
9. 分析したいなら `登録経路` を切る

## exact 手順

### representative route の見方

current の representative を触る時は、少なくとも次の 2 本を基準にする。

- LP representative
  - page list: `/funnel/d0imwFvGWVbA/page`
  - edit: `/funnel/d0imwFvGWVbA/page/lvy1yBHf1VvZ/edit`
  - preview: `/page/lvy1yBHf1VvZ?preview=true`
- ユーザー登録 representative
  - edit: `/funnel/mYSG4RqRbFiH/page/ScGYTZjaPHHX/edit`

LP と ユーザー登録 で、見る順番が変わることを前提にする。

### page edit で最初に見る順番

1. `基本情報`
2. `ページ一覧の行名`
3. visible の `主CTA`
4. `シナリオ`
5. `アクション`
6. `遷移先`
7. `デザイン`
8. `カスタムCSS`
9. `カスタムJS`
10. `高速表示モード`

`見た目` から入らず、まず接続を先に確定する。

### runtime snapshot

visible 設定だけで迷う時は、runtime も合わせて見る。

- `python3 System/scripts/utage_page_runtime_snapshot.py <edit URL>`

ここで current では少なくとも次を確認できる。
- `is_high_speed_mode`
- `first_view_css`
- `css`
- `js_head`
- `js_body_top`
- `js_body`

### `ページ設定` で current に見える主な項目

- `基本情報`
- `デザイン`
- `高速表示モード`
- `メタデータ・検索`
- `カスタムJS`
- `カスタムCSS`
- `表示期限`
- `ワンタイムオファー`
- `パスワード保護`
- `広告連携`
- `ポップアップ`
- `エディター設定`

### representative な editor 上部の見方

edit 画面を開いたら、最初に上部で次を確認する。
- `戻る`
- `PC`
- `SP`
- `ポップアップ`
- `ページ設定`
- `AIアシスト`
- `要素一覧`
- `プレビュー`
- `保存`

この並びが見えていれば、current の page editor に正しく入れている可能性が高い。

### 役割別の見方

#### `LP`

優先して見る。
- 主CTA
- `form`
- `シナリオ`
- `アクション`
- `次ページ`

current representative
- `スキルプラス_Meta広告`
  - `無料ウェビナーを受講する` の `form` が 4 箇所
  - `Meta広告_スキルプラス_ウェビナー①オプトインシナリオ`
  - `★使用中★　スキルプラス（セミナー導線）Meta広告：オプトイン　※変更時、森本雄紀に確認※`
- `起業の本質_YouTube広告`
  - 画像 CTA に `form` を載せ、`シナリオ + アクション + 次ページ` で成立する代表例

#### `thanks`

優先して見る。
- visible の CTA が主役か
- `bodyタグの最初に挿入するjs` の自動遷移が主役か

current representative
- visible CTA 型
  - `Meta広告_ライトプラン_サンクスページ（LINE登録）`
  - visible button 1 箇所
  - LIFF 直リンク
- 自動リダイレクト型
  - `【スキルプラス】サンクスページ（LINE登録）`
  - visible CTA なし
  - `bodyタグの最初に挿入するjs` で LIFF へ自動遷移

`thanks` では、まず次のどちらが主役かを切る。
- `visible CTA`
- `bodyタグの最初に挿入するjs`

ここを切らずに visible 要素だけを見ると、実際の遷移を誤りやすい。

#### `ユーザー登録`

優先して見る。
- `シナリオ`
- `アクション`
- `商品`
- 会員サイト解放

current representative
- `【スキルプラス】ユーザー登録ページ`
  - `シナリオ`
  - `アクション`
  - `商品`
  を 1 セットで見る

## representative pattern

- `LP型`
  - 主CTA は `form`
  - `シナリオ / アクション / 次ページ` の接続が本体
  - `first_view_css` や `js_head` は必要時だけ補助で使う
- `visible CTA thanks型`
  - visible button が主役
  - `short.io` や LIFF を押させる
  - 公開ページで実 click しないと誤判定しやすい
- `自動リダイレクト thanks型`
  - visible CTA より `bodyタグの最初に挿入するjs` が主役
  - 実際の遷移先で判定する
- `ユーザー登録型`
  - `商品 / シナリオ / アクション / 会員サイト解放`
    が 1 セット
  - 見た目より接続整合が最優先
- `content page型`
  - 教育や案内を担う
  - visible CTA と script 側 CTA の主従を先に切る

## representative pattern を読む時の問い

- このページは `登録させる / 送る / 視聴させる / 会員化する` のどれか
- 主CTA は visible か script か
- `新規ページ / 既存流用 / 登録経路追加` のどれが一番自然か
- code 領域は本当に必要か、それとも接続だけ直せば足りるか

## ベストな活用場面

- LP、thanks、content page、ユーザー登録ページを新規または改修したい時
- 同じページを使いながら `登録経路` で流入元分析を切りたい時
- 見た目の修正と接続修正を一緒に扱いたい時

## よくあるエラー

- ページの役割を切らずに、いきなり見た目から触る
- visible CTA と script 側 CTA の主従を見ずに誤判定する
- `登録経路` で十分な案件なのに、新規ページを増やす
- `カスタムCSS / カスタムJS / first_view_css` を理由なく触って複雑化する

## エラー時の切り分け順

1. ページの役割を `LP / thanks / content page / ユーザー登録` で切る
2. 主CTA が visible か script かを切る
3. `新規ページ / 既存流用 / 登録経路追加` のどれかを再判定する
4. `シナリオ / アクション / 遷移先` の主従を確認する
5. 最後に `カスタムCSS / カスタムJS / first_view_css` が本当に必要かを見る

### representative public page の読み方

公開ページは少なくとも次の 3 型で読む。

- `LP`
  - visible CTA が主役
  - `first_view_css` と `js_head` が効いていることが多い
- `自動リダイレクト thanks`
  - visible CTA より `bodyタグの最初に挿入するjs` が主役
- `script 側 CTA page`
  - visible CTA に見えても、script 側の direct LINE 導線が主役になることがある

したがって公開ページ review の順番は、
1. visible CTA
2. script の redirect
3. final destination
で固定する。

### code 領域の優先順

1. `デザイン`
2. `カスタムCSS`
3. `カスタムJS`
   - `headタグの最後に挿入するjs`
   - `bodyタグの最初に挿入するjs`
   - `bodyタグの最後に挿入するjs`
4. `first_view_css` は最後

`first_view_css` は LP の FV を作る、または FV 崩れを直す時だけ主因として疑う。thanks や content page では、まず `bodyタグの最初に挿入するjs` や visible CTA を先に疑う。

current representative の目安
- LP representative
  - `is_high_speed_mode = 1`
  - `first_view_css あり`
  - `js_head あり`
- ユーザー登録 representative
  - `is_high_speed_mode = 0`
  - `first_view_css = null`
  - `js_head = null`
  - `js_body_top = null`
  - `js_body = null`

## 保存前の最小チェック

- ページの役割を 1 文で言える
- 主CTA が 1 つに定まっている
- `シナリオ / アクション / 遷移先` の主従が分かっている
- `登録経路` を増やす理由を説明できる

## 保存後の最小チェック

- `プレビュー` または公開ページで実 click
- visible CTA と `bodyタグの最初に挿入するjs` が競合していないか確認
- `short.io` を使う導線なら最終遷移先まで確認
- `見た目だけ直した` つもりでも `シナリオ / アクション / 遷移先` がズレていないか再確認

## 構築精度だけを見る時のチェック

1. このページが `LP / thanks / ユーザー登録 / content page` のどれかで 1 文になっているか
2. 主CTA が visible か script かを先に切れているか
3. `シナリオ / アクション / 遷移先` の主従を 1 回で言えるか
4. `登録経路` を増やす理由が `どこから来たかを知りたい` まで下りているか
5. `カスタムCSS / カスタムJS / first_view_css` を触る理由を説明できるか
6. 公開ページで実 click して intended な挙動を確認したか
7. `short.io` を使う導線なら最終遷移先まで検証したか

## 公開前の最終検証順

1. `ページ一覧の行名`
2. `プレビュー`
3. 公開ページ
4. 主CTA
5. `シナリオ`
6. `アクション`
7. `遷移先`
8. `登録経路`
9. `short.io` の最終遷移先
10. `bodyタグの最初に挿入するjs` の有無

この順で見ると、`行名は合っているが実挙動が違う`、`visible CTA は正しいが script が別挙動を作っている` を切り分けやすい。

## ここで止めて確認する条件

- current の `ページ一覧の行名` と edit 画面の `管理名称` が噛み合わない
- visible CTA が複数あり、どれが主CTAか説明できない
- `bodyタグの最初に挿入するjs` の redirect と visible CTA の両方が生きている
- `short.io` か direct LIFF かの判断がつかない
- `登録経路` を増やす理由が `何となく分析したい` 以上に下りない
- `ユーザー登録` で `商品 / シナリオ / アクション / 会員サイト解放` のどれか 1 つでも説明できない

## 完成条件

- `新規ページ / 既存流用 / 登録経路追加` の判断を説明できる
- 主CTA、シナリオ、アクション、遷移先が一致している
- 公開ページで実 click して intended な挙動になる

## 検証

最低でも次を確認する。
- 公開ページを開く
- 主CTAを実際に押す
- 表示文字列ではなく実挙動で判定する
- short.io を使う導線なら最終遷移先まで確認する
- `登録経路` を切った場合は、対象 URL が `?ftid=` 付きで分かれることを確認する

## NG

- 広告IDの違いだけでページを複製する
- 行名を見ずに page edit を触る
- `visible CTA` と `カスタムJS` のどちらが主導線か確認しない
- 表示文字列の URL だけ見て正しいと判断する
- current / legacy の見極めなしに旧 asset を流用する
- `first_view_css` を主因と決め打ちして触り始める

## 正誤判断

正しい状態
- ページ 1 枚の役割を 1 文で言える
- `新規ページ / 既存流用 / 登録経路追加` の理由を説明できる
- 主CTA、`シナリオ`、`アクション`、遷移先が一致している
- 公開ページで実 click して正しい挙動になる

間違った状態
- ページの役割が曖昧
- 主CTAと実際の接続先がずれる
- 分析したいだけなのにページを増やす
- `カスタムCSS / カスタムJS` を理由なく足す

## References

- Addness 固有の current 例と判断は `Master/addness/utage_structure.md`
- representative な exact 手順は `references/workflow.md`
