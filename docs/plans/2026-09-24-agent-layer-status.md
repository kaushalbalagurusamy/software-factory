# Agent layer build: where we stopped

> **Paused:** 2026-09-24 evening, at the owner's request, to leave usage for the Co-Pilot final. Branch `agent-graph` (off `skills-overhaul`), pushed, no pull request. Working tree clean apart from the audit report described below.

## What exists (all committed)
- **Rules and requirements:** `docs/factory/METHODOLOGY.md`, `docs/factory/requirements.md` (R-01 to R-24).
- **Published contracts:** `docs/contracts/` (hook I/O, profile, roles and generation, graph and ledger) and the **binding** `clarifications.md` (three rounds; it wins over PRDs and contracts).
- **14 tracer-bullet PRDs:** `docs/prds/INDEX.md` has the dependency graph and waves. TB-01 to TB-14.
- **Evals (grading side):** `evals/agents/`, 1,302 cases, 129 golden (`GOLDEN.json`, locked), all resolving to `blocked` because nothing is implemented. Run: `uv run --no-project --with pytest --with pyyaml --with z3-solver --with deal --with networkx --with crosshair-tool --with hypothesis python evals/agents/run.py`. Coverage matrices and resolved ambiguity logs are in `evals/agents/coverage/`.
- **Independent MECE audit (finished):** report at `evals/agents/audit/MECE-AUDIT.md`. **Verdict: the golden gate fails MECE**: it is mostly non-redundant (4 overlapping cases) but not exhaustive, so shortcut implementations would pass it. Of 45 in-scope requirements the auditor extracted from the source documents: 20 covered by golden, 5 by diagnostic only, 2 by process evidence, 10 weak, 8 missing; the register omitted 9 source requirements (including the OS sandbox backstop and a human pause before merges and pull requests).

## Not done
- **No implementer has run.** No hook, generator, ledger or profile code exists yet (`factory/agents/`, `factory/hooks/` are absent).
- **The audit's five P0 findings have not been acted on.** Fix them before any implementer starts:
  1. The golden set never varies project settings for the path, blindness, bash and end-to-end cases (base fixture only), so hard-coded `evals/**` or `deployctl push` passes. Swap in TB14-D-001, TB08-D-114, TB06-D-082; promote TB05-D-004 and D-005.
  2. No golden case allows an implement Bash command, so a deny-all Bash guard passes. Promote TB06-D-134 and D-139.
  3. "Done needs evidence of a full test run" has no golden case. Swap TB09-G-002 for D-029; promote D-028.
  4. The contracts let the implement agent switch off its own guards (Bash writes to `.factory/profile.yaml`, `.factory/baseline.json` or the stop-gate counter; Write or Edit on `.claude/**`). Add a clarification protecting both folders, plus golden cases.
  5. This build's implementers are blind to `evals/` only by instruction. Create implementer worktrees without `evals/` and add a `Read(./evals/**)` deny rule for their sessions.
- The roles of Codex are out of scope by owner decision.

## Next steps, in order
1. Read `MECE-AUDIT.md` (P1 and P2 findings and the omitted requirements are there); apply the five P0 findings above (add, swap or drop cases; fix contract clauses); then consider trimming the golden gate to about 60 cases if the audit shows redundancy.
2. Wave 1: TB-01 and TB-02 (Sonnet implementers, each in its own worktree, briefed with only the PRD and the contracts it names, never the `evals/` directory). Then wave 2 (TB-03, TB-04, TB-12), wave 3 (TB-05 to TB-11 in two batches), wave 4 (TB-13), wave 5 (TB-14). Orchestrator merges by explicit path, one slice per commit, and runs `run.py` after each wave.
3. TB-14 includes one manual live rehearsal that also confirms whether a sub-agent's frontmatter `Stop` hook runs as `SubagentStop` (unverified, clarification C-34).

## Cost note
The eval authoring used about 1.4 million sub-agent tokens across three Opus authors and two follow-up rounds, plus the auditor. Implementers are Sonnet and much smaller per slice; check `~/.claude/state/rate_limits.json` before starting a wave.
