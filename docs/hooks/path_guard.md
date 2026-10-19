# Hook: path_guard (TB-05)

Delivers R-06 and R-10. Module `factory/hooks/path_guard.py`, hook id `path_guard`, registered on `PreToolUse` with matcher `Write|Edit|Bash`. Contracts: `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, and clarifications A-05-1..6, U-4, C-36.

## What it decides

The role is `payload.agent_type`, or the profile's `main_session_role` when absent. The role's write and Bash modes come from the shipped role specs (`factory/agents/roles/*.yaml`); every folder and glob comes from the profile. An unknown agent type is denied for Write, Edit and Bash.

| Role | Write / Edit allowed in |
|---|---|
| research | `paths.research_dir` |
| design | `paths.design_dirs` |
| audit | `paths.audit_dir` |
| test | `paths.eval` before the freeze; only `paths.baseline_update` once `.factory/frozen` exists |
| implement | anywhere except `paths.eval`, `paths.held_out`, `paths.frozen_tests`, `.factory/**` and `.claude/**` (A-05-5, C-36) |
| orchestrator, review | nowhere (`no write access for role <role>`) |

- Target paths are resolved against `cwd`, normalised, and symlinks are resolved; for a path that does not exist the nearest existing ancestor is resolved and the remaining segments appended (A-05-6). A path outside the project root is denied for every role.
- A glob also covers everything under a folder it matches (`evals/**` matches `evals` itself). `*` does not cross `/`; `**` does.
- Bash for a role whose `bash` mode is `full` is not inspected (A-05-1). For `readonly` roles (research, design, audit, review) every pipeline segment (split on `|`, `;`, `&`, newline) must start with one of `git log|diff|show|status|blame`, `ls`, `cat`, `head`, `tail`, `wc`, `grep`, `rg`, `find`, `tree`, `sf audit`, `sed -n`, `awk`. Denied: any `>` redirection outside quotes (so `2>&1` is denied too), `tee`, `rm`, `mv`, `cp`, `chmod`, `find -delete/-exec` (and `-execdir`, `-ok`, `-okdir`, `-fprint*`, `-fls`), and command substitution (`$(`, backticks, `<(`) unless inside single quotes (A-05-3). Extra hardening beyond the PRD list: `sed -i`, `git ... --output`, `tree -o`, `rg --pre`, unparseable (unterminated quote) commands.
- Read, Grep, Glob and every other tool are allowed (blindness is TB-06). Malformed input (missing or non-string `file_path` or `command`, no `tool_name`) is denied.
- Every deny reason names the role, the path or command, and the allowed folders.

## Documented gaps

Redirection inside an awk program (A-05-2); anything a script file does when run; Bash writes by full-mode roles (A-05-1); `sed` script commands such as `w`.

## Recorded example

Run with a profile containing `paths.eval: [evals/**]` in the project's `.factory/profile.yaml`:

```
$ echo '{"session_id":"s1","cwd":"<root>","hook_event_name":"PreToolUse","permission_mode":"default","agent_type":"research","agent_id":"a1","tool_name":"Write","tool_input":{"file_path":"src/app.py","content":"x"}}' | python -m factory.hooks path_guard
path_guard: role research may not write <root>/src/app.py: the path is outside the role's allowed folders. Allowed folders: research.
exit=2

$ echo '{... "agent_type":"audit","tool_name":"Bash","tool_input":{"command":"git log | tee out"}}' | python -m factory.hooks path_guard
path_guard: role audit may not run `git log | tee out`: tee is not a read command (read-only Bash). Allowed folders: docs/audit.
exit=2
```

An allowed call exits 0 with empty stdout (for example the same research payload with `research/notes.md`).

## Tests

`tests/hooks/test_path_guard.py` (unit coverage, not the acceptance gate): `.venv/bin/python -m pytest tests/hooks/test_path_guard.py`.
