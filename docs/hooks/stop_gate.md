# Stop gate (`factory.hooks.stop_gate`)

TB-09, requirement R-15. Refuses a "done" from the `implement` agent that hides weakened tests or skipped verification. Contracts: `docs/prds/TB-09-stop-gate.md`, `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, and the clauses C-01 to C-10, C-32 and C-34 of `docs/contracts/clarifications.md`. Deterministic: runs only local `git`, no network, no model call (R-09); nothing project-specific is hard-coded (R-01). Registered by id `stop_gate`; exports `decide(payload, cfg)`.

## When it runs
`SubagentStop`, and `Stop` for the main session. The role is `agent_type`, or `main_session_role` when absent; only role `implement` is checked, every other role and every other event is allowed untouched. `stop_gate` handles both events identically (A-22, C-28). Whether Claude Code runs a sub-agent's frontmatter Stop hook as SubagentStop is **unverified** (C-34).

## Checks (all run; every failure is listed, in this order)
1. **git**: the change set is `git diff HEAD --unified=0 --relative` plus `git ls-files --others --exclude-standard` under the project root; every line of an untracked file counts as added (C-04). No git executable, not a repository, or no HEAD commit blocks with `git unavailable ...` (C-07). The remaining checks that do not need git still run.
2. **skip / expected-failure marker** added in a test file: `@pytest.mark.skip`, `skipif`, `xfail`, `pytest.skip(`, `@unittest.skip` (also `skipIf`/`skipUnless`), `it.skip`, `test.skip`, `xit`, `xdescribe`. Whole-token matches, test files only (C-05, C-06): paths with a `tests/`, `test/` or `__tests__/` directory, or named `test_*.py`, `*_test.py`, `*.test.*`, `*.spec.*`. `sys.exit` does not match `xit`.
3. **trivial assertion** added in a test file: `assert True`, `assert 1`, `assertTrue(True)`, `expect(true).toBe(true)`. `assert 1 == f()` does not match.
4. **test removed**: a deleted test file, or a removed test function (`def test...`, `it('...')`, `test('...')`) whose name is not re-added in the same file.
5. **frozen files**: every file matching `paths.frozen_tests` (and every manifest key matching it) is compared with `.factory/baseline.json` (`{"<posix path>": "<sha256 hex>"}`). Changed hash, missing from the manifest, or missing on disk blocks (C-09). A missing or malformed manifest blocks when `frozen_tests` is set. Globs support `**` and `*` only.
6. **evidence of a full-suite run**: skipped when `profile.checks.test` is unset. Otherwise the transcript (`agent_transcript_path`; on `Stop`, `transcript_path` first, C-03) must show a Bash call whose command contains `checks.test` after the last Edit/Write call (containment, C-10). No Edit/Write call: passes. Missing, empty or unparseable transcript: check skipped and one line appended to `.factory/stop_gate.log` (C-01, C-02, C-32).
7. **ownership**: if `.factory/own.json` (`{"paths": [glob, ...]}`) exists, any changed file outside those globs blocks; an invalid file blocks. The gate's own `.factory/state/*` and `.factory/stop_gate.log` are never counted.

## Iteration cap
Per `agent_id` (`main` when absent; characters outside `[A-Za-z0-9._-]` become `_`), the count is kept in `.factory/state/stop_gate_<agent_id>`. It blocks at most 5 times; afterwards it allows and appends one line to `.factory/stop_gate.log` naming the unresolved reasons, on every such stop (C-08). A stop that passes all checks deletes the counter. `decide` itself updates the counter and log (side effects under the project root only).

## Example (recorded run)
Project with a committed `tests/test_a.py`, an untracked `tests/test_b.py` containing `@pytest.mark.skip` and `assert True`, and a minimal profile.
```
$ cat p.json
{"session_id":"s1","cwd":"/work/demo","hook_event_name":"SubagentStop","permission_mode":"default","agent_id":"a1","agent_type":"implement","stop_hook_active":false}
$ python -m factory.hooks stop_gate < p.json; echo "exit=$?"
{"decision":"block","reason":"stop gate: 2 check(s) failed (block 1 of 5):\n- skip or expected-failure marker added: tests/test_b.py (@pytest.mark.skip)\n- trivial assertion added: tests/test_b.py (assert True)"}
exit=0
$ cat .factory/state/stop_gate_a1
1
```
After a fifth block the sixth identical stop exits 0 with empty stdout and `.factory/stop_gate.log` gains `stop_gate agent=a1: allowed after 5 blocks; unresolved: skip or expected-failure marker added: ... | trivial assertion added: ...`.

## Tests
`python -m pytest tests/hooks/test_stop_gate.py` (unit coverage, not the acceptance gate).
