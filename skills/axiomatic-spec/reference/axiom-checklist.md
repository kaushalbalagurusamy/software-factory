# Axiom checklist and rewrite patterns

Run every requirement through this. The goal is that a coding agent cannot satisfy the requirement with a wrong implementation, and cannot pass the test by editing the test.

## The six checks

| # | Check | Fails when | Fix |
|---|---|---|---|
| 1 | Decidable | Uses adjectives (fast, secure, graceful, intuitive, scalable, robust) or "should handle" | Replace with a condition + expected outcome |
| 2 | Observable | No named assertion/metric/log that would show violation | Add the signal; if none exists, ask whether the requirement is real |
| 3 | Attributed | No symbol or state named | Attach `@symbol`; global invariants name the state (`∀ x ∈ self.balances`) |
| 4 | Falsifiable independently | Test would be written by the implementer, or asserts on implementation details | Derive test from P/Q only; lock it behind an ADR |
| 5 | Quantified | "Low latency", "many users", "large files" | Number + unit + percentile + condition (p99 < 200ms at 1k RPS) |
| 6 | Independent | Restates or is implied by another axiom | Merge or delete; keep the stronger one |

## Rewrite patterns

**Vague quality → contract clause**
- "Transfers should be safe" → `Q: sum(self.balances) == old(sum(self.balances))` on `@ledger.Ledger.transfer`; `concurrency: exclusive_lock(self.mu)`.
- "Handles bad input" → enumerate the bad inputs as `¬P_i`, each mapped to a named error with `state unchanged`.
- "Fast search" → `p95 latency of @search.query < 150ms for index size ≤ 10M docs, measured at the handler` + telemetry hook.
- "Idempotent" → `Q: calling f(x) twice yields the same state as calling f(x) once`, plus the idempotency key named as a precondition.

**Aspirational → decidable or deferred**
- "Scales to millions of users" → either a concrete load target with a measurement, or moved to `open-questions.md` as "what load do we commit to for v1?".

**Implementation detail masquerading as requirement**
- "Use Redis for the cache" → is it a one-way door (data shape, TTL semantics other systems depend on)? If yes → ADR. If no → remove from spec; it's the implementer's choice.

**Negative space**
- Every "must" implies a "must not". Write the important ones: `@auth.session.refresh` must NOT extend a session past `absolute_expiry`. Negative axioms are the ones reward-hacked implementations violate first.

## Tests derived from contracts

For each contract, mechanically:

1. **Happy-path example** per postcondition: construct a state satisfying all P, call, assert each Q.
2. **Negative example** per error in ERROR_MODEL: construct a state violating exactly one P, call, assert the named error AND the state guarantee (usually unchanged).
3. **Property sketch** per global invariant: generate random valid operation sequences; assert the invariant after every step. Write it as a hypothesis/QuickCheck-style stub even if the harness isn't wired yet.
4. **Concurrency probe** if `concurrency` is anything but `lock_free`: N concurrent calls; assert Q holds and the invariant holds; this is the test that catches lock removal.

Put these in `spec/<feature>/tests/` with a header comment: `# Spec-derived. Do not edit without an ADR. Hash: <sha256 of contract file>`. The implementer's job is to make these pass; changing them is a governance event, not a code change.

## Telemetry mapping

For each global invariant and each one-way-door contract, one row in `telemetry.md`:

| Axiom | Production signal | How measured | Alert condition |
|---|---|---|---|
| `∀ a: balance(a) ≥ 0` | `ledger_negative_balance_total` counter | Assertion at end of every mutating op emits on violation | `> 0` in any window |
| `@ledger.withdraw` p99 < 200ms | `withdraw_latency_ms` histogram | Handler-level timer | p99 > 200ms for 5m |

An axiom with an empty "Production signal" cell is flagged in the summary: it's specified but unmonitored, and will drift.
