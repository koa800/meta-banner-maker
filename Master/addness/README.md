# addness レイヤー

最終更新: 2026-03-11

`Master/addness/` は、Addness 事業の実務 knowledge をまとめる詳細層です。4層で見ると主に `knowledge` に属します。

## このフォルダの役割

- Addness のゴール構造を持つ
- 実行タスクの一覧を持つ
- 導線、Lステップ、広告、リサーチの事実を持つ
- 秘書の自律ワークが参照する運用 knowledge を持つ

## 主なファイル

- `goal-tree.md`
  Addness の全体ゴールツリー。巨大だが最重要の運用 knowledge
- `actionable-tasks.md`
  いま実行対象になっているタスク一覧
- `funnel_structure.md`
  導線・ファネル構造の把握
- `lstep_accounts_analysis.md`
  Lステップ運用とアカウント構造
- `meta_ads_大当たりCR分析.md`
  勝ち CR の分析 knowledge
- `dpro_*.md`, `ds_insight_evaluation.md`, `market_trends.md`
  外部調査・市場観察
- `ui_operations.md`
  Addness UI の操作 knowledge
- `proactive_output/`
  legacy の成果物出力先

## 現在地と100点との差分

### 100点の定義

- 要件として
  - 文章
  - 素材
  - カスタマージャーニー
  が渡されれば
- どのツールで
  - 何を作るか
  - どこに置くか
  - どの設定をつなぐか
  を迷わず判断でき
- 速く
- 事故なく
- 既存品質以上で
  実装できる状態

### 100点の見方

100点は、項目を全部触れることではない。

次の構造を持てている状態を 100 点に近いとみなす。
- 役割
- ゴール
- 必要変数
- ワークフロー
- NG
- 正誤判断

つまり、`何ができるか` より先に、`何のために存在し、何が正しく、何が間違いかを説明できるか` を見る。

### 目的とワークフローの関係

- 目的が先
- ワークフローは後

ワークフローは `今の最適手順` であって、絶対ルールではない。
目的をより速く、安全に、再現性高く、高品質に達成できるなら、ワークフローは更新する。

### 現在の自己評価

- Lステップ: `9.98 / 10`
- UTAGE: `9.8 / 10`
- Mailchimp: `9.85 / 10`
- short.io: `10 / 10`
- 全体理解: `9.0〜9.2 / 10`

### Lステップ

- かなりできる
  - テンプレート
  - 流入経路
  - タグ
  - リッチメニュー
  - 回答フォーム
  - 一斉配信
  - イベント予約
  - カレンダー予約
  - クロス分析
- ここまで live で exact 画面確認済み
  - `【予約窓口】スキルプラス合宿` で
    - 流入経路
    - クロス分析
    - イベント予約
    - カレンダー予約
    - タグ管理
    - 回答フォーム
    - 一斉配信
  - `スキルプラス【サポートLINE】` で
    - 流入経路
    - タグ管理
    - 回答フォーム
    - 一斉配信
    - リッチメニュー
    - クロス分析
  - 役割理解だけでなく、主要画面の exact UI も `スキルプラス【サポートLINE】` まで current 反映済み
  - `アクション管理` の create modal で
    - `テンプレート送信`
    - `タグ操作`
    - `シナリオ操作`
    - `メニュー操作`
    - `イベント予約操作`
    の具体 field まで確認済み
  - template editor 側では
    - `URL訪問時アクションを設定する場合は、サイト設定ページから設定`
    という current の責務分離も確認済み
  - シナリオ配信は
    - 一覧 = `/line/content/group?group={group_id}`
    - editor = `/line/content/{content_group_id}?group={group_id}`
    の current route を確認済み
  - シナリオ editor では row 単位に
    - `編集 / 挿入 / コピー / プレビュー / 別窓 / テスト / 削除`
    を使う構造まで確認済み
  - クロス分析は `作成 -> 再読込 -> 削除` まで live テスト済み
    - `POST /line/board/edit`
    - `GET /api/board/data/{id}`
    - `DELETE /api/boards/{id}`
    まで実確認済み
  - リッチメニューは current edit 画面の内部項目まで fixed
    - `タイトル / フォルダ / 初期状態 / 各ボタンの URL・テンプレ・action・回答フォーム・その他`
    - `一覧へ戻る / 保存`
    まで確認済み
  - ログイン補助も固定済み
    - `python3 System/scripts/lstep_login_helper.py --target <開きたいURL>`
    - ログイン済みならそのまま target を開く
    - 未ログインなら `System/credentials/lstep.json` から自動入力する
    - reCAPTCHA の画像 challenge が出た場合だけ手動確認が必要
- 残差
  - hidden / legacy / 命名規則違反の判断辞書を増やす

### UTAGE

- かなりできる
  - ファネル
  - ページ
  - 商品
  - detail
  - アクション
  - 会員サイト
  - バンドルコース
  - 講義
  - 動画管理
  - メディア管理
- current で理解できていること
  - Mailchimp がメール本線
  - UTAGE はページ / 会員サイト / 商品 / action の基盤
  - `【センサーズ関連】` は過去のメインファネル群として重要
  - `product -> detail -> action -> 会員サイト解放` の representative path は実値で確認済み
  - representative funnel の `データ(合算) / データ(日別) / 登録経路` も live で確認済み
    - 例: `AI：メインファネル_Meta広告`
    - funnel id: `TXUOxBYkYr9e`
    - `.../data`
    - `.../data/daily`
    - `.../tracking`
  - representative page も current 実装を複数本見ている
  - `登録経路` は「広告IDだから分ける」ではなく、「どこから来たかを知りたい時に分ける」分析軸として理解している
  - `登録経路` の create route と field も確認済み
    - `.../tracking/create`
    - `グループ / 管理名称 / ファネルステップ / ページ`
  - current page editor の settings UI も live で固定できた
    - `基本情報`
    - `デザイン`
    - `高速表示モード`
    - `メタデータ・検索`
    - `カスタムJS`
    - `カスタムCSS`
  - `カスタムJS` は
    - `headタグの最後`
    - `bodyタグの最初`
    - `bodyタグの最後`
    の3箇所
  - `高速表示モード` は current UI 上では `is_high_speed_mode` の切替のみ visible
    で、`first_view_css` は独立 field としては見えていない
  - `utage_login_helper.py` は edit 画面でも自動ログイン判定できるように補強済み
  - runtime の Vue app では `#app.__vue_app__._container._vnode.component.data.page.first_view_css`
    に `first_view_css` 実値が載っていることを確認済み
  - edit HTML には current save endpoint として
    - `/update/basic`
    - `/update/pcwidth`
    - `/update/meta`
    - `/update/js`
    - `/update/css`
    - `/update/speed`
    - `/update/ads`
    - `/update/deadline`
    - `/update/onetimeoffer`
    - `/update/password`
    が埋まっていることも確認済み
  - ログイン補助も固定済み
    - `python3 System/scripts/utage_login_helper.py --target <開きたいURL>`
  - 商品販売設定の current 標準手順も live route まで固定できた
    - `商品追加 = /product/create`
    - `detail 追加 = /product/{product_id}/detail/create`
    - `action 編集 = /action/{action_id}/edit`
    - `bundle 編集 = /site/{site_id}/bundle/{bundle_id}/edit`
  - code 領域の current 使い分けもかなり固定できた
    - `js_head = 計測タグ`
    - `js_body_top = 自動遷移 / 初回即時演出`
    - `js_body = 遅延でよい補助処理`
    - `css = page 全体補正`
    - `first_view_css = 高速表示レイヤーの FV 補正`
- 残差
  - representative page をもう少し増やし、code 領域の good / bad 事例を厚くする

### Mailchimp

- かなり見えている
  - current の本線が Mailchimp 側で動いていること
  - audience
  - trigger tag
  - AI / SNS の 7桁本線
  - 一部の個別3日間シナリオ
  - active queue の考え方
- recent sending も current 実値で確認済み
  - 例
    - `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
    - `UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
  - `UTAGE_AIカレッジ_X広告_7桁オプトイン`
  - `UTAGE_AI_YouTubeメインファネル_7桁オプトイン`
- API ベースの current 読解手順も固定できた
  - `GET /customer-journeys/journeys`
    - `journey_name`
    - `status`
    - `stats.started / in_progress / completed`
    を先に見る
  - `GET /customer-journeys/journeys/{id}/steps`
    - `step_type = action-send_email`
    - `status = active`
    - `stats.queue_count > 0`
    で「今も送信待ちが残っているメール」だけを拾う
  - 同じレスポンスの
    - `action_details.email.settings.title`
    - `action_details.email.settings.subject_line`
    - `action_details.email.emails_sent`
    で、メール名と件名と送信実績を読む
  - `GET /campaigns/{campaign_id}/content`
    で本文 HTML を取得し、UTAGE / short.io / 外部リンクを抜く
  - `GET /reports/{campaign_id}/click-details`
    で実際に押されている URL を読む
  - current のメールは short.io を介して UTAGE ページに送る前提が多いので、`click-details -> short.io -> UTAGE data` を 1 本で見るのが次の標準
- current のコンテンツ意図も読み始めている
  - 本線 7桁オプトインは `人物ストーリー / authority / open loop` で教育する
  - 途中の `コンサル / 本気オファー` は距離を縮めて直CTAへ寄せる
  - `スキルプラスフリープラン` は無料オファーで口を広げる横展開
  - `個別3日間` は `あなた専用 / 反響 / 締切` の順で面談系CTAに押し込む
  - 本文まで確認できた representative 例
    - AI本線1通目: `東大生社長みかみがAI未経験から年収2億ベースで稼ぐまでの軌跡`
    - AI直オファー: `【緊急告知！！】直接コンサルしましょうか？笑`
    - SNS本線1通目: `元東大生社長みかみが年商2億稼ぐまでの軌跡`
    - SNS直オファー: `間も無く締め切ります`
    - SNS個別3日間: `【今だけ無料！】"あなた専用" SNS運用 1st副業スタートプログラム開催！！`
  - current を誤読しない基準も固まった
  - `journey が sending` でも、`step が paused` なら current メール扱いしない
  - `last_started_at` だけでは current 判定しない
  - `queue_count > 0` を最優先で見る
  - `copy` が付くものでも、queue が残っていれば current として扱う
  - current 実例として
    - `スキルプラスフリープラン1通目 (copy 03) = queue 191 / sent 31,173`
    - `センサーズFB広告_本気コンサルオファー (copy 05) = queue 1 / sent 17,987`
    - `AIカレッジFB広告_個別3日間シナリオ_3日目 (copy 02) = queue 1 / sent 28,146`
    を確認済み
- current の代表例
  - `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
    - `started 31,902 / in_progress 4,504 / completed 27,394`
    - `スキルプラスフリープラン1〜5通目`
    - `AIカレッジFB広告_プロンプト企画`
    - `AIカレッジFB広告_SNS企画`
    - `フリープラン岡田結実`
    などで queue が残っている
  - `UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
    - `started 18,210 / in_progress 4,357 / completed 13,852`
    - `本気コンサルRe`
    - `スキルプラスフリープラン1〜5通目`
    などで queue が残っている
  - `UTAGE_AIカレッジ_X広告_7桁オプトイン`
    - `started 27,428 / in_progress 2,472 / completed 24,953`
    - `スキルプラスフリープラン`
    - `AI習得レッスン`
    - `プロンプト企画`
    - `個別誘導`
    などで queue が残っている
- 本文と click report まで current 実値で確認済み
  - 例: AI Facebook の `スキルプラスフリープラン1通目 (copy 03)` は本文内に `school.addness.co.jp/p/TzYRwepfqzFq?...` を持つ
  - 例: click report では `skill.addness.co.jp/ytad-ai2A` のような short.io が実際に押されている
- live UI の exact 画面も確認済み
  - ログインは `login.mailchimp.com` -> `login/unifiedLoginPost` -> `us5.admin.mailchimp.com/login/verify`
  - `python3 System/scripts/mailchimp_login_helper.py --target <開きたいURL>` で email / password 自動入力までは固定済み
  - 2段階認証は `Send code via SMS` -> LINE の `Mailchimp認証` グループでコード確認 -> verify 画面へ入力 の順
  - Automations 一覧には `Build from scratch` `Choose flow template` `Search by name` `Status` `Objective` `Sort by: Last created` がある
  - `Build from scratch` から `customer-journey/create-new-journey/` に入り、`Name flow` `Audience` `Choose a trigger` の順で新規作成を始める
  - `Choose a trigger` を押した時点で `builder?id={id}&stepModal=trigger` に変わり draft を作るので、live テスト時は同セッションで `Actions -> Delete -> Delete flow` まで戻す
  - Journey 名クリックで `customer-journey/builder?id={id}` に入る
  - builder 上部には `Send Test Emails` `View Report` `Pause & Edit` `Save and close flow` がある
  - builder 本体では `Contact tagged ...` `Filter who can enter` `Send email ...` `Contact exits` を map 上で管理し、右パネルは `Data / Settings` で切り替える
  - `Tag added` trigger の current 画面では `Set a tag` `Filter who can enter` `Save Trigger` が出る
  - `View Report` は `customer-journey/report?id={id}` に入り
    - `Days active`
    - `Total started`
    - `Total in progress`
    - `Total completed`
    - `Open rate`
    - `Click rate`
    - `Unsubscribe rate`
    - `Delivery rate`
    を flow 単位で読む
  - tag は英語で作る前提に寄せる
  - 基本構造は `media_funnel_event`
  - Journey は `エバーグリーン用`
  - Campaign は `1回きりのセグメント配信用`
    として使い分ける前提
  - representative campaign
    - `3/11 AIキャリアセミナーPR_2通目` = `Subscribed` 全体へ 255,250 通
    - `3/10 セミナーPR_3通目 (フリープラン)` = `freeplan_Buy` tagged contacts に 5,044 通
  - current / legacy 判定辞書もかなり固定できた
    - `active + queue > 0 = current`
    - `active + queue = 0 + sentあり = completed but still valid`
    - `paused + sentあり = historical evidence`
    - `paused + queue 0 + sent 0 = draft / legacy candidate`
  - API でも `regular campaign` の create / content / delete が通ることを確認済み
    - `ZZ_TEST_DELETE_20260311` を作成し、本文設定後に削除して最終 `404` を確認
  - Campaign Manager の current route は `/campaigns/`
  - current の create 入口は `Campaign Manager -> Create -> campaigns/#/create-campaign`
  - row 上では `Regular email / Automation flow / Draft / Sent / Segment / Exclude` まで visible
- 残差
  - current 本線と legacy copy の辞書をさらに厚くする
  - `送信 -> 開封 -> クリック -> UTAGE訪問 -> コンバージョン` を 1 本で可視化する動線データ基盤はまだ未構築

### 動線データ基盤

- 目的
  - 分析用の可視化
  - マーケティング施策立案に直結するデータ収集
- 最初に追う主要変数
  - CPA
  - 個別相談数
  - 営業成約率
  - 解約率
- そのために必要な導線データ
  - メール送信数
  - 開封数 / 開封率
  - リンククリック数 / クリック率
  - UTAGE 訪問者数
  - コンバージョン数
- このレイヤーは CDP とは別で設計する前提

### short.io

- かなり見えている
  - `skill.addness.co.jp` を固定リンク基盤として使うこと
  - URL管理シートで台帳管理していること
  - LINE に送るリンクは必ず short.io で管理すること
  - BAN / 停止時のリンク失効対策として使っていること
  - クリック分析の API 入口があること
- 役割
  - 導線に置かれたリンクの正本を 1 箇所に集約し、設置箇所を触らずに差し替えられるようにすること
- ゴール
  - 命名、台帳、差し替え、分析が一貫していて、誰が見ても同じ意味に解釈できること
- 必要変数
  - 集客媒体
  - ファネル名
  - イベント名
  - 設置場所
  - 最終遷移先
  - 流入経路名
  - リンクタイトル
  - slug
  - フォルダ
- 判断フレーム
  - 新規作成: 設置場所、流入経路名、分析単位、ファネル名、イベント名のどれかが変わる
  - 既存差し替え: 役割、設置場所、流入経路名、分析単位は同じで、最終遷移先だけ変わる
  - 既存流用: 設置場所、役割、計測単位が同じで、分ける意味がない
- 設置場所の粒度
  - 通常は `媒体 × 導線 × メール or ページ`
  - 同じページ内の複数CTAは、分析を分けないなら同一 short.io でよい
- 正誤判断
  - 正しい: `リンクタイトル = 流入経路名`、URL管理シート更新まで完了、差し替えを short.io 側で完了
  - 間違い: とりあえず短縮して配る、台帳更新しない、設置箇所を先に直す、同じ遷移先だからという理由だけで流用する
- 実例
  - 新規作成: `meta-ai3 / xad-ai3 / ttad-ai3` は同じ LINE 送りでも媒体が違うので別 short.io
  - 差し替え: `metaad-sns5` は役割と設置場所が同じなら `元のURL` 差し替え
  - historical bridge: `sp3` は current 本線ではなく historical な橋渡し痕跡
  - current 実例: `im013` は `Instagram_SNS_直リストイン_ロードマップ作成会_013` で、`014` を増やすなら新規作成、`013` の送り先だけ変えるなら差し替え
  - current 実例: `prime-kanso` は `Mプライム合宿_口コミ用` で、同じ口コミ導線の UTAGE ページだけ変えるなら差し替え、別媒体に広げるなら新規作成
- 実行テンプレート
  - 依頼を受けたら `何の導線か / 何のためのリンクか / どこに置くか / どこへ送るか / 分析単位` を先に埋める
  - その後に `新規作成 / 差し替え / 流用` を判断する
- 完了判定
  - 新規作成: short.io 作成、タイトル整合、フォルダ整合、台帳更新
  - 差し替え: short.io 側だけで完了、設置箇所未修正、台帳更新
  - 流用: 理由説明可、分析を分ける要件なし
- Loom の運用動画からも current 作法を補強済み
  - 動画タイトルは `LSTEPの短縮URL作成と管理方法について📈`
  - 命名規則を守る
  - short.io でリンクを作る
  - スプレッドシートへ記録する
  - リンク先変更は設置箇所ではなく short.io 側で差し替える
  - Loom のチャプターも `作成手順 -> ツール紹介 -> 使い方 -> 管理方法 -> 差し替え -> まとめ` の順で、この運用が一連の標準手順として説明されている
  - さらに transcript から
    - `リンクタイトルは流入経路名と完全一致`
    - `カスタマイズ機能 -> 基本的なリンク編集`
    - `鉛筆ボタンから元URLを差し替える`
    - `最新日付もシートで更新する`
    まで fixed できた
- live UI の exact 画面も確認済み
  - dashboard は `ブランドリンク` が本体で、`短縮リンク / 元のリンク / クリック数 / コンバージョン数 / タグ / アクション` を一覧で持つ
  - quick create は `Paste URL here...` に元URLを入れて `リンクを作成` を押すと、その場で短縮URLが自動発行される
  - 作成直後に `path` を持つ編集フィールドが出るため、slug の最終調整は作成直後に行う前提
  - 一覧行の `アクション` には current UI で `編集 / 統計 / 共有 / Duplicate / 削除` が直接並ぶ
  - 既存リンク編集は `users/dashboard/{domainId}/links/{linkId}/edit/basic` に入る
  - `edit/basic` の左メニューには `基本的なリンク編集 / モバイルターゲティング / キャンペーントラッキング / 地域ターゲティング / 仮URL / リンククローキング / パスワード保護 / ロゴ付きQRコード / A/Bテスト / HTTPステータス / オープングラフメタデータ / リンク許可 / トラッキングコード / Links bundle` がある
  - 既存リンク統計は `users/dashboard/{domainId}/links/{linkId}/statistics` に入る
  - `edit/basic` では `path / title / originalURL / folderId / tag` を触り、下部の `SAVE / CANCEL` で確定する
  - current の差し替え導線は `dashboard -> 対象リンク検索 -> 行アクションの編集 -> 基本的なリンク編集 -> 元のURL差し替え -> SAVE`
  - non-production のテストリンク `HIh3ps` では、実際に `title` と `originalURL` を更新し、`変更は正常に保存されました` まで live 確認済み
  - `ドメイン統計` では `過去30日` を基準に、上位リンク / 都市 / 国 / ブラウザ / OS / リファラー / ソーシャルリファラー / ミディアム / ソース / キャンペーンまで見える
  - 個別リンク統計では `期間 / 統計 / 共有 / EDIT / 時間の経過に伴うメトリックの比較 / 総クリック数 / 人によるクリック / 上位の国 / 上位の都市 / 上位のブラウザ / 上位のOS / 上位のリファラー / 上位のソーシャルリファラー` が見える
  - `統合とAPI` は `app.short.io/settings/integrations` で、`API / ブラウザプラグイン / アプリケーション / Slack / Wordpress / Zapier / Make / GitHub Actions / MCP` に入れる
  - browser セッションでは `IndexedDB(shortio)` に `encrypted_jwt / encrytion_key / iv` があり、browser 内では復号できることも確認済み
  - ただし、運用として正しい自動化は `Integrations & API -> API` で secret API key を発行して行うべきで、browser JWT は current セッション解析に限定する
  - official docs 上の rate limit は、一般 API が 20〜50 RPS、統計 API が 60 RPM、bulk create が 5 request / 10 sec・1 回最大 1000 links
  - 実際に browser JWT で `https://api.short.io/links/...` を read-only で叩くと `401 認証エラー / 無効なAPIキー` になり、official API は secret API key 必須と確認できた
  - `Integrations & API -> API` で domain `1304048` 向けの secret API key を発行済み
  - `System/scripts/shortio_api_client.py` で、official API の
    - フォルダ一覧
    - リンク検索
    - 個別リンク統計
    を再取得できる
  - URL管理シート `【アドネス全体】URL管理シート` は、広告系 4 タブを非破壊で hidden の `広告（統合）` に集約したうえで、current 正本を `01_全体台帳` に移した
  - `00_役割と使い方` は削除済み
  - hidden backend は `01_全体台帳`
  - visible の作業タブは `集客媒体` ごとに分ける
  - visible タブは `共通 / Meta広告 / TikTok広告 / YouTube広告 / 𝕏広告 / LINE広告 / Yahoo広告 / リスティング広告 / アフィリエイト広告 / YouTube / 𝕏 / Instagram / Threads / TikTok / 一般検索 / 広報 / オフライン / その他`
  - `01_全体台帳` の列は `ファネル名 / 集客媒体 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
  - visible タブの列は `ファネル名 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
  - `リンクURL` と `遷移先リンク` は plain text ではなく、セル自体にリンク属性を持たせているため、そのままクリックできる
  - 更新順は `値を書き込む -> 体裁を整える -> リンク属性を付ける`。先にリンク属性を付けると、書式再適用で消える
  - `共通導線` の行は `共通` タブへ寄せる
  - 各タブ内の並び順は `センサーズ -> AI -> アドプロ -> スキルプラス -> ライトプラン -> 書籍 -> その他`
  - `リンクエラー用` の行は `広報` ではなく `その他` タブへ寄せる
  - visible タブでは、連続する同一 `ファネル名` を A列で縦結合する
  - visible タブの罫線は全範囲で統一する
  - old tab の `飛び先URL` は `遷移先リンク` に統合し、`最新（YYYY/MM/DD）` は行単位の `更新日` に正規化した
  - `未作成` の行は master / visible ともに削除した
  - 体裁は `スプレッドシート設計ルール` に合わせて、ヘッダー色、フィルタ、凍結、交互色、列幅、`切り詰める(CLIP)` を再適用した
  - `System/scripts/shortio_api_client.py sync-ads-sheet` で、まず `広告（統合）` の `遷移先 / 更新日` を short.io 実体と照合できる
  - `System/scripts/shortio_api_client.py rebuild-sheet-views` で、`01_全体台帳` から visible の集客媒体タブを再構築できる
  - `--delete-obsolete` 付きで実行済みなので、`00_役割と使い方` を含む旧タブ群は live シートから削除済み
  - `System/scripts/shortio_api_client.py audit-sheet` で台帳品質を監査できる
  - 実行結果として、`広告（統合）` の short.io 行を `379件` チェックし、`373件` の `遷移先 / 更新日` を actual 値で同期した
  - unresolved は `4件` で、`まだない` 2件を除くと、`YhBCLQ` と `metaad-light1` は short.io 実体が見つからない broken 候補と切れた
  - 新しい媒体タブ設計に移した後の監査では、`未作成` を除く残差は `0件` まで解消した
- 完了
  - 役割 / ゴール / 必要変数 / ワークフロー / NG / 正誤判断が fixed
  - current UI の `作成 / 編集 / 統計 / API` が exact に見えている
  - URL管理シートの広告系 4 タブを `広告（統合）` に集約済み
  - `広告（統合）` の `遷移先 / 更新日` を short.io 実体で同期できる
  - broken 候補まで検出できる

#### short.io を 100 点にする完了条件

- 役割を `リンク正本基盤` として説明できる
- 新規作成 / 差し替え / 既存流用を、理由つきで判断できる
- 作成から URL管理シート更新まで、抜けなく再現できる
- 既存リンク差し替えを current UI で exact に完了できる
- 統計画面から、最低限 `どのリンクがどこで押されているか` を読める
- クリック分析の自動取得方針を説明できる
- 実案件を 1 本、判断から記録まで通しても崩れない

### いちばん効く次の順番

1. Lステップを `9.6 -> 9.8〜10` へ上げる
2. UTAGE を `8.8 -> 9.3+` へ上げる
3. Mailchimp を `7.8 -> 9.0+` へ上げる
4. short.io は完了。次は Lステップ / UTAGE / Mailchimp に同じ型を横展開する

## 4層との対応

- 事実・観察・構造理解は `knowledge`
- 勝ち筋や禁止事項に圧縮されたら `rules`
- 実際に出した提案や成果物は本来 `output`

`proactive_output/` は既存コード互換のためここに残っているが、考え方としては `Master/output/` が正本入口。現在の役割は [proactive_output/README.md](/Users/koa800/Desktop/cursor/Master/addness/proactive_output/README.md) に明記した。

## このフォルダに置かないもの

- 甲原固有の人格・価値観
- 汎用化済みの原理
- ルールだけを抜き出した最終版

人格は `前提`、汎用原理は `Skills/`、最終ルールは `Master/rules/` を優先する。
