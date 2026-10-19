# Acceptance report: factory/verify and factory/structure

Independent adversarial acceptance test, 2026-10-19, branch `sf/acc-fg` (base `46f5aad`). I did not write the
code under test. The spec I tested against is `~/sf-verification-followup.md` requirements 1 to 6,
`docs/verification-ir.md`, `skills/contract-verify/SKILL.md` and `skills/structure-scan/SKILL.md`. I did not edit `factory/`.
Environment: Python 3.14.4, z3 5.3.1, pytest from `.venv`.

Run: `scripts/bounded-pytest.sh tests/acceptance -q -p no:cacheprovider` gives **139 tests: 118 passed, 21 failed**
(about 9 s). Each failing test is one defect listed below. None is marked skip or xfail.

## What held

- **Translator semantics (25 brute-force cases, all pass).** I compared every PROVED with brute-force execution over
  ints -6..6 and bools, and replayed every COUNTEREXAMPLE in plain Python. Covered: negative `//` and `%`, the
  `a == b*(a//b) + a%b` identity, sign of `%`, division by zero (declared and undeclared), large constants,
  bool/int ternaries, short-circuit `and`/`or` guarding a division in both orders, chained comparisons including a
  faulting middle operand, `abs/min/max`, ternary precedence, the full augmented-assignment chain, early returns in
  nested ifs, raise conditions that are too wide or name the wrong class, a parameter named `max`, and bool returns.
  int64 overflow is found at `INT64_MAX + 1`, `INT64_MIN // -1`, `-INT64_MIN` and `abs(INT64_MIN)`; declared
  overflow is PROVED; math_int does not overflow. Value-returning `or`, truthiness, `True + x`, `**` and `/` are
  all reported UNSUPPORTED (exit 12). No translator unsoundness was found inside the documented subset.
- **Contract review.** It flags an unsatisfiable precondition (also via the int64 domain), contradictory and
  tautological postconditions, a postcondition implied by the precondition alone, dead error clauses and overlapping
  error clauses. The old/new comparison catches precondition strengthening, loss of an invariant after a weakened
  precondition, a weakened postcondition, a dropped error, and a signature change (COMPARISON_UNSUPPORTED, no text
  comparison). An approval for one scope does not cover another.
- **Gate exits.** The gate fails closed with the documented codes and a written reason for: z3 missing (10); a
  missing function, syntax error, missing module, import-time error or parameter mismatch (all 11, each with a
  different message); an unrouted loop (12); MODEL_MISMATCH (13); a 1 ms timeout (14 or 15); a counterexample (16);
  a review error (17); a vacuous precondition (18); a predicate with a free name and an empty contract set (2).
- **Patch-rejection demo.** For `clamp`, the head version passes a plausible unit test but returns `hi+1` at
  `x == hi+1`. The gate accepts the base, rejects the head (exit 16, counterexample `x == hi+1`), and the generated
  regression fails on the head and passes once the base is restored.
- **No text fallback.** An AST audit finds exactly two places that produce PROVED: `_prove_from_unsat`, which asserts
  unsat, satisfiable P and reachable paths, and `ObligationResult.from_dict`, which is the cache. The verdict modules
  import no `re`, `difflib` or `fnmatch`.
- **Cache.** The cache entry is invalidated by changes to the implementation, the contract, a dependency class, the
  z3 version, the Python version, the tool version or the assumptions. Formatting and comment changes keep the entry.
  Failures are never cached and a corrupt cache file is ignored.
- **Structure.** getattr, `getattr(...)()`, call through a variable or parameter, eval, subscript calls, lambdas,
  conditional and try/except imports, star imports and wrapping decorators are all `unresolved`, each with a
  reason code. Calls on parameters are `syntactic`, with candidates that are not claims. A re-export resolves
  correctly, and an alias assigned to a variable is unresolved. Every output says `complete_call_graph: false`, and
  scope lists every unresolved edge in `not_followed`. Ids and hashes stay the same under comments, blank lines and
  re-wrapping, and change only the edited symbol on a body change. The model passes `nesting_dolls.py check`. The
  diff lists true callers with edge kinds (resolved, syntactic, depth 2). It reports unparsable files on either side
  as `unknown_due_to_parse_failure` with status `incomplete`, never as removed or added symbols, and `--strict` exits 3.

## Defects

Each "Test" path is under `tests/acceptance/`.

### V1. CRITICAL: unsound PROVED and a passing gate when the module redefines the function
`find_function` takes the first top-level `def f`, but Python binds the last one. With math_int the gate passes
(exit 0) while the real `f(50)` returns -1. The 200-sample cross-check misses it.
```python
def f(x: int) -> int:
    return max(x, 0)
def f(x: int) -> int:
    if x == 50: return -1
    return max(x, 0)
# contract: post "result >= 0" -> post-1 PROVED, gate exit 0
```
Test: `verify/test_acc_verify_soundness.py::test_proved_matches_the_function_python_actually_binds[redefinition-math_int]`.

### V2. CRITICAL: under int64, PROVED is checked against the AST, not against the function Python runs
`replay.checked_callable` compiles the AST node in a bare namespace (only builtins), so the cross-check never runs
the bound function. Three cases give post-1 PROVED while real `f` returns negatives:
- `f = g` rebinding after the def;
- a module-level `def max(a, b): return a`;
- redefinition (as in V1).

In these fixtures the gate happens to fail anyway, because `no-undeclared-errors` finds an unrelated overflow. With
an overflow-free body the gate would pass.
Tests: `[rebinding-int64]`, `[shadowed_builtin-int64]`, `[redefinition-int64]` in the same test function.

### V3. HIGH: a stale cached PROVED is reused after module-level rebinding
The implementation hash covers only the first def's AST. `dependency_hashes` skips any name that exists in
`builtins`, so a module `max` or `abs` is never hashed. A redefinition, a rebinding, or a change to a shadowing
`max` therefore keeps the cache key, and the gate passes from the cache (exit 0) although real `f(-5) < 0`. For
the rebinding case this bypasses the MODEL_MISMATCH that a fresh run reports.
Test: `verify/test_acc_verify_cache.py::test_stale_proof_not_reused_when_module_rebinds[*]` (3 cases).

### V4. MEDIUM: a signature mismatch can be routed away as UNSUPPORTED
The skill says exit 11 means "signature mismatch". But `parse_function` raises Unsupported before the parameter
check runs. So `def f(x: int) -> bool` against `returns: int`, or `def f(x, y)` against `params: {x: int}`, with
`route: {default: test}` passes with exit 0.
Test: `verify/test_acc_verify_gate.py::test_signature_mismatch_cannot_be_routed_away[*]` (2 cases).

### V5. MEDIUM: false MODEL_MISMATCH for module-defined exceptions under int64
A correct function that raises `Bad(ValueError)`, defined in the same module, gets MODEL_MISMATCH. The int64 replay
namespace has no module globals, so the replay raises NameError. Correct code is rejected.
Test: `verify/test_acc_verify_soundness.py::test_int64_module_exception_class_is_not_a_model_mismatch`.

### V6. LOW: a broken z3 crashes with an uncaught traceback
If `z3.Solver` raises, `run_gate` calls `review_contract` outside its try block. The process exits 1 with a
traceback, not 11, and writes no JSON report. It still fails closed.
Test: `verify/test_acc_verify_gate.py::test_broken_z3_is_a_crash_not_a_pass`.

### V7. LOW: an int64 range tautology is PROVED quietly
Under checked int64, `result >= -2**63 and result <= 2**63-1` constrains nothing, but review checks validity with an
unbounded `result`. The obligation is PROVED and the gate exits 0.
Test: `test_int64_range_tautology_is_flagged`.

### V8. LOW: review misses postconditions that can never apply
If the declared errors cover the whole precondition (`pre x >= 0`, `ValueError when x >= 0`), every postcondition is
vacuous. `check-contracts` reports nothing. `verify` does catch it later as VACUOUS (exit 18).
Test: `test_postconditions_that_can_never_apply_are_flagged_before_code`.

### S1. HIGH: a repo decorator with a "transparent" name is trusted by name
A repo-defined `def cache(fn): return lambda *a: 0` used as `@cache` produces a `resolved` edge to the replaced
function. `_transparent` matches the last dotted name against an allow-list without resolving the decorator.
Test: `structure/test_acc_structure_edges.py::test_user_decorator_named_like_a_transparent_one`.

### S2. HIGH: a star import after a def is ignored
With `def shadowed(): ...` followed by `from pkg.b import *`, the runtime callee is `pkg.b:shadowed`. The tool
reports `resolved` to the local def.
Test: `test_star_import_after_def_rebinds_the_name`.

### S3. MEDIUM: an instance attribute that shadows a method is ignored
`self.go = other` in `__init__`, then `self.go()`, gives `resolved` to `Inst.go`. The `attr_write` is recorded but
not used.
Test: `test_instance_attribute_shadows_method`.

### S4. MEDIUM: a monkeypatched module attribute is ignored
`pkg/patcher.py` does `pkg.c.helper = fake`, yet `pkg.c:run -> helper` is reported `resolved`.
Test: `test_monkeypatched_module_attribute`.

### S5. MEDIUM: a self-call with a known override in the repo is resolved to the base only
This behaviour is documented as a caveat. But `Sub.step` is in the scanned tree, and the edge carries no candidate
or flag, so scope and diff never reach `Sub.step` through it.
Test: `test_self_call_with_override_in_repo`.

### S6. MEDIUM: the diff omits readers of a changed module constant
After `LIMIT = 10 -> 20`, only `pkg.c:<module>` is listed. `check()`, which reads LIMIT and is in the extractor's
`reads`, is not listed, and the status is still `complete_for_parsed_files`.
Test: `structure/test_acc_structure_model_diff.py::test_module_constant_change_lists_its_readers`.

### S7. MEDIUM: the diff omits callers of a function whose returned closure changed
Changing the body of `make.<locals>.inner` leaves `make`'s hash unchanged (nested defs become placeholders), and
`use_make()` is not listed.
Test: `test_closure_change_lists_callers_of_the_enclosing_function`.

### S8. LOW: model citations drift after a form feed or other `str.splitlines` separators
`model._Files` (and `nesting_dolls.py check`) split lines with `str.splitlines`, which also breaks at `\x0c`,
` ` and similar. ast line numbers do not. After a form-feed page break, `third` (span 9-10) is cited as
`lines 1-12`, the whole file, and the check still passes.
Test: `test_symbol_citations_are_the_symbols_own_span[True]`.

## Observations (not counted as failing tests)

- **The cache is trusted.** A hand-written entry under the right key (`gate.cache_key` is public) is accepted as
  PROVED without z3. If an implementer can write `.sf/proofs.json`, they can forge a pass. Consider signing the
  cache or keeping it outside the implementer's write scope.
- **Routing to tests is enough to pass.** `check_method: test` on a function the solver could handle gives exit 0
  with zero PROVED obligations. The report shows UNSUPPORTED with the route, as the skill documents, but this is
  only as good as the routed test.
- **Undocumented reason codes.** `getattr_result`, `computed_callee`, `call_of_module`, `import_cycle`,
  `bad_relative_import` and `undefined_name` are emitted but not listed in `skills/structure-scan/SKILL.md`.

## What I could not test

- Exponential integer growth in math_int replay, such as repeated `x = x * x`, could exhaust memory during the
  200-sample cross-check. I did not run it because of the resource rules.
- `git:<rev>` diff sources, z3 versions other than 5.3.1, and real UNKNOWN (as opposed to TIMEOUT) answers.
- Whether `nesting_dolls.py build` and the browser Check button work: I ran only `check`.
- Very large repositories and the 512-path limit beyond a smoke level.
