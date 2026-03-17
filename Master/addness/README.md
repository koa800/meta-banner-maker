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
- UTAGE: `9.9 / 10`
- Mailchimp: `9.4 / 10`
- short.io: `9.6 / 10`
- Zapier: `9.5 / 10`

## live 開始前チェック

- まず `python3 System/scripts/funnel_tool_live_readiness.py` を実行する
- `cdp.alive=false` なら、先に `python3 System/scripts/chrome_cdp_bootstrap.py` を実行して 9224 を起こす
- `cdp.alive=false` なら、UTAGE と Zapier の browser exact 化には入らない
- `lstep.auth_alive=true` でも十分ではない。`lstep.account_name` が intended な公式LINE account かを必ず確認する
- 2026-03-16 の current では、`auth_alive=true` でも `account_name=koa800sea` を返した。つまり `認証は生きているが対象 account 文脈はズレている` ケースがある
- Lステップは `auth_alive=true` かつ `account_name が intended account` の時だけ、API / cookie 経由の exact 作業に入る
- `mailchimp.api_alive=true` なら、Journey / Campaign / report の API 読解は進められる
- `shortio.api_alive=true` なら、short.io の作成 / 編集 / 統計 / 台帳同期は進められる
- 2026-03-17 の current では、`sp013` で `作成 -> URL管理シート記録 -> 実 click -> link-stats` まで end-to-end を確認できた
- `link-stats` では `humanClicks=1`、`2026-03-16` に 1 click が入っていることを確認済み
- `Playwright.connect_over_cdp` が timeout する回は、`python3 System/scripts/chrome_raw_cdp.py` を使う raw fallback を先に試す
- `python3 System/scripts/zapier_family_snapshot.py --limit 5` も raw fallback で再取得できる
  - current では `Webhook -> Mailchimp Add/Update Subscriber` family と `Google Sheets -> webhook post` family を再確認できた
  - `Untitled Zap` のように `steps=[]` で `signature=\"\"` の row は draft 候補として扱い、family の意味読みから外す
  - current の Zapier assets には既存の `Untitled Zap` draft が複数残っている
  - exploratory relay の cleanup を `Untitled Zap` 一括削除に寄せるのは危険
  - 新規 relay の live probe では、作成直後に unique 名へ変えるか、`last modified` と `href` で対象 draft を特定してから削除する
  - current の `zapier_cleanup_untitled.py` は `--edit-path` と `--name` 指定を受けられる
  - current の `zapier_create_delete_probe.py` は `Assets > Zaps > 甲原 > Create Zap` を主入口に使い、`before/after` の diff で新規 draft の `edit_path` を特定してその row だけ cleanup する
  - exact には、folder page を開いてから `Create Zap` を押して builder に入る
  - 2026-03-17 の current では `Untitled Zap / Draft` の rename も live で再確認した
    - 左上 title button は exact text 一致ではなく、`Untitled Zap` を含む button として拾う必要がある
    - rename 後は assets 一覧の row 名へ即反映される
    - 一方で `Zap details > Folder = 甲原` は current の row `Location` に即反映されなかった
    - したがって `Folder = 甲原` は Addness の運用ルールとして維持しつつ、current UI では exact-confirmed ではない
  - 2026-03-17 の current では `甲原` フォルダ直下 `Create Zap` からの新規 draft 作成も live で再確認した
    - folder URL: `https://zapier.com/app/assets/zaps/folders/019cdd75-b612-ec46-7e5b-bd8a9015a667`
    - `Create Zap` -> `Webhooks by Zapier` -> `Catch Hook` まで進めると assets 一覧に新規 draft が persisted する
    - assets 一覧 row の `Location = 甲原` を確認できた
    - つまり current では `Zap details > Folder` の即時反映は不安定でも、`甲原` フォルダ画面から作れば `Location = 甲原` を exact に満たせる
- 2026-03-17 の current では、UTAGE と Zapier は raw fallback で `ALREADY_LOGGED_IN_RAW` まで確認できた
- UTAGE は raw fallback で
  - `商品管理`
  - `アクション設定`
  - `登録経路`
  の `create -> delete` まで再現できた
- 2026-03-17 の current では `登録経路 > 追加` も live で `create -> delete` を再確認した
  - `管理名称` だけでは保存できない
  - 少なくとも `ファネルステップ` の選択が必要
  - temporary funnel cleanup まで完了
- 2026-03-17 の current では `ページ > 追加` も raw probe で `create -> delete` を再確認した
  - `名称` を正しく入れないと `名称は必ず指定してください。` で止まる
  - `ページ一覧` の actual URL は created row action から取る
  - `row_link` の page id と `編集` route の page id が一致しないことがある
- 2026-03-17 の current では `ページ一覧 > 編集 > ページ設定 > 基本情報 > #save-basic` も live で再確認した
  - `管理名称` を 1変更
  - 値の変更確認
  - 元の値に rollback
  - temporary funnel cleanup まで完了
- 2026-03-17 の current では `バンドルコース一覧 > 追加` も raw probe で `create -> delete` を再確認した
  - 必須は `バンドルコース名` と `追加するコース` の最小選択
  - `before_count = 0` `after_create_count = 1` `after_delete_count = 0`
- 2026-03-17 の current では `コース一覧 > 追加` も raw probe で `create -> delete` を再確認した
  - 必須は `コース名` `管理名称` `リンク先URL` の最小入力
  - `before_count = 0` `after_create_count = 1` `after_delete_count = 0`
- 2026-03-17 の current では `レッスン一覧 > 追加` も raw probe で `create -> delete` を再確認した
  - 必須は `グループ` `レッスン名` `コンテンツ` の最小入力
  - save 後に一覧へ `1件` 出ることを確認し、その後 row delete で `0件` に戻るところまで確認済み
- 2026-03-17 の current では `レッスン一覧 > 編集` も live で再確認した
  - `レッスン名` を 1変更
  - 値の変更確認
  - 元の値に rollback
  - row delete まで完了
  - `コンテンツ` は hidden textarea なので、Playwright の `fill()` ではなく JS で値を入れる必要がある
- 2026-03-17 の current では `コース一覧 > コース基本情報編集 > 管理名称 > 保存` も live で再確認した
  - `管理名称` を 1変更
  - 値の変更確認
  - 元の値に rollback
  - row delete まで完了
- 2026-03-17 の current では `商品詳細管理 > 追加` で `実行するアクション / 開放するバンドルコース` の chain save も live で再確認した
  - probe: `python3 System/scripts/utage_detail_chain_probe.py`
  - exploratory product 配下で detail を 1件追加
  - `実行するアクション = 【スタンダード】事業構築コース　講義保管庫解放アクション`
  - `開放するバンドルコース = スキルプラス講義保管庫全開放`
  - save 後に detail row が `1件` 出ることを確認
  - `detail edit` を再度開いて selected value を再読込
    - `action_id = 1127`
    - `bundle_id = 8403`
  - product row delete で cleanup 済み
- Mailchimp は raw fallback で `https://us5.admin.mailchimp.com/login/tfa-post` の verify 画面到達まで確認できた
- helper は hanging せず `LOGIN_NEEDS_TFA` で返るところまでは安定
- `Resend code` 後に `mailchimp_tfa_code_helper.py --wait` を流した current 実行では `found=false`
  - つまり今の `group-log API` は Mailchimp 認証コードの today メッセージを拾えていない
  - current blocker は `コード取得経路` であって、Mailchimp の login 導線そのものではない
- 2026-03-17 の current では browser 上で `Success! Your SMS verification code is on its way! Check your phone to catch it!` まで確認した
  - それでも helper は `found=false` だった
  - つまり current blocker は `SMS送信` ではなく `today の LINE group-log 取得`
- その後の再確認では `api/group-log?date=2026-03-17` は `groups=4` を返した
- つまり current blocker は `today の group-log 全体が空` ではなく、
  - today の group-log 自体は取れている
  - ただし `Mailchimp認証` の `group_id = Ce2900a5b8c1efb939b3778262f1a9808` が today payload に現れていない
  こと
- 2026-03-17 の current payload では、today の `groups` は 4 件とも `group_name=""`
  - `C2978001e19bfd7ea9608a586f372173c`
  - `C330ef524daef13701ef3bd1f8127207f`
  - `C5d39c4fe007af6773f770eb991b77cac`
  - `Ce2cd4420d4b7582a89c00a7294256f95`
- 本文検索では `Mailchimp` / `認証コード` / `6桁コード` に一致する today message は取れなかった
- つまり current blocker は helper の優先順ではなく、`today の group-log そのものに Mailchimp 認証 message が載っていない` こと
- `mailchimp_tfa_code_helper.py` は current で
  - `Mailchimp認証` グループ優先
  - known `group_id = Ce2900a5b8c1efb939b3778262f1a9808` も優先
  - 複数の code pattern 許容
  - warning suppress
  に更新済み
  - `group_id -> group_name` の逆引き fallback も追加済み
  - `python3 System/scripts/mailchimp_tfa_code_helper.py --max-days 7 --max-age-minutes 10080`
    で `2026-03-16T23:46:49 / code=506232 / group_id=Ce2900a5b8c1efb939b3778262f1a9808 / group_name=MailChimp認証`
    を再取得できた
  - current の `group-log API` では、この group が `group_name=""` で返る回がある
  - 2026-03-16 の履歴ログでは、`group_name=""` でも `group_id = Ce2900a5b8c1efb939b3778262f1a9808` 優先で code を再取得できた
  - つまり helper 自体は `group_name 空文字` に耐えられる
- それでも `found=false` の時は、helper ではなく server 側の group-log 取得経路を疑う
- `mailchimp_login_helper.py` の Playwright 側 TFA は current で `wait_for_mailchimp_code(...)` を使う
- したがって current の残差は helper の参照漏れではなく、本当に `today の LINE group-log 取得` 側
- Mailchimp API では `saved segment create -> delete` と `ensure-member -> add-tag -> remove-tag -> delete-permanent` まで live exact 済み
- `ensure-member` 直後の `add-tag` は、一時的に `404` になる回がある
  - current では `member` で見えてから再試行すると成功した
- `members/{hash}` への `DELETE` は current で `405`
  - cleanup は `POST /actions/delete-permanent` が通る

## 最新 readiness snapshot

- CDP: `true`
- Lステップ auth: `false`
- Lステップ account: `null`
- Lステップ next_action:
  - `cookie source が全滅で、login page は reCAPTCHA enabled=true。 current session の再取得には browser login が必要。`
- Mailchimp API: `true`
- short.io API: `true`
- UTAGE live browser: `true`
- Zapier live browser: `true`
- Mailchimp browser:
  - `2-factor authentication | Mailchimp`
  - `login/tfa-post` まで raw fallback で到達
  - helper は `LOGIN_NEEDS_TFA` で clean return

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
    - ただし 2026-03-17 時点では Render 側の `/notify/mention` と `/api/group-members` が `404`。コード実装と push は済みだが、本物メンション送信は deploy 反映待ち
  - `アクション管理` の current exact 挙動
    - `新しいアクション` は別ページ遷移ではなく side drawer
    - `タグ操作` はタグ名の直打ちでは保存できない
    - current UI では `タグ選択` を通らないと
      - `登録に失敗しました`
      - `1.[タグ編集]タグは必須です。`
      で止まる
    - unsaved drawer を閉じる時は
      - `保存されていない変更があります。本当に閉じますか？`
      - `キャンセル / 閉じる`
      の confirm が出る

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
- current browser helper の補足
  - `utage_login_helper.py` は `Playwright.connect_over_cdp` timeout 時、`chrome_raw_cdp.py` を使う raw fallback に切り替える
  - 2026-03-17 の current では `ALREADY_LOGGED_IN_RAW / https://school.addness.co.jp/funnel` を確認
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
  - 2026-03-17 live probe の再確認
    - `python3 System/scripts/utage_product_create_delete_probe.py`
      - `before_count = 0`
      - `after_create_count = 1`
      - `after_delete_count = 0`
      - `deleted = true`
    - `python3 System/scripts/utage_detail_create_delete_probe.py`
      - exploratory 商品を `create`
      - `商品詳細管理 > 追加`
      - `保存成功`
      - detail 一覧 `1件追加`
      - exploratory 商品 cleanup 後 `0件`
    - `python3 System/scripts/utage_action_create_delete_probe.py`
      - `種類 = webhook`
      - 最小値で `保存成功`
      - action 一覧 `1件追加`
      - row dropdown 内の `削除` で cleanup
  - `python3 System/scripts/utage_funnel_create_delete_probe.py`
    - `before_count = 258`
    - `after_create_count = 259`
    - `created_id = 232420`
    - `after_delete_count = 258`
    - `deleted = true`
  - `python3 System/scripts/utage_page_create_delete_probe.py`
    - temporary funnel を `create`
    - row action の `ページ一覧` から actual slug を取得
    - `追加 -> 名称 -> 保存`
    - page row 出現を確認
    - temporary funnel `delete` で rollback
    - current 実績
      - `page_list_url = /funnel/4eAriUd6li3Z/page`
      - `create_url = /funnel/4eAriUd6li3Z/create`
      - `保存後 current_url = /funnel/4eAriUd6li3Z/page/ZKxXY8aywnwm`
      - `row_link = /page/ZKxXY8aywnwm#list-ZKxXY8aywnwm`
      - `edit_link = /page/0opi5kesOlJq/edit`
      - `deleted = true`
    - 学習
      - create template の slug と created funnel の slug は一致しない
      - actual な `ページ一覧` URL は created row action から取る
      - current では `row_link` の page id と `編集` route の page id が一致しないことがある
  - helper の current 挙動
    - `python3 System/scripts/utage_login_helper.py --target https://school.addness.co.jp/product`
      - `LOGIN_SUCCESS`
    - `python3 System/scripts/utage_login_helper.py --target https://school.addness.co.jp/action`
      - `ALREADY_LOGGED_IN`
    - つまり probe 側は `一覧 URL へ自動復帰 -> exploratory create/delete` を self-heal しながら回せる

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
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action`
    - `Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap`
    - まで current UI で完了
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action --action-app webhook-post`
    - `Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Webhooks by Zapier > POST -> Test -> Delete Zap`
    - まで current UI で完了
    - つまり current では external account 不要の 1 action relay も live exact に通る
- `python3 System/scripts/zapier_create_delete_probe.py --with-action --with-second-action`
  - cleanup は成功
  - `trigger_app = Webhooks by Zapier`
  - `trigger_event = Catch Hook`
  - `action_app = Mailchimp`
  - `action_event = Add/Update Subscriber`
  - `second_action_app = Webhooks by Zapier`
  - `second_action_event = POST`
  - `second_action_selected = true`
  - `post_second_action_stage = Test`
  - つまり `trigger 1 + action 2` も live exact に通った
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action --with-second-action --action-app webhook-post --second-action-app mailchimp`
    でも live exact に通った
    - `trigger_app = Webhooks by Zapier`
    - `trigger_event = Catch Hook`
    - `action_app = Webhooks by Zapier`
    - `action_event = POST`
    - `second_action_app = Mailchimp`
    - `second_action_event = Add/Update Subscriber`
    - `post_second_action_stage = Test`
    - `deleted = true`
  - `python3 System/scripts/zapier_second_action_probe.py`
    - first action = `Webhooks by Zapier -> POST`
    - before:
      - URL = `.../draft/.../setup`
      - step node = `1. Catch Hook / 2. POST`
      - body marker = `Action / Test / Publish`
    - second action 入口を開くと URL が `.../setup -> .../fields`
    - after:
      - step node は `1. Catch Hook / 2. POST` のまま
      - `Add a step` は visible marker に出ていない
    - つまり current は `2つ目の action picker` ではなく `既存 action の fields` を再度開く回がある
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
| UTAGE | 登録経路 | create -> delete 再確認済み、`管理名称` だけでは保存できず `ファネルステップ` 選択が必要と確認済み | 計測確認の representative を増やす |
| UTAGE | 商品管理 / 商品詳細管理 / 購入後アクション | product create / rollback 再確認済み、detail create/save/cleanup 再確認済み、action create/save/delete 再確認済み | representative を増やす |
| UTAGE | 会員サイト | representative 読解済み | 1変更 -> rollback |
| UTAGE | 動画管理 / メディア管理 | representative 読解済み | small change -> smoke |
| Mailchimp | Campaign | draft create / delete 済み | representative を増やす |
| Mailchimp | Journey | trigger 入口まで済み | 1本 create -> Send Test Emails -> cleanup |
| Mailchimp | tag / saved segment | saved segment の create / delete、tag-search、search-members、safe exploratory member で tag 1件 add -> rollback 済み | UI 側の tag 1件 create -> rollback |  
| Mailchimp | report | representative 読解済み | actual case を増やす |
| short.io | short link / create / resolve / update / delete / stats / sheet sync | live 実施済み | 実案件 end-to-end を増やす |
| Zapier | representative relay 読解 | editor / step 読解済み、`Assets > Zaps > 甲原 > Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` と `Assets > Zaps > 甲原 > Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Webhooks by Zapier > POST -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` まで live 完了、cleanup も確認済み | representative family を増やす |

### current live blocker

- Mailchimp
  - `python3 System/scripts/mailchimp_journey_create_delete_probe.py` は current で `ensure_login(AUTOMATIONS_URL)` を先に実行する
  - それでも current は `LOGIN_NEEDS_TFA` で止まることがある
  - つまり browser 側の exact 化は、2段階認証を通した session がある時だけ進める
- Zapier
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action` は current で `Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` まで通った
  - exploratory draft の cleanup は `python3 System/scripts/zapier_cleanup_untitled.py` で `after_count=0` まで戻せる
  - `zapier_create_delete_probe.py` は current で raw fallback を持つ
  - 2026-03-17 の current では raw fallback で `step-node` の親要素を押す必要があることまで特定した
  - この修正で `Search apps` input が visible になるところまでは raw で再現できた
  - 一方で persisted draft の判定は timing と assets 一覧文脈の影響を受ける回があり、raw fallback だけでは毎回 `Untitled Zap` row を拾い切れない
  - つまり Zapier の create probe は current では `Playwright.connect_over_cdp が生きている回` を優先し、raw fallback は補助扱いにする
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action --with-second-action` は cleanup まで通る
    - `second_action_app = Webhooks by Zapier`
    - `second_action_event = POST`
    - `post_second_action_stage = Test`
  - `python3 System/scripts/zapier_create_delete_probe.py --with-action --with-second-action --action-app webhook-post --second-action-app mailchimp`
    も cleanup まで通る
    - `second_action_app = Mailchimp`
    - `second_action_event = Add/Update Subscriber`
    - `post_second_action_stage = Test`
  - first action 後の current builder には
    - `Choose an event`
    - `Select`
    - `Add account to continue`
    が visible
- 2026-03-17 の `zapier_second_action_probe.py` では、second action 入口を開くと `.../fields` に戻る回を確認した
- current の実 UI では、`Add a step` は visible text ではなく `aria-label=\"Add step\"` の button として出る
- `zapier_create_delete_probe.py` はこの selector を拾うよう更新済み
- つまり second action の主 blocker は解消済み
- 残差は representative family を増やすこと
  - current owner 表示は `【世捨人東大生】 ぜんT (Personal)`
  - つまり current の残差は representative family の追加で、1 action / 2 action の create/cleanup 自体はかなり exact になった

## いま重要な残差

### Lステップ

- `回答フォーム / アクション管理 / リッチメニュー` の複雑パターンを `作成 -> テスト -> rollback / cleanup` まで同じ精度で回す

### UTAGE

- `ページ -> 商品管理 -> 商品詳細管理 -> 購入後アクション -> バンドルコース` を新規案件目線で live create / rollback まで further exact 化
  - `商品管理 / 商品詳細管理 / 購入後アクション / 登録経路` は最小 create/save/delete を再確認済みなので、残差は `ページ / 会員サイト / 動画管理` の live save 本数
  - 2026-03-17 の raw probe では
  - `商品管理`: `before 0 -> after_create 1 -> after_delete 0`
  - `アクション設定`: `before 0 -> after_create 1 -> after_delete 0`
  を current browser で再確認済み
  - `商品詳細管理 > 追加` も raw fallback で再確認済み
    - `before_product_count = 0`
    - `after_product_count = 1`
    - `detail_row_count = 1`
    - `save_result.error_texts = []`
    - save 後 URL は `.../detail` 一覧へ戻る
    - temp product cleanup まで完了
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
- `Create Zap -> Trigger > Webhooks by Zapier > Catch Hook -> Action > Mailchimp > Add/Update Subscriber -> Test -> Delete Zap` の 1 action relay は live 完了
- current browser helper の補足
  - `zapier_login_helper.py` は `Playwright.connect_over_cdp` timeout 時、`chrome_raw_cdp.py` を使う raw fallback に切り替える
  - 2026-03-17 の current では `ALREADY_LOGGED_IN_RAW / https://zapier.com/app/assets/zaps` を確認
- つまり残差は `trigger 1 + action 2` と representative family の追加
- dominant family は `Webhook -> Mailchimp Add/Update Subscriber`
  なので、最初の live exact はこの family を優先する

## 10点までの最短ルート

- Lステップ
  - `回答フォーム 2問`
  - `アクション管理 1複合`
  - `リッチメニュー 2ボタン`
  を live で `作成 -> テスト -> rollback / cleanup`
- UTAGE
  - `商品管理 / 商品詳細管理 / 購入後アクション 1本`
  - `開放するバンドルコース` までの downstream smoke
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
