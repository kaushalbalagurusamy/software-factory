# Ops dashboard tabs and where each reads from (SFN-03)

Historical tabs are built from the git object database at the snapshot commit. An empty source is `not available` with the paths searched, never an empty success (the evals tab is the one exception: a parseable `GOLDEN.json` is itself a measurement).

| Tab | Source the flow produces |
|---|---|
| PRD journeys | `docs/prd/onepager.md` (`## Journey: <name>`, a `Slices: a, b` line, 1 to 5 `- ` steps; over 80 lines adds `warning: "longer than one page"`, nothing is cut; an id with no `docs/slices/<id>/` path is flagged `unknown slice <id>`), `docs/slices/*/proposal.md`, `docs/prds/*.md` |
| Experiments | `experiments/<id>/results.json` (`kind: experiment`) and `experiments/<id>/resolved.json` `{question, resolved_by, sources:[...], as_of: YYYY-MM-DD}` (`kind: resolved`); `sf intake experiments check` validates both |
| Evals & bugs | `docs/bugs/<id>.md` (first heading = title, `Status: open|fixed|wontfix` else `invalid`, optional `Slice:` / `Criterion:`), `docs/bug-log.jsonl`, and `docs/slices/*/qa-notes.md` |
| Human stops | runtime: open stops from `.factory/stops` via `factory.hitl.store` (hash chain verified, read-only, never creates `.factory`); history: ADRs with status Proposed or Pending, and events with stage `hitl` in `ops/events.jsonl` |
| Langfuse | `ops/config.json` `langfuse: {host, project}`; `sf ops init --langfuse-host https://...` records the host (non-https exits 2; userinfo, query and fragment are dropped, no credentials are stored). Unconfigured shows `not measured: <reason>`; a slice proposal line `llm_features: true` without a host shows `LLM features declared in <ids> but Langfuse is not configured` |

## Human stops banner
`runtime.json["hitl"]` is `{verified, open:[{name, reason, opened_at, scope, release_by:"human"}]}`. Every tab shows `N open human stop(s)` when `open` is non-empty, `human stops unknown` when `runtime.json` or its `hitl` block is missing, and nothing when the verified ledger is empty. A ledger that fails verification yields one open entry and the text `stop ledger failed verification`; the runtime command still exits 0. Open stops never enter a snapshot.

## Committing QA notes
`sf qa promote-notes --slice DIR [--root R] [--protect P ...] [--allow-no-protect]` reads `R/.sf/slices/<basename DIR>/` and writes `DIR/qa-notes.md`: one `## Signature <id>` block with `attempts N` (counted failures), criteria, the observed error text, the expected text from `qa feedback`, and the regression proposal. No timestamps; an unchanged re-run does not rewrite the file. The feedback leak check runs first (exit 1, nothing written, protected text never echoed); a missing log (message names `.sf`), a symlink or a target outside the root also exit 1.
