# Preserve the existing shell behavior, then add workspace-specific tab titles.
if [[ -f "$HOME/.zshrc" && "$HOME/.zshrc" != "$ZDOTDIR/.zshrc" ]]; then
  source "$HOME/.zshrc"
fi

cursor_task_is_managed_terminal() {
  [[ -o interactive ]] || return 1
  [[ -z "${ZSH_EXECUTION_STRING:-}" ]] || return 1
  [[ -t 0 && -t 1 ]] || return 1
}

cursor_task_normalize_title() {
  local raw="$*"
  local title

  title=$(printf '%s' "$raw" | tr '\n' ' ' | tr -s '[:space:]' ' ')
  title="${title#"${title%%[![:space:]]*}"}"
  title="${title%"${title##*[![:space:]]}"}"

  if [[ -z "$title" ]]; then
    title="未設定"
  fi

  if (( ${#title} > 24 )); then
    title="${title[1,24]}"
  fi

  printf '%s' "$title"
}

cursor_emit_terminal_title() {
  [[ -n "${CURSOR_TASK_TITLE:-}" ]] || return 0
  cursor_task_is_managed_terminal || return 0
  printf '\033]0;%s\007' "$CURSOR_TASK_TITLE"
  printf '\033]2;%s\007' "$CURSOR_TASK_TITLE"
}

goal() {
  export CURSOR_TASK_TITLE="$(cursor_task_normalize_title "$*")"
  cursor_emit_terminal_title
}

tasktitle() {
  goal "$*"
}

cursor_task_bootstrap() {
  cursor_task_is_managed_terminal || return 0

  if [[ -n "${CURSOR_TASK_SHELL_ACTIVE:-}" ]]; then
    cursor_emit_terminal_title
    return 0
  fi

  export CURSOR_TASK_SHELL_ACTIVE=1

  local initial_title=""
  if [[ -t 0 ]]; then
    printf 'このターミナルのゴール名（20文字目安、空欄で未設定）: '
    IFS= read -r initial_title
  fi

  goal "$initial_title"
  printf 'title: %s\n' "$CURSOR_TASK_TITLE"
  printf "変更するとき: goal '短い名前'\n"
}

typeset -ga precmd_functions
if (( ${precmd_functions[(Ie)cursor_emit_terminal_title]} == 0 )); then
  precmd_functions+=(cursor_emit_terminal_title)
fi

cursor_task_bootstrap
