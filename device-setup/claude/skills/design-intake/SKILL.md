---
name: design-intake
description: Use whenever a design idea, architectural notion, or "wouldn't it be good if" thought surfaces while you are mid-task on something else — whether it comes from the user or occurs to you. Covers unsolicited feature ideas, scope expansions, "while we're at it" suggestions, and any tangent that is interesting but not what the current task is blocked on. Triggers on phrases like "here's an idea", "what if we", "random thought", "off-topic but", "wouldn't it be good if", or the assistant's own urge to pivot toward a shinier problem. Forces triage instead of execution: capture the idea cheaply (ADR or backlog entry), decide whether it actually implicates the work in progress, rank and place it concretely, say the placement out loud, then resume the interrupted task. Use this even under deadline pressure — especially then, since that's when losing the critical path to a tangent is most expensive.
---

# Design Intake

A design idea showing up mid-task is not a request to build it. It is a request to not lose it. This skill is the triage step that sits between "interesting idea appeared" and "should I act on it now" — almost always the answer is: write it down, place it, and keep going.

## Why this exists

The default failure mode is dropping the current task to chase the new idea because it's interesting, or because the user sounds excited about it. That's expensive precisely when it's most tempting — close to a deadline, mid-implementation, right before a gate. The fix isn't to ignore good ideas; it's to separate *recording* a decision from *executing* it. A note costs minutes. A context switch costs the rest of the session.

## Decision procedure

Run this in order, out loud is fine — it should take a few sentences, not a essay:

1. **Capture it now, cheaply.** One or two sentences: what the idea is, why it might matter. Don't develop it yet.
2. **Ask the one question that matters: does this implicate the work in progress?**
   - Yes, if it invalidates an assumption the current work depends on, or changes an interface/contract being implemented right now.
   - No, if it's merely interesting, urgent-sounding, related to the same system, or something the user seems excited about. None of those are implication.
3. **If no (the common case): place it, don't just log it.**
   - Give it a specific position in the priority list — tied to a milestone, gate, or requirement if one exists. "Later" is not a placement; "after the current milestone, before X, because it affects Y" is.
   - Pick its home:
     - A **real decision** (changes direction, worth defending later) → an Architecture Decision Record.
     - A **unit of work** (a thing to build, not a thing to decide) → a ranked backlog entry.
   - If the project has no ADR directory or backlog file yet, ask the user once where these live, or create the obvious minimal one (e.g. `docs/adr/` or `BACKLOG.md`) and say you did.
   - If the write-up is simple enough to delegate (it usually is), hand it to a lightweight subagent rather than spending the main thread's attention on formatting a note. The main agent's context is the scarce resource being protected here, not the note itself.
4. **State the placement out loud.** One line: what it is, where it landed, and why, so the ranking is visible to the user instead of assumed.
5. **Return to the interrupted task and say so explicitly.** Name what you were doing before the idea came up and continue it. Do not let the reply trail off into the new idea.
6. **If yes (it genuinely implicates current work):** say plainly which part it implicates and why that's grounds to switch, then switch. This should be rare — most ideas that feel urgent fail the test in step 2.

## Red flags — you're about to context-switch when you shouldn't

If you notice yourself reaching for any of these to justify dropping the current task, that's the signal to go back to step 2, not evidence that step 2 doesn't apply:

- "This changes everything."
- "It'll only take a minute."
- "Better to do it while it's fresh."
- "The user seems really excited about this."
- "It's related, so I might as well handle it now."
- "I'm already in this file / this part of the code."
- "I can always come back to the other task after."

Every one of these is a rationalization for skipping triage, not a finding from it. The test in step 2 is narrow on purpose: invalidated assumption or changed interface, nothing softer.

## Worked example

**Mid-task:** Implementing pagination for an API endpoint. The user says: "Oh, random thought — what if we cached these results in Redis so repeated queries were instant? Could be huge for the dashboard."

1. **Capture:** "Idea: Redis caching for repeated query results, motivated by dashboard read latency."
2. **Implicates current work?** No — pagination doesn't depend on whether results are cached later; the response shape and interface being built right now are unaffected.
3. **Place it:** This is a unit of work, not a decision about direction → backlog entry. "Added to backlog, ranked after the current pagination milestone and before the next perf pass, tagged against the dashboard-latency goal." (Delegate the actual write-up to a subagent if the backlog format is templated.)
4. **State it:** "Logged the Redis-caching idea to the backlog, placed after pagination ships, since it's a latency optimization and pagination doesn't touch that path."
5. **Resume:** "Back to pagination — next up is the cursor-encoding logic."

Contrast: if the user instead said "actually, should the endpoint even be paginated, or should we cache the whole result set instead?" — that changes the interface being built right now. That's a step-6 case: name it ("this changes whether pagination is the right shape for this endpoint at all") and switch.

## Notes

- This applies whether the idea comes from the user or occurs to you mid-task — the assistant is just as prone to the shiny-idea pivot as a human collaborator floating a thought.
- Keep the whole triage compact. If it's taking more than a few sentences, you're starting to design the idea instead of placing it — stop and place it.
- Nothing here blocks a *quick clarifying question* about the idea's scope so it can be placed accurately. It blocks building it.
