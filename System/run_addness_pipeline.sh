#!/bin/bash
# Addnessパイプライン実行スクリプト
# 成功・失敗どちらもSlack（定常業務）に通知する

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUNTIME_RESOLVER="$SCRIPT_DIR/scripts/python_runtime.py"
SYSTEM_DIR="$SCRIPT_DIR"
LOG="$SYSTEM_DIR/addness.log"

resolve_python() {
    if [ -f "$RUNTIME_RESOLVER" ]; then
        /usr/bin/python3 "$RUNTIME_RESOLVER" --print-path --min 3.10 2>/dev/null && return 0
    fi
    if [ -x "$HOME/agent-env/bin/python3" ]; then
        echo "$HOME/agent-env/bin/python3"
        return 0
    fi
    command -v python3 2>/dev/null || echo /usr/bin/python3
}

PYTHON="$(resolve_python)"

resolve_webhook_url() {
    "$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

env_candidates = [
    os.environ.get("SLACK_WEBHOOK_URL", "").strip(),
    os.environ.get("SLACK_AI_TEAM_WEBHOOK_URL", "").strip(),
]
for value in env_candidates:
    if value:
        print(value)
        raise SystemExit(0)

config_candidates = [
    (Path("/Users/koa800/Desktop/cursor/System/config/addness.json"), "slack_webhook_url"),
    (Path("/Users/koa800/Desktop/cursor/System/mail_inbox_data/config.json"), "slack_webhook_url"),
]

for path, key in config_candidates:
    if not path.exists():
        continue
    try:
        data = json.loads(path.read_text())
    except Exception:
        continue
    value = str(data.get(key, "")).strip()
    if value.startswith("${") and value.endswith("}"):
        value = os.environ.get(value[2:-1], "").strip()
    if value:
        print(value)
        raise SystemExit(0)
PY
}

WEBHOOK_URL="$(resolve_webhook_url)"
if [ -z "$WEBHOOK_URL" ]; then
    echo "環境変数または既存設定から Slack Webhook URL を解決できませんでした" >&2
    exit 1
fi

# ステップ別出力を保持する変数
OUT_FETCHER=""
OUT_CONTEXT=""
OUT_EXTRACTOR=""
OUT_PROFILER=""

notify_slack() {
    local text="$1"
    curl -s -X POST "$WEBHOOK_URL" \
        -H 'Content-Type: application/json' \
        -d "{\"text\": \"${text}\"}" > /dev/null
}

run_step() {
    local name="$1"
    local var_name="$2"
    shift 2
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 開始: $name" >> "$LOG"
    output=$("$@" 2>&1)
    exit_code=$?
    echo "$output" >> "$LOG"
    if [ $exit_code -ne 0 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 失敗: $name (exit=$exit_code)" >> "$LOG"
        notify_slack "❌ *Addnessパイプライン失敗*\n*ステップ:* ${name}\n*日時:* $(date '+%Y-%m-%d %H:%M')\n\`\`\`$(echo "$output" | tail -20)\`\`\`"
        exit $exit_code
    fi
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 完了: $name" >> "$LOG"
    # 出力を変数に保存
    eval "$var_name=\"\$output\""
}

export PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin

run_step "addness_fetcher"         OUT_FETCHER   $PYTHON "$SYSTEM_DIR/addness_fetcher.py"
run_step "addness_to_context"      OUT_CONTEXT   $PYTHON "$SYSTEM_DIR/addness_to_context.py"
run_step "addness_task_extractor"  OUT_EXTRACTOR $PYTHON "$SYSTEM_DIR/addness_task_extractor.py"
run_step "addness_people_profiler" OUT_PROFILER  $PYTHON "$SYSTEM_DIR/addness_people_profiler.py"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] パイプライン完了" >> "$LOG"

# ---- 各ステップから数値を抽出 ----

# フェッチャー: "プレビュー取得完了: X件" or "X プレビュー" など
previews=$(echo "$OUT_FETCHER"  | grep -oE '[0-9]+プレビュー' | tail -1)
nodes_f=$(echo "$OUT_FETCHER"   | grep -oE '[0-9]+ノード'     | tail -1)

# ゴールツリー: "→ X ノード取得"
nodes_c=$(echo "$OUT_CONTEXT"   | grep -oE '[0-9]+ ノード取得' | grep -oE '[0-9]+' | tail -1)

# タスク抽出: "実行可能: X件" "ウォッチ: X件" "委任先超過: X件"
actionable=$(echo "$OUT_EXTRACTOR" | grep -oE '実行可能: [0-9]+件' | grep -oE '[0-9]+')
watching=$(echo "$OUT_EXTRACTOR"   | grep -oE 'ウォッチ: [0-9]+件' | grep -oE '[0-9]+')
delegated=$(echo "$OUT_EXTRACTOR"  | grep -oE '委任先超過: [0-9]+件' | grep -oE '[0-9]+')

# プロファイラー: 人数・カテゴリ内訳
total=$(echo "$OUT_PROFILER"    | grep -oE '完了: [0-9]+人'        | grep -oE '[0-9]+')
boss=$(echo "$OUT_PROFILER"     | grep -oE '上司: [0-9]+人'         | grep -oE '[0-9]+')
parallel=$(echo "$OUT_PROFILER" | grep -oE '横（並列）: [0-9]+人'   | grep -oE '[0-9]+')
direct=$(echo "$OUT_PROFILER"   | grep -oE '直下メンバー: [0-9]+人' | grep -oE '[0-9]+')

# ---- 通知メッセージ組み立て ----
msg="✅ *Addnessパイプライン完了*  $(date '+%Y-%m-%d %H:%M')\n"
msg+="━━━━━━━━━━━━━━━━━━\n"
msg+="*① スクレイピング（addness_fetcher）*\n"
[ -n "$previews" ] && msg+="　・取得プレビュー: ${previews}\n"
[ -n "$nodes_f"  ] && msg+="　・取得ノード: ${nodes_f}\n"
msg+="\n"
msg+="*② ゴールツリー更新（addness_to_context）*\n"
[ -n "$nodes_c" ] && msg+="　・総ノード数: ${nodes_c}件\n"
msg+="\n"
msg+="*③ タスク抽出（addness_task_extractor）*\n"
[ -n "$actionable" ] && msg+="　・実行可能タスク: ${actionable}件\n"
[ -n "$watching"   ] && msg+="　・ウォッチ中: ${watching}件\n"
[ -n "$delegated"  ] && msg+="　・委任先超過: ${delegated}件\n"
msg+="\n"
msg+="*④ プロファイル更新（addness_people_profiler）*\n"
[ -n "$total"    ] && msg+="　・更新人数: ${total}人\n"
[ -n "$boss"     ] && msg+="　　└ 上司: ${boss}人\n"
[ -n "$parallel" ] && msg+="　　└ 横（並列）: ${parallel}人\n"
[ -n "$direct"   ] && msg+="　　└ 直下メンバー: ${direct}人\n"
msg+="━━━━━━━━━━━━━━━━━━"

notify_slack "$msg"
