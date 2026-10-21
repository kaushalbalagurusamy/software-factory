# Independent adversarial review: SFN-01, SFN-02, SFN-03, SFN-07, SFN-08 (2026-10-20)

Reviewed at `agent-graph` (54ed4aa). Read-only on product code. Reproductions ran in temp repos under `~/.cache/sfn-rev/` (deleted afterwards). I did not run any test suite, and I did not read `evals/` or qrypt, except the one amended eval line cited under H1.

Verdict: do not call the self-updating dashboard delivered. The default path (post-commit hook, then snapshot) shows an empty Dev journey, and the gate that would have caught it was edited to pass. Two more High findings are silent data loss in the snapshot index and a hook installer that can corrupt or infect hooks. The QA write confinement has a glob hole.

## Findings, ranked

### H1 (High): stage events never reach a commit snapshot, so the Dev journey tab is empty on the default path (E-12, E-13, owner "open dev brain")
- C-50 made `ops/events.jsonl` local and untracked (`.gitignore:23`, `.git/info/exclude`). But `dev_journey` reads it from the commit's object database: `factory/ops/collect.py:412` calls `src.text("ops/events.jsonl")`, and `GitSource.read` (`collect.py:58-61`) returns None for a path not in `git ls-tree`. Only `bundle --worktree` reads the working tree.
- Reproduction (`~/.cache/sfn-rev/r7`): `sf ops init`, `autobundle install`, commit twice. `events.jsonl` has an `11-commit` line, `ops status` reports `events: 1`, yet both manifests say `dev_journey: {available: false, reason: "no stage events recorded (no docs/slices/ and no ops/events.jsonl at this commit)"}` and every `latest_stage_event` is null.
- Expected: events recorded by the loop appear in the snapshot (filtered to the commit date). Observed: none, ever, unless the log is force-added.
- Conflict of interest: commit 541078b ("Amend an SFN-01 eval for C-50") changed `evals/native/sfn01/test_staleness.py` from `git add` to `git add -f ops/events.jsonl` in three cases. So the hidden eval now passes only because the fixture tracks the file the product no longer tracks. The same loop wrote C-50, the code and the eval edit. Third state: the gate passes for the wrong reason.
- Fix: have `dev_journey` and `hitl` read events from the working tree file (and still apply the commit-date cut), or track the log. Then restore the eval to an untracked-log fixture, and add a test that runs the hook path and asserts the event appears in the manifest.

### H2 (High): concurrent bundles lose index entries, and the loss is permanent
- `bundle.update_index` (`factory/ops/bundle.py:148-160`) is an unlocked read, merge, write of `ops/index.json`. The post-commit hook backgrounds one bundle per commit, so quick commits race. `head` can also move backwards (the older bundle finishes last).
- Reproduction (`r3.py`, 8 commits bundled in parallel with distinct `--sha`): 8 snapshots on disk, 5, 4 and 3 entries in `index.json` over three runs.
- It never heals: `_backfill` (`factory/ops/cli.py:105-125`) skips any commit whose manifest exists, and never re-adds it to the index. `_status` (`cli.py:128-153`) reads the index, so it reports against a wrong "newest snapshot".
- Fix: take `fcntl.flock` on `ops/.lock` around read-modify-write; make backfill re-index skipped commits; only advance `head` if the new commit is not an ancestor of the current `head`. The tmp name `path.name + .tmp<pid>` is fine across processes but not across threads.

### H3 (High): `autobundle install` can corrupt a hook, silently never run, or run in repos that never opted in
All in `factory/ops/cli.py:156-213`.
1. A non-shell hook gets a shell block appended. Reproduction: a `#!/usr/bin/env python3` post-commit, then `autobundle install`, then `git commit`. The commit succeeds, but the user's own hook now dies with `SyntaxError` on every commit, and install printed `installed:`. Install must refuse unless the shebang is sh/bash/dash/zsh (or the file is absent).
2. A hook that exits earlier (`exit 0`, `exec`) leaves the block unreachable while `status` prints `installed:` (the docs admit this, but `status` still lies). Reproduction in `r2.py`. `status` should report `installed but unreachable` or install should insert the block first.
3. `--git-path hooks` honours `core.hooksPath`. Reproduction (`r10.py`): repos A and B share a hooksPath; `autobundle install --repo A`; commit in B (never opted in); B now has `ops/`. A shared or tracked hooks directory (husky `.husky/`) is modified for all users. Refuse when `core.hooksPath` is set, or require `--force`.
4. The block hard-codes `PYTHONPATH='<install-time checkout>'` and `sys.executable`. Installing from an ephemeral worktree such as the agent worktrees leaves a hook that does nothing once that path is deleted, and no output (all redirected to /dev/null). Paths with a `'` break the quoting.
5. `command -v sf` wins over the pinned interpreter, so any `sf` earlier on PATH runs (reproduced: a fake `sf` ran from the hook). It never makes the commit fail (the background `( ... ) &` returns 0), loops (bundle never commits) or runs repo-controlled code. The risk is "wrong tool silently", not injection.
6. A `BEGIN` marker without `END` makes `status` say not installed, and `install` appends a second block after the half block.

### H4 (High): `qa_paths` confinement is bypassed by any directory named `qa-feedback`
- `**/qa-feedback/**` compiles to `(?:.*/)?qa-feedback(?:/.*)?\Z` (`path_guard.py:94-117`), and `_matches`/the qa branch (`path_guard.py:209`) accept it at any depth.
- Reproduction (`r4.py`): role `qa` Write to `src/qa-feedback/conftest.py`, `tests/qa-feedback/conftest.py`, `scripts/qa-feedback/run.sh` all return allow. A `conftest.py` under `tests/qa-feedback/` is collected and executed by pytest in the protected suites, so a role that "never writes test source" can plant code the blind implementer's and runner's test runs execute. Only paths already under `paths.eval`/`held_out`/`frozen_tests` and `.factory`/`.claude` are denied first.
- Fix: anchor the glob to what the product actually writes: `.sf/slices/*/qa-feedback/**`, `docs/slices/*/qa-notes.md`. Also: the real attempt log lives in `.sf/slices/<id>/` (`factory/qa/store.py:44`), so `.sf/qa/**` is a dead glob and the attempt log is NOT writable by the Write tool (`.sf/slices/s1/attempts.jsonl` -> deny). The doc claim "QA attempt records under `.sf/qa/`" (`docs/hooks/roles.md:14`) is false.

### M1 (Medium): QA Bash is `full`, so "writes only QA paths" is not true for the role
- `path_guard.py:407-419`: for `qa_paths` only `bash_guard` findings are denied. Reproduction (`r4.py`): `echo x > src/app.py`, `sed -i s/a/b/ src/app.py`, `echo x > evals/golden.txt`, `cp /etc/hostname src/a`, `python -c "open('src/a','w')..."` all allow. C-41.3 accepts `full` so QA can run suites, but `docs/hooks/roles.md:14` and the generated "You may write" text present confinement. At least deny shell redirections and `sed -i`/`cp`/`mv`/`tee` whose target is not a qa path, or state in the docs that QA Bash is unconfined and treat it as a trust assumption.

### M2 (Medium): `events.jsonl` symlinked to an in-repo file appends to it (E-02, C-49.10)
- `factory/ops/events.py:50-62` only refuses links that resolve outside root; `os.open` follows links (no `O_NOFOLLOW`). Reproduction (`r1.py`): `ops/events.jsonl -> ../evals/golden.txt` gives `emit(...) == True` and a JSON line is appended to the eval file; the same for `ops/events.jsonl -> ../.git/hooks/post-commit`. A committed symlink in a cloned repo can therefore tamper protected files whenever any sf command runs. The note is JSON-escaped, so it is not code execution.
- Fix: refuse any symlink for `ops` and `events.jsonl` (the C-49.10 allowance buys nothing), and open with `O_NOFOLLOW`. Check the target is a regular file after `fstat`.

### M3 (Medium): `behind` is 0, and "Up to date" is shown, when HEAD is older than or diverged from the snapshot
- `cli.py:128-153` (`git rev-list --count snap..HEAD`) and `runtime.py:189-199`. Reproduction (`r10.py`): bundle at the tip, `git checkout <first commit>`, `ops status` prints `behind: 0` and exits 0 although `snapshot != head`. Same for a force-moved branch. Compute `behind` only when `snap` is an ancestor of HEAD; otherwise report a distinct `diverged` state and exit 4.
- Also `ops status` picks "newest snapshot" from the index by date while `runtime.json` uses `index.head`; the two can disagree.

### M4 (Medium): `eli12.py check` passes docs whose content contradicts the code (Q-03)
- `check_entry` (`eli12.py:671-716`) validates shape only. Reproduction (`r5b.py`): `def add(a, b, c=3) -> int` documented with `**Expects:** - nothing`, `**Gives back:** str: the weather`, "What it does: Sends an email" and purpose "Deletes the user's files" gives exit 0. The sig hash (`eli12.py:130`) detects a changed signature only against the hash in the doc, which an author writes. A body rewrite is also invisible. Third state: "clean" means well-formed, not true.
- Fix: compare documented parameter names/types with `params_of(s)` and the return annotation with the code, flag `bad-param`/`stale-signature` on mismatch; say plainly in the skill that meaning is unchecked.
- `doc-sync` (`skills/doc-sync/SKILL.md:96`) runs it only "if the project has `docs/eli12/`". A project that never ran `scaffold` is never checked; Q-08 says approval needs it clean for changed modules.

### M5 (Medium): `qa promote-notes` is never invoked, so "QA agents make notes when failures repeat" is not delivered
- `grep promote-notes` hits only `factory/qa/*`, tests and `docs/ops-tabs.md`. Not `skills/qa-supervisor`, `skills/sf`, `factory/agents/roles/qa.yaml`, `sf-flow.md`. There is no repeat threshold either; the command promotes every signature. Wire it into the qa-supervisor skill/role text at the point `qa next` reports a repeated signature.
- Smaller points: it writes `qa-notes.md` into any directory inside root (`notes.py:124-139`; `--slice evals/x` would write inside `evals/`; the QA Write guard would deny that, the CLI does not). Observed/expected text is committed; the leak check is skipped only with an explicit `--allow-no-protect`, and with no protected paths it exits 2 (good, fails closed).

### M6 (Medium): doctor checks are weaker than the claims
- `_skill_resolves` (`doctor.py:104-125`) accepts an empty `SKILL.md` (reproduced with a 0-byte file); counts a plugin `commands/<x>.md` or `workflows/<x>.js` as a skill; ignores whether the plugin is enabled (`enabledPlugins` exists in `~/.claude/settings.json`, nothing reads it); accepts names with `..` (`../skills/sf` resolved). `claude-api` passes with no check.
- `check_roles` (`doctor.py:142-163`) validates the factory checkout's role files, not the project's generated `.claude/agents/*.md`; `check_agents` (`doctor.py:269-290`) compares only `model`. A project agent file missing its skills passes unless the manifest hash catches it. The docstring says "one bad role does not hide the others", but a non-hashable `model` (`model: [sonnet]`) makes `model in allowed` raise and `_safe` collapses the whole role section to one FAIL line (still a FAIL, so it fails closed, but the comment is wrong).
- Model policy itself is sound: `Sonnet`, `opus` and a missing model all FAIL (reproduced), unless `--allow-model` is passed, and the extra model is printed.
- External pins (`doctor.py:166-186`, `core.py:368-388`): a changed external skill is only WARN, exit 0 (C-40.4). Only `SKILL.md` is hashed, so scripts/assets changes are invisible. `pin-external --yes` hashes whatever is installed (trust on first use) and returns 0 even when some skills were "not pinned". Nothing stops an agent with Bash from running it after a poisoned skill and turning WARN into PASS; it is not a one-way-door pattern in the default profile.

### M7 (Medium): E-04 events go to the cwd's repo, not the project the command targets
- `factory/cli.py:390-399` uses `git rev-parse --show-toplevel` of the current directory. `sf ops bundle --repo X`, `sf qa --root R ...`, `sf slice check /other/proj/docs/slices/s` run from another directory write the event into the wrong repository's `ops/events.jsonl`. Read from code, not reproduced.

### L1 (Low): editor links
- `editorUrl` throws `URIError` instead of returning null for a lone surrogate in `root` or `relPath` (`node k.js`: `"a\uD800.py"`), contrary to K-01 "string or null". In the ops shell `fileRef` (`ops/shell/index.html:199`) that aborts the table render. Wrap in try/catch returning null.
- Newlines and other control characters in `relPath`/`root` are accepted and percent-encoded (`x\n/a.py` gives `x%0A`). Harmless but K-03 does not say to allow them.
- `window.SFEditorLinks` is attached to `window` only when a window exists; fine. Three embedded copies plus `skills/lsf/assets/editor-links.js` are byte-identical (checked).

### L2 (Low): secret redaction gaps in `events.emit`
- Reproduction (`r8.py`): `sk-ant-...`, `ghp_`, `AKIA...`, `KEY=sk-or-...`, PEM, and values split by newline or tab are redacted (ordering is right: redact, then truncate to 2000 so a secret at the limit is not cut). A `Bearer <JWT>` header, `https://user:pass@host` and a base64 token pass through unredacted. The standard is "the redaction used by `factory.hooks`" so this is inherited; note it. The CLI only writes `exit=N` as the note; the shell script and `subagent-stop` role are the free-text paths.

### L3 (Low): claims in docs/comments the code does not implement
- `docs/ops-events.md:36` and C-50: "`git status --porcelain` stays clean after a commit". After `ops init` the whole `ops/` directory is untracked in a fresh repo (`?? ops/` after init and after the hook ran); only the log is excluded.
- `docs/hooks/roles.md:14` "attempt records under `.sf/qa/`" (see H4).
- `events.py` docstring says `emit` "never decides anything"; true. `_target` says it refuses a symlink "outside the repository"; it permits all inside (M2).
- C-51.10 / T-08: the `evals` tab is available with zero items when `GOLDEN.json` parses. This departs from PRD T-08 ("available requires at least one item") and is justified only by a clarification written in the same loop; the tab's `note` says "no results committed", so the label is honest. I flag it as a PRD deviation owned by the maintainer.

## Criterion status

Legend: Y satisfied, P partly, N not.

SFN-01
| id | status | evidence |
|---|---|---|
| E-01 | Y | `events.py:65-97` (one `os.write` on `O_APPEND`, keys, `ops/` created, flock) |
| E-02 | P | truncation/control chars/surrogates/PEM ok (`events.py:25-37`); out-of-root symlink refused (`:50-62`), in-root symlink appends to protected files (M2); redaction gaps (L2) |
| E-03 | Y | `events.py:90-96` stderr one line, `SF_EVENTS=off` silent |
| E-04 | P | `cli.py:344-415` stage map matches; event root is the cwd repo (M7); exit 2 and read-only quiet per C-49 |
| E-05 | Y | `cli.py:402-410` (exit 2 skip, hitl status/help none, `ops runtime` none) |
| E-06 | Y | `ledger_audit.py:51-53`, `subagent_stop.py:341-344`; emit never raises |
| E-07 | P | `ops/cli.py:62-102`; idempotent, exit 2 outside repo; the Dev journey line it prints is "not available" even after events exist (H1) |
| E-08 | P | `ops/cli.py:105-125` counts and failure listing ok; skip-by-manifest never re-indexes (H2) |
| E-09 | P | `ops/cli.py:128-153`; wrong when HEAD is behind or diverged (M3) |
| E-10 | P | marked block, background, 120 s, idempotent, uninstall, worktree hooks dir ok (`:156-213`); H3 items 1-6 |
| E-11 | P | `index.json head` (`bundle.py:155-157`), `runtime.py:189-199`, banner `ops/shell/index.html:265-268`; same M3 flaw; banner is as stale as `runtime.json` on a static host |
| E-12 | N | default path shows no events (H1) |
| E-13 | P | filter implemented (`bundle.py:92-102`) but its input is empty for commit snapshots (H1) |
| E-14 | not verified | I did not run suites |

SFN-02
| id | status | evidence |
|---|---|---|
| A-01 | Y | all eight `roles/*.yaml` `model: sonnet`; `roles.py:121-123`, `load_roles(allow_models)` |
| A-02 | P | `roles/qa.yaml` matches the spec; the confinement it promises is bypassable (H4, M1) |
| A-03 | Y | `default_graph.yaml` (implement, qa, test, review; loops; `small` gains qa) |
| A-04 | Y | `review.yaml:6`, `implementation-review/ponytail-rubric.md`, `SKILL.md:39-43`, `review.yaml:2` |
| A-05 | Y | `design.yaml` skills `prd-writer` |
| A-06 | P | `doctor.py:104-163` (M6) |
| A-07 | P | `doctor.py:166-186`, `core.py:368-388`; `--yes` required (exit 2) ok; WARN-only, SKILL.md-only, trust on first use (M6) |
| A-08 | not verified | I did not run install twice |
| A-09 | not verified | no suites run |

SFN-03
| id | status | evidence |
|---|---|---|
| T-01 | Y | `collect.py:229-285` (journeys, flags, 80-line warning, existence by path under `docs/slices/<id>/`) |
| T-02 | Y | `collect.py:288-312` |
| T-03 | P | collector and `resolved.json` handled (`collect.py` experiments); I did not exercise `sf intake experiments check` |
| T-04 | Y | `collect.py:340-382` (invalid status mapped, qa-notes merged) |
| T-05 | P | `notes.py` byte-stable, leak check first, symlink refusal ok; never invoked by anything (M5); writes into any in-root dir |
| T-06 | P | `_clean_host` strips credentials, https only (`ops/cli.py:48-59`); runtime Langfuse block not exercised |
| T-07 | Y | `runtime.py:152-165` fails to "open" entry, never zero; banner texts in the shell |
| T-08 | P | deviation for `evals` per C-51.10 (L3) |
| T-09 | Y | collectors read `GitSource`; stops excluded from `ops/` |
| T-10 | not verified | no suites run |

SFN-07
| id | status | evidence |
|---|---|---|
| Q-01 | P | format and sig line implemented (`eli12.py:130,442-476`); content truth unchecked (M4) |
| Q-02 | Y | scaffold keeps human lines, `TODO` placeholders (`r5.py`) |
| Q-03 | P | all listed finding codes exist; parameter/return/summary truth not checked (M4) |
| Q-04 | Y | `write_index`, deterministic |
| Q-05 | Y | `index.json` written (`eli12.py:568-572`) |
| Q-06 | Y | no model calls; stdlib `ast` only |
| Q-07 | P | `write_text` (`:506-527`) refuses symlinked components, uses `O_EXCL|O_NOFOLLOW`; `discover` skips symlinked dirs; 2,000 modules in 30 s not measured |
| Q-08 | P | `doc-sync` step is conditional on `docs/eli12/` existing (M4) |

SFN-08
| id | status | evidence |
|---|---|---|
| K-01 | P | UMD ES5 function; throws on lone surrogate (L1) |
| K-02 | Y | outputs match C-43 (`k.js`: `vscode://file/home/me/x/a.py:3`, `subl://open?url=file:///...&line=5`, `idea://...%2F...`) |
| K-03 | P | rejects abs/`..`/NUL/backslash/scheme/UNC/empty segment; accepts control characters (L1) |
| K-04 | P | query override with validation, hint text and Copy path present in `template.html:340-368`; not exercised in a browser |
| K-05 | not examined | `nesting_dolls.py` not reviewed |
| K-06 | Y | `ops/shell/index.html:190-205` (editor whitelisted inside `editorUrl`) |
| K-07 | Y | begin/end blocks byte-identical in template, ops shell and `docs/explorer/software-factory.html`, plus the lsf copy |
| K-08 | not verified | |

## Owner's words not delivered by these slices
- "live ops dashboard ... updated throughout this sf loop ... dev journey ... stays live with the repo": the events are written, but the snapshots never show them (H1); the index can silently drop commits (H2).
- "QA agents ... can also make notes when failures repeat": the command exists but nobody is told to run it (M5).
- "qa agents that supervise and reinitiate when tests fail": role and graph loop exist; the role's isolation is leaky (H4, M1). Reinitiation itself is outside these slices.
- "mechanistic code review agents that use the oh my mermaid dolls and ponytail": ponytail is a rubric file, not the plugin (accepted by the PRD); the dolls are named in `review.yaml` but nothing checks the reviewer opened it.
- "prevents drift ... prior to approving a completion fully": `eli12 check` can approve a doc that is wrong (M4); doctor does not verify that a project's installed agents carry the skills (M6).

## What I could not check
- Whole test and eval suites, `sf install` idempotence (A-08), a real `git commit` with a worktree-hosted hook (linked worktree behaviour read from `--git-path`, not run), the viewer in a browser, `nesting_dolls.py check --assets`, 2,000-module eli12 performance, hook behaviour on Windows, whether plugin-namespaced skills are valid in an agent's `skills:` frontmatter, and anything under `evals/` or qrypt.
