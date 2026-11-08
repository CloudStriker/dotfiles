# dotfiles

Bare-repo dotfiles: OpenCode config, agents, rules, skills, and shell setup.

Third-party skills and their licenses: `.config/opencode/skills/THIRD-PARTY.md`

## Restore
Use SSH if you have a key on GitHub, otherwise HTTPS:

    git clone --bare git@github.com:CloudStriker/dotfiles.git ~/.dotfiles
    # or
    git clone --bare https://github.com/CloudStriker/dotfiles.git ~/.dotfiles

    alias dot='git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
    dot checkout            # move conflicting old files away first
    dot config status.showUntrackedFiles no

`dot checkout` also brings the third-party skills in `.config/opencode/skills/`,
so they do not need to be installed separately.

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
