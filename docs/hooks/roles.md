# Role specs and loader (`factory.agents.roles`)

Data for the eight agent roles (`orchestrator research design audit implement qa test review`) lives in `factory/agents/roles/<role>.yaml`, one file per role, keys equal to the `RoleSpec` field names. `load_roles()` reads and validates them. Contract: `docs/contracts/roles-and-generation.md`; binding clarifications A-12 to A-18 in `docs/contracts/clarifications.md`. This component is data and a loader only: it runs no hook and renders no agent file (TB-03).

## API
- `load_roles(dir=None, allow_models=None) -> dict[str, RoleSpec]`: keys in the order above. `dir` defaults to the shipped data; a str or `Path` is accepted. Every role must declare `model: sonnet` unless the model is in `allow_models` (the profile's top-level `allow_models` list; the installer's `--allow-model` feeds the same list), else `RoleError` with field `model`. `load_roles(..., check_model=False)` skips only that model check; `path_guard` and `blindness_guard` load roles this way, because the model policy is enforced by install, doctor and generation, never by a runtime hook.
- `RoleSpec` and `McpEntry` are frozen dataclasses with `.to_dict()`; list fields are tuples.
- `RoleError(ValueError)` has `.role` and `.field`; the message names both. Per C-37, `.field` is always the bare top-level field name (`hooks`, `core_tools`, `skills`, `spawns`, `disallowed_tools`, `mcp`), never indexed or nested; the offending entry and its position are in the message (for example `entry 3: unknown hook id 'x'`).

## Validation
Raised as `RoleError`: a missing or unknown field; wrong types; `model` not `sonnet` and not in `allow_models`; `writes` not in `none app research_dir design_dirs audit_dir eval_paths qa_paths`; `bash` not in `none readonly full`; MCP `access` not `read` or `write`; a hook id outside the eight in `hook-io.md`; `max_tools` above 20; `len(core_tools) > max_tools`; `id` not matching the file name; a missing or extra role file.

## Writes class `qa_paths`
The `qa` role writes only QA notes, feedback and attempt records: `docs/slices/*/qa-notes.md`, `docs/slices/*/qa-feedback/*.md` and `.sf/slices/**` (the real attempt-log location), with extension `.md`, `.json`, `.jsonl`, `.txt` or `.tsv` only, and never through a path segment named `tests`, `evals`, `src`, `.git`, `.factory` or `.claude`. The generator lists these in the agent's "You may write" section. `path_guard` enforces the class (C-41.2): symlinks are resolved before matching, the role may not write under `paths.eval`, `paths.held_out`, `paths.frozen_tests`, and roles with writes class `app` are denied these paths. The hook configuration may override the globs with a `qa_paths` attribute. The role's Bash is `full` so it can run suites, but `path_guard` denies it every command `bash_guard` flags (no `git add -A`/`.`, no history rewrite, no checkout/restore/reset/commit/push of any path, unparseable commands) and every command whose text writes outside the QA paths (see `docs/hooks/path_guard.md`).

## MCP placeholders
Per A-15, role data never names a deploy platform or git host. `$deploy` and `$git_host` are placeholders for the generator to resolve from the profile; named general servers (`deepwiki`, `alphaXiv`, `firecrawl`, `playwright`) are omitted by the generator when the profile lacks them.

## Example
```python
from factory.agents.roles import load_roles, RoleError

roles = load_roles()
impl = roles["implement"]
assert impl.blind and impl.writes == "app" and impl.spawns == ()
print(impl.hooks)   # ('path_guard', 'blindness_guard', 'secrets_guard', 'bash_guard', 'stop_gate')

try:
    load_roles("/path/with/a/bad/audit.yaml/hook")
except RoleError as e:
    print(e.role, e.field)   # e.g. audit hooks
```

Tests: `.venv/bin/python -m pytest tests/agents/test_roles.py` (unit coverage, not the acceptance gate).
