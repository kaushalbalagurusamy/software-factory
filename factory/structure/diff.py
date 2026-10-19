"""Structural diff: changed/added/removed symbols by normalised-AST hash, plus affected callers.

Two trees are two directories or two `git:<rev>` specs (read with `git ls-tree` / `git show`, read-only).
A symbol's hash covers its own normalised AST (positions dropped, so formatting and comments do not matter;
docstrings and constants do) with nested definitions replaced by a placeholder, so editing a method changes
the method and not its class. Hashes are suitable cache keys for a later verification step, but they say
nothing about callees or contracts: a cache must also key on dependency and contract hashes.
A changed module-level variable (by hash of its assignments) lists the symbols that read it (`kind: read`), and a
changed inner function lists its enclosing function (`kind: enclosing`); callers of either follow from there.
Files that fail to parse on either side make the symbols they hold unknowable; those are reported under
`unknown_due_to_parse_failure` and never as added/removed/changed.
"""
from __future__ import annotations

from .extract import extract, make_source
from .scope import Index, reach

ALL_KINDS = {"resolved", "syntactic", "unresolved"}


def _side(ex: dict) -> dict:
    lim = ex["limits"]
    return {
        "root": ex["root"],
        "parse_failures": lim["parse_failures"],
        "unresolved_edges": lim["unresolved_edges"],
        "syntactic_edges": lim["syntactic_edges"],
        "resolved_edges": lim["resolved_edges"],
        "hash_failures": lim["hash_failures"],
    }


def diff_extractions(b: dict, h: dict, depth: int = 2) -> dict:
    bad_paths = {f["path"] for f in b["limits"]["parse_failures"]} | {f["path"] for f in h["limits"]["parse_failures"]}
    bs, hs = b["symbols"], h["symbols"]
    unknown = sorted(i for i, s in {**bs, **hs}.items() if s["path"] in bad_paths)
    ids_b = {i for i in bs if bs[i]["path"] not in bad_paths}
    ids_h = {i for i in hs if hs[i]["path"] not in bad_paths}
    added = sorted(ids_h - ids_b)
    removed = sorted(ids_b - ids_h)
    changed = []
    for i in sorted(ids_b & ids_h):
        hb, hh = bs[i]["ast_hash"], hs[i]["ast_hash"]
        if hb is None or hh is None or hb != hh:
            changed.append({"id": i, "kind": hs[i]["kind"], "path": hs[i]["path"], "base_hash": hb, "head_hash": hh,
                            "base_span": [bs[i]["start"], bs[i]["end"]], "head_span": [hs[i]["start"], hs[i]["end"]]})
    callers: list[dict] = []
    hidx, bidx = Index(h), Index(b)
    changed_ids = {c["id"] for c in changed}

    def add_callers(idx, symbols, seed, graph, via, offset):
        found, _, _ = reach(idx, [seed], depth - offset, "callers", ALL_KINDS) if depth - offset > 0 else ({}, 0, 0)
        for rec in found.values():
            callers.append({
                "id": rec["id"], "depth": rec["depth"] + offset, "kind": rec["kind"], "via_changed": via, "graph": graph,
                "span": {"path": rec["edge"]["path"], "start": rec["edge"]["start"], "end": rec["edge"]["end"]},
                "edge_text": rec["edge"]["text"], "edge_kind": rec["edge"]["edge_kind"], "also_changed": rec["id"] in changed_ids,
            })

    def add_direct(sid, symbols, via, kind, graph, path, line, idx):
        callers.append({"id": sid, "depth": 1, "kind": kind, "via_changed": via, "graph": graph,
                        "span": {"path": path, "start": line, "end": line}, "edge_text": via, "edge_kind": kind,
                        "also_changed": sid in changed_ids})
        add_callers(idx, symbols, sid, graph, via, 1)

    for seed, graph, idx in [(c["id"], "head", hidx) for c in changed] + [(i, "base", bidx) for i in removed]:
        add_callers(idx, None, seed, graph, seed, 0)
    # a changed inner function/closure changes what the enclosing function builds or returns
    for c in changed:
        cur = c["id"]
        while hs[cur]["parent"] and hs[hs[cur]["parent"]]["kind"] in ("function", "method"):
            enc = hs[cur]["parent"]
            add_direct(enc, hs, c["id"], "enclosing", "head", hs[cur]["path"], hs[cur]["start"], hidx)
            cur = enc
    # a changed module-level variable changes the symbols that read it
    sb, sh = b["state"], h["state"]
    changed_state = [{"id": i, "base_hash": sb[i].get("value_hash"), "head_hash": sh[i].get("value_hash")}
                     for i in sorted(set(sb) & set(sh)) if sb[i].get("value_hash") != sh[i].get("value_hash")
                     and sb[i]["path"] not in bad_paths]
    added_state = sorted(i for i in set(sh) - set(sb) if sh[i]["path"] not in bad_paths)
    removed_state = sorted(i for i in set(sb) - set(sh) if sb[i]["path"] not in bad_paths)
    for graph, ex_, ids, idx in (("head", h, [c["id"] for c in changed_state] + added_state, hidx), ("base", b, removed_state, bidx)):
        for st in ids:
            for reader, targets in sorted(ex_["reads"].items()):
                if st in targets and ex_["symbols"][reader]["path"] not in bad_paths:
                    add_direct(reader, ex_["symbols"], st, "read", graph, ex_["symbols"][reader]["path"],
                               ex_["read_lines"].get(reader, {}).get(st, ex_["symbols"][reader]["start"]), idx)
    best: dict = {}
    for c in callers:
        key = (c["via_changed"], c["id"])
        if key not in best or c["depth"] < best[key]["depth"]:
            best[key] = c
    callers = sorted(best.values(), key=lambda c: (c["via_changed"], c["depth"], c["id"]))
    incomplete = bool(bad_paths) or bool(b["limits"]["hash_failures"] or h["limits"]["hash_failures"])
    return {
        "schema": "factory.structure.diff/1",
        "base": b["root"],
        "head": h["root"],
        "status": "incomplete" if incomplete else "complete_for_parsed_files",
        "changed": changed,
        "added": added,
        "removed": removed,
        "changed_state": changed_state,
        "added_state": added_state,
        "removed_state": removed_state,
        "unchanged": len(ids_b & ids_h) - len(changed),
        "unknown_due_to_parse_failure": unknown,
        "affected_callers": callers,
        "caller_depth": depth,
        "hashes": {i: s["ast_hash"] for i, s in sorted(hs.items())},
        "limits": {
            "complete_call_graph": False,
            "claim": "callers are those the extractor could attribute by resolved edges, name candidates (syntactic) or decorator/conditional candidates (unresolved); dynamic callers are unknowable",
            "base": _side(b),
            "head": _side(h),
        },
    }


def diff_trees(base, head, repo=None, depth: int = 2, exclude=()) -> dict:
    """`base`/`head`: directory paths or `git:<rev>` strings (the latter need `repo`)."""
    return diff_extractions(extract(make_source(base, repo, exclude)), extract(make_source(head, repo, exclude)), depth)
