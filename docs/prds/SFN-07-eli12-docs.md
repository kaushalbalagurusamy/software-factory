# SFN-07: ELI12 documentation that cannot go stale or terse

| | |
|---|---|
| **Delivers** | Owner follow-up 2026-10-20: "both sf and lsf need ELI12 documentation skills to prevent technically terse, illegible docs (X object / function expects ABC and outputs DEF, Y depends on it, Z it depends on)" |
| **Depends on** | none |
| **Implementer model** | Sonnet |

## Purpose
Docs written for the author are unreadable to the next person. Define a fixed plain format, compute the parts that must not be guessed (who uses it, what it uses), and fail the gate when an entry is missing, stale or too dense to read.

## UX story (first)
As the owner reading the docs before a meeting, I open any module's page and for each function I read one plain sentence, what goes in, what comes out, who calls it and what it calls, without opening the code.

## Required behaviour
Implemented as a stdlib-only Python script (3.9 compatible, no third-party imports, no OS-specific calls) at `skills/eli12-docs/scripts/eli12.py`, with `skills/eli12-docs/SKILL.md` (frontmatter, when to use, the format, the writing rules, how it plugs into sf stage 10 and lsf).

- **Q-01 format.** One file per Python module at `docs/eli12/<dotted.module.path>.md`. First line `# <module path>`; second paragraph one sentence "what this file is for" a 12-year-old can follow. Then for each public class or function (name not starting with `_`; methods as `Class.method`) a section `## <name>` with exactly these labelled lines in this order: `**What it does:**` one sentence; `**Expects:**` each parameter as `name (type): meaning`, or `nothing`; `**Gives back:**` `type: meaning` or `nothing`; `**Used by:**` list; `**Depends on:**` list; optional `**Watch out:**`. Each section carries a hidden line `<!-- sig:<8 hex> -->` holding a hash of the symbol's signature (name, parameters, annotations, return annotation).
- **Q-02 computed lines.** `scaffold FILE...` writes a skeleton from the AST with `Used by` and `Depends on` computed: Depends on = the names of project functions/classes this symbol calls or references that resolve to a project module (as `module.symbol (path:line)`), Used by = project symbols that call it (same form). Calls that cannot be resolved to a project symbol are listed under a separate `(maybe)` suffix, never silently dropped or claimed as certain. Unfilled human text is `TODO`. Scaffold never overwrites human-written lines of an existing entry (it updates only sig, Used by, Depends on and adds missing sections).
- **Q-03 `check [--root DIR] [--paths P...] [--changed GITREF]`.** Exit 0 clean, 1 findings, 2 usage. Findings: a public symbol with no entry; an entry whose symbol no longer exists; sig mismatch (`stale: signature changed`); Used by / Depends on differing from the computed lists (`stale: dependencies changed`); any `TODO` left; a section missing a labelled line or out of order; a `What it does` that is longer than 25 words or has more than one sentence; a line longer than 160 characters; a parameter without `name (type): meaning`; a term from `docs/eli12/jargon.txt` (one per line, default shipped list) used in prose without an entry in `docs/eli12/GLOSSARY.md`. `--changed` limits to modules changed since the ref plus modules whose Used by/Depends on mention them. Output is one finding per line `path:line: code: message`; `--json` available.
- **Q-04 `index`.** Writes `docs/eli12/INDEX.md` listing modules with their one-sentence purpose and a count of documented symbols; deterministic.
- **Q-05 dolls link.** `scaffold` and `index` expose a machine-readable `docs/eli12/index.json` mapping module path to doc path, so the explorer and dashboards can link each file node to its page.
- **Q-06 no invention.** `check` never calls a model; `scaffold` never fabricates meanings (they stay `TODO`). The skill text tells the author to fill every TODO from the code and tests, in words a 12-year-old can follow, with one concrete example value for non-obvious parameters.
- **Q-07 performance and safety.** Parses with `ast`; a file that fails to parse is a finding (`unparseable`), not a skip; reads only files inside `--root` (no symlink escape); ignores `.venv`, `node_modules`, `.git`, `evals/` by default (override with `--include`); handles 2,000 modules within 30 s.
- **Q-08 sf/lsf wiring text.** `skills/doc-sync/SKILL.md` gains a step: run `eli12.py check` and treat findings as stale documents; `skills/implementation-review/SKILL.md` approval condition lists `eli12.py check` clean for changed modules. (Edits limited to those two sections.)

## Acceptance
Graded by hidden evals. Write your own unit tests in `tests/test_eli12.py`. Where a behaviour and a contract disagree, stop and report.

## Ownership
- **OWN:** `skills/eli12-docs/**`, `tests/test_eli12.py`, `skills/doc-sync/SKILL.md` (the new step only), `skills/implementation-review/SKILL.md` (approval condition line only; SFN-02 owns the rest of this file, so edit only the single line and report it)
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/prds/**`, `docs/requirements/**`, `pyproject.toml`, any file another slice owns
- Use `scripts/bounded-pytest.sh`; never read or search `evals/`.
