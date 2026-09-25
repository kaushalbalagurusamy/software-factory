# TB-05: Path guard hook

| | |
|---|---|
| **Delivers** | R-06, R-10 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, `docs/contracts/roles-and-generation.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Restrict where each role may write, and restrict read-only roles to a list of read commands.

## Required behaviour
1. The role is `payload.agent_type`, or the main-session role when absent. Unknown agent types are denied for Write, Edit and Bash.
2. For Write and Edit, the target path (resolved against `cwd`, normalised, symlinks resolved when the path exists) must lie inside the role's allowed folders: research→`paths.research_dir`; design→`paths.design_dirs`; audit→`paths.audit_dir`; test→`paths.eval` before the freeze; implement→anywhere except the eval, held-out and frozen-test paths; orchestrator and review→nowhere (deny).
3. The freeze: if the file `.factory/frozen` exists under the project root, `test` may write only inside `paths.baseline_update`; otherwise deny with a reason naming the freeze.
4. Any path that resolves outside the project root is denied for every role.
5. For Bash with a role whose `bash` mode is `readonly`, only commands whose every pipeline segment starts with one of: `git log`, `git diff`, `git show`, `git status`, `git blame`, `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`, `find` (without `-delete` or `-exec`), `tree`, `sf audit`, `sed -n`, `awk` (without redirection) are allowed; redirections (`>`, `>>`, `tee`), `rm`, `mv`, `cp`, `chmod` and command substitution outside quotes are denied.
6. Read, Grep and Glob are always allowed by this hook (reads are governed by the blindness hook).
7. Every deny reason names the role, the offending path or command, and the allowed folders.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/path_guard.py`, `tests/hooks/test_path_guard.py`, `docs/hooks/path_guard.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Read restrictions, secrets, git rules.
