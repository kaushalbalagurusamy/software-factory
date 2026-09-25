# Contract: hook input, output and decision functions

Status: published. Evals and implementations both depend on this file. Protocol facts come from the Claude Code hooks documentation (checked 2026-09-24; a first summary had wrong field names and was corrected against the raw page). `tool_use_id` and the full optional fields of Grep were not re-verified. Codex is out of scope.

## Payload (stdin JSON)

Common: `session_id`, `cwd`, `hook_event_name`, `permission_mode`, optional `agent_id` and `agent_type` (present only inside a sub-agent).
- **PreToolUse:** `tool_name`, `tool_input`. Known `tool_input` fields: Read `file_path`; Write `file_path`, `content`; Edit `file_path`, `old_string`, `new_string`; Grep `pattern`, `path`, `glob`; Glob `pattern`, `path`; Bash `command`.
- **PostToolUse:** as PreToolUse plus `tool_response`.
- **SubagentStop:** `agent_id`, `agent_type`, `agent_transcript_path`, `last_assistant_message`, `stop_hook_active`.
- **Stop:** `last_assistant_message`, `stop_hook_active`.
- **SessionStart:** common fields.

`agent_type` equals the agent's `name`, and generated agents are named by role id (`orchestrator`, `research`, `design`, `audit`, `implement`, `test`, `review`). A payload with no `agent_type` is the main session, which the profile maps to a role (`main_session_role`, default `orchestrator`).

## Python API (package `factory.hooks`)

```python
@dataclass(frozen=True)
class Payload:
    event: str                     # hook_event_name
    tool_name: str | None
    tool_input: dict               # {} when absent
    agent_type: str | None
    agent_id: str | None
    cwd: str
    last_assistant_message: str | None
    agent_transcript_path: str | None
    raw: dict                      # the full parsed JSON

@dataclass(frozen=True)
class Decision:
    kind: Literal["allow", "deny", "ask", "block"]   # "block" is for Stop and SubagentStop
    reason: str = ""                                  # required when kind != "allow"

def parse_payload(stdin_text: str) -> Payload        # raises PayloadError on malformed input
def run_hook(decide, stdin_text: str, cfg) -> HookResult   # never raises
@dataclass(frozen=True)
class HookResult: exit_code: int; stdout: str; stderr: str
```

Every hook module exposes `decide(payload: Payload, cfg: HookConfig) -> Decision`, a pure function of its arguments (it may read files under `cfg.project_root` but makes no network or model call).

`HookConfig.from_profile(profile: Profile, project_root: Path) -> HookConfig` carries the resolved paths, patterns and role mapping.

## Protocol adapter (`run_hook`)

| Decision | PreToolUse | Stop and SubagentStop |
|---|---|---|
| allow | exit 0, empty stdout | exit 0, empty stdout |
| deny | exit 2, `reason` on stderr | not used |
| ask | exit 0, stdout `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"<reason>"}}` | not used |
| block | not used | exit 0, stdout `{"decision":"block","reason":"<reason>"}` |

Fail closed: if the stdin text is not valid JSON, lacks `hook_event_name`, or the hook raises, `run_hook` returns a deny (PreToolUse) or block (Stop, SubagentStop) whose reason begins `hook error:`. Any other exit code would let the action proceed, so the adapter must never return one.

## Command line

`python -m factory.hooks <hook_id>` reads stdin, loads the profile from `$FACTORY_PROFILE` or `.factory/profile.yaml` under the payload's `cwd`, calls the hook's `decide` through `run_hook`, prints the result and exits with its `exit_code`. Hook ids: `path_guard`, `blindness_guard`, `secrets_guard`, `bash_guard`, `stop_gate`, `subagent_stop`, `ledger_audit`.
