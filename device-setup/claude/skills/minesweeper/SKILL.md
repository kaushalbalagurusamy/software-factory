---
name: minesweeper
description: >-
  Sweeps an untrusted product brief, PRD, assignment or rubric for traps before any of its lines
  become requirements: licence, provider-terms, privacy, regulatory and ethics violations; unsafe or
  hallucinated dependencies; guarantees that theory or physics rules out; rubrics that reward the
  wrong thing; and omitted boundary conditions (trust model, threat model, budgets). Runs as an
  iterative discovery loop with grounded-research, deep-research and experiment-designer, and hands a
  checked problem definition and trap register to prd-writer. Use whenever a new brief, PRD, spec,
  challenge or rubric arrives, at /sf stages 1-2 before research, when someone asks to "check the
  requirements", "find the traps", "what's wrong with this PRD", "is this brief safe to build", and at
  /sf stages 9 and 12 on changed or new requirement text. Not legal advice: it flags and cites; the
  owner decides.
---

# Minesweeper

## Why this exists

The factory treats every line of the source requirements as a requirement, and a run ends when every
line is satisfied. That is only safe when the brief is honest. Briefs can contain traps, on purpose
or not, and agents fail on them in two ways:

- **Sycophantic instruction-following**: the brief's author is assumed to have technical and legal
  authority, so the agent builds what was asked: unlawful surveillance, copyleft code in a
  proprietary tree, a design shaped to a poisoned rubric.
- **Boundary evasion**: faced with a hard invariant (Byzantine faults across untrusted relays, a
  regulatory duty), the agent calls it "out of scope" and builds the easy part.

This skill makes the brief something to check, not something to trust. Every line becomes a claim,
every claim is swept by topic lenses, suspects are settled with primary evidence, and what survives
reframes the problem before a PRD is written.

## Layout

```
SKILL.md            this file
engine/             procedure.md (the steps and loop), prompts/ (one brief per role), schemas/ (v1 contracts)
lenses/<id>/        lens.md (manifest + principles), traps.yaml, sources.yaml, cases/, CHANGELOG.md
config/             groups.yaml (sweep agents), models.yaml (Claude Max only), policy.yaml (severity, gates, budget)
sources/            adapters/ (web_page, spdx, ecfr, osv, paper), cache/ (regenerable)
tools/              plan, lint, validate, render, search (BM25), refresh, evaluate; checks/ (registry, licence, calc)
integration/        multi-lens cases
docs/               adding-a-lens, writing-cases, versioning
```

ROOT below is `~/.claude/skills/minesweeper`. Tools are Python 3 with PyYAML and jsonschema.

## Modes

| Mode | When | What runs |
|---|---|---|
| **full** | a new brief before /sf stages 1-2 | the discovery loop: steps 1-6, routed research and experiments, repeated to convergence or budget |
| **delta** | /sf stages 9 and 12: changed or new requirement text | steps 1-6 on the new text only, appended to the existing register |
| **eval** | `tools/evaluate.py run` | one pass, retrieval and checks only, no research hand-offs, no questions |

## How to run a full sweep

Read `engine/procedure.md` once per session; it is the contract. In short:

1. **Set up.** `RUN=<project>/docs/minesweep/<date>-<brief-slug>`. Copy the brief to `RUN/brief.md`.
   `python3 ROOT/tools/refresh.py` (stale sources), then
   `python3 ROOT/tools/plan.py RUN/brief.md --json > RUN/plan.json`. If a company or organisation is
   named, `company-context` runs its research procedure into `<project>/docs/minesweep/`.
2. **Extract** claims with the extractor brief (`engine/prompts/extractor.md`), on the extractor
   model. Validate with `tools/validate.py claims`.
3. **Sweep**: dispatch one Agent per group in `plan.json` in parallel, each with
   `engine/prompts/sweeper.md`, its lens paths, `RUN/claims.json`, and the group's model. Merge suspects into
   findings.
4. **Ground** with `engine/prompts/grounder.md`. Route by `policy.yaml routes`: retrieval and checks
   in-line; `grounded-research`, `deep-research` and `experiment-designer` by invoking those skills
   with the finding id. They write to their usual places; the finding links the path.
5. **Skeptic**: a fresh Agent on the skeptic model with `engine/prompts/skeptic.md`, given only the
   claims and the confirmed findings with evidence.
6. **Reframe** with `engine/prompts/reframer.md`, then write `register.json`, run
   `tools/validate.py register RUN/register.json --write-gates`, render `register.md`, and write
   `problem-definition.md`.
7. **Loop**: new claims from research, reframed text and moved evidence go round again until the
   convergence rule or the budget in `policy.yaml` stops it (procedure.md, "The discovery loop").
8. **Hand off** to `prd-writer` with the problem definition, register and artifacts.

Report to the owner: calibrated or not, the gates (Critical blocking, High needing disposition), the
quarantined brief lines, the ask-owner questions, and the register path.

## Rules that do not bend

- **Evidence over recall.** A finding is confirmed only with a primary quote fetched by the skill, a
  check's output, or a research/experiment artifact from this run. An `unverified` catalogue entry
  can raise a suspect, never confirm one. Never carry a price, version, limit or legal figure from
  memory.
- **Never out of scope** for the topics in `policy.yaml never_out_of_scope`. Omitting one where a
  lens requires it is itself a finding.
- **Deterministic severity.** Answer the policy questions in order; the first yes sets the tier;
  `validate.py` rejects a tier that does not follow from the answers.
- **Gates.** An open Critical finding blocks scheduling of the requirement rows it conditions until
  the owner signs off. A High finding needs a recorded disposition.
- **Uncalibrated is labelled.** A lens counts as calibrated only when its cases passed evaluation
  at its current version (`runs/calibration.json`). An uncalibrated register says so at the top;
  its findings are still acted on, as leads.
- **Read-only checks.** The skill never installs, downloads or runs a dependency it is checking.
- **Claude Max subscription only.** No OpenRouter or other paid API; model per role in
  `config/models.yaml`.
- **No project names in the skill.** Lenses, traps and cases are generic; lint enforces a denylist.
  Field findings come back as generic traps plus planted cases (`docs/writing-cases.md`).

## Contracts with the factory

| Consumer | Gets | Contract |
|---|---|---|
| `/sf` stages 1-2 | the discovery loop runs in place of a one-shot research pass | register v1 |
| `grounded-research`, `deep-research` | a finding id and question | returns a note/report path |
| `experiment-designer` | findings only a measurement settles | returns a plan/results path |
| `prd-writer` | problem definition, register, artifacts | every requirement traces to a kept line or a finding |
| `spec-writer` (/sf stage 4) | each confirmed finding's `spec_section` | the section must answer it |
| `/sf` ledger | `trust` per row: trusted, conditioned (F-id), rejected (F-id) | finding ids |
| `/sf` stage 8 | open findings as the review's hunting list | register v1 |
| `/sf` stages 9, 12 | delta sweep of changed or new text | claims v1 |

## Maintenance

```
python3 ROOT/tools/lint.py                 # structure, schemas, sources, cases, denylist
python3 -m unittest discover -s ROOT/tests # checks, search, validation rules
python3 ROOT/tools/refresh.py --dry-run    # which sources are stale
python3 ROOT/tools/refresh.py              # re-fetch; exit 1 if a source changed or lost a quote
python3 ROOT/tools/evaluate.py run --label <name> --lens <id>
python3 ROOT/tools/evaluate.py score ROOT/runs/<dir> [--record]
```

A lens change re-runs that lens's cases; an engine, schema or policy change re-runs everything
(`docs/versioning.md`). Failed evaluation runs stay in `runs/`; a rerun is a new directory.
To add a topic, add a lens folder (`docs/adding-a-lens.md`); the engine does not change.
