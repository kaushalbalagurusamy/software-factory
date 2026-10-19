---
name: contract-verify
description: >-
  Write independent executable contracts for pure Python int/bool functions and verify the real implementation
  with z3: contract review before code (unsatisfiable preconditions, vacuous or contradictory postconditions,
  precondition compatibility between old and new contract versions), a fail-closed verification gate, and
  regression tests generated from counterexamples. Use at the contracts and solver-check stages of /sf, when the
  user asks to "verify this function", "prove this contract", "check that the patch keeps the invariant",
  "review the contract", or when a change touches a small pure function whose behaviour can be stated as
  predicates. Not for I/O, databases, UI, concurrency, floats, loops or anything outside the supported subset:
  those must be routed to tests, integration checks or telemetry, never "proved".
---

# contract-verify

Tool: `python -m factory.verify` (package `factory/verify`, needs `z3-solver` and `pyyaml`; run with
`PYTHONPATH=<software-factory repo>`). Semantics, IR and limits: `docs/verification-ir.md`.
Example contract: `examples/clamp.yaml`.

## When to use

After the developer PRD and scoped exploration, **before code**: an author who is not the implementer writes the
contract; the implementer never edits it. Use it per pure function (int/bool in, int/bool out). Everything
else gets `check_method: test|property|integration|e2e|telemetry` and is verified there; the solver is
one cheap layer, not the whole gate.

## Contract format (YAML)

Required: `contract_id` (stable, never reused), `requirement_ids`, `symbol` (`module:qualname`), `state_scope`
(`pure` for the solver), `semantics` (`math_int` | `int64`), `check_method`, `concurrency` (explicit; `none`
allowed), `frame` (`nothing` or the state names that may change), `params` (`name: int|bool`), `returns`,
`intended` with `preconditions`, `postconditions`, `errors` (`{exception, when}`), `invariants`.
Optional: `assumptions`, `route` (obligation id or `default` -> non-solver check method), `observed`
(notes about current code; never parsed into obligations, excluded from the hash), `approved_change`
(`reason` + `scope` list; the only way a weakened precondition, dropped guarantee, widened frame or changed
semantics is accepted).

Predicates are Python expressions limited to: comparisons (chains ok), `and/or/not`, `+ - * // %` with Python
floor semantics, `abs/min/max`, conditional expressions, `result`, `old(param)`, int/bool literals.
Anything else is rejected at load time with the reason. A predicate that faults (division by zero) is false.
Clauses may be strings or `{id, expr, check_method}`; ids default to `post-1`, `inv-1`, `err-<Exc>`.

Every contract also gets the implicit obligation `no-undeclared-errors`.

## Workflow

1. `python -m factory.verify check-contracts spec/<slice>/contracts` - review before code. Fails (exit 17) on
   unsatisfiable preconditions, contradictory or vacuous postconditions/invariants, ambiguous or dead error
   clauses, duplicate or retired ids (`--retired RETIRED.yaml`).
2. Brownfield change: `check-contracts NEW --against OLD` - precondition compatibility (every old input still
   permitted), retained postconditions, invariants, errors, frame, concurrency and semantics. A signature change
   is reported `COMPARISON_UNSUPPORTED`; the tool never substitutes text equality.
3. Implement (blind to the contract tests as usual).
4. `python -m factory.verify verify CONTRACTS --root SRC --report out.json [--cache .sf/proofs.json]
   [--regress-dir tests/regressions] [--source SYMBOL=FILE]` - the gate. **Release/CI runs use `--no-cache`**;
   `--cache` is for local speed only, because a hand-written cache file can forge a pass. Cache hits print as
   `PROVED (cached)` and the key covers the whole module, contract, z3 version and assumptions.
5. `python -m factory.verify report out.json` - human summary; exit code is the recorded gate code.

## Verdicts

`PROVED` (solver found `P AND T_impl AND NOT Q` unsatisfiable, P satisfiable, paths reachable; within the
recorded assumptions), `COUNTEREXAMPLE` (concrete inputs, replayed on the real function), `UNSUPPORTED`
(specific reason + declared route), `UNKNOWN`, `TIMEOUT`, `MODEL_MISMATCH` (z3 and real execution disagree:
translator bug). Vacuity is `UNKNOWN` with `vacuous: true`.

## Gate failure semantics (all fail closed)

| exit | meaning |
|---|---|
| 0 | every obligation PROVED or visibly routed |
| 2 | usage / malformed contract / no contracts |
| 10 | z3 missing |
| 11 | crash or unloadable implementation / any signature mismatch (never routable) |
| 12 | UNSUPPORTED with no declared route |
| 13 | MODEL_MISMATCH |
| 14 / 15 | UNKNOWN / TIMEOUT |
| 16 | COUNTEREXAMPLE |
| 17 | contract review error, duplicate/retired id |
| 18 | vacuous obligation |
| 19 | BINDING: target name defined/assigned more than once at module scope, or a star import |

A called `abs`/`min`/`max` that the module or function rebinds is refused as exit 13 (MODEL_MISMATCH).
The verified function is the one Python binds (module executed once, symbol resolved from its namespace).

The most severe code wins; every reason is in the report. A missing verifier or a translator crash is never a
"harmless refactor". Counterexamples: `--regress-dir` writes a pytest file that fails on the buggy code and
passes once fixed; commit it with the fix.

## Honest limits

Supported subset only: pure functions of int/bool with if/else, assignment, ternary, `+ - * // %`,
comparisons, boolean logic, `abs/min/max`, `raise`. No loops, calls, attributes, floats, containers,
try/except, globals, mutation. `int64` is checked arithmetic (overflow is an error outcome), not wraparound.
`PROVED` means "discharged by z3 on the modelled semantics under the listed assumptions and not contradicted
by boundary-value and random executions of the real bound function", not a machine-checked certificate. Unsupported obligations must be covered by the
declared route; the gate only checks that a route exists, not that the routed test is any good.

## What the binding check does and does not detect

Detected (exit 19 `BINDING`, or 13 for a called shadowed builtin): the target defined or assigned more than once,
star imports, and any difference between the bound function and the code compiled from the parsed def (module
level or imported-module `f.__code__ = ...`, `__defaults__`, `__kwdefaults__`, `__wrapped__`, closure, foreign
globals). The proof cache also hashes every repo module the target imports (transitively); a module with an
unresolvable import is never cached. **Not detected, stated assumptions:** monkeypatching after the import
finished (e.g. by the caller at run time), `builtins.x = ...`, and edits to stdlib/site-packages code. Use
`--no-cache` for release gates.
