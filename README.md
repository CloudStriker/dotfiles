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

`dot checkout` also brings the third-party skills in `.config/opencode/skills/`, so they do not need to be installed separately.

## Not in this repo (recreate by hand)

- `~/.secrets/context7_key`, `~/.secrets/exa_key`, and `~/.secrets/mineru_token` (see "Secrets" below)
- Binaries: `uv`, `oh-my-posh`, `opencode`, `claude`, `agy`, `btop`, and optionally `nvm` (see "Install tools" below), plus `docker` (see "MinerU")
- `mkdir -p /tmp/agy-work ~/docs-in ~/mineru-downloads`

## Install tools
Do this before opening a new shell, because `.bashrc` runs `oh-my-posh` at startup.
Both tools install to `~/.local/bin`, which `.bashrc` already adds to `PATH`.

Each command below downloads a script and runs it. Read a script first with `curl ... | less`
if you want to check it.

`uv` (https://docs.astral.sh/uv/getting-started/installation/):

    curl -LsSf https://astral.sh/uv/install.sh | sh

To pin a version, put it in the URL, for example `https://astral.sh/uv/0.13.7/install.sh`.
Without `curl`, use `wget -qO- https://astral.sh/uv/install.sh | sh`.

Oh My Posh (https://ohmyposh.dev/docs/installation/linux). The installer needs `curl`,
`unzip`, `realpath`, and `dirname`:

    sudo apt update && sudo apt install -y ca-certificates curl unzip
    curl -s https://ohmyposh.dev/install.sh | bash -s

`realpath` and `dirname` come with `coreutils`, which Ubuntu already has. The docs ask for an
up to date `curl` and certificate store before running the script, which the `apt` line covers.

The theme `~/.config/oh-my-posh/themes/clicknow.omp.json` and the `eval` line in `.bashrc`
come with `dot checkout`. Its icons need a Nerd Font in the terminal app on the machine you
connect from, not on the server.

Check both:

    uv --version
    oh-my-posh version

### Agents and CLIs
- OpenCode: follow https://opencode.ai/docs/ (npm package, standalone binary, or Docker).
  Connect each provider again with `/connect` in the TUI. Logins are not stored in this repo.
- Claude Code (https://code.claude.com/docs/en/setup):

      curl -fsSL https://claude.ai/install.sh | bash

  Run `claude` once to sign in.
- Antigravity CLI `agy` (https://antigravity.google/docs/getting-started/):

      curl -fsSL https://antigravity.google/cli/install.sh | bash

  It installs to `~/.local/bin/agy`. The first run asks you to sign in.
- `btop`, from Ubuntu's own repository. Its theme is in the last section:

      sudo apt install -y btop

### Optional: Node.js
`.bashrc` loads `nvm` only if it exists, so skip this unless a tool asks for Node.
Installer version and docs: https://github.com/nvm-sh/nvm

    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash
    . ~/.nvm/nvm.sh        # or open a new terminal; `nvm` is a shell function
    nvm install --lts

The installer already finds the `nvm` lines in `.bashrc`, so it does not add them twice.

## Secrets

`opencode.json` reads each key from a file with `{file:~/.secrets/<name>}`, so no key is stored in this repo. Get each key from its provider's dashboard (Context7, Exa, MinerU), then save them like this:

    umask 077
    mkdir -p ~/.secrets && chmod 700 ~/.secrets
    for name in context7_key exa_key mineru_token; do
      read -rsp "$name (Enter to skip): " v; echo
      [ -n "$v" ] && printf '%s' "$v" > ~/.secrets/$name
    done
    unset v
    ls -l ~/.secrets

- `read -s` keeps the key off the screen and out of shell history. Do not paste a key into a command line.
- `printf '%s'` writes the key with no trailing newline.
- `ls -l` should show `-rw-------` for each file and `drwx------` for the folder.
- Firecrawl uses OAuth in the browser, so it has no key file. `agy` and `claude` log in on their own.
- Anything under `~/.secrets/` is blocked for the agents by the rules in `opencode.json`, and `.gitignore` keeps it out of this repo.

## MinerU (PDF and Office to Markdown)

The `mineru` MCP server in `opencode.json` is the official `mineru-open-mcp`. OpenCode starts it in a Docker container, so it can only see two folders:

- `~/docs-in`: input files, mounted read-only
- `~/mineru-downloads`: results, mounted read-write

Setup:

1. Create an API token at https://mineru.net/apiManage/token and save it to `~/.secrets/mineru_token`.
2. Install Docker Engine by following the official guide for Ubuntu:
   https://docs.docker.com/engine/install/ubuntu/
   Do not use `sudo apt install docker` or `docker.io`; those are not Docker's own packages.
   Then let your user run `docker` without `sudo`:
   https://docs.docker.com/engine/install/linux-postinstall/
   OpenCode pulls the container image on first start.
3. Put files in `~/docs-in`, then ask the agent to parse them.

Without a token the server falls back to a free mode with about 20 pages and 10 MB per file. Every parsed file is uploaded to mineru.net, so do not use it for confidential documents. The paths in `opencode.json` use `{env:HOME}`, so nothing there is tied to one username.

## btop theme (Catppuccin Mocha)

Source: https://github.com/catppuccin/btop (MIT)

    mkdir -p ~/.config/btop/themes
    curl -fsSL https://raw.githubusercontent.com/catppuccin/btop/main/themes/catppuccin_mocha.theme \
      -o ~/.config/btop/themes/catppuccin_mocha.theme

Then in `~/.config/btop/btop.conf` set `color_theme = "catppuccin_mocha"` (or select it from btop's options menu).
