if [[ -f "$HOME/.zprofile" && "$HOME/.zprofile" != "$ZDOTDIR/.zprofile" ]]; then
  source "$HOME/.zprofile"
fi
