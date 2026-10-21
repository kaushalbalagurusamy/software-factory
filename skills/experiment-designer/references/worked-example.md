# Worked example: ROADMAP Phase 3

Source: Phase 3 of `ROADMAP.md` and section 6 of `RESEARCH_MANIFESTO.md`. Everything stated as already in the repo is quoted from them. Everything marked "proposed" is what this skill would add.

## What exists

Phase 3 runs the factory on a multi-file codebase with an intentional cross-file concurrency or state-synchronization defect, and compares three ways of giving the agent context: raw source, simulated Graph RAG, and Unity-IR. It records retrieval and parsing latency (target under 100 ms against 2 to 8 s), token density (at least 40% fewer tokens), and the execution accuracy of generated patches. The manifesto extends the three arms to six conditions (C0 to C5).

Note that `docs/adr/ADR-0001` already accepts Unity-IR. This experiment therefore tests an accepted decision, and a failed run reopens the ADR.

## Applying the steps

1. **Matrix.** Avenues: raw source, simulated Graph RAG, Unity-IR (the manifesto's other conditions can be added as arms later). Open claims: the latency target, the token-density target, and resolution correctness. The first two are stated targets, not yet measured here. Resolution correctness is the claim the decision most depends on, and it has no number yet.

2. **Worth it?** Yes. The outcome can change the choice, the decision is a one-way door (ADR-0001), and being wrong costs the whole architecture.

3. **Proxy problem.** The planted defect is already a proxy: it keeps the multi-file causal chain and the concurrency invariant and drops the domain. Proposed: plant several defects of different shapes (a removed lock in one file, a shared structure mutated through a callee without the lock, a state update ordered wrongly across two modules), so the result does not hinge on one bug.

4. **Fidelity statement (proposed).**

   | Real property | Proxy feature | Not captured |
   |---|---|---|
   | Defect spans files that the issue text does not name | Planted defects whose symptom sits in a different file from the cause | Defects with no reproducible symptom |
   | Production-size repository | Codebases at three sizes | Years of accumulated style drift |
   | Concurrent language semantics | Python and Go anchors | Rust, C++ |

5. **Scale ladder (proposed).** Three codebase sizes for the correctness arms. The roadmap already records lines-of-code latency sweeps for Unity (18k to 10M) in `benchmarks/results.json`, which can be reused for the latency metric. Token density has no recorded sweep yet.

6. **Harness (proposed).** The same issue text, planted-defect set, and patch-verification tests for every arm; one model and prompt skeleton. Failure-mode cases first: a malformed issue description, a defect in a file that retrieval is likely to miss, a patch that fixes the symptom and breaks a lock invariant. Hash-lock the planted-defect set and the verification tests.

7. **Decision rule (proposed, needs your number).** The roadmap gives targets for latency and token density but none for resolution correctness. The skill would ask for it, because a pass line cannot be invented. Once given: Unity-IR holds the decision if it meets all three targets, with any shortfall in correctness falling inside the spread over repeats; otherwise ADR-0001 is reopened with the numbers.

8. **Variance (proposed).** Three repeats per agent-built arm. Report resolution correctness as a rate with its range over defects and repeats.

9. **Outcomes.** If Unity-IR misses a target, the referee's gap report names the target and the binding constraint (for example lowering time on large repositories), and research looks for a way to relax that constraint.
