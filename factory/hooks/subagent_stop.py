"""SubagentStop validators (TB-10, requirement R-16).

Rejects sub-agent reports that lack the shape their role owes the orchestrator. The validator is
chosen by ``payload.agent_type``; ``implement``, ``test``, ``orchestrator`` and unknown types are
allowed. Contracts: ``docs/prds/TB-10-subagent-stop-validators.md``, ``docs/contracts/hook-io.md``
and the TB-10 clauses C-11 to C-18 of ``docs/contracts/clarifications.md``.

Deterministic and offline: only the message and files under the project root are read (plus
read-only local ``git`` queries to find files that are new or changed relative to HEAD). Nothing
project-specific is hard-coded; directories come from the profile (via ``HookConfig``).
"""
from __future__ import annotations

import re
import subprocess
from collections import Counter
from pathlib import Path

from factory.hooks.core import Decision, HookConfig, Payload

MAX_RESEARCH_CHARS = 8000
SEVERITIES = frozenset({"critical", "high", "medium", "low"})
AUDIT_FILE = "BUGS-MITIGATIONS.md"
ADR_DIR = "docs/adr"
REQUIRED_HEADINGS = ("Goals", "Non-goals", "Axioms", "Open questions")
GRADES = ("right_reason", "wrong_reason", "inconclusive")

_CITATION = re.compile(r"(?<![\w./\-:])[\w./\-]+:\d+")
_URL = re.compile(r"https?://[^\s)>\]]+", re.I)
_SLASH_PATH = re.compile(r"(?<![\w/.:~-])(?:~/|\./|\.\./|/)?(?:[\w.@+-]+/)+[\w.@+-]+")
_FILENAME = re.compile(r"(?<![\w/.-])[\w-]+(?:\.[\w-]+)*\.[A-Za-z][A-Za-z0-9]{1,7}\b")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_GRADE_LINE = re.compile(r"^\s*(?:[-*+]\s+)?(?P<id>\S.*?):\s*(?P<grade>right_reason|wrong_reason|inconclusive)\s*$")
_HEADING = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_BULLET = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_FENCE = re.compile(r"^\s*(```|~~~)")
_SOURCES_HEADING = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+Sources[ \t]*:?[ \t]*(?:#+[ \t]*)?$", re.M)
_SOURCES_BOLD = re.compile(r"^[ \t]*(?:\*\*|__)Sources[ \t]*:?[ \t]*(?:\*\*|__)[ \t]*:?[ \t]*", re.M)
_SOURCES_PLAIN = re.compile(r"^[ \t]{0,3}Sources[ \t]*(?::[ \t]*|$)", re.M)  # C-16: plain `Sources` line
_ONE_WAY = re.compile(r"one-way door:\s*yes\b", re.I)


# ---------------------------------------------------------------- shared helpers
def _has_citation(text: str) -> bool:
    return _CITATION.search(text) is not None


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(root), "-c", "core.quotepath=off", *args],
                              capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError):
        return None


def _changed_files(root: Path) -> set[str] | None:
    """Project-relative POSIX paths added or modified relative to HEAD, plus untracked files
    (C-11). ``None`` when git is unavailable, the root is not a repository or HEAD does not
    exist: then every file counts as new."""
    head = _git(root, "rev-parse", "--verify", "-q", "HEAD")
    if head is None or head.returncode != 0:
        return None
    diff = _git(root, "diff", "--name-only", "--relative", "-z", "HEAD", "--")
    other = _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    if diff is None or other is None or diff.returncode != 0 or other.returncode != 0:
        return None
    names: set[str] = set()
    for out in (diff.stdout, other.stdout):
        for item in out.split(b"\0"):
            if item:
                names.add(item.decode("utf-8", "replace"))
    return names


def _head_text(root: Path, rel: str) -> str | None:
    r = _git(root, "show", f"HEAD:./{rel}")
    if r is None or r.returncode != 0:
        return None
    return r.stdout.decode("utf-8", "replace")


def _inside(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (OSError, ValueError):
        return False


def _block(role: str, problems: list[str]) -> Decision:
    if not problems:
        return Decision("allow")
    lines = "\n".join(f"- {p}" for p in problems)
    return Decision("block", f"{role} report rejected; missing or invalid:\n{lines}")


# ---------------------------------------------------------------- research
def _sources_tail(message: str) -> str | None:
    """Text after the first ``Sources`` heading or bold label, or None if there is none."""
    ends = []
    m = _SOURCES_HEADING.search(message)
    if m:
        ends.append(m.end())
    for rx in (_SOURCES_BOLD, _SOURCES_PLAIN):
        m = rx.search(message)
        if m:
            ends.append(m.end())
    return message[min(ends):] if ends else None


def _is_path_like(token: str) -> bool:
    anchored = token.startswith(("/", "./", "../", "~/"))
    return anchored or token.count("/") >= 2 or "." in token.rsplit("/", 1)[-1]


def _has_source(text: str) -> bool:
    if _URL.search(text) or _FILENAME.search(text):
        return True
    return any(_is_path_like(m.group(0)) for m in _SLASH_PATH.finditer(text))


def _validate_research(message: str) -> list[str]:
    problems: list[str] = []
    tail = _sources_tail(message)
    if tail is None:
        problems.append("a Sources section (the label `Sources`, plain, bold or a heading) followed by at least one URL or file path")
    elif not _has_source(tail):
        problems.append("at least one URL or file path after the Sources label")
    for sentence in _SENTENCE_SPLIT.split(message):
        if re.search(r"\bunverified\b", sentence, re.I) and "[unverified]" not in sentence.lower():
            problems.append(f"the marker [unverified] in the sentence: {sentence.strip()[:80]!r}")
    if len(message) > MAX_RESEARCH_CHARS:
        problems.append(f"a message of at most {MAX_RESEARCH_CHARS} characters (got {len(message)})")
    return problems


# ---------------------------------------------------------------- audit
def _cells(line: str) -> list[str]:
    body = line.strip()
    body = body[1:] if body.startswith("|") else body
    body = body[:-1] if body.endswith("|") and not body.endswith("\\|") else body
    return [c.strip() for c in re.split(r"(?<!\\)\|", body)]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and all(re.fullmatch(r":?-+:?", c) for c in cells)


def _audit_rows(text: str) -> list[tuple[int, str]]:
    """(1-based line number, line) for each table row, excluding header and separator lines (C-12)."""
    lines = text.splitlines()
    table = [i for i, ln in enumerate(lines) if ln.lstrip().startswith("|")]
    tableset = set(table)
    skip: set[int] = set()
    for i in table:
        if _is_separator(lines[i]):
            skip.add(i)
            if i - 1 in tableset:
                skip.add(i - 1)
    return [(i + 1, lines[i]) for i in table if i not in skip]


def _validate_audit(message: str, cfg: HookConfig) -> list[str]:
    root = cfg.project_root
    rel = f"{cfg.audit_dir.strip('/')}/{AUDIT_FILE}"
    path = root / rel
    if not path.is_file() or not _inside(root, path):
        if re.search(r"\bno findings\b", message, re.I):
            return []
        return [f"{rel} (file is missing; a report without findings must say `no findings`)"]
    try:
        current = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [f"a readable {rel} ({type(exc).__name__})"]
    changed = _changed_files(root)
    old_rows: Counter[str] = Counter()
    if changed is not None and rel not in changed:
        return []  # untouched since HEAD: no new rows
    if changed is not None:
        old = _head_text(root, rel)
        if old is not None:
            old_rows = Counter(ln.strip() for _, ln in _audit_rows(old))
    problems: list[str] = []
    for number, line in _audit_rows(current):
        key = line.strip()
        if old_rows[key] > 0:
            old_rows[key] -= 1
            continue
        if not any(re.sub(r"[*_`]", "", c).strip().lower() in SEVERITIES for c in _cells(line)):
            problems.append(f"{rel} row {number}: severity cell (critical, high, medium or low)")
        if not _has_citation(line):
            problems.append(f"{rel} row {number}: citation <path>:<line>")
    return problems


# ---------------------------------------------------------------- review
def _validate_review(message: str) -> list[str]:
    problems: list[str] = []
    approve = re.search(r"VERDICT:\s*APPROVE\b", message) is not None
    reject = re.search(r"VERDICT:\s*REJECT\b", message) is not None
    if approve and reject:
        problems.append("one verdict: the message contains both VERDICT: APPROVE and VERDICT: REJECT")
    elif not approve and not reject:
        problems.append("a verdict line `VERDICT: APPROVE` or `VERDICT: REJECT`")
    if reject and not approve and not _has_citation(message):
        problems.append("a citation <path>:<line> (required for REJECT)")
    grades = [m for m in (_GRADE_LINE.match(ln) for ln in message.splitlines()) if m]
    if not grades and not re.search(r"\bno passing cases\b", message, re.I):
        problems.append("at least one grade line `<id>: right_reason|wrong_reason|inconclusive` (or `no passing cases`)")
    if approve and not reject:
        bad = [m.group("id") for m in grades if m.group("grade") != "right_reason"]
        if bad:
            problems.append("no wrong_reason or inconclusive grade with VERDICT: APPROVE (graded: " + ", ".join(bad) + ")")
    return problems


# ---------------------------------------------------------------- design
def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """(line index, level, normalised title) for Markdown headings outside code fences."""
    out: list[tuple[int, int, str]] = []
    fenced = False
    for i, ln in enumerate(lines):
        if _FENCE.match(ln):
            fenced = not fenced
            continue
        if fenced:
            continue
        m = _HEADING.match(ln)
        if m:
            title = re.sub(r"[*_`]", "", m.group(2)).strip().rstrip(":").strip().lower()
            out.append((i, len(m.group(1)), title))
    return out


def _axiom_items(lines: list[str], start: int, end: int) -> list[str]:
    items: list[list[str]] = []
    blank = False
    fenced = False
    for ln in lines[start:end]:
        if _FENCE.match(ln):
            fenced = not fenced
        if _BULLET.match(ln) and not fenced:
            items.append([ln])
            blank = False
        elif not ln.strip():
            blank = True
        elif items and (not blank or ln[:1] in (" ", "\t")):
            items[-1].append(ln)
            blank = False
        else:
            blank = False  # an unindented paragraph after a blank line is not part of an item
    return ["\n".join(i) for i in items]


def _validate_spec(rel: str, text: str) -> list[str]:
    lines = text.splitlines()
    heads = _headings(lines)
    titles = {t for _, _, t in heads}
    problems = [f"{rel}: heading {h}" for h in REQUIRED_HEADINGS if h.lower() not in titles]
    for idx, (line_no, level, title) in enumerate(heads):
        if title != "axioms":
            continue
        end = next((ln for ln, lv, _ in heads[idx + 1:] if lv <= level), len(lines))
        for item in _axiom_items(lines, line_no + 1, end):
            if "check:" not in item:
                first = _BULLET.match(item.splitlines()[0]).group(2).strip()
                problems.append(f"{rel}: `check:` in the Axioms item {first[:60]!r}")
    return problems


def _design_docs(cfg: HookConfig) -> list[tuple[str, Path]]:
    root = cfg.project_root
    changed = _changed_files(root)
    seen: dict[str, Path] = {}
    for d in cfg.design_dirs:
        base = root / d
        if not base.is_dir() or not _inside(root, base):
            continue
        for f in sorted(base.rglob("*")):
            if f.suffix.lower() != ".md" or not f.is_file() or not _inside(root, f):
                continue
            rel = f.relative_to(root).as_posix()
            if changed is None or rel in changed:
                seen[rel] = f
    return sorted(seen.items())


def _adr_exists(cfg: HookConfig) -> bool:
    dirs = {ADR_DIR} | {d.strip("/") for d in cfg.design_dirs if d.strip("/").rsplit("/", 1)[-1] == "adr"}
    for d in dirs:
        base = cfg.project_root / d
        if base.is_dir() and _inside(cfg.project_root, base):
            if any(f.is_file() and not f.name.startswith(".") for f in base.rglob("*")):
                return True
    return False


def _validate_design(cfg: HookConfig) -> list[str]:
    problems: list[str] = []
    one_way = False
    for rel, f in _design_docs(cfg):
        try:
            text = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: a readable file ({type(exc).__name__})")
            continue
        if "spec" in f.name.lower():
            problems.extend(_validate_spec(rel, text))
        if _ONE_WAY.search(text):
            one_way = True
    if one_way and not _adr_exists(cfg):
        problems.append("an ADR file under docs/adr (a design document says `one-way door: yes`)")
    return problems


# ---------------------------------------------------------------- hook entry
def decide(payload: Payload, cfg: HookConfig) -> Decision:
    if payload.event != "SubagentStop":
        return Decision("allow")
    role = payload.agent_type
    if role not in ("research", "audit", "review", "design"):
        return Decision("allow")
    raw = payload.raw.get("last_assistant_message")
    if role in ("research", "review") and not isinstance(raw, str):
        return Decision("block", f"{role} report rejected; missing or invalid:\n- last_assistant_message (a string)")
    message = raw if isinstance(raw, str) else ""
    if role == "research":
        problems = _validate_research(message)
    elif role == "audit":
        problems = _validate_audit(message, cfg)
    elif role == "review":
        problems = _validate_review(message)
    else:
        problems = _validate_design(cfg)
    return _block(role, problems)


def record(payload: Payload, cfg: HookConfig) -> None:
    """Leave a stage event for the stop; telemetry only, the decision above is already made."""
    from factory.ops.events import emit

    if payload.event == "SubagentStop":
        emit(cfg.project_root, "subagent-stop", "-", "stopped", source="hook", role=payload.agent_type)
