# Decision trail

Contents: why it exists, the three modes, row fields, gate records, rules, the autonomy log, answering "how did we get here", an example.

## Why it exists

An ADR records what was decided. The decision trail records how: which steps an agent or tool took without a pause, where the process stopped for a human, what that human was shown, and what they said. Someone who disagrees with a decision a year later can then find the step that went wrong, see whether a human had the evidence that mattered, and reopen the decision at the right point.

The trail lives in section 6 of each ADR (section 5 in the built-in fallback template). `GovernanceEngine.generate_adr_draft` seeds it with one `auto` row per One-Way risk, copied from the audit, so the record starts from what the tool found.

## The three modes

| Mode | Meaning | What to record |
|---|---|---|
| `auto` | An agent or tool acted without pausing for a human. | The actor, what it did, and the evidence. For a door classification, also the basis: which risk categories were checked and what they returned. A two-way classification is the call that skips the human, so its reasoning must be on record. |
| `gate` | The process paused for a human and resumed after feedback. | A row in the table plus a gate record (below). |
| `reopen` | An earlier decision was reopened. | The earlier row numbers or ADR id, and the new evidence that triggered it (a failed experiment, a failed verification, a changed requirement). |

## Row fields

| Field | Content |
|---|---|
| `#` | Row number, ascending, never reused. |
| `When (UTC)` | `YYYY-MM-DD HH:MM`. For a gate, the time it paused. |
| `Mode` | `auto`, `gate`, or `reopen`. |
| `Step` | The build-loop step or activity: governance audit, option generation, debate, experiment verdict, and so on. |
| `Actor` | `tool: <name>` for deterministic tools, `agent: <name or model>` for model-driven steps, `human: <name>` for people. The difference matters: a deterministic classification can be re-run, a model's judgment cannot. |
| `What happened` | One or two sentences. For a gate row, end with "See gate record #N". |
| `Evidence` | A link or path: research note, experiment verdict, audit output, commit, or session. |

## Gate records

Each `gate` row has a block under "Gate Records", keyed by its row number:

- **Shown**: what the human was given. Options, evidence, and the recommended default. Without this, an approval cannot be judged.
- **Known gaps**: material uncertainty the agent knew about and the human may not have weighed (an inconclusive experiment, an unvalidated assumption). Write "none known" only when that is true.
- **Feedback (verbatim)**: the human's words, quoted. Do not paraphrase. If part is sensitive, replace it with `[redacted]` and say so.
- **Outcome**: approved as proposed, approved with changes, rejected, or deferred.
- **Effect**: what changed in the decision because of the feedback, in the agent's own words. This is the agent's reading and is labeled as such.
- **Source**: a link to the message or session where the feedback was given, when the environment provides one.

## Rules

1. **Append only.** Never edit or delete an existing row or gate record. Correct a mistake with a new row that cites the old one. Git history is the integrity backstop: a diff that changes an existing row is a defect.
2. **Quote the human, summarize the agent.** Human feedback is verbatim. The agent's reading of it goes in Effect.
3. **Prefer captured facts to recollection.** Copy classifications and risk lists from the tool output. Do not restate them from memory.
4. **Do not reconstruct a trail.** An ADR written before the trail existed has none, and says "no decision trail recorded" if asked. Backfilling from memory would invent provenance.
5. **Record what the human did not see.** Known gaps are part of the record, not an admission to hide.
6. **Keep secrets and personal data out.** Redact them in quotes and evidence links.

## The autonomy log

Autonomous decisions that never reach an ADR (two-way doors) are recorded in `docs/adr/AUTONOMY-LOG.md`, created on the first row:

| When (UTC) | Change | Door | Basis | Decided by | Evidence |
|---|---|---|---|---|---|
| 2026-10-06 14:02 | Refactored helper in `src/util/dates.py` | two-way | governance audit: LOCAL_REFACTOR only, no concurrency, purity, or contract delta | agent, after `sf audit` | commit `abc1234` |

One row per autonomous governance classification that proceeded without a gate. The basis is copied from the audit output. Nothing writes this file automatically yet, so rows are added by the agent that made the call, in the same change.

## Answering "how did we get here?"

When asked how a decision was made, who approved it, or where a human weighed in:

1. Read the ADR's trail and any autonomy-log rows it cites.
2. Separate `auto` rows from `gate` rows and say which steps a human saw.
3. Quote the human feedback and the Effect line.
4. Name what the trail does not cover: missing rows, an ADR with no trail, or known gaps at a gate.

## Example (illustrative)

Adapted from the pgvector ADR example in `SKILL.md`. The times, names, numbers, and quote are invented.

| # | When (UTC) | Mode | Step | Actor | What happened | Evidence |
|---|---|---|---|---|---|---|
| 1 | 2026-10-06 14:02 | auto | governance audit | tool: sf audit | Classified ONE_WAY: SCHEMA_MUTATION on global. New embedding column and index. | sf audit output |
| 2 | 2026-10-06 14:09 | auto | option generation | agent: opus | Drafted 3 options (pgvector, dedicated vector store, Elasticsearch). Recommended pgvector. | research/vector-storage.md |
| 3 | 2026-10-06 14:15 | gate | debate | human: A. Rivera | Paused for debate on storage. Outcome: approved with changes. See gate record #3. | session link |
| 4 | 2026-10-20 09:30 | reopen | verification | agent: opus | Rows 1 to 3 reopened: measured p95 71 ms against a 50 ms target at 100k documents. | experiment verdict 2026-10-20 |

**#3** · Paused 2026-10-06 14:11 · Resumed 2026-10-06 14:15
* **Shown:** Three options with trade-offs, pgvector recommended, two cited benchmarks.
* **Known gaps:** No measurement on our corpus. The recall claim rests on a vendor benchmark.
* **Feedback (verbatim):** "pgvector is fine, but we cannot run a second datastore, so cap the index memory and add a latency test before we ship."
* **Outcome:** approved with changes
* **Effect:** Added a memory cap and a p95 latency gate to the consequences. Option 2 was ruled out on operational grounds.
* **Source:** session link
