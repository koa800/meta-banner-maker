# addness レイヤー

最終更新: 2026-03-17

## 情報ラベル

- 所有元: internal
- 開示レベル: task-limited
- 承認必須: conditional
- 共有先: 僕 / 上司 / 並列 / 直下

`Master/addness/` は、Addness の current な導線運用を揃えるための正本です。
ここでは `構造理解` ではなく、`迷わず実装できるか` を基準に扱います。

## 情報ラベルの既定値

- `構造 / UI操作 / 運用手順` 系
  - 例: `utage_structure.md`, `funnel_structure.md`, `ui_operations.md`, `zapier_structure.md`
  - 所有元: `internal`
  - 開示レベル: `task-limited`
  - 承認必須: `conditional`
  - 共有先: `僕 / 上司 / 並列 / 直下`
- `ダッシュボード / ゴール / 実行タスク / 分析` 系
  - 例: `goal-tree.md`, `actionable-tasks.md`, `meta_ads_cr_dashboard.md`, `market_trends.md`
  - 所有元: `internal`
  - 開示レベル: `role-limited`
  - 承認必須: `conditional`
  - 共有先: `僕 / 上司 / 並列`

ファイルに個別ラベルがある場合は、上の既定値より個別ラベルを優先する。

## 目的

- `導線ツール` を厳しい 10 点基準まで引き上げる
- 10 点の定義は `役割 / ゴール / 必要変数 / ワークフロー / NG / 正誤判断` を持ち、exact な UI 手順で迷わず実装できる状態

## 最新の厳しめ採点

- Lステップ: `9.8 / 10`
- UTAGE: `9.7 / 10`
- Mailchimp: `9.4 / 10`
- short.io: `9.5 / 10`
- Zapier: `9.1 / 10`

## live 開始前チェック

- まず `python3 System/scripts/funnel_tool_live_readiness.py` を実行する
- `cdp.alive=false` なら、先に `python3 System/scripts/chrome_cdp_bootstrap.py` を実行して 9224 を起こす
- `cdp.alive=false` なら、UTAGE と Zapier の browser exact 化には入らない
- `lstep.auth_alive=true` でも十分ではない。`lstep.account_name` が intended な公式LINE account かを必ず確認する
- 2026-03-16 の current では、`auth_alive=true` でも `account_name=koa800sea` を返した。つまり `認証は生きているが対象 account 文脈はズレている` ケースがある
- Lステップは `auth_alive=true` かつ `account_name が intended account` の時だけ、API / cookie 経由の exact 作業に入る
- `mailchimp.api_alive=true` なら、Journey / Campaign / report の API 読解は進められる
- `shortio.api_alive=true` なら、short.io の作成 / 編集 / 統計 / 台帳同期は進められる

## 最新 readiness snapshot

- CDP: `true`
- Lステップ auth: `true`
- Lステップ account: `koa800sea`
- Mailchimp API: `true`
- short.io API: `true`
- UTAGE live browser: `true`
- Zapier live browser: `true`

## 実際に触って確認できている範囲

### Lステップ

- `テンプレート -> フレックスメッセージ`
  - `作成 -> テスト送信 -> 削除`
- `自動応答`
  - `作成 -> 一覧確認 -> 削除`
- `回答フォーム`
  - `作成 -> テスト送信 -> 削除`
- `テスト送信先`
  - 常に `甲原 海人`
- 実案件
  - `スキルプラス公式TV` 概要欄用に
    - `（スキルプラス公式TV）YouTube _スキルプラス_直リストイン`
    - `https://skill.addness.co.jp/sp013`
    を current 本番として作成済み
  - route では
    - route tag
    - `【新規】...`
    - 必須 tag
    - `友だち情報 [新規流入] / [最終流入]`
    - `メインリッチメニュー（企画専用LINE遷移）`
    - `無料体験会訴求シナリオ`
    を設定
  - 既知の差分
    - 既存 family にある `友だち情報 [新規流入日] = action_date` は current API で 422 になり、今回の route には未設定
  - 共有
    - `【アドネス】社外メディア広報` に `@しおり` 付きで共有済み
  - 今回の学習
    - 流入経路は `既存 family に何があるか` から選ばない
    - 先に `流入前オファー` と `流入時の状態` を固定し、その後で `開始シナリオ` を選ぶ
    - Lステップ は browser 上でログイン済みに見えても API セッションが切れていることがある
    - 既存 route を API でなぞっても、そのまま通らない action があるので `row の右側説明` と `実際の保存結果` の両方を確認する
    - 導線作成の実務順は `Lステップ流入経路 -> short.io -> URL管理シート -> 共有` が最もズレにくい
    - LINE の共有で `メンション` が必要な時は `@名前` の文字列だけでは不十分。`group_id + user_id + 本物メンション送信` が必要
    - 秘書 bot は current で `/notify/mention` と `/api/group-members` を持つので、共有前に対象グループの member 解決が可能

### UTAGE

- representative な
  - `ページ`
  - `商品管理`
  - `商品詳細管理`
  - `購入後アクション`
  - `バンドルコース`
  - `会員サイト`
  - `動画管理`
  - `メディア管理`
  の読解
- runtime から code 領域の値取得
  - `商品管理`
    - exploratory product `ZZ_TEST_20260316_UTAGE_product_exact` の `create -> rollback`
  - row action:
    - `開く`
    - `編集`
    - `コピー`
    - `アーカイブ(非表示化)`
    - `削除`
  - `開く = 商品詳細管理`
    - route: `/product/{product_id}/detail`
  - `商品詳細管理 > 追加`
    - route: `/product/{product_id}/detail/create`
    - live で確認した主要ラベル:
      - `名称`
      - `支払方法`
      - `決済代行会社`
      - `決済連携設定`
      - `支払回数`
      - `金額`
      - `登録するシナリオ`
      - `実行するアクション`
      - `開放するバンドルコース`
    - live で確認した主要 option:
      - `支払方法`
        - `クレジットカード払い`
        - `銀行振込`
      - `決済代行会社`
        - `Stripe`
        - `UnivaPay`
        - `AQUAGATES`
        - `テレコムクレジット`
        - `FirstPayment`
      - `支払回数`
        - `一回払い`
        - `複数回払い・分割払い`
        - `継続課金`
      - `登録するシナリオ`
        - current の `ユーザー登録` 系 scenario が大量に並ぶ
      - `実行するアクション`
        - current の `バックエンド` 系
        - `講義保管庫解放アクション` 系が並ぶ
      - `開放するバンドルコース`
        - current の `スキルプラス講義保管庫全開放`
        - `PRM JV用`
        - `プライム会員限定`
        などが並ぶ
    - exploratory detail
      - `ZZ_TEST_20260316_223638_UTAGE_detail_create_probe_detail`
      - 最小値で `保存成功`
      - detail 一覧に `1件追加` を確認
      - cleanup は `UTAGE_detail_create_probe` pattern で `0件` を確認
  - `アクション設定 > 追加`
    - route: `/action/create`
    - live で確認した主要ラベル:
      - `管理用名称`
      - `種類`
      - `URL`
      - `name`
      - `value`
      - `バンドルコース 必須`
      - `商品 必須`
      - `ファネル 必須`
      - `Googleアカウント 必須`
      - `スプレッドシートURL 必須`
      - `シート 必須`
    - exploratory action
      - `ZZ_TEST_20260316_225035_UTAGE_action_probe`
      - `種類 = webhook`
      - `URL = https://example.com/utage-action-probe`
      - `name = source`
      - `value = utage_action_probe`
      - 最小値で `保存成功`
      - action 一覧に `1件追加` を確認
      - row dropdown 内の `form-delete` で `1件削除` を確認

### Mailchimp

- regular `Campaign`
  - draft 作成 / 削除
- `Journey`
  - `Build from scratch -> Name flow -> Audience -> trigger`
  - `python3 System/scripts/mailchimp_journey_snapshot.py --list-current --count 20`
    で current email step matrix を再取得できる
- `report`
  - `Recipients -> Open rate -> Click rate -> click-details -> downstream`
- `saved segment 1件`
  - create / delete
- `tag 1件`
  - safe exploratory member で `add -> rollback`
- `tag-search`
  - 一覧読解
- `search-members`
  - safe exploratory member 探索
- `journey snapshot`
  - current matrix 読解

### short.io

- テスト短縮URLの作成 / resolve / 編集 / resolve / 削除
- API確認 / URL管理シート同期

### Zapier

- representative relay の editor / step 読解
- `Create Zap -> assets 一覧 row action Delete -> cleanup`
- `Webhooks by Zapier / Catch Hook -> Mailchimp / Add/Update Subscriber`
  family の exact 読解
- live probe:
  - `Create Zap`
  - `Trigger > Webhooks by Zapier > Catch Hook`
  - `Action > Mailchimp > Add/Update Subscriber`
  - `assets 一覧 row action Delete -> Delete`
  まで exploratory に確認
- current family snapshot
  - `WebHookCLIAPI@1.1.1:hook_v2 -> MailchimpCLIAPI@1.15.1:memberCreate`
    - `21本`
    - current の主 family
  - `GoogleSheetsV2CLIAPI@2.9.1:updated_row_notify_hook -> WebHookCLIAPI@1.1.1:post`
    - `3本`
    - SMS relay family
  - `WebHookCLIAPI@1.0.29:hook_v2 -> MailchimpCLIAPI@1.15.1:memberCreate`
    - `1本`
    - old webhook family

## live coverage matrix

| system | component | live 状態 | 次の最小単位 |
|---|---|---|---|
| Lステップ | テンプレート > フレックスメッセージ | 作成 / テスト送信 / 削除 済み | high-quality template 分解を増やす |
| Lステップ | 自動応答 | 作成 / 一覧確認 / 削除 済み | representative を増やす |
| Lステップ | 回答フォーム | 作成 / テスト送信 / 削除 済み | 2問以上の pattern |
| Lステップ | アクション管理 | 読解中心 | 最小複合 1本 |
| Lステップ | リッチメニュー | 読解中心 | 2ボタン 1本 |
| UTAGE | ページ | representative 読解済み、`ファネル -> 追加 -> 空白のファネル -> 詳細 -> このファネルを追加する -> 一覧確認 -> row delete` 済み、row action は `slug route` / delete は `numeric id form` と確認済み | 1変更 -> rollback |
| UTAGE | 登録経路 | 読解中心 | 1追加 -> rollback |
| UTAGE | 商品管理 / 商品詳細管理 / 購入後アクション | product create / rollback 1本済み、detail create/save/cleanup 1本済み、action create/save/delete 1本済み | representative を増やす |
| UTAGE | 会員サイト | representative 読解済み | 1変更 -> rollback |
| UTAGE | 動画管理 / メディア管理 | representative 読解済み | small change -> smoke |
| Mailchimp | Campaign | draft create / delete 済み | representative を増やす |
| Mailchimp | Journey | trigger 入口まで済み | 1本 create -> Send Test Emails -> cleanup |
| Mailchimp | tag / saved segment | saved segment の create / delete、tag-search、search-members、safe exploratory member で tag 1件 add -> rollback 済み | UI 側の tag 1件 create -> rollback |  
| Mailchimp | report | representative 読解済み | actual case を増やす |
| short.io | short link / create / resolve / update / delete / stats / sheet sync | live 実施済み | 実案件 end-to-end を増やす |
| Zapier | representative relay 読解 | editor / step 読解済み、`Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` まで exploratory 済み | 1本 create -> test -> delete |

### current live blocker

- Mailchimp
  - `python3 System/scripts/mailchimp_journey_create_delete_probe.py` は current で `LOGIN_NEEDS_TFA`
  - つまり browser 側の exact 化は、2段階認証を通した session がある時だけ進める
- Zapier
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action` は current で `Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` まで通った
  - exploratory draft の cleanup は `python3 System/scripts/zapier_cleanup_untitled.py` で `after_count=0` まで戻せる
  - つまり current の残差は `Publish 前提の smoke` と representative family の追加で、create/cleanup 自体はかなり exact になった

## いま重要な残差

### Lステップ

- `回答フォーム / アクション管理 / リッチメニュー` の複雑パターンを `作成 -> テスト -> rollback / cleanup` まで同じ精度で回す

### UTAGE

- `ページ -> 商品管理 -> 商品詳細管理 -> 購入後アクション -> バンドルコース` を新規案件目線で live create / rollback まで further exact 化
- `商品管理 / 商品詳細管理 / 購入後アクション` は最小 create/save/delete が 1 本ずつ済んだので、残差は `ページ / 登録経路 / 会員サイト / 動画管理` の live save 本数
- `会員サイト` と `動画管理 / メディア管理` の実変更本数を増やす

### Mailchimp

- `Journey` を `trigger -> email step -> Send Test Emails -> cleanup` まで無迷いで再現
- `tag / saved segment` は API helper 側の `create/add -> rollback -> member_count/tags_count 確認` まで exact に回した
- 残差は `UI 側の tag 1件 create -> rollback`
- `report` の漏斗診断 actual case を増やす

### short.io

- `新規作成 / 差し替え / 既存流用` の判断を、実案件で `台帳更新 -> click / 遷移先確認` まで end-to-end でさらに回す

### Zapier

- `Create Zap -> Test -> Publish or Delete Zap` の実作成本数を増やす
- `Create Zap` を開いただけでは assets 一覧に `Untitled Zap` が出ない current 挙動を確認済み
- `Trigger > Webhooks by Zapier > Catch Hook` まで選ぶと assets 一覧に `Untitled Zap` が persisted するところまで確認済み
- `Action > Mailchimp > Add/Update Subscriber` まで選ぶと `Test` stage まで進めるところも確認済み
- persisted 済み draft は `assets 一覧 row action Delete -> Delete` か `python3 System/scripts/zapier_cleanup_untitled.py` で `0件` まで cleanup 済み
- つまり残差は `downstream smoke` と representative family の追加
- dominant family は `Webhook -> Mailchimp Add/Update Subscriber`
  なので、最初の live exact はこの family を優先する

## 10点までの最短ルート

- Lステップ
  - `回答フォーム 2問`
  - `アクション管理 1複合`
  - `リッチメニュー 2ボタン`
  を live で `作成 -> テスト -> rollback / cleanup`
- UTAGE
  - `ページ 1変更`
  - `商品管理 / 商品詳細管理 / 購入後アクション 1本`
  - `会員サイト 1変更`
  を live で `保存 -> downstream 確認 -> rollback`
- Mailchimp
  - `Journey 1本`
  - `tag 1件`
  を live で `作成 -> Send Test Emails or downstream smoke -> cleanup`
- Zapier
  - `Catch Hook -> Mailchimp Add/Update Subscriber`
  の最小 relay を `Create Zap -> Test -> Delete Zap`
- short.io
  - 実案件 1 本を `判断 -> 作成 or 差し替え -> URL管理シート更新 -> click / 統計確認` まで通す

## exact 監査の状態

- `python3 System/scripts/skill_exact_audit.py /Users/koa800/Desktop/cursor/Skills/2_導線` は `OK: exact audit passed`
- つまり current の残差は skill 構造不足ではなく、live 実作成 / test / rollback の本数不足

## live 準備 helper

- `python3 System/scripts/chrome_cdp_bootstrap.py`
  - 9224 の Chrome CDP が死んでいる時に、live 作業用の Chrome を起こす
  - `live browser ready=false` の時は、まずこの helper を試してから login helper に進む
- `python3 System/scripts/utage_detail_form_snapshot.py`
  - `商品詳細管理 > 追加` の form と option を live で JSON 化する
- `python3 System/scripts/utage_action_list_snapshot.py`
  - `アクション設定` 一覧の `追加` 導線と representative row を live で取得する
- `python3 System/scripts/utage_action_form_snapshot.py`
  - `アクション設定 > 追加` の form と option を live で JSON 化する
- `python3 System/scripts/utage_action_create_delete_probe.py`
  - `アクション設定 > 追加` を最小値で `保存 -> 一覧確認 -> form-delete cleanup` まで通す
- `python3 System/scripts/utage_cleanup_test_products.py`
  - `UTAGE_detail_probe` 系の exploratory 商品を cleanup する

## 承認なしで進める範囲

- skill と正本の同期
- current / legacy の判断辞書の追加
- representative pattern の追加
- `10秒判断`
- `30秒レビュー`
- `構築精度だけを見る時のチェック`
- `最小 rollback`
- `変更後の最小 smoke`

## 手動ログインが必要な時だけ止まる条件

- Lステップ / UTAGE / Mailchimp の session が切れて `LOGIN_NEEDS_MANUAL_CONFIRM` になる
- live change が current 本線へ直接影響する
- exploratory draft や test object を cleanup できない可能性がある

## 参照先

- Lステップ: [Master/knowledge/lstep_structure.md](/Users/koa800/Desktop/cursor/Master/knowledge/lstep_structure.md)
- UTAGE: [Master/addness/utage_structure.md](/Users/koa800/Desktop/cursor/Master/addness/utage_structure.md)
- Mailchimp: [Project/3_業務自動化/メールマーケティング自動化.md](/Users/koa800/Desktop/cursor/Project/3_業務自動化/メールマーケティング自動化.md)
- Zapier: [Master/addness/zapier_structure.md](/Users/koa800/Desktop/cursor/Master/addness/zapier_structure.md)
