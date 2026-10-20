---
name: qa-supervisor
description: >-
  Use when the QA role runs in the /sf loop: after an implementer claims a slice task is done, when a
  gate fails and feedback must go back to the blind implementer, when the same failure repeats, when a
  slice looks stuck, or when tuning retry and escalation. Drives `python -m factory.qa` (state, bounded
  retry, escalation, leak-checked feedback, regression proposals, verification hand-off to the slices
  package). Triggers: "QA failed", "send feedback to the implementer", "retry cap", "slice stuck",
  "tune the retry policy", "verify this task".
---

# QA supervisor

QA runs the protected gate, records the result, decides the next step and hands the implementer
feedback in contract terms. Full schemas and exit codes: `docs/qa-loop.md`.

## Who may do what
- QA: runs gates, writes `.sf/slices/<id>/` state, feedback and regression proposals, and is the only role that
  verifies (`verify-pass`). QA never edits application code and never weakens, skips or deletes a test.
- Implementer: blind to `paths.eval` and `paths.held_out`; reads only qa-feedback files and public criteria.
- Reviewer: handles stuck slices (`reviewer-verdict`), may amend the slice additively.
- Eval author: the only one who turns a regression proposal into a case.

## Loop (all commands take `--root R --slice ID`)
1. `init --criteria AC-1 AC-2` once.
2. Run the gate, then `record --status pass|fail --case C --criterion AC-n --error-file F --tier T --duration S
   [--tokens N --cost USD --commit SHA]`. Use `--rerun` for a requested flake rerun. Environment crashes are
   classified automatically (or `--environment`); they consume no attempt and the gate stays failed.
3. `next [--apply]` returns one action:
   - `retry_same_tier` / `escalate_model` (the latter only if an opted-in different tier exists; `diagnosis` is attached): write `feedback`, relaunch the implementer at `tier`.
   - `rerun_for_flake`: rerun the gate unchanged, `record --rerun`.
   - `environment_wait`: fix or wait for the environment, rerun; nothing is counted.
   - `propose_regression`: `regression-propose` (the signature recurred after a claimed fix), then `next` again.
   - `hand_to_reviewer`: cap reached; give the reviewer the feedback files and failures log; record
     `reviewer-verdict --verdict amended|unresolved --note TEXT`.
   - `mark_blocked`: `next --apply` records what the slice waits on; move on to an independent slice.
   - `accept`: all criteria verified; `verify-pass TASK --evidence T --commit SHA --criteria AC-n` for each task.
4. `audit` before trusting state; a failed audit (exit 1) means the logs were edited.

## Repeated failures: promote notes
When `next` reports a repeated signature (the same failure again, `escalate_model`, `hand_to_reviewer` or
`mark_blocked`), run `sf qa promote-notes --slice DIR` (DIR is the slice folder, `docs/slices/<id>`; add
`--protect P` for each protected path, or the profile's eval and held-out paths apply). It reads the local
attempt log `.sf/slices/<id>/` and writes `DIR/qa-notes.md`, one block per repeated signature, after the leak
check; nothing is written if the text matches protected material. Commit `docs/slices/<id>/qa-notes.md`; it
is the only QA note file the Write tool lets you create, together with `docs/slices/<id>/qa-feedback/*.md`
and the files under `.sf/slices/` (`.md .json .jsonl .txt .tsv` only).

## Leak rule
Feedback carries criterion IDs (AC-n), observed versus expected behaviour, a product-level reproduction command,
the attempt number and what changed. Never test source, assertion text, protected file paths or fixtures.
`feedback` runs the leak check against `paths.eval`/`paths.held_out` (or `--protect`) and refuses (exit 3) on a
match. Do not paraphrase around it by pasting assertions; describe the behaviour.

## Retry policy and tuning
Defaults in `.sf/policy.yaml` (see the doc): 4 attempts per signature, tiers sonnet x4 (Sonnet-only; another model needs an explicit `allow_non_default_models` opt-in in the policy), 10
attempts per slice, 1 flake rerun. Run `stats` for per-tier success rate and mean duration; the decision escalates
early when a tier has at least `min_samples` attempts and a rate below `escalate_below`, and holds a tier whose
rate is at least `hold_above` (both only when a different tier exists in the ladder). Change the ladder or caps in the policy file only from `stats` evidence, and never
raise a cap to hide a failing gate.
