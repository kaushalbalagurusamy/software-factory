"""Blindness guard hook (TB-06): the mechanical half of "implement blind".

A blind role (``blind: true`` in its role spec, i.e. ``implement``; an unknown agent type is blind
too, A-06-7) may not read, list, search or run the profile's ``paths.eval`` and ``paths.held_out``
globs. For the same roles, Bash write targets and interpreter one-liner arguments under the
factory control folders ``.factory/`` and ``.claude/`` are denied (C-36). Every other role is
always allowed.

Contracts: ``docs/prds/TB-06-blindness-guard.md``, ``docs/contracts/hook-io.md`` and the binding
clarifications A-06-1..7, U-1, U-2 and C-36 in ``docs/contracts/clarifications.md``.

Deterministic and offline: it reads the payload, the profile, ``$HOME`` and file-system metadata
(lstat, readlink, and directory names while expanding a glob outside protected folders). It never
opens a file and never lists a protected folder. Input length, word count, nesting depth, brace
and variable expansions, glob hits and path checks are all capped; past a cap, or on anything
malformed, it denies (fail closed).
"""
from __future__ import annotations

import fnmatch
import functools
import os
import re
from dataclasses import dataclass, field

from factory.agents.roles import load_roles
from factory.hooks.core import Decision, HookConfig, Payload

CONTROL_GLOBS: tuple[str, ...] = (".factory/**", ".claude/**")  # C-36, project-independent
STRICT_VARS = frozenset({"PWD", "OLDPWD", "HOME"})  # A-06-4

MAX_COMMAND = 100_000   # characters in one Bash command
MAX_WORDS = 5_000       # words in one command, all nesting levels together
MAX_WORD = 4_096        # characters in one word or path
MAX_SEGMENTS = 256      # path segments
MAX_DEPTH = 6           # nested substitutions, sh -c and heredoc scripts
MAX_ALTS = 256          # brace or variable alternatives of one word
MAX_BRACES = 64         # "{" characters in one word
MAX_VALUES = 64         # values recorded for one variable
MAX_CHECKS = 50_000     # path classifications per decision
MAX_SCAN = 20_000       # directory entries read while expanding globs
MAX_GLOB_HITS = 2_000   # live candidates while expanding one glob

LIT = "\x01"            # a literal "$" (single-quoted or escaped)
UNK = "\x02"            # an unresolved variable or command substitution
SUBST = "${__subst__}"  # stands for a command or process substitution inside a word

EVAL, CTRL = "eval", "ctrl"

_WILD = re.compile(r"[*?\[]")
_VAR = re.compile(r"\$(?:\{([^}]*)\}|([A-Za-z_][A-Za-z0-9_]*)|([0-9@*#?$!-]))")
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]")
_ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\+?=(.*)\Z", re.S)
_SEQ_BRACE = re.compile(r"(?<!\$)\{[^{}]*\.\.[^{}]*\}")
_WALKER = re.compile(r"\b(?:f?walk|[ri]?glob|globSync|listdir|scandir|readdir(?:Sync)?|opendir(?:Sync)?"
                     r"|iterdir)\b|File::Find|Find\.find|Dir\.(?:entries|children|each_child|\[)")
_CODE_TOKEN = re.compile(r"[^\s'\"(),;`<>|&!]+")
_FRAG_SPLIT = re.compile(r"[/{}:=+#%,]")
_GIT_EXEC_KEY = re.compile(r"alias\.|.*(?:pager|editor|sshcommand|fsmonitor|textconv|hookspath|askpass"
                           r"|\.command|\.cmd|\.process|\.clean|\.smudge|\.tool|gitproxy|helper|program)"
                           r"|diff\.external")

_WRITE_REDIRS = frozenset({">", ">>", ">|", "&>", "&>>", "<>", ">&"})
_REDIR_OPS = ("&>>", "&>", "<<<", "<<-", "<<", "<>", "<&", ">>", ">|", ">&", "<", ">")
KEYWORDS = frozenset({"if", "then", "elif", "else", "fi", "do", "done", "while", "until", "for",
                      "select", "case", "esac", "function", "time", "!", "{", "}", "[[", "coproc"})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "mksh", "ash", "fish"})
_PYTHON = re.compile(r"(?:python|pypy)[0-9.]*\Z")
_PERL = re.compile(r"perl[0-9.]*\Z")
_RUBY = re.compile(r"ruby[0-9.]*\Z")
# wrapper -> (short options with a value, long options with a value, positional words to skip)
WRAPPERS: dict[str, tuple[str, tuple[str, ...], int]] = {
    "env": ("uCS", ("--unset", "--chdir", "--split-string"), 0),
    "sudo": ("ugCDhpUrtT", ("--user", "--group", "--chdir", "--host", "--prompt"), 0),
    "doas": ("uC", (), 0), "nice": ("n", ("--adjustment",), 0), "nohup": ("", (), 0),
    "time": ("fo", ("--format", "--output"), 0), "command": ("", (), 0), "builtin": ("", (), 0),
    "exec": ("a", (), 0), "stdbuf": ("ioe", ("--input", "--output", "--error"), 0),
    "timeout": ("sk", ("--signal", "--kill-after"), 1), "ionice": ("cnpt", ("--class", "--classdata"), 0),
    "xargs": ("IdnLPsaE", ("--delimiter", "--max-args", "--max-lines", "--max-procs", "--max-chars",
                           "--arg-file", "--eof", "--replace"), 0),
    "watch": ("nd", ("--interval",), 0), "strace": ("oepsSuEaIX", (), 0), "ltrace": ("oepsSuEaIX", (), 0),
    "unbuffer": ("", (), 0), "npx": ("p", ("--package",), 0), "bunx": ("", (), 0), "busybox": ("", (), 0),
}
SUB_WRAPPERS = {"uv": "run", "poetry": "run", "pipenv": "run", "pdm": "run", "conda": "run",
                "hatch": "run", "pnpm": "exec", "npm": "exec"}
_SUB_LONG = ("--with", "--python", "--extra", "--group", "--name", "--prefix", "--package", "--project",
             "--directory", "--env-file", "--index", "--from")
GIT_WRITES = frozenset({"checkout", "restore", "apply", "am", "reset", "stash", "switch"})
FIND_FILTERS = frozenset({"-name", "-iname", "-path", "-ipath", "-wholename", "-iwholename", "-regex",
                          "-iregex", "-lname", "-ilname"})
AWKS = frozenset({"awk", "gawk", "mawk", "nawk"})
EDITORS = frozenset({"vim", "vi", "nvim", "view", "ex", "less", "more"})
GIT_READS = frozenset({"log", "show", "blame", "annotate", "grep", "ls-files", "ls-tree", "cat-file",
                       "archive", "whatchanged", "format-patch", "diff-tree", "fast-export", "bundle"})
_PYTEST_LONG = ("--deselect", "--ignore", "--ignore-glob", "--rootdir", "--confcutdir", "--junitxml",
                "--junit-xml", "--cov", "--cov-report", "--cov-config", "--timeout", "--durations",
                "--durations-min", "--maxfail", "--tb", "--log-level", "--log-file", "--log-cli-level",
                "--basetemp", "--import-mode", "--capture", "--override-ini", "--dist", "--numprocesses",
                "--maxprocesses", "--color", "--show-capture", "--count", "--reruns", "--html",
                "--json-report-file", "--report-log", "--log-format", "--log-date-format",
                "--log-file-level", "--pythonwarnings")


class _Deny(Exception):
    """Carries the deny reason (without the ``blindness_guard:`` prefix)."""


@functools.lru_cache(maxsize=1)
def _roles():
    return load_roles()


def _is_blind(role: str) -> bool:
    spec = _roles().get(role)
    return spec is None or bool(spec.blind)


def _show(text: str) -> str:
    text = text.replace(LIT, "$").replace(UNK, "?").replace("\n", " ")
    return text if len(text) <= 120 else text[:120] + "..."


# ---- paths and globs -------------------------------------------------------------------------
def _resolve(path: str) -> str:
    """Normalise an absolute path, resolving symlinks component by component; for a path that
    does not exist the nearest existing ancestor is resolved and the rest appended."""
    cur = os.sep
    for part in path.split(os.sep):
        if part in ("", "."):
            continue
        if part == "..":
            cur = os.path.dirname(cur)
            continue
        cand = os.path.join(cur, part)
        cur = os.path.realpath(cand) if os.path.lexists(cand) else cand
    return cur


def _norm(path: str) -> str:
    p = os.path.normpath(path)
    return "/" + p.lstrip("/") if p.startswith("//") else p


def _rel(path: str, root: str) -> str | None:
    if path == root:
        return ""
    prefix = root.rstrip(os.sep) + os.sep
    return path[len(prefix):] if path.startswith(prefix) else None


def _segs(glob: str) -> tuple[str, ...]:
    return tuple(p for p in glob.split("/") if p not in ("", "."))


def _dir_segments(g: tuple[str, ...]) -> list[str]:
    """U-2 protected directory segments of a glob: its first named segment (``evals``) and every
    named folder in it (``held_out`` in ``tests/held_out/**``). A final segment counts only when it
    has no ``*`` or ``.``, so a bare file name such as ``h.py`` is never one."""
    out = []
    for k, p in enumerate(g):
        final = k + 1 == len(g)
        if p == "**" or (final and ("." in p or "*" in p)):
            continue
        if "*" not in p or not out:  # the first named segment counts even with a wildcard (ev*/**)
            out.append(p)
    return list(dict.fromkeys(out))


def _compat(a: str, g: str, wild: bool) -> bool:
    """Could path segment ``a`` (a shell word, wildcards allowed when ``wild``) name the same
    file as glob segment ``g``?"""
    aw = wild and _WILD.search(a) is not None
    gw = "*" in g
    if not aw and not gw:
        return a == g
    if aw and not a.startswith(".") and g.startswith("."):
        return False  # a shell wildcard does not match a leading dot
    if aw and gw:
        return True
    return fnmatch.fnmatchcase(g, a) if aw else fnmatch.fnmatchcase(a, g)


def _match(a: list[str] | tuple[str, ...], g: tuple[str, ...], wild: bool = True) -> int:
    """2 if ``a`` matches or lies under glob ``g``, 1 if it is a strict ancestor of something ``g``
    could match, else 0. Iterative search over (i, j) states, so it is bounded and never recurses."""
    la, lg = len(a), len(g)
    star_tail = [False] * lg + [True]
    for j in range(lg - 1, -1, -1):
        star_tail[j] = star_tail[j + 1] and g[j] == "**"
    seen: set[tuple[int, int]] = set()
    stack = [(0, 0)]
    ancestor = False
    while stack:
        state = stack.pop()
        if state in seen:
            continue
        seen.add(state)
        i, j = state
        if j == lg:
            return 2
        if i == la:
            if star_tail[j]:
                return 2
            ancestor = True
        if g[j] == "**":
            stack.append((i, j + 1))
            if i < la:
                stack.append((i + 1, j))
        if i < la and wild and a[i] == "**":
            stack.append((i + 1, j))
            stack.append((i, j + 1))
        elif i < la and g[j] != "**" and _compat(a[i], g[j], wild):
            stack.append((i + 1, j + 1))
    return 1 if ancestor else 0


def _braces(word: str) -> list[str]:
    """Bash brace expansion, bounded. A ``{x..y}`` sequence is approximated by ``*``."""
    if word.count("{") > MAX_BRACES:
        raise _Deny(f"cannot analyse {_show(word)!r} safely (too many braces); denied")
    done: list[str] = []
    work = [word]
    while work:
        x = work.pop()
        span = _brace_span(x)
        if span is None:
            done.append(x)
        else:
            start, end, parts = span
            work.extend(x[:start] + p + x[end + 1:] for p in parts)
        if len(work) + len(done) > MAX_ALTS:
            raise _Deny(f"cannot analyse {_show(word)!r} safely (too many brace expansions); denied")
    extra = [_SEQ_BRACE.sub("*", d) for d in done if _SEQ_BRACE.search(d)]
    return list(dict.fromkeys(done + extra))


def _brace_span(x: str):
    i = x.find("{")
    while i >= 0:
        if i == 0 or x[i - 1] != "$":
            depth, commas, j = 0, [], i
            while j < len(x):
                if x[j] == "{":
                    depth += 1
                elif x[j] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                elif x[j] == "," and depth == 1:
                    commas.append(j)
                j += 1
            if j < len(x) and commas:
                cuts = [i] + commas + [j]
                return i, j, [x[cuts[k] + 1:cuts[k + 1]] for k in range(len(cuts) - 1)]
        i = x.find("{", i + 1)
    return None


def _candidates(word: str) -> list[str]:
    """The path-like parts of one word: the word, the value of ``k=v``, ``:``-separated parts and
    the value glued to a short option (``-fFILE``)."""
    out = [word]
    if "=" in word:
        out.append(word.split("=", 1)[1])
    for x in list(out):
        if ":" in x:
            out.extend(x.split(":"))
    if word.startswith("-") and not word.startswith("--") and len(word) > 2:
        out.append(word[2:])
    return [o for o in dict.fromkeys(out) if o]


def _parse(args, short_val: str = "", long_val=(), stop=()):
    """Split arguments into (short option letters, long options, positionals, (option, value))."""
    letters: set[str] = set()
    longs: list[str] = []
    pos: list[str] = []
    vals: list[tuple[str, str]] = []
    i, n = 0, len(args)
    while i < n:
        a = args[i]
        if a in stop:
            break
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a.startswith("--"):
            longs.append(a)
            if "=" in a:
                k, v = a.split("=", 1)
                vals.append((k, v))
            elif a in long_val and i + 1 < n:
                vals.append((a, args[i + 1]))
                i += 1
        elif a.startswith("-") and len(a) > 1:
            for k in range(1, len(a)):
                letters.add(a[k])
                if a[k] in short_val:
                    if k + 1 < len(a):
                        vals.append(("-" + a[k], a[k + 1:]))
                    elif i + 1 < n:
                        vals.append(("-" + a[k], args[i + 1]))
                        i += 1
                    break
        else:
            pos.append(a)
        i += 1
    return letters, longs, pos, vals


def _skip_opts(words, i: int, short_val: str, long_val):
    """Index of the first non-option word from ``i``, and the option values skipped."""
    vals: list[tuple[str, str]] = []
    while i < len(words):
        a = words[i]
        if a == "--":
            return i + 1, vals
        if not a.startswith("-") or a == "-":
            return i, vals
        if a.startswith("--"):
            if "=" in a:
                k, v = a.split("=", 1)
                vals.append((k, v))
            elif a in long_val and i + 1 < len(words):
                vals.append((a, words[i + 1]))
                i += 1
        else:
            for k in range(1, len(a)):
                vals.append((("-" + a[k]), ""))
                if a[k] in short_val:
                    vals[-1] = ("-" + a[k], a[k + 1:] if k + 1 < len(a) else
                                (words[i + 1] if i + 1 < len(words) else ""))
                    if k + 1 == len(a):
                        i += 1
                    break
        i += 1
    return i, vals


# ---- shell lexer -----------------------------------------------------------------------------
@dataclass
class _Cmd:
    words: list = field(default_factory=list)
    redirs: list = field(default_factory=list)  # (operator, target word)
    piped: bool = False                          # stdin comes from a pipe
    stdin: list = field(default_factory=list)    # heredoc bodies and here-strings


def _match_paren(s: str, i: int) -> int:
    """Index of the ``)`` closing the ``(`` at ``i``; quotes are skipped."""
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k < 0:
                break
            j = k + 1
            continue
        if c == '"':
            k = j + 1
            while k < n and s[k] != '"':
                k += 2 if s[k] == "\\" else 1
            if k >= n:
                break
            j = k + 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise _Deny("cannot analyse the command safely (unterminated substitution); denied")


_ANSI = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b", "f": "\f",
         "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}


class _Lexer:
    """Splits a command into simple commands with words, redirections and stdin text, and
    collects the text of every command or process substitution. Never recurses."""

    def __init__(self, src: str):
        self.s, self.n, self.i = src, len(src), 0
        self.cmds: list[_Cmd] = []
        self.subs: list[str] = []
        self.cur = _Cmd()
        self.buf: list[str] = []
        self.in_word = self.quoted = False
        self.redir: str | None = None
        self.heredocs: list = []

    def fail(self, why: str):
        raise _Deny(f"cannot analyse the command safely ({why}); denied")

    def add(self, text: str, quoted: bool = False):
        self.buf.append(text)
        self.in_word = True
        self.quoted = self.quoted or quoted

    def end_word(self):
        if not self.in_word:
            return
        w = "".join(self.buf)
        quoted = self.quoted
        self.buf, self.in_word, self.quoted = [], False, False
        if len(w) > MAX_WORD:
            self.fail("word too long")
        op, self.redir = self.redir, None
        if op is None:
            self.cur.words.append(w)
        elif op in ("<<", "<<-"):
            self.heredocs.append((self.cur, w.replace(LIT, "$"), op == "<<-", quoted))
        elif op == "<<<":
            self.cur.stdin.append(w)
        elif op in (">&", "<&") and (w.isdigit() or w == "-"):
            pass  # file-descriptor duplication
        else:
            self.cur.redirs.append(("<" if op == "<&" else op, w))

    def end_cmd(self, piped: bool):
        self.end_word()
        if self.redir is not None:
            self.fail("redirection without a target")
        if self.cur.words or self.cur.redirs or self.cur.stdin:
            self.cmds.append(self.cur)
            self.cur = _Cmd(piped=piped)
        else:
            self.cur.piped = self.cur.piped or piped

    def run(self):
        s = self.s
        while self.i < self.n:
            c = s[self.i]
            nxt = s[self.i + 1] if self.i + 1 < self.n else ""
            if c in " \t":
                self.end_word()
            elif c == "\n":
                self.end_cmd(False)
                self.i += 1
                if self.heredocs:
                    self.read_heredocs()
                continue
            elif c == "#" and not self.in_word:
                j = s.find("\n", self.i)
                self.i = self.n if j < 0 else j
                continue
            elif c == "\\":
                if nxt == "\n":
                    self.i += 2
                    continue
                self.add(LIT if nxt == "$" else (nxt or "\\"), True)
                self.i += 2
                continue
            elif c == "'":
                j = s.find("'", self.i + 1)
                if j < 0:
                    self.fail("unterminated quote")
                self.add(s[self.i + 1:j].replace("$", LIT), True)
                self.i = j + 1
                continue
            elif c == "$" and nxt == "'":
                self.i = self.ansi_c(self.i + 2)
                continue
            elif c == '"' or (c == "$" and nxt == '"'):
                self.i = self.dquote(self.i + (2 if c == "$" else 1))
                continue
            elif c == "$" and nxt == "(":
                self.i = self.subst(self.i + 1)
                continue
            elif c == "`":
                self.i = self.backtick(self.i)
                continue
            elif c in "<>" and nxt == "(" and not self.in_word:
                self.i = self.subst(self.i + 1)
                continue
            elif c in "<>" or (c == "&" and nxt == ">"):
                self.i = self.redirect(self.i)
                continue
            elif c == "&":
                self.end_cmd(False)
                self.i += 2 if nxt == "&" else 1
                continue
            elif c == "|":
                self.end_cmd(nxt != "|")
                self.i += 2 if nxt in "|&" and nxt else 1
                continue
            elif c in ";()":
                self.end_cmd(False)
            else:
                self.add(c)
            self.i += 1
        self.end_cmd(False)
        for cmd, *_ in self.heredocs:
            cmd.stdin.append("")
        return self.cmds, self.subs

    def redirect(self, i: int) -> int:
        if self.in_word and not self.quoted and "".join(self.buf).isdigit():
            self.buf, self.in_word = [], False  # a file-descriptor number such as 2>
        else:
            self.end_word()
        if self.redir is not None:
            self.fail("redirection without a target")
        op = next(o for o in _REDIR_OPS if self.s.startswith(o, i))
        self.redir = op
        return i + len(op)

    def dquote(self, j: int) -> int:
        s, n = self.s, self.n
        self.add("", True)
        while j < n:
            c = s[j]
            if c == '"':
                return j + 1
            if c == "\\" and j + 1 < n and s[j + 1] in '$`"\\\n':
                self.add({"$": LIT, "\n": ""}.get(s[j + 1], s[j + 1]))
                j += 2
            elif c == "$" and j + 1 < n and s[j + 1] == "(":
                j = self.subst(j + 1)
            elif c == "`":
                j = self.backtick(j)
            else:
                self.add(c)
                j += 1
        self.fail("unterminated quote")

    def subst(self, i: int) -> int:
        j = _match_paren(self.s, i)
        self.subs.append(self.s[i + 1:j])
        self.add(SUBST)
        return j + 1

    def backtick(self, i: int) -> int:
        k = i + 1
        while k < self.n and self.s[k] != "`":
            k += 2 if self.s[k] == "\\" else 1
        if k >= self.n:
            self.fail("unterminated backquote")
        self.subs.append(self.s[i + 1:k].replace("\\`", "`"))
        self.add(SUBST)
        return k + 1

    def ansi_c(self, j: int) -> int:
        s, n, out = self.s, self.n, []
        while j < n and s[j] != "'":
            if s[j] == "\\" and j + 1 < n:
                e = s[j + 1]
                if e in _ANSI:
                    out.append(_ANSI[e])
                    j += 2
                    continue
                m = (re.match(r"x([0-9A-Fa-f]{1,2})", s[j + 1:j + 4]) or re.match(r"([0-7]{1,3})", s[j + 1:j + 4])
                     or re.match(r"u([0-9A-Fa-f]{1,4})", s[j + 1:j + 6])
                     or re.match(r"U([0-9A-Fa-f]{1,8})", s[j + 1:j + 10]))
                if m:
                    base = 8 if m.group(0)[0] in "01234567" else 16
                    code = int(m.group(1), base)
                    out.append(chr(code) if code <= 0x10FFFF else "?")
                    j += 1 + len(m.group(0))
                    continue
                out.append(s[j:j + 2])
                j += 2
                continue
            out.append(s[j])
            j += 1
        if j >= n:
            self.fail("unterminated quote")
        self.add("".join(out).replace("$", LIT), True)
        return j + 1

    def read_heredocs(self):
        s, n = self.s, self.n
        for cmd, delim, strip, quoted in self.heredocs:
            body: list[str] = []
            while self.i < n:
                e = s.find("\n", self.i)
                line = s[self.i:e if e >= 0 else n]
                self.i = e + 1 if e >= 0 else n
                if (line.lstrip("\t") if strip else line) == delim:
                    break
                body.append(line)
            text = "\n".join(body)
            cmd.stdin.append(text)
            if not quoted:
                self.body_subs(text)
        self.heredocs = []

    def body_subs(self, body: str):
        j = 0
        while j < len(body):
            c = body[j]
            if c == "\\":
                j += 2
            elif c == "$" and body[j + 1:j + 2] == "(":
                k = _match_paren(body, j + 1)
                self.subs.append(body[j + 2:k])
                j = k + 1
            elif c == "`":
                k = body.find("`", j + 1)
                if k < 0:
                    self.fail("unterminated backquote")
                self.subs.append(body[j + 1:k])
                j = k + 1
            else:
                j += 1


# ---- the guard -------------------------------------------------------------------------------
class _Guard:
    def __init__(self, cfg: HookConfig, payload: Payload):
        root = os.path.abspath(str(cfg.project_root))
        self.roots = tuple(dict.fromkeys((_norm(root), _resolve(root))))
        self.home = os.environ.get("HOME") or os.path.expanduser("~")
        cwd = payload.cwd or root
        self.cwd0 = _norm(cwd if os.path.isabs(cwd) else os.path.join(root, cwd))
        self.cwd: str | None = self.cwd0
        ev = tuple(_segs(g) for g in (*cfg.eval_globs, *cfg.held_out))
        ct = tuple(_segs(g) for g in CONTROL_GLOBS)
        self.globs = {EVAL: tuple(g for g in ev if g), CTRL: ct}
        self.frags = {k: tuple(dict.fromkeys(f for g in v for f in _dir_segments(g))) for k, v in self.globs.items()}
        self.vars: dict[str, list[str]] = {}
        self.checks = 0
        self.words = 0

    # -- classification ------------------------------------------------------------------------
    def spend(self):
        self.checks += 1
        if self.checks > MAX_CHECKS:
            raise _Deny("cannot analyse the command safely (too many path checks); denied")

    def verdict(self, word: str, cwd: str | None, kind: str) -> int:
        """2 if ``word`` could name a protected path of ``kind``, 1 if it is a strict ancestor of
        one (or the project root, or above it), else 0. Unresolved forms count only as A-06-3,
        A-06-4 and U-2 say."""
        if "\x00" in word:
            raise _Deny("a path contains a NUL byte; denied")
        if len(word) > MAX_WORD:
            raise _Deny("cannot analyse the command safely (path too long); denied")
        best = 0
        for b in _braces(word):
            for text, names in self.expand(b):
                best = max(best, self.verdict_text(text, names, cwd, kind))
                if best == 2:
                    return 2
        return best

    def expand(self, w: str, depth: int = 0, keep: bool = False):
        """Alternatives of ``w`` with known variables substituted. An unresolved variable becomes
        UNK followed by its modifier text (or stays as written when ``keep``)."""
        alts: list[tuple[str, frozenset]] = [("", frozenset())]
        pos = 0
        for m in _VAR.finditer(w):
            lit = w[pos:m.start()]
            pos = m.end()
            inner, name, mod = m.group(1), m.group(2) or m.group(3), ""
            if inner is not None:
                nm = _NAME.match(inner)
                name, mod = (nm.group(0), inner[nm.end():]) if nm and not inner.startswith("!") else ("!", inner)
            vals = self.vars.get(name) if not mod and depth < 3 else None
            if vals:
                reps: list[tuple[str, frozenset]] = []
                for v in vals:
                    reps.extend(self.expand(v, depth + 1, keep))
                    if len(reps) > MAX_ALTS:
                        raise _Deny("cannot analyse the command safely (too many variable values); denied")
            else:
                reps = [(m.group(0) if keep else UNK + mod, frozenset({name}))]
            alts = [(t + lit + rt, n | rn) for t, n in alts for rt, rn in reps]
            if len(alts) > MAX_ALTS:
                raise _Deny("cannot analyse the command safely (too many variable values); denied")
        return [(t + w[pos:], n) for t, n in alts]

    def flat(self, w: str) -> str:
        """``w`` with uniquely known variables substituted; anything else left as written."""
        alts = self.expand(w, keep=True)
        return (alts[0][0] if len(alts) == 1 else w).replace(LIT, "$")

    def verdict_text(self, text: str, names: frozenset, cwd: str | None, kind: str) -> int:
        self.spend()
        text = text.replace(LIT, "$")
        if UNK in text:
            if kind == EVAL and names & STRICT_VARS:
                return 2
            head = text.split(UNK, 1)[0]
            if self.frag_hit(text.rsplit(UNK, 1)[1], kind):
                return 2
            if "/" in head and self.verdict_known(head[:head.rindex("/")] or "/", cwd, kind) == 2:
                return 2
            return 0
        return self.verdict_known(text, cwd, kind)

    def frag_hit(self, rem: str, kind: str) -> bool:
        """U-2: the text after an unresolved prefix names a protected directory segment or contains
        a protected glob match."""
        for tok in _FRAG_SPLIT.split(rem):
            tok = tok.lstrip("-")
            if not tok or tok in (".", "..") or not re.search(r"[^*?\[\]]", tok):
                continue
            if any(_compat(tok, f, True) for f in self.frags[kind]):
                return True
        segs = [p for p in rem.split("/") if p not in ("", ".")]
        if len(segs) > MAX_SEGMENTS:
            raise _Deny("cannot analyse the command safely (path too long); denied")
        return any(_match(segs[k:], g, wild=False) == 2 for k in range(len(segs)) for g in self.globs[kind])

    def verdict_known(self, p: str, cwd: str | None, kind: str) -> int:
        if not p.startswith("~"):
            return self.verdict_path(p, cwd, kind)
        head, _, rest = p[1:].partition("/")
        base = self.home if head == "" else cwd if head == "+" else None
        if base is None:  # ~- and ~user are unresolvable (A-06-3)
            return 2 if (kind == EVAL and not rest) or self.frag_hit(rest, kind) else 0
        return self.verdict_path(os.path.join(base, rest) if rest else base, cwd, kind)

    def verdict_path(self, p: str, cwd: str | None, kind: str) -> int:
        if not os.path.isabs(p):
            if cwd is None:
                return 2 if self.frag_hit(p, kind) else 0
            p = os.path.join(cwd, p)
        if p.count("/") > MAX_SEGMENTS:
            raise _Deny("cannot analyse the command safely (path too long); denied")
        lex = _norm(p)
        if kind == EVAL and ".." in p.split("/") and all(_rel(lex, r) is None for r in self.roots):
            # PRD 4a parent form: "../evals" written in the argument and leaving the project is
            # denied when its trailing segments match a protected glob (a sibling checkout).
            # ~ and $HOME expansions alone never reach here with "..", so A-06-3 is unaffected.
            segs = [x for x in lex.split("/") if x]
            if any(_match(segs[k:], g, wild=False) == 2 for k in range(len(segs)) for g in self.globs[EVAL]):
                return 2
        best = 0
        for cand in dict.fromkeys((lex, _resolve(p), _resolve(lex))):
            best = max(best, self.verdict_abs(cand, kind))
            if best == 2:
                return 2
        if _WILD.search(lex):
            for hit in self.fs_glob(lex):
                for cand in dict.fromkeys((hit, _resolve(hit))):
                    best = max(best, self.verdict_abs(cand, kind))
                    if best == 2:
                        return 2
        return best

    def verdict_abs(self, a: str, kind: str) -> int:
        self.spend()
        globs = self.globs[kind]
        for root in self.roots:
            rel = _rel(a, root)
            if rel is not None:
                segs = rel.split("/") if rel else []
                if any(_match(segs, g) == 2 for g in globs):
                    return 2
                return 1 if any(self.is_ancestor(a, segs, g) for g in globs) else 0
        if a == "/" or any(r.startswith(a.rstrip("/") + "/") for r in self.roots):
            return 1  # an ancestor of the project root
        return 0  # outside the project: globs are project-relative (A-06-3 keeps ~/evals elsewhere allowed)

    @staticmethod
    def is_ancestor(a: str, segs: list[str], g: tuple[str, ...]) -> bool:
        """Strict ancestor of the glob's named folders: ``**`` matches no folder here, so a leading
        ``**`` does not make every folder an ancestor. A folder whose direct child is the glob's
        first named segment (for ``**/held_out``: ``src`` holding ``src/held_out``) counts too."""
        if _match(segs, tuple(p for p in g if p != "**")) == 1:
            return True
        lit = next((p for p in g if p != "**"), "")
        return (g[0] == "**" and lit and "*" not in lit and not _WILD.search(a)
                and os.path.lexists(os.path.join(a, lit)))

    def fs_glob(self, pattern: str) -> list[str]:
        """Concrete paths a shell glob expands to (``**`` as ``*``), so symlinks behind wildcards
        are seen. A folder is checked before it is listed; a protected one is returned unlisted."""
        cur = ["/"]
        scanned = 0
        for seg in pattern.split("/"):
            if not seg:
                continue
            if not _WILD.search(seg):
                cur = [os.path.join(c, seg) for c in cur]
                continue
            nxt: list[str] = []
            pat = seg.replace("**", "*")
            for c in cur:
                rc = _resolve(c)
                if self.verdict_abs(rc, EVAL) == 2:
                    return [c]
                if not os.path.isdir(rc):
                    continue
                try:
                    with os.scandir(rc) as it:
                        for e in it:
                            scanned += 1
                            if scanned > MAX_SCAN:
                                raise _Deny("cannot analyse the command safely (glob too broad); denied")
                            if e.name.startswith(".") and not pat.startswith("."):
                                continue
                            if fnmatch.fnmatchcase(e.name, pat):
                                nxt.append(os.path.join(c, e.name))
                                if len(nxt) > MAX_GLOB_HITS:
                                    raise _Deny("cannot analyse the command safely (glob too broad); denied")
                except OSError:
                    continue
            cur = nxt
        return cur

    # -- deny helpers ----------------------------------------------------------------------------
    def no_protected(self, words, cwd, what: str = "the command"):
        for w in words:
            for cand in _candidates(w):
                if self.verdict(cand, cwd, EVAL) == 2:
                    raise _Deny(f"{what} names a protected eval/held-out path ({_show(w)!r}); a blind role "
                                f"works from the brief and the published contracts only")

    def no_ancestor(self, words, cwd, what: str):
        if not words:
            if cwd is None or self.verdict_path(cwd, cwd, EVAL) >= 1:
                raise _Deny(f"{what} without a path searches the working directory, which contains "
                            f"protected eval/held-out paths; search a specific source directory instead")
            return
        for w in words:
            v = self.verdict(w, cwd, EVAL)
            if v == 2:
                raise _Deny(f"{what} on {_show(w)!r} names a protected eval/held-out path")
            if v == 1:
                raise _Deny(f"{what} on {_show(w)!r} would cover protected eval/held-out paths; "
                            f"search a specific source directory instead")

    def no_control(self, words, cwd, what: str):
        for w in words:
            for cand in _candidates(w):
                if self.verdict(cand, cwd, CTRL) == 2:
                    raise _Deny(f"{what} {_show(w)!r} is under a protected factory control folder "
                                f"(.factory/ or .claude/)")

    # -- tools -----------------------------------------------------------------------------------
    def read(self, path):
        if not isinstance(path, str) or not path.strip():
            raise _Deny("Read needs a file_path; denied (fail closed)")
        if self.literal_verdict(path) == 2:
            raise _Deny(f"Read of {_show(path)!r}: the path is protected (eval/held-out); a blind role "
                        f"works from the brief and the published contracts only")

    def literal_verdict(self, path: str) -> int:
        lit = path.replace("$", LIT)  # tools do not expand variables; check both readings
        return max(self.verdict(lit, self.cwd0, EVAL), self.verdict(path, self.cwd0, EVAL))

    def search(self, tool: str, ti: dict):
        path = ti.get("path")
        pat = ti.get("glob") if tool == "Grep" else ti.get("pattern")
        if path is not None and not isinstance(path, str) or pat is not None and not isinstance(pat, str):
            raise _Deny(f"{tool} input is malformed; denied (fail closed)")
        if not path or not path.strip() or _norm(path) == ".":
            raise _Deny(f"{tool} without a specific path would search the working directory, which "
                        f"contains protected eval/held-out paths; search a specific source directory "
                        f"(for example the slice's own source folder) instead")
        v = self.literal_verdict(path)
        if v == 2:
            raise _Deny(f"{tool} on {_show(path)!r}: the path is protected (eval/held-out)")
        if v == 1:
            raise _Deny(f"{tool} on {_show(path)!r} would search protected eval/held-out paths; search a "
                        f"specific source directory instead")
        if pat:
            # a relative pattern that stays under an allowed path cannot reach a protected path;
            # only one that escapes it (absolute, ~, ../) is checked
            base = path if os.path.isabs(path) else os.path.join(self.cwd0, path)
            joined = pat if os.path.isabs(pat) or pat.startswith("~") else os.path.join(base, pat)
            inside = _rel(_norm(joined), _norm(base)) is not None
            if (not inside and self.literal_verdict(joined) == 2) or (inside and self.resolves_protected(joined)):
                raise _Deny(f"{tool} glob {_show(pat)!r} names protected eval/held-out paths")

    def resolves_protected(self, pattern: str) -> bool:
        """A pattern that stays under an allowed path is checked by what exists on disk: every
        existing prefix is resolved through symlinks, and wildcards are expanded (``**`` as one
        folder level and as none), so ``src/link -> ../evals`` is caught while plain ``src``
        content is not widened by the pattern's wildcards."""
        lex = _norm(pattern)
        for variant in dict.fromkeys((lex, _norm(lex.replace("/**/", "/").replace("**/", "")))):
            hits = self.fs_glob(variant) if _WILD.search(variant) else [variant]
            if any(self.verdict_abs(_resolve(h), EVAL) == 2 for h in hits):
                return True
        return False

    def bash(self, command):
        if not isinstance(command, str) or not command.strip():
            raise _Deny("Bash needs a command; denied (fail closed)")
        if len(command) > MAX_COMMAND:
            raise _Deny(f"command too long to analyse ({len(command)} characters); denied (fail closed)")
        if "\x00" in command:
            raise _Deny("the command contains a NUL byte; denied (fail closed)")
        if self.verdict_path(self.cwd0, self.cwd0, EVAL) == 2:
            raise _Deny("the working directory is a protected eval/held-out path")
        self.script(command, 0)

    def script(self, src: str, depth: int):
        if depth > MAX_DEPTH:
            raise _Deny("cannot analyse the command safely (nested too deeply); denied")
        cmds, subs = _Lexer(src).run()
        self.words += sum(len(c.words) + len(c.redirs) for c in cmds)
        if self.words > MAX_WORDS:
            raise _Deny("cannot analyse the command safely (too many words); denied")
        for c in cmds:
            self.collect_vars(c)
        for inner in subs:
            saved = self.cwd
            self.script(inner, depth + 1)
            self.cwd = saved
        for c in cmds:
            self.simple(c, depth)

    def collect_vars(self, c: _Cmd):
        w = c.words
        i = 0
        while i < len(w) and _ASSIGN.match(w[i]):
            self.set_var(*_ASSIGN.match(w[i]).groups())
            i += 1
        if i < len(w) and w[i] in ("export", "declare", "local", "readonly", "typeset"):
            for x in w[i + 1:]:
                m = _ASSIGN.match(x)
                if m:
                    self.set_var(*m.groups())
        elif i < len(w) and w[i] in ("for", "select") and len(w) > i + 2 and w[i + 2] == "in":
            for x in w[i + 3:]:
                self.set_var(w[i + 1], x)

    def set_var(self, name: str, value: str):
        vals = self.vars.setdefault(name, [])
        if value not in vals:
            vals.append(value)
        if len(vals) > MAX_VALUES:
            raise _Deny("cannot analyse the command safely (too many variable values); denied")

    def new_cwd(self, target: str, cwd: str | None) -> str | None:
        if target == "-":
            return None
        alts = self.expand(target)
        if len(alts) != 1 or UNK in alts[0][0]:
            return None
        t = alts[0][0].replace(LIT, "$")
        if t.startswith("~"):
            head, _, rest = t[1:].partition("/")
            base = self.home if head == "" else cwd if head == "+" else None
            if base is None:
                return None
            t = os.path.join(base, rest) if rest else base
        if not os.path.isabs(t):
            if cwd is None:
                return None
            t = os.path.join(cwd, t)
        return _norm(t)

    def argv(self, c: _Cmd):
        """The command that actually runs, after assignments, keywords and wrappers, and the
        working directory it runs in."""
        words = [self.flat(w) for w in c.words]
        cwd = self.cwd
        self.synth = False
        i, n = 0, len(words)
        for _ in range(32):
            while i < n and (_ASSIGN.match(words[i]) or words[i] in KEYWORDS):
                i += 1
            if i >= n:
                return [], cwd
            name = os.path.basename(words[i])
            if name in SUB_WRAPPERS and i + 1 < n and words[i + 1] == SUB_WRAPPERS[name]:
                i, _vals = _skip_opts(words, i + 2, "pn", _SUB_LONG)
                continue
            if name == "flock":
                j, _vals = _skip_opts(words, i + 1, "wE", ("--timeout", "--conflict-exit-code"))
                j += 1  # the lock file
                if j < n and words[j] in ("-c", "--command"):
                    self.synth = True
                    return ["sh", "-c", words[j + 1] if j + 1 < n else ""], cwd
                i = j
                continue
            if name not in WRAPPERS:
                return words[i:], cwd
            short_val, long_val, skip = WRAPPERS[name]
            j, vals = _skip_opts(words, i + 1, short_val, long_val)
            keys = {k for k, _ in vals}
            if name == "env":
                if keys & {"-S", "--split-string"}:
                    raise _Deny("env -S builds a command at run time (dynamic construction)")
                for k, v in vals:
                    if k in ("-C", "--chdir"):
                        cwd = self.new_cwd(v, cwd)
                while j < n and _ASSIGN.match(words[j]):
                    j += 1
            if name == "command" and keys & {"-v", "-V"}:
                return [], cwd
            i = j + skip
        raise _Deny("cannot analyse the command safely (too many command wrappers); denied")

    def simple(self, c: _Cmd, depth: int):
        if depth > MAX_DEPTH:
            raise _Deny("cannot analyse the command safely (nested too deeply); denied")
        argv, cwd = self.argv(c)
        synthesized = self.synth
        off = len(c.words) - len(argv)
        self.raw_args = argv[1:] if synthesized else c.words[off + 1:]
        skip: set[int] = set()
        if argv and not synthesized and os.path.basename(argv[0]) == "find":
            # -name, -path and similar take a file-name filter, not a path (QA iteration 1)
            skip = {off + k + 1 for k in range(1, len(argv) - 1) if argv[k] in FIND_FILTERS}
        self.no_protected([w for k, w in enumerate(c.words) if k not in skip] + [t for _, t in c.redirs], self.cwd)
        writes = [t for op, t in c.redirs if op in _WRITE_REDIRS]
        if not argv:
            self.no_control(writes, cwd, "write target")
            return
        if _VAR.search(argv[0]):
            raise _Deny(f"the command name {_show(argv[0])!r} is built at run time (dynamic construction)")
        name, args = os.path.basename(argv[0]), argv[1:]
        saved, self.cwd = self.cwd, cwd
        try:
            writes += self.dispatch(name, args, c, depth)
            self.no_control(writes, cwd, "write target")
        finally:
            self.cwd = saved
        if name in ("cd", "pushd"):
            pos = [a for a in args if not a.startswith("-") or a == "-"]
            self.cwd = self.new_cwd(pos[0] if pos else "~", self.cwd)
        elif name == "popd":
            self.cwd = None

    def dispatch(self, name: str, args: list[str], c: _Cmd, depth: int) -> list[str]:
        """Command-specific checks; returns the command's own write targets (C-36)."""
        cwd = self.cwd
        letters, longs, pos, vals = _parse(args)
        # (e) dynamic construction
        if name == "eval":
            raise _Deny("eval builds a command at run time (dynamic construction)")
        if name in ("base64", "gbase64") and ("d" in letters or "D" in letters or "--decode" in longs):
            raise _Deny("base64 -d decodes text that may be a hidden command or path (dynamic construction)")
        if name == "xxd" and ("r" in letters or "-revert" in args):
            raise _Deny("xxd -r decodes text that may be a hidden command or path (dynamic construction)")
        if name in ("source", "."):
            if any(a in ("-", "/dev/stdin") or a.startswith(("/dev/fd/", "/proc/self/fd/")) or SUBST in a
                   for a in args):
                raise _Deny(f"{name} of generated text builds a command at run time (dynamic construction)")
            return []
        if name == "locate" or name in ("plocate", "mlocate"):
            raise _Deny(f"{name} searches every file name on the machine, including protected "
                        f"eval/held-out paths; search a specific source directory instead")
        if name in SHELLS:
            return self.shell(name, args, c, depth)
        if _PYTHON.match(name):
            return self.python(args, c, depth)
        if name in ("node", "nodejs"):
            return self.node(args, c)
        if _PERL.match(name) or _RUBY.match(name):
            return self.perl_ruby(name, args, c)
        if name in ("pytest", "py.test"):
            self.pytest(args)
            return []
        if name == "git":
            return self.git(args)
        if name == "find":
            self.nested(self.exec_lists(self.raw_args, ("-exec", "-execdir", "-ok", "-okdir")), depth)
        if name in ("fd", "fdfind"):
            self.nested(self.exec_lists(self.raw_args, ("-x", "--exec", "-X", "--exec-batch")), depth)
        if name in AWKS:
            self.awk(name, args)
        if name == "script":
            code = next((v for k, v in _parse(args, "cEeOT", ("--command", "--echo", "--log-io", "--log-out",
                                                              "--log-timing"))[3] if k in ("-c", "--command")), None)
            if code is not None:
                return self.shell("sh", ["-c", code], c, depth)
        if name in EDITORS:
            self.editor(name, args)
        self.recursive(name, args, letters, longs)
        return self.write_targets(name, args, letters, longs)

    # (a)+(d)+(e) for shells
    def shell(self, name: str, args: list[str], c: _Cmd, depth: int) -> list[str]:
        code, stdin_script, rest, script = None, False, [], None
        code_flag = False
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-o", "+o", "-O", "+O"):
                i += 2
                continue
            if a == "--":
                i += 1
                continue
            if a[:1] in "-+" and len(a) > 1 and not a.startswith("--"):
                code_flag = code_flag or "c" in a[1:]
                stdin_script = stdin_script or "s" in a[1:]
                i += 1
                continue
            if a.startswith("--"):
                i += 1
                continue
            if code_flag:
                code, rest = a, args[i + 1:]
            elif not stdin_script:
                script = a
            break
        if code is not None:
            raw = code.replace(LIT, "$")
            if "$(" in raw or "`" in raw or SUBST in code:
                raise _Deny(f"{name} -c with a command substitution builds a command at run time "
                            f"(dynamic construction)")
            self.one_liner(raw, rest, f"{name} -c")
            saved = self.cwd
            self.script(raw, depth + 1)
            self.cwd = saved
            return []
        if script is not None:
            if SUBST in script or script in ("/dev/stdin",) or script.startswith("/dev/fd/"):
                raise _Deny(f"{name} running generated text builds a command at run time (dynamic construction)")
            return []  # a script file is not inspected (residual gap B7)
        if c.stdin:
            for body in c.stdin:
                saved = self.cwd
                self.script(body, depth + 1)
                self.cwd = saved
            return []
        if c.piped:
            raise _Deny(f"piping into {name} runs generated text as a command (dynamic construction)")
        return []

    def program_from_stdin(self, label: str, c: _Cmd, rest: list[str]):
        if c.stdin:
            for body in c.stdin:
                self.one_liner(body.replace(LIT, "$"), rest, label)
        elif c.piped:
            raise _Deny(f"piping a program into {label} runs generated code (dynamic construction)")

    def python(self, args: list[str], c: _Cmd, depth: int) -> list[str]:
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-" or not a.startswith("-"):
                if a == "-":
                    self.program_from_stdin("python", c, args[i + 1:])
                return []  # a script file is not inspected (residual gap B7)
            if a == "--":
                i += 1
                if i < len(args):
                    return []
                break
            if a.startswith("--"):
                i += 1
                continue
            for k in range(1, len(a)):
                ch = a[k]
                if ch in "cmWX":
                    attached = a[k + 1:]
                    val = attached or (args[i + 1] if i + 1 < len(args) else "")
                    after = args[i + 1:] if attached else args[i + 2:]
                    if ch == "c":
                        self.one_liner(val, after, "python -c")
                        return []
                    if ch == "m":
                        self.python_module(val, after)
                        return []
                    if not attached:
                        i += 1
                    break
            i += 1
        self.program_from_stdin("python", c, [])
        return []

    def python_module(self, module: str, args: list[str]):
        if module in ("pytest", "py.test"):
            self.pytest(args)
        elif module == "unittest":
            self.unittest(args)

    def node(self, args: list[str], c: _Cmd) -> list[str]:
        test, files = False, []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("-e", "--eval", "-p", "--print") or (a.startswith("-") and not a.startswith("--")
                                                         and ("e" in a[1:] or "p" in a[1:])):
                self.one_liner(args[i + 1] if i + 1 < len(args) else "", args[i + 2:], "node -e")
                return []
            if a.startswith(("--eval=", "--print=")):
                self.one_liner(a.split("=", 1)[1], args[i + 1:], "node -e")
                return []
            if a == "--test":
                test = True
            elif a in ("-r", "--require", "--import", "--loader", "--test-reporter",
                       "--test-reporter-destination", "--test-name-pattern", "--test-skip-pattern",
                       "--test-shard", "--test-concurrency"):
                i += 1
            elif a == "-":
                self.program_from_stdin("node", c, args[i + 1:])
                return []
            elif not a.startswith("-"):
                if not test:
                    return []  # a script file is not inspected (residual gap B7)
                files.append(a)
            i += 1
        if test:
            if not files:
                raise _Deny("node --test without a path collects tests from the working directory, "
                            "which contains protected eval/held-out paths; name the test files")
            self.no_ancestor(files, self.cwd, "node --test")
        elif not args:
            self.program_from_stdin("node", c, [])
        return []

    def perl_ruby(self, name: str, args: list[str], c: _Cmd) -> list[str]:
        ruby = _RUBY.match(name) is not None
        codes, files, inplace = [], [], False
        value_chars = "IrCxWEFKT0" if ruby else "IMmlxC0dD"
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--":
                files.extend(args[i + 1:])
                break
            if a.startswith("-") and len(a) > 1 and not a.startswith("--"):
                for k in range(1, len(a)):
                    ch = a[k]
                    if ch in "eE" and not (ruby and ch == "E"):
                        attached = a[k + 1:]
                        codes.append(attached or (args[i + 1] if i + 1 < len(args) else ""))
                        if not attached:
                            i += 1
                        break
                    if ch == "i":
                        inplace = True
                        break
                    if ch in value_chars:
                        if k + 1 == len(a) and ch in "IrCE":
                            i += 1
                        break
            elif a.startswith("--"):
                pass
            elif not codes:
                break  # a script file is not inspected (residual gap B7)
            else:
                files.append(a)
            i += 1
        label = f"{name} -e"
        for code in codes:
            self.one_liner(code, files, label)
        if not codes and not args:
            self.program_from_stdin(name, c, [])
        return files if inplace else []

    def one_liner(self, code: str, args: list[str], label: str):
        """(d) and C-36: an interpreter one-liner may not call a directory walker, name a protected
        path, or take any argument under a control folder."""
        raw = code.replace(LIT, "$")
        if _WALKER.search(raw):
            raise _Deny(f"{label} calls a directory walker, which could list protected eval/held-out paths")
        toks = self.program_tokens(raw, label)
        for t in toks:
            if self.frag_hit(t, CTRL):
                raise _Deny(f"{label} argument {_show(t)!r} is under a protected factory control folder "
                            f"(.factory/ or .claude/)")
        self.no_control(toks + list(args), self.cwd, f"{label} argument")

    @staticmethod
    def exec_lists(raw: list[str], flags: tuple[str, ...]) -> list[list[str]]:
        """The command lists of find -exec/-ok and fd -x, with ``{}`` placeholders replaced."""
        out, i = [], 0
        while i < len(raw):
            if raw[i] in flags:
                j = i + 1
                while j < len(raw) and raw[j] not in (";", "+"):
                    j += 1
                out.append([re.sub(r"\{[^{}]*\}", "__found__", w) for w in raw[i + 1:j]])
                i = j
            i += 1
        return out

    def nested(self, lists: list[list[str]], depth: int):
        for words in lists:
            if words:
                saved = self.cwd
                self.simple(_Cmd(words=words), depth + 1)
                self.cwd = saved

    def program_tokens(self, code: str, label: str):
        """Every token of program text is checked like a Bash word (frag_hit and no_protected)."""
        toks = _CODE_TOKEN.findall(code.replace(LIT, "$"))
        self.words += len(toks)
        if self.words > MAX_WORDS:
            raise _Deny("cannot analyse the command safely (too many words); denied")
        for t in toks:
            if self.frag_hit(t, EVAL):
                raise _Deny(f"{label} code names a protected eval/held-out path ({_show(t)!r})")
        self.no_protected(toks, self.cwd, f"{label} code")
        return toks

    def awk(self, name: str, args: list[str]):
        letters, longs, pos, vals = _parse(args, "Fvfeil", ("--field-separator", "--assign", "--file",
                                                           "--source", "--include", "--load"))
        progs = [v for k, v in vals if k in ("-e", "--source")]
        if not progs and not any(k in ("-f", "--file") for k, _ in vals) and pos:
            progs = [pos[0]]
        for prog in progs:
            raw = prog.replace(LIT, "$")
            if re.search(r"\bsystem\s*\(|(?<!\|)\|(?!\|)", raw):
                raise _Deny(f"{name} program runs a command (system() or a pipe), which this guard cannot see")
            self.program_tokens(raw, name)

    def editor(self, name: str, args: list[str]):
        cmds = [v for k, v in _parse(args, "cS", ("--cmd",))[3] if k in ("-c", "--cmd", "-S")]
        cmds += [a[1:] for a in args if a.startswith("+")]
        for cmd in cmds:
            if "!" in cmd or "system(" in cmd:
                raise _Deny(f"{name} command {_show(cmd)!r} runs a shell command, which this guard cannot see")
            self.program_tokens(cmd, name)

    # (c) test runners
    def pytest(self, args: list[str]):
        letters, longs, pos, vals = _parse(args, "kmpcoWn", _PYTEST_LONG)
        paths = [p.split("::")[0] for p in pos]
        if "--pyargs" in longs:
            paths = [p if "/" in p or p.endswith(".py") else p.replace(".", "/") for p in paths]
        if not paths:
            raise _Deny("pytest without a path collects tests from the project root, which contains "
                        "protected eval/held-out paths (A-06-1); name your own test folder or file")
        self.no_ancestor(paths, self.cwd, "pytest")

    def unittest(self, args: list[str]):
        if args and args[0] == "discover":
            letters, longs, pos, vals = _parse(args[1:], "spt", ("--start-directory", "--pattern",
                                                                "--top-level-directory"))
            start = next((v for k, v in vals if k in ("-s", "--start-directory")), None) or (pos[0] if pos else ".")
            self.no_ancestor([start], self.cwd, "unittest discover")
            return
        letters, longs, pos, vals = _parse(args, "k")
        if not pos:
            raise _Deny("unittest without test names discovers tests from the working directory, which "
                        "contains protected eval/held-out paths; name your own tests")
        names = [p if "/" in p or p.endswith(".py") else p.replace(".", "/") for p in pos]
        self.no_ancestor(names, self.cwd, "unittest")

    # (b) recursive search or listing
    def recursive(self, name: str, args: list[str], letters, longs):
        targets: list[str] | None = None
        if name in ("grep", "egrep", "fgrep", "zgrep", "rgrep"):
            letters, longs, pos, vals = _parse(args, "efmABCdD", (
                "--regexp", "--file", "--max-count", "--after-context", "--before-context", "--context",
                "--directories", "--devices", "--include", "--exclude", "--exclude-dir", "--exclude-from",
                "--label", "--binary-files", "--group-separator"))
            rec = (name == "rgrep" or letters & {"r", "R"} or {"--recursive", "--dereference-recursive"} & set(longs)
                   or any(k in ("-d", "--directories") and v == "recurse" for k, v in vals))
            if rec:
                has_pat = any(k in ("-e", "--regexp", "-f", "--file") for k, _ in vals)
                targets = pos if has_pat else pos[1:]
        elif name in ("rg", "ag", "ack"):
            letters, longs, pos, vals = _parse(args, "efgtTmABCjMrEdGp", (
                "--regexp", "--file", "--glob", "--iglob", "--type", "--type-not", "--max-count",
                "--after-context", "--before-context", "--context", "--threads", "--max-columns",
                "--replace", "--encoding", "--max-depth", "--type-add", "--pre", "--sort", "--sortr",
                "--max-filesize", "--path-separator", "--ignore-file"))
            lists_files = "--files" in longs or (name in ("ag", "ack") and ("g" in letters or "f" in letters))
            has_pat = any(k in ("-e", "--regexp", "-f", "--file") for k, _ in vals) and name == "rg"
            targets = pos if (lists_files or has_pat) else pos[1:]
        elif name == "find":
            i = 0
            while i < len(args) and args[i] in ("-H", "-L", "-P") or i < len(args) and args[i].startswith("-O"):
                i += 1
            if i < len(args) and args[i] == "-D":
                i += 2
            targets = []
            while i < len(args) and not args[i].startswith("-") and args[i] not in ("(", "!", ")"):
                targets.append(args[i])
                i += 1
        elif name in ("ls", "dir", "vdir"):
            if "R" in letters or "--recursive" in longs:
                targets = _parse(args, "", ("--format", "--sort", "--time", "--ignore", "--hide",
                                            "--width", "--tabsize", "--color", "--quoting-style"))[2]
        elif name == "tree":
            targets = _parse(args, "LPIoH", ("--filelimit", "--timefmt", "--sort", "--charset"))[2]
        elif name == "du":
            targets = _parse(args, "dBtX", ("--max-depth", "--block-size", "--threshold", "--exclude",
                                            "--exclude-from", "--files0-from", "--time-style"))[2]
        elif name in ("fd", "fdfind"):
            letters, longs, pos, vals = _parse(args, "etEdjcSoX", (
                "--extension", "--type", "--exclude", "--max-depth", "--min-depth", "--threads",
                "--color", "--size", "--owner", "--changed-within", "--changed-before", "--search-path",
                "--base-directory", "--ignore-file", "--max-results"), stop=("-x", "--exec", "-X", "--exec-batch"))
            targets = pos[1:] + [v for k, v in vals if k in ("--search-path", "--base-directory")]
        elif name in ("cp", "scp") and (letters & {"r", "R", "a"} or {"--recursive", "--archive"} & set(longs)):
            targets = _parse(args, "tSPio", ("--target-directory", "--suffix"))[2] or ["."]
        elif name == "rsync" and (letters & {"r", "a"} or {"--recursive", "--archive"} & set(longs)):
            targets = _parse(args, "eTf", ("--exclude", "--include", "--filter", "--rsh", "--temp-dir"))[2] or ["."]
        elif name == "tar" and ({"c", "r", "u"} & letters or {"--create", "--append", "--update"} & set(longs)
                                or (args and not args[0].startswith("-") and set(args[0]) & {"c", "r", "u"})):
            targets = _parse(args, "fCTXbHKNgV", ("--file", "--directory", "--files-from", "--exclude-from",
                                                  "--exclude"))[2] or ["."]
            targets += [v for k, v in _parse(args, "fCTXbHKNgV", ("--directory",))[3] if k in ("-C", "--directory")]
        elif name == "zip" and ("r" in letters or "R" in letters or "--recurse-paths" in longs):
            targets = _parse(args, "bnOtxi", ())[2] or ["."]
        if targets is not None:
            self.no_ancestor(targets, self.cwd, f"recursive {name}")

    # git (A-06-6, U-1)
    def git(self, args: list[str]) -> list[str]:
        cwd = self.cwd
        i = 0
        while i < len(args):
            a = args[i]
            if a == "-C" and i + 1 < len(args):
                cwd = self.new_cwd(args[i + 1], cwd)
                i += 2
            elif a == "-c" and i + 1 < len(args):
                if _GIT_EXEC_KEY.match(args[i + 1].split("=", 1)[0].lower()):
                    raise _Deny(f"git -c {_show(args[i + 1])!r} defines a command at run time (dynamic construction)")
                i += 2
            elif a.startswith("--config-env"):
                raise _Deny("git --config-env defines configuration at run time (dynamic construction)")
            elif a in ("--git-dir", "--work-tree", "--namespace", "--super-prefix"):
                i += 2
            elif a.startswith("-"):
                i += 1
            else:
                break
        if i >= len(args):
            return []
        sub, rest = args[i], args[i + 1:]
        if sub == "config" and any(_GIT_EXEC_KEY.match(r.lower()) for r in rest if not r.startswith("-")):
            raise _Deny("git config of an alias or command setting defines commands that this guard cannot see")
        if sub in GIT_WRITES:
            return [a for a in args[:i] if a != "-C"] + rest  # any pathspec or option value (C-36)
        if sub not in GIT_READS:
            return []
        if "--" not in rest:
            raise _Deny(f"git {sub} can show protected eval/held-out files; add `-- <your paths>` with "
                        f"paths that are not protected (U-1)")
        specs = rest[rest.index("--") + 1:]
        if not specs:
            raise _Deny(f"git {sub} needs a pathspec after `--` (U-1)")
        for s in specs:
            if s.startswith(":"):
                raise _Deny(f"git {sub} pathspec magic {_show(s)!r} cannot be checked; use a plain path")
        self.no_ancestor(specs, cwd, f"git {sub}")
        return []

    # C-36 write targets
    def write_targets(self, name: str, args: list[str], letters, longs) -> list[str]:
        if name == "tee":
            return _parse(args)[2]
        if name in ("install", "ln"):
            return [a for a in args if a != "--"]  # target and link path both count (C-36 addendum)
        if name in ("cp", "mv", "rsync"):
            letters, longs, pos, vals = _parse(args, "tSmogeTf" if name in ("install", "rsync") else "tS",
                                               ("--target-directory", "--suffix", "--mode", "--owner",
                                                "--group", "--exclude", "--include", "--filter", "--rsh"))
            out = [v for k, v in vals if k in ("-t", "--target-directory")]
            if not out and pos:
                out.append(pos[-1] if len(pos) > 1 or name != "ln" else ".")
            return out + (pos if name == "mv" else [])
        if name in ("rm", "rmdir", "touch", "truncate", "mkdir", "chmod", "chown", "chgrp", "shred",
                    "unlink", "patch"):
            letters, longs, pos, vals = _parse(args, {"truncate": "sr", "touch": "rdt", "mkdir": "m",
                                                      "shred": "nsu", "patch": "pioDdrBFzVYgx"}.get(name, ""),
                                               ("--size", "--reference", "--date", "--mode", "--iterations",
                                                "--strip", "--input", "--output", "--directory",
                                                "--reject-file"))
            extra = [v for k, v in vals if name == "patch" and k in ("-o", "--output", "-d", "--directory",
                                                                     "-r", "--reject-file")]
            return pos + extra
        if name == "sed":
            letters, longs, pos, vals = _parse(args, "efl", ("--expression", "--file", "--line-length"))
            return pos if "i" in letters or any(x.startswith("--in-place") for x in longs) else []
        if name == "dd":
            return [a[3:] for a in args if a.startswith("of=")]
        if name in ("curl", "wget"):
            implicit = (name == "wget" and not ({"-O", "-P"} & {"-" + x for x in letters} or any(
                x.startswith(("--output-document", "--directory-prefix")) for x in longs))) or (
                name == "curl" and ("O" in letters or "J" in letters or "--remote-name" in longs
                                    or "--remote-name-all" in longs))
            return list(args) + (["."] if implicit else [])
        if name == "tar" and ("x" in letters or {"--extract", "--get"} & set(longs)
                              or (args and not args[0].startswith("-") and "x" in args[0])):
            dest = [v for k, v in _parse(args, "fCTXbHKNgV", ("--file", "--directory"))[3]
                    if k in ("-C", "--directory")] or ["."]
            self.no_extract_over_control(dest, name)
            return list(args)
        if name == "unzip":
            dest = [v for k, v in _parse(args, "dx", ("--exdir",))[3] if k in ("-d", "--exdir")] or ["."]
            self.no_extract_over_control(dest, name)
            return list(args)
        if name == "sort" and ("o" in letters or any(x.startswith("--output") for x in longs)):
            return list(args)
        return []

    def no_extract_over_control(self, dests: list[str], name: str):
        """An archive extracted into a control folder or a folder that holds one (such as the
        project root) can overwrite control files."""
        for d in dests:
            if self.verdict(d, self.cwd, CTRL) >= 1:
                raise _Deny(f"{name} extracting into {_show(d)!r} can overwrite the protected factory control "
                            f"folders (.factory/ or .claude/)")


# ---- entry point -----------------------------------------------------------------------------
def decide(payload: Payload, cfg: HookConfig) -> Decision:
    """Allow or deny a PreToolUse Read, Grep, Glob or Bash call of a blind role."""
    if payload.event != "PreToolUse":
        return Decision("allow")
    if not _is_blind(cfg.role_for(payload)):
        return Decision("allow")
    tool = payload.tool_name
    if not isinstance(tool, str) or not tool:
        return Decision("deny", "blindness_guard: PreToolUse payload has no tool_name; denied (fail closed)")
    if tool not in ("Read", "Grep", "Glob", "Bash"):
        return Decision("allow")
    ti = payload.tool_input
    try:
        guard = _Guard(cfg, payload)
        if tool == "Read":
            guard.read(ti.get("file_path"))
        elif tool == "Bash":
            guard.bash(ti.get("command"))
        else:
            guard.search(tool, ti)
    except _Deny as exc:
        return Decision("deny", f"blindness_guard: {exc}")
    except (RecursionError, MemoryError, ValueError) as exc:
        return Decision("deny", f"blindness_guard: cannot analyse the call safely ({type(exc).__name__}); "
                                f"denied (fail closed)")
    return Decision("allow")
