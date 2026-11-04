# Blast-radius scoping: finding the subgraph without reading the repo

## Budget reality

Rough numbers to keep in mind (they vary by language and style, so treat them as order-of-magnitude):

| Thing | Approx. tokens |
|---|---|
| 1 line of source | 8–15 |
| 10k LOC raw | 100–150k |
| 1M-token context, raw source | ~30–50k LOC (leaving room to think and answer) |
| 5M LOC raw | ~50–75M tokens — 50–75x over budget |
| 5M LOC at 4x semantic compression | still ~15M tokens — 15x over budget |

Conclusion: compression alone never makes whole-repo ingestion viable at this scale. The lever is **selection**, and the cost of a bad selection (missing a caller that holds a lock) is worse than the cost of spending a few more tool calls scoping. Compression is worth it *after* scoping, to fit a larger subgraph than raw source would allow.

## Layered approach: cheap → expensive

Each layer narrows the set before the next, more expensive layer runs.

### Layer 0 — Prior knowledge (free)
- `CLAUDE.md`, `ARCHITECTURE.md`, `docs/adr/`, `docs/reference/`, `CODEOWNERS`, top-level README.
- Any orientation doc this skill (or a human) already wrote for this area of the codebase — check before assuming you're starting cold.
- The user's own description of where the change lives — ask if it's missing.

### Layer 1 — Structural map (seconds, no bodies)
- `git ls-files | awk -F/ '{print $1"/"$2}' | sort | uniq -c | sort -rn` — where the mass is.
- LOC per top-level dir (`tokei` or `cloc` if present, else `wc -l` over `git ls-files`).
- Symbol map: signatures only. `ctags -R --output-format=json` or a tree-sitter walk that emits `path:line: def name(params) -> ret` per function/class. Aider-style repo maps are this shape. Keep bodies out of context.
- Import/dependency graph at the module level (`pydeps`, `go list -deps`, `madge`, or grep of import lines) → a DAG you can walk.

### Layer 2 — Pre-built understanding (if available)
- **DeepWiki** (Cognition): `read_wiki_structure` → `read_wiki_contents` for the relevant module → `ask_question` for "where is X handled / what calls Y". Free, no auth, **public repos only**. Add to Claude Code with `claude mcp add -s user -t http deepwiki https://mcp.deepwiki.com/mcp`. Treat its answers as a fast orientation, not ground truth — confirm the symbols it names actually exist.
- Any internal code-search/graph index the team already runs (Sourcegraph, SCIP, Glean, LSP). Prefer these over grep when present.

### Layer 3 — Blast radius expansion (targeted reads)
Starting set: the entry points the question or change names (an endpoint, a CLI command, a job, a table, a UI form).

Expand by these edges, one hop at a time, and log each addition with the reason:
- **Callers** of anything in the set (grep for the symbol name; LSP "find references" if available).
- **Callees** that mutate state or cross a boundary (DB, queue, network, filesystem).
- **Shared state**: any module that reads/writes the same table, cache key, global, or struct field.
- **Synchronization**: any lock, channel, atomic, transaction, or idempotency key on the path — these are where one-way doors hide.
- **Public surface**: any exported function/type/endpoint in the set that external code depends on.

Stop expanding at:
- A boundary with a stable, tested contract (a public interface with its own test suite) — record the contract as an assumption, don't descend.
- Code that only *reads* results without depending on invariants you're changing.
- The budget line: ~50–100 files, or ~10–15k LOC of bodies. Past that, split the change or report that it's larger than assumed.

### Layer 4 — Deep read of the scoped subgraph
Now, and only now, read bodies for the files actually in scope. This is where this skill's job ends: hand the scoped file list, expansion log, and boundary assumptions to whatever comes next. If that next step is extracting formal pre/postcondition contracts for the change (the `axiomatic-spec` skill's job), it picks up here rather than re-deriving the scope.

## Signals that the scope is wrong

- You've read three hops of callers and still find new state being mutated → the change is bigger than framed; report before continuing.
- The subgraph has no tests → current behavior is entirely inferred, not observed; flag that the current behavior itself is unverified.
- The same table/struct is written from more than ~5 modules → likely a hidden global invariant worth calling out explicitly.
- A lock is acquired in one module and its protected state is read without the lock in another → existing race; this is a finding, not something to design around silently.

## Deliverable for the scoping step

The orientation/map artifact (see SKILL.md step 5) opens with a scoping section:

```
## Scope
Entry points: ...
Files in scope: N (list)
LOC in scope: ~M
Boundaries assumed stable (not descended): ...
Layer-2 sources used: DeepWiki / internal index / none
Expansion log: <symbol> ← added because <reason>
```

This makes the scoping auditable — a reviewer can see what was excluded and why, which is the whole point.
