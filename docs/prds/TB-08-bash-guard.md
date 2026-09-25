# TB-08: Bash guard hook: git hygiene and one-way doors

| | |
|---|---|
| **Delivers** | R-13, R-14 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Block unsafe git and destructive commands, and pause a human before irreversible operations.

## Required behaviour
1. Applies to Bash only. Splits the command into pipeline and `&&`/`;` segments and inspects each.
2. Git hygiene, all roles: `git add -A`, `git add --all`, `git add .`, `git add *`, `--no-verify`, `git commit --amend`, `git rebase`, `git push` with `--force`, `-f` or `--force-with-lease`, and `git reset --hard`. For `orchestrator` (and the main session) these return `ask`; for every other role `deny`.
3. Implement never commits: for `implement`, deny `git stash`, `checkout`, `restore`, `reset`, `clean`, `add`, `commit`, `mv`, `rm`, `push`, `merge`, `cherry-pick`; read-only git (`diff`, `log`, `show`, `status`, `blame`) is allowed.
4. One-way doors for `orchestrator` and the main session return `ask`: destructive SQL (`DROP TABLE`, `DROP DATABASE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM` with no `WHERE`), resource deletion (`terraform destroy`, `kubectl delete`, `gh repo delete`, `rm -rf` outside `/tmp` and the project's `node_modules` or `.venv`), any command that starts with `profile.deploy.route`, and any command matching a regex in `profile.one_way_door_patterns`. For other roles the same commands are denied.
5. A command with no match is allowed. Matching is on the parsed command, not on substrings inside quoted arguments to `echo`, `printf` or `git commit -m` messages.
6. The reason names the rule that matched and, for `ask`, what a human is being asked to approve.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/bash_guard.py`, `tests/hooks/test_bash_guard.py`, `docs/hooks/bash_guard.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Secrets, reads, writes to files.
