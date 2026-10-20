# Binding clarifications to the contracts and PRDs

Status: published, **binding**. It resolves the 94 ambiguities the eval authors logged (IDs in brackets). Where a contract or PRD and this file differ, this file wins. Items marked *unverified* rest on a Claude Code behaviour that was not confirmed against the documentation.

## Profile and roles (TB-01, TB-02)
- **[A-01]** `Profile`, `RoleSpec` and their nested values are frozen dataclasses read by attribute; each has `.to_dict()`.
- **[A-02]** The profile loader checks the *shape* of `graph` (a mapping; `stages` a list of mappings with `id`, `role`, optional bool `gate`; `edges` and `loops` lists of two-item lists of strings; `subsets` a mapping of names to lists of role ids) and raises `ProfileError` on a wrong shape. Graph *semantics* belong to TB-12.
- **[A-03]** Omitted optional lists become empty tuples, omitted mappings become empty mappings, and omitted `deploy`, `checks` and `graph` become `None`.
- **[A-04]** For a bad entry in a list field, `.field` is the field name followed by the zero-based index in square brackets, for example `one_way_door_patterns[1]`.
- **[A-05]** Only a `..` path *segment* is rejected; `a..b` is a valid name.
- **[A-06]** `Profile.one_way_door_patterns` holds only the profile's own patterns; built-in defaults live in the bash guard.
- **[A-07]** A missing `project` has field `project`; a `project` without `name` has field `project.name`.
- **[A-08]** A wrong-typed value anywhere in the schema is invalid, and `.field` names the offending key (for `deploy`, `checks`, `mcp_servers` as for the rest).
- **[A-09]** `schema_version` must be the integer 1; the string `"1"` and the boolean `true` are invalid.
- **[A-11]** In `agents.<role>`, the only accepted keys are `model`, `extra_skills`, `mcp_servers`; any other key is a `ProfileError` with field `agents.<role>.<key>`. `GenerationError` for write access remains as a defense when a `Profile` is built in code.
- **[A-12]** The only tool-count check on role data is `len(core_tools) <= max_tools`; the generator checks the final list.
- **[A-13]** **All seven roles list `path_guard`** (the hook decides by role). Also, all seven list `secrets_guard` and `bash_guard`.
- **[A-14]** Personal skills are listed unprefixed; plugin skills as `plugin:skill`. Role skill lists, exactly:

| Role | Skills |
|---|---|
| orchestrator | `orchestration`, `plan-adherence`, `session-handoff`, `away-mode`, `deploy-verify`, `one-way-door`, `superpowers:dispatching-parallel-agents` |
| research | `grounded-research`, `deep-research`, `brownfield-explorer` |
| design | `prd-designer`, `axiomatic-spec`, `one-way-door`, `superpowers:brainstorming`, `superpowers:writing-plans` |
| audit | `legacy-audit`, `brownfield-explorer`, `claude-security:scan` |
| implement | `superpowers:test-driven-development`, `superpowers:systematic-debugging`, `claude-api`, `frontend-design:frontend-design` |
| test | `eval-designer`, `deploy-verify`, `superpowers:verification-before-completion`, `langfuse` |
| review | `implementation-review`, `code-review:code-review` |

  Project-local skills (for example `eval-gate-triage`) come from `agents.<role>.extra_skills`.
- **[A-15]** Role MCP entries never name a deploy platform or git host. Two placeholders are allowed: `$deploy` (resolved to `profile.deploy.platform_server`, read access, for orchestrator, test, review) and `$git_host` (resolved to `github` or `gitlab` from `profile.git_host`, read access, for orchestrator, research, review). Any placeholder that resolves to nothing is omitted. General servers may be named (`deepwiki`, `alphaXiv`, `firecrawl` for research; `playwright` for test) and are omitted when the profile lacks them.
- **[A-16]** Role-loading errors raise `RoleError` with `.role` and `.field`.
- **[A-17]** Each role YAML file is a mapping whose keys are the RoleSpec field names.
- **[A-18]** The `Agent(...)` entries in a role's `core_tools` list exactly the role's `spawns`; a role with no spawns has no `Agent` tool.

## Generator (TB-03)
- **[A-10]** `tools` and `disallowedTools` render as one comma-separated string; `skills` as a YAML list.
- **[A-19]** Body headings, in order: `## Purpose`, `## You may write`, `## You must never`, `## Skills`.
- **[A-21]** `ledger_audit` is registered on `SubagentStop` with no matcher.
- **[A-22, C-28]** `stop_gate` is registered under `Stop` in the implement agent's frontmatter and under `SubagentStop` in project settings (TB-13). The two are read as consistent because a sub-agent's frontmatter Stop hook is expected to run as SubagentStop (*unverified*; confirmed or corrected in the manual rehearsal of TB-14). `stop_gate` handles both events the same way.
- **[A-23]** Frontmatter `description` is the role spec's `description`, verbatim.
- **[A-24]** The project-name check is a case-insensitive whole-word match on the body text.
- **[A-34]** Matchers: `path_guard` and `secrets_guard` `Write|Edit|Bash`; `blindness_guard` `Read|Grep|Glob|Bash`; `bash_guard` `Bash`; `stop_gate`, `subagent_stop`, `ledger_audit`, `session_start` no matcher.

## Graph (TB-12)
- **[A-20]** `load_graph` builds and validates, raising `GraphError`; `validate()` re-raises the same.
- **[A-25]** `select` raises only if the resulting graph would have no start stage or no end stage (or no stages).
- **[A-26]** A stage is a gate if and only if it has `gate: true`; the "human-facing role" clause is dropped.
- **[A-27]** `order()` is Kahn's algorithm, always taking the smallest ready stage id.
- **[A-28]** With no `graph` in the profile, `load_graph` uses the shipped default graph.
- **[A-29]** `select` keeps a loop only if both its endpoints are kept. Subset names are keys of `graph.subsets` (or of the default graph's subsets); subset members must be role ids, checked at profile load.
- **[A-30]** `gates()` returns a list of stage ids in `order()` order.
- **[A-31]** An empty `stages` list is rejected (`GraphError`, or `ProfileError` on the shape).

## Settings emitter (TB-13)
- **[A-32]** It registers the union of hook ids used by the generated roles (all eight).
- **[A-33]** The `hooks` section has the shape `event -> [{matcher, hooks: [{type: command, command}]}]`.
- **[A-35]** `emit_settings` must not mutate `existing`.

## Hook core (TB-04)
- **[A-04-1]** Malformed input or an unknown event always fails closed as a deny: exit 2 with `hook error: ...` on stderr, whichever hook id is running.
- **[A-04-2]** There are **eight** hook ids (the PRD's "seven" was a miscount); the registry knows all eight.
- **[A-04-3]** `$FACTORY_PROFILE`, when set, wins over `.factory/profile.yaml`.
- **[A-04-4]** `Decision(kind, reason)` raises `ValueError` if `kind` is not one of the four, or if `kind != "allow"` and `reason` is empty.
- **[A-04-5]** Adapter rules for other combinations: on Stop and SubagentStop, `deny`, `block` and `ask` all produce the block JSON (exit 0); on PreToolUse, `block` is treated as `deny`; on PostToolUse and SessionStart, any non-allow decision exits 0 with the reason on stderr.
- **[A-04-6]** The core API is importable from `factory.hooks.core` and re-exported from `factory.hooks`.

## Path guard (TB-05)
- **[A-05-1]** The path guard does not inspect Bash writes for roles whose `bash` mode is `full`. (Documented gap; the orchestrator's `writes: none` governs the Write and Edit tools.)
- **[A-05-2]** For `awk` only shell redirection is checked; redirection inside an awk program is a documented gap.
- **[A-05-3]** Command substitution (`$(...)` or backticks) is denied unless it sits inside single quotes; double quotes do not exempt it.
- **[A-05-4]** For a role with no allowed folders the deny reason says `no write access for role <role>`.
- **[A-05-5]** `implement` may not write under `.factory/**`, in addition to the eval, held-out and frozen-test paths (this corrects "implement→anywhere except ..." in the PRD).
- **[A-05-6]** For a path that does not exist, the nearest existing ancestor is resolved through symlinks and the remaining segments are appended.

## Blindness guard (TB-06)
- **[A-06-1]** A bare `pytest` or `python -m pytest` with no path argument is denied for blind roles (it would collect from the project root). A path argument that is neither protected nor an ancestor of a protected path is allowed.
- **[A-06-2]** A protected glob such as `evals/**` also matches the directory `evals` itself.
- **[A-06-3]** `~` expands to `$HOME`; `~+` to the current directory; `~-` and `~user` are unresolvable and are denied if the remainder of the path is protected or unresolvable.
- **[A-06-4]** An unresolved `$VAR` in a path is denied only when the remainder names a protected fragment or the variable is `PWD`, `OLDPWD` or `HOME`; a variable assigned in the same command is expanded first.
- **[A-06-5]** A standalone `base64 -d` is denied for blind roles, as listed.
- **[A-06-6]** `git status` and `git diff` are allowed; `git log`, `show`, `blame`, `grep`, `ls-files`, `ls-tree`, `cat-file` and `archive` are denied unless they carry a pathspec after `--` that is not protected. (Residual gap documented.)
- **[A-06-7]** An unknown `agent_type` is treated as a blind role by this hook.

## Secrets guard (TB-07)
- **[A-07-1]** Colon assignments (`"api_key": "..."`, `password: "..."`) count as assignments.
- **[A-07-2]** An assignment whose quoted value is exactly a variable reference (`"${X}"`, `"$X"`) is allowed.
- **[A-07-3]** The placeholder rule inspects the whitespace- or quote-delimited token that contains the match, so `sk-<40 chars>...` and `sk-000...0` are placeholders.
- **[A-07-4]** Placeholder words match case-insensitively.
- **[A-07-5]** `AIza` needs at least 35 following URL-safe characters (35 or more).

## Bash guard (TB-08)
- **[A-08-1]** The main session with a non-orchestrator `main_session_role` gets that role's treatment (deny, not ask).
- **[A-08-2]** Only the git forms `git mv` and `git rm` are denied for `implement`; plain `rm` and `mv` are not restricted by this hook.
- **[A-08-3]** SQL keywords match case-insensitively.
- **[A-08-4]** For `sh`, `bash` and `zsh` with `-c`, the string argument is parsed and matched as a command.
- **[A-08-5]** The `rm -rf` exemption applies to targets that are, at any depth, a `node_modules` or `.venv` directory, or anything under `/tmp`.
- **[A-08-6]** A push with a `+refspec` counts as a force push. Git global options (`-C <dir>`, `-c k=v`, `--git-dir`, `--work-tree`) are skipped before the subcommand is identified.

## Stop gate (TB-09)
- **[C-01, C-02]** The transcript is Claude Code's native JSON-lines format, with `tool_use` blocks inside assistant messages (*unverified against the documentation*). If the file is missing or does not parse, check 5 is skipped and a line is appended to `.factory/stop_gate.log`. If it parses and holds no Edit or Write call, the check passes; if it holds one but no later Bash call containing `checks.test`, the gate blocks.
- **[C-03]** On Stop (main session) check 5 uses `transcript_path` if the payload has it, otherwise it is skipped.
- **[C-04]** Every line of an untracked new file counts as an added line.
- **[C-05, C-06]** Skip, xfail and trivial-assert markers are matched as whole tokens (word boundaries), only in test files: paths under `tests/`, `test/` or `__tests__/`, or named `test_*.py`, `*_test.py`, `*.test.*`, `*.spec.*`. `sys.exit` does not match `xit`; `assert 1 == f()` does not match `assert 1`.
- **[C-07]** "Git unavailable" means no git executable, or the project root is not a repository, or it has no HEAD commit.
- **[C-08]** The block counter resets when a stop is allowed by passing all checks; after the cap, every allowed stop appends one log line.
- **[C-09]** A frozen file that is missing on disk, or missing from the manifest, blocks. Manifest keys are project-relative POSIX paths.
- **[C-10]** A Bash call whose command contains `checks.test` counts as evidence (containment), even if narrowed to one file.

## Sub-agent stop validators (TB-10)
- **[C-11, C-13]** "New" and "changed" mean added or modified relative to git HEAD, plus untracked files.
- **[C-12]** Audit table rows exclude the header line and the separator line.
- **[C-14]** The ADR directory is the literal `docs/adr` or any `paths.design_dirs` entry whose last segment is `adr`.
- **[C-15]** `inconclusive` grades with `VERDICT: APPROVE` also block, as `wrong_reason` does.
- **[C-16]** `unverified` matches case-insensitively; the label may be `Sources`, `**Sources**`, `**Sources:**` or a heading `## Sources`.
- **[C-17]** A message containing both `VERDICT: APPROVE` and `VERDICT: REJECT` blocks.
- **[C-18]** Block reasons name each missing element (sources, unverified marker, severity, citation, verdict, grade, heading name).

## Ledger (TB-11)
- **[C-19]** Chain value: `sha256(prev_chain.encode("utf-8") + b"\n" + text.encode("utf-8")).hexdigest()`, where `text` is the entry body exactly as written after the header line with the trailing newline removed, and `prev_chain` is `""` for the first entry.
- **[C-20]** The chain runs over all entries in file order, not per section.
- **[C-21]** The file's first line after the title is `<!-- entries: N; head: <chain> -->`, updated on each append; `verify` compares it with the entries, so removing the last entry is detected.
- **[C-22]** Verify problems read `section '<name>' entry <n>` (1-based within the file).
- **[C-23]** `now` is an aware UTC `datetime` or an ISO string ending `Z`; headers print `YYYY-MM-DDTHH:MM:SSZ`.
- **[C-24]** The Audit Trail entry is appended with role `orchestrator`; a missing ledger file or a missing `current_ticket` makes the hook do nothing; whitespace around the ticket id is trimmed.
- **[C-25]** Secret-shaped values are removed first, then the text is cut to 200 characters.

## End to end (TB-14)
- **[C-26]** `run_events(project_root: Path, events: list[dict]) -> list[Outcome]`. Each event is `{"payload": {...}}`. Hooks to run are looked up from the settings that `emit_settings` produces for the project (event and matcher match, agent frontmatter hooks included for the payload's `agent_type`). `Outcome(kind, reasons)` has `kind` in `allow`, `deny`, `ask`, `block`, with precedence deny or block over ask over allow, and `reasons` the non-empty reasons in hook order.
- **[C-27]** `shadow.record(result, actual_choice, ledger_dir, state_digest="")`; `agrees` is `result.choice == actual_choice`; a missing `ledger_dir` is created.
- **[C-29]** The base fixture profile with `mcp_servers` removed serves as "the small profile".

## Second round (points the authors could still not pin)
- **[C-30, C-20 revised]** The ledger chain runs in **append order**, not file order. Each entry's trailing line is `<!-- chain: <sha256 hex>; seq: <n> -->` where `n` is the 1-based global append counter; the hash covers the chain value of the entry with `seq` n-1 (`""` for n=1) exactly as in C-19. Entries live inside their sections, so file order and `seq` order may differ; `verify` orders by `seq`, requires `seq` to run 1..N without gaps or repeats, and reports a `seq` gap or repeat as a problem. This replaces the "chain line" wording of the graph-and-ledger contract.
- **[C-31]** For a ledger with no entries the anchor line is `<!-- entries: 0; head: -->` (empty head).
- **[C-32]** A zero-byte transcript file counts as unparseable (check 5 skipped, one line logged). A missing or unparseable transcript is logged only when `checks.test` is set (otherwise check 5 does not apply and nothing is logged).
- **[C-33]** `shadow.record` treats `result` as duck-typed: it reads only the attributes `log_record` reads (`decision`, `choice`, `action`, `source`, `band`, `policy_version`, `top_prob`, `margin`, `probabilities`, `fault`, `latency_ms`); it does not require a `Routing` instance.
- **[C-34]** Still *unverified*: whether Claude Code runs a sub-agent's frontmatter Stop hook as SubagentStop. It is confirmed or corrected in the manual rehearsal of TB-14, and until then no case depends on it.
- **[U-1]** A git read command that needs a pathspec (`git grep`, `ls-files`, `ls-tree`, `log`, `show`, `blame`, `cat-file`, `archive`) is denied for blind roles unless every pathspec after `--` is neither protected nor an ancestor of a protected path (so `-- tests` is denied if `tests/held_out/**` is protected, and `-- src` is allowed).
- **[U-2]** An unresolved `$VAR` prefix is denied only if the remaining path text names a protected directory segment (the first segment of a protected glob, such as `evals` or `held_out`) or contains a protected glob match; a bare file name alone does not.
- **[U-3]** Paths are normalised (`..` collapsed) **before** the `/tmp` exemption is applied, so `/tmp/../etc` is not exempt; `rm -rf ../sibling` is not exempt either.
- **[U-4]** For an unknown agent type, path-guard deny reasons read `unknown agent type <type>`.

## Third round
- **[A-11]** `factory.agents.profile.parse_profile(data: dict) -> Profile` exists alongside `load_profile(path)` (which is `yaml.safe_load` then `parse_profile`), so a profile can be built in code. It applies every rule of the profile contract, including the override-key rule.
- **[A-29]** `Graph` exposes read-only attributes `stages` (tuple of stage objects with `id`, `role`, `gate`), `edges` (tuple of `(from_id, to_id)`) and `loops` (tuple of `(from_id, to_id)`).
- **[C-35]** The chain covers entry text only, so reordering entries within the file while keeping `seq` intact is not a tamper. `verify` also reports an entry that sits in a section its role may not write (moving an entry into another section is caught this way when the roles differ).

## Factory control files (MECE audit P0-4)
- **[C-36]** `.factory/**` and `.claude/**` (under the project root) are the factory's own control files: profile, baseline, freeze marker, ledger, hook state, `settings.json` and the generated agent definitions. For the `implement` role, whatever the profile says:
  1. **Write and Edit** to any path under `.factory/` or `.claude/` is denied by the path guard. [A-05-5] already covers `.factory/**`; `.claude/**` is added to the same write-protected set, and the deny reason names the protected folder. Paths are normalised and symlink-resolved exactly as for the other protected paths ([A-05-6], B4).
  2. **Bash**: the blindness guard denies a command that names a path under `.factory/` or `.claude/` (the directory itself or anything below it) as **a write target**, or as **an argument of an interpreter one-liner** (`python -c`, `node -e`, `perl -e`, `ruby -e`, `sh -c`, `bash -c`). Paths are recognised with the same parsing as TB-06 B4a: relative to the working directory (so a working directory inside `.factory/` counts), absolute, parent (`../`), quoted, glob, tilde and `$VAR` forms. A write target is the target of a redirection (`>`, `>>`, `>|`, `&>`, `n>`), an operand of `tee`, the destination operand of `cp`, `mv`, `install`, `ln` and `rsync`, an operand of `rm`, `touch`, `truncate`, `mkdir`, `chmod`, `chown`, `shred`, `unlink`, `patch`, `sed -i` and `perl -i`, and the `of=` operand of `dd`. The dynamic-construction rules (B4e) apply as before.
  3. **Reads are not affected.** The Read tool, `Grep` and `Glob`, and Bash commands that only read these paths (`cat .factory/profile.yaml`, `ls .claude`, `grep x .factory/profile.yaml`) stay allowed for `implement`; this clarification adds no read protection.
  4. **Other roles are unaffected** by items 2 and 3 (the blindness guard applies only to `implement`, and an unknown agent type is treated as blind per [A-06-7]). Their Write and Edit outcomes are whatever the path guard already decided; the orchestrator keeps writing routing state and ledger status under `.factory/` through its own Bash.
  5. Residual gap, unchanged: a script file that the agent runs (`python build.py`) is not inspected (TB-06 B7).

## Role-loading error fields (TB-02), added during QA of TB-02
- **[C-37]** Resolves an ambiguity between [A-04] (written under the "Profile and roles" heading, for "a bad entry in a list field") and [A-16] / TB-02 behaviour 9 ("an error naming the role and the field"). For `RoleError`, `.field` is the bare top-level `RoleSpec` field name (`hooks`, `core_tools`, `skills`, `spawns`, `disallowed_tools`, `mcp`), never an indexed or nested path; the offending entry and its position go in the message. [A-04]'s `[i]` suffix applies to `ProfileError` only. Reason: the PRD's literal wording names "the field", the role loader has a small fixed field set, and an index is unstable under reordering. Recorded 2026-10-19 by the orchestrator after the TB-02 implementer and the independent runner read A-04 differently; no existing case is weakened and the only affected acceptance case already expects the bare name.

## Hardening after the commit security review of TB-05 (C-38)
- **[C-38]** Added 2026-10-19 after an automated security review of `path_guard`. It supersedes [A-05-2] (awk) and, for two hooks, the matchers in [A-34]. Reasons are in the review: awk, sed and git have write or execute features that a prefix allowlist does not see, and two Claude Code tools write files outside `Write|Edit|Bash`.
  1. **awk in a read-only role.** `awk` stays allowed only when none of these appears anywhere in its arguments: `system`, `getline`, `close`, `fflush`, `|`, `>`, `-f`, `--file`, `-i`, `--include`, `--source`, `-E`. Redirection inside the program text is therefore denied (the program text is conservatively scanned for the characters `|` and `>`, so a comparison such as `$1 > 5` is also denied; this over-blocking is accepted and documented). Shell redirection outside the program remains denied as before. `awk '{print $1}' file` stays allowed.
  2. **sed in a read-only role.** `sed` stays allowed only as `sed -n <script> [file...]` with exactly one script word that is either a print command (`p` with an optional address or address range made of line numbers, `$`, or `/regex/`) or a substitution `s<d>pattern<d>replacement<d>flags` whose flags are drawn only from `g p i I` and digits. Any script containing the commands `w`, `W`, `e`, `r`, `R` or the substitution flags `w` or `e`, and any use of `-f`, `-s`, `-i`, `--in-place`, `--file`, `-e`, `--expression` or a second script word, is denied.
  3. **git abbreviations.** In a read-only git command any option word whose text before an optional `=` starts with `--ou` is denied (git accepts unambiguous abbreviations of `--output`, so exact-match denial is not enough).
  4. **More write tools.** `MultiEdit` (target `file_path`) and `NotebookEdit` (target `notebook_path`) are write tools: `path_guard` applies to them exactly as to `Write` and `Edit`, and `secrets_guard` scans `MultiEdit` `edits[*].new_string` and `NotebookEdit` `new_source`. The generated matcher for `path_guard` and `secrets_guard` is `Write|Edit|MultiEdit|NotebookEdit|Bash` (all other matchers in [A-34] are unchanged). A write-tool payload with a missing or non-string target is denied.
  5. These tighten the guards only. No existing deny becomes an allow, except that the cases which expected awk redirection inside a program to be allowed now expect deny.
- **[C-39]** Added 2026-10-19 after an automated security review of `secrets_guard` (tightening only; supersedes the placeholder rule of [A-07-3] and PRD TB-07 behaviour 4 where they differ).
  1. **Placeholders are whole-value.** A matched secret is exempt only when the whole matched value (for a prefixed key, the whole body after the prefix; for an assignment, the whole assigned value) is itself a placeholder form: an angle-bracket form `<...>` spanning the value, a single repeated character, or a `$VAR` / `${VAR}` reference. A placeholder word elsewhere in the surrounding token or text no longer exempts a real key (`your_key=<real key>` is denied). `secret_allow_patterns` from the profile still apply and are matched against the matched value only.
  2. **Bounded scanning.** Text longer than 2,000,000 characters is denied (fail closed) with a reason saying the content is too large to scan; the assignment-name part of any pattern is bounded so scanning cannot take unbounded time on hostile input.
  3. **Quoting does not hide a key.** For `Bash`, the command is scanned both as written and in a de-quoted form (single and double quotes and backslash escapes removed, `$'...'` sequences unescaped, adjacent literals joined), so a key split by shell quoting such as `"sk-""ant-..."` is caught.

## C-40 (2026-10-20, SFN-02): names and formats the owner flow needs

Binding for slice SFN-02 (`docs/prds/SFN-02-roles-and-doctor.md`). Source: the owner's verbatim flow (`docs/requirements/sf-owner-flow.md`) and the plan the owner approved with "Do it" on 2026-10-20 (artifact QvGeDjn8CkfoHrbATXFH11).

1. `load_roles(roles_dir, allow_models=None)` accepts an optional collection of model names allowed beyond `sonnet`; the profile file may carry a top-level list `allow_models`; the installer's existing `--allow-model` flag feeds the same list. A role declaring another model without it is rejected with `RoleError`, and `sf install install` then exits 1 and writes nothing (it no longer downgrades silently).
2. The writes class of the `qa` role is the string `qa_paths`; `docs/hooks/roles.md` defines it as QA notes (`**/qa-notes.md`, `**/qa-feedback/**`) and the QA attempt records under `.sf/qa/`.
3. `sf install pin-external` takes `--skills-dir DIR` (default the user skills directory), `--factory-root DIR` (default the repository root) and `--yes`. `docs/external-skills.json` is `{"schema": 1, "skills": {"<name>": {"sha256": "<hex of SKILL.md bytes>"}}}`; a skill without a `SKILL.md` is not pinned and is reported.
4. Doctor lines are `PASS|WARN|FAIL role <id> skill <name>: <detail>` for role skills (not beginning with `skill `, which the existing per-skill count uses) and `PASS|WARN|FAIL external <name>: <detail>` for pins; the changed-pin detail contains the words `changed since pinned`. A WARN does not change the exit code; a FAIL does.
5. Where the default graph lists stages, `qa` sits between `implement` and `review`; `test` stays as the runner stage reached from `qa`.
6. Amendment of earlier acceptance material: the earlier seven-role, Opus-declaration and `prd-designer` expectations in `evals/agents/` and `tests/` are superseded by this slice. They are updated by the maintainer after the slice lands (never by the implementer), each edit listed with its reason in ADR-0005.

Applied: ADR-0005

## C-41 (2026-10-20, SFN-02b): amendments after the automated security review of SFN-02

Supersedes C-40.1 where it differs; binding for the SFN-02 follow-up.
1. `allow_models` in a project's profile never widens the allowed models on its own: a model outside `sonnet` is allowed only when the operator passes it on the command line (`--allow-model M`), and a profile list is honoured only for models that are also given there. `install` and `doctor` print any extra model they were asked to allow. Role-file loading takes the already-combined list from its caller.
2. `path_guard` enforces the `qa_paths` writes class: a role whose writes class is `qa_paths` may write only paths matching `**/qa-notes.md`, `**/qa-feedback/**` and `.sf/qa/**` (never `evals/**`, held-out, frozen-test or control directories), and the `app` branch denies writes to those `qa_paths` globs by implement-style roles. The globs come from the hook configuration, with the three above as defaults.
3. The `qa` role's Bash mode is `full` only so it can run the protected suites. It receives the implement-style git restrictions (no `git add -A`/`.`, no history rewrite, no checkout of protected paths), and the QA feedback files are subject to the existing feedback leak check before a blind role may read them.
4. `python -m factory.install` gains the `pin-external` subcommand (flags in C-40.3), dispatching to the existing function.

## C-42 (2026-10-20, SFN-08): editor link details

Binding for `docs/prds/SFN-08-editor-links.md`.
1. `idea`: `idea://open?file=` followed by `encodeURIComponent(root + "/" + relPath)` (one encoding, so `/` becomes `%2F`), then `&line=N` when a line is valid. `sublime` and `textmate` append `&line=N` only when valid; without a line the whole `&line=` part is omitted.
2. Windows drive roots (`C:/Users/me`, a drive letter, colon, slash) are valid roots; the colon after the drive letter is kept as is. `C:` alone and `C:proj` are not valid roots.
3. Any `relPath` that begins with a scheme-like prefix (letters, digits, `+`, `.`, `-` followed by `:`) is rejected, so a file name containing `:` after such a prefix is rejected.
4. A line that is a boolean, a non-numeric string, a float or a negative is omitted, not an error. A numeric string of digits is accepted.
5. The 4,096-character limit applies to each argument separately; exactly 4,096 is accepted, 4,097 is rejected.
6. `nesting_dolls.py check --assets [--repo DIR]` finds the ops shell at `<repo>/ops/shell/index.html` (repo defaults to the current directory's git root) and the skill assets relative to the script; a mismatch is reported with the text `editor-links` and exits 1. Without `--assets`, drift is not checked.
7. With no editor or no valid root a file entry shows `Copy path` and a hint containing the word `editor`.
8. Browser tests in the hidden evals launch Chrome themselves; implementers do not run them.

## C-43 (2026-10-20, SFN-08): URL shape found wrong in review

Amends C-42 and PRD K-02/K-03. The editors' documented URL form puts the absolute path directly after `file`: with a POSIX root `/home/me/proj` and relPath `a.py` and line 120, `vscode://file/home/me/proj/a.py:120` (one slash after `file`, never two). Windows drive roots keep the drive colon: `vscode://file/C:/Users/me/proj/a.py:3`. A root given with backslashes is accepted only when it starts with a drive letter and colon; its backslashes are converted to `/`. A backslash in `relPath` is still rejected. The `..` rule rejects only a whole path segment equal to `..`; a name such as `a..b` is fine. The same one-slash rule applies to `cursor`, `windsurf` and `zed`.

## C-44 (2026-10-20, SFN-08): UNC and empty-segment roots (automated security review)

Amends K-03. A POSIX root that begins with two or more slashes (`//host/share`) is invalid, because the editors' URL handler would read the result as a network (UNC) path. A root or `relPath` containing an empty path segment (`a//b`) or a segment equal to `.` is invalid. A single trailing slash on the root is still stripped. The same rules hold for roots taken from `?root=`, which keeps overriding a configured root as K-04 says; the UNC rule is what makes a crafted link harmless on Windows.

## C-45 (2026-10-20, SFN-06): lsf interfaces the PRD left open

Binding for `docs/prds/SFN-06-lsf-lite.md`.
1. **Clock.** `LSF_NOW=<ISO UTC, e.g. 2026-10-20T10:00:00Z>` overrides "now" for every command (event `at`, budget, status).
2. **Data dump.** `lsf bundle --json` prints `{"tabs": {<tab>: {"available": bool, "items": [...] | "reason": str}}}` with tab names research, experiments, adrs, bug_log, prd_journeys, architecture, git (the names and item shapes of `factory.ops.collect`) plus `docs` (ELI12). `/api/state` and `/api/at` return the same tab layout.
3. `--root DIR` is accepted before or after the subcommand and its arguments.
4. `doctor --port N` names the port to check (default 8765).
5. **Profile keys** in `.lsf/profile.json`: `session_minutes`, `phases` (list of `{id, group}`), `weights` (`{align, review, build}`), `checkpoints` (`{phase: bool}`), `editor`, `workspace_root`, optional `models`. The default checkpoint mode is `align` (the seven align phases). A second `lsf init` never deletes events, stops or the profile.
6. **`budget --json`**: `{"groups": {name: {planned_minutes, actual_minutes, percent_of_plan, flag}}, "waiting_on_human_minutes": N}`; an unmeasured `actual_minutes` is null; flag text contains `over` or `under`; the human-readable output always has a line containing `waiting on human`. A weights sum outside tolerance is exit 2 on `budget` and `status`.
7. **`hitl status --json`**: a list of stops with `name`, `question`, `artifact` (list), `reason`, `opened_at`, and when released `released_at`, `released_by`, `note`. Release of an unknown or already released stop is exit 1. `phase end` on a phase that is not open is exit 1.
8. **Hooks.** `hooks print` decides the command names. The `PostToolUse` matcher is `Bash`; the `hook` command filters for `git commit` itself. A `hook` run prints nothing on stdout and exits 0 on any input; for malformed input stderr is empty too; for a failed write only stdout must be empty.
9. **Events.** `note` keeps the first 2000 characters, no ellipsis. Required keys: `at, stage, slice (may be null), phase, verdict, note, source`; `sha` is HEAD (full) or `unknown`. `source` is one of `lsf`, `hook`, `agent`. The hook summary lives in `note`, at most 200 characters.
10. **Stop ledger.** Each entry carries a 64-hex chain value over the previous chain value and the entry text; any edited, deleted or malformed line makes `status` print `stop ledger failed verification` and exit 1.
11. **`/api/file`**: errors are 4xx (missing 404, over 1 MiB 4xx, non-UTF-8 4xx); anything under `.lsf/` whose name contains `secret` or `token`, and every `.env*` at any depth, is refused; a symlink that stays inside the repo is allowed; the success body is the file text. `/api/at?sha=` takes a full or short sha; a bad revision is 4xx.
12. **Release route.** A wrong, missing or foreign-Host request is 403; an unknown stop, an already released stop or bad JSON is 4xx; other POST paths give 404, 405 or 501; no CORS headers are sent.
13. **`install.sh`**: shebang `#!/bin/sh` or `#!/usr/bin/env sh`; avoids `sha256sum`, `realpath`, `cp -a`, `mktemp --`, `readlink -f`, `sed -i`, `date -d`, `stat -c`; the wrapper is at most 15 lines and runs `python3` on the installed `lsf.py`; backups are named `lsf.backup-<UTC digits>`.
14. The dashboard's "never available with zero items" rule is checked statically in source and through the bundle data.

## C-46 (2026-10-20, SFN-07): eli12 finding codes and output

Binding for `docs/prds/SFN-07-eli12-docs.md`. Each finding line is `path:line: code: message` where `path` is relative to `--root`, `line` a positive integer (the entry's heading line, or 1), and `code` is one of: `missing-entry` (public symbol without an entry), `orphan-entry` (entry whose symbol no longer exists), `stale-signature`, `stale-dependencies`, `todo`, `format` (missing, misordered or malformed labelled line or heading), `too-long` (more than 25 words or more than one sentence in `What it does`, or a line over 160 characters), `bad-param` (a parameter not written `name (type): meaning`), `jargon` (a listed term without a glossary entry), `unparseable`. `--json` prints a list of objects with the keys `path`, `line`, `code`, `message`. Exit codes: 0 no findings, 1 findings, 2 usage error. Doc files are `docs/eli12/<dotted.module.path>.md` (dots, no slashes; package `__init__` modules use the package path).

## C-47 (2026-10-20, SFN-07): where a reference points

In `Used by` and `Depends on`, the `path:line` of an entry is the line where the call or reference happens (the call site), so that clicking it in an editor lands on the use. A symbol is listed once per caller with its first call-site line. Scaffolded placeholders have the shape a finished line must have: `TODO` stands in for each word to be written, so a parameter line is `name (TODO): TODO` and a return line is `TODO: TODO` when the type is not annotated; replacing every `TODO` with plain words must give a line that passes `check`.

## C-48 (2026-10-20, SFN-07): which place each reference opens

Refines C-47. In `Used by`, `path:line` is the call site in the caller (where the use happens). In `Depends on`, `path:line` is where the depended-on symbol is defined (so the entry opens the thing being relied on); a `(maybe)` dependency that resolves to no definition cites the call site in this symbol. Every finding that concerns one symbol (`stale-signature`, `stale-dependencies`, `too-long`, `bad-param`, `format`, `todo`, `missing-entry`, `orphan-entry`) names that symbol, with its short name or dotted name, in its message text.
