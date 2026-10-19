# Ticket ledger and its hooks (TB-11)

Delivers R-17 (and the documentation half of R-24). Contract: `docs/contracts/graph-and-ledger.md` and clarifications C-19 to C-25, C-30, C-31, C-35 (binding). Code: `factory/ledger.py`, `factory/hooks/ledger_audit.py`, `factory/hooks/session_start.py`.

## What it is
A ticket's shared memory: one Markdown file `<ledger_dir>/<ticket_id>.md` with nine fixed sections in this order: Spec, Research, Architecture, Evals, Implementation, Review, Test Results, Deploy Log, Audit Trail. Entries are append-only and hash-chained in append order, so editing, deleting or reordering an earlier entry is detected by `verify`. Each role may write only its own section (section ownership, C-35); an entry that tries to forge a chain or section marker is refused. Deterministic: the clock is passed in; no network, no model call, nothing project-specific.

## API (`factory.ledger`)
- `create_ledger(path, ticket_id, title)`; `append(path, section, role, text, now)`; `verify(path) -> list[str]` (empty means intact, each problem names the section and entry); `load_summary(path) -> str` (what a new session reads); `current_ticket(project_root) -> str | None` (reads `.factory/current_ticket`); `LedgerError`.

## Hooks
- `ledger_audit` (SubagentStop, no matcher): decides `allow` and, in `record`, appends one Audit Trail entry per sub-agent run (agent, outcome, redacted text). It never blocks.
- `session_start` (SessionStart, no matcher): `decide` always allows; `emit` returns the active ticket's ledger summary, or `No ticket is active.` when there is no current ticket or no ledger file.

## Recorded example (produced by running the code)
```python
create_ledger(p, "T-1", "Add login rate limit")
append(p, "Spec", "design", "Limit logins to 5 per minute per account.", "2026-10-19T12:00:00Z")
append(p, "Implementation", "implement", "Added limiter module.", "2026-10-19T12:30:00Z")
verify(p)   # -> []
```
The file then reads:
```
# T-1: Add login rate limit
<!-- entries: 2; head: b3ea2314856e2b9a22e9a55c304651fcccaf82d39840205108275b1803fc8443 -->

## Spec

### 2026-10-19T12:00:00Z design
Limit logins to 5 per minute per account.
<!-- chain: d54f3f55d28d8e36bf4efb306837f4226726d39e877dc66716ebc47ff7a2e952; seq: 1 -->
...
```
After editing the Spec text (`5 per minute` to `500 per minute`), `verify(p)` returns `["section 'Spec' entry 1: chain mismatch (entry text was edited, or the chain was altered)"]`.

## Limits
The chain proves the file was not edited after the fact; it cannot stop someone who rewrites the whole file and recomputes every hash, so git history remains the backstop. Whether a sub-agent's own frontmatter Stop hook fires as SubagentStop is still unverified (C-34).
