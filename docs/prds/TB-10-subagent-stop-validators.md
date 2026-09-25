# TB-10: Sub-agent stop validators

| | |
|---|---|
| **Delivers** | R-16 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md` |

## Purpose
Reject sub-agent reports that do not have the shape their role owes the orchestrator.

## Required behaviour
1. Runs on SubagentStop; the validator is chosen by `agent_type`. `implement`, `test`, `orchestrator` and unknown types are allowed by this hook.
2. **research:** `last_assistant_message` must contain a heading or bold label `Sources` followed by at least one URL or file path; any sentence containing the word `unverified` must carry the marker `[unverified]`; the message must be at most 8,000 characters. Otherwise block.
3. **audit:** every new row in `<audit_dir>/BUGS-MITIGATIONS.md` (rows are Markdown table lines beginning `|`) must have a severity cell equal to one of `critical`, `high`, `medium`, `low` (case-insensitive) and a citation matching `<path>:<line>`. A missing file is allowed only if the message says `no findings`.
4. **review:** the message must contain `VERDICT: APPROVE` or `VERDICT: REJECT`; a REJECT must contain at least one `<path>:<line>` citation; every line of the form `<id>: right_reason`, `wrong_reason` or `inconclusive` is a grade; at least one grade line is required unless the message contains `no passing cases`; a `wrong_reason` grade with `VERDICT: APPROVE` blocks.
5. **design:** any Markdown file changed under `paths.design_dirs` whose name contains `spec` must contain the headings `Goals`, `Non-goals`, `Axioms`, `Open questions`; every list item under `Axioms` must contain `check:`; if any design document contains `one-way door: yes`, an ADR file under `docs/adr` must exist.
6. Each block reason lists every missing element.
7. Validators read only the message and files under the project root; no network.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/subagent_stop.py`, `tests/hooks/test_subagent_stop.py`, `docs/hooks/subagent_stop.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Judging whether the content is correct.
