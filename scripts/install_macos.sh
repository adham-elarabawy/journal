#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
venv_dir="$project_dir/.venv"

python3 -m venv "$venv_dir"
"$venv_dir/bin/python" -m pip install --upgrade pip
"$venv_dir/bin/python" -m pip install -e "$project_dir"

printf '\nInstalled Journal. Next run:\n'
printf '  %s\n' "$venv_dir/bin/journal-doctor"
printf '\nThen configure tunnel-client with:\n'
printf '  --mcp-command "%s"\n' "$venv_dir/bin/journal-mcp"

