# Spec template

Use this structure for `docs/spec/<feature-slug>/spec.md`. Every section should exist even if short — a thin or missing section is itself information (nobody has asked that question yet).

```markdown
# <Feature name>: Spec

## 1. Problem
One or two paragraphs, controlled natural language, no adjectives without numbers:
- Who is affected (name the persona/role)
- What moment or situation triggers the need
- What they do today instead, and why it's insufficient
- The original raw ask, quoted verbatim, with its source (who said it, where)

## 1b. Market sizing
Who it is for (named segment and how many), what each will pay and the revenue per user that leaves after fees, what they expect for that price, what they tolerate giving up, and the request volume that follows. Mark each figure `[proposed]` or sourced. End with two lines: **Relaxed by sizing:** (targets the sizing lets us loosen, e.g. latency) and **Correctness floor:** (the capability that must work or the product has no value, with its minimum measurable bar).

## 2. Goals
Numbered list. Each goal is a claim someone could check against the shipped product:
- G1: <goal, quantified where it matters>
- G2: ...

## 3. Non-Goals
For every goal above, at least one line on what it does NOT mean:
- This version does not cover <adjacent thing someone might assume is included>

## 4. Users & Scenarios
Concrete scenarios, not generic user-story templates:
- **Scenario**: <situational description with a specific moment, e.g. "Tuesday 8:50am, before rounds">
- **Today**: what they do now
- **With this feature**: what changes, described from their point of view

## 5. Terminal Requirements & Targets
Fixed by the business. Later stages serve these and never edit them.
| Id | Requirement (verbatim) | Owner | Target (number + unit + window) | Measured how | Status |
|---|---|---|---|---|---|
| T1 | <stakeholder's words> | <who can change it> | <target> | <instrumentation/method> | proposed / confirmed |

## 6. Constraints
| Kind | Constraint | Source |
|---|---|---|
| Regulatory | ... | ... |
| Technical | ... | ... |
| Timeline | ... | ... |
| Budget/Team | ... | ... |

## 7. Open Questions
One row per unresolved item, in the exact shape the next spec-writing step needs:
| Question | Proposed answer | Who should confirm | Blocks? |
|---|---|---|---|
| <question> | [proposed] <best-guess answer, or "none — genuinely open"> | <role/person if known> | yes/no |
```

## Notes on filling it in

- Section 1's "raw ask, quoted verbatim" matters more than it looks — it's what a later reader checks the rest of the document against when something feels off or over-scoped.
- Section 5 rows with no stakeholder-supplied target still get a row: target = `[proposed] <value>`, status = `proposed`, and a matching line in section 7 asking for confirmation.
- Keep the whole document readable in one sitting. If Goals exceeds roughly seven items, or Scenarios exceeds roughly five, that's a sign the ask is actually multiple features — say so before finishing the document rather than just documenting all of them as one spec.
