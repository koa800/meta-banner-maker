# Lステップ 回答フォーム exact メモ

## current 入口

- `回答フォーム`
- `新しい回答フォーム`

代表 route
- 新規: `/lvf/edit/new`
- 既存: `/lvf/edit/{form_id}`

## current で確認できた主要ラベル

- `フォーム名`
- visible field は `フォーム名(管理用)`
- `フォームタイトル`
- visible field は `タイトル`
- `記述式(テキストボックス)`
- `保存`
- 一覧の列
  - `スプレッドシート連携`
  - `回答状態`
  - `登録日`
  - `公開状態`

## exact な最小作成手順

1. `回答フォーム`
2. `新しい回答フォーム`
3. `フォーム名(管理用)`
   - current input name は `formname`
4. `タイトル`
   - current input name は `pagetitle`
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

### current 用途の代表

- `NPS`
  - 満足度や推奨度を取る
- `ゴール設定`
  - 受講後の行動や目標を取る
- `合宿`
  - 参加情報や当日運用情報を取る
- `数値管理`
  - 運用上の structured data を取る
- `アカウント突合フォーム`
  - account や受講状況の突合に使う

## current live で固定したこと

- create route は `/lvf/edit/new`
- visible 主入力は
  - `input[name="formname"]`
  - `input[name="pagetitle"]`
- `formNameInput` / `formTitleInput` のような抽象呼び方ではなく、現在は visible field 名で読む方がズレにくい
- 最初の質問 block は `記述式(テキストボックス)`
- save 後は `/lvf/edit/{form_id}` に残る
- 一覧 row menu は
  - `詳細を確認`
  - `公開設定を変更`
  - `コピー`
  - `テスト送信`
  - `削除`

## 質問種別を切る時の基本

- 自由記述が必要
  - `記述式(テキストボックス)` または `段落(テキストエリア)`
- 単一選択でよい
  - `ラジオボタン` または `プルダウン`
- 複数選択させたい
  - `チェックボックス`
- 添付が必要
  - `ファイル添付`

## exact 検証手順

1. 一覧に戻る
2. 該当行の `... -> テスト送信`
3. modal `テスト送信先選択`
4. visible text の `甲原 海人` を押す
5. `テスト` を押す
   - folder 名 `テスト` と衝突するので confirm button を exact に押す
6. 実機で開く
7. 必要なら `... -> 削除`

## 2026-03-14 live smoke

- temp 名
  - `ZZ_TMP_20260314_AnswerFormSmoke_05`
- 通したこと
  - `新しい回答フォーム`
  - `フォーム名(管理用)`
  - `タイトル`
  - `記述式(テキストボックス)`
  - `保存`
  - 一覧 row 右端 `... -> テスト送信`
  - `テスト送信先選択 -> 甲原 海人 -> テスト`
  - `... -> 削除 -> 削除する`
- 結果
  - `TEST_SENT`
  - `EXISTS_AFTER_DELETE = 0`

## Addness 側で見るべき補足

- 命名規則
- テスト送信先
- current / legacy の見分け

これらは `Master/knowledge/lstep_structure.md` を正本にする
