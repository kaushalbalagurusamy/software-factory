---
name: intake-gate
description: >-
  Use when an external brief, spec or revised brief arrives, before any research, slice or code, and
  again whenever its text changes materially. Runs owner flow steps 1 to 4 as a checked sequence:
  verbatim requirement register, minesweeper sweep plus a core-value and best-practices pass,
  ranked research seeds, experiments between state-of-the-art options. Records each step in the
  repo and blocks slices until the recorded sweep exists and Critical findings are signed off.
  Triggers: "new brief", "intake this spec", "run the sweep", "is the intake done", "can we start
  slicing", "the brief changed".
---

# intake-gate

Owner flow, steps 1 to 4: business requirements, minesweeping for core business value and best practices, multi-agent research seeds on state-of-the-art techniques, experiments between options that research did not settle. The format, rules and limits are in `docs/intake-format.md`. Commands are `python -m factory.intake ...` (exit 0 ok, 1 check failure, 2 usage, 3 gate not met).

What is deterministic and what is not. Only recording and gating are deterministic here: ledger coverage, hashes, register shape, sweep-record existence, dispositions, seeds and experiment-record structure. The sweep, the core-value and best-practices extraction pass, the research and the experiments are procedures for the model (and its subagents) below. The gate proves they were recorded, not that they were done well.

## Procedure

1. **Verbatim register.** Invoke `spec-recomposition` on the source. Save the verbatim text as the source file (for example `docs/requirements/brief.md`; never edited afterwards except by a new owner revision). Build `docs/requirements/ledger.tsv` with one row per non-blank line: `req_id`, `source_ref` `file:line`, `text_sha` (SHA-256 of the stripped line), `category`, `trust` `trusted` for now, empty `finding_ids`/`disposition`, `status` `unserved`. Headings and narrative get category `context`, status `context` and a reason; optional and out-of-scope lines get their own rows. Run `python -m factory.intake check --source SRC --ledger LEDGER` until it passes.
2. **Sweep for traps.** Invoke `minesweeper` in full mode on the source. Its run produces `claims.json` and `register.json`. Do not run its tools against anything but the brief, and do not install anything it checks.
3. **Core value and best practices pass (model procedure, not code).** After the trap sweep, and inside the same minesweeper run so the output lands in the same register: for each advanced subcategory lens that applies to the product (for example networking and `realtime-transport`, `cryptography`, `performance`, `privacy-regulated-data`, `security-ethics`, `distributed-systems`, `databases`, `accessibility`; the lens list is `factory/intake/lenses.txt`), state the best-practice requirements a competent practitioner would expect and the brief omits. Each becomes a claim of kind `omission` whose locator is `<lens>.<statement>`, and, where the omission is itself a risk, a finding. Also state the product's core business value in one paragraph and check each kept requirement against it. Never close an omission on a topic the minesweeper policy lists as never out of scope.
4. **Record the sweep.** `python -m factory.intake record-sweep --register REGISTER.json --claims CLAIMS.json --ledger LEDGER --source SRC`. This validates the register, writes `docs/requirements/sweeps/<source-sha>.json`, adds `BP-` rows for omissions and rewrites trust, findings and disposition in the ledger. A register that does not match the source hash is refused.
5. **Dispositions and sign-off.** Every High and Critical finding needs a disposition. A Critical finding blocks the rows it conditions until the owner (or Codex, per the owner's delegation) signs off: `python -m factory.intake signoff --finding F-nnn --by human:REF|codex:REF`. Do not sign off yourself.
6. **Research seeds.** Invoke `biz-decomposer` on the kept requirements and findings. Write its ranked seeds to `research/seeds.tsv` (columns in the format doc; `lens` from the lens list; `depends_on` real). Fan out one `grounded-research` run per narrow factual seed and `deep-research` per broad one. A completed seed's output must have a `Sources` heading and a `could not verify` heading. Run `python -m factory.intake seeds check`.
7. **Experiments.** Where research returns two or more viable options and the choice is open, invoke `experiment-designer`. Write an enumeration file with a date and the candidates in `experiments/<id>/`, preregister the decision rule, run, then write `results.json`. At least two metrics; the winner rests on at least two. One-way doors keep their ADR gate. Run `python -m factory.intake experiments check`.
8. **Gate.** `python -m factory.intake gate --source SRC --ledger LEDGER`. For a slice: add `--slice docs/slices/ID`; also run `python -m factory.slices check DIR --ledger LEDGER`.

## What blocks

- No sweep record for the current source hash (the sweep did not run, or ran on other text).
- A High or Critical finding without a disposition, an unrated open finding, an unconverged sweep.
- A ledger row hand-edited away from what the record implies.
- A slice whose `source_requirement_ids` include a row tied to a Critical finding without sign-off, or an id not in the ledger.
- A source line with no ledger row; a changed source line (text_sha).

## Delta rule

When the source text changes materially (its hash changes), the old record no longer applies. Re-extract the changed ledger rows, run `minesweeper` in delta mode on the new text only, record it with `--claims` so changed lines are on record, then `gate --since <last-good-sha>`. The gate requires a record for the new hash and that every changed or inserted line appears in its claims. Run this at the build loop's stages 9 and 12 and whenever the owner revises the brief.

## Limits

State these plainly when reporting: the ledger and gate cannot judge whether the sweep or the best-practice pass was thorough, whether an enumeration is complete, or whether a decision rule truly pre-dated the data. They make skipping the steps visible and block downstream slices; they do not do the thinking.
