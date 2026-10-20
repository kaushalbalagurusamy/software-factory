#!/usr/bin/env python3
"""Build and validate a Mermaid Nesting Dolls explorer (stdlib only).

  nesting_dolls.py check  model.json --repo .            validate the model against the repo
  nesting_dolls.py build  model.json -o out.html --repo . validate, then write one portable HTML file
  nesting_dolls.py import-omm .omm -o model.json          convert an oh-my-mermaid .omm/ tree to a model

The model format is documented in references/model-schema.md. `check` exists so that every file path, line
range and `contains` quote in the explorer is verified against the real repository before anyone presents it.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
STATUSES = {"built", "partial", "designed", "external", "gap"}
EDITORS = ("vscode", "cursor", "windsurf", "zed", "idea", "sublime", "textmate")  # keep in step with assets/editor-links.js
MARK_BEGIN, MARK_END = "/* editor-links:begin */", "/* editor-links:end */"
RESERVED = {"end", "graph", "subgraph", "flowchart", "class", "classdef", "style", "click", "default"}


def id_in(text: str, node_id: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(node_id)}(?![\w-])", text) is not None


def bare(diagram: str) -> str:
    """The diagram with quoted labels blanked, so ids are matched only where Mermaid sees ids."""
    return re.sub(r'"[^"]*"', '""', diagram)


def children_map(node: dict) -> dict[str, str]:
    """Normalise `children` to {id used in the diagram: global node id}."""
    ch = node.get("children") or []
    return dict(ch) if isinstance(ch, dict) else {c: c for c in ch}


def valid_root(root: object) -> bool:
    return (isinstance(root, str) and 0 < len(root) <= 4096 and "\0" not in root and "\\" not in root
            and (root.startswith("/") or re.match(r"[A-Za-z]:/", root) is not None))


def validate_workspace(ws: object) -> list[str]:
    if ws is None:
        return []
    if not isinstance(ws, dict):
        return ["workspace must be an object {root, editor}"]
    errs = []
    if "root" in ws and not valid_root(ws["root"]):
        errs.append(f"workspace.root must be an absolute path (/abs or C:/abs), got {ws['root']!r}")
    if "editor" in ws and ws["editor"] not in (*EDITORS, "none"):
        errs.append(f"workspace.editor must be one of {', '.join(EDITORS)} or none, got {ws['editor']!r}")
    return errs


def inlined(text: str) -> str | None:
    a, b = text.find(MARK_BEGIN), text.find(MARK_END)
    return text[a:b + len(MARK_END)] if 0 <= a < b else None


def check_assets(repo: Path) -> list[str]:
    """Every inlined copy of editor-links.js must be byte-identical to the source between the markers."""
    src = inlined((SKILL / "assets" / "editor-links.js").read_text(encoding="utf-8"))
    if src is None:
        return ["editor-links: assets/editor-links.js has no begin/end markers"]
    errs = []
    for label, path in (("template", SKILL / "assets" / "template.html"), ("ops shell", repo / "ops" / "shell" / "index.html")):
        if not path.is_file():
            errs.append(f"editor-links: {label} not found at {path}")
        elif inlined(path.read_text(encoding="utf-8")) != src:
            errs.append(f"editor-links: copy in {label} ({path}) differs from assets/editor-links.js")
    return errs


def git_root() -> Path:
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path.cwd()


def validate(model: dict, repo: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = validate_workspace(model.get("workspace"))
    warns: list[str] = []
    nodes = model.get("nodes", {})
    root = model.get("root")
    if root not in nodes:
        errors.append(f"root {root!r} is not a node")
        return errors, warns

    parent: dict[str, str] = {}
    for nid, n in nodes.items():
        if nid.lower() in RESERVED or not re.fullmatch(r"[A-Za-z][\w/-]*", nid):
            errors.append(f"{nid}: id must be kebab-case/slash-path and not a Mermaid keyword")
        for k in ("title", "summary"):
            if not n.get(k):
                errors.append(f"{nid}: missing {k}")
        cov = n.get("coverage")
        if cov and cov.get("status") not in STATUSES:
            errors.append(f"{nid}: coverage.status must be one of {sorted(STATUSES)}")
        cm = children_map(n)
        if cm and not n.get("diagram"):
            errors.append(f"{nid}: has children but no diagram")
        for local, gid in cm.items():
            if gid not in nodes:
                errors.append(f"{nid}: child {gid!r} is not a node")
            elif gid in parent and parent[gid] != nid:
                errors.append(f"{gid}: has two parents ({parent[gid]}, {nid}); nesting must be a tree")
            else:
                parent[gid] = nid
            if n.get("diagram") and not id_in(bare(n["diagram"]), local):
                errors.append(f"{nid}: child {local!r} does not appear in its diagram, so it cannot be clicked")
        if n.get("diagram"):
            for local in {i for i in nodes if "/" not in i and i != nid}:
                if id_in(bare(n["diagram"]), local) and local not in cm and local not in {parent.get(nid)}:
                    warns.append(f"{nid}: diagram mentions node {local!r} that is not listed in children")

    seen: set[str] = set()
    stack = [root]
    while stack:
        cur = stack.pop()
        if cur in seen:
            errors.append(f"cycle through {cur}")
            continue
        seen.add(cur)
        stack += list(children_map(nodes[cur]).values())
    for nid in nodes:
        if nid not in seen:
            errors.append(f"{nid}: unreachable from root")

    cache: dict[Path, list[str]] = {}

    def read(p: Path) -> list[str]:
        if p not in cache:
            cache[p] = re.split(r"\r\n|\r|\n", p.read_text(encoding="utf-8", errors="replace"))  # Python source line numbering: not str.splitlines (form feed etc.)
        return cache[p]

    for nid, n in nodes.items():
        for f in n.get("files", []):
            raw = f["path"]
            ext = bool(f.get("external")) or raw.startswith("~")
            path = Path(raw).expanduser() if ext else repo / raw
            if path.is_dir():
                continue
            if not path.exists():
                (warns if ext else errors).append(f"{nid}: file not found: {raw}")
                continue
            lines = read(path)
            lo, hi = 1, len(lines)
            if f.get("lines"):
                m = re.fullmatch(r"(\d+)(?:-(\d+))?", str(f["lines"]))
                if not m:
                    errors.append(f"{nid}: bad line range {f['lines']!r} for {raw}")
                    continue
                lo, hi = int(m[1]), int(m[2] or m[1])
                if hi > len(lines) or lo > hi:
                    errors.append(f"{nid}: {raw} lines {f['lines']} outside file (has {len(lines)})")
                    continue
            if f.get("contains") and f["contains"] not in "\n".join(lines[lo - 1 : hi]):
                errors.append(f"{nid}: {raw}{':' + str(f['lines']) if f.get('lines') else ''} does not contain {f['contains']!r}")
            if not ext and not f.get("lines") and not f.get("contains") and path.is_file():
                warns.append(f"{nid}: {raw} has neither lines nor contains (weakly grounded)")
    return errors, warns


def build(model: dict) -> str:
    tpl = (SKILL / "assets" / "template.html").read_text(encoding="utf-8")
    lib = (SKILL / "assets" / "vendor" / "mermaid.min.js").read_text(encoding="utf-8")
    data = json.dumps(model, ensure_ascii=False).replace("</", "<\\/").replace("<!--", "<\\!--")
    lib = lib.replace("</script", "<\\/script")
    return tpl.replace("/*__MERMAID__*/", lib).replace("__MODEL_JSON__", data)


# ---- oh-my-mermaid import -------------------------------------------------------------------------------

def read_field(d: Path, name: str) -> str:
    p = d / f"{name}.md"
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def bullets(text: str) -> list[str]:
    out = [re.sub(r"^\s*[-*]\s+|^\s*\d+\.\s+", "", ln).strip() for ln in text.splitlines() if ln.strip()]
    return [o for o in out if o]


def first_sentences(text: str, limit: int = 300) -> str:
    out = ""
    for s in re.split(r"(?<=[.!?])\s+", text):
        if out and len(out) + len(s) > limit:
            break
        out = f"{out} {s}".strip()
    return out


def omm_node(d: Path, gid: str, nodes: dict[str, dict]) -> None:
    desc = read_field(d, "description")
    paras = [p.strip() for p in desc.split("\n\n") if p.strip()]
    node: dict = {
        "title": d.name.replace("-", " ").title(),
        "summary": first_sentences(paras[0] if paras else d.name),
        "detail": paras[1:] + ([read_field(d, "context")] if read_field(d, "context") else []),
    }
    gaps = bullets(read_field(d, "concern")) + [f"TODO: {t}" for t in bullets(read_field(d, "todo"))]
    if gaps:
        node["coverage"] = {"status": "partial", "note": "Imported from omm concern/todo fields.", "gaps": gaps}
    cons = bullets(read_field(d, "constraint"))
    if cons:
        node["design"] = [{"choice": c, "why": "Recorded as a constraint by omm."} for c in cons]
    nodes[gid] = node
    mmd = d / "diagram.mmd"
    kids = {c.name: f"{gid}/{c.name}" for c in sorted(d.iterdir()) if c.is_dir()}
    if mmd.exists() and kids:
        node["diagram"] = mmd.read_text(encoding="utf-8").strip()
        node["children"] = {k: v for k, v in kids.items() if id_in(node["diagram"], k)}
        for k, v in node["children"].items():
            omm_node(d / k, v, nodes)


def import_omm(omm: Path, title: str) -> dict:
    persp = [p for p in sorted(omm.iterdir()) if p.is_dir() and (p / "diagram.mmd").exists()]
    nodes: dict[str, dict] = {}
    for p in persp:
        omm_node(p, p.name, nodes)
    root = "systems-map"
    diagram = "graph LR\n" + "\n".join(f'    {p.name}["{p.name.replace("-", " ").title()}"]' for p in persp)
    nodes[root] = {
        "title": title,
        "summary": f"Imported from an oh-my-mermaid .omm/ tree: {len(persp)} perspectives.",
        "diagram": diagram,
        "children": [p.name for p in persp],
    }
    return {"meta": {"title": title, "subtitle": "Imported from oh-my-mermaid", "generated": ""}, "root": root, "nodes": nodes}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "build"):
        p = sub.add_parser(name)
        p.add_argument("model", nargs="?" if name == "check" else None)
        p.add_argument("--repo", default=None, help="repository root that file paths are relative to (default: .; with --assets the git root)")
        p.add_argument("--workspace-root", help="absolute checkout directory the viewer joins file paths to for editor links")
        p.add_argument("--editor", help=f"editor for deep links: {', '.join(EDITORS)} or none")
        if name == "check":
            p.add_argument("--assets", action="store_true", help="verify the inlined editor-links copies match assets/editor-links.js")
        if name == "build":
            p.add_argument("-o", "--out", required=True)
            p.add_argument("--allow-errors", action="store_true", help="write the HTML even if validation fails")
    p = sub.add_parser("import-omm")
    p.add_argument("omm_dir")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("--title", default="Architecture")
    a = ap.parse_args(argv)

    if a.cmd == "import-omm":
        m = import_omm(Path(a.omm_dir), a.title)
        Path(a.out).write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"imported {len(m['nodes'])} nodes -> {a.out}")
        return 0

    rc = 0
    if a.cmd == "check" and a.assets:
        for e in check_assets(Path(a.repo).resolve() if a.repo else git_root()):
            print("ERROR:", e)
            rc = 1
        if a.model is None:
            return rc
    if a.model is None:
        ap.error("model is required")
    model = json.loads(Path(a.model).read_text(encoding="utf-8"))
    if a.workspace_root is not None or a.editor is not None:
        ws = dict(model.get("workspace") or {})
        if a.workspace_root is not None:
            ws["root"] = a.workspace_root
        if a.editor is not None:
            ws["editor"] = a.editor
        model["workspace"] = ws
    for n in model.get("nodes", {}).values():  # a diagram may be a list of lines, which is easier to edit in JSON
        if isinstance(n.get("diagram"), list):
            n["diagram"] = "\n".join(n["diagram"])
    errors, warns = validate(model, Path(a.repo or ".").resolve())
    for w in warns:
        print("warn: ", w)
    for e in errors:
        print("ERROR:", e)
    n = len(model.get("nodes", {}))
    drill = sum(1 for x in model["nodes"].values() if x.get("diagram"))
    print(f"{n} nodes, {drill} diagrams, {len(errors)} errors, {len(warns)} warnings")
    if a.cmd == "check" or (errors and not a.allow_errors):
        return 1 if errors or rc else 0
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(build(model), encoding="utf-8")
    print(f"wrote {a.out} ({Path(a.out).stat().st_size // 1024} KiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
