# Promotion Ledger

Tracks each factory capability's position on the ladder: **skill → subagent → harness → multi-agent orchestrated workflow**. A capability is promoted to the next rung only once it has actually repeated in project work, not speculatively (see the factory's guiding principle in `README.md`).

A **harness** entry, per the promotion rule, is not just instructions — it's the capability's full operating kit: the tool calls/scripts it relies on, the MCP servers it uses, the external APIs it reaches, and the dependency packages/runtimes/images those need. That kit is recorded here alongside the rung, not left as incidental setup elsewhere.

## Current state

| Capability | Rung | Location | Notes |
| :--- | :--- | :--- | :--- |
| `axiomatic-spec` | Skill | `~/.claude/skills/axiomatic-spec` | PRD/change → axioms, contracts, ADR stubs, spec-derived tests, telemetry plan. Iteration/eval history in `~/Projects/axiomatic-spec-workspace`. Patched 2026-10-05 to read the dev-facing PRD (targets, work units, scope, decisions in force), link accepted ADRs, add a `check:` field, and fail a required Unity gate when a tool is missing; not re-benchmarked since. |
| `grounded-research` | Skill | `~/.claude/skills/grounded-research` | Verifies a specific tool/API/library claim via ground-truth check → source triage → experiment. Iteration/eval history in `~/Projects/grounded-research-workspace`. |
| `deep-research` | Skill | `~/.claude/skills/deep-research` | Synthesizes a whole topic/landscape (regulatory, competitive, best-practices) across many sources into one saved `research/<topic-slug>.md` report; distinguished from `grounded-research` by scope — one verifiable claim goes to `grounded-research`, a whole subject area needing multi-source synthesis goes here, and this skill hands off to `grounded-research` mid-research if a narrow claim surfaces. Iteration/eval history in `~/Projects/deep-research-workspace`. |
| `one-way-door` | Skill | `~/.claude/skills/one-way-door` | The installed skill that holds the one-way-door debate and ADR protocol; this repo's `skills/sf-adr-debate` is its source for the ADR decision trail, which was ported into `one-way-door` on 2026-10-05 (`references/decision-trail.md`). Master skills carry no `sf-` prefix (decided 2026-09-24). Not yet run through the skill-creator eval/benchmark loop. |
| `sf-door-guard` | Not installed | `skills/sf-door-guard` (this repo only) | Checked 2026-10-05: no copy under `~/.claude/skills`, although this row previously said installed. Decide whether to install, merge into another skill, or retire. |
| `sf-interface-auditor` | Not installed | `skills/sf-interface-auditor` (this repo only) | Checked 2026-10-05: no copy under `~/.claude/skills`, although this row previously said installed. Decide whether to install, merge into another skill, or retire. |
| `sf-io-analyzer` | Not installed | `skills/sf-io-analyzer` (this repo only) | Checked 2026-10-05: no copy under `~/.claude/skills`, although this row previously said installed. Decide whether to install, merge into another skill, or retire. |
| `sf-spec-testing` | Retired in place | `skills/sf-spec-testing` (this repo only, not installed) | Its "contract-first, deterministic eval harness" intent is being absorbed into the new `eval-designer` skill below rather than installed separately — avoids two skills claiming the same job. |
| `away-mode` | Skill | `~/.claude/skills/away-mode` | Session-keep-alive + remote-control handoff; a harness in spirit (caffeinate, git/Docker preflight) but not tracked as project-repeated work yet. |
| `use-railway` | Skill | `~/.claude/skills/use-railway` | Infra operations skill for Railway. |
| `brownfield-explorer` | Skill | `~/.claude/skills/brownfield-explorer` | Repo orientation + blast-radius mapping for unfamiliar/huge codebases, without requiring formal axioms afterward. `axiomatic-spec` Mode B steps 1-2 now delegate to it instead of duplicating the logic inline. Iteration/eval history in `~/Projects/brownfield-explorer-workspace`. |
| `sf audit` / `sf verify` (governance + zero-trust gates) | Harness | `factory/governance.py`, `factory/zero_trust.py`, `sf`/`factory` CLI entry points | Deterministic AST/SMT/hash-manifest checks, model-agnostic. Depends on `z3-solver`, `deal`, `crosshair-tool`, optionally `unity-ir` (`~/Projects/unity`). |
| `sf run` / `sf transpile` (autonomous synthesis + transpilation) | Harness | `factory/synthesis.py`, `factory/transpiler.py` | Generation step now shells out to the local `claude` CLI (`claude -p ... --restricted`); governance/zero-trust gates, atomic staging, and self-repair loop wrap it. Requires Claude Code installed and on `PATH`. |
| `eval-designer` | Skill | `~/.claude/skills/eval-designer` | Designs deterministic eval harnesses for AI-produced/judged capabilities — a skill's own trigger accuracy and output quality, or a non-deterministic product feature (LLM suggestion/summary/classification) — with boundary/failure-mode cases ordered before happy-path ones and a candidate-vs-baseline benchmark loop; absorbs `sf-spec-testing`'s intent. Reuses `skill-creator`'s benchmarking tooling directly rather than duplicating it. Iteration/eval history in `~/Projects/eval-designer-workspace`. |
| `spec-writer` | Skill | `~/.claude/skills/spec-writer` | Renamed from `prd-designer` on 2026-10-05. Business-facing: turns a vague idea or stakeholder ask into a spec that fixes the terminal requirements and targets (T1...), shaped for `biz-decomposer`. The developer-facing PRD is `prd-writer`'s. Iteration/eval history, recorded under the old name, in `~/Projects/prd-designer-workspace`. |

## Pending promotions (new skills, status as of 2026-10-05)

| Capability | Target rung | Gap it closes |
| :--- | :--- | :--- |
| `biz-decomposer` | Skill | Turns fixed business requirements into a requirement tree and ranked research seeds; nothing seeds the research fan-out without it. Drafted in `skills/biz-decomposer`; installed to `~/.claude/skills` on 2026-10-05; not yet run through the eval loop. |
| `experiment-designer` | Skill | Chooses which architectural uncertainties merit an experiment and designs fair, abstracted comparisons with a pre-registered decision rule. Drafted in `skills/experiment-designer`; installed to `~/.claude/skills` on 2026-10-05; not yet run through the eval loop. First planned test case: ROADMAP Phase 3. |
| `prd-writer` | Skill | Dev-facing PRD that merges the spec targets, accepted ADRs, and experiment verdicts, so `axiomatic-spec` does not derive axioms from a document it wrote itself. First iteration drafted in `skills/prd-writer`: work units carry a file scope (owns, new, reads, entry points) with a checker script (`scripts/check_scope.py`, tested in `tests/test_check_scope.py`). Contracts, budget shares, and held-out QA cases come later. Installed to `~/.claude/skills` on 2026-10-05; not yet run through the eval loop. |
| `experiment-arm-runner`, `experiment-referee`, `red-team-verifier` | Subagent | Isolation is structural for these roles: arms must not see each other, and the referee and red-team verifier must not see the builder's work. Defined from the first experiment, not after repetition. Not started. |

## How to update this ledger

When a capability repeats enough to justify promotion, move its row up a rung, record the harness contents (tools, MCP servers, external APIs, pinned deps, and secret *names* — never values) it now depends on, and note the date and what triggered the promotion.
