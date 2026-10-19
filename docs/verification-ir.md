# Verification IR and semantic choices

`factory/verify` is a deliberately small verifier for **pure Python functions over `int` and `bool`**. This
document is the contract for what it models. Everything it does not model is reported `UNSUPPORTED` with a
reason and must be routed to another check (see `skills/contract-verify/SKILL.md`).

Pipeline: contract (YAML) -> predicate IR; implementation source -> function IR -> symbolic paths -> z3.

## 1. Intermediate representation (`factory/verify/ir.py`)

Typed, immutable dataclasses. Every expression has a type, `int` or `bool`.

Expressions: `Const(value, ty)`, `Var(name, ty)`, `Result(ty)` and `Old(name, ty)` (predicates only),
`Unary(neg|pos|not)`, `Bin(add|sub|mul|floordiv|mod)` (int x int -> int), `Cmp(eq|ne|lt|le|gt|ge)`
(int x int, or bool x bool for eq/ne), `BoolOp(and|or, operands)` (bool operands only), `IfExp(test, a, b)`,
`Call(abs|min|max, args)`.

Statements: `Assign(name, expr)`, `If(test, body, orelse)`, `Return(expr)`, `Raise(exception_name)`.
`Func(name, params, returns, body)`.

The same expression parser serves implementation bodies and contract predicates, so both sides use one
semantic model. Chained comparisons `a < b < c` become `a < b and b < c`.

### Supported subset of implementations

`def f(p: int, q: bool) -> int:` with annotated `int`/`bool` parameters; local assignment, augmented
assignment (`+= -= *= //= %=`); `if/elif/else`; `return`; ternary; arithmetic `+ - * // %`; unary `- + not`;
comparisons; `and`/`or`/`not` on bools; the builtins `abs`, `min`, `max`; `raise ExcName(<constant args>)`.
A docstring and `pass` are ignored.

### UNSUPPORTED (never approximated)

Each yields a specific reason string: loops (`for`/`while`), calls to anything but `abs/min/max`, attribute
access, subscripts, comprehensions, `try/except`, `with`, lambdas, nested defs, floats and true division,
`**`, bit operators, strings/None/containers, truthiness of ints in `if`/`not`/`and`/`or`, mixed int/bool
arithmetic or comparison, globals or free variables, mutation of attributes/items, `assert`, a bare
`return`, a path that can fall off the end (implicit `None`), variables possibly unbound on a path, a
return/annotation type that disagrees with the contract, methods and `*args/**kwargs`, and more than 512
paths. Anything else not listed also lands here: the parser is an allow-list.

## 2. Semantics

### Integers

* `math_int`: unbounded mathematical integers (z3 `Int`), identical to Python ints.
* `int64`: parameters are constrained to `[-2^63, 2^63-1]`, and **any arithmetic result outside that range is
  an `OverflowError` outcome** (checked arithmetic). The spec asked us to document the choice between
  mathematical integers and 64-bit bit-vectors with overflow: we chose *checked* int64 on top of z3 `Int`
  rather than wrap-around bit-vectors because (a) an overflow is almost always a bug the contract author must
  decide on, so it should surface as an explicit undeclared-error obligation rather than as a silently wrong
  `result`; (b) predicates stay mathematical and readable; (c) the replay of a counterexample on real Python
  can reproduce it exactly (see 3). Wrap-around is not modelled; a function that relies on it is outside the
  model. Integer literals outside the range are `UNSUPPORTED` under `int64`.
  Overflow is checked after `+ - * // %`, unary `-` and `abs`, in evaluation order.

### Floor division and modulo

Python semantics are modelled exactly, not z3's Euclidean `div`/`mod` and not C truncation:
`a // b = (a div b) if b > 0 else ((-a) div (-b))`, `a % b = a - b*(a // b)` (result has the sign of `b`).
This is checked against Python on random programs in `tests/test_verify_semantics.py`.

### Division by zero

`a // 0` and `a % 0` are an **error outcome** `ZeroDivisionError`, not an undefined value. Faults are
evaluated in order and short-circuiting guards them: `b != 0 and a // b > 0` never faults.

### Execution

Symbolic execution forks at every `if` (no merging). A `Path` is `(condition, outcome)` with outcome
`return value` or `raise ExcName`; the conditions of all paths partition the input space (checked by a test).
Exceptions are matched by **class name**.

## 3. Verification conditions (`factory/verify/solve.py`)

Let `P` be the conjunction of preconditions and the parameter domain, `T_impl` the disjunction over return
paths of `cond_i AND result = v_i`, and `Q` a postcondition or invariant. A predicate that faults (division by
zero) is **false**.

| Obligation | Violation query (must be UNSAT to be PROVED) | Non-vacuity required |
|---|---|---|
| postcondition / invariant | `P AND T_impl AND NOT Q` | `P` satisfiable; some return path reachable under `P` |
| error `E when W` | `P AND W AND NOT (some raise-E path)` | `P AND W` satisfiable |
| `no-undeclared-errors` (implicit) | `P AND (some raise path whose exception/condition is not declared)` | `P` satisfiable |

Verdicts: `PROVED` (violation query unsat and non-vacuous), `COUNTEREXAMPLE` (sat, **and replayed**),
`UNSUPPORTED` (reason + declared route), `UNKNOWN`, `TIMEOUT`, and `MODEL_MISMATCH`.
Contract review also flags (before code) int64 range tautologies (the result is in range by construction) and
postconditions that can never apply because declared errors cover every allowed input.
Vacuous results (P unsatisfiable, unreachable paths, dead error clauses) are never `PROVED`; they are
reported as `UNKNOWN` with `vacuous: true` and fail the gate.

**Replay.** For every sat model the *real* function is executed on the concrete inputs (for `int64` a copy of
its AST with a range check around every arithmetic operation, still ordinary Python) and the obligation is
evaluated by an independent interpreter in `replay.py` that does not use z3. If the real run does not violate
the obligation the verdict is `MODEL_MISMATCH` (a translator bug) and the gate fails.

**Cross-check of PROVED.** After solving, every `PROVED` obligation is tested on the models of `P` plus 200
seeded random and boundary inputs against the real function; a violation downgrades it to `MODEL_MISMATCH`.
This is a safety net against translator unsoundness, not a proof certificate.

**No syntactic fallback.** `PROVED` is created in exactly one function (`_prove_from_unsat`) which requires a
z3 `unsat`. `solve`, `irgen`, `consistency` and `gate` import no `re`/`difflib`; tests enforce both.

## 3a. Binding: verifying the function Python actually runs

The translator reads the AST of a `def`; soundness needs that def to be what the name is bound to at run time.
Before anything is proved, `loader.check_binding` statically refuses (gate reason `BINDING`, exit 19, obligations
reported `UNKNOWN`, never `UNSUPPORTED`) any module where the target name is bound other than exactly once at
module scope (a second `def`, `f = g`, an import, a conditional def, `del`, a `global f` in some function) or that
has a star import. If the function calls `abs`/`min`/`max` and the module (or the function itself) rebinds that
name, the model of the builtin would differ from real execution: refused with reason `MODEL_MISMATCH` (exit 13).
A parameter that merely happens to be called `max` and is never called is fine. The module is then executed once
and the symbol resolved from that real namespace; its `__code__` must match the parsed def. Under `int64` the
range-checked copy is compiled *inside a copy of that namespace* (so module-defined exception classes resolve)
and wherever it completes without overflow its outcome must equal the real bound function's, otherwise the
outcome is `diverged` and the obligation becomes `MODEL_MISMATCH`. Not detected: runtime monkeypatching after
import and `builtins.x = ...`; that is an assumption.

Signature (parameter names, annotations, return annotation, `*args`/`**kw`/defaults-free shape) must equal the
contract: any mismatch is exit 11 and can never be routed away.

## 4. Recorded assumptions

Every report lists the contract's own assumptions plus the implicit ones: annotated parameter types are
honoured; the function is pure and terminating; `abs/min/max` and exception names are the builtins; exceptions
match by name; predicates read original argument values (`old(x) == x`); a faulting predicate is false; the
integer semantics above; z3 is trusted (no proof certificate is checked). The proof cache key includes all of
them.

## 5. Hashes and cache

* implementation hash: SHA-256 of the function's `ast.dump` (comments and formatting do not change it);
* dependency hashes: same-module definitions the function references by free name (functions, classes,
  assignments, imports), else `unresolved`; builtins are covered by the recorded Python version;
* contract hash: SHA-256 of the canonical JSON of the contract without `observed`/`description`.

* module hash: SHA-256 of the whole module AST, so any module-level change (a redefinition, a shadowing helper,
  a constant the function reads) invalidates every entry for that module; comments/formatting do not.

Cache key = hash of (implementation, dependencies, module, contract, z3 version, Python version, tool version,
assumptions). Cache hits are labelled (`PROVED (cached)`, `"cached": true`). The cache is for local speed only:
a hand-written cache file can forge a pass, so release/CI runs use `--no-cache`. Only fully passing results (all `PROVED` or routed `UNSUPPORTED`) are stored; a corrupt cache is
ignored. Nothing is stored for counterexamples, unknown, timeouts or mismatches.

## 6. Known limits

Only `int`/`bool` pure functions; no loops/recursion/calls (so no inductive invariants); no floats; no
state, heap, I/O or concurrency (declared in the contract, routed to tests/integration/telemetry); exceptions
matched by name; z3 timeouts on nonlinear integer arithmetic are expected and fail the gate; module top-level
code of the implementation is executed during replay.
