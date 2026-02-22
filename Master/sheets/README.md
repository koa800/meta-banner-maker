# 管理シート参照

外部の管理シート（Google Sheets等）への参照と、同期データを格納する。

## 登録シート一覧

| ID | シート名 | URL | 用途 | 同期 |
|---|---|---|---|---|
| `1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA` | 【アドネス全体】数値管理シート | [リンク](https://docs.google.com/spreadsheets/d/1FOh_XGZWaEisfFEngiN848kSm2E6HotAZiMDTmO7BNA/edit) | 事業KPI・会社全体の重要数値。集客数・売上・会員数等を知りたいときに参照 | ✅ 02/22 08:33 (6182行) |
| `16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk` | 【広告チーム】報告シート | [リンク](https://docs.google.com/spreadsheets/d/16W1zALKZrnGeesjTlmsraDfw3i71tcdYJE686cmUaTk/edit) | チーム報告シート（日報・週報・月報・年報）。目標と現状のギャップ把握→アクション導出用。**毎日使用** | ✅ 02/22 08:33 (96行) |

## ディレクトリ構成

```
sheets/
├── README.md           ← このファイル（シート一覧・用途）
└── {シートID}/         ← シートごとのキャッシュ・同期データ（今後追加）
```

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

## 追加予定

- クリエイティブ数値管理
- その他管理シート
