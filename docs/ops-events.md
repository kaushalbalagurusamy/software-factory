# Ops events and the live dashboard (SFN-01)

The system writes the dashboard's inputs; an agent no longer has to remember to.

## Stage events
`factory.ops.events.emit(root, stage, slice_id, verdict, note="", source="sf", role=None) -> bool` appends one JSON line to `<root>/ops/events.jsonl`:
`at` (UTC, seconds), `stage`, `slice`, `sha` (HEAD or `unknown`), `verdict`, `note`, `source`, and `role` when given.

- One `os.write` on an `O_APPEND` descriptor under an exclusive `flock`, so writers never interleave. A file without a final newline gets one first.
- `note` is cut to 2,000 characters. Control characters become spaces, surrogates are replaced, and secret-shaped values are redacted (the `factory.hooks.ledger_audit.redact` shapes). Redaction also runs on the note with control characters removed, so a secret split by a newline, tab or NUL is still caught, and an unterminated `BEGIN ... PRIVATE KEY` header hides everything after it.
- `ops/` or `events.jsonl` as a symlink that resolves outside `root` is refused. Links that stay inside are allowed.
- A `root` that does not exist is an error (nothing is created); only `ops/` below an existing root is created.
- Failure (read-only, full disk, refusal) returns False and prints `event not recorded: <reason>` on stderr; it never raises. `SF_EVENTS=off` writes nothing, silently.
- `source=None` omits the key. Only `scripts/ops-stage-event.sh` uses it, because the existing ops test pins that script's events to six keys (a contradiction between E-01 and E-14, resolved this way).
- `scripts/ops-stage-event.sh` runs `python3 -I` and inserts the factory path itself, so a `factory` package in the working directory cannot shadow the real one.

## Which commands leave an event
`factory.cli.run_tool` emits after the delegated tool finishes, with verdict `pass` (exit 0) or `fail`, note `exit=<code>`. The exit code is returned unchanged.

| Command | Stage |
|---|---|
| `intake` check, record-sweep, signoff, gate, seeds check, experiments check | `0-intake` |
| `slice` check, triage / lock / tick / verify / amend / done | `4-slice` / `5-evals` / `6-implement` / `7-qa` / `8-review` / `9-drift` |
| `qa` (all) | `7-qa` |
| `contracts` check-contracts / verify | `4c-contracts` / `8-gate` |
| `structure` diff / others | `8-gate` / `4b-structure` |
| `hitl` request, release | `hitl` (verdict `open` / `released` on success, else `fail`) |
| `ops bundle` | `11-commit` |

The slice id is the basename of `--slice` or, for `slice`, the first positional DIR; otherwise `-`. Nothing is emitted for exit 2, `--help`, `hitl status`, `contracts report`, `ops runtime` and every other command. `SubagentStop` hooks (`subagent_stop`, `ledger_audit`) record `subagent-stop` / `stopped` with `source` `hook` and `role` the agent type, without touching the hook decision.

## Commands
- `sf ops init [--dir DIR]`: creates `DIR/ops/config.json` (`{}`) and an empty `events.jsonl` only if absent, installs the viewer shell, bundles HEAD, prints one line per tab (`available` / `not available: <reason>`). Exit 2 outside a git repository or without a commit.
- `sf ops backfill [--limit N] [--repo DIR]`: newest first, skips commits with `ops/snapshots/<sha>/manifest.json`, lists failures and goes on. Exit 1 if any failed.
- `sf ops status [--repo DIR] [--json]`: `{"head", "snapshot", "behind", "events"}`; exit 0 when current, 4 when behind or no snapshot.
- `sf ops autobundle install|uninstall|status [--repo DIR]`: a marked block in the shared `post-commit` hook runs `sf ops bundle --sha HEAD` in the background (120 s timeout, output discarded, never fails the commit). Install keeps existing content and is idempotent; uninstall removes only the block. `status` prints `installed: <path>` or `not installed: <path>` and exits 0. A hook that exits before the block (for example `exit 0`) never reaches it. The hook runs the normal bundle, so each commit gets an `11-commit` event. `ops/events.jsonl` is a local log, not a committed file (C-50): `init` and `autobundle install` add it to the local exclude file (`git rev-parse --git-path info/exclude`; idempotent, never a tracked `.gitignore`), so `git status --porcelain` stays clean after a commit.

## Dashboard
`ops/index.json` has a top-level `head` (the commit of the newest default `--sha HEAD` bundle). `runtime.json` has `repo_head` and `behind` (null when unknown). The viewer shows `Snapshot is N commits behind the repository`, `Up to date`, or `Repository state unknown` (no `runtime.json`, or no snapshot). Snapshots filter events to those at or before the commit date; a snapshot with no events reports `not available: no stage events recorded`. Runtime telemetry stays out of snapshots.
