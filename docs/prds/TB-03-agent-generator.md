# TB-03: Agent file generator

| | |
|---|---|
| **Delivers** | R-01, R-04, R-05, R-06, R-07, R-08 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-01, TB-02 |
| **Kind** | BLOCKING (wave 2) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/roles-and-generation.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Turn role specs plus a profile into `.claude/agents/<role>.md` files, deterministically.

## Required behaviour
1. `generate_agents(profile, roles)` returns seven entries keyed `.claude/agents/<role>.md`, byte-identical across calls.
2. Frontmatter has exactly the allowed fields in the contract's order; `disallowedTools`, `skills`, `hooks` are omitted when empty.
3. `tools` is built as specified: core tools, then per `mcp` entry the profile's `read_tools` as `mcp__<server>__<tool>` (or `mcp__<server>` for write access); a server the profile lacks contributes nothing.
4. Profile overrides may change the model and add skills and profile-declared servers; a request that would add write access or change `writes` raises `GenerationError`.
5. A tool list longer than `max_tools` raises `GenerationError`.
6. Hook entries render as `python -m factory.hooks <hook_id>` under the correct event and matcher for that hook id (PreToolUse for the guards on the tools they inspect, SubagentStop for `subagent_stop`, Stop for `stop_gate`, SessionStart for `session_start`).
7. Two different profiles with no MCP servers differing only in `project.name` produce identical role files (nothing project-specific leaks in); a profile whose `project.name` appears inside a role template body causes `GenerationError`.
8. The body has the four sections in the contract's order and mentions each skill the role loads by name.
9. No generated file contains a secret-shaped value or an absolute home path.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/generate.py`, `tests/agents/test_generate.py`, `tests/agents/golden/` (your own expected outputs), `docs/hooks/generator.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Writing files to disk (the caller writes them), settings.json (TB-13).
