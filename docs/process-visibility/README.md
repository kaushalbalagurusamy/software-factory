# Process visibility: how a build moves from brief to merged slice

This page lets a reader see the process without running it. Detail lives in the
linked files; nothing here replaces them.

- `/sf` is the full software factory loop (12 stages). Source: `skills/sf/SKILL.md`, diagram in `docs/sf-flow.md`.
- `/lsf` is the lite factory for a one-hour live session. It runs the same flow as 11 timed phases. Source: `skills/lsf/SKILL.md`.

## The 12 /sf stages

| # | Stage | Output | Checked by |
|---|---|---|---|
| 1 | Research (intake: verbatim register, minesweep, ranked seeds) | dated research notes, requirement ledger | `sf intake check` |
| 2 | Experiment | `experiments/<id>/results.json` or `resolved.json` | `sf intake experiments check` |
| 3 | Decide (ADR; one-way doors get a debate) | `docs/adr/ADR-NNN-*.md` | `sf audit` |
| 4 | Tracer-bullet spec, MECE (4b structure, 4c contracts) | `docs/slices/<id>/` | `sf slice check`, `sf contracts check-contracts` |
| 5 | Tests and evals written first, then frozen | eval files, locked criteria | `sf slice lock` |
| 6 | Implement blind to the test code | code, tasks ticked `[x]` | worktree plus blindness hooks |
| 7 | A separate agent runs the tests | QA feedback in criterion terms | `sf qa ...` |
| 8 | Independent review for reward hacking | findings that amend the slice | `implementation-review`, `sf slice done` |
| 9 | Drift check against the verbatim source | updated ledger | `sf intake check` |
| 10 | Docs and ADR sync (blocks on drift) | updated docs, dashboard event | `doc-sync`, `sf ops bundle` |
| 11 | Atomic commit | one commit per logical change | `sf ops bundle` |
| 12 | Check inbound sources, brief the owner | ranked backlog, `progress-briefing` page | `sf intake gate --since SHA` |

Full command table with enforcement: "Factory toolchain by stage" in `skills/sf/SKILL.md`.

## /lsf phases and how they map to /sf

Phase clock: about 60% alignment (phases 0-6), 20% review (9-10), 20% build (7-8).

| lsf phase | group | /sf stage |
|---|---|---|
| 0-intake | align | 0 |
| 1-sweep (minesweeper) | align | 0 |
| 2-research | align | 1 |
| 3-experiments | align | 2 |
| 4-prd (UX stories first) | align | 4 |
| 5-evals | align | 5 |
| 6-decide (ADRs) | align | 3 |
| 7-implement (blind) | build | 6 |
| 8-qa | build | 7 |
| 9-review (nesting dolls, Ponytail rubric, minesweeper lenses) | review | 8 |
| 10-docs (ELI12, ADR sync, drift) | review | 10 |

Ending an alignment phase automatically opens a human checkpoint named `<phase>-review`.
Telemetry events from both tools use the same stage ids.

## Human-in-the-loop stops

- Every stage or phase begins with `sf hitl status --root .` (or `lsf hitl status`). Exit 3 means a stop is open: do nothing except report it.
- Stops are opened before owner-gated or irreversible actions and at artifact-only stopping points: `sf hitl request --name N --reason R`.
- While a stop is open, `sf slice done` refuses (exit 5) and `sf qa next` returns `human_stop`.
- Only a person releases a stop (`sf hitl release --name N --by human:<ref>`), at an interactive terminal, or by pressing Approve / Submit answer in the dashboard's Human stops tab. The ledger is hash-chained under `.factory/stops/`.
- Honest limit: this is friction and procedure, not an unforgeable barrier.

## Dashboard tabs

The lsf dashboard is offline, served on 127.0.0.1. It has eleven tabs; each reads artifacts the phases write.
Source mapping: `docs/ops-tabs.md`.

| Tab | Reads |
|---|---|
| Overview ("now") | phase clock, budget, open stops |
| PRD | `docs/prd/onepager.md`, `docs/slices/*/proposal.md`, `docs/prds/*.md` |
| Research | `research/<topic>.md` |
| Experiments | `experiments/<id>/results.json`, `resolved.json` |
| Evals and bugs | `docs/bugs/`, `docs/slices/*/qa-notes.md`, golden results |
| ADRs | `docs/adr/` |
| Architecture | nesting-doll models in `docs/explorer/` |
| Docs | `docs/eli12/` |
| Git | commits, with a Rollback button that adds a revert commit |
| Telemetry | every decision, who approved it, how long it took |
| Human stops | open stops, approve / answer controls |

## Mermaid nesting dolls

A single self-contained HTML page (`skills/mermaid-nesting-dolls`). The top screen is the system architecture
diagram; clicking a stacked box opens the diagram inside it, recursively, down to leaf components. A side panel
shows what each component does, design choices, source files (checked against the repo by the builder) and gaps.
The model lives in `docs/explorer/*.model.json`; the HTML is regenerated from it. Phase 9 of lsf uses it for review.

## Existing screenshots

All paths relative to the repo root. Captures are from real rehearsals on a VPS, not mock data; see
`docs/rehearsals/lsf-dashboard-gallery-2026-10-20.md` for context and honest caveats (the elapsed clock in the
captures is not the feature build time).

### Final-runtime dashboard (python-dotenv rehearsal)

| Tab | Image |
|---|---|
| Overview | `docs/rehearsals/screenshots/lsf-final-now.png` |
| Human stops | `docs/rehearsals/screenshots/lsf-final-stops.png` |
| PRD | `docs/rehearsals/screenshots/lsf-final-prd.png` |
| Research | `docs/rehearsals/screenshots/lsf-final-research.png` |
| Experiments | `docs/rehearsals/screenshots/lsf-final-experiments.png` |
| Evals | `docs/rehearsals/screenshots/lsf-final-evals.png` |
| ADRs | `docs/rehearsals/screenshots/lsf-final-adrs.png` |
| Architecture | `docs/rehearsals/screenshots/lsf-final-architecture.png` |
| Docs | `docs/rehearsals/screenshots/lsf-final-docs.png` |
| Git | `docs/rehearsals/screenshots/lsf-final-git.png` |
| Telemetry | `docs/rehearsals/screenshots/lsf-final-telemetry.png` |

### Earlier dashboard captures

- `docs/rehearsals/screenshots/lsf-overview.png`
- `docs/rehearsals/screenshots/lsf-prd.png`
- `docs/rehearsals/screenshots/lsf-architecture.png`
- `docs/rehearsals/screenshots/lsf-evals.png`
- `docs/rehearsals/screenshots/lsf-checkpoint.png`

### Load simulator and VPS readiness

- `docs/rehearsals/screenshots/lsf-load-simulator.png`
- `docs/rehearsals/screenshots/lsf-load-simulator-overload.png`
- `docs/rehearsals/screenshots/lsf-vps-ready.png`
- `docs/rehearsals/screenshots/lsf-vps-fallback.png`

### Other

- `docs/backlog/assets/form-audit-slide.jpg` (backlog item illustration)

## Live build screenshots (peak6-live-build)

Captured on 2026-10-20 from the real `peak6-live-build` run (booking app built with this flow; repo: https://labs.gauntletai.com/kaushalbalagurusamy/peak6-live-build).

- Demo videos (captioned, real recordings): [booking-demo.mp4](live-build/video/booking-demo.mp4) (two users, hold race, expiry, price moves only on purchase, tests passing live: 24/24) and [dashboard-demo.mp4](live-build/video/dashboard-demo.mp4) (phase clock, hash-chained stop ledger with the superseded stop, telemetry, experiments, ADRs, PRD, nested architecture diagram, evals, git).
- Every dashboard tab with a caption saying what it shows and where the data comes from: [live-build/TOUR.md](live-build/TOUR.md) (images in [live-build/img/](live-build/img/)).
- Honest limits: captions lag the screen by up to about a second; the nested diagrams load Mermaid from a CDN; phases 7-9 were logged after the fact, so they read 0 min.

![Human stops tab](live-build/img/02-stops.png)
![Nested architecture diagram](live-build/img/08b-architecture-level2.png)
