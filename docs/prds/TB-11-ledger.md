# TB-11: Ticket ledger and its hooks

| | |
|---|---|
| **Delivers** | R-17 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/graph-and-ledger.md`, `docs/contracts/hook-io.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Give agents shared, tamper-evident memory in files, and give sessions their state at start.

## Required behaviour
1. `create_ledger` writes the nine sections in the contract's order; creating over an existing file raises `LedgerError`.
2. `append` adds a block with header `### <ISO 8601 UTC time> <role>`, the text, and a chain line whose SHA-256 covers the previous chain value (empty for the first) and the entry text.
3. `append` enforces section ownership from the contract and raises `LedgerError` for any other role or an unknown section.
4. `verify` returns an empty list for an intact ledger and names the section and entry for an edited entry, a removed entry, a reordered entry or a missing chain line.
5. `load_summary` returns the section headings and the latest entry of each section, at most 4,000 characters, deterministically.
6. `ledger_audit` (SubagentStop): its `decide` always allows; its `record` appends an Audit Trail entry (agent type, agent id, and the first 200 characters of the last message with secret-shaped values removed) to the ticket named by `.factory/current_ticket`; if that file is absent it does nothing.
7. `session_start` `emit` prints `load_summary` of the current ticket's ledger, or a single line saying no ticket is active.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/ledger.py`, `factory/hooks/ledger_audit.py`, `factory/hooks/session_start.py`, `tests/test_ledger.py`, `tests/hooks/test_ledger_hooks.py`, `docs/hooks/ledger.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Ticket creation workflows, the tracker.
