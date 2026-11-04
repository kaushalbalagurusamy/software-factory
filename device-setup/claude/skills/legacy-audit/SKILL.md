---
name: legacy-audit
description: >-
  Use before rewriting or migrating a legacy or undocumented codebase: a reverse-first audit that
  reads the source cover to cover, one unit at a time (form, module, service, schema), and produces
  per-unit analyses, a severity-tagged bug catalog and inputs for a migration spec, so the rewrite
  designs the problems out instead of porting them. Triggers: "audit this legacy code", "reverse
  engineer this app before we rewrite it", "catalog the bugs and smells", "per-file analysis", "form
  audit", "bug catalog", "choose a migration route". Read-only: writes only under docs/audit/. Also use it to audit crashed or half-finished work: when an interrupted session leaves uncommitted, untracked or unreviewed files, read each changed unit and record what it does, what tests cover it and whether anyone reviewed it, before committing or building on it. Not for
  quick orientation or blast radius of one change (brownfield-explorer) and not for writing contracts
  (axiomatic-spec).
---

# Legacy audit (reverse-first)

Understand before changing. An audit is a **read pass**: fixes happen in the rewrite. Porting line for line inherits every bug the original ever had; an audit turns the old code into a triaged chart of what it does and what is wrong with it, so the new design solves those problems instead of reproducing them.

This skill is the deep, complete read. `brownfield-explorer` is the cheap orientation for one change; use it first if the codebase is still unfamiliar, and hand its map to this skill. `axiomatic-spec` turns audit findings into contracts afterwards.

**Source.** Distilled from the "Reverse-Engineering a Legacy Codebase" lecture (StarHotel VB6 case study, about 13,000 lines, 150 findings). The reference repository `github.com/decagondev/vb6-rework-reverse-forward` holds worked outputs (`docs/forms/USER-LOGIN-FORM.md`, `docs/BUGS-MITIGATIONS.md`, `docs/MIGRATION-DOTNET.md`); it was **not read while writing this skill**, so treat its layout as an unverified exemplar to consult, not a template to obey.

## Rules

1. **Read-only.** Write only under `docs/audit/`. Do not edit, move or "fix" the source. If the source must be frozen for the audit, copy it beside the docs and treat the copy as read-only.
2. **Recon before prompting.** Without knowing what the app does, a model summarizes syntax, not behavior. Spend 15 to 30 minutes on the README, running the app if possible, and the file tree. Write down the facts you own and name the **center of gravity** of the app (the screen, endpoint or job everything hangs off) so the audit aims at it.
3. **Manifest first.** Read the project manifest before any source: build files, lockfiles, entry points, dependency pins (for the VB6 case, the `.vbp` file). It lists every file, pins dependencies, declares the startup and carries the version. It scopes the audit for free and catches deprecated dependencies on day one.
4. **One bounded job at a time, with a named output.** Good: "Start with the manifest; identify the entry point, every unit, every dependency; produce a tree, not a critique." Too vague: "Tell me about this codebase." Too eager: "Find all the bugs and rewrite this in a modern language." Map first, opine later.
5. **One artifact per phase. Don't skip, don't loop.**
6. **Every finding cites the source:** unit name, function name in backticks, line number when it matters.

## Pipeline

| Phase | Step | Artifact handed on |
|---|---|---|
| 0 | Recon: README, run the app, eyeball the tree | Facts and the center of gravity, in `docs/audit/00-recon.md` |
| 1 | Manifest-first map | Tree of entry point, units, modules, dependencies: `docs/audit/01-map.md` |
| 2 | Per-unit audit, UI layer (forms, screens, routes) | One markdown per unit under `docs/audit/units/` |
| 3 | Per-unit audit, business and data logic (modules, services) | One markdown per unit |
| 4 | Data audit: schema, reports, stored procedures | `docs/audit/04-data.md` |
| 5 | Optional: freeze the source beside the docs | Read-only source plus docs tree |
| 6 | Optional: deeper long-form pass per file | Per-file analyses |
| 7 | Bug catalog | `docs/audit/BUGS-MITIGATIONS.md` |
| 8 | Migration route selection | Route memo feeding a migration spec |
| 9 | Side quests | Nice-to-have ideas, clearly separate from findings |

## The per-unit audit (phases 2 and 3)

Read the unit **cover to cover**: every handler and helper, top to bottom, no skimming, until you could narrate the file without reopening it. Then write one markdown file for the unit with these sections:

1. **Purpose and lifecycle:** what it is for; load, events, unload (or request, handler, response).
2. **Controls or entry points:** what each one does.
3. **Permission checks:** the explicit ones, and the **missing** ones.
4. **Database touches:** reads versus writes, tables and columns.
5. **Globals and shared state:** what it reads or writes (for example a global SQL string or a session user id).
6. **Bugs, dead code, half-implemented features.**

Style: prose analysis with explicit **`Bug:`** and **`Smell:`** call-outs, each with a citation. Examples of the kind of thing to call out: a one-click admin login from a clickable label; a password field length cap that disagrees with the schema; credentials left in module globals for the whole session.

One markdown per unit keeps cross-linking cheap, gives every finding a path back to source, and leaves the next person a chart instead of a guess. Link units to each other where they call each other.

For smell lists beyond the unit template, reuse `implementation-review/reference/interface-checklist.md` (encapsulation, state, bloat) and `implementation-review/reference/io-checklist.md` (query loops, unindexed scans, unbounded lists, blocking calls).

## Bug catalog (phase 7)

Lift every `Bug:` and `Smell:` from the unit files into `docs/audit/BUGS-MITIGATIONS.md`, one row per finding:

| ID | Severity | Category | Unit and citation | Finding | Mitigation in the rewrite |
|---|---|---|---|---|---|

- **Severity:** critical, high, medium, low. Define the scale at the top of the file, and tally by severity at the bottom.
- **Category:** pick a small fixed set for the codebase (for example authentication, data integrity, dead code, reporting, dependencies) and stay inside it. The case study had about 10 categories.
- **Mitigation:** concrete and about the *new* design ("hash with a slow salted algorithm; no default account"), never "fix the bug".
- The catalog is the input to the rewrite. The unit files are the evidence behind it.

## Migration route selection (phase 8)

Tally findings by severity, list the candidate routes, and score each against budget, timeline, team and reporting fidelity. Pick the route whose weaknesses you can live with, and write the reasons. In the case study five routes were evaluated (incremental conversion, greenfield in three or four stacks) and greenfield won, because the codebase was small enough that a conversion tool's licence cost more than the time it saved, and designing 150 bugs out was easier than fixing them. Lock the choice into a phased roadmap and a slice loop of one branch, one slice, one log entry. If the route is a one-way door, run `one-way-door` before committing.

## Running it as an agent job

- Each unit audit is an independent read: dispatch one narrow, read-only subagent per unit (Read, Glob, Grep and a Write limited to `docs/audit/units/`), in parallel, with a small model where the unit is short.
- The subagent's brief names its unit, the output path and the six sections; it returns the path and the count of `Bug:` and `Smell:` call-outs, not the whole file.
- Merge the catalog in the orchestrating session so severities and categories stay consistent.
- A reviewer (`implementation-review`, or a second read by another model) should spot-check citations: open the cited line and confirm it says what the finding claims. An uncited finding is not a finding.
