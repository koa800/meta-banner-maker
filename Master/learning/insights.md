# 日向の知見メモ

Claude Code サイクルで得られた知見をここに蓄積する。

## Addness 操作

- コメント投稿は `textarea[placeholder*="@でメンション"]` → `Meta+Enter`
- アクション追加は `input[placeholder*="タイトルを"]` → fill → Enter
- 「AIと相談」は右パネルに表示される。会話開始ボタンが必要な場合がある

## Lステップ 予約管理

- `カレンダー予約` は `誰に見せるか` `予約後に何を送るか` `どの Google カレンダーに同期するか` が別レイヤー
- `アクション` と `リマインダ / フォロー` の一覧名だけでは送信対象を判断しない。条件設定内の `カレンダー予約 / 予約枠 / コース` まで見る
- `外部サービス連携` は `コース` 単位ではなく `予約枠` 単位。別コースを作っただけでは別 Google カレンダーに切れない
- `連携対象` は `all / reservation-only / shift-only` の 3 種
- 同じ予約枠の `予約 -> Googleカレンダー` を複数カレンダーへ向ける保存は reject される
- current で使えた確認 API
  - `GET /api/salon/{salon_id}/googlecalendars`
  - `POST /api/salon/{salon_id}/googlecalendars`
  - `DELETE /api/salon/{salon_id}/googlecalendars/{google_calendar_primary_id}/{purpose}/{association_id}`

## 注意事項

- CDP 接続時 `browser.close()` は接続切断のみ。`context.close()` は絶対に使わない
- Slack の「報告して」は instruction として処理される（status ではない）
