"""Requirement ledger: TSV read/write and the `check` rules (docs/intake-format.md)."""
from __future__ import annotations

import csv
import hashlib
import re
from pathlib import Path

COLUMNS = ["req_id", "source_ref", "text_sha", "category", "trust", "finding_ids", "disposition",
           "status", "slice_ids", "artifact_or_waits_on"]
LEGACY = ["req_id", "trust", "status"]
STATUSES = ("satisfied", "partial", "blocked", "unserved")
TRUST_RE = re.compile(r"^(trusted|(conditioned|rejected)\((F-\d{3,})\))$")
REF_RE = re.compile(r"^(?P<file>.+):(?P<line>\d+)$")
OPEN_CRITICAL_RE = re.compile(r"open\s+critical", re.I)


def line_sha(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def file_sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_lines(path: Path) -> list[str]:
    return Path(path).read_text(encoding="utf-8").split("\n")


def read(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        rows = [{k: (v or "") for k, v in r.items() if k is not None} for r in rd if r.get("req_id")]
        return list(rd.fieldnames or []), rows


def write(path: Path, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLUMNS})


def base_status(status: str) -> str:
    """`blocked; open critical F-002` -> `blocked`. The qualifier keeps the slices checker's substring rule working."""
    return status.split(";", 1)[0].strip().lower()


def trust_finding(trust: str) -> str | None:
    m = TRUST_RE.match(trust.strip())
    return m.group(3) if m else None


def line_of(row: dict, source: Path) -> int | None:
    m = REF_RE.match(row.get("source_ref", ""))
    if m and Path(m.group("file")).name == Path(source).name:
        return int(m.group("line"))
    return None


def check(source: Path, ledger: Path, repo_root: Path | None = None, open_critical: set[str] | None = None) -> list[str]:
    """Return a list of error strings. `open_critical` = finding ids known (from a sweep record) to be open Critical."""
    root = Path(repo_root or ".")
    errs: list[str] = []
    source, ledger = Path(source), Path(ledger)
    if not source.is_file():
        return [f"source: {source} not found"]
    if not ledger.is_file():
        return [f"ledger: {ledger} not found"]
    header, rows = read(ledger)
    missing = [c for c in LEGACY if c not in header]
    if missing:
        return [f"ledger: header lacks {', '.join(missing)}"]
    full = all(c in header for c in COLUMNS)
    if not full:
        absent = [c for c in COLUMNS if c not in header]
        errs.append(f"ledger: three-column form cannot prove source coverage; missing column(s) {', '.join(absent)} "
                    f"(source_ref is required to show every source line is covered)")
    lines = source_lines(source)
    covered: dict[int, list[str]] = {}
    seen: set[str] = set()
    for r in rows:
        rid = r["req_id"]
        if rid in seen:
            errs.append(f"{rid}: duplicate req_id")
        seen.add(rid)
        trust, status = r.get("trust", "").strip(), r.get("status", "").strip()
        if not TRUST_RE.match(trust):
            errs.append(f"{rid}: trust {trust!r} must be trusted, conditioned(F-nnn) or rejected(F-nnn)")
        st = base_status(status)
        category = r.get("category", "").strip()
        waits = r.get("artifact_or_waits_on", "").strip()
        if st == "context":
            if category != "context":
                errs.append(f"{rid}: status context is only valid with category context")
            elif not waits:
                errs.append(f"{rid}: context row needs a reason in artifact_or_waits_on")
        elif st not in STATUSES:
            errs.append(f"{rid}: status {status!r} must be one of {', '.join(STATUSES)} (optionally followed by '; ...')")
        if st == "blocked" and not waits:
            errs.append(f"{rid}: blocked row must name what it waits on in artifact_or_waits_on")
        if st == "satisfied":
            arts = [a.strip().split("#", 1)[0].strip() for a in waits.split(";") if a.strip()]
            if not arts:
                errs.append(f"{rid}: satisfied row must name an artifact in artifact_or_waits_on")
            for a in arts:
                if not (root / a).exists():
                    errs.append(f"{rid}: satisfied artifact {a} does not exist under {root}")
        if trust.startswith("trusted") and OPEN_CRITICAL_RE.search(status):
            errs.append(f"{rid}: trusted row carries an open Critical finding ({status})")
        if trust.startswith("trusted") and open_critical:
            hit = open_critical & {x.strip() for x in r.get("finding_ids", "").split(";") if x.strip()}
            if hit:
                errs.append(f"{rid}: trusted row is tied to open Critical finding(s) {', '.join(sorted(hit))}")
        tf = trust_finding(trust)
        if tf and full and tf not in {x.strip() for x in r.get("finding_ids", "").split(";")}:
            errs.append(f"{rid}: trust names {tf} which is missing from finding_ids")
        if not full:
            continue
        ref = r.get("source_ref", "").strip()
        if ref.startswith("omission:"):
            if not r.get("text_sha", "").strip():
                errs.append(f"{rid}: omission row needs text_sha of its text")
            continue
        m = REF_RE.match(ref)
        if not m:
            errs.append(f"{rid}: source_ref {ref!r} must be file:line")
            continue
        if Path(m.group("file")).name != source.name:
            errs.append(f"{rid}: source_ref file {m.group('file')} is not the source {source.name}")
            continue
        n = int(m.group("line"))
        if not 1 <= n <= len(lines):
            errs.append(f"{rid}: source_ref {ref} is outside the source ({len(lines)} lines)")
            continue
        covered.setdefault(n, []).append(rid)
        if r.get("text_sha", "").strip() != line_sha(lines[n - 1]):
            errs.append(f"{rid}: text_sha does not match {source.name}:{n}; the source text changed, re-extract the row")
    if full:
        for n, text in enumerate(lines, 1):
            if text.strip() and n not in covered:
                errs.append(f"{source.name}:{n} not covered by any ledger row (a silent drop): {text.strip()[:60]!r}")
    return errs
