# Promotion Ledger

Tracks each factory capability's position on the ladder: **skill → subagent → harness → multi-agent orchestrated workflow**. A capability is promoted to the next rung only once it has actually repeated in project work, not speculatively (see the factory's guiding principle in `README.md`).

A **harness** entry, per the promotion rule, is not just instructions — it's the capability's full operating kit: the tool calls/scripts it relies on, the MCP servers it uses, the external APIs it reaches, and the dependency packages/runtimes/images those need. That kit is recorded here alongside the rung, not left as incidental setup elsewhere.

## Current state

| Capability | Rung | Location | Notes |
| :--- | :--- | :--- | :--- |
| `axiomatic-spec` | Skill | `~/.claude/skills/axiomatic-spec` | PRD/change → axioms, contracts, ADR stubs, spec-derived tests, telemetry plan. Iteration/eval history in `~/Projects/axiomatic-spec-workspace`. |
| `grounded-research` | Skill | `~/.claude/skills/grounded-research` | Verifies a specific tool/API/library claim via ground-truth check → source triage → experiment. Iteration/eval history in `~/Projects/grounded-research-workspace`. |
| `deep-research` | Skill | `~/.claude/skills/deep-research` | Synthesizes a whole topic/landscape (regulatory, competitive, best-practices) across many sources into one saved `research/<topic-slug>.md` report; distinguished from `grounded-research` by scope — one verifiable claim goes to `grounded-research`, a whole subject area needing multi-source synthesis goes here, and this skill hands off to `grounded-research` mid-research if a narrow claim surfaces. Iteration/eval history in `~/Projects/deep-research-workspace`. |
| `one-way-door` | Skill | `~/.claude/skills/one-way-door` | 2026-09-24: merge of `sf-door-guard` and `sf-adr-debate` (door check first, ADR debate only for one-way doors). Not yet run through the trigger-eval loop. |
| `implementation-review` | Skill | `~/.claude/skills/implementation-review` | Independent review of diff, traces, earned passes and drift. 2026-09-24: absorbed `sf-interface-auditor` and `sf-io-analyzer` as `reference/` checklists and dropped the `sf-` prefix. Description choice against the Codex wording is still open. |
| `orchestration` | Skill | `~/.claude/skills/orchestration` | 2026-09-24: merge of `sf-hierarchical-orchestration`, `sf-parallel-integration` and the routing half of `sf-jev-dispatcher`. Jev guidance is rewritten; the policy file and client it describes are not built yet. Not yet run through the trigger-eval loop. |
| `sf-spec-testing` | Retired in place | `skills/_archive/sf-spec-testing` (this repo only, not installed) | Its "contract-first, deterministic eval harness" intent is being absorbed into the new `eval-designer` skill below rather than installed separately — avoids two skills claiming the same job. |
| `away-mode` | Skill | `~/.claude/skills/away-mode` | Session-keep-alive + remote-control handoff; a harness in spirit (caffeinate, git/Docker preflight) but not tracked as project-repeated work yet. |
| `use-railway` | Retired (personal copy) | The Railway plugin's own `railway:use-railway` skill | 2026-09-24: the personal install was an older duplicate of the plugin skill and was removed on the Claude side. The Codex copy in `~/.agents/skills` is kept until it is confirmed that Codex loads the plugin skill. |
| `brownfield-explorer` | Skill | `~/.claude/skills/brownfield-explorer` | Repo orientation + blast-radius mapping for unfamiliar/huge codebases, without requiring formal axioms afterward. `axiomatic-spec` Mode B steps 1-2 now delegate to it instead of duplicating the logic inline. Iteration/eval history in `~/Projects/brownfield-explorer-workspace`. |
| `sf audit` / `sf verify` (governance + zero-trust gates) | Harness | `factory/governance.py`, `factory/zero_trust.py`, `sf`/`factory` CLI entry points | Deterministic AST/SMT/hash-manifest checks, model-agnostic. Depends on `z3-solver`, `deal`, `crosshair-tool`, optionally `unity-ir` (`~/Projects/unity`). |
| `sf run` / `sf transpile` (autonomous synthesis + transpilation) | Harness | `factory/synthesis.py`, `factory/transpiler.py` | Generation step now shells out to the local `claude` CLI (`claude -p ... --restricted`); governance/zero-trust gates, atomic staging, and self-repair loop wrap it. Requires Claude Code installed and on `PATH`. |
| `eval-designer` | Skill | `~/.claude/skills/eval-designer` | Designs deterministic eval harnesses for AI-produced/judged capabilities — a skill's own trigger accuracy and output quality, or a non-deterministic product feature (LLM suggestion/summary/classification) — with boundary/failure-mode cases ordered before happy-path ones and a candidate-vs-baseline benchmark loop; absorbs `sf-spec-testing`'s intent. Reuses `skill-creator`'s benchmarking tooling directly rather than duplicating it. Iteration/eval history in `~/Projects/eval-designer-workspace`. |
| `prd-designer` | Skill | `~/.claude/skills/prd-designer` | Turns a vague idea, stakeholder one-liner, or messy conversation into a structured PRD (goals, non-goals, user stories/scenarios, quantified success metrics, constraints, open questions) shaped so `axiomatic-spec` can consume it directly, without writing axioms/contracts/ADRs itself. Sits upstream of `axiomatic-spec`, which otherwise assumes a PRD already exists. Iteration/eval history in `~/Projects/prd-designer-workspace`. |

## Pending promotions (new skills, in progress as of 2026-09-15)

| Capability | Target rung | Gap it closes |
| :--- | :--- | :--- |

## How to update this ledger

When a capability repeats enough to justify promotion, move its row up a rung, record the harness contents (tools, MCP servers, external APIs, pinned deps, and secret *names* — never values) it now depends on, and note the date and what triggered the promotion.
