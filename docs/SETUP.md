# Run Agent Signal

## Installation

Use Bash and Python 3.10 or newer. From the repository root:

```bash
bash setup.sh
bash run.sh
```

`setup.sh` creates `.venv` and installs `youtube-transcript-api`, `yt-dlp`, and `certifi`. Required Bash entrypoints automatically prefer this virtual environment. Network access is needed for feeds, public pages, transcripts, and the authenticated Codex CLI.

The live editorial provider is the logged-in Codex CLI. No API secret is stored in the repository. Optional environment variables are:

- `PS04_MODEL_PROVIDER=codex` — only supported live provider.
- `PS04_MODEL=<name>` — optional explicit model; otherwise receipts record `account-default`.
- `PS04_EVIDENCE_DIR=<path>` — alternate evidence database location for isolated tests.

## Configuration

- `config/project.json` defines the publication, audience, topic, and recurring question.
- `config/sources.json` defines RSS, YouTube, podcast, and labeled publisher-index fallbacks.
- `config/editorial_policy.md` is the current policy; old policy snapshots remain under runs and `docs/policy_history/`.
- `prompts/` contains the exact reusable selection, synthesis, article, and video instructions.

Each new run snapshots configuration and prompts before collection. Edit root files only for later runs; never rewrite a prior run snapshot.

## Useful commands

```bash
python3 -m unittest discover -s tests -v
bash data/store.sh list
bash workflows/collect_sources.sh runs/RUN_ID
bash workflows/create_series.sh runs/RUN_ID
bash review/check_content.sh runs/RUN_ID
bash reporting/summarize_run.sh runs/RUN_ID
bash run.sh --package runs/RUN_ID
```

Collectors can leave valid partial output and return `1`; the workflow records incomplete coverage. Exit `2` means invalid arguments, configuration, or record shape. Content review returns `0` when it completes an assessment, even if `passed` is false; inspect `review.json`.

The normal workflow stops at `awaiting_review`. Packaging rechecks the exact files, recalculates the review fingerprint, and requires a matching student-supplied `approval.json`. It does not create human approval or publish content.

## Evidence and omitted media

- Version index: `data/evidence/index.sqlite3`, accessed only through `data/store.sh`.
- Immutable text and timestamp segments: `data/assets/`.
- Run inputs, outputs, receipts, and model records: `runs/RUN_ID/`.
- Original large media: `data/media/`, ignored by Git.

Candidates retain the original page and media URLs. Omitted recordings can be retrieved again from those URLs. Retained transcripts and exact segment locators allow grading without downloading large media files. Publisher transcripts and automatic captions can contain errors and require human spot checks.

## Tests

The offline tests use disposable evidence stores and fictional fixtures. They cover store replay, semantic deduplication, version collisions, UTC date boundaries, malformed input protection, assignment coverage gates, malformed subtitle cues, and publisher timestamp parsing.
