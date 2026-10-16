# What survives: workflow competence, not blanket correctness

_As of October 16, 2026._

_Disclosure: AI assisted the research and drafting; a human reviewed the evidence._

<!-- claim:02-c11 -->
Imagine four green lamps labeled available, cheaper, detector cleared, and production-correct. They look like one dashboard, but they are wired to different circuits. Our inference across the supplied evidence is that an agent can be available, cost less to run, and close a tool-detected condition while still failing held-out requirements, cross-module contracts, or production behavior. Much of the apparent dispute about coding agents is a measurement mismatch.

<!-- claim:02-c5 -->
GitHub’s [agentic-autofix workflow](https://github.blog/changelog/2026-10-15-agentic-autofix-for-code-scanning-alerts-general-availability) illustrates the narrowest lamp. The agent reruns CodeQL to verify that the targeted alert closes, then opens a draft PR for review. That is useful validation of a specific condition. It does not establish that every relevant application behavior remains correct.

<!-- claim:02-c6 -->
Cursor [reports](https://cursor.com/blog/improved-token-efficiency) a different success: a 7% reduction in user token costs without lower agent quality. Its internal experiments tracked cost, latency, tool-call errors, and usage. This supports an operating-efficiency claim under Cursor’s measurements, whose quality definition and denominators were not supplied—not a general correctness claim.

The harder evaluations move the finish line away from visible demonstrations.

<!-- claim:02-c1 -->
[AgentSWE](https://arxiv.org/html/2610.13361) evaluates 25 agent-building commissions. Builders develop against requirements and a few illustrative cases; submissions are then frozen and tested separately on held-out acceptance cases. That design asks whether the delivered system generalizes after the development loop ends.

<!-- claim:02-c2 -->
The AgentSWE authors report a severe gap: Creation runs scoring at least 90 during development averaged 9.9 on held-out delivery cases. The result does not describe every coding task, but it directly challenges the practice of treating a polished visible demonstration as acceptance.

<!-- claim:02-c3 -->
The authors of [SWE-Nexus](https://arxiv.org/abs/2610.20038) report that their best configuration resolved 37.8% of tasks in one attempt across 600 tasks drawn from 105 repositories and six languages. Their scope-weighted scoring also recognizes partial recovery—useful, but distinct from complete resolution.

<!-- claim:02-c4 -->
[Doc2Harness](https://arxiv.org/abs/2610.20344) applies another lens: deterministic execution across module boundaries. Its authors report a best pass rate of 53.05% across 19 models, three independent builds per model, and 328 tests. Even the leading result failed nearly half the cases, with failures clustering where cross-cutting behavior had to be divided among modules.

<!-- claim:02-c7 -->
Long-horizon work remains difficult in another setting. [InfoQ reports](https://www.infoq.com/news/2026/10/android-bench-2/) that the leading model on Android Bench 2.0 had a 32% long-horizon-task pass rate at publication time.

<!-- claim:02-c8 -->
That same account of Google’s benchmark draws a useful boundary: models perform better on several well-established, deterministic transformations, including in larger codebases, but continue to struggle with runtime validation, breaking framework changes, and knowledge gaps involving unreleased libraries. Task class matters more than the undifferentiated label coding.

<!-- claim:02-c9 -->
Production adds a layer no static score can guarantee. In [Spotify’s reported incident](https://www.infoq.com/news/2026/10/spotify-ai-quality-controls/), an automated dependency upgrade passed the available checks and failed after deployment. It is one incident, not an error rate, but it proves that check-passing and production safety can diverge.

<!-- claim:02-c10 -->
The compensating work does not occur only at final review. Researchers who observed [19 experienced developers](https://arxiv.org/html/2609.24234) characterize agent supervision as a connected, seven-stage process. Direction-setting, progress tracking, evaluation, and reusable guidance distribute supervision across the workflow rather than concentrating it at the last diff.

These results leave a defensible but narrow position: agents can execute bounded workflows and solve some well-defined tasks. They do not establish reliable autonomous delivery across hidden requirements, runtime behavior, and cross-module contracts.

The benchmarks also have limits. AgentSWE contains 25 commissions; SWE-Nexus derives tasks from traced tests; Doc2Harness uses a scripted mock model; and the supplied Android Bench account omits the distribution of long-horizon tasks. Hard evaluations may understate performance on routine work. Vendors benefit from adoption, benchmark authors from establishing novel difficulty, and InfoQ often relays company accounts. No supplied evidence supports generalizing either direction to small-team return on investment.

### What to do / what to watch

Ask what each green lamp actually measures. Accept detector closure as detector closure, cost reduction as cost reduction, and benchmark success as task-bounded evidence. Watch for convergent gains on held-out, cross-module, and runtime outcomes before upgrading workflow competence into a claim of blanket correctness.

## Sources

- *Agentic autofix for code scanning alerts general availability* — GitHub, October 15, 2026. [Read the release](https://github.blog/changelog/2026-10-15-agentic-autofix-for-code-scanning-alerts-general-availability)
- *Improved token efficiency for longer agent runs* — Cursor, September 23, 2026. [Read the report](https://cursor.com/blog/improved-token-efficiency)
- *AgentSWE: Can Coding Agents Build the Agent You Actually Want?* — Independent research authors, October 9, 2026. [Read the paper](https://arxiv.org/html/2610.13361)
- *SWE-Nexus: Automated Composition of Software Engineering Tasks from Test Execution* — arXiv research authors, October 15, 2026. [Read the paper](https://arxiv.org/abs/2610.20038)
- *Doc2Harness: Benchmarking LLMs on Long-Horizon Harness Engineering of Coding Agents* — arXiv research authors, October 15, 2026. [Read the paper](https://arxiv.org/abs/2610.20344)
- *Android Bench 2 Adds Support for Long-Horizon Tasks, Agentic Evaluation, and Continuous Scoring* — InfoQ, October 9, 2026. [Read the report](https://www.infoq.com/news/2026/10/android-bench-2/)
- *Spotify More Than Doubled Monthly Code Changes as AI Accelerated Development* — InfoQ, October 12, 2026. [Read the report](https://www.infoq.com/news/2026/10/spotify-ai-quality-controls/)
- *The Work Behind Delegation: A Framework for Supervising AI Coding Agents* — Independent research authors, September 21, 2026. [Read the paper](https://arxiv.org/html/2609.24234)
