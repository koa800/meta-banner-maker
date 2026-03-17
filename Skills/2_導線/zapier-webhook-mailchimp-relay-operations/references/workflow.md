# Zapier Webhook -> Mailchimp relay workflow

## current で固定している事実

- 一覧
  - `https://zapier.com/app/assets/zaps`
- editor
  - `https://zapier.com/editor/{zap_id}/published`
- create 入口
  - `https://zapier.com/app/assets/zaps/folders/019cdd75-b612-ec46-7e5b-bd8a9015a667`
  - `Assets > Zaps > 甲原 > Create Zap`
- current の代表 family
  - `Webhooks by Zapier / Catch Hook`
  - `Mailchimp / Add/Update Subscriber`
- `trigger 1 + action 2` の current 複雑パターンは live exact 済み
  - `trigger = Webhooks by Zapier / Catch Hook`
  - `action 1 = Mailchimp / Add/Update Subscriber`
  - `action 2 = Webhooks by Zapier / POST`
  - 逆順の `action 1 = Webhooks by Zapier / POST`, `action 2 = Mailchimp / Add/Update Subscriber` も live exact 済み

## representative pattern

### オプトイン relay

- Zap 名
  - `Meta広告_秘密の部屋_オプトイン`
- step 1
  - `Webhooks by Zapier`
  - `Catch Hook`
- step 2
  - `Mailchimp`
  - `Add/Update Subscriber`
  - audience = `アドネス株式会社`
  - member_status = `subscribed`
  - update_existing = `true`
  - tag = `metaad_himitsu_optin`
  - email = webhook payload の `メールアドレス`

### 購入 relay

- Zap 名
  - `AIコンテンツ完全習得Live_購入時`
- step 1
  - `Webhooks by Zapier`
  - `Catch Hook`
- step 2
  - `Mailchimp`
  - `Add/Update Subscriber`

### family を広げて読む current 例

- `秘密の部屋`
  - `Meta広告_秘密の部屋_オプトイン`
  - tag = `metaad_himitsu_optin`
- `AIコンテンツ完全習得Live / AICAN`
  - `AIコンテンツ完全習得Live_購入時`
  - `AICAN_月額_購入時`
- `アクションマップ`
  - `マインドセットコース_アクションマップ購入`
  - tag = `mindset_actionmap_buy`
- `フリープラン / プロモーション`
  - `フリープラン入会時_女性訴求プロモーション`
  - main tag と promotion slice tag を同時に付ける
- `SMS例外`
  - `Google Sheets updated row -> external SMS API` の historical family

## 読み方

- Zapier は Addness では `relay layer`
- 主目的は、front system の event を Mailchimp tag に変換すること
- relay の誤りは downstream の Journey 条件や配信条件をまとめて壊す

## current safety signal

- 新規 Addness 資産は原則 `甲原` folder 配下
- `update_existing = true`
- email は webhook payload の email-like key から引く
- Zap 名だけで family と event の意味が読める

## 新規 relay の exact 順

1. `Create`
2. `Assets > Zaps > 甲原`
3. `Create Zap`
4. `Untitled Zap / Draft`
5. `Trigger`
6. `Webhooks by Zapier`
7. `Catch Hook`
8. `Action`
9. `Mailchimp`
10. `Add/Update Subscriber`
11. `Audience*`
12. `Subscriber Email*`
13. `Tag(s)`
14. `Status`
15. `Update Existing`
16. `Name`

つまり、Zapier は step を埋める前に
- 何 event を relay するか
- どの tag に変換するか
- どの email key を使うか
を先に切る。

current の Addness では、`Zap details > Folder` を後から変えるより、最初から `甲原` folder page で `Create Zap` する方が exact。2026-03-17 live probe では、この入口で assets row の `Location = 甲原` を確認済み。

### create builder で実際に見るラベル

- 上部
  - `Untitled Zap`
  - `Draft`
  - `Publish`
- step 共通
  - `Trigger`
  - `Action`
  - `Test`
  - `Continue`
- trigger 側
  - `Choose app & event`
  - `Webhooks by Zapier`
  - `Catch Hook`
  - `Test trigger`
- action 側
  - `Choose app & event`
  - `Mailchimp`
  - `Add/Update Subscriber`
  - `Choose account`
  - `Set up action`
  - `Test step`
- 右側詳細
  - `Zap details`
  - `Folder`
  - `Timezone`

### trigger / action の exact smoke 順

1. `Trigger`
2. `Webhooks by Zapier`
3. `Catch Hook`
4. `Continue`
5. `Test trigger`
6. `Action`
7. `Mailchimp`
8. `Add/Update Subscriber`
9. `Choose account`
10. `Set up action`
11. `Audience*`
12. `Subscriber Email*`
13. `Tag(s)`
14. `Test step`

current の Addness では、`Test trigger` と `Test step` を飛ばして `Publish` しない。

## `Test trigger` の sample で止まる条件

- sample payload の `メールアドレス` 系 key が intended な field か言えない
- 前回の別 event の sample を掴んでいる可能性がある
- sample を見ても `何の event か` を 1 文で言えない

このどれかなら `Publish` へ進まず止まる。

## 30秒レビューの順番

1. `Name`
2. `Apps`
3. `Location`
4. `Status`
5. step 1 が `Webhooks by Zapier / Catch Hook` か
6. step 2 が `Mailchimp / Add/Update Subscriber` か
7. `Audience*`
8. `Subscriber Email*`
9. `Tag(s)`
10. その tag が downstream で何を起動するか

## editor に入れない時の fallback順

1. `Assets > Zaps`
2. `Name`
3. `Apps`
4. `Location`
5. `Status`
6. `Folder`
7. 既知の family と照合
8. editor は最後に再試行

つまり、`published editor` が閉じている時でも、まず一覧で `何系の relay か` を切る。step の exact 値が必要な変更だけを stop 条件にする。

## relay を読む最小チェック

1. この Zap は何 event を relay しているか
2. downstream の Mailchimp audience はどれか
3. 付与される tag は何か
4. その tag 名は business event と一致しているか
5. duplicate や例外 relay になっていないか

## `relay 不要` を先に切る時の問い

1. Lステップ 単体で完結できないか
2. UTAGE の `購入後アクション` や `バンドルコース` だけで閉じないか
3. Mailchimp 側の既存 tag / saved segment だけで足りないか

この 3 つが `yes` なら、まず Zapier を増やさない。

## representative pattern を読む時の問い

- この relay は何 event を受けているか
- その event を downstream のどの state に変えているか
- `Tag(s)` を見た時に business event が 1 文で言えるか
- なぜ Mailchimp に渡しているのか
- 同じ family の既存 Zap と何が違うのか

## 10秒判断

- 既存 relay 修正
  - 同じ event meaning を持つ current Zap がすでにある
  - 変えるのが `Tag(s)` や `Subscriber Email*` の参照先など局所差分
- 新規 relay
  - event meaning 自体が新しい
  - 既存 Zap を直すと別 funnel の downstream を壊す
- relay 不要
  - front system だけで state と downstream を閉じられる

この 10 秒判断が言えない時は、UI を触る前に stop する。

## 保存前の最小チェック

- `Trigger`
  - `Webhooks by Zapier`
  - `Catch Hook`
  になっているか
- `Action`
  - `Mailchimp`
  - `Add/Update Subscriber`
  になっているか
- `Audience*`
  が意図どおりか
- `Subscriber Email*`
  が webhook payload の正しい key を指しているか
- `Tag(s)`
  が downstream の Journey / Campaign 条件と 1 meaning で対応しているか
- この Zap を
  - 新規作成すべきか
  - 既存変更すべきか
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
- relay を増やしたことで、front system 側の責務が逆に分散していないか

## Publish 前の最終確認順

1. `Name`
2. `Folder`
3. `Trigger`
4. `Action`
5. `Audience*`
6. `Subscriber Email*`
7. `Tag(s)`
8. `Test trigger` の結果
9. `Test step` の結果
10. downstream の Mailchimp で、この tag が何を起動するか

`Publish` は最後に押す。`Name / Folder / Test` が曖昧なまま publish しない。

## 完成条件

次を説明できた時だけ完成扱いにする。
- この Zap が何 event を受け取るか
- downstream で何 state を作るか
- `Audience*`
- `Subscriber Email*`
- `Tag(s)`
をなぜそうしたか
- 既存変更ではなく新規作成にした理由、またはその逆
- downstream の Mailchimp 側でどの Journey / Campaign 条件に効くか

## current で迷いやすい差分

- `Create` を開いただけでも `Untitled Zap / Draft` が残ることがある
- `Folder` は step 設定ではなく `Zap details` 側
- `Mailchimp / Add/Update Subscriber` の configure で `Tag(s)` まで入れないと relay の意味が読めない
- `Google Sheets -> Webhooks POST` family は current main relay ではなく例外 family
- visible 一覧だけでは分からない時も、まず `Name / Apps / Location / Status` で family を切る
- `2つ目の action` は、既存 action の `Choose an event` を押し直しても開かない
- current では `Add a step` の visible text を探すより、`aria-label=\"Add step\"` の button を使う方が exact

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

## 危険な新規 relay シグナル

- `Tag(s)` の意味が 1 文で言えない
- 既存 Zap と event meaning が重複して見える
- downstream の `Journey / Campaign` 側で、その tag の役割が読めない
- `Mailchimp / Add/Update Subscriber` 以外の family を使いたくなっている
- `Paths / Filter / Formatter / Code` を足したくなっている

この場合は、まず `relay 不要` か `既存修正` を再判定する。新規作成は最後に回す。

## ここで止めて確認する条件

- webhook payload の key 名が current 実装と違って見える
- 既存 Zap を変えると複数の current funnel に波及しそう
- 付けたい tag が current Mailchimp naming に乗っていない
- `Webhooks by Zapier -> Mailchimp Add/Update Subscriber` 以外の family を新規で使いたい
- relay 先が Mailchimp ではなく外部 API や Google Sheets で、本番影響が読みにくい
- event の意味が 1 つに絞れず、Zap 名だけで説明できない

## cleanup の原則

- exploratory に builder を開いただけなら `Untitled Zap / Draft` を残さない
- 削除前に
  - `Folder`
  - `Status`
  - `Last modified`
  を見て、current published relay ではないことを確認する

### current の exact draft cleanup

1. builder 上部の `Untitled Zap / Draft`
2. `...` または title menu
3. `Delete`
4. dialog `Delete Zap?`
5. `Delete Zap`

`Publish` を押していない draft だけを消す。published relay でこの導線を使わない。
