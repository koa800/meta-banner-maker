# Lステップ 回答フォーム exact メモ

## current 入口

- `回答フォーム`
- `新しい回答フォーム`

代表 route
- 新規: `/lvf/edit/new`
- 既存: `/lvf/edit/{form_id}`

## current で確認できた主要ラベル

- `フォーム名`
- `フォームタイトル`
- `記述式(テキストボックス)`
- `保存`

## exact な最小作成手順

1. `回答フォーム`
2. `新しい回答フォーム`
3. `フォーム名`
4. `フォームタイトル`
5. `記述式(テキストボックス)`
6. 質問名を入れる
7. `保存`

## representative の読み方

### アンケート型

- 何を感じたか
- 何に困っているか
- 次に何を望むか
を回収する

### 申込前質問型

- 申込前の温度感
- 現状
- 適合性
を回収する

### 回答後分岐型

- 回答内容をもとに次の message や営業対応を変える

## current live で固定したこと

- create route は `/lvf/edit/new`
- 主入力は `formNameInput` と `formTitleInput`
- 最初の質問 block は `記述式(テキストボックス)`
- save 後は `/lvf/edit/{form_id}` に残る
- 一覧 row menu は
  - `詳細を確認`
  - `公開設定を変更`
  - `コピー`
  - `テスト送信`
  - `削除`

## exact 検証手順

1. 一覧に戻る
2. 該当行の `... -> テスト送信`
3. 実機で開く
4. 必要なら `... -> 削除`

## Addness 側で見るべき補足

- 命名規則
- テスト送信先
- current / legacy の見分け

これらは `Master/knowledge/lstep_structure.md` を正本にする
