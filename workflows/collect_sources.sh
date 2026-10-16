#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
export PYTHONPATH="$ROOT_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && export PATH="$ROOT_DIR/.venv/bin:$PATH"

if [[ $# -ne 1 ]]; then
  printf 'Usage: bash workflows/collect_sources.sh RUN_DIR\n' >&2
  exit 2
fi
RUN_DIR="$1"
if [[ ! -f "$RUN_DIR/run.json" ]]; then
  printf 'collect_sources: invalid RUN_DIR: %s\n' "$RUN_DIR" >&2
  exit 2
fi

started_at="$(python3 -c 'from pipeline_common import utc_now; print(utc_now())')"
mkdir -p "$RUN_DIR/candidates" "$RUN_DIR/logs"

collector_failures=0
for spec in \
  'feeds collectors/fetch_feeds.sh' \
  'youtube collectors/fetch_youtube.sh' \
  'podcasts collectors/fetch_podcasts.sh'
do
  kind="${spec%% *}"
  script="${spec#* }"
  output="$RUN_DIR/candidates/$kind.jsonl"
  temp="$output.tmp"
  rc=0
  bash "$script" "$RUN_DIR" >"$temp" || rc=$?
  # Preserve valid partial output; malformed collector output is an invalid-stage failure.
  if python3 lib/jsonl_tools.py "$temp" >"$output.valid"; then
    mv "$output.valid" "$output"
  else
    rm -f "$output.valid"
    : >"$output"
    rc=2
  fi
  rm -f "$temp"
  if (( rc != 0 )); then
    collector_failures=$((collector_failures + 1))
    printf 'collect_sources: %s collector exited %d; continuing with partial evidence\n' "$kind" "$rc" >&2
  fi
done

if ! python3 lib/jsonl_tools.py \
  "$RUN_DIR/candidates/feeds.jsonl" \
  "$RUN_DIR/candidates/youtube.jsonl" \
  "$RUN_DIR/candidates/podcasts.jsonl" >"$RUN_DIR/candidates.jsonl.tmp"
then
  rm -f "$RUN_DIR/candidates.jsonl.tmp"
  python3 lib/receipt_cli.py "$RUN_DIR" collect_sources failed "$started_at" null null \
    --tool bash --error 'could not combine valid candidate streams'
  exit 2
fi
mv "$RUN_DIR/candidates.jsonl.tmp" "$RUN_DIR/candidates.jsonl"
candidate_count="$(wc -l <"$RUN_DIR/candidates.jsonl" | tr -d ' ')"

stage_failure=0
# This is an intentional JSONL pipe required by the component contract.
if ! cat "$RUN_DIR/candidates.jsonl" | bash processing/extract_content.sh "$RUN_DIR" >"$RUN_DIR/items.jsonl.tmp"; then
  stage_failure=1
fi
mv "$RUN_DIR/items.jsonl.tmp" "$RUN_DIR/items.jsonl"

if ! cat "$RUN_DIR/items.jsonl" | bash data/store.sh upsert "$RUN_DIR" >"$RUN_DIR/changes.jsonl.tmp"; then
  rm -f "$RUN_DIR/changes.jsonl.tmp"
  stage_failure=1
else
  mv "$RUN_DIR/changes.jsonl.tmp" "$RUN_DIR/changes.jsonl"
fi

if ! bash data/store.sh list >"$RUN_DIR/corpus.jsonl.tmp"; then
  rm -f "$RUN_DIR/corpus.jsonl.tmp"
  stage_failure=1
else
  mv "$RUN_DIR/corpus.jsonl.tmp" "$RUN_DIR/corpus.jsonl"
fi

if [[ -f "$RUN_DIR/corpus.jsonl" ]]; then
  if ! cat "$RUN_DIR/corpus.jsonl" | bash processing/filter_items.sh "$RUN_DIR" >"$RUN_DIR/eligible.jsonl.tmp"; then
    rm -f "$RUN_DIR/eligible.jsonl.tmp"
    stage_failure=1
  else
    mv "$RUN_DIR/eligible.jsonl.tmp" "$RUN_DIR/eligible.jsonl"
  fi
fi

item_count=0
[[ -f "$RUN_DIR/items.jsonl" ]] && item_count="$(wc -l <"$RUN_DIR/items.jsonl" | tr -d ' ')"
if (( stage_failure != 0 )); then
  python3 lib/receipt_cli.py "$RUN_DIR" collect_sources failed "$started_at" "$candidate_count" "$item_count" \
    --tool bash --error 'one or more preparation or storage stages failed'
  exit 1
fi

status=completed
if (( collector_failures != 0 )); then
  status=incomplete
  python3 lib/receipt_cli.py "$RUN_DIR" collect_sources "$status" "$started_at" "$candidate_count" "$item_count" \
    --tool bash --error "$collector_failures collector(s) failed or returned incomplete coverage"
else
  python3 lib/receipt_cli.py "$RUN_DIR" collect_sources "$status" "$started_at" "$candidate_count" "$item_count" \
    --tool bash
fi
if (( collector_failures != 0 )); then
  exit 1
fi
exit 0
