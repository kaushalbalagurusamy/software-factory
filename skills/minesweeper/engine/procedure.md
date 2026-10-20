# Procedure: the six sweep steps and the discovery loop

The engine knows the steps and the schemas, never a domain. Each step writes a file that validates
against `engine/schemas/`. Paths below are relative to the skill root (ROOT) unless they name the
project. A run directory is `<project>/docs/minesweep/<YYYY-MM-DD>-<brief-slug>/` in full mode, or
the directory evaluate.py names in eval mode.

## 0. Plan

```
python3 ROOT/tools/plan.py <brief> --json > RUN/plan.json
python3 ROOT/tools/refresh.py            # full mode only: re-fetch stale sources first
```

`plan.py` decides which lenses apply (deterministic `applies_when`), groups them for sweep agents,
lists each lens's required statements, and says whether the run is calibrated. Copy the brief into
`RUN/brief.md` so the register's sha256 refers to an immutable copy.

## 1. Extract claims → `RUN/claims.json` (schema claims.v1)

Role: extractor (`engine/prompts/extractor.md`). Zero trust: every sentence of the brief and every
rubric item becomes at least one claim. Kinds:

| Kind | What becomes a claim |
|---|---|
| requirement | each requirement sentence, including "optional", "nice to have", and rubric prose |
| dependency | each named library, model, API, dataset, service, protocol or standard |
| metric | each target number, SLO, score or threshold, with its unit |
| rubric | each grading item, including what it rewards and what it ignores |
| example | sample data, example payloads, screenshots described in text |
| assumption | what a sentence implies but does not say ("regardless of order" implies a trust model) |
| omission | each required statement of an applied lens that the brief does not make; `locator` is `<lens>.<statement-id>` |

Claim ids are `C-001`… in brief order; omissions come last. Validate:
`python3 ROOT/tools/validate.py claims RUN/claims.json`.

## 2. Sweep by lens group

Role: sweeper (`engine/prompts/sweeper.md`), one agent per group in `plan.json`, on the group's
model. Each reads its lenses' `lens.md` and `traps.yaml` and gives **every** claim a verdict for
**every** lens it holds: `clear` (one-line reason) or `suspect` (trap id or `novel`, cues matched).
Agents may run `tools/search.py --traps` to find catalogue entries by phrasing. Output:
`RUN/sweep-<group>.json`, a list of `{claim_id, lens, verdict, trap_id, cues_matched, reason}`.
A lens with no verdicts is a failed sweep, not a clean one.

Merge suspects into findings `F-001`… (one per claim × trap; the same trap on several claims is one
finding with several claim ids). Status `suspect`.

## 3. Ground

Role: grounder (`engine/prompts/grounder.md`). Route each suspect to the cheapest method that can
settle it and record `route` and `route_reason`:

| Settled by | Route | How |
|---|---|---|
| a primary-source quote | retrieval | `tools/search.py` over the cache; a verified trap's own quotes count |
| arithmetic or registry metadata | check | the trap's `checks`, run via `tools/checks/*.py` |
| one decidable fact about a tool, version, page | grounded-research | invoke the skill; link its `research-notes/` file |
| a synthesis of many sources | deep-research | invoke the skill; link its `research/` file |
| a number nobody has measured | experiment | invoke `experiment-designer`; link the plan, then the results |

Outcomes: `confirmed` (evidence with ref, date, and for quotes the tier and locator), `plausible`
(`would_settle` says what would decide it), `dismissed` (`dismissal_reason`).

Rules:
- A finding on an **unverified** trap may be confirmed only with evidence the grounder fetched or
  computed in this run. The catalogue entry alone never confirms anything.
- A secondary source can make a finding plausible, never confirmed.
- In eval mode only retrieval and check are allowed; anything else stays plausible.

## 4. Skeptic

Role: skeptic (`engine/prompts/skeptic.md`), a fresh context on the skeptic model. It receives
`claims.json` and the confirmed findings with their evidence only, never the sweep reasoning, and
tries to dismiss each one: wrong reading of the brief, quote does not say that, rule does not apply
in this jurisdiction or configuration, a safe reading of the requirement exists. Verdicts:
`upheld`, `downgraded` (to plausible, with why), `dismissed` (with why). Record on the finding.

## 5. Reframe

Role: reframer (`engine/prompts/reframer.md`). For each confirmed or plausible finding:
- **severity**: answer the `policy.yaml` severity questions in order, each yes/no with a one-line
  why, stopping at the first yes. The tier is that question's tier (all no: low). Record every
  answer. `validate.py` recomputes the tier from the answers and fails on a mismatch.
- **underlying_problem**: the problem the brief should have stated, in one or two sentences.
- **disposition**: `comply-safely`, `reframe`, `decline` or `ask-owner` (with `owner_question`).
  Jurisdiction- or contract-dependent answers are `ask-owner`.
- **spec_section**: the section of the technical spec that must answer it (from the trap's
  remediation, or chosen for a novel finding).

Never close a finding as out of scope when its topic is in `policy.yaml never_out_of_scope`; an
omission of such a topic is itself a finding. Any proposed out-of-scope closure needs
`out_of_scope_consequence` written out.

## 6. Register → `RUN/register.json`, `RUN/register.md`, `RUN/problem-definition.md`

- `register.json` (schema register.v1): run metadata (lenses with version and calibrated flag from
  `plan.json`), all findings including dismissed ones, the **quarantine** (poisoned-instruction
  autopsy: every brief line or rubric item that will not be followed as written, with the finding
  ids and what replaces it), and convergence state.
- `python3 ROOT/tools/validate.py register RUN/register.json --write-gates` fills `gates` and
  enforces the policy rules. Fix and re-validate until clean.
- `python3 ROOT/tools/render.py RUN/register.json > RUN/register.md`.
- `problem-definition.md`: the brief's legitimate business objective, the reframed problem, the
  invariants and guardrails the findings imply, open questions (ask-owner and plausible findings),
  and the brief lines kept, conditioned or rejected. Research skills start from this note.

## The discovery loop (full mode)

Steps 1–6 are one pass. In full mode the routed research and experiments feed back:

1. A research report or experiment that surfaces a rule or constraint nobody listed adds claims
   (`origin` = the artifact path, `pass` = next pass).
2. A reframed requirement is new text: extract and sweep it.
3. A finding whose evidence moved is re-grounded.

Each pass sweeps only what changed. Stop when, after a pass:
- every finding is confirmed with evidence, dismissed with a reason, or ask-owner with the question;
- the pass produced no new findings; and
- `problem-definition.md` did not change;

or when a budget in `policy.yaml budget` is hit (`max_passes`, `wall_clock_minutes`,
`max_routed_calls_per_pass`), or a pass repeats the same routed calls with no change in findings
(`halt_on_repeat`). Record `stop_reason`, the passes, and the open finding ids. An `ask-owner`
finding never blocks the loop; it is carried as an open question.

## Hand-offs

- **prd-writer** after convergence: the problem definition, the register, the research and
  experiment artifacts. Every PRD requirement traces to a kept brief line (with its trust status) or
  to the finding that replaced it; every quarantined line is listed. The PRD keeps the business
  objective and states invariants, SLOs, regulatory and terms guardrails, and explicit non-goals.
- **spec-writer** (`/sf` stage 4): each confirmed finding's `spec_section` must be answered.
- **`/sf` ledger**: a `trust` column per row: `trusted`, `conditioned (F-xxx)`, `rejected (F-xxx)`.
- **Gates**: `gates.blocking` (Critical) blocks scheduling of conditioned rows until the owner signs
  off; `gates.needs_disposition` (High without a disposition) must be resolved before scheduling.
- **`/sf` stages 8, 9, 12**: open findings are the review's hunting list; changed or new requirement
  text is re-swept (steps 1–6 on the delta only).
