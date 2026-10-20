# Interrogation checklist and rewrite patterns

Work through this before writing a single line of the spec. The goal: nobody reading the finished document re-asks "wait, who is this actually for?" or "what does success even mean here?" — and `biz-decomposer` doesn't have to ask for terminal requirements and targets again.

## The five questions, in order

| # | Question | Fails when | Fix |
|---|---|---|---|
| 1 | Who is this for? | "users", "customers", "people" with no persona/role/context | Name a specific role and situation: "a triage nurse at shift handoff," not "users" |
| 2 | What problem, at what moment? | Feature described by its solution ("we need a dashboard") rather than the problem it solves | Ask "what were they doing right before they needed this, and what were they stuck on?" |
| 3 | What does success look like? | An adjective with no number ("fast," "easy," "better retention") | Propose a number + unit + measurement window, mark `[proposed]`, ask to confirm |
| 4 | What's out of scope? | Only goals listed, no non-goals | For every goal, ask "what adjacent thing could someone assume this covers, that it doesn't?" |
| 5 | What are the hard constraints? | Constraints implied but unstated (compliance, timeline, must integrate with a legacy system) | Ask directly by category: regulatory, technical, timeline, budget/team |

## Rewrite patterns for vague requirements

**Vague quality -> quantified goal**
- "Fast" -> propose `[proposed] p95 response under 2s for a query over the last 90 days of records` and ask if that's the right bar.
- "Intuitive" / "easy to use" -> replace with a task-completion claim: `[proposed] a first-time user completes <task> without help in under N minutes` — ask what N is and what "without help" excludes.
- "Secure" -> not a spec-level goal at all. Split into the real constraint (e.g. "must not expose PHI to unauthenticated requests") and leave anything about auth architecture out of scope for this document.
- "Scales to lots of users" -> ask for the actual number this version needs to hit, and by when. If genuinely unknown, `[proposed]` a first-version target and flag it as an open question for whoever owns capacity planning.
- "Reliable" / "no downtime" -> ask for the number (uptime %, acceptable data-loss window) and who is affected when it's violated.

**Aspirational statement -> goal or open question**
- "This should eventually support every clinic in the network" -> is that a v1 goal or a north star? If the latter, note it separately (a "Later" line, not a Goal) — mixing horizons corrupts the success metrics.

**Solution disguised as requirement**
- "We need a chatbot" -> ask what problem a chatbot solves that a better list, search, or notification wouldn't solve equally well. If the shape (conversational vs. dashboard) really is a hard requirement from the stakeholder, keep it, but push on why once.
- "Use GPT-4 / build on vendor X" -> a technology choice belongs in Constraints only if truly non-negotiable (existing contract, compliance requirement); otherwise it's an implementation decision and out of scope for the spec.

**Silent scope creep**
- A one-line ask ("add dark mode") that grows to include an accessibility overhaul, a theming API, and admin controls once you start asking questions — when this happens, treat the growth as a finding. Tell the user the ask is bigger than they thought and let them decide what's v1 versus later, rather than quietly writing the biggest version as Goals.

## When you genuinely can't get an answer

Not every question resolves in one pass — sometimes the person you're talking to isn't the one who can answer it (a number legal, compliance, or a specific stakeholder needs to confirm). In that case: write the open question, propose your best-guess answer marked `[proposed]`, name who should confirm it if you can tell, and move on. Don't block the whole spec on one unanswered question when the rest of the document is solid.


## Market sizing (ask before writing any scale, latency or availability target)

1. **Who exactly buys or uses it?** A named segment and a head count, with the source of the count.
2. **What do they pay, and what is left?** Typical spend per user, the fee or price that applies, and the resulting revenue per user. The revenue sets the infrastructure budget.
3. **What do they expect for that price?** The service level they would notice and complain about, versus the level they would never perceive. Ask what they tolerate (staleness, delay, approximate answers) at this price.
4. **What volume follows?** Share of the market reached, requests per day, requests per second at peak, payload size. Compute it; a small result means capacity is not the hard part.
5. **What is the correctness floor?** The single capability whose failure makes the product pointless (for an aggregator, correctly classifying that two listings are the same thing; at 80% there is no aggregation and no best price). State its minimum bar as a measurable target.
6. **Which targets does the sizing relax, and which does it harden?** Availability and partition tolerance still hold; what relaxes is the speed the audience cannot perceive. Hardened targets get the experiment budget.
