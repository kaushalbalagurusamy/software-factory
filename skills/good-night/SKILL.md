---
name: good-night
description: >-
  Use when the owner is going to sleep and wants the build loop to keep running unattended until
  morning. Opens an overnight run for this project, then drives /sf in non-blocking mode: blockers
  are broken through with research and experiments (one-way doors included, when the evidence is
  sufficient), paid model calls run within a $10/day cap, and only owner-gated actions or
  undecidable questions are queued for the morning, so the run never stalls. Triggers: "/good-night", "good night",
  "going to sleep", "run overnight", "keep going while I sleep", "full auto tonight". Pair with
  good-morning, which only works after this skill opened a run.
---

# Good night

The owner is asleep for the next several hours and will not answer anything. A full-auto `/sf` run
stalls overnight for a handful of predictable reasons: it asks a question and waits, it reaches a
human gate and stops, it waits on a background agent that hung, or it hits a dead credential and
treats that as the end. This skill removes each of those stalls by turning every one of them into a
queued entry for the morning and moving on.

The night breaks through blockers the way sf always does: research and experiment until the answer
is evidence, not opinion. That includes one-way decisions: with sufficient research and experiment
behind it, the night decides and records it (owner direction, 2026-10-17). What it does not do is
take the irreversible or outward-facing actions the global rules gate on the owner (see "What this
skill never does"); those wait in the queue.

State helper: `~/.claude/skills/good-night/scripts/overnight.sh` (run from the project checkout).
Its state lives in `<repo>/.claude/overnight/`, is excluded from git, and is what `good-morning`
reads.

## Start the run

1. `overnight.sh start "<one line: what the owner asked for tonight, verbatim if given>"`. If a run
   is already open, keep it; do not start a second.
2. Invoke `/sf` (the `sf` skill) and load the project's build-loop profile, ledger and backlog, as
   any slice would.
3. Run `~/.claude/skills/sf/hygiene/hygiene.sh scan`. A night is long; start with disk and memory
   headroom, not with whatever is left.
4. Check the credentials the plan will need **now**, while the owner is still awake: each API key
   the night's experiments call (a cheap authenticated read such as the provider's key-status
   endpoint, never printing the key), and each CLI (`gh api user`, `railway whoami --json`). A dead
   key found at 03:00 costs a night; found now, it costs one sentence.
5. Write the night's plan as journal lines (`overnight.sh log note ...`): the ledger rows you will
   take in order, each marked ready or blocked-with-dependency, and `overnight.sh budget` for the
   spend left today.
6. Tell the owner, in a few lines: the ordered plan, what is already blocked on them and therefore
   will not happen, any credential that failed in step 4, and that `good-morning` closes the run.
   This is the last message that expects a reply; anything they answer before sleeping is recorded
   as Human (owner) direction.

Then begin the first ready slice. Do not wait for an acknowledgement.

## Overnight rules (they hold until good-morning closes the run)

**Never wait on the owner. Find out instead.**
- Do not call AskUserQuestion, do not end a turn on a question, and do not ask "shall I proceed".
- A decision that blocks work is a research and experiment problem first. Run sf stages 1–3 on it:
  `grounded-research` or `deep-research` for the facts, `experiment-designer` for numbers on the
  options (multi-metric, from a dated enumeration), then decide.
  - **Reversible choices:** decide, record the reasoning in the ADR or journal, keep going.
  - **One-way doors:** use `one-way-door`. Decide overnight when the evidence is sufficient: the
    options were enumerated, the deciding claims are grounded in primary sources or measured, and
    the experiment separates the options on the metrics that matter. Write the ADR with the evidence
    and its honest limits, mark it `Decided overnight (pending owner review)`, and log a `decision`
    line so good-morning shows it for review. Then build on it.
  - **Not sufficient** (the evidence is split, the deciding fact cannot be grounded, or the answer
    is a matter of the owner's taste, goals or priorities rather than fact): queue it with
    `overnight.sh decide`, giving the question in one line, the options, what research and
    experiments already showed (file paths), your recommendation, and what work it unblocks. Then
    research both branches or take the next independent row.
- A changed settled requirement, an owner-stated preference, or anything the global rules gate on
  the owner is never decided overnight, however strong the evidence; queue it.
- Where the project's delegation lets Codex resolve engineering questions, that route still works.

**Spend is allowed within the daily cap.** Owner direction (2026-10-17): OpenRouter and the
Anthropic console share $200 a month, so under $10 a day is fine without asking. The cap is per day
across every session on the host, not per night per session.
- Before a paid run, check `overnight.sh budget`, and dry-run anything that can cost more than a
  dollar to get a projection.
- After each paid run, record the measured amount from the provider's own accounting:
  `overnight.sh spend <usd> "<project>: <experiment>"`. Exit 3 means the day's cap is reached: stop
  paid calls and take no-spend work.
- A project's own stricter limit wins. An experiment projected above what is left today is trimmed to
  fit, split across days, or queued with the projection; it is not started in the hope it stays
  under.

**Never stop on a blocker.** Record it (`overnight.sh log blocked "<row>: waits on <dependency>"`)
and take the next ready row from the ledger. Typical night blockers and what to do instead:

| Blocker | Instead |
|---|---|
| Expired or missing key, failed auth | Log it, queue the rotation as a decision, run the offline parts (tests, dry runs, scoring cached results) |
| Spend would cross the daily cap | Trim or split the experiment to fit what is left, or queue the projection; take a no-spend row |
| An undecided design question | Research it, run the experiment that separates the options, decide (one-way door rules above) |
| A human gate (merge outside the auto-merge scope, force-push, deletion, demo recording) | Prepare everything up to the gate, queue it, move on |
| A test fails for a reason outside the slice | Classify it (environment crash vs real), log it, keep the gate red, take another row |
| Two rows contend for the same tree | Serialise them; do another independent row meanwhile |

**Never sit on a hung wait.** Give every background agent, test run or crawl an expected duration
when you start it. If one runs more than twice that with no output, log a `stall`, stop it if it is
yours, and continue. If the harness offers a wake-up (ScheduleWakeup under `/loop`, or CronCreate),
schedule a long fallback heartbeat (about 30 minutes) so a missed notification cannot park the run.

**Keep the loop intact.** Every slice still runs all twelve sf stages: tests first, blind
implementation, separate runner, adversarial review, drift check, doc-sync, atomic commits. Overnight
speed comes from never waiting, not from dropping stages. Push ordinary commits as usual; merge and
deploy only where already authorised (for example the W4 auto-merge scope).

**Prefer work that will still be right in the morning.** Order the night: ready implementation
slices first, then experiments within budget, then research and reviews for blocked rows (read-only
plus scratch, per the dependency rules), then doc and dashboard sync. Do not start a large rewrite
whose direction depends on a queued decision; research both branches of it instead.

**Journal as you go**, one line per event, because good-morning builds its report from the journal
and git, not from your memory of the night:
- `overnight.sh log slice "<row id>: <stage reached>, <result>"`
- `overnight.sh log commit "<sha> <subject>"` for anything worth naming (git log has the rest)
- `overnight.sh log spend "<experiment>: \$<amount> from provider accounting"`
- `overnight.sh log stall|blocked|note "<text>"`

**After a compaction**, run `overnight.sh status` first. If a run is open, these rules apply again
before anything else; reread this file.

## When everything left is blocked on the owner

If every remaining ledger row is blocked on a queued decision or an external dependency, the night
is done early. Log `note "all remaining rows blocked; idle"`, run the sf idle sweep (commit and push,
stop your own processes, hygiene plan and apply), and stop. Do not invent work outside the ledger to
fill the time, and do not close the run: good-morning does that.

## What this skill never does

- Spend past the daily cap, or grant itself a permission the global rules do not already give.
- Take an irreversible or outward-facing action the global rules gate on the owner: force-push or
  history rewrite, branch or data deletion, merges or PRs outside the auto-merge scope, publishing.
- Answer a queued decision on the owner's behalf once it is queued, or overrule an owner-stated
  preference or settled requirement.
- Record a demo, publish outside the project's authorised surfaces, or message anyone new.
- Close the run. Only good-morning closes it.
