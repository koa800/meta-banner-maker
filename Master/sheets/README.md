# 管理シート参照

外部の管理シート（Google Sheets等）への参照と、同期データを格納する。

## 登録シート一覧

| ID | シート名 | URL | 用途 | 同期 |
|---|---|---|---|---|
| `1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA` | 【アドネス全体】数値管理シート | [リンク](https://docs.google.com/spreadsheets/d/1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA/edit) | 事業KPI・会社全体の重要数値。集客数・売上・会員数等を知りたいときに参照 | API経由で都度取得 |
| `16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk` | 【広告チーム】報告シート | [リンク](https://docs.google.com/spreadsheets/d/16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk/edit) | チーム報告シート（日報・週報・月報・年報）。目標と現状のギャップ把握→アクション導出用。**毎日使用** | API経由で都度取得 |
| `1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk` | 【アドネス株式会社】顧客データ（複数イベント） | [リンク](https://docs.google.com/spreadsheets/d/1qjU279OVD0i4h2AdQzkYIsZCfA1BeiUKLHNg7i2a2fk/edit) | CDP顧客マスタ。イベント発生者（セミナー予約・購入等）の統合データ | API経由で都度取得 |
| `1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00` | 【アドネス株式会社】顧客データ（メールアドレスのみ） | [リンク](https://docs.google.com/spreadsheets/d/1iD3DGxNhZruyjYcA5n6oXRDk2ZGA3uMDOo0stQS9Y00/edit) | リードプール。メールアドレスのみのリード（イベント未発生） | API経由で都度取得 |
| `1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y` | 言葉の定義 | [リンク](https://docs.google.com/spreadsheets/d/1nkmeWcHmzxPJH1d5veXwTpDoZrsPFH4_3txevqj225Y/edit) | 甲原さんが使う言葉の定義集。入力口はシート、AI参照正本は `Master/前提/用語定義.md` / `.json` | ✅ 03/09 06:58 (77行) |

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
