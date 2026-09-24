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

**Rest of the audit method (from the same deck; needed to build the skill).**

*Pipeline, one artifact per phase ("don't skip; don't loop"):*

| Phase | Step | Artifact it hands on |
|---|---|---|
| 0 | Manual recon: read the README, run the app, eyeball the file tree (15-30 minutes) | Facts you own before reading any source; names the "center of gravity" of the app to aim at |
| 1 | AI scrape with a web LLM: high-level map, starting from the project manifest | Tree of entry point, forms, modules and dependencies |
| 2 | Form audit (UI and UX layer) | One markdown per form |
| 3 | Module audit (business and data logic) | One markdown per module |
| 4 | Data audit (schema and reports) | Schema and report notes |
| 5 | Repo split: frozen source plus docs | Read-only source beside a docs tree |
| 6 | Local-LLM deep dive with skills and prompts | Per-file long-form analyses |
| 7 | Bug catalog | `BUGS-MITIGATIONS.md`: one row per finding with severity, category and concrete mitigation |
| 8 | Migration route selection | Migration spec: route, stack, phased arcs, slice loop |
| 9 | Side quests | Nice-to-haves and new features |

*Three deliverables:* per-file source readings in long-form prose; the bug catalog (the triage list the rewrite resolves; in the case study about 150 rows across 10 categories, 4 critical); the migration spec (a deliberately better target, not a port).

*Rules of the method:*
- **Understand before changing.** An audit is a read pass; fixes happen in the rewrite. Do not port line for line, because that inherits every bug.
- **Recon before prompting**, otherwise the model summarizes syntax instead of behavior.
- **Read the project manifest first** (in the case study the `.vbp` file): it lists every file, pins dependencies, declares the startup, and carries the version. That scopes the audit and briefs the model at zero cost, and catches deprecated dependencies on day one. Equivalent for other stacks: build files, lockfiles, entry points.
- **Prompt discipline:** give the model one bounded job at a time and name the output. Good: "Start with the manifest; identify the entry point, every form, every module, every dependency; produce a tree, not a critique." Too vague: "Tell me about this codebase." Too eager: "Find all the bugs and rewrite this in modern C#." Map first, opine later.
- **Per-file pass:** (1) read every handler and helper top to bottom, no skimming, until you could narrate the file without reopening it; (2) find smells (bugs, dead code, missing permission checks, hardcoded credentials, mutable globals) and cite each with the function name in backticks and a line number when it matters; (3) lift every smell into the catalog.
- **Writing style:** prose analyses with explicit "Bug:" and "Smell:" call-outs and citations. Example call-outs: a one-click admin login from a clickable label; a password field length cap that disagrees with the schema; credentials left in module globals for the whole session.
- **Route selection:** tally findings by severity, score each route against budget, timeline, team and reporting fidelity, and pick the one whose weaknesses you can live with. The case study evaluated five routes (incremental VB.NET conversion, greenfield C# on .NET 10 with Avalonia, Python, Java, TypeScript) and chose greenfield, because the codebase was small enough that the conversion tool's licence cost more than the time it saved, and designing 150 bugs out is easier than fixing them. Lock the choice to a phased roadmap (14 arcs) and a slice loop of one branch, one slice, one log entry.
- **Take the process, not the repo:** the reference repo `github.com/decagondev/vb6-rework-reverse-forward` holds worked outputs (`docs/forms/USER-LOGIN-FORM.md`, `docs/BUGS-MITIGATIONS.md`, `docs/MIGRATION-DOTNET.md`); use them as exemplars when writing the skill.

Full slide text is in the imported lecture file; this section is the distilled version.

## Tools to evaluate (from office hours)

| Tool | What it is | Why it might matter | Caution |
|---|---|---|---|
| [rtk-ai/rtk](https://github.com/rtk-ai/rtk) (Rust Token Killer) | A Rust CLI proxy that filters and compresses shell command output before an agent reads it; claims 60-90% less output. Installed through shell hooks (`rtk init`). | Token savings on agent shell output, which counts against the usage budget. | Savings are estimated as bytes / 4, not real tokens. Hooks rewrite commands, so trial it in a scratch setup first. Name collides with "Rust Type Kit". |
| [dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) | An agent skill that pushes toward the minimum code that works ("the laziest senior dev"). npm `@dietrichgebert/ponytail`, MIT. | Could cut over-building by implementer agents. Its own benchmark claims about 54% less code. | Numbers are self-reported and unverified. May conflict with the spec-first, eval-gated approach; test against our evals before adopting. |

Both were summarized from DeepWiki (rtk) and the GitHub README (ponytail, not indexed by DeepWiki); neither was cloned.
