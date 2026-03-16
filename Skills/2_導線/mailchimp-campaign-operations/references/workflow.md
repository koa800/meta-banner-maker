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

## current の作成順をさらに exact にすると

1. `Campaign Manager`
2. `Create`
3. `Regular`
4. `Audience`
5. `Segment or Tag`
6. 必要なら `Exclude`
7. `Campaign name`
8. `Subject line`
9. `Preview text`
10. 本文作成
11. test / preview
12. 配信前の review

つまり regular campaign は、本文より先に
- 誰に送るか
- 今回だけ送る理由
- 何の認識を変えたいか
を切る。

## editor で実際に見るラベル

- `Campaign name`
- `Audience`
- `Segment or Tag`
- `Exclude`
- `Subject line`
- `Preview text`
- `From name`
- `From email address`
- `Reply to email address`
- `Preview`
- `Send a test email`
- `Review and Send`

`Campaign Manager -> Create -> Regular` で入った後は、上のラベルを先に探せることを exact 性の基準にする。

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

## 30秒レビューの順番

1. `Campaign Manager`
2. 対象 row の `Campaign name`
3. `Audience`
4. `Segment or Tag`
5. `Exclude`
6. `Subject line`
7. `Preview text`
8. main CTA
9. 実 hyperlink
10. `View report`

## CTA rule

- 今後こちらで新規に作る main CTA は `short.io`
- 表示文字列ではなく hyperlink の実URLを click で確認する
- 補助リンクだけ直リンク可

## 本文と CTA の exact チェック

1. `Subject line`
2. `Preview text`
3. 冒頭 3 行
4. main CTA の文言
5. main CTA の hyperlink
6. `short.io`
7. final destination
8. 補助リンク

regular campaign は 1 通で役割を持つので、
- broad 配信なら当事者意識や危機感
- 高温 segment なら予約促進や申込促進
のように、役割を 1 つに寄せる。

## editor の exact smoke 順

1. `Campaign name`
2. `Audience`
3. `Segment or Tag`
4. `Exclude`
5. `Subject line`
6. `Preview text`
7. `From name`
8. `From email address`
9. `Reply to email address`
10. 冒頭 3 行
11. main CTA の表示文言
12. actual hyperlink
13. `short.io`
14. final destination
15. `Preview`
16. `Send a test email`
17. `Review and Send`

`Review and Send` に行く前に、表示文言と actual hyperlink を分けて確認する。

## 保存前後の最小チェックリスト

### 保存前

- `Audience` と `segment / tag / exclude` が先に確定している
- `Campaign name / Subject line / Preview text / From name / Reply to` の役割を説明できる
- main CTA を `short.io` にする理由を説明できる

### 保存後

- test または preview で `Subject line / Preview text / main CTA 表示文言 / actual hyperlink` を確認する
- `short.io` を使う場合は final destination まで押して確認する
- `click-details` を見て、main CTA と補助リンクを混同していないか確認する
- exploratory draft は配信前に削除する

## ここで止めて確認する条件

- `Audience` と `Segment or Tag` が先に切れていない
- broad 配信か高温 segment 配信か曖昧
- `direct LINE` の current 実績を見て、今回も直リンクに寄せるか迷う
- `Campaign name / Subject line / Preview text` の役割が重なっている
- main CTA と補助リンクの優先順位が曖昧

## runtime 補助

- representative の読解や smoke では、本文先頭だけでなく click report 側の実クリック URL まで合わせて見る
- `regular campaign` は `sent / open / click` と `main CTA` を 1 セットで読む

## Addness 側で見るべき補足

- current sent campaign の representative
- good / bad の判断
- segment の切り方

## 完成条件

- `Campaign Manager -> Create -> Regular` から迷わず作り始められる
- `Audience / Segment or Tag / Exclude` を本文前に固定できる
- `Subject line / Preview text / main CTA / actual hyperlink / final destination` を分けて確認している
- main CTA を `short.io` にする理由を説明できる
- exploratory draft は delete まで終えている

## 保存前の最小チェック

- audience と segment を本文前に固定している
- `Subject line / Preview text / main CTA` の役割を分けている
- main CTA の `short.io` を用意している

## 保存後の最小チェック

- preview または test で actual hyperlink を確認した
- `short.io` の final destination まで確認した
- report や click-details の見る順が決まっている

## current の exact draft cleanup

1. `Campaign Manager`
2. exploratory draft の row
3. row menu から `Delete`
4. confirm dialog の `Delete campaign`

delete 導線が不安定な時は、API の `create -> content -> delete` を fallback にする。
