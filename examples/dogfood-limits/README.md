# Dogfood demonstration: exploration, contracts, a code diff, verification, a refreshed architecture artifact

**This is an explicitly labelled MINIMAL FIXTURE.** It exercises the /sf verification toolchain end to end on one tiny pure module (`limits.clamp`). It does not claim verification coverage of the factory itself or of any real project.

What `python examples/dogfood-limits/run_demo.py` does, in order (outputs in `out/`):
1. `sf structure scan` of the base module (symbols, edges, limits).
2. Contract review before code (`sf contracts check-contracts`): the independent contract is consistent and not vacuous.
3. `sf contracts verify` on `base/`: **PROVED**, gate passes.
4. A plausible old unit test passes on `head_bad/` (the patch "looks fine").
5. `sf contracts verify` on `head_bad/`: **COUNTEREXAMPLE** (`clamp(11, 0, 10)` returns 11), gate fails with exit 16, and a regression test is generated that fails on the bad code.
6. `sf structure diff base head_bad`: the changed symbol and its callers.
7. `sf contracts verify` on `head_good/` (the corrected patch): **PROVED**; the generated regression test passes on it.
8. A model of the head is built from the structural scan, checked and rendered by Mermaid Nesting Dolls: `out/explorer.html` (click-through architecture of the fixture).

Limits stated plainly: Python only, a pure int subset, `ast`-based structure with unresolved edges reported, and PROVED holds within the recorded assumptions (math integers, annotated types, terminating pure function).
