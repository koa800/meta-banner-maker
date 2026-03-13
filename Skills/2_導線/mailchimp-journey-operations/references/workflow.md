# Mailchimp Journey exact メモ

## current でよく使う route

- Automations 一覧: `/customer-journeys/`
- builder: `/customer-journey/builder?id={journey_id}`
- trigger modal: `/customer-journey/builder?id={journey_id}&stepModal=trigger`

## create の current UI

1. `Automations`
2. `Build from scratch`
3. `Name flow`
4. `Audience`
5. `Continue`
6. `Choose a trigger`

## `Tag added`

trigger picker で current に見える主なラベル。
- `Tag added`
- `Set a tag`
- `Filter who can enter`
- `Save Trigger`

## builder 上部の current ラベル

- `Send Test Emails`
- `View Report`
- `Pause & Edit`
- `Save and close flow`

## current 判定

最低でも次を見る。
- journey status = `sending`
- step status = `active`
- `queue_count > 0`

## CTA rule

- 今後こちらで新規に作る main CTA は `short.io`
- 表示文字列ではなく hyperlink の実URLを click で確認する

## Addness 側で見るべき補足

- Journey = evergreen
- current / legacy の representative
- current コンテンツの型
