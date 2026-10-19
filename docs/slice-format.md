# Slice format (tracer-bullet PRD slices)

A slice is one vertical, user-visible increment. It is written as an OpenSpec-style change folder, adopted as a file-format profile, not as a tool dependency (see `research/openspec.md`). The checker is `python -m factory.slices`; nothing here needs OpenSpec installed.

## Layout

```
docs/slices/<id>/
  proposal.md        frontmatter + Why, UX stories, What Changes, Out of scope, Impact
  specs/<capability>/spec.md   public acceptance criteria (OpenSpec grammar)
  tasks.md           numbered task groups with checkboxes
  verification.json  QA-only, hash-chained (CLI-written)
  criteria.lock      written at approval (CLI-written)
  amendments.md      append-only (CLI-written)
```

### proposal.md

Frontmatter keys, all required: `id` (equals the directory name), `title`, `priority` (`P0`..`P3`), `depends_on` (list of slice ids), `status` (`draft`, `approved`, `in-progress`, `implemented`, `done`, `blocked`, `abandoned`), `source_requirement_ids` (ids in the requirement ledger).

Body: `## Why`, `## UX stories`, `## What Changes`, `## Out of scope`, `## Impact`, each exactly once, in that order. Nothing but `## Why` may precede `## UX stories`: stories come before technical content. Each story is `### US-n <title>`, one sentence `As a <persona> I can ... so that ...`, and a line starting `Device:` or `Context:`.

### specs/<capability>/spec.md

```
## ADDED Requirements

### Requirement: AC-1 <name>
The system SHALL ... (or MUST).
Serves: US-1, US-2

#### Scenario: AC-1.1 <name>
- GIVEN ...
- WHEN ...
- THEN ...
```
Every AC needs a `Serves:` line naming existing stories, a SHALL or MUST sentence, and at least one scenario whose id is `AC-<n>.<m>` under its own requirement, with WHEN and THEN bullets. These are the public criteria the blind implementer may read. Protected tests are never described here.

### tasks.md

```
## 1. Group name

- [ ] 1.1 Build the form (AC-1.1, AC-2). Verified by: browser check at 390 px.
```
Each task cites existing criteria in a final parenthesis group and says `Verified by:`. Every AC must be covered by at least one task (citing `AC-n` or any of its scenarios). `[x]` means IMPLEMENTED, set only by the implementer.

## Roles and CLI

`python -m factory.slices <command>`; exit codes: 0 ok, 1 check failure, 2 usage error, 3 gate not met, 4 refused (wrong role or missing approval).

| Command | Effect |
|---|---|
| `check DIR [--ledger TSV]` | Validates everything above, dependencies (exist, acyclic across the sibling slices), and the lock if present. With `--ledger` (TSV columns `req_id`, `trust`, `status`) every `source_requirement_ids` entry must exist; a row whose trust starts `rejected` or `conditioned` and whose status contains both `open` and `critical` blocks the slice. |
| `lock DIR` | Writes `criteria.lock` (per-item SHA-256 of each story, requirement and scenario, plus a combined hash). Refused if a lock exists or `check` fails. |
| `tick DIR TASK --role implementer` | Sets `[x]`. `qa` and `reviewer` are refused. |
| `verify DIR TASK --role qa --evidence TEXT --commit SHA` | Appends to the hash chain. Only `qa`; refused unless the task is `[x]`; refused on a broken chain. Entry: `{seq, task, verified, by, commit, evidence, at, task_sha, prev, hash}`. |
| `amend DIR --role reviewer\|slice-author --reason T [--added ID].. [--changed ID].. [--removed ID].. [--approved-by human:REF\|codex:REF]` | Appends to `amendments.md`, recording the current hash of added or changed items. Adding is free. Changing or removing a locked criterion is refused without an approved-by marker. |
| `done DIR` | Exit 0 only if `check` passes, the lock exists and verifies, every task is `[x]`, every task has a QA entry whose `task_sha` still matches the task text, and the chain is intact. Otherwise exit 3, listing each reason. This is the deterministic half of the completion and drift gate; the reviewer half remains. |
| `triage [--root docs/slices]` | JSON: `order` (dependencies first; among ready slices, lower priority number first), `blocked` (slices waiting on non-`done` dependencies), `cycles`, `unknown_dependencies`. Exit 1 on cycles or unknown dependencies. |

Lock semantics: the baseline is the lock overlaid with amendments. Any edit to a locked or amended item that is not recorded is a check failure; so is an unrecorded new item. The checker cannot tell a weakening edit from a strengthening one, so every edit to a locked item needs `--changed` with approval, and only additions are free.

## Mapping to OpenSpec

| This format | OpenSpec | Status |
|---|---|---|
| `proposal.md` with Why, What Changes, Impact | same filename and sections | compatible |
| Frontmatter (`id`, `priority`, `depends_on`, ...) | not defined | extended |
| `## UX stories`, `## Out of scope` in proposal | not defined | extended (extra sections) |
| `specs/<cap>/spec.md`, `## ADDED Requirements`, `### Requirement:`, `#### Scenario:` | same grammar | compatible |
| `AC-n` ids in requirement and scenario names; `Serves:` line | names only; no ids | extended (ids live in names) |
| `tasks.md` numbered groups, `- [ ] n.m` | same | compatible |
| `[x]` means implemented; separate QA verification | one checkbox, one meaning | incompatible in meaning |
| `verification.json`, `criteria.lock`, `amendments.md` | not defined | extended (extra files) |
| Hard gates (blind implementer, QA-only verify, lock) | permissive workflow, no gates | incompatible; enforced by this CLI only |
| `design.md`, MODIFIED/REMOVED/RENAMED deltas, `archive` | supported | not used here, not tested |

## Verified compatibility

Tested 2026-10-19 in a throwaway directory outside the repo with `OPENSPEC_TELEMETRY=0` and `DO_NOT_TRACK=1`, running `npx -y @fission-ai/openspec@1.14.3 validate --all --strict --json` on a copy of `tests/fixtures/slices/docs/slices/demo-login` laid out as `openspec/changes/demo-login/` (proposal.md, specs/auth/spec.md, tasks.md):

- Result: exit 0, one change, `valid: true`, no issues.
- Also valid (exit 0) after adding `criteria.lock`, `verification.json`, `amendments.md` and ticking one task `[x]`.
- Control: removing SHALL from AC-1 made the same command exit 1 with a WARNING "should contain SHALL or MUST" under `--strict`, so the validator did inspect the file.

What this does not show: that `openspec list/status/archive` or the slash-command workflows work with these files, that other OpenSpec versions behave the same, or that MODIFIED/REMOVED deltas interoperate. Only `validate --strict` was tried, only on this one fixture. `proposal.md` frontmatter and the `UX stories` section were tolerated by that command.
