if [[ -f "$HOME/.zshenv" && "$HOME/.zshenv" != "$ZDOTDIR/.zshenv" ]]; then
  source "$HOME/.zshenv"
fi
