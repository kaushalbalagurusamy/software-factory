# Findings to carry into the skills overhaul

> **Status:** reference notes. Nothing here has been acted on: no skill, repo, plugin or account was changed while gathering it.
> **Date:** 2026-09-24 (findings gathered 2026-09-23)
> **Purpose:** hand-off for the next session, whose job is a skills overhaul to streamline the software factory. This file only records what was found and where it is saved. Decisions are the owner's.
> **Separate from:** the Austin-ready plan (`2026-09-23-austin-ready-software-factory-plan.md`, same folder) and the notes repo. No existing notes or stashed files were edited to produce this file.

## 1. Skill inventory (snapshot, 2026-09-23)

### 1.1 Where skills live

| Location | Contents | Version-controlled? |
|---|---|---|
| `~/.claude/skills` | 19 personal skills (plus a `langfuse` symlink into `langfuse-skills`) | No (`~/.claude` is not a git repo) |
| `~/.agents/skills` | Codex mirror of the same set; `sf-hierarchical-orchestration` and `sf-jev-dispatcher` are canonical here and symlinked into `~/.claude` | No |
| `~/.claude/skills/synced` (and the `~/.agents` mirror) | 10 Anthropic account skills: docs, docx, pdf, pptx, xlsx, morning, import-memory, skill-creator, system-engineering-tutor, eval-ladder | Managed by the account sync |
| `~/.codex/skills/.system` | imagegen, openai-docs, plugin-creator, review-agent, skill-creator, skill-installer | No |
| 26 enabled plugins | About 250 skill files in the plugin cache (an upper bound: older cached versions are counted) | Managed by plugins |
| `~/Projects/software-factory/skills` | 5 skills: sf-adr-debate, sf-door-guard, sf-interface-auditor, sf-io-analyzer (installed copies identical) and sf-spec-testing (retired in place, never installed) | Yes |
| `~/Projects/openemr-base-clean` | 1 skill `eval-gate-triage` (in `.claude/skills` and `.agents/skills`, the two copies differ), 5 subagent definitions in `.claude/agents` (eval-author, ops-operator, docs-writer, implementation-reviewer, implementer), 3 Codex `.toml` copies | Yes (repo) |
| `~/Projects/openemr-dashboard-wt` (worktree) | Same 5 agent definitions, identical to the main checkout | Yes (worktree) |
| `~/Projects/minimum-viable-factory/.claude/skills` | 6 reference skills (spec-writing, architecture, coding, code-review, test-writing, deploy-checklist) | Yes (third-party clone) |
| `~/Projects/*-workspace/skill-iteration-1/SKILL.md` | 4 iteration snapshots (axiomatic-spec, brownfield-explorer, deep-research, eval-designer, prd-designer workspaces; two snapshots differ from what is installed: axiomatic-spec and eval-designer) | Not installed |

### 1.2 Personal skills and evidence of use

Usage counts are Skill-tool invocations found in 2,685 Claude Code transcripts as of 2026-09-23. **Codex usage cannot be measured this way** (every Codex session lists all skills in its prompt, so path counts only reflect the listing). The newest skills (written Sep 22-23) may simply be too new to appear.

| Skill | Lines | Invocations | Notes |
|---|---|---|---|
| langfuse | 152 | 5 | Bundle of 15 files under `langfuse-skills` |
| grounded-research | 92 | 4 | |
| prd-designer | 66 | 4 | |
| eval-gate-triage | 84 | 3 | Project-local, openemr-base-clean |
| deep-research | 103 | 2 | |
| session-handoff | 129 | 2 | |
| use-railway | 377 | 2 | 26 files |
| axiomatic-spec | 89 | 1 | |
| brownfield-explorer | 92 | 1 | |
| eval-designer | 206 | 1 | |
| away-mode | 51 | 1 | Claude and Codex copies differ by 3 files |
| sf-hierarchical-orchestration | 113 | 1 | Used 2026-09-23 |
| sf-adr-debate | 94 | 0 | |
| sf-door-guard | 54 | 0 | |
| sf-interface-auditor | 74 | 0 | |
| sf-io-analyzer | 67 | 0 | |
| sf-implementation-review | 33 | 0 | Claude and Codex descriptions differ in substance |
| sf-jev-dispatcher | 221 | 0 | See section 3 |
| sf-parallel-integration | 184 (Claude) / 170 (Codex) | 0 | Claude copy is newer |
| plan-adherence | 70 | 0 | |

Plugins: only `skill-creator` and five `superpowers` skills (subagent-driven-development, writing-plans, test-driven-development, finishing-a-development-branch, brainstorming) appear in the logs. No invocations from stripe, supabase, figma, firecrawl, redis-development, slack, gitlab, rust-analyzer-lsp, atomic-agents or sourcegraph. This session, the `github` and `sourcegraph` plugin MCP servers failed to connect. Bundled or built-in skills also seen in use: claude-api, dataviz, schedule, loop, artifact-design, artifact-diagramming. Synced Anthropic skills showed no invocations.

### 1.3 Drift and source-of-truth findings
- 9 of 16 skill pairs in `~/.claude/skills` and `~/.agents/skills` differ. Seven differ only by one file (description wording, "Claude" versus "Codex"). `sf-parallel-integration` is 184 versus 170 lines. `sf-implementation-review` has genuinely different descriptions. `away-mode` differs in 3 files.
- Eight `sf-*` skills exist only in the home directories and are not in the software-factory repo: sf-hierarchical-orchestration, sf-jev-dispatcher, sf-parallel-integration, sf-implementation-review, and the personal skills axiomatic-spec, brownfield-explorer, eval-designer, prd-designer are likewise home-only. The repo's `skills/` holds only the original four plus the retired one. `PROMOTIONS.md` is the ledger that describes them.
- `eval-gate-triage` `.claude` and `.agents` copies differ.

### 1.4 Overlaps found
- **Eval design:** `eval-designer` (personal) and `eval-ladder` (Anthropic-synced) describe the same method: cheapest check per criterion, fast golden set versus larger diagnostic set.
- **Orchestration cluster (about 520 lines):** sf-hierarchical-orchestration, sf-jev-dispatcher, sf-parallel-integration.
- **Post-run review:** sf-implementation-review and eval-gate-triage.
- **One-way doors:** sf-adr-debate (debate and ADR) and sf-door-guard (pre-flight check).
- **Code-quality auditors:** sf-interface-auditor and sf-io-analyzer, unused, alongside six-plus plugin review surfaces (code-review, pr-review-toolkit, feature-dev, code-simplifier, claude-security, superpowers requesting-code-review). `sf-implementation-review` already delegates to pr-review-toolkit and feature-dev reviewers.
- **Spec pipeline:** prd-designer → axiomatic-spec → brownfield-explorer, each used once to four times; the order is by design (PRD upstream of axioms).

### 1.5 Candidates (not decisions)
- **Retire or archive:** sf-spec-testing (already retired in place); the four iteration snapshots; the never-used synced skills (docx, pdf, pptx, xlsx, import-memory, system-engineering-tutor).
- **Merge:** eval-ladder into eval-designer; the three orchestration skills into one; sf-adr-debate with sf-door-guard.
- **Decide on the unused auditors:** keep or drop sf-interface-auditor and sf-io-analyzer.
- **Disable unused plugins:** every subagent inherits the full skill listing as baseline cost.
- **Fix source of truth:** bring the eight home-only skills under version control; pick one of `~/.claude` or `~/.agents` as canonical; reconcile the 9 drifted pairs.

## 2. Minimum Viable Factory (MVF) versus our skills

| MVF skill | Closest match here |
|---|---|
| spec-writing | prd-designer, with axiomatic-spec downstream |
| architecture | sf-adr-debate and brownfield-explorer |
| coding | The `implementer` subagent (an agent, not a skill) |
| code-review | sf-implementation-review |
| test-writing | eval-designer (evals rather than application unit tests) |
| deploy-checklist | use-railway covers operations; **nothing covers post-deploy verification** |

- **The one real gap:** a deploy-verification checklist. The physician-read check after redeploying the `openemr` service currently lives only in the pinned memory note.
- MVF's skills each dictate an **exact output shape** that the next step parses; ours mostly return prose. This is the pattern most worth copying into skills.
- MVF's context assembly is memory file plus one skill, with no retrieval. The ETH Zurich study found context files (AGENTS.md style) do not generally improve success and add over 20% cost, so keep skills lean and write only what agents cannot infer.
- Our manifesto argues against the PM to Dev to Reviewer to QA pipeline that MVF implements; any adoption needs an ADR that states the position.
- Code-read observations on MVF (not run): "Blocked" is not a trigger state so a Linear rejection never reaches a gate; gates approve on any trigger state; edges after gates are plain so a rejection would still run the next agent; agent failures raise instead of setting `error`.

## 3. Jev findings that touch skills

- **`sf-jev-dispatcher` uses the wrong call.** It posts to `/chat/completions` with a JSON-schema enum. The documented interface is `POST https://openrouter.ai/api/alpha/decisions` with `{model, state, questions}` returning `{model, answers, usage}`. A separate System One surface `POST /api/v1/systemone` is also documented. Questions are `noul`, `choice` or `score`, and option descriptions are written as if briefing a new hire. A live experiment recorded in `~/Projects/gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md` reports the chat-completions call is rejected by the provider; I did not re-run it.
- **Existing OpenRouter key works.** The key name `OPENROUTER_API_KEY` is in `openemr-base-clean/ai-sidecar/.env` (value not read). It was not set in the interactive shell, so the factory must load it itself.
- **Model ID:** use a pinned `typesafe/jev-1.13`, not `~typesafe/jev-latest`, so calibration does not shift.
- **Evidence status:** cheaper and faster is supported (OpenRouter's own benchmark, vendor-adjacent: 194 ms and $0.025 per 1,000 tickets versus 1,957 ms and $2.88 for Claude Opus; $0.042 per million input tokens). **Better at finding bugs is not supported**: on support triage and prompt-injection tests Jev matched the LLMs, and Langfuse's 91.5% is agreement with Claude verdicts, not correctness. An independent review says TypeSafe's benchmarks lack ground truth. No code-review or bug-detection accuracy was found. Use Jev to route work about code, not to find defects.
- **Design rules to encode in the skill:** deterministic rules first; add an explicit "unknown" option to every question; thresholds from your own labeled data in three bands (act, flag, human); shadow mode before enforcement; store state and probabilities for audit; keep the taxonomy and the category-to-action policy in one versioned file, not in skill prose; state is text only, 32,000 tokens (a 64K figure appears in some docs, unreconciled), untrusted, and leaves the machine.
- **Division of labor:** Jev returns probabilities; the harness owns the questions, thresholds and routing.

## 4. Research findings worth keeping in mind

- **"Karpathy loop" is ambiguous.** The harness lecture uses it for the plain agent loop; the term most often means Karpathy's `autoresearch` (edit one file, fixed-budget experiment, keep or revert).
- **The Claude Code `ralph-loop` plugin differs from the original Ralph loop:** it repeats the prompt inside one session with a Stop hook and does not reset context.
- **Loops that work have an external executable check, an iteration cap and a cost cap**; the main failures are the loop optimising the check and unbounded cost.
- **Memory:** plain files plus search is a strong baseline; public memory benchmarks are not comparable across vendors; unfiltered accumulated notes can hurt coding agents; memory poisoning through ordinary queries is documented.
- **Harness choices:** per-model tuning, enforced verification before finishing, environment bootstrapping and native tool calling are the most credited gains on Terminal-Bench, with no isolated ablations; some leaderboard entries are disputed.
- **Computability:** a fixed model is finite-state; chain-of-thought tokens, a growing window or external memory buy power; verification against a formal spec in a decidable fragment is sound but incomplete.

## 5. Where everything is saved

| What | Path |
|---|---|
| Lecture notes: The Orchestrator, The LLM Harness | `~/Projects/gauntlet/lectures/2026-09-23-*.md` |
| Harness deck PDF | `~/Projects/gauntlet/lectures/slides/llm-harness-jev.pdf` |
| Research reports: harness design, loop types, memory, computability | `~/Projects/gauntlet/research/agent-*.md` |
| MVF vs Unity plus software factory comparison | `~/Projects/gauntlet/W2/2026-09-23-mvf-vs-unity-software-factory-comparison.md` |
| Preliminary integration notes (marked superseded) | `~/Projects/gauntlet/W2/2026-09-23-factory-lectures-integration-notes.md` |
| Interactive MVF flowchart | https://claude.ai/artifact/4jkBGQLpApsre1VRfE9ATJ (private) |
| Austin-ready factory plan (draft) | `~/Projects/software-factory/docs/plans/2026-09-23-austin-ready-software-factory-plan.md`, branch `plan/austin-ready-factory`, pushed, no pull request opened |
| MVF clone | `~/Projects/minimum-viable-factory` |
| Jev routing assessment (another session, not mine) | `~/Projects/gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md` |

## 6. Caveats

- Skill usage counts cover Claude Code only, and only Skill-tool calls.
- Most research figures came from abstracts, search summaries or vendor posts; the individual reports mark which. Verify any figure before quoting it.
- The plugin skill count is an upper bound.
- The plan branch and this file are unmerged; no pull request exists.
