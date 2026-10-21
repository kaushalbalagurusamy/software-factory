# Handing off to biz-decomposer

`biz-decomposer` pins each terminal requirement with an id, its verbatim text, an owner, a target with a unit, and a source line, then decomposes. If the spec already carries those, it can start from the Terminal Requirements table instead of asking for them.

| biz-decomposer needs | Comes from this spec's... |
|---|---|
| Terminal requirement ids (T1, T2, ...) | Terminal Requirements & Targets table, one row per requirement |
| Verbatim text and source | The same table; quote the stakeholder, with who said it and where |
| Owner | The same table; the person who can confirm or change the target |
| Target with a unit | The same table; `[proposed]` marks a target nobody has confirmed |
| Constraints (budget, latency, compliance, team, existing systems) | Constraints section, by kind |
| Questions only the business can answer | Open Questions, with the proposed answer and who confirms |

## What not to do

Do not decompose, rank questions, or suggest architectures here. Do not write targets that bundle a solution ("p95 under 50 ms using pgvector"): the target is the 50 ms, and the choice of store belongs to research. `biz-decomposer` reports when a target looks expensive or conflicts with another; it never edits one. Only the owner does, through this skill.

## Route back here when

`biz-decomposer` finds a requirement with no measurable target, or two targets that contradict each other. Both are spec questions, not decomposition questions.
