# Experiment plan template

Contents: plan layout, matrix, fidelity table, decision-rule block, metrics file, hand-off contracts.

## Plan layout

```markdown
# Experiment plan: <decision being made>
_Version: <n> · Date: <date> · Plan hash: <sha256 of this file at lock> · Round: <n> of <cap>_

## Decision and targets
The choice this experiment informs, the door type, and the spec targets that form the pass line (with units).

## Avenue by uncertainty matrix
(see below)

## Arms
One row per avenue still standing: id, one-line description, how it is built (agent-built or deterministic), repeats k.

## Proxy problem
What is built or simulated, which real properties it keeps, which domain detail it drops.

## Fidelity statement
(see below)

## Scale ladder
Sizes, how each is generated, and the budget at each.

## Harness
Path, SHA-256 of harness and inputs, case list with boundary and failure-mode cases first, model and prompt skeleton for agent-built arms.

## Metrics
Primary (the spec targets, each with its unit and how the proxy value maps to the real target). Secondary (cost, operational burden, reversibility).

## Decision rule (pre-registered)
(see below)

## Budget
Timebox and cost cap per experiment.

## Decisions needing no experiment
Decision, door type, reason, where it goes next (decide in build, or sf-adr-debate).
```

## Avenue by uncertainty matrix

| Claim the case depends on | Avenue A | Avenue B | Avenue C | Proxy feature | Metric |
|---|---|---|---|---|---|
| e.g. holds p95 under target at 100k rows | open | settled (source) | open | query mix at 3 sizes | p95 ms |
| e.g. needs no extra infrastructure | settled (source) | open | settled (source) | not tested | not tested |

Each open cell needs a proxy feature and a metric, or the claim leaves this experiment. A row where every cell is settled needs no test.

## Fidelity table

| Real property | Proxy feature | Not captured |
|---|---|---|
| Concurrent writers during reads | 8 writer threads, fixed rate | Real traffic burstiness |

## Decision-rule block

```markdown
Pass line: an avenue must meet every spec target. A miss inside the measured range is inconclusive, not a failure.
Ranking among avenues that pass: secondary metrics in this order: <list>.
Tie-break: the simpler and more reversible avenue.
Inconclusive band: <how the range over k repeats is computed>.
Outcomes: choose | eliminate | inconclusive | none passes (gap report, back to research).
```

## Metrics file

Every arm repeat writes one JSON file, so the referee can recompute everything from it and the raw logs.

```json
{
  "plan_hash": "<sha256>",
  "harness_sha256": "<sha256 of harness and inputs as run>",
  "arm": "A",
  "repeat": 1,
  "scale": 100000,
  "metrics": {"p95_ms": 41.2, "recall_at_10": 0.93},
  "cases": [{"id": "boundary-empty-input", "passed": true}],
  "raw_logs": "arms/A/repeat1/"
}
```

## Hand-off contracts

**Arm runner** receives: its avenue description, the harness path and hash, the scale ladder, the metrics-file format, and its budget. It works in its own git worktree. It returns: raw logs and one metrics file per repeat. It may not edit the harness, the inputs, or the decision rule, and it may not read another arm's output.

**Referee** receives: the plan, the harness, and every arm's raw logs and metrics files. It does not receive arm transcripts. It: checks the harness hash matches the plan, recomputes every metric from the raw logs and compares it to the metrics file, applies the decision rule exactly as written, and returns a verdict (choose, eliminate, inconclusive, or none passes) with the numbers behind it. When none passes it also returns a gap report in seed format (see `biz-decomposer/references/seed-schema.md`: avenue, target, measured value with range, binding constraint, and what was tried).
