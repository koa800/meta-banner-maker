---
name: accounting-ops
description: Handle Kohara's personal accounting and freee workflows. Use when Codex needs to sort receipts, classify business vs personal spending, clear freee unprocessed items, update tax-related accounting rules, or prepare monthly bookkeeping and year-end filing based on the project's accounting source of truth.
---

# Accounting Ops

まず [経理運用ルール](../../../Master/knowledge/経理運用ルール.md) を読む。月次運用や入口の確認が必要なら [経理月次運用](../../../Master/knowledge/経理月次運用.md) も読む。

今年の申告値や単年判断が必要なら、必要なものだけ次から読む。

- `Master/output/経理/*判断ログ*.md`
- `Master/output/経理/*税額テーブル*.md`
- `Master/output/経理/*提出前チェックリスト*.md`
- `Master/output/経理/*オフライン証憑投入手順*.md`

## Workflow

1. 入口を確認する。優先順は `freee` → `/Users/koa800/Desktop/確定申告` → `Google Drive > 【個人】経理関係`。
2. 対象を `完全自動でよい / 推測止まり / 手動判断` に分ける。
3. `チャージ` と `実支払い` を分ける。
4. 事業用 / 私用 / 保留を切る。
5. freee の未処理を減らし、証憑があれば対応明細へ紐づける。
6. 新しい安定ルールが出たら、`Master/knowledge/経理運用ルール.md` か `Master/knowledge/経理月次運用.md` を更新する。
7. 単年固有の高額論点や特殊判断は `Master/output/経理/` に残す。

## Fixed Rules

- `PayPay / PASMO / スタバカード` はチャージ自体を経費にしない。
- `Apple / Amazon / QuickPay` は混在しやすいので、推測で確定しない。
- `国民年金 / 国民健康保険` は必要経費ではなく `社会保険料控除` 側で扱う。
- `10万円以上の支出 / 旅行 / プレゼント / 美容 / 衣装 / 立替金` は最後に人間判断が必要になりやすい。

## Output

結果は次の順でまとめる。

1. 今どうなったか
2. 金額影響
3. 残件
4. 見る場所
