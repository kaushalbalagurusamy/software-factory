# Independent review of the ADR-0005 test and eval amendments (2026-10-20)

Scope: `git diff 3c01ebb HEAD` over `evals/agents`, `tests/agents` (incl. golden), `tests/test_install.py`, plus `docs/adr/ADR-0005-sonnet-only-roles-and-qa-role.md`. Read-only review; no suite was run (static diff, name and id comparison only). Rule under test: no weakening.

## Verdict
**PASS WITH FINDINGS.** No WEAKER hunk found: no assertion removed, loosened, made conditional, no skip/xfail, no swallowing try/except, no shortened parametrization, no lowered count, no expected value derived from the implementation. Two non-weakening defects need fixing: (1) ADR-0005 documents a test, `TB12-D-034`, that does not exist; (2) the doctor `env` fixture can make role-skill checks pass for the wrong reason (blind spot, not a loosened assertion).

## Counts (hunk classes, approximate by logical edit)
| Class | Count | Examples |
|---|---|---|
| STRICT-EQUAL | 33 | ROLES/ROLE_IDS lists 7 to 8 (tb02, tb03, tb12, tb14, test_roles, test_install); `len == 7/6` to `8/7`; `writes`/`bash` dicts gain `qa`; `Agent(...)` list gains `qa`; design skill `prd-designer` to `prd-writer`; review skills 2 to 5 (exact set and length); small subset gains `qa`; `WRITES` gains `qa_paths`; `ALLOWED_MCP` gains `qa: set()`; golden model opus to sonnet; `PASS skill` count 13 to 15 |
| STRONGER | 11 | `test_graph` default-graph test now pins exact order and exact loop set; `test_roles` sonnet-for-all plus three rejection cases; install `test_every_shipped_role_declares_sonnet` replaces the exact-4-opus pin by all-8-sonnet equality; tb02 D-038..D-042 (new); install tests for rejection, role-skill and external-pin doctor lines (new); `test_skills_exact` gains a `qa` row |
| WEAKER | 0 | see "Near misses" |
| UNRELATED | docstring/rename edits plus merged-slice files | docstring-only edits (tb12 G-004, G-006, D-015; tb14); renamed functions keep case ids; `tests/lsf/**`, `tests/test_eli12.py`, `tests/test_editor_links.py` are new files from merged SFN-06/07/08 |

Goldens: 5 files changed (design, orchestrator, review, test, new qa); `audit/implement/research.md` unchanged.

## Golden files (each diff read)
- `design.md`: only `model: sonnet` and `prd-designer` to `prd-writer` (frontmatter and Skills list). Exactly intended (A-05, A-01).
- `orchestrator.md`: model sonnet; "other six" to "other seven" in description and Purpose; `qa` added in `Agent(...)` and in the "Start any agent other than" list, between implement and test. Intended.
- `review.md`: model sonnet; three skills added in the A-04 order (`mermaid-nesting-dolls, minesweeper, doc-sync`); description gains the approval and `sf slice amend --role reviewer` sentence, which matches PRD A-04 wording. Intended.
- `test.md`: only `model: sonnet`. Intended.
- `qa.md` (new): sonnet; tools Read Glob Grep Write Edit Bash; two skills; hooks path_guard, secrets_guard, bash_guard (Bash matcher), subagent_stop; no spawns; writes only `**/qa-notes.md`, `**/qa-feedback/**`, `.sf/qa/**`. Matches PRD A-02 and C-40.2 point by point.
- Caveat (ADR section 5 admits it): goldens are generator output, so they pin current output; checked here against PRD and clarifications with no divergence.

## New tests versus spec
- `TB02-D-038` (qa skills): literal set from PRD A-02 plus length 2. Pins the spec.
- `TB02-D-039` (all roles sonnet): literal "sonnet" checked on the loaded spec and the raw YAML. Pins A-01/C-40.1.
- `TB02-D-040..042` (opus, haiku, fable): literal models; asserts `RoleError` with role `design`, field `model` under default loading, and that the file loads with `allow_models=[model]`. Pins C-40.1. Ids 40+i do not collide with D-037.
- `TB12-D-034`: **does not exist** (finding 1). The behaviour is pinned instead in `tests/agents/test_graph.py::test_default_graph_validates_with_eight_roles` (literal order `orchestrate, research, design, audit, implement, qa, test, review`; loops exactly `{(qa, implement), (review, implement)}`), consistent with C-40.5 and PRD A-03. C-40.5 fixes only "qa between implement and review, test reached from qa"; putting `test` right after `qa` in the literal order is a reasonable reading, not a stated fact.
- `tests/test_install.py` new doctor tests assert literal C-40.4 line formats (`PASS role qa skill qa-supervisor`, `WARN external minesweeper ... changed since pinned` exit 0, `FAIL external good-night` exit 1, `FAIL role audit skill legacy-audit` exit 1). They pin the spec formats, not just mirror code.

## Findings
1. **Incorrect ADR entry (medium).** ADR-0005 section 4 lists "new `test_d034_default_graph_order_and_loops` (TB12-D-034)" in `evals/agents/test_tb12_graph.py`. That file ends at TB12-D-033 and has no D-034; the name appears only in the ADR (commit 0e5d213). The order and loop assertions exist only in `tests/agents/test_graph.py`, so `evals/agents` never pins the default graph order or the qa loops. Fix: add the eval test or correct the ADR.
2. **Doctor fixture can hide a missing real skill (medium, blind spot, not a loosening).** `_stock_role_and_external_skills` creates a stub `SKILL.md` for every role-named skill not in repo `skills/` (the `names.add(sk)` branch) and a stub plugin skill for every `plugin:skill` a role names. So (a) `test_doctor_all_pass` cannot detect a role naming a nonexistent skill (a regression to `prd-designer` would be auto-stubbed and still PASS); (b) the pin file is computed from the stubs, so the pin check is tautological except in the explicit edit/remove tests. Mitigations: roles tests pin exact skill names, the new doctor test asserts specific PASS lines, and `prd-writer`, `qa-supervisor`, `doc-sync`, `mermaid-nesting-dolls`, `implementation-review` resolve for real (symlinks into the repo). Hardening: stock stubs from a fixed literal list so an unknown name fails.
3. **`PASS skill` count 13 to 15 (low, accounted).** Verified: 13 non-underscore repo `skills/*/SKILL.md` at 3c01ebb, 15 at HEAD; stub dirs are not counted. Still a literal equality.
4. **Widened enum sets (low).** `D-023` (`in WRITES`) and `D-034` (`<= ALLOWED_MCP[rid]`) were already membership/subset checks; only the allowed set grew. `TB02-G-003` still pins each role's exact writes class, so `qa_paths` cannot be misassigned.
5. **Deleted test replaced (low, accounted).** `test_roles_really_propose_opus` is gone; successor asserts all eight are sonnet (stronger), and rejection tests cover opus. Allowed by C-40.6.
6. **Minor.** `shutil` imported at module level and again inside the `opus_orchestrator` fixture. `test_disallowed_model_is_rejected_and_nothing_written` checks that "orchestrator" is in stderr but not the model name; adequate for "names the role".

## Near misses checked and cleared
- `opus_orchestrator` monkeypatches `core.load_roles`; `test_doctor_fails_on_non_sonnet_agent_unless_allowed` keeps its assertions unchanged (exit 1 with `FAIL agent orchestrator`, exit 0 with `--allow-model opus`); doctor reads the installed agent file model, so the FAIL is real.
- `test_doctor_json`, `..._without_project...`, `..._trusts_arguments_not_the_manifest`: unchanged assertions; pass only because the env fixture stocks stubs (finding 2).
- No `skip`, `xfail`, `except`, `>=`, `<=` added in the diff.

## Missing cases
Compared test function names and case ids before/after for every test file under `evals/agents` and `tests`: no file deleted; no case id lost. Names removed only by rename (`seven` to `eight`: tb02 G-001, tb03 G-001, tb12 D-015, test_generate entries, test_graph default, test_roles order) and the replaced `test_roles_really_propose_opus`. Parametrize ids unchanged (`test_d009` still six roles). Added: TB02-D-038..042, sonnet-for-all tests (2 files), three non-sonnet rejection params, three install doctor tests, one install rejection test.

## GOLDEN.json
Unchanged since 3c01ebb; 141 entries, 141 unique. Each id resolves to a case in `evals/agents/test_*.py` (via `@case`, `@mark` in tb04, and the PROMOTED parametrization in tb14 for TB14-D-001/002). No renamed function changed its case id.

## Accounted versus unaccounted
Every edit appears in ADR-0005 except: the module-level `import shutil` and the `monkeypatch.setenv("HOME", ...)` line in the shared `env` fixture (harmless; the latter is covered in spirit by the "throwaway HOME" row). Incorrectly listed: TB12-D-034 (finding 1). Files from merged slices (SFN-06/07/08) are out of scope.

## Not checked
No suite was run (instructed), so the ADR's pass figures are unverified here. `evals/native` was not reviewed.
