# TB-02: Seven role specs and loader

| | |
|---|---|
| **Delivers** | R-04, R-05, R-06, R-07, R-08 (data part) (see `docs/factory/requirements.md`) |
| **Depends on** | none |
| **Kind** | BLOCKING (wave 1) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/roles-and-generation.md`, `docs/contracts/hook-io.md` (hook ids), capability map `docs/plans/2026-09-24-agent-capability-map.md` section 3, `docs/contracts/clarifications.md` (binding) |

## Purpose
Encode the seven roles as data, and load and validate them. The values come from section 3 of the capability map, stripped of anything project-specific.

## Required behaviour
1. `load_roles()` returns exactly seven `RoleSpec` objects keyed `orchestrator research design audit implement test review`.
2. Every spec has all fields in the contract, `max_tools <= 20`, and `len(core_tools) + read-tool placeholders` never exceeds `max_tools` in the data as shipped.
3. Only `implement` has `writes: app` and `blind: true`. `orchestrator` and `review` have `writes: none`. `research`, `design`, `audit` write `research_dir`, `design_dirs`, `audit_dir`. `test` writes `eval_paths`.
4. Spawn lists: `orchestrator` spawns exactly the other six role ids; `implement` spawns none and has no `Agent` tool; `review` spawns only `pr-review-toolkit:silent-failure-hunter`, `pr-review-toolkit:pr-test-analyzer`, `feature-dev:code-reviewer`.
5. `bash` modes: `research` and `audit` are `readonly`; `design`, `review` are `readonly`; `orchestrator`, `implement`, `test` are `full`. (Review's read-only list also covers `git diff`.)
6. Hook ids per role follow capability map section 3, using only ids in `hook-io.md`; every role also lists `secrets_guard` and `bash_guard`; `implement` lists `blindness_guard` and `stop_gate`; write-restricted roles list `path_guard`; `research`, `design`, `audit`, `review` list `subagent_stop`; `orchestrator` lists `session_start` and `ledger_audit`.
7. Skills per role match the consolidated names in the capability map (for example `orchestration`, `grounded-research`, `eval-designer`, `implementation-review`).
8. MCP entries never mention a specific project platform as a required server; entries are `{server, access}` with access `read` for every role except where the map grants writes (none do).
9. `load_roles` rejects a spec with an unknown hook id, an unknown `writes` value, `max_tools > 20`, or a missing field, with an error naming the role and the field.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/roles/*.yaml`, `factory/agents/roles.py`, `tests/agents/test_roles.py`, `docs/hooks/roles.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Rendering agent files (TB-03), profile overrides, hooks themselves.
