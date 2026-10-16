# Second live pipeline run

Run: `runs/20261016T021442Z-113efa68`. It began on October 15 in New York and records the required UTC as-of date of 2026-10-16. The first completed live run used 2026-10-13, so the two runs occur on different calendar dates under either local or UTC interpretation.

## Collection and storage result

- 27 observations were discovered and extracted.
- The persistent store recorded 10 new items, 5 changed versions, and 12 unchanged observations.
- The moving 30-date filter retained 25 eligible items from 10 publishers: 17 written items, 6 YouTube videos, and 2 podcasts.
- Two September 14 items aged out and were explicitly labeled `outside_window`; prior storage did not make them perpetually eligible.
- The 10 new items include current arXiv research on benchmark exploits, task composition, repository migration, and harness engineering; GitHub releases for agentic security autofix and model deprecation; and InfoQ reporting on Android Bench 2, Spotify's change volume and production failure, and GitHub's AI-assisted Rust migration.

Three changed podcast versions reflect the extraction-v2 timestamp correction. The older estimated evidence remains immutable. A changed research page and the now-expired Sourcegraph item were also preserved rather than overwritten.

## Real recovery

The first selection invocation failed because the desktop sandbox denied initialization of the authenticated in-process model client. The failure and its `create_series` consequence remain in receipts. The same snapshotted run was resumed at the affected editorial workflow with the required permission; selection, briefs, three articles, and three scripts then completed.

The generated drafts incorrectly claimed that human review had already occurred. No approval existed. The original files are preserved under `editorial_history/`; current files correctly say review is required. Generator prompts were fixed for future runs.

## Editorial result

Policy v2 produced 14 accepts, 6 rejects, and 5 deferrals. The three arguments are:

1. The material shift is coding agents entering a supervised delivery control plane.
2. Evidence supports bounded workflow competence, not blanket correctness; different sources measure different outcome layers.
3. Small teams should adopt agents as a reversible controlled system, not as a new autonomous teammate.

Among items shared with the first completed run, three decisions changed. A research synthesis moved from reject to accept; Joy Ebertz's practitioner interview moved from accept to reject as duplicative anecdotal evidence; and a psychological-safety interview moved from reject to defer pending a documented team case. Because several evidence versions also changed, the full live-run comparison cannot isolate the policy's causal effect. A separate policy-only rerun uses the exact original cohort.

## Current blocking result

Mechanical review correctly fails one requirement: neither currently eligible podcast was accepted, so the new briefs use no podcast evidence. The script word-count warnings were false positives caused by counting visual directions and description metadata as narration; the counter now measures explicitly labeled narration and has a regression test.

This later run is preserved as an honest strict-policy result rather than silently weakening the rule or relabeling evidence. The first completed run still supplies the reviewed publication candidates and uses all three input types. A genuine student judgment to retain bounded podcast evidence could repair the later series; automation will not invent that override.
