# Master/people の役割

このフォルダは、**人の情報を全部入れる場所ではない**。  
現在は主に **legacy 運用層 + 識別層** を置く場所として扱う。

## まず結論

- `Master/people/identities.json`
  - **識別用**
  - LINE表示名、Chatwork ID、メールなど「誰かを特定する」ためのキー

- `Master/people/profiles.json`
  - **legacy 運用用**
  - 週次学習で付く `comm_profile` や `group_insights` を含む、運用都合の厚い人物プロファイル
  - まだ周辺ツールが直接参照・更新するため、当面は残す

- `Master/people/profiles.md`
  - **人が読むための表示用**
  - `profiles.json` を読みやすくしたもの
  - 正本ではない

## いまの正規レイヤー

- `Master/company/people_public.json`
  - **会社共通で見てよい人物情報の正規レイヤー**
  - 役割、表面的プロフィール、共有してよい業務情報

- `Master/brains/kohara/people_private.json`
  - **甲原クローン脳だけが持つ私的人物理解**
  - 本質理解、距離感、関わり方、承認済みの深い仮説

- `System/registries/agent_registry.json`
  - **人間 / AI / shell / brain の実行主体定義**
  - 人物情報そのものではなく、「誰が何として動くか」を定義する

## 重複しているもの

現状、次の重複は存在する。

1. `identities.json` と `profiles.json`
   - 識別情報が重複している
   - 理由: 周辺ツールの歴史的都合

2. `profiles.json` と `people_public.json`
   - 公開してよい人物情報が重複している
   - 理由: 新構造への移行途中で、`people_public.json` は `profiles.json` から派生生成しているため

3. `profiles.json` と `profiles.md`
   - 内容はほぼ同じで、JSON と Markdown の表示違い

## ルール

今後は以下で統一する。

1. 新しく「会社共通の人物情報」を増やすなら `Master/company/people_public.json`
2. 新しく「甲原だけが持つ深い人物理解」を増やすなら `Master/brains/kohara/people_private.json`
3. `Master/people/profiles.json` には、legacy 運用の都合があるものだけを残す
4. `Master/people/profiles.md` は表示用。直接育てない
5. `Master/people/identities.json` は識別キー専用。人格理解は入れない

## 会話での更新ルール

ユーザーは、タグ付けせず自然文で伝えてよい。  
保存先の判定は、原則として AI 側が行う。

### ユーザーがやること

- 人物について知っていることを、そのまま自然文で伝える
- `反映して` または `覚えて` と言う
- 保存したくない場合は `まだ保存しない` または `相談だけ` と言う

例:

```text
鈴木織大は、成果が出ないことへの焦りが強い。
強めに言っても大丈夫だけど、最初に期待を渡してから入る方が伸びる。
反映して
```

### AI がやること

受け取った情報を以下の4層に自動で振り分ける。

1. 公開人物情報
   - 役割、担当、共有してよい業務情報
   - 保存先: `Master/company/people_public.json`

2. 私的人物理解
   - 本質理解、距離感、関わり方、ポテンシャルを最大化する接し方
   - 保存先: `Master/brains/kohara/people_private.json`

3. 識別情報
   - LINE表示名、Chatwork ID、メール、実名対応
   - 保存先: `Master/people/identities.json`

4. 短期文脈
   - 今週忙しい、今この案件で詰まっている、体調が悪い、などの一時情報
   - 保存先: shared context

### 判定原則

- 深い人物理解は、ユーザーが「非公開」と言わなくても基本は private に寄せる
- 会社共通に出してよいと明らかな事実だけ public に置く
- 一時的な状況は people データ本体に入れず short-term に置く
- 推測が混ざる場合は仮説扱いにし、確定保存はユーザー承認後

### 一言でいうと

ユーザーは本質情報だけ渡せばよい。  
AI がどこに保存すべきかを判断する。

## 一言でいうと

`Master/people` は **人データの最終置き場** ではなく、  
**識別と legacy 運用を引き受けている移行中フォルダ** です。
