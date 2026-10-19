# QA loop

`python -m factory.qa` (stdlib + pyyaml) holds QA runtime state, the bounded retry and escalation decision,
leak-checked feedback and regression proposals. It never calls a model: the orchestrator launches agents using
the decisions. Slice documents stay owned by `factory.slices` (`docs/slices/<id>/`, see `slice-format.md`).

Global options: `--root R` (project root, default `.`), `--slice ID`.

## Exit codes
0 ok; 1 error or audit failure; 2 usage error (including a bad policy, or `feedback` with no protected paths
configured); 3 leak check rejected, or protected material too large to check; 4 refused by the slices package.

## State: `.sf/slices/<id>/`
- `state.json`: `schema_version`, `slice`, `criteria`, `verified`, `proposals` (signature to path), `reviewer`
  (signature to `{verdict: amended|unresolved, note, at_len, at}`), `status` (`active|stuck|blocked|accepted`),
  `waits_on`, `feedback_count`, and `attempts_len/head`, `failures_len/head` (length and head hash of each log).
- `attempts.jsonl`: one line per gate run: `seq, kind, outcome, signature, case, criterion, tier, duration_s,
  tokens, cost_usd, commit, at, prev, hash` (`error_norm` on environment lines). `outcome` is `pass`, `fail`
  (a counted attempt), `suspect` (failure awaiting flake reruns), `flake` (rerun passed, not counted) or
  `environment` (not counted; gate stays failed until a clean run).
- `failures.jsonl`: `seq, signature, case, criterion, outcome (fail|suspect), error_norm, at, prev, hash`.
- `qa-feedback/<n>.md`, `regression-proposals/<signature>.md` (append-only).

Both logs are hash-chained (`hash = sha256(prev + canonical JSON of the line)`), and `state.json` records the
length and head. `audit` reports edited lines, removed or inserted lines, truncation and replaced history. Limit:
someone who rewrites the logs and `state.json` together is not detected; commit or print `attempts_head` elsewhere
to anchor it. Counters are derived from the log, never from `state.json`. `next` refuses to run on a failed audit.

## Signature
`sha256(case-or-criterion id, NUL, normalized error)[:16]`. Normalization masks timestamps, UUIDs, hex addresses
and ids, absolute and relative paths, and numbers, and collapses whitespace.

## Policy `.sf/policy.yaml` (all keys optional)
```yaml
attempts_per_signature: 4
tiers: [sonnet, sonnet, sonnet, sonnet]   # model names per attempt (names only; no model is called here)
allow_non_default_models: []          # explicit opt-in: any non-sonnet name in tiers must be listed here
slice_attempt_cap: 10
budget: {tokens: null, cost_usd: null} # caller reports tokens/cost per record
flake_reruns: 1
environment: {patterns: [...], wait_max: 5}   # ENOSPC, OOM, killed by signal, timeouts, port in use, missing tool
escalation: {min_samples: 5, escalate_below: 0.2, hold_above: 0.8}
```
Sonnet-only by default: any other model in `tiers` is rejected with a clear error unless `.sf/policy.yaml` also lists
it under `allow_non_default_models`. `python -m factory.qa policy` prints the effective values, including
`tiers_flagged`, which marks each non-sonnet entry `(opt-in)`. Unknown keys are an error.

## Decisions (`next`)
Order: already blocked, `environment_wait` (more than `wait_max` consecutive: `mark_blocked`),
`rerun_for_flake`, `accept` (gate passed and every criterion verified), `propose_regression` (a signature failed
twice or more with no proposal yet), then caps (signature, slice, budget): `hand_to_reviewer`, or `mark_blocked`
after an `unresolved` verdict recorded since the last failure (`waits_on` names the reviewer note). Otherwise
`retry_same_tier` or `escalate_model` (only when the next tier is a different model; with the all-sonnet default it is
always `retry_same_tier`, with a `diagnosis` string attached: signature, criterion, failure count, last normalized error) with the tier from the ladder position (failures of this signature), adjusted
by measured per-tier success from `stats`. An `amended` verdict gives the signature (and slice window) a fresh
budget while history stays. `--apply` persists `stuck`, `blocked` or `accepted`.

## Commands
`init`, `record`, `next [--apply]`, `feedback`, `regression-propose`, `verify-pass`, `reviewer-verdict`,
`unblock`, `stats`, `audit`, `policy`. `verify-pass TASK` runs `python -m factory.slices verify ... --role qa`
and is refused (exit 4) when the slices package rejects; the slice's `verification.json` stays the single record.

## Leak check
`feedback` and `regression-propose` check text against `paths.eval` and `paths.held_out` from
`.factory/profile.yaml` plus `--protect`. A match is a verbatim line of 16 or more characters, any 40-character
window (whitespace-normalized), or a protected file path. Memory is bounded by the feedback text (at most 1 MB);
protected material above 8 MB or 5000 files fails closed with "protected material too large to check".
With no protected paths configured the command refuses unless `--allow-no-protect` is given.

## Written-file hardening
Signatures used as file names or headers must match `^[A-Za-z0-9_-]{1,64}$` (exit 2 otherwise). The leak check runs
over the complete content about to be written: the whole `qa-feedback/<n>.md`, the header plus section of each
regression proposal, and the `reviewer-verdict` note (persisted into `state.json`). Raw gate error text recorded
by `record` is QA-private (normalized into the logs, never sent to the implementer) and is not leak-checked.
