# Zapier Webhook -> Mailchimp relay workflow

## current で固定している事実

- 一覧
  - `https://zapier.com/app/assets/zaps`
- editor
  - `https://zapier.com/editor/{zap_id}/published`
- current の代表 family
  - `Webhooks by Zapier / Catch Hook`
  - `Mailchimp / Add/Update Subscriber`

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

## 読み方

- Zapier は Addness では `relay layer`
- 主目的は、front system の event を Mailchimp tag に変換すること
- relay の誤りは downstream の Journey 条件や配信条件をまとめて壊す
