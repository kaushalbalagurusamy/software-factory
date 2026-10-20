---
name: implementation-review
description: Use after any evaluation or test run of an AI-built system, and always before a release tag, when the owner wants one reviewer to read the implementation so they do not have to nitpick every change — code review of the diff, an observability check of the traces against expectations already defined from first principles, verification that passes were earned rather than shortcut (the "third state" — passed for the wrong reason), and a drift check against the external requirements. Triggers include "review the implementation", "did this really pass", "too green", "check the traces", "is the observability doing what we designed", "reward hacking", "passed for the wrong reason", "drift", or a case that went red to green in one commit. Runs as a grading-side subagent that reads traces, diffs and code but never edits implementation or cases.
---

# Implementation review

One reviewer, four questions, after every run: is the code sound; does the observability show what it was designed to show; were the passes earned; has the build drifted from the requirements. The point is that the owner reads one report instead of every diff and every trace.

## When to use

After every eval run (golden set fully, coverage on flips); before every release tag; on demand when a pass looks too easy or the traces look thin.

## How

Dispatch a dedicated subagent (the `review` role, Sonnet unless the profile allows another model) defined like `openemr-base-clean/.claude/agents/implementation-reviewer.md`, with the run id. Its protocol, in order:

1. **Diff audit** — implementer commits touching eval or fixture directories; tests weakened (assertions removed, ranges widened, skips added); application string literals matching fixture ids, case ids, pinned identifiers, or check vocabulary.
2. **Observability review** — open a few of the run's traces by correlation ID and check them against the *already defined* expectations (one trace per request, correlation ID on every span, a span per node and tool call, model spans with tokens and cost, hashed identifiers and no content in metadata, refusals with correlation IDs, readiness per dependency). Met / not met per expectation; not met is a finding regardless of scores.
3. **Trace evidence per passing golden case** — every cited source appears in a tool output of that trace; required tool calls happened; model input holds retrieved snippets, not a canned answer; refusals came from the policy node, not a string match.
4. **Doctored-input probe** — one live call with a single corruption the case does not test; a correct implementation fails it at the verifier. Record the cost.
5. **Code-review lenses** — delegate to `pr-review-toolkit:silent-failure-hunter`, `pr-review-toolkit:pr-test-analyzer`, `feature-dev:code-reviewer`; verify every lead before it becomes a finding. For bloat and I/O smells, apply `reference/interface-checklist.md` and `reference/io-checklist.md`; findings from them are recorded, not gating.
6. **Drift cross-check** — the latest requirements drift note's "newly covered" expectations are exercised by this run; drafted cases were not added weaker than drafted.
7. **Verdicts** — `right_reason`, `wrong_reason`, `inconclusive`, `not_examined` per golden case, written into the results file; `wrong_reason` blocks like a golden failure.

## Judgment calls

- Name the mechanism, never the intent.
- `inconclusive` is honest; say what would resolve it — usually a missing trace, which is itself an observability finding.
- One live call per run; never re-run the suite.
- The reviewer is on the grading side: it may read cases and fixtures, and must never edit implementation, tests, or cases.

Full protocol with the reasoning per stage: `ai-sidecar/docs/how-to/implementation-review.md` in the OpenEMR Clinical Co-Pilot repository.

## Mechanical phase first, then judgement (added with the sf toolchain)

Before the protocol above, run the deterministic checks and hand their output to the reviewer; the reviewer does not re-derive what a command already proved.

1. `sf slice done <slice>` (every task implemented and QA-verified, verification chain intact, criteria lock verified, slice check passes); `sf intake check` (every source line covered, hashes current).
2. `sf contracts verify` on the changed symbols (verdicts PROVED / COUNTEREXAMPLE / UNSUPPORTED / UNKNOWN / TIMEOUT; a missing solver or unrouted unsupported obligation fails the gate); `sf structure diff base head` for changed symbols and callers by edge kind; the dolls `check` on the refreshed model.
3. Then the judgement review: read callers of every changed function (apply `ponytail-rubric.md` in this skill's folder to every changed file: does it need to exist, is it already in the codebase, is there a stdlib or installed-dependency way, is any code unreachable or speculative, is every new non-trivial branch covered; plus logic, safety, load and speed; every finding with a concrete case; end with `Verdict:` and a `Not checked:` line) and give the reviewer the open `minesweeper` findings and the relevant lens packs (networking, cryptography, performance, ethics, and the rest) as a hunting list. The architecture explorer lets the reviewer open exactly the component under review.
4. **Findings go back into the slice, not into a report nobody reads.** For each confirmed finding: `sf slice amend <slice> --role reviewer` adds a triaged task (priority, depends_on) or a criterion (additive only), which re-opens the implementer and QA pair. Weakening or removing a criterion needs an explicit human or Codex approval marker. Record the verdict per task in the slice, and update the docs and ADRs the finding touches (`doc-sync`) before approving completion.
5. Approval requires `sf slice done` to pass again after the amendments, `doc-sync` to report no stale document, and `eli12.py check` (skill `eli12-docs`) to be clean for the changed modules; a review that finds nothing says so and lists what it did not check.
