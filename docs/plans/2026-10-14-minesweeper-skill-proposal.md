# Proposal: the `minesweeper` skill

Status: proposal, revision 5. Owner decisions recorded 2026-10-14. Nothing is built yet.
Date: 2026-10-14. Author: SF session.

Revision 2 follows the owner's direction: design for modularity and maintainability across future releases. Do not
fit the design to past projects or limit it to the current ones.

Revision 3 follows a second direction from the owner. The sweep is not a one-shot gate. It runs interleaved and
iteratively with the `deep-research` and `experiment-designer` skills to establish findings properly, and the real PRD is
written only after that loop converges.

Revision 4 takes in the executive summary of an external research report the owner supplied ("Adversarial PRD
Deconstruction and Distinguished Engineering Syllabus", produced with Argon 4). The pasted text ended before the report's
taxonomy table and syllabus, so only the summary is used here. The report's claims are treated as a secondary source
until each one is checked against the primary sources named in the lenses.

Revision 5 takes in the full report. It contributes:

- a four-tier severity table;
- six domain detection matrices with 35 trap entries;
- a four-gate protocol.

The report is stored verbatim in the private `gauntlet` repo (`research/2026-10-14-argon4-adversarial-prd-report.md`,
commit a09ff6d). It is not stored here because it names programme briefs and this repo has a public mirror. Revision 5
adopts its structure and seeds the lens catalogue from it. Every entry stays `unverified` until promoted. The review
below lists what is wrong or unsupported in it.

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

Agents fail on trapped briefs in two ways:

- **Sycophantic instruction-following.** The agent assumes the brief's author has technical and legal authority and
  builds what was asked, even when that means unlawful surveillance, copyleft code in a proprietary tree, or a brittle
  design shaped to a poisoned rubric.
- **Boundary evasion, the "out of scope" pathology.** Faced with a hard invariant, such as Byzantine fault tolerance
  across untrusted relays or a complex regulatory duty, the agent declares it out of scope and moves on to easy
  boilerplate.

Agents rarely raise these traps unprompted. The skill makes the brief something to check, not something to trust: it is
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
    checks/                   # deterministic checks a trap entry can name (read-only, never installs)
      registry.py             # npm / PyPI metadata: exists, created, maintainers, downloads, cross-registry name
      licence.py              # SPDX id and licence family for a named package or model card
      calc.py                 # back-of-envelope physics: memory footprint, bandwidth, fan-out tail
                              # probability, BFT/CFT quorum sizes, egress cost, payload vs MTU
  docs/
    adding-a-lens.md
    writing-cases.md
    versioning.md
```

### The engine (stable core)

The engine knows the procedure and the schemas but no domain. Its steps run in order, and each writes a file that
conforms to a schema:

1. **Extract claims.** Zero trust: everything in and around the brief becomes a claim. That covers six kinds:
   - every requirement sentence;
   - every named dependency (library, model, API, dataset, service);
   - every target metric and rubric item;
   - examples and sample data;
   - implied assumptions, as when "regardless of order" implies a trust model;
   - omitted boundary conditions: what each applicable lens says a brief in its domain must state but this brief does
     not. Examples are a threat model, a trust model, failure behaviour, data retention, jurisdiction and licence of
     output.

   Every claim gets a type. An omission is a claim like any other and is swept and settled the same way.

   Output: `claims.json`.
2. **Sweep by lens.** One agent per group in `groups.yaml` loads its lenses' `lens.md` and `traps.yaml`. For each claim
   it records one of:
   - `clear`, with a reason;
   - `suspect`, with the trap id and the cues it matched.

   Every claim gets a verdict, so a silent lens can be told apart from a lens that never looked.
3. **Ground.** Each suspect is routed to the cheapest method that can settle it (see "The discovery loop"):
   - retrieval from the cache;
   - `grounded-research`;
   - `deep-research`;
   - `experiment-designer`.

   The suspect becomes:
   - `confirmed`, with evidence: a quote, a research note, a report or an experiment result, each with its path and
     date;
   - `plausible`, with what would settle it;
   - `dismissed`, with a reason.
4. **Skeptic.** A fresh Claude context sees only the claims and the citations, not the sweepers' reasoning, and tries to
   dismiss each confirmed finding.
5. **Reframe.** Each surviving finding gets three fields:
   - **severity:** Critical, High, Medium or Low, assigned deterministically (see "Severity tiers"). `policy.yaml`
     holds an ordered list of yes/no questions. The first yes sets the tier, and the answers are recorded with the
     finding. Two runs on the same evidence must give the same tier;
   - **the underlying problem the brief should have stated;**
   - **a disposition:** `comply-safely`, `reframe`, `decline` or `ask-owner`.
6. **Register.** A trap register is written as JSON for machines and Markdown for people, plus a problem-definition note
   for research to start from. The register has a **poisoned-instruction autopsy** section. It lists every brief line
   or rubric item that is quarantined, meaning it will not be followed as written, with the finding behind each one.

### Severity tiers

The criteria come from the report and match the owner's scale. Each tier becomes yes/no questions in `policy.yaml`.

| Tier | Criterion | Typical consequence |
|---|---|---|
| Critical | Following the brief harms users, compromises physical safety, or plainly breaks a law, licence, third-party terms or professional ethics. | Legal liability, injunctions, criminal exposure, loss of IP, physical damage. |
| High | The deliverable fails under production conditions, gains a severe security hole, or creates substantial financial or legal exposure. | Outages, key recovery, remote code execution, supply-chain compromise, unit-economic failure. |
| Medium | A correctness, measurement, statistical or design flaw that a principal-level reviewer would reject. | Tail-latency breaches, silent data drift, uncalibrated predictions, metrics invalidated by leakage. |
| Low | Operational friction, weaker maintainability, minor inefficiency. | Technical debt, toil, wasted compute. |

### Topics that can never be dismissed as out of scope

`policy.yaml` holds a list of topics that a finding can never close as "out of scope". The list starts with:

- distributed consensus and trust models;
- Byzantine faults;
- key management and nonce uniqueness;
- regulatory duties;
- licences and provider terms;
- memory, bandwidth and latency physics;
- agent action safety.

When a brief omits one of these where a lens applies, the omission is itself a finding, and its tier follows the
questions in `policy.yaml`. This is the report's Gate 2.

## The discovery loop

The sweep is one of three activities in a loop that runs before the real PRD exists. The input brief is treated as an
untrusted draft. The output is a problem definition that has been checked, and the PRD is written from that.

```
brief (untrusted) ──► sweep ──► findings ──► route each open finding
                        ▲                      ├─ retrieval            (a quote settles it)
                        │                      ├─ grounded-research    (one decidable claim)
                        │                      ├─ deep-research        (a landscape: law, market, practice)
                        │                      └─ experiment-designer  (only a measurement settles it)
                        │                                │
                        └── re-sweep the reframed ◄──────┘ evidence updates findings and the problem definition
                            problem and new claims
                                         │ converged
                                         ▼
                        prd-writer writes the real PRD ──► /sf Decide, Spec, Tests ...
```

**Routing rule.** Each finding records why it took its route.

| A finding is settled by | Route | Example |
|---|---|---|
| A primary-source quote | retrieval | "this licence forbids commercial use" |
| One checkable fact about a tool or version | `grounded-research` | "does this library still ship this default" |
| A synthesis of many sources | `deep-research` | "what does this regulation require of this kind of product" |
| A number nobody has measured | `experiment-designer` | "can this latency budget be met"; "does this dedupe hold under retries" |

**Why it iterates.** Evidence changes the problem. Here is what each result can do:

| Result | Effect on the loop |
|---|---|
| A research report surfaces a rule nobody listed | It adds new claims to sweep. |
| An experiment shows a guarantee is impossible | The finding is confirmed, and the reframed problem has new claims to check. |
| A dismissal | The claim is cleared for the PRD. |

Each pass sweeps only what changed: new claims, reframed text, and findings whose evidence moved.

**Convergence.** The loop stops when all four of these hold:

1. every finding is `confirmed` with evidence, `dismissed` with a reason, or `ask-owner` with the question recorded;
2. a full pass produced no new findings;
3. the problem definition did not change in the last pass;
4. or a budget in `policy.yaml` was reached. In that case the remaining open findings are listed, and the PRD carries
   them as open questions. The budget has three parts:
   - an iteration cap;
   - a token and wall-clock ceiling per loop;
   - an immediate halt when a pass repeats the same routed calls with no change in findings.

   The skill applies its own agent-loop trap (unbounded agent loops) to itself.

An `ask-owner` finding does not block other findings. The loop keeps going around it.

**Hand-off to PRD writing.** `prd-writer` receives:

- the problem definition;
- the register;
- the research reports and the experiment results.

Every PRD requirement traces to either a brief line it keeps, with its trust status, or a finding that replaced it.
Discarded brief lines are listed with the finding that discarded them, so nothing disappears silently.

The PRD keeps the brief's legitimate business objective: the real-world change the organisation needs. It replaces each
naive feature demand with four kinds of statement:

- system invariants;
- service-level objectives;
- regulatory and terms guardrails;
- explicit non-goals.

This is the report's Gate 3, done by `prd-writer`.

**Hand-off to the technical spec.** The report's Gate 4 belongs to `/sf` stage 4 (`spec-writer`), not to this skill.
Each confirmed finding names the spec section that must answer it, so the spec cannot drop it:

- trust and consensus topology;
- cryptographic and agent-security posture;
- capacity and memory physics;
- the verification and calibration harness.

Stage 8 review checks that every section is filled.

**Ownership of artifacts.**

| Artifacts | Written by |
|---|---|
| Research notes and reports | the research skills, in their usual places (`research-notes/`, `research/`) |
| Experiments | `experiment-designer`, in its usual place |
| The register | minesweeper, linking to the other two by path |

The two research skills stay unchanged and reusable.

### Lens packs (the modules)

A lens is a folder. Its manifest declares an id, a semver version, a scope, an owner and dependencies on source
adapters. It also declares `applies_when`, the conditions that mark a brief as in scope for the lens (a domain, a data
type, a technology), so lenses that don't apply are skipped and cost nothing.

Each manifest also lists the lens's **required statements**: what a brief in its domain must say. Examples are the
trust model for distributed systems, the threat model for cryptography, and the lawful basis and retention period for
privacy. Extraction checks these to produce omission claims.

`traps.yaml` entries are generic patterns, never project anecdotes. Their fields follow the report's detection-matrix
columns:

| Field | Meaning |
|---|---|
| `id` | stable, `<lens-id>.<slug>`; the report's ids (LEG-01, DIST-03 …) kept as `aliases` |
| `kind` | `requirement`, `dependency`, `metric`, `rubric` or `omission` |
| `cues` | naive phrasings and rubric patterns that suggest the trap |
| `principle` | the law, theorem, standard or term it violates |
| `sources` | primary sources that decide it, by source id |
| `severity` | default tier and blast radius; the policy questions still decide |
| `remediation` | the safe route and the invariant the spec must state |
| `checks` | optional deterministic checks from `tools/checks/` (for example `registry.exists`, `calc.bft_quorum`) |
| `status` | `unverified` until every source resolves to a primary quote; only `verified` entries can confirm a finding |

An example entry from `distributed-systems`: "exactly-once delivery asserted end to end". Its cues are *exactly once*,
*never duplicated*, *regardless of retries*. It is decided by the Two Generals and FLP results and the idempotency
literature. Its safe alternative is effectively-once via idempotent keys, stated with the trust model.

The initial catalogue follows the report's six domains plus the business lenses. The seed entries come from the
report's matrices; each starts `unverified`.

| Group (sweep agent) | Lenses | Report seeds |
|---|---|---|
| Law, terms and ethics | licensing, provider-terms, ai-regulation, privacy-regulated-data, copyright-data-rights, security-ethics, professional-duty, accessibility | LEG-01 … LEG-06 |
| Supply chain, agent security and cryptography | supply-chain, agent-security (MCP: confused deputy, token passthrough, tool poisoning, silent redefinition, shadowing), cryptography (AEAD and nonce misuse, randomness, post-quantum migration) | SEC-01 … SEC-06 |
| Distributed systems and data | distributed-systems (CFT vs BFT, Two Generals, fencing, clocks), databases (CAP/PACELC, dual writes, hot partitions) | DIST-01 … DIST-06 |
| Systems and performance | os-systems (ports, file descriptors, OOM), performance (fan-out tails, egress economics), media-pipelines (memory physics, colour-space precision), realtime-transport (head-of-line blocking, jitter, causality limits on streaming translation) | PERF-01 … PERF-06 |
| Theory and measurement | theory-complexity (disguised NP-hard work, undecidability in rules engines), numeric-representation (money in binary floats), ml-evaluation (leakage, calibration), rubric-inversion (Goodhart) | TCS-01 … TCS-05 |
| Agents and cyber-physical | agent-orchestration (unbounded loops, irreversible actions without compensation or approval), cyber-physical (OT protocols, safety interlocks, NERC CIP where the brief touches the bulk electric system) | AGT-01, AGT-02, CPS-01 … CPS-04 |
| Business | company-context, market-reality | none |

Lenses whose `applies_when` does not match a brief are skipped. A brief about a web shop never loads `cyber-physical`.

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
- Dependency checks read registry metadata only. The skill never installs a package it is checking, which is the
  report's own slopsquatting rule applied to the skill.

### Review of the Argon 4 report

The report has good structure and many correct core claims. The arithmetic checks out, for example:

- 5 × 48 MP × 16 B ≈ 3.84 GB;
- 4K60 FP16 RGBA ≈ 3.98 GB/s;
- 1 − 0.99^50 ≈ 39.5%;
- BFT needs N ≥ 3f + 1.

It is still a secondary source with real defects. These matter for how it is used:

| Issue | Detail | Handling |
|---|---|---|
| Citations do not support most claims | The numbered references are almost all EU AI Act blog posts, attached even to the cryptography, supply-chain and NERC sections. Only the NIST PQC and GCM-forgery links match their topic. | Every seed entry is re-sourced from a primary source before promotion. |
| LEG-04 overstates GPLv3 | Using GPLv3 code in a hosted service that is not distributed does not by itself oblige source release. AGPLv3 section 13 is the network clause; GPLv3 has none. | Split into two entries: distribution of GPL code; network use of modified AGPL code. |
| Stale licence examples | Sentry moved from BSL to its Functional Source Licence in 2023, and Elasticsearch added AGPLv3 as an option in 2024. | Lenses name licence families, not vendors; `licence.py` reads the current licence at sweep time. |
| Unverifiable specifics | "Regulation (EU) 2026/1744" and its dates; "Recitals 99–100" applying high-risk duties across multi-agent chains; CVE-2026-26014 and CVE-2026-50577; the "July 2026 MCP security best practices"; the "TeamPCP" campaign; the NERC per-day penalty figure; the AES-GCM-SIV "48% slower" figure. | Each is marked `unverified`. Promotion needs the primary text: EUR-Lex, NVD, the MCP specification, an incident report, FERC's penalty notice, a measured benchmark. |
| Performance figures without a source | AES-GCM vs CCM vs CBC speed ratios; LMS and XMSS signature sizes depend on parameter sets. | Replaced by `calc.py` or an experiment, not quoted. |
| Names programme briefs | It ties traps to specific briefs (FacilityGrid, Qrypt, Boostlingo, AutoHDR, Thesis, Cover). | Stripped from lens content by the no-project rule. Briefs appear only as inputs, never in the catalogue. |
| Severity sometimes fixed per entry | The matrices hard-code a tier per trap. | Kept as a default only. The `policy.yaml` questions decide, so context can raise or lower the tier. |

### Contracts with the rest of the factory

| Consumer | Uses | Contract |
|---|---|---|
| `/sf` stages 1–2 (Research, Experiment) | become the discovery loop: sweep, research and experiment interleaved until convergence | register schema v1 |
| `grounded-research`, `deep-research` | receive routed findings, return notes or reports | finding id in, artifact path out |
| `experiment-designer` | receives findings only a measurement can settle | finding id in, results path out |
| `prd-writer` | writes the real PRD after convergence, with traceability to brief lines and findings | register schema v1 |
| `/sf` ledger | a `trust` column per row: `trusted`, `conditioned (finding id)` or `rejected` | finding ids |
| `/sf` stage 1 | problem-definition note | Markdown section names |
| `/sf` stage 8 review | open findings as a hunting list | register schema v1 |
| `/sf` stages 9 and 12 | re-sweep changed or new requirement text only | claims schema v1 |

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
  - severity agreement across repeated runs on the same brief, which checks that tiering is deterministic;
  - recall on omission cases, which are briefs that leave out a required statement;
  - tokens and minutes per brief.

  Results are committed beside the cases. Failed runs stay in the history.
- **Change rules.**
  - A lens change re-runs that lens's cases.
  - An engine or schema change re-runs everything.
  - A schema change bumps its major version and keeps a reader for the previous one for one release.
- **Lint.** `lint.py` fails when:
  - a `verified` trap cites a source that is not primary;
  - a `checks` entry names a check that does not exist;
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
4. Source adapters, cache, `search.py`, `refresh.py`, and `tools/checks/`, each check with unit tests.
5. Import the report's 35 matrix entries as `unverified` seeds, with names of specific briefs removed.
6. Lenses one group at a time. For each group:
   1. promote its seeds by re-sourcing them through `grounded-research`;
   2. write planted cases and clean twins;
   3. land the group with its cases passing their thresholds and the evaluation results committed.
7. Routing hand-offs to `grounded-research`, `deep-research` and `experiment-designer`, plus the convergence check and
   loop budget.
8. `/sf` integration:
   - stages 1–2 as the discovery loop;
   - `prd-writer` after convergence, with the four PRD statement kinds;
   - spec sections required by findings;
   - the ledger `trust` column and the gates;
   - the stage 8/9/12 hooks.
9. Sweep each new brief as it arrives, with the register marked uncalibrated until its lenses have passed evaluation
   (owner decision).

## Owner decisions (2026-10-14)

1. **Hard gate: yes.** Critical findings block scheduling until the owner signs off. High needs a recorded disposition.
2. **Retrieval: yes.** Lexical search first; embeddings only if the evaluation justifies them.
3. **Cross-family skeptic: no.** Claude Max subscription only; the skeptic is a fresh Claude context.
4. **Sweep new briefs on arrival: yes,** marked uncalibrated until their lenses pass evaluation.
5. **Scope (revision 2):** no fitting to past projects and no restriction to current ones. Modularity and
   maintainability for future releases are the design goal.
6. **Discovery loop (revision 3):** the sweep is interleaved and iterative with `deep-research` and
   `experiment-designer`, which establish the findings. The real PRD is written only after the loop converges.
7. **External research (revisions 4–5):** the full Argon 4 report is incorporated:
   - its severity table, domain matrices and four-gate protocol shape the design;
   - its 35 entries seed the catalogue as `unverified`;
   - its defects are listed in the review section.
