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
