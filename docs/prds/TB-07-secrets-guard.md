# TB-07: Secrets guard hook

| | |
|---|---|
| **Delivers** | R-12, R-23 (see `docs/factory/requirements.md`) |
| **Depends on** | TB-04 |
| **Kind** | PAR (wave 3) |
| **Implementer model** | Sonnet |
| **Published contracts** | `docs/contracts/hook-io.md`, `docs/contracts/profile.md`, `docs/contracts/clarifications.md` (binding) |

## Purpose
Stop a secret value from being written into a file or typed into a command by any agent.

## Required behaviour
1. Inspects Write `content`, Edit `new_string` and Bash `command`, for every role. Other tools are allowed.
2. Denies content containing a value that matches: `sk-or-v1-` followed by at least 20 hex characters; `sk-ant-` followed by at least 20 URL-safe characters; `sk-` followed by at least 32 alphanumerics; `ghp_`, `gho_`, `ghs_`, `github_pat_` followed by at least 20 alphanumerics or underscores; `glpat-` followed by at least 20; `AKIA` followed by 16 uppercase alphanumerics; `xox[baprs]-` followed by at least 10; `AIza` followed by 35 URL-safe characters; a PEM private-key header (`-----BEGIN ... PRIVATE KEY-----`); and an assignment of a quoted value of at least 16 characters to a name containing `api_key`, `apikey`, `secret`, `token` or `password` (case-insensitive).
3. Allows references by variable name (`$OPENROUTER_API_KEY`, `${GITHUB_TOKEN}`, `os.environ["X"]`, `process.env.X`) and bare mentions of a key's shape or name without a value.
4. Allows obvious placeholders: a value that is a single repeated character, contains `xxxx`, `example`, `placeholder`, `your`, `changeme`, `<` or `>`, or ends in `...`.
5. Allows values matching any regex in `profile.secret_allow_patterns`.
6. Deny reasons name the pattern kind and the line number, never the matched value.
7. The hook never logs or persists the content it inspected.

## Acceptance
Graded by golden and diagnostic evals you cannot see. Write your own unit tests under the paths you own (they are unit coverage, not the gate). Document the component in the `docs/hooks/` file you own, with one example payload or call (requirement R-24). Every behaviour above is a promise; where a behaviour and a contract disagree, stop and report instead of choosing.

## Ownership
- **OWN:** `factory/hooks/secrets_guard.py`, `tests/hooks/test_secrets_guard.py`, `docs/hooks/secrets_guard.md`
- **DO-NOT-EDIT:** `evals/**`, `docs/contracts/**`, `docs/factory/**`, `docs/prds/**`, `pyproject.toml`, `requirements.txt`, `factory/__init__.py`, `factory/cli.py`, any file another slice owns
- Do not run git commands that touch the working tree; report the files you changed and the test command you ran.
- Never read, list, search or run anything under `evals/`.

## Out of scope
Scanning existing files; reads.
