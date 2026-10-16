# Technical demonstration outline — 4–6 minutes

Use these as screen cues and talking points. The finished narration is in `docs/DEMO_SCRIPT.md`. The course's text-to-speech alternative is used for the final technical demo, with an explicit synthetic-narration disclosure.

## 0:00–0:40 — Purpose and fixed architecture

Show `config/project.json`, `run.sh`, and `docs/ARCHITECTURE_IMPLEMENTATION.md`.

Explain that Agent Signal helps technical leads at 2–20-person teams decide which coding-agent capabilities are ready for production. Bash coordinates a deterministic pipeline; AI makes bounded selection, synthesis, and drafting decisions. Mechanical checks validate structure and provenance, not truth.

## 0:40–1:35 — Trace one claim

Open `docs/CLAIM_TRACE.md`. Follow claim `02-c9` from the retained InfoQ transcript segments through the selection decision, brief, Article 2 marker, and video-script marker. State the evidence boundary: Joy Ebertz's account demonstrates a failure mode, not its prevalence.

## 1:35–2:25 — Two live days and freshness

Show `run.json`, `changes.jsonl`, `exclusions.jsonl`, and `summary.json` for the October 13 and October 16 UTC runs. Explain that the later live run discovered 10 new items, preserved unchanged observations, and re-applied the moving 30-date window. Two September 14 items became `outside_window` rather than remaining eligible merely because they were in the store.

## 2:25–3:10 — Failure and targeted recovery

Show `docs/RECOVERY_LOG.md`, an incomplete collector receipt from the first run, and the failed selection receipt from the later run. Explain the certificate repair, explicit YouTube page fallback, and the later desktop-sandbox failure. Then show the successful targeted editorial rerun rather than claiming the initial attempt was clean.

## 3:10–3:55 — Human judgment and policy revision

Show `docs/policy_history/editorial_policy-v1.md`, `config/editorial_policy.md`, and `docs/POLICY_COMPARISON.md`. Explain the four v2 rules: availability is not readiness, quantitative claims retain measurement context, activity/efficiency are not accepted outcomes, and uninspectable creator numbers are deferred. State which shared decisions changed and acknowledge that changed source versions mean the full live-run comparison is not a policy-only causal test.

## 3:55–4:35 — Architecture tradeoff

Show `data/store.sh`, one immutable asset path, and the run's receipt directory. Explain why a local versioned SQLite index plus immutable text/segment files is preferable here to a hosted vector database: exact provenance and replay matter more than semantic scale. Only the store entrypoint touches the database.

## 4:35–5:25 — Outputs and limitations

Show the three packaged articles/scripts, rendered media, and final Substack/YouTube links once available. Explain that all four videos use disclosed synthetic narration under the course's text-to-speech alternative. End with the central result: production readiness is a measured property of a bounded task and control system, not a label attached to an agent product.

## Recording safety

Keep credentials, account pages, and local environment files off-screen. Enlarge text so IDs and counts are readable. Prefer saved artifacts and read-only commands; do not start a paid or networked generation run during the recording.
