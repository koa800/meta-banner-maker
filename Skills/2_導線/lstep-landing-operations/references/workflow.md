# Lステップ 流入経路分析 workflow

## current で固定している事実

- 一覧 URL
  - `https://manager.linestep.net/line/landing`
- create URL
  - `https://manager.linestep.net/line/landing/edit`
- visible 一覧 action
  - `URLコピー`
  - `QR`
  - `広告挿入タグ`

## live で確認した exact 手順

1. `流入経路分析`
2. `新しい流入経路`
3. visible field
   - `流入経路名`
   - `QRコード表示用テキスト`
   - `有効期間(開始)`
   - `有効期間(終了)`
   - `アクション`
   - `友だち追加時設定のアクション`
   - `アクションの実行`
4. action 未設定のまま `登録`
5. confirm dialog
   - `アクションが設定されていません。本当に登録しますか？`
6. 作成後は一覧で `URLコピー / QR / 広告挿入タグ` を確認
7. row 右端 `more_vert -> 削除`

## 読み方

- `流入経路分析` は単なる分析リンクではなく、流入直後の action を起動する landing でもある
- `友だち追加時設定のアクション` は current UI の注記どおり、landing action より先に走る
