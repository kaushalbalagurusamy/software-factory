# SFN-01: The dashboard updates itself as the loop runs

| | |
|---|---|
| **Delivers** | Owner clauses D1, D1b, D6, D10 in `docs/requirements/sf-owner-flow-clauses.tsv` |
| **Depends on** | none (extends `factory/ops`, `factory/cli.py`) |
| **Implementer model** | Sonnet |
| **Source of truth** | `docs/requirements/sf-owner-flow.md`, verbatim |

## Purpose
Today `ops/events.jsonl` only grows when an agent remembers to run `scripts/ops-stage-event.sh`, nothing bundles new commits, and no command creates the dashboard early. The owner wants a dashboard "updated throughout this sf loop" that "stays live with the repo". Make the system write the events and the snapshots, not the agent.

## UX story (first)
As the owner opening the dashboard on a phone mid-run, I see the stage the run is in, its last verdict, and a notice if the newest snapshot is older than the repo's HEAD, without anyone having run a script.

## Required behaviour
Criterion ids are public; tests are not.

- **E-01 event writer.** `factory/ops/events.py` exposes `emit(root, stage, slice_id, verdict, note="", source="sf", role=None) -> bool`. It appends exactly one JSON line to `<root>/ops/events.jsonl` with keys `at` (UTC ISO 8601 seconds), `stage`, `slice`, `sha` (HEAD of `root`, or `"unknown"` when not a git repo or no commit), `verdict`, `note`, `source`, and `role` only when given. One `os.write` on an `O_APPEND` descriptor per event, so concurrent writers never interleave a line. `ops/` is created if absent. Returns True when written.
- **E-02 bounds and safety.** `note` is truncated to 2,000 characters; control characters other than space are replaced by a space; the line is valid JSON for any input including non-UTF-8-safe surrogates (they are replaced, never raise). If `<root>/ops` or `events.jsonl` is a symlink that resolves outside `root`, nothing is written and `emit` returns False. Values shaped like secrets (the redaction used by `factory.hooks`) are replaced in `note`.
- **E-03 telemetry never changes the verdict.** A failure to write (read-only directory, full disk, symlink refusal) makes `emit` return False and print one line `event not recorded: <reason>` to stderr; it never raises. Setting `SF_EVENTS=off` makes `emit` write nothing and return False without a message.
- **E-04 every sf command leaves an event.** `factory/cli.py` `run_tool` emits one event after the delegated tool finishes, for these subcommands: `intake` (check, record-sweep, signoff, gate, seeds check, experiments check) stage `0-intake`; `slice` check/triage `4-slice`, lock `5-evals`, tick `6-implement`, verify `7-qa`, amend `8-review`, done `9-drift`; `qa` (all subcommands) `7-qa`; `contracts` check-contracts `4c-contracts`, verify `8-gate`; `structure` diff `8-gate`, others `4b-structure`; `hitl` request/release stage `hitl` with verdict `open`/`released`, status none; `ops bundle` `11-commit`. Verdict is `pass` for exit 0 and `fail` otherwise, with `exit=<code>` in the note; `hitl request` and `release` use their own verdicts when they succeed. The slice id is taken from a `DIR`/`--slice` argument when one is present (its directory name), else `-`. Commands not listed emit nothing. The exit code of the delegated tool is returned unchanged.
- **E-05 read-only commands stay quiet.** `hitl status`, `--help`, usage errors (exit 2 from argument parsing) and `ops runtime` emit no event.
- **E-06 hook events.** `factory.hooks.subagent_stop` and `ledger_audit` record a `subagent-stop` event (`source` `hook`, `role` = the agent type, verdict `stopped`) through `emit`, without changing the hook's decision or exit code, even when `emit` fails.
- **E-07 `sf ops init [--dir DIR]`.** Creates `ops/config.json` only if absent (never overwrites), creates an empty `ops/events.jsonl` if absent, installs the viewer shell, runs one `bundle` for HEAD, and prints one line per historical tab: `available` or `not available: <reason>`. Running it twice changes nothing and exits 0. It refuses with exit 2 outside a git repository.
- **E-08 `sf ops backfill [--limit N] [--repo DIR]`.** Bundles commits of the current branch, newest first, skipping any commit that already has a snapshot, one at a time, default limit 500. Prints how many were built, skipped and failed; a commit that fails to bundle is listed and does not stop the rest. Exit 1 if any failed.
- **E-09 `sf ops status [--repo DIR]`.** Prints HEAD, the newest snapshot's commit, the number of commits the snapshot is behind (`git rev-list --count`), and the event count. Exit 0 when current, 4 when behind or when no snapshot exists. `--json` prints the same as one object.
- **E-10 post-commit bundling.** `sf ops autobundle install|uninstall|status [--repo DIR]` manages a marked block in the repository's `post-commit` hook (`# >>> sf ops autobundle >>>` ... `# <<< sf ops autobundle <<<`). The block runs `sf ops bundle --sha HEAD` in the background with a 120 s timeout and never makes the commit fail. Install preserves any existing hook content, is idempotent (a second install changes no byte), and sets the executable bit. Uninstall removes only the block and deletes the file only if nothing else remains. Works in a linked worktree (uses the common hooks directory).
- **E-11 staleness in the viewer.** `ops/index.json` gains a top-level `head` (the commit the last bundle ran from) and the runtime collector writes `repo_head` and `behind` into `runtime.json`. The viewer shows a banner `Snapshot is N commits behind the repository` when `behind` is above zero and the text `Up to date` otherwise; when `runtime.json` is absent it shows `Repository state unknown`, not zero.
- **E-12 dev journey fills.** After E-04 events exist, the Dev journey tab for a snapshot shows them. A snapshot built before any event exists reports `not available: no stage events recorded` rather than an empty table.
- **E-13 stage events are history, not telemetry.** Events remain in the historical tabs and are filtered to the snapshot's commit date or earlier; runtime telemetry stays out of snapshots, as before.
- **E-14 nothing existing breaks.** Existing `tests/test_ops*.py`, `scripts/ops-stage-event.sh` (still works, now implemented through `emit`) and the unit and eval suites keep passing without edits to their assertions.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write unit tests under the paths you own (unit coverage, not the gate). Document in `docs/ops-events.md`. Where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/ops/events.py`, `factory/ops/cli.py`, `factory/ops/bundle.py`, `factory/ops/runtime.py`, `factory/cli.py` (only the `run_tool` emission and the `ops` subcommand wiring), `factory/hooks/subagent_stop.py`, `factory/hooks/ledger_audit.py`, `ops/shell/index.html` (banner and dev-journey wording only), `scripts/ops-stage-event.sh`, `tests/test_ops_events.py`, `tests/test_ops_cli_native.py`, `docs/ops-events.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/prds/**`, `docs/requirements/**`, `pyproject.toml`, `factory/ops/collect.py` (owned by SFN-03), any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran. Use `scripts/bounded-pytest.sh` for any test run, never build large inputs by repetition.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Deploying the dashboard; per-product wiring (SFN-05); collectors and tab content (SFN-03).
