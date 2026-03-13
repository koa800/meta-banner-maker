# Lステップ 標準メッセージ exact メモ

## current 入口

- `テンプレート`
- `新しいテンプレート`
- `標準メッセージ`

代表 route
- 新規: `/line/template/new?group=0`
- 既存: `/line/template/edit/{template_id}?group={group_id}`

## current で確認できた主要ラベル

- `テンプレート名`
- `テンプレート登録`
- `下書き保存`

重要
- 本文入力は visible `.ProseMirror`
- hidden `textarea[name="text_text"]` を主入口にしない

## representative の読み方

### 運用連絡型

- 例: `オンライン再リマインド`
- 読み方
  - 何の人向けか
  - なぜ今やる必要があるか
  - 押す先 1 つ
  を揃える

### 長文説明型

- 例: `SNS活用 1on1無料相談会`
- 読み方
  - 共感
  - 問題整理
  - 便益
  - 最後に 1 CTA

### お知らせ型

- 例: `2025.05.28 リトルみかみくん利用可能のお知らせ`
- 読み方
  - 説明が主
  - 行動は補助

## exact smoke 手順

1. `テンプレート名`
2. `.ProseMirror` に本文
3. `テンプレート登録`
4. 一覧へ戻る
5. 行右端 `... -> テスト送信`
6. 実機確認
7. テスト用なら `... -> 削除`

## Addness 側で見るべき補足

- どの account で作るか
- テスト送信先
- current / legacy の見分け
- 命名規則

これらは `Master/knowledge/lstep_structure.md` を正本にする
