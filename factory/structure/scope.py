"""Bounded scoping over an extraction: affected callers/callees and touched state.

The result is a slice, never "the call graph". It always carries `limits` and a `not_followed` list that says
which edges were seen but not followed (unresolved, syntactic-only when not requested, depth bound).
"""
from __future__ import annotations

RANK = {"resolved": 0, "syntactic": 1, "unresolved": 2}  # lower is more precise


def edge_targets(e: dict) -> list[str]:
    """Symbols an edge points at, per its kind. Resolved: the target. Syntactic/unresolved: name candidates."""
    if e["kind"] == "resolved":
        return [e["target"]]
    return list(e["candidates"])


class Index:
    def __init__(self, ex: dict):
        self.ex = ex
        self.forward: dict[str, list[dict]] = {}
        self.reverse: dict[str, list[dict]] = {}
        self.children: dict[str, list[str]] = {}
        for e in ex["edges"]:
            self.forward.setdefault(e["caller"], []).append(e)
            for t in edge_targets(e):
                self.reverse.setdefault(t, []).append(e)
        for sid, s in ex["symbols"].items():
            if s["parent"]:
                self.children.setdefault(s["parent"], []).append(sid)

    def descendants(self, sid: str) -> list[str]:
        out, stack = [], list(self.children.get(sid, []))
        while stack:
            c = stack.pop()
            out.append(c)
            stack.extend(self.children.get(c, []))
        return sorted(out)


def reach(idx: Index, seeds: list[str], depth: int, direction: str, kinds: set[str]):
    """Breadth-first walk. direction is 'callees' or 'callers'. Returns (found, not_followed, truncated)."""
    found: dict[str, dict] = {}
    not_followed: list[dict] = []
    truncated: set[str] = set()
    seen = set(seeds)
    frontier = {s: "resolved" for s in seeds}
    skipped: set = set()
    for d in range(1, depth + 1):
        nxt: dict[str, dict] = {}
        for sid, prec in sorted(frontier.items()):
            edges = idx.forward.get(sid, []) if direction == "callees" else idx.reverse.get(sid, [])
            for e in edges:
                if direction == "callees":
                    others = edge_targets(e)
                    sources = [e["caller"]]
                else:
                    others = [e["caller"]]
                    sources = [sid]
                if e["kind"] not in kinds:
                    key = (sid, e["caller"], e["text"], e["start"], direction)
                    if key not in skipped:
                        skipped.add(key)
                        not_followed.append(_nf(e, sid, direction, "kind not followed"))
                    continue
                for o in others:
                    if o in seen:
                        continue
                    p = prec if RANK[prec] >= RANK[e["kind"]] else e["kind"]
                    cur = nxt.get(o)
                    if cur is None or RANK[p] < RANK[cur["kind"]]:
                        nxt[o] = {"id": o, "depth": d, "kind": p, "via_symbol": sid,
                                  "edge": {"text": e["text"], "edge_kind": e["kind"], "path": e["path"], "start": e["start"], "end": e["end"],
                                           "caller": e["caller"]}}
        for o, rec in nxt.items():
            found[o] = rec
            seen.add(o)
        frontier = {o: rec["kind"] for o, rec in nxt.items()}
        if not frontier:
            break
    else:
        for sid in frontier:
            edges = idx.forward.get(sid, []) if direction == "callees" else idx.reverse.get(sid, [])
            if any(e["kind"] in kinds for e in edges):
                truncated.add(sid)
    return found, not_followed, sorted(truncated)


def _nf(e: dict, at: str, direction: str, why: str) -> dict:
    return {"from": e["caller"], "at": at, "direction": direction, "text": e["text"], "kind": e["kind"],
            "reason_code": e["reason_code"], "reason": e["reason"] or why, "followed": False, "why_not": why,
            "candidates": e["candidates"], "path": e["path"], "start": e["start"]}


def scope(ex: dict, entries: list[str], depth: int = 2, include_syntactic: bool = False, expand_containers: bool = True) -> dict:
    """Callers, callees and touched state around `entries` (symbol ids), bounded by `depth` hops."""
    if depth < 0:
        raise ValueError("depth must be >= 0")
    syms = ex["symbols"]
    for e in entries:
        if e not in syms:
            raise KeyError(e)
    idx = Index(ex)
    seeds = list(dict.fromkeys(entries))
    expanded = []
    if expand_containers:
        for e in list(seeds):
            if syms[e]["kind"] in ("class", "module"):
                for d in idx.descendants(e):
                    if d not in seeds:
                        seeds.append(d)
                        expanded.append(d)
    kinds = {"resolved"} | ({"syntactic"} if include_syntactic else set())
    callees, nf_out, trunc_out = reach(idx, seeds, depth, "callees", kinds)
    callers, nf_in, trunc_in = reach(idx, seeds, depth, "callers", kinds)
    # edges of the entries themselves that cannot be followed at all
    own_edges: list[dict] = []
    in_scope = set(seeds) | set(callees)
    for sid in sorted(in_scope):
        for e in idx.forward.get(sid, []):
            if e["kind"] == "unresolved" or (e["kind"] == "syntactic" and not include_syntactic):
                own_edges.append(_nf(e, sid, "callees", "unresolved: target cannot be determined statically" if e["kind"] == "unresolved" else "syntactic edge; use --include-syntactic to follow name candidates"))
    seen_nf = set()
    not_followed = []
    for n in own_edges + nf_out + nf_in:
        key = (n["from"], n["text"], n["start"], n["kind"], n["direction"])
        if key not in seen_nf:
            seen_nf.add(key)
            not_followed.append(n)
    touched = []
    for w in ex["writes"]:
        if w["symbol"] in in_scope:
            touched.append({"symbol": w["symbol"], "target": w["target"], "access": w["kind"], "path": w["path"], "start": w["start"]})
    for sid in sorted(in_scope):
        for t in ex["reads"].get(sid, []):
            touched.append({"symbol": sid, "target": t, "access": "read", "path": syms[sid]["path"], "start": None})
    touched.sort(key=lambda t: (t["target"], t["symbol"], t["access"]))
    lim = ex["limits"]
    return {
        "schema": "factory.structure.scope/1",
        "entries": list(dict.fromkeys(entries)),
        "expanded_from_containers": sorted(expanded),
        "depth": depth,
        "include_syntactic": include_syntactic,
        "callees": sorted(callees.values(), key=lambda r: (r["depth"], r["id"])),
        "callers": sorted(callers.values(), key=lambda r: (r["depth"], r["id"])),
        "state_touched": touched,
        "not_followed": not_followed,
        "depth_truncated": sorted(set(trunc_out) | set(trunc_in)),
        "limits": {
            "complete_call_graph": False,
            "claim": "bounded slice around the entry symbols; callers reached only through unresolved or dynamic edges are unknowable here",
            "unresolved_edges": lim["unresolved_edges"],
            "syntactic_edges": lim["syntactic_edges"],
            "unresolved_in_scope": sum(1 for n in own_edges if n["kind"] == "unresolved"),
            "syntactic_in_scope": sum(1 for n in own_edges if n["kind"] == "syntactic"),
            "parse_failures": lim["parse_failures"],
            "external_calls_not_recorded": lim["external_calls_not_recorded"],
            "kinds_followed": sorted(kinds),
        },
    }
