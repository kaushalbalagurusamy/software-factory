# Build-loop profile: software-factory

Profile for the `/sf` build loop (see `~/.claude/skills/sf/SKILL.md`, "Load the project profile first"). The `sf-reminder.py` SessionStart hook detects this file at `docs/development-workflow.md`. This file states facts about this repository only; where something does not exist it says so.

## Source requirements (verbatim, never paraphrased)
- Project requirements register: `docs/factory/requirements.md` (each requirement has an ID and a source).
- Build methodology every agent must follow: `docs/factory/METHODOLOGY.md`.
- Owner's flow request, verbatim, external to this repository and not copied into it: `/home/linuxuser/sf-workflow-owner-request-verbatim.md`. Cite it by that absolute path.
- Audit of that flow against the current state, and the integration plan: `docs/plans/2026-10-19-sf-owner-flow-audit-and-plan.md`.

Drift check rereads the sources above line by line; it does not rely on an earlier summary.

## Decisions and specs
- ADRs: `docs/adr/` (`ADR-NNNN-<slug>.md`; template at `templates/adr-template.md`).
- Published contracts (what components accept and return): `docs/contracts/`.
- Current PRDs and tracer-bullet slices: `docs/prds/` (index: `docs/prds/INDEX.md`; files `TB-NN-<slug>.md`).
- Plans: `docs/plans/`. Backlog notes: `docs/backlog/`.

## Tests and evals
- Unit tests (implementers may read and run): `tests/`.
- Agent-layer evals, graded side: `evals/agents/` (cases, `GOLDEN.json`, `run.py`). Blind to implementers: an implementer must not read, list, search or run anything under `evals/`. Plain `pytest` does not collect it (`testpaths = ["tests"]`).
- No skip, xfail, weakened or deleted assertion to obtain a pass. Marker `requires_unity` (registered in `pyproject.toml`) marks tests that need the Unity compiler; without Unity they fail with an explicit reason rather than skip.

## Environment and test commands
- Build the environment: `scripts/dev-env.sh` (creates `.venv`, installs `requirements.txt`, installs Unity editable from `$UNITY_REPO`, default `~/Projects/unity`, when that directory exists).
- Unit tests, everything (needs Unity): `.venv/bin/python -m pytest tests`
- Unit tests as CI runs them (no Unity): `.venv/bin/python -m pytest tests -m "not requires_unity"`
- Agent-layer evals (grader only): `python evals/agents/run.py [-k expr]`
- CI: `.github/workflows/ci.yml` validates skill frontmatter, runs `templates/deterministic-eval-template.py`, and runs the unit tests without `requires_unity`.
- Governance gate: `sf audit --pre A --post B` exits 0 verified, 1 input error or one-way door under `--strict`, 3 gate failed (required verifier unavailable or errored), 4 unverified pattern-only (see `factory/cli.py`).

## Reviewer
- No reviewer agent definition exists in this repository. Use a separate read-only agent that did not write the change (different model family where available) per `docs/factory/METHODOLOGY.md` rule 6, given the diff, the evidence and the open findings. It grades each pass right-reason, wrong-reason or inconclusive, and never edits implementation, tests or cases.

## Hygiene
- Limits are the defaults of `~/.claude/skills/sf/hygiene/hygiene.sh` (see its `DESIGN.md`): warn below 20 GB or 15% disk free, act below 10 GB or 8%, emergency below 3 GB or 3%. No repo-specific override.
- Run `hygiene.sh scan --agents N` before fanning out more than 2 parallel agents. Agent worktrees for this repository live under `~/Projects/sf-worktrees/`.
