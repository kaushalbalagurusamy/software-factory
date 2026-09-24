# Software factory: cleanup ideas and tooling to revisit

Captured 2026-09-24. These are unscheduled ideas, not decisions. Revisit when planning the next factory iteration.

## Cleanup and consolidation

1. **Stateful documents.** Keep three kinds of living documents as the factory's memory: ticket docs (one per unit of work), research docs, and routing docs (how work is dispatched and why). Each records current state so a fresh session can resume without the conversation.
2. **Consolidate agents into five roles:** Research, Design, Implement, Test, Review. Fold the existing redundant agents into these, and give each role its hooks, skills and tooling allowlist in one place. This also supports the narrow-tool, smallest-adequate-model approach to subagent cost.
3. **Jev routes.** Use Jev's per-option probabilities for task and route dispatch. For the co-pilot supervisor the assessment is in `gauntlet/W2/research/2026-09-24-jev-routing-integration-assessment.md` (conditional go on a shadow-mode tracer bullet).
4. **Unity.** Continue the compiler and semantic-invariant work described in `ROADMAP.md`.
5. **Encryption or isolation for evals.** Keep eval cases unreadable to implementer agents (encrypted at rest or in an isolated location with only a pass/fail interface) so implementers cannot reward-hack against them.

## Tools to evaluate (from office hours)

| Tool | What it is | Why it might matter | Caution |
|---|---|---|---|
| [rtk-ai/rtk](https://github.com/rtk-ai/rtk) (Rust Token Killer) | A Rust CLI proxy that filters and compresses shell command output before an agent reads it; claims 60-90% less output. Installed through shell hooks (`rtk init`). | Token savings on agent shell output, which counts against the usage budget. | Savings are estimated as bytes / 4, not real tokens. Hooks rewrite commands, so trial it in a scratch setup first. Name collides with "Rust Type Kit". |
| [dietrichgebert/ponytail](https://github.com/dietrichgebert/ponytail) | An agent skill that pushes toward the minimum code that works ("the laziest senior dev"). npm `@dietrichgebert/ponytail`, MIT. | Could cut over-building by implementer agents. Its own benchmark claims about 54% less code. | Numbers are self-reported and unverified. May conflict with the spec-first, eval-gated approach; test against our evals before adopting. |

Both were summarized from DeepWiki (rtk) and the GitHub README (ponytail, not indexed by DeepWiki); neither was cloned.
