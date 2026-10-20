---
name: spec-recomposition
description: >-
  Use whenever an external spec arrives and has to become a working requirements list before any
  research, design or build starts: a partner or client project brief, an assignment PDF, a PRD
  someone else wrote, an RFP, a portal page, screenshots of requirements, or a revised version of
  a brief already in hand. Transcribes the source verbatim, extracts every line of prose as a
  requirement (narrative, context, out-of-scope lists, grading criteria and "optional" items
  included, nothing summarised away), categorises each row (Hard, Given, Constraint, Quality,
  Deliverable, Optional, Context and others), links the dependencies between rows, and emits a
  dependency-ordered build list plus the open questions that seed the build loop's research
  stage. A script verifies that no line was missed. Triggers: "extract the requirements", "line
  by line", "every line is a requirement", "requirements register", "turn this brief into
  requirements", "what does this spec actually ask for", "intake this spec", "new brief dropped",
  "the brief was updated". Not for inventing requirements from a vague idea (spec-writer) or for
  writing contracts and axioms for a scoped change (axiomatic-spec).
---

# Spec recomposition

## Why this exists

An external spec is written to persuade and explain, not to be built from. Its obligations hide in
narrative paragraphs ("we care far more about the integrity of the core flow"), in lists of things
that are out of scope, in how the work will be judged, and in lines labelled optional. Requirement
extraction that keeps only the numbered list loses exactly those lines, and they are the ones that
decide whether the result is accepted. The failure is always the same: prose gets condensed into a
paraphrase, and the paraphrase quietly drops an obligation.

The standard here is therefore strict: **every line of prose in the source is a requirement**, with
its own row and a pointer back to its line. Rows are then categorised and linked by dependency, so
the register can be decomposed into an order of work instead of read as a flat list.

The register is also the **requirements ledger** that the build loop uses to decide when a run is
finished. Each row starts `unserved` and is advanced only with an artifact named as evidence.

## Outputs

All paths are in the project repository unless the project says otherwise.

| File | Contents |
|---|---|
| `docs/BRIEF.md` | The source, transcribed verbatim. Frozen: line numbers must not move once rows cite them. |
| `docs/REQUIREMENTS.md` | The register: type and status definitions, the row table, open questions, and the generated build order. Start from `reference/register-template.md`. |

## Procedure

Create a todo for each step.

### 1. Transcribe the source verbatim

Copy the source into `docs/BRIEF.md` word for word, including headers, metadata, lists, table
cells, "no attachments" notices and any duplicated text across pages or attachments. Do not fix
grammar, capitalisation or wording. Only the provenance header (title, one paragraph naming the
source, version and date, and a transcription note when text extraction re-ordered anything) may
be written fresh. If the source is images or a PDF, say so in the transcription note and keep the
original next to the brief when the project allows it.

If a `BRIEF.md` already exists and the source changed, add the new version as a new file or a
clearly marked revision, then re-run steps 2 to 7 for the changed lines. Never edit cited lines in
place.

### 2. Get the line worklist

Copy the template, declare provenance lines that carry no requirement with
`<!-- skip-lines: 1-3 -->`, and run the checker against an empty table:

```bash
python3 ~/.claude/skills/spec-recomposition/scripts/register.py check docs/BRIEF.md docs/REQUIREMENTS.md
```

Every `brief line N has no row` message is a line to process. Headings, blank lines and horizontal
rules are skipped automatically; headings supply the Section column. Skip only genuine provenance
lines, never content you find unimportant. Metadata lines such as company, version or date become
Context rows.

### 3. Extract every line

Work through the worklist in order:

- **At least one row per sentence.** A source line holding three sentences gets three rows. Split a
  sentence further when it lists separate obligations ("select one or more supplements, set the
  patient-facing price"). Split rows share the line number with a letter suffix: `21a`, `21b`.
- **Requirement text is verbatim** from the source, with list and bold markers removed. Quote the
  part that belongs to the row. Never paraphrase in this column; interpretation goes in Notes.
- **Split enumerations that could be cited on their own.** "Real payment processing, real auth, real
  shipping" is three rows, so one exclusion can be referenced without the others. The same applies
  to lists of stubs, judging criteria and deliverables.
- **Lead-in lines** ("The current flow looks like this:", "Include the following:") are Context rows.
  The rows they introduce do not depend on them.
- **Repeated content gets its own row** each time it appears, with the earlier row listed in
  Depends on and "restates R-0NN" in Notes. A restatement can differ subtly, and that difference is
  what the row exists to catch.
- **Err toward over-capture.** If unsure whether a clause carries an obligation, give it a row.

### 4. Categorise each row

Apply the first type that fits, in this order:

| # | Type | Use when the line... | What the row obliges |
|---|---|---|---|
| 1 | Optional | says optional, bonus, "unless you want to", "is fine", "nice to have" | Decide in or out and record the decision; built only if chosen. |
| 2 | Constraint | excludes, prohibits or bounds: out of scope, "ignore", "not graded on", "don't" | The solution stays inside the boundary; docs do not claim the excluded thing. |
| 3 | Given | tells the team what to assume is true about the world: "assume we hold inventory", "US-only" | The design may rely on it; the assumption is written down where it is used. |
| 4 | Deliverable | names an artifact to hand over: repo, deployed URL, video, documentation, log | The artifact exists, is linked, and contains what the line lists. |
| 5 | Test | requires a test or test suite to exist | The test exists and passes. |
| 6 | Research | asks for investigation, justification or alternatives | Findings are documented with sources. |
| 7 | Hard | states behaviour, data, an invariant, a measurable target or a stack rule the system must satisfy | Built and demonstrated; the evidence names the code and the check. |
| 8 | Behaviour | describes user-visible flow, copy or UI that is not core logic | Visible in the running product. |
| 9 | Quality | describes how the work is judged without a pass/fail threshold: "sensible data model", "explained crisply" | A named artifact demonstrates it (decision record, doc section, demo moment). |
| 10 | Context | is narrative, motivation, definition, example or metadata | The product and docs stay consistent with it, and the design is informed by it. Notes say which design choice it bears on. |

A measurable target ("settle within 10 minutes") is Hard, not Quality. "Build the smallest thing"
bounds scope, so it is Constraint. "Build a working slice" names the thing handed over, so it is a
Deliverable. "Make X measurable" is Hard.
An instruction to the team about how to work ("make assumptions and document why") is Deliverable
or Quality depending on whether it names an artifact. When a line fits two types, split it into
two rows rather than picking one.

### 5. Link dependencies

For each row, list in **Depends on** the IDs that must be decided, built or true before this row can
be started or verified. Only direct, load-bearing edges:

- Hard rows depend on the Givens and Constraints that shape them and on the Hard rows whose data or
  behaviour they consume (paying for an order depends on assembling one).
- Deliverables and Quality rows depend on the rows they document or demonstrate.
- Context rows usually depend on nothing. Do not make every row depend on a Context row; link a
  Context row only when the requirement cannot be interpreted without it.
- A restatement depends on the row it restates.
- Arithmetic rows depend on their inputs. A fee depends on the price it is taken from; a split
  depends on cost, price and fee. Routing money depends on the amount being computed, not the
  reverse.
- A whole-system Deliverable (the working slice, the deployed app) depends on **every** core Hard
  row, including the last ones such as auditability and dashboards. Demo, URL and documentation rows
  depend on it, so they land in the last tiers. Retrospective deliverables (decisions made, what was
  cut) depend on it too, because they cannot be written before the build.
- After generating the order, read it top to bottom as a build plan. If something would be built
  before its inputs exist (paying before prices can be set), an edge is missing.

Then generate the build order and validate the whole register:

```bash
python3 ~/.claude/skills/spec-recomposition/scripts/register.py order docs/BRIEF.md docs/REQUIREMENTS.md --write
python3 ~/.claude/skills/spec-recomposition/scripts/register.py check docs/BRIEF.md docs/REQUIREMENTS.md
```

`check` must print `OK`. It fails on any uncovered line, unknown type, duplicate ID, dangling
dependency or cycle. A cycle means two rows each need the other; split one of them or record which
one is decided first.

### 6. Record open questions

While extracting, every ambiguity, contradiction, undefined term or unstated number goes in the
**Open questions** table: the question, the rows it affects, and why it matters. Do not answer
them in the register. They are the seed list for the build loop's research stage, and some will
become decision records. Typical finds: a fee whose base is not stated, two lines that disagree,
"or" choices ("price (or margin)"), deliverables listed twice under different names, and stub
boundaries the spec leaves open.

### 7. Independent audit

Hand `docs/BRIEF.md` and `docs/REQUIREMENTS.md` to a separate agent that did not write the register,
with no other context. Ask it to report, with line numbers:

1. Sentences or obligations with no row, or rows whose text is paraphrased rather than quoted.
2. Rows whose type contradicts the decision table in step 4.
3. Missing or spurious dependency edges.
4. Ambiguities absent from Open questions.

Fix what it finds and re-run `check`. The script proves line coverage. Only the audit catches a
line that has a row but lost part of its meaning.

## Hand-off

Report the counts by type, the number of tiers, the open questions, and any Optional rows that need
an in-or-out decision. The next step is the build loop's research stage, seeded from tier 0 and
tier 1 and from the open questions.

## What not to do

- Do not summarise a paragraph into one row. If a paragraph has five sentences, it gets five rows
  or more.
- Do not drop Context rows because they "carry no obligation". They decide how ambiguous Hard rows
  are read, and they are what a reviewer checks the narrative against.
- Do not state facts in Notes that are not in the brief without saying where they come from (a
  company profile, a team decision). Unsourced Notes read as requirements.
- Do not resolve ambiguities inside the Requirement column. The register records what the source
  says; decisions live in decision records and are linked from Notes and Evidence.
- Do not mark a row satisfied without naming the artifact. A status without evidence is a claim.
