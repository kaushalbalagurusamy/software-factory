# TB-09: Implement stop gate hook

| | |
|---|---|
| **Delivers** | R-15 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md` |

## Purpose
Refuse a 'done' from the implement agent that hides weakened tests or skipped verification.

## Required behaviour
1. Runs on SubagentStop (and Stop for the main session when its role is `implement`); for every other role, allow.
2. Computes the change set from `git diff HEAD --unified=0` and `git ls-files --others --exclude-standard` under the project root; if git is unavailable, block with a reason.
3. Blocks when the added lines contain a new skip or expected-failure marker (`@pytest.mark.skip`, `skipif`, `xfail`, `pytest.skip(`, `@unittest.skip`, `it.skip`, `test.skip`, `xit`, `xdescribe`) or a trivial assertion (`assert True`, `assert 1`, `assertTrue(True)`, `expect(true).toBe(true)`), or when a test file or test function is removed.
4. Blocks when any file matching `paths.frozen_tests` has a SHA-256 that differs from the entry in `.factory/baseline.json` (a JSON object mapping path to hex digest); a frozen file missing from the manifest also blocks.
5. Blocks when the sub-agent's transcript (`agent_transcript_path`, JSON lines) shows no Bash tool call containing `profile.checks.test` after the last Edit or Write call; if `checks.test` is not set, this check is skipped.
6. If `.factory/own.json` (`{"paths": [glob, ...]}`) exists, blocks when the change set includes a file outside those paths.
7. Iteration cap: it blocks at most 5 times per `agent_id` (count kept in `.factory/state/stop_gate_<agent_id>`); after that it allows and appends a line to `.factory/stop_gate.log` naming the unresolved reasons, so the orchestrator can escalate.
8. Each block reason lists every failed check with file names, in a stable order.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/stop_gate.py`, `tests/hooks/test_stop_gate.py`, `docs/hooks/stop_gate.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Running the tests itself; the model choice for retries.
