# self_clone レイヤー

最終更新: 2026-03-13

`Master/self_clone/` は、クローン対象者ごとの固有スタンスを持つ場所です。4層で見ると主に `前提` の詳細層です。

## このフォルダの考え方

- ここに置くのは「その人としてどう判断するか」
- 汎用原理や再利用知識の正本は `Skills/` に置く
- 同じ構造で複数クローンを管理できるようにする

## 主な構成

- `kohara/`
  現在の甲原クローン本体
- `mikami/`
  三上クローン本体
- `templates/`
  クローン構築テンプレート
- `projects/`
  個別プロジェクト用の派生構造

## 甲原クローンで特に重要なファイル

- `kohara/BRAIN_OS.md`
- `kohara/IDENTITY.md`
- `kohara/USER.md`
- `kohara/SELF_PROFILE.md`
- `kohara/SOUL.md`

## 置かないもの

- LP・導線・広告の汎用ノウハウ
- 会社共通に公開してよい事実
- 成果物そのもの

それらは `Skills/`、`company/`、`output/` を優先する。

## 甲原クローンのオンライン再現ループ

- 実運用の一次ログは `Master/learning/reply_feedback.json` を正本にする
- ここでは `誰に / どの媒体で / どんな文脈で / どう補正したか` まで残す
- `fb [人名]: [内容]` のような個別補正は `learning` に留め、繰り返し再現されるものだけ `kohara/IDENTITY.md` や `kohara/BRAIN_OS.md` に昇格する
- `self_clone` に上げる条件は、単発の好みではなく、判断構造として再利用できること
