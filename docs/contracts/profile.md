# Contract: project profile

Status: published. Location in a project: `.factory/profile.yaml`. Loader: `factory.agents.profile.load_profile(path) -> Profile`. On an invalid profile it raises `ProfileError` with `.field` (dotted path such as `paths.eval`) and `.message`; it reports the first problem in a stable field order. The loader never reads secrets and never makes a network call.

```yaml
schema_version: 1                    # required, must be 1
project: {name: <str>}               # required
main_session_role: orchestrator      # optional, one of the seven role ids
paths:
  eval: [<glob>, ...]                # required, non-empty. Implement is blind to these; Test writes here before the freeze
  held_out: [<glob>, ...]            # optional. Also hidden from Implement
  frozen_tests: [<glob>, ...]        # optional. Hash-locked by the stop gate
  baseline_update: [<glob>, ...]     # optional. Test may write here after the freeze
  research_dir: research             # optional defaults below
  design_dirs: [docs/prd, docs/spec, docs/adr]
  audit_dir: docs/audit
  ledger_dir: .factory/ledger
agents:                              # optional overrides, keys are role ids
  <role>: {model: <str>, extra_skills: [..], mcp_servers: [..]}
mcp_servers:                         # optional, servers the project provides
  <name>: {read_tools: [<tool name>, ...]}
graph:                               # see docs/contracts/graph-and-ledger.md
  stages: [{id: <str>, role: <role id>, gate: <bool>}]
  edges: [[<stage id>, <stage id>], ...]
  loops: [[<stage id>, <stage id>], ...]
  subsets: {<name>: [<role id>, ...]}
deploy: {route: <str>, platform_server: <str|null>, checklist: <path>}   # optional
git_host: github | gitlab | none     # optional, default none
tracker: none | linear | notion      # optional, default none
checks: {test: <cmd>, lint: <cmd>, verify: <cmd>}                        # optional
one_way_door_patterns: [<regex>, ...]     # optional; added to the built-in defaults
secret_allow_patterns: [<regex>, ...]     # optional; values matching these are not treated as secrets
```

Rules: paths are relative to the project root and may not be absolute or contain `..`; globs use `**` and `*` only; `agents.<role>` keys must be role ids; every `mcp_servers` name that an agent override lists must be declared; regex fields must compile; unknown top-level keys are an error.

Defaults for omitted optional fields are exactly those shown above.
