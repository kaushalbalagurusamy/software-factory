# Skills consolidation: proposal (step 1)

> **Status:** PROPOSAL, waiting for owner approval. No skill has been changed, moved, installed or retired. The only action taken so far is the backup described in section 1.
> **Date:** 2026-09-24 · **Branch:** `skills-overhaul` (from `plan/austin-ready-factory`)
> **Baseline:** `2026-09-24-skills-overhaul-findings.md` (inventory) reconciled with `docs/backlog/2026-09-24-cleanup-and-tooling-ideas.md` (competing ideas). Sources are cited per claim. Claims I did not check are marked **[unverified]**.
> **Owner decisions are not made here.** Every verdict below is a recommendation. Section 10 lists the decisions that are yours.

## 0. Timing and usage (read first)

- The Co-Pilot Week 2 final is **Sun Sep 27, 12:00 PM CT** (`gauntlet/W1/PROGRAM_TRACKER.md`, line 33); the remote phase ends Fri Oct 2. Today is Thu Sep 24.
- Weekly usage was at 37% at 13:30 EDT today, with the 7-day window resetting around Sun Sep 27 morning (`~/.claude/state/rate_limits.json`).
- **The overhaul competes with the Co-Pilot for time and usage.** Executing it needs about 10 to 16 trigger-eval runs (each runs `claude -p` many times) plus the edits. Recommendation: approve the proposal now, but run only the zero-risk steps (E1 and E2 in section 9) before Sunday noon, and run the rest after the Week 2 submission. Steps that write to `openemr-base-clean` wait until the Co-Pilot sessions and Codex are idle (see the shared-checkout rule).

## 1. Backup (done)

- `~/.claude/skills` and `~/.agents/skills` were copied with `rsync -a` to `~/Projects/skills-snapshots/2026-09-24/{claude-skills,agents-skills}` and committed to a new local git repository (commit `dff29d3`, 682 files, no remote).
- Completeness check: `diff -r --no-dereference` against both live directories returned no differences; entry counts match (408 and 410).
- Symlinks were kept as links. The two nested `langfuse-skills/.git` directories were renamed `_git-snapshot` inside the copy so the outer repository records their contents.
- A secret-pattern scan of the copy (OpenRouter, Anthropic, GitHub, GitLab, Langfuse and AWS key shapes) found nothing.

## 2. What changed since the findings file

Re-checked today. The findings still hold, with these corrections and additions:

| # | New or corrected finding | Evidence |
|---|---|---|
| F1 | The Codex copies were made by a text substitution of "Claude" with "Codex" that also rewrote paths. `away-mode` in `~/.agents` points at `~/.Codex/skills/away-mode/scripts/`, which does not exist, so the Codex copy of away-mode cannot run its scripts. The Codex `sf-implementation-review` points at `openemr-base-clean/.Codex/agents/implementation-reviewer.md`, which also does not exist (the repo has `.codex/agents/` with only 3 of the 5 agents, and no implementation-reviewer). | `diff` of both pairs; `find` in the repo |
| F2 | The Claude `away-mode` has newer script logic (battery maintenance helpers in `common.sh`, `start.sh`) that the Codex copy lacks. | `diff -rq` |
| F3 | Personal `use-railway` is an older install of the Railway plugin's own skill: 3 files differ from plugin 1.5.2, and both are listed, so two `use-railway` skills compete. | `diff -rq ~/.claude/skills/use-railway …/railway/1.5.2/skills/use-railway` |
| F4 | `eval-designer` already absorbed `eval-ladder`'s content (`reference/check-rungs.md`, `reference/error-analysis.md`, and its own text says so). The overlap is now only a triggering conflict, not a content gap. | `eval-designer/SKILL.md` lines 40 to 46 |
| F5 | `eval-ladder` and `system-engineering-tutor` come from the account-synced `anthropic-skills` plugin (source `plugin` in the sync manifest); the others in `synced/` are `anthropic` or `anthropic-example`. None can be deleted locally, because the sync restores them. | `synced/*/manifest.json` |
| F6 | Two `skill-creator` skills are listed: the plugin `skill-creator:skill-creator` and the synced `anthropic-skills:skill-creator`. | Skill listing; manifest |
| F7 | `sf-hierarchical-orchestration` is largely Co-Pilot specific: its four "milestone bundles" name tracer bullets TB-01 to TB-11 and the R41 redaction rule. It also names "Claude Pro Max 20x", while a saved note says implementation moved to API-billed Claude Code **[unverified which is current]**. | Skill text section 3 |
| F8 | `sf-jev-dispatcher` also uses Jev for "weakened assertions detected" and door-risk detection, which are defect-detection uses the findings say Jev has not been shown to do well. | Skill sections 4 and 5; findings section 3 |
| F9 | `PROMOTIONS.md` has no rows for sf-hierarchical-orchestration, sf-jev-dispatcher, sf-parallel-integration, sf-implementation-review, plan-adherence, session-handoff, langfuse or eval-gate-triage. | `PROMOTIONS.md` |
| F10 | No config under `~/.codex` names `~/.agents/skills` as a search path. Whether Codex actually loads skills from there is **[unverified]**; the handoff and findings assume it. Codex's `config.toml` does enable most of the same Claude plugins. | Inventory subagent read of `~/.codex` |
| F11 | Product repo: `eval-gate-triage`'s two copies differ only in "Claude" versus "Codex" wording. The worktree `openemr-dashboard-wt` (branch `hosted-dashboard`) has byte-identical agent files. | `diff` |
| F12 | Of the six `*-workspace` iteration snapshots, only `axiomatic-spec` and `eval-designer` differ from what is installed; `grounded-research-workspace` has no snapshot. They are not installed, so they cost nothing at trigger time, and `PROMOTIONS.md` cites the workspaces as eval history. | Inventory subagent |

## 3. Reconciliation: six roles versus the current skills

The backlog proposes six agent roles: Research, Design, Implement, Test, Review, Audit, each with "its hooks, skills and tooling allowlist in one place". The findings file inventories skills. These are not competing answers to one question: **a role is who runs (model, tools, permissions); a skill is how a step is done (procedure, output shape).** The product repo already works this way: five agent definitions in `openemr-base-clean/.claude/agents` load skills.

**Mapping (recommended; the decision is yours):**

| Role (backlog) | Existing agent definition (product repo) | Skills the role would load | Austin plan stage |
|---|---|---|---|
| Research | none | grounded-research, deep-research, brownfield-explorer (orientation is read-only research) | Orient |
| Design | none | prd-designer, axiomatic-spec, sf-one-way-door (merged, section 5.3) | Intake, Spec, Door check, Architecture |
| Implement | `implementer` (opus) | superpowers TDD; blind to eval files | Implement |
| Test | `eval-author` (opus) | eval-designer; eval-gate-triage (project-local) | Evals first, Triage |
| Review | `implementation-reviewer` (opus) | sf-implementation-review (with the auditor checklists folded in) | Review |
| Audit | none | legacy-audit (new, section 7) | Orient, for legacy code |

**What the six roles do not cover** (to be decided, not silently dropped):

1. **Orchestration.** The orchestrator is the conductor, not a role: sf-orchestration (merged, section 5.2), the Jev routing policy, plan-adherence.
2. **Operations and deploy.** The `ops-operator` agent, use-railway, away-mode and the missing deploy-verification step have no home among the six. Options: add a seventh role "Operate", or keep ops as an orchestrator-owned utility. Recommendation: add **Operate**, because the Austin plan has a Deploy stage with its own gate (G4) and ops needs a distinct, tighter tool allowlist.
3. **Docs.** The `docs-writer` agent has no role. Recommendation: treat it as a narrow utility agent, not a role.
4. **Session continuity.** session-handoff is used by every role; keep it as a shared skill outside the roles.

**Recommended position:** the roles sit **above** the skills and replace nothing yet. Each role becomes one agent definition that names its skills, tools and model. Building those role definitions is a later step (it belongs with Austin milestone M1 or M2), not part of this overhaul. This overhaul only makes the skill set small and clean enough to assign to roles.

A naming hazard: an "Audit" role would collide with the existing `sf audit` CLI command (governance checks in `factory/governance.py`). Consider "Legacy audit" or "Reverse" for the role name.

## 4. Target skill set (recommended)

From 20 personal entries (19 skills plus the langfuse bundle) down to **13 personal factory and utility skills**, plus one new skill if you approve it:

| # | Skill | Role | Change |
|---|---|---|---|
| 1 | grounded-research | Research | keep |
| 2 | deep-research | Research | keep |
| 3 | brownfield-explorer | Research | keep |
| 4 | prd-designer | Design | keep |
| 5 | axiomatic-spec | Design | keep |
| 6 | sf-one-way-door | Design | **merge** of sf-door-guard and sf-adr-debate |
| 7 | eval-designer | Test | keep; take over eval-ladder's triggers |
| 8 | sf-implementation-review | Review | keep; fold in sf-interface-auditor and sf-io-analyzer as reference checklists |
| 9 | sf-orchestration | Orchestrator | **merge** of sf-hierarchical-orchestration, sf-parallel-integration and the routing part of sf-jev-dispatcher |
| 10 | plan-adherence | Orchestrator | keep (decide-later on evidence) |
| 11 | session-handoff | Shared | keep |
| 12 | away-mode | Operate | keep; fix the Codex copy |
| 13 | langfuse | Operate / Test | keep (third-party bundle, unchanged) |
| new | sf-deploy-verify | Operate | **new**, small (section 6) |
| new | legacy-audit | Audit | **new, only if you choose to build it now** (section 7) |

Retired from the personal set: sf-door-guard, sf-adr-debate, sf-interface-auditor, sf-io-analyzer, sf-hierarchical-orchestration, sf-parallel-integration, sf-jev-dispatcher (all merged, content preserved), and the personal copy of use-railway on the Claude side (the plugin provides it).

## 5. Per-skill verdicts

Legend for the trigger test column: **T-full** is a 20 to 32 query trigger eval with near misses, run through skill-creator's `scripts/run_eval.py` against the candidate description and against the pre-change description as baseline (method in `eval-designer/reference/trigger-and-activation-evals.md`). **T-smoke** is 6 queries (4 should trigger, 2 near misses) and a load check with `quick_validate.py`. **T-none** means no change to triggering, so only a load check.

### 5.1 Personal skills (`~/.claude/skills`, mirrored in `~/.agents/skills`)

| Skill | Verdict | Evidence | Claude and Codex copies | Trigger test | Risks |
|---|---|---|---|---|---|
| grounded-research | Keep | 4 invocations; distinct from deep-research by scope | Differ in 1 file (wording); regenerate the Codex copy from one neutral source | T-none | none |
| deep-research | Keep | 2 invocations | As above | T-none | none |
| brownfield-explorer | Keep | 1 invocation; Austin plan's Orient stage depends on it; axiomatic-spec delegates to it | As above (`CLAUDE.md` versus `AGENTS.md` wording) | T-smoke, adding legacy-audit near misses if that skill is built | Overlap with legacy-audit; resolved by scope (orient versus exhaustive read) |
| prd-designer | Keep | 4 invocations; Intake stage | Identical | T-none | none |
| axiomatic-spec | Keep | 1 invocation; Spec stage | Differ in 1 file (wording) | T-none | Workspace snapshot differs from installed; installed wins |
| eval-designer | Keep, absorb eval-ladder's trigger phrases | 1 invocation; already contains eval-ladder's content (F4) | Differ in 1 file (wording) | **T-full**, with eval-ladder's own description phrases as positives | Both keep firing while eval-ladder stays synced (section 8) |
| sf-adr-debate | **Merge** into sf-one-way-door | 0 invocations; the Austin plan needs it as the G2 architecture step | Identical; also in repo `skills/` | T-full for the merged skill | Merged description gets too broad and fires on ordinary design talk; use near misses such as "which HTTP client should I use" |
| sf-door-guard | **Merge** into sf-one-way-door | 0 invocations; it is the pre-flight half of the same decision | Identical; also in repo `skills/` | (with above) | Losing the fast pre-flight path if the merged skill always starts a debate; keep door check first, debate only if the door is one-way |
| sf-interface-auditor | **Retire as a skill**, keep its content as `sf-implementation-review/reference/interface-checklist.md` | 0 invocations; 6+ plugin review surfaces overlap | Identical; repo copy moves to `skills/_archive/` | T-smoke on sf-implementation-review (no regression) | Content loses its own trigger; low, since it never fired |
| sf-io-analyzer | **Retire as a skill**, keep as `reference/io-checklist.md` in the same skill | 0 invocations; same overlap | As above | (with above) | As above |
| sf-implementation-review | Keep; pick one description; fold in the two checklists | 0 invocations but the Review stage and the product repo's reviewer agent rely on it | **Differ in substance.** Claude: "after any evaluation run". Codex (newer, Sep 16 18:25 versus 14:54): "at a meaningful review boundary, not after each repair". The Codex copy also points at a nonexistent `.Codex/agents` path (F1) | T-full (the two descriptions are the candidate and the baseline) | Choosing the narrower trigger may under-fire; that is what the eval measures |
| sf-hierarchical-orchestration | **Merge** into sf-orchestration; move the Co-Pilot milestone bundles into a clearly labelled example section or the product repo docs | 1 invocation; generic hierarchy plus Co-Pilot specifics (F7) | Canonical in `~/.agents`, symlinked into `~/.claude` | T-full for the merged skill | The Co-Pilot sprint may still read it this week; do not change it before Sunday |
| sf-parallel-integration | **Merge** into sf-orchestration as its parallel-dispatch section | 0 invocations; Claude copy has 2 extra hazard notes (scratch-clone `${S:?}` and ops channel rule) | Claude copy newer; take it | (with above) | Losing the hard-won hazard notes; merge from the Claude copy verbatim |
| sf-jev-dispatcher | **Rewrite and merge** (section 5.4) | 0 invocations; wrong endpoint, floating alias, defect-detection uses (F8) | Canonical in `~/.agents`, symlinked | T-smoke on sf-orchestration's routing phrases | Anyone following the current text makes a call that returns HTTP 400 |
| plan-adherence | Keep (decide-later) | 0 invocations, but encodes a practice you use (verbatim spec saving) and nothing else covers it | Identical | T-none | May be dead weight; re-check usage after Austin M1 |
| session-handoff | Keep | 2 invocations; used for today's handoff | Differ in 1 file | T-none | none |
| away-mode | Keep; fix the Codex copy | 1 invocation; Austin plan 5.13 | **Codex copy is broken** (F1) and older (F2) | Load check plus running `status.sh` from each host | Script paths per host; see section 8 |
| use-railway (personal) | **Retire the Claude copy**; keep a Codex copy only if Codex lacks the plugin | 2 invocations; older duplicate of plugin skill (F3) | Codex `config.toml` enables the railway plugin, so the Codex copy is probably redundant too **[unverified that Codex loads plugin skills]** | T-smoke: "redeploy the sidecar on railway" loads `railway:use-railway` | Plugin version drift is now the plugin's job |
| langfuse (bundle) | Keep, unchanged | 5 invocations; third-party git clone | Both copies are separate clones; differ in 1 file | T-none | none |

### 5.2 Merged skill: sf-orchestration

Contents, in order: the engine division of labour and model allocation (from sf-hierarchical-orchestration, made generic); the Haiku log-digestion pattern; the pre-dispatch DAG, file-ownership manifest, shared-checkout hazards and per-agent integration loop (from sf-parallel-integration, Claude copy); routing decisions (the rewritten Jev section, 5.4); review-packet format for the independent reviewer. The Co-Pilot milestone bundles become an example, clearly labelled. Target length under 250 lines, with detail in `reference/` files so only the core loads by default.

### 5.3 Merged skill: sf-one-way-door

Phase 1, door check (from sf-door-guard): classify the blast radius with deterministic rules first, then design the rollback path. If the door is two-way, stop there. Phase 2, only for one-way doors (from sf-adr-debate): the Socratic debate and the ADR. This matches the Austin plan's order (Door check stage, then Architecture stage with gate G2).

### 5.4 The Jev rewrite

Replace the current skill text with three pieces, so the harness owns questions, thresholds and routing and the skill only explains them:

1. **One versioned policy file** in this repo, for example `factory/routing/jev-policy.yaml`, holding for every decision point (model tier, CI failure triage, milestone readiness): the `state` fields allowed, the questions, every option's criterion text written "as if briefing a new hire", an explicit **`unknown`** option in every `choice` question, the category-to-action mapping, the three bands (act, flag, human) with thresholds, the deterministic rules that run first, and a `policy_version`. Wording changes in this file are behaviour changes and go through review like code (the assessment's section 6.3 makes the same point).
2. **A small client** in `factory/` that calls `POST https://openrouter.ai/api/alpha/decisions` with `{model, state, questions}` and reads `{model, answers, usage}`; model pinned to **`typesafe/jev-1.13`** (never `~typesafe/jev-latest`); key read from `OPENROUTER_API_KEY` in the environment; a transport timeout of about 800 ms and no retry; any fault falls back to the deterministic rule. It logs state digest, probabilities, policy version and outcome for calibration. Tests use recorded responses only; no live calls in tests.
3. **Skill prose** (a section of sf-orchestration): when to ask, that deterministic rules run first, that Jev routes work and does not detect defects, that it runs in shadow mode until our own labelled data sets the thresholds, and that state is untrusted text that leaves the machine (redact first; 32,000-token documented limit, a 64K figure elsewhere is unreconciled).

Dropped from the current skill: the one-way-door tripwire and "weakened assertions detected" questions (defect detection, F8; the door check belongs to sf-one-way-door's deterministic rules), and the hard-coded model tiers inside enum names (tiers belong in the policy file so a model upgrade is a data change).

Sequencing: the assessment recommends the Co-Pilot routing tracer bullet come first and the factory dispatcher follow (assessment section 5). The skill text and policy file can be written now; wiring the client into anything waits for a labelled set of past tasks.

## 6. Deploy-verification checklist

The one real gap against MVF (findings section 2). Recommendation: a small **generic** `sf-deploy-verify` skill plus **per-project checklist files** it reads.

- The skill: pre-deploy gate (review verdict approved, tests green, no secrets in the diff), deploy, then a verify loop against named health checks with a stop condition (green, or roll back), and a fixed output block, borrowing MVF's `## Deploy Log` shape (pre-deploy checks, deploy, post-deploy checks, final `DEPLOYED` or `FAILED`).
- The project checklist for the Co-Pilot, for example `openemr-base-clean/docs/ops/deploy-verification.md`: the `openemr` service image-source hazard, the `railway up` from a clean clone rule, and the physician FHIR read check. These currently live only in a saved memory note.
- **Not written by this overhaul** until the Co-Pilot sprint and Codex are idle, because it is a write to the product repo. Alternatively a Co-Pilot session writes the checklist.

## 7. Audit agent and form-audit skill

Source: the backlog's distilled method from the reverse-engineering lecture. Whether to build it now is your decision. My recommendation: **decide now, build after Sep 27.** Nothing on the Co-Pilot needs it, and Austin partner work (plan criterion S3, brownfield) is where it pays.

If built, keep it to one skill and one agent definition:

- **Skill `legacy-audit`:** the phase pipeline (recon, manifest-first map, per-unit audit, data audit, bug catalog, route selection), with the per-unit template (purpose and lifecycle, controls, permission checks explicit and missing, database reads versus writes, globals, bugs and dead code), the "Bug:" and "Smell:" citation style with file and line, and the `BUGS-MITIGATIONS.md` row shape (severity, category, mitigation). The former sf-interface-auditor and sf-io-analyzer checklists are reusable smell lists here as well.
- **Agent definition:** read-only tools (Read, Glob, Grep, no Write outside `docs/audit/`), one unit per dispatch, run in parallel.
- **Boundary with brownfield-explorer:** explorer is cheap orientation and blast radius for one change; audit is a complete read pass before a rewrite. Their descriptions must name each other as near misses.
- Exemplars: `github.com/decagondev/vb6-rework-reverse-forward` (`docs/forms/USER-LOGIN-FORM.md`, `docs/BUGS-MITIGATIONS.md`) **[not yet read by me]**.

## 8. Eval-designer versus eval-ladder

- Content: already merged (F4). eval-designer has the ladder in `reference/check-rungs.md`.
- Triggering: both descriptions claim "writing evals, golden sets, rubrics, LLM-as-judge, CI gates for an agent". eval-ladder cannot be removed locally (F5).
- Options: (a) turn off the eval-ladder skill in your claude.ai account settings, if the account allows removing one skill from the synced plugin **[unverified whether it can]**; (b) leave it, and add to eval-designer's description that it is the factory's eval skill and supersedes eval-ladder, then measure with T-full which one fires. Recommendation: (a) if possible, otherwise (b). The same question applies to the duplicate synced `skill-creator` (F6): keep the plugin version, which ships the scripts the verification step uses.

### 8.1 Synced account skills (`~/.claude/skills/synced`, `~/.agents/skills/synced`)

| Skill | Verdict | Evidence | Note |
|---|---|---|---|
| docs | Keep | Backs the Claude Docs connector | Account-managed |
| docx, pdf, pptx, xlsx | Keep | 0 invocations, but they are format capabilities, not overlaps | Retiring saves listing tokens only |
| morning | Keep | Your morning brief | Account-managed |
| import-memory | Decide-later (turn off in account) | 0 invocations | Low value, low risk |
| skill-creator (synced) | Decide-later (turn off in account) | Duplicate of the plugin skill (F6) | Keep the plugin one |
| system-engineering-tutor | Decide-later | 0 invocations; may matter for the weekly system design session | Your call |
| eval-ladder | Retire if the account allows; otherwise shadow it | F4, F5 | Section 8 |

The two synced folders differ (the `.agents` copy has a `.staging` folder and 7 files differ). They are written by the sync, so no local action.

### 8.2 Plugins (26 enabled, `~/.claude/settings.json`)

No plugin skills are merged or edited. The question is only which plugins stay enabled, since every subagent inherits the listing. Candidates to disable, all with zero Skill-tool invocations in the findings' transcript count: stripe, supabase, figma, firecrawl, redis-development, slack, gitlab, rust-analyzer-lsp, atomic-agents (95 agent files), sourcegraph (its MCP server fails to connect). Keep: superpowers, skill-creator, code-review, pr-review-toolkit, feature-dev, code-simplifier, claude-security, railway, playwright, github, commit-commands, claude-md-management, ralph-loop, security-guidance, frontend-design, claude-code-setup. Caveats: counts cover Skill-tool calls only, so a plugin used only through its MCP tools (for example gitlab for the Co-Pilot repo, playwright for ops checks) can look unused. **This is your decision**; it is reversible in settings.

### 8.3 Codex system skills (`~/.codex/skills/.system`)

imagegen, openai-docs, plugin-creator, review-agent, skill-creator, skill-installer: managed by Codex; no action.

### 8.4 Product repo and worktree

| Item | Verdict | Note |
|---|---|---|
| `openemr-base-clean` eval-gate-triage | Keep, project-local | Its two copies differ only in host wording (F11). Make one neutral text after Sep 27 |
| 5 agent definitions in `.claude/agents` | Keep | They are the seeds of the Implement, Test and Review roles |
| `.codex/agents` (3 of 5) | Decide-later | implementation-reviewer and ops-operator have no Codex definition |
| `openemr-dashboard-wt` agent copies | No action | Byte-identical; they follow the branch and go away with the worktree |

### 8.5 Other copies

| Item | Verdict | Note |
|---|---|---|
| Repo `skills/sf-spec-testing` | Keep retired; move to `skills/_archive/` | Already retired in place |
| `*-workspace/skill-iteration-*` snapshots | Keep as eval history, not installed | Cited by `PROMOTIONS.md`; zero trigger cost |
| `minimum-viable-factory/.claude/skills` | No action | Third-party reference |

## 9. Execution plan (after approval)

Each step is one commit on `skills-overhaul` unless it only touches home directories, in which case the commit records the new canonical copy in the repo.

| Step | What | Before Sunday? |
|---|---|---|
| E1 | Choose the canonical location (section 10, D2) and create it, importing all personal skills unchanged | yes (no behaviour change) |
| E2 | Fix the broken Codex copies of away-mode and sf-implementation-review paths, only if the canonical choice does not already replace them | yes |
| E3 | Write the Jev policy file and client with recorded-response tests; no wiring | after |
| E4 | Merge sf-door-guard and sf-adr-debate into sf-one-way-door; T-full | after |
| E5 | Merge the orchestration cluster into sf-orchestration, with the Jev section; T-full | after (the Co-Pilot sprint may be reading the current skill) |
| E6 | Fold the two auditors into sf-implementation-review; settle its description; T-full | after |
| E7 | eval-designer description; T-full; account-level change to eval-ladder if you choose | after |
| E8 | Retire the personal use-railway on the Claude side; T-smoke | after |
| E9 | sf-deploy-verify (and legacy-audit if chosen); T-full each | after |
| E10 | Regenerate the Codex mirror from the canonical source; load check on both hosts | after |
| E11 | Update `PROMOTIONS.md` with every row, including the 8 missing ones (F9) | last |

**How "still loads and triggers" is verified.** Load: `quick_validate.py` on each changed skill, and a fresh `claude -p` session that lists the skill. Trigger: skill-creator's `run_eval.py` with a query set per changed skill, candidate versus pre-change baseline, 3 runs per query; pass if recall and precision are each at least 0.9 and no worse than the baseline, and every former skill's own trigger phrases now load the merged skill. The query sets are saved in `docs/evals/triggers/` so they can be re-run. Codex triggering cannot be measured with the same tooling; for Codex the check is a load check and one manual `codex exec` run per merged skill **[method unverified]**.

## 10. Decisions that are yours

| # | Decision | My recommendation |
|---|---|---|
| D1 | Which skills to keep, merge or retire | Section 5 verdicts |
| D2 | Canonical skill location | **This repo's `skills/` as the single source**, installed by a small script that symlinks each skill into `~/.claude/skills` and `~/.agents/skills`; skill text written host-neutral ("the agent", `AGENTS.md or CLAUDE.md`), with host-specific paths resolved at run time (for away-mode, scripts find their own directory). Alternatives: `~/.agents/skills` canonical with symlinks into `~/.claude` (already true for two skills, but not versioned), or two copies kept in sync by a script (keeps today's drift risk) |
| D3 | Whether the six roles replace skills | Roles sit above skills (section 3); add an Operate role; build role definitions later, with Austin M1 or M2 |
| D4 | Whether to build the Audit agent and legacy-audit skill now | Decide now, build after Sep 27 |
| D5 | Whether to trial rtk and ponytail | Not now. Both claims are self-reported; trial each after Sep 27 in a scratch setup against our own evals (rtk rewrites commands through shell hooks; ponytail may pull against spec-first work) |
| D6 | Which plugins to disable | Section 8.2 |
| D7 | eval-ladder and the synced skill-creator: turn off in the account or shadow them | Turn off if the account allows |
| D8 | Timing: which steps run before Sun Sep 27 noon | E1 and E2 only |

## 11. Risks

- **Displacing the Co-Pilot final** (section 0). Mitigation: only E1 and E2 before Sunday.
- **Losing content in a merge.** Mitigation: the snapshot repo; each merge commit states which source sections went where; hazard notes are copied verbatim.
- **Over-broad merged descriptions** firing where they should not. Mitigation: near-miss negatives in every T-full set.
- **Codex behaviour unknown** (F10). Mitigation: verify the search path with one canary skill before relying on the mirror.
- **Symlinks from home into the repo** break if the repo moves or a branch without the skill is checked out. Mitigation: install from `main` only, or from a dedicated worktree, never from a feature branch in a shared checkout.
- **Account-synced skills return** after a local delete. Mitigation: change them only in account settings.
- **Secrets.** The Jev client reads the key by name only; no file in this plan holds a value.

## 12. Items in files I do not own (for you to correct or delegate)

1. `gauntlet/W2/research/2026-09-22-jev-as-software-factory-router.md` and `2026-09-22-typesafe-jev-openrouter-integration.md` still describe the chat-completions call and `jev-latest`. The 2026-09-24 assessment already flags this; the older notes carry no superseded banner.
2. `docs/plans/2026-09-24-skills-overhaul-findings.md` section 1.3 says "Eight `sf-*` skills exist only in the home directories"; it is four `sf-*` skills plus four other personal skills (the handoff states it correctly).
3. Outside any document: `~/.codex/config.toml` stores a GitHub personal access token and a Vercel bearer token in plaintext (reported by name only). Consider moving them to environment variables.
