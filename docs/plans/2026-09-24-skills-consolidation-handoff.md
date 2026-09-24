# Skills consolidation: handoff and prompts

> **Written:** 2026-09-24, at the end of a long research and planning session.
> **Purpose:** let a fresh session start the skills overhaul without missing anything from this session or from the other sessions that worked on the factory this week.
> **How to trust this file:** claims cite real files. If a claim here conflicts with the file it cites, the file wins. Nothing described here has been executed; no skill was changed.
> **Supersedes:** nothing. Companion to `2026-09-24-skills-overhaul-findings.md` (the detailed inventory) and `2026-09-23-austin-ready-software-factory-plan.md` (the larger plan).

## 1. The one thing that matters most

The overhaul touches skills that mostly live **outside version control** (`~/.claude/skills`, `~/.agents/skills`), in **two drifting copies**, while **other sessions have already recorded overlapping ideas** (a six-role agent consolidation, stateful documents, a new Audit agent, Jev routing) in their own files. Back up first, reconcile with those ideas instead of duplicating them, and do not touch files that belong to the running Co-Pilot sprint.

## 2. Read first, in this order

| # | File | Why |
|---|---|---|
| 1 | `~/Projects/software-factory/docs/plans/2026-09-24-skills-overhaul-findings.md` | Full skill inventory, usage counts, drift, overlaps, candidates, Jev correction, where everything is saved |
| 2 | `~/Projects/software-factory/docs/backlog/2026-09-24-cleanup-and-tooling-ideas.md` (and `docs/backlog/assets/form-audit-slide.jpg`) | Another session's ideas: three kinds of living documents, six agent roles (Research, Design, Implement, Test, Review, Audit), Jev routes, Unity, eval isolation, the Audit agent and form-audit skill, tools to evaluate |
| 3 | `~/Projects/software-factory/docs/plans/2026-09-23-austin-ready-software-factory-plan.md` | The larger plan; sections 5.3, 5.4 and 6 bear directly on skills |
| 4 | `~/Projects/software-factory/PROMOTIONS.md` | The ledger of skills and their rungs; must be updated after any change |
| 5 | `~/Projects/gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md` | Live Jev experiment; confirms the correct API surface |
| 6 | `~/Projects/gauntlet/lectures/2026-09-24-reverse-engineering-legacy-codebase-slides.md` | Source of the Audit agent and form-audit skill idea (slides file: `lectures/slides/vb6-legacy-slides.html`) |
| 7 | `~/Projects/gauntlet/W2/2026-09-22-w2-agent-hierarchy-and-review-gates.md` | The current operating hierarchy that `sf-hierarchical-orchestration` encodes |
| 8 | `~/Projects/gauntlet/W2/research/2026-09-22-jev-as-software-factory-router.md`, `2026-09-22-typesafe-jev-openrouter-integration.md`, `2026-09-21-typesafe-structured-extraction.md` | Earlier Jev design notes from a planning agent; the 2026-09-22 router spec uses `jev-latest` and the chat-completions surface that the 2026-09-24 assessment says is rejected. Reconcile, do not copy |
| 9 | `~/Projects/gauntlet/research/agent-harness-design.md`, `agent-loop-types.md`, `agent-memory.md`, `agent-computability.md` | Evidence base for loops, memory and harness choices |
| 10 | `~/Projects/gauntlet/lectures/2026-09-23-the-orchestrator-software-factories.md`, `2026-09-23-the-llm-harness.md`, `~/Projects/gauntlet/W2/2026-09-23-mvf-vs-unity-software-factory-comparison.md` | Minimum viable factory lessons and comparison |

Optional context: the interactive MVF flowchart at https://claude.ai/artifact/4jkBGQLpApsre1VRfE9ATJ (private).

## 3. Who wrote what

| Source | Author | What it holds | Status |
|---|---|---|---|
| Research reports, lecture notes, comparison, flowchart, plan, findings | Claude session ending 2026-09-24 | See table above and the findings file | Committed; unmerged branch |
| `docs/backlog/2026-09-24-cleanup-and-tooling-ideas.md` and its asset | Another Claude session (three commits on `plan/austin-ready-factory`) | Backlog of unscheduled ideas, explicitly "not decisions" | Committed on the same branch |
| Jev router spec, Jev OpenRouter integration, structured-extraction notes | Planning agent "Agy" (2026-09-21 to 2026-09-22) | Earlier Jev design and cost heuristics | In the gauntlet repo; partly superseded |
| Jev routing assessment | Another session (2026-09-24) | Live experiment: about 240 ms median, about $0.00002 per decision; chat-completions call rejected | Current; conditional go for shadow mode |
| Co-Pilot final sprint handoff, overnight log, gap audit, dashboard plans | Other sessions | The live Co-Pilot final submission work | **In progress. Not part of the overhaul. Do not edit.** |
| Product repo agents and `eval-gate-triage` | `openemr-base-clean` | Project-local subagent definitions and skill | Committed in that repo |

## 4. State of the repositories

- `~/Projects/software-factory`: on branch `plan/austin-ready-factory`, pushed. Contains the Austin plan, the findings file, this file, and the other session's three backlog commits. **No pull request is open. Nothing is merged to `main`.**
- `~/Projects/gauntlet`: has many untracked and modified files from several sessions (for example `W2/README.md` modified, `discussion/`, `codex-*.md`, `W1/*`). Never run `git add -A` there. Other sessions are committing to it right now.
- `~/.claude/skills` and `~/.agents/skills`: not git repositories. Skills there have no history.
- `~/Projects/minimum-viable-factory`: a clone of a third-party repo, read-only reference.

## 5. Decisions

**Made** (by the owner, this session):
- Skills overhaul happens in a later, separate session, aimed at streamlining. Nothing to be executed before then.
- The stashed information in the notes repo, including the newly imported lecture, is not to be written to; findings go in separate documents.
- The plan and findings are drafts for review.

**Open** (nobody has decided; do not resolve silently):
1. Which skills to keep, merge or retire (candidates are in the findings file, section 1.5).
2. Whether the six-role agent consolidation from the backlog replaces or sits above the skills.
3. Which of `~/.claude/skills` or `~/.agents/skills` is canonical, and whether a git repository holds the source of truth.
4. Whether to add the Audit agent and form-audit skill now or later.
5. Whether to trial the two tools listed in the backlog (rtk, ponytail); both summaries are unverified.
6. Tracker choice, runtime choice and data policy (Austin plan, section 6).

## 6. Things easy to miss (checklist)

- Eight skills exist only in the home directories: sf-hierarchical-orchestration, sf-jev-dispatcher, sf-parallel-integration, sf-implementation-review, axiomatic-spec, brownfield-explorer, eval-designer, prd-designer. Copy them somewhere versioned **before** changing anything.
- Nine of sixteen skill pairs differ between the Claude and Codex copies; one is a real content difference (`sf-implementation-review` descriptions), one is a length difference (`sf-parallel-integration`, Claude copy newer).
- `eval-gate-triage` has `.claude` and `.agents` copies in `openemr-base-clean` that also differ.
- `sf-jev-dispatcher` calls `/chat/completions` with a JSON-schema enum; use `POST https://openrouter.ai/api/alpha/decisions` with `{model, state, questions}`, pin `typesafe/jev-1.13`, add "unknown" options, and keep the taxonomy and routing policy in one versioned file. Jev has not been proven at bug finding; use it to route, not to detect defects.
- `eval-designer` and the synced `eval-ladder` overlap. `sf-spec-testing` is already retired in place.
- The MVF's real gap for us is a deploy-verification checklist (the `openemr` service redeploy hazard and physician read check live only in the pinned memory note).
- The worktree `~/Projects/openemr-dashboard-wt` duplicates the five product-repo agents.
- `PROMOTIONS.md` lists skills and rungs; update it after each change.
- Skill usage counts cover Claude Code only. Codex usage cannot be measured from its transcripts.
- The plan warns against work that displaces the Co-Pilot deliverable. Its final submission is Sun Sep 27, 12:00 PM CT per the program tracker; confirm on the portal.
- Every subagent inherits the full skill listing, so trimming unused plugins reduces per-prompt cost. The `github` and `sourcegraph` plugin MCP servers failed to connect this session.

## 7. Suggested working method (a proposal, not a decision)

1. **Reconcile, read-only.** Read section 2. Compare the backlog's six roles with the current skill set.
2. **Write a consolidation proposal** as a new document: target skill set, old-to-new mapping, keep/merge/retire per skill with the evidence, effects on the Codex mirror, and how each merged skill's triggering will be tested. Stop for owner approval.
3. **Back up.** Snapshot both skill directories to a versioned location under `~/Projects` (not iCloud folders) before any change.
4. **Execute in small steps**, one logical change per commit, on a new branch, staging by path.
5. **Verify.** Confirm skills load and trigger (use `skill-creator` and `eval-designer` tooling), sync the Codex mirror if that is the decision, then update `PROMOTIONS.md`.

## 8. Quick verification before trusting this file

```bash
cd ~/Projects/software-factory && git branch --show-current && git log --oneline -6
ls docs/plans docs/backlog
ls ~/.claude/skills ~/.agents/skills
ls ~/Projects/gauntlet/research ~/Projects/gauntlet/W2/research
git -C ~/Projects/gauntlet status --short | head
```

Expected: branch `plan/austin-ready-factory`; the plan, findings and this file under `docs/plans`; the backlog note under `docs/backlog`; 19 personal skills plus the synced folder in each skill directory; the four `agent-*.md` reports in `gauntlet/research`. If anything differs, another session has moved on; re-read before acting.

## 9. Prompts to paste

### 9.1 Pickup prompt (start the new session with this)

```text
We are starting the skills overhaul for the software factory. Before doing anything else, read this handoff document in full:
~/Projects/software-factory/docs/plans/2026-09-24-skills-consolidation-handoff.md

It maps every finding and note from the previous Claude session and from other sessions (Jev research, the backlog of cleanup ideas with the six-role agent idea and the Audit agent, the reverse-engineering lecture, the Austin plan), lists what is decided versus open, and gives verification commands. Then read every file in its "Read first" table.

Until I say otherwise: do not edit, move, delete, rename or install anything; do not write to any file in ~/Projects/gauntlet (other sessions have uncommitted work there, including the newly imported lecture and stashed notes); do not touch the Co-Pilot final-sprint files. Run the verification commands in section 8 and tell me if anything has drifted.

When you have read everything, summarize in under 300 words what you understood, list anything in the handoff you could not verify, and ask me which thread to pick up first.
```

### 9.2 Handoff prompt (paste after the pickup summary, once you approve the direction)

```text
Mission: consolidate and streamline the software factory's skills into a minimal set that fits the Austin plan, without losing anything from the earlier findings or from other sessions.

Ground rules:
1. Work in ~/Projects/software-factory on a NEW branch named skills-overhaul (branch from the current plan/austin-ready-factory so the plan, findings and backlog are included). One logical change per commit, staged by explicit path, never git add -A. Push is fine; do not open or merge a pull request.
2. Do not write to ~/Projects/gauntlet or to any file another session owns (the Co-Pilot final-sprint files, the backlog note, the Jev assessments). If something there needs correcting, list it for me instead.
3. Back up first: before changing any skill, snapshot ~/.claude/skills and ~/.agents/skills into a versioned location under ~/Projects (not ~/Documents or ~/Desktop), and confirm the copy is complete.
4. Treat the findings file as the baseline inventory and the backlog note as a competing set of ideas: reconcile them (in particular the six roles Research, Design, Implement, Test, Review, Audit versus the current skills) and record the reconciliation instead of choosing silently.
5. Step 1 deliverable only: a consolidation proposal at docs/plans/2026-09-24-skills-consolidation-proposal.md with, for every skill in the inventory (personal, synced, plugin, product-repo, worktree copies): keep, merge, retire or decide-later; the evidence; the effect on the Claude and Codex copies; how triggering will be tested after merging; and the risks. Include the Jev skill rewrite against POST /api/alpha/decisions with a pinned model version, an "unknown" option per question, and the taxonomy and routing policy in one versioned file. Include what to do about a deploy-verification checklist, the Audit agent and form-audit skill, and the eval-designer versus eval-ladder overlap. Then STOP and wait for my approval.
6. After approval, execute in small steps, verify that each changed skill still loads and triggers (use the skill-creator and eval-designer tooling), keep the Codex mirror consistent with whatever canonical location I choose, and update PROMOTIONS.md at the end.
7. Keep secrets out of every file. Mark unverified claims as unverified. Do not displace the Co-Pilot deliverable; if the overhaul would compete with it for time or usage, say so first.

Open decisions that are mine, not yours: which skills to keep or retire, the canonical skill location, whether the six-role structure replaces skills, whether to build the Audit agent now, and whether to trial the tools in the backlog. Ask me before deciding any of them.
```
