# Lステップ テンプレートパック exact メモ

## current 入口

- `テンプレート`
- `新しいパック`

代表 route
- 新規: `/line/eggpack/edit/new?group=0`
- 表示: `/line/eggpack/show/{pack_id}?group=0`

## current で見えている主要ラベル

- `テンプレート名`
- `フォルダ`
- `メッセージ新規追加`
- `テンプレートから追加`
- `テスト送信`

## step 追加で見えている種類

- `テキスト`
- `スタンプ`
- `画像`
- `質問`
- `ボタン・カルーセル`
- `位置情報`
- `紹介`
- `音声`
- `動画`

## 最小の本文 step

1. `メッセージ新規追加`
2. `テキスト`
3. `.ProseMirror` に本文を入れる
4. `保存`

重要
- hidden textarea があっても、実務では `.ProseMirror` に見えている本文で確認する

## テンプレート差し込み

1. `テンプレートから追加`
2. modal `テンプレート選択`
3. 対象テンプレートを選ぶ
4. `追加`

current modal の主要ラベル
- `テンプレート選択`
- `閉じる`
- `コピーして編集`
- `追加`

## representative の読み方

### 認識変換 -> CTA 型

- 例: `YouTube切り抜き 無料相談会告知`
- 構成
  - step 1 `本文`
  - step 2 `テンプレート`
- 読み方
  - step 1 で urgency と理由づけ
  - step 2 で visual CTA

### 運用オペレーション型

- 例: `動画編集　進捗報告　テンプレート`
- 構成
  - step 1 `本文`
  - step 2 `テンプレート`
- 読み方
  - 進捗を出す理由を先に作る
  - その後で入力 action に渡す

### 回答回収型

- 例: `2024.10.29 アンケート`
- 構成
  - step 1 `本文`
  - step 2 実体は `カルーセルメッセージ(新方式)`
- 読み方
  - 協力理由を text で作る
  - visual CTA で迷わず回答させる

## exact smoke 手順

1. pack を作る
2. step 1 に `本文`
3. step 2 に既存テンプレートを差し込む
4. `テスト送信`
5. 受信順と CTA を確認
6. テスト用なら削除

## Addness 側で見るべき補足

- どの account で作るか
- テスト送信先
- current / legacy の見分け
- 命名規則

これらは `Master/knowledge/lstep_structure.md` を正本にする
