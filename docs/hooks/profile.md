# Profile loader (`factory.agents.profile`)

Loads `.factory/profile.yaml` into an immutable `Profile` (contract: `docs/contracts/profile.md`; binding clarifications A-01 to A-09, A-11 and the third-round A-11). It is pure: no network, no environment variables, no file other than the profile.

## API
- `load_profile(path) -> Profile`: `yaml.safe_load` then `parse_profile`.
- `parse_profile(data: dict) -> Profile`: applies every rule, so a profile can be built in code.
- `ProfileError(field, message)`: `.field` is the dotted path of the first problem (list entries as `name[i]`). Checked in this order: `schema_version`, `project`, `main_session_role`, `paths`, `agents`, `mcp_servers`, `graph`, `deploy`, `git_host`, `tracker`, `checks`, `one_way_door_patterns`, `secret_allow_patterns`, unknown top-level keys.
- `Profile`, `Project`, `Paths`, `AgentOverride`, `McpServer`, `GraphSpec`, `Stage`, `Deploy`, `Checks` are frozen dataclasses with `.to_dict()`; mappings are read-only `FrozenMap`s; the whole `Profile` is hashable.

## Example call
```python
from factory.agents.profile import load_profile, ProfileError

try:
    profile = load_profile(".factory/profile.yaml")
except ProfileError as err:
    print(err.field, err.message)   # e.g. "paths.eval[0]  path must be relative ..."
else:
    print(profile.paths.eval, profile.git_host)   # ('evals/**',) none
```

## Shape decisions where the contract is silent (unverified against the gate)
- A missing `deploy`/`checks` key inside a present mapping is `None`; unknown keys inside `project`, `paths`, `deploy`, `checks`, `mcp_servers.<name>` are ignored (only top-level and `agents.<role>` unknown keys are errors).
- Graph stage roles are checked for shape only; subset members are checked against the eight role ids.
- A non-mapping document or invalid YAML raises `ProfileError` with an empty `.field`.
