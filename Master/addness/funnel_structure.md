# アドネス ファネル全体構造

最終更新: 2026-03-12

## 情報ラベル

- 所有元: internal
- 開示レベル: task-limited
- 承認必須: conditional
- 共有先: 僕 / 上司 / 並列 / 直下

## 概要

アドネスの集客〜成約までのファネルは、**入口の広告/集客経路**によって複数の導線に分かれるが、最終的には「個別相談 → 成約」に合流する。

UTAGE 側のカテゴリ構造、グループ運用、current の作法は `Master/addness/utage_structure.md` を正本として参照する。

```
広告/集客 → LP → メール取得 → OTO(¥2,980) → LINE登録 → リマインド配信 → 個別相談 → 成約
```

### ファネル共通の流れ

| ステップ | 内容 | ツール |
|---------|------|--------|
| 1. 広告 | Meta広告(FB/IG) / リスティング広告 / YouTube | Meta Ads Manager |
| 2. LP | オプトインLP（メールアドレス取得） | 各種LP |
| 3. サンクスページ | 登録完了 + ワンタイムオファー(OTO) ¥2,980 | UTAGE |
| 4. OTO | フロント商品購入（¥2,980）。ここのCPO = フロント購入単価 | UTAGE |
| 5. LINE登録 | 公式LINEに誘導。導線ごとに異なるLINE | Lステップ |
| 6. リマインド配信 | メール + LINE で複数日にわたりナーチャリング | UTAGE / Mailchimp + Lステップ |
| 7. 個別相談 | zoom で1on1。セールス | zoom |
| 8. 成約 | バックエンド商品の購入 | - |

### KPI計測ポイント

```
広告 → LP → メール取得 → OTO購入 → LINE登録 → 個別予約 → 成約
       CPA        CPO                          CPO(バック)   ROAS
       (集客単価)  (フロント購入単価)                          (売上/広告費)
```

## 導線を触る時の最短切り分け

### 先に `何を変えたいか` を切る

- `LP / thanks / 会員サイトの見え方や CTA を変えたい`
  - まず UTAGE の `ファネル > ページ一覧の行名` を正本にする
  - 触る中心は `page / デザイン / form / action / product`
- `同じページのまま流入元や計測だけ分けたい`
  - まず UTAGE の `登録経路` と short.io を疑う
  - 広告 ID や設置場所の違いだけでページ複製しない
- `メールの件名 / 本文 / 配信順 / current 送信内容を変えたい`
  - まず Mailchimp の current Journey と active step を見る
  - UTAGE の scenario 名だけで、本線メールの正本と決めない
- `LINE の着地先を差し替えたい`
  - まず short.io と URL管理シートを正本にする
  - UTAGE や Mailchimp 本文に LIFF 直書きが残っていても、それは `修正対象候補` であって正本とは限らない
- `LINE 登録後のタグ / シナリオ / 個別予約導線を変えたい`
  - Lステップ の `流入経路 / タグ / シナリオ / テンプレート` を見る
  - LINE 名だけで判断せず、最終的に何の tag が付き、どの scenario が始まるかまで落とす
- `商品 / 決済 / 会員サイト解放を変えたい`
  - UTAGE の `product 本体` だけで判断しない
  - `detail -> action -> bundle` まで見て初めて正本を確定する

### 実務での判断順

1. 変更したいものが `見た目 / 計測 / メール / LINE着地 / LINE後処理 / 商品解放` のどれかを固定する
2. `ファネル名 > ページ一覧の行名` で対象を特定する
3. 公開URL、HTML source、short.io、LIFF、Mailchimp CTA のどれが `表示` で、どれが `正本` かを切り分ける
4. 変更は正本 1 箇所だけに入れる
5. 最後に、利用者と同じ順番で実 click して最終挙動を確認する

### 導線修正で誤りやすいこと

- `公開URL` と `ページ一覧の行名` と `source 上のリンク先` を同じものとして話す
- `visible landing` だけ見て、下流の `Zapier -> Mailchimp` relay を見落とす
- LINE の差し替えを UTAGE 本文側から始めて、short.io の正本を飛ばす
- `停止中 LIFF` が source に残っているだけで断定し、実 click の最終着地を見ずに判断する

---

## みかみ導線（SNSファネル）

> ソース: Lucidchart（みかみ導線.pdf）

### 導線の特徴

- みかみさん（著名人）の公式LINEに誘導する導線
- SNSファネルの主力。Meta広告(Facebook/Instagram)で集客
- UTAGE でメール自動配信を管理
- リマインド配信は9通構成（RM_1〜RM_9）

### フロー詳細

```
Meta広告（複数CR）
  ↓
各種LP（バージョン違い多数。LP_24/08/12 等）
  ↓
メールアドレス取得
  ↓
サンクスページ → ワンタイムオファー（OTO ¥2,980）
  ↓
UTAGE メール自動配信
  ├── Facebook連携（UTAGE_メール→_Facebook_連携）
  ├── LINE連携（UTAGE_メール→_LINE連携_メール3通）
  └── 3日間OTO連携（UTAGE_メール→_Facebook_3日間OTO連携）
  ↓
みかみさん公式LINE 登録
  ↓
リマインド配信（RM_1〜RM_9）
  ├── RM_1: 初回案内 + 20分動画
  ├── RM_2〜RM_6: Q&A形式のナーチャリング
  ├── RM_7: 追加Q&A
  ├── RM_8: まとめ
  └── RM_9: 最終案内
  ↓
SNS配信コンテンツ（複数日にわたる配信）
  ├── 1日目〜5日目: 配信コンテンツ（19:06, 21:17, 12:03等の時間指定あり）
  └── SNSマーケティング2.0 関連コンテンツ
  ↓
個別相談（zoom）
  ↓
成約
```

### LP構成

- 複数のLPバージョンが存在（日付管理: LP_24/08/12 等）
- FVパターン違い（FV差し替えでABテスト）
- LP → サンクスページ → OTO の一連はUTAGEで管理

### DM（ダイレクトメッセージ）

- LINE上でDM送信によるフォローアップあり
- 個別相談への予約促進に使用

---

## スキルプラス導線

> ソース: Miro ボード（スキルプラス導線）

### 導線の特徴

- スキルプラス公式LINEに誘導する導線
- 3つの主枝がある（セミナー / 無料体験会 / ライトプラン / その周辺枝）
- current 実態は `スキルプラス` 本体だけで閉じておらず、`スキルプラス@企画専用` と `【スキルプラス】フリープラン` を含む parallel 運用
- `visible landing` と `友だち追加時設定` は空でも、`content-group` 側に current シナリオが残っているため、landing 画面だけでは全体を誤認する

### サブ導線 1: リスティング広告

```
リスティング広告（Google等）
  ↓
LP（複数バージョン）
  ↓
リストイン直後
  ↓
スキルプラス公式LINE
  ↓
リッチメニュー
  ├── 90秒動画（仕事を変える技術）
  ├── SKILL PLUS サイト
  └── 詳細情報ページ
```

### サブ導線 2: 無料体験会導線（直個別の導線）

```
Meta広告
  ↓
オプトインLP（メール取得）
  ↓
サンクスページ
  ↓
UTAGE メールシナリオ → アナリティクス連携
  ↓
スキルプラスメインのLINE
  ↓
リストイン直後（無料体験会への案内）
  ↓
無料体験会参加
  ↓
個別相談 → 成約
```

### サブ導線 3: セミナー導線

```
Meta広告
  ↓
オプトインLP（「3STEPを年商30億社長が伝授」）
  ↓
サンクスページ（「まだ登録は完了していません!」）
  ↓
UTAGE メールシナリオ
  ↓
スキルプラスメインのLINE
  ↓
リストイン直後
  ↓
スキル習得セミナー（エバーグリーンで常時開催）
  ↓
セミナー内で「ロードマップ作成会」をオファー
  ↓
個別相談 → 成約
```

---

## AIファネル

> **AIファネル = SNS（みかみ）ファネルの横展開。** 導線構造は同一で、CRの訴求をAI関連に変えただけ。

- 大当たりCRの46.5%がAIファネル（158件/340件） — 最大のファネル
- 主力の訴求: AI活用・ChatGPT・プロンプト等
- 行き先LINE: 【みかみ】アドネス株式会社（SNSファネルと同じLINE）
- 導線構造: みかみ導線と同一（広告 → LP → メール → OTO → みかみ公式LINE → RM配信 → 個別相談 → 成約）

### 2026-03-08確認: 現在のAI Metaメイン導線

対象ファネル:

- UTAGE `AI：メインファネル_Meta広告`

入口LPの実態:

- 現行LPは1本ではなく、同一ファネル内に複数存在
- 主要な入口は `Meta広告_AI_オプトインLP1` 〜 `LP5`
- LP1 / LP3 / LP4 は同系統で、`10年後も武器になるスキル` と `みかみ式AIマネタイズ4STEPテンプレート` を約束するテンプレ受取型
- LP3 はヒカルさん用、LP4 は林さん用で、著名人・クリエイティブ差し替えの役割
- LP2 / LP5 は別系統で、無料ウェビナー視聴型
- LP5 は `ChatGPTはプロンプトが重要？それ、間違いです。` から入る本質訴求のCR別LP

UTAGEの入口シナリオ:

- LP1〜LP5 は全て `AIカレッジ：FB広告【7桁オプトインシナリオ】` に接続
- このシナリオはメール本体を持たず、以下4つのアクションのみを実行
- 登録直後: `全体配信登録用ラベル` を付与
- 1日後: `AIカレッジ：FB広告【個別3日間シナリオ】` に登録
- 1日後: `全ファネル共通：【電話番号シナリオ】` に登録
- 23日後: `全ファネル共通：【週刊みかみ】` に登録し、`週刊みかみ購読中` ラベルを付与

UTAGEでメールを持っている部分:

- `AIカレッジ：FB広告【個別3日間シナリオ】` は UTAGE 上ではステップ配信 0件
- `全ファネル共通：【電話番号シナリオ】` は 3通のメールを保持
- `全ファネル共通：【週刊みかみ】` は週刊メールを 23通保持

Mailchimpの役割:

- 主ナーチャリングは Mailchimp の `Customer Journey` 側で動いている
- classic automation は未使用
- 入口の主Journeyは `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
- trigger tag は `UTAGE_AI_FB_Optin`
- `UTAGE_AIカレッジ_Facebook_個別3日間シナリオ 2025-10-15` も同じ `UTAGE_AI_FB_Optin` で発火
- `秘密の部屋`、`AI合宿`、購入後サンキューも別Journey・別タグで分岐

Mailchimp live UI で追加確認できたこと:

- ログインは `login.mailchimp.com` から入り、`us5.admin.mailchimp.com/login/tfa` の SMS 二段階認証を経て `Home` に入る
- `Automations` 一覧には `Build from scratch`、`Choose flow template`、`Search by name`、`Status`、`Objective`、`Sort by: Last created` が並ぶ
- `Build from scratch` から `customer-journey/create-new-journey/` に入り、`Name flow`、`Audience`、`Choose a trigger` の順で新規 flow を組み始める
- Journey 名クリックで `customer-journey/builder?id={id}` に入る
- builder 上部には `Send Test Emails`、`View Report`、`Pause & Edit`、`Save and close flow` があり、運用上の主操作はここに集約されている
- map 上では `Contact tagged ...`、`Filter who can enter`、`Send email ...`、`Contact exits` を管理し、右パネルは `Data / Settings` 切り替えで読む

Zapierの役割:

- Zapier アカウントには 263 Zap が存在し、225件が稼働中、34件が停止、4件が draft
- 署名ベースで見ると 204件が `WebHookCLIAPI:hook_v2 -> MailchimpCLIAPI:memberCreate` で、アドネスの front funnel 連携基盤はほぼこの型に集約されている
- 次点は `GoogleSheets updated_row_notify_hook -> WebHook post`（SMS送信系）、`WebHook -> GoogleSheets add_row`（ログ蓄積系）、`Mailchimp new_member -> Sheets/BigQuery`（集計系）
- AI / SNS / 秘密の部屋 / 購入完了など複数導線の橋渡しを担当しているが、主用途は「Webhook で受けて Mailchimp に tag を打つ」こと
- AI Meta周辺の主な構造は `WebHookCLIAPI -> Mailchimp memberCreate` の2ステップ構成
- Mailchimp 側の送信先 audience は共通で `82aeac7431`（ラベル: `アドネス株式会社`）
- つまり UTAGE 側で発生したオプトインや購入イベントを Webhook で Zapier に流し、Zapier が Mailchimp に tag を打って Journey を起動している

2026-03-08確認: AI Meta関連の主要 Zap と tag 対応:

- `UTAGE_AIcollege_Facebook_7桁オプトイン` -> `UTAGE_AI_FB_Optin`
- `UTAGE_AIカレッジ_Facebook_合宿購入` -> `all_front_buyers`, `UTAGE_AI_FB_Gassyuku_Buy`
- `UTAGE_AIカレッジ_Facebook_秘密の部屋購入` -> `all_front_buyers`, `UTAGE_AI_FB_Himitsu_Buy`
- `Meta_AI_7桁_合宿購入` -> `Meta_AI_7keta_GassyukuOTO_Buy`, `all_front_buyers`
- `Meta_AI_7桁_秘密の部屋購入` -> `Meta_AI_7keta_HimituOTO_Buy`, `all_front_buyers`
- `Meta広告_秘密の部屋_オプトイン` -> `metaad_himitsu_optin`
- `Meta広告_秘密の部屋_月額プラン購入_導線内用` -> `metaad_himitsu_monthly_buy`
- `Meta広告_秘密の部屋_月額プラン購入_OTO用` -> `metaad_himitsu_monthly_buy_OTO`
- `Meta広告_秘密の部屋_年間プラン購入` -> `metaad_himitsu_yearly_buy`

AI Facebookのサンキューメール系 Zap:

- `AI｜FB｜合宿3dayサンキューメール` -> `UTAGE_AIcollege_Facebook_3dayG-Kounyuu`
- `AI｜FB｜合宿15minサンキューメール` -> `UTAGE_AIcollege_Facebook_15minG-Kounyuu`
- `AI｜FB｜秘密の部屋メールシナリオ｜サンキューメール` -> `UTAGE_AIcollege_Facebook_H-mail_Kounyuu`
- `AI｜FB｜秘密の部屋OTOサンキューメール` -> `UTAGE_AIcollege_Facebook_H-OTO_Kounyuu`

現時点の解釈:

- `UTAGE_AIcollege_Facebook_7桁オプトイン` は、現在確認できている AI Meta入口の Mailchimp 起点 Zap と見てよい
- AI Metaの購入系は、旧命名の `UTAGE_AIカレッジ_Facebook_*` と新命名の `Meta_AI_*` / `Meta広告_*` が併存している
- 少なくとも Mailchimp Journey と一致している tag から見る限り、現在の「秘密の部屋」導線は `Meta広告_秘密の部屋_*` 側が本線
- 一方で 7桁オプトインの入口タグは依然 `UTAGE_AI_FB_Optin` で、Zap 名も旧命名が残っている
- つまり運用実態は「導線の表示名・LP名は更新されているが、Zap / tag 命名は旧構造を引き継ぎつつ一部新設で増築されている」状態

未確定:

- Webhook トリガー自体の受信用 URL までは未抽出
- ただし Zap 単位では `Webhook -> Mailchimp tag付与` の橋渡しが明確に確認できているため、UTAGE と Mailchimp の接続層として Zapier が本番運用されていることは確定

現時点の構造理解:

- AI Meta導線は `複数LP -> 共通UTAGE入口 -> Mailchimp主ナーチャリング + 一部UTAGE補助シナリオ` のハイブリッド構造
- その接続層は `UTAGE webhook -> Zapier tag付与 -> Mailchimp Journey` の3層構造
- 入口LPはクリエイティブ別に約束が分かれている一方、下流メールはかなり共通化されている
- 今後のCR企画とLP調整では、`CR -> LPの約束 -> 最初のMailchimp件名` の接続確認が重要

---

## ファネル横断の共通基盤: short.io 固定リンク運用

### 位置づけ

- short.io は、アドネスの導線作成オペレーションで常用している短縮リンク基盤
- 役割は単なる短縮ではなく、`長いURLの短縮`、`設置先ごとの流入経路識別`、`リンク差し替え時の設置箇所修正コスト削減` の3つ
- 実運用上は、UTAGE / Mailchimp / LINE / SNS / SEO / 広報の各導線を横断して使われている
- 固定リンク用のカスタムドメインは `skill.addness.co.jp`
- アドネス導線では、`LINE に送るリンクは必ず short.io で管理する` のが原則
- 理由は、公式LINEやLステップが BAN / 停止になったときでも即時にリンク差し替えができ、直書き LIFF によるヒューマンエラーを防げるから
- したがって、UTAGE や Mailchimp に LIFF を直書きするのは運用上のアンチパターン

### 現在確認できている運用実態

- short.io の管理画面は `app.short.io/users/dashboard/1304048/links`
- ダッシュボード上には `Folder`、`インポート`、`シート` の導線があり、個別作成だけでなく一括管理を前提にした運用
- `シート` 画面には `一括作成` 導線があり、短縮リンクの台帳管理と整合している
- 実リンクは `https://skill.addness.co.jp/<slug>` 形式で発行され、そこから LINE や LP に 302 リダイレクトされる
- 例: `https://skill.addness.co.jp/ytad-main-sns1` は LINE の LIFF URL にリダイレクト
- dashboard 一覧の列は `短縮リンク / 元のリンク / クリック数 / コンバージョン数 / タグ / アクション`
- quick create は `Paste URL here...` に元URLを入れて `リンクを作成` を押すと、その場で短縮URLが自動発行される
- 作成直後に `path` を持つ編集フィールドが出るため、slug の最終調整は作成直後に行う前提
- 既存リンク編集は `users/dashboard/{domainId}/links/{linkId}/edit/basic` に入り、`path / title / originalURL / folderId / tag` を編集する
- 既存リンク統計は `users/dashboard/{domainId}/links/{linkId}/statistics` で見る
- `ドメイン統計` では `過去30日` を基準に、上位リンク / 都市 / 国 / ブラウザ / OS / リファラー / ソーシャルリファラー / ミディアム / ソース / キャンペーンを読める
- `統合とAPI` は `app.short.io/settings/integrations` にあり、`API / ブラウザプラグイン / アプリケーション / Slack / Wordpress / Zapier / Make / GitHub Actions / MCP` を持つ

### URL管理シート

- 管理用スプレッドシートは `【アドネス全体】URL管理シート`
- hidden backend は `01_全体台帳`
- visible の作業タブは `集客媒体` ごとに分ける
- visible タブは `共通 / Meta広告 / TikTok広告 / YouTube広告 / 𝕏広告 / LINE広告 / Yahoo広告 / リスティング広告 / アフィリエイト広告 / YouTube / 𝕏 / Instagram / Threads / TikTok / 一般検索 / 広報 / オフライン / その他`
- `01_全体台帳` は master で、列は `ファネル名 / 集客媒体 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
- visible タブの列は `ファネル名 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態`
- `共通導線` の行は `共通` タブへ寄せる
- 各タブ内の並び順は `センサーズ -> AI -> アドプロ -> スキルプラス -> ライトプラン -> 書籍 -> その他`
- 旧タブ群は削除済みで、current は `集客媒体タブ + hidden master` だけで見る
- 広告系 4 タブは、非破壊で hidden の `広告（統合）` に集約した
- `広告（統合）` の列構成は `導線 / カテゴリ / 設置場所 / リンクタイトル / URL / 遷移先名 / 遷移先 / 更新日`
- old 4 タブにあった `飛び先URL` は `遷移先リンク` に統合し、`最新（YYYY/MM/DD）` は行単位の `更新日` に正規化した
- `未作成` の行は master / visible ともに削除済み
- 体裁は `スプレッドシート設計ルール` に合わせて、ヘッダー色、フィルタ、凍結、交互色、列幅、`切り詰める(CLIP)` を再適用した
- C列とD列は文字が見える幅まで広げた
- 実務上は「short.io でリンクを作る」だけでなく、「どこに置かれていて、今どこへ飛ばすのか」をこのシートで管理している
- `System/scripts/shortio_api_client.py sync-ads-sheet` で、`広告（統合）` の `遷移先 / 更新日` を short.io 実体と照合・同期できる
- `System/scripts/shortio_api_client.py rebuild-sheet-views` で、`01_全体台帳` から visible の集客媒体タブを再構築できる
- `--delete-obsolete` で `00_役割と使い方` を含む旧タブ群を削除でき、live シートもこの形へ寄せた
- `System/scripts/shortio_api_client.py audit-sheet` で台帳品質を監査できる
- 2026-03-10 時点の監査では、`未作成` を除く残差は `0件` まで解消している
- 2026-03-10 の実行では `379件` をチェックし、`373件` を同期した
- unresolved は `4件` で、`YhBCLQ` と `metaad-light1` は short.io 実体が見つからない broken 候補
- 2026-03-08 時点の行数は `広告（みかみ導線）474`、`広告（スキルプラス導線）63`、`広告（ライトプラン導線）45`、`SNS34`、`SEO9`、`広報24`、`その他7`
- `最新フラグ` の `FALSE` は、停止管理が厳密に運用されていることを意味しない。現状はシート運用が破綻気味で、この列だけで現役 / 停止を判定するのは危険

### Loom で補強できた運用ルール

- 動画タイトルは `LSTEPの短縮URL作成と管理方法について📈`
- Loom ページで確認できた概要は
  - `LSTEPの流入経路を管理しやすくするための短縮URLに変換する一連の手順`
  - `命名規則を守ることが非常に重要`
  - `作成した短縮URLは必ずスプレッドシートに記入し、チーム全体で共有する`
  - `リンク先変更時の手順も決めておく`
- Loom のチャプターは
  - `00:00 短縮URL作成手順の説明`
  - `02:02 短縮URL作成ツール紹介`
  - `04:06 ショートIOの使い方`
  - `10:37 短縮URLの管理方法`
  - `13:14 リンク先の差し替え手順`
  - `16:50 まとめと運用のポイント`
- 文字起こしから fixed できた実務手順は
  - 先に Lステップ の流入経路を作る
  - 流入経路名は命名規則どおりに付ける
  - short.io dashboard の `ブランドリンク` で元URLを貼り付ける
  - `カスタマイズ機能 -> 基本的なリンク編集` で `リンクスラグ` と `リンクタイトル` を設定する
  - `リンクタイトル` は流入経路名と完全一致させる
  - `リンクスラグ` は媒体や導線のルールに沿った英数字で付ける
  - 置き先のフォルダを選ぶ
  - 作成後は URL管理シートの該当 `集客媒体` タブに `ファネル名 / 設置場所 / リンクタイトル / リンクURL / 遷移先名 / 遷移先リンク / 更新日 / 状態` を記録する
  - 差し替え時は short.io 内で対象リンクを検索し、鉛筆ボタンから `元のURL` を新URLへ置き換える
- current の考え方として重要なのは
  - 命名規則を守って作る
  - short.io でリンクを作成する
  - URL管理シートへ記録する
  - リンク先変更は設置箇所を直すのではなく short.io 側で差し替える
- つまり short.io は `短縮する道具` ではなく、`リンクの正本を一箇所に寄せるための運用基盤`
- この運用により
  - BAN / 停止時の差し替えを速くする
  - 設置箇所ごとの修正漏れを防ぐ
  - 命名と台帳を揃えて後から追えるようにする

### 使われ方の傾向

- `広告（みかみ導線）` シートでは YouTube広告 / メール / UTAGEサンクスページなど、みかみ導線の各接点に対して短縮リンクを割り当てている
- `広告（ライトプラン導線）` では、`Meta広告_秘密の部屋_*` など現在の AI / 秘密の部屋導線に対応する短縮リンクが管理されている
- `SNS` シートでは、YouTubeチャンネルや SNS 導線からの直リストイン / AI導線 / ロードマップ導線が管理されている
- `SEO`、`広報`、`その他` では、記事CTA、note、採用、エラー時の代替導線など、広告外の導線も同じ基盤で管理されている
- 例: `metaad-sns5` は `広告（みかみ導線）` にあり、`SNS7桁オプトインシナリオ2通目 / ファン化動画ページ` から `みかみメイン公式LINE` に送る本気コンサル導線として管理されている

### short.io API / 自動化余地

- フロント実装上、short.io は `https://api.short.io` と `https://profile.short.io` を利用している
- 認証は Cookie ではなく `Authorization: JWT <token>` で、ブラウザ側では `IndexedDB(localforage)` に `encrypted_jwt` / `encrytion_key` / `iv` を保存している
- リンク一覧は `/api/links` と `/links/list/search/{domainId}`、統計は `/domain/{id}/last_clicks` や `/domain/{id}/top` から取得する構造
- 統計系は `api.short.io` と `stats-eu.short.io` の両方に同じ `POST /domain/{id}/last_clicks` / `POST /domain/{id}/top` を投げ、結果をマージする実装
- 既存の browser cookie をそのまま `api.short.io` に送っても 401 で、cookie だけでは API に入れない
- つまり将来的に `short.io のクリック数 -> URL管理シート` を同期する基盤は存在する
- 現時点では `IndexedDB に保存された JWT を復号して Authorization ヘッダに載せる` 最後の部分だけが未完了

### 現時点の解釈

- short.io は「補助ツール」ではなく、アドネスのファネル横断オペレーションにおける URL 抽象化レイヤー
- 今後の導線設計では、LP / LINE / メール本文の実URLだけでなく、`どの短縮リンク slug を使うか` と `台帳にどう記録するか` まで含めて設計する必要がある
- クリック分析を始める場合も、新しい計測基盤を増やすより、まず short.io と URL管理シートを接続するのが自然
- 2026-03-08 に確認した停止中LINE誤接続も、`UTAGE ページ内の LIFF 直書き` が原因で起きており、この原則を守る重要性を裏づけている

---

## 構造理解で取りに行くもの / 今は取らないもの

### 取りに行くもの

- 主要ファネルごとの `入口CR類型 -> LP / フォーム -> UTAGE -> Zapier -> Mailchimp -> short.io / UTAGE CTA -> LINE名 -> Lステップ内の面談化地点` の完全配線
- AI、SNS、スキルプラス、ライトプラン（秘密の部屋）の主線と、購入後・面談前の分岐
- LPやクリエイティブ差分のうち、面談化の動線やシナリオ分岐に影響するもの
- Mailchimp の件名、本文、CTA、送信先タグ、Journey step の対応
- short.io の slug と実際の遷移先、どの設置場所で使われているか
- LINE の着地先は ID ではなく LINE名で把握し、必要時のみ ID を補足する

### 今は取らないもの

- 媒体別・クリエイティブ別の厳密な寄与度や実数評価
- 過去運用で記録されていない数値、もしくは未計測の数値
- URL管理シートの `TRUE / FALSE` を正として全件監査すること
- 旧導線や停止ファネルの完全棚卸し（現行主線の理解に不要な範囲）
- 同じ構造の copy メールや予備シナリオの網羅収集

### 判定原則

- `構造` は、今あるツールと権限で原理上すべて取り切れる前提で扱う
- `数値` は、計測されている範囲だけを事実として扱う
- 現役判定は、管理シートのフラグではなく `実際に流れているシナリオ / 配信本文 / CTA先` を優先する
- 取りに行くべきか迷う情報は、`面談化地点までの線を明確にするか` で判断する

---

## 2026-03-08確認: 現役主線の完全配線

### AI Meta導線

- UTAGE の現役ファネルは `AI：メインファネル_Meta広告`。ファネル step 自体の `updated_at` は `2026-02-28` まで更新されている
- 現在の入口LP step は `Meta広告_AI_オプトインLP1〜5` の5本
- 現在の先頭ページはそれぞれ以下
  - LP1: `AIカレッジ_FB広告_optin2_長め_みかみ式_緑LPテイスト_FV AI美女2_分野を問わない_累計10万人`
  - LP2: `新4つのノウハウLP_下層新テイスト_Amazon_権威ビジネスswitch_FVクロード_10万人が参加`
  - LP3: `10年後も武器_ヒカルさんLP`
  - LP4: `10年後も武器_林さんLP`
  - LP5: `プロンプトが重要`
- LP1〜LP5 のフォームはすべて同じ UTAGE シナリオ `AIカレッジ：FB広告【7桁オプトインシナリオ】` に接続
- LP後の遷移先は共通ではなく、クリエイティブ別に 15分ウェビナー側の landing page が分かれている
  - LP1 -> `p/BDDVNnsFzVO9`（15分OTO_合宿_オファーページ）
  - LP2 -> `AI_15分ウェビナー_LP2遷移先_26/02/18〜`
  - LP3 -> `AI_15分ウェビナー_ヒカルさんLP遷移先_26/02/18〜`
  - LP4 -> `AI_15分ウェビナー_林さんLP遷移先_26/02/18〜`
  - LP5 -> `AI_15分ウェビナー_プロンプトが重要訴求_遷移先`
- 重要なのは、LP差分はあるがオプトイン時の scenario は一本化されていること。`LP訴求は分岐、登録処理は共通` の構造

### AI Metaの Mailchimp 側

- `UTAGE_AI_FB_Optin` は Mailchimp 上で少なくとも2本の live journey を同時に起動している
- main journey は `10934 / UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15`
  - trigger tag: `UTAGE_AI_FB_Optin`
  - 1通目は `9c03ee4499 / AIカレッジFB広告_メインシナリオ1通目 (copy 05)`
  - 1通目の主要クリック先は `meta-ai2` と `p/OL5vahWh20nn`
  - `meta-ai2` は short.io で `【みかみ】アドネス株式会社` にリダイレクト
  - `p/OL5vahWh20nn` は UTAGE の `ファン化動画視聴ページ`
  - 途中で `9da38c6346 / AI導入プロコンサル` が入り、クリック先 `meta-ai4` も `【みかみ】アドネス株式会社` に着地
  - その後は条件分岐を挟みつつ、`スキルプラスフリープラン` メール群まで続く
- 個別誘導 journey は `10955 / UTAGE_AIカレッジ_Facebook_個別3日間シナリオ 2025-10-15`
  - trigger tag: `UTAGE_AI_FB_Optin`
  - 3通とも `p/uUfErKGsQYZ2` に送る
  - 件名は `【今だけ無料！】...スタートダッシュコンサル開催`、`【速報】参加者殺到！...`、`【驚愕】『予約殺到』...`
- つまり AI Meta は `オプトイン1回 -> long nurture journey + 個別3日間 journey が並走` する設計

### AI の面談化地点

- `ファン化動画視聴ページ` の現役タイトルは `新ファン化動画`
- ここからの CTA は short.io `meta-ai5`
- `meta-ai5` は `【みかみ】アドネス株式会社` にリダイレクト
- ここで混同しやすいのは `UTAGE のページ一覧の行名` と `公開URL` と `HTML source 上のリンク` が別物な点
- `AI：メインファネル_Meta広告 > ページ一覧` の `個別3日間シナリオ` 付近では、次の 4 行をひとまとまりとして扱う
  - `ロードマップ作成会` -> `p/uUfErKGsQYZ2`
  - `AIロードマップ作成会_1日目` -> `page/QF0eOLXCquZe`
  - `AIロードマップ作成会_2日目` -> `page/r99dMAjryKBR`
  - `AIロードマップ作成会_3日目` -> `page/RRD8QHLuz4Fj`
- `ロードマップ作成会` の現役タイトルは `AIロードマップ作成会_FV変更`
- `follow=@804mrsmd` を確認した根拠は、上記 4 ページの `公開HTML source` に残っている LIFF リンク
- ただし `@804mrsmd` は `利用停止中アカウント一覧` に載っている停止済みLINE
- したがって、AI の個別3日間シナリオ配下ページは `source 上は停止中アカウントに接続する LIFF が残っている` 状態
- これは Facebook だけではなく、現役の `AI Facebook / X / TikTok` の個別3日間シナリオ全体で再利用されている
  - Facebook: `10955 / UTAGE_AIカレッジ_Facebook_個別3日間シナリオ 2025-10-15` と `10466 / UTAGE_AIカレッジ_Facebook_個別3日間シナリオ`
    - `ロードマップ作成会` -> `p/uUfErKGsQYZ2`
    - `AIロードマップ作成会_1日目` -> `page/QF0eOLXCquZe`
    - `AIロードマップ作成会_2日目` -> `page/r99dMAjryKBR`
    - `AIロードマップ作成会_3日目` -> `page/RRD8QHLuz4Fj`
  - X: `10729 / UTAGE_AIカレッジ_X広告_個別3日間シナリオ` と `10978 / UTAGE_AIカレッジ_X広告_個別3日間シナリオ 2025-10-15`
    - `ロードマップ作成会` -> `p/XcFB1Re3138v`
    - `AIロードマップ作成会_1日目` -> `page/1zIgM0ov1N6l`
    - `AIロードマップ作成会_2日目` -> `page/EjM7SIA6asfx`
    - `AIロードマップ作成会_3日目` -> `page/fmMBrwfj79bA`
  - TikTok: `10698 / UTAGE_AI_TT_個別3日間シナリオ`
    - `ロードマップ作成会` -> `p/sGZfeKR5gIHj`
    - `AIロードマップ作成会_1日目` -> `page/942st7ismQPi`
    - `AIロードマップ作成会_2日目` -> `page/Fmt589wM4zxb`
    - `AIロードマップ作成会_3日目` -> `page/eJTIBPx0mr8X`
- 上記ページはすべて `公開HTML source` に `follow=@804mrsmd` を持っていた
- 一方で、同じページ内の short.io `meta-ai3 / xad-ai3 / ttad-ai3` は `【みかみ】アドネス株式会社` に送っている
- 差し替え先は、アカウント名ではなく Lステップ 側で実際に付くタグ、入るシナリオ、予約導線を見て確定する必要がある

### AI 7桁フロント購入後導線

- 合宿 OTO 購入後は tag `Meta_AI_7keta_GassyukuOTO_Buy`
- Mailchimp では `Meta_AI_7桁【合宿講義案内メール】` が 6通あり、`講義1日目 -> 個別誘導1通目 -> 講義2日目 -> 個別誘導2通目 -> 講義3日目 -> 個別誘導3日目` の構成
- 個別誘導メールでは `“あなた専用”オリジナル0→100ロードマップ` を訴求し、`school.addness.co.jp/page/zMvuyqxWhHkc` に送っている
- つまり購入後は `講義視聴 -> ロードマップ作成 -> 面談化` の流れ

### SNS（みかみ）導線

- UTAGE の現役ファネルは `SNS：メインファネル_Meta広告`
- 現在の入口LP step は `Meta広告_SNS_オプトインLP1 / LP2_林さん用 / LP3_漫画LP / LP4_訴求別LP`
- 現在の先頭ページは以下
  - LP1: `X LP_小フォロワー_Amazon_BTN橙_13万人が参加_予告なく終了_AMAZON1位_出しなおし_260226_FV変更`
  - LP2: `FV林さん_小フォロワー_Amazon_BTN橙_13万人が参加_予告なく終了_AMAZON1位`
  - LP3: `251007_漫画LP_LP遷移`
  - LP4: `全部やめました`
  - 漫画移行先: `センサーズ短いLP_24/08/12_漫画LP移行先_過激なし`
- LP1 / LP2 / LP4 / 漫画移行先のフォームはすべて `センサーズ：FB【7桁オプトインシナリオ】` に接続
- LP1 / LP2 / LP4 は `p/ggDUz4esErGX` の 15分OTO に送る
- 漫画LPだけは `u8rjXXvtiC0V` という専用の 15分ウェビナー遷移先ページを使う

### SNS の Mailchimp 側

- `UTAGE_Snsers_FB-Optin` も Mailchimp 上で少なくとも2本の live journey を同時に起動している
- main journey は `10932 / UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15`
  - trigger tag: `UTAGE_Snsers_FB-Optin`
  - 1通目は `986dcc9cd9 / SNS_Meta広告_7桁_1通目`
  - 途中で `48ed0b9c61 / センサーズFB広告_本気コンサルオファー (copy 05)` と `61794feb2b / 本気コンサルRe` が入る
  - `48ed0b9c61` の主要クリック先は short.io `metaad-sns5`
  - `metaad-sns5` は `【みかみ】アドネス株式会社` にリダイレクト
  - この journey も後半で `スキルプラスフリープラン` メール群に接続している
- 個別誘導 journey は `10948 / UTAGE_センサーズ_Facebook_個別３日間シナリオ 2025-10-15`
  - trigger tag: `UTAGE_Snsers_FB-Optin`
  - 1通目は A/B テストで、`“あなた専用”0→100ロードマップ作成会` 訴求と `1st副業スタートプログラム` 訴求が並走
- つまり SNS も `オプトイン1回 -> story nurture + 個別3日間 journey が並走` する構造

### SNS の面談化地点

- `センサーズFB_ファン化動画視聴ページ` の現役タイトルは `新ファン化動画`
- ここからの CTA は short.io `metaad-sns5`
- `metaad-sns5` は `【みかみ】アドネス株式会社` に送る
- ここで混同しやすいのは `UTAGE のページ一覧の行名` と `公開URL` と `HTML source 上のリンク` が別物な点
- `SNS：メインファネル_Meta広告 > ページ一覧` の `個別3日間シナリオ` 付近では、次の行が面談化ページ群
  - `ロードマップ作成会` -> `p/1hHdsZDzq7hp`
  - `SNS_Meta広告_個別3日間_1通目_RM作成会LP` -> `page/KAtTy0tucas2`
  - `個別3日間_1通目_1st副業` -> `page/vQ8ZuYjSpxuh`
  - `SNS_Meta広告_個別3日間_2通目_RM作成会LP` -> `page/fksI4L8hNu4E`
  - `個別3日間_2通目_1st副業` -> `page/ICyZyVoDrD6K`
  - `SNS_Meta広告_個別3日間_3通目_RM作成会LP` -> `page/kjOhv6Z6lU8r`
  - `個別3日間_3通目_1st副業` -> `page/bbwZzf9MxRUb`
- `ロードマップ作成会` の現役タイトルは `センサーズ_ロードマップ作成会 （FV変更）`
- `follow=@804mrsmd` を確認した根拠は、上記ページ群の `公開HTML source`
- ただし `@804mrsmd` は停止済みなので、SNS のロードマップ作成会も同様に誤接続
- これも Facebook だけではなく、現役の `SNS Facebook / X` の個別3日間シナリオ全体で再利用されている
  - Facebook: `10948 / UTAGE_センサーズ_Facebook_個別３日間シナリオ 2025-10-15` と `10446 / UTAGE_センサーズ_Facebook_個別３日間シナリオ`
    - `ロードマップ作成会` -> `p/1hHdsZDzq7hp`
    - `SNS_Meta広告_個別3日間_1通目_RM作成会LP` -> `page/KAtTy0tucas2`
    - `個別3日間_1通目_1st副業` -> `page/vQ8ZuYjSpxuh`
    - `SNS_Meta広告_個別3日間_2通目_RM作成会LP` -> `page/fksI4L8hNu4E`
    - `個別3日間_2通目_1st副業` -> `page/ICyZyVoDrD6K`
    - `SNS_Meta広告_個別3日間_3通目_RM作成会LP` -> `page/kjOhv6Z6lU8r`
    - `個別3日間_3通目_1st副業` -> `page/bbwZzf9MxRUb`
  - X: `10950 / UTAGE_センサーズ_X_個別３日間シナリオ 2025-10-15`
    - `ロードマップ作成会` -> `p/GuMTqGD4HQvN`
    - `SNS_X_個別3日間_1通目_RM作成会LP` 相当 -> `page/HvfalKEpovcY`
    - `SNS_X_個別3日間_2通目_RM作成会LP` 相当 -> `page/eATwZkzzAhA8`
    - `SNS_X_個別3日間_3通目_RM作成会LP` 相当 -> `page/hWBJQ9Yti0d3`
- 上記ページはすべて `公開HTML source` に `follow=@804mrsmd` を持っていた
- X系の一部ページは `@804mrsmd` と `【みかみ】アドネス株式会社` の両方を同居させており、停止中と稼働中が混在している
- 差し替え先は、アカウント名ではなく Lステップ 側で実際に付くタグ、入るシナリオ、予約導線を見て確定する必要がある
- したがって SNS は現状、`みかみメインLINE` は正常だが `個別相談LINE` 側は停止アカウント誤接続の疑いが強い

### スキルプラス導線

- スキルプラスは単一導線ではなく、UTAGE 上でも `セミナー / 無料体験会 / 診断 / アフィリエイト / 9,800円販売ページ` に分岐している
- 現時点で最近更新が強いのは `スキルプラス_Meta広告`、`スキルプラス_アフィリエイト広告`、`新生スキルプラス9800決済LP`
- 2026-03-09 の Mailchimp active queue 基準では、`スキルプラス` を冠した単独 Journey の送信待ちは確認できなかった
- いま Mailchimp 上で実際に流れているスキルプラス送客は、AI / SNS の 7桁本線後半に差し込まれた `スキルプラスフリープラン` メール群として現れている

### スキルプラス Meta広告導線

- `スキルプラス_Meta広告` の最上段は `Meta広告_スキルプラス_オプトインLP4_セミナー導線`
- 現役タイトルは `メインLP_みかみさんFV_オレンジボタン_要素並び替え_特典(30億社長)_新テイスト荻野_AMAZON_CTAテスト②_ベネフィット追加_権威東北大学_全CR配信`
- フォームは `Meta広告_スキルプラス_ウェビナー①オプトインシナリオ`
- LP後は `p/E6g12WwMhDWI` の `【スキルプラス】サンクスページ（LINE登録）`
- このサンクスページは `1600ms` 後に LIFF `follow=@496sircr`、つまり `スキルプラス` 公式LINEに自動リダイレクト
- 同じファネル内に `Meta広告_スキルプラス_オプトインLP1_無料体験会` もあり、こちらは `Meta広告_スキルプラス_メインLP後シナリオ` に接続して `p/OfPQyNASfrdD` へ送る
- つまりスキルプラス Meta は、現役の中でも `セミナー導線` と `無料体験会導線` が併存している

### スキルプラス アフィリエイト導線

- `スキルプラス_アフィリエイト広告` の共通LPは `アフィリエイト広告_スキルプラス_オプトインLP_セミナー導線`
- 現役タイトルは `メインLP_FV4_オレンジボタン_要素並び替え_特典(30億社長)_新テイスト荻野_AMAZON_CTAテスト②_ベネフィット追加_LPv2.1`
- フォームは `アフィリエイト広告_スキルプラス_ウェビナー①オプトインシナリオ`
- LP後は `p/FQxGwY5hERn2` に送る
- Mailchimp では会社 / 媒体ごとに Journey が分かれている
  - `11042 / アフィリエイト広告_セミナー導線_オプトイン_A社_Meta`
    - trigger tag: `afad_seminar_optin_a_meta`
    - 2通構成: `【ご確認ください】セミナー無料招待のお知らせ` -> `【御礼】講師みかみからメッセージが届いています`
  - `11036 / アフィリエイト広告_セミナー導線_オプトイン_E社_Meta`
    - trigger tag: `afad_seminar_optin_e_meta`
    - 同じく2通構成
- クリック先 short.io は媒体 / 会社で分かれている
  - `afad-a-tiktok1` -> `スキルプラス@企画専用`
  - `afad-d-meta2` -> `スキルプラス@企画専用`
  - `afad-d-meta1` -> `スキルプラス`
- したがってアフィリエイト導線は、`共通LPテンプレ + 会社別tag + short.ioでLINE受け皿を分岐` の構造

### スキルプラス購入後

- `11000 / 【新生スキルプラス_月額9800】サンキューメール`
  - trigger tag: `skillplus_buy_9,800yen_miyashiro`
  - メール本体は `dd854bc9d5 / 【新生スキルプラス】_月額9,800円_サンキューメール`
  - 主導線は `スキルプラス` 公式LINE
- `11022 / 【新生スキルプラス_年間プラン購入者】サンキューメール`
  - trigger tag: `skillplus_buy_1nenplan_miyashiro`
  - メール本体は `d0e5f094c9 / 【新生スキルプラス】_年間プラン_サンキューメール`
- `10894 / フリープラン_入会完了_女性訴求プロモーション`
  - trigger tag: `freeplan_Buy_PR_woman`
  - 初手は `フリープラン_入会完了メール`

### 2026-03-10追加確認: スキルプラス@企画専用の actual funnel

- `スキルプラス` `スキルプラス@企画専用` `【スキルプラス】フリープラン` の3 account は、役割を分けて見る必要がある
- `スキルプラス` 本体と `企画専用` の友だち追加時設定には、デフォルトシナリオが入っていない
  - つまり、実質的な routing は `友だち追加直後` ではなく `landing action` と `event trigger` 側で起きる
- `スキルプラス` 本体の visible landing は 2件だけで、どちらも action は空
  - `follow=@496sircr&lp=pROdyv`
  - `follow=@496sircr&lp=4Pkxym`
- ただし本体側の `content-group` には current シナリオが残っている
  - `セミナー導線_予約シナリオ① -> ② -> ③ -> 「プロモ対象」タグ付け用シナリオ -> フリープラン`
  - `【アーカイブ】セミナー①企画LINE遷移シナリオ（1・2通目） -> （3・4通目）`
  - `無料体験会訴求シナリオ`
  - `本気コンサル① -> ②`
  - `ライトプラン導線_リストイン後シナリオ`
- actual URL も確認済み
  - current の `セミナー導線_予約シナリオ1〜3通目` は `https://l-cast.jp/s/a0fe/xKzfgCjvkHB` に直接送る
  - このページ title は `AI時代の事業家になる3STEPセミナー`
  - `【アーカイブ】セミナー①企画LINE遷移` の 2〜4通目は `https://skill.addness.co.jp/sp3` を使う
  - `sp3` は `follow=@230vpgmc&lp=ibnz0m` に 302 リダイレクトする
- `スキルプラス@企画専用` の `広告チームコピー用` landing では、`【新規】...` と `流入：...` のタグ追加、友だち情報 `新規流入 / 最終流入` 代入、`ウェビナー①予約シナリオ` 開始が実行される
- ただし、実シナリオ名は `ウェビナー①予約シナリオ` ではなく `セミナー①予約シナリオ` だった
  - group: `★セミナー導線`
  - id: `1107670`
  - 直後 + 1時間後の2通構成
- 予約後は L-cast event trigger に接続する
  - `event_registered` で `ウェビナー①_予約者` `ウェビナー①_参加予定` などを付与
  - `live_staying_25percent` で `ウェビナー①_着座`
  - `live_ended` で `ウェビナー①_不参加` を付与し、見逃し配信へ送る
- 参加者ルート
  - landing
  - `セミナー①予約シナリオ`
  - `セミナー①リマインド` 群
  - `セミナー導線_個別オファーシナリオ`
  - `フリープランシナリオ（○セミナー着座 ×個別予約）`
- 不参加ルート
  - `live_ended`
  - `セミナー①見逃し配信シナリオ_着座なし向け`
  - `見逃し配信_個別オファーシナリオ① -> ②`
  - `フリープランシナリオ（○セミナー予約 ×セミナー着座）`
- 並列で存在する枝
  - `無料体験会_流入シナリオ`
  - `本気コンサルシナリオ① -> ②`
  - `書籍導線_ウェビナー①予約シナリオ`
  - `セミナー導線_秘密の部屋販売シナリオ`
- current 解釈としては
  - `スキルプラス` = current のメイン受け皿であり、同時に `セミナー / 無料体験会 / 本気コンサル / ライトプラン / 企画LINE遷移` の content-group 導線も持つ
  - `スキルプラス@企画専用` = landing action と L-cast event trigger を持つ webinar 自動化本体
  - `【スキルプラス】フリープラン` = 個別オファー後の教育枝

### 2026-03-10追加確認: @496sircr の current 実流入

- `System/data/lstep_skillplus.csv` の current 友だち情報を集計すると、`スキルプラス` 本体には 2026-03 だけで `217件` の友だち追加がある
- そのうち `211件` で `新規流入 / 最終流入` が埋まっていた
- 上位は以下
  - `アフィリエイト広告_スキルプラス_セミナー導線_リストイン_E社_Meta` 56件
  - `TikTok広告_スキルプラス_リストイン_オートウェビナー1` 49件
  - `Meta広告_スキルプラス_リストイン_オートウェビナー1` 40件
  - `X広告_スキルプラス_リストイン_オートウェビナー1` 32件
- つまり、UTAGE の `@496sircr` サンクスページは今も current 流入を受けている
- ただし、`スキルプラス` 本体の visible landing action は空で、`友だち追加時設定` も 0件
- このため現時点の解釈は
  - `@496sircr` は current のメイン受け皿として生きている
  - 同時に main account 側でも `セミナー導線_予約シナリオ① -> ② -> ③ -> プロモ対象タグ付け -> フリープラン` の chain が current
  - `@230vpgmc` は webinar automation の中核として生きている
  - current main セミナー本線は `l-cast` に直接送り、`@230vpgmc` へ送るのは少なくとも今回確認できた範囲では `アーカイブ企画LINE遷移` 側
  - `UTAGE Meta サンクスページの lp=i0nQbh` と `@230vpgmc` の direct bridge はまだ未確定
  - 少なくとも現在は `main account path` と `企画専用 path` が parallel に存在する

### 2026-03-17追加確認: スキルプラス公式TV 概要欄導線

- YouTube `スキルプラス公式TV` の概要欄用に current 本番導線を追加
- CTA は `スキルプラスの無料体験会に今すぐ参加する`
- route 名
  - `（スキルプラス公式TV）YouTube _スキルプラス_直リストイン`
- route は `スキルプラス (@496sircr)` に作成
  - `follow_url`: `https://liff.line.me/2006618892-P3oWzoBb/landing?follow=%40496sircr&lp=GnsXlA&liff_id=2006618892-P3oWzoBb`
- route action
  - route tag 追加
  - `【新規】（スキルプラス公式TV）YouTube _スキルプラス_直リストイン` 追加
  - 必須 tag 追加
  - `友だち情報 [新規流入] / [最終流入]` 更新
  - `メインリッチメニュー（企画専用LINE遷移）に変更`
  - `無料体験会訴求シナリオ` 開始
- short.io
  - folder: `SNS(YT)`
  - path: `sp013`
  - title: `（スキルプラス公式TV）YouTube _スキルプラス_直リストイン`
  - short URL: `https://skill.addness.co.jp/sp013`
- 管理シート
  - `01_全体台帳` row `453`
  - `YouTube` row `20`
- 既知の差分
  - 既存 family にある `友だち情報 [新規流入日] = action_date` 更新は current API で 422 になり、今回の route には未設定

### 2026-03-09追加確認: Mailchimp active queue 基準の現役主線

- 2026-03-09 時点の現役判定は、Journey 単位ではなく `action-send_email` step 単位で見る
- 現役メールの定義は `journey_status = sending` かつ `step_status = active` かつ `queue_count > 0`
- `in_progress > 0` は「今は待機中だがまだ生きている導線」の補助指標として使う
- この基準で active queue が確認できた主要 Journey は以下
  - AI: `UTAGE_AIカレッジ_Facebook_7桁オプトイン2025-10-15` / `UTAGE_AIカレッジ_X広告_7桁オプトイン` / `UTAGE_AI_TT_7桁オプトイン2025-10-15` / `UTAGE_AI_YouTubeメインファネル_7桁オプトイン`
  - SNS: `UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15` / `UTAGE_センサーズ_X_７桁オプトイン` / `UTAGE_センサーズ_TikTok_７桁オプトイン 2025-10-15` / `LINE広告_センサーズ_７桁オプトイン`
- 逆に `journey_status = sending` でも `step_status = paused` のメールは、queue が残っていても現役メールとは扱わない
  - 例: `10932 / UTAGE_センサーズ_Facebook_７桁オプトイン 2025-10-15` の `110371 / 月額プラン2通目` は `queue_count = 3502` だが `paused`

### 2026-03-09追加確認: AI の現役メールが送っている先

- AI Facebook 7桁の現役 queue は大きく3系統
  - `スキルプラスフリープラン1〜5通目` と `フリープラン岡田結実2〜3通目`
    - Mailchimp 本文 -> `p/TzYRwepfqzFq` または `p/RWOaWnbUUD2f`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `AIカレッジFB広告_SNS企画2〜3日目` と `AIカレッジFB広告_プロンプト企画1 / 3日目`
    - Mailchimp 本文 -> `p/bjdKZd0oFq5x` / `p/fcSjv7TBWWpt`
    - UTAGE ページ内に `みかみ（停止中）` と `みかみ@AI_個別専用` が同居
  - `AIカレッジFB広告_AI導入プロコンサル`
    - Mailchimp 本文 -> short.io `meta-ai4`
    - short.io -> `【みかみ】アドネス株式会社`
- AI X 7桁の現役 queue も同じく3系統
  - `メインシナリオ3 / 5 / 7通目`
    - Mailchimp 本文 -> `p/F0JDVLj808Ja`
    - `pagevideo` 系で、今回確認した範囲では直接 LINE へ送る CTA は持たない
  - `スキルプラスフリープラン1〜5通目` と `フリープラン岡田結実1〜3通目`
    - Mailchimp 本文 -> `p/Nm7FomA8ENMX` / `p/fAeWWr3VDBQy`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `AI習得レッスン2〜5日目` / `プロンプト企画2〜3日目` / `SNS企画2〜3日目`
    - Mailchimp 本文 -> `p/AOll8d2WudH7` / `p/GKTTRK0sMhC4` / `p/Fyysb2Lzmafg`
    - UTAGE ページ内に `みかみ（停止中）` と `みかみ@AI_個別専用` が同居
  - `個別誘導2〜7通目` と `プチセミナー（プロコンサル）`
    - Mailchimp 本文 -> `p/XcFB1Re3138v` または short.io `xad-ai4`
    - `p/XcFB1Re3138v` は `みかみ（停止中）` と `【みかみ】アドネス株式会社` が同居
    - `xad-ai4` は `【みかみ】アドネス株式会社`
- AI TikTok 7桁も同じ構造
  - `メインシナリオ3 / 5 / 7通目`
    - Mailchimp 本文 -> `p/JljDL3IV2d69` / `p/4hYcCd5rDWgV`
    - どちらも `pagevideo` 系で、今回確認した範囲では直接 LINE へ送る CTA は持たない
  - `スキルプラスフリープラン1〜5通目` と `フリープラン岡田結実1〜3通目`
    - Mailchimp 本文 -> `p/tKEevtnsLmBs` / `p/keUm1C2qvbsZ`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `AI習得レッスン2〜5日目` / `プロンプト企画2〜3日目` / `SNS企画2〜3日目`
    - Mailchimp 本文 -> `p/WUY1RNzVg2YP` / `p/0LYFd15t6LOV` / `p/Dx60Z1wULbUK`
    - UTAGE ページ内に `みかみ（停止中）` と `みかみ@AI_個別専用` が同居
  - `個別誘導2〜7通目`
    - Mailchimp 本文 -> `p/sGZfeKR5gIHj`
    - UTAGE ページ内に `みかみ（停止中）` と short.io `ttad-ai3 -> 【みかみ】アドネス株式会社` が同居
- AI YouTube メインファネル 7桁も同じ構造
  - `スキルプラスフリープラン1〜5通目` と `フリープラン岡田結実1〜3通目`
    - Mailchimp 本文 -> `p/4Df4zMw4zWQc` / `p/YXugIyL7JNMS`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `AI習得レッスン2〜5日目`
    - Mailchimp 本文 -> `p/dDPPAyMxzWUX`
    - UTAGE ページ内に `みかみ（停止中）` と `みかみ@AI_個別専用` が同居
  - `プロンプト企画2〜3日目` / `SNS企画2〜3日目`
    - Mailchimp 本文 -> `p/FpMaLjUlD9oY` / `p/1M794M7I5Qzm`
    - UTAGE ページ内に `みかみ（停止中）` と `【みかみ】アドネス株式会社` が同居
  - `個別誘導2〜7通目`
    - Mailchimp 本文 -> `p/V6Yi7srMbp2E`
    - UTAGE ページ内に `みかみ（停止中）` と `【みかみ】アドネス株式会社` が同居

### 2026-03-09追加確認: SNS の現役メールが送っている先

- SNS Facebook 7桁の現役 queue は、いま確認できた範囲では2系統
  - `スキルプラスフリープラン1〜4通目`
    - Mailchimp 本文 -> `p/hNuqvGx9VJgZ`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `本気コンサルRe`
    - Mailchimp 本文 -> short.io `metaad-sns5`
    - short.io -> `【みかみ】アドネス株式会社`
- SNS X 7桁の現役 queue は4系統
  - `7桁オプトインシナリオ3 / 5 / 7通目`
    - Mailchimp 本文 -> `p/Lt5DGw6A3dVK`
    - コンテンツページで、今回確認した範囲では直接 LINE へ送る CTA は持たない
  - `かずくん1〜2通目`
    - Mailchimp 本文に `school.addness.co.jp` / `short.io` / LINE の直リンクは今回確認できなかった
  - `スキルプラスフリープラン1〜4通目` と `フリープラン岡田結実1〜3通目`
    - Mailchimp 本文 -> `p/plyZB7yEIKYD` / `p/aD0nFCiXHyrb`
    - UTAGE ページ -> `【スキルプラス】フリープラン`
  - `SNS垢メイキング1〜5通目`
    - Mailchimp 本文 -> `p/9ytudOvx2T31`
    - UTAGE ページ内に `みかみ（停止中）` と `みかみ@個別専用` が同居
  - `個別誘導6〜7通目`
    - Mailchimp 本文 -> `p/GuMTqGD4HQvN`
    - UTAGE ページ内に `みかみ（停止中）` と `【みかみ】アドネス株式会社` が同居
  - `本気コンサルRe_X`
    - Mailchimp 本文 -> short.io `xad-sns4`
    - short.io -> `【みかみ】アドネス株式会社`
- SNS TikTok 7桁と LINE広告_センサーズ 7桁の現役 queue は `SNS垢メイキング` が主
  - TikTok: `p/1qNpaYQ68Aml`
  - LINE広告: `p/iGcMpYHMpUQb`
  - どちらの UTAGE ページにも `みかみ（停止中）` と `みかみ@個別専用` が同居

### 2026-03-09追加確認: active queue ページの主CTA構造

- active queue がある混在ページは、公開 HTML 内の `elements-component v-bind:data` または `window.__INITIAL_STATE__.data` を直接解析して確認した
- 結論として、混在ページの多くは同じ構造になっている
  - 停止中 `みかみ / @804mrsmd` は、ページ中段までに `button` 要素として 3回前後繰り返し配置されている
  - 稼働中の導線は、ページ末尾近くに `form` 要素として 1回だけ置かれている
  - したがって UI 上の主 CTA は依然として停止中 LIFF 側であり、稼働中フォームが共存していても事故防止にはならない
- 停止中ボタンの共通パターン
  - 文言はほぼ全ページで `今すぐ無料で申し込む`
  - subtext は `あなた専用0→100スタートダッシュコンサル` または `あなた専用0→100ロードマップ作成会`
  - `href` は `follow=@804mrsmd` の LIFF 直リンク
- 稼働中フォームの共通パターン
  - `type = form`
  - `relation_elements = 1,2,3`
  - `reader_items` に `お名前` と `メールアドレス` が入り、フォーム送信型の CTA になっている
  - つまり、稼働中側は「見えるボタンを直した」ものではなく、「ページ末尾に別導線のフォームを後付けした」状態

#### AI の mixed page 構造

- AI Facebook `SNS企画` / `プロンプト企画`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: `みかみ@AI_個別専用`
- AI X / TikTok / YouTube の `AI習得レッスン`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: `みかみ@AI_個別専用`
- AI X / TikTok の `プロンプト企画` / `SNS企画`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: `みかみ@AI_個別専用`
- AI X / TikTok / YouTube の `個別誘導`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: short.io (`xad-ai3` / `ttad-ai3` / `ytad-ai3`) -> `【みかみ】アドネス株式会社`
- AI YouTube の `プロンプト企画` / `SNS企画`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: short.io (`ytad-ai5`) -> `【みかみ】アドネス株式会社`
- つまり AI は、同じ `0→100スタートダッシュコンサル` 訴求でも、ページ群によって `みかみ@AI_個別専用` と `【みかみ】アドネス株式会社` の両系統が併存している

#### SNS の mixed page 構造

- SNS X / TikTok / LINE広告 の `SNS垢メイキング`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: `みかみ@個別専用`
- SNS X の `個別誘導`
  - 旧主CTA: 停止中 `みかみ`
  - 新フォーム: short.io (`xad-sns3`) -> `【みかみ】アドネス株式会社`
- つまり SNS も、同じく `個別専用LINE` と `【みかみ】アドネス株式会社` の2系統が併存している

#### この時点で確定できること

- `停止中 LIFF` は hidden 要素ではなく、ユーザーが普通に押せる visible button
- `稼働中 LIFF / short.io` は存在するが、ページ末尾のフォーム要素であり、停止中ボタンより後ろに置かれている
- よって、2026-03-09 時点の mixed page 群では `停止中リンクが主 CTA のまま放置されている` と判断してよい

#### 2026-03-09追加確認: Lステップ 本体で確定した役割

- Lステップ の主要3アカウントを Chrome のログイン済みセッションから直接確認した
  - `みかみ@AI_個別専用`
  - `【みかみ】アドネス株式会社`
  - `みかみ@個別専用`
- 判定は `lm-account-id` ではなく、以下を使った
  - 流入経路の `follow_url`
  - ChatPlus の `LINE名(...)`
- ここで分かったこと
  - `みかみ@AI_個別専用`
    - AI 個別相談、プロコンサル、スタートダッシュ、AI合宿購入後オファーの受け皿
    - 代表タグ: `流入：PR_AI導入プロコンサル_2/8` `スタートダッシュコンサル_流入直後_送信済み_11/25~`
    - 代表シナリオ: `PR_25/11/21_AIスキル最短習得レッスン` `AI合宿購入後_SDコンサル`
  - `【みかみ】アドネス株式会社`
    - AI / SNS の共通メインLINE
    - 流入経路からタグ追加、テンプレ送信、シナリオ開始を直接持つ
    - 代表流入経路: `2/11：セミナーオプト(メルマガ)` `2/8：書籍無料受取希望→オプト` `AIディスプレイ広告`
    - 代表タグ: `共通LINE導線_AI_プロコンサル(メルマガorファン化動画)` `共通LINE導線_センサーズ_本気コンサル（メルマガorファン化動画）`
  - `みかみ@個別専用`
    - SNS系の直個別、RM作成会、個別アプローチの受け皿
    - 代表流入経路: `X_幸一ローンチ_みかみメイン直個別`
    - この流入経路ではシナリオ `【エバー】RM作成会_1_流入直後` を開始
- つまり、mixed page の稼働中側は次のように読むのが妥当
  - `AI向けの個別相談 / スタートダッシュ / プロコンサル` -> `みかみ@AI_個別専用`
  - `AI / SNS の共通メインLINE導線、ファン化動画接続、本気コンサル再訴求、書籍 / セミナー / ディスプレイ` -> `【みかみ】アドネス株式会社`
  - `SNS系の直個別 / RM作成会` -> `みかみ@個別専用`

#### 2026-03-09追加確認: スキルプラス系 Lステップ の current 役割

- `スキルプラス`
  - current API では `タグ 20件 / 流入経路 2件 / テンプレート 39件`
  - 流入経路 2件はどちらも `follow=@496sircr`
  - ただし流入経路名は `⚠️フォルダは勝手に増やさない...` `⚠️新たに流入経路作成時は...` で、実導線名ではなく運用メモになっている
  - visible landing の action は空だが、content-group 側に `セミナー / 無料体験会 / 本気コンサル / ライトプラン / 企画LINE遷移` の current 導線がある
- `スキルプラス@企画専用`
  - current API では `タグ 17件 / 流入経路 2件 / テンプレート 8件`
  - `Meta広告_スキルプラス_スキルプラス導線_リストイン` と `広告チームコピー用` がある
  - `広告チームコピー用` には
    - `⭐️必ずつけてね！` 系タグ付与
    - `新規流入 / 流入` タグ付与
    - `シナリオ[ウェビナー①予約シナリオ]` 開始
    - `新規流入 / 最終流入` の友だち情報代入
    が残っている
  - webinar event trigger を含む `運用の中身` は `スキルプラス@企画専用` 側でより明確に見える
- `【スキルプラス】フリープラン`
  - current API では `タグ 32件 / 流入経路 0件 / テンプレート 12件`
  - こちらはフリープラン導線の別系統として見るのが妥当
- したがって、スキルプラス系は `スキルプラス本体だけ見れば分かる構造` ではない
  - `スキルプラス` = メイン受け皿であり、同時に main 側の current content-group 導線も持つ
  - `スキルプラス@企画専用` = event-trigger を含む webinar 自動化本体
  - `【スキルプラス】フリープラン` = 別導線

### 停止中LINE誤接続の監査結果

- 2026-03-09 時点で、停止中なのに現役導線で使われていると確認できたのは引き続き `みかみ / @804mrsmd` のみ
- ただし影響範囲の認識は更新が必要
  - 旧認識: `AI / SNS の個別3日間導線だけ`
  - 更新後: `AI / SNS の個別3日間導線` に加えて、`Mailchimp で今も active queue がある 7桁本線の一部 UTAGE ページ` にも残っている
- 2026-03-09 基準で `@804mrsmd` の混在が確認できた現役本線は以下
  - AI Facebook 7桁: `p/bjdKZd0oFq5x` / `p/fcSjv7TBWWpt`
  - AI X 7桁: `p/AOll8d2WudH7` / `p/GKTTRK0sMhC4` / `p/Fyysb2Lzmafg` / `p/XcFB1Re3138v`
  - AI TikTok 7桁: `p/WUY1RNzVg2YP` / `p/0LYFd15t6LOV` / `p/Dx60Z1wULbUK` / `p/sGZfeKR5gIHj`
  - AI YouTube 7桁: `p/dDPPAyMxzWUX` / `p/FpMaLjUlD9oY` / `p/1M794M7I5Qzm` / `p/V6Yi7srMbp2E`
  - SNS X 7桁: `p/9ytudOvx2T31` / `p/GuMTqGD4HQvN`
  - SNS TikTok 7桁: `p/1qNpaYQ68Aml`
  - LINE広告_センサーズ 7桁: `p/iGcMpYHMpUQb`
- 一方で、以下の現役導線は 2026-03-09 の active queue 確認範囲では停止中LINE誤接続が見つからなかった
  - `スキルプラス Meta` は `スキルプラス`
  - `スキルプラス アフィリエイト` は `スキルプラス` または `スキルプラス@企画専用`
  - `スキルプラス購入後` は `スキルプラス`
  - `フリープラン` は `【スキルプラス】フリープラン`
  - `SNS Facebook 7桁` の active queue は `【みかみ】アドネス株式会社` または `【スキルプラス】フリープラン`
  - `秘密の部屋` は `【みかみ】アドネス株式会社`
- したがって、現在の問題の本体は `Mailchimp が古いURLを持っていること` ではなく、`Mailchimp が送っている先の UTAGE ページに、停止中 LIFF と稼働中 LIFF / short.io が同居していること` にある

### 構造上の重要ポイント

- AI と SNS はどちらも `オプトインtag 1つ -> main journey と 個別3日間 journey が並走` している
- active queue 基準で見ると、いま本当に送られているのは `7桁本線の後半メール` が中心で、内容は `フリープラン送客 / 企画誘導 / 個別誘導 / 本気コンサル再訴求` に寄っている
- LP差分は `訴求` と `15分ウェビナー遷移先` にあり、`オプトイン scenario / Mailchimp trigger tag` は共通化されている
- UTAGE では `div-archived` 扱いの個別 landing page に現在の LP から直接送っているケースがある。UTAGE の「アーカイブ」は「未使用」と同義ではない
- スキルプラスは `セミナー / 無料体験会 / 診断 / アフィリエイト / 9,800円販売` が別導線で併存しているため、「スキルプラスはこれが主線」と一本では言えない
- Lステップは `稼働中アカウント一覧` と `利用停止中アカウント一覧` を明確に分けて読む必要がある
- `@804mrsmd` は現役候補ではなく、停止済みアカウントへの誤接続として扱う
- 現役ページでは、`停止中 LIFF 直リンク` と `稼働中 LIFF / short.io` が同じページ内に混在しているケースがある。これは人が迷うだけでなく、運用上も事故りやすい
- 以後、LINEの接続先判定は `稼働中一覧に存在するか` を必須条件にする

### 補足

- Mailchimp の公式 API で `customer-journeys/journeys/{id}/steps`、`campaigns/{id}/content`、`reports/{id}/click-details` まで確認できる
- current を誤読しない基準は `journey_name` と `status` を見た後、`step_type = action-send_email`、`step status = active`、`queue_count > 0` まで落とすこと
- `last_started_at` だけでは current 判定しない。`journey が sending` でも、step が paused なら current メール扱いしない
- `copy` が付くメールでも queue が残っていれば current とみなす
- 2026-03-10 時点で、AI Facebook / SNS Facebook / AI X / AI YouTube の 7桁本線は、いずれも current step の本文・件名・送信実績・click report まで API で追える
- Journey 一覧 API は offset が効いていないように見え、古い Journey の全件列挙には別手段が必要
- Zapier については AI / 秘密の部屋の主要 Zap は既に確認済み。今回追加で追った SNS / スキルプラスは、UTAGE の scenario 名と Mailchimp の trigger tag まで確定しており、橋渡し構造自体は明確

---

## デザインファネル / 広告ファネル（現在不使用）

> **2026-03-06 確認**: デザインと広告の導線は現在使っていない。AIファネルをメインに集中する方針。

### デザインファネル（停止中）

- 大当たりCR: 22件（過去実績）
- canva/Coconala等のデザイン訴求
- CPA¥1,215（全CR最安）を記録
- 行き先LINE: スキルプラス系のLINEと推定（要確認）

### 広告ファネル（停止中）

- 大当たりCR: 8件（過去実績）
- 広告運用に興味がある層を集客
- 行き先LINE: 要確認

---

## ファネル × CR企画の接続

CR企画時は「どのファネルに誘導するCRか」を明確にする必要がある。

| ファネル | 行き先LINE | 主な訴求パターン | 大当たり件数 | 状態 |
|---------|-----------|---------------|-----------|------|
| **AI** | 【みかみ】アドネス株式会社 | A.危機感, B.変化, D.実用 | 158件 | **メイン稼働中** |
| SNS（みかみ） | 【みかみ】アドネス株式会社 | A.危機感, B.変化, E.急募 | 145件 | 稼働中 |
| スキルプラス | スキルプラス公式LINE | 確認中 | 7件 | 稼働中 |
| デザイン | 要確認 | D.実用 | 22件 | **停止中** |
| 広告 | 要確認 | 確認中 | 8件 | **停止中** |

---

## Lステップアカウント構成

> Lステップのマイページで管理している全アカウント。マーケティング + サポートで使用。

### よく使っているもの（マーケティング・導線関連）

| 分類 | アカウント | 用途 |
|------|----------|------|
| みかみ系 | 【みかみ】アドネス株式会社（メイン） | AI/SNSファネルのメイン導線LINE |
| みかみ系 | その他「みかみ」と書いてあるもの | みかみ導線の関連アカウント |
| スキルプラス系 | 「スキルプラス」 | スキルプラス導線のメインLINE |
| スキルプラス系 | 「スキルプラス@企画専用」 | スキルプラス導線の企画用 |
| フリープラン | 「フリープラン」と書いてあるもの | スキルプラスのフリープラン用。てるやさん担当（甲原の管轄外） |

### 見なくていいもの

| アカウント | 理由 |
|----------|------|
| コンドウハルキ | 以前「デザジュク」というJVで協業していた方。現在は関係なし |
| 日本リスキリング支援株式会社 | 関係なし |

---

## Lステップの詳細調査

Lステップの全アカウント・タグ管理・シナリオ配信の詳細は以下を参照:

→ **`Master/addness/lstep_accounts_analysis.md`**

---

## 未確認事項

1. AI 側で `みかみ@AI_個別専用` と `【みかみ】アドネス株式会社` がページごとに分かれている理由と、どちらが正本かの確定
2. SNS 側で `みかみ@個別専用` と `【みかみ】アドネス株式会社` がページごとに分かれている理由と、どちらが正本かの確定
3. LINE着地後の Lステップ 内で、どのタグ / シナリオ / 個別予約導線に入るか
4. short.io の JWT 復号による API 直取得
5. スキルプラス Meta の `@496sircr` サンクスページと `スキルプラス@企画専用` の webinar automation が、実運用でどこで接続しているか
6. SNS / スキルプラスの current Zap を Zapier 側で再度引き切ること
7. デザイン / 広告ファネルの行き先LINE（現状は優先度低）
