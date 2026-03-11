# Zapier 構造と作法

最終更新: 2026-03-11

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

2026-03-11 時点で live 一覧上は `263 Zap` があり、本文テキストから見える current の主戦場は以下。

- オプトイン relay
- 購入 relay
- 一部の SMS relay

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

### pattern 3: historical / exception relay

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
