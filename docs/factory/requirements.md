# Requirements register: the factory's agent layer

Each requirement has a stable ID, a source, and the tracer bullets (TB) that deliver it. The golden and diagnostic evals are traced to these IDs. "Source" cites the document the requirement comes from; if this register and a source disagree, the source wins and this file is wrong.

Sources: **ADR3** = `docs/adr/ADR-0003-agent-roles-above-skills.md`; **MAP** = `docs/plans/2026-09-24-agent-capability-map.md`; **SEVEN** = `docs/plans/2026-09-24-seven-core-agents.md`; **AUSTIN** = `docs/plans/2026-09-23-austin-ready-software-factory-plan.md`; **METH** = `docs/factory/METHODOLOGY.md`; **OWNER** = a requirement the owner stated in conversation on 2026-09-24 (generality, modularity, evals first, blind implementers).

## Generality and configuration
| ID | Requirement | Source | TB |
|---|---|---|---|
| R-01 | Roles, skills and hooks are project-independent: nothing in a role template or hook names a specific project, platform or host. Everything project-specific comes from the profile. | OWNER, MAP §7 | 02, 03 |
| R-02 | A project profile supplies the per-project variation: graph, per-role overrides, paths (eval, held-out, docs folders, own paths), one-way-door patterns, deploy route and platform server, git host, tracker, check commands. An invalid profile is rejected with an error that names the field. | OWNER, MAP §7 | 01 |
| R-03 | The stage graph is data from the profile: stages, gates and roles are validated (roles exist, gates reference stages, only declared loops), and a small ticket may select a subset of roles. | OWNER, AUSTIN §3, SEVEN §4 | 12 |

## Roles and their definitions
| ID | Requirement | Source | TB |
|---|---|---|---|
| R-04 | Exactly seven roles are defined: orchestrator, research, design, audit, implement, test, review. Each has a model, tool allow and deny lists, skills, MCP servers and hooks. | ADR3 §4, SEVEN §1 | 02, 03 |
| R-05 | Narrow tools: a generated agent lists at most 20 tools; an MCP server appears only if the role allows it and the profile provides it; only read tools of a server are listed unless the role is allowed writes. | MAP §2 rules 2 | 02, 03 |
| R-06 | Only Implement has Write and Edit on application code. Orchestrator and Review have neither. Research, Design, Audit and Test write only their own folders. | ADR3 §4 items 3, 4; MAP §3 | 03, 05 |
| R-07 | Spawn allowlists: Orchestrator may start only the other six roles; Implement may start none; Review may start only the reviewer agents. | MAP §3 | 03 |
| R-08 | Generated agent files use only supported frontmatter fields (name, description, tools, disallowedTools, model, skills, hooks, mcpServers, permissionMode, maxTurns, isolation, memory, effort, background). | MAP §1 | 03 |

## Hooks
| ID | Requirement | Source | TB |
|---|---|---|---|
| R-09 | Every hook is a pure decision function over a payload plus configuration, wrapped by a thin protocol adapter. Guard hooks fail closed on malformed input. Hooks make no network call and no model call. | MAP §2, METH | 04 |
| R-10 | Path guards: Research writes only under its folder, Design under `docs/prd`, `docs/spec`, `docs/adr`, Audit under `docs/audit`, Review nowhere, Test under the eval folders only before the freeze and afterwards only through the baseline-update path. Paths come from the profile. | MAP §3 | 05 |
| R-11 | Implement blindness: for the implement agent only, deny Read, Grep, Glob and Bash commands that reference eval or held-out paths, including indirect forms (relative and parent paths, globs, shell variables, symlinks, `cat`, `head`, `rg`, `find`, `xargs`, script interpreters opening the path). Other agents are unaffected. | OWNER, METH §1, AUSTIN S5 | 06 |
| R-12 | Secrets guard, all agents: block Write, Edit and Bash content that contains a key-shaped value; allow references by variable name; allow patterns the profile whitelists. | METH §6, MAP §4 | 07 |
| R-13 | Git hygiene: block `git add -A`, `git add .`, `--no-verify`, force push, amend and rebase without approval; for parallel implementers also block the shared-tree commands listed in METH §3. | METH §3, MAP §4 | 08 |
| R-14 | One-way-door hook (Orchestrator): ask a human before force push, destructive SQL, resource deletion, any deploy, and every pattern in the profile's one-way-door list. | ADR3, MAP §3.1 | 08 |
| R-15 | Implement stop gate: block "done" if a test was skipped, xfailed, deleted or given a trivial assertion, if a frozen test file's hash changed, if there is no evidence of a full-suite run, or if files changed outside the agent's own paths; enforce an iteration cap. | ADR3, METH §5, AUSTIN S5 | 09 |
| R-16 | Subagent-stop validators: Research output has a sources section and marks unverified claims; Audit rows carry file, line and severity; Review verdict is APPROVE or REJECT with citations and a per-pass grade; Design output has every required section, each axiom names its check, and a one-way door has an ADR. | MAP §3 | 10 |
| R-17 | Ledger: an append-only ticket ledger with fixed sections; each agent may write only its own section; a session-start loader; an audit-trail entry per sub-agent run; tampering with earlier entries is detected. | SEVEN §2 rule 7, MAP §4 | 11 |

## Wiring and end to end
| ID | Requirement | Source | TB |
|---|---|---|---|
| R-18 | A settings emitter turns the profile into project-level hook and permission settings as a reviewable diff. It is idempotent, never touches user-level settings and never writes secrets. | MAP §7 | 13 |
| R-19 | Jev routing is shadow only: decisions are logged next to the actual choice and never change routing. | ADR3 §4 item 3 | 14 |
| R-20 | End to end: a profile for a fixture project produces agent files and settings, and a simulated event stream (no model calls) is allowed or blocked exactly as the requirements say. | AUSTIN M1 | 14 |

## Method (applies to how this is built, verified by process evidence)
| ID | Requirement | Source | Evidence |
|---|---|---|---|
| R-21 | Evals are authored from published contracts before any implementer starts; implementers cannot read them. | OWNER, METH §1 | Commit order; blindness rules |
| R-22 | An independent MECE audit of the golden gate precedes implementation. | OWNER, METH §1 | Audit report |
| R-23 | All generated files, fixtures and logs reference secrets by name only. | METH §6 | Secrets scan of the tree |
| R-24 | Every hook and role has published documentation and a recorded example payload. | METH §1 | `docs/contracts/` |
