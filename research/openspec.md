# OpenSpec and "OpenSpec-inspired tracer-bullet PRDs" for the /sf loop

> **Scope:** identify the OpenSpec project, describe its formats, workflow and tooling, and judge fit for /sf tracer-bullet slices.
> **As of:** 2026-10-19. Sources: `gh api`, `gh repo view`, `npm view`, and a shallow clone of `https://github.com/Fission-AI/OpenSpec` at commit `c794978f4f88` (2026-10-17), read only. Nothing from the clone was installed or executed. "Repo:" paths below are relative to that clone.
> **Marking:** VERIFIED = read in the cited source. UNVERIFIED = inferred or not checked.

## 0. Identity

- VERIFIED: the project is **Fission-AI/OpenSpec**, GitHub description "Spec-driven development (SDD) for AI coding assistants." (`gh repo view`). Owner is the org `Fission-AI`. About 72.4k stars.
- VERIFIED: licence MIT (`gh repo view` licenseInfo `mit`; `LICENSE` begins "MIT License / Copyright (c) 2024 OpenSpec Contributors"; `npm view` license MIT).
- VERIFIED: latest release **v1.14.3 "Linked specs, safer globs"**, published 2026-10-17T01:52:12Z. npm `@fission-ai/openspec` latest 1.14.3, modified 2026-10-17. Last push 2026-10-19. Dist-tags: latest 1.14.3, beta 1.6.0-beta.1, next 0.3.0.
- VERIFIED install: `npm install -g @fission-ai/openspec@latest`, or `brew install openspec`; then `openspec init` in the project (repo: `README.md` "Quick Start"). Also pnpm, yarn, bun, Nix (README). `npm view` shows `bin: openspec`, `engines.node >=20.19.0`, and no postinstall script (the `scripts.postinstall` query returned nothing).
- VERIFIED: other "openspec" repos exist but are not this tool: `ForceInjection/OpenSpec-practise` (guide), `jixoai/openspecui` ("Dream for OpenSpec", UI), `JiangWay/openspec-schemas`, `intent-driven-dev/openspec-schemas`, `danielhanold/superspec`, `wenqingyu/ralphy-openspec` (all community add-ons for Fission-AI/OpenSpec), `openspec-cn/openspec` (translation, 41 stars), `blake3dcake/openspectrym` (3D-printer project, unrelated). Seen in `gh search repos openspec`; the add-ons' relationship is from their descriptions only (UNVERIFIED beyond that).
- Confidence in identity: high. The user's phrase "spec-driven development tool for AI coding assistants" matches the repo description verbatim. The earlier-generation OpenSpec (`openspec/AGENTS.md`, `/openspec:proposal`) is the same project, now superseded (see 4).

## 1. Directory layout and artifact formats

VERIFIED (`docs/concepts.md`, "The Big Picture", "Change Structure"):

```
openspec/
  config.yaml            # schema, context, per-artifact rules, operation guidance
  specs/<capability>/spec.md      # source of truth: how the system behaves NOW
  changes/<change-name>/          # one folder per proposed change
    proposal.md  design.md  tasks.md
    .openspec.yaml       # optional metadata: schema, created, skip_specs, retire_capabilities, x-* keys
    specs/<capability>/spec.md    # DELTA specs
  changes/archive/YYYY-MM-DD-<name>/   # completed changes, whole folder preserved
```

- **Spec** (`docs/concepts.md` "Spec Format"): `## Purpose`, `## Requirements`, then `### Requirement: <name>` with an RFC 2119 sentence (SHALL/MUST), then `#### Scenario: <name>` with `- GIVEN / - WHEN / - THEN / - AND` bullets. Quote: "Requirements are the 'what'... Scenarios are the 'when'". Scenario headings must be exactly four `#` ("Using 3 hashtags or bullets will fail silently", `schemas/spec-driven/schema.yaml`).
- **Delta spec** (`docs/concepts.md` "Delta Specs", `docs/writing-specs.md`): sections `## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`, plus `## RENAMED Requirements` (FROM:/TO:, `schema.yaml`) and `## Purpose` for brand-new capabilities. Quote (`writing-specs.md`): "On archive, ADDED gets appended to the main spec, MODIFIED replaces the old version, and REMOVED is dropped from it." MODIFIED must carry the full requirement block; REMOVED must carry **Reason** and **Migration** (`schema.yaml`).
- **Proposal** (`schemas/spec-driven/templates/proposal.md`): `## Why`, `## What Changes`, `## Capabilities` (New / Modified, each naming a spec path), `## Impact`. Validation limits: Why 50 to 1000 chars (`src/core/validation/constants.ts`).
- **Design**: free-form technical approach and decisions (`docs/concepts.md`).
- **tasks.md** (`schemas/spec-driven/templates/tasks.md`): numbered groups `## 1. <Group>` with `- [ ] 1.1 <task>` lines. `docs/concepts.md` guidance: "State how each task is verified (a test, command, or observable result)" and "Land the tests and documentation each group's work calls for inside that group".
- **Task parser** (`src/utils/task-progress.ts` comment): any list item with a one-token checkbox counts; "Only `x`/`X` means done, so every unrecognised marker reads as not-done."
- **Metadata** (`.openspec.yaml`): schema, created, skip_specs, retire_capabilities "plus your own x-* keys" (`docs/concepts.md`). Whether arbitrary `x-*` keys are ever surfaced to agents or preserved by tools: UNVERIFIED.
- **Schemas are customisable** (`docs/customization.md`): a workflow is a DAG of artifacts in `schema.yaml` (`id`, `generates`, `template`, `instruction`, `requires`). Default `spec-driven`: proposal -> specs -> design -> tasks. Custom schemas live in `openspec/schemas/<name>/`.

## 2. Workflow commands and stages

VERIFIED (`README.md`, `docs/commands.md` "Quick Reference"). Default (`core` profile): `/opsx:propose <name>` (creates proposal, specs, design, tasks in one go), `/opsx:explore`, `/opsx:apply`, `/opsx:archive`. Expanded profile (`openspec config profile`, then `openspec update`): `/opsx:new`, `/opsx:continue`, `/opsx:ff`, `/opsx:verify`, `/opsx:sync`, `/opsx:bulk-archive`, `/opsx:onboard`, `/opsx:update`.

- `/opsx:apply`: "Reads `tasks.md` and identifies incomplete tasks... Marks tasks complete with checkboxes `[x]`" (`docs/commands.md`).
- `/opsx:verify`: three dimensions (completeness, correctness, coherence); issues rated CRITICAL, WARNING or SUGGESTION; "Does not block archive, but surfaces issues" (`docs/commands.md`).
- `/opsx:archive`: checks artifact and task completion (warns if incomplete), offers to sync delta specs into `openspec/specs/`, then moves the folder to `changes/archive/YYYY-MM-DD-<name>/`.
- Philosophy (README, `docs/concepts.md`): "fluid not rigid / iterative not waterfall / easy not complex / built for brownfield". Quote: "no phase gates". This matters for /sf, which wants hard gates (see 7).
- CLI (`docs/cli.md`, `docs/agent-contract.md`): `openspec init|update|list|show|validate|status|instructions|new change|archive|schemas|templates|doctor|context|store`. Agent-facing JSON: `openspec status --change X --json` returns per-artifact status `done|skipped|ready|blocked` plus `requires`; `openspec instructions apply --change X --json` returns `{progress:{total,complete,remaining}, tasks:[{id,description,done}], state:"blocked"|"all_done"|"ready"}`.

## 3. How tasks are marked done

VERIFIED: by editing the Markdown checkbox, `- [ ]` -> `- [x]`, in `tasks.md`. Done state lives only in the file; there is no separate ledger (`docs/commands.md`: "Completion state is tracked in `tasks.md` checkboxes"). The agent that implements ticks the box. The tool does not distinguish implemented from verified: one box, one meaning. `openspec list --json` derives `completedTasks`/`totalTasks` and `status` from it; `openspec validate --archived` fails if any archived change has unticked boxes (`docs/cli.md`); `archive` emits `archive_tasks_incomplete` when tasks are open (`src/core/archive.ts:1627`).

## 4. Claude Code integration

VERIFIED (`docs/supported-tools.md` table; `docs/migration-guide.md`):

- `openspec init --tools claude` writes, for Claude Code, **skills** at `.claude/skills/openspec-*/SKILL.md` and **slash commands** at `.claude/commands/opsx/<id>.md` (invoked `/opsx:<id>`). Skill source examples: repo `skills/openspec-apply-change/SKILL.md` has frontmatter `allowed-tools: Bash(openspec:*)` and tells the agent to run `openspec status ... --json` and `openspec instructions ...`.
- Older generation used `openspec/AGENTS.md` plus marker blocks in `CLAUDE.md`/`AGENTS.md`. Quote (`docs/migration-guide.md`): `openspec/AGENTS.md` is "Obsolete workflow trigger"; migration "OpenSpec markers are stripped from `CLAUDE.md`, `AGENTS.md`, etc. (your content stays)". So the current design does not depend on AGENTS.md. The repo's own `AGENTS.md` is contributor guidance, not a generated file (UNVERIFIED in detail; only the head was read).
- Project context and rules are injected into generated prompts from `openspec/config.yaml` (`docs/customization.md`): `context` appears in all artifacts, `rules.<artifact>` only for that artifact, and `operations.apply|archive.guidance` is advisory.
- Supports 30+ tools (README); `openspec init` writes into the project, and `openspec update` regenerates those files.

## 5. Validation tooling

VERIFIED (`docs/cli.md` "openspec validate"; `src/core/validation/*`):

- `openspec validate [item] [--all|--changes|--specs|--archived] [--strict] [--json]`. JSON shape `{items:[{id,type,valid,issues:[{level,path,message,line}]}], summary, version}`; exit 1 on any failing item.
- Checks seen in source: requirement must contain SHALL or MUST (`REQUIREMENT_NO_SHALL`), every requirement needs at least one scenario, requirement text at most 500 chars (warning; fails under `--strict`), Why section length, Purpose at least 50 chars under `--strict`, at most `MAX_DELTAS_PER_CHANGE = 10` deltas, zero-delta changes rejected unless `skip_specs: true`, MODIFIED requirements checked against the main spec they replace, tasks.md checkbox and numbering checks (`task-checkboxes.ts`, `task-numbering.ts`).
- What it does NOT do: check that code satisfies a scenario, that a test exists, or that a task was independently verified. `/opsx:verify` is an LLM judgement, not a gate (see 2).

## 6. Licence and caveats

- Licence MIT (VERIFIED, see 0). Fully compatible with copying the format and ideas.
- Runtime: Node.js >= 20.19.0 (VERIFIED, README, `npm view engines`). Runtime deps: commander, zod, yaml, ora, chalk, inquirer, etc. (`npm view dependencies`).
- **Telemetry** (VERIFIED, README "Telemetry"): "OpenSpec collects anonymous usage stats... only command names and version... Automatically disabled in CI." Opt out with `openspec config set telemetry.enabled false`, or `OPENSPEC_TELEMETRY=0`, or `DO_NOT_TRACK=1`. Unset means on. If adopted, set the opt-out in the environment first.
- Maturity: very active. Version 1.14.3, release cadence fast, large community (72k stars), and the command surface has already changed once (`/openspec:*` and `AGENTS.md` -> `/opsx:*` and skills; `docs/migration-guide.md`). The agent-contract doc lists "Known inconsistencies" (mixed snake_case/camelCase keys). Stores are "in beta" (README). Expect churn.
- It rewrites files in the project on `init`/`update` (`.claude/skills`, `.claude/commands`), and the README says it works best with high-reasoning models ("Codex 5.5 and Opus 4.7").
- Dependency metadata between changes: an in-repo change proposal `openspec/changes/add-change-stacking-awareness/proposal.md` proposes `dependsOn`, `provides`, `requires`, `touches`, `parent`, but `grep -rl dependsOn src` found nothing in implementation code. Treat as proposed, not shipped. The repo's own ordering is a hand-written `openspec/changes/IMPLEMENTATION_ORDER.md`. (VERIFIED for both observations.)
- Community schemas exist that add review gates and test plans (`docs/customization.md` "Community Schemas"), e.g. `anvil`: "`review` is written by a fresh-context, read-only reviewer... emits a `VERDICT:` line... OpenSpec only checks that artifacts exist, so enforce the gate with your own CI or hook." Not reviewed by us; UNVERIFIED beyond that catalog text.

## 7. Mapping to a tracer-bullet slice

Target slice shape (from the owner's wording): UX stories first, acceptance-criteria IDs, a tasks checklist with two boxes per task (implemented by the implementer, verified by QA), and priority/depends_on triage fields.

| Our element | OpenSpec counterpart | Fit |
|---|---|---|
| One slice = one folder | `changes/<name>/` with "one intent you can say in a sentence" (`writing-specs.md` "Right-size the change") | Compatible. Same tracer-bullet instinct. |
| Why / scope / out of scope | `proposal.md` Why, What Changes, Impact; proposal sample has "Out of scope" (`concepts.md`) | Compatible. |
| UX stories first | None. The default schema starts at proposal then specs; no user-story section. | Extend: add `## UX stories` (As a / I can / so that, per persona and device) at the top of proposal.md, or a `stories` artifact that `specs` requires. |
| Acceptance criteria with IDs | `### Requirement: <name>` + `#### Scenario: <name>`; names are the only identifiers, and `archive` matches MODIFIED/REMOVED by requirement name (`agent-contract.md` 4.2) | Mostly compatible; extend: encode an ID in the name, e.g. `### Requirement: AC-3 Rate limit on login`, and in scenarios `#### Scenario: AC-3.1 Rejects the 6th attempt`. The grammar tolerates it; renames then need RENAMED deltas. Each UX story would cite the AC IDs it needs. |
| Given/When/Then | Native | Compatible. |
| Delta ADDED/MODIFIED/REMOVED | Native | Compatible, and valuable for brownfield. Over-engineered for greenfield slices; optional for us. |
| Tasks checklist | `tasks.md` numbered checkboxes, grouped | Compatible as the base. |
| Two boxes per task (implemented, verified) | One box; `[x]` only. Parser treats any non-x marker as not-done and drops multi-character brackets (`task-progress.ts` comment: "A dropped `- [WIP] ...` is the accepted residue") | **Extend**: write `- [ ] impl  - [ ] qa  1.1 <task> (AC-3.1)`? Probably not safe: the parser would see only the first bracket as the checkbox, so a second `[ ]` is plain text. Safest: two lines per task, `- [ ] 1.1 impl: ...` and `- [ ] 1.1q verify: ...`, both counted by OpenSpec; or a separate `qa.md` ledger. Distinct ownership (implementer ticks first line, QA agent ticks second) is our rule, not OpenSpec's. |
| Priority, depends_on triage | `.openspec.yaml` accepts `x-*` keys (docs claim); built-in dependency fields only proposed (see 6) | **Extend**: `x-priority`, `x-depends_on` in `.openspec.yaml`, or YAML frontmatter in proposal.md. Our own checker must enforce them; the OpenSpec tool will not (UNVERIFIED whether unknown keys survive `openspec` rewrites). |
| Hard gates (tests first, blind implementer, separate runner, independent reviewer) | "fluid not rigid... no phase gates"; `/opsx:verify` "Does not block archive" | **Incompatible in spirit.** The tool's workflow is permissive and agent-self-reported. Our gates must stay in /sf, implemented as a schema `requires` chain plus our own scripts, not by the tool. |
| Tests-first from scenarios | Scenarios "could become an automated test" (`writing-specs.md`); no test-generation | Compatible as input to the tests-first stage; extension needed to map AC ID to test name (a ledger). |
| Archive and spec sync | `archive` merges deltas into `specs/` and moves the folder | Optional. We already keep requirements in the repo; adopting archive would add a second source of truth unless the main `openspec/specs/` replaces our requirement register (decision for the owner, not taken here). |
| Source-requirement drift check | None | Keep ours. |

## 8. Recommendation

**Adopt only the file format (a profile of it), not the tool; take workflow ideas as inspiration.** Reasons:

1. The format is plain Markdown with a documented, validated grammar (requirement/scenario, deltas, numbered checkbox tasks) and an MIT licence, so reuse is free and low risk. It fits "one intent per slice" and acceptance criteria that can become tests.
2. Our hard requirements are not in the tool: UX stories first, AC IDs that survive across tests and reviews, two-stage done state, `depends_on`/priority triage, and enforced gates with separate agents. The tool's stated philosophy is "no phase gates", its `verify` is advisory, and its dependency metadata is only a proposal. Adopting the CLI would give us little we cannot enforce with a small script of our own, while adding a Node >=20.19 runtime, default-on telemetry, files written into `.claude/`, and fast version churn (command names already changed once).
3. A staged path keeps options open: write slices in OpenSpec-compatible layout (`proposal.md`, `specs/<cap>/spec.md` deltas, `tasks.md`) so `openspec validate` can be run optionally as a linter later, with telemetry off, without committing to the CLI. We would add our extensions only in places the tool tolerates (extra sections in the proposal, `x-*` keys, ID-bearing names, extra task lines), and verify tolerance with a throwaway project before relying on it (not done here; UNVERIFIED).

Open questions for the owner or the next research step: (a) whether `openspec validate --strict` accepts ID-prefixed requirement names and two-line tasks; (b) whether the community `anvil` schema's review gate and test-plan ledger are close enough to borrow; (c) whether `openspec/specs/` should replace or sit beside our requirement register.

## Sources read

`README.md`, `docs/{concepts,commands,writing-specs,customization,cli,agent-contract,supported-tools,migration-guide}.md`, `schemas/spec-driven/{schema.yaml,templates/proposal.md,templates/tasks.md}`, `src/utils/task-progress.ts`, `src/core/validation/{constants,task-checkboxes}.ts`, `src/core/archive.ts` (grep), `skills/openspec-apply-change/SKILL.md` (head), `openspec/config.yaml`, `openspec/changes/{IMPLEMENTATION_ORDER.md,add-change-stacking-awareness/proposal.md}`, plus `gh repo view`, `gh search repos`, `npm view @fission-ai/openspec`.
