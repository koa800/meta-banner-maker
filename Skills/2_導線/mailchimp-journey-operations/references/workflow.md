# Mailchimp Journey exact メモ

## current でよく使う route

- Automations 一覧: `/customer-journeys/`
- create: `/customer-journey/create-new-journey/`
- builder: `/customer-journey/builder?id={journey_id}`
- trigger modal: `/customer-journey/builder?id={journey_id}&stepModal=trigger`
- report: `/customer-journey/report?id={journey_id}`

## current login / verify

- `login.mailchimp.com`
- `unifiedLoginPost`
- `login/verify`
- 2段階認証は current では
  - `Send code via SMS`
  - LINE の `Mailchimp認証` グループでコード確認
    - current では group name が空で返ることがある
    - helper は `Mailchimp認証` という表示名だけでなく、known `group_id = Ce2900a5b8c1efb939b3778262f1a9808` も優先する
  - verify 画面へ入力
  の順
- 補助取得が必要な時は `python3 System/scripts/mailchimp_tfa_code_helper.py --wait-seconds 90`

## create の current UI

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`

`Build from scratch` は、trigger を選び始めた時点で draft flow を作る。live テストでは、必要な確認が終わったら一覧へ戻って削除する。

## current の作成順をさらに exact にすると

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`
7. `Tag added`
8. `Set a tag`
9. 必要なら `Filter who can enter`
10. `Save Trigger`
11. builder 上で `+`
12. `Send email`
13. `Email name`
14. `Subject line`
15. 本文作成
16. `Save and close flow`

つまり current の Journey は、本文を書く前に
- `誰が入るか`
- `何をきっかけに入るか`
- `絞り込むか`
を先に固定する。

## Journey state を汚さない rule

- `trigger` は入口条件
- `Filter who can enter` は入口後の絞り込み
- `saved segment` は Campaign 側の発想として扱い、Journey 設計へ持ち込まない
- 新規 tag は
  - event meaning
  - downstream で何を起動するか
  が 1 文で言える時だけ作る

## draft cleanup

exploratory な draft を作っただけなら、一覧へ戻って次で削除する。
- `Actions`
- `Delete`
- `Delete flow`

保存していないつもりでも draft は残る前提で扱う。

## `Tag added`

trigger picker で current に見える主なラベル。
- `Tag added`
- `Set a tag`
- `Filter who can enter`
- `Save Trigger`

trigger を選び始めた時点で draft flow が作られるので、探索だけでも cleanup 前提で扱う。

## builder 上部の current ラベル

- `Send Test Emails`
- `View Report`
- `Pause & Edit`
- `Save and close flow`

builder 右側は `Data / Settings` の切り替えで見る。

## email step で実際に見るラベル

- `Email name`
- `Subject line`
- `Preview text`
- `From name`
- `From email address`
- `Reply to email address`
- `Send Test Emails`
- `Save and close flow`

## 本文と CTA の exact チェック

本文を作る時は、次の順で見る。

1. `Email name`
2. `Subject line`
3. 冒頭 3 行
4. main CTA の文言
5. main CTA の hyperlink
6. `short.io`
7. final destination

Journey は 1 通単体より前後の文脈が重要なので、
- 前の step で何を理解させたか
- この step で何を変えたいか
- 次の step か CTA で何をさせたいか
を 1 本で確認する。

## email step の exact smoke 順

1. `Email name`
2. `Subject line`
3. `Preview text`
4. `From name`
5. `From email address`
6. `Reply to email address`
7. 冒頭 3 行
8. main CTA の文言
9. actual hyperlink
10. `short.io`
11. final destination
12. `Send Test Emails`
13. `Save and close flow`

## current 判定

最低でも次を見る。
- journey status = `sending`
- step status = `active`
- `queue_count > 0`
- `last_started_at` だけで current 判定しない

## CTA rule

- 今後こちらで新規に作る main CTA は `short.io`
- 表示文字列ではなく hyperlink の実URLを click で確認する

## runtime 補助

- `python3 System/scripts/mailchimp_journey_snapshot.py`
  - current builder / step / queue の snapshot を読む時の補助に使う
  - UI 表示だけで current / legacy を切らず、`queue_count` や step 状態も合わせて見る

### exact command

- current matrix:
  - `python3 System/scripts/mailchimp_journey_snapshot.py --list-current --count 20`
- journey 名検索:
  - `python3 System/scripts/mailchimp_journey_snapshot.py --query "<journey_name_substring>"`
- journey id 指定:
  - `python3 System/scripts/mailchimp_journey_snapshot.py --journey-id <journey_id>`

## representative report

- `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
  - `Days active = 147`
  - `Total started = 32,167`
  - `Total in progress = 4,596`
  - `Total completed = 27,567`
  - `Open rate = 17.4%`
  - `Click rate = 0.04%`

## 30秒レビューの順番

1. `Automations`
2. 対象 `Journey` 名
3. `Audience`
4. `trigger`
5. `Filter who can enter`
6. current queue がある step
7. main CTA
8. 実 hyperlink
9. `View Report`
10. cleanup の要否

## 保存前後の exact チェック

### 保存前

- `Journey` にする理由を 1 文で言える
- `Audience` を先に切れている
- `Tag added` と `Filter who can enter` の役割が混ざっていない
- この 1 通の役割が
  - 教育
  - 直オファー
  - 横展開
  - 締切ブースト
  のどれか 1 つに寄っている
- main CTA を `short.io` にする理由を説明できる

### 保存後

- `Send Test Emails` で本文の表示と actual hyperlink を確認する
- `View Report` と `mailchimp_journey_snapshot.py` の両方で current 判定を確認する
- `short.io` を使う時は final destination まで押して確認する
- exploratory draft は一覧へ戻って `Actions -> Delete -> Delete flow` まで戻す

## current の draft cleanup

1. 一覧へ戻る
2. row の `Actions`
3. `Delete`
4. dialog `Delete flow`

`Build from scratch` を開いて trigger を触っただけでも draft は残る前提で、exploratory な flow は同セッションで消す。

## 完成条件

次を全部満たした時だけ完成扱いにする。
- `Journey` にする理由を 1 文で言える
- `Audience`
- `trigger`
- `Filter who can enter`
- `email step`
の役割が混ざっていない
- main CTA の `表示文言 / actual hyperlink / final destination` を分けて確認している
- `Send Test Emails` と `View Report` のどちらを何のために使うか言える
- exploratory draft を残していない

## current で迷いやすい差分

- `Build from scratch` を開いて trigger を選び始めた時点で draft ができる
- `Tag added` と `Filter who can enter` の役割を混同しやすい
  - 前者は入口条件
  - 後者は入口後の絞り込み
- `Send Test Emails` は本文と hyperlink の確認用で、current 判定そのものは `View Report` と `queue_count` を併用する
- `copy` や `Resend` でも sent 実績があれば current representative になりうる

## ここで止めて確認する条件

- `Journey` にすべきか `Campaign` にすべきか曖昧
- `trigger` と `Filter who can enter` の役割が混ざっている
- `Tag added` で作る state が downstream とつながっていない
- current 既存 flow を直すか、新規 draft を作るか迷う
- main CTA を `short.io` にしない例外判断が必要
- `Filter who can enter` に単発 campaign の配信条件みたいな発想が入り始めた

## Addness 側で見るべき補足

- Journey = evergreen
- current / legacy の representative
- current コンテンツの型

## 保存前の最小チェック

- audience と segment を本文前に固定している
- `Subject line / Preview text / main CTA` の役割を分けている
- main CTA の `short.io` を用意している

## 保存後の最小チェック

- preview または test で actual hyperlink を確認した
- `short.io` の final destination まで確認した
- report や click-details の見る順が決まっている
