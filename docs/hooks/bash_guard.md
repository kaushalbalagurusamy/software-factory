# Hook: `bash_guard` (TB-08)

Module `factory/hooks/bash_guard.py`, hook id `bash_guard`, event PreToolUse, tool Bash only (every other tool or event is allowed). Delivers R-13 (git hygiene) and R-14 (one-way doors). Contracts: `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, clarifications A-08-1 to A-08-6. Deterministic; no network or model call; nothing project-specific is hard-coded (deploy route and extra patterns come from the profile).

## How it decides
1. The command is parsed, not grepped: quotes, escapes, `;` `&&` `||` `|` `&`, newlines, subshells and braces, `$(...)`, backticks, here-documents, `sh|bash|zsh -c '...'` and `eval` strings (A-08-4), `$'..'` strings, and variables assigned earlier in the same command. Each resulting command is inspected after dropping env assignments and wrappers (`sudo`, `env`, `command`, `nohup`, `time`, `timeout`, `nice`...). Text inside quoted arguments to `echo`, `printf`, `grep`, `cat`... and inside `git commit -m` messages is never matched.
2. Role = `agent_type`, else `main_session_role` (A-08-1). `orchestrator` gets `ask`; every other role (including unknown ones) gets `deny`.
3. A command that cannot be parsed (unterminated quote or substitution, nesting deeper than 8) or a Bash payload without a string `command` is denied for every role.
4. Several matches: `deny` outranks `ask`; the first match in command order names the rule. The reason starts `bash_guard <rule>:`, says what was matched, and for `ask` ends with what a human is asked to approve.

## Rules
- Git hygiene (all roles; ask for orchestrator, deny otherwise): `git add -A|--all|.|*`, `--no-verify` (and `git commit -n`, `-c core.hooksPath=`), `git commit --amend`, `git rebase`, `git push` with `--force`, `-f`, `--force-with-lease` or a `+refspec` (A-08-6), `git reset --hard`. Flags may come in any order, in clusters (`-fA`), or as unique long-option prefixes. Git global options (`-C dir`, `-c k=v`, `--git-dir`, `--work-tree`, `--no-pager`...) are skipped before the subcommand.
- `implement` never commits (always deny): git `stash checkout restore reset clean add commit mv rm push merge cherry-pick`. Read-only git (`diff log show status blame`, and anything else not listed) is allowed. Plain `rm`/`mv` are not restricted (A-08-2).
- One-way doors (ask for orchestrator, deny otherwise): `DROP TABLE|DATABASE|COLUMN`, `TRUNCATE`, `DELETE FROM` with no `WHERE` (case-insensitive, A-08-3; also through here-documents and `echo ... | psql`); `terraform|tofu destroy`, `kubectl delete`, `gh repo delete`; `rm` with recursive and force flags (any spelling or order) on any target not under `/tmp` and not at any depth a `node_modules` or `.venv` (A-08-5; `/tmp` itself is not exempt; paths are normalised so `/tmp/../etc` is not exempt; unresolved `$VAR` or `~` targets are not exempt); any command whose words start with `profile.deploy.route`; any command matching a regex in `profile.one_way_door_patterns` (searched in the joined words and the raw segment text).

## Recorded example payloads
Run with `python -m factory.hooks bash_guard` and a profile containing `deploy: {route: "railway up"}`.

Orchestrator, `git add -A`, result `ask` (exit 0):
```
{"session_id":"s","cwd":"/tmp/tb08p","hook_event_name":"PreToolUse","agent_type":"orchestrator","agent_id":"a1","tool_name":"Bash","tool_input":{"command":"git add -A"}}
-> {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"bash_guard git-add-all: git add -A / --all stages every change in the tree. A human is asked to approve running: git add -A"}}
```
Same command, role `test`, result `deny` (exit 2, stderr):
```
bash_guard git-add-all: git add -A / --all stages every change in the tree. Denied for role test; command: git add -A
```
Role `implement`, `git commit -m x`, result `deny` (exit 2):
```
bash_guard implement-no-commit: the implement role never changes the git state: git commit is not allowed
```
Orchestrator, `psql -c 'DROP TABLE users'`, result `ask`: reason `bash_guard sql-drop: destructive SQL: DROP TABLE. A human is asked to approve running: psql -c 'DROP TABLE users'`.
Orchestrator, `railway up`, result `ask`: reason `bash_guard deploy-route: the project's deploy route (railway up) ships to a live environment. ...`.
Orchestrator, `git commit -m 'never git add -A'`: allow (exit 0, empty output), because the text is a commit message.

## Known gaps (not verified or not handled)
Shell aliases (`!cmd` git aliases), `xargs`, `find -exec`, variables set outside the command, `psql -f file.sql` (file contents are not read), and arrays/`case` syntax beyond splitting are not interpreted. Unit tests: `tests/hooks/test_bash_guard.py`.
