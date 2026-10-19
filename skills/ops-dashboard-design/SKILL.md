---
name: ops-dashboard-design
description: >-
  Use at the docs-update stage of every slice (and when naming a slice's MECE surface): add that slice's evals, error traces, LLM traces, logs and golden-gate status to the project's ops dashboard, so the dashboard grows with the feature. Also fixes the Langfuse span plan before the first model call. Triggers: "ops dashboard", "observability", "wire in Langfuse", "what goes on the dashboard", "golden gate eval set", "show traces in the demo", "update the dashboard", or any slice that finishes or introduces a model call. Distilled from the Clinical Co-Pilot and ai-red-team dashboards. Not for product UI, and not for choosing eval cases (eval-designer).
  Also use whenever the owner says the dashboard is thin or asks for error logs, latency, cost, key metrics, telemetry or log parsing on it, and whenever a project adds a runtime model call (then the Langfuse plan and the LLM telemetry rules below apply).
---

# Ops dashboard design

The ops dashboard answers one question for a reviewer who was not there: does this system work, and what proves it. Every slice updates it, not only slices that call a model. The slice's tracer-bullet spec has a MECE test and eval surface; that surface is also the list of what the dashboard must show for the slice: its evals and golden-gate cases, its error conditions and their traces, its logs, and its LLM traces when a model is called. Name that list in the spec, then add the rows in the docs-update stage (sf stage 10, `doc-sync`). A dashboard built later is built from whatever was logged, and what was not logged is gone.

## Core panels (common to the Gauntlet projects)

1. **Eval gate.** Pass and fail by suite and category, the golden-gate verdict, and each failed case with its reason code. Name the **golden gate set** explicitly: which cases, why each is there, the floor for each category, and what the gate blocks. "A suite that blocks nothing is a dashboard, not a gate."
2. **Third state.** Cases that passed for the wrong reason, and what was excluded from the pooled number, beside the verdict.
3. **Cost.** Every metered dependency gets a row: model spend (from the provider's own accounting), chain fees, RPC and data-API requests against their quota, hosting, subscriptions. Show cost per unit of work (per request, per market, per settlement) next to the total. Quota rows show used, limit and headroom, because a hit limit is an outage (an RPC daily limit stopped every service in one Gauntlet project). Unmeasured items (hosting, subscriptions) show as unknown, never $0. Never label model spend "total cost".
4. **Latency and volume.** Requests, errors, p50, p95 and p99 per operation (not one pooled number), with the sample size beside each and the target it is judged against. Include the dependency calls (RPC, oracle, data API, model) as operations of their own, and the rate of throttled or refused calls.
5. **Traces.** One link per run, with a check that the trace was actually ingested. Spans per stage of the pipeline.
6. **Test run record.** Commit SHA, command, timestamp, a stale label past 24 h.
7. **Outcomes.** Decision outcomes (answered, refused, degraded, error) and failures grouped by category, from stored records. If nothing stores failures, say so on the page; an alert that goes only to a webhook is not a record.
8. **Drift.** Requirements ledger status against the verbatim source: satisfied, partial, blocked, unserved.
9. **Platform inventory.** Tests, ADRs, specs, experiments, CI jobs.
10. **Logs and errors.** The errors the running system generated, grouped and counted, from its own logs (see "Logs and errors panel" below). Not the test log.
11. **Key metrics.** The few figures that say whether the platform is doing its job, each with its target from the requirements, the measured value, the sample size and window, and a verdict (see "Key metrics panel" below).

## Rules that held in every project

- Read-only. No write path from the dashboard.
- Every figure is `{measured: true, value}` or `{measured: false, reason}`. A missing value never renders as 0.
- Data comes from committed JSON, request-time reads of the repo, or the trace store. No prompts, completions or personal data on the page.
- The ops surface stays separate from the product or operator surface.
- State "not live" for a metric nothing measures yet, with the reason and what would measure it.
- A panel that only shows tests and gates is a test report. Before calling a dashboard done, check that it answers: what is failing now, how fast and how much does it cost, and is the platform meeting its targets.
- Instrument first. If a service emits no structured logs, request counters or timings, adding them is part of the slice; a dashboard cannot show what nothing records.

## Langfuse plan (write it with the spec)

- One trace per request or per unit of work; one span per pipeline stage; the model call as a generation with tokens and `usage.cost` from the provider.
- Names, metadata keys and the cache-hit flag are fixed in the spec, so the dashboard queries stable fields.
- Wire it before the first model call lands. Check that a trace appears with a real call before the slice counts as done.
- Credentials come from the environment by name only; never print them.

## Logs and errors panel

The owner needs to see what is going wrong in the running system without opening a log console.

- **Source.** The services' own structured logs (one JSON object per line: timestamp, level, event name, service, fields). Pull them where the credentials already live (the platform CLI or API on the operator's machine, or the log drain) and write a parsed summary into the repository's committed data; the dashboard must not hold a platform token. Say where and when the summary was taken ("as of"), and mark it stale past a day.
- **Parser.** A pure function from log lines to groups, tested with real lines. Group by service, event name and a normalized message (numbers, addresses, ids and URLs replaced by placeholders), so 2,383 repeats of one failure are one row with a count. Each group keeps count, first seen, last seen, severity, one redacted sample and the first line number. Unparseable lines are counted, never dropped silently.
- **Redaction before commit.** Remove API keys, bearer tokens, URLs with credentials, private keys and personal data from every sample; a test feeds lines containing each and asserts none survive. A secret in a committed log summary is a leak. Lessons from a real build (each was a defect that review or a test caught, in this order):
  - Redact every text that reaches the summary, not only the sample: the group template, the event name and field values are text too. Normalising (replacing digits and long runs) is not redacting; it leaves the letters of a short key.
  - Redact before any truncation, never after: a secret cut by a length limit leaves a piece shorter than the redaction thresholds.
  - Values nested inside structured fields (an error object carrying `config.headers.Authorization`) need the secret-name rule applied at every depth, and header lines, JSON string values, URL fragments, URL-encoded forms and JWTs need their own rules; a list of token shapes alone misses them.
  - Length thresholds leave secrets shorter than the threshold unredacted when nothing names them. Therefore also scan the generated file against the ACTUAL secret values in the environment (every 6-character piece of each key and each URL path segment, in memory, never printed) before committing it. This is the check that does not depend on guessing token shapes.
  - Over-redaction loses diagnostics (a rule that eats the rest of a line removed `limit=5` and an auth failure's reason). Test that ordinary error lines survive unchanged.
  - Test `redact` with long unbroken input under a time budget and with a scaling check (double the size, expect under 4x the time); a pattern that scans to the end of a run from every start position is quadratic and will stall the command on one large row.
  - Group by what a human would call the same failure: normalise UUIDs and short hex tokens, join the rows of a multi-line printed object into the head row, and count what was cut (`groupsDropped`, `eventsDropped`) so a cap can never turn "errors exist" into "no errors".
- **Page.** Errors by service and event over the window, the top groups with count and last seen, a "new since yesterday" mark, the rate per hour, and the alerts the system fired. Link each group to the code that emits it and to the runbook line if one exists.
- **When nothing is collected.** Render "not live: <reason>", not an empty table that reads as "no errors". Zero errors is a measurement only when the window and the number of lines read are shown beside it.

## Key metrics panel

Take the metrics from the source requirements (impact metrics, success criteria, performance targets), not from what is easy to count. For each: name, target, measured value, sample size and window, verdict (met, missed, not enough data), and the source of the measurement. A metric measured once is reported as one sample, not as a rate. Typical shapes: correctness (share of outcomes that match an independent reference), liveness (jobs completed within their deadline), latency against a target, availability, cost per unit against a budget. A metric nothing measures yet is "not live" with the work that would measure it.

## Telemetry when the system calls a model

Everything above applies, and the model calls add:

- **Traces.** One trace per unit of work, one span per stage, the model call as a generation with input and output token counts, latency, model name and `usage.cost` from the provider (never from a list price). Fix names and metadata keys in the spec so the dashboard queries stable fields, and wire tracing before the first call lands.
- **Metrics from traces.** Cost and tokens per request and per day, latency p50, p95 and p99 per stage and for the model call alone, cache-hit rate, retry and timeout rate, refusal and fallback rate, error rate by class (provider error, rate limit, timeout, malformed output, guardrail block).
- **Log parsing.** The application's log lines about model errors go through the same parser and appear in the Logs and errors panel beside the trace links; a trace and a log line for the same failure should share an id.
- **Ingestion check.** A scheduled or on-demand check that a recent real call produced a trace, shown on the page. "Tracing configured" is not "traces arriving".
- **Privacy.** Prompts, completions and personal data stay in the trace store; the page shows counts, ids and links only.
- **No model call.** State "not applicable: the product calls no model" on the cost and traces rows, and still build the logs, latency, cost and key-metrics panels in full. Do not leave the rest blank because the model rows are not applicable.

## Live development dashboard: tabs, snapshots and the two data classes

The dashboard is also the project's open development brain: it shows how the product was built, kept live with the repository. Implemented in `factory/ops/` and `ops/shell/index.html`.

**Tab set.** Overview; Ops; Architecture (the `mermaid-nesting-dolls` viewer loading a model blob through `viewer.html?model=<url>`); Research (`research/*.md`); Experiments (`experiments/*/results.json`); ADRs (`docs/adr/`); PRD journeys (every slice's UX stories on one page, from `docs/slices/*/proposal.md`); Langfuse; Evals and bug log; Dev journey (`docs/slices/*/tasks.md` checkbox counts, `verification.json` verified counts, `amendments.md`, and `ops/events.jsonl` stage events); Git history with the commit selector.

**Historical versus runtime (structural, not cosmetic).**
- Historical development artifacts (ADRs, research, experiments, architecture model, PRD journeys, evals, bug log, dev journey, git history) are read from the git object database at a sha, written as content-addressed blobs under `ops/blobs/`, and referenced by `ops/snapshots/<sha>/manifest.json`. `python -m factory.ops bundle` can rebuild any past commit. The commit selector swaps every historical tab to that manifest and shows "Snapshot at <sha> (<date>)".
- Runtime telemetry (app health, deployed commit, CI status, last test summary, Langfuse) is "as of now": `python -m factory.ops runtime` writes `ops/runtime.json` from `ops/config.json`. A manifest never references it, and the selector never changes it. The Ops and Langfuse tabs carry "as of <time>, not tied to a commit".
- A missing historical artifact is `{available:false, reason}` for its tab, never an empty success (for example "no slices at this commit").

**Measured or not measured.** Every runtime figure is `{measured:true, value, source, as_of, label}` or `{measured:false, reason}`. The label is `live` (fetched this run), `static` (from a file or config) or `unavailable`. Absent config gives `measured:false` with the reason. The Langfuse tab says "not applicable" unless the config declares `langfuse.llm_features`. `ops/config.json` keys: `health_url`, `deployed_version` and `expected_version` (`{url|file, json_path}`), `ci` (`{repo}`; uses `gh run list` when authenticated), `test_summary_file`, `langfuse` (`{llm_features, host}`). No secrets in config or output; URLs are reported as scheme and host only.

**Stage-update rule.** At every `/sf` stage boundary call `scripts/ops-stage-event.sh <stage> <slice> <verdict> [note]`; it appends one JSON line `{at, stage, slice, sha, verdict, note}` to `ops/events.jsonl` (append-only, never rewritten), so the Dev journey updates at each stage, not only at commit time. At stage 11 run `python -m factory.ops bundle` (add `--backfill N` the first time) and commit `ops/index.json`, `ops/snapshots/` and `ops/blobs/` if small. Serve locally with `python -m factory.ops serve --port N --refresh-seconds S` (binds 127.0.0.1, GET only, no command endpoints).

## Output

In the spec: the list of emitted evals, error traces, logs and spans for the slice. In the docs-update pass: the new dashboard rows, each measured or marked not live. The full set covers: panel list and each panel's data source; the golden gate set and floors; the span and metadata schema; and the check that proves traces arrive. Then tests for the dashboard's data builder (absence stays absence).

Sources: Clinical Co-Pilot `ai-sidecar/ops-dashboard/` and `observability/`; `ai-red-team/dashboard-ops/` and `KEY_METRICS.md`; lectures `2026-09-16-evaluating-agents-with-aaron.md`, `2026-09-15-defining-metrics-with-byron.md`.
