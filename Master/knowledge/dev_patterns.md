# 開発パターン・教訓

## 実装パターン

- **出力→入力ループ**: Slack/LINEなど「書いたものを読み返す」システムでは、自分のメッセージを必ず除外する。subtype + user_id + テキストパターンの3重フィルタ推奨
- **15秒間隔タスクにはガードを**: Claude API呼び出しを含む短間隔タスクは、前回未完了ならスキップする実行中フラグ必須
- **ファイルベースの状態管理**: 複数プロセスが同じJSONを読み書きする場合、tmp-rename（アトミック書き込み）必須
- **Slackメンションルーティング**: #ai-team は宛先明示運用。「日向」→日向タスク、「秘書」→秘書直接応答、メンションなし→スキップ

## Claude Code CLI 移行パターン（API消費削減）

- **対象**: 非リアルタイムのバッチ/スケジュールタスク（即時応答やRenderサーバーは対象外）
- **ヘルパー関数**: `_run_claude_cli(prompt, model, max_turns, timeout)` を各ファイルに配置
- **system prompt統合**: CLI では system prompt が指定できないため、プロンプト冒頭に「あなたは〇〇です。」として統合
- **JSON出力**: `===JSON_START===` / `===JSON_END===` マーカーで囲む指示をプロンプトに含め、stdoutから抽出
- **PATH保証**: launchd環境では `/opt/homebrew/bin` がPATHにないため、env に追加必須
- **max_turns=3**: 単純テキスト生成には十分（Tool Use不要）

## Mac Mini デプロイ

- git pull → stash（ローカル変更あれば）→ rsync → launchctl unload/load。plist名は正確に確認
