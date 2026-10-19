# Native Claude Code installation and verification (2026-10-19)

Scope: make `/sf` and its associated skills, agents, hooks and tools work **natively** in Claude Code, not merely exist in the repository. All delegated work and all test sessions used **Sonnet 5.5 only** (`claude-sonnet-5-5`); no Opus session was started, and the one precedence test that needed a different "inherited default" used Haiku as the stand-in.

Evidence labels used throughout:
- **ACTUAL HARNESS**: a real headless Claude Code session (`claude -p --model sonnet`), judged from the recorded `stream-json` event stream, files on disk and exit codes, never from what the model said. Evidence: `streams/` (S1 to S4) and `streams-s5/`, summary in `summary.json` (32 of 32 checks pass in the final runs).
- **SUBPROCESS/UNIT**: the hooks or commands executed as subprocesses with canned JSON payloads, or unit tests. Useful, but not the harness.
- **NOT VERIFIED**: stated as such.

## 1. Result in one paragraph

Real sessions verified that: the 13 installed skills (including through the symlinked `~/.claude/skills`) and the 7 generated agents resolve; `/sf` expands natively (the session quoted the skill's own sentence verbatim); the project's settings-level hooks fire in a headless session without a trust dialog and receive the subagent's role (`Denied for role implement`); the protected eval `Read` and `git add -A` were blocked by the real hooks (exit 2); a deliberately failing contract gate (exit 16, COUNTEREXAMPLE) was repaired through delegation to the `implement` agent and then passed (re-run by the harness: exit 0); a human stop was obeyed (`sf slice done` refused with exit 5, the release attempt refused, the stop still open afterwards); and a project pin forced both the main session and a subagent (whose own definition names another model) to Sonnet although the user-level default is something else. A second `sf install` into the same project reports `unchanged`, and a second global skill adoption reports `already linked` with no new backup.

## 2. Stage by stage: repo source, installed artifact, invocation, observed result, remaining gap

| Stage | Repo source | Installed artifact / config | Actual invocation | Observed result | Remaining gap |
|---|---|---|---|---|---|
| `/sf` itself | `skills/sf/SKILL.md` | `~/.claude/skills/sf` (symlink to the repo) | S1: prompt `/sf ...` in a real session | ACTUAL: skill expanded; session quoted "The loop is not a variable. Schedule pressure may reorder work or slice it smaller", ran `sf hitl status` and `sf slice triage` successfully (9 hook responses) | Interactive `/sf` (not `-p`) and compaction re-injection by the `sf-reminder` hook (user-level, excluded from the isolated config) were not exercised |
| Skill resolution (13 skills) | `skills/*` | `~/.claude/skills/*` symlinks, backups in `~/.claude/skills-backups/20261019-205147` | init message of every session | ACTUAL: all 13 present in the real runtime's skill list: sf, qa-supervisor, intake-gate, structure-scan, contract-verify, orchestration, implementation-review, prd-writer, ops-dashboard-design, mermaid-nesting-dolls, axiomatic-spec, doc-sync, eval-designer | `lsf` (a separate lightweight skill, `disable-model-invocation: true`) is untouched |
| `sf` command | `factory/cli.py`, `pyproject.toml` | `~/.local/bin/sf` shim (new file) | every session ran `sf ...` | ACTUAL: ran from the project directory, exit codes propagate | The shim hard-codes the checkout path and its venv; `sf install doctor` checks it |
| Intake gate (source-hash sweep record) | `factory/intake`, `skills/intake-gate` | `sf intake ...` | SUBPROCESS/UNIT only (61 tests) | UNIT: gate fails without a sweep record for the current source hash | **Not run in a real session**; the sweep itself is a model procedure |
| Slice format, triage | `factory/slices`, `docs/slice-format.md` | `sf slice ...` | S1 `sf slice triage`, S3 `sf slice done` | ACTUAL: triage returned the fixture slice; `done` blocked by an open stop (exit 5) | Full slice lifecycle (lock, tick, verify chain, amend) not run live |
| Structure and dolls | `factory/structure`, `skills/structure-scan`, `skills/mermaid-nesting-dolls` | skills linked; `sf structure ...` | UNIT and the dogfood demo only | UNIT: 4,458 tests include the independent adversarial acceptance suite | Not run in a real session |
| Contracts and solver outcome routing | `factory/verify`, `skills/contract-verify` | `sf contracts ...` | S4 in a real session | ACTUAL: first verify exit 16 (COUNTEREXAMPLE), repair by the `implement` agent, harness re-run exit 0 (PROVED) | UNSUPPORTED/UNKNOWN routing to tests is unit-tested, not live |
| Role separation | `factory/agents/roles/*.yaml`, `generate.py` | `.claude/agents/*.md` in the project (see section 3) | S2, S4 delegation | ACTUAL: `implement` ran as a subagent with its tool list; denial text said "for role implement", proving the runtime passes `agent_type` to settings-level hooks | `claude --agent orchestrator` (running the main session as the orchestrator role) not exercised |
| Blind implementer | `scripts/implementer-worktree.sh`, `blindness_guard` | hooks in `.claude/settings.json` | S2: subagent asked to Read `evals/cases/case_a.py` | ACTUAL (attempt 1 of 3): `PreToolUse:Read` exit 2; the marker `EVAL-LEAK-7f3a9c` never appeared in any tool result | A subagent may skip the attempt out of its own prose (seen once); the runner retries until it attempts. A denylist guard is not OS isolation (section 6) |
| Git hygiene / one-way doors | `bash_guard` | settings hook | S2 `git add -A`; S3 `sf hitl release` | ACTUAL: `git add -A` exit 2 and the index stayed empty; release command asked or denied | Parser guard, cannot be complete |
| QA feedback handling, retry and escalation | `factory/qa`, `skills/qa-supervisor` | skill linked; `sf qa ...` | UNIT only (83 tests with a scripted fake implementer) | UNIT: bounded retries, environment crashes separate, leak check; default ladder is Sonnet-only | **Not run with real agent sessions** |
| Reviewer amendments | `implementation-review` skill, `sf slice amend` | skill linked | UNIT only | UNIT: additive-only amendment, weakening refused | Not run live |
| Human stop | `factory/hitl` | `sf hitl ...`, stop ledger under `.factory/stops` | S3 in a real session | ACTUAL: `request` created the stop; `status` exit 3; `slice done` exit 5; release refused; stop open afterwards | Friction not proof (a role with full Bash could allocate a terminal); no out-of-band secret |
| Docs / ADR drift | `doc-sync`, `sf slice done`, `sf intake check` | skills linked | prose and UNIT | UNIT only | Mostly procedure; not run live |
| Stage dashboard events and snapshot refresh | `scripts/ops-stage-event.sh`, `factory/ops` | `sf ops bundle` | run by hand; verified in a real browser against this repo's history | ACTUAL (browser): commit selector time travel, runtime telemetry separate, 390 px layout | Not driven by a real `/sf` session; not deployed |
| Model routing (Sonnet only) | `factory/install/core.py` | project `.claude/settings.json`: `model` and env pins; agent files `model: sonnet` | S5, and `--model sonnet` in S1 to S4 | ACTUAL: with a Haiku user default and no pin the session ran `claude-haiku-5-5` (control); with the pin the main session and a subagent defined as `haiku` ran `claude-sonnet-5-5` | The global user default is still Opus (see section 5) |

## 3. Inventory

- **Generated roles and permissions** (installed by `sf install` into the project, all `model: sonnet`):

| role | tools | disallowed |
|---|---|---|
| orchestrator | Read, Bash, PushNotification, Agent(research, design, audit, implement, test, review) | Write, Edit |
| research | Read, Glob, Grep, WebSearch, WebFetch, Write, Bash | Edit |
| design | Read, Glob, Grep, Write, Bash | |
| audit | Read, Glob, Grep, Write, Bash | Edit |
| implement | Read, Glob, Grep, Write, Edit, LSP, Bash | Agent |
| test | Read, Glob, Grep, Write, Edit, Bash | |
| review | Read, Glob, Grep, Bash, Agent(pr-review-toolkit reviewers) | Write, Edit |

- **Hooks and scope.** Installed in the project's `.claude/settings.json` (settings-level, which the docs say run in headless mode even in an untrusted folder; confirmed): `PreToolUse` `path_guard` and `secrets_guard` on `Write|Edit|MultiEdit|NotebookEdit|Bash`, `blindness_guard` on `Read|Grep|Glob|Bash`, `bash_guard` on `Bash`; `SubagentStop` `stop_gate`, `subagent_stop`, `ledger_audit`; `SessionStart` `session_start` (observed firing: "No ticket is active."). The same commands are also written into the agent files' frontmatter, but project-subagent frontmatter hooks need folder trust, so nothing relies on them. The owner's user-level hooks (alerts, reminders) are not touched and do not run in the isolated test config.
- **A broken hook fails open.** In Claude Code a hook command that cannot run exits non-2 and is a non-blocking error. `sf install` therefore writes absolute, verified commands (`PYTHONPATH=<checkout> <venv python> -m factory.hooks <id>`) and `sf install doctor` executes each one with a canned allow payload and a canned deny payload and fails if a command cannot run. The real-session denials above are the proof that the installed commands actually run.
- **MCP and credentials.** The flow needs no MCP server to function. Connected and reused: github, playwright (dashboard checks), langfuse (only for apps with LLM features), deepwiki. Needing authentication, left alone: gitlab.com, the Railway and Firecrawl plugins (the `railway` CLI MCP is connected). `docker` fails to connect (unused). Credential names present in the runtime env file (values never read): GitHub, GitLab, OpenRouter, portal and two Qrypt keys. Nothing was added or changed.
- **Stale or conflicting copies.** No product repository has its own `sf`, `lsf` or `build-loop` skill; `~/.claude/skills/build-loop` had already been deleted by someone else; `lsf` is separate and explicit-only. The previous live `sf` differed from the repo copy by one run-output file only (kept in the backup).
- **Sessions already registered** (`~/.claude/vultr/sessions.json`) are pinned to `sonnet`.

## 4. Findings from the real sessions that changed the build

1. `--setting-sources project,local` also excludes the user-level **skills** directory, so the first probe could not see `sf`; the rehearsal uses an isolated `CLAUDE_CONFIG_DIR` that links the real `~/.claude/skills` and carries only a copy of the login (deleted at the end of the run).
2. The generated hook command `python -m factory.hooks <id>` assumes `python` and the `factory` package are resolvable; the installer now resolves them and `doctor` executes them.
3. Narrow `--allowedTools` plus a model that chains `; echo "exit=$?"` produced permission denials unrelated to the factory; the scenarios now tell the session to run plain commands.
4. A subagent can skip a step it believes is forbidden, which leaves a guard unexercised; the runner retries until the protected `Read` is attempted and reports the attempt number.
5. Subagent messages are not in the stream unless `--forward-subagent-text` is passed.
6. A security review of the release gate led to: release requires an interactive terminal, the stop ledger moved under `.factory/` (covered by the existing control-folder protection), stop roots are derived from the slice path (a `--root` flag cannot point elsewhere), and `doctor` runs only the commands the installer would generate (no shell).

## 5. Sonnet-only routing and the inherited Opus default

The owner's `~/.claude/settings.json` has `"model": "opus"`; it was **not changed** (Opus is reserved for another use and the change would affect every project). Instead:
- new sessions for this work start with `--model sonnet` (it beats every settings file and `ANTHROPIC_MODEL`);
- `sf install install --project DIR` writes the project pin (`model: sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`), and the generated agent files all carry `model: sonnet` although the role specs propose Opus for four roles;
- the QA retry ladder defaults to Sonnet only and accepts another model only through an explicit opt-in in `.sf/policy.yaml`;
- this repository has its own local pin in `.claude/settings.json` (git-ignored, new file).
Gap: any session started elsewhere without `--model sonnet` and without a project pin still inherits Opus.

## 6. What this does not prove

- No claim of mechanical or OS isolation: the guards are command-text parsers plus settings hooks, and a subagent with Bash can still reach the same machine. The sandbox and permission layer remain the backstop (see the residual-risk sections of `docs/hooks/*.md`).
- The human stop is an enforced procedure, not an unforgeable barrier.
- Not exercised in a real session: the intake gate, the full slice and QA lifecycle with real agents, reviewer amendments, the dashboard driven by a real `/sf` run, interactive (non-`-p`) use, the user-level reminder hooks, and the ponytail and oh-my-mermaid plugins (they are not loaded in the isolated config).
- Real-session outcomes vary with the model (S2 needed one attempt in the final run; in an earlier run the subagent skipped the protected read). Results here are from the final runs, with the variability disclosed.
- Approximate cost of all real sessions including re-runs: a few dollars; each final scenario cost between $0.07 and $0.21.

## 7. Commands

```bash
# install into a project (idempotent; backs up what it changes; never edits an existing profile)
sf install install --project DIR            # add --dry-run to see the diff only
sf install doctor  --project DIR            # executes the generated hook commands; non-zero on any failure
sf install uninstall --project DIR          # restores from the manifest; refuses files changed since install
# global skills (backups in ~/.claude/skills-backups/<timestamp>)
python3 scripts/skills_sync.py status
python3 scripts/skills_sync.py install --adopt          # idempotent: second run says 'already linked'
sf install doctor                                        # skills, sf command and dependencies
# real-session rehearsal (disposable project, isolated config, Sonnet only, bounded)
python3 scripts/rehearse-native.py --keep --out DIR      # S1 to S5; delete the temp project afterwards
```

Rollback: remove a skill link and move the backup directory back (`mv ~/.claude/skills-backups/20261019-205147/<name> ~/.claude/skills/<name>`), delete `~/.local/bin/sf`, delete `.claude/settings.json` in this repository, and `sf install uninstall --project DIR` for a project.

## 8. Which sessions need to restart

- A running session keeps the skills, agents and settings it loaded at start: **restart or start a new session** to pick up the changed `sf`, `orchestration`, `implementation-review`, `prd-writer`, `ops-dashboard-design` skills and the four new ones (whether Claude Code live-reloads the skills directory was not tested).
- The `sf` command works immediately in running sessions (it is looked up when a command runs).
- A project's new `.claude/settings.json` pin and hooks apply to sessions started after the install in that directory.
- Sessions in other projects (including the AEA and Riverside work and the older sessions) were not touched.
