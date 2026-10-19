# Writing Eval Cases

## Schema

Whether you're evaluating a skill or a product feature, an eval case is one JSON object. This is the same
shape skill-creator uses for `evals/evals.json` and each case's `eval_metadata.json` — keep using it so the
aggregation and viewer tooling works without modification:

```json
{
  "id": 2,
  "name": "brownfield-small-ledger-transfer",
  "prompt": "In our ledger-service repo (at ./repo) we want to add a transfer(...) operation... Spec this change properly before anyone writes code.",
  "expected_output": "One sentence a human skims to remember what this case is checking.",
  "files": ["fixtures/ledger-service"],
  "expectations": [
    "Before writing contracts, the output contains an explicit scoping section that lists the files in scope with a reason for each, covering ledger/ledger.py, ledger/ledger.go, api/handlers.py and tests/test_ledger.py",
    "The transfer contract states conservation (from and to balances sum to the same total before and after) and that no partial write occurs on any error"
  ]
}
```

- `id` / `name`: `name` should describe what's being probed, not just be `eval-3` — it becomes the eval's
  section header in the viewer and its directory name (`eval-3-brownfield-large-openemr-appointment-cap`,
  not `eval-3`).
- `prompt`: the literal input the candidate receives, written the way a real user would actually phrase it
  (see the trigger-eval query style in `trigger-and-activation-evals.md` for the same "sounds like a real
  person" bar).
- `files`: fixture paths the prompt refers to, if any (a small real repo like `fixtures/ledger-service` in
  `axiomatic-spec-workspace`, not a synthetic toy unless a toy is genuinely representative).
- `expectations`: the part that makes this an eval and not a demo. Each one must be independently
  checkable by a grader reading the transcript and output files — no expectation should require re-running
  the candidate's judgment call to verify. Assign each expectation a rung using `check-rungs.md` before
  moving on — the rung determines whether the case can sit in the golden set or only in behavioral
  coverage.
- `category` / `difficulty` / `rung`: optional case-level tags (`check-rungs.md`) that don't change how the
  case runs, only what the aggregated results tell you — they're what turns a flat pass rate into a
  category × difficulty coverage matrix.

## What makes an expectation discriminating

An expectation that a broken or lazy run would also satisfy is worse than no expectation — it manufactures
false confidence. Before adding one, ask: **would a plausible bad output also pass this?**

Bad (surface-level): "The output mentions error handling."
A candidate that writes one throwaway sentence about error handling passes this and tells you nothing.

Good (structural + attributed): "The transfer error model covers self-transfer (from == to), non-positive
amount, unknown source or destination account, and insufficient funds" — this can only pass if all four
cases are actually present, and a grader can point at the exact lines that satisfy each.

Good (negative/must-not, falsifiable): "Preference handling includes a negative axiom: a notification is
never sent on a channel the user has muted (a must-not statement that a test could falsify)" — this forces
the candidate to produce something a test can actually violate, not just a description of intent.

When grading (see `agents/grader.md` in skill-creator, reused as-is for this), a PASS needs evidence that
the underlying task was genuinely done, not that a keyword or filename happens to match. The grader should
also flag expectations that turn out to be non-discriminating once real outputs are in hand — fix the eval,
don't just let it pass forever.

## Order failure-mode and boundary cases before happy path

This is the one piece of `sf-spec-testing`'s framing worth keeping explicitly: write the cases that should
break the candidate, or that sit exactly on a decision boundary, before the case that just confirms the
obvious path works. A case set that's all happy path can't tell you anything about where the candidate
actually fails in production — and production is where AI-driven capabilities fail, not in the demo.

Checklist to pull failure-mode/boundary cases from (not all apply to every target):

- **Payload/input extremes**: empty input, a single word, a massively over-scoped ask ("spec our entire
  platform"), unicode/emoji, malformed structure (see `eval-4-precondition-weakening-negative-deposit` in
  `axiomatic-spec-workspace/iteration-1/` — the case is deliberately an anti-pattern request, not a clean
  feature ask).
- **Ambiguous or contradictory intent**: a request that sounds like it wants X but the details point to Y;
  a request that asks for two things that can't both be true (e.g. "remove this safety check but also make
  sure nothing breaks").
- **Near-miss non-triggers / non-cases**: for trigger evals this is the negative half of the set (see
  `trigger-and-activation-evals.md`); for output-quality evals it's a prompt that's adjacent to the target
  capability but should be handled differently (implementing an existing spec rather than writing one,
  reviewing a PR rather than scoping a change).
- **Scale/blast-radius stress**: the same request against a tiny fixture and against something like the
  ~4M-line OpenEMR fork (`eval-3-brownfield-large-openemr-appointment-cap`) — behavior that's fine at small
  scale (read everything) becomes wrong at large scale (must scope before reading bodies).
- **Concurrency/race conditions**, when the target has shared mutable state: two callers hitting the same
  invariant at once (the ledger transfer lock case; the OpenEMR "two concurrent bookings both pass the
  count check" case).
- **Irreversible/one-way-door requests**: a request that, if followed literally, would silently make a
  bad, hard-to-reverse decision (the negative-deposit precondition-weakening case) — the correct behavior
  is often to flag and block, not to comply.

Only after these should you add the happy-path case(s) that confirm the capability works when nothing
adversarial is going on. One or two happy-path cases is usually enough; they exist to catch total failure
and to serve as the return of investment case per capability tier, not to pad the pass rate.

This checklist is deductive — it covers failure modes you can anticipate from the spec. `error-analysis.md`
covers the inductive complement: finding the failure modes nobody anticipated by reading real traces.

## Fixtures

Prefer a small, real, inspectable fixture over a synthetic one whenever the eval needs "an existing
codebase" or "existing data" — `axiomatic-spec-workspace/fixtures/ledger-service` is a real tiny Python +
Go service with genuine concurrency bugs and a genuine README-stated invariant, not a mock. For scale-stress
cases, point at a real large repo you already have on disk (`~/Projects/openemr-base-clean`) rather than
generating a fake one — file paths and symbol names cited by the candidate can then be spot-checked against
reality, which is itself a strong, cheap expectation ("file paths and class/function names cited in the
spec actually exist in the target repo — spot-check at least 5").
