# 前提レイヤー

最終更新: 2026-03-11

ここは「AIが判断する前に先に揃えておくもの」を置く場所です。最上位では、甲原さんのOS・信念・目的を扱い、個別事業より上の判断軸をここで固定します。`スキルプラス` はここでいう最上位ではなく、今の主要実装の一つです。

## 前提に入れるもの

- 用語定義
- 目的
- 人格
- 価値観
- 判断軸
- 優先順位
- NG前提

## 前提に入れないもの

- 単発の事例や観察
- 成功失敗の生データ
- 個別案件の成果物
- 一時的な作業メモ

## 正本

- 用語定義のローカル正本: `Master/前提/用語定義.md`
- AI参照用の機械可読版: `Master/前提/用語定義.json`
- 冒頭の `2026-03-11 手動確定概念` は、Sheets 同期結果より優先する
- 人が追記する入力口: Google Sheets `言葉の定義`
- 目的の入口: `Master/前提/目的.md`
- 判断軸の入口: `Master/前提/判断軸.md`
- 優先順位の入口: `Master/前提/優先順位.md`
- 更新境界: `Master/前提/更新ルール.md`
- 本人の固定プロフィール: `Master/前提/本人基本プロフィール.md`

```bash
python3 System/sheets_sync.py --id 1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y
```

## 現在の参照先

- 価値観・思考OS: `Master/self_clone/kohara/BRAIN_OS.md`
- 言語スタイル: `Master/self_clone/kohara/IDENTITY.md`
- 判断スタンス: `Master/self_clone/kohara/USER.md`
- 哲学・価値観: `Master/self_clone/kohara/SELF_PROFILE.md`
- 人物理解: `Master/company/people_public.json`, `Master/brains/kohara/people_private.json`
- 事務・申告で使う固定プロフィール: `Master/前提/本人基本プロフィール.md`

## 運用ルール

- 新しい言葉の定義はまずシートに追記する
- シート更新後に同期コマンドを実行してローカル正本を更新する
- 同じ意味で使うべき重要語は、定義が曖昧なまま output や rules に流さない
- 甲原さんが頻繁に使い、判断や表現のズレを生みやすい言葉は `定義候補` として先に拾う
- `前提` の意味変更は、`更新ルール.md` に従って扱う
