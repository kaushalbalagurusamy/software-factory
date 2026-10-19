---
name: axiomatic-spec
description: >-
  Use this skill after the developer-facing PRD exists (work units with file scope, accepted ADRs, experiment verdicts; written by `prd-writer`) and before any implementation, whenever the user wants it turned into something implementable and verifiable. A bare idea, stakeholder ask, or business spec with no PRD is not input: send it upstream (`spec-writer`, `biz-decomposer`, `prd-writer`) and say which. A standalone feature request or issue against an existing repo is still in scope; treat it as a one-unit PRD. Triggers include: "polish this PRD", "define requirements", "write the spec", "make this testable", "what are the invariants", "axiomatic", "contracts for this feature", "scope this change in our codebase", or any request to plan a change against an existing (brownfield) repository before coding. Converts vague intent into axioms — decidable, observable, symbol-attributed contracts (pre/postconditions, purity, concurrency, error models) — plus spec-derived tests and a telemetry plan, so implementation is harder to reward-hack and easier to verify. Handles both greenfield (define the domain from scratch) and brownfield (scope a change inside a multi-million-LOC repo without ingesting the whole thing).
---

# Axiomatic Spec

## What this is for

Most implementation failures — and most reward-hacking by coding agents — trace back to a spec that could not be falsified. "The API should be fast and secure" cannot be violated in a detectable way, so an agent can satisfy it with anything. This skill turns intent into **axioms**: statements that are decidable (true or false for a given execution), observable (can be measured in a test or in production telemetry), and attributed to a concrete symbol so a later verification step knows where to look.

The contract format (symbol IDs, purity, concurrency scope, P/Q clauses, error models, causal links) is language-agnostic. It happens to mirror Unity-IR so a spec can later be checked by the `unity` semantic-delta engine, but that is an optional gate; see "Verification gate" below.

## Inputs

When the factory loop ran upstream, the input is the dev-facing PRD from `prd-writer`. Read these parts of it and do not re-derive them:

| PRD part | What this skill does with it |
|---|---|
| Source and targets (T1, T2, ...) | Every axiom carries `serves: [T..]`. A target that cannot be made decidable goes to `open-questions.md` and back to the spec owner. Never reword a target to make it easier to check. |
| Work units (U1, U2, ...) and each unit's `owns`, `new`, `reads`, `entry_points` | One contract set per unit. A contract's symbol must live in that unit's `owns` or `new`. Entry points are where contract extraction starts. |
| `confidence` on a unit | `high`: use the scope as the brownfield surface (Mode B steps 1 and 2) and do not re-run `brownfield-explorer`. `low`: run `brownfield-explorer` first, and report the real scope back to the PRD owner. |
| Decisions in force (accepted ADRs, experiment verdicts) | Treated as fixed. Contracts cite the ADR id as a constraint. If a contract cannot be written without contradicting one, stop and report it. That reopens the ADR through `one-way-door`, not through an edit here. |

No PRD (a standalone change request): run as before, and say at the top of the bundle that no PRD scope backed it.

## The bar for an axiom

Every requirement that survives this process must pass all six checks. If it can't, it is either decomposed until it can, or moved to `open-questions.md` with the exact question that would resolve it.

1. **Decidable** — for any single execution, it is unambiguously true or false. "Handles errors gracefully" fails; "returns `Err(InsufficientFunds)` and leaves `balances` unchanged when `amount > balance`" passes.
2. **Observable** — there is a concrete way to check it: an assertion, a test, a metric, a log line. Name it, and give its machine-checkable form in `check:` (see "Machine-checkable form").
3. **Attributed** — it names the symbol(s) it constrains (`@pkg.module.Class.method`). Global invariants name the state they range over.
4. **Falsifiable by a test the implementer did not write** — the acceptance/property test derives from the contract, not from the code. This is the anti-tautology rule: an agent implementing the symbol never authors the criteria that verify it.
5. **Quantified where it matters** — latency, throughput, size, retry counts, timeouts are numbers with units and percentiles, not adjectives.
6. **Independent** — it doesn't restate another axiom. Redundancy hides which one actually failed.

See `reference/axiom-checklist.md` for the rewrite patterns that get a vague requirement over this bar.

## Workflow

Decide the mode first, then follow that path. Both paths end in the same output set.

### Mode A — Greenfield (nothing exists yet)

1. **Interrogate the intent.** Read the PRD/vision and extract every claim. For each vague word ("fast", "scalable", "secure", "robust", "intuitive"), ask the user for the number or the failure mode they'd actually complain about. Don't invent numbers silently — propose one, mark it as proposed, and ask. Write ambiguities to `open-questions.md` as you go; a spec with honest open questions beats one with hidden assumptions.
2. **Model the domain.** Entities, their state, and legal state transitions. Write global invariants as quantified statements (`∀ account: balance(account) ≥ 0`). These are the things that must hold between any two operations, not per-operation.
3. **Write capability contracts.** One per externally meaningful operation, in the contract format (`reference/contract-format.md`): symbol ID, params with types, return/error model, purity, concurrency scope, preconditions P1..Pn, postconditions Q1..Qn, and causal links to the symbols it calls / is called by. Prefer fewer, sharper contracts over exhaustive ones — the core state-mutating operations first, read paths second, glue last.
4. **Classify decisions.** First match each choice against the PRD's decisions in force: an accepted ADR already covers it, so link `docs/adr/NNNN-...` from the contract and write no stub. For a choice no ADR covers that is expensive to reverse (storage schema, public API shape, concurrency model, auth boundary, data residency), write an ADR stub: the question, the alternatives, and `Status: Proposed`. The stub is a pointer, not a decision; `one-way-door` runs the debate and fills in the Decision Trail. Two-way doors get a one-line note and move on.
5. **Derive tests from contracts, not from code.** For each contract: an example test per postcondition, a negative test per error in the error model, and a property test sketch for each invariant (hypothesis-style: generate inputs satisfying P, assert Q). Write them in the project's own test framework (PHPUnit for PHP, pytest for Python, etc.) and put them in `spec/<feature-slug>/tests/` as executable-shaped stubs the implementer is not allowed to edit without an ADR.
6. **Plan telemetry.** Each global invariant and each one-way-door contract gets an observability hook: what metric/assertion/log proves it holds in production, and what the alert condition is. Axioms with no production signal are flagged — they'll silently rot.
7. **Emit the spec bundle** (see Output).

### Mode B — Brownfield (change inside an existing, possibly huge repo)

The governing constraint: **you cannot ingest a multi-million-LOC repo, and you shouldn't try.** A 1M-token context holds on the order of 30–50k LOC of raw source; even a 4× semantic compression doesn't get a 5–10M LOC codebase anywhere near fitting. The work is scoping — finding the small subgraph the change actually touches — and then running the greenfield steps on that subgraph only.

1. **Orient and locate the blast radius.** When the PRD unit has `confidence: high`, its scope is the surface: take it and go to step 3. Otherwise invoke `brownfield-explorer`. That skill owns cheap-first orientation (existing docs/`CLAUDE.md`/ADRs, module layout by LOC, a symbol-level repo map, DeepWiki for public repos) and blast-radius expansion from the change's entry points (callers/callees, data stores, locks/channels/atomics, public API surface crossed), with its own stop condition (~50–100 files) and an explicit call-out when the change is bigger than assumed. Invoke it — or point it at this area of the repo if it's already been mapped, so it updates rather than re-derives — before continuing; don't re-run that orientation/expansion logic inline here. If it reports the scope busts the budget, that's a finding to report to the user before writing a single contract.
2. **Take the scoped surface it hands back** — entry points, in-scope file list, boundaries assumed stable, expansion log — as the input to the rest of this mode. It becomes the opening "Scope" section of `delta.md` (see Output).
3. **Extract the current-state contracts (S_pre).** For every symbol in scope, write down what the code *actually* guarantees today: guard clauses → preconditions, return paths and raised errors → error model, `with lock:` / `mu.Lock()` → concurrency scope, writes to `self.*`/globals → purity, existing tests → already-enforced postconditions. These are observations, not aspirations; label anything you inferred rather than read.
4. **Write the target contracts (S_post)** in the same format, then diff them against S_pre by hand. Flag every one-way door: lock removed or scope changed, pure → impure, postcondition dropped, symbol removed, schema shape changed, and precondition changes in **either** direction:
   - **Strengthened or added** (old P ⇏ new P): inputs callers could send before are now rejected — breaks callers.
   - **Weakened or removed** (new P ⇏ old P) where a postcondition, error-model entry, or global invariant depended on it: the implementation now accepts inputs the old guarantees were built on excluding — e.g. dropping `amount > 0` from `deposit` lets a "deposit" drive a balance negative, silently breaking `∀ a: balance(a) ≥ 0`. For every removed or relaxed guard, name which Q or invariant it was protecting; if none, say so explicitly, which makes it a two-way door.

   Each one-way door that no accepted ADR covers gets an ADR stub before implementation starts.
5. **Continue with greenfield steps 5–7** on the scoped surface only.

## Output

Write the bundle to `spec/<feature-slug>/` in the project:

```
spec/<feature-slug>/
├── vision.md            # Intent in controlled natural language; one paragraph per capability, no adjectives without numbers
├── domain.md            # Entities, state, transitions, global invariants (∀/∃ statements)
├── contracts/           # One .uir-style file per symbol (see reference/contract-format.md); each axiom has serves: and check:
├── delta.md             # Brownfield only: S_pre vs S_post per symbol, one-way doors flagged
├── adrs/                # One ADR stub per one-way door no accepted ADR covers; links to accepted ADRs live in the contracts
├── tests/               # Spec-derived acceptance + property test stubs (implementer may not edit)
├── telemetry.md         # Invariant → production signal → alert condition
└── open-questions.md    # Everything that couldn't be made decidable, with the question that would resolve it
```

Then give the user a short inline summary: number of contracts, one-way doors found, open questions that block implementation, and what you'd recommend resolving first.

## Machine-checkable form

Each axiom names how it is checked, in `check:`. Use the cheapest form that can decide it:

| `check:` | Use when | Status in this repo (read vs run) |
|---|---|---|
| `deal` | Python symbol; the clause is an arithmetic or boolean expression over params and result. Emit `@deal.pre`, `@deal.ensure`, `@deal.pure`, `@deal.raises` on a stub, and run `python -m crosshair check <file>`. | Run, 2026-10-05: crosshair returned a counterexample for a deliberately wrong postcondition and nothing for a correct one. `factory/` does not import `deal` or `crosshair` anywhere yet, so no gate runs this automatically. |
| `unity-l2` | The Unity gate applies (see below) and the predicate fits the SMT prover's two supported shapes. Build the spec `UnityModule` by hand. | Read and run: see `reference/unity-integration.md`. |
| `test` | The clause needs a fixture or I/O; write it as a spec-derived test in the project's framework. | Project-specific. |
| `telemetry` | The clause is only observable in production (latency percentile, rate). | Needs the telemetry plan entry. |

Do not mark an axiom `deal` or `unity-l2` on the strength of its shape alone: run the check once against a known-bad stub and record that it fails. An axiom whose check cannot fail is decoration.

## Verification gate

The gate is the **spec-derived test suite, written in the project's own test framework** (pytest, PHPUnit, Jest, go test, …) and locked behind an ADR, plus the telemetry plan. That works for any language and is the default.

**Unity is off by default, and when it is required, a missing tool is a failure.** Only bring it in when both hold:
1. The user explicitly asks for Unity verification or Unity-IR output.
2. The code under spec is Python or Go. Unity's parser supports nothing else, so for PHP, JS/TS, Java and so on it cannot apply at all.

If both hold, the gate mode is `required`: if `compiler` or `z3` cannot be imported, report the gate as FAILED with the import error. Never fall back to regex or text checks and report a pass. (`factory/governance.py` currently does fall back; see the note in `reference/unity-integration.md`.) Read `reference/unity-integration.md` for what Unity can and cannot check today. Otherwise don't run Unity, don't cite it, and don't add Unity caveats or schema-mapping notes to the spec bundle. It would only be noise.

## Judgment calls

- **Don't gold-plate.** A feature with three state-mutating operations needs three real contracts, not thirty. Depth on the mutating core, breadth only where it's cheap.
- **Proposed ≠ decided.** Any number or decision you supplied rather than the user is marked `[proposed]` in the spec until they confirm. Never let a proposed value become a load-bearing axiom silently.
- **The blast radius is a finding.** If brownfield scoping reveals the change touches far more than the user assumed, say so before writing contracts — that often changes the plan.
- **Stop when it's decidable, not when it's pretty.** The point is that the next step (implementation) can be verified. Prose polish is secondary.
