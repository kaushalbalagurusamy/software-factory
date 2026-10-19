"""Path guard hook (TB-05): where each role may write, and which Bash a read-only role may run.

Contracts: ``docs/prds/TB-05-path-guard.md``, ``docs/contracts/hook-io.md`` and the binding
clarifications A-05-1..6, U-4 and C-36 in ``docs/contracts/clarifications.md``.

Deterministic and offline: it reads the role specs and the freeze marker from disk and makes no
network or model call. Nothing project-specific is hard-coded; every folder and glob comes from the
profile through :class:`~factory.hooks.core.HookConfig`. Anything malformed fails closed (deny).
"""
from __future__ import annotations

import functools
import os
import re

from factory.agents.roles import RoleSpec, load_roles
from factory.hooks.core import Decision, HookConfig, Payload

# Write tools and the tool_input field naming the file they write (C-38.4).
WRITE_TARGET_FIELDS = {"Write": "file_path", "Edit": "file_path", "MultiEdit": "file_path",
                       "NotebookEdit": "notebook_path"}
FREEZE_MARKER = ".factory/frozen"
# Folders the implement role may never write (C-36 and A-05-5), project-relative.
CONTROL_DIRS: tuple[str, ...] = (".factory", ".claude")

# Read commands a read-only role may start a pipeline segment with (PRD behaviour 5).
READONLY_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("git", "log"), ("git", "diff"), ("git", "show"), ("git", "status"), ("git", "blame"),
    ("ls",), ("cat",), ("head",), ("tail",), ("wc",), ("grep",), ("rg",), ("find",), ("tree",),
    ("sf", "audit"), ("sed", "-n"), ("awk",),
)
# C-38.1: awk words that can write, execute or load code, matched anywhere in its arguments.
_AWK_SUBSTRINGS = ("system", "getline", "close", "fflush", "|", ">", "@load", "@include")
_AWK_SHORT_FLAGS = frozenset("fieElodp")  # -f -i -E -e -l -o -d -p (and clusters / attached values)
_AWK_LONG_FLAGS = ("file", "include", "source", "exec", "load", "pretty-print", "profile", "dump-variables")
# C-38.2: the only sed scripts a read-only role may run (with ``sed -n``).
_SED_ADDR = r"(?:\d+|\$|/(?:[^/\\\n]|\\.)*/)"
_SED_PRINT = re.compile(rf"(?:{_SED_ADDR}(?:,{_SED_ADDR})?)?p\Z")
_SED_FLAGS = re.compile(r"[gpiI0-9]*\Z")
DENIED_COMMANDS = frozenset({"rm", "mv", "cp", "chmod", "tee"})
_FIND_FORBIDDEN = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir",
                             "-fprint", "-fprint0", "-fprintf", "-fls"})


@functools.lru_cache(maxsize=1)
def _roles() -> dict[str, RoleSpec]:
    return load_roles()


# ---- paths -----------------------------------------------------------------------------------
def _resolve(path: str) -> str:
    """Normalise an absolute path, resolving symlinks component by component. For a path that
    does not exist, the nearest existing ancestor is resolved and the rest appended (A-05-6)."""
    cur = os.sep
    for part in path.split(os.sep):
        if part in ("", "."):
            continue
        if part == "..":
            cur = os.path.dirname(cur)
            continue
        cand = os.path.join(cur, part)
        cur = os.path.realpath(cand) if os.path.islink(cand) or os.path.exists(cand) else cand
    return cur


def _lexical(path: str) -> str:
    return os.path.normpath(path)


def _within(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def _rel(path: str, root: str) -> str | None:
    if path == root:
        return ""
    if path.startswith(root.rstrip(os.sep) + os.sep):
        return path[len(root.rstrip(os.sep)) + 1:]
    return None


@functools.lru_cache(maxsize=256)
def _glob_regex(glob: str) -> re.Pattern:
    out: list[str] = []
    i, n = 0, len(glob)
    while i < n:
        if glob.startswith("/**", i) and i + 3 == n:
            out.append("(?:/.*)?")
            i += 3
        elif glob.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif glob.startswith("**", i):
            out.append(".*")
            i += 2
        elif glob[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(glob[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches(rel: str, globs: tuple[str, ...]) -> str | None:
    """The first glob matching ``rel`` or one of its ancestor folders, else None."""
    parts = rel.split("/")
    prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
    for g in globs:
        rx = _glob_regex(g)
        if any(rx.match(p) for p in prefixes):
            return g
    return None


def _fmt(items) -> str:
    items = [i for i in items if i]
    return ", ".join(items) if items else "none"


# ---- write tools -----------------------------------------------------------------------------
def _allowed_folders(role: str, writes: str, cfg: HookConfig) -> tuple[str, ...]:
    if writes == "research_dir":
        return (cfg.research_dir,)
    if writes == "design_dirs":
        return tuple(cfg.design_dirs)
    if writes == "audit_dir":
        return (cfg.audit_dir,)
    if writes == "eval_paths":
        return tuple(cfg.eval_globs)
    if writes == "app":
        return ("anywhere in the project except " + _fmt(
            (*cfg.eval_globs, *cfg.held_out, *cfg.frozen_tests, *(c + "/**" for c in CONTROL_DIRS))),)
    return ()


def _deny(role: str, subject: str, allowed: str, why: str) -> Decision:
    return Decision("deny", f"path_guard: role {role} may not {subject}: {why}. Allowed folders: {allowed}.")


def _decide_write(role: str, spec: RoleSpec | None, raw_path, payload: Payload, cfg: HookConfig) -> Decision:
    if not isinstance(raw_path, str) or not raw_path.strip() or "\x00" in raw_path:
        return _deny(role, f"write {raw_path!r}", "unknown", "missing or malformed file_path")
    if spec is None:
        return _deny(role, f"write {raw_path}", "none",
                     f"unknown agent type {role}, no write access for role {role}")
    root = _resolve(os.path.abspath(str(cfg.project_root)))
    base = payload.cwd or root
    if not os.path.isabs(raw_path):
        raw_path = os.path.join(base, raw_path)
    lex = _lexical(raw_path)
    target = _resolve(raw_path)
    folders = _allowed_folders(role, spec.writes, cfg)
    allowed = _fmt(folders)
    subject = f"write {target}"
    no_access = spec.writes == "none"

    if _rel(target, root) is None:
        why = "the path is outside the project root"
        if no_access:
            why += f"; also no write access for role {role}"
        return _deny(role, subject, allowed, why)
    if no_access:
        return _deny(role, subject, allowed, f"no write access for role {role}")
    rel = _rel(target, root)
    lex_rel = _rel(lex, os.path.abspath(str(cfg.project_root)))

    if spec.writes == "app":
        for cdir in CONTROL_DIRS:
            if _within(target, os.path.join(root, cdir)) or (lex_rel is not None and _within(lex_rel, cdir)):
                return _deny(role, subject, allowed, f"{cdir}/** is a protected factory control folder")
        for label, globs in (("eval", cfg.eval_globs), ("held-out", cfg.held_out),
                             ("frozen-test", cfg.frozen_tests)):
            hit = _matches(rel, globs) or (lex_rel is not None and _matches(lex_rel, globs))
            if hit:
                return _deny(role, subject, allowed, f"the path is in the protected {label} paths ({hit})")
        return Decision("allow")

    if spec.writes == "eval_paths":
        if os.path.exists(os.path.join(root, FREEZE_MARKER)):
            if _matches(rel, cfg.baseline_update):
                return Decision("allow")
            return _deny(role, subject, _fmt(cfg.baseline_update),
                         f"the tests are frozen ({FREEZE_MARKER} exists) and only paths.baseline_update is writable")
        if _matches(rel, cfg.eval_globs):
            return Decision("allow")
        return _deny(role, subject, allowed, "the path is outside the role's allowed folders")

    for folder in folders:
        fdir = _resolve(os.path.join(root, folder))
        if _within(target, fdir) and target != fdir:
            return Decision("allow")
    return _deny(role, subject, allowed, "the path is outside the role's allowed folders")


# ---- read-only Bash --------------------------------------------------------------------------
def _scan(command: str):
    """Split a command into pipeline segments of unquoted words. Returns
    ``(segments, has_redirect, has_substitution)`` or raises ValueError on an unterminated quote."""
    segments: list[list[str]] = []
    words: list[str] = []
    cur: list[str] = []
    in_word = False
    redirect = subst = False
    quote = None
    i, n = 0, len(command)

    def end_word():
        nonlocal cur, in_word
        if in_word:
            words.append("".join(cur))
        cur, in_word = [], False

    def end_segment():
        nonlocal words
        end_word()
        if words:
            segments.append(words)
        words = []

    while i < n:
        c = command[i]
        nxt = command[i + 1] if i + 1 < n else ""
        if quote == "'":
            if c == "'":
                quote = None
            else:
                cur.append(c)
        elif quote == '"':
            if c == "\\" and nxt:
                cur.append(nxt if nxt in '"\\$`' else c + nxt)
                i += 1
            elif c == "`" or (c == "$" and nxt == "("):
                subst = True
                cur.append(c)
            elif c == '"':
                quote = None
            else:
                cur.append(c)
        else:
            if c == "\\":
                if nxt:
                    cur.append(nxt)
                    in_word = True
                    i += 1
            elif c in "'\"":
                quote, in_word = c, True
            elif c == "`" or (c == "$" and nxt == "(") or (c == "<" and nxt == "("):
                subst = True
                cur.append(c)
                in_word = True
            elif c == ">":
                redirect = True
                cur.append(c)
                in_word = True
            elif c in "|;&\n":
                end_segment()
            elif c.isspace():
                end_word()
            else:
                cur.append(c)
                in_word = True
        i += 1
    if quote:
        raise ValueError("unterminated quote")
    end_segment()
    return segments, redirect, subst


def _awk_problem(args: list[str]) -> str | None:
    for w in args:
        low = w.lower()
        if any(t in low for t in _AWK_SUBSTRINGS):
            return "awk program or option uses a write, execute or pipe feature"
        if w.startswith("--") and len(w) > 2:
            name = w[2:].split("=", 1)[0]
            if any(opt.startswith(name) for opt in _AWK_LONG_FLAGS):
                return f"awk {w.split('=', 1)[0]} can read code or write files"
        elif w.startswith("-") and len(w) > 1 and any(c in _AWK_SHORT_FLAGS for c in w[1:]):
            return f"awk {w} can read code or write files"
    return None


def _sed_script_ok(script: str) -> bool:
    if _SED_PRINT.match(script):
        return True
    if len(script) < 2 or script[0] != "s":
        return False
    d = script[1]
    if d.isalnum() or d.isspace() or d in "\\":
        return False
    parts, cur, i = [], [], 2
    while i < len(script) and len(parts) < 2:
        c = script[i]
        if c == "\\" and i + 1 < len(script):
            cur.append(script[i:i + 2])
            i += 2
            continue
        if c == d:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    return len(parts) == 2 and bool(_SED_FLAGS.match(script[i:]))


def _sed_problem(words: list[str]) -> str | None:
    if len(words) < 3 or words[1] != "-n":
        return "sed is only allowed as sed -n <print or substitution script> [file...]"
    if not _sed_script_ok(words[2]):
        return "sed script is not a plain print or substitution"
    if any(w.startswith("-") and w != "-" or _sed_script_ok(w) for w in words[3:]):
        return "sed option or second script word after the script"
    return None


def _segment_problem(words: list[str]) -> str | None:
    head = words[0]
    if head in DENIED_COMMANDS:
        return f"{head} is not a read command"
    prefix = next((p for p in READONLY_PREFIXES if tuple(words[:len(p)]) == p), None)
    if prefix is None:
        return f"{head} is not in the read-only command list"
    if prefix == ("find",):
        bad = [w for w in words if w in _FIND_FORBIDDEN]
        if bad:
            return f"find {bad[0]} can modify files"
    if prefix[0] == "git" and any(w.split("=", 1)[0].startswith("--ou") for w in words):
        return "git --output (or an abbreviation) writes a file"
    if prefix[0] == "awk":
        return _awk_problem(words[1:])
    if prefix[0] == "sed":
        problem = _sed_problem(words)
        if problem:
            return problem
    if prefix[0] == "sed" and any(
            w.startswith("-") and not w.startswith("--") and "i" in w[1:] or w.startswith("--in-place")
            for w in words):
        return "sed -i edits files"
    if prefix[0] == "tree" and any(w == "-o" for w in words):
        return "tree -o writes a file"
    if prefix[0] == "rg" and any(w == "--pre" or w.startswith("--pre=") for w in words):
        return "rg --pre runs a command"
    return None


def _decide_bash(role: str, spec: RoleSpec | None, command, cfg: HookConfig) -> Decision:
    shown = command if isinstance(command, str) else repr(command)
    if len(shown) > 200:
        shown = shown[:200] + "..."
    allowed = _fmt(_allowed_folders(role, spec.writes, cfg)) if spec else "none"
    subject = f"run `{shown}`"
    if spec is None:
        return _deny(role, subject, "none", f"unknown agent type {role}, no Bash access")
    if spec.bash == "full":
        return Decision("allow")  # A-05-1: Bash writes are not inspected for full-mode roles
    if spec.bash == "none":
        return _deny(role, subject, allowed, f"role {role} has no Bash access")
    if not isinstance(command, str) or not command.strip():
        return _deny(role, subject, allowed, "missing or empty command")
    try:
        segments, redirect, subst = _scan(command)
    except ValueError as exc:
        return _deny(role, subject, allowed, f"unparseable command ({exc})")
    if subst:
        return _deny(role, subject, allowed, "command substitution is not allowed")
    if redirect:
        return _deny(role, subject, allowed, "redirection is not allowed in a read-only role")
    if not segments:
        return _deny(role, subject, allowed, "no command found")
    for words in segments:
        problem = _segment_problem(words)
        if problem:
            return _deny(role, subject, allowed, f"{problem} (read-only Bash)")
    return Decision("allow")


# ---- entry point -----------------------------------------------------------------------------
def decide(payload: Payload, cfg: HookConfig) -> Decision:
    """Allow or deny a PreToolUse call. Read, Grep, Glob and every other tool are allowed here."""
    if payload.event != "PreToolUse":
        return Decision("allow")
    tool = payload.tool_name
    if not isinstance(tool, str) or not tool:
        return Decision("deny", "path_guard: PreToolUse payload has no tool_name")
    role = cfg.role_for(payload)
    spec = _roles().get(role)
    tool_input = payload.tool_input if isinstance(payload.tool_input, dict) else {}
    if tool in WRITE_TARGET_FIELDS:
        return _decide_write(role, spec, tool_input.get(WRITE_TARGET_FIELDS[tool]), payload, cfg)
    if tool == "Bash":
        return _decide_bash(role, spec, tool_input.get("command"), cfg)
    return Decision("allow")
