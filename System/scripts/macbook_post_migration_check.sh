#!/usr/bin/env bash

set -u

script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"
ai_cmd="$repo_root/System/scripts/ai"

warn_count=0
error_count=0

print_section() {
  printf "\n== %s ==\n" "$1"
}

check_command() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    printf "[OK] command %-8s %s\n" "$name" "$(command -v "$name")"
  else
    printf "[WARN] command %-8s not found\n" "$name"
    warn_count=$((warn_count + 1))
  fi
}

check_required_path() {
  local label="$1"
  local path="$2"
  if [ -e "$path" ]; then
    printf "[OK] %s %s\n" "$label" "$path"
  else
    printf "[ERROR] %s missing: %s\n" "$label" "$path"
    error_count=$((error_count + 1))
  fi
}

check_optional_path() {
  local label="$1"
  local path="$2"
  if [ -e "$path" ]; then
    printf "[OK] %s %s\n" "$label" "$path"
  else
    printf "[WARN] %s missing: %s\n" "$label" "$path"
    warn_count=$((warn_count + 1))
  fi
}

print_section "Machine"
sw_vers
printf "arch: %s\n" "$(uname -m)"

print_section "Commands"
check_command git
check_command python3
check_command codex
check_command claude
check_command cursor
check_command gh

print_section "Critical paths"
check_required_path "repo" "$repo_root"
check_required_path "ai" "$ai_cmd"
check_required_path "post-commit" "$repo_root/.git/hooks/post-commit"
check_required_path "codex config" "$HOME/.codex/config.toml"
check_required_path "claude home" "$HOME/.claude"

print_section "Recommended paths"
check_optional_path "codex auth" "$HOME/.codex/auth.json"
check_optional_path "codex sessions" "$HOME/.codex/sessions"
check_optional_path "codex skills" "$HOME/.codex/skills"
check_optional_path "claude history" "$HOME/.claude/history.jsonl"
check_optional_path "ssh key" "$HOME/.ssh/id_ed25519"
check_optional_path "gh config" "$HOME/.config/gh/config.yml"

print_section "Git"
printf "branch: %s\n" "$(git -C "$repo_root" branch --show-current 2>/dev/null || printf 'unknown')"
printf "HEAD: %s\n" "$(git -C "$repo_root" rev-parse --short HEAD 2>/dev/null || printf 'unknown')"
git -C "$repo_root" status --short || true

latest_backup="$(ls -1dt "$repo_root"/System/data/migration_backup_* 2>/dev/null | head -n1 || true)"
print_section "Backup"
if [ -n "$latest_backup" ]; then
  printf "[OK] latest backup %s\n" "$latest_backup"
else
  printf "[WARN] no migration backup directory found under System/data\n"
  warn_count=$((warn_count + 1))
fi

print_section "ai doctor"
if "$ai_cmd" doctor; then
  printf "[OK] ai doctor passed\n"
else
  printf "[ERROR] ai doctor failed\n"
  error_count=$((error_count + 1))
fi

print_section "ai status (summary)"
"$ai_cmd" status | sed -n '1,6p'

print_section "ai pins (top)"
"$ai_cmd" pins | sed -n '1,8p'

print_section "Next"
printf "1. If the checks above look good, run: System/scripts/ai restore <別名>\n"
printf "2. If you want the previous pinned work first, example: System/scripts/ai restore 導線ツール\n"
printf "3. If home files are missing after Migration Assistant, use the latest backup shown above.\n"
printf "4. If repo state is missing, compare with diagnostics/git-state.txt and repo-uncommitted/worktree-files-full.tgz in the backup.\n"

print_section "Result"
printf "errors=%s warnings=%s\n" "$error_count" "$warn_count"

if [ "$error_count" -gt 0 ]; then
  exit 1
fi
