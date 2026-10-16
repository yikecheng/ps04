#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$ROOT_DIR" || exit 1
export PYTHONPATH="$ROOT_DIR/lib${PYTHONPATH:+:$PYTHONPATH}"
[[ -x "$ROOT_DIR/.venv/bin/python3" ]] && export PATH="$ROOT_DIR/.venv/bin:$PATH"

if [[ $# -ne 1 ]]; then
  printf 'Usage: bash workflows/create_series.sh RUN_DIR\n' >&2
  exit 2
fi
RUN_DIR="$1"
if [[ ! -f "$RUN_DIR/run.json" || ! -f "$RUN_DIR/eligible.jsonl" ]]; then
  printf 'create_series: missing run metadata or eligible evidence\n' >&2
  exit 2
fi

started_at="$(python3 -c 'from pipeline_common import utc_now; print(utc_now())')"
eligible_count="$(wc -l <"$RUN_DIR/eligible.jsonl" | tr -d ' ')"
fail() {
  local message="$1"
  python3 lib/receipt_cli.py "$RUN_DIR" create_series failed "$started_at" "$eligible_count" null \
    --tool bash --error "$message" || true
  printf 'create_series: %s\n' "$message" >&2
  exit 1
}

if ! python3 lib/coverage_check.py "$RUN_DIR/eligible.jsonl" >"$RUN_DIR/coverage.json.tmp"; then
  mv "$RUN_DIR/coverage.json.tmp" "$RUN_DIR/coverage.json"
  fail 'eligible evidence does not meet the assignment coverage minimums'
fi
mv "$RUN_DIR/coverage.json.tmp" "$RUN_DIR/coverage.json"

cat "$RUN_DIR/eligible.jsonl" | bash editorial/select_items.sh "$RUN_DIR" >"$RUN_DIR/decisions.jsonl.tmp" \
  || fail 'editorial selection failed'
mv "$RUN_DIR/decisions.jsonl.tmp" "$RUN_DIR/decisions.jsonl"

cat "$RUN_DIR/decisions.jsonl" | bash editorial/create_briefs.sh "$RUN_DIR" >"$RUN_DIR/briefs.jsonl.tmp" \
  || fail 'brief creation failed'
mv "$RUN_DIR/briefs.jsonl.tmp" "$RUN_DIR/briefs.jsonl"

cat "$RUN_DIR/briefs.jsonl" | bash content/write_articles.sh "$RUN_DIR" >"$RUN_DIR/articles.jsonl.tmp" \
  || fail 'article generation failed'
mv "$RUN_DIR/articles.jsonl.tmp" "$RUN_DIR/articles.jsonl"

cat "$RUN_DIR/briefs.jsonl" | bash content/write_video_scripts.sh "$RUN_DIR" >"$RUN_DIR/video_scripts.jsonl.tmp" \
  || fail 'video-script generation failed'
mv "$RUN_DIR/video_scripts.jsonl.tmp" "$RUN_DIR/video_scripts.jsonl"

if ! bash review/check_content.sh "$RUN_DIR" >"$RUN_DIR/review.json.tmp"; then
  rm -f "$RUN_DIR/review.json.tmp"
  fail 'content assessment could not run'
fi
mv "$RUN_DIR/review.json.tmp" "$RUN_DIR/review.json"

passed="$(python3 - "$RUN_DIR/review.json" <<'PY'
import json, sys
print('true' if json.load(open(sys.argv[1], encoding='utf-8')).get('passed') is True else 'false')
PY
)"
if [[ "$passed" != true ]]; then
  fail 'content checks completed with blocking errors'
fi

python3 lib/receipt_cli.py "$RUN_DIR" create_series completed "$started_at" "$eligible_count" 3 --tool bash
exit 0
