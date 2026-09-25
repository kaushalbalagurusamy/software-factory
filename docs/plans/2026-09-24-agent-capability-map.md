# Agent capability map: hooks, skills, MCP servers and tools per agent

> **Status:** DESIGN, nothing built. Follows ADR-0003 and `2026-09-24-seven-core-agents.md` (this file replaces that file's section 3.2 with names that match the consolidated skills and the MCP servers actually installed).
> **Date:** 2026-09-24.
> **Model choices are proposals.** Measure them with small experiments before fixing them.

## 1. What the platform supports (checked against the Claude Code docs today)

Source for this section: a docs lookup run today (code.claude.com pages on sub-agents, hooks, permissions and sandboxing). Where the docs were silent it says so.

- **Agent definition fields:** `name`, `description`, `tools`, `disallowedTools`, `model`, `skills` (preloads skills at start), `hooks` (scoped to that agent), `mcpServers`, `permissionMode`, `maxTurns`, `isolation: worktree`, `memory`, `effort`, `background`. So one file per agent can carry its model, tools, skills, MCP servers and hooks.
- **MCP tools in `tools`:** named `mcp__<server>__<tool>`; `mcp__<server>` grants a whole server. Whether a single-tool entry works in `tools` is **not documented**; test it before relying on it.
- **Spawn allowlist:** `Agent(a, b)` in `tools` limits which agents an agent can start (already used in the OpenEMR repo's `implementation-reviewer`).
- **Hooks that see agents:** `SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`. A `PreToolUse` hook input carries `agent_type` (the agent name), so **one shared hook can block a path for one agent only**. A hook in an agent's own frontmatter runs only while that agent is active. Frontmatter hooks and inline MCP servers from a repo do not run until the folder is trusted.
- **Blindness limits:** a `permissions.deny` rule such as `Read(evals/**)` applies to sub-agents, and is applied best-effort to Grep and Glob. It does **not** stop a shell command or script that reads the files without naming them. The sandbox is the OS-level backstop.
- **Not verified:** whether Codex has hook equivalents. Treat Codex enforcement as exec-policy and permission profiles until checked.

## 2. Rules the map follows

1. **Enforce with hooks and missing tools, never with prompt text alone.** A "must never" is a hook, a deny rule or an absent tool.
2. **Attach an MCP server only to the agents that need it.** Every attached server adds its tool list to that agent's context. Keep each agent under about 15 to 20 tools.
3. **One writer at a time** (Implement). Others write only their own folder.
4. **Verification is blind and independent** (Implement never sees evals; Review sees the diff, spec and traces, not the implementer's story).
5. **Least secret:** no agent gets a credential it does not use. Keys are read from environment variables by name; nothing writes a key value to a file.

## 3. The seven agents

Each entry: model, skills to preload, tools, MCP servers, hooks, and what it must never do.

### 3.1 Orchestrator

- **Model:** Opus, the main session. Long-lived; compaction plus the ticket ledger.
- **Skills:** `orchestration`, `plan-adherence`, `session-handoff`, `away-mode`, `deploy-verify` (the pre-deploy gate and the deploy step), `one-way-door` (to classify a door before any risky step). Plugin: superpowers `dispatching-parallel-agents`.
- **Tools:** Read; `Agent(research, design, audit, implement, test, review)` only; Bash restricted to git (read plus commit by path), the Jev client, and the deploy command the project checklist names; PushNotification for gate packets.
- **MCP servers:** the project's git host for PR and CI status (`github` or `gitlab`, read tools only); `railway` read tools (status, logs) for deploy state. A tracker (Linear or Notion) once one is chosen.
- **Hooks:**
  - `SessionStart`: load the ticket ledger and routing state.
  - `PreToolUse` on Bash: one-way-door rules. Ask a human on force push, `--no-verify`, destructive SQL, service or volume deletes, variable changes on a service whose image source is the known hazard, and any deploy.
  - `PreCompact` and `Stop`: write the ledger and a handoff.
  - `Notification`: push permission prompts and finished tasks to the phone.
  - A per-run budget cap.
- **Never:** Write or Edit application code; run whole-repo greps or the test suite itself (dispatch a Haiku worker).

### 3.2 Research

- **Model:** Sonnet lead, Haiku workers. Fan-out allowed; each returns a 1,000 to 2,000 token summary.
- **Skills:** `grounded-research`, `deep-research`, `brownfield-explorer`.
- **Tools:** Read, Glob, Grep, WebSearch, WebFetch; Write only under `research/`.
- **MCP servers:** `deepwiki` (repo docs), `alphaXiv` (papers), `firecrawl` (still enabled; drop it if WebFetch proves enough), git-host read tools for code search.
- **Hooks:** `PreToolUse` path guard: Write only under `research/`. `SubagentStop`: reject output with no sources section or with an unmarked unverified claim.
- **Never:** Edit; Bash beyond a read-only list; write outside `research/`.

### 3.3 Design

- **Model:** Opus. Single, behind the human gates (idea, spec, architecture).
- **Skills:** `prd-designer`, `axiomatic-spec`, `one-way-door`; superpowers `brainstorming` and `writing-plans`.
- **Tools:** Read, Glob, Grep; Write only under `docs/prd`, `docs/spec` and `docs/adr`; Bash limited to `sf audit` (read).
- **MCP servers:** none by default. Add Notion or Claude Docs only for a project that keeps its PRDs there.
- **Hooks:** `PreToolUse` path guard on those three folders. `Stop`: the spec must have every required section and every axiom must name its check. `SubagentStop`: if the door check said one-way, an ADR must exist.
- **Never:** write application code; use deploy tools.

### 3.4 Audit

- **Model:** Sonnet per unit, Haiku for inventory. Fan-out, one unit per dispatch.
- **Skills:** `legacy-audit`, `brownfield-explorer`; the two checklists under `implementation-review/reference/`; plugin `claude-security` for security findings.
- **Tools:** Read, Glob, Grep; read-only Bash (`git log`, `wc`, a tree-sitter CLI, `sf audit`); Write only under `docs/audit/`.
- **MCP servers:** none. No network.
- **Hooks:** `PreToolUse` path guard: block every write outside `docs/audit/` ("an audit is a read pass"). `SubagentStop`: every catalog row has a file and line citation and a severity.
- **Never:** Edit anything; touch the network.

### 3.5 Implement

- **Model:** Sonnet, escalating to Opus after repeated failure. One per working tree; parallel slices get their own worktrees (`isolation: worktree`) or a file-ownership manifest.
- **Skills:** superpowers `test-driven-development` and `systematic-debugging`; `claude-api` when the slice calls an LLM; `frontend-design` for UI slices.
- **Tools:** Read, Glob, Grep, Write, Edit, LSP, Bash in the OS sandbox.
- **MCP servers:** none by default. A docs server for library questions only if a slice needs one.
- **Hooks:**
  - Blindness: `permissions.deny` for `Read` and `Grep` on `evals/**` and held-out fixtures, plus a `PreToolUse` Bash hook that checks `agent_type == implement` and blocks commands naming those paths. The sandbox denies file reads there at the OS level. Residual gap: a script that opens the files itself, which is why the sandbox is not optional.
  - `PreToolUse` on Bash: block the git commands that touch a shared tree (`stash`, `checkout`, `restore`, `reset`, `clean`, `add -A`, `add .`) as the orchestration skill requires.
  - `PostToolUse` on Edit and Write: formatter and linter.
  - `Stop`: run `sf verify` (baseline test hash, skip and xfail scan, trivial-assert scan) and block "done" on failure; check `git status --porcelain` stayed inside the agent's own paths; iteration cap.
- **Never:** read evals; edit frozen tests; use deploy tools; spawn agents.

### 3.6 Test

- **Model:** Opus to author evals, Haiku to run them and digest logs. Runs in parallel with Review.
- **Skills:** `eval-designer`; `eval-gate-triage` (project-local); `deploy-verify` (its post-deploy checks section); superpowers `verification-before-completion`; `langfuse`.
- **Tools:** Read, Glob, Grep, Bash for test runners, Write under `evals/**` only before the freeze.
- **MCP servers:** `playwright` for post-deploy UI checks; `railway` read tools (status, logs, HTTP metrics) for live checks; Langfuse through its skill or API for traces. Add `vercel` or `supabase` only in a project that uses them.
- **Hooks:** `PreToolUse`: after the freeze, block writes to eval files unless the baseline-update path is used. `Stop`: require evidence of a full-suite run. `SubagentStop` on the Haiku runner: return failure lines only.
- **Never:** Edit application code; edit evals after the freeze.

### 3.7 Review

- **Model:** a different vendor from Implement (Codex or a GPT-class model) when available, otherwise Opus in a fresh context. Runs in parallel with Test; read-only.
- **Skills:** `implementation-review` (with its two checklists). Plugins: `code-review`, the `pr-review-toolkit` reviewers, `feature-dev:code-reviewer`, `claude-security`.
- **Tools:** Read, Glob, Grep; read-only Bash (`git diff`, trace queries); `Agent(pr-review-toolkit:silent-failure-hunter, pr-review-toolkit:pr-test-analyzer, feature-dev:code-reviewer)`.
- **MCP servers:** git-host read tools (PR diff, CI logs); Langfuse read for traces; `railway` logs read-only.
- **Hooks:** `PreToolUse`: deny Write and Edit. `SubagentStop`: the verdict must be APPROVE or REJECT, with file and line citations and a right-reason, wrong-reason or inconclusive grade for each passing case.
- **Never:** edit implementation, tests or cases; re-run the whole suite; read the implementer's own account of its work.

## 4. Hooks that apply to every agent

- **Secrets:** `PreToolUse` on Write, Edit and Bash blocks content shaped like a key (for example `sk-or-`, `sk-ant-`, `ghp_`, private-key headers). Secrets are referenced by variable name only. This also stops a value pasted into chat from reaching a file.
- **Git hygiene:** block `git add -A`, `git add .`, `--no-verify`, force push, amend and rebase unless a human has approved that step.
- **Audit trail:** `SubagentStop` appends agent, duration, tool count and outcome to the ticket ledger.

## 5. MCP servers: attach and do not attach

| Server | Attach to | Why |
|---|---|---|
| `deepwiki`, `alphaXiv` | Research | Repo documentation and papers |
| `firecrawl` (plugin) | Research, optional | Scraping; WebFetch may be enough |
| `github` or `gitlab` | Orchestrator, Research, Review (read tools) | PR, CI and code search; pick the one the project uses |
| `railway` | Orchestrator, Test, Review (read tools) | Deploy state, logs, HTTP metrics; deploys go through the checklist route |
| `playwright` | Test | Post-deploy UI checks |
| Notion, Claude Docs | Design, optional per project | Only if PRDs live there |
| `vercel`, `supabase` | Test, Orchestrator, per project | Only for projects deployed there |
| Gmail, Calendar, Drive, Slack, Wolfram, Alpha Vantage, Safari, Figma, Stripe | none | No agent's job needs them |

Every agent that gets an MCP server should list only the server or its read tools in `tools`, so the write tools never appear in its context.

## 6. What exists today and what to build first

- **Exists:** the OpenEMR repo has five agent files (`implementer`, `eval-author`, `implementation-reviewer`, `ops-operator`, `docs-writer`). They map to Implement, Test, Review, an Orchestrator-side deploy utility, and a docs utility. They use `name`, `description`, `model` and `tools` only; none uses `skills`, `hooks` or `mcpServers` yet.
- **Build first (highest value per effort):** (1) the Implement blindness rules (deny rules, the agent-type Bash hook, sandbox), because they turn the eval-first rule from advice into enforcement; (2) the Review deny-Write hook and verdict check; (3) the secrets hook; (4) the Orchestrator's one-way-door Bash hook. Research, Design and Audit path guards are small and can follow.
- **Then:** add `skills:` to each definition so roles preload their skills, and test whether single-tool MCP entries work in `tools`.
