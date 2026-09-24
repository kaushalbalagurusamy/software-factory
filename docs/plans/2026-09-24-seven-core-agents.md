# Seven core agents: skills, tools and hooks

> **Status:** DESIGN DRAFT for owner review. Nothing is built. Companion to `2026-09-24-skills-consolidation-proposal.md`; skill names below use that proposal's target set (merged names such as `sf-orchestration` and `sf-one-way-door` do not exist yet).
> **Date:** 2026-09-24. **Evidence:** the Gauntlet lectures and research notes (read-only) and primary sources from Anthropic, OpenAI and Google, each cited in section 5. Vendor numbers are self-reported unless stated.

## 1. The seven agents

The backlog (`docs/backlog/2026-09-24-cleanup-and-tooling-ideas.md`) planned **six roles**: Research, Design, Implement, Test, Review and Audit. The **Orchestrator** is the seventh. It was not in the backlog; it is the Opus main session from the Week 2 hierarchy (`gauntlet/W2/2026-09-22-w2-agent-hierarchy-and-review-gates.md`) and the "orchestrator" of The Orchestrator lecture.

This replaces the consolidation proposal's suggested seventh role, "Operate". Deploy becomes a deterministic step the Orchestrator runs, and post-deploy checks belong to Test (section 4, point 6).

## 2. Design rules the table follows (and why)

1. **Split by context boundary, not by pipeline phase.** Anthropic (Jan 2026) warns that phase-based splits (plan, build, test) "create constant coordination overhead". Google's scaling study found every multi-agent setup lost 39% to 70% on sequential tasks, but gained 81% with a central coordinator on parallelisable ones. So the seven are **agent definitions**, not seven agents always running in a chain. The only fan-out is where the work is independent reading: Research, Audit, and Test running alongside Review.
2. **One writer at a time.** Only Implement edits application code, and only one Implement runs per git working tree. Parallel slices get their own worktrees. The lecture's rule is "parallelize reads, serialize writes". The MVF's so-called parallel dev step races on git's `index.lock`.
3. **The Orchestrator writes zero application code**, and its routing is code: typed state plus deterministic rules, with Jev only in shadow mode (The Orchestrator lecture, slides 5 and 10; OpenAI Agents SDK favours code-driven orchestration when results must be predictable).
4. **Verification is independent and blind.** Test and Review work without the implementer's context. Implement never sees held-out evals. SpecBench (2026) found the gap between visible and held-out test scores grows 28 points for every tenfold increase in code size. Anthropic (Jan 2026) recommends a verification subagent with no implementation context that runs the full suite.
5. **Hooks enforce; prompts advise.** CLAUDE.md and AGENTS.md are context, not enforcement (Claude Code hooks docs; `gauntlet/research/agent-harness-design.md` section 4). Every "must never" in the table is a hook or a missing tool, never just a sentence in a prompt. This also fixes the MVF flaw: its skills declare narrow tools, but its runner grants every agent all five MCP servers with permission checks bypassed.
6. **Narrow tool lists and the smallest adequate model.** Anthropic treats 15 to 20 or more tools on one agent as a red flag. Both Claude Code and Codex support per-agent tool lists and models.
7. **Handoff is through files, not chat.** Each agent reads the ticket ledger (fixed sections, append-only) plus its skills, and writes its section back. The MVF has "no agent-to-agent chatter; the memory file is the only shared state".

## 3. The table

### 3.1 Role, model and how it runs

| Agent | Job | Model (proposed; measure before fixing) | Runs as | Reads | Writes |
|---|---|---|---|---|---|
| **Orchestrator** | Holds state, sequences stages, dispatches, calls humans at gates, runs deploy | Opus (main session) | Single, long-lived; compaction plus ledger | Ticket ledger, routing state, subagent summaries | Routing state, ledger status lines, gate packets |
| **Research** | Verifies facts and surveys topics; orients in a repo | Sonnet lead, Haiku workers | Fan-out allowed (read-only), each returns a summary of 1,000 to 2,000 tokens | Web, docs, repo (read) | `research/*.md`, ledger "Research" section |
| **Design** | Brief to PRD, axioms and contracts, one-way-door check, ADR | Opus | Single, behind gates G0, G1 and G2 | Brief, repo map, research | PRD, spec, ADRs |
| **Audit** | Complete read pass over legacy code before a rewrite; bug catalog | Sonnet per unit, Haiku for inventory | Fan-out, one unit per dispatch | Source (read-only) | `docs/audit/**` only |
| **Implement** | Builds one slice against the spec | Sonnet; escalate to Opus after repeated failure | **One per worktree**; fresh-context loop with a cap | Slice brief, spec, repo, **not evals** | App code and its unit tests |
| **Test** | Writes evals first from the spec, freezes them, runs them, triages failures, runs post-deploy checks | Opus to author, Haiku to run and digest logs | Parallel with Review | Spec, frozen evals, build output | Eval files (before implementation only), verdicts |
| **Review** | Independent read of diff, traces and passes; drift against requirements | **A different vendor from Implement** (Codex or GPT-class), or Opus when that is unavailable | Parallel with Test; read-only | Diff, traces, spec, eval verdicts | Review verdict only |

### 3.2 Skills, tools and hooks

| Agent | Skills it loads (personal, then plugin) | Tools: allow | Tools: deny or absent | Hooks (all new; none exist today) |
|---|---|---|---|---|
| **Orchestrator** | sf-orchestration (with the Jev routing policy), plan-adherence, session-handoff, away-mode; superpowers `dispatching-parallel-agents` and `subagent-driven-development`; `railway:use-railway` for the deploy step | `Agent(research, design, audit, implement, test, review)` only; Read; git; tracker MCP (Linear or Notion, not chosen); Jev client; Railway CLI for deploy | Write and Edit on app code; repo-wide grep sweeps (delegate to a Haiku worker) | **SessionStart:** load ledger and routing state. **PreToolUse (Bash):** one-way-door rules on force push, destructive SQL, service deletes and deploys, asking a human on a match. **PreCompact / Stop:** write the ledger and handoff. **Notification:** push gate packets to the phone. Budget cap per run. |
| **Research** | grounded-research, deep-research, brownfield-explorer | Read, Glob, Grep, WebSearch, WebFetch, DeepWiki, alphaXiv; firecrawl only if kept | Write outside `research/`; Edit; Bash beyond a read-only list | **PreToolUse:** block writes outside `research/`. **SubagentStop:** reject output without a sources section. |
| **Design** | prd-designer, axiomatic-spec, sf-one-way-door; superpowers `brainstorming` | Read, Glob, Grep; Write only under `docs/specs`, `docs/adr`, `docs/prd`; `sf audit` (read) | App code writes; deploy tools | **PreToolUse:** path guard for the three doc folders. **Stop:** check the spec has every required section and each axiom has a check assigned. |
| **Audit** | legacy-audit (new, if approved), brownfield-explorer; interface and I/O checklists (folded from the retired auditors); `claude-security` scan for security findings | Read, Glob, Grep; read-only Bash (`git log`, `wc`, tree-sitter, `sf audit`); Write under `docs/audit/` | Edit anywhere; Write outside `docs/audit/`; network | **PreToolUse:** block every write outside `docs/audit/` ("an audit is a read pass"). **SubagentStop:** every catalog row carries a file and line citation and a severity. |
| **Implement** | superpowers `test-driven-development` and `systematic-debugging`; `claude-api` when the slice calls an LLM | Read, Glob, Grep, Write, Edit, Bash in the OS sandbox; LSP | **Any read of eval and held-out paths**; edits to frozen tests; deploy tools; Agent | **PreToolUse:** deny Read, Grep and Bash access to `evals/**` and to held-out fixtures (blindness enforced, not requested). **PostToolUse (Edit/Write):** formatter and linter. **Stop:** run `sf verify` (baseline test hash, skip and xfail scan, trivial-assert scan); block "done" on failure. Iteration cap. |
| **Test** | eval-designer, eval-gate-triage (project-local), sf-deploy-verify (new); superpowers `verification-before-completion`; langfuse | Read, Glob, Grep, Bash (test runners), Write under `evals/**` **only before the freeze**; Playwright (post-deploy UI checks); Langfuse | Edit on app code; eval edits after the freeze | **PreToolUse:** after the freeze, block writes to eval files unless the baseline-update path is used. **Stop:** require evidence of a full-suite run (Anthropic's warning about declaring victory too early). |
| **Review** | sf-implementation-review (with the folded checklists); plugins: `code-review`, pr-review-toolkit reviewers, `claude-security` | Read, Glob, Grep, read-only Bash (`git diff`, trace queries); `Agent(pr-review-toolkit:*, feature-dev:code-reviewer)` | Write and Edit everywhere; running the suite again | **PreToolUse:** deny Write and Edit. **SubagentStop:** verdict must be APPROVE or REJECT, with file and line citations and a right-reason or wrong-reason grade per pass. |

**Codex side.** The same seven go in `.codex/agents/*.toml` (Codex custom subagents, generally available March 2026, each with its own model). Codex rules are enforced through exec policy rules and permission profiles; whether Codex has hooks equivalent to Claude Code's is **[unverified]**. Today only three of the five product-repo agents have Codex definitions.

**Caveats to verify before building.**
- Whether a Claude Code subagent's frontmatter can preload skills (`skills:`) and carry its own `hooks:` is **[unverified in this session]**. If it cannot, hooks go in project `.claude/settings.json`, using the subagent-aware events (`SubagentStop`) and path matchers.
- Plugin names assume the plugin cleanup in the proposal's section 8.2.

## 4. Positions taken (for your review)

1. **Seven definitions, not a seven-stage relay.** A small ticket may use only Orchestrator, Implement, Test and Review. Design runs at gates; Research and Audit run when the ticket needs them.
2. **Your manifesto versus multi-agent bureaucracy.** The manifesto argues against a PM, Dev, Reviewer and QA relay (`gauntlet/W2/2026-09-23-mvf-vs-unity-software-factory-comparison.md`, section 5). This design takes the evidence-backed middle position: split only where context isolation or parallel reading pays, keep one writer, and let deterministic checks (`sf verify`, `sf audit`, hooks) carry the verification burden rather than agent debate. That position needs an ADR (Austin plan, section 8).
3. **The Review model should come from another vendor.** This follows the Austin plan's rule against correlated blind spots, and Codex already plays that role in the Week 2 hierarchy. The cost is a second billing surface.
4. **Test writes evals before Implement exists and freezes them;** Implement is blocked from them by a hook. This follows your saved eval-first rule and the SpecBench result.
5. **Audit and Research are the only fan-out writers**, and each writes only its own docs folder.
6. **Deploy has no agent of its own.** The Orchestrator runs a scripted deploy (for the Co-Pilot, `railway up` from a clean clone), and Test runs `sf-deploy-verify` against the project checklist. The `ops-operator` agent in the product repo stays as a project utility.
7. **Model tiers are proposals.** Your standing rule is to survey models and run small experiments before settling. The Austin plan's section 5.6 is where that happens.

## 5. Evidence

**Gauntlet (local, read-only):**
- `lectures/2026-09-23-the-orchestrator-software-factories.md`: the orchestrator holds state and "writes zero application code"; routing without an LLM; three gates where "being wrong is expensive and catching it is cheap"; review and test run in parallel because they only read; the gate "does not edit the work"; routing state is kept separate from the content ledger.
- `lectures/2026-09-22-advanced-graphs-with-aaron.md`: parallelize reads, serialize writes; gate by risk, not habit. Your replication (n=1, flagged as noisy) found multi-agent at about 0.8 times the tokens, thanks to cheaper worker models and separate contexts.
- `lectures/2026-09-24-reverse-engineering-legacy-codebase-slides.md`: "an audit is a read pass"; one artifact per phase.
- `gauntlet/research/agent-harness-design.md`, `agent-memory.md`, `agent-loop-types.md`: hooks enforce and instruction files advise; files plus search is a strong memory baseline; METR observed reward hacking, including an agent patching the evaluator.

**Anthropic:**
- "How we built our multi-agent research system" (Jun 2025): +90.2% over a single agent on an internal eval, at about 15 times the tokens; most coding tasks have fewer parallel parts than research; each delegation needs an objective, output format, tools and boundaries.
- "Building multi-agent systems: when and how to use them" (Jan 23, 2026): start with one agent; multi-agent costs 3 to 10 times the tokens; split for context protection, parallel work or specialisation, not by phase; 15 to 20 or more tools is a red flag; verification subagent without implementation context.
- "Effective context engineering for AI agents" (Sep 2025): context rot; subagents return summaries of 1,000 to 2,000 tokens; compaction and notes files for long-running agents.
- Claude Code docs (subagents, hooks, skills): per-agent tools, disallowed tools and model; limits on which agents a subagent may spawn; hooks as the deterministic layer.

**OpenAI:**
- Agents SDK docs: code-driven orchestration for predictable speed, cost and performance; agents-as-tools versus handoffs.
- Codex docs: layered AGENTS.md with a 32 KiB cap; formatting and lint belong in CI, not review prompts; custom subagents as TOML with their own models (GA March 2026, per Simon Willison, 16 Mar 2026).
- "A practical guide to building agents" (PDF): **not verified**; the fetch failed.

**Google:**
- "Towards a science of scaling agent systems" (Google Research, DeepMind, MIT; arXiv Dec 2025, blog Jan 28, 2026): independent agents amplified errors 17.2 times versus 4.4 times with central coordination; +81% on parallelisable tasks; −39% to −70% on sequential tasks; the best architecture for a new task was predicted with 87% accuracy.
- ADK multi-agent patterns (Dec 2025): start with a sequential chain, then add complexity; a loop agent for generate, critique and refine.

**Academic:** SpecBench (arXiv 2605.21384, 2026): reward hacking grows with code size; one agent memorised test inputs in a 2,900-line "compiler". Other 2026 reward-hacking papers were found by title only and are **unverified leads**.
