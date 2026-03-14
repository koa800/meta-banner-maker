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
