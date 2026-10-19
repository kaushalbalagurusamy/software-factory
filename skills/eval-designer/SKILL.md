---
name: eval-designer
description: >-
  Use whenever an AI-produced or AI-judged capability needs a real pass/fail bar instead of a vibe
  check: a skill's own trigger accuracy or output quality, a non-deterministic feature (LLM summary,
  classification), or PRD/user-story acceptance criteria for an AI system that need a check assigned.
  Triggers: "how do we know this works", "write evals for X", "benchmark this skill", "design test
  cases", "is this requirement testable", "edge-case input", "golden set", "CI gate for an agent",
  "LLM-as-judge", "rubric", "eval ladder", "error analysis of traces", or auditing an eval suite that is
  slow, flaky or misses real failures, even if the user never says "eval". Produces falsifiable eval
  cases each assigned the cheapest check rung, a golden set plus a diagnostic suite, failure-mode cases
  first, and a trigger-description loop. The one eval skill: it contains the eval ladder, so use it
  instead of eval-ladder. Not for unit tests of deterministic code, implementing the feature under test,
  or code review.
---

# Eval Designer

## Why this exists

Two skills in this factory (`axiomatic-spec`, `grounded-research`) were each benchmarked by hand: someone
wrote eval prompts, ran the skill against them with and without the skill installed, graded the outputs
against assertions, and rolled the results into a `benchmark.json`/`benchmark.md`. Separately, a query set
was used to tune each skill's trigger *description* through several candidate versions until it reliably
fired on the right prompts and stayed silent on the wrong ones. That is the same methodology, reinvented
twice. This skill formalizes it so the next capability — skill or product feature — doesn't reinvent it a
third time.

The retired `sf-spec-testing` skill named the right problem ("replace vibe checks with deterministic
harnesses") but never got built against a real target. Its useful ideas — contract-first framing,
ordering failure-mode injection before the happy path — are folded in here, grounded in what the two
workspaces actually did rather than the abstract 4-tier matrix it proposed.

A separate downloaded skill, `eval-ladder`, independently formalized the piece this skill originally left
implicit: *which kind of check* a given expectation should use, and where the line is between a suite that
gates every commit and one that's read for diagnostic signal. Its ideas are folded in as `reference/
check-rungs.md` (the 5-rung ladder, the golden-set/behavioral-coverage split, promotion rules) and
`reference/error-analysis.md` (finding failure modes inductively from real traces, rather than only the
deductive checklist in `eval-case-design.md`). Reach for those two files whenever you're deciding what type
of check an expectation needs, or auditing why an existing suite is slow, flaky, or missing real failures.

## The two things you'll be asked to evaluate

1. **A skill itself.** Two independent axes: does it *trigger* on the prompts it should and stay silent on
   the ones it shouldn't (see `reference/trigger-and-activation-evals.md`), and does *following* it produce
   good, correct, non-hallucinated output compared to not having it (see `reference/benchmark-workflow.md`).
2. **A product feature with non-deterministic (LLM-driven) behavor.** A clinical co-pilot suggestion, a
   generated summary, a classification — anything where you can't assert exact string equality. The
   mechanics (eval cases, candidate vs. baseline, benchmark aggregation) are identical to case 1; what
   changes is that "expected output" becomes a rubric with a deterministic pass/fail line per criterion,
   and the case set must lean harder on boundary and failure-mode inputs because happy-path fuzzy output is
   the easiest thing to fake. See `reference/llm-judged-rubrics.md`.

If you're not sure which one you have: if there's a `SKILL.md` involved, you're doing both axes of (1). If
the thing under test is a feature, prompt, or model call inside a product (no `SKILL.md`), you're doing (2)
plus, if the feature has an activation/trigger condition of its own (e.g. "when should the co-pilot surface
this suggestion at all"), the activation half of `reference/trigger-and-activation-evals.md` still applies.

## Reuse skill-creator's mechanics — do not reimplement them

`skill-creator` (invoke via the Skill tool as `skill-creator:skill-creator`) already has working,
non-trivial tooling for exactly the benchmark-execution part of this: subagent orchestration for
with/without runs, a grader protocol, an aggregation script, an HTML review viewer, and a trigger-eval
loop that calls `claude -p` to test descriptions. Locate its scripts directory once per session:

```bash
SKC=$(dirname "$(find ~/.claude -path '*/skill-creator/scripts/aggregate_benchmark.py' 2>/dev/null | head -1)")/..
```

Use `$SKC/scripts/aggregate_benchmark.py`, `$SKC/scripts/run_eval.py`, `$SKC/scripts/run_loop.py`, and
`$SKC/eval-viewer/generate_review.py` directly (see the reference files for exact invocations). This skill
only adds what skill-creator doesn't cover: designing eval cases with rubrics instead of prompts, assigning
each expectation the right check rung and suite, ordering failure-mode/boundary cases deliberately (plus
finding the ones you didn't think of via error analysis), generalizing "with_skill/without_skill" to
"candidate vs. baseline" for non-skill targets, and activation evals for a feature that isn't a skill at
all.

## Workflow

### 1. Decide what "candidate" and "baseline" mean here

For a skill: candidate = with the skill installed, baseline = without it (or, when improving an existing
skill, the previous version — snapshot it first). For a product feature: candidate = the new prompt/model/
logic version, baseline = the current production version, a naive baseline (e.g. "always say nothing" or
"always flag"), or a prior candidate version if you're mid-iteration. Name these consistently — the
benchmark tooling groups by the literal strings `with_skill` / `without_skill`, so keep using those two
labels even when the "skill" is actually a feature version, and say once at the top of `benchmark.md` what
each label means in this run.

### 2. Write eval cases: input + falsifiable expected behavior, each assigned a rung

An eval case is not a prompt. A prompt with no rubric can only be eyeballed. Every case needs an `id`, a
`name`, the `prompt`/input, `files` if any fixture is needed, and `expectations` — a list of statements
that are each independently checkable against the transcript and output files, the same discipline
`axiomatic-spec`'s own axioms use (decidable, observable, attributed). Read
`reference/eval-case-design.md` before writing these; it has the schema and worked examples pulled from
both existing workspaces, plus what makes an expectation discriminating rather than decorative (an
expectation that a broken run would also satisfy is worse than no expectation).

Assign each expectation a check rung (1–5) using `reference/check-rungs.md` before moving on: walk the
ladder from assertion upward and stop at the first rung that can actually test the claim as stated. Don't
default to an LLM judge (rung 4) because it's easiest to write — that's the over-climbing failure mode the
ladder exists to catch, and it's exactly as costly to a benchmark's reproducibility as an under-specified
assertion is to its rigor.

### 3. Split cases into a golden set and behavioral coverage

Not every case belongs in the same run. `reference/check-rungs.md`'s two-suite model: a **golden set**
(10–20 cases, all must pass, rung ≤3 only, run on every candidate change) that answers "does it work," and
**behavioral coverage** (30–100+ cases, read as a signal rather than a gate, rungs up to 5 allowed) that
answers "does it work for every category." Default a case to coverage; promote it to the golden set only
when a failure would be an incident rather than a quality complaint — and never promote a case that needs
rung 4+ without first finding a rung-≤3 proxy, or it can't go in the golden set at all. State any such
proxy's blind spot in `benchmark.md`.

### 4. Order failure-mode and boundary cases before happy-path cases

Write the cases that should break the candidate, or that probe the edges of the spec, before you write the
case that just confirms the obvious thing works. A set of five happy-path cases and zero adversarial ones
tells you nothing about the failure surface, which is where AI-driven capabilities actually go wrong in
production. `reference/eval-case-design.md` has the checklist (payload extremes, malformed/ambiguous
input, near-miss non-triggers, contradictory instructions, and — for concurrent or stateful features —
race conditions). That checklist is deductive; once a candidate has real usage (or a large synthetic
batch) behind it, `reference/error-analysis.md` covers the inductive complement — finding the failure
modes nobody thought to write a case for by reading real traces.

### 5. For skill trigger accuracy: run the candidate-description loop

Build a `trigger_eval_set.json` (query + `should_trigger`), weighted toward near-miss negatives (prompts
that share vocabulary with the skill but need something else) rather than obviously irrelevant ones. Run it
against the current description with `run_eval.py`, look at what actually failed, write a revised
`candidate_description_vN.txt`, and re-run — exactly the `candidate_description_v1.txt` →
`candidate_v1_results.json` pattern already in `axiomatic-spec-workspace/trigger-evals/`. Full mechanics,
including the automated `run_loop.py` path, are in `reference/trigger-and-activation-evals.md`. For a
product feature with its own activation condition (not a Claude Code skill), the same precision/recall
framing applies but there's no `run_eval.py` to lean on — that reference file also covers the small
hand-rolled harness for that case.

### 6. Run candidate and baseline, grade, aggregate

Spawn one subagent per (eval case × configuration), save outputs under
`iteration-N/eval-<name>/<with_skill|without_skill>/run-<k>/outputs/`, capture `timing.json` from each
subagent's completion notification (this is your only chance — it's not recoverable later), then grade each
run against its expectations. Reuse skill-creator's `agents/grader.md` protocol as-is for skill evals; for
rubric-graded feature evals, read `reference/llm-judged-rubrics.md` first — the same PASS/FAIL/evidence
discipline applies, but "evidence" means showing the rubric line was actually met, not just that a keyword
appears. Then aggregate with skill-creator's `scripts/aggregate_benchmark.py` and open the results with its
`eval-viewer/generate_review.py`; full directory shape and exact commands are in
`reference/benchmark-workflow.md`.

Once aggregated, pivot behavioral-coverage results into the category × difficulty matrix from
`reference/check-rungs.md` and read it for two things: low pass ratios (a known failure pattern) and empty
cells (an untested blind spot — usually the more urgent of the two). Separately, audit the golden set
itself: any case in it above rung 3 is misfiled and must be resolved before this iteration counts as done,
not just noted for later.

### 7. Iterate

Read the failures, decide whether they're a real gap (the candidate genuinely underperforms) or a weak
assertion (an expectation a broken run would also pass — flag and fix the eval, don't just declare victory).
An under-climbed expectation — one that passed while a human reading the same output immediately sees the
failure — gets promoted a rung per `reference/check-rungs.md`, not just noted. When you change the
candidate (skill body, description, or feature prompt/logic) in response, re-run into a new
`iteration-N+1/`, keep the old one for comparison, and say in the summary what changed and why.

### When to run a full error-analysis pass

The steps above cover designing and running one eval suite. Once a candidate has enough real usage (or a
large enough synthetic batch) behind it, run `reference/error-analysis.md`'s five-step protocol separately
— it's a periodic, trace-driven pass, not a step in every iteration. Its output feeds back into this
workflow at exactly two points: new coverage categories (back to step 4) and under-climbed checks to
promote (step 7).

## Judgment calls

- **Don't build a rubric so rigid it can only match the example you wrote it against.** A rubric line
  should describe a property of a *correct* answer, not the literal wording of one correct answer — a model
  reusing your fixture's phrasing verbatim is a sign the rubric is too narrow, not that the candidate is
  good.
- **Non-discriminating expectations are worse than fewer expectations.** If both candidate and baseline
  pass every case at 100%, either the case is too easy or the expectations don't test what actually
  differs — say so in the benchmark notes rather than reporting the tie as a clean pass.
- **Scale the eval count to the blast radius.** A skill that touches irreversible decisions (schema
  changes, clinical suggestions, financial transfers) earns more boundary/failure-mode cases than a
  low-stakes formatting helper. Don't gold-plate a low-stakes feature with twenty adversarial cases it
  doesn't need.
- **A single run per configuration only tells you eval-to-eval spread, not flakiness.** Say this explicitly
  in benchmark notes (as the reference workspaces do) rather than implying the ± figures are variance when
  they're really just differences across eval cases.
- **Walk the ladder from rung 1 every time — don't default to an LLM judge because it's the easiest check
  to write.** It feels thorough and is usually the wrong instrument; see `reference/check-rungs.md`.
- **Never let a rung-4+ check into the golden set or a per-commit gate.** A non-deterministic gate trains
  people to re-run until green, which destroys what "gate" means.
- **An unvalidated judge is a number with unknown meaning.** Every rung-4 grader needs a rung-5 human-label
  sample it's measured against — decide who labels and how many before trusting its verdicts.
- **For human review, use a binary verdict plus free-text notes, not a numeric scale.** A 1–5 rating makes
  reviewers agonize over 3-vs-4 and produces an unactionable average; the prose is where the failure
  taxonomy in `reference/error-analysis.md` actually comes from.
- **Coverage tags must never change how a case runs.** If a tag changes execution, it's configuration, not
  a label, and the category × difficulty matrix stops meaning what it appears to mean.
