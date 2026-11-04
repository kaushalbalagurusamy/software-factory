---
name: brownfield-explorer
description: >-
  Use this skill whenever someone needs to orient inside an unfamiliar, large, or "brownfield" codebase before doing anything else with it — even if they never want formal specs, axioms, or contracts out of it. Triggers include: "help me understand this codebase", "where does X live", "what would this change touch", "onboard me into this module", "map the blast radius of...", "give me a mental model of...", requests to explore, tour, or get oriented in a repo, and any task that starts with a multi-hundred-thousand-plus-LOC repo the user hasn't scoped yet. Also use it as the first move before scoping a bug fix, a PR, or a refactor in a codebase you (Claude) haven't worked in recently, even if the user didn't ask for orientation explicitly — reading the whole repo is not an option, so orient cheap, then expand from the actual entry points to find what the change really touches, and write down what you found so the next person (or the next you) doesn't repeat the search. Also use it to pick up crashed, interrupted or half-finished work: a session died or the user asks "where did the last session stop", "pick this back up", "what was I in the middle of", or `git status` shows uncommitted or untracked files nobody reviewed. Reconstruct what landed, what stopped and what is unreviewed from the commit history, file modification times, session transcripts and the working tree before resuming. Do NOT use this for greenfield work (nothing exists yet) or once the user has already asked for formal axioms/contracts/a spec bundle for a scoped change — that goes to `axiomatic-spec`, which calls into this skill for its own orientation step and then continues with contract extraction.
---

# Brownfield Explorer

> For a complete, cover-to-cover read of a legacy codebase before a rewrite (per-unit analyses and a bug catalog), use `legacy-audit`. This skill is the cheap orientation that comes first.

## What this is for

You cannot read a multi-million-line-of-code repository, and trying to is worse than not trying: it burns the context budget you needed for the actual task, and skimming under pressure means you miss the caller that holds a lock or the second write path nobody mentioned. The fix isn't compression — a 4x semantic squeeze on 5M LOC is still 15x over a 1M-token budget. The fix is **selection**: find the small, real subgraph a question or a change actually touches, using the cheapest source that answers it, and stop as soon as you hit a boundary you can trust.

This skill is for the moment *before* you start reading or editing code in a codebase you don't already hold in your head: "where does X live", "what would touching Y break", "get me oriented in this module", or just "help me understand this codebase." The output is a map, not a fix and not a spec — callers/callees, data stores, boundaries, and a file list, written down somewhere durable so the next person (including future-you, or `axiomatic-spec` continuing on to write contracts) doesn't have to re-derive it.

## Workflow

### 1. Figure out what's actually being asked

Before spending a single tool call, pin down: what's the entry point or symbol the question centers on (a feature name, an endpoint, a table, a file, a bug report)? Is this "just tell me where things are" (stop after orientation) or "I'm about to change X" (orientation + blast radius)? If the user's request is vague ("help me understand this codebase"), a light full-repo orientation is the answer; if it names a specific change or symbol, go straight to blast-radius expansion from that entry point once you've got the cheap structural context.

### 2. Orient wide and cheap — read before you grep, grep before you open files

Cheapest sources first, in this order, and stop climbing the ladder as soon as you have enough to proceed:

1. **What's already written down.** `CLAUDE.md`, `ARCHITECTURE.md`, `README`, `docs/adr/` or `docs/reference/`, `CODEOWNERS`. Check for a prior orientation doc this skill (or a human) already wrote for this project — see step 5, "reuse before rewrite." If one exists and isn't stale, most of this workflow is just a targeted update.
2. **Structural map, no bodies.** `git ls-files | awk -F/ '{print $1"/"$2}' | sort | uniq -c | sort -rn` for where the mass is; LOC per top-level directory (`tokei`/`cloc` if present, else `wc -l` over `git ls-files`); a symbol-level map (`ctags -R --output-format=json`, or a tree-sitter walk emitting `path:line: def name(params) -> ret`) — signatures only, never bodies, at this stage. An import/dependency graph at the module level (`pydeps`, `go list -deps`, `madge`, or a grep of import lines) turns the directory list into a walkable DAG.
3. **Pre-built understanding, if it exists.** For a public repo, DeepWiki (`read_wiki_structure` → `read_wiki_contents` for the relevant module → `ask_question` for "where is X handled") is free orientation — treat its answers as a fast lead, not ground truth, and confirm every symbol it names actually exists on disk before citing it. Add it once with `claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp` if it isn't already configured. For a private repo, or if DeepWiki has nothing, fall back entirely to the structural map — that's normal, not a failure.

Full detail and the token-budget math behind "why selection, not compression" is in `reference/blast-radius-scoping.md` — read it before a first-time orientation of a codebase over ~100k LOC.

### 3. Expand from the entry point to the real blast radius

Skip this step if the ask was pure orientation with no specific change in mind — steps 1-2 already answered it. Otherwise, start from the entry point(s) the question or change names (an endpoint, a CLI command, a job, a UI form, a table) and expand outward one hop at a time, logging each addition and the reason it was pulled in:

- **Callers** of anything already in the set — grep for the symbol name, or LSP "find references" where available.
- **Callees that cross a boundary** — anything that touches a DB, queue, filesystem, or network call, not pure in-process helpers.
- **Shared state** — any other module reading or writing the same table, cache key, global, or struct field.
- **Synchronization** — any lock, channel, atomic, transaction, or idempotency key on the path. This is where silent breaking changes hide, so treat any lock/tx boundary as worth one more hop even if nothing else about it looks interesting.
- **Public surface** — any exported function, type, or endpoint in the set that code outside this subgraph depends on.

Stop expanding at a boundary that already has a stable, tested contract (a public interface with its own test suite) — record it as an assumption and don't descend into it. Also stop at code that only reads results without depending on the invariant in question. Target **≤ ~50–100 files, ≤ ~10–15k LOC of bodies** actually read in depth; past that the change is bigger than one pass can respsonsibly handle.

### 4. Say so when the scope is bigger than assumed

If the entry point the user named turns out to have three other write paths nobody mentioned, or the "small tweak" touches a table five other modules also write to, that is itself the finding — say it plainly, before going further, rather than quietly scoping down to fit the assumption. This is usually the single most valuable sentence in the whole exercise: "you asked about the calendar save function; there are actually 4 places appointments get created, and this table has no existing lock around the count you want to enforce."

Signals the scope drifted wide, worth calling out explicitly:
- Three hops of callers in and you're still finding newly-mutated state.
- The subgraph has no tests at all — anything you write about its current behavior is inferred, not observed, and that's worth flagging on its own.
- More than ~5 modules write the same table/struct — that's very likely an undocumented global invariant, not incidental coupling.
- A lock is taken in one module and the state it protects is read without the lock somewhere else — an existing race, not something to design around quietly.

### 5. Write (or update) the durable artifact — reuse before rewrite

The output is a map, and maps go stale slower than code changes, so write it to the **target project**, not this skill's own directory: `docs/reference/<topic>-map.md` (or wherever that project already keeps this kind of reference — check for an existing `docs/reference/` or similar pattern first). Structure:

```markdown
# <Topic> map

> As of <date>[, with corrections on <date>]
> Sources: <CLAUDE.md/docs read, DeepWiki y/n, files verified on disk>

## Scope
Entry point(s): ...
Files in scope: N (list, or link to a longer list if large)
Boundaries assumed stable (not descended into): ...
Expansion log: <symbol> ← added because <reason>

## What's here
<the actual map: modules, key symbols, data flow, ownership>

## Blast radius (if a change was in view)
Callers / callees / data stores / locks / public surface crossed, and which
of these is a one-way door if touched.

## Open questions / things not covered
```

**Before writing a new file, check whether one already exists for this area of the codebase.** If it does and it's not stale (dates line up, the facts still check out on a spot re-read), update it in place rather than duplicating: append a dated "corrections on <date>" note for anything that changed, refresh facts that drifted, and leave the rest alone — this mirrors how a human maintainer would keep a wiki page current. Only write from scratch when nothing usable exists yet, or the existing doc covers a genuinely different area.

Every path, class name, and table name in the artifact must be something you actually verified on disk during this pass — DeepWiki and memory are leads, not citations. Don't include what you didn't check.

### 6. Hand off cleanly

Close with a short inline summary: what you now know, the file count and rough LOC in scope, the biggest surprise (if any), and where the artifact landed. If the user's actual goal is a full spec with pre/postcondition contracts for a change on this scoped surface, say that the natural next step is `axiomatic-spec` — hand it this skill's scope (entry points, file list, boundaries assumed stable) as its starting point rather than making it re-derive the same orientation.

## Judgment calls

- **Selection over compression, always.** If you're tempted to summarize your way through a directory you haven't actually looked at, stop — that's how a caller holding a lock gets missed. Spend the extra tool call instead.
- **A pure "where does X live" question doesn't need the full blast-radius expansion.** Steps 1-2 alone often answer it. Don't manufacture a change to expand from when nobody's making one.
- **The map is for reuse, not a one-off answer.** Writing it to the target project's own docs, and updating rather than duplicating on reuse, is what turns this from "an answer" into "an asset." Skipping the write because the immediate question felt small is a false economy — the next question about this area starts from zero again.
- **Uncertain beats confidently wrong.** Anything inferred rather than directly observed (behavior with no tests, an unread branch) gets flagged as such in the artifact, not smoothed over.
