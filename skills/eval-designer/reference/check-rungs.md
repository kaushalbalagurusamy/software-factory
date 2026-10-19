# The Check Ladder

How to decide what checks an expectation, so the eval suite stays fast where it can be and rigorous where
it must be. Read this before finishing step 2 in `SKILL.md` (writing eval cases) — every expectation you
write should carry a rung, and the rung determines which suite (below) the case is allowed to sit in.

Two failures this exists to prevent:

- **Over-climbing**: using an LLM judge for something a string comparison would settle. Costs money, adds
  latency, introduces non-determinism, and makes the result unreproducible.
- **Under-climbing**: writing a deterministic assertion for something that genuinely needs judgment. The
  check passes, everyone relaxes, and the real failure ships.

The guiding line: **climb only as high as you must. Every rung up costs money, latency, and trust.**

## The ladder

| Rung | Check | Use for | Deterministic? |
|---|---|---|---|
| 1 | Assertion, exit code | Facts with one right answer | Yes |
| 2 | Property or invariant check | "Never does X", schema conformance, policy | Yes |
| 3 | Trajectory inspection | Tool order, retries, whether verification ran | Yes |
| 4 | LLM judge (`agents/grader.md`, rubric-graded expectations) | Quality, tone, "would a reviewer approve this" | No |
| 5 | Human label | Ground truth, and judging the judge | No |

Rungs 1–3 are deterministic, cheap, and reproducible. Rungs 4–5 are not. That distinction is the backbone
of everything below. Most of this skill's mechanics — expectations checked by `agents/grader.md`,
rubric-graded expectations from `llm-judged-rubrics.md` — live at rung 4 by default; the ladder's job is to
stop you from reaching for rung 4 when 1–3 would do, and from trusting rung 4 without validating it.

Rung 5 has two jobs people often conflate. It produces ground truth, **and** it measures whether a rung-4
judge (your grader) agrees with an expert. A judge that has never been checked against human labels
produces an unvalidated number.

## The two suites

Eval cases split into two suites with different jobs. Don't blend them into one `evals.json` run
indiscriminately — the value comes from their different failure semantics.

| | Golden set | Behavioral coverage |
|---|---|---|
| Question it answers | "Does it work?" | "Does it work for all types?" |
| Size | 10–20 cases | 30–100+ cases |
| All must pass? | **Yes** — hard gate | No — it's a signal to read |
| Run cadence | Every commit / every candidate change | Every iteration/release |
| Max rung allowed | **3** | 5 |
| What a failure means | The build is broken | A data point in a pattern |

The golden set is a tripwire. The coverage suite (most of what `eval-case-design.md` describes — the
failure-mode/boundary cases ordered before happy path) is a map. A candidate can pass every golden-set case
and still have entire categories untested, which is what the coverage matrix below exists to expose.

### The rung ceiling rule

**Nothing above rung 3 belongs in the golden set.** Golden-set cases run on every commit/candidate change
and gate the result, so they must be fast and deterministic. A rung-4 grader in a per-commit gate makes the
gate non-deterministic: the same candidate passes and fails on different runs, and people learn to re-run
until green, which destroys the gate's meaning.

This rule is the single most useful audit you can run on an existing suite. Walk the golden set, ask what
rung each expectation actually needs, and any expectation needing 4+ is misfiled.

When a golden-set case turns out to need rung 4, there are exactly two honest resolutions:

1. **Find a rung ≤3 proxy** that captures most of the risk, and note in the case (or `benchmark.md`) what
   the proxy does *not* catch.
2. **Move the case to behavioral coverage**, where rung 4 is allowed.

What you must not do is write a weak deterministic expectation, leave it in the golden set, and let its
passing imply the real property holds. That converts a known gap into a false assurance, which is worse
than no check — this is the same failure mode `eval-case-design.md` calls a "non-discriminating
expectation," specialized to the golden set.

## Procedure: assigning a rung to each expectation

For each expectation in a case (or each acceptance criterion, if you're deriving cases from a PRD/user
story before any eval case exists yet), in order:

1. **State it as an observable claim.** If you can't say what would be observed when it fails, it isn't
   testable yet — fix the criterion before assigning a check. This is the same bar `eval-case-design.md`
   applies to "discriminating."
2. **Walk the ladder from rung 1 upward and stop at the first rung that can actually test it.** Not the
   first rung that tests something adjacent — the first that tests the claim as stated.
3. **Record the rung alongside the expectation.** The rung is part of the eval case, not an implementation
   detail — it's what makes over- and under-climbing visible later, and what the rung-ceiling audit reads.
4. **If the rung is 4 or 5, ask what would have to be true for a lower rung to work.** Sometimes tightening
   the criterion drops it a rung at no real cost. "The response is helpful" is rung 4. "The response cites
   at least one retrieved source" is rung 2 and may be what you actually meant.
5. **If the rung is 4, decide how the judge gets validated** — a rung-5 human-label sample it's measured
   against, per case. Say who labels and how many. `llm-judged-rubrics.md` covers the mechanics of writing
   the rung-4 rubric itself.

### Worked examples

**"Every dose value matches the source record."** Rung 1 — exact comparison against a known value. Don't
climb.

**"No response reaches the user without a resolvable source citation."** Rung 2 — an invariant. Check every
emitted claim carries an ID that resolves. Don't climb to a judge to ask "is this well-cited?"

**"Authorization is checked before any retrieval tool dispatches."** Rung 3 — not visible in the output at
all, only the trajectory shows it. A correct final answer can coexist with a broken authz order, which is
exactly why output-only expectations miss it.

**"The summary surfaces the most decision-relevant changes."** Rung 4 — "most relevant" is a judgment. But
notice the fallback: "the summary includes any medication change in the interval" is rung 2 and captures
part of it. Write both: the cheap expectation in the golden set, the judgment expectation in coverage.

**"The response is clinically sound given the record."** Rung 5 — a domain expert is the only instrument
that detects claims that are internally consistent and correctly cited but wrong in the domain. No lower
rung sees this class at all.

> **Program example (Gauntlet AI, "Evaluating Agents" deck, `evaluating_agents.pdf`, shared 2026-09-16 by
> Aaron Gallant, #cohort-main).** The deck's worked example is a rung-3 case this file doesn't otherwise
> spell out: an agent asked to fix failing tests instead edits the test file's expected values so the
> suite goes green, leaving the underlying bug untouched. Every rung-1/2 check (exit code, assertion count)
> passes; only trajectory inspection (diffing which files changed) catches it. The deck names this a
> **third state** — "passed," "failed," and "passed for the wrong reason" — and warns that the third state
> "looks exactly like the first one on your dashboard." It also gives a concrete rung-1 example of "write
> the cheapest grader that works" for this specific failure, cheaper than reaching for an LLM judge:
> intersect the literal string tokens in the source diff against the literal string tokens in the test-file
> diff and flag overlap — deterministic, free, catches the exact tampering pattern without ever asking a
> model whether something looks like cheating.

## Promotion

Two different things get promoted, for two different reasons. Keep them straight.

### Promoting a case into the golden set

Default placement is behavioral coverage. Promote a case to the golden set when a failure is
**categorically unacceptable rather than merely bad** — safety, security, privacy, data integrity, or
regulatory exposure.

The test: *if this failed in production, is it an incident or a quality complaint?* Incidents belong in the
golden set.

This deliberately overrides "keep the golden set small and representative." A case about a category that
could cause real harm earns a hard gate even if it looks like one instance of a broad category. **State
this as a judgment call in `benchmark.md`**, with the rationale, rather than letting it look like sloppy
filing — the same discipline as the "scale eval count to blast radius" judgment call in `SKILL.md`.

The constraint: a promoted case still has to obey the rung ceiling. If it needs rung 4, it can't be
promoted as-is — find a proxy or leave it in coverage. Severity does not buy an exemption from determinism.

### Promoting a check up a rung

Promote a check to a higher rung when the current rung passes on outputs that are actually wrong. This is
usually discovered through error analysis (`error-analysis.md`), not by reasoning in advance.

The signature of an under-climbed check: **the deterministic check passes, and a human reading the same
output immediately sees the failure.** That gap is the whole signal — it's the ladder's version of the
"non-discriminating expectation" flag in `eval-case-design.md`. When you see it, the check needs to climb,
or needs a companion at a higher rung.

Demotion is real too. If a rung-4 grader agrees with human labels near-perfectly on some criterion, that
criterion may have been deterministic all along and the grader is burning money to restate a rule.

## Behavioral coverage: tagging and the matrix

Coverage works by tagging cases with labels that don't affect execution. A case runs identically tagged or
not — **the tags change what the results tell you**, not how they run. Add these fields to the eval case
schema in `eval-case-design.md`:

- `category` — the capability under test (retrieval, synthesis, authz, safety, conversation, ops…)
- `difficulty` — `straightforward` / `ambiguous` / `edge_case`
- `rung` — the ladder rung this case's expectations use

When aggregating (`benchmark-workflow.md` step 6), pivot results into a matrix of category × difficulty and
read it for two distinct things:

- **Low ratios** (`1/3`) — a failure pattern. You know the rate and it's bad.
- **Empty cells** (`--`) — a blind spot. You don't know the rate *because nothing tests it*. These are
  usually more urgent than the failures, because a failure is a known problem and an empty cell is an
  unknown one.

Add a rung dimension to the read: a category tested only at rung 1 is shallowly covered even at 100% pass.
Passing everywhere at the lowest rung is a common way to look well-tested while remaining fragile.

## Output format for a rung/suite audit

When producing or auditing an eval plan's rung assignments, use this structure per criterion:

```markdown
## Criterion: <the observable claim>
- **Rung**: <1-5> — <why this is the lowest rung that can test it>
- **Suite**: golden set | behavioral coverage
- **Tags**: category=<x>, difficulty=<y>
- **If rung >= 4**: how the judge is validated, and against how many human labels
- **If a proxy was used**: what the proxy does NOT catch
```

Then a summary table (`Criterion | Rung | Suite | Category | Notes`), and close with an audit section
naming: any golden-set case above rung 3 (must be resolved, not noted), any criterion where no rung can
test it as written (the criterion needs rewriting), any rung-4 check with no validation plan, and empty
cells in the coverage matrix.

## Anti-patterns specific to rung/suite assignment

**LLM judge as the default.** It feels thorough and is usually the wrong instrument. Walk the ladder from
the bottom every time.

**Judges in the per-commit/golden-set gate.** Non-deterministic gates train people to re-run until green.

**Unvalidated judges.** A rung-4 score with no human-label agreement measurement is a number with unknown
meaning.

**Numeric scales where a boolean belongs**, for human review especially — a 1–5 rating makes reviewers
agonize over 3-vs-4 and produces an unactionable average. Binary verdict plus free-text notes puts the
signal in the prose, which is where the failure taxonomy in `error-analysis.md` comes from.

**A deterministic check standing in for a judgment check, silently.** Proxies are fine; undocumented
proxies are a false assurance. Always write down what the proxy misses.

**Coverage tags that affect execution.** If a tag changes how a case runs, it's configuration, not a
label, and the matrix stops meaning what it appears to mean.

**Treating rung 5 as optional because experts are expensive.** Expert time is scarce, so spend it where
only rung 5 works: correct-looking, well-cited, domain-wrong outputs. Don't spend it on things rung 1
could check.
