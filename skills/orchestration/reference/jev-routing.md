# Routing with TypeSafe Jev

> Reference for the orchestration skill. This replaces the former sf-jev-dispatcher skill, which called the wrong endpoint, used a floating model alias, and asked Jev to detect defects. **Status: policy file and client exist (software-factory repo, `factory/routing/`), in shadow mode only, not wired into anything.** Do not give Jev authority until shadow-mode data has set the thresholds.
>
> **Verification status.** The API surface, latency and cost figures come from `gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md`. On 2026-09-24 one live call confirmed the wire format: `POST /api/alpha/decisions` with `{model, state, questions}` works when each question carries an `instructions` field (a `question` field is rejected with HTTP 400); the call took about 250 ms and cost about $0.00002, and the response echoes a dated model snapshot for the pinned name. Calibration and thresholds are still unmeasured. Test fixtures carry the observed response shape with illustrative probabilities.

## What Jev is for

Jev is a sub-second classifier that answers a fixed question from a state description and returns per-option probabilities. Use it to **route work**: pick a model tier for a task, pick an owner for a CI failure, judge whether a milestone is ready for independent review. Do **not** use it to **detect defects** (weakened assertions, dangerous commands, one-way doors). It has not been shown to do that well, and those checks belong to deterministic rules and to the `one-way-door` skill.

## Who owns what

The harness owns the questions, thresholds and routing. The skill only explains them. Three pieces:

1. **One versioned policy file** (`factory/routing/jev-policy.yaml` in the software-factory repo). For every decision point (model tier, CI-failure triage, milestone readiness) it holds:
   - the `state` fields allowed in the request;
   - the questions, with every option's criterion text written as if briefing a new hire;
   - an explicit **`unknown`** option in every choice question;
   - the mapping from category to action;
   - three bands with thresholds: **act** (probability high enough to route automatically), **flag** (route, but record for review), **human** (ask a person);
   - the deterministic rules that run first;
   - a `policy_version`.
   Wording changes in this file are behavior changes and go through review like code.
2. **A small client** (`factory/routing/jev_client.py`). It calls `POST https://openrouter.ai/api/alpha/decisions` with `{model, state, questions}` and reads `{model, answers, usage}`. The model is pinned to **`typesafe/jev-1.13`**, never a floating alias such as `~typesafe/jev-latest`. The key comes from `OPENROUTER_API_KEY` in the environment. The transport timeout is about 800 ms with no retry, and any fault falls back to the deterministic rule. It logs the state digest, probabilities, policy version and outcome so thresholds can be calibrated. Tests use recorded responses only; no live calls in tests.
3. **This prose.** When to ask, and the rules below.

The old `/chat/completions` call with a JSON-schema enum is rejected by this API; do not copy it.

## Rules

- **Deterministic rules run first.** Ask Jev only when no rule decides. Seed rules carried over from the old skill:
  - traceback mentions `SyntaxError` or `ImportError` → mechanical tier (Haiku-class);
  - `AssertionError` → implementation tier (Sonnet-class);
  - `Timeout` or `Deadlock` → specialist tier (Opus-class);
  - milestone evidence contains any `FAIL` or `SKIP` → not ready for independent review.
- **Shadow mode first.** Log what Jev would have chosen next to what was actually chosen. Set the act, flag and human thresholds from our own labelled past tasks, not from defaults.
- **State is untrusted text that leaves the machine.** Redact secrets and personal data before sending. The documented request limit is 32,000 tokens (a 64K figure elsewhere is unreconciled).
- **Model tiers live in the policy file, not in enum names.** A model upgrade should be a data change.
- **Fault means fallback.** Timeout, HTTP error, malformed answer or an `unknown` answer all fall back to the deterministic rule or to a human.

## Decision points (as written in the policy file)

| Decision | Question | Options (each with an `unknown`) | Action |
|---|---|---|---|
| Model tier | What capability tier does this task need? | mechanical single-file work, bounded multi-file implementation, cross-cutting or persistent-deadlock work | Haiku, Sonnet, Opus class |
| CI failure owner | What is the primary root cause of this failure? | syntax or import, assertion mismatch, stale mock or fixture, race or timeout, environment or dependency | mechanical, implementation, or specialist tier per the rules above |
| Milestone readiness | Is this milestone ready for independent review? | ready, incomplete local evidence, blocked on a product decision | ready: build the review packet; otherwise return to the implementer |

## Sequencing

The assessment recommends the Co-Pilot routing tracer bullet come first and the factory dispatcher follow. The policy file and client are written; wiring the client into anything waits for a labelled set of past tasks.
