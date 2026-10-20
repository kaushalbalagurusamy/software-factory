---
name: doc-sync
description: >-
  Use at the end of a loop iteration whenever a decision, ADR, or drift check just changed or
  superseded something — after accepting or amending an ADR, after a drift check against
  source-of-truth requirements finds a mismatch, after a PRD/spec revision, or right before
  declaring a milestone or submission done. Triggers on phrases like "that supersedes the old
  design", "update the docs to match", "are the docs still accurate", "sweep the documentation",
  "milestone is done, anything stale", or any moment a decision record changed but the documents
  that describe the system in prose (architecture overview, README, requirements/status tracker,
  diagrams, metric or cost figures, published artifacts/dashboards, API or interface contracts)
  were not touched in the same pass. Builds a dependency map from the changed decision to the
  documents that derive from it, prioritises externally-visible and submission-required documents
  over internal notes, detects staleness concretely (contradicted claims, superseded numbers,
  renamed or removed components, references to superseded records) rather than by vibe, then
  either updates each document or annotates precisely what is superseded and by which record, and
  reports what was updated versus deliberately left. Not for writing the ADR itself or running the
  drift check itself (that's one-way-door / implementation-review's job) — this is the propagation
  step that runs right after, closing the gap between "we decided X" and "every document that says
  something else has been fixed or flagged."
---

# Doc Sync

## Why this exists

A development loop that runs requirements → research → experiments → decisions (ADRs) → MECE
eval-driven specs → implementation → review → drift check is good at accumulating decisions. It is
bad, by default, at propagating them. Each iteration a drift check or a new ADR changes the plan,
and the decision record itself gets written down correctly — but the documents other people
actually read keep describing the design as it was before the decision. Nobody agreed to let that
happen; it's just what's left over once the decision is made and everyone moves on to the next
task.

This matters more than it looks like it should, because the stale documents are frequently the
*deliverables*. A flawless ADR trail is worth nothing if the architecture document a reviewer
opens at a deadline still describes the superseded design. The ADR proves you made the right call;
it does not, by itself, make the right call visible to anyone reading anything else.

This skill is the propagation step: the sweep that runs after a decision lands, before the
iteration is declared closed, that finds every document downstream of that decision and either
brings it current or marks exactly what in it is now superseded.

## When to run it

Run this at the end of a loop iteration, specifically:
- Right after a drift check finds and resolves a mismatch against source-of-truth requirements.
- Right after accepting, amending, or superseding an ADR (or any equivalent decision record).
- Right after a PRD/spec revision that changes a name, number, component, or contract.
- Right before declaring a milestone, phase, or submission done — as a final gate, even if you
  believe nothing changed this iteration, because "I don't think anything downstream needs
  updating" is exactly the belief that produces silent staleness.

If none of the above happened this iteration, there is nothing to sync — don't run it reflexively
on every turn.

## Decision procedure

1. **Identify the decision that just changed.** Name it precisely: which ADR, which spec section,
   which requirement, what the old value/design was and what it is now. If you can't state the
   before/after in one sentence each, the decision isn't concrete enough yet to propagate.

2. **Build the dependency map.** Ask: which documents derive a claim, number, name, or diagram
   from this decision? A decision rarely lives alone. Walk the common propagation targets (see
   checklist below) and for each one, decide in or out — don't skip silently. If the project has
   an existing map of docs to their source decisions, use it; if not, this pass is also a chance
   to leave a note (a "derived from ADR-N" comment or manifest entry) so the next sync is cheaper.

3. **Prioritise by audience.** Rank the in-scope documents by who reads them and when. Anything
   external — handed to a reviewer, grader, stakeholder, or another team, or published as a
   submission/deliverable/dashboard — goes first, because someone opens it on a schedule you don't
   control. Internal notes, scratch docs, and working logs can lag a cycle without real cost. When
   time is short, do the external ones and say so explicitly rather than doing a shallow pass over
   everything.

4. **Detect staleness concretely.** For each document in scope, check for:
   - A claim (prose, number, or diagram) that the new decision now contradicts.
   - A superseded number — a metric, cost, latency, size, or count that the decision changed.
   - A named component, service, or field that was renamed, merged, or removed.
   - A cross-reference (link, ADR id, "see design doc X") that now points at a superseded record.
   Don't rely on a general impression that the document "seems fine" — check it against the
   specific before/after from step 1. A document can look polished and still assert the old thing.

5. **Update or explicitly mark — never leave it silently stale.** For each stale spot, either:
   - Bring it current (rewrite the claim/number/name to match the new decision), or
   - Annotate precisely what is superseded and by which record — e.g. "~~this metric~~ superseded
     by ADR-014, see [link]" — when a full rewrite isn't warranted yet or you're not the right
     owner to rewrite it. An honest "this is stale, here's why, here's the current source of
     truth" is a correct outcome. A document that looks current but isn't is the failure this
     skill exists to prevent.

6. **Report the sweep.** List what you updated and what you deliberately left (and why — lower
   priority, needs an owner's judgment call, out of scope this pass). The point is that the user
   can see the sweep happened and audit the choices, not just trust that it did.

7. **Check the plain-English module docs.** If the project has `docs/eli12/`, run
   `python3 skills/eli12-docs/scripts/eli12.py check --root . --changed <base ref>` and treat every
   finding as a stale document: fix it (see the `eli12-docs` skill) or report why it stays.

8. **Delegate the mechanical part.** Once the dependency map and the before/after are established,
   checking a stack of documents against a known set of superseded claims is cheap, well-specified
   work — a good candidate to hand to a smaller/cheaper model via a subagent, one document (or a
   batch) per dispatch, with the before/after and the priority order given explicitly rather than
   re-derived. Keep the higher-judgment calls — what counts as "derived from," what's safe to mark
   versus rewrite, prioritization under time pressure — for yourself.

## Document classes that commonly go stale

Use this as a checklist when building the dependency map in step 2; not every class applies every
time, but check each one off deliberately rather than skipping it by default.

- **Architecture overview** — component names, data flow, diagrams of "how it works now."
- **Requirements / status trackers** — anything claiming a requirement is met, in progress, or
  blocked, and anything that names the current design as the answer to a requirement.
- **READMEs and quickstarts** — setup steps, commands, environment variables, service names.
- **Diagrams** — sequence, architecture, or data-flow diagrams; these decay silently because
  nothing forces a re-render when the underlying design changes.
- **Metric and cost figures** — latency numbers, prices, throughput, accuracy figures quoted
  anywhere outside the experiment record that produced them.
- **Published artifacts or dashboards** — anything already shared as a link, a deployed page, or a
  submitted deliverable; these are the highest-priority class because someone else may already be
  looking at them.
- **API / interface contracts** — field names, endpoint shapes, function signatures described in
  prose docs (not just in code, which usually fails loudly if wrong — the prose description next
  to it doesn't).

## Worked example

An ADR is accepted: "Switch the retrieval backend from a single FAISS index to a two-stage
BM25-then-rerank pipeline, because recall on long-tail queries was under target." This supersedes
an earlier ADR that had picked the FAISS-only design and quoted its latency and recall numbers.

1. **Decision**: retrieval backend, FAISS-only → BM25 + rerank two-stage. Old recall figure
   (quoted at 71%) is superseded by a new measured figure (89%).

2. **Dependency map**: the architecture overview describes the retrieval component and includes a
   diagram of the FAISS index; the requirements tracker cites the 71% recall figure as evidence a
   requirement is met; the README's "how search works" section names FAISS; a published metrics
   dashboard shows the old recall number; the API contract doc is unaffected (interface didn't
   change, only the backend behind it).

3. **Priority**: the published dashboard and the requirements tracker go first (external/
   submission-visible); the architecture doc and README next; nothing internal-only in this case.

4. **Staleness detected**: the architecture diagram shows a single FAISS box (renamed/removed
   component); the requirements tracker's 71% is a superseded number; the README's "search uses
   FAISS" is a contradicted claim; the dashboard's recall figure is a superseded number; the old
   ADR is now cross-referenced from three places as if it were still current.

5. **Outcome**: architecture diagram and README rewritten to describe the two-stage pipeline;
   requirements tracker's recall figure updated to 89% with a cite to the new ADR; dashboard
   flagged with a note ("figure stale, pending next data refresh, see ADR-022") since the pipeline
   that generates it can't be rerun until the next scheduled batch — an explicit mark rather than a
   silent gap.

6. **Report**: "Updated: architecture overview, README, requirements tracker. Marked-not-updated:
   published dashboard (recall figure stale pending next refresh, annotated with ADR-022 pointer).
   Out of scope: no change needed to the API contract doc — interface unchanged."
