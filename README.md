# dotfiles

Personal shell environment, CLI tool bootstrap, and universal AI agent configuration for **OpenCode**, **Antigravity (`agy`)**, **Claude Code**, and **Codex CLI**, managed from one repository.

Third-party skills and their licenses are listed in `THIRD-PARTY.md` and `LICENSES/`.

## Quick Start

```bash
git clone git@github.com:CloudStriker/dotfiles.git ~/workspace/personal/dotfiles
cd ~/workspace/personal/dotfiles
./install.sh
```

Controls in interactive terminals:
- `↑` / `↓` (or `j` / `k`): move cursor
- `Space`: toggle selection
- `a`: toggle all / none
- `Enter`: confirm and continue
- `q` / `Ctrl+C`: cancel

Non-interactive terminals fall back automatically to numbered selection. Before modifying any file, `./install.sh` prints an installation plan and asks for `[y/N]` confirmation. Replaced or updated files are backed up under `~/.agent-config-backups/<timestamp>/`.

## Directory Structure

```text
dotfiles/
├── install.sh                    # Launches scripts/install.py
├── scripts/install.py            # Interactive checkbox installer & sync (Python 3 stdlib)
├── shell/
│   ├── bashrc.custom             # PATH, Oh My Posh init, fzf, zoxide
│   ├── clicknow.omp.json         # Oh My Posh prompt theme (needs Nerd Font on client)
│   └── install-tools.sh          # Host tool installer (uv, oh-my-posh, CLIs, optional nvm)
├── skills/                       # 31 portable Agent Skills (SKILL.md)
├── LICENSES/                     # Third-party skill licenses
├── THIRD-PARTY.md                # Attribution for third-party skills
├── rules/
│   ├── AGENTS.md                 # Universal global rules
│   └── opencode-delegation.md    # OpenCode-only delegation, relay & quota rules
├── mcp/
│   └── servers.json              # Canonical MCP manifest (no secrets)
└── agents/
    ├── prompts/                  # Shared role prompt bodies (architect, reviewer, worker, pr-writer)
    └── targets/
        ├── opencode/             # 10 OpenCode agent files (verbatim)
        ├── antigravity.json      # Antigravity agent manifest
        ├── claude.json           # Claude Code agent manifest
        └── codex.json            # Codex CLI agent manifest
```

## Targets & Harness Mapping

### Host & Shell (`shell`, `tools`, `node`)
- **`shell`**: symlinks `~/.bashrc.custom`, hooks it into `~/.bashrc`, symlinks `~/.config/oh-my-posh/themes/clicknow.omp.json`, downloads the Catppuccin Mocha `btop` theme (MIT, `catppuccin/btop`) and sets `color_theme = "catppuccin_mocha"` in `~/.config/btop/btop.conf`, and ensures `/tmp/agy-work`, `~/docs-in`, and `~/mineru-downloads` exist.
- **`tools`**: runs `shell/install-tools.sh` to install any missing tools (`uv`, `oh-my-posh`, `opencode`, `claude`, `agy`, `btop`, `fzf`, `zoxide`).
- **`node`**: optionally installs `nvm` (`v0.41.0`) and Node.js LTS.

### AI Harnesses

| Component | OpenCode | Antigravity (`agy`) | Claude Code | Codex CLI |
|---|---|---|---|---|
| **Skills** | `~/.agents/skills/` (native) | `~/.gemini/config/skills.json` -> resolved absolute path of `~/.agents/skills` | Per-skill symlinks in `~/.claude/skills/` | `~/.agents/skills/` (native) |
| **Rules** | `instructions` in `~/.config/opencode/opencode.json` (`~/.agents/AGENTS.md` + `opencode-delegation.md`) | `~/.gemini/AGENTS.md` -> `~/.agents/AGENTS.md` | `~/.claude/CLAUDE.md` -> `~/.agents/AGENTS.md` | `~/.codex/AGENTS.md` -> `~/.agents/AGENTS.md` |
| **MCP** | `mcp.servers` in `~/.config/opencode/opencode.json` (`{file:...}`) | `mcpServers` in `~/.gemini/config/mcp_config.json` (`0600`) | `mcpServers` in `~/.claude.json` (`0600`) | `[mcp_servers.*]` block in `~/.codex/config.toml` (`0600`) |
| **Subagents** | Symlinks in `~/.config/opencode/agents/*.md` | Rendered `.md` in `~/.gemini/config/agents/` | Rendered `.md` in `~/.claude/agents/` | Rendered `.toml` in `~/.codex/agents/` + `[agents.*]` block |

## Model Whitelist

Subagent models follow the approved roster without substitution:

| Harness | Subagents & Models |
|---|---|
| **OpenCode** | All 10 existing agents preserved verbatim (`architect`: `claude-agent/opus#medium`, `worker-sonnet`: `claude-agent/sonnet#medium`, `worker-haiku` / `pr-writer`: `claude-agent/haiku#low`, `openai-reviewer`: `openai/gpt-6-luna#medium`, `worker-free`: `opencode/deepseek-v4.1-flash-free`, `worker`: `deepseek/deepseek-flash#none`, plus `agy-neon`, `agy-hydrogen`, `agy-argon` relays) |
| **Antigravity** | `architect`, `reviewer`, `worker`, `pr-writer` all set to `model: inherit` (inherits the active session model) |
| **Claude Code** | `architect` (`opus`), `reviewer` (`sonnet`), `worker` (`sonnet`), `worker-haiku` (`haiku`), `pr-writer` (`haiku`) |
| **Codex CLI** | `architect`, `reviewer`, `worker`, `pr_writer` all set to `gpt-6-luna` (use `gpt-5.6-luna` manually as fallback if needed) |

## Secrets Setup

No API keys are stored in this repository. Create `~/.secrets/` with restrictive permissions before syncing MCP servers:

```bash
umask 077
mkdir -p ~/.secrets && chmod 700 ~/.secrets
for name in context7_key exa_key mineru_token; do
  read -rsp "$name (Enter to skip): " v; echo
  [ -n "$v" ] && printf '%s' "$v" > ~/.secrets/$name
done
unset v
ls -l ~/.secrets
```

- **OpenCode** reads keys dynamically at runtime via `{file:~/.secrets/...}`.
- **Antigravity, Claude Code, and Codex CLI** do not support `{file:...}` syntax, so `./install.sh` resolves keys locally into `~/.gemini/config/mcp_config.json`, `~/.claude.json`, and `~/.codex/config.toml` with `0600` permissions. Never commit those generated files.
- If `context7_key` or `exa_key` is missing, those required servers are skipped for non-OpenCode harnesses.
- Firecrawl uses browser OAuth (`/mcp` in `agy` and `claude`), and each CLI handles its own sign-in (`claude`, `agy`, `/connect` in `opencode`).

## MinerU (Docker Host Prerequisite)

The `mineru` MCP server runs `mineru-open-mcp` inside a Docker container mounted only to `~/docs-in` (read-only) and `~/mineru-downloads` (read-write):

1. Install Docker Engine from https://docs.docker.com/engine/install/ubuntu/ and configure rootless/non-sudo `docker` access (https://docs.docker.com/engine/install/linux-postinstall/).
2. Optionally create a token at https://mineru.net/apiManage/token and save it to `~/.secrets/mineru_token` (without it, `mineru` falls back to free mode: ~20 pages and 10 MB per file).
3. Put files in `~/docs-in` before asking an agent to parse them. Do not upload confidential documents.
