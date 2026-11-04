---
name: good-morning
description: >-
  Use when the owner wakes up after an overnight run that good-night opened. Closes the run, builds
  a private Artifact report of what happened overnight from the journal and git (slices, commits,
  tests, spend, stalls, blockers), then walks the owner through the queued decisions one at a time
  and hands back to the normal /sf loop. Triggers: "/good-morning", "good morning", "I'm up", "what
  happened overnight". Only works if good-night was invoked; otherwise it says so and stops.
---

# Good morning

State helper: `~/.claude/skills/good-night/scripts/overnight.sh` (run from the project checkout).

## 1. Check that a night ran

Run `overnight.sh status`. If no run is open, say so in one line ("No overnight run is open for
<project>; good-night was not invoked here") and stop. Do not build a report from git history alone:
without the journal there is no record of what was blocked or queued, and a report that looks
complete but is not is worse than none. If the owner wants a general status instead, that is
`progress-briefing`.

## 2. Close the run and gather facts

1. `dir=$(overnight.sh end)`. From here on the overnight rules no longer apply; the owner is
   reachable again.
2. Read, from primary sources only:
   - `$dir/run.json` (start and end time, start and end HEAD, the night's note)
   - `$dir/journal.md` and `$dir/decisions.md`
   - `git log --oneline <start_head>..HEAD` on the run's branch, and on any branch the journal names;
     whether each is pushed (`git status -sb`, `git log @{u}..`)
   - the ledger now, compared with the plan lines at the top of the journal: rows moved, rows still
     open, rows newly blocked
   - test and eval results from the separate runner, not the implementer's claim
   - spend from the journal's spend lines and, where possible, the provider's own accounting
   - anything still running (background agents, tasks, wake-ups); say whether it is still needed
3. Anything you cannot verify is written as "not checked" on the page, never inferred.

## 3. Publish the overnight report

Build one private Artifact page (HTML, phone-first; follow the Artifact tool's page contract and
the artifact-design guidance). Title it "<Project> overnight <date>". If the project has a
progress-briefing page, link it; do not overwrite it. Sections, in order:

1. **Summary strip:** hours run, slices finished, commits, ledger rows moved (e.g. 41 to 44 of 60
   satisfied), spend against the ceiling, decisions waiting.
2. **Decisions waiting on you**, ranked by how much work each unblocks, each with its one-line
   question, options and recommendation. Then, separately, **decided overnight, for your review**:
   each ADR marked `Decided overnight (pending owner review)`, with the choice, the deciding evidence
   and what was built on it. This is the section the owner acts on, so it comes before the history.
3. **What got done:** per slice, the row, the stage it reached, its test and review result, and its
   commits (short sha and subject), pushed or not, merged or deployed where applicable.
4. **What stalled or failed:** blockers, stalls, failed gates and how each was handled, with the
   time it happened. Report failures as plainly as successes.
5. **Still running and next up:** live tasks, and what the loop will take next once decisions land.
6. **Footer:** run directory, start and end HEAD, "as of <time, zone>".

Send it with SendUserFile too if the owner is on the phone. In chat, give a three-line summary and
the link; do not paste the report.

## 4. Bring the decisions back, one at a time

Go through `decisions.md` in the report's ranked order. For each: state the question, the
options, the evidence in a sentence, and your recommendation, then wait for the owner's free-text
answer before the next one. Record each answer verbatim as Human (owner) direction in the place the
decision belongs (the ADR, backlog or project state), and mark it answered in `decisions.md`. If the
owner defers one, keep it open and say what stays blocked. Then do the same for the decisions made
overnight: the owner confirms or overturns each. A confirmation changes the ADR status to accepted
with the owner's words; an overturn becomes the next slice's first work, including reverting what was
built on it.

## 5. Hand back to the normal loop

When the queue is answered or deferred, invoke `/sf` and resume normal operation: questions are
allowed again, and the next slice is chosen from the ledger with the new answers applied, starting
with the rows those answers unblocked. Run stage 12 (inbound check) first, since the owner may have
added work overnight.
