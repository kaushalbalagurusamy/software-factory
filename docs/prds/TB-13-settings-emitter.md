# TB-13: Project settings emitter

| | |
|---|---|
| **Delivers** | R-18, R-23 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-01, TB-02, TB-04 |
| **Kind** | BLOCKING (wave 4) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/roles-and-generation.md`, `docs/contracts/profile.md` |

## Purpose
Produce the project-level Claude Code settings that register the hooks, as a reviewable change.

## Required behaviour
1. `emit_settings(profile, roles, existing=None) -> dict` returns a settings object with a `hooks` section registering each hook id under its event and matcher (PreToolUse for the guards, SubagentStop for `subagent_stop`, `ledger_audit` and `stop_gate`, SessionStart for `session_start`), each as `python -m factory.hooks <id>`.
2. Idempotent: emitting twice, or emitting over its own output, gives an equal result.
3. Merging: keys and hooks in `existing` that this tool did not create are preserved; entries this tool created (commands starting `python -m factory.hooks`) are replaced or removed to match the profile.
4. Never adds `permissions.deny` rules for the eval paths (blindness is a hook, see requirements R-11).
5. `diff_settings(old, new) -> str` returns a stable unified-diff text; empty when equal.
6. The output contains no secret-shaped value and no absolute home path; it never reads or writes any file (the caller does).

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/settings.py`, `tests/agents/test_settings.py`, `docs/hooks/settings.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Writing files, user-level settings.
