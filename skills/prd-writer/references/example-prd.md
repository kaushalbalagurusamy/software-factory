# PRD: Axiom checks at the scope of change (illustrative)

_Spec: illustrative, no business spec behind this example · Date: 2026-10-05 · Status: example_

This file is an example of the PRD layout in `prd-template.md`. Its scope block names real paths in this repository, so `scripts/check_scope.py` can validate it. The content is for illustration only and is not a plan of record.

## Source and targets

| Target | Text | Source |
|---|---|---|
| T1 | A change that violates an in-scope axiom is blocked with a counterexample | illustrative |
| T2 | A missing `unity` or `z3` fails the gate instead of degrading silently | illustrative |

## Decisions in force

- ADR-0001: Dual-plane architecture with Unity-IR. Lowering is deterministic and never uses an LLM.
- ADR-0002: Epistemic zero-trust verification. Implementers do not edit the locked test manifest.

## Work units

Goals and the reasons behind each scope are written here. The block below is the machine-readable form.

- **U1, axiom contract form.** Adds a module that represents axioms as checkable predicates. New files only, so it can run alongside U2.
- **U2, hard failure on missing tooling.** Changes the governance module so a missing `unity` or `z3` raises instead of falling back to regex checks. Owns `factory/governance.py` alone, because U1 and U3 only read it.
- **U3, CLI exposure.** Adds the command-line surface once U1's module exists. Depends on U1.

```yaml scope
units:
  - id: U1
    goal: "Represent axioms as checkable predicates"
    serves: [T1]
    owns: ["factory/axioms.py", "tests/test_axioms.py"]
    new: ["factory/axioms.py", "tests/test_axioms.py"]
    reads: ["factory/governance.py", "docs/adr/**"]
    entry_points:
      - {path: factory/governance.py, symbol: GovernanceEngine.audit_semantic_delta, why: "where deltas are classified today"}
    depends_on: []
    confidence: high
  - id: U2
    goal: "Fail the gate when unity or z3 is missing"
    serves: [T2]
    owns: ["factory/governance.py", "tests/test_governance.py"]
    reads: ["factory/cli.py", "factory/synthesis.py"]
    entry_points:
      - {path: factory/governance.py, symbol: UNITY_AVAILABLE, why: "silent fallback flag"}
    depends_on: []
    confidence: high
  - id: U3
    goal: "Expose axiom checks through the sf CLI"
    serves: [T1]
    owns: ["factory/cli.py", "tests/test_cli.py"]
    reads: ["factory/axioms.py", "factory/governance.py"]
    entry_points:
      - {path: factory/cli.py, symbol: main, why: "command registration"}
    depends_on: [U1]
    confidence: high
```

## Open questions

- Which axiom syntax does `axiomatic-spec` emit? U1's predicate representation depends on the answer.
