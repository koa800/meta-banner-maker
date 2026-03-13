# Lステップ 一斉配信 workflow

## current で固定している事実

- 一覧 URL
  - `https://manager.linestep.net/line/magazine`
- create URL
  - `https://manager.linestep.net/magazine/new`
- visible な上部 button
  - `新規配信`
  - `テンプレート配信`
- visible な一覧列
  - `タイトル`
  - `配信日時`
  - `編集`
  - `配信条件`
  - `内容`
  - `開封数`

## live で確認した exact 手順

1. `一斉配信`
2. `新規配信`
3. 管理用タイトルは visible `input.form-control`
4. 本文は visible `.ProseMirror`
5. `下書き保存` は `#v_draft_save`
6. success toast
   - `下書き [テキスト]... を新たに保存しました。`
7. `下書きを開く`
8. `/line/draft/magazine` に移動
9. row 左端 checkbox label を押して選択
10. 上部 `チェックをした下書きを削除する`
11. success toast
    - `選択した下書きを削除しました。`

## 読み方

- `一斉配信` は送る画面だけではなく、`配信履歴と配信条件を見返す画面` でもある
- 後片付けの正規手順は create 画面ではなく `下書き一覧` 側
