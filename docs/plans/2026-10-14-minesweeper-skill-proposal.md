# Proposal: the `minesweeper` skill

Status: proposal, owner decisions recorded 2026-10-14. Nothing is built yet.
Date: 2026-10-14. Author: SF session.

## The problem

The factory trusts the PRD. Stage 9 of `/sf` treats every line of the source requirements as a requirement, and the ledger
counts a run as finished when every line is satisfied. That works only when the brief is honest. The current briefs are not
reliably honest. A peer who evaluated six of this week's briefs found traps in all six. Some briefs, read literally, would
make the builder:

- break the licence terms of the software being used,
- break the terms of the model providers being used,
- break copyright law,
- cross ethical engineering lines, such as disclosing a vulnerability in a harmful way,
- install dependencies that are unmaintained, against project rules, or insecure,
- chase a goal that a grading rubric rewards but the real problem punishes.

Agents miss these unless they are told to look, and even then it takes several passes. When asked "any issues with building
this?", the answer was "Nothing blocks it."

We already have two cases of our own:

1. **FacilityGrid.** Requirement 1 says "no reading is ever duplicated or lost … regardless of delivery order, retries, or
   how many times a gateway resends it". Requirement 3 says a new device is "registered exactly once". Both are distributed
   systems claims with known impossibility results behind them (Two Generals, FLP, and Byzantine faults when a sender can
   lie). The agent built a sound idempotent design, but it filed the trust questions under "cuts":
   - gateway clocks are trusted, so a gateway that boots in 2099 pins a device's value;
   - the claim endpoint has no authentication;
   - nothing defends against a gateway that lies.

   It listed them without naming the problem: the brief asks for guarantees that need a trust model the brief never gives.
   The real problem was "decide which gateways to believe", and the answer was effectively "out of scope ✅".
2. **OpenEMR one-click sign-in (2026-10-13).** This session built and deployed a shortcut that discloses the reviewer
   password to any visitor and enables login CSRF. The security review found both problems only after the deploy. A sweep
   before the feature was built would have offered a separate low-privilege demo account up front.

What both cases show: naive, feature-driven development turns PRD sentences into tickets. The fix is a stage that asks what
the PRD should be solving, checks each line against real rules, and only then lets the line onto the ledger.

## What the skill is

`minesweeper` is a global skill at `~/.claude/skills/minesweeper/`. It has three parts:

1. **A syllabus.** One file per topic. Each file holds the principles, the usual traps, the phrases in a brief that hint
   at them, the primary sources to check, and the question to ask.
2. **A retrieval corpus.** Dated snapshots of primary sources (licences, terms of service, statutes, standards, papers),
   plus a live fetch for anything that changes. Every confirmed trap cites a passage from this corpus or from a live fetch.
3. **A sweep procedure.** It turns a brief into a trap register and a list of conditions on the ledger.

`/sf` calls it as a new **stage 0** before Research. It runs again on any requirement text that changes (stage 9) and on any
new inbound item (stage 12).

## Part 1: the syllabus

Topics are grouped so each group can be swept by a separate agent. Each file uses one template: principles, traps (each
with a known real case), smell phrases, primary sources, and the questions to ask.

| Group | Topic files | Example smells in a brief |
|---|---|---|
| **Law and terms** | `licensing` (SPDX, GPL/AGPL network clause, non-commercial model and data licences, attribution) · `provider-terms` (Anthropic, OpenAI, Google and others: usage policies, rules on output use and training, account sharing, automation on consumer plans) · `copyright-data-rights` (scraping, site ToS, training data, media rights) · `privacy-regulated-data` (HIPAA, 42 CFR Part 2, GDPR/CCPA, COPPA, FERPA, BIPA, TCPA) · `professional-duty` (medical device / SaMD, financial and trading rules, unauthorised practice, interpreter certification, ADA/WCAG) | "use any open model", "scrape", "fine-tune on outputs", "real patient", "send texts to", "trade", "diagnose" |
| **Security ethics and supply chain** | `security-ethics` (coordinated disclosure, CFAA and authorisation scope, credential handling, dark patterns) · `supply-chain` (unmaintained packages, OSV/CVE checks, typosquats, dependency licences, pinning) | "publish the vulnerabilities", "use library X" (check X), "share the demo login", "bypass" |
| **Deep technical** | `cryptography` (no home-made crypto, nonce reuse, RNG, key management, "quantum-proof" claims) · `distributed-systems` (FLP, CAP/PACELC, Two Generals, effectively-once vs exactly-once, Byzantine 3f+1, clocks and ordering, split brain) · `theory-complexity` (undecidable asks, NP-hard optimum at scale, impossibility results in fairness metrics, information limits) · `os-systems` · `databases` (isolation anomalies, write skew, uniqueness under concurrency) · `performance` (physically impossible latency budgets, tail latency, Little's law, bad measurement) | "exactly once", "regardless of", "never lost", "guaranteed", "real time", "unbreakable", "optimal", "zero latency" |
| **Evaluation and business** | `rubric-inversion` (Goodhart, metrics that reward the wrong behaviour, rubrics that reward fabrication or dark patterns) · `company-context` (the hiring company's mission, customers, regulators, public incidents, what they would never ship) | a rubric that scores volume, speed or conversion with no quality floor |

Each file grows from real cases. FacilityGrid seeds `distributed-systems`, OpenEMR seeds `security-ethics`, and this week's
briefs seed the rest. The course lectures in `~/Projects/gauntlet/lectures` are read first, as `/sf` stage 1 already
requires. They are the floor, not the ceiling.

## Part 2: retrieval

- **Corpus layout:** `minesweeper/corpus/<topic>/<source-id>.md`. Each file holds the source URL, the fetch date, a content
  hash, and the text. Licences come from SPDX and the licence's own repository. Terms come from the provider's own page.
  Statutes come from eCFR or the official text.
- **Freshness:** terms of service and usage policies are fetched again at sweep time if the snapshot is over 30 days old.
  Licences and statutes are re-checked on a 90-day schedule.
- **Search, first version:** local lexical search (ripgrep plus a small BM25 script). It is free, needs no new service, and
  can be checked by hand.
- **Embeddings:** added only if an experiment on the golden set (below) shows lexical search misses traps that embeddings
  find. That follows the `/sf` experiment rule rather than assuming RAG needs vectors.
- **Company context:** gathered per brief by web search into `docs/minesweep/company-<name>.md`, with sources. It covers the
  mission, products, customers, regulators and public incidents.

## Part 3: the sweep

The steps run in order, and each one writes a file:

1. **Split the brief into claims.** Every sentence is a claim, and so is everything attached to the brief: the rubric,
   examples, sample data, linked repos, suggested libraries and models. Implied claims count too: "regardless of order"
   assumes a trust model. Output: `claims.md`.
2. **Sweep by lens.** One agent per group runs in parallel, so there are four. Each marks every claim either `clear` (with
   the reason) or `suspect` (with the trap and the syllabus entry). A lens with nothing to report must still list each claim
   it checked. A blank result then means "checked" rather than "not looked at".
3. **Ground each suspect.** Retrieve the primary passage, then label the suspect `confirmed` (with a quote and its source),
   `plausible` (no primary passage found yet, with what would settle it), or `dismissed` (with the reason).
4. **Run a skeptic pass.** A separate agent tries to dismiss each confirmed trap. Over-flagging has a real cost: it turns a
   legitimate brief into refusals. The skeptic runs on Claude under the Max subscription, in a fresh context with no access
   to the sweepers' reasoning, only their claims and citations (owner decision: no OpenRouter).
5. **Reframe.** For each surviving trap, record:
   - **Severity**, on the peer's scale:
     - **Critical:** following the brief harms people or plainly breaks a law, licence or professional duty.
     - **High:** the deliverable fails, or there is substantial legal or security exposure.
     - **Medium:** a flaw a careful reviewer would catch.
     - **Low:** operational.
   - **The problem the brief should have stated.**
   - **A disposition:** `comply-safely` (a route that meets the intent without the trap), `reframe`, `decline`, or
     `ask-owner`.
6. **Write the register.** Output: `docs/minesweep/<date>-trap-register.md`. It holds one row per trap with its severity,
   brief line, quote, source, disposition and status. It also gets a short "problem definition" section that stage 1
   research starts from.

## Changes to `/sf`

- **Stage 0 Minesweep is added** before Research, with a todo of its own like every other stage.
- **The ledger gains a `trust` column:** `trusted`, `conditioned (trap id)` or `rejected`. A row from a brief line with an
  open Critical or High trap cannot be scheduled until its disposition is recorded. A Critical row also needs the owner's
  sign-off.
- **"Out of scope" no longer closes a trap.** A trap can be cut only with its consequence written down and a disposition.
  This is the FacilityGrid lesson.
- **Stage 1 Research widens.** Before market sizing and SOTA methods, it states the real problem: the company's mission, the
  rules that govern its industry, and the known pitfalls. It then states where the brief points away from that problem.
- **Stage 8 review** gets the trap register as a hunting list.
- **Stages 9 and 12** run the sweep again on changed requirement text and on new inbound items.

## How we test the skill (tests first, as `/sf` requires)

A golden set built from cases we know, with expected traps written before the skill exists:

| Case | Expected traps |
|---|---|
| FacilityGrid brief | the trust model is missing (Byzantine or lying gateways); clock trust; the unauthenticated claim; "exactly once" needs to be framed as effectively-once |
| OpenEMR one-click sign-in request | password disclosure; login CSRF and session fixation; a low-privilege demo account as the safe route |
| OpenEMR modifications on a public deploy | GPL obligations for distributed changes (to verify against the licence text) |
| Meridian brief | trading and prediction-market rules; real money; jurisdiction |
| ai-red-team brief | disclosure ethics and authorisation scope |
| This week's six briefs | compared against the peer's counts as an outside benchmark (their judgement, not ground truth) |
| Two clean controls | briefs with no planted traps, to measure false alarms |

Metrics:

- **recall**, the share of expected traps found;
- **precision**, the share of confirmed traps that survive owner review;
- **citation rate**, the share of confirmed traps with a primary quote;
- tokens and minutes per brief.

Failed runs stay in the history, as with every other gate.

## Cost and limits

- Each brief costs four lens agents, one grounding pass, one skeptic pass and one reframe pass. That is roughly seven agent
  runs, on Sonnet by default, with Opus for the deep-technical lens.
- Everything runs on the Claude Max subscription. No OpenRouter or other paid API (owner decision 2026-10-14).
- This is not legal advice. The skill flags problems and cites sources; the owner decides. Where the answer depends on
  jurisdiction or contract terms, the disposition is `ask-owner`.
- Snapshots of terms of service go stale, which is why they are fetched again at sweep time.

## Build order once approved

1. Write the golden set and expected registers (tests first).
2. Write `SKILL.md`, the syllabus template and the four group files, seeded from FacilityGrid and OpenEMR.
3. Build the corpus and the lexical search; snapshot the primary sources the golden set needs.
4. Run the sweep on the golden set; record recall and precision; fix the procedure, not the expectations.
5. Add stage 0 and the ledger `trust` column to `/sf`, and run the sweep on this week's briefs when they arrive.

## Owner decisions (2026-10-14)

1. **Hard gate: yes.** Critical traps block scheduling until the owner signs off. High needs a recorded disposition.
2. **Retrieval: yes.** Lexical search first; embeddings only if the golden-set experiment justifies them.
3. **Cross-family skeptic: no.** The project runs on the Claude Max subscription; the skeptic is a fresh Claude context.
4. **This week's briefs: yes.** Sweep them as soon as they land, before any build starts, with the register marked
   uncalibrated.
