# Controlled editorial-policy comparison

Comparison run: `runs/20261016T023600Z-policy-v2`. Cohort date: 2026-10-13. The exact same 17 item/version records from the first completed run were supplied. The comparison changed the editorial policy from v1 to v2 but did not recollect or substitute evidence. It is mode `policy_comparison`, not a live run.

## Result

| Outcome | Policy v1 | Policy v2 |
| --- | ---: | ---: |
| Accept | 10 | 11 |
| Reject | 6 | 5 |
| Defer | 1 | 1 |

Five of 17 decisions changed:

| Source | v1 | v2 | Interpretation |
| --- | --- | --- | --- |
| GitHub Gemini 4 Argon announcement | Reject | Accept for Piece 1 | V2 accepted the narrow availability and admin-control facts while still rejecting performance claims. This conflicts with the proposed human judgment that model-picker news adds too little value. |
| “Why Software Engineering Is Indispensable...” position paper | Reject | Accept for Pieces 2/3 | V2 retained the explicit comparison of task and outcome layers, while labeling older cited numbers as attributed background rather than new evidence. |
| Sourcegraph Agentic Batch Changes | Accept | Reject | V2 judged the hundreds/thousands-of-repositories use case too distant from a 2–20-person team and the outcome evidence insufficient. The proposed human review would retain its bounded workflow mechanics, so this is a disagreement. |
| InfoQ psychological-safety interview | Reject | Accept for Piece 3 | V2 treated willingness to disclose failures and challenge generated work as a distinct team-practice consideration, while explicitly refusing to treat it as effectiveness evidence. |
| InfoQ junior-training/preceptorship interview | Accept | Reject | V2 rejected the analogy because no observed implementation or outcome supports it and other InfoQ material covers the operational themes more directly. |

The proposed six-item human-review labels matched v1 on 6/6 items and v2 on 4/6. That is an unfavorable but useful result: a more explicit policy did not simply reproduce the reviewer recommendations. The model interpreted the new narrow-use rules differently, especially for availability facts and audience fit. One rerun also contains model sampling variation, so changed decisions should not be attributed to policy language with experimental certainty.

## Real failed comparison attempt

The first v2 response paired one YouTube item with another item's version ID. Validation rejected the entire result. The failed request, response, receipt, and error remain in the comparison run.

The interface was then repaired: the model returns a judgment for a deterministic `decision_slot`, and application code reattaches the exact item/version identity. A regression test verifies this behavior. The successful retry produced all 17 decisions without changing the evidence cohort. This repair strengthens provenance without changing editorial content.

## Editorial implication

Policy v2 is still useful because it makes reasons more inspectable: it separates availability, efficiency, activity, and accepted outcomes and names missing measurement context. It is not a substitute for human portfolio judgment. The final publication should retain the first run's bounded Sourcegraph and Joy Ebertz evidence and reject unsupported GitHub/IBM performance claims unless the student decides otherwise after review.
