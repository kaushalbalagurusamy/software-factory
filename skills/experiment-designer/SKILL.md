---
name: experiment-designer
description: >-
  Chooses which architectural uncertainties are worth testing and designs a fair, abstracted
  comparison for each, so a choice between approaches rests on evidence from a problem that mimics the
  real build. Use this whenever research has returned two or more candidate approaches and a decision
  between them is still open, or the user asks "which approach should we use", "compare these
  architectures", "benchmark the options", "do a spike", or "how do we test this before committing".
  Produces an experiment plan with a pre-registered decision rule, plus a list of decisions that need
  no experiment. It does not run experiments, judge them, or make one-way-door decisions.
---

# experiment-designer

Research returns avenues, and claims about them that are sourced but not yet tested against your workload. This skill decides which of those uncertainties deserve an experiment and designs each one so that the result transfers to the real build without building the real thing several times.

It runs at station 4 of the build loop, after research and before the experiments run. Its plan is executed by `experiment-arm-runner` subagents and judged by an independent `experiment-referee`. A choice that is a one-way door then goes to `sf-adr-debate` with the verdict as evidence.

## Inputs

- Research notes: the avenues, the claims each avenue depends on, how well each claim is evidenced, and the open uncertainties.
- The terminal requirements and spec targets from `biz-decomposer`. The targets are the pass line.
- Constraints: budget, time, environment, existing systems.
- On a repeat round: the gap reports from the previous round, so the new avenues differ from the ones already tried.

If a target is missing a number or a unit, stop and ask. A pass line cannot be invented.

## Process

1. **Lay avenues against uncertainties.** Rows are avenues, columns are the claims each avenue's case depends on. Mark each cell settled by evidence or open. Remove any avenue that a settled claim already rules out. Cheap elimination comes before expensive testing.

2. **Test whether an experiment is worth running.** Run one only when all three hold: an outcome could change the choice, the door is hard to reverse, and the test costs less than being wrong. For each decision, write one of three outcomes: run an experiment, decide by reasoning (two-way doors; record the reasoning), or send it to `sf-adr-debate` as it stands. Keep the "no experiment needed" list with a reason per line. It is part of the output.

3. **Build the proxy problem.** Keep the properties of the real build that make the decision matter: data shape and volume, concurrency pattern, failure modes, latency budget, consistency needs, workload mix. Remove the domain detail. Then check traceability: every open claim from step 1 must map to a proxy feature and a metric. A claim with no feature means the proxy cannot answer it, so extend the proxy or take that claim out of this experiment.

4. **Write the fidelity statement.** A table of real property, proxy feature, and what the proxy does not capture. Undocumented proxies read as stronger evidence than they are, so state the gaps.

5. **Add a scale ladder.** Run each arm at three or more sizes, spaced multiplicatively, up to the real target size or the largest the budget allows. Crossover points between avenues often matter more than any single size.

6. **Fix one harness for every arm.** Same inputs, same metrics, same budget, and the same model and prompt skeleton for any arm an agent implements. Put boundary and failure-mode cases ahead of happy-path cases (the `eval-designer` rule). Use `eval-designer` for the harness mechanics instead of building them here. Lock the harness and its inputs with a SHA-256 manifest, as `BaselineHashGuard` in `factory/zero_trust.py` does for tests, so no arm can alter what it is measured by.

7. **Pre-register the decision rule before any run.** The spec targets are the pass line: an avenue that misses one is out, however it scores elsewhere, unless the miss falls inside the measured spread, in which case the result is inconclusive. Among avenues that clear every target, rank by the secondary metrics (cost, operational burden, reversibility), then by the tie-break. The default tie-break is the simpler and more reversible avenue. Record the plan with its hash and date. After the first arm starts the plan is read-only, and any change is a new plan version that reruns the affected arms.

8. **Allow for implementer variance.** An avenue built by an agent is measured partly through that agent's skill at building it. Repeat each agent-built arm k times (default 3) and report the mean and range. Treat a gap inside the range as no difference.

9. **Set a timebox and a cost cap per experiment,** and state the four outcomes in advance:
   - **Choose**: one avenue wins under the rule.
   - **Eliminate**: one or more avenues fail a target, the rest are ranked.
   - **Inconclusive**: results sit inside the spread. Refine the proxy or add repeats. Never pick the favorite.
   - **None passes**: no avenue clears every target. The referee writes a gap report in seed format (avenue, target, measured value, binding constraint, what was tried) and the loop returns to research.

10. **Write the hand-offs.** One brief per arm and one for the referee, from the contracts in `references/experiment-plan-template.md`. An arm receives only its own avenue, the harness path and hash, the scale ladder, the metrics-file format, and its budget.

## After the results

- **Choose or eliminate:** pass the verdict and raw logs to `sf-adr-debate` for a one-way door. A two-way door proceeds with the winning avenue.
- **None passes:** the gap report goes to station 3 as new seeds. On the next round, read it first so the new avenues relax the binding constraint instead of repeating the old ones. When the round cap is reached, the gap reports go to the human via `biz-decomposer`.
- **A decision already accepted in an ADR:** an experiment can test it. If it fails, say so plainly and reopen the ADR instead of explaining the result away.

## Boundaries

This skill does not run arms, judge results, decide a one-way door, or build harness mechanics. Those belong to `experiment-arm-runner`, `experiment-referee`, `sf-adr-debate` with the human, and `eval-designer`. It also does not treat a proxy result as a measurement of the real system. The fidelity statement says how far the result carries.

## Reference files

- `references/experiment-plan-template.md`: the plan layout, the avenue-by-uncertainty matrix, the fidelity table, the decision-rule block, the metrics-file format, and the hand-off contracts for arms and referee. Read it before writing a plan.
- `references/worked-example.md`: the Phase 3 benchmark in this repo's `ROADMAP.md`, taken through the steps above. Read it when the shape of a plan is unclear.
