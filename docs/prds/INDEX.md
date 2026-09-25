# Tracer-bullet PRDs: the agent layer

Each PRD is one thin slice that is testable on its own. Contracts in `docs/contracts/` are published first; the evals are authored from them and these PRDs before any implementer starts. Rules for the build are in `docs/factory/METHODOLOGY.md`; requirement IDs are in `docs/factory/requirements.md`.

| PRD | Title | Delivers | Depends on | Kind | Model |
|---|---|---|---|---|---|
| [TB-01](TB-01-profile-loader.md) | Project profile loader | R-02 | none | BLOCKING | Sonnet |
| [TB-02](TB-02-role-specs.md) | Seven role specs and loader | R-04, R-05, R-06, R-07, R-08 (data part) | none | BLOCKING | Sonnet |
| [TB-03](TB-03-agent-generator.md) | Agent file generator | R-01, R-04, R-05, R-06, R-07, R-08 | TB-01, TB-02 | BLOCKING | Sonnet |
| [TB-04](TB-04-hook-core.md) | Hook core: payload, decision, adapter, command line | R-09, R-24 | TB-01 | BLOCKING | Sonnet |
| [TB-05](TB-05-path-guard.md) | Path guard hook | R-06, R-10 | TB-04 | PAR | Sonnet |
| [TB-06](TB-06-blindness-guard.md) | Implement blindness guard hook | R-11, R-21 | TB-04 | PAR | Opus |
| [TB-07](TB-07-secrets-guard.md) | Secrets guard hook | R-12, R-23 | TB-04 | PAR | Sonnet |
| [TB-08](TB-08-bash-guard.md) | Bash guard hook: git hygiene and one-way doors | R-13, R-14 | TB-04 | PAR | Sonnet |
| [TB-09](TB-09-stop-gate.md) | Implement stop gate hook | R-15 | TB-04 | PAR | Sonnet |
| [TB-10](TB-10-subagent-stop-validators.md) | Sub-agent stop validators | R-16 | TB-04 | PAR | Sonnet |
| [TB-11](TB-11-ledger.md) | Ticket ledger and its hooks | R-17 | TB-04 | PAR | Sonnet |
| [TB-12](TB-12-graph.md) | Stage graph as data | R-03 | TB-01 | PAR | Sonnet |
| [TB-13](TB-13-settings-emitter.md) | Project settings emitter | R-18, R-23 | TB-01, TB-02, TB-04 | BLOCKING | Sonnet |
| [TB-14](TB-14-walking-skeleton.md) | End-to-end walking skeleton and shadow routing log | R-19, R-20, R-01 | TB-03, TB-05 to TB-13 | BLOCKING | Opus |

## Dependency graph and waves
```
TB-01 ──┬─> TB-03 (with TB-02) ─────────────────────┐
TB-02 ──┘                                            │
TB-01 ──> TB-04 ──> TB-05 TB-06 TB-07 TB-08 TB-09 TB-10 TB-11 ─┤
TB-01 ──> TB-12                                      │
TB-01, TB-02, TB-04 ──> TB-13 ───────────────────────┤
                                                     └─> TB-14
```
- **Wave 1:** TB-01, TB-02
- **Wave 2:** TB-03, TB-04, TB-12
- **Wave 3:** TB-05, TB-06, TB-07, TB-08, TB-09, TB-10, TB-11 (run in two batches of three or four)
- **Wave 4:** TB-13
- **Wave 5:** TB-14

BLOCKING means another slice needs its output; PAR means it needs only committed inputs. Slices in one wave are file-disjoint by their OWN lists and may run in parallel, three or four at a time, each in its own git worktree and merged by the orchestrator by explicit path.

## Coverage of the requirements
R-01 (02, 03, 14), R-02 (01), R-03 (12), R-04 (02, 03), R-05 (02, 03), R-06 (03, 05), R-07 (02, 03), R-08 (03), R-09 (04), R-10 (05), R-11 (06), R-12 (07), R-13 (08), R-14 (08), R-15 (09), R-16 (10), R-17 (11), R-18 (13), R-19 (14), R-20 (14), R-21 to R-24 (method and documentation, checked by process evidence and by the docs each PRD requires).

## Rules for the slices
- Implementers read their PRD and the contracts it names, and nothing under `evals/`.
- Everything project-specific comes from the profile; no PRD, role file or hook may name a specific project.
- Hooks are deterministic: no network, no model call.
- The orchestrator alone edits `pyproject.toml`, `factory/__init__.py`, `factory/cli.py` and CI files, between agents.
