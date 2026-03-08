# brains レイヤー

最終更新: 2026-03-08

`Master/brains/` は、各エージェント脳の実行定義を持つ場所です。4層で見ると `前提` の中でも「実行主体ごとの設定」にあたります。

## 役割

- 脳ごとの manifest を持つ
- 各脳が参照してよい private people model を分ける
- 甲原クローン脳と日向脳を分離する

## 現在の脳

- `kohara/`
  - `brain_manifest.json`
  - `people_private.json`
  - `awakened_self.md`
- `hinata/`
  - `brain_manifest.json`
  - `people_private.json`
  - `persona.md`

## ルール

- `company/` には確認済み事実だけを置く
- 深い人物理解や private モデルは各 brain 配下に置く
- 別人格の脳同士で private 情報を混ぜない
