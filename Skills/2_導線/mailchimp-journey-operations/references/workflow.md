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
  - verify 画面へ入力
  の順

## create の current UI

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`

`Build from scratch` は、trigger を選び始めた時点で draft flow を作る。live テストでは、必要な確認が終わったら一覧へ戻って削除する。

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

## representative report

- `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
  - `Days active = 147`
  - `Total started = 32,167`
  - `Total in progress = 4,596`
  - `Total completed = 27,567`
  - `Open rate = 17.4%`
  - `Click rate = 0.04%`

## 保存前後の最小チェック

### 保存前

- evergreen で流す理由を説明できる
- `trigger / filter / email step` の役割を区別できる
- main CTA を `short.io` にする理由を説明できる

### 保存後

- `View Report` と `mailchimp_journey_snapshot.py` の両方で current 判定を確認する
- main CTA の actual hyperlink を click で確認する
- 探索だけで作った draft は `Delete flow` まで戻す

## Addness 側で見るべき補足

- Journey = evergreen
- current / legacy の representative
- current コンテンツの型
