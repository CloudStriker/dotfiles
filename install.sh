#!/usr/bin/env bash
# Hook ~/.bashrc.custom into ~/.bashrc and install my tools. Safe to run more than once:
# a tool that is already on PATH is skipped. Add --with-node to install nvm + Node LTS too.
# Not handled here: docker, ~/.secrets, and first-run logins (see README.md).
set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"

line='[ -f ~/.bashrc.custom ] && . ~/.bashrc.custom'
grep -qxF "$line" ~/.bashrc 2>/dev/null || printf '\n%s\n' "$line" >> ~/.bashrc

# need <command> <install command>: runs the install only if <command> is missing.
need() {
  if command -v "$1" >/dev/null 2>&1; then echo "skip $1 (already installed)"; return; fi
  echo "install $1"
  bash -c "$2"
}

sudo apt update
sudo apt install -y ca-certificates curl unzip btop

need uv          'curl -LsSf https://astral.sh/uv/install.sh | sh'
need oh-my-posh  'curl -s https://ohmyposh.dev/install.sh | bash -s'
need opencode    'curl -fsSL https://opencode.ai/install | bash'
need claude      'curl -fsSL https://claude.ai/install.sh | bash'
need agy         'curl -fsSL https://antigravity.google/cli/install.sh | bash'

if [ "${1:-}" = "--with-node" ] && [ ! -s "$HOME/.nvm/nvm.sh" ]; then
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.41.0/install.sh | bash
  . "$HOME/.nvm/nvm.sh"
  nvm install --lts
fi

mkdir -p /tmp/agy-work ~/docs-in ~/mineru-downloads
echo "done. open a new shell, then sign in: claude, agy, and /connect in opencode"
