---
name: orchestration
description: >-
  Use when an orchestrator coordinates several agents on a software build: deciding which model
  tier or engine does what, dispatching two or more implementer sub-agents against one shared git
  checkout, deciding what can run concurrently on a PRD or tracer-bullet ledger, integrating the
  agents' results, packaging a read-only review packet for an independent reviewer, or routing a
  task or CI failure to an owner. Triggers include "parallelize", "run these in parallel", "fan
  out implementers", "what can run concurrently", "integrate the agents' work", "which model
  should do this", "orchestrate this build", "review packet", "route this task", and the start of
  any multi-PRD autonomous build.
---

# Orchestration

How the orchestrator divides work across engines and model tiers, runs implementers in parallel without corrupting a shared checkout, and calls an independent reviewer sparingly. This merges three former skills (hierarchical orchestration, parallel integration, and the routing half of the Jev dispatcher). The Co-Pilot-specific milestone bundles are kept as a labelled example.

Detail lives in `reference/`; read the file when its section applies:

| File | When |
|---|---|
| `reference/parallel-integration.md` | Before dispatching 2+ implementers, and for the per-agent integration loop |
| `reference/jev-routing.md` | When routing a task, CI failure or milestone with a classifier |
| `reference/copilot-milestones-example.md` | As a worked pattern for bundling work into a few review milestones |

---

## 1. Division of labor

Three engines, each with one job. Keep the invariants: they are what stop token waste and role creep.

| Engine | Job | Invariant |
|---|---|---|
| **Planning engine** (Antigravity / Gemini in the original setup) | Plan adherence, PRD drafting, axiomatic contracts, evaluation ladders, requirements traceability, dependency graph | Zero product code edits, zero live deployments |
| **Autonomous local execution engine** (Claude Code) | State, architecture, diff audit, implementation, tests, local gates | Closes local deterministic gates on its own, without halting for approval |
| **Independent reviewer** (Codex, or another vendor's model) | High-value read-only verification at milestone boundaries and emergency tripwires | Never used for syntax, lint, unit tests or iterative coding; outputs APPROVE or REJECT with file and line citations, at most about 4k tokens |

Which vendor plays which role, and which plan or billing route pays for it, changes over time; treat the table as roles, not subscriptions. (The former skill named a specific Claude plan; the notes say implementation later moved to API-billed Claude Code, which was not re-verified here.)

## 2. Model allocation inside the execution engine

| Tier | Model class | Scope | Never |
|---|---|---|---|
| **Orchestrator** | Opus, main session | Holds dependency order, reads PRDs, reviews implementer diffs, decides gate closure | Raw `grep` or `find` across whole repos; running test suites directly |
| **Workhorse** | Sonnet, sub-agent | Scoped feature implementation, data models, unit tests, mock servers | Orchestrating other agents; cross-repo refactors without orchestrator guidance |
| **Eyes and hands** | Haiku, sub-agent | File-tree search, ripgrep sweeps, running the test suite and linter, extracting failure lines | Designing architecture; writing complex domain logic |
| **Specialist** | Opus, sub-agent (rare) | Only when escalated: subtle concurrency races, adversarial sandbox bypass | Routine implementation; tasks Sonnet has not tried yet |
| **Router** | Classifier such as TypeSafe Jev (optional) | Sub-second routing of task tier and CI-failure owner | Writing code, free text, detecting defects. See `reference/jev-routing.md` |

Model choices here are proposals: survey current models and run small experiments before fixing them.

### The Haiku log-digestion pattern
Keep hundreds of lines of passing test output out of the Opus and Sonnet contexts:
1. The orchestrator dispatches Haiku to run the suite (for example `pytest tests/test_tb01.py`).
2. If it passes, Haiku returns one line: `ALL 14 TESTS PASSED (0.42s)`.
3. If it fails, Haiku parses stdout and returns **only the failure block and line number**, 5 to 10 lines:
   ```
   FAILED tests/test_tb01.py::test_rejection_on_cross_patient - AssertionError: expected 403, got 200 at line 84
   ```
4. Sonnet ingests that snippet, fixes the code, and asks Haiku to re-verify.

## 3. Sequential by default, parallel by exception

Implement in strict dependency order. Never run multi-slice parallel implementations, **except** file-disjoint slices ("PAR" slices) whose inputs are already committed. Those run concurrently under the rules in `reference/parallel-integration.md`, which covers:

1. Building the dependency graph rather than trusting ledger order, and tagging each item BLOCKING or PAR.
2. The pre-dispatch checklist: acceptance cases written first by an agent the implementers never see, a file-ownership manifest per agent (`OWN` and `DO-NOT-EDIT`), orchestrator-only seams (lockfiles, migrations, wiring, CI YAML), banned git commands in briefs, allowed live channels, complete scope up front.
3. Shared-checkout hazards: peer edits, the side-effect guard, staging by explicit path, scratch-clone safety (`${S:?}`).
4. The per-agent integration loop: read the report, review the diff yourself, verify claims with real exit codes, commit one slice per commit, let CI be the gate, run repo-wide guard tests before every slice commit, report to the user per agent.
5. Adversarial loops: re-run a red-team against the fix, aimed at the new code's escape routes.

Keep implementers blind to eval and golden files. Eval-side agents never edit application code.

## 4. Independent review gates

Call the independent reviewer **rarely and in bundles**, never per pull request or per tracer bullet.

- **Milestones:** group work into a small number of milestone audits, each with a stated prerequisite (local deterministic tests already green) and a short list of invariants to verify. `reference/copilot-milestones-example.md` shows four bundles for one project.
- **Emergency tripwires** (out-of-band invocation) only for: a new telemetry or logging exporter that touches an external sink and could leak sensitive data; a persistent defect that implementer and orchestrator failed to resolve after 3 attempts; any branch merge or remote deployment.
- **Review packet format.** Always hand the reviewer a read-only packet:
  1. `git diff base..HEAD --stat` plus the surgical diff of the target files;
  2. an exact checklist of 3 to 5 invariant questions;
  3. the instruction: `Read-only audit. Output APPROVE or REJECT with file and line citations.`
- Before calling the reviewer, confirm readiness: local evidence complete, no `FAIL` or `SKIP` in the milestone's results, no open product decision. Otherwise return the work to the implementer.

## 5. Quota and context hygiene

1. **Sub-agent lifecycles:** terminate sub-agents as soon as their bounded task ends.
2. **Session compaction:** use `/compact` in the main session between tracer bullets.
3. **Autonomous local gates:** close local deterministic gates when automated tests pass. Never pause for human or reviewer approval on local unit tests.
4. **Report as you go:** when an agent finishes, report what was committed and what is blocked on an external action, without batching it with the next agent's report.
