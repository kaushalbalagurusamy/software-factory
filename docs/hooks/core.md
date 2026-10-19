# Hook core (`factory.hooks`)

Shared pieces for every hook (TB-04): payload parsing, `Decision`, the protocol adapter `run_hook`, `HookConfig`, a lazy registry and the command line. Contracts: `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, and the "Hook core" clauses A-04-1 to A-04-6 of `docs/contracts/clarifications.md` (binding). Deterministic: no network, no model call (R-09); nothing project-specific is hard-coded (R-01).

## API (`factory.hooks.core`, re-exported from `factory.hooks`)
- `parse_payload(text) -> Payload`; raises `PayloadError` for invalid JSON, a non-object, a missing/non-string `hook_event_name`, or a present `tool_input` that is not an object.
- `Decision(kind, reason="")`: `ValueError` if `kind` is not allow/deny/ask/block or a non-allow decision has an empty reason.
- `run_hook(decide, stdin_text, cfg) -> HookResult(exit_code, stdout, stderr)`: never raises, exit code only 0 or 2.
- `HookConfig.from_profile(profile, project_root)`: `profile`, `project_root`, `eval_globs`, `held_out`, `frozen_tests`, `baseline_update`, `research_dir`, `design_dirs`, `audit_dir`, `ledger_dir` (absolute, under the root), `main_session_role`, `checks`, `one_way_door_patterns`, `secret_allow_patterns`; `cfg.role_for(payload)` gives `agent_type`, or `main_session_role` when absent.

## Adapter table
| Decision | PreToolUse | Stop / SubagentStop | PostToolUse / SessionStart |
|---|---|---|---|
| allow | exit 0 | exit 0 | exit 0 |
| deny, block | exit 2, reason on stderr | exit 0, `{"decision":"block","reason":...}` | exit 0, reason on stderr |
| ask | exit 0, `permissionDecision: ask` JSON | block JSON | exit 0, reason on stderr |

Fail closed: bad JSON, missing/unknown event, non-`Decision` return or an exception gives exit 2 with `hook error: ...` on stderr (PreToolUse and unparseable or unknown events), block JSON with a `hook error:` reason (Stop, SubagentStop), or exit 0 with the error on stderr (PostToolUse, SessionStart).

## Registry (`factory.hooks.registry`)
Eight ids: `path_guard`, `blindness_guard`, `secrets_guard`, `bash_guard`, `stop_gate`, `subagent_stop`, `ledger_audit`, `session_start`. Id `X` resolves lazily to the module `factory.hooks.X`, which exports `decide(payload, cfg)` and optionally `record(payload, cfg)` and (SessionStart) `emit(payload, cfg) -> str`. A guard slice only has to add that module; the registry is not edited. If the module does not exist, a stub fails closed with `hook error: hook not implemented: <id>`. An import error inside an existing module is not hidden: the command line fails closed with `cannot load hook`. `register(id, decide, record, emit)` is available for explicit registration.

## Command line
`python -m factory.hooks <id>` reads stdin, loads `$FACTORY_PROFILE` (relative paths resolved against the payload `cwd`) or `<cwd>/.factory/profile.yaml`, runs `decide` through `run_hook`, then `record` (errors go to stderr, exit code unchanged), then, for SessionStart only, `emit` (text appended to stdout). `project_root` is the payload `cwd` (the process directory if absent). Unknown id: exit 2, `unknown hook: <id>`. Missing or invalid profile: fail-closed result, no traceback.

## Example (recorded run)
```
$ cat > /tmp/p.json <<'JSON'
{"session_id":"s","cwd":"/work/demo","hook_event_name":"PreToolUse","permission_mode":"default","tool_name":"Write","tool_input":{"file_path":"a.txt","content":"x"}}
JSON
$ python -m factory.hooks no_such_hook < /tmp/p.json; echo "exit=$?"
unknown hook: no_such_hook
exit=2
$ cd /work/demo   # no .factory/profile.yaml here
$ python -m factory.hooks path_guard < /tmp/p.json; echo "exit=$?"
hook error: cannot read profile /work/demo/.factory/profile.yaml: ...
exit=2
```
In Python: `run_hook(lambda p, c: Decision("deny", "no"), payload_text, cfg)` returns `HookResult(2, "", "no")`.

## Shape decisions where the contracts are silent (unverified against the gate)
- `HookConfig` field names are not specified by the contracts; the list above is this slice's choice and `cfg.profile` always holds the full profile.
- `Payload.cwd` is `""` when absent. A present non-object `tool_input` is a `PayloadError`.
- Compact JSON separators are used for stdout JSON.
- `record` runs for every parsed payload whatever the decision; `emit` is skipped when the result is a fail-closed error.
