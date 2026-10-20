# SFN-03: Every dashboard tab has a source the flow produces

| | |
|---|---|
| **Delivers** | Owner clauses D2, D4, D7, D8, D9, R7c in `docs/requirements/sf-owner-flow-clauses.tsv`, plus the human-stop view |
| **Depends on** | SFN-01 (events, `ops init`), merged first |
| **Implementer model** | Sonnet |
| **Source of truth** | `docs/requirements/sf-owner-flow.md`, verbatim |

## Purpose
Four dashboard tabs show "not available" in this repo because nothing in the flow writes what they read: the one-page core PRD "summarized as 1 page for UX journeys", experiment results, the bug log, and the QA repeat-failure notes. The owner also wants every human stop visible. Define the artifact each tab reads, make the flow produce it, and keep every empty tab honest.

## UX story (first)
As the owner on a phone, I open the PRD tab and read one page of user journeys with the slices that serve each; I open Human stops and see what is waiting for me and since when; I open Evals & bugs and see the repeated failures QA wants turned into test cases.

## Required behaviour
- **T-01 one-page core PRD.** Convention `docs/prd/onepager.md`: a title line, then one `## Journey: <name>` section per user journey, each with a line `Slices: <id>, <id>` and 1 to 5 bullet steps. The `prd_journeys` collector returns the page's journeys (name, steps, slice ids, and for each slice id whether `docs/slices/<id>/` exists). A page longer than 80 lines is returned with `warning: "longer than one page"`, never truncated silently. A journey naming a slice id with no directory is flagged `unknown slice`.
- **T-02 other PRD sources.** The same tab also lists slice proposals (`docs/slices/*/proposal.md`) as before and PRD files under `docs/prds/*.md` (`kind: prd`, title, the Delivers line). The tab is unavailable only when none of the three sources exists, and the reason names all three paths.
- **T-03 experiments, including skipped ones.** `experiments/<id>/results.json` as before, plus `experiments/<id>/resolved.json` `{question, resolved_by, sources:[...], as_of}` for a choice settled by research. `sf intake experiments check` accepts a valid `resolved.json` (non-empty `resolved_by`, at least one source, a date) and rejects one missing any of those with exit 1. The Experiments tab lists both kinds with a `kind` of `experiment` or `resolved`.
- **T-04 bug log.** Convention `docs/bugs/<id>.md`: first heading is the title, a line `Status: open|fixed|wontfix`, optional `Slice:` and `Criterion:` lines. The `bug_log` collector returns these and the repeated-failure entries of every `docs/slices/*/qa-notes.md`. Unknown status values are returned as `status: "invalid"`, not dropped.
- **T-05 QA notes are committed.** `sf qa promote-notes --slice DIR [--root R]` writes `DIR/qa-notes.md` from the QA attempt log in `.sf/`: per failure signature the attempt count, the public criterion ids, a short observed/expected summary and any regression proposal ids. It runs the existing feedback leak check over the text and exits 1 without writing if protected material is found. Running it twice yields byte-identical output when nothing changed. It writes only inside `DIR`.
- **T-06 Langfuse honesty.** `ops/config.json` may hold `langfuse: {host, project}`. The Langfuse tab says `not measured: <reason>` when unconfigured; when a slice proposal declares `llm_features: true` and no host is configured it says `LLM features declared in <slice ids> but Langfuse is not configured`. `sf ops init --langfuse-host URL` records the host (https only; any other scheme exits 2). No credentials are ever stored in the config or printed.
- **T-07 human stops view.** A new `hitl` tab. Runtime part: open stops from the stop ledger under `.factory/stops` read through the `factory.hitl` store (name, stage, reason, opened-at, and who may release), with the ledger's hash chain verified; a chain that fails verification is shown as `stop ledger failed verification` in the same place, not as zero stops. Historical part: ADRs with status Proposed or Pending, and events with stage `hitl`. A banner `N open human stop(s)` appears on every tab when the runtime part has any open stop; when the runtime file is absent the banner says `human stops unknown`, not none. The collector never writes to `.factory`.
- **T-08 no fake availability.** For every historical collector, `available: true` requires at least one item. An empty source returns `available: false` with a reason saying which path was searched.
- **T-09 snapshots stay reproducible.** All new collectors read from the git object database at the snapshot's commit like the existing ones; the runtime part of T-07 is the only live read and is excluded from snapshots.
- **T-10 nothing existing breaks.** Existing `tests/test_ops*.py`, golden and eval suites pass without edits to their assertions.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write unit tests under the paths you own. Document in `docs/ops-tabs.md`. Where a behaviour and a contract disagree, stop and report.

## Ownership
- **OWN:** `factory/ops/collect.py`, `factory/ops/runtime.py` (only the stops part), `factory/qa/` (only the new `promote-notes` command and its helper), `factory/intake/` (only `resolved.json` acceptance), `ops/shell/index.html` (tabs, banner), `tests/test_ops_content.py`, `tests/test_qa_notes.py`, `docs/ops-tabs.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/prds/**`, `docs/requirements/**`, `pyproject.toml`, `factory/ops/events.py`, `factory/ops/bundle.py`, `factory/hitl/`, any file another slice owns
- Do not run git commands that touch the working tree. Use `scripts/bounded-pytest.sh`. Never read, list, search or run anything under `evals/`.

## Out of scope
Deploying; per-product wiring (SFN-05); the live rehearsal (SFN-04).
