---
name: demo-script
description: Write timed software demo scripts as STAR bullet points, connecting business research and experiments to implementation, measured results, and honest limitations.
---

# Demo script

Confirm the desired video duration before writing; ask how long only when the user has not already specified it. Also establish audience and narration mode from context. A script request does not authorize recording, publication, or another project's demo.

Read the original brief/PRD, research, experiment records, implementation decisions, current deployed behavior, and dated verification evidence. Distinguish proposed, implemented, deployed, and verified capabilities. Flag conflicts between the requested duration and submission rules; produce the requested cut without claiming it satisfies conflicting rules, and preserve any longer submission script.

Deliver a timestamped script in bullet points using STAR:

- **S — Situation:** Target consumer, business problem, market/state-of-the-art research, and available budget or operational constraints. Explain why the problem matters.
- **T — Task:** Research uncertainty → isolated experiments and measured trade-offs → the requirement and acceptance criteria chosen. Explain the evidence behind priorities and scope. Do not invent experiments or retrofit decisions as measured results.
- **A — Action:** Specific implementation mechanisms, architecture, stack choices, algorithms, data structures/models, and failure handling that satisfy those requirements. Tie each technical choice to its purpose and a visible demo action.
- **R — Result:** Measured outcomes with dataset, date/build, units, and scope; core behavior demonstrated; honest limitations, failed cases, deferred requirements, and the next validation needed. Separate test results from production performance and AI-labelled evaluation from human ground truth.

Within S and T preserve the causal chain **business → research → experiment → requirement defined**. Allocate most screen time to A. Use concise first-person speaking bullets, not a dense essay. For each timed bullet include the screen/action cue, the narration point, and a compact source reference to the PRD or evidence. Put references in production notes, not spoken narration.

Use the requirements-defined UX journey as the narrative backbone: the user's goal, entry point, successive feature interactions, and visible outcome. Interleave a compact STAR explanation for each core feature as it appears: business need and research/experiment-derived requirement (S/T), the mechanism and technical decision that enables the interaction (A), and visible outcome plus measured evidence or honest limitation (R). Do not interrupt the journey with separate long business, architecture, or results lectures. An overall opening and closing can frame these feature-level STAR bullets.

Make segment durations sum to the requested runtime, including transitions. At normal speaking pace budget roughly 120–140 words/minute, then rehearse and adjust to the actual narrator. For a 150-second cut, reserve a brief opening and closing and give most time to the connected feature walkthrough with interleaved STAR explanations. Allocate time by core requirement importance rather than forcing equal feature coverage.

Choose a small coherent workflow that proves the core requirements; include technical/terminal evidence when mandated by the brief. Use real app outcomes and label replayed, seeded, simulated, or disabled features accurately. Do not turn loading-time edits into performance claims. Never claim a current build passed an older build's full suite.

If the owner will narrate later, supply a silent-footage shot list paced to the script, with natural cursor movement and readable pauses; add no synthetic narration, decorative audio, or webcam overlay unless requested. Keep editing source and final export paths in the handoff. Recording still requires the relevant session's explicit authorization.
