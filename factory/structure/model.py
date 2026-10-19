"""Turn an extraction (or a scoped slice of it) into a Mermaid Nesting Dolls model.

Nesting: system -> package -> module -> class / function -> method. Every symbol node carries `files` with a
real line range and a `contains` quote so `nesting_dolls.py check` verifies it against the repository.
Edges in each diagram are aggregated by kind:
  solid  `-->`   resolved calls
  dashed `-.->`  syntactic (name-match) calls; drawn only when a name has few candidates
  dashed to an explicit "Unresolved / dynamic calls" node: calls that cannot be resolved, with reasons
Coverage status is deliberately not set: that is the caller's judgement.
"""
from __future__ import annotations

import datetime
import hashlib
import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from .extract import ast_lines

RESERVED = {"end", "graph", "subgraph", "flowchart", "class", "classdef", "style", "click", "default"}
MAX_SYNTACTIC_CANDIDATES = 5


def slug(part: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", part.lower().replace("_", "-")).strip("-")
    if not s or not s[0].isalpha():
        s = "x" + s
    return s


def label(text: str) -> str:
    return text.replace('"', "'").replace("<", "&lt;").replace(">", "&gt;")


class _Files:
    """Line ranges use ast's numbering (the symbol's real lines). The dolls checker splits with str.splitlines, which
    also breaks at form feed, vertical tab, \\x1c-\\x1e, \\x85 and U+2028/9, so a quote is only emitted when it is
    present in the symbol's own lines AND in the checker's view of the same line numbers; otherwise the file is listed in
    meta.structure.line_numbering_mismatch_files and the checker is expected to flag it."""

    def __init__(self, ex: dict, repo: Path | None):
        self.repo = repo
        self.cache: dict[str, tuple[list[str], list[str]] | None] = {}
        self.mismatch: set[str] = set()

    def both(self, path: str):
        if path not in self.cache:
            try:
                text = (self.repo / path).read_text(encoding="utf-8", errors="replace") if self.repo else None
            except OSError:
                text = None
            self.cache[path] = None if text is None else (ast_lines(text), text.splitlines())
        return self.cache[path]

    def lines(self, path: str) -> list[str] | None:
        b = self.both(path)
        return b[0] if b else None

    def ref(self, path: str, lo: int, hi: int, quotes: list[str], note: str) -> dict | None:
        b = self.both(path)
        if b is None or not b[0]:
            return None  # no repo to ground against: omit rather than emit an unverified claim
        mine, theirs = b
        lo, hi = max(1, min(lo, len(mine))), max(1, min(hi, len(mine)))
        mt, tt = "\n".join(mine[lo - 1 : hi]), "\n".join(theirs[lo - 1 : hi])
        fallback = [ln.strip() for ln in sorted(mine[lo - 1 : hi], key=len, reverse=True) if ln.strip()]
        rng = f"{lo}-{hi}" if hi > lo else str(lo)
        for q in quotes + fallback:
            if q and "\n" not in q and q in mt and q in tt:
                return {"path": path, "lines": rng, "contains": q, "note": note}
        # No quote is common to both numberings (form feed etc.). Cite the symbol's real lines with a quote that is
        # true for them, and record the file: the dolls checker (splitlines numbering) will report it loudly.
        self.mismatch.add(path)
        for q in quotes + fallback:
            if q and "\n" not in q and q in mt:
                return {"path": path, "lines": rng, "contains": q,
                        "note": f"{note} (lines follow Python's numbering; this file has line separators that str.splitlines numbers differently)"}
        return {"path": path, "lines": rng, "note": note}


def _git_commit(root: str) -> str:
    try:
        p = subprocess.run(["git", "-C", root, "rev-parse", "--short", "HEAD"], capture_output=True, text=True)
        return p.stdout.strip() if p.returncode == 0 else "unknown"
    except OSError:
        return "unknown"


def _last_ident(text: str) -> str:
    m = re.findall(r"[A-Za-z_][A-Za-z_0-9]*", text)
    return m[-1] if m else text


def build_model(ex: dict, scoped: dict | None = None, repo_name: str | None = None, max_nodes: int = 14,
                repo: str | Path | None = None, generated: str | None = None) -> dict:
    syms = ex["symbols"]
    root_path = ex["root"] if not str(ex["root"]).startswith("git:") else None
    repo_dir = Path(repo) if repo else (Path(root_path) if root_path else None)
    files = _Files(ex, repo_dir)

    # ---- which symbols are in the picture
    if scoped is not None:
        keep = set(scoped["entries"]) | set(scoped["expanded_from_containers"]) | {c["id"] for c in scoped["callees"]} | {c["id"] for c in scoped["callers"]}
        for sid in list(keep):
            p = syms[sid]["parent"]
            while p:
                keep.add(p)
                p = syms[p]["parent"]
    else:
        keep = set(syms)
    mods = sorted({syms[s]["module"] for s in keep})

    # ---- node tree (symbols that become nodes: modules, classes, top-level functions, methods of 2+ method classes)
    nodes: dict[str, dict] = {}
    parent_of: dict[str, str | None] = {}
    sym_node: dict[str, str] = {}  # symbol id -> node id of the symbol itself (if it has one)
    kids: dict[str, list[str]] = defaultdict(list)
    used: set[str] = set()
    owner: dict[str, str] = {}

    def fresh(base: str, key: str) -> str:
        nid = base
        if nid in used and owner.get(nid) != key:
            nid = f"{base}-{hashlib.sha1(key.encode()).hexdigest()[:4]}"
        used.add(nid)
        owner[nid] = key
        return nid

    root_name = repo_name or (Path(root_path).resolve().name if root_path else "repository")
    root_id = fresh("system", "<root>")
    nodes[root_id] = {"title": root_name, "kind": "system"}
    parent_of[root_id] = None

    mod_names = set(ex["modules"])
    pkg_node: dict[str, str] = {}

    def ensure_pkg(dotted: str) -> str:
        if dotted in pkg_node:
            return pkg_node[dotted]
        head, _, tail = dotted.rpartition(".")
        par = ensure_pkg(head) if head else root_id
        base = (par + "/" if par != root_id else "") + slug(tail)
        if par == root_id and base in RESERVED:
            base += "-pkg"
        nid = fresh(base, "pkg:" + dotted)
        nodes[nid] = {"title": dotted, "kind": "package"}
        parent_of[nid] = par
        kids[par].append(nid)
        pkg_node[dotted] = nid
        return nid

    mod_node: dict[str, str] = {}
    for m in mods:
        info = ex["modules"][m]
        if info["is_package"]:
            nid = ensure_pkg(m) if m != "__init__" else root_id
            mod_node[m] = nid
            if nid != root_id:
                nodes[nid]["kind"] = "package"
            continue
        head, _, tail = m.rpartition(".")
        par = ensure_pkg(head) if head else root_id
        base = (par + "/" if par != root_id else "") + slug(tail)
        if par == root_id and base in RESERVED:
            base += "-mod"
        nid = fresh(base, "mod:" + m)
        nodes[nid] = {"title": m, "kind": "module"}
        parent_of[nid] = par
        kids[par].append(nid)
        mod_node[m] = nid
    for m, nid in mod_node.items():
        sym_node[f"{m}:<module>"] = nid

    def members(parent_sid: str) -> list[str]:
        return sorted((s for s in keep if syms[s]["parent"] == parent_sid and syms[s]["kind"] != "module"),
                      key=lambda s: (syms[s]["start"], s))

    def add_symbol_nodes(parent_sid: str, parent_nid: str, prefix: str) -> None:
        for sid in members(parent_sid):
            s = syms[sid]
            if s["kind"] == "function" and s["qualname"] != s["name"]:
                continue  # nested function: folded into its parent's detail, edges lift to the parent
            if s["kind"] == "class" and s["qualname"] != s["name"] and s["parent"] and syms[s["parent"]]["kind"] != "class":
                continue
            nid = fresh(f"{prefix}/{slug(s['name'])}", sid)
            nodes[nid] = {"title": s["qualname"] if s["kind"] == "method" else s["name"], "kind": s["kind"]}
            parent_of[nid] = parent_nid
            kids[parent_nid].append(nid)
            sym_node[sid] = nid
            if s["kind"] == "class":
                ms = [x for x in members(sid) if syms[x]["kind"] == "method"]
                nested = [x for x in members(sid) if syms[x]["kind"] == "class"]
                if len(ms) + len(nested) >= 2:
                    add_symbol_nodes(sid, nid, nid)

    for m in mods:
        add_symbol_nodes(f"{m}:<module>", mod_node[m], mod_node[m] if mod_node[m] != root_id else "mod")

    def node_of(sid: str) -> str | None:
        while sid:
            if sid in sym_node:
                return sym_node[sid]
            sid = syms[sid]["parent"]
        return None

    def chain(nid: str) -> list[str]:
        out = []
        while nid is not None:
            out.append(nid)
            nid = parent_of[nid]
        return out

    # ---- edges lifted onto nodes
    drawn: list[tuple[str, str, str]] = []  # (src node, dst node, kind)
    unresolved_by_node: dict[str, list[dict]] = defaultdict(list)
    skipped_syntactic = 0
    for e in ex["edges"]:
        if e["caller"] not in keep:
            continue
        src = node_of(e["caller"])
        if src is None:
            continue
        if e["kind"] == "unresolved":
            unresolved_by_node[src].append(e)
            continue
        targets = [e["target"]] if e["kind"] == "resolved" else e["candidates"]
        if e["kind"] == "syntactic" and len(targets) > MAX_SYNTACTIC_CANDIDATES:
            skipped_syntactic += 1
            continue
        for t in targets:
            if t not in keep:
                continue
            dst = node_of(t)
            if dst is not None:
                drawn.append((src, dst, e["kind"]))

    def child_under(nid: str, container: str) -> str | None:
        c = chain(nid)
        return c[c.index(container) - 1] if container in c and c.index(container) > 0 else None

    # ---- files, summaries, detail
    out_counts: dict[str, Counter] = defaultdict(Counter)
    for e in ex["edges"]:
        if e["caller"] in keep:
            out_counts[e["caller"]][e["kind"]] += 1

    def edge_summary(sids: list[str]) -> str:
        c = Counter()
        reasons = Counter()
        for sid in sids:
            c.update(out_counts.get(sid, {}))
        for e in ex["edges"]:
            if e["caller"] in sids and e["kind"] == "unresolved":
                reasons[e["reason_code"]] += 1
        text = f"Calls made from here: {c['resolved']} resolved, {c['syntactic']} syntactic, {c['unresolved']} unresolved"
        if reasons:
            text += " (" + ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items())) + ")"
        return text + "."

    def descendants_of_symbol(sid: str) -> list[str]:
        out = [sid]
        for s in keep:
            p = syms[s]["parent"]
            while p:
                if p == sid:
                    out.append(s)
                    break
                p = syms[p]["parent"]
        return out

    sym_of_node = {v: k for k, v in sym_node.items()}
    for nid, n in nodes.items():
        sid = sym_of_node.get(nid)
        if nid == root_id and sid is None:
            continue
        if sid is None:  # directory package without __init__.py
            n["summary"] = f"Directory package {n['title']} ({len(kids[nid])} direct children)."
            n["detail"] = ["No __init__.py was scanned for this package."]
            continue
        s = syms[sid]
        mod_info = ex["modules"][s["module"]]
        if s["kind"] == "module":
            first = next((ln.strip() for ln in (files.lines(s["path"]) or []) if ln.strip()), "")
            ref = files.ref(s["path"], 1, max(s["end"], 1), [first], "module source")
            sub = [x for x in keep if syms[x]["parent"] == sid and syms[x]["kind"] in ("class", "function")]
            nc = sum(1 for x in sub if syms[x]["kind"] == "class")
            nf = sum(1 for x in sub if syms[x]["kind"] == "function")
            n["summary"] = s["doc"] or f"Python {'package' if mod_info['is_package'] else 'module'} {s['module']}: {nc} classes, {nf} top-level functions ({s['path']})."
            n["title"] = s["module"]
        else:
            kw = "class" if s["kind"] == "class" else "def"
            ls = files.lines(s["path"]) or []
            defline = ""
            for i in range(s["start"] - 1, min(s["end"], len(ls))):
                t = ls[i].strip()
                if t.startswith((kw + " ", "async def ")):
                    defline = t
                    break
            ref = files.ref(s["path"], s["start"], s["end"], [defline, f"{kw} {s['name']}", s["name"]], f"{s['kind']} {s['qualname']}")
            n["summary"] = s["doc"] or f"Python {s['kind']} {s['id']} in {s['path']}:{s['start']}-{s['end']}."
        if ref:
            n["files"] = [ref]
        det = [f"Symbol id: {sid} (stable across line shifts).", edge_summary(descendants_of_symbol(sid))]
        nested = [x for x in keep if syms[x]["parent"] == sid and syms[x]["kind"] in ("function", "class", "method") and x not in sym_node]
        if nested:
            det.append("Folded into this node (not drawn separately): " + ", ".join(sorted(syms[x]["qualname"] for x in nested)) + ".")
        n["detail"] = det

    # ---- diagrams
    def render(container: str) -> None:
        ch = list(kids[container])
        unres = Counter()
        unres_edges: list[tuple[str, dict]] = []
        for src, edges in unresolved_by_node.items():
            c = child_under(src, container)
            if c is not None:
                unres[c] += len(edges)
                unres_edges += [(c, e) for e in edges]
        agg: Counter = Counter()
        deg: Counter = Counter()
        for src, dst, kind in drawn:
            a, b = child_under(src, container), child_under(dst, container)
            if a and b and a != b:
                agg[(a, b, kind)] += 1
                deg[a] += 1
                deg[b] += 1
        for k, v in unres.items():
            deg[k] += v
        hidden = []
        if len(ch) > max_nodes:
            ranked = sorted(ch, key=lambda c: (-deg[c], c))
            keep_ch = set(ranked[: max_nodes - 1])
            hidden = [c for c in ch if c not in keep_ch]
            ch = [c for c in ch if c in keep_ch]
        if not ch:
            return
        local = {c: f"n_{i}" for i, c in enumerate(ch)}
        lines = ["flowchart LR"]
        for c in ch:
            n = nodes[c]
            sub = ""
            if "files" in n:
                sub = "<br/>" + label(n["files"][0]["path"])
            lines.append(f'  {local[c]}["{label(n["title"])}{sub}"]')
        mapping = dict((local[c], c) for c in ch)
        for (a, b, kind), cnt in sorted(agg.items()):
            if a in local and b in local:
                if kind == "resolved":
                    lines.append(f'  {local[a]} -->|"calls x{cnt}"| {local[b]}')
                else:
                    lines.append(f'  {local[a]} -.->|"syntactic x{cnt}"| {local[b]}')
        total_unres = sum(v for k, v in unres.items() if k in local)
        if total_unres:
            uid = fresh(f"{container}/unresolved" if container != root_id else "unresolved", f"unresolved:{container}")
            mapping["u_0"] = uid
            visible = [e for c, e in unres_edges if c in local]
            reasons = Counter(e["reason_code"] for e in visible)
            samples = visible[:20]
            n = {"title": f"Unresolved / dynamic calls ({total_unres})", "kind": "unresolved",
                 "summary": "Calls whose callee cannot be determined statically. Listed, never counted as resolved: " +
                            ", ".join(f"{k} x{v}" for k, v in sorted(reasons.items())) + ".",
                 "detail": [f"{e['caller']} calls `{e['text']}` ({e['reason_code']}): {e['reason']} [{e['path']}:{e['start']}]" for e in samples]
                           + ([f"... and {total_unres - len(samples)} more"] if total_unres > len(samples) else [])}
            refs = []
            for e in samples[:5]:
                r = files.ref(e["path"], e["start"], e["end"], [e["text"], _last_ident(e["text"])], "unresolved call site")
                if r:
                    refs.append(r)
            if refs:
                n["files"] = refs
            nodes[uid] = n
            parent_of[uid] = container
            kids[container].append(uid)
            lines.append(f'  u_0["Unresolved / dynamic calls"]')
            for k, v in sorted(unres.items()):
                if k in local:
                    lines.append(f'  {local[k]} -.->|"unresolved x{v}"| u_0')
        if hidden:
            mid = fresh(f"{container}/more" if container != root_id else "more", f"more:{container}")
            nodes[mid] = {"title": f"{len(hidden)} more", "kind": "group",
                          "summary": f"{len(hidden)} lower-degree children are not drawn to keep this diagram readable.",
                          "detail": ["Not drawn: " + ", ".join(nodes[h]["title"] for h in hidden[:60]) + (" ..." if len(hidden) > 60 else "")]}
            parent_of[mid] = container
            lines.append(f'  m_0["{len(hidden)} more (not drawn)"]')
            mapping["m_0"] = mid
            truncated.append({"container": container, "hidden": len(hidden)})
            for h in hidden:  # hidden subtrees stay out of the model entirely
                _drop(h)
        nodes[container]["diagram"] = lines
        nodes[container]["children"] = mapping
        for c in ch:
            render(c)

    def _drop(nid: str) -> None:
        for c in list(kids.get(nid, [])):
            _drop(c)
        nodes.pop(nid, None)

    truncated: list[dict] = []
    # hidden nodes must not receive diagrams; render() recurses only into drawn children
    # note: unresolved/more leaf nodes appended to kids are leaves (no diagram of their own)
    render(root_id)
    unreachable = [n for n in list(nodes) if n != root_id and not any(n in (nodes[p].get("children") or {}).values() for p in nodes)]
    for n in unreachable:
        nodes.pop(n, None)  # nodes that never made it into a diagram (should only be dropped hidden subtrees)

    lim = ex["limits"]
    nodes[root_id]["summary"] = (f"Structural map of {len(mods)} Python modules extracted by factory.structure (stdlib ast)"
                                 + (f", scoped to {len(scoped['entries'])} entry symbol(s) at depth {scoped['depth']}" if scoped else "")
                                 + ". Not a complete call graph.")
    nodes[root_id]["detail"] = [
        f"Edges: {lim['resolved_edges']} resolved, {lim['syntactic_edges']} syntactic, {lim['unresolved_edges']} unresolved (whole extraction).",
        f"Parse failures: {len(lim['parse_failures'])}" + ("".join(f"; {f['path']}: {f['error']}" for f in lim["parse_failures"])),
        f"Syntactic edges with more than {MAX_SYNTACTIC_CANDIDATES} name candidates are not drawn ({skipped_syntactic} here).",
        "Solid arrows are resolved calls, dashed arrows are name matches, the Unresolved node lists dynamic calls with reasons.",
    ]
    meta = {
        "title": f"Structure: {root_name}",
        "subtitle": "Source-grounded Python structure from ast; resolved, syntactic and unresolved edges are distinguished",
        "repo": root_name,
        "commit": _git_commit(root_path) if root_path else "unknown",
        "generated": generated or datetime.date.today().isoformat(),
        "structure": {
            "generator": "factory.structure",
            "complete_call_graph": False,
            "counts": ex["counts"],
            "edges": {"resolved": lim["resolved_edges"], "syntactic": lim["syntactic_edges"], "unresolved": lim["unresolved_edges"]},
            "unresolved_by_reason": lim["unresolved_by_reason"],
            "parse_failures": lim["parse_failures"],
            "syntactic_edges_not_drawn": skipped_syntactic,
            "line_numbering_mismatch_files": sorted(files.mismatch),
            "containers_truncated": truncated,
            "scoped": ({"entries": scoped["entries"], "depth": scoped["depth"], "include_syntactic": scoped["include_syntactic"]} if scoped else None),
        },
    }
    return {"meta": meta, "root": root_id, "nodes": nodes}
