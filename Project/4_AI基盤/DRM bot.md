# DRM bot

最終更新: 2026-03-11
ステータス: 設計待機・未着手

---

## 目的

ユーザー単位で最適化されたコミュニケーションを、AI が

- 誰に送るか
- いつ送るか
- 何を送るか
- 送った結果をどう次に活かすか

まで一気通貫で扱える状態を作る。

スプレッドシートは手段の1つにすぎず、正本は `DRM bot` の判断基盤に置く。

---

## ゴール

甲原さんが `このユーザー群にこの目的で打ちたい` と決めたときに、AI が

- 対象者の状態を理解し
- 送信優先度を判定し
- 個別最適化した本文を作り
- 意図したタイミングで送り
- 反応データを学習に戻す

ところまで進められること。

---

## 前提として決めたこと

### 1. Lステップは補助レイヤー

Lステップは残してよいが、中核の頭脳には置かない。

- 向いていること
  - タグ
  - 既存導線
  - 既存シナリオ
  - Webhook転送
  - オペレーション管理
- 向いていないこと
  - ユーザーごとに毎回ゼロベースで最適化する判断
  - 毎回自由に構造を変えるメッセージ生成

### 2. 送信の主経路は LINE Messaging API 直送

本文や構造の自由度を最大化するため、主送信経路は `LINE Messaging API` を前提にする。

### 3. Lステップ契約と直送は併用可能

- 送信は `Messaging API` 直送で併用できる
- ただし Webhook の一次受信先は1つなので、Lステップを一次受信に置くなら自前基盤へは `Webhook転送` で流す

### 4. 初回は dry-run から始める

いきなり本番送信はしない。

最初に作るのは

- 判断
- 送信候補生成
- payload 生成
- ログ

までで、外部送信は明示的に有効化するまで発火させない。

---

## 想定アーキテクチャ

```text
CDP / Lステップ / Mailchimp / 各種イベント
  -> DRM bot input layer
  -> user state / priority / timing judgment
  -> message generation
  -> delivery router
      -> LINE Messaging API direct send
      -> Lステップ API連携（必要時のみ）
  -> response logging / learning loop
```

---

## 役割分担

### DRM bot が持つ責務

- ユーザー状態の集約
- 送信タイミング判定
- 送信対象選定
- 本文生成
- 送信経路選択
- 結果学習

### Lステップが持つ責務

- 既存LINE運用の継続
- タグ/シナリオ/導線の補助
- Webhook転送
- 必要時のアクション実行

### 既存AI基盤が流用できる責務

- `System/line_bot_local/` の coordinator 設計
- `System/config/` の設定管理パターン
- `Project/3_業務自動化/メールマーケティング自動化.md` の segment -> draft -> send の考え方

---

## 着手時に最初にやること

### Phase 0: 実装準備

- `System/drm_bot/` を切る
- `dry-run` 既定の runner を作る
- `LINE Messaging API` 送信クライアントを分離する
- `Lステップ bridge` を分離する
- 設定テンプレートを `System/config/` に置く

### Phase 1: 判断だけ動かす

- ユーザー状態の入力形式を固定
- `誰に / いつ / なぜ送るか` をAIが返す
- 送信本文候補を生成する
- 外部送信はまだしない

### Phase 2: dry-run 送信検証

- 実際の payload 生成まで通す
- safety limit を入れる
- 送信前ログと review を残す

### Phase 3: 本番有効化

- 小さいセグメントだけ有効化
- 送信頻度上限
- 重複防止
- 反応ログ収集

---

## 今はやらないこと

- `System/line_bot/` サブモジュール本体の改修
- 既存の本番 Webhook URL の切り替え
- 既存の Lステップ 運用導線の大改修
- 本番一斉送信

---

## 再開時の最短入口

再開したら、まずこの順で見る。

1. このファイル
2. `Master/knowledge/lstep_structure.md`
3. `Project/3_業務自動化/メールマーケティング自動化.md`
4. `System/line_bot_local/coordinator.py`
5. `ai works DRM bot` で current work を探し、`ai work <work_id|キーワード>` で切り替えてから対応する `System/data/ai_router/handoffs/<work_id>.md` を見る
6. `.ai_handoff.md` は current work mirror としてだけ扱う

---

## 次に着手する時の一言定義

`DRM bot = Lステップを補助として残しつつ、AI がユーザー単位で最適な LINE コミュニケーションを判断・生成・実行する基盤`
