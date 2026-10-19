# Intake format (requirement ledger, sweep record, seeds, experiments)

Owner flow steps 1 to 4 (business requirements, minesweeping, research seeds, experiments) as a checked sequence. The checker is `python -m factory.intake`; exit codes: 0 ok, 1 check failure, 2 usage error, 3 gate not met. What is deterministic here is recording and gating. The sweep, the value-extraction pass, the research and the experiments are done by a model following `skills/intake-gate/SKILL.md`; this package proves they were recorded, not that they were done well.

## Requirement ledger: `docs/requirements/ledger.tsv`

Tab-separated, header required. Columns:

| Column | Meaning |
|---|---|
| `req_id` | Unique id. `BP-C-nnn` for a best-practice row the brief omitted (from an omission claim). |
| `source_ref` | `file:line` in the verbatim source (file name must equal the source's), or `omission:<lens>.<statement>`. One row per source line. |
| `text_sha` | SHA-256 of the line after `strip()`. For omission rows, of the claim text. |
| `category` | Free word: `requirement`, `optional`, `out-of-scope`, `context`, `best-practice:<lens>`, ... |
| `trust` | `trusted`, `conditioned(F-nnn)` or `rejected(F-nnn)`. |
| `finding_ids` | `;`-separated non-dismissed finding ids that touch the row. |
| `disposition` | Disposition of the finding that set the trust (`comply-safely`, `reframe`, `decline`, `ask-owner`). |
| `status` | `satisfied`, `partial`, `blocked`, `unserved`, or `context` (only with category `context`). May be followed by `; qualifier`, e.g. `blocked; open critical F-002`. |
| `slice_ids` | `;`-separated slices serving the row. |
| `artifact_or_waits_on` | `satisfied`: `;`-separated repo paths that must exist. `blocked`: what it waits on. `context`: the reason. |

Compatibility with `python -m factory.slices check --ledger`: that checker reads only `req_id`, `trust`, `status` and blocks a slice when trust starts `rejected` or `conditioned` and status contains both "open" and "critical". The extra columns are ignored by it, and the `; open critical F-nnn` qualifier is what keeps its substring rule working. A legacy three-column file still satisfies the slices checker but fails `intake check`, because it cannot show source coverage.

### `check --source SRC --ledger LEDGER [--repo-root DIR]`

Fails (exit 1) when: a non-blank source line has no row (a silent drop; "optional" and "out of scope" lines count, as do headings, which need a `context` row with a reason); a row's `text_sha` differs from its source line (drift, including inserted lines that shift numbers); `trust` or `status` is not in the vocabulary; a `blocked` row names nothing it waits on; a `satisfied` row names no artifact or one that does not exist under `--repo-root`; a `trusted` row carries `open critical` in status; `conditioned(F)`/`rejected(F)` names a finding missing from `finding_ids`; duplicate `req_id`.

## Sweep record: `docs/requirements/sweeps/<source-sha256>.json`

Written only by `record-sweep`. The file name is the SHA-256 of the whole source file, so a record exists for a given text or it does not. Contents: source and register hashes, run date and lenses, convergence, `claim_lines` (source lines covered by claims or quarantine), `omissions` (best-practice rows to add), normalised `findings` (id, lens, status, tier, disposition, lines, omission rows, quarantined), and `signoffs`.

`record-sweep --register REGISTER.json --ledger LEDGER [--source SRC] [--claims CLAIMS.json]`:
- validates the register against vendored copies of minesweeper's `register.v1.json` and `finding.v1.json` (`factory/intake/schemas/`, copied 2026-10-19; no minesweeper code is imported). It does not re-derive severity from answers; run the skill's own `validate.py` for that.
- refuses unless `register.brief.sha256` equals the source's SHA-256, and refuses `mode: eval` registers (calibration runs, not sweeps).
- maps findings to ledger rows through claim locators (`--claims`, or `run.claims_path` beside the register) and quarantine locators. A locator must carry line numbers (`L12-14`, `lines 12-14`, `12`); every integer or integer range in it counts. Omission claims (kind `omission`) become new `BP-<claim id>` rows with category `best-practice:<lens>`.
- rewrites trust, `finding_ids`, `disposition` and status for every row of this source: `rejected(F)` for a quarantined line or a `decline` disposition; `conditioned(F)` for a Critical or High finding; otherwise `trusted` (Medium and Low are listed in `finding_ids` only). A Critical finding without an owner sign-off sets status `blocked; open critical F-nnn` and `artifact_or_waits_on` `owner sign-off F-nnn`. Dismissed findings are ignored.
- refuses to write if the ledger fails `check` before or after.

`signoff --finding F-nnn --by human:REF|codex:REF` appends the sign-off to the record and re-applies it; the row keeps its trust but loses the `open critical` qualifier.

## Gate: `gate [--source SRC] [--ledger LEDGER] [--slice DIR] [--since GITREF]`

Exit 3 listing reasons when: no sweep record exists for the source hash (the sweep did not run or was not recorded); `check` fails; the sweep did not converge; a non-dismissed finding has no severity; a Critical or High finding has no disposition; a Critical or High finding maps to no ledger row; a ledger row's trust or `finding_ids` differ from what the record implies (a hand edit toward `trusted`). Open Critical findings with a disposition but no sign-off do not fail the plain gate (they are the owner's queue) but block slices.

`--slice DIR`: reads `source_requirement_ids` from `DIR/proposal.md`; fails if an id is missing from the ledger or its row is tied to an unsigned Critical.

`--since GITREF` (delta mode): reads the source at that revision. If its hash differs, the gate needs a record for the current hash (a new sweep) and every changed or inserted non-blank line must be in that record's `claim_lines`. Deleted lines need no coverage. Pass `--claims` when recording a delta sweep, or the changed lines cannot be shown as swept.

## Research seeds: `research/seeds.tsv`

Columns `seed_id, topic, lens, question, priority, depends_on, status, output_path`. `priority` P0..P3; `status` open, in-progress, completed, blocked, abandoned; `depends_on` is `;` or `,` separated seed ids. `lens` must appear in the lens list: `--lenses FILE`, else `research/lenses.txt`, else the shipped `factory/intake/lenses.txt` (the 25 lens directory names in the minesweeper skill on 2026-10-19; one per line, `#` comments). `python -m factory.intake seeds check [--file F] [--lenses FILE] [--repo-root DIR]` fails on unknown lens, bad priority/status, duplicate or unknown ids, cycles, a completed seed that depends on an incomplete one, a completed seed without an existing `output_path`, or an output without a heading containing `Sources` and one containing `could not verify`.

## Experiment records: `experiments/<id>/results.json`

```json
{"question": "...",
 "candidates": [{"name": "alpha", "enumeration": "enumeration-2026-10-01.md"}],
 "metrics": [{"name": "latency_ms", "direction": "lower"}, {"name": "cost_usd", "direction": "lower"}],
 "decision_rule_preregistered": "text, or a file name in the same directory",
 "result": {"winner": "alpha", "basis": ["latency_ms", "cost_usd"], "scores": {"alpha": {"latency_ms": 5, "cost_usd": 2}}},
 "as_of": "2026-10-02"}
```
`python -m factory.intake experiments check [ID] [--root experiments]` rejects: candidates that are bare strings or lack an `enumeration` file in the same directory; an enumeration file that is missing, carries no `YYYY-MM-DD`, or does not mention the candidate; fewer than two metrics; no preregistered rule (a rule that looks like a file name must exist); a result whose `basis` has fewer than two metrics (single-metric winner), whose winner is not a candidate, or whose scores miss a metric for a candidate; a missing `as_of`. A result with `winner: null` needs `status: "no-winner"`.

## Limits

The checks cannot tell that a rule was written before the data (preregistration is a claim; git history is the evidence), that an enumeration is complete, that a sweep found everything, or that a best-practice pass was thorough. Locator parsing is by integers, so a locator like `tier 2` is read as line 2. Severity is taken as recorded.
