#!/usr/bin/env bash
# Hook ~/.bashrc.custom into ~/.bashrc. Safe to run more than once.
set -euo pipefail

line='[ -f ~/.bashrc.custom ] && . ~/.bashrc.custom'
grep -qxF "$line" ~/.bashrc 2>/dev/null || printf '\n%s\n' "$line" >> ~/.bashrc
