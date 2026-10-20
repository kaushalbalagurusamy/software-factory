---
name: plan-adherence
description: Use whenever the user hands over a precise, detailed spec for a multi-step implementation — one that includes concrete implementation details, acceptance criteria meant to be tested in a loop until they pass, and explicit out-of-scope boundaries. Save that spec verbatim, byte-for-byte, to a durable file BEFORE any planning, decomposition, or task-brief writing begins, and make every derived plan/brief/dispatch point back to that file for exact values instead of re-deriving them. Trigger this even if the user doesn't say "save this" or "plan adherence" explicitly — the signal is the shape of the message (long, structured, itemized requirements/criteria/scope), not the phrasing. Also trigger mid-project the moment a follow-up message changes or supersedes an earlier spec, or right before decomposing any such spec into a plan document or subagent task briefs.
---

# Plan Adherence

## Why this exists

A precise spec — the kind with numbered acceptance criteria, exact field names, literal JSON/table examples, and an explicit out-of-scope list — is only that precise once: the moment the user typed it. Every step after that (writing a plan document, splitting it into task briefs, dispatching a subagent, summarizing across a context compaction) is a chance to paraphrase something that should have been copied. A paraphrase reads as faithful and passes a skim, which is exactly what makes it dangerous: the drift is invisible until a downstream check catches it, usually several steps and several dispatched agents later, after real work has already been built on the wrong value.

This is not hypothetical. In one session, a plan document summarized a spec's literal JSON result-contract example instead of transcribing it, and quietly dropped one field's exact name (`uncited_displayed_claim` became a guessed `uncited_claim`). A dispatched implementer, working only from the plan's summary, had nothing to check its own reasonable-looking guess against, and a review cycle was spent catching and fixing it. The fix was cheap. Catching it relied on a reviewer thinking to ask "where's the real source for this," which is not something to leave to chance on every future spec.

The failure mode generalizes past JSON examples: a task-brief extraction tool that pulls one section of a larger plan for a subagent will, by construction, drop whatever lived in a different section — global constraints, an out-of-scope note three paragraphs up, a table defined once and referenced twice. None of that is anyone's mistake. It is what happens by default when the only copy of the source lives inside a document that keeps getting re-read, re-summarized, and re-excerpted instead of a document that never changes.

## When to use this

Reach for this whenever a message has the shape of a precise spec, regardless of whether the user names it that way:

- Concrete implementation details (specific files, exact field names, literal examples, precise commands).
- Acceptance criteria meant to be verified in a loop — "test until it passes," a list of required checks, an explicit verification sequence.
- An explicit out-of-scope or "must not" section, delineating what this work does *not* cover.
- Usually (not always) a multi-task or multi-session decomposition — "Task 1, Task 2...", "do X then Y", a sequence meant to survive more than one sitting.

A short, conversational request ("add a loading spinner to the button") is not this. A five-paragraph message with a numbered task list, named files to read first, and a block of acceptance criteria is. When in doubt, the cost of saving verbatim is small and the cost of not doing so, discovered three tasks later, is not — lean toward using this skill.

Also use this the moment a **follow-up** message changes, extends, or re-sequences an earlier spec (a `git log` for the conversation, in effect). Do not fold the follow-up into a revised version of the first saved file — see "When the spec changes" below.

## What to do

**1. Save the user's message verbatim, before writing any plan, ledger, or summary of it.** Not "faithfully paraphrased" — copied. Every line, in the order given, including formatting the user used (headings, code blocks, bullet nesting). Do not reorder sections to be more logical, do not compress a table, do not "clean up" a run-on paragraph. If the message is long, that is fine; this file is a source of record, not something anyone is meant to read start to finish every time.

Pick a durable, discoverable location and a name that makes the file's purpose obvious without opening it — a planning/spec directory the project already uses if one exists (check for an established convention — a `spec/`, `docs/planning/`, or similar directory — before inventing a new one), a filename that includes the date and a short slug, and `-original-prompt`, `-verbatim`, or similar in the name so nobody mistakes it for a plan document later.

Give the file a short header (this is the only part that isn't a literal copy) stating: what this is, that it is saved byte-for-byte, and — if relevant — what it supersedes or is superseded by. For example:

```markdown
# Original prompt — <short description>

> **What this is:** the verbatim, unmodified text of the task the project owner gave for
> <short description>. Saved byte-for-byte, with no paraphrasing or reorganization, on <date>.
> This is the source of truth every derived plan document and task brief should check exact
> values against, not a document that itself gets edited.
>
> **Status at time of saving:** <one line — what's done, what hasn't started>.

---

<the message, verbatim, starting here>
```

If the project is a git repository, commit this file immediately, on its own, before starting any planning work. A file sitting uncommitted in a working tree is one `git clean`, one crashed session, or one context compaction away from being the thing nobody remembers existed. Commit it even if the rest of the response is still in progress — this file is cheap insurance and should never wait on anything else finishing first.

**2. Treat the verbatim file as immutable.** Once saved, it is never edited, reformatted, or "improved" — not even to fix a typo the user made. If the spec needs correcting, that correction belongs in a plan document or a ledger entry that says so, not in the source record. This mirrors how a delivery plan transcribed from a released set of requirements stays untouched while new thinking goes in companion documents — the value of a verbatim record comes specifically from the guarantee that it never moved.

**3. Write plan documents and task briefs as decompositions that point back to the verbatim file, not as replacements for it.** A plan document should organize the spec into dispatchable units, sequence dependencies, and add the file-level detail the spec didn't have — but wherever it needs to state an exact field name, a literal example, a specific command, or a table, either quote it directly from the verbatim file or explicitly say "see `<verbatim file>`'s `<section>` for the exact shape" rather than re-typing it from memory. If a plan document's own prose ever disagrees with the verbatim file, the verbatim file wins, and the disagreement is a bug in the plan to fix, not a judgment call to make in the moment.

This matters most for the part of the process most likely to only see a fragment: task-brief generation for subagents. A tool or a manual excerpt that pulls "just this task's section" out of a larger plan will not carry along a JSON example defined once near the top, an out-of-scope note from a different section, or a cross-reference to another task. When writing a dispatch prompt for a subagent — especially one instructed not to read the full plan, or not to read certain directories at all — either inline the exact values it needs from the verbatim file directly in the dispatch, or give it the verbatim file's path and tell it explicitly which section answers which question. Don't assume the plan document's summary was complete; the two failures described above (a paraphrased JSON field, a globally-scoped rule left out of a task-scoped excerpt) both happened exactly this way.

**4. Preserve acceptance criteria and out-of-scope boundaries with the same discipline as implementation details.** A "test until it passes" loop is only meaningful if the exact test command, the exact pass condition, and the exact list of what must be verified survive intact — "run the tests" is not the same instruction as "run `pytest -p no:cacheprovider -q` and do not claim completion from unit tests alone; also run the fixture evals." An out-of-scope line is not a nice-to-have footnote; a request that says "do not touch Redis/Postgres" or "no live model calls without approval" is defining a boundary exactly as load-bearing as anything in the "must do" list, and it deserves the same verbatim treatment — paraphrasing "do not run paid model calls except an approved final smoke test" down to "avoid unnecessary spend" changes what's actually permitted.

**5. When the spec changes, save the new message verbatim too — as its own new file, never as an edit to the old one.** State plainly in the new file's header what it supersedes and, just as important, what it does *not* supersede (a follow-up that reorders execution but preserves all prior scope should say so explicitly, so nothing gets quietly dropped in the handoff). Update the living plan documents to point at whichever verbatim file is now authoritative for which part of the work, rather than merging the two source messages into one rewritten narrative.

## A concrete pattern worth reusing

Two-file split, once a spec is large enough to need real decomposition: a durable, boring **verbatim file** (exactly what's described above) sitting next to one or more **plan documents** that reference it. The plan documents are living — task status tables, commit SHAs, ledger notes, rulings made mid-execution — and get rewritten constantly as work proceeds. The verbatim file never changes after the moment it's saved. Readers who need "what exactly did the spec say" go to the verbatim file; readers who need "where do things stand" go to the plan document. Conflating the two — writing one document that's supposed to be both the source of truth and the living tracker — is how paraphrasing sneaks back in, because a document under constant edit pressure inevitably gets rephrased a little each time someone touches it.

## What this skill does not do

It does not replace planning discipline, task decomposition, or the actual engineering judgment a good implementation plan requires — a verbatim copy of the spec is the input to that work, not a substitute for it. It also isn't a reason to skip reading and understanding the spec deeply before acting; saving it verbatim is necessary, not sufficient, for faithful execution.
