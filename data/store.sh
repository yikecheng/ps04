#!/usr/bin/env bash

# Persistent evidence-store entry point.  All database access stays behind this
# component; store.py is its private implementation helper.
set -uo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && export PATH="$ROOT_DIR/.venv/bin:$PATH"
exec python3 "$SCRIPT_DIR/store.py" "$@"
