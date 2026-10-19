# Agent-layer evals (grading side)

Implementers must never read, list, search or run anything under `evals/`. Plain `pytest` does not collect this directory (`testpaths = ["tests"]`); run it with `python evals/agents/run.py`.

## Case model
Each case is a pytest test tagged with `@pytest.mark.case(id, tier=..., tb=..., reqs=[...])`:
- `id`: `TB<nn>-G-<nnn>` for golden, `TB<nn>-D-<nnn>` for diagnostic; unique.
- `tier`: `golden` (the small must-pass gate, every case deterministic, every check cheap) or `diagnostic` (larger coverage suite, read for signal, includes bypass attempts and boundaries).
- `tb`: the tracer bullet whose PRD the case exercises; `reqs`: the requirement IDs from `docs/factory/requirements.md`.

A case may be written before its producer exists. Use `lib.need("module", "attr", ...)` to import the implementation: if it is missing, the case resolves to **blocked** (never pass). Any other skip is a defect.

Expectations come only from the published contracts (`docs/contracts/`) and the PRDs (`docs/prds/`), quoted or paraphrased in the case's docstring with the clause it checks. Never derive an expectation from implementation code.

## Golden membership
`GOLDEN.json` lists the golden case IDs; `run.py` requires the set of golden-tagged cases to equal it exactly. Changing it is a reviewed baseline update. A case's tier normally follows its id (`-G-` golden, `-D-` diagnostic); a baseline update that moves a case keeps its id and records the move in the owning test module (`PROMOTED` and `DEMOTED` sets, applied through `lib.tier_of`) and in `GOLDEN.json`, so both must agree or `run.py` reports a membership problem.

## Baseline updates
- **2026-10-19, MECE audit P0 (`audit/MECE-AUDIT.md`, section 4 "P0"). Golden 129 -> 139 (+10); diagnostic 1,173 -> 1,213; all cases 1,302 -> 1,352 (50 new cases).** Reason: the audit found the golden gate passed hard-coded paths, a hard-coded deploy command, a deny-all implement Bash guard and a stop gate that never needed full-suite evidence, and the contracts let `implement` rewrite its own gates. Nothing was removed; swapped-out golden cases stay in the suite as diagnostic.
  - P0-1 (generality, alt profile): TB14-G-008 -> TB14-D-001, TB08-G-010 -> TB08-D-114, TB06-G-004 -> TB06-D-082 swapped; TB14-D-002, TB08-D-128, TB06-D-157, TB05-D-004, TB05-D-005 promoted.
  - P0-2 (allowed implement Bash): TB06-D-134 (`pytest tests/unit`) and TB06-D-139 (`ls src`) promoted.
  - P0-3 (R-15 full-suite evidence): TB09-G-002 -> TB09-D-029 swapped; TB09-D-028 promoted. Note: the trivial-assertion check (old G-002) is no longer golden; the remaining golden stop-gate cases keep skip, removed-test, frozen-hash, own-path and iteration-cap coverage. Reviewers may want to promote a trivial-assertion case back later.
  - P0-4 (control files): new binding clarification C-36 in `docs/contracts/clarifications.md`; new golden cases TB05-G-011 and TB06-G-011; new diagnostics TB05-D-135 to D-148 and TB06-D-234 to D-267.
  - P0-5 (process): see the next section; not a case.
  - Net golden: 4 swapped out, 12 promoted (the replacements and promotions of P0-1 to P0-3), 2 new (P0-4) = 129 - 4 + 12 + 2 = 139.

## Mechanical blindness for implementers
Until the hooks exist, the only barrier keeping this build's own implementers from the grading side is prose, which contradicts "hooks enforce; prompts advise" (ADR-0003 section 2) and the owner's blindness requirement (R-21). So:
- Every implementer worktree is created **without `evals/`**: a sparse checkout that excludes `evals/` (or a branch with `evals/` removed). The files are then not on disk for the implementer to read, list, grep or run.
- Implementer sessions also run with a project `permissions.deny` rule for `Read(./evals/**)`. A global deny is acceptable for this build, because the Test role does not run inside implementer sessions.
- The orchestrator provides `scripts/implementer-worktree.sh` to create such a worktree. This slice does not create the script; another slice does. Until it lands, an orchestrator must apply the two rules above by hand.
- Record of origin: MECE-AUDIT P0-5. The methodology note belongs in `docs/factory/METHODOLOGY.md` (outside this slice's file ownership).

## Running
`python evals/agents/run.py [-k expr]` runs pytest, writes `evals/agents/results/latest.json`, and prints pass, fail and blocked counts per tier, per TB and per requirement, and the golden verdict (green only if every golden case passes and membership matches).

## Helpers (`lib.py`)
`make_project`, `payload`, `run_cli`, `run_decide`, `need`, `PROFILES`. Profile fixtures: `profiles/base.yaml` and `profiles/alt.yaml`.
