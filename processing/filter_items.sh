#!/usr/bin/env bash

# Mechanical 30-calendar-date eligibility filter.  Editorial relevance is
# deliberately outside this component.
set -uo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
ROOT_DIR="$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)"
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && export PATH="$ROOT_DIR/.venv/bin:$PATH"
exec python3 "$SCRIPT_DIR/filter_items.py" "$@"
