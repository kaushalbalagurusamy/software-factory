# End-to-end walking skeleton and shadow routing log (TB-14)

Shows that the profile, role specs, generator, settings emitter and hooks work together on a fixture project. Nothing calls a model and nothing touches the network. Requirements: R-01, R-19, R-20. Contracts: `docs/contracts/hook-io.md`, clarifications C-26, C-27, C-29, C-33, C-34.

## Simulation (`factory.agents.simulate`)
- `run_events(project_root, events) -> list[Outcome]`. Each event is `{"payload": {...}}`, which is a Claude Code hook payload. The function loads `<project_root>/.factory/profile.yaml` and ignores `$FACTORY_PROFILE`. It generates the agent files and settings in memory and writes neither. For each payload it runs the factory hooks that match it in process. A hook matches when it is in the emitted settings for the payload's event and its matcher regex fully matches `tool_name`. The frontmatter hooks of the payload's `agent_type` are added to those. On `SubagentStop` this includes the agent's frontmatter `Stop` hooks, following A-22. Each hook runs once, and settings hooks run first.
- `Outcome(kind, reasons)`. Deny or block takes precedence over ask, and ask over allow. `reasons` holds the non-empty reasons in the order the hooks ran. Kinds are what the protocol adapter enforces (A-04-5): on Stop and SubagentStop every non-allow becomes `block`, and on PreToolUse `block` becomes `deny`.
- These cases fail closed with a deny, or a block on Stop and SubagentStop, and the reason begins `hook error:`:
  - an event that has no `payload` mapping
  - a payload with no `hook_event_name`, or an unknown event
  - a hook that raises
  - a hook that returns something other than a `Decision`

  A missing `cwd` defaults to the project root. A hook's `record` runs after `decide`, as on the command line, and its errors are ignored. An invalid profile raises `ProfileError`.
- `generate_project(project_root) -> dict[str, str]` returns the seven `.claude/agents/<role>.md` texts and `.claude/settings.json`, all produced from the profile alone.
- The module never reads `routing.jsonl` or any Jev state.

### Fixtures (`tests/fixtures/e2e_project/`)
- **Base project:** the fixture root. Eval paths are `evals/**`, held-out paths are `held_out/**`, the research directory is `research`, and the one-way door is `\bdropdb\b`. It has no MCP servers.
- **Variant project:** `variant/`. Eval paths are `golden/**` and the one-way door is `\bpurge-tenant\b`.

Only the profile differs between the two. Copy a fixture to a temporary directory before running it, because the stop gate keeps a counter under `.factory/state`.

### Example call and recorded output (2026-10-19, base fixture copied to a scratch directory)
```python
from pathlib import Path
from factory.agents.simulate import run_events

root = Path("/tmp/demo")            # copy of tests/fixtures/e2e_project without variant/
def pre(tool, ti, agent=None):
    p = {"hook_event_name": "PreToolUse", "cwd": str(root), "tool_name": tool, "tool_input": ti}
    if agent: p["agent_type"] = agent
    return {"payload": p}
key = "sk-" + "ant-" + "api03-" + "Q7wErT9yUi0pAs2dFg4h" * 2      # fake, built at run time
events = [
    pre("Read", {"file_path": "evals/case_001.yaml"}, "implement"),
    pre("Read", {"file_path": "evals/case_001.yaml"}, "test"),
    pre("Write", {"file_path": "src/notes.md", "content": "x"}, "review"),
    pre("Bash", {"command": f"echo {key} > .env"}, "implement"),
    pre("Bash", {"command": "git push --force origin main"}),            # main session = orchestrator
    {"payload": {"hook_event_name": "SubagentStop", "cwd": str(root), "agent_type": "research",
                 "last_assistant_message": "The library supports streaming."}},
]
for o in run_events(root, events):
    print(o.kind, o.reasons)
```
Recorded output (each reason cut to its first words):
```
deny  ["blindness_guard: Read of 'evals/case_001.yaml': the path is protected (eval/held-out); ..."]
allow []
deny  ['path_guard: role review may not write .../src/notes.md ...']
deny  ['secret value in Bash command (anthropic key at line 1). Reference it by variable name ...']
ask   ['bash_guard git-force-push: git push --force / -f / --force-with-lease / +refspec overwrites remote history. ...']
block ['research report rejected; missing or invalid:\n- a Sources section ...']
```
On the variant, `evals/case_001.yaml` can be read and `golden/case_001.yaml` is denied for `implement`. The command `./scripts/purge-tenant acme` asks there and is allowed in the base project. `dropdb appdb` does the reverse.

## Shadow routing log (`factory.routing.shadow`)
`record(result, actual_choice, ledger_dir, state_digest="") -> None` appends one line to `<ledger_dir>/routing.jsonl` and creates the directory if it is missing. The line is the content-free `jev_client.log_record(result, state_digest)` plus `actual_choice` and `agrees`, where `agrees` is `result.choice == actual_choice`. `result` is duck-typed (C-33). A Jev fault is logged through the result's `fault` field.

The function never raises. A result with missing attributes, a value that is not valid JSON (NaN), or an unwritable directory drops the line and writes one short note to stderr. Nothing reads the log to make a routing decision: the actual choice is made before `record` and is never changed by it.
```python
from factory.routing.jev_client import Routing
from factory.routing.shadow import record
r = Routing("model_tier", "opus", "use_opus", "jev", "act", "v1", 0.9, 0.5, {"opus": 0.9, "sonnet": 0.1}, None, 12.0)
record(r, "sonnet", ".factory/ledger", state_digest="abc")
# .factory/ledger/routing.jsonl gains:
# {"decision": "model_tier", "state_digest": "abc", "policy_version": "v1", "source": "jev", "band": "act",
#  "choice": "opus", "action": "use_opus", "top_prob": 0.9, "margin": 0.5, "probabilities": {"opus": 0.9,
#  "sonnet": 0.1}, "fault": null, "latency_ms": 12.0, "actual_choice": "sonnet", "agrees": false}
```

## Running the simulation
```
scripts/bounded-pytest.sh tests/agents/test_simulate.py tests/routing/test_shadow.py -q -p no:cacheprovider
```
These are unit tests. They are not the acceptance gate. They block socket connections for the whole run.

## Manual live rehearsal (once, by a human)
1. Copy `tests/fixtures/e2e_project` (without `variant/`) to a scratch directory and run `git init` and an initial commit there.
2. Write the output of `generate_project(<dir>)` into `<dir>`, which gives the seven agent files and `.claude/settings.json`. Make sure `python -m factory.hooks` resolves, either by installing this repo in the active venv or by setting `PYTHONPATH`.
3. Start `claude` in that directory and do each step of the scripted stream for real:
   - Have the `implement` agent read `evals/case_001.yaml`. Expect a deny.
   - Have the `test` agent read the same file. Expect it to be allowed.
   - Have `review` write a file. Expect a deny.
   - Have any agent echo a fake key. Expect a deny.
   - In the main session, run `git push --force`. Expect an ask prompt.
   - Have `research` finish without a Sources section. Expect a block.
4. Record whether the `implement` agent's frontmatter `Stop` hook ran as `SubagentStop`. This is C-34, which is still unverified. Record the result in `docs/contracts/clarifications.md` through the orchestrator, not in this file.
5. Delete the scratch directory. No model output from the rehearsal is used by any test.
