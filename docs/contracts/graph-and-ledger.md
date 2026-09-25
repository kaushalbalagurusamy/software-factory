# Contract: stage graph and ticket ledger

Status: published.

## Graph (`factory.agents.graph`)
`load_graph(profile) -> Graph`; `Graph.validate()` raises `GraphError` naming the problem; `Graph.select(subset_name) -> Graph`; `Graph.order() -> list[stage id]` (a deterministic topological order over `edges`, ignoring `loops`).

Validation: every stage id is unique; every stage's role is one of the seven; every edge and loop endpoint exists; `edges` contain no cycle; a back-reference is allowed only as a declared entry in `loops`; every stage has a path from a start stage (no incoming edges) and at least one end stage exists; a gate stage must have a human-facing role or be marked `gate: true`. `select` keeps only stages whose role is in the subset and reconnects edges across removed stages; it raises if the subset removes every start or end stage.

## Ledger (`factory.ledger`)
A ticket ledger is a Markdown file `<ledger_dir>/<ticket_id>.md` with fixed sections in this order: `Spec`, `Research`, `Architecture`, `Evals`, `Implementation`, `Review`, `Test Results`, `Deploy Log`, `Audit Trail`. Each entry appended to a section is a block starting with a header line `### <ISO 8601 UTC time> <role>` followed by text, then a trailing line `<!-- chain: <sha256 hex> -->` where the hash covers the previous chain value (empty string for the first entry) and this entry's text; so any edit to an earlier entry is detectable.

API: `create_ledger(path, ticket_id, title)`; `append(path, section, role, text, now) -> None` (raises `LedgerError` if the role may not write that section; section ownership: research→`Research`, design→`Spec` and `Architecture`, test→`Evals`, `Test Results` and `Deploy Log`, implement→`Implementation`, review→`Review`, orchestrator→`Audit Trail` and `Deploy Log`); `verify(path) -> list[str]` returns problems (empty when intact); `load_summary(path) -> str` returns the text the session-start hook injects (section headings plus the latest entry of each, at most 4,000 characters).
