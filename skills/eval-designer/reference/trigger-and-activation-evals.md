# Trigger and Activation Evals

This is the axis that asks "does the capability fire when it should and stay silent when it shouldn't" —
distinct from "is the output good once it does fire" (that's `benchmark-workflow.md`). For a Claude Code
skill this is literally the SKILL.md `description`. For a product feature it's whatever governs when the
feature activates (a classifier threshold, a routing prompt, a rule).

## Skill trigger evals (there's real tooling for this — use it)

### The eval set

`trigger_eval_set.json` is a flat list, not the case-with-expectations shape used elsewhere:

```json
[
  {"query": "we're adding soft-delete to the orders table in our rails monolith (~1.2M LOC). before anyone touches code i want to know every place that reads orders and which invariants we'd break. write it up as a spec", "should_trigger": true},
  {"query": "review PR #412 for me, it removes the lock in cache/lru.go and I'm not sure that's safe", "should_trigger": false}
]
```

Aim for 20-32 queries, split roughly evenly. Positive queries need phrasing coverage (formal and casual,
with and without naming the capability explicitly) — see the range in
`axiomatic-spec-workspace/trigger-evals/trigger_eval_set.json`. Negative queries are worth almost nothing
if they're obviously irrelevant; the useful ones are **near misses** that share vocabulary or a keyword
with the capability's domain but genuinely need something else (e.g. "extend unity's SMTContractProver..."
sounds spec-adjacent but is an implementation task, not a specification task). If every negative query is
trivially distinguishable, the eval set can't tell you whether the description is too broad.

### Running it

```bash
python3 -m scripts.run_eval \
  --eval-set <path-to-trigger_eval_set.json> \
  --skill-path <path-to-skill> \
  --model <model-id-powering-this-session> \
  --runs-per-query 3 \
  --verbose
```

Run from skill-creator's directory (or `python3 -m scripts.run_eval` after `cd`-ing there). Use the actual
model ID powering the current session (check the system prompt) so the trigger test matches what the user
experiences, not an arbitrary default. `--runs-per-query 3` matters — triggering is not fully deterministic,
and a single run can't distinguish a flaky borderline case from a solid one (see the `0.6666...` and
`0.333...` trigger rates in `axiomatic-spec-workspace/trigger-evals/candidate_v1_results.json` — both came
from genuinely marginal queries, not noise).

### Iterating on the description

Write the current or proposed description to `candidate_description_v1.txt`, run it, save results to
`candidate_v1_results.json` and the raw log to `run_eval_candidate_v1.log` — this is the exact pattern
already in use. Read the failures, understand *why* the description didn't cover them (missing phrasing,
too narrow a trigger list, a negative case that's actually ambiguous and arguably should trigger), write
`candidate_description_v2.txt`, and re-run. Stop when the held-out failures are either fixed or judged to
be genuinely ambiguous (not every query has a clean right answer — say so rather than forcing a rewrite
that overfits to one query).

For a fully automated version of this loop (train/held-out split, iterative rewriting, up to N rounds):

```bash
python3 -m scripts.run_loop \
  --eval-set <trigger_eval_set.json> \
  --skill-path <skill-path> \
  --model <model-id> \
  --max-iterations 5 \
  --verbose
```

This splits 60/40 train/test, evaluates the current description 3x per query, proposes an improved
description from what failed, and picks the best-scoring one on the *held-out* set (not train) to avoid
overfitting the description to the exact queries you wrote. Still read the output — an automated pick can
still overfit if the eval set itself is too narrow.

## Activation evals for a non-skill product feature

There's no `run_eval.py` equivalent for "should the co-pilot surface this suggestion" because that's not a
Claude Code skill description — it's whatever internal logic decides to fire (a classifier, a threshold, a
routing prompt). The same precision/recall framing still applies; you just drive it by hand or with a small
script instead of `claude -p`:

1. Build the same shape of eval set: `{"input": <patient context / document / event>, "should_activate":
   bool}`, weighted toward near-miss cases — inputs that are clinically adjacent to the trigger condition
   but shouldn't fire (e.g. a vital sign that's borderline-normal vs. one that's genuinely out of range),
   and inputs that should fire but are phrased/structured unusually.
2. Run the actual candidate logic (the real code path or prompt, not a re-description of it) against each
   input, N times if there's any non-determinism, and record activate/silent.
3. Report as a confusion matrix (true positive / false positive / false negative / true negative) rather
   than a single "accuracy" number — for a clinical suggestion feature specifically, false negatives (a
   suggestion that should have fired and didn't) and false positives (alert fatigue) usually have very
   different costs, and collapsing them into one accuracy score hides which one is actually the problem.
4. Treat this as its own iteration loop exactly like the description loop above: change the
   threshold/prompt/logic, re-run, compare the confusion matrix, not just a headline number.
