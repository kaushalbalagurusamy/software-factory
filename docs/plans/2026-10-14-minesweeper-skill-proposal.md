# Proposal: the `minesweeper` skill

Status: proposal, revision 2. Owner decisions recorded 2026-10-14. Nothing is built yet.
Date: 2026-10-14. Author: SF session.

Revision 2 follows the owner's direction: design for modularity and maintainability across future releases. Do not
fit the design to past projects or limit it to the current ones.

## The problem

The factory trusts the brief. `/sf` treats every line of the source requirements as a requirement, and a run ends when
every line is satisfied. That is safe only when the brief is honest. Briefs can contain traps, on purpose or not.
Followed literally, a trapped brief leads the builder to:

- break a software licence,
- break a model provider's terms,
- break copyright or privacy law,
- breach a professional duty,
- install a dependency that is unsafe or unmaintained,
- promise a guarantee that theory rules out,
- optimise a rubric against the real goal.

Agents rarely raise these unprompted. The skill makes the brief something to check, not something to trust: it is
checked against real rules before its lines reach the requirements ledger.

## Design goals

1. **Modular.** Knowledge lives in self-contained lens packs. Adding, removing or updating a topic never touches the
   engine.
2. **Stable contracts.** Inputs and outputs are versioned schemas. `/sf` and other skills depend on the schemas, not on
   internals.
3. **Evidence over recall.** A finding is confirmed only with a quote from a primary source fetched by the skill.
4. **Tested per module.** Each lens carries its own test cases. Any change to the engine or a lens re-runs the affected
   cases.
5. **Maintainable by default.** Sources have freshness policies, lenses have versions and changelogs, and a lint script
   enforces the structure.
6. **Not tied to any project.** No lens, case or rule refers to a specific past or current project.

## Architecture

```
~/.claude/skills/minesweeper/
  SKILL.md                    # entry point: when to run, how to call, the procedure
  engine/                     # stable core, rarely changes
    procedure.md              # the six sweep steps and their contracts
    prompts/                  # extractor, lens-sweeper, grounder, skeptic, reframer briefs
    schemas/                  # claim, finding, register, lens-manifest, source (JSON Schema, versioned)
  lenses/                     # one folder per lens; add a folder to add a topic
    <lens-id>/
      lens.md                 # manifest + guidance: scope, principles, questions, severity guidance
      traps.yaml              # trap catalogue: id, pattern, cues, sources, safe alternatives
      sources.yaml            # primary sources this lens cites, with adapter and freshness policy
      cases/                  # planted-trap briefs, clean twins, expected findings
      CHANGELOG.md
  sources/
    adapters/                 # fetchers by source kind: spdx, web-page, ecfr, osv, paper
    cache/                    # fetched copies (regenerable, never hand-edited)
  config/
    groups.yaml               # which lenses each sweep agent covers (tuning knob, not structure)
    models.yaml               # model per role (Claude Max subscription only)
    policy.yaml               # severity gates, freshness defaults, dispositions
  tools/
    lint.py                   # validates manifests, schemas, source refs, case coverage
    refresh.py                # re-fetches stale sources and reports changed ones
    search.py                 # local BM25 over the cache
    evaluate.py               # runs cases, writes per-lens recall and precision
  docs/
    adding-a-lens.md
    writing-cases.md
    versioning.md
```

### The engine (stable core)

The engine knows the procedure and the schemas but no domain. Its steps run in order, and each writes a file that
conforms to a schema:

1. **Extract claims.** The brief and everything attached to it become a list of claims. Attachments include the rubric,
   examples, sample data, linked repos, and suggested libraries and models. Implied claims count: "regardless of
   order" implies a trust model. Output: `claims.json`.
2. **Sweep by lens.** One agent per group in `groups.yaml` loads its lenses' `lens.md` and `traps.yaml`. For each claim
   it records one of:
   - `clear`, with a reason;
   - `suspect`, with the trap id and the cues it matched.

   Every claim gets a verdict, so a silent lens can be told apart from a lens that never looked.
3. **Ground.** For each suspect, search the cache and fetch the cited source if the cached copy is stale. The suspect
   becomes:
   - `confirmed`, with a quote, source id and fetch date;
   - `plausible`, with what would settle it;
   - `dismissed`, with a reason.
4. **Skeptic.** A fresh Claude context sees only the claims and the citations, not the sweepers' reasoning, and tries to
   dismiss each confirmed finding.
5. **Reframe.** Each surviving finding gets three fields:
   - **severity:** Critical, High, Medium or Low, as defined in `policy.yaml`;
   - **the underlying problem the brief should have stated;**
   - **a disposition:** `comply-safely`, `reframe`, `decline` or `ask-owner`.
6. **Register.** A trap register is written as JSON for machines and Markdown for people, plus a problem-definition note
   for research to start from.

### Lens packs (the modules)

A lens is a folder. Its manifest declares an id, a semver version, a scope, an owner and dependencies on source
adapters. It also declares `applies_when`, the conditions that mark a brief as in scope for the lens (a domain, a data
type, a technology), so lenses that don't apply are skipped and cost nothing.

`traps.yaml` entries are generic patterns, never project anecdotes. Each entry has:

- an id, a statement and the cues that suggest it;
- the sources that decide it;
- a default severity and safe alternatives.

An example entry from `distributed-systems`: "exactly-once delivery asserted end to end". Its cues are *exactly once*,
*never duplicated*, *regardless of retries*. It is decided by the Two Generals and FLP results and the idempotency
literature. Its safe alternative is effectively-once via idempotent keys, stated with the trust model.

The initial catalogue covers broad professional literacy and can grow:

| Group | Lenses |
|---|---|
| Law and terms | licensing, provider-terms, copyright-data-rights, privacy-regulated-data, professional-duty, accessibility |
| Security | security-ethics, supply-chain, appsec-auth |
| Deep technical | cryptography, distributed-systems, theory-complexity, os-systems, databases, performance |
| Evaluation and business | rubric-inversion, company-context, market-reality |

`company-context` holds no company data. It is a procedure for researching whatever company a brief names: mission,
customers, regulators, public incidents. It writes to the project's own `docs/minesweep/`.

### Sources and retrieval

- `sources.yaml` lists primary sources by id, URL, adapter and freshness policy. Terms of service are refreshed when
  older than 30 days at sweep time. Licences and statutes are refreshed every 90 days.
- Adapters keep fetching logic out of the lenses. A new source kind needs one adapter that every lens can use.
- The cache is regenerable. `refresh.py` reports which sources changed text since the last fetch, so a changed policy
  becomes a review item rather than a silent drift.
- Search starts as local BM25. Embeddings are added only if the evaluation shows BM25 missing traps that they find
  (owner decision).

### Contracts with the rest of the factory

| Consumer | Uses | Contract |
|---|---|---|
| `/sf` stage 0 (new) | runs the sweep before Research | register schema v1 |
| `/sf` ledger | a `trust` column per row: `trusted`, `conditioned (finding id)` or `rejected` | finding ids |
| `/sf` stage 1 | problem-definition note | Markdown section names |
| `/sf` stage 8 review | open findings as a hunting list | register schema v1 |
| `/sf` stages 9 and 12 | re-sweep changed or new requirement text only | claims schema v1 |
| `prd-writer`, `deep-research` | optional: sweep a draft, or seed research | register schema v1 |

Policy enforced through `/sf` (owner decision):

- An open Critical finding blocks scheduling of its rows until the owner signs off.
- A High finding needs a recorded disposition.
- "Out of scope" never closes a finding without a written consequence and a disposition.

## Testing and maintenance

- **Per-lens cases.** Each lens ships synthetic briefs, each with one planted trap, plus a clean twin that differs only
  in the trap. Twins measure false alarms precisely. Cases come from the trap catalogue, not from past projects.
- **Integration cases.** A small set of multi-trap briefs crossing lenses tests grouping, de-duplication and severity
  ranking.
- **Metrics.** `evaluate.py` writes per-lens and overall figures:
  - recall on planted traps;
  - the false-alarm rate on clean twins;
  - citation rate on confirmed findings;
  - tokens and minutes per brief.

  Results are committed beside the cases. Failed runs stay in the history.
- **Change rules.**
  - A lens change re-runs that lens's cases.
  - An engine or schema change re-runs everything.
  - A schema change bumps its major version and keeps a reader for the previous one for one release.
- **Lint.** `lint.py` fails when:
  - a manifest is invalid;
  - a trap has no source or no case;
  - a source has no adapter;
  - a lens has no clean twin.
- **Real-world findings.** When a sweep in the field confirms a trap no case covers, it is written up as a new generic
  trap entry plus a planted case through `writing-cases.md`, with no project names.

## Cost and limits

- Everything runs on the Claude Max subscription. There is no OpenRouter or other paid API (owner decision).
- Model per role is set in `models.yaml`: Sonnet by default, Opus for deep-technical lenses.
- `applies_when` and the group config bound the cost per brief. Lenses that don't apply are skipped.
- This is not legal advice. The skill flags and cites; the owner decides. Where the answer depends on jurisdiction or
  contract terms, the disposition is `ask-owner`.

## Build order

1. Schemas and `lint.py` (the contracts first).
2. The lens template, `adding-a-lens.md`, and case format; `evaluate.py` with cases written before lenses.
3. Engine prompts and `procedure.md`; `SKILL.md`.
4. Source adapters, cache, `search.py`, `refresh.py`.
5. Lenses one group at a time, each landing with its cases passing their thresholds; evaluation results committed.
6. `/sf` integration: stage 0, ledger `trust` column, gates, stage 8/9/12 hooks.
7. Sweep each new brief as it arrives, with the register marked uncalibrated until its lenses have passed evaluation
   (owner decision).

## Owner decisions (2026-10-14)

1. **Hard gate: yes.** Critical findings block scheduling until the owner signs off. High needs a recorded disposition.
2. **Retrieval: yes.** Lexical search first; embeddings only if the evaluation justifies them.
3. **Cross-family skeptic: no.** Claude Max subscription only; the skeptic is a fresh Claude context.
4. **Sweep new briefs on arrival: yes,** marked uncalibrated until their lenses pass evaluation.
5. **Scope (revision 2):** no fitting to past projects and no restriction to current ones. Modularity and
   maintainability for future releases are the design goal.
