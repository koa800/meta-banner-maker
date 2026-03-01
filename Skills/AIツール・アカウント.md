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

## 今後の拡張計画

- [ ] ブラウザ経由の画像生成（Lovart, Gemini ナノバナナ）
- [ ] ブラウザ経由の動画生成
- [ ] secretary_proactive_work で自律的にAIツールを使い分け
