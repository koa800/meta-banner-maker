# short.io workflow

## 目的

Addness の short.io 運用を、動画の作法と current UI の差分込みで安全に再現するための reference。

## 役割

short.io の役割は、短くすることではなく、`導線のリンク正本を 1 箇所に集約すること` です。

- 設置箇所に直URLを散らさない
- BAN やアカウント停止が起きても、short.io 側で差し替える
- URL管理シートとセットで、誰が見ても同じ意味に解釈できる状態を作る

## ゴール

- 何の導線のリンクかを一目で判別できる
- どこに置かれているか追える
- 差し替え時に設置箇所を触らずに済む
- 台帳と実体がズレない

## Mailchimp での扱い

- Mailchimp で新規に作る Journey / Campaign の `main CTA` は short.io を標準にする
- current には direct LIFF の campaign も残っているが、今後の正本運用にはしない
- 配信前は
  - 表示文字列
  - 実 hyperlink
  - short.io の最終遷移先
  を実際にクリックして確認する

## 前提

この document に書かれたワークフローは current の最適解です。
ただし、役割とゴールをより良く満たす手順が見つかったら更新してよいです。

- 目的が先
- ワークフローは後

## 必要変数

short.io を触る前に、最低でも次を確定する。
- 集客媒体
- ファネル名
- イベント名
- 設置場所
- 最終遷移先
- 流入経路名
- リンクタイトル
- slug
- フォルダ
- URL管理シート記録先

## 30秒レビューの順番

1. このリンクの役割を 1 文で言う
2. `新規作成 / 差し替え / 既存流用` のどれかを先に決める
3. `リンクタイトル` と `slug` が命名規則に合っているか見る
4. `元のURL` が意図した最終遷移先か見る
5. `フォルダ` が正しいか見る
6. URL管理シートに記録される単位か確認する

## 判断フレーム

### 1. 新規作成

次のどれかが変わるなら、新規 short.io を作る。
- 設置場所
- 流入経路名
- ファネル名
- イベント名
- 分析したい単位

つまり、`同じページに送る` だけでは流用の理由にならない。

### 2. 差し替え

次の条件をすべて満たすなら、既存 short.io の `元のURL` を差し替える。
- 役割が同じ
- 設置場所が同じ
- 流入経路名が同じ
- 計測単位も同じ
- 変わるのは最終遷移先だけ

### 3. 既存流用

次の条件をすべて満たすなら、既存 short.io をそのまま流用してよい。
- 設置場所が同じ
- 役割が同じ
- 計測を分ける必要がない
- 今後の差し替えも同じ単位で扱う

### 4. 迷ったとき

迷ったときは、`あとで分けたくなるか` を見る。
- 分けて分析したくなるなら新規作成
- 分ける意味がないなら流用
- 役割は同じでリンク先だけ更新したいなら差し替え

### 5. 設置場所の粒度

`設置場所` は、見た目上の部品ではなく、運用上区別したい単位で切る。

- 通常は `媒体 × 導線 × メール or ページ` を 1 単位で考える
- 同じページ内の複数ボタンでも、分析を分けないなら同一 short.io でよい
- 同じ LINE に送る場合でも、媒体や導線が違えば別 short.io を作る
- 迷ったら `後でここだけクリック数を見たくなるか` で判断する

## 実例

### 実例1: 新規作成

- `meta-ai3`
- `xad-ai3`
- `ttad-ai3`

この 3 つは、最終的には同じ `【みかみ】アドネス株式会社` に送る。
それでも別 short.io にする理由は、媒体が違い、後で分析したい単位も違うから。

つまり、`同じ LINE に送る` は流用理由にならない。

### 実例2: 差し替え

- `metaad-sns5`

これは `SNS7桁オプトインシナリオ2通目 / ファン化動画ページ` から `【みかみ】アドネス株式会社` に送る current 導線として使われている。

この導線の役割、設置場所、分析単位を変えずに、送る先の LINE だけを更新したいなら、新規 short.io は作らず `metaad-sns5` の `元のURL` を差し替える。

### 実例3: historical bridge

- `sp3`

`sp3` は `【アーカイブ】セミナー①企画LINE遷移` で使われる historical な橋渡し痕跡。

このように、current 本線ではない short.io も存在する。
したがって、short.io は `今見えている設置箇所だけ` で判断せず、`current / historical / bridge` の文脈まで見る。

### 実例4: 流用してよいケース

同一 UTAGE ページ内で、上部ボタンと下部ボタンがどちらも同じ LINE に送り、分析も同じ単位で見ればよい場合は、同じ short.io を流用してよい。

ただし、上部と下部でクリック差を見たいなら別にする。

## 代表ケース

### ケースA: `im013`

dashboard の current 実例として、次が見えている。  
- リンクタイトル: `Instagram_SNS_直リストイン_ロードマップ作成会_013`
- 短縮URL: `https://skill.addness.co.jp/im013`
- 元のURL: `liff.line.me/...follow=%40303zgzwt&lp=dyJ7Yy...`

このケースの判断は次のとおり。

#### 1. もし `014` を追加したい

- 広告 ID 単位で登録経路を分ける前提なら、新規作成
- 理由
  - イベント番号が変わる
  - 分析単位が変わる
  - 流入経路名も変わる

#### 2. もし `013` の送り先だけ変えたい

- 同じ広告 ID、同じ設置場所、同じ分析単位のまま送り先だけ更新するなら差し替え
- 理由
  - 役割が同じ
  - 設置場所が同じ
  - 流入経路名も同じ
  - 変わるのは最終遷移先だけ

#### 3. もし同じ LP の別ボタンにも貼りたい

- 分析を分けないなら流用
- クリック位置差を見たいなら別 short.io

### ケースB: `prime-kanso`

dashboard の current 実例として、次が見えている。  
- リンクタイトル: `Mプライム合宿_口コミ用`
- 短縮URL: `https://skill.addness.co.jp/prime-kanso`
- 元のURL: `https://school.addness.co.jp/page/TFmCVkVygNI3`

このケースの判断は次のとおり。

#### 1. 口コミ導線の同じ設置場所で、UTAGE ページだけ差し替えたい

- 差し替え
- 理由
  - 役割は `口コミ用`
  - 設置場所も変えない
  - 分析単位も変えない
  - 変わるのは UTAGE の遷移先だけ

#### 2. 別媒体用の口コミ導線を増やしたい

- 新規作成
- 理由
  - 媒体が変わる
  - 計測単位を分けたくなる
  - 後で成績比較したくなる

## 実行テンプレート

### 依頼を受けたら最初に埋める

- 何の導線か
- 何のためのリンクか
- どこに置くか
- どこへ送るか
- 分析をどの単位で見たいか
- 既存リンクを使う前提か、新しく切る前提か

### 新規作成テンプレート

- 集客媒体:
- ファネル名:
- イベント名:
- 設置場所:
- 最終遷移先:
- 流入経路名:
- リンクタイトル:
- slug:
- フォルダ:
- URL管理シート記録先:

### 差し替えテンプレート

- 対象 short.io:
- 現在の役割:
- 現在の設置場所:
- 現在の流入経路名:
- 新しい遷移先:
- 差し替え理由:

### 流用テンプレート

- 既存 short.io:
- 流用先:
- 同一とみなす理由:
- 分析を分けない理由:

## 完了判定

### 新規作成

- short.io を作成した
- `リンクタイトル = 流入経路名`
- フォルダが正しい
- URL管理シートを更新した

### 差し替え

- short.io 側だけで差し替えた
- 設置箇所を触っていない
- URL管理シートの遷移先と最新日付を更新した

### 流用

- 流用理由を言語化できる
- 後で分けて見たくなる要件がない
- 誰が見ても同じ意味に解釈できる

## live exact 補助経路

- create:
  - `python3 System/scripts/shortio_api_client.py create-link --original-url "<url>" --path "<slug>" --title "<title>"`
- resolve:
  - `python3 System/scripts/shortio_api_client.py resolve "https://skill.addness.co.jp/<slug>"`
- update:
  - `python3 System/scripts/shortio_api_client.py update-link "<link_id>" --original-url "<url>" --title "<title>"`
- delete:
  - `python3 System/scripts/shortio_api_client.py delete-link "<link_id>"`

### 2026-03-16 の live exact

- exploratory link:
  - `https://skill.addness.co.jp/zz-test-20260316-shortio`
- 通した順:
  - create
  - resolve
  - update
  - resolve
  - delete
- cleanup:
  - resolve で一致 link が見つからないことまで確認済み

## 動画から固定するルール

### 1. 作成前

- 先に Lステップ の流入経路を作る
- 流入経路名の命名規則を先に確定する
- `リンクタイトル` は流入経路名と完全一致させる

### 2. 作成

- short.io の `ブランドリンク` を開く
- 元URLを貼る
- `カスタマイズ機能 -> 基本的なリンク編集` で
  - `リンクスラグ`
  - `リンクタイトル`
  を設定する
- 正しいフォルダへ入れる

### 3. 台帳管理

- 作成後は URL管理シートを更新する
- 最低でも次を記録する
  - 区分
  - ファネル
  - 設置場所
  - リンクタイトル
  - リンクURL
  - 遷移先名
  - 遷移先リンク
  - 更新日

### 実案件でズレにくい順番

- 先に short.io を作らない
- 実務順は次に固定する
  - `Lステップ / UTAGE 側の遷移先を先に作る`
  - `short.io を作る`
  - `URL管理シートを更新する`
  - `必要な相手に共有する`
- 理由
  - 遷移先が固まる前に short.io を作ると、タイトル、台帳、共有文面がずれやすい
  - 実際に 2026-03-17 の `スキルプラス公式TV` 事例でも、この順が最も安定した

### 4. 差し替え

- 設置箇所を直接修正する前に、short.io 側で差し替える
- 対象リンクを検索する
- 編集画面から `元のURL` を新URLへ差し替える

## URL管理シートの current 正本

- 管理シートは `【アドネス全体】URL管理シート`
- hidden backend は `01_全体台帳`
- visible の作業タブは `集客媒体` ごとに分ける
- visible タブは `共通 / Meta広告 / TikTok広告 / YouTube広告 / 𝕏広告 / LINE広告 / Yahoo広告 / リスティング広告 / アフィリエイト広告 / YouTube / 𝕏 / Instagram / Threads / TikTok / 一般検索 / 広報 / オフライン / その他`
- `01_全体台帳` の列は
  - `ファネル名`
  - `集客媒体`
  - `設置場所`
  - `リンクタイトル`
  - `リンクURL`
  - `遷移先名`
  - `遷移先リンク`
  - `更新日`
  - `状態`
- `リンクURL` と `遷移先リンク` は、シート上でそのまま押せるようセル自体にリンク属性を持たせる
- 適用順は `値を書き込む -> 体裁を整える -> リンク属性を付ける` に固定する。逆順だと書式更新でリンク属性が消える
- visible タブの列は
  - `ファネル名`
  - `設置場所`
  - `リンクタイトル`
  - `リンクURL`
  - `遷移先名`
  - `遷移先リンク`
  - `更新日`
  - `状態`
- `共通導線` の行は、媒体に関係なく `共通` タブへ寄せる
- 各タブ内の並び順は `センサーズ -> AI -> アドプロ -> スキルプラス -> ライトプラン -> 書籍 -> その他`
- `リンクエラー用` の行は `広報` ではなく `その他` タブへ寄せる
- visible タブでは、連続する同一 `ファネル名` を A列で縦結合する
- visible タブの罫線は全範囲で統一する
- old tab は削除済みで、current は `集客媒体タブ + hidden master` だけで見る
- 広告系 4 タブ
  - `広告（みかみ導線）`
  - `広告（スキルプラス導線）`
  - `広告（ライトプラン導線）`
  - `広告（書籍）`
  は、非破壊で hidden の `広告（統合）` に集約し、その上で `01_全体台帳` に取り込んだ
- つまり、old tab の `飛び先URL` は `遷移先リンク` に統合し、`最新（YYYY/MM/DD）` は行単位の `更新日` に正規化した
- `未作成` の行は master / visible ともに残さない
- 体裁は `スプレッドシート設計ルール` に合わせて、ヘッダー色、フィルタ、凍結、交互色、列幅、`切り詰める(CLIP)` を再適用する
- C列とD列は文字が見える幅まで広げる
- short.io 実体との同期は `System/scripts/shortio_api_client.py sync-ads-sheet` を使い、まず `広告（統合）` の `遷移先 / 更新日` を合わせる
  - dry-run: `python3 System/scripts/shortio_api_client.py sync-ads-sheet`
  - 反映: `python3 System/scripts/shortio_api_client.py sync-ads-sheet --write`
- visible タブの再構築は `System/scripts/shortio_api_client.py rebuild-sheet-views` を使う
- `--delete-obsolete` を付けると、`00_役割と使い方` を含む旧タブ群を削除したうえで current 形へ寄せる
- 品質監査は `python3 System/scripts/shortio_api_client.py audit-sheet` で行う
- 2026-03-10 時点の監査結果では、`未作成` を除く残差は `0件` まで解消済み

## current UI で見えていること

### dashboard

- route: `https://app.short.io/users/dashboard/1304048/links`
- 主列
  - `短縮リンク`
  - `元のリンク`
  - `クリック数`
  - `コンバージョン数`
  - `タグ`
  - `アクション`
- quick create は元URLを入れて `リンクを作成`
- 発行直後に `path` フィールドが見えるので、slug の最終調整はここで行う
- 一覧行のアクションには current UI で少なくとも次がある
  - `編集`
  - `統計`
  - `共有`
  - `Duplicate`
  - `削除`
- `編集` は `/users/dashboard/1304048/links/{linkId}/edit/basic`
- `統計` は `/users/dashboard/1304048/links/{linkId}/statistics`
- したがって、既存リンクの差し替えや確認は `dashboard -> 対象行のアクション` を起点にする

### 既存リンクの編集

- route: `https://app.short.io/users/dashboard/1304048/links/{linkId}/edit/basic`
- 左メニューで current に見えている項目
  - `基本的なリンク編集`
  - `モバイルターゲティング`
  - `キャンペーントラッキング`
  - `地域ターゲティング`
  - `仮URL`
  - `リンククローキング`
  - `パスワード保護`
  - `ロゴ付きQRコード`
  - `A/Bテスト`
  - `HTTPステータス`
  - `オープングラフメタデータ`
  - `リンク許可`
  - `トラッキングコード`
  - `Links bundle`
- `基本的なリンク編集` で少なくとも次を触る
  - `リンクスラッグ`
  - `リンクタイトル`
  - `元のURL`
  - `フォルダ内のリンク`
  - `短縮URLのタグ`
- 画面下部は `SAVE / CANCEL`
- current の差し替え導線は
  - `dashboard`
  - 対象リンクを検索
  - 行アクションの `編集`
  - `基本的なリンク編集`
  - `元のURL` 差し替え
  - `SAVE`
  の順で固定できる
- non-production のテストリンク `HIh3ps` では、実際に
  - `リンクタイトル = codex_test_link_20260310`
  - `元のURL = https://example.com/shortio-test-20260310`
  を保存し、`変更は正常に保存されました` を確認した
- したがって、`edit/basic` の save 導線は机上ではなく live 実績がある

### folders

- category chip として少なくとも次が見える
  - `SEO`
  - `SNS`
  - `SNS(YT)`
  - `その他`
  - `導線`
  - `広告`
  - `広報`

### 統計

- route: `https://app.short.io/users/dashboard/1304048/statistics`
- 期間は `過去30日` が見える
- 読める主項目
  - 上位リンク
  - 都市
  - 国
  - ブラウザ
  - OS
  - リファラー
  - ソーシャルリファラー
  - ミディアム
  - ソース
  - キャンペーン
- 個別リンク統計 route は `https://app.short.io/users/dashboard/1304048/links/{linkId}/statistics`
- 個別リンク統計の current UI で少なくとも次が見える
  - `期間`
  - `統計`
  - `共有`
  - `EDIT`
  - `時間の経過に伴うメトリックの比較`
  - `総クリック数`
  - `人によるクリック`
  - `上位の国`
  - `上位の都市`
  - `上位のブラウザ`
  - `上位のOS`
  - `上位のリファラー`
  - `上位のソーシャルリファラー`
- つまり、効果確認は
  - `dashboard`
  - 対象行の `統計`
  - `期間`
  - `総クリック数 / 人によるクリック`
  - `国 / 都市 / リファラー`
  の順で読むとズレにくい

### 統合とAPI

- route: `https://app.short.io/settings/integrations`
- 少なくとも次が見える
  - `API`
  - `ブラウザプラグイン`
  - `アプリケーション`
  - `Slack`
  - `Wordpress`
  - `Zapierを使ったその他のサービス`
  - `Make`
  - `GitHub Actions`
  - `MCP`
- durable な自動化をするなら、ここから `API` に入り secret API key を作るのが正道
- browser セッションでは `IndexedDB(shortio)` に
  - `encrypted_jwt`
  - `encrytion_key`
  - `iv`
  があり、browser 内では復号できる
- ただし、これは current セッション解析には使えても、運用の正本にはしない
- 正しい方針は `Integrations & API -> API -> secret API key` を作って使うこと
- 実際に browser JWT を使って `https://api.short.io/links/...` を read-only で叩くと `401 認証エラー / 無効なAPIキー` になる
- つまり、official API の自動取得は `session JWT` ではなく `secret API key` が必須

### API 自動取得の current 実績

- 2026-03-10 に `codex_shortio_api_20260310` を domain `1304048` 向けに発行済み
- 保存先は `System/credentials/shortio_api_key.json`
- 再利用用の helper は `System/scripts/shortio_api_client.py`
- 現時点で通っているコマンド
  - `python3 System/scripts/shortio_api_client.py folders`
  - `python3 System/scripts/shortio_api_client.py search --query prime --limit 1`
  - `python3 System/scripts/shortio_api_client.py link-stats lnk_5tf2_mogQ2Cl7tSBVud7XVeYkn --period last30`
- つまり、official API では少なくとも
  - フォルダ一覧
  - リンク検索
  - 個別リンク統計
  までは自動取得できる
- official docs の起点
  - Guides: `https://developers.short.io/docs`
  - Reference: `https://developers.short.io/reference`
- rate limit の目安
  - 一般 API は 20〜50 RPS
  - 統計 API は 60 RPM
  - bulk create は 5 request / 10 sec、1 回で最大 1000 links
- したがって、自動化で `一覧取得 -> 統計取得 -> シート同期` をやるときは
  - bulk で一気に叩きすぎない
  - 統計取得は interval を持たせる
  - 正式 API key を domain/team 単位で制限する
  の順で考える

## 動画と current UI の差分

- 動画では `カスタマイズ機能 -> 基本的なリンク編集` と `鉛筆ボタン` が前面に出ている
- current UI では、既存リンク編集の入口は `dashboard の各行アクション -> 編集` で固定できた
- つまり、考え方は動画どおりで、入口だけを current UI に読み替えればよい

## 保存前の最小チェック

- 新規作成か差し替えか流用かを決めている
- title と slug を確定している
- シート更新の行先が決まっている

## 保存後の最小チェック

- 実 click で final destination を確認した
- URL 管理シートを更新した
- 既存 link の役割を壊していない

## NG

- 命名規則が未確定のまま作る
- リンクタイトルと流入経路名をずらす
- URL管理シートを更新しない
- BAN や停止の可能性があるリンクを直URLで配る
- 差し替え時に設置箇所を先に直してしまう
- browser の一時 JWT を、そのまま長期運用の自動化トークンとして使う

## 正誤判断

### 正しい

- 「このリンクは何のために存在するか」を説明できる
- 「どの変数が変わったから新規作成なのか / 差し替えなのか」を説明できる
- 作成から台帳更新まで一連で完了している
- 差し替えを short.io 側で完了できている
- 設置場所と分析単位をセットで説明できる
- 集客媒体タブを見れば、担当者が迷わず必要行へ辿り着ける
- 自動化が必要なとき、browser セッション解析と正式 API key 運用を分けて判断できる

### 間違い

- 短縮した時点で完了扱いにする
- URL管理シートと short.io の実体がズレる
- 設置箇所と short.io のどちらを正本にするか曖昧
- 既存リンクを流用して良い条件が曖昧
- 同じ遷移先だからという理由だけで流用する

## 完成条件

- `新規作成 / 差し替え / 流用` のどれかを理由付きで選べる
- `リンクタイトル = 流入経路名` が守られている
- short.io 上の実体と URL管理シートが一致している
- final destination まで押して確認している
- 後から別担当が見ても、役割と設置場所を迷わず読める

## ここで止めて確認する条件

- 役割が同じかどうか自分で言い切れず、`新規作成 / 差し替え / 流用` の判断が割れる
- `リンクタイトル` と `流入経路名` を一致させられない
- 設置場所は違うのに、同じ short.io を使い回したくなっている
- final destination が LINE か UTAGE か外部ページか分からない
