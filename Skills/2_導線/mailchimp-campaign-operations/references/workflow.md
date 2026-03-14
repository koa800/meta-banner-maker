# Mailchimp Campaign exact メモ

## current でよく使う route

- Campaign Manager: `/campaigns/`
- create: `/campaigns/#/create-campaign`

## current login / verify

- `login.mailchimp.com`
- `unifiedLoginPost`
- `login/verify`
- 2段階認証は current では
  - `Send code via SMS`
  - LINE の `Mailchimp認証` グループでコード確認
  - verify 画面へ入力
  の順

## current の create 順

1. `Campaign Manager`
2. `Create`
3. `Regular`
4. audience
5. segment
6. `Campaign name`

current UI では `campaigns/create/` 直URLではなく、`Campaign Manager -> Create -> Regular` の SPA 入口を使う。
segment や audience を先に固めずに本文から作り始めない。

## draft cleanup

- exploratory draft を UI で作った時は、配信前に必ず削除する
- current 実測では API の `create -> content -> delete` は通っていて、`ZZ_TEST_DELETE_20260311` を削除後 `404` まで確認済み
- したがって UI 側の delete 導線が揺れる時は、API cleanup を fallback として持つ

## current 読み方

- `Campaign` = 今回だけの配信
- representative を読む時は
  - `sent`
  - `open`
  - `click`
  - main CTA
  の順で見る

## representative current campaign

- `AI全自動PR_1通目(3/13)`
  - `sent = 259,813`
  - `open_rate = 8.57%`
  - `click_rate = 0.187%`
  - main CTA は current 実測で `direct LINE`
  - follow family は `%40631igmlz`
- `3/11 AIキャリアセミナーPR_2通目`
  - `sent = 255,250`
  - `open_rate = 10.41%`
  - `click_rate = 0.042%`
  - main CTA は current 実測で `direct LINE`
  - follow family は `%40770dyrre`
- `3/10 セミナーPR_3通目 (フリープラン)`
  - `sent = 5,044`
  - `open_rate = 38.87%`
  - `click_rate = 0.654%`
  - main CTA は current 実測で `direct LINE`
  - follow family は `%40076cqpuk`
- broad 配信の current benchmark
  - `open_rate` は概ね `9〜11%`
  - `click_rate` は概ね `0.04〜0.21%`
- 高温度 segment 配信の current benchmark
  - `open_rate` は概ね `38〜46%`
  - `click_rate` は概ね `0.59〜4.99%`
- ただし、今後こちらが新規に作る標準は `main CTA = short.io`

## CTA rule

- 今後こちらで新規に作る main CTA は `short.io`
- 表示文字列ではなく hyperlink の実URLを click で確認する
- 補助リンクだけ直リンク可

## 保存前後の最小チェックリスト

### 保存前

- `Audience` と `segment / tag / exclude` が先に確定している
- `Campaign name / Subject line / Preview text / From name / Reply to` の役割を説明できる
- main CTA を `short.io` にする理由を説明できる

### 保存後

- test または preview で `Subject line / Preview text / main CTA 表示文言 / actual hyperlink` を確認する
- `short.io` を使う場合は final destination まで押して確認する
- `click-details` を見て、main CTA と補助リンクを混同していないか確認する

## runtime 補助

- representative の読解や smoke では、本文先頭だけでなく click report 側の実クリック URL まで合わせて見る
- `regular campaign` は `sent / open / click` と `main CTA` を 1 セットで読む

## Addness 側で見るべき補足

- current sent campaign の representative
- good / bad の判断
- segment の切り方
