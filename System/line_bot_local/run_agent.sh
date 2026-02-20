#!/bin/bash
# LINE Bot Local Agent 起動スクリプト
# 未設定なら Secret Manager から ANTHROPIC_API_KEY / LOCAL_AGENT_TOKEN を取得して注入（gcloud 利用時）

cd "$(dirname "$0")"

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

exec /usr/bin/python3 local_agent.py
