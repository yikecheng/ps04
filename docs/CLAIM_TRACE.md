# Claim trace: a test “fix” that deleted the test

Claim `02-c9` in Piece 2 says that Joy Ebertz asked an agent to fix a test, the agent deleted it, and her team added explicit guidance not to delete tests.

1. Publisher page: `https://www.infoq.com/podcasts/what-really-mean-program-ai/`.
2. Stable item: `podcast:infoq:5925e1fbf36f4960a85e`.
3. First-run evidence version: `v-fa6a1a051450d1962bb56646`.
4. Retained evidence: `data/assets/podcast-infoq-5925e1fbf36f4960a85e/v-fa6a1a051450d1962bb56646.segments.json`, segments `seg-0060` through `seg-0063`, approximately 13:35–14:31 and explicitly labeled `estimated_from_duration`.
5. AI selection: the matching item/version is accepted in `runs/20261013T231400Z-55620c5a/decisions.jsonl` as bounded practitioner evidence rather than prevalence data.
6. Brief: exact claim and segment locators appear under `02-c9` in `runs/20261013T231400Z-55620c5a/briefs.jsonl`.
7. Working outputs: the same marker appears in `articles/02.md` and `video_scripts/02.md` for that run.

The retained passage supports what Ebertz recounts. It does not establish how often agents delete tests. Extraction v2 will create a separate source-section-derived timestamp version on the next run; it does not mutate this first-run trace.
