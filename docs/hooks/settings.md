# Settings emitter (`factory.agents.settings`)

Produces the project-level Claude Code `hooks` registration as a reviewable change. Pure and deterministic: it never reads or writes a file, and makes no clock, network or model call (the caller loads `.claude/settings.json`, passes it as `existing`, and writes the result). It never touches user-level settings. Contract: `docs/contracts/hook-io.md`; binding clarifications A-21, A-22, A-32, A-33, A-34, A-35.

## API
- `emit_settings(profile, roles, existing=None) -> dict`: registers the union of hook ids used by `roles` (all eight for the shipped roles), each as `python -m factory.hooks <id>`, shape `event -> [{matcher, hooks: [{type: command, command}]}]`. One entry per hook id, in canonical order. `PreToolUse`: `path_guard`, `secrets_guard` (`Write|Edit|MultiEdit|NotebookEdit|Bash`), `blindness_guard` (`Read|Grep|Glob|Bash`), `bash_guard` (`Bash`); `SubagentStop`: `stop_gate`, `subagent_stop`, `ledger_audit`; `SessionStart`: `session_start`. Hooks with no matcher have no `matcher` key.
- `diff_settings(old, new) -> str`: unified diff of the key-sorted, 2-space JSON of both objects; `""` when equal.
- `SettingsError(ValueError)`.

## Merge rules
Keys and hook entries in `existing` that do not start `python -m factory.hooks` are preserved (a mixed entry keeps its foreign hooks). Own commands are removed and re-added to match the roles, so emitting over its own output is a no-op. `existing` is not mutated. No `permissions.deny` rule is ever added (blindness is a hook); an existing `permissions` section is preserved untouched.

## Errors (`SettingsError`)
`existing` or its `hooks` is not a mapping, an event's entries are not a list, a role names an unknown hook id, or the result would contain a secret-shaped value or an absolute home path.

## Example
```python
from factory.agents.profile import parse_profile
from factory.agents.roles import load_roles
from factory.agents.settings import diff_settings, emit_settings

profile = parse_profile({"schema_version": 1, "project": {"name": "demo"},
                         "paths": {"eval": ["evals/**"]}})
old = {"model": "opus"}
new = emit_settings(profile, load_roles(), old)
print(new["hooks"]["SessionStart"])
# [{'hooks': [{'type': 'command', 'command': 'python -m factory.hooks session_start'}]}]
print(diff_settings(old, new)[:60])
```

Tests: `.venv/bin/python -m pytest tests/agents/test_settings.py` (unit coverage, not the acceptance gate).
