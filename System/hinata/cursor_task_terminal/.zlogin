if [[ -f "$HOME/.zlogin" && "$HOME/.zlogin" != "$ZDOTDIR/.zlogin" ]]; then
  source "$HOME/.zlogin"
fi
