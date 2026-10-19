---
name: implementation-review
description: Use after any evaluation or test run of an AI-built system, and always before a release tag, when the owner wants one reviewer to read the implementation so they do not have to nitpick every change — code review of the diff, an observability check of the traces against expectations already defined from first principles, verification that passes were earned rather than shortcut (the "third state" — passed for the wrong reason), and a drift check against the external requirements. Triggers include "review the implementation", "did this really pass", "too green", "check the traces", "is the observability doing what we designed", "reward hacking", "passed for the wrong reason", "drift", or a case that went red to green in one commit. Runs as a grading-side subagent that reads traces, diffs and code but never edits implementation or cases.
---

# Implementation review

One reviewer, four questions, after every run: is the code sound; does the observability show what it was designed to show; were the passes earned; has the build drifted from the requirements. The point is that the owner reads one report instead of every diff and every trace.

## When to use

After every eval run (golden set fully, coverage on flips); before every release tag; on demand when a pass looks too easy or the traces look thin.

## How

Dispatch a dedicated subagent (Opus) defined like `openemr-base-clean/.claude/agents/implementation-reviewer.md`, with the run id. Its protocol, in order:

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
