# Agent file generator (`factory.agents.generate`)

Turns the seven role specs plus a project profile into `.claude/agents/<role>.md` text. Pure and deterministic: no file write, clock, randomness, network or model call (writing to disk is the caller's job; `settings.json` is TB-13). Contract: `docs/contracts/roles-and-generation.md`; binding clarifications A-10, A-15, A-19, A-21 to A-24, A-34 in `docs/contracts/clarifications.md`.

## API
- `generate_agents(profile, roles) -> dict[str, str]`: keys `.claude/agents/<role>.md` in role order (`orchestrator research design audit implement test review`); `roles` must hold exactly the seven ids. Same inputs give byte-identical output.
- `GenerationError(ValueError)` with `.role` and `.message`.

## Output
Frontmatter fields, in order: `name`, `description` (the role's, verbatim), `model`, `tools`, `disallowedTools`, `skills`, `hooks`; the last three are omitted when empty. `tools` and `disallowedTools` are comma-separated strings, `skills` a YAML list. Body headings: `## Purpose`, `## You may write`, `## You must never`, `## Skills` (every skill the role loads is named).

`tools` = `core_tools`, then per `mcp` entry the profile server's `read_tools` as `mcp__<server>__<tool>` (or `mcp__<server>` for write access), then read tools of servers added by `agents.<role>.mcp_servers`. `$deploy` resolves to `deploy.platform_server`, `$git_host` to `github`/`gitlab`; a server the profile lacks or a placeholder resolving to nothing contributes nothing. Duplicates are dropped, first occurrence kept.

Hooks render as `python -m factory.hooks <hook_id>`, one entry per hook id in role order, under: `path_guard`, `secrets_guard` PreToolUse `Write|Edit|Bash`; `blindness_guard` PreToolUse `Read|Grep|Glob|Bash`; `bash_guard` PreToolUse `Bash`; `stop_gate` Stop; `subagent_stop` and `ledger_audit` SubagentStop; `session_start` SessionStart. Hooks with no matcher have no `matcher` key.

## Errors (`GenerationError`)
More than `max_tools` tools; an override that carries anything beyond `model`, `extra_skills`, `mcp_servers` (write access, `writes`) or names an undeclared server; the profile's `project.name` (case-insensitive whole word) found in the body; a secret-shaped value or an absolute home path in the generated text; roles not exactly the seven ids; an unknown hook id.

## Example
```python
from factory.agents.generate import generate_agents
from factory.agents.profile import parse_profile
from factory.agents.roles import load_roles

profile = parse_profile({"schema_version": 1, "project": {"name": "demo"},
                         "paths": {"eval": ["evals/**"]}})
files = generate_agents(profile, load_roles())
print(files[".claude/agents/review.md"].splitlines()[:4])
# ['---', 'name: review', 'description: Independent read-only reviewer; ...', 'model: opus']
```

Tests: `.venv/bin/python -m pytest tests/agents/test_generate.py` (unit coverage, not the acceptance gate). Own expected outputs: `tests/agents/golden/`.
