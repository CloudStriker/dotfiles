# dotfiles

Bare-repo dotfiles: OpenCode config, agents, rules, skills, and shell setup.

## Restore
    git clone --bare git@github.com:CloudStriker/dotfiles.git ~/.dotfiles
    alias dot='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
    dot checkout            # move conflicting old files away first
    dot config status.showUntrackedFiles no

## Not in this repo (recreate by hand)
- `~/.secrets/context7_key` and `~/.secrets/exa_key` (`chmod 600`)
- Binaries: `uv`, `agy`, `claude`, `oh-my-posh`, `nvm`
- `mkdir -p /tmp/agy-work`

## btop theme (Catppuccin Mocha)
Source: https://github.com/catppuccin/btop (MIT)

    mkdir -p ~/.config/btop/themes
    curl -fsSL https://raw.githubusercontent.com/catppuccin/btop/main/themes/catppuccin_mocha.theme \
      -o ~/.config/btop/themes/catppuccin_mocha.theme

Then in `~/.config/btop/btop.conf` set `color_theme = "catppuccin_mocha"` (or select it from btop's options menu).
