# addness レイヤー

最終更新: 2026-03-14

`Master/addness/` は、Addness 事業の実務 knowledge をまとめる詳細層です。4層で見ると主に `knowledge` に属します。

## このフォルダの役割

- Addness のゴール構造を持つ
- 実行タスクの一覧を持つ
- 導線、Lステップ、広告、リサーチの事実を持つ
- 秘書の自律ワークが参照する運用 knowledge を持つ

## Addness 操作基盤の現在方針

UI は頻繁に変わるので、`操作できる` の定義を UI 手順暗記に置かない。

- 読み取りは Addness API を正本にする
- 書き込みは公開 API があればそれを使う
- 公開 API がなければ goal ページの server action を再生する
- UI クリックは endpoint 発見と fallback の位置づけに留める
- 甲原海人の `activity-logs/by-member` を見て、よく使う操作から CLI と秘書ツールへ実装する
- 不可逆削除は既定の自動化対象にしない
- ただし `テスト` 配下では日次スモークテストを回し、API 側のズレを早めに検知する
- write 系操作は `System/data/addness_audit_log.jsonl` に監査ログを残す
- 行動ログ集計の latest は `System/data/addness_activity_summary_latest.json` を正本にする

### current で直接できること

- ゴール検索 / 詳細取得
- ゴール作成
- タイトル変更
- 完了 / 未完了の切り替え
- 期日変更
- 完了の基準更新
- 親ゴール変更
- コメント一覧 / 投稿 / 解決 / 削除
- アーカイブ / 削除
- AI 会話一覧 / 新規会話開始 / メッセージ送信 / 返答取得
- 現在メンバー取得
- 行動ログ取得 / 集計
- テスト配下の定期スモークテスト

削除系だけは guardrail を入れている。

- `delete_goal`
- `delete_comment`

この2つは CLI でも秘書側でも明示確認が必要。
特に `delete_goal` は次を満たさないと動かない。

- `confirm=true` / `--yes`
- 対象タイトル一致の確認 (`expected_title` / `--expected-title`)
- 既定では `テスト` 配下のみ許可

## Addness 自動運用

- 日次スモークテスト
  - `System/mac_mini/agent_orchestrator/config.yaml` の `addness_smoke_test`
  - 毎日 06:45 に `smoke-test` を実行する
  - 最新結果は `System/data/addness_smoke_test_latest.json`
- 行動ログ追従
  - `System/mac_mini/agent_orchestrator/config.yaml` の `addness_activity_watch`
  - 毎日 08:55 に `activity-summary --save-report` を実行する
  - 最新集計は `System/data/addness_activity_summary_latest.json`
- 監査ログ
  - `System/data/addness_audit_log.jsonl`
  - Addness の write 系操作を時系列で追える

## 主なファイル

- `goal-tree.md`
  Addness の全体ゴールツリー。巨大だが最重要の運用 knowledge
- `actionable-tasks.md`
  いま実行対象になっているタスク一覧
- `funnel_structure.md`
  導線・ファネル構造の把握
- `zapier_structure.md`
  Zapier の relay layer と current pattern
- `lstep_accounts_analysis.md`
  Lステップ運用とアカウント構造
- `meta_ads_大当たりCR分析.md`
  勝ち CR の分析 knowledge
- `dpro_*.md`, `ds_insight_evaluation.md`, `market_trends.md`
  外部調査・市場観察
- `ui_operations.md`
  Addness UI の操作 knowledge
- `System/hinata/addness_cli.py`
  Codex / 秘書が使う Addness 操作 CLI。ゴール作成・更新・コメント・AI相談・行動ログ集計・スモークテストの入口
- `System/line_bot_local/tool_registry.json`
  秘書側の `addness_ops` 定義。CLI で使える操作を秘書からも呼べるようにする入口
- `System/data/addness_audit_log.jsonl`
  Addness write 系操作の監査ログ
- `System/data/addness_activity_summary_latest.json`
  Addness 行動ログ集計の latest
- `System/data/addness_smoke_test_latest.json`
  Addness 日次スモークテストの latest
- `proactive_output/`
  legacy の成果物出力先

## 導線を読む最初の入口

- まず `何を変えたいか` を次の 6 分類に切る
  - `LP / thanks / 会員サイトの見え方や CTA`
  - `登録経路や計測の切り方`
  - `メールの件名 / 本文 / 配信順`
  - `LINE の着地先`
  - `LINE登録後のタグ / シナリオ / 面談化`
  - `商品 / 決済 / 会員サイト解放`
- 分類できたら、開く正本は次で固定する
  - `funnel_structure.md`
    - 導線全体の current 配線と、どのツールを見るべきかの切り分け
  - `utage_structure.md`
    - `page / form / scenario / product / action / site` の exact 手順
  - `zapier_structure.md`
    - `UTAGE webhook -> Zapier -> Mailchimp` relay の exact 読み方
  - `lstep_accounts_analysis.md` と `Master/knowledge/lstep_structure.md`
    - LINE登録後の `流入経路 / タグ / シナリオ / テンプレート`
- 迷った時の原則
  - LP やメール本文に見えている URL を正本と見なさない
  - LINE の差し替えは、まず short.io と URL管理シートを正本として見る
  - 同じページで流入元だけ分けたい時は、まず `登録経路` や short.io を疑い、安易にページ複製しない
  - 最後の判定は `実際に押した時の挙動` で行う

## 現在地と100点との差分

### 100点の定義

- 要件として
  - 文章
  - 素材
  - カスタマージャーニー
  が渡されれば
- どのツールで
  - 何を作るか
  - どこに置くか
  - どの設定をつなぐか
  を迷わず判断でき
- 速く
- 事故なく
- 既存品質以上で
  実装できる状態

### 100点の見方

100点は、項目を全部触れることではない。

次の構造を持てている状態を 100 点に近いとみなす。
- 役割
- ゴール
- 必要変数
- ワークフロー
- NG
- 正誤判断

つまり、`何ができるか` より先に、`何のために存在し、何が正しく、何が間違いかを説明できるか` を見る。

### Master と Skills の役割

- `Master`
  - この案件、この会社、この current 運用で判断を揃えるための正本
  - account 役割
  - current / legacy
  - 命名規則
  - Addness 固有の代表例
- `Skills`
  - 会社をまたいでも再利用できる実行の型
  - exact 手順
  - NG
  - 正誤判断
  - 入力変数

2026-03-13 時点で、導線系では次を `Skills/2_導線/` に昇格した。
- `lstep-standard-message-operations`
- `lstep-carousel-message-operations`
- `lstep-flex-message-operations`
- `lstep-template-review-operations`
- `lstep-answer-form-operations`
- `lstep-template-pack-operations`
- `lstep-action-management-operations`
- `lstep-rich-menu-operations`
- `lstep-broadcast-operations`
- `lstep-scenario-operations`
- `lstep-landing-operations`
- `lstep-tag-management-operations`
- `lstep-event-reservation-operations`
- `lstep-cross-analysis-operations`
- `utage-page-operations`
- `utage-tracking-operations`
- `utage-event-operations`
- `utage-product-detail-action-operations`
- `utage-member-site-operations`
- `utage-video-media-operations`
- `mailchimp-journey-operations`
- `mailchimp-campaign-operations`
- `mailchimp-tag-segment-operations`
- `mailchimp-report-operations`
- `zapier-webhook-mailchimp-relay-operations`

### 10点に置く条件

- 最初の入口を誤らない
- exact な UI / API 手順で迷わない
- セッション切れや current / legacy の罠を事前に避けられる
- 保存、送信、削除まで含めて短時間で再現できる
- 例外発生時も、どこを見ればよいか分かる

つまり、`最終的にできた` では 10 点にしない。`迷わず / 速く / 事故なく / 再現できた` 時だけ 10 点に置く。

### 目的とワークフローの関係

- 目的が先
- ワークフローは後

ワークフローは `今の最適手順` であって、絶対ルールではない。
目的をより速く、安全に、再現性高く、高品質に達成できるなら、ワークフローは更新する。

### コンテンツの定義

- コンテンツとは、`コミュニケーションの手段であり、ユーザーをこちらが意図した認識に変換するもの`
- これは Addness 固有の定義ではなく、上位の判断原則として扱う
- 文章だけを指さない
  - メール本文
  - LINE テンプレート / Flex
  - LP の見出し / 画像 / 動画 / CTA
  - 会員サイトの案内文や講義構成
  を含む
- 良いコンテンツかどうかは、`見た目が整っているか` ではなく
  - 何の認識を変えたいのか
  - その接点で何をしてほしいのか
  - 次の接点へ滑らかにつながるか
  で判断する
- したがって、コンテンツは Mailchimp だけの話ではない
  - Lステップのテンプレート / Flex
  - UTAGE の LP / サンクス / 動画 / 会員サイト
  - 広告
  - SNS
  - 人が話すセミナーや個別相談
  まで含めた、全コミュニケーション領域の上位原則として扱う

### シームレスな顧客体験

- 販売導線設計のゴールは、`シームレスな顧客体験をコミュニケーションコンテンツ単位で描くこと`
- つなぎ目なく、エスカレーターのように自然に次の認識と次の行動へ進めるのが理想
- したがって Addness の導線実装では、各ツールを単体で最適化するのではなく
  - 前の接点で何を感じたか
  - 次の接点で何を理解させるか
  - 最終的に何を行動してほしいか
  を 1 本でつなげることを優先する

### コンテンツを読む共通フレーム

広告でも、SNSでも、メールでも、LINEでも、LPでも、会員サイトでも、まず次を同じ順番で見る。

1. 今この相手は何を誤解しているか
2. 今この相手に何が足りていないか
3. この接点で、どの認識を変えたいか
4. その結果、次にどの行動をしてほしいか
5. 次の接点でも文脈が滑らかにつながるか

つまり、良いコンテンツは `情報が多い` ことでも `見た目が整っている` ことでもなく、

- 誤解を解く
- 足りない認識を補う
- 次の行動を起こさせる
- 次の接点へ自然につなぐ

を 1 つの流れで成立させている。

逆に悪いコンテンツは、

- 何を変えたいかが曖昧
- 次の行動がぼやける
- 前後の接点と文脈が切れる
- promise と CTA がずれる

のどれかが起きている。

### コミュニケーションコンテンツの2分類

- 販売導線で扱うコンテンツは、大きく
  - `非リアルタイムコミュニケーション`
  - `リアルタイムコミュニケーション`
  に分かれる
- 非リアルタイム
  - メール
  - LINE テンプレート / Flex
  - LP
  - 動画
  - 音声
  - 会員サイト内の案内
  のように、自動化・複製しやすいコンテンツ
- リアルタイム
  - 個別相談
  - オンラインセミナー
  - オフラインイベント
  - 展示会
  のように、その場の相互作用が入るコンテンツ
- Addness の販売導線では、非リアルタイムで温度と認識を上げ、リアルタイムで最後の意思決定や深い納得を作る設計が多い
- したがって、各システムは
  - どちらのコンテンツを主に扱うか
  - その前後の接点とどうつなぐか
  まで含めて役割を定義する

### 役割の見方

システムはかなり広い意味で使う。

- 人
- Mailchimp や UTAGE や Lステップ のようなツール
- 人が作った AI エージェント

は、Addness の販売導線では全部 `役割を持ったシステム` として扱う。

したがって、`何ができるか` だけではなく、
- 何を入力として受け
- 何を変換し
- 何を出力し
- 次のどのシステムへ渡すか
まで定義できていないと、実務では `理解した` とみなさない。

役割は 1 層では見ない。

- `ツールそのものの役割`
  - そのツールが世の中で何をするためのものか
- `アドネス株式会社の販売導線における役割`
  - Addness の current business model の中で、そのツールを何のために使っているか

この 2 つを分けないと、一般論としては正しくても、Addness の実務ではズレる。

例:
- Mailchimp そのものは `メールマーケティング基盤`
- でも Addness では、`非リアルタイムの長文教育` を担い、認識と温度を段階的に変える本線
- UTAGE そのものは `オールインワンのマーケ・販売基盤`
- でも Addness では、`ページ / 購入 / 視聴 / 会員化` を成立させる実行基盤
- Lステップ そのものは `LINE 運用拡張ツール`
- でも Addness では、`状態管理と次行動の実行制御` を担う operational layer

さらに、実務では次の 8 視点で見る。

- 役割
- 入力
- 変換
- 出力
- 接続先
- 制約
- 失敗条件
- 正誤判断

### Addness の販売導線におけるシステム別の担当範囲

#### Mailchimp

- 一般役割
  - メール配信、自動化、segment 配信、レポートの基盤
- Addness での役割
  - 非リアルタイムの本線教育
  - みかみや商品に対する認識を変え、温度を上げる
  - 次の接点へ進む理由を作る
- どの状態の顧客を扱うか
  - `知らない`
  - `半信半疑`
  - `興味はあるがまだ動かない`
- どこまで変えるか
  - `理解している`
  - `信じられる`
  - `今動く理由がある`
  まで持っていく
- 主に扱うコンテンツ
  - 非リアルタイム
  - 長文ストーリー
  - authority
  - open loop
  - offer
  - urgency
- 次につなぐ先
  - short.io
  - UTAGE
  - LINE

#### Lステップ

- 一般役割
  - LINE 上の顧客管理、配信、タグ管理、予約、分析の基盤
- Addness での役割
  - 顧客の状態を管理し、その状態に応じて次の行動を起こさせる
  - リアルタイム接点の予約や、受講後の運用も支える
- どの状態の顧客を扱うか
  - `理解はした`
  - `動けていない`
  - `今どの状態かを管理したい`
- どこまで変えるか
  - `今やることが分かる`
  - `押すべきボタンが分かる`
  - `予約 / 返信 / 提出 / 参加` が実行される
- 主に扱うコンテンツ
  - 非リアルタイムの短い実務メッセージ
  - リアルタイム接点の案内
  - 予約
  - リマインド
  - CS
- 次につなぐ先
  - 予約ページ
  - UTAGE
  - short.io
  - LINE 内次メッセージ
- representative
  - `3月 スキルプラス合宿 集客`
    - `作業が進まない` を `この場なら前に進める` に変え、合宿予約へ送る
  - `ゴール設定1on1予約案内`
    - `何をすればよいか分からない` を `まず1on1予約` に変え、タグも同時に作る
  - `【障害報告】外部システム障害の影響に関するお知らせ`
    - 不安と混乱を減らし、問い合わせや離脱を防ぐ
- 実物レビューの標準
  - 仕様書だけを見せず、正しい account 内で `ZZ_TEST_YYYYMMDD_用途` の隔離テストを作る
  - タグ、テンプレート、流入経路は同名で揃える
  - review 時は
    - 何を作ったか
    - どの edit URL を見ればよいか
    - 何を見てほしいか
    を短く添える
  - 2026-03-12 の実例
    - account: `スキルプラス【サポートLINE】`
    - テスト名は `ZZ_TEST_YYYYMMDD_用途`

#### UTAGE

- 一般役割
  - LP、決済、会員サイト、商品管理、動画管理などを持つ販売基盤
- Addness での役割
  - 顧客接点を登録、購入、視聴、会員化に変換する
  - 非リアルタイムコンテンツを、実際の行動と体験に変える
- どの状態の顧客を扱うか
  - `興味はある`
  - `登録したい`
  - `購入したい`
  - `受講したい`
- どこまで変えるか
  - `登録した`
  - `購入した`
  - `視聴した`
  - `会員サイトへ入れた`
- 主に扱うコンテンツ
  - LP
  - サンクス
  - VSL / セールスページ
  - 会員サイト
  - 講義
- 次につなぐ先
  - Mailchimp
  - Lステップ
  - 会員サイト内次導線
  - spreadsheet / Zapier

#### short.io

- 一般役割
  - 短縮 URL、差し替え、クリック分析
- Addness での役割
  - 導線リンクの正本
  - リンク失効対策
  - 差し替えの安全装置
  - クリック計測の入口
- 顧客に直接やること
  - 認識変容はしない
  - 顧客体験を壊さず、安定して目的地へ送る

#### Zapier

- 一般役割
  - ツール間連携、自動化
- Addness での役割
  - relay layer
  - event を tag や外部記録へ変換する
  - 既存導線を裏でつなぐ
- 顧客に直接やること
  - 認識変容もしない
  - front 体験も作らない
  - ただし relay を誤ると downstream 全体が崩れる

### Addness の current 販売導線での基本シーケンス

- `広告 / SNS`
  - 冷たい見込み客を集める
- `UTAGE LP`
  - 登録、オプトイン、視聴開始の入口を作る
- `Mailchimp`
  - 長文教育で認識と温度を上げる
- `Lステップ`
  - 状態を管理し、予約や返信など次行動を起こさせる
- `UTAGE`
  - 登録、購入、会員化、講義視聴を成立させる
- `Lステップ サポート / 予約系`
  - 受講後運用、イベント、CS を回す

つまり Addness の current では、

- `UTAGE = 入口と体験基盤`
- `Mailchimp = 教育本線`
- `Lステップ = 状態制御と実行`
- `short.io = リンク正本`
- `Zapier = relay`

の順でつなぐとズレにくい。

### 現在の自己評価

- Lステップ: `9.6 / 10`
- UTAGE: `9.0 / 10`
- Mailchimp: `8.4 / 10`
- short.io: `9.5 / 10`
- Zapier: `8.1 / 10`
- 全体理解: `8.9 / 10`

### いまの最優先

- いま優先するのは `見た目の磨き込み` ではなく、`どんな依頼でも正しくミスなく構築できること`
- 例えば Lステップ の `フレックスメッセージ` なら、現時点では内容 quality の 60 点 / 100 点評価を上げるより先に
  - 正しい入口を最初から選べる
  - 画像 / テキスト / ボタン / アクションを迷わず入れられる
  - `テスト送信`
  - 後片付け
  まで exact に再現できることを優先する
- 同じ考え方を
  - UTAGE の `ページ / 商品 / detail / アクション / 会員サイト`
  - Mailchimp の `Journey / Campaign / tag / CTA`
  - Zapier の `trigger / action / relay`
  にも適用する
- 2026-03-14 時点で、Lステップの reusable skill に昇格済みなのは
  - `標準メッセージ`
  - `カルーセルメッセージ(新方式)`
  - `フレックスメッセージ`
  - `テンプレートパック`
  - `テンプレートレビュー`
  - `回答フォーム`
  - `アクション管理`
  - `一斉配信`
  - `シナリオ配信`
  - `流入経路分析`
  - `タグ管理`
  - `イベント予約`
  - `クロス分析`
  です
- `自動応答` はまだ representative と live exact 手順が薄いので、現時点では `Master/knowledge/lstep_structure.md` 側に留める
- 2026-03-13 の current では、Lステップ は browser 上でログイン済みに見えても `python3 System/scripts/lstep_auth.py` が `auth_alive=false` を返すことがあった
- したがって Lステップ の live exact 作業は、毎回 `auth_alive=true` を開始条件にする

この再採点の理由
- Lステップ
  - `フレックスメッセージ` は
    - 作成
    - `甲原 海人` への `テスト送信`
    - 削除
    まで exact に通った
  - `GET /api/templates` から `form_type / editor_version` を使って
    - `標準メッセージ`
    - `カルーセルメッセージ(新方式)`
    - `フレックスメッセージ`
    - `テンプレートパック`
    を機械的に判定できる
  - current の generic edit 入口は `/line/template/edit/{id}?group={group}` で、
    - `標準メッセージ` はそのまま
    - `カルーセルメッセージ(新方式)` は `edit_v2`
    - `フレックスメッセージ` は `edit_v3?editMessage=1`
    - `テンプレートパック` は `line/eggpack/show/{id}`
    に流れるところまで固定できた
  - current 実例を使って
    - `標準メッセージ = 長文説明 / simple CTA`
    - `カルーセルメッセージ(新方式) = 複数 card の比較 / 選択`
    - `フレックスメッセージ = 視覚階層の強い重要告知 / main CTA`
  - representative template を
    - `SNS活用 1on1無料相談会`
    - `▼無料相談はこちら【YouTube切り抜き 無料相談会】`
    - `YouTube切り抜き 無料相談会告知`
    - `3月 スキルプラス合宿 集客`
    で分解し、`何の認識を変えて / 何を行動させるか` まで正本化できた
    - `テンプレートパック = message 群の container`
    の使い分けを一段深く固定できた
  - `テンプレート -> 新しいテンプレート -> フレックスメッセージ -> edit メッセージを作成`
    の current 導線と、
    `ボタン -> アクション設定 -> URLを開く`
    の exact 手順も live で固定できた
  - `画像を入れる / テキストを入れる / アクション設定 / テスト送信 / 後片付け`
    の current 手順はかなり固まった
  - さらに `標準メッセージ` と `カルーセルメッセージ(新方式)` も
    - 作成
    - `甲原 海人` への `テスト送信`
    - 削除
    まで live で通した
  - さらに `テンプレートパック` も
    - pack 作成
    - step 追加
    - `甲原 海人` への `テスト送信`
    - step 削除
    - pack 削除
    まで live で通した
  - ただし live の開始条件は `画面上の見た目ログイン` ではない
  - browser 上でログイン済みに見えても、`python3 System/scripts/lstep_auth.py` が `auth_alive=false` を返すことがある
  - したがって exact な live 作業の前提は、毎回 `auth_alive=true` を確認すること
  - `アクション管理` も current の field と save route までは exact に取れた
    - 一覧: `GET /api/actions?page=1`
    - 詳細: `GET /api/actions/{id}`
    - save: `POST /api/action/register`
  - ただし `新しいアクション -> 保存 -> 削除` の end-to-end はまだ未固定
  - そのうえで、既存 high-quality template の分解、action が多い実戦パターン、見た目品質の再現性にはまだ強化余地がある
- UTAGE
  - 構造理解は高いが、page code 領域や current 改修パターンでまだ迷いが残る
  - 新規で `ページ -> 商品 -> detail -> action -> 会員サイト解放` を end-to-end で無迷い実装した実績はまだ薄い
- Mailchimp
  - Journey / Campaign の役割は固い
  - ただし current / legacy copy の読み分けと builder 操作で、まだ representative を増やす余地がある
  - `認識変換` の観点で本文を読む厚みも、まだ増やす必要がある
- short.io
  - 役割、判断、台帳運用、API までかなり固い
  - ただし実案件を複数本通して完全に無迷いとまではまだ言わない
- Zapier
  - visible current 25本の family 分布まで確認できた
  - current 主戦場が `Webhooks by Zapier -> Mailchimp Add/Update Subscriber` だと実測で押さえられた
  - `Create` 入口は `Untitled Zap / Draft / sandbox` から始まり、開いただけで `Untitled Zap` draft が残ることを確認した
  - `Webhooks by Zapier -> Catch Hook` と `Mailchimp -> Add/Update Subscriber` を create builder 上で exact に辿れた
  - `Mailchimp アドネス株式会社 #4` の account 選択と、`Audience* / Subscriber Email* / Tag(s)` などの field 名まで確認した
  - `Rename`、`Folder` (`Zap details`)、`Delete Zap` を実際の draft で通し、assets 一覧への反映と後片付けまで確認した
  - `Publish` は必須項目不足だと disabled のままで、`Status` に `Please test this step` と `Please set up the required fields` が出るところまで確認した
  - ただし current family 外の relay 作成はまだ余地がある
  
この採点は、`最終的にできた` ではなく、`最初の入口を誤らず、迷わず、速く、安全に end-to-end を再現できるか` を基準にしている。

### Lステップ

- 役割
  - LINE 上で `状態を持った顧客` を制御し、次の行動を実行させる
- 入力
  - 流入経路
  - タグ
  - 回答フォーム回答
  - 予約状態
  - 配信対象条件
- 変換
  - 顧客の `状態` を更新する
  - `今の自分に必要な次の一歩` を明確にする
  - `分かったけど動けない` を `今何をすればいいか分かる` に変える
- 出力
  - テンプレート / Flex
  - シナリオ配信
  - タグ更新
  - 予約導線
  - 実務連絡
- 接続先
  - LINE 内の次 message
  - 予約ページ
  - short.io
  - UTAGE
- 制約
  - 長文の世界観教育には向かない
  - 深い心理変容の本線には向かない
- 失敗条件
  - タグ設計が弱く、状態と message がずれる
  - 1 通に役割を詰め込み、何をしてほしいか分からなくなる
  - URL や action がずれて誤導線になる
- 正誤判断
  - 良い: 状態に合う短い message で、次の行動が 1 つに絞られている
  - 悪い: 認識変容まで 1 通でやろうとして重くなる

- かなりできる
  - テンプレート
  - 流入経路
  - タグ
  - リッチメニュー
  - 回答フォーム
  - 一斉配信
  - イベント予約
  - カレンダー予約
  - クロス分析
- ここまで live で exact 画面確認済み
  - `【予約窓口】スキルプラス合宿` で
    - 流入経路
    - クロス分析
    - イベント予約
    - カレンダー予約
    - タグ管理
    - 回答フォーム
    - 一斉配信
  - `スキルプラス【サポートLINE】` で
    - 流入経路
    - タグ管理
    - 回答フォーム
    - 一斉配信
    - リッチメニュー
    - クロス分析
  - 役割理解だけでなく、主要画面の exact UI も `スキルプラス【サポートLINE】` まで current 反映済み
  - `アクション管理` の create modal で
    - `テンプレート送信`
    - `タグ操作`
    - `シナリオ操作`
    - `メニュー操作`
    - `イベント予約操作`
    の具体 field まで確認済み
  - template editor 側では
    - `URL訪問時アクションを設定する場合は、サイト設定ページから設定`
    という current の責務分離も確認済み
  - シナリオ配信は
    - 一覧 = `/line/content/group?group={group_id}`
    - editor = `/line/content/{content_group_id}?group={group_id}`
    の current route を確認済み
  - シナリオ editor では row 単位に
    - `編集 / 挿入 / コピー / プレビュー / 別窓 / テスト / 削除`
    を使う構造まで確認済み
  - step 編集 modal では
    - `配信タイミング`
    - `pause`
    - `送信先を絞り込む`
    - `テンプレート詳細`
    - `アクションを設定しない / する`
    が 1 画面に並ぶ current 構造まで確認済み
  - つまり Lステップ の step は
    - いつ送るか
    - 誰に送るか
    - 何を送るか
    - 送信後に何を起こすか
    を同時に決める battlefield と理解している
  - クロス分析は `作成 -> 再読込 -> 削除` まで live テスト済み
    - `POST /line/board/edit`
    - `GET /api/board/data/{id}`
    - `DELETE /api/boards/{id}`
    まで実確認済み
  - リッチメニューは current edit 画面の内部項目まで fixed
    - `タイトル / フォルダ / 初期状態 / 各ボタンの URL・テンプレ・action・回答フォーム・その他`
    - `一覧へ戻る / 保存`
    まで確認済み
  - ログイン補助も固定済み
    - `python3 System/scripts/lstep_login_helper.py --target <開きたいURL>`
    - ログイン済みならそのまま target を開く
    - 未ログインなら `System/credentials/lstep.json` から自動入力する
    - reCAPTCHA の画像 challenge が出た場合だけ手動確認が必要
- 残差
  - hidden / legacy / 命名規則違反の判断辞書をさらに増やす
  - 特に `旧 / 作成中 / 下書き / 日付付き` が混在する folder を、実導線参照込みで切るサンプルを増やす

### UTAGE

- 役割
  - 顧客接点を `登録 / 購入 / 視聴 / 会員化` に変換する販売実行システム
- 入力
  - 流入元
  - 登録経路
  - ページ閲覧
  - フォーム入力
  - 商品選択
  - 決済情報
- 変換
  - `興味はある` を `登録する / 買う / 視聴する / 受講する` に変える
  - 認識変容の一部を page / video / sales content 上で担う
- 出力
  - 登録完了
  - 次ページ遷移
  - 商品購入
  - action 実行
  - 会員サイト解放
- 接続先
  - Mailchimp
  - Lステップ
  - short.io
  - スプレッドシート
  - Zapier
- 制約
  - メール本線の長期教育は主戦場ではない
  - 細かい状態配信の制御は Lステップ ほど強くない
- 失敗条件
  - 見た目だけ整えて接続がずれる
  - 登録経路の切り方を誤って分析軸を壊す
  - product / detail / action / bundle の分離が甘く、販売後体験が壊れる
- 正誤判断
  - 良い: 何を理解させ、何を押させ、次にどこへ進ませるかが page と設定で一致している
  - 悪い: デザインはあるが、接続や次の体験がずれている
- かなりできる
  - ファネル
  - ページ
  - 商品
  - detail
  - アクション
  - 会員サイト
  - バンドルコース
  - 講義
  - 動画管理
  - メディア管理
- current で理解できていること
  - Mailchimp がメール本線
  - UTAGE はページ / 会員サイト / 商品 / action の基盤
  - `【センサーズ関連】` は過去のメインファネル群として重要
  - `product -> detail -> action -> 会員サイト解放` の representative path は実値で確認済み
  - representative funnel の `データ(合算) / データ(日別) / 登録経路` も live で確認済み
    - 例: `AI：メインファネル_Meta広告`
    - funnel id: `TXUOxBYkYr9e`
    - `.../data`
    - `.../data/daily`
    - `.../tracking`
    - representative create route: `/funnel/d0imwFvGWVbA/tracking/create`
    - current create 画面は `グループ / 管理名称 / ファネルステップ / ページ / 保存` を先に見る
  - representative page も current 実装を複数本見ている
    - `【スキルプラス】ユーザー登録ページ`
      - funnel id: `mYSG4RqRbFiH`
      - representative row: `【クレカ】ユーザー登録`
      - edit: `/funnel/mYSG4RqRbFiH/page/ScGYTZjaPHHX/edit`
      - preview: `/page/ScGYTZjaPHHX?preview=true`
      - LP と同じ `ページ設定` タブを持つが、実務では `フォーム / 商品詳細管理 / 購入後アクション / バンドルコース` を先に見る
  - `登録経路` は「広告IDだから分ける」ではなく、「どこから来たかを知りたい時に分ける」分析軸として理解している
  - `登録経路` の create route と field も確認済み
    - `.../tracking/create`
    - `グループ / 管理名称 / ファネルステップ / ページ`
  - current page editor の settings UI も live で固定できた
    - `基本情報`
    - `デザイン`
    - `高速表示モード`
    - `メタデータ・検索`
    - `カスタムJS`
    - `カスタムCSS`
  - `カスタムJS` は
    - `headタグの最後`
    - `bodyタグの最初`
    - `bodyタグの最後`
    の3箇所
  - `高速表示モード` は current UI 上では `is_high_speed_mode` の切替のみ visible
    で、`first_view_css` は独立 field としては見えていない
  - `utage_login_helper.py` は edit 画面でも自動ログイン判定できるように補強済み
  - runtime の Vue app では `#app.__vue_app__._container._vnode.component.data.page.first_view_css`
    に `first_view_css` 実値が載っていることを確認済み
  - edit HTML には current save endpoint として
    - `/update/basic`
    - `/update/pcwidth`
    - `/update/meta`
    - `/update/js`
    - `/update/css`
    - `/update/speed`
    - `/update/ads`
    - `/update/deadline`
    - `/update/onetimeoffer`
    - `/update/password`
    が埋まっていることも確認済み
  - ログイン補助も固定済み
    - `python3 System/scripts/utage_login_helper.py --target <開きたいURL>`
  - 商品販売設定の current 標準手順も live route まで固定できた
    - `商品追加 = /product/create`
    - `detail 追加 = /product/{product_id}/detail/create`
    - `action 編集 = /action/{action_id}/edit`
    - `bundle 編集 = /site/{site_id}/bundle/{bundle_id}/edit`
  - code 領域の current 使い分けもかなり固定できた
    - `js_head = 計測タグ`
    - `js_body_top = 自動遷移 / 初回即時演出`
    - `js_body = 遅延でよい補助処理`
    - `css = page 全体補正`
    - `first_view_css = 高速表示レイヤーの FV 補正`
  - `【センサーズ関連】` の representative public page でも
    - `15分OTO は content page`
    - `ロードマップ作成会は visible CTA に停止中 LIFF が残る`
    という差分まで current 反映済み
- 残差
  - representative page をさらに増やし、code 領域の good / bad 事例を厚くする
  - `first_view_css` を触るべきケースと触るべきでないケースの具体例をさらに増やす

### Mailchimp

- 役割
  - 認識と温度を設計的に変えるメール nurture システム
- 入力
  - audience
  - tag
  - segment
  - copy
  - CTA
- 変換
  - `知らない / 半信半疑 / 今は動かない` を
  - `理解している / 欲しい / 今動く理由がある` に変える
  - 人物ストーリー、authority、悩みの言語化、urgency、offer 理解を進める
- 出力
  - Journey
  - Campaign
  - open / click / report
- 接続先
  - short.io
  - UTAGE
  - LINE
- 制約
  - 予約実務の細かい案内には向かない
  - 購入や会員サイト解放そのものは担わない
- 失敗条件
  - 1 通ごとの役割が曖昧で、認識が進まない
  - CTA が content の文脈と合っていない
  - hyperlink mismatch で意図しない URL に飛ばす
- 正誤判断
  - 良い: 1通ごとの役割が明確で、前後の通数と連続して認識を進める
  - 悪い: ただ情報を送っているだけで、認識変換や次の行動が設計されていない
  - リアルタイムの細かな状態制御
- helper でかなり固くなった部分
  - `mailchimp_journey_snapshot.py --journey-id 10934`
    - `email_step_summary`
    - `current_email_steps`
    - `email_steps[].state_reason`
    を返せる
  - `mailchimp_journey_snapshot.py --list-current --count 2`
    で `current` と `paused_with_queue` を横断抽出できる
  - `mailchimp_campaign_snapshot.py --campaign-id e836af06b7`
    で `click-details` 集計済みの `top_clicked_url` を返せる
- representative 実測
  - `10934 / UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
    - `total = 36`
    - `current = 12`
    - `queue_zero = 24`
  - `10932 / UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
    - `started = 18,733`
    - `in_progress = 4,880`
    - `completed = 13,852`
    - `current = 5`
    - `paused_with_queue = 1`
  - `10729 / UTAGE_AIカレッジ_X広告_個別3日間シナリオ`
    - `current = 1`
    - `paused_with_queue = 1`
  - `e836af06b7 / 3/11 AIキャリアセミナーPR_2通目`
    - `top_clicked_url = direct LINE`
    - `top_clicked_total_clicks = 149`
    - `secondary_clicked_url = https://addness.co.jp/`
    - `secondary_clicked_total_clicks = 33`

### short.io

- 役割
  - リンク管理、差し替え、クリック分析
- アドネスでの役割
  - 導線リンクの正本基盤
  - 失効対策、差し替え容易性、クリック計測
- 顧客の何を変えるか
  - 顧客の認識を変えるツールではない
  - 顧客体験を壊さず安定させるための裏方
- 任せないこと
  - 教育
  - オファー提示
  - 予約や購入の本体処理
- かなり見えている
  - current の本線が Mailchimp 側で動いていること
  - audience
  - trigger tag
  - AI / SNS の 7桁本線
  - 一部の個別3日間シナリオ
  - active queue の考え方
- recent sending も current 実値で確認済み
  - 例
    - `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
    - `UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
  - `UTAGE_AIカレッジ_X広告_7桁オプトイン`
  - `UTAGE_AI_YouTubeメインファネル_7桁オプトイン`
- regular campaign の current 代表例も実値で確認済み
  - `3/11 AIキャリアセミナーPR_2通目`
    - `emails_sent = 255,250`
    - `open_rate = 10.59%`
    - `click_rate = 0.043%`
    - `main CTA = direct LINE`
    - `secondary CTA = https://addness.co.jp/`
  - `3/11 AIキャリアセミナーPR_1通目`
    - `emails_sent = 257,147`
    - `open_rate = 9.29%`
    - `click_rate = 0.04%`
  - `3/10 セミナーPR_3通目 (フリープラン)`
    - `emails_sent = 5,044`
    - `open_rate = 38.07%`
    - `click_rate = 0.57%`
  - `3/10 セミナーPR_1通目 (フリープラン)`
    - `emails_sent = 5,012`
    - `open_rate = 38.55%`
    - `click_rate = 1.03%`
  - つまり current の regular campaign は
    - 全体配信系は `開封 9%台 / クリック 0.04%台`
    - フリープラン絞り込みは `開封 38%台 / クリック 0.5〜1.0%台`
    と差がかなり大きい
  - ただし今後こちらが新規で作る regular campaign の `main CTA` は `short.io` を標準にする
    - current に direct LIFF の例が残っていても、それは historical 実装として扱う
- API ベースの current 読解手順も固定できた
  - `GET /customer-journeys/journeys`
    - `journey_name`
    - `status`
    - `stats.started / in_progress / completed`
    を先に見る
  - `GET /customer-journeys/journeys/{id}/steps`
    - `step_type = action-send_email`
    - `status = active`
    - `stats.queue_count > 0`
    で「今も送信待ちが残っているメール」だけを拾う
  - 同じレスポンスの
    - `action_details.email.settings.title`
    - `action_details.email.settings.subject_line`
    - `action_details.email.emails_sent`
    で、メール名と件名と送信実績を読む
  - `GET /campaigns/{campaign_id}/content`
    で本文 HTML を取得し、UTAGE / short.io / 外部リンクを抜く
  - `GET /reports/{campaign_id}/click-details`
    で実際に押されている URL を読む
  - current のメールは short.io を介して UTAGE ページに送る前提が多いので、`click-details -> short.io -> UTAGE data` を 1 本で見るのが次の標準
- current のコンテンツ意図も読み始めている
  - 本線 7桁オプトインは `人物ストーリー / authority / open loop` で教育する
  - 途中の `コンサル / 本気オファー` は距離を縮めて直CTAへ寄せる
  - `スキルプラスフリープラン` は無料オファーで横展開する
  - `個別3日間 / プロンプト企画3日目 / 本気コンサルRe` は締切と実例で最後の一押しをする
  - `3/11 AIキャリアセミナーPR` のような regular campaign は、既存認知を前提に短く反応を取りにいく `単発PR告知型`
  - 直近の sent regular campaign は実測上 `direct LIFF` が主CTAに多い
  - ただし `AIキャンプ` や `みかみの秘密合宿プロモ` のように、UTAGE ページを main CTA にする regular campaign もある
  - つまり current メールは
    - `本線ストーリー型`
    - `直オファー型`
    - `横展開オファー型`
    - `短期締切ブースト型`
    - `単発PR告知型`
    の 5 型で読むとズレにくい
  - `スキルプラスフリープラン` は無料オファーで口を広げる横展開
  - `個別3日間` は `あなた専用 / 反響 / 締切` の順で面談系CTAに押し込む
  - 本文まで確認できた representative 例
    - AI本線1通目: `東大生社長みかみがAI未経験から年収2億ベースで稼ぐまでの軌跡`
    - AI直オファー: `【緊急告知！！】直接コンサルしましょうか？笑`
    - SNS本線1通目: `元東大生社長みかみが年商2億稼ぐまでの軌跡`
    - SNS直オファー: `間も無く締め切ります`
    - SNS個別3日間: `【今だけ無料！】"あなた専用" SNS運用 1st副業スタートプログラム開催！！`
  - current を誤読しない基準も固まった
  - `journey が sending` でも、`step が paused` なら current メール扱いしない
  - `last_started_at` だけでは current 判定しない
  - `queue_count > 0` を最優先で見る
  - `copy` が付くものでも、queue が残っていれば current として扱う
  - `active` でも `queue_count = 0` なら、今この瞬間に送信待ちが残っている current step とは読まない
  - current 実例として
    - `スキルプラスフリープラン1通目 (copy 03) = queue 191 / sent 31,173`
    - `AI新卒プロモーション_1通目(4/3) (copy 02) = sent 269,919` でも current 実績として読む
    - `センサーズFB広告_本気コンサルオファー (copy 05) = queue 1 / sent 17,987`
    - `AIカレッジFB広告_個別3日間シナリオ_3日目 (copy 02) = queue 1 / sent 28,146`
    を確認済み
- current の代表例
  - `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
    - `started 31,902 / in_progress 4,504 / completed 27,394`
    - `スキルプラスフリープラン1〜5通目`
    - `AIカレッジFB広告_プロンプト企画`
    - `AIカレッジFB広告_SNS企画`
    - `フリープラン岡田結実`
    などで queue が残っている
  - `UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
    - `started 18,733 / in_progress 4,880 / completed 13,852`
    - current queue-positive は
      - `本気コンサルRe`
      - `スキルプラスフリープラン1〜4通目 (copy 02/03)`
    - `センサーズFB広告_本気コンサルオファー (copy 05)` や 7桁本線 1〜8 通目は `active` でも `queue = 0`
  - `UTAGE_AIカレッジ_X広告_7桁オプトイン`
    - `started 27,571 / in_progress 2,287 / completed 25,281`
    - current queue-positive は
      - `スキルプラスフリープラン1〜5通目`
      - `メインシナリオ2 / 3 / 5 / 7通目`
      - `AI習得レッスン2〜5日目`
      - `プロンプト企画2〜3日目`
      - `SNS企画2〜3日目`
      - `個別誘導1〜7通目`
- 本文と click report まで current 実値で確認済み
  - 例: AI Facebook の `スキルプラスフリープラン1通目 (copy 03)` は本文内に `school.addness.co.jp/p/TzYRwepfqzFq?...` を持つ
  - 例: click report では `skill.addness.co.jp/ytad-ai2A` のような short.io が実際に押されている
  - ただし regular campaign の current 代表例では、main CTA が short.io ではなく direct LIFF のものもある
    - `3/11 AIキャリアセミナーPR_2通目`
    - `3/11 AIキャリアセミナーPR_1通目`
    - `3/10 セミナーPR_3通目 (フリープラン)`
    - `3/10 セミナーPR_1通目 (フリープラン)`
  - この 4 本は click-details でも content HTML でも、main CTA が direct LIFF として確認できた
  - つまり current では
    - Journey 本線 = short.io や UTAGE ページが多い
    - regular campaign = direct LIFF が main CTA の例もある
    と分けて読む方がズレにくい
  - したがって URL 検証も
    - Journey 本線では `short.io -> UTAGE or LINE`
    - regular campaign では current 実装に direct LIFF もある
    のどちらかを、実際に押して確認する前提で運用する
  - ただし今後の新規実装では、Journey / Campaign を問わず `main CTA = short.io` を正とする
- live UI の exact 画面も確認済み
  - ログインは `login.mailchimp.com` -> `login/unifiedLoginPost` -> `us5.admin.mailchimp.com/login/verify`
  - `python3 System/scripts/mailchimp_login_helper.py --target <開きたいURL>` で email / password 自動入力までは固定済み
  - 2段階認証は `Send code via SMS` -> LINE の `Mailchimp認証` グループでコード確認 -> verify 画面へ入力 の順
  - Automations 一覧には `Build from scratch` `Choose flow template` `Search by name` `Status` `Objective` `Sort by: Last created` がある
  - `Build from scratch` から `customer-journey/create-new-journey/` に入り、`Name flow` `Audience` `Choose a trigger` の順で新規作成を始める
  - `Choose a trigger` を押した時点で `builder?id={id}&stepModal=trigger` に変わり draft を作るので、live テスト時は同セッションで `Actions -> Delete -> Delete flow` まで戻す
  - Journey 名クリックで `customer-journey/builder?id={id}` に入る
  - builder 上部には `Send Test Emails` `View Report` `Pause & Edit` `Save and close flow` がある
  - builder 本体では `Contact tagged ...` `Filter who can enter` `Send email ...` `Contact exits` を map 上で管理し、右パネルは `Data / Settings` で切り替える
  - `Tag added` trigger の current 画面では `Set a tag` `Filter who can enter` `Save Trigger` が出る
  - `View Report` は `customer-journey/report?id={id}` に入り
    - `Days active`
    - `Total started`
    - `Total in progress`
    - `Total completed`
    - `Open rate`
    - `Click rate`
    - `Unsubscribe rate`
    - `Delivery rate`
    を flow 単位で読む
  - tag は英語で作る前提に寄せる
  - 基本構造は `media_funnel_event`
  - Journey は `エバーグリーン用`
  - Campaign は `1回きりのセグメント配信用`
    として使い分ける前提
  - representative campaign
    - `3/11 AIキャリアセミナーPR_2通目` = `Subscribed` 全体へ 255,250 通
    - `3/10 セミナーPR_3通目 (フリープラン)` = `freeplan_Buy` tagged contacts に 5,044 通
  - current / legacy 判定辞書もかなり固定できた
    - `active + queue > 0 = current`
    - `active + queue = 0 + sentあり = completed but still valid`
    - `paused + sentあり = historical evidence`
    - `paused + queue 0 + sent 0 = draft / legacy candidate`
  - API でも `regular campaign` の create / content / delete が通ることを確認済み
    - `ZZ_TEST_DELETE_20260311` を作成し、本文設定後に削除して最終 `404` を確認
  - Campaign Manager の current route は `/campaigns/`
  - current の create 入口は `Campaign Manager -> Create -> campaigns/#/create-campaign`
  - row 上では `Regular email / Automation flow / Draft / Sent / Segment / Exclude` まで visible
- 残差
  - current 本線と legacy copy の辞書をさらに厚くする
  - `送信 -> 開封 -> クリック -> UTAGE訪問 -> コンバージョン` を 1 本で可視化する動線データ基盤はまだ未構築

### Zapier

- 役割
  - 複数システムの間で、状態とイベントを受け渡す relay layer
- 入力
  - UTAGE や Lステップ などから飛んでくる webhook payload
  - 一部のシート更新イベント
- 変換
  - business event を、Mailchimp tag や外部 API 呼び出しに変換する
  - `オプトインした / 購入した / 月額化した` という出来事を、次システムで実行可能な状態に変える
- 出力
  - Mailchimp の `Add/Update Subscriber`
  - 一部の webhook post
  - 一部のシート連携
- 接続先
  - UTAGE
  - Mailchimp
  - Google Sheets
  - 外部 API
- 制約
  - 顧客に見える表の体験は作らない
  - relay の誤りは downstream の tag / journey をまとめて壊す
- 失敗条件
  - 1 つの business event に対して tag が曖昧
  - webhook payload の key が変わり、email や event が正しく渡らない
  - current Zap と legacy Zap の見分けを誤る
- 正誤判断
  - 良い: 1 event = 1 meaning で tag や relay 先が明確
  - 悪い: 名前は似ているが event の意味がぶれ、どの Journey を起動するか読めない
- current で見えている主戦場
  - `Webhooks by Zapier -> Mailchimp Add/Update Subscriber`
  - Addness の front funnel relay は、ほぼこの型に集約
- representative 例
  - `Meta広告_秘密の部屋_オプトイン`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tag: `metaad_himitsu_optin`
  - `AIコンテンツ完全習得Live_購入時`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tag: `AIkontentuLive_Buy`
  - `AICAN_月額_購入時`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tag: `AICAN_monthly_buy`
  - `共通_秘密の部屋_年間プラン購入`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tag: `himitsu_yearly_buy`
  - `マインドセットコース_アクションマップ購入`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tag: `mindset_actionmap_buy`
    - `全コース` と並んで、course-specific 購入 relay の representative
  - `フリープラン入会時_女性訴求プロモーション`
    - trigger: `Catch Hook`
    - action: `Mailchimp Add/Update Subscriber`
    - tags: `freeplan_Buy_PR_woman`, `freeplan_Buy`
    - 本体 tag と promotion slice tag を同時に付ける representative
  - historical 例
    - `AI個別_SMS送信`
    - current 主戦場ではなく、`Google Sheets updated row -> external SMS API` の別パターン
- live UI と current 読解
  - 一覧は `https://zapier.com/app/assets/zaps`
  - editor は `https://zapier.com/editor/{zap_id}/published`
  - current の editor は `__NEXT_DATA__` に `zap.current_version.zdl` を持つ
  - `zdl.steps` を読むと
    - app
    - type
    - action
    - params
    を機械的に取れる
  - representative 例では、Mailchimp action は `memberCreate`、list は `アドネス株式会社` audience に固定されていた
  - helper は `python3 System/scripts/zapier_editor_snapshot.py <zap_id>` を使う
  - 今後 Addness 株式会社の業務で新しく作る Zapier 資産は、原則 `甲原` フォルダ配下に置く
  - 既存の current Zap は無理に移動せず、`新規は甲原、既存はそのまま読む` を運用ルールにする

### 動線データ基盤

- 目的
  - 分析用の可視化
  - マーケティング施策立案に直結するデータ収集
- 最初に追う主要変数
  - CPA
  - 個別相談数
  - 営業成約率
  - 解約率
- そのために必要な導線データ
  - メール送信数
  - 開封数 / 開封率
  - リンククリック数 / クリック率
  - UTAGE 訪問者数
  - コンバージョン数
- このレイヤーは CDP とは別で設計する前提

### short.io 詳細

- かなり見えている
  - `skill.addness.co.jp` を固定リンク基盤として使うこと
  - URL管理シートで台帳管理していること
  - LINE に送るリンクは必ず short.io で管理すること
  - BAN / 停止時のリンク失効対策として使っていること
  - クリック分析の API 入口があること
- 役割
  - 導線に置かれたリンクの正本を 1 箇所に集約し、設置箇所を触らずに差し替えられるようにすること
- ゴール
  - 命名、台帳、差し替え、分析が一貫していて、誰が見ても同じ意味に解釈できること
- 必要変数
  - 集客媒体
  - ファネル名
  - イベント名
  - 設置場所
  - 最終遷移先
  - 流入経路名
  - リンクタイトル
  - slug
  - フォルダ
- 判断フレーム
  - 新規作成: 設置場所、流入経路名、分析単位、ファネル名、イベント名のどれかが変わる
  - 既存差し替え: 役割、設置場所、流入経路名、分析単位は同じで、最終遷移先だけ変わる
  - 既存流用: 設置場所、役割、計測単位が同じで、分ける意味がない
- 設置場所の粒度
  - 通常は `媒体 × 導線 × メール or ページ`
  - 同じページ内の複数CTAは、分析を分けないなら同一 short.io でよい
- 正誤判断
  - 正しい: `リンクタイトル = 流入経路名`、URL管理シート更新まで完了、差し替えを short.io 側で完了
  - 間違い: とりあえず短縮して配る、台帳更新しない、設置箇所を先に直す、同じ遷移先だからという理由だけで流用する
- 実例
  - 新規作成: `meta-ai3 / xad-ai3 / ttad-ai3` は同じ LINE 送りでも媒体が違うので別 short.io
  - 差し替え: `metaad-sns5` は役割と設置場所が同じなら `元のURL` 差し替え
  - historical bridge: `sp3` は current 本線ではなく historical な橋渡し痕跡
  - current 実例: `im013` は `Instagram_SNS_直リストイン_ロードマップ作成会_013` で、`014` を増やすなら新規作成、`013` の送り先だけ変えるなら差し替え
  - current 実例: `prime-kanso` は `Mプライム合宿_口コミ用` で、同じ口コミ導線の UTAGE ページだけ変えるなら差し替え、別媒体に広げるなら新規作成
- 実行テンプレート
  - 依頼を受けたら `何の導線か / 何のためのリンクか / どこに置くか / どこへ送るか / 分析単位` を先に埋める
  - その後に `新規作成 / 差し替え / 流用` を判断する
- 完了判定
  - 新規作成: short.io 作成、タイトル整合、フォルダ整合、台帳更新
  - 差し替え: short.io 側だけで完了、設置箇所未修正、台帳更新
  - 流用: 理由説明可、分析を分ける要件なし
- Loom の運用動画からも current 作法を補強済み
  - 動画タイトルは `LSTEPの短縮URL作成と管理方法について📈`
  - 命名規則を守る
  - short.io でリンクを作る
  - スプレッドシートへ記録する
  - リンク先変更は設置箇所ではなく short.io 側で差し替える
  - Loom のチャプターも `作成手順 -> ツール紹介 -> 使い方 -> 管理方法 -> 差し替え -> まとめ` の順で、この運用が一連の標準手順として説明されている
  - さらに transcript から
    - `リンクタイトルは流入経路名と完全一致`
    - `カスタマイズ機能 -> 基本的なリンク編集`
    - `鉛筆ボタンから元URLを差し替える`
    - `最新日付もシートで更新する`
    まで fixed できた
- live UI の exact 画面も確認済み
  - dashboard は `ブランドリンク` が本体で、`短縮リンク / 元のリンク / クリック数 / コンバージョン数 / タグ / アクション` を一覧で持つ
  - quick create は `Paste URL here...` に元URLを入れて `リンクを作成` を押すと、その場で短縮URLが自動発行される
  - 作成直後に `path` を持つ編集フィールドが出るため、slug の最終調整は作成直後に行う前提
  - 一覧行の `アクション` には current UI で `編集 / 統計 / 共有 / Duplicate / 削除` が直接並ぶ
  - 既存リンク編集は `users/dashboard/{domainId}/links/{linkId}/edit/basic` に入る
  - `edit/basic` の左メニューには `基本的なリンク編集 / モバイルターゲティング / キャンペーントラッキング / 地域ターゲティング / 仮URL / リンククローキング / パスワード保護 / ロゴ付きQRコード / A/Bテスト / HTTPステータス / オープングラフメタデータ / リンク許可 / トラッキングコード / Links bundle` がある
  - 既存リンク統計は `users/dashboard/{domainId}/links/{linkId}/statistics` に入る
  - `edit/basic` では `path / title / originalURL / folderId / tag` を触り、下部の `SAVE / CANCEL` で確定する
  - current の差し替え導線は `dashboard -> 対象リンク検索 -> 行アクションの編集 -> 基本的なリンク編集 -> 元のURL差し替え -> SAVE`
  - non-production のテストリンク `HIh3ps` では、実際に `title` と `originalURL` を更新し、`変更は正常に保存されました` まで live 確認済み
  - `ドメイン統計` では `過去30日` を基準に、上位リンク / 都市 / 国 / ブラウザ / OS / リファラー / ソーシャルリファラー / ミディアム / ソース / キャンペーンまで見える
  - 個別リンク統計では `期間 / 統計 / 共有 / EDIT / 時間の経過に伴うメトリックの比較 / 総クリック数 / 人によるクリック / 上位の国 / 上位の都市 / 上位のブラウザ / 上位のOS / 上位のリファラー / 上位のソーシャルリファラー` が見える
  - `統合とAPI` は `app.short.io/settings/integrations` で、`API / ブラウザプラグイン / アプリケーション / Slack / Wordpress / Zapier / Make / GitHub Actions / MCP` に入れる
  - browser セッションでは `IndexedDB(shortio)` に `encrypted_jwt / encrytion_key / iv` があり、browser 内では復号できることも確認済み
  - ただし、運用として正しい自動化は `Integrations & API -> API` で secret API key を発行して行うべきで、browser JWT は current セッション解析に限定する
  - official docs 上の rate limit は、一般 API が 20〜50 RPS、統計 API が 60 RPM、bulk create が 5 request / 10 sec・1 回最大 1000 links
  - 実際に browser JWT で `https://api.short.io/links/...` を read-only で叩くと `401 認証エラー / 無効なAPIキー` になり、official API は secret API key 必須と確認できた
  - `Integrations & API -> API` で domain `1304048` 向けの secret API key を発行済み
  - `System/scripts/shortio_api_client.py` で、official API の
    - フォルダ一覧
    - リンク検索
    - 個別リンク統計
    を再取得できる
  - URL管理シート `【アドネス全体】URL管理シート` は、広告系 4 タブを非破壊で hidden の `広告（統合）` に集約したうえで、current 正本を `01_全体台帳` に移した
  - `00_役割と使い方` は削除済み
  - hidden backend は `01_全体台帳`
  - visible の作業タブは `集客媒体` ごとに分ける
  - visible タブは `共通 / Meta広告 / TikTok広告 / YouTube広告 / 𝕏広告 / LINE広告 / Yahoo広告 / リスティング広告 / アフィリエイト広告 / YouTube / 𝕏 / Instagram / Threads / TikTok / 一般検索 / 広報 / オフライン / その他`
  - `01_全体台帳` の列は `ファネル名 / 集客媒体 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
  - visible タブの列は `ファネル名 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
  - `リンクURL` と `遷移先リンク` は plain text ではなく、セル自体にリンク属性を持たせているため、そのままクリックできる
  - 更新順は `値を書き込む -> 体裁を整える -> リンク属性を付ける`。先にリンク属性を付けると、書式再適用で消える
  - `共通導線` の行は `共通` タブへ寄せる
  - 各タブ内の並び順は `センサーズ -> AI -> アドプロ -> スキルプラス -> ライトプラン -> 書籍 -> その他`
  - `リンクエラー用` の行は `広報` ではなく `その他` タブへ寄せる
  - visible タブでは、連続する同一 `ファネル名` を A列で縦結合する
  - visible タブの罫線は全範囲で統一する
  - old tab の `飛び先URL` は `遷移先リンク` に統合し、`最新（YYYY/MM/DD）` は行単位の `更新日` に正規化した
  - `未作成` の行は master / visible ともに削除した
  - 体裁は `スプレッドシート設計ルール` に合わせて、ヘッダー色、フィルタ、凍結、交互色、列幅、`切り詰める(CLIP)` を再適用した
  - `System/scripts/shortio_api_client.py sync-ads-sheet` で、まず `広告（統合）` の `遷移先 / 更新日` を short.io 実体と照合できる
  - `System/scripts/shortio_api_client.py rebuild-sheet-views` で、`01_全体台帳` から visible の集客媒体タブを再構築できる
  - `--delete-obsolete` 付きで実行済みなので、`00_役割と使い方` を含む旧タブ群は live シートから削除済み
  - `System/scripts/shortio_api_client.py audit-sheet` で台帳品質を監査できる
  - 実行結果として、`広告（統合）` の short.io 行を `379件` チェックし、`373件` の `遷移先 / 更新日` を actual 値で同期した
  - unresolved は `4件` で、`まだない` 2件を除くと、`YhBCLQ` と `metaad-light1` は short.io 実体が見つからない broken 候補と切れた
  - 新しい媒体タブ設計に移した後の監査では、`未作成` を除く残差は `0件` まで解消した
- 完了
  - 役割 / ゴール / 必要変数 / ワークフロー / NG / 正誤判断が fixed
  - current UI の `作成 / 編集 / 統計 / API` が exact に見えている
  - URL管理シートの広告系 4 タブを `広告（統合）` に集約済み
  - `広告（統合）` の `遷移先 / 更新日` を short.io 実体で同期できる
  - broken 候補まで検出できる

#### short.io を 100 点にする完了条件

- 役割を `リンク正本基盤` として説明できる
- 新規作成 / 差し替え / 既存流用を、理由つきで判断できる
- 作成から URL管理シート更新まで、抜けなく再現できる
- 既存リンク差し替えを current UI で exact に完了できる
- 統計画面から、最低限 `どのリンクがどこで押されているか` を読める
- クリック分析の自動取得方針を説明できる
- 実案件を 1 本、判断から記録まで通しても崩れない

### いちばん効く次の順番

1. Lステップを `9.6 -> 9.8〜10` へ上げる
2. UTAGE を `8.8 -> 9.3+` へ上げる
3. Mailchimp を `7.8 -> 9.0+` へ上げる
4. short.io は完了。次は Lステップ / UTAGE / Mailchimp に同じ型を横展開する

## 4層との対応

- 事実・観察・構造理解は `knowledge`
- 勝ち筋や禁止事項に圧縮されたら `rules`
- 実際に出した提案や成果物は本来 `output`

`proactive_output/` は既存コード互換のためここに残っているが、考え方としては `Master/output/` が正本入口。現在の役割は [proactive_output/README.md](/Users/koa800/Desktop/cursor/Master/addness/proactive_output/README.md) に明記した。

## このフォルダに置かないもの

- 甲原固有の人格・価値観
- 汎用化済みの原理
- ルールだけを抜き出した最終版

人格は `前提`、汎用原理は `Skills/`、最終ルールは `Master/rules/` を優先する。
