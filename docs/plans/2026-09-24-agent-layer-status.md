# Agent layer build: where we stopped

> **Paused:** 2026-09-24 evening, at the owner's request, to leave usage for the Co-Pilot final. Branch `agent-graph` (off `skills-overhaul`), pushed, no pull request. Working tree clean apart from the audit report described below.

## What exists (all committed)
- **Rules and requirements:** `docs/factory/METHODOLOGY.md`, `docs/factory/requirements.md` (R-01 to R-24).
- **Published contracts:** `docs/contracts/` (hook I/O, profile, roles and generation, graph and ledger) and the **binding** `clarifications.md` (three rounds; it wins over PRDs and contracts).
- **14 tracer-bullet PRDs:** `docs/prds/INDEX.md` has the dependency graph and waves. TB-01 to TB-14.
- **Evals (grading side):** `evals/agents/`, 1,302 cases, 129 golden (`GOLDEN.json`, locked), all resolving to `blocked` because nothing is implemented. Run: `uv run --no-project --with pytest --with pyyaml --with z3-solver --with deal --with networkx --with crosshair-tool --with hypothesis python evals/agents/run.py`. Coverage matrices and resolved ambiguity logs are in `evals/agents/coverage/`.
- **Independent MECE audit:** was running when this note was written. If it finished, its report is `evals/agents/audit/MECE-AUDIT.md`; if that file is missing, the audit did not finish and must be re-run.

## Not done
- **No implementer has run.** No hook, generator, ledger or profile code exists yet (`factory/agents/`, `factory/hooks/` are absent).
- The MECE audit's findings have not been acted on. Fix its P0 items (contract or eval changes) before any implementer starts.
- The roles of Codex are out of scope by owner decision.

## Next steps, in order
1. Read `MECE-AUDIT.md`; apply P0 findings (add, swap or drop cases; fix contract clauses); consider trimming the golden gate to about 60 cases if the audit shows redundancy.
2. Wave 1: TB-01 and TB-02 (Sonnet implementers, each in its own worktree, briefed with only the PRD and the contracts it names, never the `evals/` directory). Then wave 2 (TB-03, TB-04, TB-12), wave 3 (TB-05 to TB-11 in two batches), wave 4 (TB-13), wave 5 (TB-14). Orchestrator merges by explicit path, one slice per commit, and runs `run.py` after each wave.
3. TB-14 includes one manual live rehearsal that also confirms whether a sub-agent's frontmatter `Stop` hook runs as `SubagentStop` (unverified, clarification C-34).

## Cost note
The eval authoring used about 1.4 million sub-agent tokens across three Opus authors and two follow-up rounds, plus the auditor. Implementers are Sonnet and much smaller per slice; check `~/.claude/state/rate_limits.json` before starting a wave.
