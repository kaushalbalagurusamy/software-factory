#!/usr/bin/env python3
"""Check and order a spec-recomposition requirements register.

Usage:
  register.py check  BRIEF.md REQUIREMENTS.md
  register.py order  BRIEF.md REQUIREMENTS.md [--write]

The register is a markdown file with one table whose header row starts with
"| ID | Line |". Required columns: ID, Line, Requirement, Type, Depends on.
Lines of the brief that need no row are declared in the register with an HTML
comment such as  <!-- skip-lines: 1-6, 12 -->  (headings, blank lines and
horizontal rules are skipped automatically).

`check` exits non-zero when any brief line lacks a row, a row cites a line that
is blank or out of range, a type is unknown, an ID repeats, a dependency is
dangling, or the dependency graph has a cycle.

`order` computes a tier for every row (tier 0 = no dependencies; otherwise
1 + the highest tier among its dependencies) and prints the dependency-ordered
build list. With --write it replaces the block between
<!-- build-order:start --> and <!-- build-order:end --> in the register.
"""
import re
import sys
from collections import defaultdict

TYPES = [
    "Given",
    "Context",
    "Constraint",
    "Hard",
    "Behaviour",
    "Quality",
    "Test",
    "Research",
    "Deliverable",
    "Optional",
]
TYPE_RANK = {t: i for i, t in enumerate(TYPES)}
LINE_RE = re.compile(r"^(\d+)([a-z]?)$")


def brief_lines_needing_rows(brief_path, skip):
    needed = set()
    with open(brief_path, encoding="utf-8") as f:
        for n, raw in enumerate(f, start=1):
            s = raw.strip()
            if not s or s.startswith("#") or re.fullmatch(r"[-*_]{3,}", s):
                continue
            if n in skip:
                continue
            needed.add(n)
        total = n
    return needed, total


def parse_skip(text):
    skip = set()
    for m in re.finditer(r"<!--\s*skip-lines:\s*([^>]*?)\s*-->", text):
        for part in m.group(1).split(","):
            part = part.strip()
            if not part:
                continue
            if "-" in part:
                a, b = part.split("-", 1)
                skip.update(range(int(a), int(b) + 1))
            else:
                skip.add(int(part))
    return skip


def split_row(line):
    # Split a markdown table row on unescaped pipes.
    cells = re.split(r"(?<!\\)\|", line.strip())
    return [c.strip() for c in cells[1:-1]]


def parse_register(path):
    text = open(path, encoding="utf-8").read()
    rows, header, errors = [], None, []
    for ln, line in enumerate(text.splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            header = None  # a table ends at the first non-table line
            continue
        cells = split_row(line)
        if header is None:
            if len(cells) >= 2 and cells[0] == "ID" and cells[1] == "Line":
                header = cells
            continue
        if all(re.fullmatch(r":?-+:?", c) for c in cells):
            continue
        if len(cells) != len(header):
            errors.append(f"register line {ln}: {len(cells)} cells, header has {len(header)}")
            continue
        rows.append(dict(zip(header, cells), _ln=ln))
    if not rows:
        errors.append("no table with a header row starting '| ID | Line |' found")
    return text, rows, errors


def deps_of(row):
    raw = row.get("Depends on", "")
    if raw in ("", "-", "—", "none"):
        return []
    return [d.strip() for d in re.split(r"[,\s]+", raw) if d.strip()]


def build_graph(rows, errors):
    ids = {}
    for r in rows:
        rid = r["ID"]
        if rid in ids:
            errors.append(f"duplicate ID {rid} (register lines {ids[rid]['_ln']} and {r['_ln']})")
        ids[rid] = r
    for r in rows:
        for d in deps_of(r):
            if d not in ids:
                errors.append(f"{r['ID']}: dependency {d} does not exist")
            elif d == r["ID"]:
                errors.append(f"{r['ID']}: depends on itself")
    return ids


def tiers(ids, errors):
    tier, state = {}, {}

    def visit(rid, stack):
        if state.get(rid) == "done":
            return tier[rid]
        if state.get(rid) == "active":
            cycle = stack[stack.index(rid):] + [rid]
            errors.append("dependency cycle: " + " -> ".join(cycle))
            return 0
        state[rid] = "active"
        ds = [d for d in deps_of(ids[rid]) if d in ids and d != rid]
        t = 0 if not ds else 1 + max(visit(d, stack + [rid]) for d in ds)
        state[rid] = "done"
        tier[rid] = t
        return t

    for rid in ids:
        visit(rid, [])
    return tier


def check(brief, register):
    text, rows, errors = parse_register(register)
    skip = parse_skip(text)
    needed, total = brief_lines_needing_rows(brief, skip)
    covered = set()
    raw_lines = open(brief, encoding="utf-8").read().splitlines()
    for r in rows:
        m = LINE_RE.match(r.get("Line", ""))
        if not m:
            errors.append(f"{r['ID']}: Line '{r.get('Line')}' is not a number with an optional letter suffix")
            continue
        n = int(m.group(1))
        if n < 1 or n > total or not raw_lines[n - 1].strip():
            errors.append(f"{r['ID']}: cites brief line {n}, which is blank or out of range")
        covered.add(n)
        if r.get("Type") not in TYPE_RANK:
            errors.append(f"{r['ID']}: unknown Type '{r.get('Type')}' (allowed: {', '.join(TYPES)})")
    missing = sorted(needed - covered)
    for n in missing:
        errors.append(f"brief line {n} has no row: {raw_lines[n - 1].strip()[:90]}")
    ids = build_graph(rows, errors)
    tiers(ids, errors)
    counts = defaultdict(int)
    for r in rows:
        counts[r.get("Type")] += 1
    print(f"rows: {len(rows)}; brief lines needing rows: {len(needed)}; covered: {len(needed & covered)}; skipped: {sorted(skip)}")
    print("by type: " + ", ".join(f"{t} {counts[t]}" for t in TYPES if counts[t]))
    if errors:
        for e in errors:
            print("FAIL " + e)
        return 1
    print("OK every brief line is covered, types are valid, dependencies resolve and are acyclic")
    return 0


def order(brief, register, write):
    text, rows, errors = parse_register(register)
    ids = build_graph(rows, errors)
    tier = tiers(ids, errors)
    if errors:
        for e in errors:
            print("FAIL " + e)
        return 1
    by_tier = defaultdict(list)
    for rid, r in ids.items():
        by_tier[tier[rid]].append(r)
    out = []
    out.append("Generated by `register.py order --write`; do not edit by hand. Tier 0 rows depend on nothing; every other row sits one tier above its deepest dependency, so work can proceed top to bottom.")
    out.append("")
    for t in sorted(by_tier):
        out.append(f"### Tier {t}")
        out.append("")
        out.append("| ID | Type | Requirement | Depends on |")
        out.append("|---|---|---|---|")
        for r in sorted(by_tier[t], key=lambda r: (TYPE_RANK.get(r["Type"], 99), r["ID"])):
            req = r["Requirement"]
            if len(req) > 110:
                req = req[:107].rstrip() + "..."
            out.append(f"| {r['ID']} | {r['Type']} | {req} | {r.get('Depends on') or '-'} |")
        out.append("")
    block = "\n".join(out).rstrip() + "\n"
    if not write:
        print(block)
        return 0
    start, end = "<!-- build-order:start -->", "<!-- build-order:end -->"
    if start not in text or end not in text:
        print(f"FAIL register has no {start} ... {end} block to replace")
        return 1
    pre, rest = text.split(start, 1)
    _, post = rest.split(end, 1)
    open(register, "w", encoding="utf-8").write(pre + start + "\n\n" + block + "\n" + end + post)
    print(f"wrote build order: {len(rows)} rows in {len(by_tier)} tiers")
    return 0


def main(argv):
    if len(argv) < 4 or argv[1] not in ("check", "order"):
        print(__doc__)
        return 2
    if argv[1] == "check":
        return check(argv[2], argv[3])
    return order(argv[2], argv[3], "--write" in argv[4:])


if __name__ == "__main__":
    sys.exit(main(sys.argv))
