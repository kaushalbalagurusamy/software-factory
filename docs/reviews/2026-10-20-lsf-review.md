# Adversarial review of `lsf` (2026-10-20)

Scope: `skills/lsf/**` at commit 2613220, `editor-links.js`, `skills/eli12-docs`, `scripts/make-lsf-bundle.sh`. Read-only on product code. Runs used Python 3.9.25 on Linux in temporary repos under `~/.cache/lsfreview/` (one with a space and a `ü` in the path, one with no commits). Server started on an ephemeral port and killed by port.

Bottom line: the core mechanics (phase clock, budget arithmetic, event writes under concurrency, path and Host checks, editor-URL encoding) are good. The demo risk is that the human-in-the-loop story is a convention, not a barrier, and several telemetry numbers on screen are inflated or silently wrong.

## Findings, ranked

### Critical

**C1. An agent can release or erase a human stop with no human, and nothing detects it.** The ledger chain is an unkeyed SHA-256, and `stops.head` is a plain file next to it.
Reproductions (all verified):
1. `rm .lsf/stops.jsonl .lsf/stops.head` after `phase end 0-intake`, then `lsf hitl status` prints `no human stops recorded` (exit 0) and `lsf phase start 1-sweep` succeeds (exit 0). Expected: tamper detected. The events log still holds the `opened` event with no `released`, but nothing cross-checks it.
2. `forge.py` (about 8 lines of Python) appends a `release` entry with a valid chain and rewrites `stops.head`. `lsf hitl status` shows `[released ... by owner]`, exit 0, phase start allowed. No `released` event is emitted, so the Telemetry tab disagrees with the Now tab and nobody is told.
3. Plain `lsf hitl release NAME --by Owner` has no TTY check, no confirmation, and `--by`/`LSF_BY` is free text.
4. SKILL.md step 3 has the agent run `lsf serve`, so the agent sees the token in its own tool output and can `POST /api/hitl/release` itself. `serve --open` also puts the token in the `open` process argv.
5. `lsf phase start` is the only gate. An agent that never calls it, or just keeps writing code, is not stopped; no hook denies tool calls while a stop is open.
Expected for an audience watching HITL: at least the CLI and HTTP routes require something an agent's Bash tool cannot supply.
Fix: (a) `hitl release` requires an interactive `/dev/tty` read and typed confirmation, refusing otherwise (Claude's Bash tool has no controlling TTY; I did not verify that on a Mac); (b) `lsf serve` never prints the token to stdout when stdout is not a TTY, and passes it to the browser via a mode-600 file or the opener only; (c) add a `PreToolUse` Bash hook (blocking) that denies `lsf ... hitl release`, writes to `.lsf/`, and `curl` to the release route, and that denies all tool use while a stop is open; (d) put an HMAC key in a file outside the project (`~/.config/lsf/`) and keep a second copy of the head hash in `events.jsonl`; treat "events say opened, ledger says nothing" as failed verification; (e) always emit a `released` event from the ledger code and have the dashboard flag disagreement. Be honest on screen that this is a procedure: say so in the demo if (a) to (c) are not done.

### High

**H1. A corrupted or half-written ledger is unrecoverable and the budget lies about it.** `stops_append` appends to `stops.jsonl` and then writes `stops.head` (lsf.py:417-426). A kill, SIGSTOP plus kill, lid close or Ctrl-C between the two writes leaves seq N+1 in the file and N in the head. Verified equivalent: after editing one byte of `stops.jsonl`, `hitl status`, `status`, `phase start`, `hitl request` all exit 1 with `stop ledger failed verification`, and there is no repair command, so the demo is dead unless the owner deletes both files (which is C1.1). Worse, `lsf budget` in that state prints `waiting on human: 0.0 min` with exit 0 and no warning (lsf.py:501-504 swallows the Fail): a zero standing for a failed lookup. The dashboard does show a red banner (dashboard.html:226), which is good, but the CLI budget and the `waiting_on_human_minutes` JSON do not.
Fix: write the head first as a pending marker or, simpler, drop `stops.head` and verify only the chain, or write a single record containing both. Make `budget` print `waiting on human: unknown (ledger failed verification)` and null in JSON. Add `lsf hitl repair` that quarantines the file and requires a human.

**H2. Telemetry "pass" counts are inflated.** `verdictClass` (dashboard.html:208-211) counts `done`, `approved`, `released`, `commit`, `ok`, `success` as pass. Every `phase end` defaults to verdict `done`, every release logs `released`, every seen commit is `commit`. The Telemetry "pass" tile and the "Verdicts logged by agents" list therefore show passes when no test has run. In the one-hour scenario I ran, ending three phases and releasing three stops gives pass = 6 with zero evals. An audience watching telemetry will ask. Fix: count only `pass` and `fail` verdicts from `lsf event` (source agent or lsf, type absent), and show phase completions, releases and commits as separate tiles.

**H3. The 20,000-file cap silently makes tabs say "not available".** `WorkTree.paths` sorts then truncates (lsf.py:592-593). Repro: 21,000 files under `a/` plus `research/t.md` gives `research  not available: no research/*.md in the working tree`. That is a false empty for a file that exists. `Source.paths` does the same for historical commits, and `git()` turns a timeout into `None`, so a slow `ls-tree` also reads as "no files". Fix: do not truncate; glob lazily over the stream, or when the cap is hit return `unavailable("file list truncated at 20000; narrow with .lsfignore")`. Distinguish git failure from empty.

**H4. `install.sh` creates a second skill named `lsf`.** When the installed copy differs, it is moved to `~/.claude/skills/lsf.backup-<stamp>` (install.sh:19-24), which still contains `SKILL.md` with `name: lsf`. Verified: after an upgrade, two `SKILL.md` files with `name: lsf` sit in the skills directory. Claude Code loads skills by scanning that directory, so which one wins on demo day is undefined and an old copy can shadow the new one. The repo's own `scripts/skills_sync.py` already uses `~/.claude/skills-backups` for this reason. `scripts/make-lsf-bundle.sh` does the same for `eli12-docs` and `mermaid-nesting-dolls`. Fix: back up to `${CLAUDE_SKILLS_BACKUP_DIR:-$HOME/.claude/skills-backups}/lsf.backup-<stamp>`. Note the spec text (PRD L-01, C-45.13) says `lsf.backup-<UTC>` "there"; the contract needs amending.

**H5. Hooks write events wherever the cwd is, not into the project.** `hooks_config` bakes no `--root` (lsf.py:1125-1132) and `find_root` uses the cwd (lsf.py:207-213). Verified: running the Stop hook from a non-lsf directory creates `.lsf/events.jsonl` there. If the session or a subagent runs from another repo or worktree, the events land in that tree and never reach the dashboard that serves the project; no error anywhere. The payload's `cwd` is ignored. Fix: `hooks install --project DIR` writes `--root DIR` into each command, and the hook refuses (silently, exit 0) to create `.lsf` where none exists.

### Medium

**M1. Budget has no session-level truth and does not match the "60% alignment" claim.** I computed a 72-minute scenario by hand (below). `lsf budget` is right on every number, but (a) it never shows the total (actual 44 + waiting 28 = 72 of a 60-minute session) while the header clock says 72:00, so every bar can read "under plan" or near it while the session is 12 minutes over; (b) waiting is not attributed to a group, so "alignment time" excludes the very minutes the human spends reviewing at alignment checkpoints; with checkpoints attributed it is 52 of 72 minutes (72%), not 29 (40%) which is what the bar shows; (c) the Telemetry tab's phase durations are wall clock (include waiting) while the Now bars exclude it, so two tabs give different numbers for one phase. Fix: add `total`, `waiting_by_group` (stop `X-review` attributed to the group of phase X, mid-phase requests to the open phase), and a session-level over/under flag; use one definition in both tabs.

**M2. Open phase time counts a closed laptop lid.** Open phases and open stops count to now (lsf.py:512, 479). A 30-minute sleep adds 30 minutes to the open phase with no marker, and `LSF_NOW` exported from a rehearsal freezes every timestamp for the live run with no warning (status prints `now` but not that it is overridden). Fix: when `LSF_NOW` is set print `clock overridden` to stderr on every command and show it in the dashboard header; add an idle-gap detector (no event for more than N minutes while a phase is open) shown as "gap, not counted" or as an explicit adjustment.

**M3. Embedded nested diagrams will not open the editor.** The dashboard iframe is `sandbox="allow-scripts"` with a URL that carries no `editor`/`root` query (dashboard.html:349-352). The explorer template reads the editor from its model (default `none`) or from `?editor=&root=` (template.html:338-345), so links inside the diagram show "set the editor and root", and a sandbox without `allow-top-navigation-to-custom-protocols` blocks `vscode://` navigation in Chrome in any case (I could not test Safari). The owner's headline wish was "nested mermaids ... open up specific files on our code editor". The node lists beside the iframe do work (editorUrl, verified), so the requirement is only met outside the diagram. Fix: pass `&editor=..&root=..` from the header settings and add `allow-top-navigation-by-user-activation` plus test on a Mac, or open links via `postMessage` to the parent.

**M4. Docs tab in snapshot mode mixes eras.** `renderDocs` fetches doc bodies from `/api/file` (working tree) even when `S.snap` shows the index from an old commit (dashboard.html:387). Fix: add `/api/at/file?sha=&path=` or show "not available at this commit".

**M5. Redaction gaps in hook notes and events.** Tested on `clean_note`: not redacted are `curl -u admin:hunter2`, URL userinfo `postgres://user:pw@host`, Stripe `sk_live_...` (regex needs `sk-`), `--token VALUE` and `--password VALUE`, `mysql -pSecret`, Google `AIza...`, `npm_...`, `hf_...`, `pass=`. A `git commit -m` or any Bash command containing these reaches `events.jsonl` (200 characters) and the screen. Fix: add these patterns and a rule for `scheme://user:pass@`, plus `-u`/`-p`/`--token|--password|--secret|--key` followed by a value.

**M6. `/api/file` forbidden-name checks are case-sensitive.** `.GIT/config` and `.Env` are compared against `.git` (lsf.py:1356) but `.env` is lowercased; on macOS's default case-insensitive APFS `/api/file?path=.GIT/config` should read `.git/config` (remote URLs may carry credentials). On Linux it returns 404 as expected, so I could not reproduce on a Mac. Fix: compare `s.lower()` for `.git` and `.lsf`, and re-check against `os.path.realpath` plus `os.path.samefile` with the `.git` directory.

**M7. Stale lock blocks Approve for up to 30 s.** After a kill -9 the `.lsf/.lock` directory stays; every ledger write then waits 5 s and exits 1 (`another lsf process holds ...`, verified, 5.1 s), and the dashboard's Approve gets a 409 for up to 30 s. A SIGSTOPped holder older than 30 s has its lock removed by another process while it still thinks it holds it, which can duplicate a `seq`. Fix: write PID and host into the lock, break it when the PID is dead, shorten the staleness window only for dead PIDs.

**M8. `bug_log` is "available" with zero items.** An empty `docs/bug-log.jsonl` gives `bug_log  available, 0 items` in `lsf bundle` (verified) because `if not items and t is None` (lsf.py:783). That breaks the stated rule L-10 and C-45.14. The UI hides it (`items()` returns null), so only `/api/state`, `/api/at` and the bundle JSON are wrong. Fix: `if not items: return unavailable(...)`.

**M9. "Commits seen" counts any Bash command containing the text `git commit`.** `cmd_hook` checks substring only (lsf.py:1224), so `git commit --dry-run`, `echo "git commit"` or a failed commit are all `commit` events, and the sha recorded is whatever HEAD is. Fix: record `commit` only when HEAD differs from the previous event's sha; otherwise log `commit-attempt`.

### Low

- L1. The last 1,000 events are all the dashboard sees (`read_events`), and the tiles say `events 1000` without saying it is capped.
- L2. `ThreadingHTTPServer` has no socket timeout: a slowloris connection holds a thread forever (local only; GETs from other connections still worked in my tests, I did not run a flood).
- L3. No `frame-ancestors` or `X-Frame-Options`; harmless without the token but cheap to add. The token also stays in the URL bar, history and screen share; strip it with `history.replaceState` after reading.
- L4. `cmd_hook` can still print a traceback and exit 1 if the cwd was deleted (`os.getcwd()` raises in `find_root`), which contradicts "always exit 0".
- L5. `git show` reads a whole blob before truncating to 5 MiB; `ls-tree -r` output is unbounded; `os.walk` fallback ignores the cap in its outer loop.
- L6. `doctor`'s port check binds `127.0.0.1` with `SO_REUSEADDR`; on macOS that can succeed while another process holds `*:PORT`, so "port free" can be wrong.
- L7. Editor `none` exists in the Python list but not in the dashboard's select; `.g-build` chip text is 4.08:1 on white and the nav `.dot` is 4.05:1 (both under 4.5); the `Copy path` button is 36 px, not 44.
- L8. Duplicate error output (`stop ledger failed verification` printed on stdout and stderr).
- L9. A phase whose end timestamp precedes its start (clock stepped back) is clamped to 0 minutes with no message.
- L10. The `hooks`' PostToolUse hook launches `python3` on every Bash call; fine, but it is on the demo's critical path with no timeout configured in the settings entry.

## Budget worked scenario (3: planned vs actual vs waiting)

Plan 60 min, weights 0.6/0.2/0.2, so planned align 36, review 12, build 12. Script `~/.cache/lsfreview/scen.sh` with `LSF_NOW` per command:

| time | action |
|---|---|
| 10:00-10:08 | 0-intake; stop opens 10:08, released 10:14 (wait 6) |
| 10:14-10:20 | 1-sweep; stop 10:20, released 10:35 (wait 15) |
| 10:35-10:50 | 2-research; stop 10:50, released 10:52 (wait 2) |
| 10:52-11:10 | 7-implement; mid-phase `hitl request` 10:58, released 11:03 (wait 5) |
| 11:10 | 9-review open; now = 11:12 |

By hand: align = 8 + 6 + 15 = 29 (80.6%); build = 18 minus 5 overlap = 13 (108.3%, over); review = 2 (16.7%); waiting = 6 + 15 + 2 + 5 = 28; check 29 + 13 + 2 + 28 = 72 = 10:00 to 11:12. `lsf budget` printed exactly those numbers (`align 29.0 / 80.6%`, `build 13.0 / 108.3% over plan`, `review 2.0 / 16.7%`, `waiting on human: 28.0`). The arithmetic is correct; see M1 for what it does not tell the audience.

## Other areas checked

- macOS portability (read, plus Python 3.9 run on Linux): no 3.10+ syntax (`doctor` self-check passes), no GNU-only flags in `install.sh`, `install.sh` is idempotent and handles paths with spaces (wrapper content verified), `hooks install` quotes a path with spaces and uninstalls cleanly. Repo with no commits: `sha` is `unknown`, git tab says "no commits reachable". Paths with spaces and `ü`: all commands worked. Not checked: zsh, real BSD userland, `open`, Xcode's `python3` shim and the "install command line tools" dialog that `git`/`python3` can raise on a fresh Mac, Safari.
- Detached HEAD: only read (`rev-parse HEAD` works). Huge history: `git log -n200` is bounded; not run on a large repo.
- Concurrency: 60 parallel `event` plus 25 parallel `hitl request` gave 85 event lines and 25 ledger lines, all valid; no events lost.
- HTTP security (verified by raw requests): Host `evil.com`, `127.0.0.1.evil.com`, `evil.com@127.0.0.1` all 403; `Origin` other than localhost and `null` 403; OPTIONS 405 and no CORS headers; POST without or with a wrong token 403; bad body 400; unknown or released stop 409; `..`, `//`, `%2e%2e` 400; symlink to `/etc/passwd` and out-of-repo symlink 403; `.env` and `.git/config` 403; `--output=x`, `HEAD` and newline injection in `sha` 400 (hex only, so no option injection); token compared with `hmac.compare_digest`; `log_message` is a no-op so the token is never logged. DNS rebinding is blocked by the Host check. Cross-origin POST needs a preflight that is refused. No XSS path found: the dashboard builds DOM with `textContent` only and the markdown renderer emits no links.
- Editor links (`node` against `editor-links.js`): spaces, `ü`, `#`, `?`, newline, `%`, `&` are all encoded; `javascript:` roots and paths, `//host/share`, `..\\` and `a:b.py` return `null`; line `7;rm` is dropped. Only residue: a root containing `..` segments is accepted (owner-typed or from `?root=`; opens a file, runs nothing).
- Dashboard at 390 px (Playwright on localhost): `scrollWidth` 390 = viewport, no page-wide overflow; header, tabs scroll horizontally; all inputs and primary buttons 44 px; no external requests (404 on favicon only). Light and dark tokens read for contrast (L7). 1280 px not rendered; CSS has a 1180 px max-width and sticky header.
- Byte identity: `eli12.py` equals `skills/eli12-docs/scripts/eli12.py`, `jargon.txt` equal, `assets/editor-links.js` equals the dolls copy, and the copy embedded in `dashboard.html` equals the asset. `scripts/skills_sync.py check` passes (`check ok: 15 skills`).

## PRD criteria

| id | status | evidence |
|---|---|---|
| L-01 | Partly | Layout, frontmatter and byte-identical copies satisfied (`SKILL.md:2-4`, cmp); idempotent install satisfied (`install.sh:16-18,41-45`); backup location creates duplicate skill (H4, `install.sh:19-24`) |
| L-02 | Satisfied | all subcommands at lsf.py:1557-1640; exit codes 0/1/2/3 in `main` lsf.py:1668-1680; `--root` anywhere via `extract_root` |
| L-03 | Satisfied | `default_profile` lsf.py:245-254; `check_weights` lsf.py:274-286 (exit 2); alias map lsf.py:42-45 and SKILL.md table |
| L-04 | Satisfied | `cmd_phase` lsf.py:968-1000 (switched, not-open exit 1, unknown name exit 2) |
| L-05 | Partly | numbers verified by hand; unmeasured is null/"not measured"; but waiting is not attributed and no session total (M1); ledger failure shows 0 (H1) |
| L-06 | Satisfied | `emit_event` lsf.py:301-321, `append_line` O_APPEND, truncation and redaction (redaction coverage is M5), env switches, stderr on failure |
| L-07 | Partly | open/request/status/release and chain implemented lsf.py:354-465; exit 3 on start; broken chain exit 1; but chain is forgeable and bypassable (C1) and unrecoverable (H1) |
| L-08 | Partly | print/install/uninstall idempotent and exit 0 verified; hooks write to cwd root (H5), redaction gaps (M5), traceback possible (L4) |
| L-09 | Satisfied | Host 403, routes, token header, constant time, no logging (verified). Case-insensitive `.git` (M6) is a residual risk on macOS |
| L-10 | Partly | ten tabs, dark/light, 390 px OK, honest empties; "available never with zero items" fails in data (M8); pass/fail counts wrong (H2); Architecture editor links inside diagram do not work (M3); Docs snapshot mismatch (M4) |
| L-11 | Satisfied (not run) | collectors follow the shared shapes; parity test exists at `tests/lsf/test_hooks_collect.py:64`; I did not run it |
| L-12 | Satisfied | `cmd_cost` lsf.py:1080-1102, labelled manual |
| L-13 | Satisfied | `cmd_doctor` lsf.py:1272-1318, verified FAIL on a busy port with exit 1 |
| L-14 | Partly | flow, aliases, split, hitl rule, "never release" all in SKILL.md; it names `skills/eli12-docs` and "its check" without the bundled `scripts/eli12.py` command, which does not exist at that path on a Mac |
| L-15 | Partly | caps exist but silently drop data (H3); `git show` and `ls-tree` unbounded in memory (L5); no socket timeouts (L2); no network use confirmed |
| L-16 | Satisfied | `skills_sync.py check` passes; no changes outside new files observed in `skills/lsf` |

## What the owner said that `lsf` does not deliver

- "a live ops dashboard ... langfuse observability if llm features included": no Langfuse tab or hook anywhere.
- "eval suite status": the Evals tab shows the bug log, QA-notes headings and agent-typed pass/fail lines; it does not read any eval run result, golden-gate status or suite totals.
- "nested mermaids ... should open up specific files on our code editor": works in the node list beside the diagram, not inside the embedded diagram (M3).
- "60% on human-AI alignment": the tool plans 60% but measures it without human wait (M1), so the figure the audience sees does not support the claim either way.
- "ELI12 ... prevents illegible docs": the bundled `eli12.py` exists but SKILL.md does not tell an agent on a Mac how to invoke it (L-14).
- "git history to toggle what the snapshot ... looked like at that time": works for the tabs that read git, but the Docs bodies and explorer page come from the working tree (M4).

## What I could not check

macOS itself (BSD tools, zsh, Safari, case-insensitive APFS, the Xcode shims, `open`), 1280 px rendering, a repo with a huge history, real SIGSTOP/lid-close behaviour (I reasoned from the code and from a manually created stale lock), a running Claude Code to confirm skill-directory scanning (H4) and hook payload fields (`cwd`, `agent_type`), and any model behaviour (whether an agent would try the bypasses). I did not run the lsf test suite, and I did not look at `evals/`.
