"""python -m factory.slices. Exit codes: 0 ok, 1 check failure, 2 usage error, 3 gate not met, 4 refused,
5 done blocked by an open human stop (or an unverifiable stop ledger; fails closed)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from factory.hitl import store as hitl_store

from . import ops
from .model import parse

OK, CHECK_FAIL, USAGE, GATE, REFUSED, HUMAN_STOP = 0, 1, 2, 3, 4, 5


class Usage(Exception):
    pass


class Refused(Exception):
    pass


def _slice_dir(a) -> Path:
    p = Path(a.dir)
    if not (p / "proposal.md").is_file():
        raise Usage(f"{p}: not a slice directory (no proposal.md)")
    return p


def _report(errs: list[str], label: str) -> int:
    for e in errs:
        print(f"FAIL {e}")
    if not errs:
        print(f"ok: {label}")
    return CHECK_FAIL if errs else OK


def cmd_check(a) -> int:
    p = _slice_dir(a)
    return _report(ops.check(p, Path(a.ledger) if a.ledger else None), f"{p.name} passes")


def cmd_lock(a) -> int:
    p = _slice_dir(a)
    if (p / "criteria.lock").exists():
        raise Refused("criteria.lock exists; use `amend` (re-locking would bypass the amendment record)")
    errs = ops.check(p, with_lock=False)
    if errs:
        return _report(errs, "")
    ops.write_lock(parse(p))
    print(f"locked {p.name}")
    return OK


def _task(p: Path, tid: str):
    for t in parse(p).tasks:
        if t.id == tid:
            return t
    raise Usage(f"no task {tid} in {p / 'tasks.md'}")


def cmd_tick(a) -> int:
    p = _slice_dir(a)
    if a.role != "implementer":
        raise Refused(f"role {a.role} may not tick tasks; only the implementer marks [x] (implemented)")
    t = _task(p, a.task)
    lines = (p / "tasks.md").read_text(encoding="utf-8").split("\n")
    lines[t.line] = lines[t.line].replace("- [ ]", "- [x]", 1)
    (p / "tasks.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"ticked {a.task} (implemented; not yet verified)")
    return OK


def cmd_verify(a) -> int:
    p = _slice_dir(a)
    if a.role != "qa":
        raise Refused(f"role {a.role} may not verify; only qa writes verification.json")
    t = _task(p, a.task)
    if not t.checked:
        raise Refused(f"task {a.task} is not ticked [x]; the implementer must tick it before qa verifies")
    errs = ops.chain_errors(p)
    if errs:
        raise Refused(errs[0] + "; refusing to extend a broken chain")
    ops.append_verification(p, t.id, t.sha, a.commit, a.evidence)
    print(f"verified {a.task}")
    return OK


def cmd_amend(a) -> int:
    p = _slice_dir(a)
    base, _, _ = ops.baseline(p)
    if base is None:
        raise Refused("no readable criteria.lock; amendments apply only to a locked slice")
    s = parse(p)
    cur = s.items()
    weak = bool(a.changed or a.removed)
    if weak and not ops.APPROVAL.match(a.approved_by or ""):
        raise Refused("changing or removing a locked criterion needs --approved-by human:<ref> or codex:<ref>")
    for i in a.added:
        if i not in cur:
            raise Usage(f"--added {i}: not present in the slice; write it first")
        if i in base:
            raise Usage(f"--added {i}: already locked; use --changed")
    for i in a.changed:
        if i not in base or i not in cur:
            raise Usage(f"--changed {i}: must be a locked criterion that still exists")
    for i in a.removed:
        if i not in base or i in cur:
            raise Usage(f"--removed {i}: must be locked and already deleted from the slice")
    ap = p / "amendments.md"
    n = len(ops.parse_amendments(ap)) + 1
    lines = [f"\n## Amendment {n}", f"- who: {a.role}", f"- when: {ops.now()}", f"- reason: {a.reason}"]
    for k, ids in (("added", a.added), ("changed", a.changed)):
        if ids:
            lines.append(f"- {k}: " + ", ".join(f"{i}={cur[i]}" for i in ids))
    if a.removed:
        lines.append("- removed: " + ", ".join(a.removed))
    if a.approved_by:
        lines.append(f"- approved-by: {a.approved_by}")
    with ap.open("a", encoding="utf-8") as f:
        if not ap.exists() or ap.stat().st_size == 0:
            f.write("# Amendments (append-only)\n")
        f.write("\n".join(lines) + "\n")
    print(f"recorded amendment {n}")
    return OK


def gate_reasons(p: Path) -> list[str]:
    reasons = [f"check: {e}" for e in ops.check(p)]
    if not (p / "criteria.lock").is_file():
        reasons.append("criteria.lock missing: criteria were never approved")
    reasons += ops.chain_errors(p)
    latest = {}
    if not ops.chain_errors(p):
        for e in ops.load_chain(p):
            latest[e["task"]] = e
    for t in parse(p).tasks:
        if not t.checked:
            reasons.append(f"task {t.id} is not implemented ([ ])")
        e = latest.get(t.id)
        if e is None:
            reasons.append(f"task {t.id} is not verified by qa")
        elif e["task_sha"] != t.sha:
            reasons.append(f"task {t.id} changed after it was verified; re-verify")
    return reasons


def cmd_done(a) -> int:
    p = _slice_dir(a)
    root = Path(a.root) if a.root else hitl_store.find_root(p)
    if root is not None:
        try:
            stops = hitl_store.blocking(root, f"slice:{p.resolve().name}")
        except hitl_store.StopLedgerError as e:
            print(f"NOT DONE human-stop ledger failed verification: {e}")
            return HUMAN_STOP
        for s in stops:
            print(f"NOT DONE human stop {s['name']} [{s['scope']}] is open: {s['reason']}")
        if stops:
            return HUMAN_STOP
    reasons = gate_reasons(p)
    for r in reasons:
        print(f"NOT DONE {r}")
    if not reasons:
        print(f"done: {p.name} is complete (all tasks implemented and verified, chain and lock intact)")
    return GATE if reasons else OK


def cmd_triage(a) -> int:
    root = Path(a.root)
    if not root.is_dir():
        raise Usage(f"{root}: not a directory")
    res = ops.triage(root)
    print(json.dumps(res, indent=2))
    return CHECK_FAIL if res["cycles"] or res["unknown_dependencies"] else OK


def build() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m factory.slices", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("dir"); c.add_argument("--ledger"); c.set_defaults(f=cmd_check)
    c = sub.add_parser("lock"); c.add_argument("dir"); c.set_defaults(f=cmd_lock)
    c = sub.add_parser("tick"); c.add_argument("dir"); c.add_argument("task")
    c.add_argument("--role", required=True, choices=["implementer", "qa", "reviewer"]); c.set_defaults(f=cmd_tick)
    c = sub.add_parser("verify"); c.add_argument("dir"); c.add_argument("task")
    c.add_argument("--role", required=True, choices=["implementer", "qa", "reviewer"])
    c.add_argument("--evidence", required=True); c.add_argument("--commit", required=True)
    c.set_defaults(f=cmd_verify)
    c = sub.add_parser("amend"); c.add_argument("dir")
    c.add_argument("--role", required=True, choices=["reviewer", "slice-author"])
    c.add_argument("--reason", required=True)
    for k in ("added", "changed", "removed"):
        c.add_argument(f"--{k}", action="append", default=[], metavar="ID")
    c.add_argument("--approved-by"); c.set_defaults(f=cmd_amend)
    c = sub.add_parser("done"); c.add_argument("dir"); c.add_argument("--root", help="project root holding .sf/stops (default: nearest ancestor that has one)")
    c.set_defaults(f=cmd_done)
    c = sub.add_parser("triage"); c.add_argument("--root", default="docs/slices"); c.set_defaults(f=cmd_triage)
    return ap


def main(argv: list[str] | None = None) -> int:
    try:
        a = build().parse_args(argv)
    except SystemExit as e:
        return USAGE if e.code else OK
    try:
        return a.f(a)
    except Usage as e:
        print(f"usage error: {e}", file=sys.stderr)
        return USAGE
    except Refused as e:
        print(f"REFUSED: {e}", file=sys.stderr)
        return REFUSED
