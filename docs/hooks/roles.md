# Role specs and loader (`factory.agents.roles`)

Data for the seven agent roles (`orchestrator research design audit implement test review`) lives in `factory/agents/roles/<role>.yaml`, one file per role, keys equal to the `RoleSpec` field names. `load_roles()` reads and validates them. Contract: `docs/contracts/roles-and-generation.md`; binding clarifications A-12 to A-18 in `docs/contracts/clarifications.md`. This component is data and a loader only: it runs no hook and renders no agent file (TB-03).

## API
- `load_roles(dir=None) -> dict[str, RoleSpec]`: keys in the order above. `dir` defaults to the shipped data; a str or `Path` is accepted.
- `RoleSpec` and `McpEntry` are frozen dataclasses with `.to_dict()`; list fields are tuples.
- `RoleError(ValueError)` has `.role` and `.field`; the message names both. List entries use `field[index]` (for example `hooks[2]`); MCP entries `mcp[0].access`.

## Validation
Raised as `RoleError`: a missing or unknown field; wrong types; `writes` not in `none app research_dir design_dirs audit_dir eval_paths`; `bash` not in `none readonly full`; MCP `access` not `read` or `write`; a hook id outside the eight in `hook-io.md`; `max_tools` above 20; `len(core_tools) > max_tools`; `id` not matching the file name; a missing or extra role file.

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
    print(e.role, e.field)   # e.g. audit hooks[3]
```

Tests: `.venv/bin/python -m pytest tests/agents/test_roles.py` (unit coverage, not the acceptance gate).
