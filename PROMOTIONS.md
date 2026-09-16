# Promotion Ledger

Tracks each factory capability's position on the ladder: **skill → subagent → harness → multi-agent orchestrated workflow**. A capability is promoted to the next rung only once it has actually repeated in project work, not speculatively (see the factory's guiding principle in `README.md`).

A **harness** entry, per the promotion rule, is not just instructions — it's the capability's full operating kit: the tool calls/scripts it relies on, the MCP servers it uses, the external APIs it reaches, and the dependency packages/runtimes/images those need. That kit is recorded here alongside the rung, not left as incidental setup elsewhere.

## Current state

| Capability | Rung | Location | Notes |
| :--- | :--- | :--- | :--- |
| `axiomatic-spec` | Skill | `~/.claude/skills/axiomatic-spec` | PRD/change → axioms, contracts, ADR stubs, spec-derived tests, telemetry plan. Iteration/eval history in `~/Projects/axiomatic-spec-workspace`. |
| `grounded-research` | Skill | `~/.claude/skills/grounded-research` | Verifies a specific tool/API/library claim via ground-truth check → source triage → experiment. Iteration/eval history in `~/Projects/grounded-research-workspace`. |
| `deep-research` | Skill | `~/.claude/skills/deep-research` | Synthesizes a whole topic/landscape (regulatory, competitive, best-practices) across many sources into one saved `research/<topic-slug>.md` report; distinguished from `grounded-research` by scope — one verifiable claim goes to `grounded-research`, a whole subject area needing multi-source synthesis goes here, and this skill hands off to `grounded-research` mid-research if a narrow claim surfaces. Iteration/eval history in `~/Projects/deep-research-workspace`. |
| `sf-adr-debate` | Skill | `~/.claude/skills/sf-adr-debate` | Installed 2026-09-15 from this repo's `skills/`; not yet run through the skill-creator eval/benchmark loop the way `axiomatic-spec` and `grounded-research` were. |
| `sf-door-guard` | Skill | `~/.claude/skills/sf-door-guard` | Same status as above — installed, not yet benchmarked. |
| `sf-interface-auditor` | Skill | `~/.claude/skills/sf-interface-auditor` | Same status as above. |
| `sf-io-analyzer` | Skill | `~/.claude/skills/sf-io-analyzer` | Same status as above. |
| `sf-spec-testing` | Retired in place | `skills/sf-spec-testing` (this repo only, not installed) | Its "contract-first, deterministic eval harness" intent is being absorbed into the new `eval-designer` skill below rather than installed separately — avoids two skills claiming the same job. |
| `away-mode` | Skill | `~/.claude/skills/away-mode` | Session-keep-alive + remote-control handoff; a harness in spirit (caffeinate, git/Docker preflight) but not tracked as project-repeated work yet. |
| `use-railway` | Skill | `~/.claude/skills/use-railway` | Infra operations skill for Railway. |
| `brownfield-explorer` | Skill | `~/.claude/skills/brownfield-explorer` | Repo orientation + blast-radius mapping for unfamiliar/huge codebases, without requiring formal axioms afterward. `axiomatic-spec` Mode B steps 1-2 now delegate to it instead of duplicating the logic inline. Iteration/eval history in `~/Projects/brownfield-explorer-workspace`. |
| `sf audit` / `sf verify` (governance + zero-trust gates) | Harness | `factory/governance.py`, `factory/zero_trust.py`, `sf`/`factory` CLI entry points | Deterministic AST/SMT/hash-manifest checks, model-agnostic. Depends on `z3-solver`, `deal`, `crosshair-tool`, optionally `unity-ir` (`~/Projects/unity`). |
| `sf run` / `sf transpile` (autonomous synthesis + transpilation) | Harness | `factory/synthesis.py`, `factory/transpiler.py` | Generation step now shells out to the local `claude` CLI (`claude -p ... --restricted`); governance/zero-trust gates, atomic staging, and self-repair loop wrap it. Requires Claude Code installed and on `PATH`. |

## Pending promotions (new skills, in progress as of 2026-09-15)

| Capability | Target rung | Gap it closes |
| :--- | :--- | :--- |
| `prd-designer` | Skill | Nothing today turns a vague idea/ask into a structured PRD; `axiomatic-spec` assumes one already exists. |
| `eval-designer` | Skill | Generalizes `sf-spec-testing`'s "deterministic eval harness, not vibe checks" intent, and formalizes the eval/benchmark/iterate loop already hand-run twice (`axiomatic-spec-workspace`, `grounded-research-workspace`). |

## How to update this ledger

When a capability repeats enough to justify promotion, move its row up a rung, record the harness contents (tools, MCP servers, external APIs, pinned deps, and secret *names* — never values) it now depends on, and note the date and what triggered the promotion.
