# Lステップ カレンダー予約 workflow

## current で固定している事実

- 一覧 URL
  - `https://manager.linestep.net/line/reserve/salon`
- 代表 calendar detail URL
  - `https://manager.linestep.net/salon/{salon_id}/schedule/day/YYYY/M/D`
- 代表 config URL
  - `https://manager.linestep.net/salon/{salon_id}/config`
  - `https://manager.linestep.net/salon/{salon_id}/config/action`
  - `https://manager.linestep.net/salon/{salon_id}/config/episode`
  - `https://manager.linestep.net/salon/{salon_id}/config/external_services`

## current で見えている主要タブ

- 左タブ
  - `予約一覧`
  - `シフト`
  - `予約設定`
- `予約設定` 配下
  - `予約受付`
  - `予約枠 / コース`
  - `予約画面`
  - `アクション`
  - `リマインダ / フォロー`
  - `外部サービス連携`

## `アクション` と `リマインダ / フォロー` の読み方

- 一覧名だけでは送信対象を判断しない
- action 設定の条件 block で少なくとも次を見る
  - `カレンダー予約`
  - `予約枠`
  - `コース`
- 同じカレンダー内に別コースがあっても、`コース` 条件を切れば送信を分けられる

## `外部サービス連携` の読み方

- modal で選べる current 項目
  - `Googleアカウント名`
  - `カレンダーID`
  - `予約枠`
  - `連携対象`
- `連携対象`
  - `すべて`
  - `予約をGoogleカレンダーに連携`
  - `Googleカレンダーをシフトに連携`
- current の設計は `コース` 単位ではなく `予約枠` 単位
- 同じ予約枠の `予約 -> Googleカレンダー` を複数カレンダーへ向ける保存は reject される
  - 実際の error
    - `1つの予約枠の予約を複数のGoogleカレンダーに反映することはできません。`

## live で確認した API

- `GET /api/salon/{salon_id}`
  - episode step と action_id を返す
- `GET /api/action/data/{action_id}`
  - action の条件設定を返す
- `GET /api/salon/{salon_id}/googlecalendars`
  - Google account と association を返す
- `POST /api/salon/{salon_id}/googlecalendars`
  - body 例
    - `{"salon_resource_id":109117,"google_token_id":16079,"google_calendar_id":"koa800sea.nifs@gmail.com","link_target":"all"}`
- `DELETE /api/salon/{salon_id}/googlecalendars/{google_calendar_primary_id}/{purpose}/{association_id}`

## representative 例

`スキルプラス【サポートLINE】 > 広告コース：設定サポート`

- 同じカレンダー内に
  - `設定サポート`
  - `スキルプラス 広告コース1on1`
  を共存
- `アクション` と `リマインダ / フォロー` は `予約枠 + コース` 条件で分岐
- Google カレンダー連携は `予約枠` 単位で切り替え

## live で確認した exact 検証順

1. `予約枠 / コース` で対象名を確認する
2. `アクション` で予約直後 action の条件を見る
3. `リマインダ / フォロー` で前日 / 直前 step の条件を見る
4. `外部サービス連携` で Google account と連携対象を見る
5. 必要なら API で
   - episode step
   - action condition
   - google calendar association
   を確認する

## 読み方

- `カレンダー予約` は `1on1 を作る画面` ではなく `露出 / 送信 / 同期` を束ねる operational screen
- `コース` は予約内容とメッセージ分岐に効く
- `予約枠` は Google カレンダー連携の単位に効く
- `表示条件` と `送信条件` は別物として扱う

## 30秒レビューの順番

1. 対象が `予約枠 / コース / アクション / リマインダ / 外部サービス連携` のどれかを切る
2. `予約枠` と `コース` の違いを言う
3. `アクション` と `リマインダ / フォロー` の条件を見る
4. Google カレンダー連携があるか見る
5. 送信条件と露出条件を混同していないか確認する

## 完成条件

- 対象が `予約枠 / コース / アクション / リマインダ / 外部サービス連携` のどれかで固定できている
- `予約枠` と `コース` の役割の違いを説明できる
- `アクション` と `リマインダ / フォロー` の条件が意図どおりか確認している
- Google カレンダー連携がある場合は `連携対象` まで確認している

## ここで止めて確認する条件

- `予約枠` と `コース` のどちらで分けるべきか言えない
- 同じ予約枠を複数の Google カレンダーに同期したくなっている
- `送信条件` と `表示条件` を同じものとして扱い始めている

## 保存前の最小チェック

- 目的と次行動を 1 文で言える
- 入力値や action の実体が確定している
- テスト後に残すか削除するか決めている

## 保存後の最小チェック

- 一覧と実挙動の両方で確認した
- `テスト送信` があるものは `甲原 海人` で確認した
- テスト用は削除して残っていない
