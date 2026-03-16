# Zapier 構造と作法

最終更新: 2026-03-12

## 情報ラベル

- 所有元: internal
- 開示レベル: task-limited
- 承認必須: conditional
- 共有先: 僕 / 上司 / 並列 / 直下

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

## live 確認済みの範囲

- 一覧の読み方
  - `Name / Apps / Location / Last modified / Status / Owner`
- editor 読解
  - representative な `Webhooks by Zapier -> Mailchimp Add/Update Subscriber`
- draft cleanup
  - `Create Zap -> assets 一覧 row action Delete -> Delete`
  - `python3 System/scripts/zapier_cleanup_untitled.py`
- current family
  - `秘密の部屋`
  - `AIコンテンツ完全習得Live / AICAN`
  - `アクションマップ`
  - `フリープラン / プロモーション`
  - `SMS exception`
- exact に読めているもの
  - `Create Zap` の入口
  - `Untitled Zap / Draft` の cleanup 観点
  - `Trigger -> Action` の最小 2 step 構造
  - `Action > Mailchimp > Add/Update Subscriber` で `Test` stage に進めること

## まだ live create / rollback を厚くすべき範囲

- `Catch Hook -> Mailchimp Add/Update Subscriber -> Test` は exploratory で 1 本通った
- 残差は、同じ family の本数と `trigger 1 + action 2` の最小複雑 pattern を live で積むこと
- `既存 relay 修正` と `新規 relay` の rollback 手順を、current UI でさらに exact 化すること

## current の主戦場

- 一覧: `https://zapier.com/app/assets/zaps`
- editor: `https://zapier.com/editor/{zap_id}/published`
- create 入口: `https://zapier.com/webintent/create-zap?...`
- create 直後は `https://zapier.com/editor?attempt_id=...` の untitled builder に入る
- current の代表型は `Webhooks by Zapier -> Mailchimp Add/Update Subscriber`
- exploratory cleanup helper: `python3 System/scripts/zapier_cleanup_untitled.py`

### 入口選択の exact な問い

Zapier で迷いやすいのは、`とりあえず Zap を作る` に入ることです。最初に次を切る。

- 今やりたいのは `既存 relay を読む / 壊さず直す` か
  - なら `一覧 > Name / Apps / Location / Status` から current を特定
- 今やりたいのは `新規 relay を作る` か
  - なら `Create Zap`
- 今やりたいのは `relay が本当に必要か` の判断か
  - なら `UTAGE / Lステップ / Mailchimp 側で完結しないか` を先に見る

つまり Zapier では、最初の 1 手は `作るか読むか` ではなく、

- relay を新設すべきか
- 既存 relay を読めば足りるか
- そもそも relay layer を使わず他ツールで閉じるべきか

を先に切る。

### 10秒判断

- `既存 relay 修正`
  - business event の意味が同じ
  - 変えたいのが audience、email mapping、tag の一部
- `新規 relay`
  - business event の意味が違う
  - downstream の Journey / Campaign の役割が変わる
- `relay 不要`
  - UTAGE、Lステップ、Mailchimp 側だけで目的を果たせる

この 10 秒判断が言えない時は、`Create Zap` を押さない。

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
- `サンクスメール relay` 系
  - `みかみの秘密合宿_サンクスメール`

2026-03-16 に visible current 25 本を再確認したところ、step family は次の分布でした。

- `Webhooks by Zapier -> Mailchimp Add/Update Subscriber`
  - 21 本
  - current の主 family
  - visible version は
    - `WebHookCLIAPI@1.1.1 -> MailchimpCLIAPI@1.15.1`: 20 本
    - `WebHookCLIAPI@1.0.29 -> MailchimpCLIAPI@1.15.1`: 1 本
- `Google Sheets Updated Spreadsheet Row -> Webhooks by Zapier POST`
  - 3 本
  - すべて SMS 例外 relay
- old family
  - `WebHookCLIAPI@1.0.29 -> MailchimpCLIAPI@1.15.1`
  - 1 本
  - `フリープラン入会時_女性訴求プロモーション`

つまり Addness の current Zapier は、`webhook で business event を受けて Mailchimp tag に変換する` のが圧倒的な主戦場で、`Google Sheets -> webhook post` は SMS 例外 family、old webhook version は legacy 読みの候補と見てよい。

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

## current を読む最短順

Zapier の current 一覧や editor を見た時は、まず次の順で読む。

1. `Name`
2. `Apps`
3. `Location`
4. `Status`
5. step 1 の app / event
6. step 2 の app / event
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. その tag が downstream の Mailchimp で何を起動するか

これで、
- relay family
- 何の event か
- Mailchimp 側の意味
を 30 秒で切る。

## 新規 relay を作る時の exact 順

1. `Create`
2. `Untitled Zap / Draft`
3. `Trigger`
4. `Webhooks by Zapier`
5. `Catch Hook`
6. `Action`
7. `Mailchimp`
8. `Add/Update Subscriber`
9. `Audience*`
10. `Subscriber Email*`
11. `Tag(s)`
12. `Status`
13. `Update Existing`
14. `Name`
15. `Folder = 甲原`

つまり Addness の current では、step を埋める前に
- 何 event を relay するか
- どの tag に変換するか
- どの email key を使うか
を先に切る。

## 新規作成と既存変更の判断

- 新規作成
  - event の意味が既存 Zap と重ならない
  - 新しい tag を切る理由が説明できる
  - `1 event = 1 meaning` を保てる
- 既存変更
  - その Zap が current 本線と分かっている
  - 変えるのが
    - `Tag(s)`
    - `Audience*`
    - `Subscriber Email*`
    - downstream の意味
    のどこか説明できる
  - 変更後も downstream の意味が変わらない
- 迷ったら新規作成も既存変更も止めて確認する

## draft cleanup の原則

- exploratory に builder を開いた時は `Untitled Zap / Draft` を残さない
- 削除前に、必ず
  - `Folder`
  - `Status`
  - `Last modified`
  を見て、current published relay ではないことを確認する
- Addness の新規資産は `甲原` folder を正にするが、既存 current relay は無理に移動しない

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

### pattern 6: サンクスメール起点の購入 relay

- Zap 名
  - `みかみの秘密合宿_サンクスメール`
- trigger
  - `Webhooks by Zapier`
  - `Catch Hook`
- action
  - `Mailchimp`
  - `Add/Update Subscriber`
- meaning
  - 購入後サンクスメールの送信条件を、Mailchimp 側の購入 tag に変換する
- representative tag
  - `mikami_gassyuku_20260307_buy`

#### current 実値で確認できた representative

- `みかみの秘密合宿_サンクスメール`
  - step 1
    - app: `Webhooks by Zapier`
    - action: `Catch Hook`
  - step 2
    - app: `Mailchimp`
    - action: `Add/Update Subscriber`
    - audience: `アドネス株式会社`
    - member_status: `subscribed`
    - update_existing: `true`
    - tag: `mikami_gassyuku_20260307_buy`
    - email mapping: webhook payload の `メールアドレス`
- 読み方
  - Addness の relay は `購入直後の教育・案内を出してよい状態を作る` ところまで持つ
  - つまり `買った` を `購入後コンテンツを出せる` に変える relay としても読む

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
- ただし 2026-03-13 の current では、editor URL に直接入っても `access_issue=true` になることがあった
- その場合は
  - `python3 System/scripts/zapier_login_helper.py`
  - `python3 System/scripts/zapier_assets_snapshot.py --limit 12`
  を先に使い、visible row と `edit_path` を正本にする
- editor が閉じている時は、`access issue` 自体を current 制約として扱い、一覧と family から relay を読む
- `python3 System/scripts/zapier_login_helper.py`
- current Chrome CDP セッションを再利用し、`System/credentials/zapier.json` の認証情報で
  - assets 一覧へ直接入れるか
  - login 画面で email / password を埋められるか
  を先に確認する
- current 実動作では `ALREADY_LOGGED_IN` で `https://zapier.com/app/assets/zaps` へ入れることを確認済み
- `python3 System/scripts/zapier_assets_snapshot.py --limit 12`
- assets 一覧の visible row を JSON で抜き、
  - `name`
  - `zap_id`
  - `edit_path`
  - `location`
  - `last_modified`
  をまとめて棚卸しできる
- current 実動作では
  - title: `Zaps | Zapier`
  - columns: `Name / Apps / Location / Last modified / Status / Owner`
  - rows: `AI個別_SMS送信` など 20 件
  を JSON 出力できることを確認済み

### create 入口で分かること

- `Create` から入ると、最初は `Untitled Zap / Draft` の builder が開く
- 初期 builder には
  - `Trigger`
  - `Action`
  の 2 step が見え、ここから app と event を選ぶ
- create 入口の URL は
  - `https://zapier.com/webintent/create-zap?useCase=from-scratch`
- この URL を開いた直後の current 状態は
  - title: `New Zap | Zapier`
  - header: `Untitled Zap`
  - status: `Draft`
  - editor 内の `zap.id`: `sandbox`
- 重要
- 2026-03-16 live では、`Create Zap` を開いただけでは assets 一覧に `Untitled Zap` は出なかった
- つまり current では、draft が persisted する前に `trigger` 選択などもう 1 段階進む可能性が高い
- `builder を開いた = assets に draft が残る` と決め打ちしない
- exploratory 後は `builder 側の Untitled Zap / Draft 表示` と `assets 一覧検索結果` を両方見る
- 2026-03-16 live では
  - `Trigger > Select the event that starts your Zap`
  - `Search apps -> Webhooks`
  - `Trigger event * -> Catch Hook`
  まで選ぶと、assets 一覧の `Untitled Zap` 件数が `2 -> 3` に増えた
- つまり current では、`draft persisted` の境目は `Create Zap` 直後ではなく、少なくとも `app + trigger event` 選択後と読む
- 右上の `Zap details` を開くと、少なくとも
  - `Folder`
  - current value: `Home`
  - `Timezone`
  - `Create a template`
  が見える
- つまり `folder` は step 設定ではなく、`Zap details` 側の管理項目として扱う
- つまり create 入口を開いた時点では、published relay ができたのではなく、`sandbox draft builder が始まった状態` と読む
- つまり Zapier の新規 relay は
  - 先に event を決める
  - 次に relay 先 action を決める
  の順で組む
- 一方で `published editor` が account 権限や session 文脈で閉じる時は、無理に editor に固執しない
- current の exact 作業は
  1. `assets 一覧で row が visible`
  2. `edit_path` が取れる
  3. editor が `access_issue=false`
  の 3 条件がそろった時だけ editor 直読みに進む

#### current の exact create 導線

- trigger 側
  - `Trigger`
  - `Select the event that starts your Zap`
  - app picker の current major category
    - `Apps`
    - `AI`
    - `Flow controls`
    - `Utilities`
    - `Products`
    - `Custom`
  - app search input
    - `Search 7,000+ apps and tools...`
  - `Webhooks by Zapier` を選ぶと
    - `App *`
    - `Webhooks by Zapier`
    - `Trigger event *`
    - `Choose an event`
    が出る
  - `Choose an event` を開くと current では少なくとも
    - `Catch Hook`
    - `Catch Raw Hook`
    - `Retrieve Poll`
    が出る
  - `Catch Hook` を選ぶと
    - `Setup`
    - `Configure`
    - `Test`
    - `Continue`
    が出る

- action 側
  - `Action`
  - `Select the event for your Zap to run`
  - `Mailchimp` を選ぶと
    - `App *`
    - `Mailchimp`
    - `Action event *`
    - `Choose an event`
    - `Account *`
    - `Select an account`
    が出る
  - `Choose an event` を開くと current では少なくとも
    - `Add/Update Subscriber`
    - `Create Tag`
    - `Create Campaign`
    - `Send Campaign`
    - `Add Subscriber to Tag`
    - `Remove Subscriber from Tag`
    - `Find a Subscriber`
    が出る

- 読み方
  - Addness の current relay は、ここで
    - trigger に `Webhooks by Zapier / Catch Hook`
    - action に `Mailchimp / Add/Update Subscriber`
    を置くのが主戦場
  - つまり create builder でも、まずこの current 主戦場に寄せて考える

#### current の exact 編集導線

- title / menu
  - 左上の `Untitled Zap / Draft` ボタンを押す
  - current menu は
    - `Rename`
    - `Duplicate`
    - `Transfer data`
    - `Create template`
    - `Export PNG`
    - `Delete`
- rename
  - `Rename`
  - title が text input に変わる
  - 新しい名前を入れて `Enter`
  - そのまま autosave で assets 一覧に反映される
- folder move
  - 右側 `Zap details`
  - `Folder`
  - current value 例: `Home`
  - folder picker で
    - `Home`
    - `【みた】`
    - `てるや`
    - `ゆうじ`
    - `AICAN`
    - `センサーズFB→メールチンプ`
    - `kishi`
    - `QC（三上大）`
    - `SPS`
    - `【ライトプラン】_宮代`
    - `アクションマップ_森本作成`
    - `甲原`
    - `\"みかみ\"の秘密の部屋_森本作成`
    - `サンキューメール移行`
    - `【マーケ部_数値管理】`
    - `高見澤`
    が出る
  - `甲原` を押すと autosave で assets 一覧の `Location` に即反映される
- delete
  - 左上の title menu
  - `Delete`
  - confirm dialog
    - title: `Delete Zap?`
    - body: `This Zap will move to the trash and be recoverable for 30 days before being permanently deleted.`
    - buttons:
      - `Cancel`
      - `Delete Zap`
  - `Delete Zap` 後は assets 一覧、または選択していた folder 一覧へ戻る

#### assets 一覧からの exact cleanup

- route:
  - `https://zapier.com/app/assets/zaps`
- exploratory に `Create Zap` を開いた後、draft が persisted している時だけ assets 一覧 row action cleanup を使う
- current の exact cleanup は assets 一覧 row action からも行える
  - row menu trigger:
    - `Zap actions`
  - visible menu:
    - `Rename`
    - `View history`
    - `Duplicate`
    - `Change owner`
    - `Move to folder`
    - `Delete`
  - cleanup:
    - `Delete`
    - confirm `Delete`
- 2026-03-16 live では、この導線で exploratory `Untitled Zap` を削除し、一覧検索結果が `0件` になるところまで確認した
- 同日の probe では、`Create Zap` を開いただけでは assets 一覧の `Untitled Zap` 件数は増えなかった
- 同日の live では、`Webhooks by Zapier -> Catch Hook` を選んだ draft を cleanup し、`Untitled Zap` 残数が `2` に戻るところまで確認した
- 同日の probe で、さらに `Action > Mailchimp > Add/Update Subscriber` まで選び、cleanup 後に `Untitled Zap` 残数が `0件` に戻るところまで確認した
- つまり builder 側で消しにくい時は、assets 一覧 row action cleanup を current の安全 fallback として使える

#### current の exact Add/Update Subscriber 設定面

- `Mailchimp`
- `Add/Update Subscriber`
- `Account *`
  - `Select an account`
  - 例:
    - `Mailchimp アドネス株式会社 #4`
    - `Mailchimp アドネス株式会社 #2`
    - `Mailchimp アドネス株式会社 #3`
    - `Mailchimp zent`
    - `+ Connect a new account`
  - current で最も使われているのは `Mailchimp アドネス株式会社 #4`
    - `Used in 181 Zaps`
- account 選択後の field
  - `Continue` を押して `Configure` に進む
  - `Audience*`
  - `Subscriber Email*`
  - `New Email`
  - `Status*`
  - `Double Opt-In`
  - `Update Existing`
  - `Replace Groups`
  - `Groups`
  - `Language Code`
  - `Tag(s)`
- required field が埋まる前は
  - `To continue, finish required fields`
  が出る
- `Publish`
  - field 未入力の時点では disabled
  - 右側 `Status` を開くと
    - `Please test this step`
    - `Please set up the required fields`
    が出る
  - つまり Addness の current relay 作成では
    - trigger test
    - action 必須 field 入力
    を終える前に publish しない

### bulk family を一気に見る helper

- `python3 System/scripts/zapier_family_snapshot.py --limit 25`
- visible current の row を開いて
  - `signature`
  - `件数`
  - `主要 param key`
  を先に掴む
- 使いどころ
  - `今の主戦場が何系か`
  - `例外 family がどれだけあるか`
  を editor を 1 本ずつ開く前に判断したい時

## current の判断基準

### current と読むシグナル

- `is_enabled = true`
- updated_at が recent
- Zap 名が current funnel / 商品 / event と一致
- `Location = 甲原` なら、新規運用ルールに沿った Addness 専用 relay 候補として優先して読む
- trigger が webhook、action が Mailchimp tag relay
- 同じ命名規則で `オプトイン / 購入 / 月額 / OTO` の family が束で存在する
- 現行 funnel 名や product 名と series で対応している
- step family が
  - `Webhooks by Zapier / Catch Hook`
  - `Mailchimp / Add/Update Subscriber`
  の 2 step なら current 本線候補として先に疑う

### legacy / exception と読むシグナル

- paused
- `Draft`
- current の main relay pattern から外れる
- SMS や old sheet relay のように、今の front funnel 本線ではない
- `Location` が Addness 用 folder から外れ、かつ命名も current family とつながらない

### draft と読むシグナル

- `Untitled Zap`
- `Draft`
- step が 1 つだけで止まっている
- `Publish` が disabled
- `Please test this step`
- `Please set up the required fields`
- `Folder = 甲原` だけ先に置いた未完成 relay

つまり current の新規作成では、
- まず `Folder = 甲原`
- その後 `Trigger / Action / 必須 field`
- 最後に `Publish`
の順で見る

途中状態を current relay と混同しない。

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

## 実装前の最小チェック

- この relay が起動した後、Mailchimp 側で何を起こしたいかを 1 文で言えるか
- tag 名が英語で 1 meaning になっているか
- email mapping の key が payload に実在するか
- 既存 Zap 変更と新規 Zap 作成のどちらかを説明できるか
- relay 作成後、どの Journey / Campaign 条件に効くかを説明できるか

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

## representative pattern を読む時の問い

- この relay は `オプトイン / 購入 / promotion / 例外` のどれか
- source system は何か
- downstream で何を起こしたいのか
- `Audience*` と `Tag(s)` の組み合わせは、その目的に対して自然か
- `Journey` を起動したいのか、`Campaign` の対象条件を作りたいのか
- 既存 Zap の変更で済むのか、新規作成に切るべきか

## 30秒レビューの順番

1. 一覧で `Name`
2. `Apps`
3. `Location`
4. `Status`
5. editor で step 1 が `Webhooks by Zapier / Catch Hook` か
6. step 2 が `Mailchimp / Add/Update Subscriber` か
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. その tag が downstream で何を起動するか

## 保存前の最小チェック

- step 1 が
  - `Webhooks by Zapier`
  - `Catch Hook`
  か
- step 2 が
  - `Mailchimp`
  - `Add/Update Subscriber`
  か
- `Audience*`
  が意図どおりか
- `Subscriber Email*`
  が webhook payload の正しい key を指しているか
- `Tag(s)`
  が downstream の Journey / Campaign 条件と 1 meaning で対応しているか
- この Zap を
  - 新規作成するのか
  - 既存変更するのか
  を 1 文で説明できるか

## 保存後の最小チェック

- 一覧で
  - `Name`
  - `Apps`
  - `Location`
  - `Status`
  が意図どおりか
- `Folder`
  が `甲原` か
- `Name` を見て
  - funnel / product family
  - event
  - relay 先の意味
  が読めるか
- downstream の Mailchimp 側で
  - tag が current naming に乗っているか
  - その tag を条件にした導線が説明できるか

## relay 作成後の最終確認順

1. 一覧へ戻る
2. `Name`
3. `Apps`
4. `Location`
5. `Status`
6. editor を開き直す
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. `Update Existing`
11. downstream の Mailchimp 側で、その tag が何を起動するか

### 新規作成と既存変更の exact チェック

- 新規作成を選ぶ時
  - event の意味が既存 Zap と重ならない
  - 置き場所を `甲原` フォルダに寄せられる
  - relay の責務を 1 event = 1 meaning に保てる
- 既存変更を選ぶ時
  - その Zap が current 本線だと分かっている
  - 変えるのが `tag / audience / payload mapping / downstream action` のどこか説明できる
  - 変更後に downstream の意味が変わらない
- 迷ったら
  - まず既存 Zap の `Name / Apps / Location / Last modified / Status` を見る
  - 次に editor で step を開いて
    - trigger app
    - trigger event
    - email mapping
    - tag
    - audience
    を確認する
  - それでも event の意味が 1 つに絞れないなら、新規も既存変更も止めて確認する

## ここで止めて確認する条件

- webhook payload の key 名が current 実装と違って見える
- 既存 Zap を変えると複数の current funnel に波及しそう
- 付けたい tag が current Mailchimp naming に乗っていない
- `Webhooks by Zapier -> Mailchimp Add/Update Subscriber` 以外の family を新規で使いたい
- relay 先が Mailchimp ではなく外部 API や Google Sheets で、本番影響が読みにくい
- event の意味が 1 つに絞れず、Zap 名だけで説明できない

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
