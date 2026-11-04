---
name: business-problem-decomposition
description: Use at the very top of the software factory, upstream of axiomatic-spec and the build loop, when a fuzzy business problem must become a decomposed, quantified, sourced problem statement a PRD can be derived from. Runs WHO / WHAT / WHEN / HOW, a consequence chain from event to terminal consequence, and a scripted case calculation with sourced assumptions, then hands off to axiomatic-spec. Does not propose solutions before Stage 4 and never invents numbers.
---

# Business Problem Decomposition

Runs at the very top of the software factory, upstream of axiomatic-spec and the build loop. Its job: turn a fuzzy business problem into a decomposed, quantified, sourced problem statement that a PRD can be derived from. It does NOT propose or design solutions until Stage 4, and it never invents numbers.

## Operating rules

1. **Problem before solution.** Stages 1-3 contain no solutioning. If the user opens with a solution, restate the problem it implies and decompose that.
2. **Every number carries provenance.** Sourced, derived (with formula and parent inputs), or flagged `[UNSOURCED-ESTIMATE]` with the cheapest way to get a real value. No silent assumptions.
3. **Money and time are two dimensions, not the whole picture.** Always ask what the domain's real currency is (safety, health, trust, regulatory exposure, scientific validity, optionality, learning rate, mission) and carry it to the terminal consequence.
4. **Compute, don't estimate in prose.** Run the case model in code. Show the formulas.
5. **Separate the author from the checker.** Final red-team pass should be done by a fresh subagent that sees the artifact but not the reasoning.
6. **Use grounded-research for sourcing when available:** verify before trust, prefer primary sources, record date and quality tier.

## Stage 0: Frame

Write back, in 3-5 lines: the problem as understood, the decision this analysis will inform, who will make it, and what artifact comes next (usually an axiomatic-spec PRD). Ask at most 3 questions if the framing is genuinely ambiguous or expensive to get wrong; otherwise state the reading taken and proceed.

## Stage 1: WHO

Build an actor map. For each actor: role, what they want, what they fear, what power they have over the outcome, current workaround, and how they are measured.

Cover these classes (skip none; write "none" explicitly if empty):

- Payer / budget owner
- Direct user / operator
- Beneficiary or victim who never touches the system
- Decision-maker vs. blocker vs. champion
- Regulator / auditor / counterparty
- Adversary or free-rider (who benefits if this goes wrong or is gamed)
- Internal builders / maintainers

Output: actor table plus the 1-3 actors whose incentives dominate the problem.

## Stage 2: WHAT

- Current state vs. desired state, stated observably (what could be measured).
- Symptom vs. cause: ask "why" until you hit a mechanism, not a label. Record the causal mechanism.
- Unit of work: the repeated atomic thing (a claim processed, a cell cycled, a trade settled, a patient visit). Volume and variance of this unit drive everything downstream.
- Failure definition: what counts as the problem occurring, what counts as bad vs. catastrophic.
- Out of scope: adjacent problems explicitly not being solved.

## Stage 3: WHEN

- Trigger: what event or condition starts it.
- Frequency and volume, with trend.
- Hard deadlines, windows, seasonality, regulatory clocks.
- Time-value: does value decay, compound, or step-change with delay?
- Lead and lag: delay between cause and visible consequence (long lags hide problems).
- Sequencing and dependencies on other work.

## Stage 4: HOW

- Current mechanism: how the work actually gets done today, including shadow processes and manual patches.
- Constraint map: technical, legal, organizational, data, trust. Mark hard vs. soft.
- Levers: where intervention could change the causal mechanism from Stage 2.
- Option set (always include): do nothing, process/policy change, buy, build narrow, build broad. Each gets a one-line mechanism of action, not a design.

## Stage 5: Consequence chain (first-order to terminal)

For the problem as-is (do-nothing baseline) AND for each viable option, trace the chain:

`event -> 1st-order -> 2nd-order -> ... -> terminal`

For every link record:

- **Mechanism:** why A causes B
- **Probability and lag**
- **Reversibility:** can it be undone, at what cost
- **Evidence:** source or `[UNSOURCED]`
- **Currency:** money, time, safety/health, trust, legal exposure, scientific validity, optionality, learning, reputation, morale (name the domain-specific ones)

Terminal consequence = the point past which no further effect changes what the decision-maker or domain ultimately cares about. Examples by domain: clinical: patient outcome; battery/energy: cell failure or safety event; fintech: fiduciary loss, enforcement action; research: invalid or irreproducible conclusion; a company: survival or loss of the core relationship. State why the chain stops there.

Also trace second-order effects of the solution itself (new failure modes, gaming, behavior change, maintenance burden), and branches that fork (low-probability, catastrophic-severity tails deserve their own line even if expected value is small).

Output as an indented tree or table, not prose.

## Stage 6: Case calculation

**Assumption register** (table): ID, assumption, value (low / base / high), unit, source (title, URL or citation, date), quality tier (primary data > reputable secondary > analogy > estimate), and which Stage 5 link it feeds.

**Model:** write a small script (Python) that takes the register and computes, per option vs. do-nothing baseline:

- Cost / benefit in money and in time where relevant
- The natural-unit outcome from Stage 5 (events avoided, hours returned, defects caught, risk reduced) with money conversion only where defensible; otherwise report both unconverted
- Break-even: what must be true for the option to win
- Payback and sensitivity (tornado: which 3 assumptions move the answer most)
- Scenario spread (low / base / high), never a single point estimate

Research the top-sensitivity assumptions first. Spend sourcing effort in order of sensitivity. Unsourced assumptions that dominate the answer are the headline risk; say so.

**Reality checks:** compare the result against an outside benchmark or analog; if it implies something implausible (ROI over 50x, market larger than the industry), find the error before reporting.

## Stage 7: Output and handoff

Produce one document (Docs artifact by default) with:

1. One-paragraph problem statement (who suffers what, how often, why, with the terminal consequence)
2. WHO table, WHAT / WHEN / HOW summaries
3. Consequence tree: do-nothing vs. options
4. Case calc results: scenarios, break-even, tornado, with the assumption register in an appendix
5. Recommendation with kill criteria: what evidence would make us stop
6. Assumptions & Bets ledger: unsourced or weakly sourced assumptions, ranked by sensitivity, each with the cheapest test
7. Handoff block for axiomatic-spec: the key metrics (with target values from the model), constraints, in-scope and out-of-scope, and the top risks that tests must cover

Attach the model script and assumption register as files so the numbers are reproducible.

## Quality gates (run before delivering)

- [ ] WHO classes all addressed or explicitly "none"
- [ ] Stages 1-3 contain no solutions
- [ ] Consequence chains reach a stated terminal point with a reason
- [ ] At least one non-money, non-time currency is carried through if the domain has one
- [ ] Every number is sourced, derived, or flagged; zero silent assumptions
- [ ] Model re-run from the register end to end; outputs match the document
- [ ] Decomposition is MECE: no overlapping causes counted twice in the calculation
- [ ] Fresh-agent red-team pass: attack the assumptions that dominate the result and the chain links with weakest evidence; fix or flag what it finds
- [ ] Recommendation includes kill criteria

## Parallelization

Stages 1, 2, and 3 can be researched by parallel subagents. Stage 5 depends on 2-4. In Stage 6, fan out one sourcing subagent per top-sensitivity assumption, each returning value, source, date, and quality tier.
