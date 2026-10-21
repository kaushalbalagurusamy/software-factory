# SFN-02: Roles match the owner's flow, and the installer proves it

| | |
|---|---|
| **Delivers** | Owner clauses R5, R7, R8, R9, R9b in `docs/requirements/sf-owner-flow-clauses.tsv` |
| **Depends on** | none (extends `factory/agents`, `factory/install`, `skills/`) |
| **Implementer model** | Sonnet |
| **Source of truth** | `docs/requirements/sf-owner-flow.md`, verbatim |

## Purpose
The owner's flow has "qa agents that supervise and reinitiate when tests fail" and "mechanistic code review agents that use the oh my mermaid dolls and ponytail", equipped "with the minesweeper skillset", who update docs and prevent drift "prior to approving a completion fully". Today the roles have no QA supervisor, the reviewer carries none of those skills, four role files name Opus, one names a skill that is not installed, and nothing checks any of it.

## UX story (first)
As the owner running `sf install doctor --project DIR`, I see one line per role saying which skills it carries and whether each resolves, and the command fails if any role would run on a model other than Sonnet or names a skill that does not exist.

## Required behaviour
- **A-01 all roles Sonnet.** Every `factory/agents/roles/*.yaml` declares `model: sonnet`. The loader rejects any other model unless the profile's `allow_models` list names it; generated agent files then carry that model. Default profile has no `allow_models`.
- **A-02 qa role.** New `factory/agents/roles/qa.yaml`, id `qa`: description a QA supervisor that runs the protected suites, writes behavioural feedback in criterion terms, records attempts and proposes regression cases, never edits application code and never writes test source; tools Read, Glob, Grep, Write, Edit, Bash; writes limited to QA notes and attempt records (a new writes class, with the path set `qa_paths` documented in `docs/hooks/roles.md`); skills `qa-supervisor`, `superpowers:verification-before-completion`; hooks `path_guard`, `secrets_guard`, `bash_guard`, `subagent_stop`; `blind: false`; `spawns: []`.
- **A-03 graph.** The default graph gains a `qa` stage between `implement` and `test`'s successor so the order is implement, qa, review, with the loops `[qa, implement]` and `[review, implement]` and the existing `test` stage retained as the runner invoked by qa. Existing graph tests that assert the earlier seven-role shape are NOT edited: if one conflicts, stop and report it as a clarification request instead of changing the assertion. The `small` subset gains `qa`.
- **A-04 reviewer skills.** `review.yaml` skills are `implementation-review`, `code-review:code-review`, `mermaid-nesting-dolls`, `minesweeper`, `doc-sync`. `skills/implementation-review/` gains `ponytail-rubric.md` (the Ponytail review questions as plain text: does it need to exist, is it already in the codebase, is there a stdlib or installed-dependency way, is any code unreachable or speculative, is every new non-trivial branch covered) and the skill text tells the reviewer to apply it. The reviewer's text states that approval requires `sf slice done` to pass and `doc-sync` to report no stale document, and that a finding becomes `sf slice amend --role reviewer` rather than a chat note.
- **A-05 design skill.** `design.yaml` replaces the missing `prd-designer` with `prd-writer`.
- **A-06 skill resolution.** `sf install doctor` gains a per-role check. For each skill a role names it reports PASS when the skill resolves in the repo `skills/`, the user skills directory, or an installed plugin (`~/.claude/plugins/installed_plugins.json` plus its cache; a name of the form `plugin:skill`), or is in the documented built-in list (`claude-api`); otherwise FAIL naming the role and skill. A role file naming a non-Sonnet model, when `allow_models` does not allow it, is a FAIL.
- **A-07 external skills pinned.** `docs/external-skills.json` lists the skills the flow depends on that live outside the repo (`minesweeper`, `spec-recomposition`, `biz-decomposer`, `grounded-research`, `deep-research`, `experiment-designer`, `one-way-door`, `progress-briefing`, `away-mode`, `good-night`) with the SHA-256 of each directory's `SKILL.md`. `sf install doctor` compares: missing is FAIL; changed is WARN named `changed since pinned` (never silently PASS). `sf install pin-external` rewrites the file from the current installed copies, prints the diff, and requires `--yes`; without it exits 2.
- **A-08 idempotent install.** `sf install install --project DIR` generates eight agent files, updates the manifest, and a second run reports `unchanged`. Uninstall removes the eight.
- **A-09 nothing existing breaks.** The golden gate and all existing unit and eval suites keep passing without edits to their assertions, except tests that pin the number of roles or the Opus declaration, which you must list in your report and NOT edit.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write unit tests under the paths you own. Where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/agents/roles/*.yaml`, `factory/agents/default_graph.yaml`, `factory/agents/roles.py`, `factory/agents/generate.py`, `factory/agents/profile.py`, `factory/install/doctor.py`, `factory/install/core.py`, `docs/external-skills.json`, `docs/hooks/roles.md`, `skills/implementation-review/**`, `tests/agents/test_native_roles.py`, `tests/test_install_native.py`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/prds/**`, `docs/requirements/**`, `pyproject.toml`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran. Use `scripts/bounded-pytest.sh`.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Changing any hook's logic; per-product rollout; adding the `ponytail` plugin to a subagent's skills (the rubric file stands in until it is tested).
