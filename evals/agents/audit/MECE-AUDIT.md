# Independent MECE audit: agent-layer golden gate and eval suite

- **Auditor:** independent read-only agent (did not author the cases, contracts or PRDs). Date 2026-09-24, branch `agent-graph`.
- **Scope:** the 129 golden cases in `evals/agents/GOLDEN.json`, the 1,173 diagnostic cases, the register `docs/factory/requirements.md`, the PRDs `docs/prds/TB-01..14`, the contracts in `docs/contracts/` (including the binding `clarifications.md`) and the coverage matrices in `evals/agents/coverage/`.
- **Method:** requirements were extracted independently from the five source documents plus the owner requirements (section 2), then traced through the register, PRDs and cases. Every golden case was read. About 200 diagnostic cases were read and compared with the clauses they cite, weighted toward TB-06, TB-08, TB-09 and TB-11 (section 5).
- **Run:** `uv run ... python evals/agents/run.py` gave 1,302 cases: golden 129 blocked, diagnostic 1,173 blocked, **0 failed, 0 invalid_skip, no membership problem**, golden verdict NOT GREEN (expected, since nothing is implemented). The run rewrites `evals/agents/results/latest.json`; its content came out byte-identical to the pre-run copy.
- **Secret scan:** a regex scan of `evals/` and `docs/` for every key shape in TB-07 B2 found **no secret-shaped literal**. TB-07, TB-11 and TB-14 build synthetic keys from fragments at run time.

## 1. Verdict

**MECE: FAIL.** The golden gate is mostly mutually exclusive (4 redundant cases). It is **not collectively exhaustive** in three ways:
1. A shortcut implementation that hard-codes the base fixture's paths, deploy route and door patterns passes every golden case for the path guard, the blindness guard, the bash guard and the end-to-end slice. So the owner's generality requirement is not gated.
2. An implement blindness guard that denies every Bash command passes the golden set.
3. R-15's full-suite-evidence clause has no golden case.

Separately, the contracts let the implement agent rewrite its own gate configuration through Bash (P0-4).

## 2. Requirements extracted from the sources (audit IDs)

Source keys: ADR3 = ADR-0003; MAP = agent-capability-map; SEVEN = seven-core-agents; AUSTIN = Austin plan; METH = METHODOLOGY; OWNER = owner requirements stated in conversation.

### 2.1 Traceability matrix (in scope for the agent-layer build)

| AR | Requirement (short) | Source | Register | Golden cases | Diagnostic (examples) | Status |
|---|---|---|---|---|---|---|
| AR-01 | Seven role definitions (model, tools, skills, MCP, hooks), not a fixed relay | ADR3 §4.1-2; SEVEN §1, §4.1; MAP §3 | R-04 | TB02-G-001,002,007; TB03-G-001,002,006,009 | TB02-D-001..015 | COVERED (golden) |
| AR-02 | Skills preloaded per role, consolidated names | MAP §3; ADR3 §4.1 | R-04 (A-14) | none | TB02-D-009..015; TB03-D-015,016 | COVERED (diag only) |
| AR-03 | Narrow tools (at most 20); MCP only where needed; read tools only | MAP §2.2, §5 | R-05 | TB02-G-008; TB03-G-003,004,005 | TB03-D-005..008 | COVERED (golden) |
| AR-04 | Role MCP entries never name a platform or host; resolved from the profile | MAP §1 note, §5 | R-05, R-01 (A-15) | none | TB02-D-017,034,035; TB03-D-033..035 | COVERED (diag only) |
| AR-05 | Only Implement writes app code; Orchestrator and Review none; others their own folder | ADR3 §4.3-4; MAP §2.3, §3 | R-06, R-10 | TB02-G-003; TB03-G-008; TB05-G-001..007 | TB05-D-001..056 | WEAK (Bash writes by full-mode roles are unguarded, A-05-1; see P1-6) |
| AR-06 | Orchestrator Bash restricted to git, the Jev client and the deploy command | MAP §3.1 | none (TB-02 B5 sets `bash: full`) | none | none | MISSING (register contradicts source) |
| AR-07 | Spawn allowlists | MAP §1, §3 | R-07 | TB02-G-005,006 | TB02-D-003,022,033; TB03-D-021 | COVERED (golden) |
| AR-08 | Only supported frontmatter fields | MAP §1 | R-08 | TB03-G-002 | TB03-D-001,027,030 | COVERED (golden) |
| AR-09 | Hooks deterministic, no network or model call, fail closed | METH; INDEX rules | R-09 | TB04-G-001..010 | TB04-D-016..021,042..048 | COVERED (golden) |
| AR-10 | Research, Design and Audit path guards; read-only Bash list | MAP §3.2-3.4 | R-10 | TB05-G-001,002,009,010 | TB05-D-001..020,062..102 | COVERED (golden) |
| AR-11 | Test writes evals only before the freeze, then only through the baseline path | ADR3 §4.5; MAP §3.6 | R-10 | TB05-G-007,008 | TB05-D-027..031 | WEAK (Bash edits after the freeze are unguarded; the baseline-path allow is diagnostic only) |
| AR-12 | Implement blind to eval and held-out paths by an agent-type hook, indirect forms included; other roles unaffected; no global deny | MAP §1, §3.5; ADR3 §4.5; OWNER | R-11 | TB06-G-001..010; TB13-G-005; TB14-G-002,003 | TB06-D-001..233 | WEAK (P0-1, P0-2) |
| AR-13 | The OS sandbox is the blindness backstop and "is not optional" | MAP §1, §3.5; AUSTIN §5.10 | none | none | none | MISSING (P1-9) |
| AR-14 | Implement cannot edit frozen tests or the factory's own control files | MAP §3.5 "Never"; AUSTIN S5 | R-10 (A-05-5), R-15 | TB05-G-006 (eval path only) | TB05-D-115..117 | WEAK (P0-4) |
| AR-15 | Secrets guard for every agent; references by name allowed | MAP §4; METH §6 | R-12 | TB07-G-001..010 | TB07-D-001..117 | COVERED (golden) |
| AR-16 | No secret values in generated files, fixtures or logs | METH §6; AUSTIN inv. 5 | R-23 | none | TB03-D-017,018; TB13-D-012,013; TB11-D-033 | COVERED (diag only) |
| AR-17 | Git hygiene for all agents (add -A/., --no-verify, force push, amend, rebase) | MAP §4; METH §6 | R-13 | TB08-G-001,002,003 | TB08-D-001..046 | COVERED (golden); amend, rebase and --no-verify are diagnostic only |
| AR-18 | Shared-tree git commands blocked for implementers | MAP §3.5; METH §3 | R-13 | TB08-G-004,005 | TB08-D-047..075 | COVERED (golden) |
| AR-19 | One-way doors ask a human: destructive SQL, deletes, deploy, profile patterns | MAP §3.1; SEVEN §3.2 | R-14 | TB08-G-006,007,008 | TB08-D-076..130 | WEAK (SQL and profile patterns are diagnostic only; a hard-coded route passes, P0-1) |
| AR-20 | Human pause before merges, opening PRs, deleting or force-pushing shared history | METH §4 | none | none | TB08-D-073,074 expect **allow** | MISSING (P1-8) |
| AR-21 | Implement stop: skip, xfail, trivial or removed tests; frozen hash; own paths; iteration cap | MAP §3.5; ADR3; METH §5 | R-15 | TB09-G-001..009 | TB09-D-001..027,043..050,057..069 | COVERED (golden) |
| AR-22 | Evidence of a full-suite run before "done" | MAP §3.6; METH §5 | R-15 | none | TB09-D-028..035,052..056,070..072 | COVERED (diag only), with a bypass (P0-3, P1-5) |
| AR-23 | Implement PostToolUse formatter and linter | MAP §3.5; SEVEN §3.2 | none | none | none | MISSING (P1-10) |
| AR-24 | Test role Stop needs full-suite evidence; the Haiku runner's SubagentStop returns failure lines only | MAP §3.6 | none | none | none | MISSING (P1-10) |
| AR-25 | Research SubagentStop: sources and unverified marks | MAP §3.2 | R-16 | TB10-G-001,002 | TB10-D-001..011,044,045 | COVERED (golden) |
| AR-26 | Audit SubagentStop: file:line and severity per row | MAP §3.4 | R-16 | TB10-G-003,004 | TB10-D-012..021,048..050 | COVERED (golden) |
| AR-27 | Review verdict, citations and per-pass grade; wrong_reason and inconclusive block | MAP §3.7; METH §1.6, §5 | R-16 | TB10-G-005,006,007 | TB10-D-022..029,046,047 | COVERED (golden) |
| AR-28 | Design: required spec sections, a check on each axiom, an ADR for a one-way door | MAP §3.3 | R-16 | TB10-G-008,009 | TB10-D-030..038,051..055 | COVERED (golden); the ADR clause is diagnostic only |
| AR-29 | Review denied Write and Edit | MAP §3.7 | R-06, R-10 | TB05-G-003; TB14-G-004 | TB05-D-051 | COVERED (golden) |
| AR-30 | Ledger: fixed sections, append-only, per-role section, tamper-evident | SEVEN §2.7; AUSTIN §5.5 | R-17 | TB11-G-001..007 | TB11-D-001..031,042..058 | WEAK (no agent-facing append path, P1-7; unkeyed chain, P2-6) |
| AR-31 | SessionStart loads the ledger (and routing state) | MAP §3.1 | R-17 | TB11-G-009 (no-ticket branch only) | TB11-D-039..041 | WEAK (P1-3) |
| AR-32 | Audit-trail entry per sub-agent run: agent, duration, tool count, outcome | MAP §4 | R-17 (only type, id and message) | TB11-G-008 | TB11-D-032..038,048..051 | WEAK (fields dropped, P1-10) |
| AR-33 | Orchestrator PreCompact and Stop write the ledger and a handoff | MAP §3.1; SEVEN §3.2 | none | none | none | MISSING (P1-10) |
| AR-34 | A profile per project; an invalid profile is rejected naming the field | MAP §7; OWNER | R-02 | TB01-G-001..009 | TB01-D-001..080 | COVERED (golden) |
| AR-35 | Nothing project-specific in role, skill or hook definitions; definitions generated from templates plus the profile | MAP §1 note, §7; METH §6; OWNER | R-01, R-18 | TB03-G-007; TB07-G-008; TB12-G-005; TB14-G-001 | TB14-D-001..016; TB02-D-017,018 | WEAK (P0-1) |
| AR-36 | The stage graph is data per project, validated, with subsets for small tickets | OWNER; AUSTIN §3, §5.2; SEVEN §4.1; ADR3 §4.2 | R-03 | TB12-G-001..008 | TB12-D-001..033 | COVERED (golden) |
| AR-37 | Graph nodes are agents, deterministic steps or typed decisions | AUSTIN §3 ("each node one of three kinds") | none (a stage's role must be one of the seven) | none | none | MISSING (P1-11) |
| AR-38 | Settings emitter: project-level, idempotent, reviewable diff, no user settings | MAP §7 | R-18 | TB13-G-001..008 | TB13-D-001..024 | COVERED (golden); see P1-4 |
| AR-39 | Jev routing is shadow only, logged beside the actual choice | ADR3 §4.3; AUSTIN §5.3 | R-19 | TB14-G-009 | TB14-D-025..039,046 | COVERED (golden); "never steers" is D-035 only |
| AR-40 | End-to-end simulated event stream, no model calls | AUSTIN M1 | R-20 | TB14-G-001..008 | TB14-D-017..024,040..045 | COVERED (golden) |
| AR-41 | Evals authored first; an unimplemented case resolves to blocked | OWNER; METH §1.3 | R-21 | process | INFRA-D-001; run.py | COVERED (process evidence) |
| AR-42 | Implementers of **this** build are mechanically blind to `evals/` | OWNER; METH §1.5; ADR3 §2 | R-21 | none | none | WEAK (P0-5) |
| AR-43 | Independent MECE audit before implementers start | METH §1.4; OWNER | R-22 | process | this report | COVERED (process evidence) |
| AR-44 | Every hook and role documented with an example | METH §1 | R-24 | none | TB04-D-046, TB05-D-114, TB06-D-181, TB07-D-098, TB08-D-146, TB14-D-036 | COVERED (diag only), partial (P2-2) |
| AR-45 | Orchestrator "never": whole-repo greps, running the suite itself | MAP §3.1 | none | none | none | MISSING (P2-9) |

**Counts (45 in-scope requirements):** COVERED (golden) 20; COVERED (diagnostic only) 5; COVERED (process evidence) 2; WEAK 10; MISSING 8.

### 2.2 Requirements the register omitted
AR-06 (Orchestrator Bash restriction; the register and TB-02 contradict MAP §3.1), AR-13 (OS sandbox backstop), AR-20 (human pause for merges, PRs and shared-history deletes, METH §4), AR-23 (PostToolUse formatter and linter), AR-24 (Test-role Stop and runner SubagentStop), AR-32 (audit-trail fields: duration, tool count, outcome), AR-33 (Orchestrator PreCompact and Stop ledger or handoff write), AR-37 (graph node kinds), AR-45 (Orchestrator "never" rules). Two items the register **changed** rather than omitted: it moved "full-suite evidence" from the Test role's Stop (MAP §3.6) onto Implement's stop gate, and it reduced the audit-trail fields. The register's own rule is "if this register and a source disagree, the source wins", so each of these needs either a requirement row or an explicit, recorded deferral.

### 2.3 Out of scope for this build (with reason)
- Tracker adapters and TicketPort, D2 (AUSTIN §5.1): the tracker build; the PRDs exclude it.
- Graph runtime, checkpointing, stop/resume/replay, **S7**, D1 (AUSTIN §5.2): TB-12 excludes "executing the graph or a runtime".
- AgentRuntime multi-vendor adapters; Review from a different vendor (ADR3 §4.6, AUSTIN §5.6); Codex equivalents (MAP §1): runtime and model-portfolio work. Model values in role data are proposals.
- Langfuse tracing and cost per stage (S6, METH §6); budgets, timeouts and the per-run budget cap (MAP §3.1): observability and runtime.
- Human gate packets, phone notifications, the Notification hook, HITL and AFK modes (S4, AUSTIN §5.7): the gates build.
- Intake (G0), untrusted-input handling, memory consolidation, brownfield orientation (S1, S3): other stages.
- Sandbox choice D3, data policy D4, runbook S8: decisions and ops. But see P1-9: the sandbox *requirement* on the blindness backstop is in scope as a requirement, even if its configuration is deferred.

## 3. Golden-gate quality

### 3.1 Mutual exclusivity (redundant golden cases)
| Redundant case | Overlaps | Why redundant | Proposed swap |
|---|---|---|---|
| TB01-G-003 | TB01-G-007 | Both reject a non-1 `schema_version` with field `schema_version`; G-007 subsumes it | Swap for TB01-D-009 or D-010 (absolute path or `..` segment rejected, B4): currently no golden, and it is security-relevant |
| TB09-G-002 | TB09-G-008, G-001 | `assert True` is already the trigger that G-008 blocks five times; same added-line scan as G-001 | Swap for TB09-D-029 (Edit with no later `checks.test` run blocks) and add TB09-D-028 (allow control); see P0-3 |
| TB14-G-008 | TB14-G-002..007 | Replays exactly the same six events | Swap for TB14-D-001 (alt: `qa/cases` protected); see P0-1 |
| TB08-G-010 | TB08-G-005, G-009 | A third plain-allow control | Swap for TB08-D-114 (alt `db-reset` asks); see P0-1 |
| TB12-G-001 (minor) | TB12-G-008 | Both check `order()`; G-008 is the stronger Kahn tie-break | Optional (P2-1): swap for TB12-D-014 (unknown subset raises) |

### 3.2 Exhaustiveness (clauses with no golden case)
Whole requirements with no golden case: R-23 and R-24 (diagnostic only), R-21 and R-22 (process), plus every MISSING row above. Mandatory clauses of golden-covered requirements that have no golden case: R-11 profile-driven paths and allowed Bash; R-10 outside-root denial (B4) and the post-freeze baseline allow; R-14 destructive SQL and profile patterns; R-15 check 5 (full-suite evidence); R-17 the session-start positive path; R-01 the placeholder resolution (`$deploy`, `$git_host`); R-07 implement has no `Agent` tool.

### 3.3 Trivial-implementation resistance per hook (golden only)
| Hook | allow | deny, ask or block | always-allow passes? | always-deny passes? | role-blind passes? | other shortcut that passes |
|---|---|---|---|---|---|---|
| path_guard (TB05) | 4 (G-001,005,007,009) | 6 deny | no | no | no (G-005 vs G-002/004; G-006 vs G-007) | **Hard-coded default folders** (every case uses base) |
| blindness_guard (TB06) | 2 (G-002 Read src; G-010 test Read) | 8 deny | no | no | no (G-010) | **Deny every implement Bash, Grep and Glob**; **hard-coded `evals/**` and `tests/held_out/**`** |
| secrets_guard (TB07) | 3 (G-006,007,008) | 7 deny | no | no | n/a (applies to all roles) | none found (G-008 forces the profile allow-list) |
| bash_guard (TB08) | 3 (G-005,009,010) | 4 ask, 3 deny | no | no | no (G-001 vs G-002) | **Hard-coded `deployctl push`, no profile patterns, no SQL rule** |
| stop_gate (TB09) | 2 (G-006,007) | 7 block | no | no | no (G-007) | **Ignore the transcript (check 5)**; ignore git-unavailable |
| subagent_stop (TB10) | 5 | 5 block | no | no | no (G-010) | none found |
| ledger_audit (TB11-G-008) | 1 (decide is allow by contract) | none | spec'd | n/a | n/a | a no-op `record` fails, as intended |
| session_start (TB11-G-009) | 1 | none | n/a | n/a | n/a | **A constant "no ticket is active" `emit` passes** |

### 3.4 Pinning, derivation and observability
- No golden case pins a point the clarifications leave open. C-34 (frontmatter Stop run as SubagentStop) is honoured: no case depends on it.
- Every golden expectation traces to a PRD behaviour, a contract clause or a clarification ID in its docstring. TB-02 cases also cite MAP §3, which the TB-02 PRD lists as a published contract.
- Observable surfaces exist for every gated behaviour, except those the matrices already disclose: "no model call" (only no-network is observable), "never touches user-level settings", and "never steers routing" (checked only through D-035).
- Stale text: TB11-G-003's docstring cites the old chain line `<!-- chain: <hex> -->`, but its regex correctly requires `; seq: <n>` (C-30).

## 4. Findings

### P0: fix before any implementer starts
- **P0-1. Generality is not gated at golden.** Every golden case of TB-05, TB-06 and TB-08, and the TB-14 stream, uses the base fixture only. Hard-coded `research/`, `evals/**`, `tests/held_out/**` and `deployctl push` all pass. This violates the owner requirement and R-01, MAP §7 and METH §6. **Change:**
  - Swap TB14-G-008 for TB14-D-001, and promote TB14-D-002 (alt: `evals/**` is not protected).
  - Swap TB08-G-010 for TB08-D-114, and promote TB08-D-128 (alt: `deployctl push` is allowed).
  - Swap TB06-G-004 for TB06-D-082 (alt held_out, which keeps the held_out clause), and promote TB06-D-157.
  - Promote TB05-D-004 and TB05-D-005 (alt research dir).
- **P0-2. The blindness golden set has no allowed Bash case**, so "deny all implement Bash" passes, even though it would make the implement agent unable to build or test. **Change:** promote TB06-D-134 (`pytest tests/unit` allowed) and TB06-D-139 (`ls src`).
- **P0-3. R-15's clause "no evidence of a full-suite run" has no golden case.** Every golden stop-gate case removes `checks`. **Change:** swap TB09-G-002 for TB09-D-029 and promote TB09-D-028.
- **P0-4. Contract hole: the implement agent can switch off its own gates.**
  - A-05-1 exempts full-mode Bash from the path guard, and neither the blindness guard nor the bash guard covers `.factory/`. So `implement` can, through Bash, rewrite:
    - `.factory/profile.yaml`: drop `paths.eval`, and the next hook call loads the edited profile;
    - `.factory/baseline.json`: bless an edited frozen test;
    - `.factory/state/stop_gate_<id>`: write `5` and skip the cap.
  - Path guard B2 plus A-05-5 also let `implement` Write or Edit `.claude/settings.json` and `.claude/agents/implement.md`, which removes its hooks.

  This defeats S5 and R-11/R-15 in exactly the reward-hacking mode MAP §3.5 and SEVEN §5 cite (an agent patching the evaluator). **Change:** add a clarification:
  - add `.factory/**` and `.claude/**` to implement's write-protected paths for Write and Edit;
  - for `implement` Bash, deny any command that names a `.factory/` or `.claude/` path as a write target or an interpreter-one-liner argument (the same parsing as TB-06 B4a);
  - add golden cases: implement Edit of `.claude/settings.json` is denied; implement `echo 5 > .factory/state/stop_gate_x` is denied.
- **P0-5. This build's own implementers are only blind by instruction.** The repo has no `.factory/profile.yaml` and no `.claude` settings, and the hooks do not exist yet. The only barrier is PRD text ("Never read ... evals/"), which contradicts "hooks enforce; prompts advise" (ADR3 §2) for the owner's blindness requirement (R-21). **Change:** create each implementer worktree without `evals/` (sparse checkout excluding `evals/`, or a branch with `evals/` removed), and run implementer sessions with a project `permissions.deny` for `Read(./evals/**)`. A global deny is acceptable for this build, because the Test role does not run inside implementer sessions. Record this in METHODOLOGY.

### P1
- **P1-1.** The golden TB-04 set has no case where malformed stdin goes through `run_hook`; TB04-G-003 tests only `parse_payload`. R-09's "fail closed on malformed input" should be gated. **Change:** swap TB04-G-003 for TB04-D-020.
- **P1-2.** There is no golden case for the path guard's outside-root rule (B4). **Change:** promote TB05-D-048 (a symlink resolving outside the root).
- **P1-3.** TB11-G-009 checks only the no-ticket branch of `session_start`. **Change:** promote TB11-D-039 (emit contains the latest entry of the current ticket), or swap it for G-009.
- **P1-4.** TB13-G-001 and G-002 loop over hook ids taken from the implementation's own role data, so they are vacuous for any id TB-02 omits. TB-02 golden guarantees only `secrets_guard` and `bash_guard`, and nothing golden forces `ledger_audit` or `session_start`. **Change:** assert the literal eight ids with events and matchers (A-32, A-34).
- **P1-5. Check 5 can be satisfied by a denied or failed call.** The transcript records the `tool_use` block even when a hook denied it. With base `checks.test: "pytest -q"`, a bare `pytest -q` is itself denied for implement (A-06-1), yet it still counts. **Change:** a clarification that only a Bash call whose `tool_result` is not an error counts, plus a diagnostic case.
- **P1-6. "Never" rules for full-mode roles are advice, not enforcement.**
  - A-05-1 leaves Orchestrator Bash writes to app code and Test Bash edits of frozen evals unguarded, against ADR3 §4.3 and MAP §3.6.
  - The orchestrator's legitimate writes (routing state, ledger status lines, gate packets, shared seams per SEVEN §3.1 and METH §3) currently work *only* through this gap.

  **Change:** give `orchestrator` an explicit write set (ledger dir, routing state dir, shared-seam files from the profile) and restrict its Bash per MAP §3.1 (AR-06). Apply the freeze to Test's Bash, or record both as accepted residual gaps in the register.
- **P1-7. No agent can append to its own ledger section.** Research, Design, Audit and Review have read-only Bash and path-limited writes; the ledger lives under `.factory/ledger`; and the contract publishes only a Python API. So R-17 "each agent writes its own section" cannot actually happen (SEVEN §2 rule 7). **Change:** publish an agent-facing append path, such as `python -m factory.ledger append <section>` on the read-only allow list with role checking, or a SubagentStop `record` that appends to the role's section.
- **P1-8. METH §4's pause before merges, opening PRs and deleting shared history is not in R-14 or TB-08.** TB08-D-073 and D-074 expect **allow** for `git push origin main` and `git merge` from the orchestrator. **Change:** add `git merge`, `gh pr create`, `gh pr merge`, `git push --delete` and `git branch -D` as ask for orchestrator and deny for others, or record a deferral in the register.
- **P1-9.** The OS sandbox backstop (MAP §1, §3.5 "the sandbox is not optional") is in no requirement or PRD. TB-06 excludes it, and TB-13 emits no `sandbox` settings. **Change:** add a requirement (for example R-25) and a TB-13 behaviour that emits sandbox read-deny for eval and held-out paths, or record an explicit deferral.
- **P1-10.** Omitted MAP hooks: PostToolUse formatter and linter (AR-23); Test Stop and runner SubagentStop (AR-24); Orchestrator PreCompact and Stop (AR-33); audit-trail duration, tool count and outcome (AR-32). **Change:** add them to the register, or mark each deferred with its reason.
- **P1-11.** AUSTIN §3's node kinds (deterministic step, typed decision) cannot be expressed, because a stage's `role` must be one of the seven. Verify, Deploy, Door check and Triage have no representation. **Change:** add `kind: agent|deterministic|decision` to the graph contract (role required only for `agent`), or document the limit.
- **P1-12.** TB06-D-076 (`ln -s ../evals src/e` must be denied) is not derivable from the contract. Normalised against cwd, `../evals` lies *outside* the root; it points at `evals` only because `ln` resolves relative to the link's directory. **Change:** use `ln -s evals src/e`, or add a clarification (a protected directory segment in any path argument is denied).
- **P1-13.** `factory/agents/default_graph.yaml` (TB-12 B5, used by TB12-G-006) is not in TB-12's OWN list. **Change:** add it.
- **P1-14.** The golden set does not pin that implement has no `Agent` tool (A-18), nor that role data names no platform (R-01). **Change:** promote TB02-D-022 (or D-003) and TB02-D-017.

### P2
1. TB12-G-001 overlaps G-008 (see 3.1).
2. R-24 documentation cases exist only for TB-04, 05, 06, 07, 08 and 14. Add them for TB-01, 02, 03, 09, 10, 11, 12 and 13, whose PRDs all require a `docs/hooks/*.md`.
3. Clarification IDs A-11 and A-29 are each used for two different rulings, and C-20 is revised by C-30. Renumber so citations are unambiguous.
4. C-22 (entry numbers are file positions) and C-30 (verify orders by `seq`) can diverge after an out-of-order append. State that problems keep file positions.
5. C-35 (an entry moved into a section its role may not write is reported) has no case, and `coverage/TB-11.md` and `ambiguities-C.md` still say the point is unsettled. Add a diagnostic and update both notes.
6. The ledger chain is an unkeyed SHA-256 with its head anchor in the same file, so any writer can recompute it (implement can do so through Bash). Document the threat model, or anchor the head outside the file (git or routing state).
7. Stop-gate double registration (implement frontmatter `Stop` plus settings `SubagentStop`, A-22) will double-count the cap if C-34 resolves to "runs as SubagentStop". Make the counter idempotent per stop event.
8. C-01 and C-32 make an unparseable transcript fail open, against R-09's fail-closed rule. C-10 containment plus A-06-1 means "full-suite" is never actually required. Record both as accepted weakenings in the register.
9. AR-45: the Orchestrator's "never" rules (whole-repo greps, running the suite) are unenforced. Accept or add to the register.
10. Ambiguities two correct implementers could split on:
    - A-06-6 says `git diff` is allowed, while TB06-D-073 denies `git diff HEAD -- evals/` under B4a. State that B4a takes precedence.
    - The PRD says `rm -rf`, while TB08-D-094 expects `rm -fr` to be a door. State that flag order and combined forms count.
11. TB04-G-010 (and D-026, D-028) call `_need_cli("factory.hooks.path_guard")`, an undeclared dependency on TB-05. TB-04's golden stays blocked until TB-05 lands, although the B8 stub would already give exit 2. Drop the module requirement.
12. `lib.need` turns any `ImportError` inside an existing module into "blocked". Once modules exist, a broken import reads as blocked rather than failed. The verdict stays NOT GREEN, but restrict "blocked" to `ModuleNotFoundError` for the named module.
13. PRD text still conflicts with binding clarifications (TB-02 B6 says write-restricted roles list `path_guard`, A-13 says all seven; TB-04 says "seven hook ids", A-04-2 says eight). Clarifications win, but the PRDs tell implementers to stop and report on disagreement. Correct the PRD text to avoid needless stops.
14. No role may write `paths.frozen_tests`: Test writes only `paths.eval`, and implement is denied. State who creates frozen tests.

## 5. Sample check (diagnostic cases read against their clauses)
About 200 cases were read, including all of TB06-D-040..160 and D-161..169, TB08-D-001..179, TB09-D-012..017, 028..048, 052..058, 065..067, TB11-D-001..038 and 052..058, TB10-D-003..031, TB04-D-016..021, 047..048, 059..067, TB02-D-004..007, 016..019, 034..035, TB05-D-046..049, 115..117, 123..127, and TB12-D-015, 016, 026.
- **Wrong or underivable expectation:** TB06-D-076 (P1-12).
- **Correct by the contract but conflicting with a source:** TB08-D-073 and D-074 (P1-8), and TB05-D-123..126, which codify A-05-1 (P1-6).
- **Tautologies or cases that cannot fail:** none found among the sampled cases. TB13-G-001 and G-002 can pass vacuously (P1-4).
- **Undeclared cross-slice dependencies:** TB04-G-010, D-026 and D-028 need TB-05 (P2-11). Everything else that depends on another slice (TB-03 and TB-13 on TB-02; TB-05..11 on TB-01 and TB-04; TB-14 on all) matches the dependency graph in the PRD index.
- **Secret-shaped literals:** none. Synthetic keys are joined from fragments at run time; example emails use `example.invalid`.
