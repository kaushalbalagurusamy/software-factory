# TB-01: Project profile loader

| | |
|---|---|
| **Delivers** | R-02 (see `docs/factory/requirements.md`) |
| **Depends on** | none |
| **Kind** | BLOCKING (wave 1) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/profile.md` |

## Purpose
Load and validate `.factory/profile.yaml` into an immutable `Profile`. Everything project-specific reaches the rest of the system through this object.

## Required behaviour
1. `load_profile(path)` returns a `Profile` for a valid file; omitted optional fields take exactly the defaults in the contract.
2. An invalid profile raises `ProfileError` whose `.field` is the dotted path of the first problem, in this fixed order of checking: `schema_version`, `project`, `main_session_role`, `paths`, `agents`, `mcp_servers`, `graph`, `deploy`, `git_host`, `tracker`, `checks`, `one_way_door_patterns`, `secret_allow_patterns`, then unknown top-level keys.
3. `schema_version` other than 1, a missing `project.name`, an empty `paths.eval`, a `main_session_role` that is not one of the seven role ids are all rejected.
4. Paths must be relative, must not contain `..`, must not be absolute; globs use only `*` and `**`.
5. `agents.<role>` keys must be role ids; an override that lists an MCP server not declared under `mcp_servers` is rejected with the field `agents.<role>.mcp_servers`.
6. Regex fields that do not compile are rejected with the field name and the index of the entry.
7. Unknown top-level keys are rejected with the key name as the field.
8. The loader does no network access and does not read environment variables; the same file always gives an equal `Profile`.
9. `Profile` is hashable or otherwise immutable; mutating it raises.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/__init__.py`, `factory/agents/profile.py`, `tests/agents/test_profile.py`, `docs/hooks/profile.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Graph validation (TB-12), role ids beyond the seven constants, reading any file other than the profile.
