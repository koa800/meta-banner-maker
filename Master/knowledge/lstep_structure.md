# Lステップ 構造・操作ガイド

最終更新: 2026-03-13

## 概要

LステップはLINE公式アカウントの拡張ツール。LINE登録→育成→販売→CSの全導線をLステップ上で構築・自動化する。

### アドネスのビジネスフローにおけるLステップの位置づけ

```
広告集客（Meta広告/Google広告）
  → LP（オプトインページ）
    → LINE登録（Lステップへ）
      → 教育シナリオ（シナリオ配信/一斉配信）
        → オファー（VSL/セミナーセールス）
          → 購入（UTAGE決済）
            → CS/オンボーディング（Lステップ + SLS）
```

- **リストマーケティング**: 広告で温かい見込み客を集め、LINEで教育→オファーの流れ
- **販売導線のツール選択**: Lステップは分析機能に優れるがランニングコスト高。UTAGEはオールインワンでコスパ良
- **アカウントBAN対策**: メイン/サブのLINE分散、メールアドレス同時取得、エンゲージ低い層への配信除外

---

## アドネスのLステップ運用体制

### アカウントタイプの役割

| タイプ | 役割 |
|--------|------|
| **メイン** | ユーザーを1箇所に集めるためのアカウント |
| **サブ** | ユーザーにプロモーション施策を打つためのアカウント |
| **サポート** | バックエンド購入者のサポート用アカウント |

### 2026-03-10 実アカウント役割

- `【みかみ】アドネス株式会社`
  - AI / SNS の共通メインLINE
  - 流入経路の登録時アクションで、タグ追加、テンプレ送信、シナリオ開始を直接持つ
  - 書籍、セミナー、AIディスプレイ、秘密の部屋購入後などの共通受け皿
- `スキルプラス`
  - スキルプラス導線のメイン受け皿
  - current API では `流入経路 2件 / タグ 20件 / テンプレート 39件`
  - visible landing と友だち追加時設定は空だが、current の `セミナー①導線 / 無料体験会 / 本気コンサル / ライトプラン / 企画LINE遷移` を content-group 側に持っている
  - ただし流入経路名は運用メモ化しており、命名規則から崩れている
- `みかみ@AI_個別専用`
  - AI の個別相談、プロコンサル、スタートダッシュ、AI合宿購入後オファー用
- `みかみ@個別専用`
  - SNS系の直個別、RM作成会、個別アプローチ用
- `スキルプラス@企画専用`
  - スキルプラス導線の実運用寄り account
  - `流入タグ追加 / 新規流入代入 / シナリオ開始` が流入経路 action に残っている
  - current UI のシナリオ画面は `content-group` 系 API で取る
  - `セミナー①予約シナリオ / リマインド / 個別オファー / フリープラン / 見逃し配信 / 無料体験会 / 本気コンサル / 書籍導線` が見える
- `【スキルプラス】フリープラン`
  - フリープラン導線の独立受け皿
  - current API では流入経路 0件だが、タグとテンプレートの独立運用がある
- `スキルプラス【サポートLINE】`
  - 受講後運用の本線
  - current API 直確認では `流入経路 41件 / タグ 49件 / テンプレート 50件 / リッチメニュー 3件`
  - `ゴール設定1on1予約案内` や `週報リマインド` の landing が並び、受講後運用の起点を持つ
  - シナリオフォルダも `毎日日報 / オンボ未完了 / 新オンボ / 日報 / オンボーディング` が current に並ぶ
  - テンプレート sample も `コース移行`, `合宿詳細`, `日報提出`, `SL.AIアップデート` など教育・CS寄り
  - `Project/2_CS/サポートLINE_イベント情報設計.md` では、イベント案内と予約導線の実装先として指定されている
  - `Project/2_CS/質問自動回答プロジェクト.md` では、`回答用：サポートLINE` シートを通じて AI下書き支援の入口になっている
- `【予約窓口】スキルプラス合宿`
  - 合宿予約とライトプラン年会員オフライン導線の受付口
  - current API 直確認では `流入経路 1件 / タグ 0件 / シナリオ 0件 / テンプレート 12件 / リッチメニュー 0件`
  - 現在見えている流入経路は `ライトプラン年間会員_オフラインDM_QRコード_リストイン` の1本
  - テンプレート本文も `予約ページ / 本人確認 / Zoomリンク` の実務連絡に集中している
  - `予約ページ送付 / 本人確認 / Zoomリンク送付` の小さく閉じた実務口として使われている
  - `System/data/lstep_yoyaku_skillplus.csv` では、`お名前 / 電話番号 / メール / プラン名 / 日程別参加列` を持つ予約台帳として機能している

### 命名規則の正本

> ソース: MindMeister `シートの名前やタグ名の共通ルール`

- 目的は `担当者や部署ごとの認識ズレを防ぎ、運用ミスを減らすこと`
- 使っていないものは `使用していないもの` に入れる
- 使っているものは `⭐️` で識別する
- 流入経路名は `集客媒体_ファネル名-イベント名`
- 新規流入タグは `【新規】集客媒体_ファネル名-イベント名`
- 流入タグは `集客媒体_ファネル名-イベント名`
- 購入タグは `【購入】商品名`
- テンプレート名は `【流入】...` `【購入】...` `シナリオ概要_イベント名-詳細` のいずれかに寄せる

### 判断辞書

#### 良い

- 流入経路
  - `Meta広告_スキルプラス-リストイン`
  - `YouTube広告_AI-オプトイン`
- タグ
  - `【新規】Meta広告_スキルプラス-リストイン`
  - `Meta広告_センサーズ-合宿購入`
  - `【購入】秘密の部屋`
- テンプレート
  - `【流入】スキルプラス-夏休み企画`
  - `【購入】ダイナマイト合宿`
  - `メインシナリオ_リストイン-直後`

#### 悪い

- 流入経路
  - `広告チームコピー用`
  - `⚠️フォルダは勝手に増やさない。媒体ごとにフォルダを管理する`
  - `⚠️新たに流入経路作成時は"必ずつけてね！"のタグを挿入するようにお願いします。`
- タグ
  - `やばい人`
  - `加藤`
  - `加藤彰吾`
  - `1月`
- テンプレート
  - `流入_1`
  - `流入_2`
  - `ズームリンク`
  - `事前メッセージ`

#### legacy / 例外として扱う

- 表示名と実体がズレるもの
  - landing action では `ウェビナー①予約シナリオ`
  - 実シナリオ名は `セミナー①予約シナリオ`
- visible landing が空でも current の content-group 導線が動いている account
  - `スキルプラス`
- `lm-account-id` は account 判定に使わない
  - `follow_url` と `LINE名(...)` を正にする
- old 名称の account / ファネルは current 事業名と分けて読む
  - `センサーズ`
  - `AIカレッジ`
  - `デザジュク`
  - `アドプロ`
  - `ギブセル`

#### 実務での正誤判断

- 命名規則を満たし、第三者が見て
  - どの媒体か
  - どのファネルか
  - どのイベントか
  を一読で言えるなら正
- 運用メモや担当者名や感想語が混ざり、第三者が用途を再現できないなら誤り
- current UI で空に見えても、`content-group` や `event trigger` に current 実装があれば `未使用` と断定しない
- folder や group 名に
  - `使用していないもの`
  - `━━↓使わない↓━━`
  - `old`
  - `backup`
  のような明示マーカーがあるものは、まず draft / legacy 候補として扱う
- さらに current 運用上は、folder 名に
  - `下書き`
  - `エラー`
  - `変更用`
  が入るものも、そのまま current 本線とは見なさない
  - 例
    - `オンボーディングフロー（下書き）`
    - `秘伝オンボエラー`
    - `LINE変更用`
- ただし `使わない` 配下にあるから即削除ではなく、
  - landing から参照されていないか
  - template / scenario / rich menu から current で呼ばれていないか
  まで見てから legacy と確定する
- `⭐️` は current の強いシグナルだが、星がないだけで未使用とは断定しない
- `未分類` は current / legacy の判定根拠にしない
  - 実際に `スキルプラス【サポートLINE】` では current のものも `未分類` に多く残っている
- 日付付き folder も、それだけでは legacy と決めない
  - `2024.12.16 リッチメニュー 6`
  - `24.09.09 リッチメニュー 3`
  は current account 内に実件数付きで残っており、`旧版の保管` と `現行切替履歴` のどちらかを導線参照で見分ける
- current 実例として、`スキルプラス【サポートLINE】` の
  - `会員タグ 35`
  - `ゴール設定 19`
  - `スキルプラス合宿シリーズ 11`
  は folder 名と件数の組み合わせだけで `運用中の状態管理` と読める
- `★マーケ部使用中★` のように、folder 名に `使用中` が明示されているものは current の強いシグナル
- `会員タグ` `ゴール設定` `スキルプラス合宿シリーズ` のように、受講後運用やイベント運用の役割が明確な folder も current の強いシグナル
- draft / temporary の強い例
  - `新リッチメニュー（宮本作成中）0`
  - `オンボーディングフロー（下書き）6`
  - `実行中アクション（小澤）1`
  は、そのまま current 本線の正本と見なさない
- `（仮）リッチメニュー` のような仮置き名も、current 本線の確定版とは分けて扱う
- legacy 候補の強い例
  - `旧：リッチメニュー 2`
  - `━━↓使わない↓━━`
  は、まず historical 保管と見て current 参照の有無を後で確認する
- 例外処理 / 変更待ちの例
  - `秘伝オンボエラー 1`
  - `LINE変更用 1`
  は「今も使われる可能性がある helper」ではあるが、current 主導線の正本とは分けて扱う
- `要修正` や `確認必須` を含む folder は、current に存在していてもそのまま標準として複製しない
- `⚠️とりあえず確認必須⚠️` や `スキルプラス導線（要修正）` のような folder は、current に見えても「そのまま使ってよい正本」ではなく、まず運用注意や修正待ちとして読む
- `【予約窓口】スキルプラス合宿` のような小さく閉じた account では、folder 数よりも
  - event 名が月次で更新されているか
  - `予約ページ / 本人確認 / Zoomリンク` の template が残っているか
  を current シグナルとして優先する

### スキルプラス系を見るときの注意

- `スキルプラス` 本体は受け皿だけではなく、current の content-group 導線も持っている
- ただし `System/data/lstep_skillplus.csv` では 2026-03 にも `Meta広告_スキルプラス_リストイン_オートウェビナー1` などの current 流入が入っているため、空の箱ではない
- `スキルプラス@企画専用` は運用 action と event trigger が見えるため、webinar 自動化の把握ではこちらが重要
- `【スキルプラス】フリープラン` は別系統として切って見る
- landing action に出る `ウェビナー①予約シナリオ` は、実シナリオ名では `セミナー①予約シナリオ`
- `スキルプラス` `スキルプラス@企画専用` `【スキルプラス】フリープラン` の3つとも、友だち追加時設定のデフォルトシナリオは 0件
- current の main セミナー系テンプレートは `https://l-cast.jp/s/a0fe/xKzfgCjvkHB` に直接送っている
- `【アーカイブ】セミナー①企画LINE遷移` は `https://skill.addness.co.jp/sp3` を介して `follow=@230vpgmc&lp=ibnz0m` に送っている
- `スキルプラス` 本体と `企画専用` の direct bridge はまだ未確定。少なくとも現在は `本体の content-group 導線` と `企画専用の event-trigger 導線` が parallel に存在する
- つまり、スキルプラス系は `1アカウントだけ見れば分かる` 前提で見ない
- `スキルプラス【サポートLINE】` と `【予約窓口】スキルプラス合宿` も含めると、実務上は `集客 / webinar / 教育 / CS / 予約` の5役で分けて見る方がズレにくい
- `スキルプラス【サポートLINE】` は `教育 / CS` 側、`【予約窓口】スキルプラス合宿` は `予約` 側としてかなり明確に分かれている

### account 判定の注意

- Lステップ の `lm-account-id` はアカウント切り替え後も固定値のままだった
- 実際にどの LINE を見ているかは、以下で判定する
  - 流入経路の `follow_url`
  - ChatPlus 側の `LINE名(...)`
- 実務では `lm-account-id` より `follow_url` を正として扱う

### テンプレート / Flex の current editor

- `テンプレート` 一覧の current 正本 API は `GET /api/templates`
- 一覧 API では少なくとも
  - `id`
  - `name`
  - `content_text`
  - `form_type`
  - `editor_version`
  - `group`
  が取れる
- current の種類判定は、実ラベルだけでなく `form_type + editor_version` でも切れる
  - `form_type=8 / editor_version=0` = `標準メッセージ`
  - `form_type=30 / editor_version=1` = `カルーセルメッセージ(新方式)`
  - `form_type=60 / editor_version=2` = `フレックスメッセージ`
  - `form_type=40 / editor_version=10` = `テンプレートパック`
- したがって、一覧から edit URL を開く時の current 基本は
  - まず `https://manager.linestep.net/line/template/edit/{template_id}?group={group_id}`
  - ここを generic 入口として使う
- generic 入口の current 挙動は次
  - `標準メッセージ` はそのまま `/line/template/edit/{id}?group={group}` に入る
  - `カルーセルメッセージ(新方式)` は `/line/template/edit_v2/{id}` に redirect
  - `フレックスメッセージ` は `/line/template/edit_v3/{id}?editMessage=1` に redirect
  - `テンプレートパック` は `/line/eggpack/show/{id}` に redirect
- つまり、編集画面を開く時に種類が分からなくても、まず generic edit URL を踏めば current の正しい editor へ流れる
- live で account を切り替える時は、右上の account ボタンから入る
  - 例
    - `甲原海人 (副管理者) みかみの秘密の部屋 expand_more`
    - `スキルプラス【プライム】に切り替え`
- account 切替後は `/` に戻ることがあるので、切替直後に目的画面へ戻ってから読む
- テンプレート一覧の current 正規入口は
  - `テンプレート -> 新しいテンプレート -> フレックスメッセージ`
  - つまり `フレックスメッセージ` は pack を経由しなくても単体で新規作成できる
- したがって Lステップ で Flex を作る前提は、まず
  - `フレックスメッセージとして作るのか`
  - `テンプレートパックの 1 step として作るのか`
  を切り分ける
- `テンプレートパック -> メッセージ新規追加` の current route は `/line/eggpack/step/{pack_id}/new?`
- current editor は 1 画面で
  - `テキスト`
  - `画像`
  - `ボタン・カルーセル`
  を切り替える構造
- `ボタン・カルーセル` は `テンプレートパック内でカード型の訴求を作る時の主入口` として読む
- current form は `#msgform`、submit 先は `/line/eggpack/step`
- `ボタン・カルーセル` では少なくとも次の field が見える
  - `carousel_title[panel]`
  - `carousel_text[panel]`
  - `carousel_action_title[button][panel]`
  - `carousel_action_type[button][panel]`
  - `carousel_action_url[button][panel]`
- current editor 上で確認できた inline action の種類
  - `何もしない`
  - `URLを開く`
  - `電話をかける`
  - `LINEアカウントを友だち追加`
  - `メールを送る`
  - `回答フォームを開く`
  - `シナリオを移動・停止`
- つまり、Lステップの action は `友だち追加時設定` だけでなく、Flex / カルーセルの button ごとにも直接持てる
- 2026-03-12 の live 観察では、`スキルプラス【サポートLINE】` の隔離テスト pack からここまで確認済み
- 現時点で確定している事実は
  - `フレックスメッセージ` の作成入口
  - `テンプレートパック` 内の `ボタン・カルーセル` editor の field / action 種類
  - `フレックスメッセージ` の `作成 -> テスト送信 -> 削除`
  まで
- 画像 block の current field も live で確認済み
  - `画像`
  - `形状`
  - `ラベル`
  - `タイトル`
  - `サブタイトル`
  - `アクション`
  - `アクションラベル`
- current の使い分けを切る時は、まず `どの message 種を選ぶか` を先に決める
  - `標準メッセージ`
    - テキスト説明が長い
    - その場で理解させたい
    - direct URL や simple CTA で足りる
  - `カルーセルメッセージ(新方式)`
    - 複数カードで比較させる
    - 複数の選択肢や補足導線を並べたい
    - `無料相談` のように `質問フォーム / 申込` へ複数 panel で見せたい
  - `フレックスメッセージ`
    - 視覚階層を強く作りたい
    - 重要告知や main CTA を 1 画面で強く見せたい
    - `合宿集客` `コース移行` `アップデート告知` のように、見落とされると困る message に向く
  - `テンプレートパック`
    - 1通ではなく、同テーマの message 群をまとめて扱いたい
    - `無料相談会告知` のように、複数 message を 1 セットで配信手前まで保持したい時に向く
- つまり current の Lステップ では
  - `標準メッセージ = 文字中心の説明`
  - `カルーセルメッセージ(新方式) = 複数カードの比較 / 選択`
  - `フレックスメッセージ = 視覚階層の強い重要告知 / main CTA`
  - `テンプレートパック = message 群の container`
  と読むのが一番ズレにくい

#### フレックスメッセージ の current 作成とテスト送信

- フレックスメッセージ の新規作成は
  - `テンプレート -> 新しいテンプレート -> フレックスメッセージ`
  - 最初の route は `/line/template/edit_v3/new?group=0&editMessage=0`
  - `edit メッセージを作成` を押すと `/line/template/edit_v3/new?group=0&editMessage=1`
- current UI では、作成直後に editor が全面展開されるのではなく
  - `テンプレート名`
  - `フォルダ`
  - `edit メッセージを作成`
  - `PC版・通知欄での代替テキスト`
  - `公式アイコンで送信`
  が並ぶ
- したがって最初の exact 手順は
  1. `テンプレート`
  2. `新しいテンプレート`
  3. `フレックスメッセージ`
  4. `テンプレート名` を入れる
  5. `edit メッセージを作成`
  6. editor 内で block を組む
  7. `メッセージを保存`
  8. route が `/line/template/edit_v3/{id}?editMessage=0` に切り替わる
  9. 外側の `保存`
  10. 一覧へ戻って `テスト送信`
  11. 問題なければ `削除`
- current の API は
  - `GET /api/template/lflexes/{id}`
  - `POST /api/template/lflexes`
  - `POST /api/template/lflexes/{id}` + `_method=patch`
- 2026-03-12 の live probe では、画面右上の account 表示が `スキルプラス【プライム】` の状態で
  - `group=1`
  - `sender_id=1`
  で保存成功を確認した
- したがって live 作業では、最初に右上の account 表示を確認する
  - 2026-03-14 の current 実例では `スキルプラス【サポートLINE】`
  - API helper は cookie だけだと別 account 文脈を読むことがある
  - `一覧で見えているテンプレートを helper でも読めるか` を先に確認する
- create payload で最低限使われる field は
  - `name`
  - `group`
  - `editor_json`
  - `alt_text`
  - `sender_id`
  - `do_override_sender`
  - `answer_type`
  - `twice_do_reply`
  - `twice_action_id`
- live の隔離テストでは、最小構成として
  - `ボタン` block 1つ
  - ボタン名 `確認リンク`
  - `アクション設定 -> URLを開く -> https://example.com/test-flex`
  の保存とテスト送信と削除まで確認済み
- 2026-03-13 の live では、さらに
  - `テンプレート名`
  - `＋ブロックを追加 -> テキスト`
  - テキスト本文 `これは保存確認用のフレックスです`
  の 1 block だけでも保存できることを確認した
- この時の保存済み item は
  - `ZZ_TEST_20260313_Flex保存確認_105433`
  - id `249482757`
  - `1 panel / テキスト1`
  だった
- button block の `アクション設定` で current に選べる種類は
  - `アクション実行`
  - `URLを開く`
  - `回答フォームを開く`
  - `電話をかける`
  - `LINEアカウントを友だち追加する`
  - `メールを送る`
  - `その他`
- `URLを開く` を選ぶと
  - `表示方法`
  - `URL`
  が出る
- representative 例
  - `動画編集　進捗管理　カルーセル`
    - id `229361471`
    - `alt_text = ※本日で募集終了です。`
    - button title は `回答する📝`
    - action は `回答フォームを開く`
    - `action_form_id = 958377`
    - `本文で必要性を作った後に回答フォームへ送る` CTA 型
  - `委託先アンケート　カルーセル`
    - id `226111956`
    - `alt_text = ※本日で募集終了です。`
    - button title は `回答する📝`
    - action は `回答フォームを開く`
    - `action_form_id = 946155`
    - `アンケート回答を 1 action で friction なく起こさせる` survey CTA 型
- さらに同日の live テストで、`画像` block も current UI で追加して保存まで確認した
  - `＋ブロックを追加 -> 画像`
  - inline block の `なし`
  - modal `画像を追加`
  - modal 内で `新規アップロード` または `登録メディア`
  - `登録メディア` では card 全体ではなく filename 行を押して選択状態にする
  - `選択中のファイル数: 1 / 1`
  - modal の `保存`
  - editor 上部の `メッセージを保存`
  の順
- 画像 upload modal の current 表示は
  - `新規アップロード`
  - `登録メディア`
  - `ここにファイルをドロップ`
  - `ファイルを選択する`
  - `閉じる`
  - `保存`
  まで確認済み
- 既存の representative 例として、`3月 スキルプラス合宿 集客` では
  - `alt_text = 【3月スキルプラス合宿】のご案内`
  - text 3 block
  - button 1 block
  - image 1 block
  が組まれていた
- helper から見える actual JSON では、button の `action_type` は `liny-action` だった
- representative 実例では `action.data.type=1` で、
  - `url_action.url`
  - `liff_size=full`
  - description `[URLを開く] ... をトーク内ブラウザ(大)で開きます`
  まで入っていた
- したがって、代表例の button は `Lステップ内 action 実行系` だが、その中身は `URLを開く` を包含しうる
- create 直後の route は `edit_v3/new?group=0&editMessage=1` だが、一覧行から開く既存 item の route は `edit_v3/{id}?group=0&editMessage=0` が current 実例として確認できた
- 2026-03-14 の full smoke では、`メッセージを保存` 後の route が `/line/template/edit_v3/249634889?editMessage=0` まで切り替わることも確認した
- つまり、`新規作成時の URL` と `保存後の URL` と `一覧行から再編集する URL` は一致しない前提で読む
- `＋ブロックを追加` で current に出る追加候補は
  - `画像`
  - `タイトル`
  - `テキスト`
  - `ボタン`
  - `動画`
- 既存の representative editor で visible だった主な設定ラベルは
  - `パネル設定`
  - `背景`
  - `テーマカラー（共通）`
  - `サイズ（共通）`
  - `ブロック設定`
  - `画像`
  - `テキスト`
  - `囲み`
  - `ボタン`
  - `アクション`
  - `ボタンスタイル`
- current editor では `＋ブロックを追加` が 2 箇所に見える
  - 実際に押す button の `＋ブロックを追加`
  - helper text の `右上の「＋ブロックを追加」から作成してください`
- したがって automation や確認時は、helper text ではなく button 自体を対象にする
- `ボタン` block の `アクション設定` dialog で live に確認できたラベルは次
  - `アクション設定`
  - `種類`
  - `アクション実行`
  - `閉じる`
  - `保存する`
- つまり `ボタン` は `押した後の挙動` をここで確定するまで未完成として扱う
- `画像` block の upload modal で live に確認できたラベルは次
  - `新規アップロード`
  - `登録メディア`
  - `ここにファイルをドロップ`
  - `ファイルを選択する`
  - `閉じる`
  - `保存`
- ここで重要なのは、file を input に入れただけでは `保存` できないこと
  - current UI では、upload 後に file 一覧の row を明示的に選ぶ必要がある
  - row を選ぶと `選択中のファイル数: 1 / 1` になり、その後に `保存` を押せる
- つまり `画像を入れる` は drag and drop だけでなく `登録メディア` から既存 asset を再利用する前提も持つ
- つまり `フレックスメッセージ` は
  - `見た目を組む`
  - `押した後の action を組む`
  を同じ editor 内で持つ
- `タイトル` と `ボタン名` の入力は通常 input ではなく ProseMirror の contenteditable なので、通常の input selector 前提で考えない
- フレックスメッセージ のテスト送信は、editor 画面ではなくテンプレート一覧の行右端メニューから行う
  - 行右端の `more_vert`
  - `テスト送信`
  - `テスト送信先選択` ダイアログ
  - 左端 checkbox の `label` を押して友だちをチェック
  - `テスト`
- 送信先 `甲原 海人` は、名前テキストを押すのではなく、行左端の checkbox label を押すのが current の exact 手順
- 2026-03-13 の live 実行では、保存済み `フレックスメッセージ` を送信先 `甲原 海人` に対して
  - checkbox label 選択
  - `テスト`
  の順で送り、
  - `POST /line/template/test/multi`
  - status `200`
  - modal が閉じる
  ところまで確認した
- ただし live の exact 作業は、画面上の見た目ログインだけでは開始しない
- browser 上でログイン済みに見えていても `python3 System/scripts/lstep_auth.py` が `auth_alive=false` を返し、保存 / 送信 API が `401` になることがある
- したがって current の開始条件は
  1. `python3 System/scripts/lstep_auth.py`
  2. `auth_alive=true` を確認
  3. その後に `フレックスメッセージ` の保存や `テスト送信`
  で固定する
- `auth_alive=false` の時は、その場で browser 手動ログインを依頼する
- 今後、Lステップ等の公式LINEでテスト送信する時の送信先は `甲原 海人` に統一する
- テスト送信は重複禁止。同一内容を再送する前に、直前送信の有無を確認する
- 後片付けの UI 導線はここまで確認済み
  - テンプレート一覧の行右端 `more_vert`
  - `削除`
  - confirm dialog `この操作は取り消せません。本当に削除しますか？`
  - `削除する`
- 2026-03-12 の live probe では、`ZZ_TMP_FLEX_20260312_BTN` について
  - `テスト送信`
  - `削除`
  - 一覧再読込
  まで行い、`delete_clicked=true`、`exists_after=0` を確認した
- 同 probe では、`未分類` 件数も `82 -> 81` に減っており、少なくともこの temp item 1件の delete は exact に確認済み
- 2026-03-13 の live では、`ZZ_TEST_20260313_Flex保存確認_105433` についても
  - `テスト送信`
  - `削除`
  - confirm dialog の `削除する`
  - 一覧再読込後 `after 0`
  を確認した
- さらに同日の live で、current smoke test を 2 本追加した
  - `ZZ_TEST_20260313_Flex3blocks_112020`
    - `タイトル1 / テキスト1 / ボタン1`
    - title `LSTEP Flex 確認用`
    - text `このメッセージは、タイトル・テキスト・ボタンの exact 動作確認用です。`
    - button `確認する`
    - action `URLを開く -> https://example.com/flex-review-20260313`
    - `テスト送信 -> 削除 -> after 0`
  - `ZZ_TEST_20260313_FlexImage_113022`
    - `画像1 / タイトル1 / テキスト1 / ボタン1`
    - title `画像つき Flex 確認用`
    - text `このメッセージは、画像・タイトル・テキスト・ボタンの exact 動作確認用です。`
    - button `確認する`
    - action `URLを開く -> https://example.com/flex-image-review-20260313`
    - `テスト送信 -> 削除 -> after 0`
- さらに `ZZ_` 検索で `[]` を返し、少なくとも一覧 API 上で temp item が残っていないことも確認済み
- 2026-03-14 の live full smoke では `ZZ_TMP_20260314_FlexFullSmoke_01` を使い
  - `画像1 / タイトル1 / テキスト1 / ボタン1`
  - `アクション設定 -> URLを開く -> https://example.com/flex-full-smoke-20260314`
  - `メッセージを保存`
  - route `/line/template/edit_v3/249634889?editMessage=0`
  - 外側の `保存`
  - 一覧行右端 `... -> テスト送信`
  - `甲原 海人`
  - `テスト`
  - 一覧行右端 `... -> 削除 -> 削除する`
  - 一覧再読込後 `after 0`
  まで exact に確認した
- したがって `単体フレックスメッセージ` の current 手順は
  - `作成`
  - `テスト送信`
  - `削除`
  まで 1 本通っている
- 一方で、後日の一覧スクリーンショットに別の `ZZ_` 系が残っていたため、今後の live 作業でも
  - `削除する`
  - 一覧で対象行が消えたか
  - 必要なら API / DOM 再読込でも消えたか
  を毎回確認する
- つまり、フレックスメッセージ のレビュー手順は
  1. フレックスメッセージ を作る
  2. 必要なら `画像` block まで作る
  3. 一覧に戻る
  4. 行右端メニューから `テスト送信`
  5. 自分の LINE に送る
  6. 実機で見た目とタップ先を確認する
  7. テスト用なら一覧から `削除する`
  8. 一覧と API の両方で消えているか確認する
  が current の正本
- 再利用できる型としては
  - `作る` = `Skills/2_導線/lstep-flex-message-operations`
  - `レビューする` = `Skills/2_導線/lstep-template-review-operations`
  に分けて持つ
- つまり Addness 固有の representative はここに残し、`どう分解して良し悪しを判断するか` の手順だけを `Skills` に切り出す

#### 標準メッセージ の current 作成とテスト送信

- 標準メッセージ の新規作成は
  - `テンプレート -> 新しいテンプレート -> 標準メッセージ`
  - route は `/line/template/new?group=0`
- current editor は `単なるテキスト専用画面` ではなく、少なくとも
  - `テキスト`
  - `スタンプ`
  - `画像`
  - `質問`
  - `ボタン・カルーセル`
  - `位置情報`
  - `紹介`
  - `音声`
  - `動画`
  を 1 画面に持つ message editor だった
- ただし current 実例の使い方としては、`標準メッセージ` は今も
  - 長めの説明
  - 補足
  - simple CTA
  に寄ることが多い
- create 画面の本文入力欄は hidden の `textarea[name="text_text"]` ではなく、visible editor の `.ProseMirror` を使う
- 保存ボタンは submit input ではなく、表示ラベル `テンプレート登録` の click target で発火する
- `下書き保存` も同画面にあるが、current の本線確認では `テンプレート登録` を正とする
- 2026-03-12 の live create では、最低限
  - `テンプレート名`
  - `.ProseMirror` への本文入力
  を入れて保存成功を確認した
- visible form だけでは不足し、server 側では
  - `sender_id=166906`
  - `do_override_sender=0`
  も要求される
- つまり、標準メッセージ は見た目の入力欄だけでなく、送信者まわりの hidden 値も current 保存条件に入る
- representative な current 標準メッセージ例として
  - `動画編集進捗管理　リマインド`
    - id は `229401295`
    - `char_count = 92`
    - `line_count = 4`
    - `url_candidates = 0`
    - 先頭 4 行は
      - `[name]さん お疲れ様です！`
      - `本日の進捗報告がまだのようです！`
      - `報告がないと、的確なフィードバックができません！`
      - `今日の頑張り、しっかり報告してくださいね！ 報告待ってます！`
    - つまり current の `標準メッセージ` では
      - `誰向けか`
      - `何が未完了か`
      - `今やる理由`
      - `次にしてほしいこと`
      を text 4 行で friction なく渡す運用連絡型がある
  - `オンライン再リマインド`
    - `テンプレート編集` 画面の `テンプレート名` はそのまま `オンライン再リマインド`
    - 本文は `オンラインのプライム合宿へお申し込みありがとうございます` から始まる運用連絡
    - 途中で `みかみの秘密合宿` の公式LINE追加を依頼し、直接 LIFF URL を 1 本だけ置いている
    - 目的は `Zoomリンク送付前に必要な追加行動を 1 つだけ起こさせること`
    - よい理由は
      - `何の人向けか` が冒頭で明確
      - `なぜ今やる必要があるか` が書かれている
      - `押す先` が 1 つに絞られている
      - sales ではなく operational message として friction が低い
  - `SNS活用 1on1無料相談会`
    - 長文で共感 -> 問題整理 -> 便益 -> 最後に Google Forms CTA
    - `長文で理解させてから 1 つの申込先へ送る` 型
  - `LINE構築1on1無料相談会`
    - urgency を前に出して、本文は text-heavy
    - `終了間際の一押し` を text でやる型
    - id `225070385`
    - URL は `https://forms.gle/Dfsv666UdmWjsYhCA`
    - `終了間際の一押しを text-heavy に行う` current の代表例
  - `SNS活用 1on1無料相談会`
    - id `225316639`
    - URL は `https://forms.gle/ThNmeHBBxsRc2ahz6`
    - `共感 -> 問題整理 -> 便益 -> 1つの Google Forms CTA`
    - `長文で理解させてから 1 つの申込先へ送る` current の代表例
  - `2025.05.28 リトルみかみくん利用可能のお知らせ`
    - サポート導線の使い方を text で案内
    - `説明中心のお知らせ` 型
- 2026-03-12 の live テストでは
  - 一時 `標準メッセージ`
  - item id `249318424`
  - `甲原 海人`
  - `tester_ids[]=131674`
  - `POST /api/message/test`
  - `DELETE /api/templates/249318424`
  まで通し、一覧と `GET /api/templates` の両方で残っていないことを確認した
- 2026-03-13 の live では、一覧 page 1 に残っていた
  - `ZZ_TEST_20260313_Standard_121612`
  - `ZZ_TEST_20260313_Standard_121509`
  の 2 件を使い、`作成済みの標準メッセージ` の exact 手順をさらに固定した
  - 行右端 `...`
  - `テスト送信`
  - modal `テスト送信先選択`
  - `甲原 海人`
  - `テスト`
  - 送信後に同じ行の `... -> 削除 -> 削除する`
  - 再読込と `/api/templates?page=1` の両方で `exists=false`
- この時の row menu の current ラベルは
  - `コピー`
  - `名前を変更`
  - `テスト送信`
  - `一斉配信を作成`
  - `削除`
  だった
- つまり `標準メッセージ` も
  - 保存された item を一覧で見つける
  - `テスト送信`
  - `削除`
  まで UI ラベルどおりに exact 再現できる
- 注意
  - Lステップは `右上の account 表示` と helper の account 文脈がずれることがある
  - したがって live 作業では
    1. `lstep_auth.py` で `auth_alive=true`
    2. 一覧に見えている `テンプレート名` を browser fetch か UI で先に確認
    3. その後に `テスト送信` や `削除`
    の順に入る方が事故りにくい
  - 2026-03-13 の追加確認では、browser 上はログイン済みに見えていても `python3 System/scripts/lstep_auth.py` は `auth_alive=false` を返した
  - したがって `見た目のログイン状態` は正としない
  - exact な live 開始条件は `lstep_auth.py = auth_alive=true`
  - `false` の時は、その場で browser 手動ログインを依頼する

#### カルーセルメッセージ(新方式) の current 解釈

- current editor は `/line/template/edit_v2/{id}`
- representative 例として
  - `▼無料相談はこちら【YouTube切り抜き 無料相談会】`
  - `▼無料相談はこちら【AI活用 無料相談会】`
  がある
- current 実装の意図としては
  - `無料相談` のように、
    - 事前質問
    - 申込
    - 補足説明
    のような複数 card を並べて見せる型
  - 1 text で押し切るより、`選びやすさ` を優先する型
- 実務判断では
  - CTA が 1 つで十分なら `標準メッセージ` または `フレックスメッセージ`
  - CTA や説明の card を複数並べた方が分かりやすいなら `カルーセルメッセージ(新方式)`
  と切る

#### テンプレートパック の current 解釈

- current route は `/line/eggpack/show/{pack_id}`
- 新規 `テンプレートパック` の作成入口は
  - `テンプレート -> 新しいパック`
  - route は `/line/eggpack/edit/new?group=0`
- create form の必須は最低限
  - `テンプレート名`
  - `フォルダ`
  で、save route は `POST /line/eggpack/edit`
- 2026-03-13 の live create では
  - account は `スキルプラス【プライム】`
  - pack id `249497749`
  - pack 名 `ZZ_TEST_20260313_Pack確認_1330`
  まで確認した
- `メッセージ新規追加` の route は `/line/eggpack/step/{pack_id}/new?`
- step 作成画面では
  - `テキスト`
  - `スタンプ`
  - `画像`
  - `質問`
  - `ボタン・カルーセル`
  - `位置情報`
  - `紹介`
  - `音声`
  - `動画`
  を選べる
- 最小の `本文` step は
  - route `POST /line/eggpack/step`
  - `テキスト` を選んでも通常の visible `textarea` が主入口ではなく、実際に編集するのは `.ProseMirror`
  - hidden の `textarea[name=\"text_text\"]` はあるが、実務上は `.ProseMirror` に本文が見えていることを確認してから保存する方がズレにくい
- 2026-03-13 の live create では
  - step 本文 `これはテンプレートパックの本文確認用です。 次のステップで行動用テンプレートへつなぎます。`
  を追加して show 画面へ戻るところまで確認した
- representative 例として
  - `YouTube切り抜き 無料相談会告知`
  - `AI活用 無料相談会告知`
  - `Teambase経営者向け無料相談会案内`
  がある
- `テンプレートパック` は単体 message 種ではなく、message 群の container
- 一覧画面では
  - `メッセージ新規追加`
  - `テンプレートから追加`
  - `テスト送信`
  が主な入口
- `テンプレートから追加` は modal で開き
  - title `テンプレート選択`
  - button `閉じる`
  - button `コピーして編集`
  - button `追加`
  が current の exact UI
- 2026-03-13 の live 実行では
  - `委託先アンケート　カルーセル`
  を選び
  - `追加`
  で pack step 2 に差し込めた
- `YouTube切り抜き 無料相談会告知` の current 実例では
  - page title は `メッセージパック「YouTube切り抜き 無料相談会告知」`
  - step は `2件`
  - `1件目` は `本文`
  - `2件目` は `テンプレート`
  - `テスト送信` の内部設定は `url=/line/template/test/multi` と `item_id=225292504`
- つまり current の `テンプレートパック` は
  - `本文をそのまま入れる step`
  - 既存 `テンプレート` を差し込む step
  を 1 つの container に束ねる使い方がある
- representative 実例から見る current の意図は
  - `無料相談会告知` のように、複数 message を 1 セットで回す
  - 1通単体より、同テーマの message 群を再利用したい時に使う
  - `本文` と `テンプレート` を混在させて friction を下げる
- `2024.10.29 アンケート` の current 実例では
  - page title は `メッセージパック「2024.10.29 アンケート」 設定`
  - step は `2件`
  - `1件目` は `本文`
    - `サービス向上を目的としたアンケート`
    - `今のアドプロについて教えてください`
    という理由づけ
  - `2件目` は preview 上 `【カルーセル】アンケートへ`
    - 本文でお願いの理由を作ってから、visual CTA に渡す型
- `動画編集　進捗報告　テンプレート` の current 実例では
  - page title は `メッセージパック「動画編集 進捗報告 テンプレート」 設定`
  - step は `2件`
  - `1件目` は `本文`
    - `本日もお疲れ様でした`
    - `進捗報告の時間です`
    - `報告された内容を元にフィードバックしていく`
    で行動理由を先に作る
  - `2件目` は `テンプレート`
    - actual 実体は `カルーセルメッセージ(新方式)` の visual CTA
  - つまり `テンプレートパック` は
    - `まず理由を作る`
    - `次に押させる`
    を 1 container に束ねる current 実例として読める
  - id `229361137`
  - `進捗報告の理由づけ -> 回答 action` を 1 pack に束ねた運用 message 型として読める
- `委託先アンケート` の current 実例では
  - id `226112180`
  - 本文で `協力する理由` と `回答特典` を先に作る
  - その後に `【カルーセル】` で回答 action へ渡す
  - `協力する理由 -> 特典 -> 回答 action` を 1 pack に束ねた survey 型として読める
- `テスト送信` は pack 画面右上にもあるが、current の安全手順としては
  - まず pack の step 構成を確認する
  - その後に `テスト送信`
  と読む方がズレにくい
- pack の `テスト送信` は current 実例で
  - `url=/line/template/test/multi`
  - `item_id={pack_id}`
  を使っていた
- 2026-03-13 の live 実行では
  - `item_ids[]=249497749`
  - `tester_ids[]=131674`
  - `POST /line/template/test/multi`
  - HTTP 200
  を確認した
- `テスト送信` の exact 導線は
  - pack 一覧行右端 `...`
  - `テスト送信`
  - modal `テスト送信先選択`
  - `甲原 海人`
  - `テスト`
  だった
- 後片付けの exact 手順も確認した
  - pack 削除の exact 導線は
    - 一覧行右端 `...`
    - `削除`
    - confirm modal `この操作は取り消せません。本当に削除しますか？`
    - `削除する`
  - current API は
    - `DELETE /api/templates/249497749`
    - 応答 `204`
  - `GET /api/templates?page=1` 上で `exists=false`

#### テンプレート inspection helper

- current の `テンプレート` 編集画面を保存なしで読みたい時は
  - `python3 System/scripts/lstep_template_snapshot.py --url <edit_url>`
  を使う
- 一覧 API と種類判定を先に取りたい時は
  - `python3 System/scripts/lstep_template_catalog.py list --limit 30`
  - `python3 System/scripts/lstep_template_catalog.py list --search "スキルプラス合宿"`
  - `python3 System/scripts/lstep_template_catalog.py inspect --id 249005485`
  - `python3 System/scripts/lstep_template_catalog.py inspect --id 225310549`
  - `python3 System/scripts/lstep_template_catalog.py inspect --id 225292504`
  - `python3 System/scripts/lstep_template_catalog.py inspect --id 247339595`
  - `python3 System/scripts/lstep_template_catalog.py inspect --id 239319965`
  を使う
- 主用途
  - `標準メッセージ`
  - `カルーセルメッセージ(新方式)`
  - `フレックスメッセージ`
  - `テンプレートパック`
  の representative editor から
  - 見出し
  - ボタン
  - `.ProseMirror`
  - input / select / textarea
  - carousel の `alt_text / panel / action_type / action_form_id / action_liff_size`
  - carousel inspect の current API `GET /api/line/template/{id}`
    - `messagesData.carousel` を読む
  - pack の step 構成
  - pack の `テスト送信` route
  をまとめて抜くこと
- 前提
  - `lstep_template_snapshot.py` は Chrome CDP `9224` が必要
  - `lstep_template_catalog.py` は Lステップ にログイン済み Chrome cookie が必要
  - current 版 `lstep_template_catalog.py` は、cookie だけで current account を読めない時に browser fetch へ fallback する
- これは `保存` や `テスト送信` を行わず、current editor を読むための helper として使う

#### カルーセルメッセージ(新方式) の current 作成とテスト送信

- カルーセルメッセージ(新方式) の新規作成は
  - `テンプレート -> 新しいテンプレート -> カルーセルメッセージ(新方式)`
  - route は `/line/template/edit_v2/new?group=0`
- current editor の主な UI ラベルは
  - `テンプレート名`
  - `パネル #1`
  - `タイトル`
  - `本文`
  - `画像`
  - `画像選択`
  - `選択肢名`
  - `アクション設定`
  - `テンプレート登録`
- 本文入力欄は `textarea` ではなく `ProseMirror` editor
- current の visible input は
  - `input[name="template.name"]`
  - `input[name="message.0.body.panels.0.actions.0.title"]`
- 2026-03-12 の live create では、最低限
  - `テンプレート名`
  - `本文`
  - `選択肢名`
  を入れて保存成功を確認した
- save request は
  - `POST /line/template/edit_v2`
  - payload の主値は `eggjson`
  - `eggjson` 内に
    - `template.name`
    - `message[0].body.panels[0].text`
    - `message[0].body.panels[0].actions[0].title`
    - `message[0].body.panels[0].actions[0].type`
    が入る
- `タイトル` は空でも保存が通った
- `アクション設定` は未設定のままでも最小保存が通った
- 一覧では badge が `カルーセル(新)` と表示される
- `テスト送信` の current 手順は
  1. テンプレート一覧の対象行の右端 `more_vert`
  2. `テスト送信`
  3. `テスト送信先選択`
  4. `甲原 海人` をチェック
  5. `テスト`
- 2026-03-12 の live 実行では
  - template item id `249321068`
  - テンプレート名 `ZZ_TMP_g1_s1_try1`
  - `甲原 海人` を送信先に選んで `テスト送信` を実行
  - headless の network capture では `テスト送信` の API route 自体は切れなかった
  - したがって、current の正本は `API route の推測` ではなく `UI 手順` として残す
  まで確認した
- 削除の current 手順は
  1. 対象行の右端 `more_vert`
  2. `削除`
  3. confirm dialog `この操作は取り消せません。本当に削除しますか？`
  4. `削除する`
- 2026-03-12 の live 実行では
  - `DELETE /api/templates/249321068`
  - 一覧 DOM と `GET /api/templates` の両方で `exists=0`
  まで確認した
- つまり、カルーセルメッセージ(新方式) も
  - 作成
  - `甲原 海人` への `テスト送信`
  - 削除
  を exact に再現できる状態
- representative な current 例として
  - `▼無料相談はこちら【AI活用 無料相談会】`
  - `▼無料相談はこちら【YouTube切り抜き 無料相談会】`
  を一覧 API で確認済み
  - いずれも `form_type=30 / editor_version=1`
  - `【カルーセル】...` の preview を持つ
  - current では `比較` より `複数 panel に情報を分けて friction を下げる` 用途で使われている
  - `パラダイムシフトーカルーセル`
    - id は `220925523`
    - `alt_text = 🚨価値観を180度変える🚨【衝撃のコンテンツ】`
    - `panel_count = 1`
    - panel title は `みかみの新コンテンツ誕生───`
    - CTA title は `気になる.... ！！`
    - action は `URLを開く`
    - `action_liff_size = legacy`
    - つまり current のカルーセルメッセージ(新方式) でも、比較用途だけでなく `1 panel で視覚訴求 + CTA` の単発オファー型がある

### 依頼を受けたら最初に確定すべき変数

- どの account を使うか
  - `【みかみ】アドネス株式会社`
  - `みかみ@AI_個別専用`
  - `みかみ@個別専用`
  - `スキルプラス`
  - `スキルプラス@企画専用`
  - `【スキルプラス】フリープラン`
  - `スキルプラス【サポートLINE】`
  - `【予約窓口】スキルプラス合宿`
- 何を達成したい導線か
  - 流入
  - 教育
  - 個別相談
  - webinar 予約
  - イベント予約
  - 受講後サポート
- 起点は何か
  - 流入経路
  - テンプレート / Flex
  - シナリオ step
  - リッチメニュー
  - 回答フォーム
  - 一斉配信
- 最初に作る状態は何か
  - 追加するタグ
  - 外すタグ
  - 代入する友だち情報
- 次に何を起こすか
  - テンプレ送信
  - シナリオ開始 / 停止
  - メニュー変更
  - イベント予約
  - 回答フォーム遷移
- どこへ送るか
  - UTAGE
  - short.io
  - 予約URL
  - 外部ページ
- どう計測したいか
  - 流入経路で分けるか
  - タグで見るか
  - クロス分析まで使うか

### 新規設定の標準手順

1. どの account でやるかを決める
2. `何の状態を先に作るか` を決める
   - タグ
   - 友だち情報
3. 起点を決める
   - 流入経路
   - テンプレート / Flex
   - シナリオ step
   - リッチメニュー
4. 予約管理を触る時は、先に次の 3 変数を固定する
   - 誰に見せるか
     - タグ条件
     - コース条件
   - 予約後に何を送るか
     - 予約直後
     - 前日
     - 直前
   - どの外部カレンダーに同期するか
     - 予約を書き込む Google カレンダー
     - シフト元にする Google カレンダー
5. 次の行動を 1 つに絞る
   - テンプレ送信
   - シナリオ開始
   - 予約
   - 回答フォーム
6. inline action で足りるか、reusable action に切り出すかを決める
7. 実際に `タップ -> 期待した画面 or 動作` を確認する
8. 必要ならタグやクロス分析で計測軸を足す

### 実物レビュー用の隔離テスト手順

Lステップを実際に作って甲原さんに見てもらう時は、資料だけで見せない。`本番 account 内の隔離テスト領域` で実物を作って見せる。

1. 正しい account を選ぶ
2. `ZZ_TEST_YYYYMMDD_用途` で、タグ、テンプレート、流入経路を同じ名前で揃える
3. 必要最小限の action だけを入れる
4. 実際に保存して、edit URL と screenshot を残す
5. レビュー時は
   - 何を作ったか
   - どの URL を開けば見られるか
   - 何を見てほしいか
   をセットで渡す
6. 必要なら `テスト送信` で自分の LINE に送り、受信体験まで確認する
7. OK 後に本番名へ寄せるか、不要なら削除する

2026-03-12 の実例
- account: `スキルプラス【サポートLINE】`
- テスト名は `ZZ_TEST_YYYYMMDD_用途`
- テスト送信の current 挙動
  - テンプレートパック画面の `テスト送信` は Bootstrap modal `#testModal`
  - 送信 form は `#message_modal_sender`
  - 送信先は hidden の `member_id`、表示用の名前入力は `modal_sender_text`
  - submit 先は `/api/message/send`
  - 2026-03-12 は `甲原 海人 / member_id=165543565` を送信先として指定して API 応答まで確認
  - ここでの `甲原 海人` は本文ではなく送信先名

### アカウント一覧（21件）

> スプレッドシート: [導線データ / Lステップ一覧](https://docs.google.com/spreadsheets/d/1eX0Fk-vs9UqBXIqAtbwvbwwXorMgE7HyxLB-YrGXlhY/edit)
> 詳細分析は `Master/addness/lstep_accounts_analysis.md` を参照

このシートは `稼働中` と `停止中` を同じタブで管理する。正本として扱うのは `稼働状況 = 稼働中` の行だけで、`停止中` の行は旧アカウントや誤接続候補の確認用とする。

| アカウントID | アカウント名 | タイプ |
|-------------|------------|--------|
| @303zgzwt | 【みかみ】アドネス株式会社 | メイン |
| @496sircr | スキルプラス | メイン |
| @076cqpuk | 【スキルプラス】フリープラン | メイン |
| @647asytm | みかみのSNSマーケ完全攻略LINE | メイン |
| @597wrjru | アドネス出版社 | メイン |
| @368czlci | アドネス株式会社 | メイン |
| @230vpgmc | スキルプラス@企画専用 | サブ |
| @631igmlz | みかみ@AI_個別専用 | サブ |
| @147anzid | みかみ@個別専用 | サブ |
| @949jhzuf | 【会員限定】フリープラン企画用 | サブ |
| @647asytm | みかみのSNSマーケ完全攻略LINE | サブ |
| @899laigi | みかみ@AI運用完全攻略 | サブ |
| @909refvl | 【予約窓口】スキルプラス合宿 | サブ |
| @035pilld | みかみの秘密の部屋 | サブ |
| @151lnnvv | みかみ@秘密の部屋 | サブ |
| @064ahgph | みかみの秘密合宿 | サブ |
| @750ikcwm | アドネス株式会社【人事採用部】 | サブ |
| @900kxiwl | スキルプラス【サポートLINE】 | サポート |
| @440xhtoq | スキルプラス【エリート】 | サポート |
| @402upiph | スタートダッシュ【サポートLINE】 | サポート |
| @974sshuu | スキルプラス【プライム】 | サポート |
| @838ssmtj | ライトプラン【会員限定】 | サポート |

**今後の方針**: CS用は「スキルプラス【サポートLINE】」に統合予定

### ログイン

- URL: `https://manager.linestep.net/account/login`
- 1Password自動入力 + reCAPTCHA突破
- 副管理者: 甲原海人
- 自動ログイン補助: `python3 System/scripts/lstep_login_helper.py --target <開きたいURL>`
- 認証診断 helper: `python3 System/scripts/lstep_auth.py`
- できること
  - 既存 Chrome CDP セッションを再利用する
  - 未ログイン時は `System/credentials/lstep.json` から `user_id / password` を自動入力する
  - ログイン済みなら target URL をそのまま開く
  - current login form の `name / password` selector に合わせて自動入力できる
- `lstep_auth.py` で見える current 条件
  - probe は `chrome_auto / chrome_default / chrome_profile_9 / chrome_debug_default`
  - action probe は `GET /api/actions?page=1`
  - login form は `POST /account/login`
  - field は `_token / name / password`
  - login page の `reCAPTCHA enabled=true`
- 限界
  - reCAPTCHA の画像 challenge が出た場合だけは手動確認が必要
  - ただし、ログイン画面を開く、ID/PW を入れる、checkbox を試すところまでは自動で進める
  - 2026-03-12 時点の probe では、上記 cookie source は全て `401 Unauthorized`
  - この状態では requests helper だけでは復旧できず、browser login が必要
  - 2026-03-12 の Cursor sandbox では
    - `open URL` が LaunchServices で失敗
    - `osascript` で `Google Chrome` を取れない
    - Chrome 直起動も crashpad permission で失敗
    した
  - つまり、この sandbox 内からの browser 起動は再現性が低く、手動 login を前提にした方が早い

### ログイン復旧の優先順位

1. `CDP 既存セッション再利用`
   - 使う条件: `python3 System/scripts/lstep_auth.py` で `cdp.alive = true`
   - 理由: もっとも再現性が高く、reCAPTCHA を踏まずに戻れる可能性が高い
2. `CDP + 自動入力 + checkbox 試行`
   - 使う条件: `cdp.alive = true` だが未ログイン
   - 理由: `lstep_login_helper.py` が `name / password` を埋め、checkbox まで寄せられる
3. `手動 browser login`
   - 使う条件: `cdp.alive = false`、または image challenge が出た時
   - 理由: 最後はこれが確実
4. `cookie 直利用`
   - 使う条件: `auth_alive = true`
   - 理由: API 読み取りだけなら最速
   - ただし今回の probe では該当なし

---

## Lステップの主要機能（左サイドバー順）

### 1. トップ
- 有効友だち数・ブロック率の確認
- 送信可能数の確認（Lステップ残数 / LINE公式残数）
- 友だち数推移（日別: 登録数・ブロック数）

### 2. 1対1トーク
- 個別のLINEメッセージ送受信
- 友だちリスト: 全友だち一覧（タグ・情報で検索可能）
- トーク一覧: 最新メッセージ順のリスト
- 個別トーク: 特定友だちとの会話画面

### 3. メッセージ配信

#### シナリオ配信
- **用途**: 登録後の自動ステップ配信（教育シナリオ）
- **構成**: シナリオ → ステップ（日数/時間指定）→ メッセージ
- **オンボーディング利用**: 入会直後から段階的にメッセージを送る
- **URL**: `https://manager.linestep.net/line/content/group`
- **API**
  - フォルダ一覧: `https://manager.linestep.net/api/content-group-groups`
  - シナリオ一覧: `https://manager.linestep.net/api/content-groups?group={group_id}&page=1`
  - シナリオ詳細: `https://manager.linestep.net/api/v1/content_groups/{id}`
- 補足: 旧メモにある `/api/journeys` は historical な endpoint で、current UI では `content-group` 系を読む方が正確

#### 一斉配信
- **用途**: 全友だち or セグメントへの一括配信
- **絞り込み**: タグ・友だち情報・配信日時で指定

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/magazine`
- `新規配信` の create 画面は `https://manager.linestep.net/magazine/new`
- 画面上部に
  - `新規配信`
  - `テンプレート配信`
  が並ぶ
- current 一覧では
  - `タイトル`
  - `配信日時`
  - `編集`
  - `配信条件`
  - `内容`
  - `開封数`
  が visible だった
- つまり、一斉配信は `送る画面` というより、`配信履歴と配信条件を見返す画面` としても重要
- `スキルプラス【サポートLINE】` でも same UI を確認済み
  - 画面上部は `新規配信 / テンプレート配信`
  - current visible 一覧は `0 件見つかりました`
  - つまり current は配信履歴より、シナリオ・テンプレート・流入経路中心で運用している可能性が高い
- 2026-03-13 の live で `新規配信` の draft 保存を exact 化した
  - 管理用タイトルは hidden の `#template_name` ではなく、画面上部の visible `input.form-control` が主入口
  - 本文は visible `.ProseMirror` が主入口
  - `下書き保存` は `#v_draft_save`
  - 保存成功時は `下書き [テキスト]... を新たに保存しました。` の toast が出る
  - `下書きを開く` から `https://manager.linestep.net/line/draft/magazine` に入る
- draft の削除は row menu ではなく bulk action だった
  - draft 一覧の row 左端 checkbox の `label[for="<checkbox_id>"]` を押して選択
  - 上部 button `チェックをした下書きを削除する`
  - confirm modal は出ず、そのまま削除される
  - 成功時は `選択した下書きを削除しました。` の toast
  - 再読込後に row が消える
- 2026-03-14 の live smoke では `ZZ_TMP_20260314_BroadcastSmoke_01` を使い、
  - `新規配信`
  - 管理用タイトル input
  - `.ProseMirror`
  - `下書き保存`
  - `下書き一覧`
  - `チェックをした下書きを削除する`
  まで end-to-end で通した
  - `draft_exists 1`
  - `exists_after_delete 0`
  まで確認した
- つまり、一斉配信の後片付けは
  - `一斉配信（新規）` 画面に戻るのではなく
  - `下書き一覧（一斉配信）` で選択削除する
  が current 手順

#### 自動応答
- **用途**: キーワードに応じた自動返信
- **設定**: キーワード → アクション（テンプレート送信等）

### 4. テンプレート
- **用途**: 再利用可能なメッセージの定義
- **タイプ**: テキスト / 画像 / 動画 / フレックスメッセージ
- **フレックスメッセージ**: ブロック単位で構築（画像・テキスト・ボタンの組み合わせ）
- **フォルダ管理**: グループ（group=ID）でフォルダ分け
- **URL**: `https://manager.linestep.net/line/template`
- **API**: `https://manager.linestep.net/api/templates`
- **編集**: `https://manager.linestep.net/line/template/edit_v3/{template_id}?group={group_id}&editMessage=1`
- **フレックス本文取得**: `https://manager.linestep.net/api/template/lflexes/{template_id}`
  - `editor_json` にボタン URL / LIFF / 画像 URL が入る
  - 導線監査では `api/templates` よりこちらの方が重要

#### 実運用上の注意

- 2026-03-09 時点で、`【みかみ】アドネス株式会社` `みかみ@AI_個別専用` `みかみ@個別専用` のテンプレート一覧は `126件 / 130グループ` で完全一致した
- 少なくとも甲原さんの権限範囲では、テンプレートはアカウント別というより `ユーザー共通ライブラリ` として見える
- そのため account ごとの差は、主に `流入経路 / タグ / シナリオ` に出る

#### アドネスでの current の見方

- `【みかみ】アドネス株式会社` `みかみ@AI_個別専用` `みかみ@個別専用` は、テンプレート一覧が共通ライブラリとして見える
- 実務で差が出るのは `どのテンプレートをどの流入経路 / シナリオ / リッチメニューから使うか`
- `スキルプラス【サポートLINE】` は current で `50件` のテンプレートを持ち、主用途は
  - 受講生サポート
  - コース移行
  - 合宿詳細
  - 日報 / 週報
  - 1on1予約導線
  - イベント案内
- `【予約窓口】スキルプラス合宿` は `12件` で、主用途は
  - 予約ページ送付
  - 本人確認
  - Zoomリンク送付
  - 合宿当日連絡

#### 作るときの基本型

- まず `フォルダ` を決める
- 次に `テンプレート名` を命名規則へ寄せる
- フレックスなら
  - 画像
  - テキスト
  - ボタン
  の3層で意味を切る
- URL を置く場合は
  - 失効しうるLINE導線なら short.io を優先
  - 予約やタグ付与が目的なら Lステップ の流入経路 URL を優先
- 導線監査や改修時は `api/templates` だけで終わらせず、`api/template/lflexes/{template_id}` の `editor_json` で実際のボタン遷移先まで見る

#### フレックスメッセージの構造
```
パネル（1/1〜複数）
├── サイズ: S / M / L
├── テーマカラー
└── ブロック（1〜複数）
    ├── 画像ブロック: 画像 + アクション（URL/テンプレ送信/回答フォーム）
    ├── テキストブロック: テキスト内容
    └── ボタンブロック: ボタンテキスト + アクション
```

**アクション種類:**
- テンプレートを送信
- URLを開く（LINEブラウザ/外部ブラウザ）
- 回答フォームを開く
- タグ追加/削除
- 友だち情報代入
- リッチメニュー変更

#### フレックスメッセージの representative と意図

- `3月 スキルプラス合宿 集客`
  - id
    - `249005485`
  - UI 上の種類
    - `フレックスメッセージ`
  - 一覧からの current edit URL
    - `/line/template/edit_v3/249005485?group=0&editMessage=0`
  - alt
    - `【3月スキルプラス合宿】のご案内`
  - 構成
    - `1 panel`
    - `画像` 1
    - `テキスト` 3
    - `ボタン` 1
  - editor_json で分かること
    - `themeColors` を持つ
    - `button.action_type = liny-action`
    - `action_label = Linyアクション`
    - `action_description` は `[URLを開く] ... をトーク内ブラウザ(大)で開きます`
    - `action_url` は `follow=@909refvl&lp=HBTqth` を含む LIFF
  - action
    - `詳細はこちら`
    - 見た目は 1 button
    - 内部 action の種類は `liny-action`
    - 実質的な挙動は `URLを開く`
    - 遷移先は `【予約窓口】スキルプラス合宿` 側の LIFF
  - 意図
    - `興味はあるが動けていない` を `今すぐ詳細を見る` に変える
  - 良い点
    - 1 panel 内で
      - 感情
      - 事実
      - urgency
      - CTA
      の順が揃っている

- `2月 スキルプラス合宿 集客`
  - id
    - `243548267`
  - alt
    - `【2月スキルプラス合宿】のご案内`
  - 構成
    - `1 panel`
    - `画像` 1
    - `テキスト` 4
    - `ボタン` 1
  - action
    - `参加申し込みはこちら`
    - 実体は `URLを開く`
    - 遷移先は `【予約窓口】スキルプラス合宿` 側の LIFF
  - 意図
    - `参加価値は理解したが後回し` を `今ここで申込む` に変える
  - 良い点
    - `悩みの言語化 -> 合宿価値 -> 開催情報 -> urgency -> CTA`
      が 1 panel で閉じている

- `20250228 コース移行のお知らせ`
  - id
    - `247339595`
  - 構成
    - `タイトル` 1
    - `テキスト` 3
    - `ボタン` 2
  - alt
    - `⚠️新・コース移行のお知らせ⚠️`
  - action
    - `①新コース登録はこちら`
    - `②コース移行ガイドはこちら`
  - 意図
    - `何をすればよいか分からない` を `手順どおりに移行できる` に変える
  - 良い点
    - CTA が 2 つでも役割が明確に分かれている
      - 登録
      - ガイド確認
    - `タイトル -> 現状説明 -> 変更点 -> 手順 -> 2CTA`
      の順で、迷いを減らす設計になっている

- `対象者に告知（1on1予約→実施でアマギフ1,000円）`
  - id
    - `239319965`
  - alt
    - `[姓]さんへ本日限定のお知らせ`
  - 構成
    - `画像` 1
    - `テキスト` 1
    - `ボタン` 1
  - action
    - ボタン文言 `今すぐ予約する`
    - ラベルは `Linyアクション`
    - 実体は `URLを開く` ではなく
      - `タグ[アマギフ_オプト]を追加`
      - `テキスト[...]を送信`
  - 意図
    - `予約した方がよいか分からない` を `いま予約すると得だし、動く理由がある` に変える
  - 良い点
    - CTA クリック時に行動だけでなく状態も更新している
    - 後続メッセージまで含めて 1 つの認識変換にしている

- `12/14 スキルプラス合宿 予約専用LINE誘導１`
  - id
    - `234752948`
  - alt
    - `【スキルプラス合宿ご予約の方へ】大切なご連絡です`
  - 構成
    - `画像` 1
    - `テキスト` 3
    - `ボタン` 1
  - action
    - ボタン文言 `【合宿専用】の公式LINE登録はこちら`
    - ラベルは `Linyアクション`
    - 実体は `URLを開く` ではなく `テキスト[ありがとう...]を送信`
  - 意図
    - `別LINEへ移動が必要だが、何をすればいいか分からない` を `専用窓口へ移って手続きを続ける` に変える
  - 良い点
    - `専用LINE登録が必要` という重要な認識を text で先に作っている
    - CTA の裏側は text send なので、押した後の次導線まで control している

- `ゴール設定1on1予約案内【2026/01/12：アマギフ訴求】`
  - id
    - `239338635`
  - alt
    - `この機会に、ぜひ1on1をご予約ください☺️`
  - 構成
    - `画像` 1
    - `テキスト` 1
    - `ボタン` 1
  - action
    - ボタン文言 `今すぐ予約する`
    - 実体は `URLを開く` ではなく
      - `タグ[アマギフ_オプト]を追加`
      - `テキスト[こちらから...]を送信`
  - 意図
    - `1on1 の価値は分かったが今は予約していない` を `今ここで予約線へ進む` に変える
  - 良い点
    - `準備不要 / 手ぶらで来てください`
      の一文で予約の心理障壁を下げている
    - click と同時に状態も更新している

- `2月16日スキルプラス 大幅アップデートのお知らせ`
  - id
    - `245089782`
  - 構成
    - `動画` 1
    - `画像` 1
    - `テキスト` 4
  - action
    - なし
  - 意図
    - 変更の理由と全体像を先に納得させる
  - 良い点
    - まだ行動させず、認識合わせに集中している

- `スキルプラス 大幅アップデートのお知らせ`
  - id
    - `236884696`
  - 構成
    - `動画` 1
    - `画像` 1
    - `テキスト` 4
  - action
    - なし
  - 意図
    - `サービス変更を部分的にしか理解していない` を `アップデート全体像と価値が分かる` に変える
  - 良い点
    - `変更理由 -> 変更点1 -> 変更点2 -> 変更点3`
      の順でアップデートを整理している

- `SL.AIアップデートのお知らせ`
  - id
    - `242752111`
  - 構成
    - `動画` 1
    - `タイトル` 1
    - `テキスト` 4
  - action
    - なし
  - 意図
    - `何が変わったか分からない` を `変更点と意味が分かっている` に変える
  - 良い点
    - CTA を置かず、重要告知に役割を絞っている
    - `動画 + タイトル + テキスト` で認識合わせを優先している

- `日報提出方法変更のお知らせ`
  - id
    - `242714460`
  - 構成
    - `動画` 1
    - `タイトル` 1
    - `テキスト` 4
  - action
    - なし
  - 意図
    - `これまでの提出習慣のまま動いてしまう` を `新しい提出方法で迷わず提出できる` に変える
  - 良い点
    - `変更内容 / 旧運用と新運用の差 / 実行場所 / 開始日`
      が順に並んでいて、誤操作を減らす

- `12/14 スキルプラス合宿 予約専用LINE誘導１`
  - id
    - `234752948`
  - alt
    - `【スキルプラス合宿ご予約の方へ】大切なご連絡です`
  - 構成
    - `画像` 1
    - `テキスト` 3
    - `ボタン` 1
  - action
    - ボタン文言 `【合宿専用】の公式LINE登録はこちら`
    - 実体は `URLを開く` ではなく `テキスト[ありがとう...]を送信`
  - 意図
    - `別 LINE に登録する必要があるのか不安` を `期限内に専用窓口へ移る` に変える
  - 良い点
    - `別物です` と `再度のご予約は不要`
      を入れて、余計な再予約や問い合わせを防いでいる

- `【障害報告】外部システム障害の影響に関するお知らせ`
  - id
    - `231576974`
  - alt
    - `⚠️一部サービスの閲覧障害のお知らせ⚠️`
  - 構成
    - `テキスト` 3
  - action
    - なし
  - 意図
    - `不安で問い合わせしたい` を `状況を理解し、待機でよい` に変える
  - 良い点
    - `発生事実 / 影響範囲 / 復旧目処 / 補足案内 / お詫び`
      が短く整理されている

#### フレックスメッセージの良い / 悪い

- 良い
  - 1 message で役割が 1 つに寄っている
  - `ブロック` の順が
    - 共感 / 問題提起
    - 情報整理
    - urgency
    - CTA
    のように自然
  - `ボタン` の action が message の目的と一致している
  - `画像` も decoration ではなく文脈補強として使われている

- 悪い
  - 1 message に
    - 告知
    - 手順説明
    - FAQ
    - 営業
    を詰め込む
  - CTA が抽象的で、押した後の期待とズレる
  - `画像` が message の役割と無関係
  - `ボタン` が複数あるのに役割分担が曖昧

#### フレックスメッセージを current の良い例として読む時の exact 分類

- `募集型`
  - 例: `3月 スキルプラス合宿 集客`
  - 例: `2月 スキルプラス合宿 集客`
  - 役割: 興味を申込行動へ変える
  - 読む順: `alt_text -> 画像 -> urgency を含む text -> CTA button -> action`
  - exact 実値
    - `3月 スキルプラス合宿 集客`
    - `alt_text = 【3月スキルプラス合宿】のご案内`
    - `image 1 / text 3 / button 1`
    - button は `Linyアクション` 表示でも、中身は `URLを開く`
    - action_url は `follow=%40909refvl&lp=HBTqth` の LIFF
- `移行案内型`
  - 例: `20250228 コース移行のお知らせ`
  - 役割: 手順の迷いを消して移行完了へ進める
  - 読む順: `見出し -> 何をすべきか -> 2 button の役割分離 -> 遷移先`
- `状態更新連動型`
  - 例: `対象者に告知（1on1予約→実施でアマギフ1,000円）`
  - 例: `ゴール設定1on1予約案内【2026/01/12：アマギフ訴求】`
  - 役割: CTA クリックと同時にタグや follow-up を発火し、次の分岐条件も作る
  - 読む順: `誰向けか -> 何が得か -> CTA 文言 -> action_description`
- `障害告知型`
  - 例: `12/5 サーバーエラーによる 一部サービスの閲覧障害`
  - 役割: 不安を減らし、不要な問い合わせを減らす
  - 読む順: `何が起きているか -> 何が影響範囲か -> 今待てばいいか -> CTA なしで良いか`
- `運用変更告知型`
  - 例: `日報提出方法変更のお知らせ`
  - 役割: ルール変更を伝え、提出行動を揃える
  - 読む順: `何が変わったか -> なぜ変わったか -> 自分にどう影響するか -> CTA が不要なら置かない`
- `重要アップデート告知型`
  - 例: `2月16日スキルプラス 大幅アップデートのお知らせ` / `スキルプラス 大幅アップデートのお知らせ` / `SL.AIアップデートのお知らせ`
  - 役割: 変更の背景と価値を理解させ、後続導線の摩擦を減らす
  - 読む順: `何が変わったか -> なぜ変わるか -> どう使うべきか -> CTA が不要なら置かない`
  - exact 実値
    - `2月16日スキルプラス 大幅アップデートのお知らせ`
    - `alt_text = スキルプラス 大幅アップデートのお知らせ`
    - `video 1 / image 1 / text 4`
    - CTA は置かず、`変更内容の理解` と `不安軽減` を優先している
- `専用窓口誘導型`
  - 例: `12/14 スキルプラス合宿 予約専用LINE誘導１`
  - 役割: 既存の予約状態を維持したまま、案内窓口だけを正しい LINE へ切り替える
  - 読む順: `何の連絡か -> なぜ別窓口か -> 期限 -> action_description`
  - exact 実値
    - `alt_text = 【スキルプラス合宿ご予約の方へ】大切なご連絡です`
    - `image 1 / text 3 / button 1`
    - button は `Linyアクション` 表示だが、実体は `テキスト[ありがとう...]を送信`
    - つまり `別 LINE へ飛ばす URL` ではなく、トーク内で次の案内を発火する型として読む
- つまり、良い `フレックスメッセージ` は first view 的に派手かどうかではなく、`何の認識を変える message か` が一瞬で切れる

#### フレックスメッセージを新規で作る時の exact 観点

- いま優先するのは `見た目を磨くこと` ではなく、`どんな依頼でも正しくミスなく構築できること`
- したがって最初に exact 化するのは
  - 正しい入口
  - block の追加順
  - `アクション設定`
  - `テスト送信`
  - 後片付け
  の再現性
- 入口は
  - `テンプレート -> 新しいテンプレート -> フレックスメッセージ`
- editor に入ったら、まず次をこの順で決める
  1. `テンプレート名`
  2. `パネル設定`
  3. `背景`
  4. `テーマカラー（共通）`
  5. `サイズ（共通）`
  6. `ブロック設定`
  7. `画像`
  8. `テキスト`
  9. `ボタン`
  10. `アクション`
  11. `ボタンスタイル`
- Addness の current では、考える順番も UI 順ではなく次がズレにくい
  1. 何の状態の人に送るか
  2. 何の認識を変えるか
  3. 何を 1 つだけ行動させるか
  4. その行動を `ボタン` にするか `画像` にするか
  5. その後に `テーマカラー` や余白を整える
- つまり、`見た目を作ってから action を足す` ではなく
  - `役割`
  - `行動`
  - `アクション`
  - `見た目`
  の順で詰める
- Addness で良い `フレックスメッセージ` に寄せる時の判断は次
  - `画像`
    - decoration ではなく promise の補強に使う
  - `テキスト`
    - 1 block 1 役割
    - `共感 / 問題提起 / 事実 / urgency / CTA前の後押し`
    のどれを担うかを先に決める
  - `ボタン`
    - 1 つなら main CTA に振り切る
    - 2 つ以上なら役割の分離が説明できる時だけ置く
  - `アクション`
    - `URLを開く`
    - `回答フォーム`
    - `テンプレートを送信`
    のどれが正しいかを、押した後に起きる行動から逆算する
  - `デザイン`
    - 強い配色は CTA と見出しだけに寄せる
    - 情報を増やすより、読ませる順番を作る
- 送信前の最低確認
  1. `プレビュー`
  2. `アクション` の遷移先
  3. `テスト送信`
  4. 実機で `押した後の挙動`

#### テスト送信の exact 操作

- current の入口は editor 画面ではなく、`テンプレート` 一覧の対象行右端 `...`
- `...` を押すと
  - `コピー`
  - `名前を変更`
  - `テスト送信`
  - `一斉配信を作成`
  - `削除`
  が出る
- `テスト送信` を押すと modal `テスト送信先選択` が開く
- modal 内の current ラベルは
  - `友だち名`
  - `キャンセル`
  - `テスト`
- Addness の current 運用では、送信先は常に `甲原 海人`
- つまり review の exact 手順は次で固定
  1. `テンプレート` 一覧で対象行を探す
  2. 行右端 `...`
  3. `テスト送信`
  4. `甲原 海人` を選ぶ
  5. `テスト`
  6. 実機で `表示 / action / 押下後挙動` を確認する
  7. 不要な test asset は削除する

#### テンプレートパックを新規で作る時の exact 観点

- 入口は
  - `テンプレート -> 新しいパック`
- pack で最初に決めるのは `見た目` ではなく `順番`
- Addness の current では、`テンプレートパック` は `message をまとめる箱` ではなく
  - `認識を変える step`
  - `行動させる step`
  を分ける container として使うと強い
- representative の `YouTube切り抜き 無料相談会告知` を基準にすると、次の順がズレにくい
  1. `本文` で urgency や問題認識を作る
  2. `テンプレート` で CTA を visual に渡す
- 逆に悪い使い方は
  - step 1 で全部説明する
  - step 2 でも同じ説明を繰り返す
  - `本文` と `テンプレート` の役割が重複する
- pack を作る時の review 観点
  1. step 1 は何の認識を変えるか
  2. step 2 は何を行動させるか
  3. step 同士の役割が重複していないか
  4. `テスト送信` 後に、受信側で step の順番が自然か

#### テンプレートパックの representative

- current 一覧で、pack として確認できた representative は少なくとも次
  - `YouTube切り抜き 無料相談会告知`
  - `動画編集　進捗報告　テンプレート`
  - `2024.10.29 アンケート`
- この3本は役割が分かれていて、pack をどう使うかの current 幅を読む時に向いている
  - `YouTube切り抜き 無料相談会告知`
    - `認識変換 -> CTA`
  - `動画編集　進捗報告　テンプレート`
    - id は `229366734`
    - `運用報告 -> 回答 / 進捗入力`
    - `step件数 = 2`
    - `step1 = 本文`
    - 冒頭は `[name]さん 本日もお疲れ様でした！`
    - 今日の進捗を報告させる理由づけをテキストで作る
    - `step2 = テンプレート`
    - preview は `【カルーセル】...`
    - つまり本文で状況を揃えてから visual CTA に渡している
  - `2024.10.29 アンケート`
    - id は `173198692`
    - `回答収集`
    - `step件数 = 2`
    - `step1 = 本文`
    - アンケート実施理由と協力依頼をテキストで作る
    - `step2 = 本文` と見えるが、実体は `カルーセルメッセージ(新方式)`
    - preview は `【カルーセル】アンケートへ`
    - panel 1 の CTA は `協力する！`
    - selected action は `回答フォームを開く`
    - current 実体の template は `委託先アンケート　カルーセル`
      - id は `226111956`
      - `panel_count = 1`
      - `answer_type = 1`
      - `action_form_id = 946155`
      - `action_liff_size = tall`
    - つまり `本文で理由づけ -> カルーセルで回答行動` の 2 step になっている
- `動画編集　進捗報告　テンプレート` の current 周辺資産として、同じ一覧には少なくとも
  - `動画編集進捗報告　リマインド` (`標準メッセージ`)
  - `動画編集　進捗報告　カルーセル` (`カルーセルメッセージ(新方式)`)
  - `動画編集　進捗報告　テンプレート` (`テンプレートパック`)
  が並んでいた
- `アンケート1通目`
  - id は `220923233`
  - `step件数 = 3`
  - `1件目 = 本文`
    - 特典配布時の案内と同意に近い補足
  - `2件目 = 本文`
    - `[name]さん、追加ありがとうございます` から始まり、特典受け取りの価値を text で伝える
  - `3件目 = 本文` と見えるが preview は `【カルーセル】回答後に【...】`
  - つまり `前置き -> 価値提示 -> visual CTA` の 3 step 構成で、すぐ CTA に行かず認識を順番に揃える current 例
- `12月プライムセミナー告知文`
  - id は `220925443`
  - `step件数 = 3`
  - `1件目 = 本文`
    - 緊急企画、開催時刻、問題提起を text で先に置く
  - `2件目 = 本文` preview は `【画像】`
    - 中盤で image を挟み、視覚で熱量を上げる
  - `3件目 = 本文`
    - `導入！` と返信させる明確な CTA
  - つまり `告知 -> 視覚訴求 -> 返信CTA` の 3 step で、申込導線ではなく `返信を返させる` 型の current 例
- したがって、この family は
  - text で状況を揃える
  - visual で入力や確認を friction なくさせる
  という current の運用オペレーション型として読むのがズレにくい
- つまり pack は
  - sales 導線だけの機能ではない
  - `複数 step で認識や入力を滑らかにつなぐ container`
  として読む方が current に近い

#### 既存の良い `テンプレートパック` を分解する exact 順番

- 一覧で pack を見つけたら、まず `テンプレート名` より `何を変える pack か` を先に切る
  - `無料相談会告知`
  - `進捗報告`
  - `アンケート`
  のように、`行動` か `入力` か `案内` かで役割を先に決める
- その後に `プレビュー` や `メッセージパック「...」 設定` 画面で、次の順に見る
  1. `step件数`
  2. `1件目` が `本文` か `テンプレート` か
  3. `2件目以降` が、認識変換の続きなのか、CTA なのか、回答入力なのか
  4. `テスト送信`
  5. 実際の受信順
- Addness の current で良い pack は、各 step の役割が重複しない
  - `1件目 = 問題認識 / urgency / 事情説明`
  - `2件目 = CTA / 回答 / 進捗入力`
  のように、`何を変える step か` が分かれている
- 悪い pack は、各 step が同じことを言っている
  - `本文` で全部説明したあと
  - `テンプレート` でも同じ説明を繰り返す
  - `どれを押せばいいか` が逆にぼやける

#### `テンプレートパック` を high-quality と判断する時の観点

- `YouTube切り抜き 無料相談会告知`
  - `認識変換 -> CTA` の分業が明確
  - `本文` は urgency と理由づけ
  - `テンプレート` は押す先の明確化
- `動画編集　進捗報告　テンプレート`
  - sales ではなく、運用オペレーションを滑らかにする代表例として読む
  - `進捗を出す` という行動を friction なく起こさせる pack として扱う
  - `step1 = 本文`, `step2 = テンプレート` で役割が明確に分かれている
- `2024.10.29 アンケート`
  - `回答してもらう` こと自体がゴールの pack として読む
  - 認識変換より、`迷わず入力させる` 設計が主になる
  - `step2` の CTA が `回答フォームを開く` に固定されており、行動が 1 つに絞られている
- つまり `テンプレートパック` は
  - `長い内容をまとめて送る機能`
  ではなく
  - `複数 step に役割を分け、受信体験を滑らかにする機能`
  として読むとズレにくい

#### 既存の良いテンプレートを exact に読む時の共通順番

- `標準メッセージ`
  1. `何の状態の人に送るか`
  2. `本文の最初の 1-2 行で何の認識を変えているか`
  3. CTA は 1 つに絞れているか
- `カルーセルメッセージ(新方式)`
  1. `alt_text`
  2. `panel_count`
  3. `panel text`
  4. `button title`
  5. `action_type / action_form_id / action_liff_size`
- `フレックスメッセージ`
  1. 画像が `内容の主役` なのか `補助` なのか
  2. テキストが `状況説明` なのか `緊急告知` なのか
  3. ボタンが 1 つに絞れているか
  4. `URLを開く` か `回答フォーム` か `友だち追加` か
  5. 見た目が `読ませる` ためか `押させる` ためか
  6. 画像ごとに action が分かれているか、ボタン 1 つに集約しているか
- `テンプレートパック`
  1. step ごとの役割分担
  2. 前 step が次 step の意味を作れているか
  3. 最後の step が `何を押せばいいか` を明確にしているか

#### current の representative を追加で読む時のメモ

- `選べる3種のPR`
  - id は `220916725`
  - `フレックスメッセージ`
  - `alt_text = あなたはどのAIから始める？`
  - `panel_count = 3`
  - `text 4 / image 4`
  - 画像 4 つとも `Linyアクション` を持ち、実体は `URLを開く`
  - 遷移先は同じ LINE account だが `lp` が分かれている
  - つまり `複数商品を比較させる` より、`相手の自己認識に近い入口を選ばせる` segmentation 型の current 例
- `アンケート_フィニッシュ`
  - id は `220923081`
  - `標準メッセージ`
  - 6 行、URL 1 本
  - 構成は `回答完了へのお礼 -> 特典 URL -> 次に取りたい行動（サポート希望の返信）`
  - つまり `完了後の friction を下げながら次の相談行動へつなぐ` finish 型の current 例

### 5. 予約管理
- **予約機能は2種類**: `カレンダー予約` と `イベント予約`
- `【予約窓口】スキルプラス合宿` を触るときは、ここに加えて `友だち情報管理` をセットで見る
- 理由は、予約そのものより `どの日程に誰が参加するか` の friend info が本体だから

#### カレンダー予約

- 個別相談、1on1、面談、担当者ごとの枠管理に向く
- 本質は `誰に見せるか` `予約後に何を送るか` `どの外部カレンダーに同期するか` が別レイヤーで分かれていること
- 設定の中心は
  - 担当者
  - コース
  - 予約枠
  - 営業日 / シフト
  - リマインド
  - Googleカレンダー連携
- 実務では少なくとも次の 3 系統を分けて考える
  - `予約枠 / コース`
    - 何を予約させるか
  - `アクション / リマインダ / フォロー`
    - 予約直後、前日、直前、終了後に何を送るか
  - `外部サービス連携`
    - どの Google カレンダーに予定を書き、どの Google カレンダーをシフトとして使うか
- `アクション` と `リマインダ / フォロー` は一覧名だけでは送信対象を判定できない
  - 実際の送信対象は action の条件設定内にある `カレンダー予約 / 予約枠 / コース` で分岐している
  - 同じカレンダー内に複数コースを共存させる時は、`コース` 条件まで切らないとメッセージが混線する
- `外部サービス連携` は `コース` 単位ではなく `予約枠` 単位
  - modal で選べるのは `Googleアカウント名 / カレンダーID / 予約枠 / 連携対象`
  - 保存 payload も `salon_resource_id` を使う
  - したがって `コースごとに別 Google カレンダーへ反映` をしたいなら、`コース` を増やすだけでは足りず `予約枠` か `カレンダー` 自体を分ける必要がある
- `連携対象` は
  - `すべて`
  - `予約をGoogleカレンダーに連携`
  - `Googleカレンダーをシフトに連携`
  の 3 種
- 同じ予約枠の `予約 -> Googleカレンダー` を複数 Google カレンダーへ向ける保存は server 側で reject される
- 公式には `担当者ごとのコース設定` と `営業日 / シフト設定` を持ち、`予約変更 / キャンセル` までLINE上で回せる
- 2025-11 の公式アップデートでは
  - `予約枠とコース` のコピー作成
  - Googleカレンダー予定名への `予約枠名` 反映
  が入っている

#### イベント予約

- セミナー、合宿、オフ会、研修など `特定日時に開催する単発イベント` 向き
- アドネス current では
  - `スキルプラス【サポートLINE】` でイベント情報を出す
  - イベント詳細は UTAGE ページに置く
  - 予約ボタンから Lステップ の流入経路を踏ませる
  - 予約タグで前日 / 当日案内を打つ
  この形が最も強い
- 公式には `開催日時 / 場所 / 場所URL / 予約枠` を予約画面に出せる
- 2025-11 の公式アップデートでは、イベント予約の `プラン作成上限が50件` まで拡張された

#### アドネスでの current 解釈

- `スキルプラス【サポートLINE】`
  - イベント情報の配信口
  - 予約タグ付与の起点
  - 前日 / 当日案内の送り元
- `【予約窓口】スキルプラス合宿`
  - 実務予約の受付口
  - 本人確認
  - 予約ページ送付
  - Zoomリンク送付
  - 日程別参加管理

#### live で確認した exact 操作

- イベント予約の一覧URLは `https://manager.linestep.net/line/reserve/event`
- 画面上部に
  - `新しいフォルダ`
  - `新しいイベント`
  が出る
- 既存イベントの行には
  - `友だち予約URL`
  - `友だち予約履歴URL`
  - `予約枠一覧`
  - `CSV出力`
  - `予約者一覧`
  - `プレビュー`
  が並ぶ
- `【予約窓口】スキルプラス合宿` で visible だった current event は
  - `3月 スキルプラス合宿`
  - `2月 スキルプラス合宿`
  - `1月 スキルプラス合宿`
  - `12/27 スキルプラス合宿`
  - `12/20 スキルプラス合宿`
  - `12/14 スキルプラス合宿`
- 予約数も `33/120` `158/243` `182/231` のように一覧上で見える
- つまり、イベント予約は `イベント作成` だけでなく
  - 予約URL配布
  - 予約者確認
  - CSV出力
  まで含めて実務画面として使う

- カレンダー予約の一覧URLは `https://manager.linestep.net/line/reserve/salon`
- `【予約窓口】スキルプラス合宿` では current 時点で intro 画面寄りで
  - `利用を開始する`
  - `新しいカレンダー`
  が出ていた
- この account では、少なくとも visible 設定としてはイベント予約の方が主で、カレンダー予約は current の本線ではなさそう
- `スキルプラス【サポートLINE】` の `広告コース：設定サポート` では、1 つのカレンダー内に
  - `設定サポート`
  - `スキルプラス 広告コース1on1`
  のような別コースを共存させられることを live で確認した
- この時、`予約設定 -> アクション` と `予約設定 -> リマインダ / フォロー` は
  - `カレンダー予約`
  - `予約枠`
  - `コース`
  の条件で分けると、同じカレンダーの中でもコースごとに別メッセージを送れる
- `外部サービス連携` の current API は `GET /api/salon/{salon_id}/googlecalendars`
- 連携追加は `POST /api/salon/{salon_id}/googlecalendars`
  - body 例
    - `{\"salon_resource_id\":109117,\"google_token_id\":16079,\"google_calendar_id\":\"koa800sea.nifs@gmail.com\",\"link_target\":\"all\"}`
- 連携解除は `DELETE /api/salon/{salon_id}/googlecalendars/{google_calendar_primary_id}/{purpose}/{association_id}`
- つまり、カレンダー予約の live 検証は UI 一覧を見るだけで終えず
  - action 条件
  - reminder 条件
  - google calendar association
  まで API で確認した方が事故が少ない

### 6. 回答フォーム
- **用途**: アンケート・申込フォーム（LINE内で表示）
- **URL**: `https://manager.linestep.net/line/form`
- **編集**: `https://manager.linestep.net/lvf/edit/{form_id}?group={group_id}`
- **フォルダ管理**: グループ別

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/form`
- `新しい回答フォーム` の create 画面は `https://manager.linestep.net/lvf/edit/new`
- 画面上部に
  - `新しいフォルダ`
  - `新しい回答フォーム`
  が出る
- current 一覧では
  - `フォーム名`
  - `スプレッドシート連携`
  - `回答状態`
  - `登録日`
  - `公開状態`
  が visible だった
- current row には `呼び出しタグ` `外部用` のラベルも見える
- つまり、回答フォームは `フォーム作成` だけでなく
  - 公開中か
  - スプレッドシート連携があるか
  - どの用途ラベルが付いているか
  まで一覧で見る前提
- `スキルプラス【サポートLINE】` で visible だった folder は `未分類 11 / オンボーディングフロー（下書き）3 / セミナーNPS 3 / NPS 20 / ゴール設定 2 / 数値管理（小澤2511）1 / アドネス合宿 1 / お仕事チャレンジ 6 / SL.AIアカウント突合フォーム 3`
- サポートLINEの回答フォームは、`NPS / ゴール設定 / 合宿 / 数値管理 / アカウント突合` が current の主用途
- 2026-03-13 の live で最小構成の `回答フォーム` を exact 化した
  - 画面上部の visible 主入力は
    - `input[name="formname"]` = `フォーム名(管理用)`
    - `input[name="pagetitle"]` = `タイトル`
  - つまり、現在は data-testid より visible field 名で読む方がズレにくい
  - 質問追加の current 入口は
    - `記述式(テキストボックス)` = `[data-testid="addTextBtn"]`
  - 追加後の最初の質問 block は
    - `data-testid="text_1"`
    - 質問名は `input[name="text_1_title"]`
  - save は `#lvbuildsave`
  - 保存成功時は `保存完了` の toast が出て、URL は `/lvf/edit/{form_id}` に切り替わる
- 一覧からの削除は row 右端 menu だった
  - row 右端 `...`
  - `削除`
  - confirm dialog `削除する`
  - 再読込後に row が消える
- row menu の current ラベルは少なくとも
  - `詳細を確認`
  - `公開設定を変更`
  - `コピー`
  - `テスト送信`
  - `削除`
  を確認した
- 2026-03-14 の live で `テスト送信` まで exact に通した
  - temp 名は `ZZ_TMP_20260314_AnswerFormSmoke_05`
  - 一覧 row の右端 button は 3 つで、右端 `more_vert` が menu 入口
  - `... -> テスト送信` で modal `テスト送信先選択` が開く
  - modal 内では
    - `友だち名`
    - 候補一覧
    - `キャンセル`
    - `テスト`
    が見える
  - 送信先は visible text の `甲原 海人` をそのまま押す
  - confirm は `テスト` だが、folder 名 `テスト` と衝突する
    - 実操作では `exact=True` 相当で confirm button を押す
  - 送信後は `TEST_SENT` まで確認
  - その後 `... -> 削除 -> 削除する` で削除し、再読込後 `exists_after_delete = 0`

#### フォームの構成要素
| 要素タイプ | 説明 |
|-----------|------|
| 小見出し | セクションの見出し（画像付きも可） |
| 中見出し | より大きな見出し |
| 記述式(テキストボックス) | 1行テキスト入力 |
| 段落(テキストエリア) | 複数行テキスト入力 |
| チェックボックス | 複数選択 |
| ラジオボタン | 単一選択 |
| プルダウン | ドロップダウン選択 |
| ファイル添付 | ファイルアップロード |
| 都道府県 | 都道府県選択 |
| 日付 | 日付ピッカー |
| メール登録 | メールアドレス入力 |

#### フォームのオプション設定
- 進むボタンテキスト / 送信ボタンテキスト
- 送信確認ダイアログ
- 回答期限 / 先着数制限
- 1人が回答できる回数（制限なし / 1度のみ）
- サンクスページURL（送信後のリダイレクト先）
- 回答後アクション（タグ追加・テンプレ送信等）
- 回答復元（2回目以降で前回の入力を復元）
- Googleスプレッドシート連携

---

## 良い / 悪い / NG 判断ログ（暫定）

### コンテンツを読む時の基準

- Lステップ の message も、単なる通知ではない
- `コミュニケーションの手段であり、ユーザーをこちらが意図した認識に変換するもの`
  として読む
- ただし Mailchimp と違って、Lステップ は長文教育の場ではない
- Addness の current では
  - 今の状態を正しく認識させる
  - 次にやることを 1 つに絞る
  - friction を下げて今すぐ動かせるようにする
  ことが中心

### 制作者意図の読み方

- `3月 スキルプラス合宿 集客`
  - 変えたい認識
    - `興味はあるが自分ごとではない`
    - を
    - `このイベントは今の自分に必要かもしれない`
    に変える
  - 次にしてほしい行動
    - 合宿予約ページを見る
- `ゴール設定1on1予約案内【2026/01/12：アマギフ訴求】`
  - 変えたい認識
    - `登録したが何をすればいいか分からない`
    - を
    - `まず1on1を予約すれば前に進める`
    に変える
  - 次にしてほしい行動
    - 1on1 を予約する
- `【障害報告】外部システム障害の影響に関するお知らせ`
  - 変えたい認識
    - `不具合が起きたが放置されているかもしれない`
    - を
    - `状況は把握され、案内も届いている`
    に変える
  - 次にしてほしい行動
    - 基本はなし
    - 目的は trust 保持

### 良い

- 流入経路名を `集客媒体_ファネル名-イベント名` に寄せる
- 新規流入タグを `【新規】...`、通常流入タグを `媒体_ファネル-イベント` で分ける
- account の役割を `メイン / サブ / サポート` で分けて考える
- 実際の account 判定を `follow_url` と `LINE名` で行う
- current 導線は `landing / tag / content-group / trigger` の4点セットで見る
- 1 message で 1 状態だけを前に進める
- 行動が不要な message なら、安心感や trust 回復のように役割を明示できる

### 悪い

- account 名や見た目だけで current / legacy を決める
- template が共通ライブラリである前提を忘れて、account 別差分だと決めつける
- landing 一覧が空だから何も動いていないと判断する
- `表示名` と `実シナリオ名` のズレを無視して配線を読む
- タグ名を人名や月名だけで付けて意味が分からない状態にする
- 1 message に複数の unrelated action を詰め込む
- 長文教育をそのまま LINE へ持ち込み、次の行動がぼやける

### NG

- `lm-account-id` で今見ている LINE を判定する
- 停止中 LINE や old LP の follow_url を current landing に残す
- 命名規則に反して、誰が見ても意味が取れないタグや流入経路を増やす
- 本番導線の trigger / landing action を、影響範囲を見ずに上書きする

### 要確認で止めるべきもの

- hidden landing や legacy routing が絡むケース
- 命名規則に合わない current タグを整理・改名したいケース
- template / Flex / rich menu を新規で足すときの account 選定

#### フィールドの詳細設定
- 必須/任意
- 選択時のアクション: 友だち情報代入（例: 性別→友だち情報の「性別」に保存）
- 選択肢ごとの登録値・初期表示・定員設定

### 7. シナリオ
- **用途**: 時間差配信シナリオの構築
- 登録日起点 or 特定日時起点で段階配信

### 8. 流入経路分析（プロプラン以上）
- **用途**: どこから友だち追加されたか追跡
- **構成**: 流入経路名 + QRコード/URL + 登録時アクション
- **登録時アクション**: テンプレート送信 / タグ追加 / リッチメニュー変更 / シナリオ開始
- **設定**: 友だち追加時設定（無視する/しない）/ アクション実行タイミング（いつでも/初回のみ）
- **URL**: `https://manager.linestep.net/line/setting/follow`（友だち追加時設定）
- **一覧URL**: `https://manager.linestep.net/line/landing`
- **API**: `https://manager.linestep.net/api/landings`

#### アドネスでの current 使い方

- 基本は `どこから来たか` を分けるために作る
- 予約やイベントでは `友だち追加` より `タグ付与トリガー` として使うことが多い
- `スキルプラス【サポートLINE】` のイベント導線では
  - UTAGE の予約ボタン
  - Lステップ の流入経路 URL
  - タグ追加
  - 前日 / 当日案内配信
  が1本でつながる
- `【予約窓口】スキルプラス合宿` では
  - 流入テンプレ送信
  - 本人確認テンプレ送信
  - 予約ページテンプレ送信
  - 流入タグ追加
  の実務起点として使っている

#### 作るときの基本型

- 名前は `集客媒体_ファネル名-イベント名`
- 必要なら `【新規】...` タグと通常流入タグをセットで付ける
- 友だち追加時設定を無視するかどうか、初回だけ動かすかを最初に決める
- QRコードを使う施策では、流入経路作成後に発行URLとQRの両方を控える
- 2025-09 の公式アップデートで、流入経路分析の集計結果は CSV エクスポートできるようになっている

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/landing`
- current 一覧には `URLコピー` `QR` `広告挿入タグ` が並ぶ
- `【予約窓口】スキルプラス合宿` では
  - `ライトプラン年間会員_オフラインDM_QRコード_リストイン`
  の1本が visible で、inline action として
  - `テンプレ[1 流入した時に送るやつ]を送信`
  - `【条件ON】テンプレ[1 本人確認がまだの人に送るやつ（ライトプラン用）]を送信`
  - `【条件ON】テンプレ[1月 予約ページ]を送信`
  - `タグ[流入：ライトプラン年...]を追加`
  が表示されていた
- `新しい流入経路` を押すと `https://manager.linestep.net/line/landing/edit` に遷移する
- 登録画面で live 確認できた主要 field は
  - `流入経路名`
  - `フォルダ`
  - `QRコード表示用テキスト`
  - `有効期間(開始)`
  - `有効期間(終了)`
  - `アクション`
  - `友だち追加時設定のアクション`
  - `アクションの実行`
  - 折りたたみの `広告連携設定`
  - 折りたたみの `HTMLタグ設定`
- `友だち追加時設定のアクション` は `無視しない` が visible option で、注記でも
  - 先に友だち追加時設定が走る
  - その後に流入経路 action が走る
  - 流入経路 action 側でシナリオを操作すると、友だち追加時設定のデフォルトシナリオは送られない
  という順序が明示されていた
- action 未設定のまま `登録` を押すと確認 dialog が出る
  - message: `アクションが設定されていません。本当に登録しますか？`
  - button: `キャンセル / OK`
- 2026-03-12 の live テストでは、最小構成で一時流入経路を作成し、直後に削除まで確認した
  - create API: `POST https://manager.linestep.net/api/landings`
  - payload 例:
    - `name`
    - `qr_text`
    - `action_id`
    - `prevent_default`
    - `only_welcome`
    - `cv_head / cv_body`
    - `group_id`
    - `from_date / from_time / to_date / to_time`
    - `custom_params`
  - delete API: `DELETE https://manager.linestep.net/api/landings/{landing_id}`
- つまり landing は
  - 一覧 -> `新しい流入経路`
  - edit 画面で最小 field 入力
  - action 未設定なら確認 dialog を経由
  - 一覧行右端 `more_vert -> 削除`
  の往復で最小検証できる
- つまり、landing は `分析用リンク` であると同時に、`流入直後の action 実行器` でもある
- `スキルプラス【サポートLINE】` でも same UI を確認済み
  - visible folder は `未分類 41 / オンボーディングフロー（下書き）5 / ゴール設定1on1 7 / 実行中アクション（小澤）1 / SL.AI登録促進用 1 / LINE変更用 1 / 秘伝オンボエラー 1 / 購入案内 28 / アップセル 3`
  - current のサポートLINEは `オンボ / 1on1 / 実行フォロー / 購入案内 / アップセル` を landing で切っている

#### 2026-03-09 時点の実例

- `【みかみ】アドネス株式会社`
  - `2/11：セミナーオプト(メルマガ)`
    - 流入タグを追加
    - 動画系テンプレを複数送信
  - `2/8：書籍無料受取希望→オプト`
    - 流入タグを追加
    - テンプレ `起業の本質` を送信
    - `テンプレ送信トリガー` タグを追加
  - `AIディスプレイ広告`
    - 流入タグを追加
    - シナリオ `AIディスプレイ_１通目アンケート` を開始
- `みかみ@個別専用`
  - `X_幸一ローンチ_みかみメイン直個別`
    - 流入タグを追加
    - シナリオ `【エバー】RM作成会_1_流入直後` を開始
- `みかみ@AI_個別専用`
  - 現在確認できた流入経路は `スタッフ用` のみ
- `スキルプラス@企画専用`
  - `広告チームコピー用`
    - `【新規】...` と `流入：...` を追加
    - `新規流入 / 最終流入` を友だち情報に代入
    - 実シナリオ `セミナー①予約シナリオ` を開始
  - webinar event trigger で
    - `ウェビナー①_予約者`
    - `ウェビナー①_参加予定`
    - `ウェビナー①_着座`
    - `ウェビナー①_不参加`
    を付け分ける

### 9. アクション管理
- **用途**: 複数のアクションをまとめて実行
- テンプレ送信 + タグ追加 + リッチメニュー変更 を1つのアクションにまとめる

#### current で主にアクション設定が発生する場所

- 流入経路を作るとき
- テンプレート / Flex メッセージを作るとき
- シナリオ配信の step を作るとき

アドネスの current 運用では、この 3 箇所の inline action が主戦場。  
`アクション管理` 画面に reusable な action を作ることもあるが、まずは

- 入口で何を起こすか
- メッセージを押したら何を起こすか
- シナリオ内で何を起こすか

を決める方が実務に近い。

#### current の基本思想

- まずタグで状態を作る
- そのタグに応じてテンプレートやシナリオを適用する

つまり、`先に状態管理`、`後から送る / 見せる / 分岐する` が基本。  
`友だち追加時設定` は機能としてあるが、current 実務では主戦場ではなく、例外や初期設定寄りとして扱う。

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/action`
- live 確認時の account 表示は `スキルプラス【プライム】`
- 画面上部に
  - `新しいフォルダ`
  - `新しいアクション`
  - `並び替え`
  が出る
- 一覧では
  - `アクション名`
  - `登録日`
  - `スケジュール設定`
  - `more`
  が visible
- 代表例 `アップセル者対応` では、1つの action に
  - タグ解除
  - タグ追加
  - テンプレ送信
  - シナリオ停止
  - 対応マーク変更
  を束ねていた
- representative をさらに追加すると、current の action は少なくとも次の 4 型で読むとズレにくい
  - `毎日作業会　参加済　タグ解除`
    - 単純な `タグをはずす` 型
    - action_texts は `タグ[毎日作業会　参加済]を解除`
    - detail を読むと削除済みタグを参照している場合があり、この時は `【無効】削除済みのタグ操作` として扱う
  - `週報返信してタグをつけちゃおう`
    - `タグ追加 + テンプレ送信` 型
    - `週報返信済み` の状態を作って、その直後に返信テンプレを送る
  - `カルーセルついてく「いつサポ」「講師」「オフサポ」`
    - `テキスト送信 + テンプレ送信` の二段階型
    - 先に状況説明のテキストを送り、その後に visual CTA を出す
  - `アップセル者対応`
    - `タグ解除 + タグ追加 + テンプレ送信 + シナリオ停止 + 対応マーク変更` の複合制御型
    - state を切り替えながら downstream を止める representative
- `新しいアクション` の modal では、追加できる動作として
  - `テキスト送信`
  - `テンプレート送信`
  - `タグ操作`
  - `友だち情報操作`
  - `シナリオ操作`
  - `メニュー操作`
  - `リマインダ操作`
  - `対応マーク・表示操作`
  - `イベント予約操作`
  - `コンバージョン操作`
  が出る
- modal の末尾には
  - `発動2回目以降も各動作を実行する`
  - `この条件で決定する`
  が出る
- `保存するアクション名` と `フォルダ` を先に決めてから、動作を積む構造
- 各動作 block には
  - `条件ON / 条件OFF`
  - 並び替え
  - 削除
  がある
- `テンプレート送信` を選ぶと
  - `テンプレート`
  - `送信タイミング`
  が出る
- `テキスト送信` を選ぶと
  - `1. テキスト送信`
  - `メッセージ`
  - `送信タイミング`
  が出る
  - 本文入力は visible `textarea` ではなく `[contenteditable="true"]` が主入口
- `タグ操作` を選ぶと
  - `タグを追加`
  - `タグをはずす`
  - `タグフォルダで指定`
  - `タグ選択`
  が出る
- `シナリオ操作` を選ぶと
  - `シナリオ選択`
  が出る
- `イベント予約操作` を選ぶと
  - `アクション種別`
  - `イベントを予約`
  - `予約をキャンセル`
  - `予約枠を選択`
  が出る
- `メニュー操作` を選ぶと
  - `メニュー変更`
  が出る
- `対応マーク・表示操作` を選ぶと
  - `対応マーク`
  - `表示状態`
  が出て、初期値はどちらも `変更しない`
- つまり Lステップ の action は、単なるテンプレ送信ではなく `状態変更 + 送信 + シナリオ制御 + 表示制御` をまとめる macro として使える
- 2026-03-13 の live では、最小構成の `テキスト送信` action を end-to-end で確認した
  - 一覧右上 `新しいアクション`
  - `テキスト送信`
  - `保存するアクション名`
  - `1. テキスト送信`
  - `メッセージ`
  - `この条件で決定する`
  の順
  - `保存するアクション名` は、右ペイン上部に出る visible textbox の 1 つ目を使う
  - `名前` placeholder の input も見えるが、これは action 名ではなく本文側の変数入力
  - `メッセージ` は `[contenteditable="true"]` に入れる
  - 作成後は一覧検索に name を入れて row を絞れる
  - row 右端 `more_vert -> 削除 -> 削除する`
  - 再読込後と検索結果の両方で `after_exists=false`
  まで確認した

#### current API と schema

- 一覧取得は `GET /api/actions?page=1`
- 既存 action 詳細は
  - `GET /api/action/data/{id}`
  - `GET /api/actions/{id}/texts`
- save は `POST /api/action/register`
- live で開いた既存 action `テスト` (`aid=27783572`) の実値は次だった
  - `a_name=テスト`
  - `a_twice_type=1`
  - `funnel_descriptions={}`
  - `inputs[0][type]=13`
  - `inputs[0][remove]=1`
  - `inputs[0][tag_ids][0]=9592204`
  - `action_texts[0]=タグ[テスト]を解除`
- つまり current の reusable action は
  - action 名
  - 発動回数設定
  - 動作配列 `inputs`
  - 人が読む要約 `action_texts`
  で保存される
- helper
  - `python3 System/scripts/lstep_auth.py`
  - `python3 System/scripts/lstep_action_catalog.py list --limit 20`
  - `python3 System/scripts/lstep_action_catalog.py inspect --id 27783572`

#### まだ未完了の exact 部分

- `テキスト送信` は `新規作成 -> 保存 -> 削除` まで閉じた
- 残っているのは
  - `タグ操作 -> タグ選択`
  - `テンプレート送信 -> テンプレート選択`
  - `イベント予約操作 -> 予約枠選択`
  の selector 系
- したがって `アクション管理` は
  - 最小構成の create / delete
  - field と save route の理解
  までは exact
  - 残差は selector の複雑な action 種別に寄っている

#### 実務での使い分け

- reusable にしたい複合処理は `アクション管理`
- 導線の入口ごとに少しずつ違う処理は `流入経路 / テンプレート(Flex) / シナリオ step` の inline action
- つまり
  - 使い回すなら action
  - その場限りなら inline
  で切るのがズレにくい

#### current で多い action の型

- `状態更新型`
  - タグ解除
  - タグ追加
  - 対応マーク変更
  - 目的:
    - 友だちの状態を先に正す
- `分岐開始型`
  - タグ追加
  - シナリオ開始
  - 目的:
    - 次の nurture や予約導線へ入れる
- `案内即時送信型`
  - テンプレ送信
  - 必要ならメニュー変更
  - 目的:
    - 受講生や予約者に次の行動をすぐ見せる
- `例外停止型`
  - シナリオ停止
  - タグ解除
  - 目的:
    - 二重送信や誤導線を止める

#### 良い / 悪いの判断

- 良い
  - 1 action の目的が 1 つにまとまっている
  - `状態更新` と `次アクション` の順が読みやすい
  - 同じ複合処理を複数箇所で使うなら action 管理へ切り出す
- 悪い
  - 何のための action か名前だけでは読めない
  - 1 action に unrelated な処理を詰め込みすぎる
  - inline で何度も同じ複合処理を書いて、後で修正箇所が散る

#### コンテンツの型と制作意図

コンテンツとは、`コミュニケーションの手段であり、ユーザーをこちらが意図した認識に変換するもの`。

そのうえで、Lステップのコンテンツは Mailchimp のような長文教育ではなく、`次の行動を friction なく起こさせる` ことが主目的。

つまり Lステップでは、
- 認識を大きく塗り替える
ではなく
- 今この状態の人に、次の1歩を迷わず踏ませる
ためのコンテンツとして作る。

Addness の販売導線でいうと、Lステップは

- 非リアルタイムの短い実務メッセージ
- 予約やイベントの入口
- 受講後サポート
- リアルタイム接点の前後の案内

を担当する。

つまり `教育の本線` ではなく、`状態管理と次行動の実行制御` を担う。

- 受講後サポート
  - 例: `2月16日スキルプラス 大幅アップデートのお知らせ`
  - 意図: 変更点を先に理解させて混乱を減らす
- 合宿 / イベント案内
  - 例: `3月 スキルプラス合宿 集客`
  - 意図: 対象者を明確にし、詳細確認や申込へ最短でつなぐ
- 予約導線
  - 例: `ゴール設定1on1予約案内`
  - 意図: 押すべきボタンを明確にして予約率を上げる
- 実務連絡
  - 例: `Zoomリンク【東京会場】`
  - 意図: 情報の抜け漏れを防ぐ
- イベント一覧導線
  - 例: `Project/2_CS/サポートLINE_イベント情報設計.md`
  - 意図:
    - `どんなイベントがあるか分からない`
    - を
    - `自分に関係あるイベントを見つけ、予約へ進める`
    に変える
  - current の作り方:
    - リッチメニュータップ
    - テンプレート送信
    - 1段目にカレンダー画像
    - 2段目にイベントカードのカルーセル
    - 必要ならイベントごとの前日リマインドと当日案内を一斉配信
- オンボーディング導線
  - 例: `Project/2_CS/スキルプラス_オンボーディング.md`
  - 意図:
    - `入会したが何から始めればいいか分からない`
    - を
    - `今やるべき初期設定と次の1歩が分かる`
    に変える
  - current の作り方:
    - テンプレート送信
    - 回答フォーム誘導
    - リッチメニュー切替
    - タグ追加
    - 必要に応じて SLS や受講生サイト URL へ送る

良いテンプレートの条件:
- 何のためのメッセージかが一読で分かる
- 受信者の次の行動が1つに絞られている
- タグや流入状態と文脈が合っている
- LINEらしく短く、行動導線が前に出ている

#### 制作者意図を読む時の問い

Lステップ の current テンプレートや Flex を読む時は、次を順に見る。

1. この相手は今どの状態か
2. その状態で、何に迷っているか
3. このメッセージで、どの迷いを消すか
4. その結果、次に何をさせたいか
5. ボタン、回答フォーム、予約、次テンプレートのどれが最短か

つまり、良い Lステップ コンテンツは `情報量が多い` ことではなく、`迷いを 1 個消して 1 個行動させる` ことに集中している。

悪いテンプレートの兆候:
- 情報は多いが、結局何を押せばいいか分からない
- タグ状態と文脈が合っておらず、唐突に見える
- Mailchimp 的な長文教育メールになっている
- URL やボタンの役割が複数あって迷う

#### 良い / 悪いをさらに具体化

- 良い
  - 1 メッセージ 1 目的で、押す場所が明確
  - 受信者が `今ほしい情報` と `今やるべき行動` が一致している
  - 予約、回答、視聴、確認のどれか 1 つに行動を絞れている
  - action や URL が、タグ状態と矛盾しない
- 悪い
  - 複数の選択肢を同時に並べて迷わせる
  - 状態管理のタグと、出している案内の文脈がずれる
  - 長文で教育しようとして、結局押されない
  - 予約案内なのに、予約以外の情報が前に出る

#### テンプレート品質を作る時の exact チェック

- `標準メッセージ`
  - 実務連絡、補足説明、障害連絡、長めの案内に向く
  - 見出し画像より、本文の分かりやすさと URL / action の正確さを優先する
- `カルーセルメッセージ(新方式)`
  - 複数選択肢を比較させたい時に向く
  - `画像 / タイトル / 本文 / 選択肢名 / アクション設定` の整合を見る
  - 1 panel ごとに役割が重複しない方が良い
- `フレックスメッセージ`
  - 見た目の強さと行動誘導を両立したい時に向く
  - 画像、余白、テキスト階層、ボタン位置まで含めて設計する
  - デザインが崩れると押されなくなるので、`体裁を整える` の比重が最も高い

形式選択で迷った時は、次の順で切る。

1. まず `今この相手に何をしてほしいか` を 1 つに絞る
2. 次に、その行動に `視覚階層` が必要かを見る
3. 最後に、選択肢が 1 つか複数かで分ける

- `標準メッセージ`
  - 行動より先に説明や連絡を正確に届けたい時
  - 例
    - 障害連絡
    - 架電テンプレ
    - 個別の補足連絡
- `フレックスメッセージ`
  - 1 つの main CTA を、画像と階層で強く押したい時
  - 例
    - 合宿募集
    - コース移行案内
    - アップデート告知
- `カルーセルメッセージ(新方式)`
  - 複数 panel を並べて比較や分岐をさせたい時
  - 例
    - 複数講座の案内
    - 複数日程の比較
    - 複数特典の出し分け

使い分けを誤る典型:

- `標準メッセージ` で強い視覚訴求をやろうとして、長文の中に CTA を埋もれさせる
- `フレックスメッセージ` なのに、説明を詰め込みすぎて結局 main CTA が弱くなる
- `カルーセルメッセージ(新方式)` で panel ごとの役割が重複し、比較ではなくノイズになる

テンプレートを保存する前に最低限見る順番:

1. 受信者の状態に対して、`標準メッセージ / カルーセルメッセージ(新方式) / フレックスメッセージ` の選択が合っているか
2. `テンプレート名` を見ただけで用途が分かるか
3. 画像を使う場合、画像が promise を先に伝えているか
4. テキストが `補足` になっていて、画像やボタンと役割が競合していないか
5. `アクション設定` が 1 つの main action に収束しているか
6. CTA 文言と遷移先の promise が一致しているか
7. `テスト送信` を `甲原 海人` に送り、実際に押して挙動を確認したか
8. 一時確認用に作ったものなら、確認後に削除したか

`フレックスメッセージ` で特に見る点:

- 一番上で何が得られるか分かるか
- 途中に不要な情報の横滑りがないか
- ボタンの色、順番、文言が main action を強めているか
- 画像が decorative ではなく、認識変換に効いているか

つまり、Lステップ のテンプレート品質は

- 画像を入れられるか
- テキストを入れられるか
- アクションを設定できるか

ではなく、

- その状態の相手に対して
- どの形式を選び
- どの順番で見せ
- どの action を押させるか

まで exact に作れているかで判断する。

#### current のコンテンツ判断で見る順番

1. このテンプレートや Flex は誰のどの状態向けか
2. 今回変えたい認識は何か
3. 次に起こさせたい行動は 1 つに絞れているか
4. その行動は
   - ボタン
   - 回答フォーム
   - 予約
   - 次テンプレート
   のどれで起こすか
5. その action や URL は、タグ状態や文脈とずれていないか

#### live で確認した representative template と意図

- `3月 スキルプラス合宿 集客`
  - alt: `【3月スキルプラス合宿】のご案内`
  - 何を変えるか
    - `学んだけど形にできない / 一人だと進まない`
    - を
    - `このイベントなら前に進めそう`
    に変える
  - 何を起こすか
    - 合宿詳細確認と申込
  - current の action
    - LIFF で `【予約窓口】スキルプラス合宿` に送る
  - 読み方
    - 教育ではなく、`作業が進む場` という promise を提示して予約窓口へ渡すイベント募集テンプレート

- `SNS活用 1on1無料相談会`
  - 形式
    - `標準メッセージ`
  - id
    - `225311282`
  - editor 上の実体
    - `text_text` に本文が 1 本で入る
    - `content_summary`
      - `char_count = 448`
      - `line_count = 9`
      - URL は `https://forms.gle/ThNmeHBBxsRc2ahz6`
  - 何を変えるか
    - `SNS は大事だが、自分では何をやればいいか分からない`
    - を
    - `まず 1on1 無料相談会に出ればよい`
    に変える
  - 何を起こすか
    - Google フォーム遷移
  - 良い点
    - 1 通の中で
      - 問題提起
      - 共感
      - 支援の promise
      - 参加 CTA
      の順に流れている
    - `標準メッセージ` を使う理由がはっきりしている
      - 画像より説明量を優先
      - 受信者を迷わせず 1 本の CTA に押し込む
  - 注意点
    - current 実装は direct URL
    - 新規で同種の main CTA を作る時は、まず short.io 化の要否を確認する

- `▼無料相談はこちら【YouTube切り抜き 無料相談会】`
  - 形式
    - `カルーセルメッセージ(新方式)`
  - id
    - `225310549`
  - editor 上の実体
    - `https://manager.linestep.net/line/template/edit_v2/225310549`
    - current builder root は `v-message-builder`
    - save 先は `post_to=/line/template/edit_v2`
    - inspect API は `GET /api/line/template/225310549`
    - `carousel_summary`
      - `alt_text = ※本日で終了です。`
      - `panel_count = 1`
      - panel text は `事前質問フォームに回答して👇`
      - button title は `無料相談に参加する！`
      - `action_type = 8`
      - `action_form_id = 943733`
      - `action_liff_size = tall`
  - 何を変えるか
    - `説明は読んだが、どこを押せばよいか迷う`
    - を
    - `この選択肢から相談導線へ進めばよい`
    に変える
  - 何を起こすか
    - 無料相談への遷移
  - 良い点
    - 単体で世界観教育を背負わず、CTA の可視化に役割を絞っている
    - 後段の `テンプレートパック` と組み合わせると、説明と行動喚起を分離できる
  - current の読み方
    - `カルーセルメッセージ(新方式)` は、最初の接点より `説明後の選択肢提示` に強い
    - `画像 / タイトル / 本文 / 選択肢名 / アクション設定` の役割が重複しないほど強い
  - 同型の current 実例
    - `▼無料相談はこちら【AI活用 無料相談会】` (`225085931`)
    - `alt_text = ※本日で終了です。`
    - panel text は同じく `事前質問フォームに回答して👇`
    - button title は同じく `無料相談に参加する！`
    - `action_type = 8`
    - `action_form_id = 943168`
    - `action_liff_size = tall`
  - つまり current の無料相談系カルーセルは
    - `標準メッセージ or pack` で説明
    - `カルーセルメッセージ(新方式)` で回答フォーム CTA を 1 panel で提示
    の分離が recurring pattern になっている

- `YouTube切り抜き 無料相談会告知`
  - 形式
    - `テンプレートパック`
  - id
    - `225292504`
  - page title
    - `メッセージパック「YouTube切り抜き 無料相談会告知」 設定`
  - step 構成
    - `step 1 = 本文`
      - preview は `※24時間後終了です。...`
      - long copy で urgency と問題認識を先に作る
    - `step 2 = テンプレート`
      - preview は `【カルーセル】事前質問フ…`
      - CTA を visual に受け渡す
  - 何を変えるか
    - `YouTube の切り抜きに関心はあるが、まだ相談する理由が弱い`
    - を
    - `今相談した方がいい`
    に変える
  - 何を起こすか
    - 無料相談への CTA クリック
  - 良い点
    - `本文` と `テンプレート` を同じ message に詰め込まず、2 step に分けている
    - 先に認識変換、次に action という流れがきれい
    - `テンプレートパック` が、単なるまとめ送信ではなく `認識 -> 行動` の順番制御として使われている

- `ゴール設定1on1予約案内【2026/01/12：アマギフ訴求】`
  - alt: `この機会に、ぜひ1on1をご予約ください☺️`
  - 何を変えるか
    - `登録したが何をすればいいか分からない`
    - を
    - `まず1on1を予約すればよい`
    に変える
  - 何を起こすか
    - 1on1 予約
  - current の action
    - タグ `アマギフ_オプト` を付与
    - その後に follow-up text を送る
  - 読み方
    - 予約導線そのものに加えて、`誰がこのオファーを踏んだか` という状態も同時に作る representative

- `【障害報告】外部システム障害の影響に関するお知らせ`
  - alt: `⚠️一部サービスの閲覧障害のお知らせ⚠️`
  - 何を変えるか
    - `今何が起きているか分からず不安`
    - を
    - `何が使えず、何が使えて、次の連絡を待てばよい`
    に変える
  - 何を起こすか
    - 不要な問い合わせや混乱を減らす
  - current の action
    - なし
  - 読み方
    - Lステップ のテンプレートは販促だけでなく、信頼維持と期待値調整の実務連絡にも使う代表例

- `20250228 コース移行のお知らせ`
  - id
    - `247339595`
  - alt
    - `⚠️新・コース移行のお知らせ⚠️`
  - current の構成
    - `title` 1
    - `text` 3
    - `button` 2
  - current の action
    - `①新コース登録はこちら`
      - `https://student.success-learning.ai/invite_code/...`
    - `②コース移行ガイドはこちら`
      - `https://skillplus-renewal.pages.dev/`
  - 何を変えるか
    - `移行しないといけないが、何を押せばいいか曖昧`
    - を
    - `登録 -> ガイド確認 の順に動けばよい`
    に変える
  - 良い点
    - 2 button でも役割が重複していない
    - `登録` と `理解補助` を分けている

- `12/5 サーバーエラーによる 一部サービスの閲覧障害`
  - id
    - `234261363`
  - alt
    - `⚠️一部サービスの閲覧障害のお知らせ⚠️`
  - current の構成
    - `text` 2
    - action なし
  - 何を変えるか
    - `何が壊れていて、何を待てばいいか分からない`
    - を
    - `現状と待つべき行動が分かる`
    に変える
  - 良い点
    - 販促ではなく、期待値調整と問い合わせ抑止に振り切っている
    - 余計な CTA を置かず、混乱を増やしていない

#### テンプレート編集で確認した補足

- representative editor:
  - `https://manager.linestep.net/line/template/edit_v3/249005485?group=0&editMessage=0`
- current の template editor では、URL 自体に action を直書きするのではなく、`URL設定` ブロックから `サイト設定ページ` を参照させる構造が visible
- 画面上でも
  - `URL訪問時アクションを設定する場合は、サイト設定ページから設定してください`
  と出ていた
- つまり、テンプレート / Flex の action 設計は
  - 本文やボタン自体は template editor
  - URL 到達後の action は site setting / URL 訪問時アクション
  に分かれる

#### シナリオ配信の current 入口

- 一覧URLは `https://manager.linestep.net/line/content/group`
- folder を開くと `?group={group_id}` で切り替わる
  - 例: `新オンボシナリオ = /line/content/group?group=117742`
- `新しいフォルダ`
- `新しいシナリオ`
- `並び替え`
- `検索`
  が current 入口
- シナリオ名を押すと `https://manager.linestep.net/line/content/{content_group_id}?group={group_id}` に入る
  - 例: `⓪ウェルカムメッセージ = /line/content/1000634?group=117742`
- current のシナリオ編集画面では
  - `シナリオ名`
  - `シナリオフォルダ`
  - `状態`
  - `対象の絞り込み`
  - `コンテンツ`
  - `最終コンテンツ配信後の処理`
  が並ぶ
- `コンテンツ` 行には少なくとも
  - `タイプ`
  - `日数`
  - `経過時間`
  - `本文`
  - `到達人数`
  が visible
- 各 row では
  - `編集`
  - `挿入`
  - `コピー`
  - `プレビュー`
  - `別窓`
  - `テスト`
  - `削除`
  を使う
- つまり、シナリオ step の current 編集は別の hidden 画面ではなく、まず `/line/content/{id}` の editor に入り、そこで row 単位に操作する前提

#### シナリオ step 編集で実際に見る項目

- representative step:
  - `スキルプラス【サポートLINE】`
  - `新オンボシナリオ`
  - `⓪ウェルカムメッセージ`
  - `1通目`
- row の `編集` を押すと、同一 URL 上の modal で `配信メッセージ日時編集` が開く
- current modal で確認できた field は少なくとも以下
  - `配信タイミング`
    - `購読開始直後`
    - `経過時間指定`
  - `step`
  - `time`
  - `order`
  - `開始当日`
  - `pause`
    - `シナリオを一時停止しない`
    - `シナリオを一時停止する`
  - `送信先を絞り込む`
    - `tag_limit`
    - `tag_id`
  - `テンプレート詳細`
    - `テンプレート名`
    - `テンプレート種別`
    - `テンプレートフォルダ`
    - `テンプレートを編集する`
    - `テンプレートプレビュー`
  - `アクションを設定しない / アクションを設定する`
  - `アクションを設定`
  - `設定解除`
- つまり、シナリオ step では
  - いつ送るか
  - 誰に送るか
  - 何を送るか
  - 送ったあと何を起こすか
  を 1 modal で決める

#### シナリオ step 内の action の読み方

- current 実例では、`⓪ウェルカムメッセージ（シナリオ用）` というテンプレート pack を送り、その下で inline action が追加されていた
- 表示上は
  - `アクション タグ[シナリオ配信⓪ウェル...]を...`
  のように summary が出る
- つまり、step 内 action は `action 管理` の reusable action とは別に、
  - この step を送ったら
  - このタグを付ける / 外す
  - この状態へ進める
  という step 固有処理を置く場所として使う
- 実務上は
  - 何度も使う複合処理 = `アクション管理`
  - この step 専用の軽い処理 = `step 内 inline action`
  の切り分けがズレにくい

#### 良い / 悪いの判断

- 良い
  - `テンプレート pack` で本文をまとめ、step では `タイミング / 絞り込み / state change` だけを調整する
  - `タグで状態を作る -> 次の step や別導線で使う` を崩さない
  - `pause` は意図を持って使う
- 悪い
  - step ごとに本文、タグ、導線が全部バラバラで、あとから全体像が追えない
  - reusable にすべき複合処理を毎回 inline で書く
  - 絞り込みタグと action で付けるタグの役割が混線する

### 10. タグ管理
- **用途**: 友だちの状態・属性をラベル付け
- 例: 「オンボーディング完了」「SLS登録済み」「コワーキング利用可」

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/tag`
- 画面上部に
  - `新しいフォルダ`
  - `新しいタグ`
  - `CSVアップロード`
  が出る
- `新しいタグ` は一覧上部の primary button から dialog で開く
  - dialog title: `タグの新規作成`
  - field: `タグ名`
  - button: `キャンセル / 作成`
- 2026-03-12 の live テストでは、folder `会員タグ` を開いた状態で一時タグを作成し、直後に削除まで確認した
  - create API: `POST https://manager.linestep.net/api/tags?return=minimal`
  - payload 例: `{"name":"...","group_id":477811}`
  - delete API: `DELETE https://manager.linestep.net/api/tags/{tag_id}`
- つまり tag は
  - 一覧 -> `新しいタグ`
  - dialog で名前入力
  - `作成`
  - 一覧行右端 `more_vert -> 削除`
  の往復で最小検証できる
- `【予約窓口】スキルプラス合宿` で visible だったフォルダは
  - `[2026] スキルプラス合宿`
  - `[2025] スキルプラス合宿`
- current visible 一覧は空でも、folder count が出ていた
- つまり、タグは `一覧が空 = 使っていない` ではなく
  - folder 側に何件あるか
  - action 側で付与されているか
  までセットで見る
- `スキルプラス【サポートLINE】` で visible だった folder は `未分類 49 / オンボーディングフロー（下書き）6 / 会員タグ 35 / セミナー参加者（毎日作業会参加者）10 / 🚨現在地チェック 38 / ゴール設定 19 / 中途解約 7 / 現在地チェック（リマインド）4 / スキルプラス合宿シリーズ 11`
- サポートLINEのタグは、`会員状態 / 現在地 / ゴール設定 / 合宿 / 解約兆候` の状態管理が中心

#### アドネスでの基本ルール

- `【新規】集客媒体_ファネル名-イベント名`
- `集客媒体_ファネル名-イベント名`
- `【購入】商品名`
を基本にする

#### 予約・イベントでよく使う型

- `イベント予約_[イベント名略称]_[日付4桁]`
  - 例: `イベント予約_グルコン_0307`
- このタグを
  - 前日リマインド
  - 当日案内
  - 参加者抽出
  の母集団に使う

#### current の解釈

- `スキルプラス【サポートLINE】` は `49件` あり、教育 / CS / 日報 / 予約導線の状態管理に使う
- `【予約窓口】スキルプラス合宿` は visible には `タグ 0件` だが、landing action では `流入：ライトプラン年...` の付与が動いている
- visible 一覧が空でも、action 側でタグ操作しているケースがあるので、`タグ一覧が少ない = 何もしていない` とは見ない

### 11. 友だち情報管理
- **用途**: 友だちのカスタム属性を管理
- 例: 性別、生年月日、ニックネーム、メールアドレス等
- 回答フォームからの自動代入が可能

### 12. カスタム検索管理
- 複合条件での友だち検索を保存

### 13. リッチメニュー
- **用途**: LINE画面下部の固定メニュー
- オンボーディング中は制限版メニュー → 完了後にフルメニューに切替
- **API入口**: `https://manager.linestep.net/api/rich-menus`
- current account によっては空配列で返るが、少なくとも一覧取得の入口は確認済み

#### アドネスでの current 使い方

- `スキルプラス【サポートLINE】` は current UI 上で `3件`
  - `2026.03.01リッチメニュー`
  - `2026.02.01リッチメニュー`
  - `（仮）リッチメニュー`
- イベント導線では、リッチメニュー `イベント情報` からテンプレートを送信し、イベント一覧を見せる設計が正本
- オンボーディングでは
  - 制限版
  - フル版
  の切替が重要で、流入経路やアクションとセットで使う

#### 作る / 直すときの考え方

- リッチメニュー自体にすべてを詰め込まず、`タップ -> テンプレート送信 -> 流入経路 or 回答フォーム` の分業で作る
- 2025-09 の公式アップデートで、リッチメニューのタップ数計測が追加された
- 計測対象は
  - トーク内ブラウザ
  - アクション
  - 回答フォーム
  なので、改善時はデザインだけでなく `どのボタンが押されているか` も見る

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/richmenu`
- 画面上部に出る主ボタンは
  - `新しいフォルダ`
  - `新しいリッチメニュー`
  - `並び替え`
- `新しいリッチメニュー` を押すと、いきなり編集画面には入らず、作成方法の選択が先に出る
  - `画像をアップロードして作成`
  - `テンプレートをベースに作成`
- `画像をアップロードして作成` を押すと `https://manager.linestep.net/line/richmenu/new?group=0` に入り、最初の画面で見えるのは
  - `画像`
  - `メニュー画像選択`
  - footer の `登録`
  だけ
- つまり current の `画像アップロード作成` は
  - 最初に画像を確定する
  - その後で編集項目が増える
  の 2 段階
- `メニュー画像選択` の modal は
  - `登録メディア一覧`
  - `新規アップロード`
  - `アップロード済み`
  - `ファイルを選択する`
  - `決定`
  で構成される
- file 条件は `1MBまで / jpg,png / 2500×1686 or 2500×843`
- upload 後に row を選んで `決定` を押すと、最初の `登録` が enabled になる
- 最初の `登録` は final save ではなく、同じ `new?group=0` の editor 状態へ進むための遷移
- editor 状態で初めて visible になる主項目は
  - `タイトル`
  - `フォルダ`
  - `トークルームメニュー`
  - `メニューの初期状態`
  - `プレビュー`
  - `テンプレート`
  - `コンテンツ設定`
- current の先頭 `テンプレート` を選ぶと、最低でも
  - `ボタン1URL`
  - `ボタン2URL`
  - `ボタン3URL`
  が必須
- つまり最小保存でも、テンプレートに応じた URL 数を先に把握しないと 422 になる
- つまり、リッチメニューを増やすときは
  - 新規画像で作るのか
  - 既存テンプレ型から入るのか
  を最初に決める設計になっている
- 画面文言上でも、友だちごとの表示切替は `自動応答 / タグアクション` から行う前提が明示されていた
- `スキルプラス【サポートLINE】` では visible folder と件数も確認済み
  - `未分類 3 / メイン 4 / 2025.09.15 1 / 2024.12.16 リッチメニュー 6 / 24.09.09 リッチメニュー 3 / 旧：リッチメニュー 2 / 新リッチメニュー（宮本作成中）0`
- つまりサポートLINEのリッチメニューは、`現行 / 旧版 / 作成中` が混在するので、current 判定を名前だけでやらない方が安全
- 実務では次の順で切るとズレにくい
  1. visible 件数があるか
  2. current のテンプレート送信や導線説明と役割がつながるか
  3. `旧 / 作成中 / 下書き` の明示があるか
  4. それでも曖昧なら、編集画面の実内容と参照先テンプレートを開いて確定する
- current の代表 edit 画面として `https://manager.linestep.net/line/richmenu/edit/561714` を確認済み
  - visible field は
    - `画像`
    - `タイトル`
    - `フォルダ`
    - `トークルームメニュー`
    - `メニューの初期状態`
    - `プレビュー`
    - `テンプレート`
    - `コンテンツ設定`
  - 各ボタンでは
    - `URL`
    - `TEL`
    - `ユーザーメッセージ`
    - `アクション`
    - `回答フォーム`
    - `その他`
    の切替があり、`アクション設定` からテンプレ送信や action を割り当てる
  - current 実例では
    - `【25/09~】受講生サイト`
    - `【25/09~】サクセスラーニング`
    - `【最新】3月`
    - `日報`
    - `【25/09~】お問い合わせ・質問`
    などのテンプレ送信が割り当てられていた
- 末尾には `一覧へ戻る` と `保存` がある
- つまり、リッチメニューは
  - 画像を置く
  - ボタンごとに `テンプレ送信 / URL遷移 / 回答フォーム / action`
  を割り当てる
  という editor になっている
- 2026-03-14 の live では、最小テストとして
  - 2500x843 の png を upload
  - `タイトル = ZZ_TMP_20260314_RichMenu検証`
  - `トークルームメニュー = メニューはこちら`
  - 初期状態 `表示する`
  - 先頭テンプレートを選択
  - `ボタン1URL / ボタン2URL / ボタン3URL = https://example.com/richmenu-test`
  で final `登録` が 200 になるところまで確認
- 削除も exact に確認済み
  - 一覧 row 右端 `more_vert`
  - `削除`
  - confirm `この操作は取り消せません。本当に削除しますか？`
  - `削除する`
  - row が一覧から消えることまで確認

### 14. クロス分析
- **用途**: 2つ以上の項目を掛け合わせて傾向を見る
- **対応プラン**: プロプラン以上
- 公式上は
  - `流入経路 × 性別`
  - `商品購入者 × 年代`
  - `友だち登録日 × 来店回数`
  のような掛け合わせが可能

#### アドネスで相性が良い軸

- `流入経路 × 商品購入`
- `流入経路 × 個別予約`
- `プラン名 × 合宿参加日`
- `イベント予約タグ × 実参加`
- `日報提出状況 × プラン名`

#### 何に使うか

- どの流入が予約や購入につながっているかを見る
- どのプランの人がどのイベントに集まりやすいかを見る
- どの状態の受講生が日報やオンボに詰まりやすいかを見る
- 感覚ではなく `優先して改善すべき層` を切る

#### 実務上の前提

- クロス分析そのものは `後から見る画面` だが、精度は先に作る `タグ / 友だち情報 / 流入経路` に依存する
- つまり、クロス分析を良くしたいなら、先に
  - 命名規則
  - 友だち情報の代入
  - 流入経路の切り方
  を整える必要がある

#### live で確認した exact 操作

- 一覧URLは `https://manager.linestep.net/line/board`
- 画面上部に
  - `新しいフォルダ`
  - `新しいクロス分析`
  - `並び替え`
  がある
- `新しいクロス分析` を押すと `https://manager.linestep.net/line/board/edit/new` に遷移する
- 登録画面で live 確認できた主要 field は
  - `管理名`
  - `フォルダ`
  - `評価対象`
  - `評価軸(縦軸)`
  - `評価項目(横軸)`
  - `オプション`
- `評価軸(縦軸)` の候補文言として
  - `友だち情報`
  - `タグ(個別選択)`
  - `タグ(フォルダ選択)`
  - `友だち登録日`
  が visible だった
- つまり、クロス分析は `分析画面` というより、`どの軸を掛け合わせるかを定義して保存する機能` と見るのが正確
- `スキルプラス【サポートLINE】` でも same UI を確認済み
  - visible folder は `未分類 0 / アドプロ 2`
  - `group=9069` に切り替えると
    - `アドプロ「広告マーケターコース」進捗管理`
    - `アドプロ「自社商品コース」進捗管理`
    が見える
- フロント JS `board_editor.js` から見える保存条件
  - 保存 API は `POST /line/board/edit`
  - payload は
    - `bid`
    - `name`
    - `row_type`
    - `row_ids`
    - `cols`
    - `options`
    - `first_funnel_id`
    - `group_id`
  - `row_ids.length === 0` だと保存前に `評価軸(縦軸)は必須です` で止まる
- live テストで `保存 -> 再読込 -> 削除` まで確認済み
  - account: `スキルプラス【サポートLINE】`
  - folder: `アドプロ`
  - テスト名: `TEST_削除用_20260311`
  - 作成 payload の最小構成は
    - `row_type = tag`
    - `row_ids = [6904539]`
    - `cols = [{funnel_id: 8570979, description: "タグアドプロ入会"}, {funnel_id: 8570981, description: "タグ【アドプロ】1on1予約直前"}]`
    - `first_funnel_id = 8570956`
    - `group_id = 9069`
  - 再読込は `GET /api/board/data/116309` で確認
  - 削除は一覧の `more_vert -> 削除 -> 削除する` で `DELETE /api/boards/116309`
  - つまり、クロス分析は `設計して保存するだけでなく、後から再利用・削除まで安全に回せる`

### current / draft / legacy の見分け方

- current の可能性が高い
  - folder や item count が 0 ではない
  - current 導線や current account に実データがある
  - 役割名が具体的で、実務オペレーションに直結している
- draft の可能性が高い
  - `下書き`
  - `作成中`
  - 件数 0
  - 例: `新リッチメニュー（宮本作成中）0`
  - 例: `━━↓使わない↓━━`
- legacy の可能性が高い
  - `旧：`
  - 古い日付だけが残った版管理
  - 現行 account で current の導線説明と結びつかない
  - 例: `旧：リッチメニュー 2`
- 注意
  - `未分類` は current / legacy 判定そのものではない
  - date 付き folder も、snapshot なのか current 切替履歴なのかを実件数と導線参照で判断する
  - 命名規則違反だから即 legacy ではない。まず current 参照の有無を確認する

---

## オンボーディングフローでの活用パターン

### 秘密の部屋の完成版フロー（スキルプラスに移植中）

```
入会直後
  → テンプレート#1「入会直後」画像
  → テンプレート#2「回答フォーム①」→ 4つの簡単アンケート回答

SLS登録
  → 流入経路①トリガー
  → テンプレート#3「SLS登録①」→ SLS登録URL
  → テンプレート#4「SLS登録②」（遅れあり）→ 登録確認

セットアップ開始
  → テンプレート#5「セットアップ開始」→ SLSコースURL

リッチメニュー開放
  → 流入経路②トリガー
  → テンプレート#6「動画」+ #7「リッチメニュー開放」
  → テンプレート#8「受講生サイト登録確認」（遅れあり）
  → リッチメニュー変更（制限版→フル版）

コワーキング開放
  → 流入経路③トリガー
  → テンプレート#9「コワーキング利用開放」
  → テンプレート#10「利用方法チェック」
  → テンプレート#11「確認後」

目標設定
  → 流入経路④トリガー
  → テンプレート#12「回答フォーム②」→ 全機能解放アンケート

ゴール達成
  → 流入経路⑤トリガー
  → テンプレート#13「機能全開放」
  → リッチメニュー→メインメニューに変更
  → タグ「オンボーディング完了」追加
```

---

## Lステップ × 他ツール連携

| 連携先 | 方法 | 用途 |
|--------|------|------|
| **Success Learning AI** | テンプレ内URLリンク + 流入経路 | SLS登録・コース受講誘導・進捗連動 |
| **Googleスプレッドシート** | 回答フォームβ連携 | アンケート回答の自動記録 |
| **Addnessスクール** | サンクスページURL | 回答後のリダイレクト |
| **UTAGE** | メールアドレス照合 | 広告CR→LP→LINE登録の計測 |
| **AI秘書（Render/local_agent）** | 回答フォーム→シート→AI回答 | Q&A自動回答（承認フロー付き） |

### 質問回答の流れ（Lステップ経由）

```
受講生がLステップの回答フォームで質問
  → Googleスプレッドシート（回答用：サポートLINE等）に自動追加
  → ローカルエージェントが60秒ごとにポーリング
  → AI回答案を生成 → LINE秘書グループに通知
  → 講師が承認 → スプレッドシートに書き込み → Pineconeに蓄積
```

L-stepシートの列構成: A=タイムスタンプ, B=名前, C=LINE名, F=目的, G=やったこと, H=質問, N=L-STEPリンク, O=回答済み, Q=回答

---

## ブラウザ自動操作

### ログイン手順
1. `https://manager.linestep.net/account/login` にアクセス
2. 1Password自動入力（ID/PW）
3. reCAPTCHA v2 checkbox 突破（`cliclick` でOSレベルクリック）
4. ログインボタンクリック
5. current probe の submit 条件は `POST /account/login` + `_token / name / password`

### reCAPTCHA突破の技術
- Chrome拡張のクリックではiframe内に到達しない → `cliclick`（OSレベルマウス操作）で突破
- 手順: AppleScriptでウィンドウ固定→screencapture→座標特定→物理ピクセル÷2=ポイント座標→cliclick
- スクリーン解像度: 3024x1964物理ピクセル（1512x982ポイント、Retina 2x）

---

## スキルプラスサポートLINEの構築状況

### 作成済みリソース
- テンプレートフォルダ: ★オンボーディング（本番）（group=968329）
- 回答フォームフォルダ: オンボーディングフロー（下書き）（group=206232）

### 構築対象（秘密の部屋から移植中）
- テンプレート: 13件
- 回答フォーム: 2件（4つの簡単アンケート + 全機能解放アンケート）
- 流入経路: 5件
- リッチメニュー: 制限版 + フル版

### 現時点で言えること

- `スキルプラス【サポートLINE】` は、単なる問い合わせ窓口ではなく、今後 `受講生サポートの集約先` になる前提で設計が進んでいる
- 実務で主に触る想定が高いのは
  - リッチメニュー
  - イベント情報テンプレート
  - 回答フォーム
  - 一斉配信
  - 予約タグ / 流入経路
- local CSV では 2025-10 以降も継続流入があり、2026-03 にも新規追加がある
- friend info は `登録メールアドレス / メールアドレス / 電話番号` の contact 情報が中心で、受講生特定の土台として使える

### 【予約窓口】スキルプラス合宿の現時点理解

- 合宿予約専用の Lステップ account として扱うのが自然
- local CSV では `プラン名` と `日程別参加列` が中心で、受講生教育より予約・参加管理に寄っている
- 実務で主に触る想定が高いのは
  - 予約流入経路
  - 予約タグ
  - 前日 / 当日案内テンプレート
  - 参加者 friend info の更新
- 予約窓口は `予約管理` と `友だち情報管理` を一緒に見る

詳細は `Project/2_CS/スキルプラス_オンボーディング.md` を参照。

---

## 実画面確認の進捗

- [x] リッチメニューの新規作成フロー（2段階）
- [x] シナリオ配信の具体的な設定画面 → `lstep_accounts_analysis.md` に記録
- [x] 流入経路の作成画面と QR / URL 導線
- [x] タグ一覧（みかみ/スキルプラス両方） → `lstep_accounts_analysis.md` に記録
- [x] 友だち情報欄の一覧（スキルプラスサポートLINE / 予約窓口のCSVベース）
- [x] アクション管理の設定パターン
- [ ] 自動応答の設定状況
- [x] テンプレートフォルダ一覧の全体構造 → `lstep_accounts_analysis.md` に記録
- [x] 予約管理の current 解釈（カレンダー予約 / イベント予約の使い分け）
- [x] `スキルプラス【サポートLINE】` と `【予約窓口】スキルプラス合宿` のテンプレート / 流入経路 / タグ / リッチメニューの役割整理
- [x] クロス分析の用途と、アドネスで相性が良い軸の整理
- [x] クロス分析の作成画面と保存前の操作確認
