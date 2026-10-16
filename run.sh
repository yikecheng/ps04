#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1
export PYTHONPATH="$ROOT_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"
if [[ -x "$ROOT_DIR/.venv/bin/python3" ]]; then
  export PATH="$ROOT_DIR/.venv/bin:$PATH"
fi

usage() {
  printf 'Usage: bash run.sh [--package RUN_DIR]\n' >&2
}

summarize() {
  local target="$1"
  local temp_summary="$target/.summary.tmp"
  if bash reporting/summarize_run.sh "$target" >"$temp_summary"; then
    mv "$temp_summary" "$target/summary.json"
  else
    local rc=$?
    rm -f "$temp_summary"
    printf 'run: summary generation failed for %s\n' "$target" >&2
    return "$rc"
  fi
  cat "$target/summary.json"
}

if [[ "${1:-}" == "--package" ]]; then
  if [[ $# -ne 2 ]]; then
    usage
    exit 2
  fi
  RUN_DIR="$2"
  if [[ ! -d "$RUN_DIR" || ! -f "$RUN_DIR/run.json" ]]; then
    printf 'run: invalid RUN_DIR for packaging: %s\n' "$RUN_DIR" >&2
    exit 2
  fi

  review_tmp="$RUN_DIR/.review.tmp"
  bash review/check_content.sh "$RUN_DIR" >"$review_tmp"
  rc=$?
  if (( rc != 0 )); then
    rm -f "$review_tmp"
    summarize "$RUN_DIR" || true
    exit "$rc"
  fi
  mv "$review_tmp" "$RUN_DIR/review.json"

  package_tmp="$RUN_DIR/.package-manifest.tmp"
  bash publishing/prepare_package.sh "$RUN_DIR" >"$package_tmp"
  rc=$?
  if (( rc == 0 )); then
    mv "$package_tmp" "$RUN_DIR/package/manifest.json"
    summarize "$RUN_DIR"
    exit 0
  fi
  rm -f "$package_tmp"
  summarize "$RUN_DIR" || true
  exit "$rc"
fi

if [[ $# -ne 0 ]]; then
  usage
  exit 2
fi

RUN_DIR="$(python3 lib/run_manager.py create)"
rc=$?
(( rc == 0 )) || exit "$rc"

if ! bash data/store.sh init; then
  printf 'run: evidence store initialization failed\n' >&2
  summarize "$RUN_DIR" || true
  exit 1
fi

collection_rc=0
bash workflows/collect_sources.sh "$RUN_DIR" || collection_rc=$?

series_rc=0
if [[ -s "$RUN_DIR/eligible.jsonl" ]]; then
  bash workflows/create_series.sh "$RUN_DIR" || series_rc=$?
else
  printf 'run: no eligible evidence; series workflow not started\n' >&2
  series_rc=1
fi

summary_rc=0
summarize "$RUN_DIR" || summary_rc=$?

if (( summary_rc != 0 || series_rc != 0 )); then
  exit 1
fi
# Partial collector failures are represented in receipts and the summary while
# usable evidence proceeds through the full pipeline.
exit 0
