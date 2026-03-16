#!/bin/bash
# LINE Bot Local Agent 起動スクリプト
# 未設定なら Secret Manager から ANTHROPIC_API_KEY / LOCAL_AGENT_TOKEN を取得して注入（gcloud 利用時）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

resolve_runtime_resolver() {
  local candidate
  for candidate in \
    "$SCRIPT_DIR/../scripts/python_runtime.py" \
    "$SCRIPT_DIR/../System/scripts/python_runtime.py"
  do
    if [ -f "$candidate" ]; then
      echo "$candidate"
      return 0
    fi
  done
  return 1
}

resolve_python() {
  local resolver
  resolver="$(resolve_runtime_resolver 2>/dev/null || true)"
  if [ -n "$resolver" ]; then
    /usr/bin/python3 "$resolver" --print-path --min 3.10 2>/dev/null && return 0
  fi

  if [ -x "$HOME/agent-env/bin/python3" ]; then
    echo "$HOME/agent-env/bin/python3"
    return 0
  fi

  command -v python3 2>/dev/null || echo /usr/bin/python3
}

# gcloud でシークレット取得（5秒タイムアウト）
fetch_secret() {
  local secret_name="$1"
  local result
  result=$(gtimeout 5 gcloud secrets versions access latest --secret="$secret_name" 2>/dev/null) || result=""
  echo "$result"
}

if command -v gcloud >/dev/null 2>&1 && command -v gtimeout >/dev/null 2>&1; then
  [[ -z "${ANTHROPIC_API_KEY:-}" ]] && export ANTHROPIC_API_KEY=$(fetch_secret ANTHROPIC_API_KEY) || true
  [[ -z "${LOCAL_AGENT_TOKEN:-}" ]] && export LOCAL_AGENT_TOKEN=$(fetch_secret LOCAL_AGENT_TOKEN) || true
elif command -v gcloud >/dev/null 2>&1; then
  # gtimeout がない場合はバックグラウンドで取得を試みる（ハング防止）
  echo "⚠️ gtimeout がないため、gcloud シークレット取得をスキップ"
  echo "   環境変数 ANTHROPIC_API_KEY / LOCAL_AGENT_TOKEN を手動で設定してください"
fi

PYTHON_BIN="$(resolve_python)"
exec "$PYTHON_BIN" -u local_agent.py
