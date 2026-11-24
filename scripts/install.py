#!/usr/bin/env python3
"""Interactive unified dotfiles and multi-harness AI config installer."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import select
import shutil
import subprocess
import sys
import tempfile
import termios
import tomllib
import tty
import urllib.request

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGETS: list[tuple[str, str]] = [
    ("shell", "Shell & Host Config (.bashrc.custom, Oh My Posh, btop theme)"),
    ("tools", "Install CLI Tools (uv, oh-my-posh, btop, fzf, zoxide, AI CLIs)"),
    ("node", "Install Node.js LTS via nvm (optional)"),
    ("opencode", "OpenCode"),
    ("antigravity", "Antigravity (agy)"),
    ("claude", "Claude Code"),
    ("codex", "Codex CLI"),
]

AI_TARGETS = ("opencode", "antigravity", "claude", "codex")
HOST_TOOLS = ("uv", "oh-my-posh", "opencode", "claude", "agy", "btop", "fzf", "zoxide")
BTOP_THEME_URL = "https://raw.githubusercontent.com/catppuccin/btop/main/themes/catppuccin_mocha.theme"

COMPONENTS: list[tuple[str, str]] = [
    ("skills", "Skills (~/.agents/skills/)"),
    ("rules", "Rules (AGENTS.md & OpenCode delegation)"),
    ("mcp", "MCP Servers (from mcp/servers.json + ~/.secrets)"),
    ("subagents", "Subagents (per-harness)"),
]

OPENCODE_SCHEMA = "https://opencode.ai/config.json"
OPENCODE_PERMISSIONS = [
    {"action": "read", "resource": "*.secrets/*", "effect": "deny"},
    {"action": "edit", "resource": "*.secrets/*", "effect": "deny"},
    {"action": "shell", "resource": "*.secrets*", "effect": "deny"},
    {"action": "experimental_image_generate", "resource": "*", "effect": "deny"},
]

MCP_START = "# >>> agent-config:mcp start >>>"
MCP_END = "# <<< agent-config:mcp end <<<"
AGENTS_START = "# >>> agent-config:agents start >>>"
AGENTS_END = "# <<< agent-config:agents end <<<"


class InstallError(RuntimeError):
    """Raised when configuration loading or validation fails safely."""


def _extended_path(home: Path) -> str:
    """Return PATH prepended with ~/.local/bin and ~/.opencode/bin."""
    extra = [str(home / ".local" / "bin"), str(home / ".opencode" / "bin")]
    existing = os.environ.get("PATH", "")
    return os.pathsep.join(extra + ([existing] if existing else []))


def detect_targets(home: Path) -> dict[str, bool]:
    """Detect installed or previously configured AI harnesses."""
    ext_path = _extended_path(home)
    return {
        "opencode": shutil.which("opencode", path=ext_path) is not None
        or (home / ".config" / "opencode").exists(),
        "antigravity": shutil.which("agy", path=ext_path) is not None
        or (home / ".gemini").exists(),
        "claude": shutil.which("claude", path=ext_path) is not None
        or (home / ".claude").exists(),
        "codex": shutil.which("codex", path=ext_path) is not None
        or (home / ".codex").exists(),
    }


def build_target_items(home: Path) -> tuple[list[dict[str, str]], set[str]]:
    """Build target checkbox metadata and default selections."""
    ext_path = _extended_path(home)
    missing_tools = sum(1 for t in HOST_TOOLS if shutil.which(t, path=ext_path) is None)
    has_node = (home / ".nvm" / "nvm.sh").is_file()
    detected_ai = detect_targets(home)

    notes = {
        "shell": "",
        "tools": "all installed" if missing_tools == 0 else f"{missing_tools} missing",
        "node": "installed" if has_node else "",
        "opencode": "detected" if detected_ai["opencode"] else "",
        "antigravity": "detected" if detected_ai["antigravity"] else "",
        "claude": "detected" if detected_ai["claude"] else "",
        "codex": "detected" if detected_ai["codex"] else "",
    }
    defaults = {"shell"}
    if missing_tools > 0:
        defaults.add("tools")
    for tid in AI_TARGETS:
        if detected_ai[tid]:
            defaults.add(tid)

    items = [{"id": tid, "label": label, "note": notes[tid]} for tid, label in TARGETS]
    return items, defaults


def _read_key(fd: int) -> str:
    """Read one logical key press (including arrow escape sequences) in raw mode."""
    b = os.read(fd, 1)
    if b == b"\x03":
        return "CANCEL"
    if b in (b"\r", b"\n"):
        return "ENTER"
    if b == b" ":
        return "SPACE"
    if b == b"\x1b":
        ready, _, _ = select.select([fd], [], [], 0.05)
        if not ready:
            return "CANCEL"
        seq = os.read(fd, 1)
        if seq in (b"[", b"O"):
            ready2, _, _ = select.select([fd], [], [], 0.05)
            if ready2:
                code = os.read(fd, 1)
                if code == b"A":
                    return "UP"
                if code == b"B":
                    return "DOWN"
        return "ESC"
    ch = b.decode("utf-8", errors="ignore").lower()
    if ch == "k":
        return "UP"
    if ch == "j":
        return "DOWN"
    if ch == "a":
        return "ALL"
    if ch == "q":
        return "CANCEL"
    return ""


def _render_checkbox_menu(
    title: str,
    items: list[dict[str, str]],
    selected: set[str],
    cursor: int,
    prev_lines: int,
) -> int:
    """Render checkbox menu in place and return the number of lines printed."""
    lines = [
        f"\033[1m{title}\033[0m",
        "  [↑/↓] move  [Space] toggle  [a] all/none  [Enter] continue  [q] cancel",
    ]
    for idx, item in enumerate(items):
        pointer = ">" if idx == cursor else " "
        mark = "x" if item["id"] in selected else " "
        note = f" ({item['note']})" if item.get("note") else ""
        lines.append(f"  {pointer} [{mark}] {item['label']}{note}")

    if prev_lines > 0:
        sys.stdout.write(f"\033[{prev_lines}A\r\033[J")
    sys.stdout.write("\r\n".join(lines) + "\r\n")
    sys.stdout.flush()
    return len(lines)


def _checkbox_tty(
    title: str,
    items: list[dict[str, str]],
    selected: set[str],
) -> list[str]:
    """Run raw-mode interactive checkbox menu."""
    fd = sys.stdin.fileno()
    old_attrs = termios.tcgetattr(fd)
    cursor = 0
    prev_lines = 0
    try:
        tty.setraw(fd)
        sys.stdout.write("\033[?25l")
        sys.stdout.flush()
        prev_lines = _render_checkbox_menu(title, items, selected, cursor, 0)
        while True:
            key = _read_key(fd)
            if key == "CANCEL":
                raise KeyboardInterrupt
            if key == "UP":
                cursor = (cursor - 1) % len(items)
            elif key == "DOWN":
                cursor = (cursor + 1) % len(items)
            elif key == "SPACE":
                item_id = items[cursor]["id"]
                if item_id in selected:
                    selected.remove(item_id)
                else:
                    selected.add(item_id)
            elif key == "ALL":
                all_ids = {item["id"] for item in items}
                if selected == all_ids:
                    selected.clear()
                else:
                    selected.update(all_ids)
            elif key == "ENTER":
                return [item["id"] for item in items if item["id"] in selected]
            else:
                continue
            prev_lines = _render_checkbox_menu(title, items, selected, cursor, prev_lines)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_attrs)
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def _checkbox_fallback(
    title: str,
    items: list[dict[str, str]],
    selected: set[str],
) -> list[str]:
    """Numbered fallback menu for non-TTY stdin/stdout."""
    print(f"\n{title}")
    for idx, item in enumerate(items, start=1):
        parts = [p for p in (item.get("note", ""), "default" if item["id"] in selected else "") if p]
        suffix = f" ({', '.join(parts)})" if parts else ""
        print(f"  [{idx}] {item['label']}{suffix}")

    try:
        raw = input("Select numbers (e.g. '1 2', 'all', 'none', Enter=default): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise KeyboardInterrupt

    if raw == "":
        chosen = set(selected)
    elif raw == "all":
        chosen = {item["id"] for item in items}
    elif raw == "none":
        chosen = set()
    else:
        chosen = set()
        for token in re.split(r"[\s,]+", raw):
            if not token:
                continue
            if token.isdigit():
                idx = int(token) - 1
                if 0 <= idx < len(items):
                    chosen.add(items[idx]["id"])
                else:
                    print(f"Warning: unknown number '{token}', skipped.")
            else:
                print(f"Warning: unknown input '{token}', skipped.")
    return [item["id"] for item in items if item["id"] in chosen]


def checkbox_menu(
    title: str,
    items: list[dict[str, str]],
    default_selected: set[str],
) -> list[str]:
    """Show checkbox selection using TTY raw mode or numbered fallback."""
    selected = set(default_selected)
    if sys.stdin.isatty() and sys.stdout.isatty():
        return _checkbox_tty(title, items, selected)
    return _checkbox_fallback(title, items, selected)


class BackupManager:
    """Backs up modified or replaced paths at most once per run."""

    def __init__(self, home: Path) -> None:
        self.home = home
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.root = home / ".agent-config-backups" / stamp
        self.backed_up: set[Path] = set()

    def backup_once(self, path: Path, secure: bool = False) -> Path | None:
        """Move an existing file, dir, or symlink into the backup directory."""
        if path in self.backed_up:
            return None
        if not path.exists() and not path.is_symlink():
            return None

        try:
            rel = path.relative_to(self.home)
        except ValueError:
            rel = Path(path.name)

        dest = self.root / rel
        if dest.exists() or dest.is_symlink():
            counter = 1
            while (self.root / f"{rel}.{counter}").exists():
                counter += 1
            dest = self.root / f"{rel}.{counter}"

        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        dest.parent.mkdir(parents=True, exist_ok=True)

        if path.is_symlink():
            dest.symlink_to(os.readlink(path))
            path.unlink()
        else:
            shutil.move(str(path), str(dest))
            if secure and dest.is_file():
                os.chmod(dest, 0o600)

        self.backed_up.add(path)
        return dest


def copy_for_backup(path: Path, backup_mgr: BackupManager, secure: bool = False) -> Path | None:
    """Create a backup copy of a file that will be updated in-place."""
    if path in backup_mgr.backed_up or not path.exists():
        return None
    try:
        rel = path.relative_to(backup_mgr.home)
    except ValueError:
        rel = Path(path.name)

    dest = backup_mgr.root / rel
    backup_mgr.root.mkdir(parents=True, exist_ok=True)
    os.chmod(backup_mgr.root, 0o700)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, dest)
    if secure and dest.is_file():
        os.chmod(dest, 0o600)
    backup_mgr.backed_up.add(path)
    return dest


def ensure_symlink(link: Path, target: Path, backup_mgr: BackupManager) -> str:
    """Ensure `link` symlinks to `target.resolve()`, backing up conflicts."""
    resolved_target = target.resolve()
    if link.is_symlink():
        if link.exists() and link.resolve() == resolved_target:
            return "unchanged"
        backup_mgr.backup_once(link)
    elif link.exists():
        backup_mgr.backup_once(link)

    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(resolved_target)
    return "linked"


def atomic_write(path: Path, content: str, mode: int | None = None) -> None:
    """Write text atomically via same-directory temp file with chmod before replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.chmod(tmp_path, mode if mode is not None else 0o644)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def load_json_dict(path: Path) -> dict:
    """Load JSON object, treating missing or empty file as {}."""
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InstallError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise InstallError(f"Root JSON in {path} must be an object.")
    return data


def read_secret(secret_ref: str, home: Path) -> str | None:
    """Resolve ~/ secret path relative to `home` and return stripped secret or None."""
    if secret_ref.startswith("~/"):
        secret_path = home / secret_ref[2:]
    else:
        secret_path = Path(secret_ref)
    if not secret_path.is_file():
        return None
    val = secret_path.read_text(encoding="utf-8").rstrip("\r\n")
    return val if val else None


def discover_skills() -> list[Path]:
    """Return sorted list of valid skill directories inside repo/skills/."""
    skills_dir = REPO_ROOT / "skills"
    if not skills_dir.is_dir():
        return []
    return [
        entry
        for entry in sorted(skills_dir.iterdir())
        if entry.is_dir() and (entry / "SKILL.md").is_file()
    ]


def load_mcp_manifest() -> dict[str, dict]:
    """Load canonical MCP server definitions from mcp/servers.json."""
    manifest = load_json_dict(REPO_ROOT / "mcp" / "servers.json")
    servers = manifest.get("servers", {})
    if not isinstance(servers, dict):
        raise InstallError("mcp/servers.json must contain a 'servers' object.")
    return servers


def _yaml_scalar(value: str | bool | int) -> str:
    """Format a scalar YAML value cleanly."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if re.fullmatch(r"[A-Za-z0-9_.-]+", value):
        return value
    return json.dumps(value)


def render_yaml_frontmatter(fields: dict[str, object], body: str) -> str:
    """Render Markdown file with YAML frontmatter."""
    lines = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            if key in ("tools", "disallowedTools"):
                lines.append(f"{key}: {json.dumps(val)}")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {_yaml_scalar(item)}")
        else:
            lines.append(f"{key}: {_yaml_scalar(val)}")
    lines.append("---")
    lines.append("")
    return "\n".join(lines) + body.rstrip("\n") + "\n"


def _toml_key(key: str) -> str:
    """Quote a TOML key if it is not a bare key."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    return json.dumps(key)


def _toml_str(value: str) -> str:
    """Format a single-line TOML string safely."""
    return json.dumps(value)


def _toml_inline_table(mapping: dict[str, str]) -> str:
    """Format a flat string-to-string TOML inline table."""
    pairs = [f"{_toml_key(k)} = {_toml_str(v)}" for k, v in mapping.items()]
    return "{ " + ", ".join(pairs) + " }"


def _toml_multiline(text: str) -> str:
    """Format a TOML multiline basic string safely for any content."""
    escaped = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    if escaped.endswith('"'):
        escaped = escaped[:-1] + '\\"'
    return '"""\n' + escaped.rstrip("\n") + '\n"""'


def _strip_managed_block(text: str, start_marker: str, end_marker: str) -> str:
    """Remove an existing managed block (if any) from text cleanly."""
    pattern = re.compile(
        r"\n?" + re.escape(start_marker) + r".*?" + re.escape(end_marker) + r"\n?",
        flags=re.DOTALL,
    )
    cleaned = re.sub(pattern, "\n", text).strip("\n")
    return cleaned + "\n" if cleaned else ""


def _upsert_managed_block(
    existing: str,
    start_marker: str,
    end_marker: str,
    block_body: str,
) -> str:
    """Replace or append a delimited managed block inside a config file."""
    cleaned = _strip_managed_block(existing, start_marker, end_marker).rstrip("\n")
    wrapped = f"{start_marker}\n{block_body.rstrip()}\n{end_marker}"
    if not cleaned:
        return wrapped + "\n"
    return cleaned + "\n\n" + wrapped + "\n"


def install_skills(
    targets: list[str],
    home: Path,
    backup_mgr: BackupManager,
    notes: list[str],
) -> None:
    """Install skills into ~/.agents/skills and link selected harnesses."""
    skills = discover_skills()
    agents_skills = home / ".agents" / "skills"
    agents_skills.mkdir(parents=True, exist_ok=True)

    for skill_dir in skills:
        ensure_symlink(agents_skills / skill_dir.name, skill_dir, backup_mgr)

    if "antigravity" in targets:
        skills_json = home / ".gemini" / "config" / "skills.json"
        data = load_json_dict(skills_json)
        entries = data.get("entries")
        if entries is None:
            entries = []
        if not isinstance(entries, list):
            raise InstallError(f"'entries' in {skills_json} must be an array.")

        target_resolved = agents_skills.resolve()
        abs_skills_path = str(target_resolved)
        normalized: list[object] = []
        added = False
        for e in entries:
            is_match = (
                isinstance(e, dict)
                and isinstance(e.get("path"), str)
                and (
                    e["path"] == "~/.agents/skills"
                    or (
                        home / e["path"][2:]
                        if e["path"].startswith("~/")
                        else Path(e["path"])
                    ).resolve()
                    == target_resolved
                )
            )
            if is_match:
                if not added:
                    updated_entry = dict(e)
                    updated_entry["path"] = abs_skills_path
                    normalized.append(updated_entry)
                    added = True
            else:
                normalized.append(e)
        if not added:
            normalized.append({"path": abs_skills_path})

        data["entries"] = normalized
        rendered = json.dumps(data, indent=2) + "\n"
        if not skills_json.exists() or skills_json.read_text(encoding="utf-8") != rendered:
            if skills_json.exists() and skills_json.stat().st_size > 0:
                copy_for_backup(skills_json, backup_mgr)
            atomic_write(skills_json, rendered)

    if "claude" in targets:
        claude_skills = home / ".claude" / "skills"
        claude_skills.mkdir(parents=True, exist_ok=True)
        for skill_dir in skills:
            ensure_symlink(claude_skills / skill_dir.name, agents_skills / skill_dir.name, backup_mgr)

    if "opencode" in targets:
        legacy_oc_skills = home / ".config" / "opencode" / "skills"
        if legacy_oc_skills.exists() and not legacy_oc_skills.is_symlink():
            notes.append(
                f"OpenCode: legacy directory {legacy_oc_skills} still exists. "
                "OpenCode already reads ~/.agents/skills/ natively; remove the old folder after verifying."
            )


def _ensure_opencode_json(
    home: Path,
    backup_mgr: BackupManager,
    instructions: list[str] | None = None,
    mcp: dict | None = None,
) -> None:
    """Create or update ~/.config/opencode/opencode.json safely."""
    oc_path = home / ".config" / "opencode" / "opencode.json"
    data = load_json_dict(oc_path)

    if "$schema" not in data:
        data["$schema"] = OPENCODE_SCHEMA
    if mcp is not None:
        mcp_obj: dict[str, object] = {}
        existing_mcp = data.get("mcp")
        if isinstance(existing_mcp, dict) and "timeout" in existing_mcp:
            mcp_obj["timeout"] = existing_mcp["timeout"]
        mcp_obj["servers"] = mcp["servers"]
        data["mcp"] = mcp_obj
    if instructions is not None:
        data["instructions"] = instructions
    if "permissions" not in data:
        data["permissions"] = OPENCODE_PERMISSIONS

    rendered = json.dumps(data, indent=2) + "\n"
    if oc_path.exists() and oc_path.read_text(encoding="utf-8") == rendered:
        return
    copy_for_backup(oc_path, backup_mgr)
    atomic_write(oc_path, rendered)


def install_rules(targets: list[str], home: Path, backup_mgr: BackupManager) -> None:
    """Install universal AGENTS.md and target rule symlinks."""
    shared_rules = home / ".agents" / "AGENTS.md"
    ensure_symlink(shared_rules, REPO_ROOT / "rules" / "AGENTS.md", backup_mgr)

    if "opencode" in targets:
        delegation_dst = home / ".config" / "opencode" / "rules" / "opencode-delegation.md"
        ensure_symlink(delegation_dst, REPO_ROOT / "rules" / "opencode-delegation.md", backup_mgr)
        _ensure_opencode_json(
            home,
            backup_mgr,
            instructions=[
                "~/.agents/AGENTS.md",
                "~/.config/opencode/rules/opencode-delegation.md",
            ],
        )

    if "antigravity" in targets:
        ensure_symlink(home / ".gemini" / "AGENTS.md", shared_rules, backup_mgr)
    if "claude" in targets:
        ensure_symlink(home / ".claude" / "CLAUDE.md", shared_rules, backup_mgr)
    if "codex" in targets:
        ensure_symlink(home / ".codex" / "AGENTS.md", shared_rules, backup_mgr)


def _expand_args(args: list[str], home_str: str) -> list[str]:
    """Expand {HOME} placeholders in stdio argument lists."""
    return [arg.replace("{HOME}", home_str) for arg in args]


def _drop_env_flag(args: list[str], env_name: str) -> list[str]:
    """Remove `-e ENV_NAME` flag pair from docker-style args when optional secret is absent."""
    result: list[str] = []
    skip_next = False
    for i, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg == "-e" and i + 1 < len(args) and args[i + 1] == env_name:
            skip_next = True
            continue
        result.append(arg)
    return result


def _resolve_server_runtime(
    name: str,
    spec: dict,
    home: Path,
    warnings: list[str],
) -> dict | None:
    """Resolve a canonical server definition with local secrets for non-OpenCode harnesses."""
    transport = spec["transport"]
    if transport == "http":
        entry: dict[str, object] = {"transport": "http", "url": spec["url"]}
        auth = spec.get("auth")
        if auth:
            secret = read_secret(auth["secret_file"], home)
            if secret is None:
                if auth.get("required", True):
                    warnings.append(
                        f"MCP '{name}' skipped for non-OpenCode targets because {auth['secret_file']} is missing or empty."
                    )
                    return None
            else:
                entry["headers"] = {"Authorization": f"Bearer {secret}"}
        return entry

    if transport == "stdio":
        args = _expand_args(list(spec.get("args", [])), str(home))
        env: dict[str, str] = {}
        for env_key, env_spec in spec.get("env_secret_files", {}).items():
            secret = read_secret(env_spec["secret_file"], home)
            if secret is None:
                if env_spec.get("required", False):
                    warnings.append(
                        f"MCP '{name}' skipped because {env_spec['secret_file']} is missing or empty."
                    )
                    return None
                args = _drop_env_flag(args, env_key)
                warnings.append(
                    f"MCP '{name}' configured without {env_key} ({env_spec['secret_file']} missing; free mode)."
                )
            else:
                env[env_key] = secret
        entry = {
            "transport": "stdio",
            "command": spec["command"],
            "args": args,
        }
        if env:
            entry["env"] = env
        return entry

    raise InstallError(f"Unknown MCP transport for '{name}': {transport}")


def _build_opencode_mcp(servers: dict[str, dict]) -> dict[str, dict]:
    """Render OpenCode v2 MCP section using native {file:...} and {env:HOME} placeholders."""
    rendered: dict[str, dict] = {}
    for name, spec in servers.items():
        if spec["transport"] == "http":
            entry: dict[str, object] = {"type": "remote", "url": spec["url"]}
            auth = spec.get("auth")
            if auth:
                entry["headers"] = {"Authorization": f"Bearer {{file:{auth['secret_file']}}}"}
            rendered[name] = entry
        elif spec["transport"] == "stdio":
            entry = {
                "type": "local",
                "command": [spec["command"]] + _expand_args(list(spec.get("args", [])), "{env:HOME}"),
            }
            env_map = {
                env_key: f"{{file:{env_spec['secret_file']}}}"
                for env_key, env_spec in spec.get("env_secret_files", {}).items()
            }
            if env_map:
                entry["environment"] = env_map
            rendered[name] = entry
    return {"servers": rendered}


def _render_codex_mcp_toml(resolved_servers: dict[str, dict]) -> str:
    """Render [mcp_servers.*] TOML tables for Codex CLI."""
    blocks: list[str] = []
    for name, srv in resolved_servers.items():
        lines = [f"[mcp_servers.{_toml_key(name)}]"]
        if srv["transport"] == "http":
            lines.append(f"url = {_toml_str(srv['url'])}")
            if "headers" in srv:
                lines.append(f"http_headers = {_toml_inline_table(srv['headers'])}")
        else:
            lines.append(f"command = {_toml_str(srv['command'])}")
            args_list = ", ".join(_toml_str(a) for a in srv["args"])
            lines.append(f"args = [{args_list}]")
            if "env" in srv:
                lines.append(f"env = {_toml_inline_table(srv['env'])}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _update_codex_config(
    home: Path,
    backup_mgr: BackupManager,
    start_marker: str,
    end_marker: str,
    block_body: str,
) -> None:
    """Update a delimited block in ~/.codex/config.toml and validate with tomllib."""
    cfg_path = home / ".codex" / "config.toml"
    existing = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
    updated = _upsert_managed_block(existing, start_marker, end_marker, block_body)
    try:
        tomllib.loads(updated)
    except tomllib.TOMLDecodeError as exc:
        raise InstallError(f"TOML validation failed for {cfg_path}: {exc}") from exc

    if cfg_path.exists() and existing == updated:
        os.chmod(cfg_path, 0o600)
        return
    copy_for_backup(cfg_path, backup_mgr, secure=True)
    atomic_write(cfg_path, updated, mode=0o600)


def _merge_mcp_servers_json(
    cfg_path: Path,
    resolved: dict[str, dict],
    url_key: str,
    include_types: bool,
    backup_mgr: BackupManager,
) -> None:
    """Merge resolved MCP entries into a JSON file's mcpServers object."""
    data = load_json_dict(cfg_path)
    mcp_servers = data.get("mcpServers")
    if mcp_servers is None:
        mcp_servers = {}
    if not isinstance(mcp_servers, dict):
        raise InstallError(f"'mcpServers' in {cfg_path} must be an object.")

    for name, srv in resolved.items():
        if srv["transport"] == "http":
            entry: dict[str, object] = {url_key: srv["url"]}
            if include_types:
                entry["type"] = "http"
            if "headers" in srv:
                entry["headers"] = srv["headers"]
        else:
            entry = {"command": srv["command"], "args": srv["args"]}
            if include_types:
                entry["type"] = "stdio"
            if "env" in srv:
                entry["env"] = srv["env"]
        mcp_servers[name] = entry
    data["mcpServers"] = mcp_servers

    rendered = json.dumps(data, indent=2) + "\n"
    if cfg_path.exists() and cfg_path.read_text(encoding="utf-8") == rendered:
        os.chmod(cfg_path, 0o600)
        return
    if cfg_path.exists() and cfg_path.stat().st_size > 0:
        copy_for_backup(cfg_path, backup_mgr, secure=True)
    atomic_write(cfg_path, rendered, mode=0o600)


def install_mcp(
    targets: list[str],
    home: Path,
    backup_mgr: BackupManager,
    warnings: list[str],
) -> None:
    """Install MCP configurations across selected harnesses."""
    servers = load_mcp_manifest()
    if "mineru" in servers:
        (home / "docs-in").mkdir(parents=True, exist_ok=True)
        (home / "mineru-downloads").mkdir(parents=True, exist_ok=True)

    if "opencode" in targets:
        _ensure_opencode_json(home, backup_mgr, mcp=_build_opencode_mcp(servers))

    non_oc = [t for t in targets if t != "opencode"]
    if not non_oc:
        return

    resolved: dict[str, dict] = {}
    for name, spec in servers.items():
        srv = _resolve_server_runtime(name, spec, home, warnings)
        if srv is not None:
            resolved[name] = srv

    if "antigravity" in targets:
        _merge_mcp_servers_json(
            home / ".gemini" / "config" / "mcp_config.json",
            resolved,
            url_key="serverUrl",
            include_types=False,
            backup_mgr=backup_mgr,
        )

    if "claude" in targets:
        _merge_mcp_servers_json(
            home / ".claude.json",
            resolved,
            url_key="url",
            include_types=True,
            backup_mgr=backup_mgr,
        )

    if "codex" in targets:
        toml_block = _render_codex_mcp_toml(resolved)
        _update_codex_config(home, backup_mgr, MCP_START, MCP_END, toml_block)


def _load_prompt_body(prompt_name: str) -> str:
    """Load canonical prompt body from agents/prompts/<prompt_name>.md."""
    path = REPO_ROOT / "agents" / "prompts" / f"{prompt_name}.md"
    if not path.is_file():
        raise InstallError(f"Master prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def _write_rendered_file(
    out: Path,
    content: str,
    backup_mgr: BackupManager,
    mode: int | None = None,
) -> None:
    """Write rendered text file only when changed, backing up prior content."""
    if out.is_symlink():
        backup_mgr.backup_once(out)
    elif out.exists():
        if out.read_text(encoding="utf-8") == content:
            return
        copy_for_backup(out, backup_mgr)
    atomic_write(out, content, mode=mode)


def install_subagents(
    targets: list[str],
    home: Path,
    backup_mgr: BackupManager,
    warnings: list[str],
) -> None:
    """Install harness-specific subagents from canonical prompts and manifests."""
    if "opencode" in targets:
        src_dir = REPO_ROOT / "agents" / "targets" / "opencode"
        dst_dir = home / ".config" / "opencode" / "agents"
        for src in sorted(src_dir.glob("*.md")):
            ensure_symlink(dst_dir / src.name, src, backup_mgr)

    if "antigravity" in targets:
        manifest = load_json_dict(REPO_ROOT / "agents" / "targets" / "antigravity.json")
        dst_dir = home / ".gemini" / "config" / "agents"
        for spec in manifest.get("agents", []):
            fields: dict[str, object] = {
                "name": spec["name"],
                "description": spec["description"],
                "mainAgent": spec["mainAgent"],
                "subagent": spec["subagent"],
                "model": spec["model"],
                "commandExecutionPolicy": spec["commandExecutionPolicy"],
            }
            if "skills" in spec:
                fields["skills"] = spec["skills"]
            content = render_yaml_frontmatter(fields, _load_prompt_body(spec["prompt"]))
            _write_rendered_file(dst_dir / f"{spec['name']}.md", content, backup_mgr)

    if "claude" in targets:
        manifest = load_json_dict(REPO_ROOT / "agents" / "targets" / "claude.json")
        dst_dir = home / ".claude" / "agents"
        for spec in manifest.get("agents", []):
            fields = {
                "name": spec["name"],
                "description": spec["description"],
                "model": spec["model"],
                "effort": spec["effort"],
                "tools": spec["tools"],
                "disallowedTools": spec["disallowedTools"],
                "maxTurns": spec["maxTurns"],
            }
            if "skills" in spec:
                fields["skills"] = spec["skills"]
            content = render_yaml_frontmatter(fields, _load_prompt_body(spec["prompt"]))
            _write_rendered_file(dst_dir / f"{spec['name']}.md", content, backup_mgr)

    if "codex" in targets:
        manifest = load_json_dict(REPO_ROOT / "agents" / "targets" / "codex.json")
        dst_dir = home / ".codex" / "agents"
        agent_entries: list[str] = []

        cfg_path = home / ".codex" / "config.toml"
        existing_raw = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else ""
        stripped = _strip_managed_block(existing_raw, AGENTS_START, AGENTS_END)
        stripped = _strip_managed_block(stripped, MCP_START, MCP_END)
        try:
            outside_data = tomllib.loads(stripped) if stripped.strip() else {}
        except tomllib.TOMLDecodeError as exc:
            raise InstallError(f"Existing TOML in {cfg_path} is invalid: {exc}") from exc

        if "features" not in outside_data:
            agent_entries.append("[features]\nmulti_agent = true")
        elif not isinstance(outside_data["features"], dict) or outside_data["features"].get("multi_agent") is not True:
            warnings.append(
                f"Section [features] already exists in {cfg_path}; set 'multi_agent = true' manually under [features]."
            )

        for spec in manifest.get("agents", []):
            body = _load_prompt_body(spec["prompt"])
            toml_text = "\n".join(
                [
                    f"name = {_toml_str(spec['name'])}",
                    f"description = {_toml_str(spec['description'])}",
                    f"model = {_toml_str(spec['model'])}",
                    f"model_reasoning_effort = {_toml_str(spec['model_reasoning_effort'])}",
                    f"developer_instructions = {_toml_multiline(body)}",
                ]
            ) + "\n"
            try:
                tomllib.loads(toml_text)
            except tomllib.TOMLDecodeError as exc:
                raise InstallError(f"TOML validation failed for subagent {spec['name']}: {exc}") from exc

            out = dst_dir / f"{spec['name']}.toml"
            _write_rendered_file(out, toml_text, backup_mgr)

            agent_entries.append(
                f"[agents.{_toml_key(spec['name'])}]\nconfig_file = {_toml_str(str(out))}"
            )

        _update_codex_config(home, backup_mgr, AGENTS_START, AGENTS_END, "\n\n".join(agent_entries))


def install_shell(home: Path, backup_mgr: BackupManager, warnings: list[str]) -> None:
    """Install shell configs, Oh My Posh theme, host directories, and btop theme."""
    ensure_symlink(home / ".bashrc.custom", REPO_ROOT / "shell" / "bashrc.custom", backup_mgr)

    bashrc = home / ".bashrc"
    hook = "[ -f ~/.bashrc.custom ] && . ~/.bashrc.custom"
    existing_rc = bashrc.read_text(encoding="utf-8") if bashrc.exists() else ""
    if hook not in existing_rc.splitlines():
        if bashrc.exists() and bashrc.stat().st_size > 0:
            copy_for_backup(bashrc, backup_mgr)
        prefix = existing_rc.rstrip("\n") + "\n\n" if existing_rc.strip() else ""
        atomic_write(bashrc, prefix + hook + "\n")

    ensure_symlink(
        home / ".config" / "oh-my-posh" / "themes" / "clicknow.omp.json",
        REPO_ROOT / "shell" / "clicknow.omp.json",
        backup_mgr,
    )

    for folder in (home / "docs-in", home / "mineru-downloads"):
        folder.mkdir(parents=True, exist_ok=True)
    try:
        Path("/tmp/agy-work").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        warnings.append(f"Could not create /tmp/agy-work: {exc}")

    theme_path = home / ".config" / "btop" / "themes" / "catppuccin_mocha.theme"
    if not (theme_path.is_file() and theme_path.stat().st_size > 0):
        try:
            with urllib.request.urlopen(BTOP_THEME_URL, timeout=10) as resp:
                theme_text = resp.read().decode("utf-8")
            atomic_write(theme_path, theme_text)
        except Exception as exc:
            warnings.append(f"Could not download btop Catppuccin Mocha theme: {exc}")

    conf_path = home / ".config" / "btop" / "btop.conf"
    existing_conf = conf_path.read_text(encoding="utf-8") if conf_path.exists() else ""
    if not re.search(r'^color_theme\s*=\s*".*catppuccin_mocha', existing_conf, flags=re.MULTILINE):
        if re.search(r"^color_theme\s*=.*$", existing_conf, flags=re.MULTILINE):
            updated_conf = re.sub(
                r"^color_theme\s*=.*$",
                'color_theme = "catppuccin_mocha"',
                existing_conf,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            sep = "\n" if existing_conf and not existing_conf.endswith("\n") else ""
            updated_conf = existing_conf + sep + 'color_theme = "catppuccin_mocha"\n'
        if conf_path.exists() and conf_path.stat().st_size > 0:
            copy_for_backup(conf_path, backup_mgr)
        atomic_write(conf_path, updated_conf)


def install_tools(with_node: bool, home: Path) -> None:
    """Run host CLI tool bootstrap script."""
    script = REPO_ROOT / "shell" / "install-tools.sh"
    env = dict(os.environ, HOME=str(home), WITH_NODE="1" if with_node else "0")
    res = subprocess.run(["bash", str(script)], env=env, check=False)
    if res.returncode != 0:
        raise InstallError(f"Tool installation script exited with status {res.returncode}.")


def build_plan_preview(
    targets: list[str],
    components: list[str],
    home: Path,
) -> list[str]:
    """Build a human-readable summary of planned changes without reading secret values."""
    lines: list[str] = []
    skill_count = len(discover_skills())

    if "shell" in targets:
        lines.append("- Shell & Host:")
        lines.append(f"  - Symlink {home / '.bashrc.custom'} -> shell/bashrc.custom and hook into {home / '.bashrc'}")
        lines.append(f"  - Symlink Oh My Posh theme to {home / '.config' / 'oh-my-posh' / 'themes' / 'clicknow.omp.json'}")
        lines.append(f"  - Configure btop Catppuccin Mocha theme in {home / '.config' / 'btop' / 'btop.conf'}")
        lines.append(f"  - Ensure /tmp/agy-work, {home / 'docs-in'}, and {home / 'mineru-downloads'} exist")

    if "tools" in targets:
        lines.append("- CLI Tools: check and install missing tools via shell/install-tools.sh (uv, oh-my-posh, opencode, claude, agy, btop, fzf, zoxide)")

    if "node" in targets:
        lines.append("- Node.js: install nvm + Node.js LTS via shell/install-tools.sh")

    if "skills" in components:
        lines.append(f"- Skills ({skill_count} items): symlink to {home / '.agents' / 'skills'}")
        if "antigravity" in targets:
            lines.append(f"  - Antigravity: add {home / '.agents' / 'skills'} to {home / '.gemini' / 'config' / 'skills.json'}")
        if "claude" in targets:
            lines.append(f"  - Claude Code: per-skill symlinks in {home / '.claude' / 'skills'} (other folders untouched)")
        if "opencode" in targets:
            lines.append("  - OpenCode: reads ~/.agents/skills/ natively")
        if "codex" in targets:
            lines.append("  - Codex CLI: reads ~/.agents/skills/ natively")

    if "rules" in components:
        lines.append(f"- Rules: symlink {home / '.agents' / 'AGENTS.md'} -> rules/AGENTS.md")
        if "opencode" in targets:
            lines.append(
                f"  - OpenCode: symlink opencode-delegation.md & set instructions in {home / '.config' / 'opencode' / 'opencode.json'}"
            )
        if "antigravity" in targets:
            lines.append(f"  - Antigravity: symlink {home / '.gemini' / 'AGENTS.md'}")
        if "claude" in targets:
            lines.append(f"  - Claude Code: symlink {home / '.claude' / 'CLAUDE.md'}")
        if "codex" in targets:
            lines.append(f"  - Codex CLI: symlink {home / '.codex' / 'AGENTS.md'}")

    if "mcp" in components:
        servers = load_mcp_manifest()
        lines.append(f"- MCP ({len(servers)} servers in mcp/servers.json):")
        if "opencode" in targets:
            lines.append(f"  - OpenCode: update mcp.servers in {home / '.config' / 'opencode' / 'opencode.json'} (uses {{file:...}})")
        if "antigravity" in targets:
            lines.append(f"  - Antigravity: merge mcpServers into {home / '.gemini' / 'config' / 'mcp_config.json'} (chmod 600)")
        if "claude" in targets:
            lines.append(f"  - Claude Code: merge mcpServers into {home / '.claude.json'} preserving other keys (chmod 600)")
        if "codex" in targets:
            lines.append(f"  - Codex CLI: update MCP block in {home / '.codex' / 'config.toml'} (chmod 600)")

        missing_secrets = []
        for s_name, spec in servers.items():
            auth = spec.get("auth")
            if auth and not (home / auth["secret_file"][2:]).is_file():
                missing_secrets.append(f"{auth['secret_file']} (for {s_name})")
            for env_spec in spec.get("env_secret_files", {}).values():
                if not (home / env_spec["secret_file"][2:]).is_file():
                    missing_secrets.append(f"{env_spec['secret_file']} (optional for {s_name})")
        if missing_secrets and any(t in ("antigravity", "claude", "codex") for t in targets):
            lines.append("  - Missing secrets (contents not read): " + ", ".join(missing_secrets))

    if "subagents" in components:
        lines.append("- Subagents:")
        if "opencode" in targets:
            lines.append(f"  - OpenCode: symlink 10 agents to {home / '.config' / 'opencode' / 'agents'}")
        if "antigravity" in targets:
            lines.append(f"  - Antigravity: write 4 agents (model: inherit) to {home / '.gemini' / 'config' / 'agents'}")
        if "claude" in targets:
            lines.append(f"  - Claude Code: write 5 agents (opus/sonnet/haiku) to {home / '.claude' / 'agents'}")
        if "codex" in targets:
            lines.append(f"  - Codex CLI: write 4 .toml files (gpt-6-luna) + agents block in {home / '.codex' / 'config.toml'}")

    return lines


def main() -> int:
    """Run interactive installer flow."""
    home = Path.home()

    print("=== Dotfiles & Agent Config Installer ===")
    target_items, default_targets = build_target_items(home)

    try:
        selected_targets = checkbox_menu("1. Select setup targets:", target_items, default_targets)
        if not selected_targets:
            print("No targets selected. Aborted.")
            return 0

        has_ai = any(t in AI_TARGETS for t in selected_targets)
        selected_components: list[str] = []
        if has_ai:
            component_items = [{"id": cid, "label": label, "note": ""} for cid, label in COMPONENTS]
            default_components = {cid for cid, _ in COMPONENTS}
            selected_components = checkbox_menu(
                "2. Select AI components to install:",
                component_items,
                default_components,
            )
            if not selected_components:
                print("No AI components selected; continuing with non-AI targets only.")

        print("\n=== Installation Plan ===")
        print(f"Targets   : {', '.join(selected_targets)}")
        if has_ai:
            comp_str = ", ".join(selected_components) if selected_components else "(none)"
            print(f"Components: {comp_str}")
        for line in build_plan_preview(selected_targets, selected_components, home):
            print(line)

        confirm = input("\nProceed with installation? [y/N]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 0

    if confirm not in ("y", "yes"):
        print("Cancelled. No files were modified.")
        return 0

    backup_mgr = BackupManager(home)
    warnings: list[str] = []
    notes: list[str] = []

    if "shell" in selected_targets:
        install_shell(home, backup_mgr, warnings)
    if "tools" in selected_targets or "node" in selected_targets:
        install_tools("node" in selected_targets, home)

    ai_selected = [t for t in selected_targets if t in AI_TARGETS]
    if ai_selected and selected_components:
        if "skills" in selected_components:
            install_skills(ai_selected, home, backup_mgr, notes)
        if "rules" in selected_components:
            install_rules(ai_selected, home, backup_mgr)
        if "mcp" in selected_components:
            install_mcp(ai_selected, home, backup_mgr, warnings)
        if "subagents" in selected_components:
            install_subagents(ai_selected, home, backup_mgr, warnings)

    print("\n=== Done ===")
    if backup_mgr.backed_up:
        print(f"Backups of previous files saved to: {backup_mgr.root}")
    for msg in warnings:
        print(f"[Warning] {msg}")
    for msg in notes:
        print(f"[Note] {msg}")
    print("Configuration applied successfully.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InstallError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
