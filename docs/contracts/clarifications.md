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
