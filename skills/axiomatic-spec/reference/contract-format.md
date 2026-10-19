# Contract format

One file per symbol in `spec/<feature>/contracts/<symbol-slug>.uir.md`. The format is language-agnostic; its fields happen to mirror Unity-IR (see the mapping at the bottom, relevant only when the Unity gate applies).

```
SYMBOL: @<pkg>.<module>.<Class>.<method>          # canonical ID; Class omitted for free functions

CONTRACT:
  params:
    - name: <snake_case>   type: <Str|Int64|Float64|Bool|<Domain type>>
  returns: Result<<Type>, Error[<Err1> | <Err2>]>  # every possible error named; none hidden in "Error"
  purity: pure | impure(IO) | impure(StateMutation:<target>)
  concurrency: lock_free | exclusive_lock(<mutex>) | atomic | csp_channel(<chan>)

PRECONDITIONS:                                    # what must hold on entry; violating one → a named error, never UB
  P1: <expr>
  P2: <expr>

EXECUTION_LOGIC:                                  # optional in spec; required in brownfield S_pre extraction
  1. <ACQUIRE|QUERY|EVALUATE|MUTATE|RELEASE|RETURN>: <step>   [ASSERT <expr> ELSE <ErrName>]

POSTCONDITIONS:                                   # what holds on successful return; RESULT names the return value
  Q1: <expr>
  Q2: <expr>

ERROR_MODEL:                                      # for each error: the precondition it maps to, and the state guarantee on failure
  <ErrName>: when <P-id or condition>; state unchanged | partial: <what changed>

CAUSAL:
  CALLED_BY: @<symbol>, ...
  CALLS:     @<symbol>, ...

INTENT: <one or two sentences of controlled natural language: who calls this, why, and what they can rely on>
```

## Writing good P/Q clauses

- Use plain expression syntax over params, `self.<state>`, and `RESULT`. Keep integer/boolean arithmetic simple (`amount > 0`, `self.balances[account_id] >= amount`) so a test can check each clause directly.
- Postconditions reference pre-state explicitly when needed: `self.balances[account_id] == old(self.balances[account_id]) + amount`.
- Every error in `returns` must appear in `ERROR_MODEL` with a state guarantee. "Throws on failure" with unspecified state is the single most common source of undetectable bugs.
- If a clause needs a helper predicate (`isValidId(x)`), define it once in `domain.md`.
- **P/Q IDs are permanent.** Tests, ADRs and diff tools refer to clauses by ID, so renumbering `P3 → P2` after deleting a clause makes it look like P2 changed, P3 changed and P4 was removed. When a clause is deleted, retire its ID (leave a gap); new clauses take the next unused number.

## Example (abbreviated)

```
SYMBOL: @ledger.Ledger.withdraw

CONTRACT:
  params:
    - name: account_id   type: Str
    - name: amount       type: Int64
  returns: Result<Int64, Error[NotFound | InvalidAmount | InsufficientFunds]>
  purity: impure(StateMutation:self.balances)
  concurrency: exclusive_lock(self.mu)

PRECONDITIONS:
  P1: isValidId(account_id)
  P2: amount > 0
  P3: account_id in self.balances
  P4: self.balances[account_id] >= amount

POSTCONDITIONS:
  Q1: self.balances[account_id] == old(self.balances[account_id]) - amount
  Q2: self.balances[account_id] >= 0
  Q3: RESULT == self.balances[account_id]

ERROR_MODEL:
  InvalidAmount:     when ¬P2; state unchanged
  NotFound:          when ¬P3; state unchanged
  InsufficientFunds: when ¬P4; state unchanged

CAUSAL:
  CALLED_BY: @api.handlers.execute_withdrawal

INTENT: Debits a funded account atomically; callers can rely on the balance never going negative and on no partial writes under any error.
```

## Mapping to Unity's schema (only when the Unity gate applies)

| Spec field | `schema.py` |
|---|---|
| SYMBOL | `SymbolDeclaration.symbol_id` |
| CONTRACT.params / returns | `Contract.params: [Parameter(name, type_spec)]`, `Contract.returns: str` |
| purity / concurrency | `Contract.systems: SystemAttributes(concurrency, purity, resource=None)` |
| PRECONDITIONS | `SymbolDeclaration.preconditions: [Precondition(id, expr)]` |
| EXECUTION_LOGIC | `SymbolDeclaration.execution_logic: [ExecutionStep(step_num, action, assert_expr, assert_throw)]` |
| POSTCONDITIONS | `SymbolDeclaration.postconditions: [Postcondition(id, expr)]` |
| CAUSAL | `SymbolDeclaration.causal_topology: [CausalLink(kind, target_symbol)]` |
| (optional) `resource: owned \| mutable_borrow(T) \| shared_borrow(T)` | `SystemAttributes.resource` — add to CONTRACT only when ownership matters |
| ERROR_MODEL, INTENT | not in schema yet — kept in the spec for humans and tests |
