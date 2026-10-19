# Error Analysis Protocol

The cases in `eval-case-design.md`'s failure-mode/boundary checklist are deductive — they test the
failures you imagined. This protocol is inductive: run real traces, have someone read them, let the
failure taxonomy emerge from what actually broke. Read this when setting up or running an error-analysis
pass — typically after a candidate has been in front of real usage (or a large synthetic batch) and you
want to find gaps the eval-case checklist didn't anticipate. It's the concrete source for two things:
which existing checks are under-climbed (`check-rungs.md`'s promotion rule), and which coverage categories
are missing from the matrix.

## Why this exists

It is the only reliable source for a category of failure that automated checks structurally cannot see:
**output that is internally consistent, correctly sourced, and still wrong.**

A worked example. An agent is asked how many refunds were processed in a quarter for which the database
holds no data. It runs the right query over the right date range, gets zero rows, and answers "0 refunds
were processed," citing the query. Every deterministic check passes — the tool was correct, the citation
resolves, the number is derivable from the result. An LLM judge likely passes it too. But "zero refunds
happened" and "there is no data for this period" are different claims, and only one of them is true. A
human sees it instantly.

Every domain has this class. Finding it is the job.

## The five steps

### 1. Gather representative traces

Real user interactions when you have them; synthetic ones when you don't (the candidate-vs-baseline runs
from `benchmark-workflow.md` are a source of synthetic traces too, if you've already run some). Traces are
cheap to generate and expensive to review — **reviewer time is the bottleneck, not trace volume.** Generate
generously.

Cover the span of your use cases, not just the happy path. Deliberately include: missing data, ambiguous
phrasing, out-of-scope requests, and permission boundaries. If your requirements list edge cases, generate
traces for each.

### 2. A domain expert reviews and journals

Open-ended notes in the reviewer's own words. **Journaling, not scoring.**

This matters more than it sounds. A rating scale asks the reviewer to categorize before a taxonomy exists,
which is backwards — categories emerge from the notes in step 4. A scale also produces an average nobody
can act on. Use a **binary verdict** (error / looks right) plus free-text notes, and let the prose carry
the signal — the same shape `check-rungs.md`'s anti-patterns section argues for over a 1–5 scale.

Who counts as the expert: someone who can judge domain correctness, not just fluency. If no true expert is
available, the honest options in descending order are:

1. A real practitioner for even one hour — an hour of genuine review beats a hundred self-reviewed traces
2. Review against published standards or documentation, explicitly labeled as a proxy
3. Self-review with a written checklist, with the limitation stated plainly

An LLM reviewing its own traces is not expert review — it is not rung 5, whatever it's labeled as. The
failure class that experts exist to catch is precisely the one a model shares blind spots with.

### 3. Focus on the first failure in each trace

Upstream errors cause downstream ones. If retrieval pulled the wrong record and synthesis then faithfully
summarized it, that is **one** failure, not two. Counting downstream symptoms inflates the taxonomy and
points remediation at the wrong step.

This step is unimplementable without step-level tracing. Correlation IDs spanning every tool call and model
interaction are what make it possible — this is the concrete payoff of observability for evals, not just
for ops. (This is a stronger tracing bar than `benchmark-workflow.md`'s `timing.json`, which only captures
aggregate duration/tokens, not per-step attribution.)

Record the first failing **step**, not just that the trace failed.

> **Program example (Gauntlet AI, "Evaluations Part 1 with Byron," live Q&A, shared 2026-09-16 by Byron
> Mackay).** Asked how this scales when a single trace holds many LLM calls (a multi-agent or
> supervisor/worker pipeline), Byron's answer was not to review the whole call stack in order: reviewing ten
> chained LLM calls per trace is "helpful, but it's also burdensome." Instead, **start from what the user
> actually sees** — the final output — decide if *that* looks right, and only work backward through the
> preceding steps when it doesn't. This is a triage order for reviewer time on top of step 3's rule, not a
> replacement for it: the first failure found working backward from the output is still the one step 3 asks
> you to record and stop at. It matters most exactly where trace length grows — a supervisor dispatching to
> multiple workers, each producing its own tool calls and model spans, is the shape reviewer time runs out on
> fastest.

### 4. Categorize into a failure taxonomy

After a batch of reviews, cluster the notes into distinct, named categories. Let names come from the notes
rather than from a pre-made list — a category you invented before looking is a hypothesis, not a finding.

Good categories are **actionable**: each should suggest a different fix. If two categories would be fixed
the same way, merge them. If one category's cases would need three different fixes, split it.

For each category record: name, description, trace count, the step where it first appears, and the rung
(`check-rungs.md`) that would catch it.

### 5. Iterate to theoretical saturation

Stop when new traces stop revealing new failure modes. Aim for at least ~100 traces reviewed before
claiming saturation. If the last 20 traces produced no new category, you're likely saturated. If they
produced three, keep going.

## Feeding results back

The taxonomy is not the deliverable. These four moves are:

**1. Under-climbed checks.** Any failure a human caught that all automated checks passed is an under-climbed
check per `check-rungs.md`'s promotion rule. Either promote it a rung or add a companion check at a higher
rung.

**2. Missing coverage categories.** A failure category with no matching column in the coverage matrix
(`check-rungs.md`) is a new column. Write cases for it using `eval-case-design.md`'s schema.

**3. Invented categories.** A coverage category that produced zero failures across the whole review may be
one you imagined rather than found. Not automatically wrong — it may be genuinely solid — but worth
questioning.

**4. Golden-set candidates.** A failure that would be an incident rather than a complaint gets promoted to
the golden set, subject to the rung ceiling (nothing above rung 3). If it needs rung 4, find a proxy or
leave it in coverage.

## Review tooling

General-purpose observability platforms are strong at tracing, dataset versioning, and running scorers.
They are consistently weak at this specific step, because their annotation UIs are built around
**scoring** — thumbs, rubrics, 1–5 scales — which fights the journaling that step 2 requires.

Keep the platform for tracing and dashboards. Build a thin local review layer for annotation. It's usually
a script and a small UI, not a platform — closer in scope to skill-creator's `eval-viewer/generate_review.py`
than to a full observability product.

What the review layer needs:

- **Trace beside source records.** The reviewer must check claims against underlying data without going
  hunting. This is the single biggest determinant of how many traces get reviewed per hour.
- **Binary verdict, keyboard-driven.** Navigation and verdict on single keys. With a scarce reviewer, this
  roughly doubles throughput.
- **Free-text notes with no required category.** Categories come later; forcing one now corrupts step 4.
- **First-failure step marking.** Step 3 is otherwise unimplementable.
- **Structured export.** JSONL or similar, so notes can be clustered in step 4 rather than re-read.
- **Progress and filtering.** Reviewed / unreviewed / errors, so a session can be resumed.

**Data sensitivity**: when traces contain regulated or confidential data, a local review tool keeps
annotation inside your boundary rather than shipping records to a third-party UI. Where a compliance
review is part of the project, this is a stronger argument for building it than ergonomics is.
