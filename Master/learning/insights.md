# 日向の知見メモ

Claude Code サイクルで得られた知見をここに蓄積する。

## Addness 操作

- コメント投稿は `textarea[placeholder*="@でメンション"]` → `Meta+Enter`
- アクション追加は `input[placeholder*="タイトルを"]` → fill → Enter
- 「AIと相談」は右パネルに表示される。会話開始ボタンが必要な場合がある

## 注意事項

- CDP 接続時 `browser.close()` は接続切断のみ。`context.close()` は絶対に使わない
- Slack の「報告して」は instruction として処理される（status ではない）
