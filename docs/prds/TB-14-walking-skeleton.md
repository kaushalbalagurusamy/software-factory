# TB-14: End-to-end walking skeleton and shadow routing log

| | |
|---|---|
| **Delivers** | R-19, R-20, R-01 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-03, TB-05 to TB-13 |
| **Kind** | BLOCKING (wave 5) |
| **Implementer model** | Opus |
| **Published contracts** | all contracts, `docs/contracts/clarifications.md` (binding) |

## Purpose
Prove the pieces work together on a fixture project with no model calls, and log Jev decisions without giving them authority.

## Required behaviour
1. `simulate.run_events(project_root, events)` loads the project's profile, builds its `HookConfig`, and for each event (a payload dict plus the hook ids registered for that event and tool) returns the combined outcome: any deny or block wins, else any ask, else allow.
2. On the fixture project (a small profile with two agents' worth of paths, no MCP servers), the generated agents and settings are produced from the profile alone, and a scripted event stream is decided as the requirements say: an `implement` read of an eval file is denied, a `test` read of it is allowed, a `review` Write is denied, a secret-shaped Bash command is denied, an `orchestrator` `git push --force` asks, a research report without sources is blocked at stop.
3. Changing only the profile (a second fixture with different eval paths and a different one-way-door pattern) changes the outcomes accordingly; role and hook code paths are the same.
4. `shadow.record(result, actual_choice, ledger_dir) -> None` appends one JSON line to `<ledger_dir>/routing.jsonl` with the content-free record from `factory.routing.jev_client.log_record` plus `actual_choice` and `agrees` (bool); it returns nothing, never raises into the caller, and nothing in the simulation reads that file to decide anything.
5. The whole simulation runs with the network disabled and makes no model call.
6. A short runbook in `docs/hooks/e2e.md` describes how to run the simulation and how to do one manual live rehearsal.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/simulate.py`, `factory/routing/shadow.py`, `tests/agents/test_simulate.py`, `tests/routing/test_shadow.py`, `tests/fixtures/e2e_project/`, `docs/hooks/e2e.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
A live agent run, the tracker, the runtime.
