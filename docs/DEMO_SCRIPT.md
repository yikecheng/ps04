# Agent Signal — Technical Demonstration

*Target runtime: 4–6 minutes. Narration: disclosed synthetic text-to-speech.*

[VISUAL: Show `config/project.json`, `run.sh`, and a compact pipeline diagram.]

**NARRATION:** Agent Signal is a repeatable evidence pipeline for technical leads at software teams of roughly two to twenty people. It asks a narrow question: which coding-agent capabilities are genuinely ready for production, what evidence supports that conclusion, and what should a small team do next? Bash coordinates the fixed stages. Python handles deterministic parsing, storage, coverage, receipts, and validation. AI is limited to selection, synthesis, and drafting. The mechanical checks verify structure and provenance; they do not pretend to verify truth.

[VISUAL: Animate the implemented stages from collection through publication handoff.]

**NARRATION:** A run starts with three collectors for feeds, YouTube, and podcasts. Extracted text and timestamped segments enter a versioned evidence store. A mechanical thirty-date filter runs before the editorial model. Coverage gates then require source-type and publisher diversity. Accepted evidence becomes three briefs, three articles, and three matched audience-video scripts. A content review checks identifiers, citations, markers, lengths, and source coverage. Packaging is blocked until a fingerprint-bound human approval matches the exact reviewed drafts.

[VISUAL: Open `docs/CLAIM_TRACE.md`, then highlight claim `02-c9` across the decision, brief, article, and video script.]

**NARRATION:** Here is one end-to-end claim trace. Article Two says that Joy Ebertz asked an agent to fix a test, the agent deleted the test, and her team added guidance not to delete tests. The claim marker is zero-two-c-nine. It points back to the accepted InfoQ item, immutable source version v-fa-six-a-one, and segments sixty through sixty-three, approximately thirteen minutes thirty-five seconds through fourteen thirty-one. The same marker appears in the brief, article, and video script. The editorial boundary is explicit: this is practitioner evidence of a failure mode, not evidence of how often that failure occurs.

[VISUAL: Show the immutable transcript path and the storage interface, with the database behind a single entrypoint.]

**NARRATION:** Source assets are content-addressed. The repository keeps full extracted text or transcript segments, exact locators, retrieval metadata, and a substantive version hash. Retrieval time is excluded from that hash, so revisiting an unchanged page does not create fake evidence. Only `data/store.sh` accesses the SQLite index. Every other stage communicates through files and JSON Lines, which makes inspection and replay straightforward.

[VISUAL: Compare the October 13 and October 16 run summaries and show the moving window exclusions.]

**NARRATION:** The first completed live run on October thirteenth produced seventeen eligible items from nine independent publishers, ten accepts, six rejects, one defer, and all six required drafts. The October sixteenth run observed twenty-seven items: ten new, five changed, and twelve unchanged. Its moving window retained twenty-five eligible items from ten publishers and excluded two September fourteenth items as outside the window. This demonstrates update behavior without counting every retrieval as new evidence.

[VISUAL: Show `docs/RECOVERY_LOG.md`, failed receipts, then the successful targeted reruns.]

**NARRATION:** The failure history is preserved rather than edited away. The first live attempt hit macOS certificate failures. The repair added an explicit CA bundle and made every entrypoint prefer the project environment. Several YouTube channel-feed endpoints still returned errors, so collection used individually verified watch pages labeled as a fallback. On the later run, a sandbox-blocked model call and an invalid item-version pairing both failed validation. The affected editorial stage was rerun from saved inputs instead of recollecting or claiming a clean first attempt.

[VISUAL: Compare policy version one with version two and show the controlled comparison table.]

**NARRATION:** Human review led to four operational policy changes. Availability is no longer treated as readiness. Quantitative claims must preserve their denominator, baseline, task, and outcome context—or state what is missing. Activity and efficiency stay separate from accepted outcomes. Creator-reported numerical improvements are deferred when the primary method is not inspectable. A controlled rerun applied both policies to the same original evidence cohort. The comparison also admits model variation, so it does not overstate policy-only causality.

[VISUAL: Show the review fingerprint, `approval.json`, and the immutable production-package manifest.]

**NARRATION:** The human handoff is a real gate. Yike Cheng reviewed the packet and approved its recommendations. The saved approval names the exact review identifier and fingerprint. The packaging command refuses missing, stale, or mismatched approval and copies the already reviewed files without rewriting them. The result is one immutable production package containing three articles, three matched scripts, source notes, a manifest, and publication-link records.

[VISUAL: Contrast the local evidence architecture with a hosted vector database.]

**NARRATION:** The main architecture tradeoff is deliberate. A local versioned SQLite index plus immutable text and segment files is less scalable than hosted semantic search. At twelve to thirty items per run, however, exact provenance, simple replay, credential-free grading, and visible failure records matter more than retrieval sophistication. If the corpus grew substantially, semantic retrieval could be added behind the store interface without changing the editorial contracts.

[VISUAL: Show the three final article/video pairs, the four rendered MP4 files, and the submission record.]

**NARRATION:** The production set contains three connected pieces: workflow control beyond the diff, production readiness as a measurement claim, and an evidence-gated adoption ladder. Each audience video uses the same reviewed brief as its article, includes source references, and discloses AI-assisted production. This separate technical demonstration uses synthetic narration under the course’s text-to-speech alternative. Final platform URLs are recorded in the submission files after upload and checked for shareable access.

[VISUAL: End on the central result and a limitations card.]

**NARRATION:** The central result is that production readiness is a measured property of a bounded task, harness, acceptance test, and supervision regime—not a label attached to an agent product. This project does not rank vendors or claim universal failure rates. Its strongest contribution is a reproducible chain from fresh evidence to bounded claims, visible human judgment, recoverable failure, and an auditable publication handoff.

[ON-SCREEN DISCLOSURE: Synthetic narration. AI assisted research, drafting, and presentation. A human editor approved the reviewed recommendations.]
