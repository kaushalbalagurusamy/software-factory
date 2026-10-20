# Ops events and the live dashboard (SFN-01)

The system writes the dashboard's inputs; an agent no longer has to remember to.

## Stage events
`factory.ops.events.emit(root, stage, slice_id, verdict, note="", source="sf", role=None) -> bool` appends one JSON line to `<root>/ops/events.jsonl`:
`at` (UTC, seconds), `stage`, `slice`, `sha` (HEAD or `unknown`), `verdict`, `note`, `source`, and `role` when given.

- One `os.write` on an `O_APPEND` descriptor under an exclusive `flock`, so writers never interleave. A file without a final newline gets one first.
- `note` is cut to 2,000 characters. Surrogates are replaced and secret-shaped values are redacted (the `factory.hooks.ledger_audit.redact` shapes, plus `Bearer <token>` and `scheme://user:password@host` userinfo). Control characters become spaces, but redaction runs on both the spaced and the control-characters-removed view: a secret that shows only in the joined view (split by a newline, tab or NUL) replaces the whole field with `[REDACTED]`. An unterminated `BEGIN ... PRIVATE KEY` header hides everything after it.
- A symlink at `ops/` or `ops/events.jsonl` is refused whatever its target, and the file is opened with `O_NOFOLLOW` and must be a regular file.
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

The event is written to the repository of the command's `--root`, `--repo`, `--repo-root` or `--slice` path (or the `slice` DIR), else the cwd's repository. The slice id is the basename of `--slice` or, for `slice`, the first positional DIR; otherwise `-`. Nothing is emitted for exit 2, `--help`, `hitl status`, `contracts report`, `ops runtime` and every other command. `SubagentStop` hooks (`subagent_stop`, `ledger_audit`) record `subagent-stop` / `stopped` with `source` `hook` and `role` the agent type, without touching the hook decision.

## Commands
- `sf ops init [--dir DIR]`: creates `DIR/ops/config.json` (`{}`) and an empty `events.jsonl` only if absent, installs the viewer shell, bundles HEAD, prints one line per tab (`available` / `not available: <reason>`). Exit 2 outside a git repository or without a commit.
- `sf ops backfill [--limit N] [--repo DIR]`: newest first, skips commits with `ops/snapshots/<sha>/manifest.json` (but re-lists in `index.json` any such commit the index lost), lists failures and goes on. Exit 1 if any failed.
- `sf ops status [--repo DIR] [--json]`: `{"head", "snapshot", "behind", "events"}`; exit 0 when current, 4 when behind or no snapshot. When the snapshot's commit is not an ancestor of HEAD (HEAD is older, or on another line), `behind` is null, the text adds `diverged`, the JSON gains `"diverged": true`, and the exit code is 4. `runtime.json` likewise reports `behind` null, never 0.
- `sf ops autobundle install|uninstall|status [--repo DIR]`: a marked block in the repository's `post-commit` hook (the hooks directory `git rev-parse --git-path hooks` names, so a linked worktree or `core.hooksPath` is honoured) runs `sf ops bundle --sha HEAD` in the background (120 s timeout, output discarded, never fails the commit).
  - Install refuses (exit 1, nothing written) a hook whose shebang is not sh, bash, dash or zsh (directly or through `env`) and a hook with a half marker block. It puts the block right after the shebang, so a later top-level `exit` cannot skip it, and keeps the rest of the hook. A second install changes no byte. It also creates `ops/config.json` (`{}`) if absent: the block acts only when the repository toplevel has that file, so a shared `core.hooksPath` never creates `ops/` in a repository that did not opt in.
  - The block resolves `sf` from PATH when the hook runs, and falls back to the interpreter and checkout recorded at install time (shell-quoted) only if `sf` is not found and they still exist.
  - Uninstall removes only the block, and deletes the file only if nothing else remains.
  - `status` prints `installed: <path>` (exit 0), `not installed: <path>` (exit 0), or `not effective: <reason>` (exit 1) when the hook is not executable, its shebang is unsupported, a line before the block exits, the markers are incomplete, or `ops/config.json` is missing.
  - The hook runs the normal bundle, so each commit gets an `11-commit` event. `ops/events.jsonl` is a local log, not a committed file (C-50): `init` and `autobundle install` add it to the local exclude file (`git rev-parse --git-path info/exclude`; idempotent, never a tracked `.gitignore`), so the log never shows in `git status`. Other generated files (`ops/index.json`, `ops/snapshots/`, ...) are not excluded: in a fresh repository the untracked `ops/` directory does appear in `git status` until the project ignores or commits it.

## Dashboard
`ops/index.json` has a top-level `head` (the commit of the newest default `--sha HEAD` bundle; it never moves to a commit that is not a descendant of the current head). Index updates take an exclusive lock (`ops/.lock`, `flock`; an atomic `mkdir` lock where `fcntl` is missing) so parallel bundles lose no entry. `runtime.json` has `repo_head` and `behind` (null when unknown or diverged). The viewer shows `Snapshot is N commits behind the repository`, `Up to date`, or `Repository state unknown` (no `runtime.json`, or no snapshot). Stage events come from the committed `ops/events.jsonl` when the commit tracks it, otherwise from the working-tree log (source label `local log`), read at bundle time into the snapshot blob; only events at or before the commit's committer date are kept. A snapshot with no such event reports `not available: no stage events recorded`. Runtime telemetry stays out of snapshots.
