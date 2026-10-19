Read this file only when the Unity gate applies (see "Verification gate" in SKILL.md): the user asked for Unity verification AND the code under spec is Python or Go. Unity's parser only supports those two languages.

# Unity integration (optional gate)

`unity` (kaushalbalagurusamy/unity) is the intended downstream verifier: lower the implementation to Unity-IR, compute ΔS against this spec, and reject one-way-door regressions automatically. Current state (verified against unity `f941fed`, Sept 2026 — re-check if the repo has moved on), so expectations are right:

- The **format** (`compiler/schema.py`: `SymbolDeclaration`, `Contract`, `Parameter`, `SystemAttributes`, `Precondition`, `ExecutionStep`, `Postcondition`, `CausalLink`, `UnityModule`) is stable and is what this skill's contract files mirror. Field-level mapping is in `reference/contract-format.md`.
- The **delta engine** (`SemanticDeltaEngine().compute_delta(pre_module, post_module)` in `compiler/delta.py`) works on any two `UnityModule`s you construct by hand. Know what it does and doesn't catch, because the skill has to cover the gaps manually:
  - Clauses are matched **by ID** (`P2`, `Q1`), so renumbering produces false violations. IDs are permanent; retire, never reuse.
  - Flags as ONE_WAY_DOOR: concurrency change, pure → impure, a P or Q ID removed, a same-ID precondition that SMT shows is *strengthened*, any removed symbol.
  - Flags only as CONTRACT_SHIFT (**not** blocked): a same-ID precondition *relaxed* (e.g. `amount > 0` → `amount >= 0`), and a *newly added* precondition, even though that is a strengthening that breaks callers. Postcondition edits are plain string comparisons with no SMT.
- `SMTContractProver.verify_implication(old, new)` handles exactly two regex shapes: `<var> <op> <int literal>` and the literal `self.balances[account_id] <op> <var>`. Anything else (`amount <= limit`, `a > 0 and b < 10`, other dict names, helper predicates) falls back to string equality and reports *any* textual change as a violation. Useful for simple integer bounds only.
- The **extractor** (`compiler/extractor.py`) is still fitted to `examples/ledger`: hard-coded preconditions, execution steps, postconditions, error names, and `@ledger.` symbol prefix. Lowering an unrelated class (e.g. an `Inventory.reserve` that mutates under a lock) yields `@ledger.Inventory.reserve`, `purity: pure`, `Error[]`, the precondition `account_id in self.balances`, and no postconditions. Only the causal resolver is pluggable (`CausalGraphResolver`). Treat "lower the implementation and diff against spec" as a manual step.
- `compile_source(path)` and `compute_semantic_delta(pre_path, post_path)` take **file paths** and run the extractor on both sides, so neither can compare against a spec today.
- **Performance claims:** `benchmarks/scale_sweep.py` times Tree-sitter parsing only (it constructs the extractor and emitter but never calls them). The README's "301,000 lines/second full lowering pipeline" and the 301,014 / 355,577 lines/s and 0.392 ms figures in `docs/PERFORMANCE_AND_SCALABILITY.md` are not produced by any script in the repo. Don't cite them as end-to-end lowering performance.

When the extractor generalizes, the intended gate becomes: build `spec_module` from `contracts/`, lower the implementation to `impl_module`, run `SemanticDeltaEngine().compute_delta(spec_module, impl_module)`, and block on `has_one_way_doors`, plus the manual checks above for added preconditions and invariant-protecting relaxations.

## Re-checked 2026-10-05 (unity `f941fed`; first three bullets run in a scratch venv, the fourth read from source only)

- **Callers of a changed symbol are not available.** The only caller source is `CausalGraphResolver.resolve_called_by`, and the default `LexicalCausalResolver` looks the method name up in a fixed three-entry map (`get_balance`, `deposit`, `withdraw`) and returns `@api.default` for anything else. On a two-method class where `deposit` calls `helper`, unity reported `helper` as `CALLED_BY @api.default`. A real resolver (SCIP, LSP, or a grep-based one) has to be supplied through the protocol.
- **`VerificationStatus` has three values:** `DECIDABLE_SMT_PROVED`, `COUNTEREXAMPLE_FOUND`, `CONSERVATIVE_SYNTACTIC` (the last for predicates outside the decidable theory).
- **The extractor is still fitted to the ledger example.** A non-ledger module came out as `@ledger.Store.*`.
- **The software factory's governance gate fails open.** In `factory/governance.py`, an import failure sets `UNITY_AVAILABLE = False` and skips Unity, and an exception during lowering is recorded as a `TWO_WAY` / `LOCAL_REFACTOR` risk that does not require an ADR. Only a regex scan for destructive SQL still runs.
