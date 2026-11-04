---
name: spec-writer
description: >-
  Use this skill at the very front of the software factory, before decomposition, research, or any
  developer-facing planning, whenever the user brings a vague idea, a one-line feature request, a
  stakeholder's verbal ask ("we want to build X", "product wants Y", "can we add Z"), or a rough
  conversation, Slack thread, or meeting recap and needs it turned into a business-facing SPEC.
  Triggers include: "write a spec for...", "write a PRD for..." when no spec exists yet, "turn this idea
  into requirements", "help me scope this before I bring it to eng", "our CEO/stakeholder said X, what
  does that actually mean", or any request to work out who a feature is for, what problem it solves,
  what success looks like with numbers, or what is out of scope before anything has been written down.
  The spec fixes the terminal requirements and their targets (T1, T2, ...) in the business's own terms;
  it interrogates the idea like a product manager would, proposes quantified targets instead of
  accepting adjectives, marks anything it supplied itself as `[proposed]`, and writes real open
  questions rather than inventing answers. It does NOT choose architectures, decompose requirements
  into research questions (biz-decomposer), write the developer-facing PRD with work units and file
  scope (prd-writer), or write axioms, contracts, ADRs, or tests (axiomatic-spec).
---

# Spec Writer

## What this is for

Most product work drifts before a single axiom or line of code exists, because nobody turned the stakeholder's sentence into a document with edges. "We want an AI that helps nurses" is not a target — it doesn't say who, what problem, what done looks like, or what's explicitly excluded. Handed straight to `biz-decomposer`, to research, or to a coding agent, that vagueness just gets rediscovered mid-build, at far higher cost than it would have taken to ask up front.

This skill owns the business-facing **spec**: the first document in the build loop and the one that fixes the terminal requirements (T1, T2, ...) and their targets. It takes the raw idea, however rough, and interrogates it until the spec can be handed to `biz-decomposer` without re-asking the same basic questions. Later stages treat the terminal requirements and targets as fixed: research serves them and never edits them. The developer-facing PRD (work units, file scope) is a different document, written later by `prd-writer`.

## The bar for a spec claim

A spec claim doesn't need to be a formal pre/postcondition, but it does need to survive contact with a skeptical engineer. Every goal, success metric, and constraint that survives this process must be:

1. **Concrete** — no unquantified adjective (fast, intuitive, secure, scalable, delightful, seamless) stands alone as a requirement.
2. **Attributed to a real user** — a persona and a situation, not "users" in general.
3. **Falsifiable in principle** — someone could look at the shipped product and say yes or no to whether the goal was met.
4. **Marked honestly** — anything this skill proposed rather than the stakeholder confirmed carries `[proposed]` and a matching line in Open Questions.
5. **Bounded** — every goal has a corresponding non-goal or scope line stating what it does not cover.

If a requirement can't clear this bar in one pass, don't force it — write it to Open Questions with the exact question that would resolve it, and a `[proposed]` best guess if one is useful. A spec with honest open questions beats one with hidden assumptions.

## Workflow

1. **Capture the raw ask verbatim.** Don't paraphrase away the vagueness yet — quote the actual line ("nurses need an AI to help them"), and note who said it and in what context (a stakeholder ping, a backlog ticket, a meeting recap, a pasted Slack thread). That context matters later for who should confirm an open question.
2. **Interrogate the idea.** Work through `reference/interrogation-checklist.md`: who is this for (a named persona, not "users"), what problem or moment does it address, what does success look like (a number), what's explicitly out of scope, and what are the hard constraints (regulatory, technical, timeline, budget/team). For every vague word, propose a concrete value or answer, mark it `[proposed]`, and ask — never silently invent a number and never let an adjective stand as the final requirement.
2b. **Size the market before any target is written.** Work through the "Market sizing" block in `reference/interrogation-checklist.md`: who the buyers are and how many, what each is willing to pay (and what that leaves as revenue per user), what they expect for that price, and what they tolerate giving up. Every number is `[proposed]` until sourced, and the sizing is written into the spec's Market sizing section (`reference/spec-template.md`). Scale, latency and availability targets are then derived from it, never picked first: a small, low-paying audience is a licence to relax latency, and the same sizing names the one capability whose failure makes the product worthless (the correctness floor), which no relaxed target may touch.
3. **Draft user stories / scenarios.** Concrete and situational ("between 8:50 and 9:00am, a nurse opens the med-pass screen and needs to see which of her 12 patients have an overdue dose"), not generic "as a user I want X" templates that could describe any feature. Later stages draw their entities and state transitions from these — the more concrete the scenario, the less anyone has to guess.
4. **Draft success metrics.** Numbers with units, a measurement method, and a time window. If the stakeholder hasn't supplied a number, propose one (from comparable features, prior data, or a reasonable first-version bar), mark it `[proposed]`, and ask them to confirm or correct it.
5. **Name constraints by kind.** Regulatory/compliance, technical (must integrate with X, must run on Y), timeline, and budget/team — each kind routes to a different reviewer and a different kind of open question, so don't collapse them into one bucket.
6. **Write non-goals.** For every goal, ask "what would someone assume this covers that it doesn't?" and write the answer down. A spec with goals and no non-goals almost always understates how big the feature really is — flag that growth as a finding if it surfaces, rather than quietly writing the largest version as Goals.
7. **Compile Open Questions.** Everything that didn't clear the bar in steps 2–6, in a question, proposed answer, and confirmer shape (see `reference/handoff-to-biz-decomposer.md`) — so `biz-decomposer` can absorb them directly instead of re-asking.
8. **Emit the spec** (see Output) and give the user a short inline summary: what's settled, what's `[proposed]` and needs their confirmation, and how many open questions remain before this is ready to hand to `biz-decomposer`.

## Output

Write to `docs/spec/<feature-slug>/spec.md` in the project — check first for an existing planning-doc convention (`docs/planning/`, `docs/prd/`, a wiki) and follow it rather than inventing a new location. Use `reference/spec-template.md` for the exact section shape:

```
docs/spec/<feature-slug>/
└── spec.md   # Problem, Goals, Non-Goals, Users & Scenarios, Terminal Requirements & Targets, Constraints, Open Questions
```

Split Open Questions into its own `open-questions.md` alongside `spec.md` only when the list would otherwise dominate the document; either way it keeps the same question/proposed-answer/confirmer shape.

## What this does NOT do

This skill stops at a validated spec. It never writes:

- **A requirement tree or research seeds** — that's `biz-decomposer`.
- **The developer-facing PRD** (work units, file scope, decisions in force) — that's `prd-writer`.
- **Axioms, pre/postcondition contracts, or symbol-attributed specs** — that's `axiomatic-spec`.
- **ADRs for one-way-door technical decisions** — those come out of the research and experiment stages and `one-way-door`.
- **Spec-derived tests or a telemetry plan** — same boundary.
- **Code, architecture, or implementation choices** ("use Postgres", "add a queue", "build a microservice"). If a stakeholder ask already bundles one in, keep it under Constraints only if it's a genuine hard requirement (e.g. "must run on our existing infra"); otherwise leave it out — that choice belongs downstream, and including it here just gives research a decision to unwind.

If, partway through, the conversation turns into "now make this testable," "what are the invariants," or a spec already exists and the next move is breaking it into research questions (`biz-decomposer`) or making a scoped change falsifiable against a codebase (`axiomatic-spec`) — that's the signal to hand off rather than keep going here. Say so explicitly rather than drifting into contract-writing.

## Judgment calls

- **Don't manufacture user stories or metrics wholesale** for a feature described in one sentence — interrogate first. A spec built entirely from `[proposed]` values with no real stakeholder input back-and-forth is a sign the conversation isn't finished, not a deliverable.
- **Proposed ≠ decided.** Never let a number or scope line this skill supplied quietly become load-bearing; every `[proposed]` needs a real path to confirmation — a question actually asked, not just a footnote nobody will read.
- **Scale effort to the ask.** A one-line idea for an internal tool needs a lean, fast spec; a regulated, multi-stakeholder feature (anything touching PHI/PII, payments, safety) needs real interrogation of compliance constraints before success metrics are even worth drafting.
- **The size of the ask is itself a finding.** If interrogation reveals the feature is much bigger than the one-liner implied, say so before finishing the doc — that often changes what v1 even is.
- **Size first, then target.** A latency, throughput or uptime number written before the sizing is a guess that research will later optimise for the wrong problem. If the sizing shows the audience is small and pays little, say that targets on speed should be modest and that the effort belongs on the correctness floor.
- **Stop at the spec.** The pull to keep going into contracts and tests is real, especially in a well-understood domain — resist it. That discipline keeps the terminal requirements free of solution choices, which is what lets research be open.
