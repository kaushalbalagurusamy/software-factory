"""python -m factory.structure scan|scope|model|diff

Exit codes: 0 ok; 2 usage error (bad arguments, unknown entry symbol, missing path or revision);
3 a file that was asked about (or any file with --strict) could not be parsed. Parse failures are always
reported in `limits.parse_failures`.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .diff import diff_trees
from .extract import StructureError, extract
from .model import build_model
from .scope import scope as run_scope

EXIT_OK, EXIT_USAGE, EXIT_PARSE = 0, 2, 3


class _Parser(argparse.ArgumentParser):
    def error(self, message):  # argparse default already exits 2; keep that explicit
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def _common(p, strict=True):
    p.add_argument("--exclude", action="append", default=[], metavar="GLOB", help="skip files whose repo-relative path matches (repeatable)")
    if strict:
        p.add_argument("--strict", action="store_true", help="exit 3 if any scanned file fails to parse")


def parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="python -m factory.structure", description="Honest structural exploration of Python projects (ast only; not a complete call graph).")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    s = sub.add_parser("scan", help="extract symbols, edges and state as JSON")
    s.add_argument("repo")
    s.add_argument("--paths", nargs="+", metavar="FILE", help="files you are asking about (repo-relative): output is restricted to them and a parse failure in any exits 3")
    s.add_argument("--summary", action="store_true", help="print counts and limits only")
    _common(s)
    c = sub.add_parser("scope", help="callers, callees and touched state around entry symbols")
    c.add_argument("repo")
    c.add_argument("--entry", action="append", required=True, metavar="MODULE:QUALNAME")
    c.add_argument("--depth", type=int, default=2)
    c.add_argument("--include-syntactic", action="store_true", help="also follow name-match (syntactic) edges")
    _common(c)
    m = sub.add_parser("model", help="write a Mermaid Nesting Dolls model JSON")
    m.add_argument("repo")
    m.add_argument("-o", "--output", required=True)
    m.add_argument("--entry", action="append", metavar="MODULE:QUALNAME", help="limit the model to a scoped slice")
    m.add_argument("--depth", type=int, default=2)
    m.add_argument("--include-syntactic", action="store_true")
    m.add_argument("--name", help="system node title (default: repo directory name)")
    m.add_argument("--max-nodes", type=int, default=14)
    _common(m)
    d = sub.add_parser("diff", help="structural diff of two trees (paths or git:<rev>)")
    d.add_argument("base")
    d.add_argument("head")
    d.add_argument("--repo", help="git repository for git:<rev> arguments")
    d.add_argument("--depth", type=int, default=2, help="caller depth")
    _common(d)
    return ap


def _emit(obj) -> None:
    json.dump(obj, sys.stdout, indent=2, sort_keys=False)
    sys.stdout.write("\n")


def _fail(msg: str) -> int:
    print(f"error: {msg}", file=sys.stderr)
    return EXIT_USAGE


def main(argv: list[str] | None = None) -> int:
    a = parser().parse_args(argv)
    try:
        if a.cmd == "diff":
            r = diff_trees(a.base, a.head, repo=a.repo, depth=a.depth, exclude=a.exclude)
            _emit(r)
            failed = r["limits"]["base"]["parse_failures"] + r["limits"]["head"]["parse_failures"]
            return EXIT_PARSE if a.strict and failed else EXIT_OK
        if not Path(a.repo).is_dir():
            return _fail(f"not a directory: {a.repo}")
        ex = extract(a.repo, exclude=a.exclude)
        failed = ex["limits"]["parse_failures"]
        if a.cmd == "scan":
            asked = None
            if a.paths:
                asked = {p.replace("\\", "/") for p in a.paths}
                unknown = sorted(asked - set(ex["files"]) - {f["path"] for f in failed})
                if unknown:
                    return _fail("not a scanned Python file: " + ", ".join(unknown))
                ex = _restrict(ex, asked)
            if a.summary:
                _emit({"counts": ex["counts"], "limits": ex["limits"]})
            else:
                _emit(ex)
            bad = [f for f in failed if asked is None or f["path"] in asked]
            if bad and (a.strict or asked is not None):
                for f in bad:
                    print(f"parse failure: {f['path']}:{f['line']}: {f['error']}", file=sys.stderr)
                return EXIT_PARSE
            return EXIT_OK
        try:
            sc = run_scope(ex, a.entry, depth=a.depth, include_syntactic=a.include_syntactic) if a.entry else None
        except KeyError as e:
            return _fail(f"unknown entry symbol {e.args[0]!r} (ids look like 'pkg.mod:Class.method')")
        except ValueError as e:
            return _fail(str(e))
        if a.cmd == "scope":
            _emit(sc)
        else:
            model = build_model(ex, scoped=sc, repo_name=a.name, max_nodes=a.max_nodes, repo=a.repo)
            out = Path(a.output)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
            print(f"wrote {out} ({len(model['nodes'])} nodes); check it with: python3 skills/mermaid-nesting-dolls/scripts/nesting_dolls.py check {out} --repo {a.repo}", file=sys.stderr)
        if a.strict and failed:
            for f in failed:
                print(f"parse failure: {f['path']}:{f['line']}: {f['error']}", file=sys.stderr)
            return EXIT_PARSE
        return EXIT_OK
    except StructureError as e:
        return _fail(str(e))


def _restrict(ex: dict, paths: set[str]) -> dict:
    """Keep only the parts of an extraction that live in `paths`; limits stay whole-repo plus a marker."""
    out = dict(ex)
    out["symbols"] = {k: v for k, v in ex["symbols"].items() if v["path"] in paths}
    out["edges"] = [e for e in ex["edges"] if e["path"] in paths]
    out["writes"] = [w for w in ex["writes"] if w["path"] in paths]
    out["state"] = {k: v for k, v in ex["state"].items() if v["path"] in paths}
    out["reads"] = {k: v for k, v in ex["reads"].items() if k in out["symbols"]}
    out["limits"] = {**ex["limits"], "restricted_to": sorted(paths)}
    return out


if __name__ == "__main__":
    raise SystemExit(main())
