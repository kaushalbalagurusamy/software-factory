"""Structural diff: changed/added/removed symbols by normalised-AST hash, plus affected callers.

Two trees are two directories or two `git:<rev>` specs (read with `git ls-tree` / `git show`, read-only).
A symbol's hash covers its own normalised AST (positions dropped, so formatting and comments do not matter;
docstrings and constants do) with nested definitions replaced by a placeholder, so editing a method changes
the method and not its class. Hashes are suitable cache keys for a later verification step, but they say
nothing about callees or contracts: a cache must also key on dependency and contract hashes.
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
    callers = []
    hidx, bidx = Index(h), Index(b)
    changed_ids = {c["id"] for c in changed}
    for seed, graph, idx in [(c["id"], "head", hidx) for c in changed] + [(i, "base", bidx) for i in removed]:
        found, _, trunc = reach(idx, [seed], depth, "callers", ALL_KINDS)
        for rec in found.values():
            callers.append({
                "id": rec["id"], "depth": rec["depth"], "kind": rec["kind"], "via_changed": seed, "graph": graph,
                "span": {"path": rec["edge"]["path"], "start": rec["edge"]["start"], "end": rec["edge"]["end"]},
                "edge_text": rec["edge"]["text"], "edge_kind": rec["edge"]["edge_kind"],
                "also_changed": rec["id"] in changed_ids,
            })
    callers.sort(key=lambda c: (c["via_changed"], c["depth"], c["id"]))
    incomplete = bool(bad_paths) or bool(b["limits"]["hash_failures"] or h["limits"]["hash_failures"])
    return {
        "schema": "factory.structure.diff/1",
        "base": b["root"],
        "head": h["root"],
        "status": "incomplete" if incomplete else "complete_for_parsed_files",
        "changed": changed,
        "added": added,
        "removed": removed,
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
