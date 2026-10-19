"""Research seeds file (research/seeds.tsv) check."""
from __future__ import annotations

import csv
import re
from pathlib import Path

COLUMNS = ["seed_id", "topic", "lens", "question", "priority", "depends_on", "status", "output_path"]
PRIORITIES = ("P0", "P1", "P2", "P3")
STATUSES = ("open", "in-progress", "completed", "blocked", "abandoned")
DEFAULT_LENSES = Path(__file__).resolve().parent / "lenses.txt"


def load_lenses(path: Path | None) -> tuple[set[str], Path]:
    cands = [Path(path)] if path else [Path("research/lenses.txt"), DEFAULT_LENSES]
    for c in cands:
        if c.is_file():
            return {ln.strip() for ln in c.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")}, c
    raise FileNotFoundError(f"lens list not found: {', '.join(map(str, cands))}")


def _has_heading(text: str, needle: str) -> bool:
    return any(re.match(r"^#{1,6}\s+.*" + needle, ln, re.I) for ln in text.splitlines())


def check(seeds_file: Path, lenses: set[str], root: Path = Path(".")) -> list[str]:
    if not seeds_file.is_file():
        return [f"{seeds_file} not found"]
    with open(seeds_file, newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f, delimiter="\t")
        missing = [c for c in COLUMNS if c not in (rd.fieldnames or [])]
        if missing:
            return [f"seeds: header lacks {', '.join(missing)}"]
        rows = [{k: (v or "").strip() for k, v in r.items() if k} for r in rd if any((v or "").strip() for v in r.values())]
    errs: list[str] = []
    ids = [r["seed_id"] for r in rows]
    for i in sorted({x for x in ids if ids.count(x) > 1}):
        errs.append(f"{i}: duplicate seed_id")
    deps: dict[str, list[str]] = {}
    by = {r["seed_id"]: r for r in rows}
    for r in rows:
        i = r["seed_id"]
        if not i:
            errs.append("a row has no seed_id")
        if r["lens"] not in lenses:
            errs.append(f"{i}: lens {r['lens']!r} is not in the configured lens list")
        if r["priority"] not in PRIORITIES:
            errs.append(f"{i}: priority {r['priority']!r} must be one of {', '.join(PRIORITIES)}")
        if r["status"] not in STATUSES:
            errs.append(f"{i}: status {r['status']!r} must be one of {', '.join(STATUSES)}")
        if not r["topic"] or not r["question"]:
            errs.append(f"{i}: topic and question are required")
        deps[i] = [d.strip() for d in re.split(r"[;,]", r["depends_on"]) if d.strip()]
        for d in deps[i]:
            if d not in by:
                errs.append(f"{i}: depends_on {d} is not a seed")
    # cycles (DFS, white/grey/black)
    colour: dict[str, int] = {}

    def visit(n: str, stack: list[str]) -> None:
        colour[n] = 1
        for d in deps.get(n, []):
            if d not in by:
                continue
            if colour.get(d) == 1:
                errs.append("depends_on cycle " + " -> ".join(stack[stack.index(d):] + [n, d]) if d in stack else f"depends_on cycle at {d}")
            elif d not in colour:
                visit(d, stack + [n])
        colour[n] = 2

    for n in by:
        if n not in colour:
            visit(n, [])
    for r in rows:
        if r["status"] != "completed":
            continue
        i = r["seed_id"]
        for d in deps.get(i, []):
            if d in by and by[d]["status"] != "completed":
                errs.append(f"{i}: completed but depends on {d} which is {by[d]['status']}")
        out = r["output_path"]
        if not out:
            errs.append(f"{i}: completed seed has no output_path")
            continue
        p = Path(root) / out
        if not p.is_file():
            errs.append(f"{i}: output_path {out} does not exist")
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        if not _has_heading(text, r"sources"):
            errs.append(f"{i}: {out} has no 'Sources' heading")
        if not _has_heading(text, r"could\s+not\s+verify"):
            errs.append(f"{i}: {out} has no 'could not verify' heading")
    return errs
