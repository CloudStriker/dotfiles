#!/usr/bin/env bash
# Install host CLI tools. Safe to run repeatedly: tools already on PATH are skipped.
# Set WITH_NODE=1 to also install nvm + Node.js LTS.
# Not handled here: docker, ~/.secrets, and first-run logins (see README.md).
set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$PATH"

mkdir -p /tmp/agy-work "$HOME/docs-in" "$HOME/mineru-downloads"

# need <command> <install command>: runs the install only if <command> is missing.
need() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "skip $1 (already installed)"
    return
  fi
  echo "install $1"
  bash -c "$2"
}

tools=(uv oh-my-posh opencode claude agy btop fzf zoxide)
apt_tools=(curl unzip btop fzf zoxide)

# report <title>: prints each tool as ok or MISSING and sets $missing to the count.
report() {
  missing=0
  echo "== $1 =="
  for t in "${tools[@]}"; do
    if command -v "$t" >/dev/null 2>&1; then
      echo "  ok       $t"
    else
      echo "  MISSING  $t"
      missing=$((missing + 1))
    fi
  done
}

report "before"

need_apt=0
for t in "${apt_tools[@]}"; do
  if ! command -v "$t" >/dev/null 2>&1; then
    need_apt=1
    break
  fi
done

if [ "$missing" -gt 0 ]; then
  if [ "$need_apt" -eq 1 ]; then
    sudo apt update
    sudo apt install -y ca-certificates curl unzip btop fzf zoxide
  fi
  need uv          'curl -LsSf https://astral.sh/uv/install.sh | sh'
  need oh-my-posh  'curl -s https://ohmyposh.dev/install.sh | bash -s'
  need opencode    'curl -fsSL https://opencode.ai/install | bash'
  need claude      'curl -fsSL https://claude.ai/install.sh | bash'
  need agy         'curl -fsSL https://antigravity.google/cli/install.sh | bash'
fi

if [ "${WITH_NODE:-0}" = "1" ] && [ ! -s "$HOME/.nvm/nvm.sh" ]; then
  curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.41.0/install.sh | bash
  # shellcheck disable=SC1091
  . "$HOME/.nvm/nvm.sh"
  nvm install --lts
fi

hash -r
report "after"
if [ "$missing" -ne 0 ]; then
  echo "$missing tool(s) still missing, check the output above"
  exit 1
fi
echo "done. open a new shell, then sign in: claude, agy, and /connect in opencode"
