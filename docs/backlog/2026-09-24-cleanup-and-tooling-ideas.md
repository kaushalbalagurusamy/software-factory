# Software factory: cleanup ideas and tooling to revisit

Captured 2026-09-24. These are unscheduled ideas, not decisions. Revisit when planning the next factory iteration.

## Cleanup and consolidation

1. **Stateful documents.** Keep three kinds of living documents as the factory's memory: ticket docs (one per unit of work), research docs, and routing docs (how work is dispatched and why). Each records current state so a fresh session can resume without the conversation.
2. **Consolidate agents into six roles:** Research, Design, Implement, Test, Review, and Audit (see the next section). Originally five; Audit was added the same day for brownfield work. Fold the existing redundant agents into these, and give each role its hooks, skills and tooling allowlist in one place. This also supports the narrow-tool, smallest-adequate-model approach to subagent cost.
3. **Jev routes.** Use Jev's per-option probabilities for task and route dispatch. For the co-pilot supervisor the assessment is in `gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md` (conditional go on a shadow-mode tracer bullet).
4. **Unity.** Continue the compiler and semantic-invariant work described in `ROADMAP.md`.
5. **Encryption or isolation for evals.** Keep eval cases unreadable to implementer agents (encrypted at rest or in an isolated location with only a pass/fail interface) so implementers cannot reward-hack against them.

## Audit agent for brownfield work

Add an **Audit** agent (and skill) for brownfield and legacy codebases: a reverse-first audit that reads the source cover to cover and produces a structured spec and risk catalog *before* any rewrite, so the rewrite designs the problems out instead of porting them. It complements the existing `brownfield-explorer` skill (orientation) and `axiomatic-spec` (contracts): Audit is the deep per-unit reading that feeds them.

Source: the "Reverse-Engineering a Legacy Codebase" lecture (StarHotel VB6 case study). Slide text is imported at `gauntlet/lectures/2026-09-24-reverse-engineering-legacy-codebase-slides.md`; deck at <https://vb6-legacy-slides.netlify.app/>. Pipeline shape: manual recon and AI scrape, then per-form audit, module audit, data audit, repo split (frozen source plus docs), local-LLM deep dive, bug catalog with severity and mitigation, migration-route selection, side quests.

**Form audit (the per-unit skill), as taught.** Cover-to-cover reading that captures structure and risk in one pass. For each form, capture:
- Purpose and lifecycle (load, events, unload).
- Controls and what each one does.
- Permission checks, both explicit and missing.
- Database touches, reads versus writes.
- Globals it reads or writes (for example `gstrSQL`, `gstrUserID`).
- Bugs, dead code and half-implemented features.

Why one markdown file per form (for example `docs/forms/USER-LOGIN-FORM.md`): cross-linking between forms is cheap, every finding cites back to source, and the next person to port it has a chart, not a guess.

Screenshot of the slide: `assets/form-audit-slide.jpg`.

Design notes for the factory: the audit output is a stateful document (fits the ticket, research and routing docs in item 1); each per-unit audit is a natural parallel subagent task with a narrow read-only tool list; findings should carry file and line citations so the Review agent can verify them.

## Tools to evaluate (from office hours)

| Tool | What it is | Why it might matter | Caution |
|---|---|---|---|
| [rtk-ai/rtk](https://github.com/rtk-ai/rtk) (Rust Token Killer) | A Rust CLI proxy that filters and compresses shell command output before an agent reads it; claims 60-90% less output. Installed through shell hooks (`rtk init`). | Token savings on agent shell output, which counts against the usage budget. | Savings are estimated as bytes / 4, not real tokens. Hooks rewrite commands, so trial it in a scratch setup first. Name collides with "Rust Type Kit". |
| [dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) | An agent skill that pushes toward the minimum code that works ("the laziest senior dev"). npm `@dietrichgebert/ponytail`, MIT. | Could cut over-building by implementer agents. Its own benchmark claims about 54% less code. | Numbers are self-reported and unverified. May conflict with the spec-first, eval-gated approach; test against our evals before adopting. |

Both were summarized from DeepWiki (rtk) and the GitHub README (ponytail, not indexed by DeepWiki); neither was cloned.
