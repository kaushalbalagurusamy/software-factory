"""Secrets guard (TB-07): stop a secret value being written to a file or typed into a command.

Contracts: ``docs/contracts/hook-io.md``, ``docs/prds/TB-07-secrets-guard.md`` and the TB-07
clauses of ``docs/contracts/clarifications.md``. Deterministic: no network, no model call, no
file or environment access. The hook never logs or persists the text it inspects, and a deny
reason names the pattern kind and the line number, never the matched value.
"""
from __future__ import annotations

import re
from typing import Any

from factory.hooks.core import Decision, HookError, Payload

# tool name -> the tool_input field that carries text to inspect
INSPECTED: dict[str, str] = {"Write": "content", "Edit": "new_string", "Bash": "command",
                             "MultiEdit": "edits", "NotebookEdit": "new_source"}

# (kind, regex, number of leading characters of the match that are the fixed prefix)
_PREFIXED: tuple[tuple[str, re.Pattern[str], int], ...] = (
    ("openrouter key", re.compile(r"sk-or-v1-[0-9a-fA-F]{20,}"), len("sk-or-v1-")),
    ("anthropic key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), len("sk-ant-")),
    ("sk- API key", re.compile(r"sk-[A-Za-z0-9]{32,}"), len("sk-")),
    ("github token", re.compile(r"gh[pos]_[A-Za-z0-9_]{20,}"), len("ghp_")),
    ("github fine-grained token", re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), len("github_pat_")),
    ("gitlab token", re.compile(r"glpat-[A-Za-z0-9_-]{20,}"), len("glpat-")),
    ("aws access key id", re.compile(r"AKIA[A-Z0-9]{16}"), len("AKIA")),
    ("slack token", re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"), len("xoxb-")),
    ("google api key", re.compile(r"AIza[A-Za-z0-9_-]{35,}"), len("AIza")),
)
_PEM = re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")
# A sensitive word, then (C-39.2) a linear scan of the rest of the name, a separator (= : := =>) and
# a quoted value of 16+ characters. The word is found first (linear), the tail is matched anchored
# at it, and a failed tail skips the rest of the name run, so no input makes the scan quadratic.
_SENSITIVE = re.compile(r"api_key|apikey|secret|token|password", re.IGNORECASE)
_NAME_RUN = re.compile(r"[\w.\-]*")
_ASSIGN_TAIL = re.compile(
    r"[\w.\-]*[\"']?\]?\s*(?::=|=>|=|:)\s*(?P<q>[\"'])(?P<value>(?:(?!(?P=q))[^\n]){16,})(?P=q)")
_VARREF = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)")
_ANGLE = re.compile(r"<[^<>\n]*>")
MAX_SCAN_CHARS = 2_000_000  # C-39.2
TOO_LARGE = "content is too large to scan (limit 2,000,000 characters)"
_SIMPLE_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "e": "\x1b", "E": "\x1b",
               "f": "\f", "v": "\v", "\\": "\\", "'": "'", '"': '"', "?": "?"}
_OCT = re.compile(r"[0-7]{1,3}")
_HEXSEQ = {"x": 2, "u": 4, "U": 8}


def _is_placeholder(text: str) -> bool:
    """C-39.1: the WHOLE value is an angle-bracket form, one repeated character or a $VAR reference."""
    if not text:
        return False
    return len(set(text)) == 1 or bool(_ANGLE.fullmatch(text)) or bool(_VARREF.fullmatch(text))


def _ansi_c(s: str, i: int) -> tuple[str, int]:
    """Unescape ``$'...'`` content starting at s[i] (after the opening quote); returns (text, next index)."""
    out: list[str] = []
    n = len(s)
    while i < n and s[i] != "'":
        c = s[i]
        if c == "\\" and i + 1 < n:
            e = s[i + 1]
            if e in _HEXSEQ:
                digits = s[i + 2:i + 2 + _HEXSEQ[e]]
                k = 0
                while k < len(digits) and digits[k] in "0123456789abcdefABCDEF":
                    k += 1
                if k:
                    try:
                        out.append(chr(int(digits[:k], 16)))
                    except (ValueError, OverflowError):
                        out.append("?")
                    i += 2 + k
                    continue
            m = _OCT.match(s, i + 1)
            if m:
                out.append(chr(int(m.group(0), 8) & 0xFF))
                i = m.end()
                continue
            out.append(_SIMPLE_ESC.get(e, "\\" + e))
            i += 2
            continue
        out.append(c)
        i += 1
    return "".join(out), i + 1


def dequote(command: str) -> str:
    """C-39.3: the shell's view of literal words: quotes and backslash escapes removed, ``$'..'``
    unescaped, so adjacent literals join. Linear time; an unterminated quote just runs to the end."""
    out: list[str] = []
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if c == "\\":
            if i + 1 < n and command[i + 1] != "\n":
                out.append(command[i + 1])
            i += 2
        elif c == "$" and command.startswith("$'", i):
            text, i = _ansi_c(command, i + 2)
            out.append(text)
        elif c == "$" and command.startswith('$"', i):
            i += 1
        elif c == "'":
            j = command.find("'", i + 1)
            j = n if j < 0 else j
            out.append(command[i + 1:j])
            i = j + 1
        elif c == '"':
            i += 1
            while i < n and command[i] != '"':
                if command[i] == "\\" and i + 1 < n and command[i + 1] in '"\\$`\n':
                    if command[i + 1] != "\n":
                        out.append(command[i + 1])
                    i += 2
                else:
                    out.append(command[i])
                    i += 1
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _allow_regexes(cfg: Any) -> list[re.Pattern[str]]:
    out = []
    for pattern in getattr(cfg, "secret_allow_patterns", ()) or ():
        try:
            out.append(re.compile(pattern))
        except re.error as exc:
            raise HookError(f"invalid secret_allow_patterns entry: {exc}") from None
    return out


def scan(text: str, allow: list[re.Pattern[str]] | None = None) -> list[tuple[str, int]]:
    """Return ``(kind, line)`` for each secret-shaped value in ``text``, in order, deduplicated."""
    allow = allow or []
    found: list[tuple[int, str]] = []

    def allowed_by_profile(value: str) -> bool:  # C-39.1: matched against the matched value only
        return any(rx.search(value) for rx in allow)

    for kind, rx, prefix_len in _PREFIXED:
        for m in rx.finditer(text):
            if _is_placeholder(m.group(0)[prefix_len:]) or allowed_by_profile(m.group(0)):
                continue
            found.append((m.start(), kind))
    for m in _PEM.finditer(text):
        if allowed_by_profile(m.group(0)):
            continue
        found.append((m.start(), "private key header"))
    pos = 0
    while True:
        kw = _SENSITIVE.search(text, pos)
        if kw is None:
            break
        m = _ASSIGN_TAIL.match(text, kw.end())
        if m is None:
            pos = _NAME_RUN.match(text, kw.end()).end()  # same failure for any word in this name run
            continue
        pos = m.end()
        value = m.group("value")
        if _VARREF.fullmatch(value) or _is_placeholder(value) or allowed_by_profile(value):
            continue
        found.append((m.start("value"), "credential assignment"))

    out: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    last_index = last_line = 0
    last_line = 1
    for index, kind in sorted(found):
        last_line += text.count("\n", last_index, index)
        last_index = index
        item = (kind, last_line)
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _texts(tool: str, tool_input: dict) -> list[tuple[str, str]] | Decision:
    """The (label, text) pairs to inspect, or a deny Decision for a malformed payload."""
    def bad(what: str) -> Decision:
        return Decision("deny", f"hook error: {tool} {what} is not a string")

    if tool == "MultiEdit":
        edits = tool_input.get("edits")
        if edits is None:
            return []
        if not isinstance(edits, list):
            return Decision("deny", "hook error: MultiEdit edits is not a list")
        out = []
        for i, e in enumerate(edits):
            if not isinstance(e, dict):
                return Decision("deny", f"hook error: MultiEdit edits[{i}] is not an object")
            t = e.get("new_string")
            if t is None:
                continue
            if not isinstance(t, str):
                return bad(f"edits[{i}].new_string")
            out.append((f"edits[{i}].new_string", t))
        return out
    field = INSPECTED[tool]
    t = tool_input.get(field)
    if t is None:
        return []
    if not isinstance(t, str):
        return bad(field)
    return [(field, t)]


def decide(payload: Payload, cfg: Any) -> Decision:
    """Deny Write ``content``, Edit ``new_string``, MultiEdit ``edits[*].new_string``, NotebookEdit
    ``new_source`` or Bash ``command`` holding a secret value. Every role is inspected; other tools
    are allowed. Non-string text and text over 2,000,000 characters fail closed."""
    tool = payload.tool_name or ""
    if tool not in INSPECTED:
        return Decision("allow")
    tool_input = payload.tool_input
    if not isinstance(tool_input, dict):
        return Decision("deny", f"hook error: tool_input of {tool} is not an object")
    texts = _texts(tool, tool_input)
    if isinstance(texts, Decision):
        return texts
    if sum(len(t) for _, t in texts) > MAX_SCAN_CHARS:
        return Decision("deny", f"secrets_guard: {tool} {TOO_LARGE}.")
    allow = _allow_regexes(cfg)
    found: list[str] = []
    for label, text in texts:
        views = [text, dequote(text)] if tool == "Bash" else [text]
        seen: set[tuple[str, int]] = set()
        for view in views:
            for item in scan(view, allow):
                if item not in seen:
                    seen.add(item)
                    found.append(f"{item[0]} at line {item[1]}" + (f" of {label}" if tool == "MultiEdit" else ""))
    if not found:
        return Decision("allow")
    return Decision(
        "deny",
        f"secret value in {tool} {texts[0][0] if tool != 'MultiEdit' else 'edits'} ({'; '.join(found)}). "
        "Reference it by variable name (for example $NAME or os.environ) instead of writing the value.",
    )
