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

## Resource limits and concurrency (added after the 2026-10-19 OOM)
- Incident: a test in an implementer's worktree built its input by wrapping a command in `json.dumps` 40 times; each level doubles the escaping, so the string grew as about 2^40 characters and one pytest process reached ~19 GB RSS and was OOM-killed, taking the session with it. The implementation under test was not at fault.
- Every pytest run is bounded by the repo-root `conftest.py`: address space `SF_TEST_MEM_MB` (default 4096 MB, inherited by child processes) and a per-test wall clock `SF_TEST_TIMEOUT_S` (default 120 s). A tripped limit is a FAILURE with a `resource limit` message, never a skip or a pass; the limits are printed in the report header.
- Heavy or whole-suite runs go through `scripts/bounded-pytest.sh [pytest args]`: memory cap, hard wall-clock kill (`SF_TEST_WALL_S`, default 900), a machine-wide lock so only ONE heavy run executes at a time, and a line per run in `.sf/resource-limits.log`.
- Fan-out: at most two implementation agents at once while stabilising; at most one memory-heavy run. Run `hygiene.sh scan --agents N` first.
- Test authors: never build inputs by repeated self-nesting or doubling inside a loop (escaping, quoting, `json.dumps`, `shlex.quote` all multiply); build deep nesting linearly (for example `"$(" * n + "x" + ")" * n`) and keep sizes bounded.
