"""Ticket ledger (TB-11): shared, tamper-evident memory in a Markdown file.

Contracts: ``docs/contracts/graph-and-ledger.md`` and the Ledger clauses (C-19 to C-25, C-30,
C-31, C-35) of ``docs/contracts/clarifications.md`` (binding). Deterministic given its inputs
(``now`` is passed in); no network, no model call, nothing project-specific.

File layout::

    # <ticket_id>: <title>
    <!-- entries: N; head: <chain> -->

    ## Spec

    ### 2026-10-19T12:00:00Z design
    entry text
    <!-- chain: <sha256 hex>; seq: 1 -->

    ## Research
    ...
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

SECTIONS: tuple[str, ...] = (
    "Spec", "Research", "Architecture", "Evals", "Implementation",
    "Review", "Test Results", "Deploy Log", "Audit Trail",
)

# Which roles may write which section (contract: graph-and-ledger.md).
OWNERS: dict[str, frozenset[str]] = {
    "Spec": frozenset({"design"}),
    "Research": frozenset({"research"}),
    "Architecture": frozenset({"design"}),
    "Evals": frozenset({"test"}),
    "Implementation": frozenset({"implement"}),
    "Review": frozenset({"review"}),
    "Test Results": frozenset({"test"}),
    "Deploy Log": frozenset({"test", "orchestrator"}),
    "Audit Trail": frozenset({"orchestrator"}),
}

SUMMARY_LIMIT = 4000

_HEADER_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z) (\S+)$")
_CHAIN_RE = re.compile(r"^<!-- chain: ([0-9a-f]{64}); seq: ([0-9]+) -->$")
_ANCHOR_RE = re.compile(r"^<!-- entries: ([0-9]+); head:(?: ([0-9a-f]+))? -->$")
_HEADINGS = {f"## {s}": s for s in SECTIONS}


class LedgerError(Exception):
    """A ledger operation was refused (bad role, section, time, existing or missing file...)."""


def chain_value(prev: str, text: str) -> str:
    """C-19: ``sha256(prev + b"\\n" + text)`` as lowercase hex."""
    return hashlib.sha256(prev.encode("utf-8") + b"\n" + text.encode("utf-8")).hexdigest()


def _anchor(n: int, head: str) -> str:
    return f"<!-- entries: {n}; head: {head} -->" if head else f"<!-- entries: {n}; head: -->"  # C-31


def _format_time(now: object) -> str:
    if isinstance(now, datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise LedgerError("now must be a timezone-aware datetime")
        dt = now.astimezone(timezone.utc)
    elif isinstance(now, str):
        if not now.endswith("Z"):
            raise LedgerError(f"now must end with 'Z': {now!r}")
        try:
            dt = datetime.fromisoformat(now[:-1] + "+00:00")
        except ValueError:
            raise LedgerError(f"now is not an ISO 8601 time: {now!r}") from None
    else:
        raise LedgerError(f"now must be a datetime or an ISO string, not {type(now).__name__}")
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- parsing

@dataclass
class _Entry:
    index: int                 # 1-based position in the file
    section: str
    time: str
    role: str
    text: str
    chain: str | None = None   # None: the chain line is missing
    seq: int | None = None


@dataclass
class _Parsed:
    lines: list[str]
    title_ok: bool = False
    anchor: tuple[int, str] | None = None
    headings: list[tuple[str, int]] = field(default_factory=list)   # (section, line index)
    entries: list[_Entry] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _read(path: Path) -> str:
    try:
        with open(path, "r", encoding="utf-8", newline="") as fh:
            return fh.read()
    except FileNotFoundError:
        raise LedgerError(f"ledger not found: {path}") from None
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerError(f"cannot read ledger {path}: {exc}") from None


def _parse(content: str) -> _Parsed:
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    out = _Parsed(lines)
    section: str | None = None
    cur: _Entry | None = None
    body: list[str] = []

    def finish_unterminated() -> None:
        nonlocal cur, body
        if cur is not None:
            while body and body[-1] == "":
                body.pop()
            cur.text = "\n".join(body)
            out.entries.append(cur)
            cur, body = None, []

    for i, line in enumerate(lines):
        if cur is not None:
            m = _CHAIN_RE.match(line)
            if m:
                cur.text = "\n".join(body)
                cur.chain, cur.seq = m.group(1), int(m.group(2))
                out.entries.append(cur)
                cur, body = None, []
                continue
            if _HEADER_RE.match(line) or line in _HEADINGS:
                finish_unterminated()
            else:
                body.append(line)
                continue
        if i == 0:
            out.title_ok = line.startswith("# ")
            if not out.title_ok:
                out.problems.append("line 1: missing title line")
            continue
        if i == 1:
            m = _ANCHOR_RE.match(line)
            if m:
                out.anchor = (int(m.group(1)), m.group(2) or "")
                continue
        if line in _HEADINGS:
            section = _HEADINGS[line]
            out.headings.append((section, i))
            continue
        h = _HEADER_RE.match(line)
        if h:
            if section is None:
                out.problems.append(f"line {i + 1}: entry outside any section")
                continue
            cur = _Entry(len(out.entries) + 1, section, h.group(1), h.group(2), "")
            body = []
            continue
        if line == "":
            continue
        out.problems.append(f"line {i + 1}: unexpected line outside an entry")
    finish_unterminated()
    return out


def _by_seq(entries: list[_Entry]) -> list[_Entry]:
    return sorted((e for e in entries if e.seq is not None), key=lambda e: (e.seq, e.index))


def _where(e: _Entry) -> str:
    return f"section '{e.section}' entry {e.index}"


def _anchor_problems(p: _Parsed) -> list[str]:
    if p.anchor is None:
        return ["anchor line missing or malformed (expected '<!-- entries: N; head: <chain> -->' on line 2)"]
    chained = _by_seq(p.entries)
    head = chained[-1].chain if chained else ""
    n, claimed = p.anchor
    out = []
    if n != len(chained):
        out.append(f"anchor says {n} entries but the file has {len(chained)} (an entry was removed or added)")
    if claimed != (head or ""):
        out.append("anchor head does not match the last entry's chain value")
    return out


def _structure_problems(p: _Parsed) -> list[str]:
    names = [s for s, _ in p.headings]
    out = []
    if names != list(SECTIONS):
        missing = [s for s in SECTIONS if s not in names]
        if missing:
            out.append("section heading missing: " + ", ".join(f"'{m}'" for m in missing))
        elif len(names) != len(SECTIONS):
            out.append("section heading repeated")
        else:
            out.append("section headings are out of order")
    return out


def verify(path: str | os.PathLike) -> list[str]:
    """Return the problems found in the ledger (empty when it is intact)."""
    try:
        content = _read(Path(path))
    except LedgerError as exc:
        return [str(exc)]
    p = _parse(content)
    problems: list[str] = list(p.problems)
    problems += _structure_problems(p)
    problems += _anchor_problems(p)

    for e in p.entries:
        owners = OWNERS[e.section]
        if e.role not in owners:
            problems.append(f"{_where(e)}: role '{e.role}' may not write this section")
        if e.chain is None:
            problems.append(f"{_where(e)}: missing chain line")

    chained = _by_seq(p.entries)
    seen: dict[int, _Entry] = {}
    for e in chained:
        if e.seq in seen:
            problems.append(f"{_where(e)}: seq {e.seq} is repeated")
        else:
            seen[e.seq] = e
    expect = 1
    for s in sorted(seen):
        if s != expect:
            problems.append(f"{_where(seen[s])}: seq gap (expected {expect}, found {s})")
        expect = s + 1
    for s, e in seen.items():
        if s == 1:
            prev = ""
        elif (s - 1) in seen:
            prev = seen[s - 1].chain or ""
        else:
            problems.append(f"{_where(e)}: chain cannot be checked, previous entry (seq {s - 1}) is missing")
            continue
        if chain_value(prev, e.text) != e.chain:
            problems.append(f"{_where(e)}: chain mismatch (entry text was edited, or the chain was altered)")
    return problems


# ---------------------------------------------------------------- operations

def create_ledger(path: str | os.PathLike, ticket_id: str, title: str) -> None:
    """Create ``path`` with the nine sections. Raises :class:`LedgerError` if it exists."""
    for label, value in (("ticket_id", ticket_id), ("title", title)):
        if not isinstance(value, str) or "\n" in value or "\r" in value:
            raise LedgerError(f"{label} must be a single-line string")
    if not ticket_id:
        raise LedgerError("ticket_id must not be empty")
    p = Path(path)
    parts = [f"# {ticket_id}: {title}", _anchor(0, ""), ""]
    for s in SECTIONS:
        parts += [f"## {s}", ""]
    data = "\n".join(parts) + "\n"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "x", encoding="utf-8", newline="") as fh:
            fh.write(data)
    except FileExistsError:
        raise LedgerError(f"ledger already exists: {p}") from None
    except OSError as exc:
        raise LedgerError(f"cannot create ledger {p}: {exc}") from None


def _forged(line: str) -> bool:
    return bool(_HEADER_RE.match(line) or line in _HEADINGS
                or line.startswith("<!-- chain:") or line.startswith("<!-- entries:"))


def append(path: str | os.PathLike, section: str, role: str, text: str, now: object) -> None:
    """Append one chained entry to ``section`` as ``role``.

    Raises :class:`LedgerError` for an unknown section, a role that may not write it, a bad
    ``now``, text that imitates ledger structure, a missing file, or a ledger whose anchor line
    no longer matches its entries (appending would hide the removal).
    """
    p = Path(path)
    if section not in OWNERS:
        raise LedgerError(f"unknown section {section!r}")
    if role not in OWNERS[section]:
        raise LedgerError(f"role {role!r} may not write section {section!r}")
    if not isinstance(text, str):
        raise LedgerError("text must be a string")
    stamp = _format_time(now)
    body = text.rstrip("\n")
    if any(_forged(ln) for ln in body.split("\n")):
        raise LedgerError("entry text may not contain lines that imitate ledger headers, chain lines, anchors or section headings")

    parsed = _parse(_read(p))
    bad = _structure_problems(parsed) + _anchor_problems(parsed)
    if bad:
        raise LedgerError("ledger is damaged, not appending: " + "; ".join(bad))
    chained = _by_seq(parsed.entries)
    prev = chained[-1].chain if chained else ""
    seq = (chained[-1].seq if chained else 0) + 1
    new_chain = chain_value(prev or "", body)

    order = [s for s, _ in parsed.headings]
    idx = order.index(section)
    at = parsed.headings[idx + 1][1] if idx + 1 < len(order) else len(parsed.lines)
    block = [f"### {stamp} {role}"] + ([body] if body else []) + [f"<!-- chain: {new_chain}; seq: {seq} -->", ""]
    lines = list(parsed.lines)
    lines[at:at] = block
    lines[1] = _anchor(len(chained) + 1, new_chain)
    data = "\n".join(lines) + "\n"
    tmp = p.with_name(p.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as fh:
            fh.write(data)
        os.replace(tmp, p)
    except OSError as exc:
        raise LedgerError(f"cannot write ledger {p}: {exc}") from None


def _render_summary(p: _Parsed, limit: int | None) -> str:
    latest: dict[str, _Entry] = {}
    for e in _by_seq(p.entries):
        latest[e.section] = e
    out = [p.lines[0] if p.lines else ""]
    for s in SECTIONS:
        out.append(f"## {s}")
        e = latest.get(s)
        if e is None:
            out.append("(no entries)")
            continue
        out.append(f"### {e.time} {e.role}")
        text = e.text
        if limit is not None and len(text) > limit:
            text = text[:limit].rstrip() + "..."
        if text:
            out.append(text)
    return "\n".join(out)


def load_summary(path: str | os.PathLike) -> str:
    """Section headings plus the latest entry of each section, at most 4,000 characters."""
    p = _parse(_read(Path(path)))
    full = _render_summary(p, None)
    if len(full) <= SUMMARY_LIMIT:
        return full
    lo, hi = 0, max(len(e.text) for e in p.entries)
    while lo < hi:  # largest per-entry text length that still fits
        mid = (lo + hi + 1) // 2
        if len(_render_summary(p, mid)) <= SUMMARY_LIMIT:
            lo = mid
        else:
            hi = mid - 1
    return _render_summary(p, lo)[:SUMMARY_LIMIT]


_TICKET_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def current_ticket(project_root: str | os.PathLike) -> str | None:
    """The id named by ``<project_root>/.factory/current_ticket`` (whitespace trimmed), or None
    when the file is absent or blank. Raises :class:`LedgerError` for an id that is not a plain
    file stem (no path separators), so it cannot point outside the ledger directory."""
    f = Path(project_root) / ".factory" / "current_ticket"
    try:
        raw = f.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as exc:
        raise LedgerError(f"cannot read {f}: {exc}") from None
    tid = raw.strip()
    if not tid:
        return None
    if not _TICKET_ID_RE.match(tid) or ".." in tid:
        raise LedgerError(f"invalid ticket id in {f}: {tid!r}")
    return tid
