# Lステップ カルーセルメッセージ(新方式) exact メモ

## current 入口

- `テンプレート`
- `新しいテンプレート`
- `カルーセルメッセージ(新方式)`

代表 route
- 新規: `/line/template/edit_v2/new?group=0`
- 既存: `/line/template/edit_v2/{template_id}`

## current で確認できた主要ラベル

- `テンプレート名`
- `パネル #1`
- `タイトル`
- `本文`
- `画像`
- `画像選択`
- `選択肢名`
- `アクション設定`
- `テンプレート登録`

重要
- 本文は `ProseMirror`
- save payload の主値は `eggjson`
- current の visible input は
  - `input[name="template.name"]`
  - `input[name="message.0.body.panels.0.actions.0.title"]`
- `タイトル` は current UI では省略できる representative がある

## representative の読み方

## 30秒レビューの順番

1. panel 数に意味があるか見る
2. `誰に送るか` を 1 文で言う
3. main CTA panel がどれか決める
4. `選択肢名` と `アクション設定` が一致しているか見る
5. 画像と本文が同じ方向を向いているか見る
6. `テスト送信` で実機の押し順を見る

### 1 panel 単発オファー型

- 例: `パラダイムシフトーカルーセル`
- 読み方
  - 比較ではなく、1 panel で視覚訴求 + CTA

### 回答フォーム誘導型

- 例: `動画編集　進捗報告　カルーセル`
- 読み方
  - visual CTA で迷わず回答させる

### 無料相談会 CTA 型

- 例: `▼無料相談はこちら【AI活用 無料相談会】`
- 読み方
  - 複数 panel 比較より、friction を下げる CTA card として使う

## exact smoke 手順

1. `テンプレート名`
   - current input name は `template.name`
2. `本文`
3. `選択肢名`
   - current input name は `message.0.body.panels.0.actions.0.title`
4. 必要なら `アクション設定`
5. `テンプレート登録`
6. 一覧へ戻る
7. 行右端 `... -> テスト送信`
8. 実機確認
9. テスト用なら `... -> 削除`

## Addness 側で見るべき補足

- どの account で作るか
- テスト送信先
- current / legacy の見分け
- 命名規則

これらは `Master/knowledge/lstep_structure.md` を正本にする

## 完成条件

- panel の役割を説明できる
- `選択肢名` と `アクション設定` が一致している
- `テンプレート登録` 後に `テスト送信` で実機確認している
- テスト用なら削除まで終えている

## ここで止めて確認する条件

- panel を増やしたい理由が `情報を全部入れたい` だけになっている
- どの panel を押してほしいか自分で言えない
- `カルーセルメッセージ(新方式)` ではなく `フレックスメッセージ` の方が自然に見える

## 保存前の最小チェック

- 目的と次行動を 1 文で言える
- 入力値や action の実体が確定している
- テスト後に残すか削除するか決めている

## 保存後の最小チェック

- 一覧と実挙動の両方で確認した
- `テスト送信` があるものは `甲原 海人` で確認した
- テスト用は削除して残っていない
