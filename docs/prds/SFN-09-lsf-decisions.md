# SFN-09: lsf decision records (owner direction 2026-10-20, interview prep)

Source: `docs/requirements/owner-followup-2026-10-20-codex-hitl-analysis.md`. Scope: `skills/lsf` only (and its tests).
The factory `sf` side is explicitly out of scope today.

## Contract (binding; ids D-1..D-12)

D-1. A decision is a human stop; its id is the stop `name`. Every stop derived from the ledger has `state`, one of
`asked` (open), `answered` (released), `recorded`, `applied`. Old ledgers without the new fields still verify and derive.
D-2. `lsf hitl request NAME --question Q [--artifact P]... [--option TEXT]... [--reason R]`. `--option` repeats, at most 6,
each 1..120 chars after cleaning. The open entry stores `options` (list) and `proposal_hash`: sha256 hex of canonical
JSON (`sort_keys`, no spaces) of `{"question", "options", "artifacts": [{"path", "sha256"}]}` where `sha256` is the hash of the
file bytes at open time, or null when the path is missing, not a regular file, outside the repo root, or over 1 MiB.
`phase end` checkpoints use the same function (no options).
D-3. Answering = releasing. `hitl_release(root, name, note, by, via, answer=None, proposal_hash=None)`. If the stop has options,
`answer` must equal one of them exactly, else `Usage` (HTTP 400). If `proposal_hash` is given and differs from the stored one,
`Fail("stale ...")` (HTTP 409). Before releasing, the hash is recomputed from the current artifacts; a difference from the stored
hash is `Fail("proposal changed since it was asked; ask again")` (HTTP 409) and nothing is released. A stop with options and
no `answer` is refused. The release entry stores `answer` and `proposal_hash`.
D-4. Dashboard `POST /api/hitl/release` body is `{name, note, answer, proposal_hash}`. When the stop has a `proposal_hash`, a body
without `proposal_hash` is 400. Token, host and size checks are unchanged. The CLI release gains `--answer`; the strict-mode TTY
rule is unchanged and applies to it.
D-5. `lsf hitl recorded NAME --where PATH [--note N]` is valid only when state is `answered`; PATH must be an existing file or
directory inside the repo root (no escape, symlink resolved). It appends a chained `recorded` entry. Otherwise `Fail`.
D-6. `lsf hitl applied NAME --evidence TEXT` is valid only when state is `recorded`; evidence is required (non-blank after
cleaning). It appends a chained `applied` entry. Otherwise `Fail`. Neither command can release a stop, so neither is gated by
strict mode; both emit events (stage `hitl`, verdicts `recorded`, `applied`).
D-7. Derived stop fields: existing ones plus `id`, `state`, `options`, `proposal_hash`, `answer`, `answered_at`, `recorded_where`,
`recorded_at`, `applied_evidence`, `applied_at`. `/api/state` and `lsf hitl status --json` expose them. Chain verification, the
head pointer and cross-checks cover the new entry kinds.
D-8. `lsf hitl status` text prints `state` per stop; exit 3 only while any stop is `asked`.
D-9. Dashboard: a banner at the top of every tab reads `N decision(s) waiting for you` while any stop is asked (hidden otherwise).
The Human stops tab shows asked cards first with the four-step chip row Asked / Answered / Recorded / Applied, the options as
radio buttons (required before submit), a note field, and a `Submit answer` button (a stop without options keeps `Approve`).
Submit sends the stop's `proposal_hash`; a 409 shows the server message and keeps the card. Answered, recorded and applied cards
list below with their answer, record location and evidence; an answered card says `not applied yet` until applied.
D-10. A decision whose state is answered or recorded must never render as applied; nothing in the dashboard or CLI output may
say `applied` before an `applied` entry exists.
D-11. The Mac quick start in `skills/lsf/SKILL.md` documents the lifecycle in five lines; the lsf evals for the old Approve button
keep passing (a stop without options behaves as before).
D-12. Stdlib only, Python 3.9 syntax. Pending/historical separation: pending decisions come from the live ledger and never from
a bundle snapshot.
