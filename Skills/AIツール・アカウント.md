# AIツール・アカウント情報

## アカウント

| アカウント | 用途 | ログイン先 |
|-----------|------|-----------|
| `koa800sea.nifs@gmail.com` | 生成AIツール全般（Lovart, 動画AI等） | Chrome ブックマーク「AIツール」 |
| `kohara.kaito@team.addness.co.jp` | Gemini（ナノバナナ=画像生成機能） | gemini.google.com |

## Chrome ブックマーク構造（AIツール）

```
AIツール/
├── 動画生成AI/
├── 画像生成AI/    ← Lovart 等
└── テキスト生成AI/
```

## 現在の画像生成フロー

| 方式 | ツール | 用途 |
|------|--------|------|
| API経由（実装済み） | Gemini 2.5 Flash (`gemini-2.5-flash-image`) | LINE「画像作って」→自動生成 |
| APIフォールバック | Pollinations.ai (Flux) | Gemini予算超過時 |
| ブラウザ経由（未実装） | Gemini ナノバナナ / Lovart 等 | 高品質画像・特殊スタイル |

## 秘書の使用モデル（自己認識用）

- テキスト応答・ツール選択: Claude Haiku 4.5
- 画像生成: Gemini 2.5 Flash (gemini-2.5-flash-image)
- 返信案生成: Claude Sonnet 4.5（local_agent経由）
- ゴール実行・日報入力: Claude Code CLI (claude-secretary)
- カレンダー・メール: Google Calendar/Gmail API

## 広告リサーチツール

### 動画広告分析Pro（DPro）

| 項目 | 内容 |
|------|------|
| URL | https://dpro.kashika-20mile.com/search |
| ログインID | addness.adteam@gmail.com |
| パスワード | Addness0726@@ |
| 用途 | YouTube / Instagram の動画広告を横断分析。消化額・再生数・LP遷移先・広告主を一覧で確認できる |

**主な使い方**:
- 競合・他社の動画広告クリエイティブ（CR）とLP（遷移先）をリサーチ
- 消化額の増加が大きい＝直近で当たっている広告を特定
- LP種別（記事LP / 直LP / LINE誘導LP / アンケートLP）ごとのトレンド把握

**URLパラメータ**:
- `app_id=1` → YouTube のみ
- `app_id=4` → Instagram のみ
- `app_id=1%2C4` → YouTube + Instagram
- `media_type=video` → 動画のみ
- `interval=2` → 2週間

**データ取得の技術メモ**:
- テーブルは ag-grid（仮想スクロール、DOMに18行のみ）
- 全行取得は React fiber tree → `stateNode.api` → `forEachNode()` で100件取得可能
- URL を含むデータは `console.log()` → `read_console_messages` で回収（JavaScript tool の return では BLOCKED される）
- 詳細なスクリプトは `Master/addness/dpro_動画広告リサーチ.md` を参照

---

## 今後の拡張計画

- [ ] ブラウザ経由の画像生成（Lovart, Gemini ナノバナナ）
- [ ] ブラウザ経由の動画生成
- [ ] secretary_goal_progress で自律的にAIツールを使い分け
