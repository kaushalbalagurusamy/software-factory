# LSF interview manual — explained like you're 12

**Your setup in one sentence:** Claude is the builder, Antigravity is your magnifying
glass, the dashboard is the shared notebook, and you decide when the builder may continue.
Codex can help operate the setup and pass your review findings to Claude.

Choose **local Claude** if the Mac has enough memory. Choose **VPS Claude** if you
want the building and tests off the Mac. The workflow and human decisions are the same.
The VPS route has been rehearsed with a real python-dotenv feature; local Claude's
launcher was smoke-tested, but an equivalent full local feature build was not run.

## If you only read one minute

1. Open the actual interview repo; run the fresh three-stop setup below.
2. **Local:** `claude -lsf`, then in another repo terminal `lsf serve --open`.
3. **VPS:** `lsf-vps prepare peak6 "$PWD"`, `lsf-vps start peak6`,
   `lsf-vps attach peak6`; open its dashboard in another local terminal.
4. Paste the starter prompt and task. At each stop, investigate in Antigravity;
   in VPS mode refresh the snapshot first. Send findings back to Claude.
5. Approve only when satisfied. Require real test evidence and inspect the final
   diff. VPS users must fetch **and integrate** commits before submitting locally.

## 1. When the interviewer gives you the repo

Clone/open the supplied repo. Open a terminal **inside its folder**. Save any IDE
buffers before transferring files. Do not use the old python-dotenv rehearsal folder.

Explain the approach: “I'll first inspect the repo and clarify the goal, agree a
small slice and its checks, then implement and independently verify it. I'll stop
for review before building and before calling it done.”

Run:

```sh
pwd
lsf doctor
```

`pwd` tells you which folder you're in. `doctor` checks the LSF setup; resolve any
FAIL before starting. A repo's own dependencies still need its normal setup.

### Set the three interview stops — once, for a fresh run

There is **no named interview-mode toggle** yet. The built-in choices are
`align`, `all`, and `none`. This block customizes the profile to our three stops.
It also recommends 18 minutes planning, 30 building/QA, and 12 reviewing/docs for
an hour. Those are targets, not automatic cutoffs. The normal default is 36/12/12.

If this repo already has `.lsf/profile.json`, **do not use this fresh-run block**:
ask Codex to inspect and retain its existing decisions and configure a safe resume.

```sh
lsf init --minutes 60 --checkpoints none --editor antigravity-ide \
  --weight align=0.3 --weight build=0.5 --weight review=0.2
python3 - <<'PY'
from pathlib import Path
import json
p = Path('.lsf/profile.json')
d = json.loads(p.read_text())
# Run this before starting any phases or opening any checkpoints.
for name in ('phases.jsonl', 'stops.jsonl', 'events.jsonl'):
    q = p.parent / name
    if q.exists() and q.stat().st_size:
        raise SystemExit('Existing activity: stop and ask Codex to inspect it.')
p.with_suffix('.json.before-interview').write_bytes(p.read_bytes())
stops = {'1-sweep', '6-decide', '10-docs'}
d['checkpoints'] = {phase['id']: phase['id'] in stops for phase in d['phases']}
tmp = p.with_suffix('.json.tmp')
tmp.write_text(json.dumps(d, indent=2) + '\n')
tmp.replace(p)
print('Stops: after exploration; before implementation; final acceptance.')
PY
```

This sets the stops in the repo you're about to run. For VPS mode, `prepare`
will carry this profile across. Claude's later `lsf init` preserves an existing
profile. You can still ask for an extra checkpoint whenever something needs a decision.

## 2A. Local Claude + local Antigravity

In that repo terminal:

```sh
claude -lsf
```

This starts Sonnet, Remote Control and bypass permissions. On the Mac it also
keeps the machine awake while Claude runs. With no task it waits for your brief.
Keep the Mac plugged in and open, as intended for this setup.

Open **another terminal in the same repo** and run:

```sh
lsf serve --port 8765 --open
```

Leave that terminal running. The browser opens the dashboard with its approval
access. You, not the builder, own that access. A plain copied dashboard URL may
show the page without approval access; reopen using `--open` if needed.

Open the repo in Antigravity. The dashboard header should say:

- **Editor:** `antigravity-ide`
- **Workspace root:** this repo's absolute Mac path, the one printed by `pwd`

Now paste the starter prompt in section 3 into Claude.

## 2B. VPS Claude + local Antigravity

Run these **from the original local repo**, after the fresh profile setup:

```sh
lsf-vps prepare peak6 "$PWD"
lsf-vps start peak6
lsf-vps attach peak6
```

`prepare` makes a separate copy on the VPS and pins the tested tools. `start`
launches Sonnet there without inventing a task. `attach` shows its terminal.
Accept the workspace trust prompt if it appears, then paste section 3's prompt.
Use a different name instead of `peak6` if that remote project already exists.

The transfer carries on-disk source, history and LSF state. Dependency folders
and root `.env` files are excluded. Tell Claude to follow the repo's installation
instructions and identify missing configuration; don't assume local dependencies
or secrets exist remotely. It does not transfer the local Claude conversation.

In another **local** terminal, open the dashboard:

```sh
lsf-vps dashboard peak6 --port 8894 --open
```

This connects your browser to the VPS dashboard through a private SSH tunnel.
Port 8894 avoids our existing rehearsal dashboards. It is still a local URL;
you don't need a public website or a firewall change.

At **every HITL pause**, refresh and open the review copy:

```sh
lsf-vps snapshot peak6
lsf-vps review peak6
```

Antigravity opens a separate window at:

```text
/Users/kaushal/Projects/lsf-vps/peak6/current
```

The dashboard's file links should use that same Mac path. Check
`.lsf-vps-review.json` for the remote commit and capture time. An old open editor
tab can still show an older snapshot: refresh, then reopen the current file.

**The review copy is a photograph, not a remote-editing connection.** If you edit
it locally, the VPS won't receive that change. Send findings to Codex/Claude.
Earlier snapshots are kept, so your old notes aren't overwritten.

Detach from the remote terminal with **Ctrl-b, then d**. The remote session keeps
running. Reconnect with `lsf-vps attach peak6`. Don't close the builder with Ctrl-C
when you only mean to detach.

## 3. Starter prompt for Claude

Paste this after choosing local or VPS mode, then append the interview task:

```text
Use /lsf for this repo and the following brief. Keep the existing 60-minute
profile and its checkpoint map; do not reset it. Use Sonnet for subagents too.
Use brownfield-explorer together with minesweeper. Focus on the smallest useful
slice for a one-hour supervised interview. Research or experiment only when it
will resolve a real implementation choice.

The three required stops are after 1-sweep, after 6-decide, and after 10-docs.
Attach the relevant artifacts and a clear question to each stop. Wait for my
answer in the dashboard. Never approve, release, or work around your own stop.
Record my decisions and show evidence that they were applied. Request changes
means revise and seek approval again, not permission to build the rejected plan.

Use independent QA/review and feed failures back into the PRD and implementer.
Keep the dashboard, architecture map, ADRs and documentation current. If system
capacity matters, declare the actual topology and sourced assumptions in
docs/load-model.json. The Load simulator must remain arithmetic only.

Use lsf-vps-test for tests when available. Serialize heavy tests. Report actual
commands, exit statuses and failures; timeout or missing dependencies is not a pass.
Ask me to start the dashboard if it isn't available. Do not access its approval token.

Interview brief:
[PASTE THE TASK HERE]
```

## 4. The complete loop, and what you do

| Step | Builder's job | Your job / place to look |
|---|---|---|
| 0 — Intake | Save the brief; identify the user outcome and constraints; draft a one-page summary. | Check the PRD tab if the goal looks wrong. |
| 1 — Explore + minesweep | Find relevant code, callers and tests; spot traps and clarify business value. | **STOP 1:** inspect Architecture, PRD and linked sweep/exploration reports. Is this the right problem and scope? |
| 2 — Research | Resolve technical questions with evidence. | Research tab: inspect sources and uncertainties. |
| 3 — Experiments | Run a useful spike, or explain why evidence already settles the choice. | Experiments tab: distinguish measured results from assumptions. |
| 4 — Tracer PRD | Write prioritized UX stories, file scope, dependencies and acceptance criteria. | PRD tab: can you explain what will change for the user? |
| 5 — Evals | Define success, invariants, boundaries and regression checks before implementation. | Evals & bugs plus linked criteria: do the checks cover the promise? |
| 6 — Decide | Record the implementation decision and tradeoffs in an ADR. | **STOP 2:** approve the PRD, checks and decision before code changes. |
| 7 — Implement | Build the agreed slice and update task progress. | Now / Telemetry / Git: watch progress and scope. |
| 8 — QA | Independently test; send failures and feedback to the implementer. | Evals & bugs: failures go back to step 7. |
| 9 — Review | Trace source/callers with dolls and review lenses; amend requirements for confirmed defects. | Architecture / Git: investigate with Antigravity. Findings return to 7 and 8. |
| 10 — Docs | Update explanations and ADRs; compare the final work to the brief. | **STOP 3:** inspect final diff, test evidence, UX/demo and known gaps before accepting completion. |

A return to a checkpointed phase can create another human stop. Extra uncertainty
can also trigger a requested stop. Three required stops does not mean “only three
questions are allowed.”

### What to do at a stop

1. Read the question in **Human stops** and open the attached artifacts.
2. In VPS mode, refresh the snapshot before investigating code.
3. Use Antigravity to inspect the disputed code, relevant callers and tests.
4. Send concrete findings to Claude/Codex. If changes are needed, **do not click
   Approve**. Ask for a revised proposal and a new/updated question.
5. When satisfied, select the offered answer and **Submit answer**, or **Approve**
   for a simple approval card. Keep the builder waiting until you've decided.
6. Tell Claude to continue if it remains waiting after your dashboard answer.
7. Check that the card reaches **Recorded**, then **Applied**, with real evidence.

The states mean: **Asked** = waiting for you; **Answered** = you decided;
**Recorded** = the builder wrote it down; **Applied** = it acted on the decision.
A recommendation from Antigravity is not an approval. A green test is not approval.
The final phase ending is not your acceptance until you answer the final stop.

## 5. Use Antigravity as your magnifying glass

Start a **new agent conversation** so the installed global LSF review rule loads.
Paste:

```text
Act as the LSF investigator for this checkpoint. State your review-only role,
repo/commit and snapshot capture time if applicable. Read the PRD, relevant code,
callers and tests; use nesting dolls and ELI12 docs to navigate.
Do not implement, edit files, run mutating commands, or approve checkpoints.
Return: scope/provenance; confirmed findings with severity, file:line, failing
scenario, evidence and affected criterion; proposed builder handoff and regression
check; advisory approve/request-changes/needs-evidence; and what you did not check.
```

If it starts proposing to implement, remind it: **“Return investigation findings
only. Claude owns development.”** You can explicitly delegate a small edit later,
but inspection doesn't grant that permission. The rule is prompt guidance, not
an operating-system write lock; live rule ingestion has not been visually verified.

Click file chips in the dashboard to open source in Antigravity. Nesting dolls
help you find the component, then a smaller component, then its files. ELI12 docs
explain symbols and relationships; they aren't guaranteed explanations of every
line, and the source is still the authority.

A useful handoff looks like:

```text
Request changes on slice X: HIGH, src/example.py:42.
For empty input the function throws, but criterion AC3 requires an empty result.
Evidence: [source/log/test]. Please fix within the agreed slice, add a regression
check for empty input, rerun independent QA, and return to review.
```

## 6. Dashboard cheat sheet

| Tab | Think of it as… |
|---|---|
| Now | Current phase and what's waiting. |
| Human stops | Your decision inbox and decision history. |
| Telemetry | What agents did and how the phase clock is being used. |
| Research | Evidence and sources behind choices. |
| Experiments | Spikes and their verdicts, or why no spike was needed. |
| ADRs | The “why we chose this” notebook. |
| PRD | User journeys, prioritized slice and acceptance criteria. |
| Architecture | Clickable nesting-dolls maps and source-file links. |
| Load simulator | What-if capacity calculations on the declared system graph. |
| Docs | ELI12 explanations and module navigation. |
| Evals & bugs | Test verdicts, QA notes, bugs and captured error logs. |
| Git | Commit history and available historical views. |

Some tabs link to reports rather than displaying the entire report inline.
Git historical views show artifacts available at that commit; they aren't a
reconstruction of an uncommitted past state. An empty tab means inspect the
reason—it doesn't prove the work was performed or that it was unnecessary.

### Load simulator: a weather forecast, not a fire drill

Move the user slider, request rate and burst multiplier. The graph shows demand
on each service/path versus the capacity assumptions. Red means at/over modeled
capacity or a simulated outage; amber means near capacity or upstream risk.
Outage checkboxes let you explore “what if this service is unavailable?”

Nothing sends load to the real services. No provider calls or infrastructure
are created by the simulator. Capacities aren't measurements unless a source
says so. Missing `docs/load-model.json` shows a clearly labelled example, not
a discovery of this repo. Its math does not predict exact latency, queue growth
or real failures. See [normal](../rehearsals/screenshots/lsf-load-simulator.png)
and [overload](../rehearsals/screenshots/lsf-load-simulator-overload.png) screenshots.

## 7. If something gets stuck

| Symptom | What to do |
|---|---|
| “Human stop open” / exit 3 | Expected: inspect Human stops and answer the actual pending question. Don't bypass it. |
| Approved, but Claude still waits | Tell it to read `lsf hitl status` and continue according to the answer. |
| Answer is stale / HTTP 409 | Proposal/artifacts changed. Ask Claude to open a fresh question; review again. |
| Local dashboard vanished | From the repo, rerun `lsf serve --port 8765 --open`. Keep its terminal open. |
| VPS dashboard vanished | Rerun `lsf-vps dashboard peak6 --port 8894 --open`. Remote work may still be running. |
| Wrong file opens | Check Editor and Workspace root; refresh the VPS snapshot and reopen the current file. |
| VPS terminal disconnected | `lsf-vps attach peak6`; `lsf-vps status peak6` reports running agent/dashboard. |
| Mac feels memory-constrained | Pause local Claude, save files, prepare a new VPS project and pass a handoff. Keep one active builder. |
| Test exits 124 / 137 | Time / memory guard stopped it. Narrow the test or explicitly adjust its budget. This isn't a passing test. |
| Login expired | Sign in on the affected machine with `claude auth login`; don't share a token in chat. |
| `claude -lsf` not recognized in an old terminal | Open a fresh terminal, or run `~/.local/bin/claude-lsf`. |
| `lsf` not found | Run `~/.local/bin/lsf` or open a fresh terminal with `~/.local/bin` on PATH. |

Remote tests should use `lsf-vps-test COMMAND...`. Its default budget is 4 GiB
sampled process-tree memory, 180 seconds and a shared test lock. Use the repo's
actual test command; not every project uses pytest or npm.

To switch mid-build, pause local Claude and save all on-disk work before copying.
Tell the remote Claude the brief, current PRD, completed work, failures, open
human decisions and next action. Source and `.lsf` transfer; conversational
memory and unsaved editor buffers do not. Don't run two builders on the same task.

## 8. Finish and show the result

At the final stop, ask Claude to show the user journey working, summarize the diff,
list tests with real results, identify remaining risks and explain tradeoffs.
Use Antigravity to inspect the critical code before accepting.

With local Claude, the commits/files are already in the local repo.
With VPS Claude, from the **original local checkout**, run:

```sh
lsf-vps fetch peak6
git log --oneline HEAD..lsf-vps/peak6
git diff HEAD...lsf-vps/peak6
```

Fetching brings commits home; it doesn't merge or alter the current working files.
After reviewing, ask Codex to integrate the desired commits into the submission
branch while preserving any local work. Don't submit the unchanged local branch
assuming fetch already merged it. Push/open a PR only as the interview requires.

## Your 30-second checklist

- Correct repo and task; one active builder; Sonnet selected.
- Three-stop profile configured before phases begin.
- Dashboard open with approval access; Antigravity points at the right files.
- VPS route: fresh snapshot at every review, findings sent back to the builder.
- Before build: agreed UX slice, checks and decision.
- Before done: demonstrated behavior, inspected diff, verified tests and documented gaps.

[All dashboard tab screenshots](../rehearsals/lsf-dashboard-gallery-2026-10-20.md)
· [Detailed VPS commands](lsf-vps-fallback.md)
