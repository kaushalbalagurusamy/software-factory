# [Short Title of Solved Problem and Chosen Decision]

* **Status:** Proposed | Accepted | Deprecated | Superseded by [ADR-0000](0000-example.md)
* **Date:** YYYY-MM-DD
* **Authors:** [Author Name / Agent]
* **Deciders:** [Team / Human Stakeholder]

---

## 1. Context and Problem Statement
[Describe the context and problem to be solved. Explain why an architectural decision is necessary.]

## 2. Decision Drivers
* [Driver 1, e.g., Low latency (<50ms p95)]
* [Driver 2, e.g., Strict transactional integrity across accounts]
* [Driver 3, e.g., Operational simplicity / cloud hosting budget]

## 3. Considered Options
* **Option 1:** [Name of Option 1]
* **Option 2:** [Name of Option 2]
* **Option 3:** [Name of Option 3]

---

## 4. Decision Outcome
**Chosen Option:** Option [X], because [justification grounded in decision drivers and trade-off analysis].

### Positive Consequences
* [Benefit 1]
* [Benefit 2]

### Negative Consequences & Mitigations
* [Trade-off 1 / Cost and how it will be mitigated]
* [Trade-off 2 / Operational complexity]

---

## 5. Pros and Cons of the Options

### Option 1: [Name of Option 1]
* Good, because [argument a]
* Bad, because [argument b]

### Option 2: [Name of Option 2]
* Good, because [argument a]
* Bad, because [argument b]

---

## 6. Decision Trail
_Append-only. Add rows at the bottom, oldest first. Never edit or delete a row; correct a mistake with a new row that cites the old one. Rules, field meanings, and an example: `skills/sf-adr-debate/references/decision-trail.md`._

| # | When (UTC) | Mode | Step | Actor | What happened | Evidence |
|---|---|---|---|---|---|---|
| 1 | YYYY-MM-DD HH:MM | auto | [step] | [actor] | [what happened] | [evidence] |

### Gate Records
_One block per `gate` row, keyed by its row number._

**#[N]** · Paused [YYYY-MM-DD HH:MM] · Resumed [YYYY-MM-DD HH:MM]
* **Shown:** [what the human was given: options, evidence, recommended default]
* **Known gaps:** [material uncertainty the human was not shown, or "none known"]
* **Feedback (verbatim):** "[the human's words]"
* **Outcome:** approved as proposed | approved with changes | rejected | deferred
* **Effect:** [what changed in the decision because of the feedback, in the agent's words]
* **Source:** [link to the message or session]
