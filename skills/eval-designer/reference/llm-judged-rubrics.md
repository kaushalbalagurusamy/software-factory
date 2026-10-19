# Deterministic Rubrics for Non-Deterministic Output

This is for case 2 in SKILL.md: a product feature whose output is inherently fuzzy — a generated summary,
a clinical suggestion, a classification with a confidence score. You cannot assert exact string equality,
and "looks reasonable" is exactly the vibe check this skill exists to replace. The fix is not a looser
assertion; it's a rubric where each line is still individually decidable, the same bar `axiomatic-spec`
holds contracts to.

A rubric-graded expectation is, in `check-rungs.md` terms, a **rung 4** check by construction — it needs a
reader, human or LLM, not a script. Before writing one, confirm rungs 1–3 genuinely can't test the claim
(tighten the wording if they can), and once you do write one, it belongs in behavioral coverage, never the
golden set, and needs a rung-5 human-label sample to validate the grader against (`check-rungs.md`'s
promotion section).

## Structure every rubric in three tiers (adapted from `sf-spec-testing`, kept because it's still the right
shape — the difference is each tier below is graded by evidence-based pass/fail, not a 1-10 vibe score)

The three tiers below map onto the ladder as rung 1 (structural), rung 2 (deterministic constraints), and
rung 4 (rubric-graded judgment) respectively — writing a rubric almost always means writing all three, not
defaulting straight to tier 3.

1. **Structural conformance.** Does the output parse into the shape the downstream system requires — the
   right fields present, the right type for each, no missing keys? This is checkable with a script, not a
   judgment call, and should be. If the feature emits JSON/a schema, validate it programmatically before
   any human or LLM judgment enters the picture.
2. **Deterministic constraint checks.** Hard must-not and must statements that don't require judgment about
   quality, only presence/absence: forbidden content never appears (a diagnosis suggestion never states a
   specific drug dosage the model isn't authorized to recommend, a summary never fabricates a value not
   present in the source document), required disclaimers/citations are present, numeric outputs fall within
   a physically/clinically plausible range. Write these as literal checks a grader (or script) can run
   without interpreting intent.
3. **Rubric-graded judgment.** The part that genuinely needs a reader — but "reader" here means a grader
   following `agents/grader.md`'s evidence discipline (from skill-creator), not a free-floating quality
   score. Each rubric line should read like an `axiomatic-spec` postcondition: attributable to a specific
   part of the output, and falsifiable by pointing at what's missing or wrong. "The summary is good" is not
   a rubric line. "The summary states the primary reason for the visit stated in the source note, and does
   not introduce a reason not present in the source" is.

Embedding-cosine-similarity-to-a-golden-answer (as `sf-spec-testing` originally proposed) is a legitimate
option when you have a large graded corpus and need cheap regression detection at scale, but it trades away
interpretability — a failing score doesn't tell you *what* was wrong, and choosing a defensible threshold is
itself a judgment call that needs justifying. Prefer the explicit rubric-line approach above by default; it
requires no extra embedding infrastructure or dependency, and every failure comes with a reason attached.
Reach for similarity scoring only when rubric grading genuinely doesn't scale (e.g. thousands of cases run
on every commit) and even then, keep a rubric-graded sample as a check on what the similarity threshold is
actually measuring.

## Write boundary and failure-mode cases before happy-path ones — this matters more here than anywhere else

A generative feature can produce fluent, confident-sounding output for almost any input, including inputs
where the correct behavior is to abstain, flag uncertainty, or refuse. Happy-path cases are the easiest
thing for a bad candidate to fake — a model that always outputs a plausible-sounding suggestion will pass
every happy-path case regardless of whether its underlying judgment is any good. The cases that actually
discriminate are:

- **Input where correct behavior is silence/abstention.** A clinical co-pilot given ambiguous or
  insufficient data should say so, not fabricate a confident suggestion — a rubric line here is a
  *must-not* ("does not state a specific recommendation when required inputs X, Y are absent from the
  chart"), which only a genuinely careful candidate can satisfy.
- **Input that resembles a known pattern but differs in the detail that matters.** The near-miss case from
  trigger evals, applied to content: a symptom cluster that looks like condition A but the one differentiating
  lab value points to B — does the suggestion get the differentiator right, or pattern-match on the surface
  similarity?
- **Contradictory or stale source data.** Two notes in the chart disagree, or the most recent data point
  supersedes an older one still present in context — does the output resolve this correctly or silently
  pick one?
- **Adversarial/injected content in the input**, where relevant (e.g. free-text fields containing
  instruction-like text) — does the feature stay scoped to its actual task?
- **Scale/volume stress**: a very long input document/chart history — does quality degrade, or does the
  feature silently truncate and miss something material?

Only after these should you add one or two clean happy-path cases, to confirm baseline competence.

## Grading

Use the same `grading.json` shape skill-creator's grader produces (`expectations[]` with `text`/`passed`/
`evidence`, plus `summary`). The grader's evidence for a rubric line must show the specific span of the
output that satisfies or violates it — not just restate the rubric line as true. Where a rubric line is
programmatically checkable (tier 1/2 above), write the check as a script and run it rather than having a
grader eyeball it; reserve the grader's judgment for tier 3.
