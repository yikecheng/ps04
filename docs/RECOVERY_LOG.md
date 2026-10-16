# Live recovery record

These are actual failures from the 2026-10-13 live work, not simulated examples.

## TLS trust failure

The first live attempt could not verify certificates with the macOS Python trust configuration. Feed, YouTube, podcast, and full-text retrieval emitted incomplete receipts rather than successful empty results. The recovery added an explicit `certifi` CA bundle and made every Bash entrypoint prefer the repository virtual environment.

## YouTube feed endpoints

Configured channel-feed endpoints returned HTTP 404 or 500 even after TLS repair. The run preserved those failures. Recovery used individually verified YouTube watch pages while retaining the failed channel-feed URL and a `collection_mode` label in configuration. This is a transparent fallback, not a claim that the channel feeds succeeded.

## Inaccessible content

One OpenAI written page did not yield substantive main text, and one Thoughtworks podcast lacked a usable timestamped transcript. Both were reported as extraction failures and removed from the clean source configuration rather than filled with invented summaries.

## Timestamp provenance

InfoQ transcript pages contain publisher section markers formatted with spaces inside brackets. Extraction v1 missed those markers and generated duration-based timestamps, explicitly labeled as estimates. Extraction v2 recognizes the publisher format, labels within-section interpolation, and invalidates the old cache without overwriting retained v1 evidence. The next live run will preserve the corrected versions separately.

## What recovery demonstrates

The system retains partial valid output, failure status, repeated receipts, and the final recovery path. It never treats a failed collector as a successful zero-result search, never overwrites evidence referenced by an earlier run, and never invents a transcript to satisfy coverage.

## Second-day sandbox and structured-identity failures

The 2026-10-16 UTC live run completed collection but its first model invocation was denied by the desktop sandbox. The failed receipt remains. The exact snapshotted run was resumed with the required permission and produced decisions, briefs, articles, and scripts.

The first controlled policy-comparison response later paired a YouTube item with another item's version ID. The validator rejected the entire response. Selection now gives the model deterministic decision slots and application code attaches exact item/version identities. The failed model response is preserved, and a new regression test verifies slot-to-identity mapping.

The second live review also caught a portfolio-level failure: policy v2 accepted no eligible podcast evidence. The run remains failed at that gate rather than silently using rejected sources. Separately, generated drafts falsely claimed completed human review; original files are retained and current disclosures correctly state that review is still required.
