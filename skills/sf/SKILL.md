---
name: sf
description: >-
  Use at the start of any implementation task on a project that has a build-loop profile, and
  again whenever picking work back up after a long session, a compaction, or a context reset.
  Binds the fixed development loop into one sequence — research, experiment, decide with an ADR
  for one-way doors, MECE tracer-bullet spec, tests and evals authored FIRST, implement blind to
  the test code, tests run by a separate agent, independent review for reward hacking, drift check
  against the verbatim source requirements — and creates a todo per stage so a stage cannot be
  skipped silently. Triggers: "implement X", "build the next slice", "continue dev", "are we still
  following the loop", "pick up where we left off", or any coding task on a project whose repo
  contains a build-loop profile. Also use before declaring a milestone complete.
---

# Build loop

## Why this exists

A defined development loop decays across a long session. The front half — research, experiments,
decision records — is interesting and gets done. The back half — tests authored before
implementation, implementing blind to the test code, a separate agent running the tests, an
independent adversarial review, a drift check against the source requirements — is the part that
costs time without producing visible progress, so it is the part that quietly goes missing.

The decay is not a knowledge problem. The loop can be written down in the repository and still be
skipped, because consulting a document is itself a step that has to be remembered. This skill
turns the loop into a checklist with a todo per stage, so a skipped stage is visible rather than
forgotten. The companion `SessionStart` hook re-injects the invariants after compaction, which is
where the loop is most likely to be lost.

**The loop is not a variable.** Schedule pressure may reorder work or slice it smaller; it may
never drop a stage, substitute a decision an ADR already settled, or cut a deliverable to fit a
date. If the plan and a deadline genuinely conflict, state the conflict and let the human choose
what moves.

## When the run ends

**The run ends when every line of the source-of-truth requirements is either satisfied or recorded
as blocked with what it waits on. Not when a queue empties, not when a wake-up timer fires, and not
when the current slice looks finished.** A queue is a guess at what the requirements need; it runs
out long before they are met, and treating it as the finish line is how a run stops with work left.

That is only a termination condition if satisfaction is **measurable**, so it has to be written down:

- The profile names a **requirements ledger** — one row per requirement line, each `satisfied`,
  `partial`, `blocked` or `unserved`, with the artifact that satisfies it or the thing it waits on.
  If no ledger exists, building it is the first slice, derived line by line from the source document
  rather than from any summary of it.
- **Stage 9 updates the ledger** for the lines the slice touched, and only from re-derivation. A row
  marked satisfied without an artifact named beside it is not evidence; it is a claim.
- A **`blocked` row must name what it waits on** — an asset, a decision, a measurement, another
  slice. "Blocked" with no dependency is how an unserved requirement acquires the appearance of a
  decision.
- **`unserved` rows with no producer are the highest-value work**, above anything already partly
  built. A requirement nothing produces will not fail a test or surface in a review; it is invisible
  until someone re-derives, which is why it survives longest.

Between slices, pick the next one from the ledger, not from the queue: highest-severity `unserved`
or `blocked`-now-unblocked first. **Never stop on a blocker** — record what it waits on and move to
the next independent line. Stop only for a ceiling the operator set (budget, rate, an irreversible
action needing their call), and say which one, with the ledger's remaining rows, so what is left is
legible rather than implied.

## Start away mode with the run

`/sf` is the user's indefinite away-mode trigger: a build-loop run is long and is driven from the phone
over Remote Control, so invoking it turns on away mode for this session with no end time, as the first
action and before the profile is loaded. Never pass a duration. Run
`~/.claude/skills/away-mode/scripts/status.sh`. If this session's Claude pid is not listed as `Active`,
or its line says "until HH:MM" (a timed run), run `~/.claude/skills/away-mode/scripts/start.sh` with no
argument, which replaces any timer with a keep-awake that lasts until the session exits. If the line
shows no end time, it is already indefinite: leave it alone. Re-run the status check after a compaction
or context reset, because that is when a session is most likely to have lost track of it. Report any `[warn]` or `[fail]` lines, and
on macOS remind the user once that `/remote-control` and an open lid are theirs to do. On the Vultr VPS, Remote Control is enabled by the launcher, the cloud host does not sleep, and tmux plus the session recovery service supply indefinite away mode; do not ask for a Mac lid or caffeinate. Never run `sudo`, never
touch caffeinate processes the script did not start, and do not stop away mode when the run ends; the
user turns it off with `/away-mode stop`.

## Overnight mode

On every invocation and resume, run `~/.claude/skills/good-night/scripts/overnight.sh status` from
the project checkout. If a run is open, the owner is asleep: read `good-night/SKILL.md` and follow its
overnight rules (queue decisions instead of asking, never stop on a blocker, journal each event) until
`good-morning` closes the run. Exit 1 means no run is open and the loop runs normally.

## Load the project profile first

This skill is project-independent. Everything project-specific lives in a profile at
`.claude/build-loop.md` (or the path the project's `CLAUDE.md` names) and must be read before
starting. A profile states: where the verbatim source requirements live, where ADRs go, where
specs go, where tests and evals go, the test command, which reviewer agent to dispatch, and
(optionally) a `## Hygiene` section for disk and memory limits.

If no profile exists, write one with the human before implementing. Do not guess these paths.

## The stages

Create one todo per stage. Mark a stage complete only when its artifact exists on disk.

1. **Research** — establish what is actually true now, not what was true at training time.
   Enumerate live options from primary sources; never carry a version number, model name, price
   or API shape from recall. Record findings as a brief with sources and explicit "could not
   verify" notes. Use `deep-research` or `grounded-research` for the search itself.

   **Seed the first research agents from the course corpus, before any external search.** The
   profile names a lecture/curriculum directory; read the relevant notes there first and put them
   in the research agent's brief as the starting point. Two reasons, and the second is the one that
   bites: the corpus is the floor the work is graded against, and an agent that searches the web
   first will produce a brief that is *technically better* and *misaligned with the assignment* —
   which costs a re-derivation later at exactly the point where nobody wants to redo research.

   The corpus is a **floor, not a ceiling.** Name which lecture each seeded claim came from, then
   exceed it and say where you exceeded it. A brief that only restates the lectures has not done
   stage 1, and a brief that ignores them has done stage 1 for a different assignment.

   **Sweep the brief before trusting it.** For a new source brief, PRD or rubric, stages 1–2 run as
   the `minesweeper` discovery loop: every line becomes a claim, topic lenses sweep it for traps
   (licence, provider terms, regulation, unsafe dependencies, impossible guarantees, inverted
   rubrics, omitted trust and threat models), and suspects are settled through `grounded-research`,
   `deep-research` and `experiment-designer` until the loop converges. The ledger is built from the
   register, with a `trust` column per row: `trusted`, `conditioned (F-id)` or `rejected (F-id)`.
   An open Critical finding blocks scheduling of the rows it conditions until the owner signs off; a
   High finding needs a recorded disposition. "Out of scope" never closes a finding without a written
   consequence. `prd-writer` then writes the real PRD from the problem definition and register.

2. **Experiment** — for any choice that matters, produce numbers. Multi-metric, so no candidate
   wins on a single axis. Read cost and latency from the provider's own accounting rather than
   estimating from list prices. Write results to a committed file beside the script. If an LLM
   judges the comparison, the judges must come from families with no candidate in it.

   **Build the candidate list from a dated enumeration, never from recall.** When the choice is
   among external options — models, providers, libraries, hosted tools — enumerate the live set
   from the primary source (the provider's catalogue endpoint, the registry) *before* the candidate
   list is written, and commit the output beside the experiment with its date. A list assembled
   from memory is not a starting point to broaden; it is a defect to replace, because the names you
   recall stop at the training cutoff and broadening them only widens the same blind spot. The
   committed enumeration is what lets a later reader tell a candidate that was *rejected* from one
   that was *never considered*; without it the two look identical.

   Before the experiment runs, check the candidate list against the enumeration. Every live vendor
   or family absent from the list is either added or given a one-line recorded reason for
   exclusion (fails a stated capability bar, unavailable to this account, out of the cost ceiling).
   "I did not think of it" is not a reason. Prices come from the same enumeration, read at run
   time, never from a list price, a blog post or recall; a comparison built on a figure nobody
   measured produces conclusions like "33× cheaper" for output that did not exist.

   **The tell: a docstring that cites an enumeration while the code carries a hardcoded list.** In
   `ai-red-team` experiment 006 opened by saying the previous experiment had excluded the frontier
   "by accident rather than by judgement" and claimed every candidate came from enumerating the live
   catalogue; its candidates were six literal names, and no DeepSeek model appeared in it or in
   007 or 013 although one had been live for five months and priced at 0.32× the incumbent judge.
   The fix had widened the list without changing how the list was built, and it passed review
   twice because the prose cited the tool. A reviewer should read the code path, not the comment:
   the candidate list must be produced by, or loaded from, the committed enumeration.

3. **Decide** — record the decision. For a genuine one-way door, invoke `one-way-door`; for an
   ordinary decision an ADR still beats a chat message, because the reasoning is what a later
   reviewer needs. State the honest limits of the evidence in the ADR itself.

4. **Tracer-bullet spec, MECE** — one thin end-to-end slice, decomposed so the parts are mutually
   exclusive and collectively exhaustive over the slice. A spec that overlaps itself or leaves a
   gap will produce tests that do the same.

   **Name what the feature will emit, once the PRD exists.** The MECE test and eval surface of this slice is
   also the list of what the ops dashboard must show for it: the evals and golden-gate cases, the error
   conditions and their traces, the logs, and (when the slice calls a model) the LLM traces with tokens and
   cost. Record that list in the spec. Where a model is called, the Langfuse span plan is fixed here and
   tracing exists from the first call (`ops-dashboard-design`).

5. **Author tests and evals FIRST** — before any implementation. Use `eval-designer`. A case may
   be written before the thing that satisfies it exists; it simply resolves to blocked until the
   producer lands. **Never accept a plan that writes tests after the feature.** Every case should
   exercise a boundary, an invariant, or a regression risk — a static payload list satisfies none
   of these.

6. **Implement blind to the test code** — the implementer must not read the test or eval files.
   When a subagent implements, its brief names the contract and excludes the test paths. When
   implementing directly and the tests are already written, do not reread them to make something
   pass; fix against the contract.

7. **A separate agent runs the tests** — not the implementer, and not the author of the code. This
   is the cheapest guard against a green result that was arranged rather than earned.

8. **Independent review for reward hacking** — dispatch `implementation-review`, or a fresh
   adversarial reviewer told to be skeptical and not agreeable. It must specifically hunt the
   "third state": a pass earned for the wrong reason. Pay attention where the same author wrote
   both the code under test and the logic deciding whether a gate is met — that is a conflict of
   interest and the reviewer should be pointed at it explicitly. **Report what the review finds
   even when it finds against you.** Give the reviewer the open `minesweeper` findings as a hunting
   list, and have it check that every spec section a confirmed finding names is filled.

9. **Drift check against the verbatim source** — reread the primary requirements document line by
   line, treating every line of prose as a requirement, including anything labelled optional. Do
   not check against a previously built summary table: re-derive, because the table is exactly
   where drift hides. Confirm phase assignment too — a requirement that is a component of an
   earlier milestone's artifact belongs to that earlier milestone.

   **Then update the requirements ledger** for the lines this slice touched: the status, and the
   artifact that justifies it or the dependency it waits on. This is what makes "the run ends when
   the requirements are met" checkable instead of a feeling. The ledger is the one summary table
   allowed to exist, and only because stage 9 rebuilds its touched rows from the source every time —
   a ledger updated from memory is the drift it was built to catch. If the source text changed or
   gained lines, run a `minesweeper` delta sweep on that text before its rows enter the ledger.

10. **Propagate the decision into the documents that derive from it** — invoke `doc-sync`. Stage 9
    compares the *implementation* against the requirements; it says nothing about the documents
    that describe the system in prose, and those go stale silently because nothing fails when they
    do. Build the dependency map from what just changed — an accepted ADR, a superseded figure, a
    renamed component — to what derives from it: the architecture overview, the README, status
    trackers, metric and cost figures, published dashboards and artifacts, interface contracts.
    Then update each, or annotate precisely what is superseded and by which record. **Update the ops dashboard in this pass as one of the derived documents:** add the evals, error
    traces, LLM traces, logs and gate status the slice's MECE surface produced, using `ops-dashboard-design`.
    A slice is not documented until its dashboard rows exist, measured or marked not live. **Report what
    was updated and what was deliberately left**, because a known-stale document is a different
    thing from a surprise one.

    This stage exists because the loop's own shape works against it. Stage 11 asks for one atomic
    commit per logical change, so propagating a decision into six documents *feels* like unrelated
    work and gets deferred to a tidy-up that never comes. Naming it a stage is what stops it
    competing with the next feature and losing.

11. **Integrate and commit** — one atomic commit per logical change, as each lands.

12. **Check the inbound sources for what arrived while you were working** — the task list, the PRD,
    and the backlog or ticket queue the profile names. **This is the last stage of every slice, not
    an end-of-run step**, and it exists because of when new work appears rather than because anyone
    forgets to look: a slice takes long enough that the operator adds an idea, a peer files a ticket,
    or a review lands a finding *during* it. None of those announce themselves, and the next slice is
    chosen from the ledger — so an item that never reaches the ledger is never chosen.

    **The state only reads correctly after one loop has run.** Before the first slice the backlog is
    whatever was last written down; after it, the backlog plus everything the slice produced plus
    everything that arrived meanwhile. Re-reading at the end is what makes the *next* slice's choice
    a real choice.

    What to do with what you find: **rank it into the ledger or the backlog, and do not context-switch
    into it.** A new inbound item is a candidate for the next slice, not an interruption to this one —
    and the ranking is the work, because an unranked item is indistinguishable from an unnoticed one.
    Where an item is a requirement, it becomes a ledger row and the run's termination condition grows;
    where it is an idea, it goes to the backlog with a stated rank. A new requirement or brief is
    swept by `minesweeper` (delta mode) before it gets a ledger row, so it arrives with a trust status.

    State explicitly when nothing arrived. "I checked the backlog and the ticket queue and there is
    nothing new" is a result; silence reads as not having looked, which is the distinction this whole
    skill keeps being about.

    **Then brief the owner.** When the slice changed the ledger, the in-flight set or the open
    decisions, invoke `progress-briefing`: it updates the project's one private three-tab page (status
    with household analogies, the research and experiment story with real outcomes, and the open-question
    survey). Do this at stage 12 of every slice that finished something, before a human gate or deadline,
    and whenever the owner asks for an update. Read the survey answers from the page's database at the
    start of the next slice and record each as a Human (gate) row in the ADR it touches.

## Factory toolchain by stage (the owner's flow, with what is enforced)

The owner's flow is authoritative: business requirements, then minesweeping for core business value and best
practices in advanced subcategories, then multi-agent research seeds on state-of-the-art techniques, then
experiments where the options are not already resolved, then tracer-bullet slices that start with UX stories
(triaged by priority and dependency), then a MECE eval surface, then blind implementers supervised by QA
agents, then mechanistic review that can amend the slice and restart the implementer/QA pair, then docs and
ADR sync that blocks completion on drift, with a live development and ops dashboard updated at every stage.
The stages above are that flow; this table says which command does the checking in each. The flow diagram
with current versus planned behaviour is `docs/sf-flow.md`. All commands run as `sf <group> ...`
(`python -m factory.<module>` also works). Rows marked *prose* have no mechanical check yet.

| Stage | Do this | Mechanical check | How it is enforced |
|---|---|---|---|
| 1 Research (intake) | Verbatim register (`spec-recomposition`), minesweeper sweep **plus** the core-value and best-practice pass per advanced subcategory (`skills/intake-gate`), ranked seeds (`biz-decomposer`) | `sf intake check --source S --ledger L`, `sf intake record-sweep`, `sf intake gate`, `sf intake seeds check` | CLI gate; fails when the sweep record for the current source hash is missing (proof that the sweep ran), an open Critical lacks a sign-off, or a source line has no ledger row. The sweep and research themselves are model procedure |
| 2 Experiment | Pre-registered multi-metric comparison from a dated enumeration | `sf intake experiments check` | CLI gate; a literal candidate list with no enumeration file is rejected |
| 3 Decide | ADR; one-way doors through `one-way-door` | `sf audit` (fails closed: exit 3 when the required verifier is unavailable) | CLI gate; the `bash_guard` hook asks a human before force-push, destructive SQL, deploys |
| 4 Slice | `docs/slices/<id>/`: UX stories first, public acceptance criteria with IDs, tasks with two boxes, priority and depends_on (`prd-writer`, `docs/slice-format.md`) | `sf slice check DIR [--ledger L]`, `sf slice triage` | CLI gate; `check` blocks a slice whose source rows are conditioned on an open Critical |
| 4b Structure | Map the affected area; refresh the architecture artifact | `sf structure scan|scope|model|diff`, then the dolls `check` and `build` (`skills/mermaid-nesting-dolls`) | CLI; edges are labelled resolved, syntactic or unresolved and never claimed complete |
| 4c Contracts | Independent contracts with IDs, frame conditions, assumptions; consistency review before code (`skills/contract-verify`, `axiomatic-spec`) | `sf contracts check-contracts` | CLI gate; unsatisfiable or vacuous contracts fail |
| 5 Tests first | Eval author writes and freezes cases from the contracts | `sf slice lock DIR` freezes criteria by hash | CLI; later changes to criteria need an additive amendment or an explicit human or Codex approval marker |
| 6 Implement blind | `scripts/implementer-worktree.sh NAME` (protected paths absent from the tree); implementer ticks `[x]` meaning implemented | `sf slice tick ... --role implementer` | worktree plus PreToolUse hooks `blindness_guard`, `path_guard`, `secrets_guard`, `bash_guard`; the `stop_gate` hook refuses a stop with skipped or weakened tests |
| 7 Separate runner | QA supervisor runs the suites, writes behavioural feedback in criterion terms, never test source; bounded retries, measured escalation, repeat failures become regression proposals | `sf qa init|record|next|feedback|regression-propose|verify-pass|stats` ; `scripts/bounded-pytest.sh` | CLI; the feedback leak check rejects protected material; only QA can set `verified` (`sf slice verify --role qa`) |
| 8 Review | Deterministic first: `sf slice done`, `sf contracts verify`, `sf structure diff`, dolls `check`; then evidence-backed review with `implementation-review`, the Ponytail review rubric and the minesweeper lenses; findings amend the slice (`sf slice amend --role reviewer`) and re-kick the implementer and QA | `sf slice done DIR` | CLI gate for the deterministic part; the judgement part is prose |
| 9 Drift | Re-derive from the verbatim source; update the ledger | `sf intake check`, `sf slice done` | CLI gate: refuses completion with an unverified task, a broken verification chain, a changed criterion, or an uncovered source line |
| 10 Docs and dashboard | `doc-sync`; update the dashboard at every stage | `scripts/ops-stage-event.sh STAGE SLICE VERDICT`, `sf ops bundle` at commit time | CLI; historical artifacts are snapshotted per commit, runtime telemetry is 'as of now' and never part of a snapshot |
| 11 Commit | Atomic commits, explicit paths | `sf ops bundle` | CLI |
| 12 Inbound | Rank new items into the ledger or backlog | `sf intake gate --since SHA` for new source text | CLI for new requirement text; the ranking is prose |

Added 2026-10-20 (owner flow `docs/requirements/sf-owner-flow.md`, ADR-0005, clarifications C-40 to C-50):
- **The dashboard updates itself.** Every `sf` command in the table above writes its own stage event to `ops/events.jsonl` (a local,
  append-only log that is excluded from git; `SF_EVENTS=off` switches it off), the sub-agent stop hooks add `subagent-stop` events,
  and `sf ops init | backfill | status | autobundle` create the dashboard, snapshot past commits, report how far the newest snapshot is
  behind HEAD, and bundle every new commit from a `post-commit` hook. The viewer shows a staleness banner. Details: `docs/ops-events.md`.
- **Eight roles, all Sonnet.** A `qa` role (skill `qa-supervisor`, writes only QA notes and attempt records, enforced by `path_guard`) sits between
  `implement` and `review`; the reviewer carries `implementation-review`, `mermaid-nesting-dolls`, `minesweeper`, `doc-sync` and the Ponytail rubric
  (`skills/implementation-review/ponytail-rubric.md`) and approves only after `sf slice done` and `doc-sync` are clean. A role file that names another
  model is rejected unless the operator passes `--allow-model`. `sf install doctor` checks every role's skills and the pinned external skills
  (`docs/external-skills.json`; refresh with `sf install pin-external --yes`).
- **Plain-language docs.** At stage 10, `python3 skills/eli12-docs/scripts/eli12.py check` must be clean for the changed modules (`scaffold` writes the
  skeleton with who-uses-it and what-it-uses computed from the code; the explanations are written from the code and tests).
- **Review in the editor.** The nested diagrams and every dashboard file reference open the exact file and line in the owner's editor
  (`skills/mermaid-nesting-dolls/assets/editor-links.js`; build the explorer with `--workspace-root "$PWD" --editor vscode`).
- **`/lsf`** is the fast version of this same flow for a live session on a laptop (`skills/lsf`): same stage names and file conventions, phase clock,
  human checkpoints with an Approve button, telemetry, needs only python3 and git.

Retry and escalation defaults (configurable in `.sf/policy.yaml`, tuned from `sf qa stats`): 4 attempts per
failure signature, model tier per attempt, one flake rerun, environment crashes (out of disk, out of memory,
killed, timeout) classified separately and never consuming an attempt. At the cap QA hands the slice to the
reviewer; a slice the reviewer cannot unblock is recorded as blocked with what it waits on and the run moves to
the next independent slice. Never stop on a blocker.

Resource limits (after the 2026-10-19 out-of-memory incident): run tests through `scripts/bounded-pytest.sh`,
at most one heavy run at a time and at most two implementation agents at once; never build test inputs by
doubling or repeated self-nesting. A tripped limit is a failure, never a pass.

Human stops (explicit human-in-the-loop points): at the start of every stage run `sf hitl status --root .`.
Exit 3 means an open stop applies: do nothing further except report it. Open one with `sf hitl request --name N --reason R`
before any owner-gated or irreversible action and at artifact-only stopping points. While a stop is open, `sf slice done`
refuses (exit 5) and `sf qa next` returns `human_stop`; the stop ledger lives under `.factory/stops/` (a control folder the
blind implementer cannot write) and is hash-chained. Releasing a stop is a person's act at a terminal
(`sf hitl release --name N --by human:<ref>`): an agent never releases one, the release command is a one-way door
(the orchestrator is asked, every other role is denied) and it requires an interactive terminal. This is friction, not proof:
a role with full Bash could still allocate a terminal, so the stop is a procedure the run obeys, not an unforgeable barrier.

Sonnet-only routing: sessions for this work start with `--model sonnet`; `sf install install --project DIR` pins
`"model": "sonnet"` and forces every subagent to Sonnet (`CLAUDE_CODE_SUBAGENT_MODEL=sonnet`, `CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1`)
in that project's settings, so an inherited user-level default of another model does not apply (checked in a real session:
`docs/native-verification/2026-10-19/REPORT.md`). The QA retry ladder is Sonnet-only unless the policy explicitly opts in
(`sf qa policy`). Do not escalate to another model on your own. Check an installation with `sf install doctor --project DIR`
(it executes the generated hook commands and fails if one cannot run, because a hook that cannot run fails open).

Known limits, stated so nothing reads as more than it is: the hooks are mechanical only in projects where
`sf` has generated the project settings and agent files, and their behaviour inside a live Claude Code session
has been exercised through the command line, simulated event streams and scripted headless real sessions
(`docs/native-verification/2026-10-19/REPORT.md`: denials, a failing gate and repair, a human stop), but not in an
interactive session, and not for the intake gate, the full QA loop with real agents or reviewer amendments;
the Bash and blindness guards are denylist parsers and cannot be complete, so the OS sandbox and permission
layer remain the backstop; the solver gate covers a small pure-Python subset and everything else must route
to tests; structure extraction is Python-only and never a complete call graph.

## Hygiene: disk and memory (runs beside the stages, not as a stage)

A long run dies of a full disk or memory pressure long before it runs out of requirements. The helper
`~/.claude/skills/sf/hygiene/hygiene.sh` does this deterministically (design: `hygiene/DESIGN.md`).
Use the script alone by default; spawn the hygiene agent (`hygiene/agent-brief.md`) only when `plan`
lists items flagged `needs_judgment`.

- **Before** fanning out more than 2 parallel agents, and before a stage 7 run that starts servers:
  `hygiene.sh scan --agents N`. Exit 2 or higher: sweep first or reduce N.
- **After** each stage 11 commit that merges worktree work and after each stage 8 review round:
  `hygiene.sh plan`, then `apply <plan> --execute` for the auto items.
- **At stage 12**, state the scan result in one line ("disk 43 GB free, memory normal").
- **Emergency** (ENOSPC, free below the profile's emergency threshold, memory critical):
  `plan --emergency`, then `apply --execute` immediately; record what was removed.
- **Register** every server, validator or browser the run starts: `hygiene.sh register PID label`.
  Only registered PIDs whose command line still matches are ever stopped.
- **Standing rule: worktree agents share one build directory (`CARGO_TARGET_DIR` = the main checkout's
  `target/`) and clean their own caches** (`.next`, `dist`, `.vitest`, `.turbo`) before reporting done.
- **Idle after completion: shrink the session.** When the run has finished (the ledger's termination
  condition is met, or every open row is blocked with a named dependency), stage 12 has run, and nothing
  project-critical is still running, the session sweeps itself so a parked session costs almost nothing.
  **Never mid-run.** Not idle if any of these hold: a recurring watcher or scheduled wakeup is active, a
  background agent or test run is still going, or a human gate is pending whose answer resumes work on
  these artifacts (then sweep only the auto tier from `plan`). In order:
  1. Commit and push anything worth keeping (stage 11). Nothing is deleted whose only copy is in scratch.
  2. Stop the registered processes and the background tasks, monitors and idle subagents this session
     started. Only registered PIDs whose command line still matches are ever stopped.
  3. `hygiene.sh plan`, then `apply --execute` for the auto items.
  4. Clear this session's own regenerable scratch (venvs, `node_modules`, `target/`, build caches,
     throwaway repo copies). Not the shared build directory (long rebuild; report its size instead), and
     never evidence, keys, memory, branches, or the protected list below.
  5. State one line: "idle: freed X GB, disk Y free, N processes stopped, kept: shared target Z GB".

  Leave the away-mode keep-awake alone unless the user says otherwise (`/sf` starts it, see above): it is what keeps a session
  reachable from a phone. The next slice starts with `scan` and pays only the rebuild. **Status:** steps
  1, 3 and 5 work with the current script; for step 2 and 4 `plan` only includes registered processes under
  memory pressure and only clears scratch older than `scratch_max_age_days`, so an idle session does them
  by hand until `plan --idle` exists (see `hygiene/DESIGN.md`).
- The script never deletes branches, locked or dirty worktrees, keys, `.env*`, evidence or memory
  directories, or anything with unique commits. Deleting a branch still needs the user's say-so.
- `apply` without `--execute` is a dry-run. Never pass `-f -f` to `git worktree remove`.

## Checks that catch the common failures

- Did anything get labelled "a fixable limit" without being measured? Measure it.
- Does any comment claim a guarantee the code does not implement? Those diverge silently.
- Is a zero a measurement or a failed lookup? Return absent, never zero, for a failed read.
- Can a gate be satisfied by the cheapest possible cases? Then it measures nothing. Require a
  minimum per category and surface what was excluded next to the verdict.
- **Is the next slice chosen from the ledger, or from a queue?** A queue is a guess at what the
  requirements need and runs out first. Re-derive from the ledger between slices.
- **Did a research brief skip the course corpus?** A brief that searched the web first is often
  better and aimed at a different assignment.
- **Where did the candidate list come from?** If a model, provider or library comparison holds a
  literal list, find the committed enumeration it was checked against. None means the list is
  recall, whatever the docstring says.
- Is any engineering requirement being deferred as polish? Contracts, typed error schemas, test
  design rules, decision records and documented external-API limits are day-one habits; adding
  them later means reworking everything built without them.
- **Did stage 12 run, and did it say what it found?** A slice that ends at the commit leaves whatever
  arrived during it unranked, and the next slice is chosen from a ledger that does not know about it.
  "Nothing new" is the expected answer most of the time and still has to be said.
- **Did a decision change a number, a name or a status that some document still asserts?** The
  document does not know, and nothing will fail. Count the README, the metrics document, the cost
  analysis, spec status lines and the requirements tracker as downstream of every decision until
  checked otherwise — including a document corrected earlier in the same session, which is the
  one most likely to be assumed current.
- **Was disk and memory checked before this fan-out, and after the last merge?** The failure mode is
  not slowness but ENOSPC mid-write, which also corrupts the memory and ledger writes that keep the
  run resumable. Worktree agents must share one build directory; every started process is registered.
