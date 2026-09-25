# Ambiguities found while writing the TB-04 to TB-08 evals

Each entry gives the slice, the clause, and the competing readings. No case pins an expectation to either reading, except where noted that a case accepts both. These points should be settled in the PRD or contract, and a case added once they are.

## TB-04 hook core

- **A-04-1. Fail closed when the event is unknown.** hook-io "Fail closed" and TB-04 B3 say invalid JSON or a missing `hook_event_name` gives "a deny (PreToolUse) or block (Stop, SubagentStop)". With no parseable event, the adapter cannot tell which one applies. (a) Always deny (exit 2, reason on stderr). (b) Choose by the hook id, for example block JSON for `stop_gate`. Cases D-020, D-021 and D-028 accept either, provided the result is not an allow and the reason starts `hook error:`.
- **A-04-2. Seven or eight hook ids.** TB-04 B5 says `registry` maps "the seven hook ids", but hook-io lists eight (`path_guard`, `blindness_guard`, `secrets_guard`, `bash_guard`, `stop_gate`, `subagent_stop`, `ledger_audit`, `session_start`). (a) One of the eight is missing from the registry, and the PRD does not say which. (b) "Seven" is a miscount and all eight are registered. No case checks that every id is known; D-029 to D-032 cover only the four guard ids.
- **A-04-3. `$FACTORY_PROFILE` versus `.factory/profile.yaml`.** B6 and hook-io say the profile is loaded "from `$FACTORY_PROFILE` or `.factory/profile.yaml` under cwd". When both exist: (a) the environment variable wins; (b) the project file wins. D-027 tests only the case where the environment variable is set and there is no project file.
- **A-04-4. "reason: required when kind != allow".** (a) Constructing `Decision` without a reason raises an error. (b) It is a convention for hook authors only. No case constructs a reasonless non-allow decision.
- **A-04-5. Table cells marked "not used" and non-guard events.** The adapter table leaves deny and ask on Stop, block on PreToolUse, and every ordinary decision on PostToolUse and SessionStart undefined. B3 defines only the fail-closed output for PostToolUse and SessionStart. No case checks these combinations.
- **A-04-6. Module of the core API.** hook-io puts the Python API in "package `factory.hooks`"; the TB-04 OWN list and `lib.run_decide` use `factory.hooks.core`. The cases import `Decision`, `PayloadError`, `parse_payload`, `run_hook` and `HookConfig` from `factory.hooks.core`. If they live only in the package `__init__`, those cases resolve to BLOCKED rather than failing.

## TB-05 path guard

- **A-05-1. Bash writes by full-mode roles.** B2 says orchestrator and review write "nowhere", but B5 restricts Bash only for `readonly` roles, and orchestrator is `full` (TB-02 B5). (a) An orchestrator `echo x > file` is allowed by this hook. (b) It is denied, because orchestrator writes nowhere. No case covers it.
- **A-05-2. Redirection inside awk.** "`awk` (without redirection)": (a) only shell redirection after the awk command; (b) also `print > "file"` inside the awk program. Only (a) is tested (D-093).
- **A-05-3. Command substitution in double quotes.** B5 denies "command substitution outside quotes". The shell expands `"$(...)"` inside double quotes. (a) Any quotes exempt it. (b) Only single quotes exempt it. Only the single-quoted form is tested (D-080).
- **A-05-4. "Allowed folders" for roles with none.** B7 requires the allowed folders in every deny reason. What the reason should say for orchestrator, review or an unknown role is not specified. D-111 checks only the role and the path.
- **A-05-5. Implement writing factory control files.** "implement→anywhere except the eval, held-out and frozen-test paths" literally lets implement write `.factory/frozen` or `.factory/profile.yaml`. (a) Allowed, as written. (b) An unintended hole. No case covers it.
- **A-05-6. A new file under a symlinked directory.** "symlinks resolved when the path exists": for `link_dir/new.py`, where the file does not exist but its parent symlink does, (a) the parent is resolved; (b) nothing is resolved. Only existing link targets are tested (D-006, D-044, D-048).

## TB-06 blindness guard

- **A-06-1. Bare `pytest` with no path.** B4(c) covers test runners "on a protected path" and B5 allows commands with no protected path. A bare `pytest` or `python -m pytest` collects from the project root, which contains the evals. (a) Allowed under B5. (b) Denied, like the `.` or no-path rule in B4(b). No case covers it. B7's residual gap may be meant to cover it.
- **A-06-2. The protected directory itself.** Does `evals/**` match `evals`? This matters for a Read of the directory path. For Grep, Glob and Bash the strict-ancestor rule settles it, but no Read case uses the bare directory.
- **A-06-3. Tilde forms.** B4(a) covers "tilde ... forms that could expand to it". When HOME is not the project root, `~/evals/x` expands elsewhere. (a) Denied because it names `evals`. (b) Allowed. Only `~+/evals/...` (current directory) is tested (D-051).
- **A-06-4. `$VAR` with no protected fragment.** "`$VAR` forms that could expand to it": `cat $X/case_a.py` could expand to a protected path for some X. (a) Deny any unresolved variable in a path. (b) Deny only when the rest of the path names a protected fragment, or the variable is `$PWD`. Only `$PWD`, `${PWD}` and a variable assigned `evals` in the same command are tested.
- **A-06-5. Standalone `base64 -d`.** B4(e) lists `base64 -d` under "constructs commands dynamically". A `base64 -d file > out` that feeds no shell: (a) denied because it is listed; (b) allowed because it builds no command. Only the forms piped into `sh` or used inside `$(...)` are tested.
- **A-06-6. `git status` or plain `git diff` with no path.** Their output names or shows protected files, but they are not in the B4(b) list. No case covers them.
- **A-06-7. Unknown agent types.** B1 gives "every other role" an allow. Whether an unknown `agent_type` counts as another role (allow) or should fail closed is not stated. No case covers it.

## TB-07 secrets guard

- **A-07-1. Colon assignments.** B2 covers "an assignment of a quoted value". Whether `"api_key": "..."` (JSON) or `password: "..."` (YAML) counts as an assignment is not stated. Only `=` forms are tested.
- **A-07-2. A quoted variable reference assigned to a secret name.** `password = "${DB_PASSWORD_FROM_ENV}"` (20 or more characters, quoted) matches the B2 assignment rule and the B3 variable-reference allowance at once. No case covers it.
- **A-07-3. Which "value" the placeholder rule inspects.** B4 allows a value that "ends in `...`" or "is a single repeated character". For a key-shaped token, (a) the value is the regex match itself, which never includes trailing dots, so `sk-<40 chars>...` is denied; (b) the value is the surrounding whitespace-delimited token, so it is allowed. The same question arises for `sk-000...0`. The draft case TB07-D-065 was removed for this reason. Placeholder cases that hold under both readings (`xxxx`, `your` inside the token) remain.
- **A-07-4. Case of placeholder words.** Whether `EXAMPLE`, `YOUR` or `CHANGEME` count as placeholders is not stated. Only lowercase forms are tested.
- **A-07-5. `AIza` length.** "`AIza` followed by 35 URL-safe characters" can mean exactly 35 or at least 35. Only 35 (deny) and 34 (allow) are tested.

## TB-08 bash guard

- **A-08-1. Main session with a non-orchestrator `main_session_role`.** B2 and B4 give "`orchestrator` (and the main session)" ask. hook-io maps the main session to `main_session_role`, which could be, say, `test`, and that role gets deny. No case sets a non-orchestrator main-session role for this hook.
- **A-08-2. Bare `rm` and `mv` for implement.** B3 lists "`git stash`, `checkout`, ..., `mv`, `rm`". (a) All of these are git subcommands. (b) Bare `rm` and `mv` are denied too. Only the `git mv` and `git rm` forms are tested.
- **A-08-3. Case of SQL keywords.** Whether B4 matches `drop table` in lowercase is not stated. Only uppercase forms are tested.
- **A-08-4. Nested shells.** In `bash -c "git push --force"`, (a) the `-c` string is parsed and matched; (b) it is a quoted argument and ignored. B5 names only `echo`, `printf` and `git commit -m` as exempt. No case covers it.
- **A-08-5. Scope of the `rm -rf` exemption.** "the project's `node_modules` or `.venv`": whether `./node_modules`, `app/node_modules` or an absolute path to them is exempt is not stated. Only bare `node_modules` and `.venv` are tested.
- **A-08-6. Force push by refspec, and git global options.** `git push origin +main` forces without a flag, and `git -C dir add -A` puts an option before the subcommand. Neither is in the B2 list as written. No case covers them.
