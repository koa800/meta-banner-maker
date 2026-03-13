# 管理シート参照

外部の管理シート（Google Sheets等）への参照と、同期データを格納する。

## 登録シート一覧

| ID | シート名 | URL | 用途 | 同期 |
|---|---|---|---|---|
| `1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA` | 【アドネス全体】数値管理シート | [リンク](https://docs.google.com/spreadsheets/d/1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA/edit) | 事業KPI・会社全体の重要数値。集客数・売上・会員数等を知りたいときに参照 | API経由で都度取得 |
| `1w-eFCzbGjgmoiuZe54X49BVZw46vm7hg6_CXI7f_gmw` | 【アドネス株式会社】KPI基盤（正本） | [リンク](https://docs.google.com/spreadsheets/d/1w-eFCzbGjgmoiuZe54X49BVZw46vm7hg6_CXI7f_gmw/edit) | 5KPIの一次データ正本。raw / fact / view を分けて、経営会議・日報・Cursor の共通入力元にする | ✅ 03/13 22:02 (32603行) |
| `16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk` | 【広告チーム】報告シート | [リンク](https://docs.google.com/spreadsheets/d/16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk/edit) | チーム報告シート（日報・週報・月報・年報）。目標と現状のギャップ把握→アクション導出用。**毎日使用** | API経由で都度取得 |
| `1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk` | 【アドネス株式会社】顧客データ（複数イベント） | [リンク](https://docs.google.com/spreadsheets/d/1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk/edit) | CDP顧客マスタ。イベント発生者（セミナー予約・購入等）の統合データ | API経由で都度取得 |
| `1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00` | 【アドネス株式会社】顧客データ（メールアドレスのみ） | [リンク](https://docs.google.com/spreadsheets/d/1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00/edit) | リードプール。メールアドレスのみのリード（イベント未発生） | API経由で都度取得 |
| `1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8` | 【アドネス株式会社】集客データ（UUメールアドレス） | [リンク](https://docs.google.com/spreadsheets/d/1mtfvXN92_vtzwLhOiTcufdLJ6vkfn8oYjCiqC0ZK6j8/edit) | `顧客マスター + メールのみ` を母集団にした `UUメールアドレス / 日別UUメールアドレス数 / 複数アドレスユーザー / メール集計サマリー / データソース管理 / データ追加ルール` の6タブ構成。登録日の正本は `集客データ（メールアドレス）` の各流入経路タブ A列 | `python3 System/unique_email_sheet_sync.py` で再生成 |
| `12RGMUfU8Wj0CCdcRfY7kI56kdATV7wDXjvYmGdQb_Nk` | 【スキルプラス】個別予約AIテレアポ管理 | [リンク](https://docs.google.com/spreadsheets/d/12RGMUfU8Wj0CCdcRfY7kI56kdATV7wDXjvYmGdQb_Nk/edit) | スキルプラス販売導線における AIテレアポ運用の管理シート。顧客マスタを正本に、架電一覧・架電履歴・架電成績・運用状態を管理する | API経由で都度取得 |
| `1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y` | 言葉の定義 | [リンク](https://docs.google.com/spreadsheets/d/1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y/edit) | 甲原さんが使う言葉の定義集。入力口はシート、AI参照正本は `Master/前提/用語定義.md` / `.json` | ✅ 03/12 00:25 (128行) |

## ディレクトリ構成

```
sheets/
├── README.md           ← このファイル（シート一覧・用途・取得コマンド）
└── {シートID}/
    ├── _meta.json      ← シートのメタ情報（タブ名・行数・列数）
    └── {tab名}.csv     ← タブごとの同期キャッシュ
```

> **API取得が正本、CSVは高速参照用キャッシュ。**
> 人が厳密に確認するときは必要に応じて API / 元シートを見直し、AI の高速参照や差分確認には `sheets_sync.py` が生成するローカルキャッシュを使う。

## シート詳細

### 【アドネス全体】数値管理シート

事業のKPIや会社全体の数値を確認するためのマスターシート。

| タブ名 | 内容 |
|---|---|
| 元データ | 997行×26列。集計元の生データ |
| スキルプラス（日別） | 6036行×13列。日別の詳細数値 |
| スキルプラス（月別） | 100行×12列。月別サマリー |

```bash
# データ取得コマンド
python3 System/sheets_manager.py read "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA"
python3 System/sheets_manager.py read "1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA" "スキルプラス（月別）"
```

### 【アドネス株式会社】KPI基盤（正本）

Looker や日報を正本にせず、一次データから 5KPI を再現するための基盤シート。

| タブ名 | 内容 |
|---|---|
| README | 5KPI定義、レイヤー構造、次の投入順 |
| raw_ads_* | Meta / Google / TikTok / X の広告生データ入口 |
| raw_funnel_events | lead / booking / attend 等のイベント入口 |
| raw_payments | 決済・返金の入口 |
| raw_membership | 入会 / クーリングオフ / 中途解約の入口 |
| route_master | `route_key = 媒体|ファネル|CR|LP` の定義 |
| 導線データ | 1イベント1行の正本 |
| 媒体×CR×LPデータ | `1日 × 1 route_key × 1行` の正本 |
| 顧客マスタ | 1人1行の正本 |
| kpi_daily | 日別再集計ビュー |
| exec_dashboard | 経営会議・日報・Cursor 向けの表示タブ |

```bash
# 初期構築
python3 System/kpi_foundation_setup.py

# 決済履歴の反映
python3 System/kpi_foundation_payment_import.py

# シート確認
python3 System/sheets_manager.py info "1w-eFCzbGjgmoiuZe54X49BVZw46vm7hg6_CXI7f_gmw"
```

### 【広告チーム】報告シート

目的や目標に対しての現状を把握し、ギャップを埋めるためのアクションを出しやすくすることで、ビジネスモデルの強化・維持を図るためのシート。毎日使用。

| タブ名 | 内容 |
|---|---|
| 目的・ルール | シートの使い方・ルール定義 |
| 日報 | 1047行×261列。日次の数値報告（集客数・個別予約数・着金売上等） |
| 週報 | 週次サマリー |
| 月報 | 月次サマリー |
| 年報 | 年次サマリー |
| 表・グラフ | 可視化用 |

```bash
# データ取得コマンド
python3 System/sheets_manager.py read "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "日報"
python3 System/sheets_manager.py read "16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk" "週報"
```

---

### 【アドネス株式会社】顧客データ（複数イベント）＝ CDPマスタ

イベント発生者（セミナー予約・購入・アンケート回答等）の顧客データを統合管理するマスターシート。

| タブ名 | 内容 |
|---|---|
| 顧客マスタ | 約57,750行×58列。全顧客の統合データ |
| データソース管理 | カラムマッピング（CDPカラム→参照先） |
| マスター追加ルール | 登録・名寄せ・更新のルール |
| 除外リスト | スタッフ・テストデータの除外対象 |
| 定義 | 各カラムの定義・データソース |

```bash
# 同期コマンド（cdp_sync.py経由）
python3 System/cdp_sync.py sync
python3 System/cdp_sync.py status
```

### 【アドネス株式会社】顧客データ（メールアドレスのみ）＝ リードプール

CDPマスタに未登録のリード（メールアドレスのみ・イベント未発生）を格納。

| タブ名 | 内容 |
|---|---|
| メール集客データ | 約278,000行×3列。登録日/メールアドレス/初回流入経路 |
| データソース管理 | ソースマッピング |
| データ追加ルール | 追加条件・削除ルール |
| 定義 | カラム定義 |

```bash
# 同期コマンド（経路別タブ→メール一覧）
python3 System/cdp_sync.py sync-leads
```

### 【アドネス株式会社】集客データ（UUメールアドレス）

メール登録の重複なし人数を持つための専用シート。未転換リード一覧とは役割を分ける。

| タブ名 | 内容 |
|---|---|
| UUメールアドレス | `登録日 / メールアドレス` の2列。母集団は `顧客マスター + メールのみ`。登録日の正本は `集客データ（メールアドレス）` の各流入経路タブ A列で、同じメールは最も古い日付を使う |
| 日別UUメールアドレス数 | `日付 / UUメールアドレス数 / 累計UUメールアドレス数`。初回登録日ベースの日次集計 |
| 複数アドレスユーザー | `顧客ID / メールアドレス数 / メールアドレス`。1人で複数メールを持つ顧客を確認する |
| メール集計サマリー | `更新日時 / UUメールアドレス数 / 登録日ありUUメールアドレス数 / 登録日空欄UUメールアドレス数 / 複数アドレスユーザー数 / 主メール重複数 / 実際のユニーク人数（暫定）` |
| データソース管理 | 母集団に使うシートと、登録日補完だけに使うシートを固定する |
| データ追加ルール | 母集団、登録日、手編集禁止、異常検知、更新頻度の運用ルール |

```bash
# 6タブまとめて再生成
python3 System/unique_email_sheet_sync.py

# 主メール重複の統合
python3 System/cdp_sync.py merge-primary-email-duplicates
```

- 定期更新: Orchestrator が `18 */2 * * *` で2時間ごとに再生成
- 異常検知: `主メール重複 > 0` または `UU件数の急減` を検知した場合は更新を止める
- 保護: `UUメールアドレス / 日別UUメールアドレス数 / 複数アドレスユーザー / メール集計サマリー` は保護対象

---

### 【スキルプラス】個別予約AIテレアポ管理

スキルプラス販売導線の中で、AIテレアポ施策を運用するための管理シート。

- 配置: `マイドライブ > 03. スキルプラス > 販売導線`
- 役割: 顧客マスタを読み取り専用の正本にし、`架電一覧` を毎朝自動更新する
- 必須キー: `顧客ID`。`顧客ID` が空欄の行は状態引き継ぎできないため同期対象にしない
- 氏名: `架電一覧` に `氏名` を持ち、原則 `姓 + 名`、欠ける時だけ `LINE名` を使う。AIの本人確認に使う
- 対象外条件: `デザジュク` / `デザ塾` を `初回流入経路` または `初回購入商品` / `最新購入商品` / `購入商品` に含む人は、スキルプラス販売対象外として `架電一覧` に載せない
- 対象外商品: `デザイン限界突破3日間合宿` / `コンドウハルキ秘密の部屋` を `初回購入商品` / `最新購入商品` / `購入商品` に含む人も `架電一覧` に載せない
- タブ: `架電一覧` / `架電履歴` / `架電成績` / `運用チェック` / `抽出条件・優先順位`
- 自動同期: Mac Mini Orchestrator が `06:15` に `python3 System/teleapo_sync.py sync` を実行
- 並び順: `運用ステータス` を先に見て、`未着手 -> 予約完了 -> 対応完了 -> 対象外` の順に先頭へ出す。その中で `優先順位帯` を並べる。`優先順位帯` は `P1_0-60日` のように base priority と時間帯を合わせて表示し、同一優先帯の中では `初回流入日` を `0-60日 -> 61-180日 -> 181-365日 -> 366日以上 -> 日付不明` の順に並べる。`作成日` は取込日に寄るため使わない
- プルダウン: `架電一覧` の `運用ステータス` / `最新架電結果` と、`架電履歴` の `架電結果` に固定選択肢を入れる。`架電結果` は `応答あり / 留守電 / 応答なし / 拒否 / 番号不備 / 対象外`
- 誤操作防止: `架電一覧` の同期列と、`架電成績` / `運用チェック` / `抽出条件・優先順位` は warning-only 保護を入れる。運用では `架電一覧` の `運用ステータス` / `最新架電結果` を主に触る
- AI更新ルール: 通話後は `架電一覧` の `運用ステータス` / `最新架電結果` を更新し、`架電履歴` に 1 通話 1 行で追記する。`最新架電結果` と `架電結果` は電話の事実だけを記録し、予約は `個別予約日` と `個別予約合計` の現値で判定する
- 予約扱い: もともと `架電一覧` にいる人に予約シグナルが入ったら `予約完了` に更新して一覧へ残す。新規の予約済み顧客を一覧へ追加はしない。`予約完了` を過去ステータスだけで維持しない
- 架電成績: `架電一覧` と `架電履歴` から、更新日時 / 架電対象数 / 対応完了 / 応答あり / 留守電 / 応答なし / 拒否 / 番号不備 / 予約完了 / 予約完了（架電あり） を自動集計する
- 運用チェック: 最終同期成功日時 / 同期鮮度 / 前回同期件数 / 今回同期件数 / 予約完了だが個別予約日なし / 番号不備だが対象外でない / 架電履歴の顧客ID空欄 / 架電履歴の架電結果空欄 を自動表示する
- 要確認事項: `抽出条件・優先順位` に、森本さんと決める `送信チャネル / 送信タイミング / 送信システム / 導線成功の定義` を残す
- ガード: Google API の一時エラーはリトライし、対象件数が前回比で急減したときは一覧を壊さないために更新を止める

```bash
# シート確認
python3 System/sheets_manager.py info "12RGMUfU8Wj0CCdcRfY7kI56kdATV7wDXjvYmGdQb_Nk"

# 架電一覧を顧客マスタから同期
python3 System/teleapo_sync.py sync

# 書き込みなしで件数確認
python3 System/teleapo_sync.py sync --dry-run
```

---

### 言葉の定義

甲原さんが使う言葉の定義を育てる入力口。人は Google Sheets に追記し、AI はローカル正本を参照する。

- シート入力口: `言葉の定義`
- ローカル正本: `Master/前提/用語定義.md`
- 機械可読版: `Master/前提/用語定義.json`

```bash
# シート同期 + 前提レイヤーの glossary 再生成
python3 System/sheets_sync.py --id "1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y"
```

---

## 追加予定

- クリエイティブ数値管理
- その他管理シート
