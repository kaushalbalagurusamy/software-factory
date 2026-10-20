---
name: lsf
description: Lite software factory for a one-hour live session on a laptop. Runs the owner's flow (brief, minesweep, research, experiments, tracer PRDs, evals, blind build, QA, mechanistic review, docs and drift) with a phase clock, telemetry, human checkpoints and an offline dashboard. Invoke explicitly with /lsf.
disable-model-invocation: true
---

# lsf: the lite software factory

This is `/sf` made fast. Same stage names, same file conventions, same artifacts. It needs only Python 3.9+ and git (no virtualenv, no solver). The audience watches telemetry and human-in-the-loop checkpoints, so the dashboard is the main screen. Everything you do must leave a trace the dashboard can show.

Run the tool as `lsf` (installed by `install.sh`) or `python3 <skill dir>/scripts/lsf.py`. Every command takes `--root DIR`.

## Mac quick start

1. `python3 --version` must print 3.9 or newer (macOS ships it with the Xcode command line tools; `xcode-select --install` if missing). `git --version` too.
2. From the unpacked skill folder: `sh install.sh`. It copies the skill to `~/.claude/skills/lsf` and puts an `lsf` wrapper in `~/.local/bin` (add that folder to `PATH` if it says so). Running it again changes nothing. An older different copy is kept in `~/.claude/skills-backups`, never inside the skills folder (it would load as a second `lsf`).
3. In the project folder: `lsf doctor`, then `lsf init`.
4. `lsf serve --open` prints `http://127.0.0.1:PORT/#token=...` once in that terminal and opens it. The token after `#` is what enables the Approve button, so open that exact URL (if the page has no token it shows the terminal command instead). Keep this terminal running.
5. Decisions you are asked for follow this lifecycle (agents never release):
   - **Asked**: the agent runs `lsf hitl request NAME --question Q --option A --option B`; the dashboard banner says `N decision(s) waiting for you`.
   - **Answered**: you pick an option and press **Submit answer** in the Human stops tab (a question without options keeps **Approve**), or run `lsf hitl release NAME --answer A`.
   - **Recorded**: the agent writes your answer down and runs `lsf hitl recorded NAME --where PATH`.
   - **Applied**: once the change is made, the agent runs `lsf hitl applied NAME --evidence "what changed"`; only then does the card say Applied.
   - **Stale**: if the question or an artifact changed after it was asked, the answer is refused (409) and the agent must ask again.

Error logs: `lsf event STAGE fail --slice S --log-file out.txt` (or `--log -` with the output piped in) stores the last 64 KiB, redacted, in `.lsf/logs/`; click a failing row in the Evals & bugs tab to read it, with `path:line` editor links. A bug links to a log with a `Log: .lsf/logs/FILE` line in `docs/bugs/*.md`, or by matching slice and stage of the latest failing event.
Rollback: the Git tab has a **Rollback** button per commit (confirm in the page), or `lsf rollback SHA` to preview and `--yes` to do it. It adds a revert commit; history is never rewritten. Human only; agents are denied.

## Start

1. `lsf doctor` and fix any FAIL.
2. `lsf init` (add `--minutes N`, `--checkpoints align|all|none`, `--editor vscode|cursor|antigravity-ide|zed|idea|none|...`). `lsf init --strict-hitl` makes `hitl release` and `hitl repair` refuse unless they run in a real terminal.
3. **The human starts the dashboard**, in their own terminal: `lsf serve --open`. The agent must never run `lsf serve`, never read or print the token (the `#token=...` part of the URL), and never call the release route. If the dashboard is not running, ask the owner to start it.
4. `lsf hooks install --project .` shows a diff; add `--apply` only when the owner agrees. It adds automatic telemetry (subagent stops, session stops, `git commit`) and a PreToolUse guard that denies `hitl release`, `hitl repair`, and writes to `.lsf/stops*`. The guard is friction, not proof. Hooks write only into a project that already has `.lsf` (found by walking up from the hook's directory); elsewhere they do nothing.

## The flow, in the owner's order

Time split for the hour: about **60% alignment** (phases 0 to 6, informed by research and experiments), **20% review** (phases 9 and 10), **20% build** (phases 7 and 8). Weights are in `.lsf/profile.json`; `lsf budget` shows planned against actual.

| lsf phase | group | what you do | writes | /sf stage |
|---|---|---|---|---|
| `0-intake` | align | Save the brief verbatim; one-page core PRD of user journeys | `docs/requirements/brief.md`, `docs/prd/onepager.md` | 0 |
| `1-sweep` | align | Minesweep: core business value, traps, best practices in networking, crypto, performance, ethics | sweep notes in `docs/requirements/` | 0 |
| `2-research` | align | Multi-agent research seeds on state of the art, dated sources, "could not verify" | `research/<topic>.md` (include `As of: DATE`) | 1 |
| `3-experiments` | align | Experiments only where research did not settle the choice | `experiments/<id>/results.json`, or `resolved.json` `{question, resolved_by, sources, as_of}` | 2 |
| `4-prd` | align | Tracer-bullet PRDs, UX stories first, triaged by priority and dependency | `docs/slices/<id>/proposal.md` (heading "UX stories"; `priority:`), `docs/prds/*.md` | 4 |
| `5-evals` | align | MECE eval surface: golden gates, invariants, boundaries, regressions, written before code | eval files, criteria in the slice | 5 |
| `6-decide` | align | ADRs for consequential choices | `docs/adr/ADR-NNN-title.md` with `Status:` and `Date:` | 3 |
| `7-implement` | build | Blind implementers build from the PRD; they tick tasks off, they do not read the evals | code, tasks marked `[x]` | 6 |
| `8-qa` | build | QA agents run the evals, send feedback to the implementer, note repeat failures | `docs/slices/<id>/qa-notes.md`, `docs/bugs/<id>.md` (`Status: open|fixed|wontfix`) | 7 |
| `9-review` | review | Mechanistic review with the nesting dolls (`mermaid-nesting-dolls`), the Ponytail rubric and the minesweeper lenses; failures amend the PRD and go back to 7 and 8 | amendments, bug notes; the dolls model and page in `docs/explorer/*.model.json` and `.html` (Architecture tab) | 8b |
| `10-docs` | review | ELI12 docs, ADR sync, drift check against the verbatim brief | `docs/eli12/`, updated ADRs | 10 |

Stage ids are an alias map to `/sf` (last column) so events from both tools read the same. If a phase finds the earlier work wrong, go back: start the earlier phase again.

## Per-phase procedure

- **At the start of every phase run `lsf hitl status`.** Exit 3 means a human stop is open: stop working and wait. Do not start the phase. (`lsf phase start` also refuses with exit 3.)
- `lsf phase start NAME`, do the work, write the artifacts the dashboard tabs read (table above), then `lsf phase end NAME --verdict V --note "what happened" --ask "the one question for the owner" --artifact PATH [--artifact PATH ...]`.
- Ending an alignment phase opens a human checkpoint named `<phase>-review` automatically. Put the question and the artifacts in it. **Do not ask the owner a question in chat when a checkpoint will do**: open one with `lsf hitl request NAME --question "..." --artifact PATH`. The owner approves from the dashboard (Approve button) or the terminal.
- **Never run `lsf hitl release` or `lsf hitl repair`.** Release is a human act. You may not approve your own checkpoint, edit or delete anything in `.lsf/stops*`, call the release route, or work around a stop. The tool records how each release happened (`via`: dashboard, cli-tty or cli-nontty) and cross-checks the ledger against the event log, but be plain about the limit: no software check can prove who clicked or typed. It is a procedure with an audit trail, not proof of identity.
- Record evidence as you go: `lsf event STAGE VERDICT --note "..." [--role R] [--slice S]`. Use verdicts `pass` and `fail` for test and review results so the dashboard counts them. Notes are truncated and secrets are redacted, but do not paste secrets anyway.
- If the owner states cost, log it: `lsf cost add --usd X --tokens N --model M`. Never estimate it.
- Check `lsf budget` at each phase boundary. If a group is over plan, say so to the owner and propose what to cut (smaller slices, not skipped stages).

## Rules for the work

- Tests and evals come before code. Implementers are blind to eval files. A separate runner runs tests. Never weaken, skip or delete an assertion to get green.
- Docs use the ELI12 format (`skills/eli12-docs`, `docs/eli12/<module>.md`): per function, one plain sentence, what it expects, what it gives back, who uses it, what it depends on. Run its `check` in `10-docs`; findings are stale docs. If `docs/eli12/index.json` is missing the Docs tab says so; do not fake it.
- Review uses the nesting dolls to read code at the right depth, and the Ponytail rubric: does it need to exist, is it already in the codebase, does the standard library do it, is there a smaller change, does the new logic have a check. Findings go back into the slice as amendments; the implement and QA duo runs again.
- When you build the explorer for the project, pass the editor so the diagram links open files: `python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py build model.json -o docs/explorer/NAME.html --workspace-root "$PWD" --editor <editor>` (use the editor in `.lsf/profile.json`).
- File references in anything the owner reads should be `path:line` so the dashboard opens them in the editor (the editor and workspace root are in `.lsf/profile.json`).
- Models are a profile choice: optional `models` in `.lsf/profile.json` maps roles (for example `synthesis`, `implementation`, `review`) to whatever the owner has available. Do not assume a model name; read the profile.
- Atomic commits, explicit paths, no force-push.

## Commands

`init`, `phase`, `event`, `hitl`, `status`, `budget`, `serve`, `bundle`, `hooks`, `doctor`, `cost`; each has `--help`. Exit codes: 0 ok, 1 a check failed, 2 usage, 3 refused by a human stop. `LSF_NOW=2026-10-20T10:00:00Z` overrides the clock (rehearsals, tests). `LSF_EVENTS=off` disables telemetry writes. Nothing makes a network request; `serve` listens on 127.0.0.1 only.

## The end of the hour

`lsf budget` for the planned-versus-actual story, `lsf cost summary`, and the dashboard's Telemetry tab for the journey: every decision the owner approved and how long each took.
