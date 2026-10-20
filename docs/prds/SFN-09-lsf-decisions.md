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
D-4. Dashboard `POST /api/hitl/release` body is `{name, note, answer, proposal_hash}`. When the stop has options, a body
without `proposal_hash` is 400 (a stop without options keeps accepting a body with no hash, per D-11; the server-side drift
check of D-3 still applies to it). Token, host and size checks are unchanged. The CLI release gains `--answer`; the strict-mode TTY
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

## Rollback from the commit log (owner direction 2026-10-20, added to SFN-09)

D-13. `lsf rollback SHA [--yes]` and dashboard `POST /api/rollback` body `{sha, confirm_sha}` create a NEW commit that reverts SHA
(`git revert --no-edit SHA`). It never resets, rebases, amends, force-pushes or deletes; history only grows. The CLI without
`--yes` prints what would be reverted (subject, files changed) and exits 2 without changing anything. The endpoint needs the same
token, host and size checks as release, and `confirm_sha` must equal the full resolved sha of `sha` (a second, in-page step).
D-14. Refusals (nothing changed, HTTP 409 / CLI exit 1, message names the reason): working tree not clean (tracked changes or
staged; untracked files are ignored); SHA does not resolve to a commit; SHA is not an ancestor of HEAD; SHA is a merge commit;
SHA is the root commit; a stop is `asked` for the current phase is NOT a reason. If `git revert` conflicts, run `git revert --abort`
and report 409 `revert conflicts; resolve by hand` with the tree restored. Success returns `{ok, reverted, new_head}` and emits
an event stage `rollback`, verdict `reverted`, note with both short shas. Rollback is not a gate: it never releases, answers or
applies a decision.
D-15. Dashboard: in the git commit log tab each commit row has a `Rollback` button (not on merges or the root commit). Clicking it
expands the row to show the commit subject, files changed and the text `This adds a new commit that undoes it; history is kept.`,
with `Confirm rollback` and `Cancel`. Confirm posts `confirm_sha`. Without a token in the URL the button is replaced by the
command `lsf rollback SHA --yes`. After success the log reloads and the new revert commit appears on top. The commit's historical
ops state view is unchanged.
D-16. The PreToolUse `hook guard` also denies agent Bash that calls `/api/rollback`, and treats `lsf rollback` like the human-only
release path: refused under strict mode without a TTY (same rule and message style as release).

## Error logs behind failing tests and bugs (owner direction 2026-10-20, added to SFN-09)

D-17. `lsf event STAGE VERDICT ... --log-file PATH` (and `--log -` reading stdin) stores the log: bytes are decoded as UTF-8
with replacement, redacted with the same redaction as events (secrets, bearer tokens, URL userinfo, control characters), cut to
the LAST 64 KiB (a line saying `[earlier output cut: N bytes]` first when cut), and written to `.lsf/logs/<event-id>.txt`
(regular file, never following symlinks, directory created 0700 files 0600). The event gains `log` = that repo-relative path.
A missing or unreadable log file is `Usage`, and no event is emitted. Events with verdict other than a failure may carry logs too.
D-18. Collectors: a failing eval/test item (an event with verdict `fail`, `error` or `red`, and any item whose golden/eval result
is failing) exposes `log` when the event had one. A bug item exposes `log`, taken from a `Log: <repo-relative path>` line in
`docs/bugs/*.md`, else from the most recent failing event with the same slice and criterion; the path must be inside the repo
and exist, otherwise `log` is null and the item says `log: none recorded`. The same shapes are produced by the factory collector
only if it already does; this slice changes lsf only.
D-19. Dashboard: the rows of failing tests and bugs are clickable (keyboard: Enter/Space). Clicking expands an Error log panel
below the row that loads the log through the existing file endpoint (capped, redacted again on read), shows it in a scrollable
monospace block with a `Copy` button, and turns every `path:line` occurrence that resolves inside the repo into an editor link
using the shared editor-links builder (so a traceback line opens in the owner's editor). A row without a log shows `No log
recorded. Record one with: lsf event STAGE fail --log-file FILE`. Loading failures show the error text, never an empty panel.
Clicking again collapses. The log is never executed or inserted as HTML.
