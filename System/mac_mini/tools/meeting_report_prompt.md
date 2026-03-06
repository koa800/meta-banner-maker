# 経営会議資料 自動作成プロンプト

あなたはAI秘書です。毎週金曜の経営会議に向けて、広告チーム報告資料をGoogle Docsに自動作成します。

## 実行手順

### 前提情報
- Google Doc ID: `18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s`
- Looker Studio URL: `lookerstudio.google.com/u/1/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2`
  - 月次KPI: `/page/p_ghqtl90f1d`（「広告チーム報告」のコピー）
  - 12週実績: `/page/p_l2misk7gyd`
- 今日は{today}（金曜日）
- 会議日: {meeting_date}
- 月次期間: {month_start}〜{month_end}（当月1日〜会議2日前の水曜日）
- 週次期間: {week_start}〜{week_end}（木曜〜水曜の7日間）
- Credentials: `System/credentials/token.json`

### Step 1: Looker Studioからスクリーンショット取得

#### 1-1. 月次KPIスクショ
1. Looker Studio「広告チーム報告」のコピーページを開く
2. 日付フィルターをクリック → 「詳細設定」を選択
3. JavaScriptで開始オフセットを変更:
   - 開始日 = 今日 - {month_offset_start}日 = {month_start}
   - 終了日 = 今日 - {month_offset_end}日 = {month_end}
   ```javascript
   const inputs = document.querySelectorAll('input[type="number"]');
   const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
   setter.call(inputs[0], '{month_offset_start}');
   inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
   inputs[0].dispatchEvent(new Event('change', { bubbles: true }));
   setter.call(inputs[1], '{month_offset_end}');
   inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
   inputs[1].dispatchEvent(new Event('change', { bubbles: true }));
   ```
4. 「適用」ボタンをクリック → 3秒待機
5. KPIカード領域（重要数値の上段4カード+下段5カード）をscreencaptureで切り取り
6. `/tmp/meeting_monthly_kpi.png` に保存

#### 1-2. 12週実績グラフスクショ
1. 左メニューから「過去12週実績」ページに移動
2. 4つのグラフ（集客数・個別予約数・広告費・CPA）をscreencaptureで切り取り
3. `/tmp/meeting_12week_graphs.png` に保存

#### 1-3. 週次（7日間）KPIスクショ
1. 「広告チーム報告」のコピーページに戻る
2. 日付フィルターを7日間に変更:
   - 開始日 = 今日 - {week_offset_start}日 = {week_start}
   - 終了日 = 今日 - {week_offset_end}日 = {week_end}
3. 「適用」→ 3秒待機
4. KPIカード領域をscreencaptureで切り取り
5. `/tmp/meeting_weekly_kpi.png` に保存
6. フィルターを元に戻す（開始オフセット={month_offset_start}に変更→適用）

### Step 2: スクリーンショットから数値を読み取る

各スクリーンショットからKPI数値を読み取る:

**月次KPI（必須）:**
- 集客数、個別予約数、着金売上、ROAS（上段。前期比%付き）
- 広告費（税込）、CPA、個別予約CPO、粗利、返金額（下段）

**週次（7日間）KPI（必須）:**
- 同上のレイアウト

### Step 3: Google Docsに資料を作成

`System/mac_mini/tools/meeting_report_v4.py` をベースに、読み取った数値を使って資料を作成する。

1. 既存のセクション（前回分）を削除
2. テキスト・テーブルを挿入
3. フォーマット適用（タイトル20pt中央/見出し14pt太字/評価太字/テーブルスタイル）
4. セル内容を埋める（実際の数値で）

### Step 4: スクリーンショットを貼り付け

各プレースホルダーテキストを画像で置き換える:

1. `/tmp/meeting_monthly_kpi.png` をクリップボードにコピー
   ```bash
   osascript -e 'set the clipboard to (read (POSIX file "/tmp/meeting_monthly_kpi.png") as «class PNGf»)'
   ```
2. Google Docsで「[月次KPIスクショ]」テキストを選択 → Cmd+V
3. 同様に12週グラフ、7日間KPIも貼り付け

### Step 5: 総評・コメントの生成

数値から以下を判定:
- **5段階評価**: 月目標に対する達成ペースで判定
  - 5=大幅超過、4=達成ペース、3=ギリギリ、2=やや未達、1=全然ダメ
- **総評コメント**: 1-2文で端的に
- **12週コメント**: 傾きの変化に注目
- **着地予想**: 日割り計算（当月経過日数 / 当月日数 × 実績）
- **プロジェクト評価**: 数値から推定（判断できなければ「（確認）」）
- **ボトルネック**: 数値悪化ポイントから特定

### Step 6: LINE通知

完成したらLINE秘書グループに報告:
```
経営会議資料の下書きができました
→ https://docs.google.com/document/d/18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s/edit

総評: X/5 — 〇〇〇
補足・修正があれば返信してください
```

## 注意事項

- スクリーンショットは必ずzoomで内容確認してから使う
- screencaptureの座標計算: MCP座標 × (1890/1552) × 1.6 + Chrome UIオフセット(422px)
- Google Docs APIは `System/credentials/token.json` を使用（scopes: documents, drive, spreadsheets）
- KPI優先度: ①着金売上 ②ROAS(300%=OK) ③集客数 ④CPA(3000以下=良)
- フィルター変更はJavaScriptのnativeInputValueSetterパターンで行う
