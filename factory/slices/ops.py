"""Checks and state files: criteria.lock, amendments.md, verification.json, dependency graph."""
from __future__ import annotations

import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .model import PRIORITIES, SECTIONS, STATUSES, META_KEYS, STORY_BODY, STORY_CONTEXT, Slice, parse, read_frontmatter, sha

APPROVAL = re.compile(r"^(human|codex):\S+$")
GENESIS = "0" * 64


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- dependency graph
def load_graph(root: Path) -> dict[str, dict]:
    g = {}
    for p in sorted(root.glob("*/proposal.md")):
        meta, _, _ = read_frontmatter(p)
        deps = meta.get("depends_on")
        g[p.parent.name] = {
            "id": p.parent.name, "priority": meta.get("priority", "P3"),
            "status": meta.get("status", "draft"),
            "depends_on": [d for d in deps if isinstance(d, str)] if isinstance(deps, list) else [],
        }
    return g


def find_cycles(g: dict[str, dict]) -> list[list[str]]:
    cycles: list[list[str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(n: str) -> None:
        state[n] = 1
        stack.append(n)
        for d in g[n]["depends_on"]:
            if d not in g:
                continue
            if state.get(d) == 1:
                cycles.append(stack[stack.index(d):] + [d])
            elif d not in state:
                visit(d)
        stack.pop()
        state[n] = 2

    for n in g:
        if n not in state:
            visit(n)
    return cycles


def triage(root: Path) -> dict:
    g = load_graph(root)
    cycles = find_cycles(g)
    in_cycle = {n for c in cycles for n in c}
    unknown = {n: [d for d in v["depends_on"] if d not in g] for n, v in g.items()}
    unknown = {n: d for n, d in unknown.items() if d}
    placed: list[str] = []
    remaining = {n for n in g if n not in in_cycle}
    while remaining:
        ready = [n for n in remaining
                 if all(d in placed for d in g[n]["depends_on"] if d in g) and n not in unknown]
        if not ready:
            break
        pick = min(ready, key=lambda n: (g[n]["priority"], n))
        placed.append(pick)
        remaining.discard(pick)
    order = [{k: g[n][k] for k in ("id", "priority", "status", "depends_on")} for n in placed]
    blocked = []
    for n, v in g.items():
        waiting = [d for d in v["depends_on"] if d in g and g[d]["status"] != "done"]
        waiting += [f"unknown:{d}" for d in unknown.get(n, [])]
        if waiting:
            blocked.append({"id": n, "waiting_on": waiting})
    return {"order": order, "blocked": blocked, "cycles": cycles, "unknown_dependencies": unknown,
            "unplaced": sorted(remaining)}


# ---------------------------------------------------------------- amendments and lock
def parse_amendments(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## Amendment"):
            out.append({})
        elif out and (m := re.match(r"^- ([a-z-]+): ?(.*)$", line)):
            out[-1][m.group(1)] = m.group(2).strip()
    return out


def _id_hashes(v: str) -> dict[str, str]:
    res = {}
    for part in v.split(","):
        part = part.strip()
        if part:
            k, _, h = part.partition("=")
            res[k.strip()] = h.strip()
    return res


def baseline(sl_path: Path) -> tuple[dict[str, str] | None, set[str], list[str]]:
    """Locked item hashes overlaid with amendments: (items, removed ids, errors)."""
    lp = sl_path / "criteria.lock"
    if not lp.is_file():
        return None, set(), []
    errs: list[str] = []
    try:
        lock = json.loads(lp.read_text(encoding="utf-8"))
        items = dict(lock["items"])
    except (ValueError, KeyError, TypeError):
        return None, set(), ["criteria.lock: unreadable"]
    removed: set[str] = set()
    for i, a in enumerate(parse_amendments(sl_path / "amendments.md"), 1):
        weak = {k: _id_hashes(a.get(k, "")) for k in ("changed", "removed")}
        if (weak["changed"] or weak["removed"]) and not APPROVAL.match(a.get("approved-by", "")):
            errs.append(f"amendments.md: amendment {i} changes or removes criteria without a "
                        f"human:<ref> or codex:<ref> approved-by marker")
            continue
        for k, h in _id_hashes(a.get("added", "")).items():
            items[k] = h
        for k, h in weak["changed"].items():
            items[k] = h
        for k in weak["removed"]:
            items.pop(k, None)
            removed.add(k)
    return items, removed, errs


def lock_errors(s: Slice) -> list[str]:
    base, removed, errs = baseline(s.path)
    if base is None:
        return errs
    cur = s.items()
    for k, h in base.items():
        if k not in cur:
            errs.append(f"lock: criterion {k} was removed without an approved amendment")
        elif cur[k] != h:
            errs.append(f"lock: criterion {k} differs from the locked or amended version "
                        f"(any edit needs an amendment; weakening needs --approved-by)")
    for k in cur:
        if k not in base:
            errs.append(f"lock: {k} was added without an amendments.md entry")
    return errs


def write_lock(s: Slice) -> None:
    items = s.items()
    combined = hashlib.sha256(json.dumps(items, sort_keys=True).encode()).hexdigest()
    (s.path / "criteria.lock").write_text(
        json.dumps({"version": 1, "locked_at": now(), "combined_sha256": combined, "items": items},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- verification chain
def entry_hash(e: dict) -> str:
    body = {k: v for k, v in e.items() if k != "hash"}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_chain(sl_path: Path) -> list[dict]:
    p = sl_path / "verification.json"
    if not p.is_file():
        return []
    return json.loads(p.read_text(encoding="utf-8")).get("entries", [])


def chain_errors(sl_path: Path) -> list[str]:
    try:
        entries = load_chain(sl_path)
    except (ValueError, AttributeError):
        return ["verification.json: unreadable"]
    prev = GENESIS
    errs = []
    for i, e in enumerate(entries):
        if e.get("seq") != i or e.get("prev") != prev or e.get("hash") != entry_hash(e):
            errs.append(f"verification chain broken at entry {i} (task {e.get('task')}); "
                        f"earlier entries were altered or reordered")
            break
        prev = e["hash"]
    return errs


def append_verification(sl_path: Path, task_id: str, task_sha: str, commit: str, evidence: str) -> dict:
    entries = load_chain(sl_path)
    e = {"seq": len(entries), "task": task_id, "verified": True, "by": "qa", "commit": commit,
         "evidence": evidence, "at": now(), "task_sha": task_sha,
         "prev": entries[-1]["hash"] if entries else GENESIS}
    e["hash"] = entry_hash(e)
    entries.append(e)
    (sl_path / "verification.json").write_text(
        json.dumps({"entries": entries, "head": e["hash"]}, indent=2) + "\n", encoding="utf-8")
    return e


# ---------------------------------------------------------------- check
def check(path: Path, ledger: Path | None = None, with_lock: bool = True) -> list[str]:
    s = parse(path)
    errs = list(s.errors)
    m = s.meta
    for k in META_KEYS:
        if k not in m:
            errs.append(f"frontmatter: missing {k}")
    if m.get("id") not in (None, path.name):
        errs.append(f"frontmatter: id {m.get('id')!r} must equal the directory name {path.name!r}")
    if "priority" in m and m["priority"] not in PRIORITIES:
        errs.append(f"frontmatter: priority {m['priority']!r} not one of {', '.join(PRIORITIES)}")
    if "status" in m and m["status"] not in STATUSES:
        errs.append(f"frontmatter: status {m['status']!r} not one of {', '.join(STATUSES)}")
    for k in ("depends_on", "source_requirement_ids"):
        if k in m and not (isinstance(m[k], list) and all(isinstance(x, str) for x in m[k])):
            errs.append(f"frontmatter: {k} must be a list of strings")
    # section order
    pos = [s.sections.index(n) if n in s.sections else None for n in SECTIONS]
    for n in SECTIONS:
        if s.sections.count(n) != 1:
            errs.append(f"sections: '## {n}' must appear exactly once")
    present = [p for p in pos if p is not None]
    if present != sorted(present):
        errs.append("sections: wrong order; required order is " + " > ".join(SECTIONS))
    elif s.sections.count("UX stories") == 1 and s.sections.index("UX stories") > 1:
        errs.append("sections: UX stories must come first, before any technical content (only Why may precede)")
    # stories
    if not s.stories:
        errs.append("stories: no '### US-n' story under '## UX stories'")
    for sid, text in s.stories.items():
        if not STORY_BODY.search(text):
            errs.append(f"{sid}: must read 'As a <persona> I can ... so that ...'")
        if not STORY_CONTEXT.search(text):
            errs.append(f"{sid}: needs a 'Device:' or 'Context:' line")
    # requirements
    if not s.reqs:
        errs.append("specs: no '### Requirement: AC-n' found under specs/<capability>/spec.md")
    for rid, r in s.reqs.items():
        head = r["text"].split("Serves:")[0]
        if not re.search(r"\b(SHALL|MUST)\b", head):
            errs.append(f"{rid}: requirement text needs SHALL or MUST")
        if not r["serves"]:
            errs.append(f"{rid}: missing 'Serves: US-n' line")
        else:
            for u in r["serves"]:
                if u not in s.stories:
                    errs.append(f"{rid}: Serves names unknown story {u}")
        if not r["scenarios"]:
            errs.append(f"{rid}: needs at least one '#### Scenario: {rid}.m' scenario")
        for sid, st in r["scenarios"].items():
            for kw in ("WHEN", "THEN"):
                if not re.search(rf"^- {kw}\b", st, re.M):
                    errs.append(f"{sid}: scenario needs a '- {kw} ...' bullet")
    # tasks
    known = set(s.reqs) | {sc for r in s.reqs.values() for sc in r["scenarios"]}
    covered: set[str] = set()
    if not s.tasks:
        errs.append("tasks: no '- [ ] n.m task' lines in tasks.md")
    seen = set()
    for t in s.tasks:
        if t.id in seen:
            errs.append(f"task {t.id}: duplicate task number")
        seen.add(t.id)
        if not t.cites:
            errs.append(f"task {t.id}: cites no acceptance criteria, e.g. (AC-1.1, AC-2)")
        if not re.search(r"verified by:", t.text, re.I):
            errs.append(f"task {t.id}: must say how it is verified ('Verified by: ...')")
        for c in t.cites:
            if c not in known:
                errs.append(f"task {t.id}: cites unknown criterion {c}")
            else:
                covered.add(c.split(".")[0])
    for rid in s.reqs:
        if rid not in covered:
            errs.append(f"{rid}: no task covers this criterion")
    # dependencies
    root = path.resolve().parent
    g = load_graph(root)
    for d in (m.get("depends_on") or []) if isinstance(m.get("depends_on"), list) else []:
        if d not in g:
            errs.append(f"depends_on: unknown slice {d!r} (no {root.name}/{d}/proposal.md)")
    for c in find_cycles(g):
        if path.name in c:
            errs.append("depends_on: dependency cycle " + " -> ".join(c))
    if with_lock:
        errs += lock_errors(s)
    if ledger is not None:
        errs += ledger_errors(m.get("source_requirement_ids") or [], ledger)
    return errs


def ledger_errors(ids: list[str], ledger: Path) -> list[str]:
    if not ledger.is_file():
        return [f"ledger: {ledger} not found"]
    with ledger.open(newline="", encoding="utf-8") as f:
        rows = {r["req_id"]: r for r in csv.DictReader(f, delimiter="\t") if r.get("req_id")}
    errs = []
    for i in ids:
        r = rows.get(i)
        if r is None:
            errs.append(f"ledger: source requirement {i} not found in {ledger.name}")
            continue
        trust, status = (r.get("trust") or "").lower(), (r.get("status") or "").lower()
        if trust.startswith(("rejected", "conditioned")) and "open" in status and "critical" in status:
            errs.append(f"ledger: {i} is {r['trust']} with an open Critical finding ({r['status']}); "
                        f"the slice is blocked until the owner signs off")
    return errs
