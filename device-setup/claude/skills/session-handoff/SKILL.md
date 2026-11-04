---
name: session-handoff
description: Write or update a handoff document that lets a brand-new Claude Code session resume this exact project with zero prior context, plus a ready-to-paste starter prompt for that next session. Use this whenever a long or multi-step working session is wrapping up, whenever the context window is getting large or a compaction/context-limit warning has appeared, or whenever the user asks something like "can I close this window", "will I lose anything if I close this", "is anything at risk", wants a "pass doc", "handoff", "summary for the next session", or "what should I tell the next session". Also invoke this proactively, without being asked, right after a large body of work finishes in one session — a multi-task implementation plan, a long investigation, several shipped features or fixes — since that is exactly the moment a fresh session will most need this and the current session is the only one with the context to write it accurately. Do not wait for the user to ask if the signals above are present.
---

# Session handoff

## Why this exists

Nothing about a conversation's context survives when the window closes — not the reasoning, not the
"oh right, we tried that and it didn't work" moments, not the open questions that got raised and never
resolved. Code, commits, and files on disk survive fine; the *judgment* built up over a long session does
not. A fresh session that starts cold either re-derives everything the slow way, or worse, quietly acts on
a wrong assumption because nothing told it otherwise.

A good handoff document is the difference between a new session picking up cleanly and a new session
re-litigating decisions that were already made, or missing a blocker that was already found. This skill's
job is to make writing that document a habit, not a one-off — the same way `USERS.md`'s target user needs
a five-line brief instead of a chart dump, the *next session* needs a handoff instead of a raw commit log.

## When this fires

Two different triggers, both real, and increasingly common when a project runs many long, agentic sessions:

- **Reactive**: the user is closing out, asks about losing work, or explicitly asks for a pass-off.
- **Proactive**: this session itself just finished something substantial — a shipped feature, a resolved
  investigation, several fixes — and nobody has to ask for the write-up to make it worth doing before that
  context evaporates.

If you notice the proactive signal and the user hasn't asked, say so and offer it rather than staying
silent — a completed body of work with no handoff is a missed opportunity that costs nothing to avoid.

## The process

### 1. Find the existing handoff doc, if one exists

Run `scripts/find-handoff-doc.sh` (from this skill's directory) against the repo root. If it finds one,
**that file is what you update, not something you fork a second copy of** — read it in full first. Its own
header usually states when it was last written and what it covers; that's your baseline.

If none exists, this is the first one for this project. Pick a sensible, discoverable location —
`docs/planning/` or `docs/` if the project already has that structure, otherwise the repo root as
`HANDOFF.md`. Check `README.md` and any project-specific `CLAUDE.md`/`AGENTS.md` for a documentation
convention before inventing a new one.

### 2. Establish what's actually new since the last version

If a prior handoff exists, `git log --oneline <last-commit-touching-that-file>..HEAD` (and `git diff
--stat` over the same range) tells you exactly what happened since it was written — don't rely on your own
memory of the conversation alone, verify against the commit history, the same way you'd ground any other
claim in this codebase's files rather than assumption. If this is the first handoff, the "since" boundary
is just "since this project started" or "since the last known-good state" — use your judgment, but say
explicitly what range you're covering.

Also check for anything valuable that exists **only locally and is not in git** — a subagent-driven-plan's
ledger (e.g. `.superpowers/sdd/*/progress.md`), scratch notes, an in-progress spec bundle not yet committed.
These are exactly the kind of thing that's expensive to reproduce and easy to lose track of. If something
like this holds real decisions or findings, either fold the substance into the handoff doc's prose or name
its exact path and say plainly that it's local-only and won't travel to a fresh checkout on another machine.

### 3. Gather the substance, not just a commit list

A handoff is not a changelog. For each thread of work from the session, capture:

- **What actually shipped or got resolved**, cited to real files/commits — not "we worked on X" but "X is
  implemented in `path/to/file.py`, commit `abc123`, tested by `path/to/test.py`."
- **Real findings**, especially ones that overturned an earlier assumption or corrected something believed
  going in. A discovery that "the thing we thought was true wasn't" is far more valuable to hand off than a
  list of files touched — it's exactly the kind of insight a fresh session has no way to re-derive except by
  making the same mistake again.
- **What's genuinely still open, and precisely why** — not "TODO: fix X" but the actual blocker: what's
  known, what's unknown, what the next concrete step is. A vague "this needs more work" forces the next
  session to re-investigate from scratch; a named blocker lets it start exactly where this one stopped.
- **Decisions that were made along the way**, especially ones with real reasoning behind them (a design
  ruling, a rejected alternative, a scope call) — these are cheap to lose and expensive to redo.
- **Anything genuinely open for the user's judgment**, distinguished clearly from things that are simply
  unstarted. Don't let "not yet decided by anyone" read the same as "decided, just not built."
- **A live-state verification snippet**, if the project has anything deployed or running that the next
  session should confirm still works before trusting anything else in the document — a live system can
  drift out from under a stale doc, so give the next session a cheap way to check rather than asking it to
  trust prose.

### 4. Write it for someone with zero context

The single most important test: could a fresh session, with no memory of this conversation, read this
document and know what to do next without asking you to re-explain anything? Concretely:

- Cite files and line numbers or commit hashes instead of asserting facts from memory — if a claim in the
  doc turns out to be wrong, the file it cites is the tie-breaker, not the document itself. Say this
  explicitly in the doc's own preamble, the same way this convention shows up in well-written handoffs.
- Never reference "the fix we discussed" or "that thing from earlier" — spell out what it was, since the
  reader has no earlier to point to.
- Mark an open decision as open. Don't quietly resolve it yourself just to make the document feel more
  finished — a handoff that invents answers is worse than one that honestly says "nobody has decided this
  yet."
- If this document supersedes a prior version, say so at the top, and don't silently drop sections from the
  old one that are still true — either carry them forward or explicitly note they're now resolved.
- Prefer a short, scannable structure (numbered sections, a clear headline of "the one thing that matters
  most" near the top) over a wall of undifferentiated prose. The next session will skim before it reads
  closely, the same way a clinician skims a chart before reading a note in full.

### 5. Produce the starter prompt as its own, separate deliverable

The handoff document and the prompt that tells a new session to *read* it are two different things — write
both. The starter prompt should:

- Tell the new session to read the handoff document in full before doing anything else.
- Give a one-or-two-sentence preview of what's in it (enough that the user reading the prompt later
  remembers roughly what they're about to get, without needing to open the file first).
- End by asking the new session to summarize what it understood and ask which thread to pick up, rather
  than assuming — the same discipline this session should have used when it started.

Give this to the user directly in your reply — it doesn't need to be a file, since the user pastes it
verbatim into a new session.

### 6. Commit it, and use judgment about sending it

Commit the handoff document following this repository's own commit conventions (atomic, attributed per
whatever standing convention this session has already been using). If the user appears to be stepping away
or explicitly asked about closing the window, and a file-sending tool is available in this environment,
send the document directly rather than only linking to its path — the whole point is that they shouldn't
have to go find it later.

## What good looks like

A handoff document that does its job reads like the opening pages of a well-run on-call handover: here's
the state of the world, here's the one thing most likely to bite you, here's what's genuinely undecided and
needs a human, here's how to check nothing has quietly broken since this was written. It is a summary
written *for* the next reader, not a diary written *by* the last one.
