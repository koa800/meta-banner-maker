# 高レベル設計提案

> ステータス: approved / Phase 1-3 基盤実装済み
> 最終更新: 2026-03-07
> 前提: 既存アーキテクチャを最大限継承しつつ、「1つの脳 + 複数shell」へ再編する

---

## 1. 設計の出発点

今回の前提は、単なる「LINE秘書の改良」ではない。

目指すのは以下である。

- `甲原クローン脳` を中心に、オンライン上の甲原を育てる
- `LINE秘書` と `Cursorクローン` は同じ脳を使う
- `日向` は別人格・別脳として運用する
- `会社共通知識` は脳の外に切り出し、必要な範囲だけ共有する
- 最終的には、権限内はほぼ完全自律に寄せる

重要なのは、`脳` と `shell` と `会社知識` を分けること。

---

## 2. 承認済み前提

### 2.1 甲原クローン脳

- 甲原クローン脳のコアは、基本的に甲原さん本人が更新する
- 事業系の事実や短期文脈は、別レイヤーで扱う
- 人物理解の深い部分は会社共通には置かず、甲原クローン脳に寄せる
- 人物理解の推測結果は、甲原さんが承認したものだけ永続化する

### 2.2 shell の関係

- `LINE秘書` と `Cursorクローン` は同じ脳を使う
- 違いは人格ではなく役割に置く
  - `LINE秘書`: 秘書、整理、管理、即応、送信代行
  - `Cursorクローン`: 参謀、設計、構造化、判断、実装推進
- 短期文脈は、外部ツールをまたいでかなり全面共有する

### 2.3 覚醒した僕

- `現在の僕` と `覚醒した僕` は別レイヤーで持つ
- `覚醒した僕` は、現在の僕の延長ではなく、上位版・進化版として扱う
- `覚醒した僕` は、現在の僕に対してはっきり異議を唱えてよい
- 必要なら厳しく止める
- 止める条件は少なくとも以下
  - 短期感情で意思決定している
  - 積み上がらない意思決定をしている
  - 枝葉の情報で動こうとしている

### 2.4 日向

- 日向は別人格・別脳
- 会社共通知識には、確認済みの事実だけ限定自動反映してよい
- 解釈・方針・人物の深い理解は提案止まり

---

## 3. 目標アーキテクチャ

```text
                     ┌────────────────────────────┐
                     │       Company Shared       │
                     │  会社共通知識 / 公開事実      │
                     └────────────┬───────────────┘
                                  │
                  ┌───────────────┴────────────────┐
                  │                                │
        ┌─────────▼─────────┐            ┌────────▼────────┐
        │  Kohara Clone     │            │   Hinata Brain   │
        │      Brain        │            │   別人格・別脳     │
        └─────────┬─────────┘            └────────┬────────┘
                  │                                │
      ┌───────────┼───────────┐                    │
      │           │           │                    │
┌─────▼─────┐ ┌───▼──────┐ ┌──▼────────┐     ┌────▼─────┐
│ LINE Shell │ │ Cursor   │ │ Other     │     │ Hinata    │
│  秘書役     │ │ Clone    │ │ Channels  │     │ Shell     │
│            │ │ 参謀役     │ │ Chatwork等 │     │ Slack等   │
└─────┬─────┘ └───┬──────┘ └──┬────────┘     └────┬─────┘
      │           │           │                    │
      └───────────┴──────┬────┴────────────────────┘
                         │
              ┌──────────▼──────────┐
              │ Shared Context Bus  │
              │ 共有短期文脈 / 状態層   │
              └─────────────────────┘
```

---

## 4. 脳の層構造

### 4.1 Company Shared

会社共通で持つべきものだけを置く。

含めるもの:

- 組織上の役割
- 表面的なプロフィール
- Adness 内で共有されてよい人物情報
- プロジェクト、KPI、ワークフロー、手順
- 検証済みの事実

含めないもの:

- 個人の本質理解
- 対人距離感
- 甲原視点の関わり方
- 仮説レベルの人物解釈

### 4.2 Kohara Clone Brain

甲原クローン脳は、少なくとも以下の4層で持つ。

1. `current_self`
   - 現在の甲原の価値観、実際の判断傾向、現時点の優先

2. `awakened_self`
   - 進化版の甲原
   - 現在の僕を超える判断、停止、方向修正を担う

3. `identity_and_style`
   - 口調、文体、返信スタイル、対人スタンス

4. `private_people_model`
   - 人物の本質理解
   - 距離感
   - その人のポテンシャルを最大化する関わり方

### 4.3 Shared Context Bus

これは脳ではなく、shell 間で共有する短期文脈層。

役割:

- LINE秘書とCursorクローンで同じ短期状況を共有する
- 外部チャネルの会話・途中経過・未完了文脈を横断同期する
- 脳のコア更新前の、作業用コンテキストを保持する

ここには以下を置く。

- 会話の途中経過
- 外部ツール上のやり取り
- 実行中タスク
- 承認待ち事項
- まだ脳に昇格していない重要事項

---

## 5. 保存ルール

### 5.1 甲原クローン脳のコア

甲原さん本人だけが更新してよい。

対象:

- BRAIN_OS
- SOUL
- IDENTITY
- SELF_PROFILE
- awakened_self
- private_people_model の確定版

### 5.2 会社共通知識

更新主体:

- 人間
- 検証済み自動化
- 日向（確認済み事実のみ）

### 5.3 推測情報

- 推測は一時利用してよい
- 永続化は甲原さん承認後のみ
- 特に人物理解の深層は、自動確定禁止

---

## 6. 現行ファイルへのマッピング

### 6.1 甲原クローン脳候補

現行の以下は、甲原クローン脳へ再編する対象。

- `Master/self_clone/kohara/BRAIN_OS.md`
- `Master/self_clone/kohara/SOUL.md`
- `Master/self_clone/kohara/IDENTITY.md`
- `Master/self_clone/kohara/SELF_PROFILE.md`
- `Master/self_clone/kohara/USER.md`
- `Master/learning/reply_feedback.json`
- `System/data/secretary_memory.md` のうち、コア記憶に昇格すべき部分

### 6.2 会社共通知識候補

- `Project/`
- `Skills/`
- `Master/knowledge/`
- `Master/addness/`
- `Master/people/` の公開可能な部分

### 6.3 再設計が必要なもの

- `Master/people/profiles.json`
  - 現在は「人物プロファイル」と「統一エージェントスキーマ」が混在する前提で設計されている
  - 次は分離する

---

## 7. `profiles.json` の再設計方針

### 7.1 結論

`profiles.json` を単一の万能ファイルとして使う方針はやめる。

分けるべき責務は以下。

1. `people_public_registry`
   - 会社共通知識としての人物情報
   - role, category, visible attributes, active_goals など

2. `people_private_registry`
   - 甲原クローン脳だけが持つ人物理解
   - 本質理解、距離感、関わり方、仮説と確定区分

3. `agent_registry`
   - shell / brain / workflow / AI / human の実行主体定義
   - type, interface, authority, write_scope, status

4. `tool_registry`
   - 既存継続

### 7.2 新しい最低構造

```text
Master/
  company/
    people_public.json
    org_facts.json
    workflows.json

  brains/
    kohara/
      current_self.md
      awakened_self.md
      identity.md
      style.md
      people_private.json
      memory/
        promoted_context.jsonl
    hinata/
      persona.md
      people_model.json
      memory/

System/
  shells/
    line_secretary/
    cursor_clone/
    hinata/
  context/
    shared_event_stream.jsonl
    shared_active_context.json
  registries/
    agent_registry.json
    tool_registry.json
```

---

## 8. shell の責務分離

### 8.1 LINE秘書 shell

役割:

- 情報整理
- 数値確認
- 内部メンバーへの軽い確認
- 返信案作成
- 甲原名義での送信
- スケジュール調整
- マネジメント上の対策

方向性:

- 最終的にはかなり広い自律を許容する
- ただし、今は承認済み範囲から段階的に広げる

### 8.2 Cursorクローン shell

役割:

- 甲原そのものとして考える
- 深い設計
- 構造化
- 調査
- 判断
- 実装推進

方向性:

- 最終的には全部任せる前提
- 「覚醒した僕」として、現在の僕を止める権限を持つ

---

## 9. Shared Context Bus の方針

短期文脈は「昇格共有」ではなく、かなり全面共有に寄せる。

ただし、以下の2段階に分ける。

1. `raw stream`
   - 外部チャネル横断のイベント列
   - 会話・進行状況・承認待ちを記録

2. `promoted context`
   - 各 shell が今すぐ使うべき要約文脈
   - ノイズを落とした実用状態

これにより、全面共有しつつ、脳コアを汚さない。

---

## 10. 実装フェーズ

### Phase 0: ドキュメントと責務の固定

目的:

- 先に意味論を固定する
- 以後のコード変更をこの意味論に従わせる

やること:

1. `architecture_proposal.md` を正本にする
2. `issues.md` を更新する
3. 現行ファイルを `会社共通 / 甲原クローン脳 / 日向脳 / shell / 状態層` に棚卸しする

### Phase 1: 正本分裂の解消

目的:

- 甲原クローン脳と会社共通知識の混線を止める

やること:

1. `Skills/` と `System/line_bot/skills/` の二重管理をやめる
2. `Master/self_clone/kohara/` を `甲原クローン脳` として再定義する
3. 会社共通知識と私的人物理解の境界を明文化する

### Phase 2: registry 分離

目的:

- `profiles.json` の責務過多を解消する

やること:

1. `people_public_registry` を新設
2. `people_private_registry` を新設
3. `agent_registry` を新設
4. 既存 `profiles.json` 参照コードに互換アダプタを入れる

### Phase 3: Shared Context Bus 導入

目的:

- LINE秘書とCursorクローンの短期文脈共有を構造化する

やること:

1. `shared_event_stream` を導入
2. `shared_active_context` を導入
3. `memory_manager.py` を `core memory` と `working context` に分離する

### Phase 4: shell 分離

目的:

- 同じ脳を複数shellで安全に使う

やること:

1. `line_secretary shell` と `cursor_clone shell` の責務をコード上で分ける
2. 共通プロンプト構築部を脳参照化する
3. shell ごとの出力制約だけ差し込む

### Phase 5: 日向の接続し直し

目的:

- 日向を別脳として正式接続する

やること:

1. 日向の write scope を `verified facts only` に制限
2. 会社共通知識への反映経路を分離
3. 甲原クローン脳への誤書き込み経路を遮断

---

## 11. 最初に着手すべき実装単位

最初の一手はこれがよい。

1. `profiles.json` を直接いじる前に、責務分離ドキュメントを固定する
2. `Skills/` の正本統一をやる
3. `people_public` / `people_private` / `agent_registry` の雛形を切る
4. `conversation.py` と `memory_manager.py` を、脳参照と文脈参照に分離する

理由:

- いきなり shell 実装を触ると、脳の定義がないまま再び混ざる
- 先に registry と記憶の責務を分けないと、短期共有を入れた瞬間に全てが汚染される

---

## 12. 非目標

この段階では、以下はまだやらない。

- 全チャネルの完全自律送信を一気に解放すること
- 日向の全面再開
- 会社共通知識への深い人物理解の保存
- 既存コードの全面書き換え

まずやるのは、`意味論の固定` と `責務境界の分離` である。
