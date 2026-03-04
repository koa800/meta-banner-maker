# アドネス株式会社 請求書提出スキル

## 概要

毎月の業務委託報酬と経費立替の請求書を作成し、アドネス株式会社に提出する。
Orchestrator の `monthly_invoice_submission` タスクで毎月3日 09:30 に自動実行される。

## タイミング

- **毎月3日 09:30** に前月分を自動実行（Orchestrator スケジュール）
- 期限: 翌月5日まで
- 例: 1月分 → 2月3日に自動実行 → 5日までに提出完了

## 使用サービス

| サービス | URL | ログイン |
|---------|-----|---------|
| INVOY（請求書作成） | https://www.invoy.jp/login?next=/dashboard/ | Google ログイン（koa800sea.nifs@gmail.com） |
| 請求金額管理シート | https://docs.google.com/spreadsheets/d/1Bmbeglbhf62NeiJUHpai63DITrMDC3WSr09jJD8YhaM/edit?gid=0#gid=0 | - |
| 提出フォーム | https://docs.google.com/forms/d/e/1FAIpQLScu_sb_EI5rwo7eJSAQKLrmZdk5kv5rhwmxGgMSA2DLUN0pZA/viewform | - |
| Google Drive（保存先） | マイドライブ > アドネス > 給与、経費 > [年]年/ | koa800sea.nifs@gmail.com |

## 自動実行フロー

```
Step 1: 単価確認（スプレッドシートAPI）
  ↓
Step 2: INVOY で請求書2通作成（ブラウザ自動操作）
  ↓
Step 3: PDF ダウンロード
  ↓
Step 4: LINE で甲原さんに確認依頼（/api/notify_owner → 秘書グループ）
  ↓  ★ ここで中断。承認されるまで提出しない ★
  ↓  甲原さんが「OK」と返信 → _pending_confirmations で検知
  ↓
Step 5: 提出フォームで2回提出（ブラウザ自動操作）
  ↓
Step 6: Google Drive に PDF 保存
  ↓
Step 7: LINE で完了報告
```

## 詳細手順

### Step 1: 単価の確認

請求金額管理シートを開き、**甲原海人の行（行5）** の該当月列を確認する。

- シートID: `1Bmbeglbhf62NeiJUHpai63DITrMDC3WSr09jJD8YhaM`
- 列の見方: ヘッダー行4の「YY/MM 末払い」が支払月。**前月分の報酬** がその列に記載
  - 例: 「26/2 末払い」= 1月分報酬 → 2月に請求
- この金額を業務委託報酬の単価として使用
- API で取得可能: `python3 System/sheets_manager.py read "1Bmbeglbhf62NeiJUHpai63DITrMDC3WSr09jJD8YhaM" "Sheet1" "A4:Z5"`

### Step 2: INVOY で請求書作成（2通）

1. INVOY にログイン（Google: koa800sea.nifs@gmail.com）
   - URL: https://www.invoy.jp/login?next=/dashboard/
2. 「発行」→「請求書」から **アドネス株式会社** のテンプレートを **複製**
   - 業務委託報酬と経費建替の2種類がある。それぞれ複製する

#### 業務委託報酬

| 項目 | 設定値 |
|------|--------|
| 発行日 | 作成日（当日） |
| お支払い期限 | 作成日の月の最終日 |
| 件名 | `業務委託報酬　YYYY年MM月分`（前月を指定） |
| 品目明細（単価） | スプレッドシートの金額 |

#### 経費立替

| 項目 | 設定値 |
|------|--------|
| 発行日 | 作成日（当日） |
| お支払い期限 | 作成日の月の最終日 |
| 件名 | `経費立替　YYYY年MM月分`（前月を指定） |
| 品目明細（単価） | ¥2,000（Facebook広告代、毎月固定） |

### Step 3: PDF ダウンロード・リネーム

各請求書をPDFで保存し、以下の命名規則でリネームする。

| 種類 | ファイル名 |
|------|-----------|
| 業務委託報酬 | `YYYY年M月請求書_甲原海人.pdf` |
| 経費立替 | `YYYY年M月経費建替_甲原海人.pdf` |

例: `2026年1月請求書_甲原海人.pdf`, `2026年1月経費建替_甲原海人.pdf`

### Step 4: 甲原さんに確認（必須・承認ゲート）

**提出前に必ず承認を得る。**

1. PDF を Render サーバーにアップロード（`/api/upload` エンドポイント）
2. LINE 秘書グループに確認依頼を送信（`/api/notify_owner` エンドポイント）
   - 甲原さんが「OK」と引用返信 → `_pending_confirmations` で検知される
3. **承認されるまで提出しない**（ここで処理を中断する）

### Step 5: 提出フォームで提出（2回）

承認後、Google フォームで **業務委託報酬** と **経費立替** をそれぞれ1回ずつ提出する。

- フォームURL: https://docs.google.com/forms/d/e/1FAIpQLScu_sb_EI5rwo7eJSAQKLrmZdk5kv5rhwmxGgMSA2DLUN0pZA/viewform

| フォーム項目 | 入力値 |
|-------------|--------|
| メールアドレス | koa800sea.nifs@gmail.com |
| アドネスの誰が担当か？ | 三上功太 |
| 請求書発行事業者の氏名 | 甲原海人 |
| 提出者の氏名 | 甲原海人 |
| 請求金額 | PDFに記載の金額（業務委託と経費で異なる） |
| 備考 | 未記入 |
| PDFファイル追加 | 対応するPDFを添付 |

#### ブラウザ操作の注意点

- **フォームの ref ID は毎回変わる可能性がある**: `read_page` で全要素を取得してから入力すること
- **チェックボックスは `form_input` 不可**: `role="checkbox"` の DIV 要素。JavaScript で `.click()` するか `left_click` を使う
- **PDF添付は Google Drive Picker**: ファイルをアップロードボタン → 「最近使用したアイテム」タブから選択
  - 事前に PDF を Drive にアップロードしておく必要がある（Render の `/api/upload` 経由でも可）
- **「回答のコピーを自分宛に送信する」トグル**: 不要。ON になっていたら OFF にする

### Step 6: Google Drive に保存

保存先: `マイドライブ > アドネス > 給与、経費 > [YYYY]年/`
- 親フォルダID: `1bgUmZAH6okAGUWQ7uYSUo4K2KbOomfaM`
- 2026年フォルダID: `1s64JH0T4nWlDIZV6QgAOvg9xDPV1pBAD`

#### API アップロード（自動化済み）

`token_drive_personal.json`（koa800sea.nifs@gmail.com）で Drive API 経由でアップロード可能。

```bash
cd /path/to/project
python3 -c "
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json

with open('System/credentials/token_drive_personal.json') as f:
    t = json.load(f)
creds = Credentials(token=t['token'], refresh_token=t['refresh_token'],
                     token_uri=t['token_uri'], client_id=t['client_id'],
                     client_secret=t['client_secret'], scopes=t['scopes'])
service = build('drive', 'v3', credentials=creds)
folder_id = '1s64JH0T4nWlDIZV6QgAOvg9xDPV1pBAD'  # 2026年フォルダ

for f in ['YYYY年M月請求書_甲原海人.pdf', 'YYYY年M月経費建替_甲原海人.pdf']:
    media = MediaFileUpload(f, mimetype='application/pdf')
    service.files().create(body={'name': f, 'parents': [folder_id]}, media_body=media).execute()
"
```

### Step 7: 完了報告

甲原さんに LINE で提出完了を報告する。

## 注意事項

- **承認前に絶対に提出しない**（Step 4 の確認が必須）
- フォーム提出時、業務委託と経費のPDFを取り違えないこと
- 経費立替は基本的に毎月 ¥2,000（Facebook広告代）で固定
- INVOY のテンプレート複製時、前月のデータが残っている場合があるので日付・件名・金額を必ず確認すること
