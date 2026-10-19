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
INSPECTED: dict[str, str] = {"Write": "content", "Edit": "new_string", "Bash": "command"}

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
# name containing a sensitive word, a separator (= : := =>), then a quoted value of 16+ characters
_ASSIGN = re.compile(
    r"(?P<name>[\w.\-]*(?:api_key|apikey|secret|token|password)[\w.\-]*)[\"']?\]?\s*"
    r"(?::=|=>|=|:)\s*(?P<q>[\"'])(?P<value>(?:(?!(?P=q))[^\n]){16,})(?P=q)",
    re.IGNORECASE,
)
_VARREF = re.compile(r"\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*)")
_DELIMS = " \t\r\n\f\v'\"`"
_PLACEHOLDER_WORDS = ("xxxx", "example", "placeholder", "your", "changeme", "<", ">")


def _is_placeholder(text: str) -> bool:
    """A single repeated character, a placeholder word (any case), or a trailing ellipsis."""
    if not text:
        return False
    if len(set(text)) == 1:
        return True
    low = text.lower()
    return any(w in low for w in _PLACEHOLDER_WORDS) or low.endswith("...") or low.endswith("…")


def _token(text: str, start: int, end: int) -> str:
    """The whitespace- or quote-delimited token that contains text[start:end]."""
    a = start
    while a > 0 and text[a - 1] not in _DELIMS:
        a -= 1
    b = end
    while b < len(text) and text[b] not in _DELIMS:
        b += 1
    return text[a:b]


def _allow_regexes(cfg: Any) -> list[re.Pattern[str]]:
    out = []
    for pattern in getattr(cfg, "secret_allow_patterns", ()) or ():
        try:
            out.append(re.compile(pattern))
        except re.error as exc:
            raise HookError(f"invalid secret_allow_patterns entry: {exc}") from None
    return out


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def scan(text: str, allow: list[re.Pattern[str]] | None = None) -> list[tuple[str, int]]:
    """Return ``(kind, line)`` for each secret-shaped value in ``text``, in order, deduplicated."""
    allow = allow or []
    found: list[tuple[int, str]] = []

    def allowed_by_profile(*candidates: str) -> bool:
        return any(rx.search(c) for rx in allow for c in candidates)

    for kind, rx, prefix_len in _PREFIXED:
        for m in rx.finditer(text):
            token = _token(text, m.start(), m.end())
            body = m.group(0)[prefix_len:]
            if _is_placeholder(token) or _is_placeholder(body) or _is_placeholder(m.group(0)):
                continue
            if allowed_by_profile(m.group(0), token):
                continue
            found.append((m.start(), kind))
    for m in _PEM.finditer(text):
        if allowed_by_profile(m.group(0)):
            continue
        found.append((m.start(), "private key header"))
    for m in _ASSIGN.finditer(text):
        value = m.group("value")
        if _VARREF.fullmatch(value) or _is_placeholder(value) or allowed_by_profile(value, m.group(0)):
            continue
        found.append((m.start("value"), "credential assignment"))

    out: list[tuple[str, int]] = []
    for index, kind in sorted(found):
        item = (kind, _line_of(text, index))
        if item not in out:
            out.append(item)
    return out


def decide(payload: Payload, cfg: Any) -> Decision:
    """Deny Write ``content``, Edit ``new_string`` or Bash ``command`` holding a secret value.
    Every role is inspected; other tools are allowed. Non-string text fails closed."""
    field = INSPECTED.get(payload.tool_name or "")
    if field is None:
        return Decision("allow")
    tool_input = payload.tool_input
    if not isinstance(tool_input, dict):
        return Decision("deny", f"hook error: tool_input of {payload.tool_name} is not an object")
    text = tool_input.get(field)
    if text is None:
        return Decision("allow")
    if not isinstance(text, str):
        return Decision("deny", f"hook error: {payload.tool_name} {field} is not a string")
    findings = scan(text, _allow_regexes(cfg))
    if not findings:
        return Decision("allow")
    where = "; ".join(f"{kind} at line {line}" for kind, line in findings)
    return Decision(
        "deny",
        f"secret value in {payload.tool_name} {field} ({where}). Reference it by variable name "
        "(for example $NAME or os.environ) instead of writing the value.",
    )
