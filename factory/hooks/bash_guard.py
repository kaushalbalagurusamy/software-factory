"""Bash guard hook (TB-08): git hygiene and one-way doors.

Contracts: ``docs/contracts/hook-io.md``, ``docs/contracts/profile.md`` and the TB-08 clauses
(A-08-1 to A-08-6) of ``docs/contracts/clarifications.md``. Documentation: ``docs/hooks/bash_guard.md``.

``decide`` is a pure, deterministic function of the payload and the config: no network, no model
call, no environment access. The command is parsed (quotes, escapes, ``;``, ``&&``, ``||``, ``|``,
``&``, newlines, subshells, ``$(...)``, backticks, ``sh -c`` / ``eval`` strings, here-documents,
simple same-command variable assignments) into commands, and every command is inspected on its
parsed words, never on substrings of quoted text passed to ``echo``, ``printf`` or ``git commit -m``.
Anything that cannot be parsed fails closed as a deny, for every role.

Nothing project-specific is hard-coded: the deploy route and extra one-way-door regexes come from
the profile (``profile.deploy.route``, ``profile.one_way_door_patterns``).
"""
from __future__ import annotations

import posixpath
import re
import shlex
from dataclasses import dataclass, field

from factory.hooks.core import Decision, HookConfig, Payload

ORCHESTRATOR = "orchestrator"
IMPLEMENT = "implement"
MAX_DEPTH = 8
MAX_EXPANSIONS = 64

IMPLEMENT_DENIED_GIT = (
    "stash", "checkout", "restore", "reset", "clean", "add", "commit", "mv", "rm", "push", "merge",
    "cherry-pick",
)
# Commands whose arguments are text, not something that executes them.
TEXT_COMMANDS = frozenset({
    "echo", "printf", "grep", "egrep", "fgrep", "rg", "ag", "ack", "cat", "less", "more", "head",
    "tail", "wc", "diff", "man",
})
SQL_CLIENTS = frozenset({
    "psql", "mysql", "mariadb", "sqlite3", "sqlcmd", "duckdb", "usql", "sqlplus", "cockroach",
    "clickhouse-client", "pgcli", "mycli",
})
# Privilege or context-switching wrappers that run arbitrary command strings. They are never
# unwrapped: any use is unanalysable, so it asks the orchestrator and denies every other role.
UNANALYSABLE_WRAPPERS = frozenset({
    "su", "runuser", "doas", "pkexec", "nsenter", "chroot", "ssh", "watch", "flock", "parallel",
})
SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh", "ash"})
RESERVED_PREFIX = frozenset({"if", "then", "else", "elif", "do", "while", "until", "{", "!", "}", "fi", "done", "esac"})
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")


class ParseError(Exception):
    """The command cannot be parsed safely."""


# ---------------------------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------------------------
@dataclass
class Cmd:
    words: list[str] = field(default_factory=list)
    raw: str = ""
    bodies: list[str] = field(default_factory=list)  # here-document bodies
    piped: bool = False  # its output feeds the next command
    start: int = -1


def _match_paren(s: str, i: int) -> int:
    """Index of the ``)`` closing the ``(`` at ``s[i]``, honouring quotes and escapes."""
    depth = 0
    j = i
    n = len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k < 0:
                raise ParseError("unterminated single quote")
            j = k + 1
            continue
        if c == '"':
            j += 1
            while j < n and s[j] != '"':
                if s[j] == "\\":
                    j += 1
                j += 1
            if j >= n:
                raise ParseError("unterminated double quote")
            j += 1
            continue
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j
        j += 1
    raise ParseError("unterminated command substitution")


def _match_backtick(s: str, i: int) -> int:
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "`":
            return j
        j += 1
    raise ParseError("unterminated backtick substitution")


def _ansi_c(s: str, i: int) -> tuple[str, int]:
    """Decode ``$'...'`` starting at the ``'`` (index ``i``). Returns (text, index after)."""
    j = i + 1
    while j < len(s):
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "'":
            inner = s[i + 1:j]
            try:
                text = inner.encode("latin-1", "backslashreplace").decode("unicode_escape")
            except (UnicodeError, ValueError):
                text = inner
            return text, j + 1
        j += 1
    raise ParseError("unterminated $'...' string")


class Lexer:
    def __init__(self, src: str, depth: int, variables: dict[str, str]):
        if depth > MAX_DEPTH:
            raise ParseError("command nesting is too deep")
        self.s = src
        self.depth = depth
        self.vars = dict(variables)
        self.out: list[Cmd] = []
        self.cur = Cmd()
        self.words: list[str] = self.cur.words
        self.buf: list[str] = []
        self.in_word = False
        self.skip_next = False
        self.pending: list[tuple[str, Cmd, bool]] = []
        self.expansions = 0

    # -- words and commands ------------------------------------------------------------------
    def add(self, text: str) -> None:
        self.buf.append(text)
        self.in_word = True

    def end_word(self) -> None:
        if not self.in_word:
            return
        word = "".join(self.buf)
        self.buf = []
        self.in_word = False
        if self.skip_next:
            self.skip_next = False
            return
        if not self.cur.words and self.cur.start < 0:
            self.cur.start = self._word_start
        self.cur.words.append(word)

    def finalize(self, end: int, piped: bool = False) -> None:
        self.end_word()
        self.skip_next = False
        cmd = self.cur
        if cmd.words or cmd.bodies:
            cmd.raw = self.s[cmd.start:end].strip() if cmd.start >= 0 else " ".join(cmd.words)
            cmd.piped = piped
            self.out.append(cmd)
            self._register_assignments(cmd)
        self.cur = Cmd()

    def _register_assignments(self, cmd: Cmd) -> None:
        words = cmd.words
        if words and words[0] == "export":
            words = words[1:]
        if words and all(ASSIGNMENT.match(w) for w in words):
            for w in words:
                name, _, value = w.partition("=")
                self.vars[name.rstrip("+")] = value

    def sub(self, inner: str) -> None:
        sub = Lexer(inner, self.depth + 1, self.vars)
        self.out.extend(sub.run())

    # -- expansion ---------------------------------------------------------------------------
    def _var_at(self, i: int) -> tuple[str, int] | None:
        """Parse ``$NAME`` or ``${NAME}`` at s[i]=='$'. Returns (name, end) or None."""
        s = self.s
        if i + 1 >= len(s):
            return None
        if s[i + 1] == "{":
            k = s.find("}", i + 2)
            if k < 0:
                raise ParseError("unterminated ${")
            name = s[i + 2:k]
            return (name, k + 1) if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else ("", k + 1)
        m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", s[i + 1:])
        if m:
            return m.group(0), i + 1 + len(m.group(0))
        return None

    # -- main loop ---------------------------------------------------------------------------
    def run(self) -> list[Cmd]:
        i = 0
        while i < len(self.s):
            s = self.s
            n = len(s)
            c = s[i]
            if c in " \t\r":
                self.end_word()
                i += 1
                continue
            if not self.in_word:
                self._word_start = i
            if c == "\n":
                self.end_word()
                self._heredocs_at_newline(i)
                i = self._skip_heredocs(i)
                self.finalize(i)
                i += 1
                continue
            if c == "\\":
                if i + 1 < n and s[i + 1] == "\n":
                    i += 2
                    continue
                if i + 1 < n:
                    self.add(s[i + 1])
                i += 2
                continue
            if c == "'":
                k = s.find("'", i + 1)
                if k < 0:
                    raise ParseError("unterminated single quote")
                self.add(s[i + 1:k])
                i = k + 1
                continue
            if c == '"':
                i = self._double(i)
                continue
            if c == "$":
                i = self._dollar(i)
                continue
            if c == "`":
                k = _match_backtick(s, i)
                self.sub(s[i + 1:k])
                self.add(s[i:k + 1])
                i = k + 1
                continue
            if c == "#" and not self.in_word:
                k = s.find("\n", i)
                i = n if k < 0 else k
                continue
            if c == ";":
                self.finalize(i)
                i += 1
                continue
            if c == "&":
                if s.startswith("&&", i):
                    self.finalize(i)
                    i += 2
                    continue
                if s.startswith("&>", i):
                    i = self._redirect(i + 1)
                    continue
                self.finalize(i)
                i += 1
                continue
            if c == "|":
                piped = not s.startswith("||", i)
                self.finalize(i, piped=piped)
                i += 2 if s.startswith(("||", "|&"), i) else 1
                continue
            if c in "()":
                self.finalize(i)
                i += 1
                continue
            if c in "<>":
                if i + 1 < n and s[i + 1] == "(":
                    k = _match_paren(s, i + 1)
                    self.sub(s[i + 2:k])
                    self.add(s[i:k + 1])
                    i = k + 1
                    continue
                i = self._redirect(i)
                continue
            self.add(c)
            i += 1
        self.end_word()
        # a here-document with no terminating newline has an empty body
        self.finalize(len(self.s))
        return self.out

    _word_start = 0

    def _double(self, i: int) -> int:
        s = self.s
        n = len(s)
        j = i + 1
        self.in_word = True
        while j < n:
            c = s[j]
            if c == '"':
                return j + 1
            if c == "\\" and j + 1 < n:
                nxt = s[j + 1]
                self.buf.append(nxt if nxt in '"\\$`' else "\\" + nxt) if nxt != "\n" else None
                j += 2
                continue
            if c == "$" and j + 1 < n and s[j + 1] == "(":
                k = _match_paren(s, j + 1)
                self.sub(s[j + 2:k])
                self.buf.append(s[j:k + 1])
                j = k + 1
                continue
            if c == "`":
                k = _match_backtick(s, j)
                self.sub(s[j + 1:k])
                self.buf.append(s[j:k + 1])
                j = k + 1
                continue
            if c == "$":
                ref = self._var_at(j)
                if ref is not None:
                    name, end = ref
                    self.buf.append(self.vars[name] if name in self.vars else s[j:end])
                    j = end
                    continue
            self.buf.append(c)
            j += 1
        raise ParseError("unterminated double quote")

    def _dollar(self, i: int) -> int:
        s = self.s
        n = len(s)
        nxt = s[i + 1] if i + 1 < n else ""
        if nxt == "(":
            k = _match_paren(s, i + 1)
            self.sub(s[i + 2:k])
            self.add(s[i:k + 1])
            return k + 1
        if nxt == "'":
            text, end = _ansi_c(s, i + 1)
            self.add(text)
            return end
        if nxt == '"':
            return self._double(i + 1)
        ref = self._var_at(i)
        if ref is not None:
            name, end = ref
            if name in self.vars and self.expansions < MAX_EXPANSIONS:
                self.expansions += 1
                self.s = s[:i] + self.vars[name] + s[end:]
                return i
            self.add(s[i:end])
            return end
        self.add("$")
        return i + 1

    def _redirect(self, i: int) -> int:
        """Consume a redirection operator starting at s[i] (``<`` or ``>``)."""
        s = self.s
        n = len(s)
        if self.in_word and "".join(self.buf).isdigit():
            self.buf = []
            self.in_word = False
        else:
            self.end_word()
        j = i
        op = ""
        while j < n and s[j] in "<>" and len(op) < 3:
            op += s[j]
            j += 1
        if j < n and s[j] == "&":
            j += 1
        if op == "<<<":
            return j
        if op.startswith("<<"):
            if j < n and s[j] == "-":
                j += 1
            while j < n and s[j] in " \t":
                j += 1
            k = j
            quoted = False
            delim: list[str] = []
            while k < n and s[k] not in " \t\n;&|()<>":
                if s[k] in "'\"":
                    quoted = True
                    q = s[k]
                    e = s.find(q, k + 1)
                    if e < 0:
                        raise ParseError("unterminated quote in here-document delimiter")
                    delim.append(s[k + 1:e])
                    k = e + 1
                    continue
                if s[k] == "\\" and k + 1 < n:
                    quoted = True
                    delim.append(s[k + 1])
                    k += 2
                    continue
                delim.append(s[k])
                k += 1
            if self.cur.start < 0:
                self.cur.start = i
            self.pending.append(("".join(delim), self.cur, not quoted))
            return k
        self.skip_next = True
        return j

    def _heredocs_at_newline(self, i: int) -> None:  # pragma: no cover - placeholder for symmetry
        return None

    def _skip_heredocs(self, i: int) -> int:
        """At the newline s[i], read pending here-document bodies. Returns the index of the
        last consumed character (the newline after the final delimiter, or i)."""
        if not self.pending:
            return i
        s = self.s
        pos = i + 1
        for delim, cmd, expand in self.pending:
            body: list[str] = []
            while pos <= len(s):
                end = s.find("\n", pos)
                line = s[pos:] if end < 0 else s[pos:end]
                pos = len(s) + 1 if end < 0 else end + 1
                if line.strip() == delim:
                    break
                body.append(line)
            text = "\n".join(body)
            cmd.bodies.append(text)
            if expand:
                self._scan_substitutions(text)
        self.pending = []
        return max(i, min(pos, len(s)) - 1) if pos <= len(s) else len(s)

    def _scan_substitutions(self, text: str) -> None:
        j = 0
        while j < len(text):
            if text.startswith("$(", j):
                k = _match_paren(text, j + 1)
                self.sub(text[j + 2:k])
                j = k + 1
            elif text[j] == "`":
                k = _match_backtick(text, j)
                self.sub(text[j + 1:k])
                j = k + 1
            elif text[j] == "\\":
                j += 2
            else:
                j += 1


def parse(command: str, depth: int = 0, variables: dict[str, str] | None = None) -> list[Cmd]:
    return Lexer(command, depth, variables or {}).run()


# ---------------------------------------------------------------------------------------------
# Command normalisation
# ---------------------------------------------------------------------------------------------
def _base(word: str) -> str:
    return posixpath.basename(word) if "/" in word else word


MAX_SPLIT_LEN = 100_000


def _spec(flags: str = "", values: str = "", cmds: str = "", opts: str = "") -> dict[str, str]:
    """Option table: letter (or long name) -> kind. ``value`` takes a value, ``cmd`` takes a COMMAND
    STRING, ``opt`` takes an optional value (attached or after ``=`` only), ``flag`` takes none."""
    d: dict[str, str] = {}
    for kind, letters in (("flag", flags), ("value", values), ("cmd", cmds), ("opt", opts)):
        for ch in (letters if isinstance(letters, (list, tuple)) else letters):
            d[ch] = kind
    return d


def _lspec(flags=(), values=(), cmds=(), opts=()) -> dict[str, str]:
    return _spec(list(flags), list(values), list(cmds), list(opts))


def _getopt(args: list[str], short: dict[str, str], long: dict[str, str], *, permute: bool = False,
            digits: bool = False, any_letter: bool = False, plus: bool = False
            ) -> tuple[list[tuple[str, str | None, str]], list[str]]:
    """Parse options the way GNU getopt_long does. Returns ([(name, value, kind)], operands).

    Long options resolve by unique prefix (exactly one match, an exact name always wins); short
    clusters are walked letter by letter, a value-taking letter consuming the rest of the cluster or
    the next word. Anything unclassifiable (unknown option, ambiguous prefix, missing value, a value
    given to a flag) raises :class:`ParseError`, so the caller fails closed."""
    opts: list[tuple[str, str | None, str]] = []
    rest: list[str] = []
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        i += 1
        if a == "--":
            rest.extend(args[i:])
            break
        if a.startswith("--"):
            name, eq, val = a[2:].partition("=")
            if name in long:
                full = name
            else:
                cands = [k for k in long if k.startswith(name)] if name else []
                if len(cands) != 1:
                    raise ParseError(f"unknown or ambiguous option --{name}")
                full = cands[0]
            kind = long[full]
            if kind == "flag":
                if eq:
                    raise ParseError(f"option --{full} takes no value")
                opts.append((full, None, kind))
            elif kind == "opt":
                opts.append((full, val if eq else None, kind))
            else:
                if not eq:
                    if i >= n:
                        raise ParseError(f"option --{full} needs a value")
                    val = args[i]
                    i += 1
                opts.append((full, val, kind))
            continue
        if (a.startswith("-") or (plus and a.startswith("+"))) and len(a) > 1:
            lead = a[0]
            for k, ch in enumerate(a[1:]):
                kind = short.get(ch)
                if kind is None:
                    if any_letter and ch.isalpha():
                        kind = "flag"
                    elif digits and ch.isdigit():
                        kind = "flag"
                    else:
                        raise ParseError(f"unknown option {lead}{ch}")
                if kind == "flag":
                    opts.append((ch, None, kind))
                    continue
                tail = a[k + 2:]
                if kind == "opt":
                    opts.append((ch, tail or None, kind))
                elif tail:
                    opts.append((ch, tail, kind))
                else:
                    if i >= n:
                        raise ParseError(f"option {lead}{ch} needs a value")
                    opts.append((ch, args[i], kind))
                    i += 1
                break
            continue
        if a == "-" and "-" in short:
            opts.append(("-", None, "flag"))
            continue
        rest.append(a)
        if not permute:
            rest.extend(args[i:])
            break
    return opts, rest


def _split_command_string(value: str) -> list[str]:
    """Split a command line carried by an option (``env -S``) into words; fail closed."""
    if len(value) > MAX_SPLIT_LEN:
        raise ParseError("option command string is too long")
    try:
        return shlex.split(value)
    except ValueError as exc:
        raise ParseError(f"cannot split option command string: {exc}") from None


ENV_SHORT = _spec(flags="i0v-", values="uCaP", cmds="S")
ENV_LONG = _lspec(flags=("ignore-environment", "null", "debug", "list-signal-handling", "help", "version"),
                  values=("unset", "chdir", "argv0"), cmds=("split-string",),
                  opts=("block-signal", "default-signal", "ignore-signal"))
SUDO_SHORT = _spec(flags="AbEeHiKklnPSsVvB", values="CDghpRrTtUuc")
SUDO_LONG = _lspec(
    flags=("askpass", "background", "bell", "edit", "set-home", "help", "login", "remove-timestamp",
           "reset-timestamp", "list", "non-interactive", "preserve-groups", "stdin", "shell", "version",
           "validate"),
    values=("close-from", "chdir", "group", "host", "login-class", "prompt", "chroot", "role", "type",
            "command-timeout", "other-user", "user"),
    opts=("preserve-env",))
XARGS_SHORT = _spec(flags="0oprtvx", values="adILnPsE", opts="eil")
XARGS_LONG = _lspec(
    flags=("null", "interactive", "no-run-if-empty", "verbose", "exit", "open-tty", "show-limits", "help",
           "version"),
    values=("arg-file", "delimiter", "max-args", "max-procs", "process-slot-var", "max-chars"),
    opts=("eof", "replace", "max-lines"))
NICE_SHORT = _spec(values="n")
NICE_LONG = _lspec(flags=("help", "version"), values=("adjustment",))
TIME_SHORT = _spec(flags="apqvV", values="fo")
TIME_LONG = _lspec(flags=("append", "portability", "quiet", "verbose", "version", "help"), values=("format", "output"))
TIMEOUT_SHORT = _spec(flags="fpv", values="ks")
TIMEOUT_LONG = _lspec(flags=("foreground", "preserve-status", "verbose", "help", "version"),
                      values=("kill-after", "signal"))
NOHUP_LONG = _lspec(flags=("help", "version"))
COMMAND_SHORT = _spec(flags="pvV")
EXEC_SHORT = _spec(flags="cl", values="a")
SETSID_SHORT = _spec(flags="cfwV")
SETSID_LONG = _lspec(flags=("ctty", "fork", "wait", "help", "version"))
STDBUF_SHORT = _spec(values="ioe")
STDBUF_LONG = _lspec(flags=("help", "version"), values=("input", "output", "error"))
SHELL_SHORT = _spec(values="oO")
SHELL_LONG = _lspec(
    flags=("login", "noprofile", "norc", "posix", "restricted", "verbose", "version", "help", "debugger",
           "dump-po-strings", "dump-strings", "noediting", "pretty-print", "protected"),
    values=("rcfile", "init-file"))


def _strip_prefix(words: list[str], scripts: list[str]) -> list[str]:
    """Drop leading reserved words, variable assignments and transparent wrappers.

    Wrapper options are parsed with a per-wrapper table (see :func:`_getopt`); an option that carries a
    command string is never skipped: ``env -S`` is split into words and analysed as the wrapped
    command, while ``sudo -s|-i``, ``su -c`` and ``runuser -c`` strings are appended to ``scripts``
    (shell text for the caller to parse). An option that cannot be classified raises ParseError."""
    ws = list(words)
    for _ in range(64):
        if not ws:
            return ws
        w = ws[0]
        if w in RESERVED_PREFIX:
            ws = ws[1:]
            continue
        if ASSIGNMENT.match(w):
            ws = ws[1:]
            continue
        name = _base(w)
        args = ws[1:]
        if name == "env":
            while True:
                opts, rest = _getopt(args, ENV_SHORT, ENV_LONG)
                pre: list[str] = []
                for _n, val, kind in opts:
                    if kind == "cmd":
                        pre += _split_command_string(val or "")
                rest = pre + rest
                while rest and ASSIGNMENT.match(rest[0]):
                    rest = rest[1:]
                if rest and rest[0].startswith("-") and len(rest[0]) > 1:
                    args = rest  # conservative: options after assignments are still parsed
                    continue
                break
            ws = rest
        elif name == "sudo":
            opts, rest = _getopt(args, SUDO_SHORT, SUDO_LONG)
            if any(o in ("s", "i", "shell", "login") for o, _v, _k in opts) and rest:
                scripts.append(" ".join(rest))
                return []
            ws = rest
        elif name == "xargs":
            ws = _getopt(args, XARGS_SHORT, XARGS_LONG)[1]
        elif name == "nice":
            ws = _getopt(args, NICE_SHORT, NICE_LONG, digits=True)[1]
        elif name == "time":
            ws = _getopt(args, TIME_SHORT, TIME_LONG)[1]
        elif name == "timeout":
            rest = _getopt(args, TIMEOUT_SHORT, TIMEOUT_LONG)[1]
            ws = rest[1:]  # the duration
        elif name == "nohup":
            ws = _getopt(args, {}, NOHUP_LONG)[1]
        elif name == "builtin":
            ws = _getopt(args, {}, {})[1]
        elif name == "command":
            ws = _getopt(args, COMMAND_SHORT, {})[1]
        elif name == "exec":
            ws = _getopt(args, EXEC_SHORT, {})[1]
        elif name == "setsid":
            ws = _getopt(args, SETSID_SHORT, SETSID_LONG)[1]
        elif name == "stdbuf":
            ws = _getopt(args, STDBUF_SHORT, STDBUF_LONG)[1]
        else:
            return ws
    raise ParseError("command wrapping is too deep")


# ---------------------------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Finding:
    rule: str
    what: str  # what a human would be asked to approve / what is blocked
    implement_rule: bool = False  # always deny, even for the orchestrator


def _opt_matches(arg: str, full: str, minlen: int) -> bool:
    name = arg.split("=", 1)[0]
    return name == full or (len(name) >= minlen and full.startswith(name) and name.startswith("--"))


def _scan_args(args: list[str], value_short: str = "", value_long: tuple[str, ...] = ()) -> tuple[list[str], list[str]]:
    """Split git arguments into option names and positionals, skipping option values."""
    opts: list[str] = []
    pos: list[str] = []
    i = 0
    end = False
    while i < len(args):
        a = args[i]
        i += 1
        if end or a == "-" or not a.startswith("-"):
            pos.append(a)
            continue
        if a == "--":
            end = True
            continue
        if a.startswith("--"):
            name = a.split("=", 1)[0]
            opts.append(name)
            if "=" not in a and len(name) >= 4 and any(v.startswith(name) for v in value_long):
                i += 1
            continue
        for k, ch in enumerate(a[1:]):
            opts.append("-" + ch)
            if ch in value_short:
                if k == len(a) - 2:
                    i += 1
                break
    return opts, pos


GIT_VALUE_GLOBAL = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix", "--attr-source"})


def _git_split(words: list[str]) -> tuple[str, list[str], list[str], dict[str, str]]:
    """Return (subcommand, args, config entries from -c, aliases) for a ``git`` command."""
    i = 1
    configs: list[str] = []
    while i < len(words):
        w = words[i]
        if w in GIT_VALUE_GLOBAL:
            if w == "-c" and i + 1 < len(words):
                configs.append(words[i + 1])
            i += 2
        elif w.startswith("-") and w != "-":
            if w.startswith("-c") and len(w) > 2 and not w.startswith("--"):
                configs.append(w[2:])
            i += 1
        else:
            break
    aliases: dict[str, str] = {}
    for c in configs:
        k, _, v = c.partition("=")
        if k.lower().startswith("alias."):
            aliases[k[6:]] = v
    sub = words[i] if i < len(words) else ""
    args = words[i + 1:]
    if sub in aliases and aliases[sub] and not aliases[sub].startswith("!"):
        try:
            exp = shlex.split(aliases[sub])
        except ValueError:
            exp = aliases[sub].split()
        if exp:
            sub, args = exp[0], exp[1:] + args
    return sub, args, configs, aliases


def _git_findings(words: list[str]) -> list[Finding]:
    sub, args, configs, _aliases = _git_split(words)
    out: list[Finding] = []
    if not sub:
        return out
    value_short = {"commit": "mFCct", "push": "o"}.get(sub, "")
    value_long = {
        "commit": ("--message", "--file", "--author", "--date", "--template", "--reuse-message",
                   "--reedit-message", "--fixup", "--squash", "--cleanup", "--trailer", "--pathspec-from-file"),
        "push": ("--receive-pack", "--exec", "--repo", "--push-option"),
        "add": ("--pathspec-from-file",),
        "reset": ("--pathspec-from-file",),
    }.get(sub, ())
    opts, pos = _scan_args(args, value_short, value_long)

    if sub == "add":
        if "-A" in opts or any(_opt_matches(o, "--all", 4) for o in opts):
            out.append(Finding("git-add-all", "git add -A / --all stages every change in the tree"))
        elif any(p in (".", "./", "*", "./*", "**", ".//") for p in pos):
            out.append(Finding("git-add-all", "git add . or git add * stages every change in the tree"))
    if any(_opt_matches(o, "--no-verify", 7) for o in opts) or (sub == "commit" and "-n" in opts):
        out.append(Finding("git-no-verify", "--no-verify skips the git hooks"))
    for c in configs:
        if c.lower().startswith("core.hookspath="):
            out.append(Finding("git-no-verify", "core.hooksPath override skips the git hooks"))
    if sub == "commit" and any(_opt_matches(o, "--amend", 4) for o in opts):
        out.append(Finding("git-amend", "git commit --amend rewrites the previous commit"))
    if sub == "rebase":
        out.append(Finding("git-rebase", "git rebase rewrites history"))
    if sub == "push":
        forced = "-f" in opts or any(o.startswith("--force") or (len(o) >= 5 and "--force".startswith(o)) for o in opts)
        if forced or any(p.startswith("+") and len(p) > 1 for p in pos):
            out.append(Finding("git-force-push", "git push --force / -f / --force-with-lease / +refspec overwrites remote history"))
    if sub == "reset" and any(_opt_matches(o, "--hard", 4) for o in opts):
        out.append(Finding("git-reset-hard", "git reset --hard discards uncommitted work"))
    if sub in IMPLEMENT_DENIED_GIT:
        out.append(Finding("implement-no-commit", f"the implement role never changes the git state: git {sub} is not allowed", True))
    return out


def _non_options(args: list[str], value_opts: frozenset[str] = frozenset()) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a in value_opts:
            i += 1
        elif a.startswith("-") and a != "-":
            continue
        else:
            out.append(a)
    return out


def _rm_exempt(target: str) -> bool:
    if not target or target.startswith("~") or "$" in target or "`" in target:
        return False
    path = posixpath.normpath(target)
    parts = [p for p in path.split("/") if p]
    if "node_modules" in parts or ".venv" in parts:
        return True
    return path.startswith("/tmp/") and len(path) > len("/tmp/")


def _rm_findings(args: list[str]) -> list[Finding]:
    recursive = force = False
    targets: list[str] = []
    end = False
    for a in args:
        if end or not a.startswith("-") or a == "-":
            targets.append(a)
        elif a == "--":
            end = True
        elif a.startswith("--"):
            recursive |= a == "--recursive"
            force |= a == "--force"
        else:
            recursive |= any(ch in "rR" for ch in a[1:])
            force |= "f" in a[1:]
    if recursive and force:
        bad = [t for t in targets if not _rm_exempt(t)]
        if bad:
            return [Finding("rm-rf", f"rm -rf recursively deletes {', '.join(bad)}, outside /tmp, node_modules and .venv")]
    return []


SQL_DROP = re.compile(r"\bdrop\s+(table|database|column)\b", re.I)
SQL_TRUNCATE = re.compile(r"\btruncate\s+(?:table\s+)?[\w\"`'\[.]", re.I)
SQL_DELETE = re.compile(r"\bdelete\s+from\b[^;]*", re.I)
SQL_WHERE = re.compile(r"\bwhere\b", re.I)


def _sql_findings(text: str) -> list[Finding]:
    m = SQL_DROP.search(text)
    if m:
        return [Finding("sql-drop", f"destructive SQL: {' '.join(m.group(0).upper().split())}")]
    if SQL_TRUNCATE.search(text):
        return [Finding("sql-truncate", "destructive SQL: TRUNCATE")]
    for m in SQL_DELETE.finditer(text):
        if not SQL_WHERE.search(m.group(0)):
            return [Finding("sql-delete-no-where", "destructive SQL: DELETE FROM with no WHERE clause")]
    return []


def _norm(word: str) -> str:
    return word[2:] if word.startswith("./") else word


def _route_matches(words: list[str], route: str) -> bool:
    try:
        rt = shlex.split(route)
    except ValueError:
        rt = route.split()
    if not rt or len(words) < len(rt):
        return False
    head = list(words[:len(rt)])
    if "/" not in rt[0] and "/" in head[0]:
        head[0] = _base(head[0])
    return [_norm(w) for w in head] == [_norm(w) for w in rt]


# ---------------------------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------------------------
def _message_free(words: list[str]) -> list[str]:
    """For ``git commit`` drop the message-carrying arguments so patterns do not see them."""
    sub, args, _c, _a = _git_split(words)
    if sub != "commit":
        return words
    keep = list(words[:len(words) - len(args)])
    i = 0
    while i < len(args):
        a = args[i]
        i += 1
        if a in ("-m", "--message", "-F", "--file", "-t", "--template"):
            i += 1
            continue
        if a.startswith("--message=") or a.startswith("--file="):
            continue
        if re.fullmatch(r"-[A-Za-z]*m", a):
            keep.append(a[:-1] or a)
            i += 1
            continue
        if a.startswith("-m") and len(a) > 2:
            continue
        keep.append(a)
    return keep


BUILTIN_HITL_GUARD = r"\bsf\s+hitl\b.*\b(release|supersede)"


def _analyse(cmds: list[Cmd], cfg: HookConfig, depth: int = 0) -> list[Finding]:
    if depth > MAX_DEPTH:
        raise ParseError("command nesting is too deep")
    findings: list[Finding] = []
    # built in, so a project installed before `supersede` existed is still guarded
    patterns = [re.compile(p) for p in (*cfg.one_way_door_patterns, BUILTIN_HITL_GUARD)]
    deploy = cfg.profile.deploy
    route = deploy.route if deploy is not None and deploy.route else None
    for idx, cmd in enumerate(cmds):
        scripts: list[str] = []
        words = _strip_prefix(cmd.words, scripts)
        for sc in scripts:
            findings += _analyse(parse(sc, depth + 1), cfg, depth + 1)
        if not words:
            continue
        if re.search(r"\s", words[0]):
            raise ParseError("command word contains whitespace after unwrapping")
        name = _base(words[0])
        args = words[1:]
        is_git = name == "git"
        is_text = name in TEXT_COMMANDS

        if name in UNANALYSABLE_WRAPPERS or (name == "machinectl" and "shell" in args):
            findings.append(Finding("unanalysable-wrapper", f"{name} runs arbitrary command strings the guard cannot inspect"))

        # nested shell strings
        if name in SHELLS:
            script = _shell_script(args)
            if script is not None:
                findings += _analyse(parse(script, depth + 1), cfg, depth + 1)
        elif name == "find":
            i = 0
            while i < len(args):
                if args[i] in ("-exec", "-execdir", "-ok", "-okdir"):
                    j = i + 1
                    while j < len(args) and args[j] not in (";", "+"):
                        j += 1
                    sub = args[i + 1:j]
                    if sub:
                        findings += _analyse([Cmd(words=sub, raw=" ".join(sub))], cfg, depth + 1)
                    i = j
                i += 1
        elif name == "eval" and args:
            findings += _analyse(parse(" ".join(args), depth + 1), cfg, depth + 1)

        if is_git:
            findings += _git_findings(words)
        elif name == "rm":
            findings += _rm_findings(args)
        elif name in ("terraform", "tofu", "terragrunt"):
            non = _non_options(args)
            if "destroy" in non[:2] or (non[:1] == ["apply"] and "-destroy" in args):
                findings.append(Finding("terraform-destroy", f"{name} destroy deletes managed infrastructure"))
        elif name in ("kubectl", "oc"):
            non = _non_options(args, frozenset({"-n", "--namespace", "--context", "--cluster", "--user", "-s", "--server", "--kubeconfig", "--as"}))
            if non[:1] == ["delete"]:
                findings.append(Finding("kubectl-delete", f"{name} delete removes cluster resources"))
        elif name == "gh":
            non = _non_options(args, frozenset({"-R", "--repo"}))
            if non[:2] == ["repo", "delete"]:
                findings.append(Finding("gh-repo-delete", "gh repo delete permanently deletes a repository"))

        # SQL in the arguments (and here-documents) of anything that is not text or git
        if not is_git and not is_text:
            texts = [" ".join(args)] + list(args) + list(cmd.bodies)
            for t in texts:
                f = _sql_findings(t)
                if f:
                    findings += f
                    break
        # echo/printf piped into a SQL client
        if is_text and name in ("echo", "printf", "cat") and cmd.piped and idx + 1 < len(cmds):
            nxt = _strip_prefix(cmds[idx + 1].words, [])
            if nxt and _base(nxt[0]) in SQL_CLIENTS:
                findings += _sql_findings(" ".join(args))

        # profile-driven doors
        if not is_text:
            if route and _route_matches(words, route):
                findings.append(Finding("deploy-route", f"the project's deploy route ({route}) ships to a live environment"))
            if patterns:
                shown = _message_free(words)
                candidates = [" ".join(shown), " ".join(cmd.words)]
                if not (is_git and _git_split(words)[0] == "commit"):
                    candidates.append(cmd.raw)
                for pat in patterns:
                    if any(pat.search(t) for t in candidates):
                        findings.append(Finding("one-way-door-pattern", f"the command matches one_way_door_patterns entry {pat.pattern!r}"))
                        break
    return findings


def _shell_script(args: list[str]) -> str | None:
    """The string passed to ``sh -c`` style invocations, or None when there is none."""
    opts, rest = _getopt(args, SHELL_SHORT, SHELL_LONG, any_letter=True, plus=True)
    if any(o == "c" for o, _v, _k in opts) and rest:
        return rest[0]
    return None


# ---------------------------------------------------------------------------------------------
# Decision
# ---------------------------------------------------------------------------------------------
def _decision_for(finding: Finding, role: str, command: str) -> Decision:
    shown = command if len(command) <= 200 else command[:197] + "..."
    if finding.implement_rule:
        # reached only for the implement role (see decide); other roles never get these
        return Decision("deny", f"bash_guard {finding.rule}: {finding.what}")
    if role == ORCHESTRATOR:
        return Decision("ask", f"bash_guard {finding.rule}: {finding.what}. A human is asked to approve running: {shown}")
    return Decision("deny", f"bash_guard {finding.rule}: {finding.what}. Denied for role {role}; command: {shown}")


def decide(payload: Payload, cfg: HookConfig) -> Decision:
    if payload.event != "PreToolUse" or payload.tool_name != "Bash":
        return Decision("allow")
    command = payload.tool_input.get("command") if isinstance(payload.tool_input, dict) else None
    if not isinstance(command, str):
        return Decision("deny", "bash_guard malformed-input: Bash tool_input has no string command")
    role = cfg.role_for(payload)
    try:
        findings = _analyse(parse(command), cfg)
    except ParseError as exc:
        return Decision("deny", f"bash_guard unparseable-command: {exc}; the command is denied because it cannot be inspected")
    findings = [f for f in findings if not f.implement_rule or role == IMPLEMENT]
    if not findings:
        return Decision("allow")
    # deny outranks ask; within a kind the first finding in command order names the rule
    decisions = [_decision_for(f, role, command) for f in findings]
    for d in decisions:
        if d.kind == "deny":
            return d
    return decisions[0]
