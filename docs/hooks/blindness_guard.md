# Blindness guard (`factory.hooks.blindness_guard`)

The mechanical half of "implement blind" (TB-06, requirements R-11 and R-21): a blind role cannot read, list, search or run the profile's `paths.eval` and `paths.held_out` globs. Contracts: `docs/prds/TB-06-blindness-guard.md`, `docs/contracts/hook-io.md`, and the binding clarifications A-06-1 to A-06-7, U-1, U-2 and C-36 in `docs/contracts/clarifications.md`. Matcher (A-34): `Read|Grep|Glob|Bash`, PreToolUse.

Deterministic and offline (R-09): it reads the payload, the profile, `$HOME` and file-system metadata only (lstat, readlink, and directory names while expanding a glob outside protected folders). It never opens a file and never lists a protected folder. Nothing project-specific is hard-coded (R-01): protected paths come from the profile; `.factory/` and `.claude/` are the factory's own control folders named by C-36.

## Who it applies to
- The role is `cfg.role_for(payload)` (`agent_type`, or `main_session_role` for the main session). It applies when that role's spec has `blind: true` (only `implement`) or the agent type is unknown (A-06-7). Every other role gets allow, whatever the payload.
- Events other than PreToolUse and tools other than Read, Grep, Glob and Bash are allowed (Write and Edit belong to the path guard).
- A blind-role PreToolUse payload with no `tool_name`, a missing or non-string `file_path`, `command`, `path` or `glob`, a NUL byte, an unparseable command, or any input past a size cap is denied (fail closed).

## Path normalisation
A word or tool path is protected when, after normalisation, it matches or lies under a protected glob (`evals/**` also matches `evals` itself, A-06-2). Normalisation: relative to the payload `cwd` (and to `cd`, `pushd`, `env -C` and `git -C` targets earlier in the same command); `.` and `..` collapsed; symlinks resolved component by component when the path exists; both the lexical and the resolved form are checked.
- **Tilde (A-06-3):** `~` is `$HOME` and `~+` the working directory, and only that expansion is used: `~/evals/x` is denied only when `$HOME/evals/x` falls in the project's protected paths (for example when `$HOME` is the project root), and allowed when `$HOME` is elsewhere. `~-` and `~user` are unresolvable and denied if the rest of the path is empty or names a protected fragment.
- **Variables (A-06-4, U-2):** a variable assigned in the same command (`X=v`, `export`, `declare`, `local`, `readonly`, `typeset`, `for X in ...`) is expanded first, with every assigned value tried. An unresolved `$VAR` is denied when it is `PWD`, `OLDPWD` or `HOME`, when the text after it names a protected directory segment, or when it contains a protected glob match; a bare file name (`$X/foo.py`) is allowed. Protected directory segments are the first named segment of each glob plus every named folder in it, so `tests/held_out/**` contributes `tests` and `held_out`; a final segment with a `.` or `*` (a file name) never counts. A known folder before the variable counts too (`evals/$X`). Single-quoted `$` is literal.
- **Quoting and escapes:** `"ev"'als'`, `e\vals` and ANSI-C `$'\x65vals'` are de-quoted before checking.
- **Globs:** `*`, `?`, `[...]` and `**` in a word are compared segment by segment with the protected globs (`ev*/`, `*/cases`, `**/evals` are protected); a shell wildcard does not match a leading dot. Globs are also expanded on disk (outside protected folders, capped) so a wildcard that reaches a symlink into a protected folder is caught. Brace lists `{a,b}` are expanded; `{x..y}` sequences are treated as `*`.
- **Word parts:** the value after `=` (`--file=evals/x`, `of=`, `PYTHONPATH=src:evals`), `:`-separated parts (`HEAD:evals/x`) and a value glued to a short option (`-fevals/x`) are checked as paths.
- **Outside the project:** globs are project-relative, so a path outside the project root is not protected (`/etc/evals/x`, `~/evals/x` with `$HOME` elsewhere, A-06-3), with one exception: a path whose argument is written with `..` segments (`../evals`, `./../evals`, `../../evals/x`) and whose normalised form leaves the project is denied when its trailing segments match a protected glob (PRD 4a parent form, for example a sibling checkout). The carve-out is by how the path is written: `~` and `$HOME` expansion alone never triggers it. The root's own ancestors (`..`, `/`, a `$HOME` above the project) count as ancestors.
- **Ancestor:** the project root, anything above it, or a strict ancestor of a folder a glob names, reading `**` as no folder. A leading `**` therefore does not make every folder an ancestor: with `**/held_out`, `src` is an ancestor only if `src/held_out` exists (a direct-child check; nothing is walked).

## Decisions
| Tool | Denied |
|---|---|
| Read | a protected `file_path` (control folders stay readable, C-36.3) |
| Grep, Glob | a missing, empty or `.` `path`; a protected or ancestor `path`; a `glob` (Grep) or `pattern` (Glob) that escapes the path (absolute, `~`, `../`) and names a protected path. A relative pattern that stays under an allowed path is not widened by its `*` or `**`; it is checked against what exists on disk instead: every existing prefix is resolved through symlinks and wildcards are expanded (`**` as one level and as none, never inside a protected folder), so `src/link -> ../evals` reached by `**/*.py` is denied while a plain `src` is allowed. The reason tells the agent to search a specific source directory. |
| Bash (a) | any word or redirection target that names a protected path in any of the forms above, at any nesting level (substitutions, `sh -c`, heredoc scripts) |
| Bash (b) | a recursive search or listing (`grep -r/-R/--recursive/-d recurse`, `rgrep`, `rg`, `ag`, `ack`, `find`, `ls -R`, `tree`, `du`, `fd`, recursive `cp`/`scp`/`rsync`/`zip`, `tar` creating an archive) on `.`, no path, an unknown working directory, or an ancestor; `locate`. The value of `find -name`, `-iname`, `-path`, `-ipath`, `-wholename`, `-regex` and `-lname` is a file-name filter, not a path. |
| Bash (c) | `pytest`, `py.test`, `python -m pytest` or `python -m unittest` with no path (A-06-1) or a protected or ancestor path (`::node` ids stripped, dotted unittest names read as paths); `unittest discover` without `-s`, or with an ancestor start; `node --test` with no file or an ancestor |
| Nested commands | each `find -exec/-execdir/-ok/-okdir` list (up to `;` or `+`, `{}` replaced by a placeholder) and each `fd -x/--exec/-X/--exec-batch` list is analysed as its own command one level deeper; `script -c` code as `sh -c`; awk (`awk`, `gawk`, `mawk`, `nawk`) programs from the first operand or `-e`/`--source` are denied when they contain `system(` or a pipe (`|`, which covers `cmd \| getline` and `print \| "cmd"`), and otherwise have every token checked like a Bash word; `vim`, `vi`, `nvim`, `view`, `ex`, `less`, `more` commands from `-c`, `--cmd`, `-S` and `+cmd` are denied when they contain `!` or `system(` and are token-checked |
| Bash (d) | `python -c`, `node -e/-p/--eval`, `perl -e`, `ruby -e`, `sh -c`, `bash -c` (and heredoc or `-` programs for these interpreters) whose code names a protected path or fragment, or calls a directory walker (`walk`, `glob`, `rglob`, `iglob`, `listdir`, `scandir`, `readdir`, `opendir`, `iterdir`, `File::Find`, `Dir.glob`, ...) |
| Bash (e) | `eval`; `base64 -d/--decode` (even standalone, A-06-5); `xxd -r`; `sh`/`bash -c` code that contains a command substitution; a pipe into a shell, or a program piped into python/node/perl/ruby; `source` of stdin or of a substitution; a shell running `<(...)`; `env -S`; a command name built from a variable or substitution; `flock -c` code is analysed as `sh -c` |
| git (A-06-6, U-1) | `log`, `show`, `blame`, `annotate`, `grep`, `ls-files`, `ls-tree`, `cat-file`, `archive`, `whatchanged`, `format-patch`, `diff-tree`, `fast-export`, `bundle` unless every pathspec after `--` is neither protected nor an ancestor (pathspec magic `:(...)` is denied); `git -c` or `git config` of an alias or a command-running key (pager, editor, textconv, ...). `git status`, `git diff` and other subcommands are allowed. |
| C-36 | for `.factory/` and `.claude/` (the folder itself or below, any form above, cwd inside counts): write targets (redirections `>`, `>>`, `>|`, `&>`, `n>`, `<>`; `tee`; destination of `cp`, `mv`, `rsync`, including `-t`; every operand of `install` and `ln`/`ln -s` (target and link path); operands of `rm`, `rmdir`, `touch`, `truncate`, `mkdir`, `chmod`, `chown`, `chgrp`, `shred`, `unlink`, `patch` (and its `-o`, `-d`, `-r`), `sed -i`, `perl -i`, `ruby -i`; `dd of=`), and every argument or code token of an interpreter one-liner. Security addendum: every word and option value of `curl` and `wget` (plus the working directory for `curl -O/-J` and for `wget` without `-O`/`-P`), of `tar` when extracting, of `unzip`, of `sort -o/--output`, and of `git checkout`, `restore`, `apply`, `am`, `reset`, `stash`, `switch` (pathspecs and `--directory=`); `tar -x` and `unzip` are also denied when the destination (`-C`/`--directory`, `-d`, or the working directory) is a control folder or a folder holding one, such as the project root. Reads stay allowed (`cat .claude/settings.json`). |

Commands are seen through wrappers (`env`, `sudo`, `doas`, `nice`, `nohup`, `time`, `command`, `exec`, `stdbuf`, `timeout`, `ionice`, `xargs`, `watch`, `strace`, `npx`, `busybox`, `uv/poetry/pipenv/pdm/conda/hatch run`, `npm/pnpm exec`), leading assignments, keywords and `#` comments.

Everything else is allowed: builds, tests of the agent's own folders (`pytest tests/unit`), `git diff`, `git log -- src`, `ls`, `ls src`, `grep -rn foo src`, `cat .factory/profile.yaml`, writes outside the control folders.

**Bounds (fail closed):** command 100,000 characters, 5,000 words, word or path 4,096 characters, 256 path segments, nesting depth 6, 256 brace or variable alternatives per word, 64 braces per word, 64 values per variable, 50,000 path checks, 20,000 directory entries and 2,000 live glob candidates per decision. The lexer and the glob matcher are iterative; nothing recurses on input size.

Deny reasons start `blindness_guard:` and quote only the word the agent typed (truncated to 120 characters), never file contents.

## Example (recorded run)
```
$ cat > /tmp/p.json <<'JSON'
{"session_id":"s","cwd":"/work/demo","hook_event_name":"PreToolUse","permission_mode":"default","agent_type":"implement","tool_name":"Bash","tool_input":{"command":"cat evals/case1.yaml"}}
JSON
$ python -m factory.hooks blindness_guard < /tmp/p.json; echo "exit=$?"   # /work/demo/.factory/profile.yaml: eval [evals/**], held_out [held_out/**]
blindness_guard: the command names a protected eval/held-out path ('evals/case1.yaml'); a blind role works from the brief and the published contracts only
exit=2
```
Other commands in the same project, same payload shape:
| `command` | exit | stderr |
|---|---|---|
| `grep -r TODO .` | 2 | `blindness_guard: recursive grep on '.' would cover protected eval/held-out paths; search a specific source directory instead` |
| `pytest` | 2 | `blindness_guard: pytest without a path collects tests from the project root, which contains protected eval/held-out paths (A-06-1); name your own test folder or file` |
| `echo x > .factory/profile.yaml` | 2 | `blindness_guard: write target '.factory/profile.yaml' is under a protected factory control folder (.factory/ or .claude/)` |
| `pytest tests/unit -q` | 0 | (empty) |

A Grep payload `{"tool_name":"Grep","tool_input":{"pattern":"x"}}` exits 2 with `blindness_guard: Grep without a specific path would search the working directory, which contains protected eval/held-out paths; search a specific source directory (for example the slice's own source folder) instead`. In Python: `decide(parse_payload(text), HookConfig.from_profile(profile, root))` returns `Decision("deny", ...)` or `Decision("allow")`.

## Residual gaps (documented, not closed)
- **Scripts and test runs (B7, capability map "Blindness limits"):** a script or test run that itself reads the protected paths is not visible to this hook (`python build.py`, `bash scripts/x.sh`, `make test`, `npm test`, a conftest that opens `evals/`). Permission deny rules do not stop a shell command or script that reads the files without naming them; the OS sandbox is the backstop.
- **Text built at run time (OS sandbox is the backstop):** file names computed when a command or program runs are not reconstructed: unresolved command substitutions (`"$(printf 'ev')als/x"`), variables set by `read`, `printf -v` or `mapfile`, string building inside interpreter one-liners, awk, find/fd `-exec` and vim programs (`'eva'+'ls'`, `subprocess`, `os.popen`), and pipelines such as `ls | xargs cat` or `printf '\x65vals' | xargs cat`. The guard checks only the text written in the command.
- **git (A-06-6 allows `git diff`):** `git diff <rev>` and similar read-only subcommands outside the U-1 list (`git stash show -p`, `git reflog -p`) can print the content of protected files between revisions; aliases already in git config are invisible. The OS sandbox is the backstop.
- **Symlinks inside a searched folder:** `grep -R`, `find -L` or `rg -L` on an allowed folder that contains a symlink into a protected folder are not caught; the Glob tool's `**` is expanded on disk one level deep (and as no level), so a symlink into a protected folder two or more levels below the searched path is not seen.
- **Outside the project:** another checkout or worktree of the same project (`/elsewhere/clone/evals/x`) is not protected, because the globs are project-relative (the A-06-3 reading confirmed in QA). With a leading `**` glob, a protected folder deeper than a direct child of a searched folder is not seen.
- **Over-blocking accepted by the literal rules:** any word that resolves to a protected path is denied even when it is a search pattern or message (`grep -n evals src`, `pytest src --ignore=evals`), except `find` name filters; `$HOME`, `$PWD` and `$OLDPWD` in any path are denied (A-06-4); a quoted lone `*` counts as a glob; any single `|` in an awk program (even inside a regex) is denied; `tar -x` or `unzip` into the project root is denied.

## Shape decisions where the contracts are silent (unverified against the gate)
- Blindness is read from the role spec's `blind` flag, which only `implement` sets; an unknown agent type is blind.
- `mv` sources under a control folder count as write targets (moving a file out writes the folder).
- `git` content commands beyond the A-06-6 list (`annotate`, `whatchanged`, `format-patch`, `diff-tree`, `fast-export`, `bundle`) follow U-1.
