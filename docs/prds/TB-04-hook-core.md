# TB-04: Hook core: payload, decision, adapter, command line

| | |
|---|---|
| **Delivers** | R-09, R-24 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-01 |
| **Kind** | BLOCKING (wave 2) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
The shared pieces every hook uses, so the seven hook slices can be built in parallel without touching each other.

## Required behaviour
1. `parse_payload` returns a `Payload` for valid PreToolUse, PostToolUse, SubagentStop, Stop and SessionStart JSON, including sub-agent fields when present; it raises `PayloadError` for invalid JSON, a non-object, or a missing `hook_event_name`.
2. `run_hook` maps decisions exactly as the contract's table: allow, deny, ask, block; it never raises and never returns an exit code other than 0 or 2.
3. Fail closed: malformed input or an exception inside `decide` gives a deny (PreToolUse) or block (Stop, SubagentStop) whose reason starts `hook error:`; for SessionStart and PostToolUse it gives exit 0 with the error on stderr.
4. `HookConfig.from_profile(profile, project_root)` resolves the paths, patterns and role mapping; a payload with no `agent_type` resolves to the profile's `main_session_role`.
5. `registry` maps the seven hook ids to `decide` (and optional `record`, `emit`) lazily; an unknown id causes the command line to exit 2 with `unknown hook`.
6. `python -m factory.hooks <id>` reads stdin, loads the profile from `$FACTORY_PROFILE` or `.factory/profile.yaml` under `cwd`, calls the hook through `run_hook`, prints stdout, writes stderr and exits with the code; a missing or invalid profile is a fail-closed result, not a traceback.
7. `record` errors are written to stderr and do not change the exit code; `emit` output goes to stdout only for SessionStart.
8. Hooks modules that do not exist yet make their id resolve to a stub that fails closed with `hook not implemented`, so the registry works while other slices are still being built.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/__init__.py`, `factory/hooks/core.py`, `factory/hooks/__main__.py`, `factory/hooks/registry.py`, `tests/hooks/test_core.py`, `docs/hooks/core.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Any hook's decision logic.
