# Mailchimp tag / saved segment exact メモ

## current rule

- tag は英語
- 基本構造は `media_funnel_event`

代表例
- `meta_ai_optin`
- `x_skillplus_webinar1_optin`
- `linead_sns_consult_reserve`

## Journey 側の exact 入口

1. `Build from scratch`
2. `Name flow`
3. `Audience`
4. `Choose a trigger`
5. `Tag added`
6. `Set a tag`
7. `Filter who can enter`
8. `Save Trigger`

## Campaign 側の exact 入口

1. `Campaign Manager`
2. `Create`
3. `Regular email`
4. `Audience`
5. `Segment or Tag`
6. `Exclude`

## Addness 側の重要解釈

- `Journey` は evergreen
- `Campaign` は 1回きりの segment 配信用
- したがって `tag` は state を持たせるため、`saved segment` は配信母集団を切るために使い分ける

## 役割分離の最小型

- `tag`
  - evergreen の state
  - `Journey` の入口や downstream state
- `saved segment`
  - 今回だけ送る母集団
  - `Campaign` の対象条件

`今回だけ送る母集団` を `tag` で残しそうになったら、一度止まる。

## 30秒レビューの順番

1. `Journey` か `Campaign` かを切る
2. audience を固定する
3. `tag` で state を作る話か、`saved segment` で母集団を切る話かを切る
4. `誰に送るか` を 1 文で言う
5. `誰を除外するか` があるか確認する
6. 英語で `media_funnel_event` に落とす

## 迷った時の原則

- evergreen の入口条件なら、まず `tag`
- 単発配信の対象条件なら、まず `saved segment`
- `日本語でしか意味が保てない` と感じたら、その時点で名前の切り方を見直す

## 保存前の最小チェック

- `Journey` 用か `Campaign` 用か切れている
- `tag` で持たせたい state を 1 文で言える
- `saved segment` で切りたい母集団を 1 文で言える
- 英語命名で意味が残るか確認している

## 保存後の最小チェック

- `tag` なら trigger 条件として読める
- `saved segment` なら `誰に送るか / 誰を除外するか` が一覧で言える
- current の `media_funnel_event` 命名から外れていない
- `tag` と `saved segment` の役割が逆転していない

## 補助 helper

- saved segment create:
  - `python3 System/scripts/mailchimp_segment_helper.py create-static-empty --name ZZ_TEST_SEGMENT_...`
- saved segment delete:
  - `python3 System/scripts/mailchimp_segment_helper.py delete --id <segment_id>`
- tag list:
  - `python3 System/scripts/mailchimp_tag_helper.py list-tags --limit 10`
- safe test member 探索:
  - `python3 System/scripts/mailchimp_tag_helper.py search-members --query "@team.addness.co.jp" --limit 10`
  - `python3 System/scripts/mailchimp_tag_helper.py search-members --query "koa800" --limit 10`
- safe test member がある時だけ tag add / remove:
  - `python3 System/scripts/mailchimp_tag_helper.py add-tag --email <safe_test_member> --tag zz_test_xxx`
  - `python3 System/scripts/mailchimp_tag_helper.py remove-tag --email <safe_test_member> --tag zz_test_xxx`

### 2026-03-16 の live exact

- safe exploratory member:
  - `koa800sea.nifs+1006@gmail.com`
  - `status=pending`
  - `tags_count=0`
- 通したこと:
  - `add-tag --tag zz_test_mailchimp_tag_flow`
  - `member` で `tags_count=1`
  - `remove-tag --tag zz_test_mailchimp_tag_flow`
  - `member` で `tags_count=0`
- 意味:
  - `tag add -> rollback` の exact 性は API helper で live 確認済み
  - ただし future に status や tags_count が変わる可能性があるので、使用前に `member` を再確認する

### 2026-03-17 の live exact

- saved segment:
  - `ZZ_TEST_20260317_segment_probe`
  - `create-static-empty -> delete`
  - `id=4641625`
  - delete `204`
- member:
  - `koa800sea.nifs+zzrouteprobe20260317@gmail.com`
- 通したこと:
  - `ensure-member`
  - `add-tag --tag youtube_skillplus_routeprobe`
  - `remove-tag --tag youtube_skillplus_routeprobe`
  - `archive-member`
- current 学習:
  - `ensure-member` 直後の `add-tag` は、一時的に `404` になる回があった
  - current では `member` で対象が見えてから再試行すると成功した

## ここで止めて確認する条件

- `tag` と `saved segment` のどちらで切るべきか曖昧
- 日本語名の方が自然に見えるが、英語へ落とした時に意味が崩れる
- 既存 current naming と衝突しそう
- 一時的な配信条件を `tag` で恒久 state 化しそう

## 完成条件

- `Journey` 用か `Campaign` 用かを最初に切れている
- `tag` で持たせたい state か、`saved segment` で切りたい母集団かを説明できる
- 英語命名で意味が保たれている
- 既存 current naming と衝突しない
- 保存後に trigger 条件または配信母集団として正しく読める
