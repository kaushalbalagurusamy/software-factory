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
`GOLDEN.json` lists the golden case IDs; `run.py` requires the set of golden-tagged cases to equal it exactly. Changing it is a reviewed baseline update.

## Running
`python evals/agents/run.py [-k expr]` runs pytest, writes `evals/agents/results/latest.json`, and prints pass, fail and blocked counts per tier, per TB and per requirement, and the golden verdict (green only if every golden case passes and membership matches).

## Helpers (`lib.py`)
`make_project`, `payload`, `run_cli`, `run_decide`, `need`, `PROFILES`. Profile fixtures: `profiles/base.yaml` and `profiles/alt.yaml`.
