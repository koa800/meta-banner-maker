# Zapier 構造と作法

最終更新: 2026-03-12

## この文書の役割

- Zapier そのものの一般役割
- アドネス株式会社の販売導線における役割
- current の representative Zap pattern
- 何を見れば正しく relay を読めるか

を固定する。

## ツールそのものの役割

- 複数システム間の trigger と action をつなぐ自動化システム
- event を受け取り、次システムが実行可能な action に変換する

## アドネス株式会社における役割

- Addness では、Zapier は `relay layer` として使う
- 主目的は `UTAGE や他システムで起きた event を Mailchimp tag に変換すること`
- つまり、表の顧客体験を直接作るのではなく、裏側で
  - 誰が
  - どの event を起こし
  - 次にどの Journey や配信に入るべきか
  を正しく受け渡す
- コンテンツそのものを作るシステムではないが、
  - どのコンテンツを次に出すか
  - どの状態の相手にそのコンテンツを見せるか
  を裏で決める接続システム
- つまり Addness では、コンテンツ OS を支える `relay system` として見る

## 8視点での定義

### 役割

- 複数システムの間で、状態と event を受け渡す relay layer

### 入力

- webhook payload
- 一部の Google Sheets row update

### 変換

- `オプトインした`
- `購入した`
- `月額化した`

のような business event を、Mailchimp tag や外部 API 呼び出しに変換する

### 出力

- Mailchimp `Add/Update Subscriber`
- 一部の webhook post
- 一部の Google Sheets add/update

### 接続先

- UTAGE
- Mailchimp
- Google Sheets
- 外部 API

### 制約

- 顧客に見える front 体験は作らない
- relay の誤りは downstream の tag / Journey / 記録をまとめて壊す

### 失敗条件

- 1つの business event に対して tag が曖昧
- webhook payload の key が変わり、email や event が正しく渡らない
- current Zap と legacy Zap の見分けを誤る

### 正誤判断

- 良い
  - 1 event = 1 meaning で tag や relay 先が明確
- 悪い
  - 名前は似ているが、event の意味がぶれてどの Journey を起動するか読めない

## current の主戦場

- 一覧: `https://zapier.com/app/assets/zaps`
- editor: `https://zapier.com/editor/{zap_id}/published`
- create 入口: `https://zapier.com/webintent/create-zap?...`
- create 直後は `https://zapier.com/editor?attempt_id=...` の untitled builder に入る
- current の代表型は `Webhooks by Zapier -> Mailchimp Add/Update Subscriber`

### live 一覧でまず見る場所

- 一覧の主要列は
  - `Name`
  - `Apps`
  - `Location`
  - `Last modified`
  - `Status`
  - `Owner`
  です
- 2026-03-12 時点の visible current には、少なくとも次が並んでいました
  - `AI個別_SMS送信`
  - `AIコンテンツ完全習得Live_購入時`
  - `AICAN_月額_購入時`
  - `みかみの秘密合宿_サンクスメール`
  - `X_AI_3days合宿購入時39SMS`
  - `共通_秘密の部屋_年間プラン購入`
  - `共通_秘密の部屋_月額プラン購入_導線内用`
  - `共通_秘密の部屋_月額プラン購入_OTO用`
  - `X広告_秘密の部屋_オプトイン`
  - `Meta広告_秘密の部屋_オプトイン`
- つまり current 一覧では
  - `Name` で event family を見る
  - `Location` と `Owner` で置き場と責任範囲を見る
  - `Last modified` と `Status` で current / legacy を判断する
  の順で読むと速い

## Addness の運用ルール

- 今後、Addness 株式会社の業務で新しく作る Zapier 資産は、原則 `甲原` フォルダ配下に置く
- 対象は
  - Zap
  - 関連する subfolder
  - 今後増える Addness 専用の relay 資産
- 既存の current Zap は、動いているものを無理に移動しない
- つまり運用方針は
  - 既存 = そのまま読む
  - 新規 = `甲原` に置く
 で固定する
- 置き場所のルールを先に固定する理由は
  - Addness 業務の relay を他用途と混ぜない
  - 後から見た時に `これは Addness 用の Zapier 資産か` を folder で即判定できる
  - 保守や棚卸しのコストを下げる

2026-03-11 時点で live 一覧上は `263 Zap` があり、本文テキストから見える current の主戦場は以下。

- オプトイン relay
- 購入 relay
- 一部の SMS relay

2026-03-12 に live 一覧から追加で見えた current family は次の通り。

- `秘密の部屋` 系
  - `Meta広告_秘密の部屋_オプトイン`
  - `X広告_秘密の部屋_オプトイン`
  - `...年間プラン購入`
  - `...月額プラン購入_導線内用`
  - `...月額プラン購入_OTO用`
- `AIコンテンツ完全習得Live / AICAN` 系
  - `AIコンテンツ完全習得Live_購入時`
  - `AICAN_月額_購入時`
- `アクションマップ` 系
  - `全コース_アクションマップ購入`
  - `生成AIコース_アクションマップ購入`
  - `SNSマーケコース_アクションマップ購入`
  - `広告マーケコース_アクションマップ購入`
- `フリープラン / プロモーション` 系
  - `フリープラン入会時_女性訴求プロモーション`
- `SMS exception` 系
  - `AI個別_SMS送信`
  - `X_AI_3days合宿購入時39SMS`
  - `YT_AI_OTO合宿購入時39SMS`

## representative pattern

### pattern 1: オプトイン relay

- Zap 名
  - `Meta広告_秘密の部屋_オプトイン`
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- meaning
  - UTAGE / front で起きたオプトイン event を、Mailchimp audience + tag に変換する
- representative tag
  - `metaad_himitsu_optin`

#### current 実値で確認できた representative

- `Meta広告_秘密の部屋_オプトイン`
  - step 1
    - app: `Webhooks by Zapier`
    - action: `Catch Hook`
  - step 2
    - app: `Mailchimp`
    - action: `Add/Update Subscriber`
    - audience: `アドネス株式会社`
    - member_status: `subscribed`
    - update_existing: `true`
    - tag: `metaad_himitsu_optin`
    - email mapping: webhook payload の `メールアドレス`
- つまり current のオプトイン relay も
  - webhook で event を受け
  - email を引き
  - audience に optin tag を付ける
  という 2 step 構造
  - その結果、次に Mailchimp の evergreen 教育コンテンツへ入る条件を作る

### pattern 2: 購入 relay

- Zap 名
  - `AIコンテンツ完全習得Live_購入時`
  - `AICAN_月額_購入時`
  - `共通_秘密の部屋_年間プラン購入`
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- meaning
  - 購入 event を、その後の Mailchimp branch 用 tag に変換する
- representative tag
  - `AIkontentuLive_Buy`
  - `AICAN_monthly_buy`
  - `himitsu_yearly_buy`

#### current 実値で確認できた representative

- `AIコンテンツ完全習得Live_購入時`
  - step 1
    - app: `Webhooks by Zapier`
    - action: `Catch Hook`
  - step 2
    - app: `Mailchimp`
    - action: `Add/Update Subscriber`
    - audience: `アドネス株式会社`
    - member_status: `subscribed`
    - update_existing: `true`
    - tag: `AIkontentuLive_Buy`
    - email mapping: webhook payload の `メールアドレス`
- つまり current の購入 relay は
  - front system で起きた購入 event を受ける
  - 購入者の email を引く
  - Mailchimp audience に対して購入 tag を付ける
  という、かなり素直な 2 step 構造
  - その結果、購入後コンテンツやアップセル判定の分岐条件を作る

### pattern 2.5: 商品 family の course-specific purchase relay

- Zap 名
  - `マインドセットコース_アクションマップ購入`
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- meaning
  - 共通商品ではなく、コース別購入 event をコース別購入 tag に変換する
- representative tag
  - `mindset_actionmap_buy`

#### current 実値で確認できた representative

- `マインドセットコース_アクションマップ購入`
  - step 1
    - app: `Webhooks by Zapier`
    - action: `Catch Hook`
  - step 2
    - app: `Mailchimp`
    - action: `Add/Update Subscriber`
    - audience: `アドネス株式会社`
    - member_status: `subscribed`
    - update_existing: `true`
    - tag: `mindset_actionmap_buy`
    - email mapping: webhook payload の `メールアドレス`
- 読み方
  - `全コース_アクションマップ購入` のような共通 relay と、
    `マインドセット / 生成AI / SNSマーケ / 広告マーケ` のような course-specific relay が並立している
  - つまり Addness の Zapier は、`商品購入` だけでなく `どの商品のどの系統か` まで tag で切り分ける relay layer として読む

### pattern 3: コンテンツ切替 relay として読む

- Zap 名の読み方
  - `...オプトイン`
  - `...購入時`
  - `...月額_購入時`
  のように、名前に event が明示されている
- Addness での本質
  - Zapier はコンテンツを直接作らない
  - 代わりに `次にどのコンテンツを出してよい状態か` を downstream system に伝える
- 具体
  - オプトイン relay は
    - `未登録`
    - を
    - `教育開始できる`
    に変える
  - 購入 relay は
    - `見込み客`
    - を
    - `購入後案内を出してよい`
    に変える
  - 月額 relay は
    - `単発購入`
    - を
    - `継続利用者向け案内を出してよい`
    に変える
- つまり、Zapier の正しい読み方は
  - `何の event を受けたか`
  - `どの tag を付けたか`
  - `その tag で次にどのコンテンツが解禁されるか`
  の 3 点で見ること

### pattern 4: historical / exception relay

- Zap 名
  - `AI個別_SMS送信`
- trigger
  - `Google Sheets updated row`
- action
  - `webhook post`
- meaning
  - current の main relay ではなく、シート更新を SMS 送信へ変換する historical / exception pattern
- 読み方
  - Addness の Zapier を理解する時は、これを main と見ない

#### current 実値で確認できた representative

- `AI個別_SMS送信`
  - step 1
    - app: `Google Sheets`
    - action: `Updated Spreadsheet Row`
    - spreadsheet: `AI個別電話番号リスト`
    - worksheet: `RAWDATA`
    - dedupe column: `電話番号`
  - step 2
    - app: `Webhooks by Zapier`
    - action: `POST`
    - destination: `https://www.sms-console.jp/api/`
    - payload: `mobilenumber = COL$C`, `smstext = COL$D`
  - state
    - `is_enabled = false`
- 読み方
  - この系統は `Mailchimp tag relay` ではなく、sheet をトリガーにした業務例外系
  - enabled でも本線とは限らないので、`source = Google Sheets` かつ `destination = external SMS API` の時点で exception と読む

### pattern 5: promotion relay

- Zap 名
  - `フリープラン入会時_女性訴求プロモーション`
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- meaning
  - 通常の購入 tag に加えて、promotion 用の slice tag を重ねる
- representative tag
  - `freeplan_Buy_PR_woman`
  - `freeplan_Buy`

#### current 実値で確認できた representative

- `フリープラン入会時_女性訴求プロモーション`
  - step 1
    - app: `Webhooks by Zapier`
    - action: `Catch Hook`
  - step 2
    - app: `Mailchimp`
    - action: `Add/Update Subscriber`
    - audience: `アドネス株式会社`
    - tags:
      - `freeplan_Buy_PR_woman`
      - `freeplan_Buy`
    - email mapping: webhook payload の `メールアドレス`
- 読み方
  - Addness の promotion relay は、`本体 tag` と `施策切り口 tag` を同時に付けることがある
  - つまり downstream では、
    - 事業や商品で切る
    - 施策や訴求でも切る
    の 2 軸で audience を読めるようにしている

## relay から見た良い / 悪いの判断

### 良い relay

- 1 event に対して 1 meaning で tag が付く
- tag を見れば、次にどのコンテンツを出す前提か読める
- event 名と Zap 名が一致していて、あとから見返しても意味がズレない
- source system と downstream system が明確

### 悪い relay

- 1 Zap で複数の unrelated event を混ぜる
- tag 名だけでは次のコンテンツが読めない
- `購入` なのか `予約` なのか `登録` なのかが名前で区別できない
- relay の結果として、Mailchimp 側でどの Journey に入るか説明できない

## current の読み方

### 一覧から分かること

- Zap 名
- owner / folder 的な置き場
- last modified
- enabled / paused の状態

### editor で分かること

- published 版を開くと、`__NEXT_DATA__` に `zap.current_version.zdl` が入っている
- `zdl.steps` を読むと
  - app
  - type
  - action
  - params
  が機械的に取れる

### helper

- `python3 System/scripts/zapier_editor_snapshot.py <zap_id>`
- current Chrome CDP セッションから editor を開き、`__NEXT_DATA__` の Zap 定義を安全に抜く
- secret っぽい key は `[REDACTED]` に置き換える
- `python3 System/scripts/zapier_login_helper.py`
- current Chrome CDP セッションを再利用し、`System/credentials/zapier.json` の認証情報で
  - assets 一覧へ直接入れるか
  - login 画面で email / password を埋められるか
  を先に確認する
- current 実動作では `ALREADY_LOGGED_IN` で `https://zapier.com/app/assets/zaps` へ入れることを確認済み
- `python3 System/scripts/zapier_assets_snapshot.py --limit 12`
- assets 一覧の visible row を JSON で抜き、
  - `name`
  - `location`
  - `last_modified`
  をまとめて棚卸しできる
- current 実動作では
  - title: `Zaps | Zapier`
  - columns: `Name / Apps / Location / Last modified / Status / Owner`
  - rows: `AI個別_SMS送信` など 12 件
  を JSON 出力できることを確認済み

### create 入口で分かること

- `Create` から入ると、最初は `Untitled Zap / Draft` の builder が開く
- 初期 builder には
  - `Trigger`
  - `Action`
  の 2 step が見え、ここから app と event を選ぶ
- つまり Zapier の新規 relay は
  - 先に event を決める
  - 次に relay 先 action を決める
  の順で組む

## current の判断基準

### current と読むシグナル

- `is_enabled = true`
- updated_at が recent
- Zap 名が current funnel / 商品 / event と一致
- trigger が webhook、action が Mailchimp tag relay
- 同じ命名規則で `オプトイン / 購入 / 月額 / OTO` の family が束で存在する
- 現行 funnel 名や product 名と series で対応している

### legacy / exception と読むシグナル

- paused
- current の main relay pattern から外れる
- SMS や old sheet relay のように、今の front funnel 本線ではない

## 依頼を受けたら最初に確定すべき変数

- 何の business event か
  - オプトイン
  - 購入
  - 月額化
  - 予約
- source system は何か
  - UTAGE
  - Google Sheets
  - 外部 webhook
- relay 先は何か
  - Mailchimp
  - Google Sheets
  - 外部 API
- downstream で何を起こしたいか
  - tag 付与
  - subscriber 更新
  - row 追加
  - webhook post
- email は payload のどの key か
- 付与する tag は何か
- 既存 Zap を流用するのか、新規 Zap を切るのか

## 新規設定の標準手順

1. business event を 1 つに絞る
2. source system を決める
3. downstream で起こしたい action を 1 つに絞る
4. email や event name など必須 key を決める
5. downstream tag / row / payload 名を決める
6. current Zap と意味が重複しないかを見る
7. test payload で relay を確認する
8. downstream 側で
   - tag が付いたか
   - subscriber が更新されたか
   - row が増えたか
   を確認する

## NG

- 1 つの Zap で unrelated な event をまとめる
- tag 名だけ見て意味が曖昧な relay を作る
- email mapping を webhook payload の変更に依存させたまま未確認で進める
- current Zap があるのに、同じ意味の Zap を別名で増やす

## 何ができれば 100 点に近いか

- current Zap を見て
  - 何の event を受けて
  - 何の tag を付け
  - どの downstream system を起動するか
  を迷わず説明できる
- main relay と exception relay を分けて読める
- 新しく relay を足す時に
  - event
  - tag
  - downstream system
  の責務分離を崩さない
- 一覧を見た時に、`これはどの funnel / product family の relay か` を数秒で説明できる
