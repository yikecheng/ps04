#!/usr/bin/env bash
set -uo pipefail
ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
export PYTHONPATH="$ROOT_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && export PATH="$ROOT_DIR/.venv/bin:$PATH"
if [[ $# -ne 1 ]]; then
  printf 'Usage: bash editorial/select_items.sh RUN_DIR\n' >&2
  exit 2
fi
exec python3 editorial/select_items.py "$1"
