# TB-06: Implement blindness guard hook

| | |
|---|---|
| **Delivers** | R-11, R-21 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Opus |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Make the eval-first rule enforceable: an agent with `blind: true` (only `implement`) cannot read, list, search or run the eval and held-out paths. Other roles are never affected by this hook.

## Required behaviour
1. Applies only when the resolved role is `implement`; every other role always gets allow.
2. Protected paths are `paths.eval` and `paths.held_out`. A path is protected if, after normalisation (against `cwd`, `~` and `$VAR` left literal, `.` and `..` collapsed, symlinks resolved when the path exists), it matches or lies under a protected glob.
3. Read: deny a protected `file_path`. Grep and Glob: deny a protected `path` or `glob`, and deny a `path` that is missing, `.`, or a strict ancestor of a protected path (the reason tells the agent to search a specific source directory).
4. Bash: deny a command that (a) names a protected path in any argument, including relative, absolute, parent (`../`), quoted, glob (`ev*/`, `**/evals`), tilde and `$VAR` forms that could expand to it; (b) runs a recursive search or listing (`grep -r`, `rg`, `find`, `ls -R`, `tree`, `du`, `fd`, `ag`) on `.`, no path, or a strict ancestor of a protected path; (c) runs `pytest`, `python -m pytest`, `unittest` or `node --test` on a protected path; (d) runs an interpreter one-liner (`python -c`, `node -e`, `perl -e`, `ruby -e`, `sh -c`, `bash -c`) whose code names a protected path or calls a directory walker (`os.walk`, `glob`, `rglob`, `listdir`, `scandir`, `readdir`); (e) constructs commands dynamically (`eval`, `base64 -d`, `xxd -r`, `sh|bash -c` containing command substitution, or a pipe into `sh`/`bash`).
5. Bash commands that reference no protected path and do not fall under (b) to (e) are allowed, including normal builds, tests of the agent's own directories, `git diff` of its own files and `ls src`.
6. Deny reasons state that the path is protected without echoing eval file contents; the hook never opens a protected file.
7. Documented residual gap in `docs/hooks/blindness_guard.md`: a script or test run that itself reads the protected paths is not visible to this hook; the OS sandbox is the backstop.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/blindness_guard.py`, `tests/hooks/test_blindness_guard.py`, `docs/hooks/blindness_guard.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Sandbox configuration, other roles' reads.
