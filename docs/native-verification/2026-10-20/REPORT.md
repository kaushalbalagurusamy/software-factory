# Native verification, 2026-10-20 (real headless Claude Code sessions)

Label: ACTUAL HARNESS. `python3 scripts/rehearse-native.py --only S6,S7`, `claude -p --model sonnet` in an isolated config, Sonnet 5.5 only (no other model appeared in either stream), a disposable project with `sf install install` applied. Each session cost about $0.10 to $0.14.

| Scenario | What it showed | Result |
|---|---|---|
| S6 events and dashboard | In a real session `sf ops init`, `sf slice check` and `sf ops status --json` ran; `sf slice check` wrote its own `4-slice` event to `ops/events.jsonl` without anyone calling a script; `ops init` created the viewer and added `ops/events.jsonl` to `.git/info/exclude`; the working tree stayed clean | 6/6 checks (second run) |
| S7 qa role | The session delegated to the generated `qa` agent. The QA notes file write was allowed; writing `src/hack.py` and `git add -A` were blocked by the real hooks (`PreToolUse:Write` and `PreToolUse:Bash`, exit 2); nothing was staged | 7/7 checks |
| Install | All 15 skills (incl. `eli12-docs`, `lsf`) and all 8 generated agents (incl. `qa`) resolve in the real runtime | 2/2 |

Findings from the runs:
- The first S6 run failed because my prompt used `--root .` on `sf slice check`, which that tool does not accept; the usage error correctly emitted no event (E-05). The prompt was fixed; this is a runner bug, not a product defect.
- Each sub-agent stop is recorded twice (both the `subagent_stop` and `ledger_audit` hooks emit one event, same second). Harmless for the dashboard counts of stops it shows, but the agent-stop tile would double count. Left as is; noted for a follow-up.

Evidence kept: `summary-s6.json` (the second S6 run). The S7 stream and its summary were deleted when I cleaned the output directory before the S6 rerun, so the S7 row rests on the console output of that run (all 7 checks printed PASS, hook blocks `PreToolUse:Write` and two `PreToolUse:Bash` with exit 2); rerun `--only S7` to regenerate the stream.

Not covered (still not run in a real session): the intake gate, the full QA loop with a real implementer and a real QA agent, reviewer amendments, the `lsf` skill driven by Claude Code, and interactive (non `-p`) use.
