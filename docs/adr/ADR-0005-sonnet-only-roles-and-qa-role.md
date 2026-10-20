# ADR-0005: Sonnet for every role, a qa role, and the test and eval edits that follow

* **Status:** Accepted (owner-approved plan).
* **Date:** 2026-10-20
* **Related:** `docs/contracts/clarifications.md` C-40 (esp. C-40.6) and C-41, `docs/prds/SFN-02-roles-and-doctor.md`, `docs/hooks/roles.md`, `docs/native-install.md`, ADR-0003 (seven roles, superseded in count), ADR-0004 (untouched)

## 1. Context
The owner's flow (clauses R7, R8, R9 in `docs/requirements/sf-owner-flow-clauses.tsv`) asks for Sonnet 5.5 in every role, QA agents that supervise and reinitiate when tests fail, and mechanistic reviewers carrying the oh-my-mermaid, minesweeper and doc-sync skills. SFN-02 and SFN-02b implemented that in `factory/agents/` and `factory/install/`: eight roles (new `qa`), `model: sonnet` in every role file, installer rejection (exit 1, nothing written) of any other model unless `--allow-model`, the graph order implement, qa, test, review with loops `[qa, implement]` and `[review, implement]`, the `small` subset gaining `qa`, reviewer skills `implementation-review, code-review:code-review, mermaid-nesting-dolls, minesweeper, doc-sync`, design using `prd-writer`, and new doctor checks (`role <id> skill <name>`, `external <name>`).

C-40.6 says the earlier acceptance material that pinned the seven-role, Opus and `prd-designer` shape is superseded and must be updated by the maintainer (not the implementer), each edit listed here. This ADR is that list.

## 2. Decision
Update the existing tests and evals to the new spec. Rules followed for every edit: replace the old pinned value with the exact new value and keep the assertion as strict (equality stays equality); no test is deleted, skipped or loosened; where a test pinned "some roles are Opus" it now pins "every role declares sonnet, other models are rejected unless allowed", with new cases; golden files were regenerated with the generator and reviewed line by line.

## 3. Evidence
* The owner approved the plan (artifact https://claude.ai/artifact/QvGeDjn8CkfoHrbATXFH11) with "Do it" on 2026-10-20; the plan fixes the eight roles, Sonnet-only rule and qa role.
* C-40 and C-41 (binding clarifications) state the names, formats and the supersession in C-40.6.
* After the edits: `evals/agents` 1501 passed, 1 failed (`TB06-D-035`, open on purpose, ADR-0004), 1 skipped; see the report that accompanied this change for the other suites.

## 4. Edits, per file
Counts are tests in the file or family that changed value, not total tests.

### evals/agents/test_tb02_roles.py
| Test | Before | After | Reason |
|---|---|---|---|
| module constant `ROLES` | 7 ids | 8 ids, `qa` between `implement` and `test` | R8, C-40 |
| `WRITES` | 6 classes | adds `qa_paths` | C-40.2 |
| `test_g001_exactly_seven_roles` (TB02-G-001) | renamed `test_g001_exactly_eight_roles`; `len == 7` | `len == 8`, id set equal to the 8 ids | R8. Case id unchanged, so `GOLDEN.json` needs no edit |
| `test_g003_writes_per_role` | 7-entry dict | adds `"qa": "qa_paths"` | C-40.2 |
| `test_g005_orchestrator_and_implement_spawns` | orchestrator spawns the other 6 | the other 7 (qa included) | orchestrator spawns include qa |
| `test_d004_bash_modes` | 7-entry dict | adds `"qa": "full"` | C-41.3 |
| `test_d006` / d001 / d033 / d023 / d032 docstrings and sets | derived from `ROLES` or `WRITES` | same assertions over the new sets; d032 compares the 8 file stems | R8 |
| `SKILLS["design"]` (`test_d009[design]`) | contains `prd-designer` | contains `prd-writer` | A-05 / R9 |
| `SKILLS["review"]` (`test_d009[review]`) | `{implementation-review, code-review:code-review}` | those two plus `mermaid-nesting-dolls, minesweeper, doc-sync` | A-04 / R9 |
| `ALLOWED_MCP` (`test_d034`) | 7 keys | adds `"qa": set()`, no MCP | A-02 |
| new `test_d038_qa_skills` (TB02-D-038) | none | qa skills exactly `qa-supervisor`, `superpowers:verification-before-completion`, no duplicates | A-02 (the existing d009 id range could not take an eighth role without colliding with TB02-D-015) |
| new `test_d039_every_role_file_declares_sonnet` (TB02-D-039) | none (no test in this file pinned opus) | every role file and spec says `sonnet` | C-40.1, R7 |
| new `test_d040_rejects_non_sonnet_model` (TB02-D-040..042, opus, haiku, fable) | none | each model is rejected with role and field `model`, and loads when passed in `allow_models` | C-40.1 |

### evals/agents/test_tb03_generator.py
| Test | Before | After | Reason |
|---|---|---|---|
| `ROLES` | 7 ids | 8 ids | R8 |
| `test_g001_seven_files_deterministic` (TB03-G-001) | seven entries | renamed `..._eight_files_...`; eight entries | R8 |
| `test_d021_spawn_allowlists_in_tools` | orchestrator `Agent(...)` is `set(ROLES) - {orchestrator}`, docstring "other six" | same expression over 8 ids (now seven spawned), docstring "other seven" | spawns include qa |
| `test_d032_project_name_substring_is_not_a_match` | `len(...) == 7` | `== 8` | R8 |

### evals/agents/test_tb12_graph.py
| Test | Before | After | Reason |
|---|---|---|---|
| `ROLES` | 7 | 8 | R8 |
| `test_d015_default_graph_covers_seven_roles` | renamed `..._eight_roles`; roles of the default graph equal 7 ids | equal 8 ids | C-40.5 |
| `test_d016_default_small_roles` | small subset `[orchestrator, implement, test, review]` | `[orchestrator, implement, qa, test, review]`, and the selected stage ids use the same set | A-03 |
| docstrings of G-004, G-006, D-015 and the one-stage-per-role chain test | "seven" | "eight" (the chain test builds one stage per `ROLES` entry, so it now has 8 stages) | prose only |
| new `test_d034_default_graph_order_and_loops` (TB12-D-034) | none | default order is orchestrate, research, design, audit, implement, qa, test, review; loops are exactly `{(qa, implement), (review, implement)}` | C-40.5, A-03 (the old tests did not pin the order, so they could not detect a wrong qa position) |

### evals/agents/test_tb14_skeleton.py
| Test | Before | After | Reason |
|---|---|---|---|
| `ROLES` (used by `test_g001_agents_and_settings_from_profile`) | 7 ids | 8 ids | R8; docstring "seven" to "eight" |

### tests/agents/test_roles.py
| Test | Before | After | Reason |
|---|---|---|---|
| `ROLE_IDS` | 7 | 8 | R8 |
| `test_seven_roles_in_order` | renamed `test_eight_roles_in_order`; list equals 7 ids in order | list equals the 8 ids in order | R8 |
| `test_writes_and_blind` | 7 entries | adds `qa: qa_paths` | C-40.2 |
| `test_spawns` | `len(orchestrator.spawns) == 6`; empty-spawn loop research, design, audit, test | `== 7`; loop adds `qa` | spawns include qa |
| `test_bash_modes` | 7 entries | adds `qa: full` | C-41.3 |
| `test_skills_exact` | `design` has `prd-designer`; `review` has 2 skills; no qa | `prd-writer`; `review` has the 5 skills in order; `qa` has `qa-supervisor`, `superpowers:verification-before-completion` | A-04, A-05, A-02 |
| `test_string_dir_accepted` | `len == 7` | `len == 8` | R8 |
| `test_round_trips_through_yaml_files` | passes by `ROLE_IDS` | unchanged code, now asserts 8 file stems | R8 |
| new `test_every_shipped_role_declares_sonnet` | none | all 8 `model == "sonnet"` | R7 |
| new `test_non_sonnet_model_rejected_unless_allowed` (opus, haiku, fable) | none | `RoleError` for role `design`, field `model`; loads with `allow_models=[model]`; a different allowed model does not help | C-40.1 |

### tests/agents/test_graph.py
| Test | Before | After | Reason |
|---|---|---|---|
| `test_default_graph_validates_with_seven_roles` | renamed `..._eight_roles`; 7 roles, `len(stages) == 7` | 8 roles, `len == 8`, exact order, exact loop set | C-40.5 |
| `test_small_subset_selects_and_validates` | roles and order without qa | roles include `qa`; order `orchestrate, implement, qa, test, review` | A-03 |

### tests/agents/test_generate.py, tests/agents/golden/*.md
| Item | Before | After | Reason |
|---|---|---|---|
| `test_seven_entries_keys_and_determinism` | renamed `test_eight_entries_...`; keys for 7 roles | keys for 8 roles (driven by `ROLE_IDS`) | R8 |
| `test_tools_built_from_core_then_mcp` | `Agent(research, design, audit, implement, test, review)` | `Agent(research, design, audit, implement, qa, test, review)` | spawns include qa |
| `test_project_name_substring_is_not_whole_word` | `len(out) == 7` | `== 8` | R8 |
| `golden/design.md` | `model: opus`, skill `prd-designer` | `model: sonnet`, skill `prd-writer` (frontmatter and Skills list) | R7, A-05 |
| `golden/orchestrator.md` | `model: opus`; "other six roles"; `Agent(... implement, test, review)` and "Start any agent other than" list without qa | `model: sonnet`; "other seven roles"; both lists include `qa` | R7, spawns |
| `golden/review.md` | `model: opus`; 2 skills; short description | `model: sonnet`; 5 skills; description carries the approval and amend sentences from `review.yaml` | R7, A-04 |
| `golden/test.md` | `model: opus` | `model: sonnet` | R7 |
| `golden/qa.md` | did not exist | new, generated by `generate_agents` for the same fixture profile | R8; reviewed: sonnet, tools Read Glob Grep Write Edit Bash, the two skills, hooks path_guard, secrets_guard, bash_guard, subagent_stop, writes only the three `qa_paths` globs |
| `golden/{audit,implement,research}.md` | unchanged | unchanged (verified byte-identical) | |

### tests/agents/test_simulate.py
| Test | Before | After | Reason |
|---|---|---|---|
| `test_generated_from_profile_alone` | set of 7 agent files plus settings | 8 agent files plus settings | R8 |

### tests/test_install.py
| Test | Before | After | Reason |
|---|---|---|---|
| `ROLES_WITH_OPUS`, `test_roles_really_propose_opus` | asserted exactly orchestrator, design, review, test declare opus | removed constant; replaced by `test_every_shipped_role_declares_sonnet` (all 8 sonnet) | R7, C-40.1 (rule 3) |
| `ROLE_IDS` | 7 | 8 | R8 |
| new fixture `opus_orchestrator` and `test_disallowed_model_is_rejected_and_nothing_written` | none | the installer loads roles from a copy where orchestrator declares opus: `install` exits 1, names `orchestrator` on stderr, the project directory stays empty | C-40.1 (no silent downgrade) |
| `test_allow_model_widens_explicitly` | relied on the shipped orchestrator being opus | uses `opus_orchestrator`; with `--allow-model opus` the orchestrator agent file is opus, implement stays sonnet, settings model stays sonnet | same behaviour, shipped data changed |
| `test_doctor_fails_on_non_sonnet_agent_unless_allowed` | same reliance | uses `opus_orchestrator`; doctor FAILs `agent orchestrator`, passes with `--allow-model opus` | same |
| `env` fixture (all doctor tests) | symlinked repo skills only | also stocks: minimal `SKILL.md` stubs for the ten external names and for every non-repo, non-plugin skill a role names; a throwaway `HOME` with a plugin registry and stub plugin skills for each `plugin:skill`; an external pin file (absolute path via `doctor.EXTERNAL_PINS`) pinning exactly those stubs | rule 4: the new role-skill and external checks must pass because the skills resolve and the pins match, not because the checks are bypassed |
| `test_doctor_all_pass` | `joined.count("PASS skill ") == 13` | `== 14` | the repo has 14 `skills/*/SKILL.md`; the per-skill count is one per repo skill and the number moved with the repo, not with this change |
| `test_doctor_json`, `test_doctor_without_project_runs_global_checks`, `test_doctor_trusts_arguments_not_the_manifest` | failed once the new checks ran against the old fixture | unchanged assertions, pass with the stocked fixture | rule 4 |
| new `test_doctor_reports_role_skills_and_external_pins` | none | PASS lines for `role qa skill qa-supervisor`, `role review skill minesweeper`, `role design skill prd-writer`, `external minesweeper: matches pin` | C-40.4 |
| new `test_doctor_fails_on_unresolved_role_skill` | none | removing a role skill gives `FAIL role audit skill legacy-audit`, exit 1 | A-06 |
| new `test_doctor_warns_on_changed_external_pin_and_fails_on_missing` | none | a changed pin gives `WARN external minesweeper ... changed since pinned` with exit 0; a missing external gives `FAIL external good-night`, exit 1 | A-07, C-40.4 |

### Prose fixed because it was now false
`docs/hooks/profile.md` (seven role ids), `docs/hooks/generator.md` (seven role specs, role order list without qa, review example `model: opus`), `docs/hooks/e2e.md` (seven agent files, two places), `docs/hooks/graph.md` (seven-stage graph and `small` subset), `docs/contracts/profile.md` and `docs/contracts/roles-and-generation.md` (one wording each: "seven" to "eight"), `docs/factory/METHODOLOGY.md` (implementers "Opus for hard slices"). `docs/hooks/roles.md` and `docs/native-install.md` were already updated.

### Deliberately not edited
* `evals/agents/test_tb06_blindness_guard.py::test_grep_glob[TB06-D-035]`: open on purpose (ADR-0004).
* `evals/native/**` and `evals/agents/GOLDEN.json`: no edit needed (no golden case id changed; renamed test functions keep their case ids). The golden gate list is therefore unchanged.
* Historical records that describe a past decision and should keep saying seven: ADR-0003, `docs/prds/TB-*.md` and `docs/prds/INDEX.md`, `docs/factory/requirements.md` (R-04, R-07 wording is the source register; C-40.6 supersedes it), `docs/plans/**`, `docs/native-verification/**`.
* Not docs, so outside this task and reported rather than changed: `skills/orchestration/SKILL.md` (its model table names Opus for the orchestrator and specialist), and the generated explorer (`docs/explorer/build_model.py`, `software-factory.html`, `software-factory.model.json`), which still shows seven roles and Opus/Haiku suggestions and needs regeneration by whoever owns it.

## 5. Honest limits
* This change was made by one maintainer pass; the new assertions were written against the implementation they check, so an independent review of them is still due under the sf loop.
* Goldens were regenerated from the generator, so they pin current output rather than an independent expectation; the line-by-line diff was reviewed against `review.yaml`, `qa.yaml` and the other role files.
* The fixture changes make doctor pass with stubs, so these tests prove the checks' logic, not that a real user skills directory is complete.
* The explorer and orchestration skill statements above remain false until their owners update them.
