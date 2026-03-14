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

## relay を読む最小チェック

1. この Zap は何 event を relay しているか
2. downstream の Mailchimp audience はどれか
3. 付与される tag は何か
4. その tag 名は business event と一致しているか
5. duplicate や例外 relay になっていないか
